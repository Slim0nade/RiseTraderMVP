#!/usr/bin/env python3
"""
check_loop_throughput.py — Daily loop-throughput monitor for RiseTrader.

Connects to PostgreSQL and rolls up the last 7 days (or a custom window via
--days) per symbol:

    signals_emitted   — decision_log rows in window (any decision_type with
                        a non-null symbol).  These are entries written by the
                        agent pipeline at signal-generation time.

                        SCHEMA NOTE: migration 015 (branch phase6/signal-tagging)
                        will add strategy_version / regime columns to decision_log.
                        Until that migration is applied, ALL decision_log rows are
                        counted regardless of decision_type, because the live
                        trading loop currently writes 'position_sizing' type rows
                        via the fund-manager agent.  When 015 lands, filter on
                        decision_type IN ('trade_intent', 'signal') for precision.

    signals_filtered  — decision_log rows where was_executed=false in window,
                        with top-5 rejection reason breakdown.  The rejection
                        reason is extracted from decision_data->>'reasoning' as a
                        short prefix (first 60 chars), because the live service
                        does not yet persist a dedicated 'rejection_reason' field
                        to the DB (it logs those to structlog stdout only).

    positions_opened  — trading_history rows in window, split by paper (simulation=true)
                        vs live (simulation=false).

    positions_resolved — trading_history rows in window where profit IS NOT NULL,
                         classified as:
                           tp_hit      — profit > 0
                           sl_hit      — profit < 0
                           watchdog_24h — not yet tracked in DB; will appear once
                                          A4 paper-watchdog branch lands and adds a
                                          close_reason column to trading_history.
                           other        — profit = 0 exactly (rare, breakeven close)

    realized_pnl      — SUM(profit) from closed paper-trade rows in window.
                        Live-account P&L is excluded from this rollup to avoid
                        conflating paper validation stats with real-money risk.
                        Set --include-live-pnl to include live account P&L.

ALERT:
    --alert-threshold N (default 10): if resolved trades < N for any symbol
    in the window, that symbol is added to a breach list.  Script exits with
    code 1 if any breaches exist, 0 otherwise.
    Empty symbol list → exit 0 (no false-positive on a paused system).

SYMBOLS:
    Loaded from LIVE_TRADING_SYMBOLS env var (comma-separated).  Fails loudly
    if the variable is not set.

Usage:
    python3 scripts/check_loop_throughput.py
    python3 scripts/check_loop_throughput.py --days 14 --alert-threshold 20
    python3 scripts/check_loop_throughput.py --include-live-pnl --symbols CrudeOIL
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# .env loading — mirrors what other scripts do (python-dotenv is in requirements)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path, override=False)  # don't override existing env
except ImportError:
    pass  # dotenv optional — env vars may already be set

# ---------------------------------------------------------------------------
# psycopg2
# ---------------------------------------------------------------------------
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: psycopg2-binary not installed. Run: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# DB connection helper — reads DATABASE_URL or individual PG* vars
# ---------------------------------------------------------------------------

def _build_pg_params() -> Dict[str, object]:
    """
    Build psycopg2 connection kwargs from the environment.

    Priority:
      1. DATABASE_URL (full connection string; strips the asyncpg driver prefix)
      2. Individual PGHOST / PGPORT / PGDATABASE / PGUSER / PGPASSWORD vars
         (same convention as dedupe_within_source.py and validate_post_import.py)
    """
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        # DATABASE_URL may use asyncpg driver: postgresql+asyncpg://...
        # psycopg2 needs plain postgresql://
        normalized = db_url.replace("postgresql+asyncpg://", "postgresql://")
        parsed = urlparse(normalized)
        params: Dict[str, object] = {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 5433,
            "dbname": (parsed.path or "/risetrader").lstrip("/"),
            "user": parsed.username or "postgres",
            "password": parsed.password or "",
        }
        return params

    # Fallback: individual env vars (mirrors dedupe_within_source.py pattern)
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": int(os.environ.get("PGPORT", "5433")),
        "dbname": os.environ.get("PGDATABASE", "risetrader"),
        "user": os.environ.get("PGUSER", "postgres"),
        "password": os.environ.get("PGPASSWORD", "risetrader2024"),
    }


def _connect() -> "psycopg2.connection":
    params = _build_pg_params()
    try:
        return psycopg2.connect(**params)
    except psycopg2.OperationalError as exc:
        print(f"ERROR: Cannot connect to PostgreSQL: {exc}", file=sys.stderr)
        print("  Check DATABASE_URL or PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD", file=sys.stderr)
        sys.exit(2)


# ---------------------------------------------------------------------------
# Symbol loading — from LIVE_TRADING_SYMBOLS env var; NO default fallback
# ---------------------------------------------------------------------------

def _load_symbols(override: Optional[List[str]] = None) -> List[str]:
    """
    Return the list of symbols to scan.

    If --symbols was passed on the CLI, use that list directly.
    Otherwise read LIVE_TRADING_SYMBOLS env var.  Fails loudly if neither is set.
    """
    if override:
        return override

    raw = os.environ.get("LIVE_TRADING_SYMBOLS", "").strip()
    if not raw:
        print(
            "ERROR: LIVE_TRADING_SYMBOLS env var is not set and --symbols was not provided.\n"
            "  Set LIVE_TRADING_SYMBOLS=CrudeOIL,USA500,GBPJPY. or pass --symbols on the CLI.",
            file=sys.stderr,
        )
        sys.exit(2)

    return [s.strip() for s in raw.split(",") if s.strip()]


# ---------------------------------------------------------------------------
# Query helpers — all indexed, no full-table scans on market_data
# ---------------------------------------------------------------------------

def _query_signals_emitted(cur, symbols: List[str], since: datetime, until: datetime) -> Dict[str, int]:
    """
    Count decision_log rows per symbol in the window.

    Index used: ix_decision_log_symbol_time (symbol, decided_at)
    """
    if not symbols:
        return {}
    cur.execute(
        """
        SELECT symbol, COUNT(*) AS cnt
          FROM decision_log
         WHERE symbol = ANY(%s)
           AND decided_at >= %s
           AND decided_at <  %s
         GROUP BY symbol
        """,
        (symbols, since, until),
    )
    return {row["symbol"]: row["cnt"] for row in cur.fetchall()}


def _query_signals_filtered(
    cur, symbols: List[str], since: datetime, until: datetime
) -> Dict[str, Dict[str, int]]:
    """
    For signals that were NOT executed, extract the top-5 rejection reasons.

    Rejection reason: decision_data->>'reasoning' first 60 chars (there is no
    dedicated rejection_reason field in the current schema — the live service
    writes rejection reasons only to structlog stdout).  When migration 015 lands,
    this query can be updated to GROUP BY decision_data->>'rejection_reason'.

    Index used: ix_decision_log_symbol_time + ix_decision_log_executed_time
    """
    if not symbols:
        return {}
    cur.execute(
        """
        SELECT symbol,
               LEFT(decision_data->>'reasoning', 60) AS reason_prefix,
               COUNT(*) AS cnt
          FROM decision_log
         WHERE symbol = ANY(%s)
           AND decided_at >= %s
           AND decided_at <  %s
           AND was_executed = false
         GROUP BY symbol, reason_prefix
         ORDER BY symbol, cnt DESC
        """,
        (symbols, since, until),
    )
    result: Dict[str, Dict[str, int]] = {}
    for row in cur.fetchall():
        sym = row["symbol"]
        if sym not in result:
            result[sym] = {}
        reason = (row["reason_prefix"] or "").strip() or "(no reasoning recorded)"
        result[sym][reason] = int(row["cnt"])
    return result


def _query_positions_opened(
    cur, symbols: List[str], since: datetime, until: datetime
) -> Dict[str, Dict[str, int]]:
    """
    Count trading_history rows (new position entries) per symbol in window.

    Splits paper (simulation=true) vs live (simulation=false).
    Index used: ix_trading_history_symbol_time (symbol, time)

    NOTE: trading_history stores every MT4 position event including closes.
    We filter to order_type IN ('BUY','SELL') to count entry-side events only.
    """
    if not symbols:
        return {}

    cur.execute(
        """
        SELECT symbol,
               simulation,
               COUNT(*) AS cnt
          FROM trading_history
         WHERE symbol = ANY(%s)
           AND time >= %s
           AND time <  %s
           AND order_type IN ('BUY', 'SELL')
         GROUP BY symbol, simulation
        """,
        (symbols, since, until),
    )
    result: Dict[str, Dict[str, int]] = {}
    for row in cur.fetchall():
        sym = row["symbol"]
        if sym not in result:
            result[sym] = {"paper": 0, "live": 0}
        key = "paper" if row["simulation"] else "live"
        result[sym][key] = int(row["cnt"])
    return result


def _query_positions_resolved(
    cur, symbols: List[str], since: datetime, until: datetime
) -> Dict[str, Dict[str, int]]:
    """
    Count CLOSED positions per symbol by resolution reason.

    The current schema has no 'close_reason' column (that will be added when
    A4 paper-watchdog branch merges).  We infer reason from profit sign:
        tp_hit      — profit > 0
        sl_hit      — profit < 0
        other       — profit = 0 exactly (breakeven; very rare)

    watchdog_24h is not yet tracked in the DB; the column will appear when
    trading_history gains a close_reason field in the A4 branch.

    Index used: ix_trading_history_symbol_time
    """
    if not symbols:
        return {}

    cur.execute(
        """
        SELECT symbol,
               CASE
                   WHEN profit > 0 THEN 'tp_hit'
                   WHEN profit < 0 THEN 'sl_hit'
                   ELSE              'other'
               END AS reason,
               COUNT(*) AS cnt
          FROM trading_history
         WHERE symbol = ANY(%s)
           AND time >= %s
           AND time <  %s
           AND profit IS NOT NULL
         GROUP BY symbol, reason
        """,
        (symbols, since, until),
    )
    result: Dict[str, Dict[str, int]] = {}
    for row in cur.fetchall():
        sym = row["symbol"]
        if sym not in result:
            result[sym] = {"tp_hit": 0, "sl_hit": 0, "watchdog_24h": 0, "other": 0}
        result[sym][row["reason"]] = int(row["cnt"])
    return result


def _query_pnl(
    cur,
    symbols: List[str],
    since: datetime,
    until: datetime,
    include_live: bool,
) -> Dict[str, float]:
    """
    Sum realized P&L for closed positions (profit IS NOT NULL) per symbol.

    By default, only paper positions (simulation=true) are included.
    Pass include_live=True to add live-account P&L to the total.

    Index used: ix_trading_history_symbol_time
    """
    if not symbols:
        return {}

    sim_filter = "" if include_live else "AND simulation = true"

    cur.execute(
        f"""
        SELECT symbol, COALESCE(SUM(profit), 0) AS total_pnl
          FROM trading_history
         WHERE symbol = ANY(%s)
           AND time >= %s
           AND time <  %s
           AND profit IS NOT NULL
           {sim_filter}
         GROUP BY symbol
        """,
        (symbols, since, until),
    )
    return {row["symbol"]: float(row["total_pnl"]) for row in cur.fetchall()}


# ---------------------------------------------------------------------------
# Data transformation helpers (pure functions — testable without DB)
# ---------------------------------------------------------------------------

def _top5_with_other(reason_counts: Dict[str, int]) -> List[Tuple[str, int]]:
    """
    Return top-5 reasons by count.  The long tail is collapsed into '...other'.

    Returns a list of (reason_label, count) pairs, sorted descending by count.
    """
    sorted_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)
    if len(sorted_reasons) <= 5:
        return sorted_reasons
    top5 = sorted_reasons[:5]
    other_count = sum(cnt for _, cnt in sorted_reasons[5:])
    return top5 + [("...other", other_count)]


def _total_resolved(resolved_by_reason: Dict[str, int]) -> int:
    """Sum all resolved counts across all reason buckets for one symbol."""
    return sum(resolved_by_reason.values())


def _check_breaches(
    symbols: List[str],
    resolved: Dict[str, Dict[str, int]],
    threshold: int,
) -> List[str]:
    """
    Return list of symbols whose total resolved trades fall below threshold.

    Symbols with zero data (no rows at all) ARE considered breaches if the
    system is expected to be running.  An empty symbols list → no breaches.
    """
    breaches: List[str] = []
    for sym in symbols:
        total = _total_resolved(resolved.get(sym, {}))
        if total < threshold:
            breaches.append(sym)
    return breaches


# ---------------------------------------------------------------------------
# Formatting helpers (no external deps)
# ---------------------------------------------------------------------------

_COL_WIDTH_SYMBOL = 12
_COL_WIDTH_NUMBER = 8
_COL_WIDTH_WIDE   = 55


def _hr(width: int = 100) -> str:
    return "-" * width


def _header(title: str) -> str:
    return f"\n{'=' * 100}\n  {title}\n{'=' * 100}"


def _fmt_pnl(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}"


def _print_rollup(
    symbols: List[str],
    window_days: int,
    since: datetime,
    until: datetime,
    signals_emitted: Dict[str, int],
    signals_filtered_by_symbol: Dict[str, Dict[str, int]],
    positions_opened: Dict[str, Dict[str, int]],
    positions_resolved: Dict[str, Dict[str, int]],
    pnl: Dict[str, float],
    breaches: List[str],
    threshold: int,
    include_live_pnl: bool,
) -> None:
    """Pretty-print the full rollup to stdout."""
    print(_header(f"RiseTrader Loop Throughput Report — Last {window_days} Days"))
    print(f"  Window : {since.strftime('%Y-%m-%d %H:%M UTC')} → {until.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"  Alert threshold: {threshold} resolved trades / symbol / window")
    print(f"  Live P&L included: {'yes' if include_live_pnl else 'no (paper only)'}")

    # ── Section 1: Signal funnel ──────────────────────────────────────────────
    print(_header("1. Signal Funnel  (decision_log)"))
    print(
        f"  {'Symbol':<{_COL_WIDTH_SYMBOL}}  {'Emitted':>{_COL_WIDTH_NUMBER}}  "
        f"{'Filtered':>{_COL_WIDTH_NUMBER}}  {'Execute%':>{_COL_WIDTH_NUMBER}}"
    )
    print("  " + _hr(48))
    for sym in symbols:
        emitted  = signals_emitted.get(sym, 0)
        filtered = sum(signals_filtered_by_symbol.get(sym, {}).values())
        executed = emitted - filtered
        pct      = f"{100 * executed / emitted:.1f}%" if emitted > 0 else " —"
        print(
            f"  {sym:<{_COL_WIDTH_SYMBOL}}  {emitted:>{_COL_WIDTH_NUMBER}}  "
            f"{filtered:>{_COL_WIDTH_NUMBER}}  {pct:>{_COL_WIDTH_NUMBER}}"
        )

    # ── Section 2: Filter reason breakdown ───────────────────────────────────
    print(_header("2. Filter Reason Breakdown  (top 5 per symbol)"))
    for sym in symbols:
        reasons = signals_filtered_by_symbol.get(sym, {})
        if not reasons:
            print(f"  {sym}: no filtered signals recorded")
            continue
        top5 = _top5_with_other(reasons)
        print(f"\n  {sym}:")
        for label, cnt in top5:
            truncated = label[:52] + "…" if len(label) > 52 else label
            print(f"    {cnt:>5}  {truncated}")

    # ── Section 3: Positions opened ───────────────────────────────────────────
    print(_header("3. Positions Opened  (trading_history BUY/SELL entries)"))
    print(
        f"  {'Symbol':<{_COL_WIDTH_SYMBOL}}  {'Paper':>{_COL_WIDTH_NUMBER}}  "
        f"{'Live':>{_COL_WIDTH_NUMBER}}  {'Total':>{_COL_WIDTH_NUMBER}}"
    )
    print("  " + _hr(44))
    for sym in symbols:
        opened = positions_opened.get(sym, {})
        paper  = opened.get("paper", 0)
        live   = opened.get("live", 0)
        print(
            f"  {sym:<{_COL_WIDTH_SYMBOL}}  {paper:>{_COL_WIDTH_NUMBER}}  "
            f"{live:>{_COL_WIDTH_NUMBER}}  {paper + live:>{_COL_WIDTH_NUMBER}}"
        )

    # ── Section 4: Positions resolved ─────────────────────────────────────────
    print(_header("4. Positions Resolved  (trading_history rows with profit IS NOT NULL)"))
    note = ("  NOTE: watchdog_24h not yet tracked in DB (A4 paper-watchdog branch pending).\n"
            "        sl_hit/tp_hit inferred from profit sign; manual_close not yet distinguished.")
    print(note)
    print(
        f"\n  {'Symbol':<{_COL_WIDTH_SYMBOL}}  {'tp_hit':>{_COL_WIDTH_NUMBER}}  "
        f"{'sl_hit':>{_COL_WIDTH_NUMBER}}  {'watchdog':>{_COL_WIDTH_NUMBER}}  "
        f"{'other':>{_COL_WIDTH_NUMBER}}  {'TOTAL':>{_COL_WIDTH_NUMBER}}"
    )
    print("  " + _hr(64))
    for sym in symbols:
        res     = positions_resolved.get(sym, {})
        tp      = res.get("tp_hit", 0)
        sl      = res.get("sl_hit", 0)
        wd      = res.get("watchdog_24h", 0)
        other   = res.get("other", 0)
        total   = tp + sl + wd + other
        breach  = " << BREACH" if sym in breaches else ""
        print(
            f"  {sym:<{_COL_WIDTH_SYMBOL}}  {tp:>{_COL_WIDTH_NUMBER}}  "
            f"{sl:>{_COL_WIDTH_NUMBER}}  {wd:>{_COL_WIDTH_NUMBER}}  "
            f"{other:>{_COL_WIDTH_NUMBER}}  {total:>{_COL_WIDTH_NUMBER}}{breach}"
        )

    # ── Section 5: Realized P&L ───────────────────────────────────────────────
    pnl_label = "Realized P&L (paper+live)" if include_live_pnl else "Realized P&L (paper only)"
    print(_header(f"5. {pnl_label}"))
    print(
        f"  {'Symbol':<{_COL_WIDTH_SYMBOL}}  {'P&L (USD)':>{_COL_WIDTH_NUMBER + 4}}"
    )
    print("  " + _hr(28))
    for sym in symbols:
        val = pnl.get(sym, 0.0)
        print(f"  {sym:<{_COL_WIDTH_SYMBOL}}  {_fmt_pnl(val):>{_COL_WIDTH_NUMBER + 4}}")

    # ── Section 6: Breach summary ─────────────────────────────────────────────
    print("\n" + "=" * 100)
    if not breaches:
        print(f"  PASS: All {len(symbols)} symbol(s) met the {threshold}-trade threshold.")
    else:
        for sym in breaches:
            total = _total_resolved(positions_resolved.get(sym, {}))
            print(f"  BREACH: {sym}  resolved={total}  threshold={threshold}")
        print(f"\n  {len(breaches)} BREACH(ES) detected. Investigate signal funnel above.")
    print("=" * 100)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RiseTrader daily loop-throughput check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 scripts/check_loop_throughput.py\n"
            "  python3 scripts/check_loop_throughput.py --days 14 --alert-threshold 20\n"
            "  python3 scripts/check_loop_throughput.py --symbols CrudeOIL --include-live-pnl\n"
        ),
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Lookback window in days (default: 7)",
    )
    parser.add_argument(
        "--alert-threshold",
        type=int,
        default=10,
        help="Minimum resolved trades per symbol per window (default: 10). "
             "Symbols below this threshold trigger exit code 1.",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated symbol list override (default: read LIVE_TRADING_SYMBOLS env var)",
    )
    parser.add_argument(
        "--include-live-pnl",
        action="store_true",
        default=False,
        help="Include live-account P&L in the P&L column (default: paper-only)",
    )
    return parser.parse_args(argv)


def run(argv: Optional[List[str]] = None) -> int:
    """
    Entry point.  Returns exit code (0=pass, 1=breach, 2=error).

    Separated from __main__ so tests can call run([...]) directly.
    """
    args = _parse_args(argv)

    symbol_override = (
        [s.strip() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else None
    )
    symbols = _load_symbols(symbol_override)

    if not symbols:
        print("No symbols configured. System appears paused — exiting 0.", file=sys.stderr)
        return 0

    until = datetime.now(timezone.utc)
    since = until - timedelta(days=args.days)

    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            signals_emitted          = _query_signals_emitted(cur, symbols, since, until)
            signals_filtered_by_sym  = _query_signals_filtered(cur, symbols, since, until)
            positions_opened         = _query_positions_opened(cur, symbols, since, until)
            positions_resolved       = _query_positions_resolved(cur, symbols, since, until)
            pnl                      = _query_pnl(cur, symbols, since, until, args.include_live_pnl)
    finally:
        conn.close()

    breaches = _check_breaches(symbols, positions_resolved, args.alert_threshold)

    _print_rollup(
        symbols=symbols,
        window_days=args.days,
        since=since,
        until=until,
        signals_emitted=signals_emitted,
        signals_filtered_by_symbol=signals_filtered_by_sym,
        positions_opened=positions_opened,
        positions_resolved=positions_resolved,
        pnl=pnl,
        breaches=breaches,
        threshold=args.alert_threshold,
        include_live_pnl=args.include_live_pnl,
    )

    return 1 if breaches else 0


if __name__ == "__main__":
    sys.exit(run())
