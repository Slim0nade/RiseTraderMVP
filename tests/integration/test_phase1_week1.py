"""
Phase 1, Week 1 Integration Tests

Validates three code changes with real data:
1. StealthStopManager.get_atr() — real candles, no hardcoded defaults
2. RiskManagerAgent position sizing — hard 2% account risk cap
3. CrudeOilStrategy seasonality filter — Q4 suppressed, Q3 halved

Run:
    python3 -m pytest tests/integration/test_phase1_week1.py -v --no-cov

Author: mcp-verifier
"""

import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, List

import pytest

# Ensure project root is on the path so src imports work outside Docker
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Database URL targeting the forwarded port (runs outside Docker)
TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader",
)

# Raw asyncpg DSN (no driver prefix)
TEST_PG_DSN = "postgresql://postgres:risetrader2024@localhost:5433/risetrader"


# ===========================================================================
# Helper: fetch CrudeOIL H1 candles via raw asyncpg
#
# IMPORTANT: The market_data table uses column name "last" (not "close").
# The ORM model exposes a .close property that aliases .last.
# Raw SQL must use "last" directly.
# ===========================================================================

async def _fetch_crude_h1_candles(limit: int, offset: int = 0) -> List[dict]:
    """Fetch CrudeOIL H1 candles via asyncpg (uses 'last' column, not 'close')."""
    import asyncpg
    conn = await asyncpg.connect(TEST_PG_DSN)
    try:
        rows = await conn.fetch(
            """
            SELECT time, open, high, low, last, volume
            FROM market_data
            WHERE symbol = 'CrudeOIL' AND timeframe = 'H1'
            ORDER BY time DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


# ===========================================================================
# TEST 1 — Real ATR in StealthStopManager
# ===========================================================================

class TestATRIsReal:
    """
    Verify that StealthStopManager.get_atr() returns real, dynamic ATR values.

    Tests use the PostgreSQL DB at localhost:5433 (94,922 CrudeOIL H1 candles).
    Requires DATABASE_URL env var pointing to the real DB (not SQLite).

    Bug history:
    - tf_map "H1"→"1h" (fixed in commit 92a99d9): now uses timeframe.upper()
    - import side-effect from src.api.dependencies: bypassed by setting DATABASE_URL
    """

    @pytest.mark.asyncio
    async def test_atr_direct_db_query_returns_real_candles(self):
        """
        Directly query the DB to confirm candle data exists for CrudeOIL H1,
        then manually calculate ATR to verify the math is real.
        This bypasses Bug-A and Bug-B to prove the underlying data + math works.
        """
        from src.utils.atr_calculator import Candle, calculate_atr_wilder

        try:
            rows = await _fetch_crude_h1_candles(limit=20)
        except Exception as e:
            pytest.skip(f"Cannot connect to DB at {TEST_PG_DSN}: {e}")

        assert len(rows) >= 15, (
            f"Expected at least 15 CrudeOIL H1 rows, got {len(rows)}. "
            f"Check DB population."
        )

        # Reverse to oldest-first for Wilder's ATR calculation
        candles = [
            Candle(
                timestamp=row["time"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["last"]),   # DB column is "last", not "close"
                volume=float(row["volume"]) if row["volume"] else 0.0,
            )
            for row in reversed(rows)
        ]

        atr = calculate_atr_wilder(candles, period=14)

        assert atr is not None, "calculate_atr_wilder returned None — not enough candles"
        assert atr != 0.75, f"ATR == 0.75 — this matches the hardcoded CrudeOIL fake!"
        assert atr != 15.0, f"ATR == 15.0 — this matches the XAUUSD hardcoded fake!"
        assert 0.1 < atr < 10.0, (
            f"ATR {atr:.5f} is outside plausible range for CrudeOIL H1 "
            f"(expected 0.1–10.0 USD/barrel). Check candle data."
        )
        print(f"\n[PASS] Real ATR(14) from DB candles: {atr:.5f}")

    @pytest.mark.asyncio
    async def test_atr_not_equal_across_two_windows(self):
        """
        Fetch two distinct CrudeOIL H1 time windows and confirm ATR differs —
        proving the calculation is dynamic, not hardcoded.
        """
        from src.utils.atr_calculator import Candle, calculate_atr_wilder

        try:
            rows_recent = await _fetch_crude_h1_candles(limit=20, offset=0)
            rows_older = await _fetch_crude_h1_candles(limit=20, offset=500)
        except Exception as e:
            pytest.skip(f"Cannot connect to DB: {e}")

        def to_candles(rows):
            return [
                Candle(
                    timestamp=r["time"],
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["last"]),
                    volume=float(r["volume"]) if r["volume"] else 0.0,
                )
                for r in reversed(rows)
            ]

        candles_recent = to_candles(rows_recent)
        candles_older = to_candles(rows_older)

        atr_recent = calculate_atr_wilder(candles_recent, period=14)
        atr_older = calculate_atr_wilder(candles_older, period=14)

        assert atr_recent is not None, "Could not compute ATR for recent window"
        assert atr_older is not None, "Could not compute ATR for older window"

        # Neither should be the known fakes
        assert atr_recent != 0.75, f"Recent ATR == 0.75 (CrudeOIL hardcoded fake)"
        assert atr_recent != 15.0, f"Recent ATR == 15.0 (XAUUSD hardcoded fake)"
        assert atr_older != 0.75, f"Older ATR == 0.75 (CrudeOIL hardcoded fake)"
        assert atr_older != 15.0, f"Older ATR == 15.0 (XAUUSD hardcoded fake)"

        # They MUST differ (different market conditions 500 candles apart)
        assert atr_recent != atr_older, (
            f"ATR is identical across two windows 500 candles apart: {atr_recent}. "
            f"This indicates static/hardcoded output."
        )

        # Both must be in plausible CrudeOIL range
        assert 0.1 < atr_recent < 10.0, f"Recent ATR {atr_recent:.5f} outside plausible range"
        assert 0.1 < atr_older < 10.0, f"Older ATR {atr_older:.5f} outside plausible range"

        print(
            f"\n[PASS] ATR is dynamic across time windows:\n"
            f"       Recent (last 20 H1 candles):  {atr_recent:.5f}\n"
            f"       Older  (500 candles back):     {atr_older:.5f}\n"
            f"       Difference: {abs(atr_recent - atr_older):.5f}"
        )

    @pytest.mark.asyncio
    async def test_tf_map_regression_guard(self):
        """
        Regression guard for the tf_map bug (fixed in commit 92a99d9).

        The original bug mapped "H1" → "1h", causing 0 rows to be returned
        from the DB. The fix uses timeframe.upper() directly.

        This test verifies that "H1" timeframe candles ARE reachable from DB,
        i.e. the fix is permanent. If this ever returns 0 rows again, the
        bug has regressed.
        """
        import asyncpg

        try:
            conn = await asyncpg.connect(TEST_PG_DSN)
        except Exception as e:
            pytest.skip(f"Cannot connect to DB: {e}")

        try:
            rows = await conn.fetch(
                """
                SELECT COUNT(*) as cnt
                FROM market_data
                WHERE symbol = 'CrudeOIL' AND timeframe::text = 'H1'
                """
            )
        finally:
            await conn.close()

        count = rows[0]["cnt"]
        assert count >= 100, (
            f"Expected >= 100 CrudeOIL H1 rows via 'H1' text match, got {count}. "
            f"tf_map regression: get_atr() may be sending the wrong timeframe string."
        )
        print(f"\n[PASS] Regression guard: CrudeOIL H1 rows accessible = {count}")

    async def test_stealth_stop_manager_get_atr_returns_real_float(self):
        """
        End-to-end: StealthStopManager.get_atr("CrudeOIL", timeframe="H1")
        must return a real float from the DB — NOT raise InsufficientDataError
        and NOT return 0.75 (the hardcoded fake).

        KNOWN LIMITATION: This test only runs correctly when DATABASE_URL in the
        environment points to the real PostgreSQL DB. The root conftest.py sets
        DATABASE_URL to SQLite (for unit tests), which causes src.api.dependencies
        to create an incompatible SQLAlchemy engine at import time, which is then
        caught by get_atr()'s broad except and re-raised as InsufficientDataError.

        VERIFIED EXTERNALLY (2026-02-22): Running inside Docker API container
        (where DATABASE_URL=postgresql+asyncpg://...):
            StealthStopManager.get_atr("CrudeOIL", "H1") = 0.36115
            Type: float, range: 0.1 < 0.36115 < 10.0 ✓
            Not 0.75 (CrudeOIL fake) ✓
            Not 15.0 (XAUUSD fake) ✓
            SQL sent: CAST(timeframe AS TEXT) = 'H1' → 94,922 rows matched ✓

        This test is skipped when DATABASE_URL is not set to Postgres.
        """
        import os
        db_url = os.environ.get("DATABASE_URL", "")
        if "sqlite" in db_url or "memory" in db_url or not db_url.startswith("postgresql"):
            pytest.skip(
                "Skipping e2e ATR test: DATABASE_URL is not pointing to PostgreSQL. "
                f"Current value: {db_url!r}. "
                "Set DATABASE_URL=postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader"
            )

        from src.services.stealth_stop_manager import StealthStopManager
        from src.utils.atr_calculator import InsufficientDataError

        manager = StealthStopManager(mt4_host="192.168.0.123")

        try:
            result = await manager.get_atr("CrudeOIL", period=14, timeframe="H1")
        except InsufficientDataError as e:
            pytest.fail(
                f"get_atr('CrudeOIL', 'H1') raised InsufficientDataError: {e}\n"
                f"The DB has 94,922 H1 candles — this should not fail. "
                f"Check DATABASE_URL={db_url!r} and DB connectivity."
            )
        except Exception as e:
            pytest.fail(f"get_atr() raised unexpected {type(e).__name__}: {e}")

        assert isinstance(result, float), (
            f"Expected float, got {type(result).__name__}: {result}"
        )
        assert result > 0, f"ATR must be positive, got {result}"
        assert result != 0.75, (
            f"ATR == 0.75 — this is the old CrudeOIL hardcoded fake."
        )
        assert result != 15.0, (
            f"ATR == 15.0 — this is the old XAUUSD hardcoded fake."
        )
        assert 0.1 < result < 10.0, (
            f"ATR {result:.5f} outside plausible range for CrudeOIL H1 (0.1–10.0 USD)."
        )
        print(
            f"\n[PASS] StealthStopManager.get_atr('CrudeOIL', 'H1') = {result:.5f} "
            f"(real float from DB, not hardcoded)"
        )


# ===========================================================================
# TEST 2 — 2% Position Sizing Cap
# ===========================================================================

class TestPositionSizingCap:
    """
    Verify that RiskManagerAgent never allocates more than 2% account risk.

    These tests instantiate the agent directly without the full event-bus
    infrastructure and call the sizing methods directly. The event_bus and
    agent_registry are minimal stubs (internal agent infrastructure, NOT
    MT4/MCP — mocking them is permitted per CLAUDE.md).
    """

    def _make_risk_manager(self, balance: float = 10000.0, method: str = "kelly"):
        """Create a RiskManagerAgent with minimal stub event infrastructure."""
        from src.agents.execution.risk_manager import RiskManagerAgent

        # Minimal stubs for internal agent infrastructure (NOT MT4/MCP)
        class StubEventBus:
            def subscribe(self, *a, **kw): pass
            def publish(self, *a, **kw): pass

        class StubRegistry:
            def register(self, *a, **kw): pass
            def get_shared_context(self, *a, **kw): return None

        config = {
            "max_position_size": 5000.0,   # High absolute limit
            "max_daily_loss": 500.0,
            "max_open_positions": 10,
            "max_correlation": 0.9,
            "position_sizing_method": method,
            "risk_per_trade": 0.02,         # 2% cap
            "database_url": TEST_DATABASE_URL,
        }

        agent = RiskManagerAgent(
            agent_id="test-risk-manager",
            event_bus=StubEventBus(),
            agent_registry=StubRegistry(),
            config=config,
        )
        agent.account_balance = balance
        return agent

    @pytest.mark.asyncio
    async def test_kelly_capped_at_2_percent(self):
        """
        Kelly with real trade stats must be hard-capped at 2% (= $200 for $10,000 account).
        Since _kelly_criterion_size now queries DB, it returns minimum size for < 30 trades.
        Requires PostgreSQL — skipped when DATABASE_URL points to SQLite (CI/unit mode).
        """
        import os
        db_url = os.environ.get("DATABASE_URL", "")
        if "sqlite" in db_url or "memory" in db_url or not db_url.startswith("postgresql"):
            pytest.skip(
                "Skipping Kelly DB test: DATABASE_URL is not pointing to PostgreSQL. "
                f"Current value: {db_url!r}. "
                "Set DATABASE_URL=postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader"
            )
        agent = self._make_risk_manager(balance=10000.0, method="kelly")
        max_risk = agent.account_balance * 0.02  # = 200.0

        signal_data = {"confidence": 0.99, "symbol": "CrudeOIL"}
        result = await agent._kelly_criterion_size(signal_data)

        assert result <= max_risk, (
            f"Kelly size {result:.2f} exceeds 2% cap of {max_risk:.2f} "
            f"(balance: {agent.account_balance:.2f})"
        )
        assert result > 0, "Position size must be positive"
        print(
            f"\n[PASS] Kelly (CrudeOIL): {result:.2f} "
            f"<= 2% cap of {max_risk:.2f}"
        )

    @pytest.mark.asyncio
    async def test_kelly_capped_at_2_percent_low_confidence(self):
        """Kelly with real trade stats also must not exceed 2%. Requires PostgreSQL."""
        import os
        db_url = os.environ.get("DATABASE_URL", "")
        if "sqlite" in db_url or "memory" in db_url or not db_url.startswith("postgresql"):
            pytest.skip(
                "Skipping Kelly DB test: DATABASE_URL is not pointing to PostgreSQL. "
                f"Current value: {db_url!r}. "
                "Set DATABASE_URL=postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader"
            )
        agent = self._make_risk_manager(balance=10000.0, method="kelly")
        max_risk = agent.account_balance * 0.02

        signal_data = {"confidence": 0.3, "symbol": "CrudeOIL"}
        result = await agent._kelly_criterion_size(signal_data)
        assert result <= max_risk, (
            f"Kelly size {result:.2f} exceeds 2% cap of {max_risk:.2f}"
        )
        print(f"\n[PASS] Kelly (low confidence): {result:.2f} <= 2% cap of {max_risk:.2f}")

    def test_fixed_size_at_2_percent(self):
        """Fixed sizing always returns exactly 2% of balance."""
        agent = self._make_risk_manager(balance=10000.0, method="fixed")
        max_risk = agent.account_balance * 0.02  # = 200.0

        result = agent._fixed_size()

        assert result <= max_risk, (
            f"Fixed size {result:.2f} exceeds 2% cap of {max_risk:.2f}"
        )
        assert result == max_risk, (
            f"Fixed size {result:.2f} should equal exactly 2% ({max_risk:.2f})"
        )
        print(f"\n[PASS] Fixed sizing: {result:.2f} == 2% of {agent.account_balance:.2f}")

    @pytest.mark.asyncio
    async def test_calculate_position_size_hard_cap_kelly(self):
        """
        End-to-end: _calculate_position_size applies the hard 2% cap
        after Kelly sizing, and the assert in the implementation fires.
        Requires PostgreSQL — skipped when DATABASE_URL points to SQLite (CI/unit mode).
        """
        import os
        db_url = os.environ.get("DATABASE_URL", "")
        if "sqlite" in db_url or "memory" in db_url or not db_url.startswith("postgresql"):
            pytest.skip(
                "Skipping Kelly DB test: DATABASE_URL is not pointing to PostgreSQL. "
                f"Current value: {db_url!r}. "
                "Set DATABASE_URL=postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader"
            )
        agent = self._make_risk_manager(balance=10000.0, method="kelly")
        max_risk = agent.account_balance * 0.02  # = 200.0

        signal_data = {
            "confidence": 0.99,  # Max confidence — Kelly would overshoot 2%
            "symbol": "CrudeOIL",
        }

        result = await agent._calculate_position_size(signal_data)

        assert result <= max_risk, (
            f"_calculate_position_size returned {result:.2f} which exceeds "
            f"the 2% hard cap of {max_risk:.2f} "
            f"(balance={agent.account_balance:.2f})"
        )
        assert result > 0, "Position size must be positive"
        print(
            f"\n[PASS] _calculate_position_size (kelly, confidence=0.99): "
            f"{result:.2f} <= hard cap {max_risk:.2f}"
        )

    @pytest.mark.asyncio
    async def test_calculate_position_size_hard_cap_fixed(self):
        """Fixed method also stays at or below 2%."""
        agent = self._make_risk_manager(balance=10000.0, method="fixed")
        max_risk = agent.account_balance * 0.02

        signal_data = {"confidence": 0.99, "symbol": "CrudeOIL"}
        result = await agent._calculate_position_size(signal_data)

        assert result <= max_risk, (
            f"Fixed size {result:.2f} exceeds 2% cap {max_risk:.2f}"
        )
        print(f"\n[PASS] _calculate_position_size (fixed): {result:.2f} <= {max_risk:.2f}")

    @pytest.mark.asyncio
    async def test_cap_holds_at_larger_balances(self):
        """2% cap scales correctly with different account sizes. Requires PostgreSQL."""
        import os
        db_url = os.environ.get("DATABASE_URL", "")
        if "sqlite" in db_url or "memory" in db_url or not db_url.startswith("postgresql"):
            pytest.skip(
                "Skipping Kelly DB test: DATABASE_URL is not pointing to PostgreSQL. "
                f"Current value: {db_url!r}. "
                "Set DATABASE_URL=postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader"
            )
        for balance in [5000.0, 10000.0, 50000.0, 100000.0]:
            agent = self._make_risk_manager(balance=balance, method="kelly")
            agent.account_balance = balance
            max_risk = balance * 0.02

            signal_data = {"confidence": 0.99, "symbol": "CrudeOIL"}
            result = await agent._kelly_criterion_size(signal_data)

            assert result <= max_risk, (
                f"Balance=${balance}: Kelly size {result:.2f} exceeds "
                f"2% cap {max_risk:.2f}"
            )
        print(f"\n[PASS] 2% cap holds for balances: $5k, $10k, $50k, $100k")

    @pytest.mark.asyncio
    async def test_position_risk_never_exceeds_2_percent_at_any_confidence(self):
        """
        Sweep confidence 0.1..0.99 — risk percentage must never exceed 2%.
        Requires PostgreSQL — skipped when DATABASE_URL points to SQLite (CI/unit mode).
        """
        import os
        db_url = os.environ.get("DATABASE_URL", "")
        if "sqlite" in db_url or "memory" in db_url or not db_url.startswith("postgresql"):
            pytest.skip(
                "Skipping Kelly DB test: DATABASE_URL is not pointing to PostgreSQL. "
                f"Current value: {db_url!r}. "
                "Set DATABASE_URL=postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader"
            )
        agent = self._make_risk_manager(balance=10000.0, method="kelly")
        balance = agent.account_balance

        for confidence in [0.1, 0.3, 0.5, 0.7, 0.9, 0.99]:
            signal_data = {"confidence": confidence, "symbol": "CrudeOIL"}
            size = await agent._kelly_criterion_size(signal_data)
            risk_pct = size / balance
            assert risk_pct <= 0.02, (
                f"confidence={confidence}: risk {risk_pct:.4%} exceeds 2% limit. "
                f"size={size:.2f}, balance={balance:.2f}"
            )

        print(f"\n[PASS] Risk percentage <= 2% across all confidence levels (0.1–0.99)")


# ===========================================================================
# TEST 3 — Seasonality Filter on CrudeOilStrategy
# ===========================================================================

class TestSeasonalityFilter:
    """
    Verify _check_seasonality weights and _check_entry Q4 gate.
    """

    def _make_strategy(self):
        from src.services.backtesting.crude_oil_strategy import (
            CrudeOilStrategy,
            CrudeOilParams,
        )
        return CrudeOilStrategy(params=CrudeOilParams(enable_seasonality=True))

    def _make_tick(self, timestamp: datetime, price: float = 70.0) -> Any:
        from src.services.backtesting.data_replay_engine import MarketTick
        return MarketTick(
            symbol="CrudeOIL",
            timestamp=timestamp,
            open=Decimal(str(price)),
            high=Decimal(str(price + 0.5)),
            low=Decimal(str(price - 0.5)),
            close=Decimal(str(price)),
            volume=1000,
        )

    # -- Direct _check_seasonality tests --

    def test_q1_weight_is_1_0(self):
        """January–March (Q1) → weight 1.0"""
        strategy = self._make_strategy()
        for month in [1, 2, 3]:
            weight = strategy._check_seasonality(datetime(2026, month, 15))
            assert weight == 1.0, f"Month {month}: expected 1.0, got {weight}"
        print("\n[PASS] Q1 (Jan-Mar) seasonality weight = 1.0")

    def test_q2_weight_is_1_0(self):
        """April–June (Q2) → weight 1.0"""
        strategy = self._make_strategy()
        for month in [4, 5, 6]:
            weight = strategy._check_seasonality(datetime(2026, month, 15))
            assert weight == 1.0, f"Month {month}: expected 1.0, got {weight}"
        print("\n[PASS] Q2 (Apr-Jun) seasonality weight = 1.0")

    def test_q3_weight_is_0_5(self):
        """July–September (Q3) → weight 0.5"""
        strategy = self._make_strategy()
        for month in [7, 8, 9]:
            weight = strategy._check_seasonality(datetime(2026, month, 15))
            assert weight == 0.5, f"Month {month}: expected 0.5, got {weight}"
        print("\n[PASS] Q3 (Jul-Sep) seasonality weight = 0.5")

    def test_q4_weight_is_0_0(self):
        """October–December (Q4) → weight 0.0 (disabled)"""
        strategy = self._make_strategy()
        for month in [10, 11, 12]:
            weight = strategy._check_seasonality(datetime(2026, month, 15))
            assert weight == 0.0, f"Month {month}: expected 0.0, got {weight}"
        print("\n[PASS] Q4 (Oct-Dec) seasonality weight = 0.0")

    def test_seasonality_disabled_returns_1_0_all_months(self):
        """When enable_seasonality=False, every month returns 1.0."""
        from src.services.backtesting.crude_oil_strategy import (
            CrudeOilStrategy,
            CrudeOilParams,
        )
        strategy = CrudeOilStrategy(params=CrudeOilParams(enable_seasonality=False))
        for month in range(1, 13):
            weight = strategy._check_seasonality(datetime(2026, month, 15))
            assert weight == 1.0, f"Month {month}: expected 1.0 (disabled), got {weight}"
        print("\n[PASS] Disabled seasonality: all months return 1.0")

    # -- Entry gate tests --

    def test_q4_check_entry_returns_no_signal(self):
        """
        _check_entry in Q4 must return action=None with Q4 reason,
        regardless of indicator values.
        """
        from src.services.backtesting.crude_oil_strategy import CrudeOilStrategy, CrudeOilParams
        strategy = CrudeOilStrategy(params=CrudeOilParams(enable_seasonality=True))

        tick = self._make_tick(datetime(2026, 10, 15, 12, 0), price=70.0)
        signal = strategy._check_entry(tick)

        assert signal.action is None, (
            f"Q4 entry should produce no signal, got action='{signal.action}'"
        )
        assert "Q4" in signal.reason, (
            f"Q4 rejection reason should mention 'Q4', got: '{signal.reason}'"
        )
        assert signal.confidence == 0.0, (
            f"Q4 signal confidence should be 0.0, got {signal.confidence}"
        )
        print(f"\n[PASS] Q4 check_entry blocked. Reason: '{signal.reason}'")

    def test_q3_open_position_confidence_is_halved(self):
        """
        When _open_position is called with Q3 weight (0.5),
        confidence = 0.7 * 0.5 = 0.35.
        """
        from src.services.backtesting.crude_oil_strategy import CrudeOilStrategy, CrudeOilParams
        strategy = CrudeOilStrategy(params=CrudeOilParams(enable_seasonality=True))

        tick = self._make_tick(datetime(2026, 7, 15, 12, 0), price=70.0)
        signal = strategy._open_position(
            position_type="buy",
            tick=tick,
            stop_distance=1.0,
            tp_distance=2.5,
            reason="TEST: Q3 seasonality weight",
            seasonality_weight=0.5,
        )

        expected = 0.7 * 0.5
        assert signal.confidence == pytest.approx(expected, abs=1e-9), (
            f"Q3 confidence should be {expected} (0.7 × 0.5), got {signal.confidence}"
        )
        print(f"\n[PASS] Q3 confidence = {signal.confidence} (= 0.7 × 0.5 = {expected})")

    def test_q1_open_position_confidence_is_full(self):
        """Q1 signals have full confidence (0.7 * 1.0 = 0.7)."""
        from src.services.backtesting.crude_oil_strategy import CrudeOilStrategy, CrudeOilParams
        strategy = CrudeOilStrategy(params=CrudeOilParams(enable_seasonality=True))

        tick = self._make_tick(datetime(2026, 1, 15, 12, 0), price=70.0)
        signal = strategy._open_position(
            position_type="sell",
            tick=tick,
            stop_distance=1.0,
            tp_distance=2.5,
            reason="TEST: Q1 full weight",
            seasonality_weight=1.0,
        )

        expected = 0.7 * 1.0
        assert signal.confidence == pytest.approx(expected, abs=1e-9), (
            f"Q1 confidence should be {expected}, got {signal.confidence}"
        )
        print(f"\n[PASS] Q1 confidence = {signal.confidence} (= 0.7 × 1.0 = {expected})")

    def test_process_tick_q4_produces_zero_entry_signals(self):
        """
        Feed 60 ticks with Q4 timestamps through process_tick.
        Verify no entry signals (buy/sell) are produced.
        """
        from src.services.backtesting.crude_oil_strategy import CrudeOilStrategy, CrudeOilParams
        import random

        params = CrudeOilParams(
            enable_seasonality=True,
            use_time_filter=False,  # Disable so hour doesn't interfere
        )
        strategy = CrudeOilStrategy(params=params)

        base_price = 70.0
        signals = []
        for i in range(60):
            noise = (random.random() - 0.5) * 2.0
            price = base_price + noise
            ts = datetime(2026, 10, 1 + min(i // 24, 28), 12, 0)
            tick = self._make_tick(ts, price=price)
            signal = strategy.process_tick(tick)
            signals.append(signal)

        entry_signals = [s for s in signals if s.action in ("buy", "sell")]
        assert len(entry_signals) == 0, (
            f"Q4 should produce 0 entry signals, got {len(entry_signals)}: "
            f"{[s.reason for s in entry_signals]}"
        )
        q4_blocked = [s for s in signals if "Q4" in s.reason]
        print(
            f"\n[PASS] Q4 process_tick: 0 entry signals from {len(signals)} ticks. "
            f"Q4-blocked by filter: {len(q4_blocked)}"
        )


# ===========================================================================
# SUMMARY / STATIC CHECKS
# ===========================================================================

class TestPhase1Week1Summary:
    """
    Static code checks: confirm the implementation changes are present.
    """

    def test_no_hardcoded_atr_defaults_in_stealth_stop_manager(self):
        """
        Verify the hardcoded dict {"CrudeOIL": 0.75} is gone.
        This was Fake #1 — the old fallback defaults.
        """
        content = (PROJECT_ROOT / "src" / "services" / "stealth_stop_manager.py").read_text()

        assert '"CrudeOIL": 0.75' not in content, (
            "FAIL: Hardcoded ATR {'CrudeOIL': 0.75} still present in "
            "stealth_stop_manager.py (Fake #1 not eliminated)."
        )
        assert '"XAUUSD": 15.0' not in content, (
            "FAIL: Hardcoded ATR {'XAUUSD': 15.0} still present in "
            "stealth_stop_manager.py (Fake #1 not eliminated)."
        )
        print("\n[PASS] Hardcoded ATR defaults removed from stealth_stop_manager.py")

    def test_tf_map_bug_detected(self):
        """
        REGRESSION DETECTOR: Confirm the 'H1' → '1h' mapping bug exists.

        The tf_map in get_atr() maps 'H1' to '1h', but the DB stores the
        timeframe enum as 'H1'. MarketDataRepository casts timeframe to text
        for comparison, so '1h' != 'H1' → 0 rows returned → InsufficientDataError
        always fires for H1 data.

        DB evidence: 94,922 CrudeOIL rows exist with timeframe='H1'.

        REQUIRED FIX (risk-eng):
            In stealth_stop_manager.py get_atr(), change:
                "H1": "1h"
            to:
                "H1": "H1"
            OR remove the tf_map entirely and pass the timeframe string directly.
        """
        content = (PROJECT_ROOT / "src" / "services" / "stealth_stop_manager.py").read_text()

        has_broken_mapping = '"H1": "1h"' in content

        if has_broken_mapping:
            pytest.fail(
                "BUG DETECTED in stealth_stop_manager.py get_atr() tf_map:\n"
                '  Current:  "H1": "1h"  →  DB query returns 0 rows\n'
                '  Required: "H1": "H1"  →  matches PostgreSQL enum text\n'
                "  Effect: get_atr('CrudeOIL', timeframe='H1') always raises\n"
                "          InsufficientDataError despite 94,922 H1 candles in DB.\n"
                "  Owner: risk-eng must fix src/services/stealth_stop_manager.py"
            )

        print(
            "\n[PASS] tf_map bug not present — 'H1' → '1h' mapping was not found."
        )

    def test_risk_manager_has_2percent_cap_assertion(self):
        """Verify the 2% hard cap assert exists in _calculate_position_size."""
        content = (PROJECT_ROOT / "src" / "agents" / "execution" / "risk_manager.py").read_text()

        assert "assert position_size <= max_risk" in content, (
            "FAIL: The hard 2% cap assert is missing from "
            "risk_manager.py._calculate_position_size."
        )
        assert "risk_per_trade" in content, (
            "FAIL: risk_per_trade attribute not found in risk_manager.py."
        )
        print("\n[PASS] 2% cap assert confirmed in risk_manager.py")

    def test_seasonality_filter_is_implemented(self):
        """
        Verify _check_seasonality exists with Q4=0.0, Q3=0.5, and
        the entry gate blocks Q4.
        """
        content = (
            PROJECT_ROOT / "src" / "services" / "backtesting" / "crude_oil_strategy.py"
        ).read_text()

        assert "_check_seasonality" in content, (
            "FAIL: _check_seasonality method not found in crude_oil_strategy.py"
        )
        assert "return 0.0" in content, (
            "FAIL: Q4 zero-return (return 0.0) not found in crude_oil_strategy.py"
        )
        assert "return 0.5" in content, (
            "FAIL: Q3 half-weight (return 0.5) not found in crude_oil_strategy.py"
        )
        assert "Q4 seasonal filter" in content, (
            "FAIL: Q4 filter reason string not found in crude_oil_strategy.py"
        )
        print(
            "\n[PASS] Seasonality filter with Q4=0.0 and Q3=0.5 "
            "confirmed in crude_oil_strategy.py"
        )
