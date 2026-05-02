"""
Integration tests for check_loop_throughput.py — DB-backed.

These tests hit the real PostgreSQL database (localhost:5433).
They are intentionally NOT mocked — per RiseTrader ABSOLUTE RULES:
  "NEVER use unittest.mock / MagicMock for MT4/MCP/market data interactions."

If the DB is unreachable (e.g. in CI without the compose stack), each test
skips with a clear reason.  No mock fallback is provided.

What these tests verify:
  1. The script connects to the real DB without error.
  2. All query helpers return correctly typed results.
  3. The breach check logic is consistent with the data returned.
  4. run() exits with code 0 or 1 (never crashes) on the live DB.
  5. The LIVE_TRADING_SYMBOLS env var is read correctly.
"""
import os
import sys
import pytest
from datetime import datetime, timedelta, timezone

# Add project root to sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Fixture: try to connect to the real DB; skip all tests if unavailable
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_conn():
    """
    Return a live psycopg2 connection to the test DB.

    Skips the whole module if the DB is not reachable.
    Does NOT mock anything — uses the real DB pointed to by DATABASE_URL.
    """
    try:
        # Load .env so DATABASE_URL is available
        try:
            from dotenv import load_dotenv
            env_path = os.path.join(_PROJECT_ROOT, ".env")
            if os.path.exists(env_path):
                load_dotenv(env_path, override=False)
        except ImportError:
            pass

        from scripts.check_loop_throughput import _connect
        conn = _connect()
        yield conn
        conn.close()
    except SystemExit:
        pytest.skip(reason="test DB unavailable — cannot connect to PostgreSQL")


@pytest.fixture(scope="module")
def window():
    """Return a 7-day window anchored to now."""
    until = datetime.now(timezone.utc)
    since = until - timedelta(days=7)
    return since, until


@pytest.fixture(scope="module")
def symbols():
    """Return the live trading symbols from env var, or skip if not set."""
    # Load .env first so LIVE_TRADING_SYMBOLS is populated
    try:
        from dotenv import load_dotenv
        env_path = os.path.join(_PROJECT_ROOT, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path, override=False)
    except ImportError:
        pass

    raw = os.environ.get("LIVE_TRADING_SYMBOLS", "").strip()
    if not raw:
        pytest.skip(reason="LIVE_TRADING_SYMBOLS not set — cannot determine symbol list")
    return [s.strip() for s in raw.split(",") if s.strip()]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSignalsEmittedQuery:
    def test_returns_dict_keyed_by_symbol(self, db_conn, symbols, window):
        from psycopg2.extras import RealDictCursor
        from scripts.check_loop_throughput import _query_signals_emitted
        since, until = window
        with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            result = _query_signals_emitted(cur, symbols, since, until)
        # Result is a dict; keys are symbol strings; values are non-negative ints
        assert isinstance(result, dict)
        for sym, cnt in result.items():
            assert isinstance(sym, str), f"key {sym!r} is not a string"
            assert isinstance(cnt, int), f"count for {sym} is not int: {cnt!r}"
            assert cnt >= 0

    def test_empty_symbol_list_returns_empty(self, db_conn, window):
        from psycopg2.extras import RealDictCursor
        from scripts.check_loop_throughput import _query_signals_emitted
        since, until = window
        with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            result = _query_signals_emitted(cur, [], since, until)
        assert result == {}


class TestSignalsFilteredQuery:
    def test_returns_dict_with_correct_structure(self, db_conn, symbols, window):
        from psycopg2.extras import RealDictCursor
        from scripts.check_loop_throughput import _query_signals_filtered
        since, until = window
        with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            result = _query_signals_filtered(cur, symbols, since, until)
        assert isinstance(result, dict)
        for sym, reasons in result.items():
            assert isinstance(sym, str)
            assert isinstance(reasons, dict)
            for reason, cnt in reasons.items():
                assert isinstance(reason, str)
                assert isinstance(cnt, int)
                assert cnt > 0

    def test_empty_symbol_list_returns_empty(self, db_conn, window):
        from psycopg2.extras import RealDictCursor
        from scripts.check_loop_throughput import _query_signals_filtered
        since, until = window
        with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            result = _query_signals_filtered(cur, [], since, until)
        assert result == {}


class TestPositionsOpenedQuery:
    def test_returns_paper_live_split(self, db_conn, symbols, window):
        from psycopg2.extras import RealDictCursor
        from scripts.check_loop_throughput import _query_positions_opened
        since, until = window
        with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            result = _query_positions_opened(cur, symbols, since, until)
        assert isinstance(result, dict)
        for sym, counts in result.items():
            assert "paper" in counts or "live" in counts, (
                f"symbol {sym} missing paper/live keys: {counts}"
            )
            for key in counts:
                assert key in ("paper", "live"), f"unexpected key {key!r}"
                assert counts[key] >= 0

    def test_empty_symbol_list_returns_empty(self, db_conn, window):
        from psycopg2.extras import RealDictCursor
        from scripts.check_loop_throughput import _query_positions_opened
        since, until = window
        with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            result = _query_positions_opened(cur, [], since, until)
        assert result == {}


class TestPositionsResolvedQuery:
    def test_returns_reason_buckets(self, db_conn, symbols, window):
        from psycopg2.extras import RealDictCursor
        from scripts.check_loop_throughput import _query_positions_resolved
        since, until = window
        with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            result = _query_positions_resolved(cur, symbols, since, until)
        assert isinstance(result, dict)
        valid_reasons = {"tp_hit", "sl_hit", "watchdog_24h", "other"}
        for sym, buckets in result.items():
            for reason, cnt in buckets.items():
                assert reason in valid_reasons, f"{sym}: unexpected reason {reason!r}"
                assert isinstance(cnt, int) and cnt >= 0

    def test_empty_symbol_list_returns_empty(self, db_conn, window):
        from psycopg2.extras import RealDictCursor
        from scripts.check_loop_throughput import _query_positions_resolved
        since, until = window
        with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            result = _query_positions_resolved(cur, [], since, until)
        assert result == {}


class TestPnlQuery:
    def test_returns_float_per_symbol(self, db_conn, symbols, window):
        from psycopg2.extras import RealDictCursor
        from scripts.check_loop_throughput import _query_pnl
        since, until = window
        with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            result = _query_pnl(cur, symbols, since, until, include_live=False)
        assert isinstance(result, dict)
        for sym, val in result.items():
            assert isinstance(val, float), f"P&L for {sym} is not float: {val!r}"

    def test_include_live_does_not_crash(self, db_conn, symbols, window):
        from psycopg2.extras import RealDictCursor
        from scripts.check_loop_throughput import _query_pnl
        since, until = window
        with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            result = _query_pnl(cur, symbols, since, until, include_live=True)
        assert isinstance(result, dict)

    def test_empty_symbol_list_returns_empty(self, db_conn, window):
        from psycopg2.extras import RealDictCursor
        from scripts.check_loop_throughput import _query_pnl
        since, until = window
        with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            result = _query_pnl(cur, [], since, until, include_live=False)
        assert result == {}


class TestRunEndToEnd:
    """
    Run the full script via run() against the live DB.

    Requires db_conn to be available so the test skips cleanly when DB is
    not reachable (rather than crashing with SystemExit(2)).

    Verifies:
    - Script completes without exception (no crash)
    - Returns exit code 0 or 1 only
    - With threshold=0, always exits 0 (every symbol passes)
    - With threshold=9999, always exits 1 (no system can produce 9999 trades/week)
    """

    def test_run_exits_0_or_1(self, db_conn, symbols):
        """Script must not crash and must return a valid exit code."""
        from scripts.check_loop_throughput import run
        sym_list = ",".join(symbols)
        exit_code = run(["--symbols", sym_list, "--alert-threshold", "10"])
        assert exit_code in (0, 1), f"Unexpected exit code: {exit_code}"

    def test_run_threshold_0_always_passes(self, db_conn, symbols):
        """threshold=0 means every symbol is fine → exit code 0."""
        from scripts.check_loop_throughput import run
        sym_list = ",".join(symbols)
        exit_code = run(["--symbols", sym_list, "--alert-threshold", "0"])
        assert exit_code == 0, (
            f"Expected 0 with threshold=0 but got {exit_code}"
        )

    def test_run_extreme_threshold_exits_1(self, db_conn, symbols):
        """threshold=9999 → all symbols breach → exit code 1."""
        from scripts.check_loop_throughput import run
        sym_list = ",".join(symbols)
        exit_code = run(["--symbols", sym_list, "--alert-threshold", "9999"])
        assert exit_code == 1, (
            f"Expected 1 with threshold=9999 but got {exit_code}"
        )
