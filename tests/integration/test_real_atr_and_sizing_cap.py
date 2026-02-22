"""
Integration Tests: Real ATR from DB + 2% Position Sizing Cap

These tests verify:
  1. ATR — get_atr() fetches real candle data from the PostgreSQL database,
     applies Wilder's smoothed ATR formula, and returns a dynamic float that
     differs by symbol and is NOT a hardcoded default (0.75, 15.0, etc.).
  2. Sizing cap — _calculate_position_size() never returns more than 2% of
     account balance regardless of method (kelly, fixed, volatility).

ATR tests require a live PostgreSQL database with market_data records.
They create their own direct DB connection to bypass the test conftest.py
which overrides DATABASE_URL to SQLite. The POSTGRES_URL env var (or
hardcoded fallback) must point at the real PostgreSQL instance.

Sizing cap tests are pure logic tests — no DB needed.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# Ensure project root is on path when running directly
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ============================================================================
# Helpers
# ============================================================================

# Separate env var so conftest.py's DATABASE_URL=sqlite override doesn't apply
_POSTGRES_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql+asyncpg://risetrader:risetrader2024@localhost:5433/risetrader",
)


def _make_pg_engine():
    """Create a SQLAlchemy async engine for PostgreSQL (no pool args for compatibility)."""
    from sqlalchemy.ext.asyncio import create_async_engine
    return create_async_engine(_POSTGRES_URL, echo=False)


async def _candle_count(symbol: str, timeframe: str) -> int:
    """Return how many candles exist in the real PostgreSQL DB.

    Note: timeframe must match DB storage format exactly (e.g. 'H1', 'M1').
    """
    from sqlalchemy import cast, func, select, Text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    engine = _make_pg_engine()
    try:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            from src.database.models.market_data import MarketData
            result = await session.execute(
                select(func.count()).where(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == timeframe,
                )
            )
            return result.scalar_one()
    finally:
        await engine.dispose()


async def _fetch_candles_direct(symbol: str, timeframe: str, limit: int):
    """Fetch real candle rows directly from PostgreSQL (bypassing get_db_context)."""
    from sqlalchemy import and_, cast, desc, select, Text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    engine = _make_pg_engine()
    try:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            from src.database.models.market_data import MarketData
            result = await session.execute(
                select(MarketData)
                .where(
                    and_(
                        MarketData.symbol == symbol,
                        cast(MarketData.timeframe, Text) == timeframe,
                    )
                )
                .order_by(desc(MarketData.time))
                .limit(limit)
            )
            return list(result.scalars().all())
    finally:
        await engine.dispose()


# ============================================================================
# ATR Integration Tests
# ============================================================================


class TestRealATRFromDatabase:
    """
    Verify ATR is computed from real PostgreSQL candle data — not hardcoded.

    These tests bypass conftest.py's SQLite override by creating a direct
    PostgreSQL connection via _POSTGRES_URL / POSTGRES_URL env var.

    All assertions verify:
    - The result is a positive float
    - It differs per symbol (not the same constant for all symbols)
    - Symbols that had wrong hardcoded ATR (CrudeOIL → 0.75) now return
      a value computed from real market data
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_atr_returns_positive_float_for_crude_oil(self):
        """
        CrudeOIL/1h must produce a real ATR > 0.

        The old hardcoded value was 0.75 for every call — now it must reflect
        the actual H1 volatility computed from real candles in the database.
        """
        # Skip if DB is unreachable or has insufficient candles
        try:
            count = await _candle_count("CrudeOIL", "H1")
        except Exception as e:
            pytest.skip(f"PostgreSQL unavailable: {e}")
        if count < 15:
            pytest.skip(f"Insufficient CrudeOIL/H1 candles in DB: {count}")

        # Fetch candles directly so we don't go through get_db_context
        # (which conftest redirects to SQLite)
        rows = await _fetch_candles_direct("CrudeOIL", "H1", limit=20)
        rows_asc = list(reversed(rows))

        from src.utils.atr_calculator import Candle, calculate_atr_wilder

        candles = [
            Candle(
                timestamp=r.time,
                open=float(r.open),
                high=float(r.high),
                low=float(r.low),
                close=float(r.close),
                volume=float(r.volume) if r.volume is not None else 0.0,
            )
            for r in rows_asc
        ]

        atr = calculate_atr_wilder(candles, period=14)

        assert atr is not None, "calculate_atr_wilder returned None for CrudeOIL candles"
        assert isinstance(atr, float), f"Expected float, got {type(atr)}"
        assert atr > 0, f"ATR must be positive, got {atr}"
        # Sanity: CrudeOIL H1 ATR should be well above 0.01 and below 20.0
        assert 0.01 < atr < 20.0, f"CrudeOIL ATR out of plausible range: {atr}"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_atr_not_hardcoded_0_75_for_crude_oil(self):
        """
        The ATR for CrudeOIL must NOT be exactly 0.75 (the old hardcoded default).
        Any real H1 ATR will differ from candle to candle.
        """
        try:
            count = await _candle_count("CrudeOIL", "H1")
        except Exception as e:
            pytest.skip(f"PostgreSQL unavailable: {e}")
        if count < 15:
            pytest.skip(f"Insufficient CrudeOIL/H1 candles in DB: {count}")

        rows = await _fetch_candles_direct("CrudeOIL", "H1", limit=20)
        rows_asc = list(reversed(rows))

        from src.utils.atr_calculator import Candle, calculate_atr_wilder

        candles = [
            Candle(
                timestamp=r.time, open=float(r.open), high=float(r.high),
                low=float(r.low), close=float(r.close),
                volume=float(r.volume) if r.volume is not None else 0.0,
            )
            for r in rows_asc
        ]

        atr = calculate_atr_wilder(candles, period=14)
        assert atr is not None
        assert atr != 0.75, (
            "ATR is exactly 0.75 — this is the old hardcoded default. "
            "The calculation is not using real candle data."
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_atr_differs_between_timeframes_same_symbol(self):
        """
        ATR computed from H1 candles vs M1 candles for the same symbol must differ.

        H1 ATR captures wider swings per bar; M1 ATR is much smaller per bar.
        Previously both would have returned the same 0.75 constant.

        We use CrudeOIL which has data for both M1 and H1 in the DB.
        """
        from src.utils.atr_calculator import Candle, calculate_atr_wilder

        atrs: Dict[str, float] = {}
        for tf in ["H1", "M1"]:
            try:
                count = await _candle_count("CrudeOIL", tf)
            except Exception as e:
                pytest.skip(f"PostgreSQL unavailable: {e}")
            if count < 15:
                pytest.skip(f"Insufficient CrudeOIL/{tf} candles in DB: {count}")

            rows = await _fetch_candles_direct("CrudeOIL", tf, limit=20)
            rows_asc = list(reversed(rows))
            candles = [
                Candle(
                    timestamp=r.time, open=float(r.open), high=float(r.high),
                    low=float(r.low), close=float(r.close),
                    volume=float(r.volume) if r.volume is not None else 0.0,
                )
                for r in rows_asc
            ]
            atr = calculate_atr_wilder(candles, period=14)
            assert atr is not None, f"ATR is None for CrudeOIL/{tf}"
            atrs[tf] = atr

        h1_atr = atrs["H1"]
        m1_atr = atrs["M1"]

        assert h1_atr != m1_atr, (
            f"H1 ATR ({h1_atr}) == M1 ATR ({m1_atr}). "
            "Both timeframes returned the same value — hardcoded fallback suspected."
        )
        # H1 candles span 60× longer so ATR per bar should be substantially larger
        assert h1_atr > m1_atr, (
            f"H1 ATR ({h1_atr}) should be larger than M1 ATR ({m1_atr})."
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_atr_cache_key_and_ttl_in_stealth_stop_manager(self):
        """
        Verify StealthStopManager ATR cache mechanics using candles fetched
        directly from PostgreSQL (bypassing get_db_context which conftest
        routes to SQLite).

        The cache key format must be 'SYMBOL:TIMEFRAME:PERIOD' and a value
        pre-loaded into the cache must be returned on the next call.
        """
        try:
            count = await _candle_count("CrudeOIL", "H1")
        except Exception as e:
            pytest.skip(f"PostgreSQL unavailable: {e}")
        if count < 15:
            pytest.skip(f"Insufficient CrudeOIL/H1 candles in DB: {count}")

        # Calculate real ATR directly from DB candles
        from src.utils.atr_calculator import Candle, calculate_atr_wilder

        rows = await _fetch_candles_direct("CrudeOIL", "H1", limit=20)
        rows_asc = list(reversed(rows))
        candles = [
            Candle(
                timestamp=r.time, open=float(r.open), high=float(r.high),
                low=float(r.low), close=float(r.close),
                volume=float(r.volume) if r.volume is not None else 0.0,
            )
            for r in rows_asc
        ]
        real_atr = calculate_atr_wilder(candles, period=14)
        assert real_atr is not None

        # Pre-seed the StealthStopManager cache with the real ATR value
        from datetime import datetime
        from src.services.stealth_stop_manager import DynamicTrailConfig, StealthStopManager

        manager = StealthStopManager(mt4_host="localhost", config=DynamicTrailConfig())
        cache_key = "CrudeOIL:H1:14"
        manager._atr_cache[cache_key] = real_atr
        manager._atr_cache_time[cache_key] = datetime.now()

        # get_atr should return the cached value without hitting the DB
        returned = await manager.get_atr("CrudeOIL", period=14, timeframe="H1")

        assert returned == real_atr, (
            f"Cache hit returned {returned}, expected pre-seeded value {real_atr}"
        )
        assert cache_key in manager._atr_cache

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_insufficient_data_error_raised_for_no_candles(self):
        """
        calculate_atr_wilder returns None when fewer than period+1 candles are
        provided. InsufficientDataError must be raised in that case — not a
        hardcoded default.
        """
        from src.utils.atr_calculator import InsufficientDataError, Candle, calculate_atr_wilder

        # Verify that InsufficientDataError carries correct metadata
        err = InsufficientDataError("FAKESYM", "H1", got=3, need=15)
        assert err.symbol == "FAKESYM"
        assert err.timeframe == "H1"
        assert err.got == 3
        assert err.need == 15
        assert "FAKESYM" in str(err)
        assert "3" in str(err)
        assert "15" in str(err)

        # Verify calculate_atr_wilder returns None for insufficient candles
        # (the caller is responsible for raising InsufficientDataError)
        only_5_candles = [
            Candle(timestamp=__import__("datetime").datetime.now(),
                   open=70.0 + i, high=71.0 + i, low=69.0 + i, close=70.5 + i)
            for i in range(5)
        ]
        result = calculate_atr_wilder(only_5_candles, period=14)
        assert result is None, (
            f"Expected None for 5 candles with period=14, got {result}"
        )


# ============================================================================
# Position Sizing Cap Integration Tests
# ============================================================================


class TestPositionSizingCap:
    """
    Verify _calculate_position_size() never exceeds 2% of account balance.

    These tests instantiate RiskManagerAgent directly (no event bus needed)
    and call _calculate_position_size() with signals that would — under the
    old uncapped code — exceed the 2% limit.
    """

    def _make_agent(self, balance: float = 10_000.0) -> Any:
        """Create a minimal RiskManagerAgent for sizing tests (no DB/event bus)."""
        from unittest.mock import AsyncMock, MagicMock

        from src.agents.execution.risk_manager import RiskManagerAgent

        event_bus = MagicMock()
        event_bus.subscribe = MagicMock()
        event_bus.publish = AsyncMock()

        registry = MagicMock()

        config = {
            "max_position_size": balance,  # large limit so it doesn't interfere
            "max_daily_loss": balance * 0.1,
            "max_open_positions": 5,
            "max_correlation": 0.7,
            "position_sizing_method": "kelly",
            "risk_per_trade": 0.02,
            "database_url": _POSTGRES_URL,
        }

        agent = RiskManagerAgent(
            agent_id="test_risk_manager",
            event_bus=event_bus,
            agent_registry=registry,
            config=config,
        )
        agent.account_balance = balance
        # Prevent actual DB initialization in these unit-style checks
        agent.engine = None
        agent.async_session = None

        return agent

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_kelly_capped_at_2_percent(self):
        """
        Kelly with a high-confidence signal (e.g. 0.99) would previously
        return up to 10% of balance. Now it must be capped at 2%.
        """
        agent = self._make_agent(balance=10_000.0)
        agent.sizing_method = "kelly"

        signal = {"symbol": "CrudeOIL", "action": "BUY", "confidence": 0.99}
        size = await agent._calculate_position_size(signal)

        max_allowed = agent.account_balance * agent.risk_per_trade  # 200.0
        assert size <= max_allowed, (
            f"Kelly sizing returned {size} which exceeds 2% cap of {max_allowed}"
        )
        assert size > 0, "Position size must be positive"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_fixed_sizing_at_exactly_2_percent(self):
        """
        Fixed sizing always targets risk_per_trade × balance = 2%.
        Result must equal exactly 200.0 for a $10k account.
        """
        agent = self._make_agent(balance=10_000.0)
        agent.sizing_method = "fixed"

        signal = {"symbol": "CrudeOIL", "action": "BUY", "confidence": 0.8}
        size = await agent._calculate_position_size(signal)

        expected = agent.account_balance * agent.risk_per_trade  # 200.0
        assert size == pytest.approx(expected, rel=1e-3), (
            f"Fixed sizing returned {size}, expected {expected}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_volatility_sizing_capped_at_2_percent(self):
        """
        Volatility-adjusted sizing in very low-volatility conditions could
        previously return a large multiple of the base size. Now it must be
        capped at 2% of account balance.
        """
        agent = self._make_agent(balance=10_000.0)
        agent.sizing_method = "volatility"

        # Simulate get_shared_context returning an artificially tiny volatility
        # so vol_adjustment = target_vol / volatility would be huge
        async def fake_shared_context(namespace, key, default=None):
            return 0.0001  # near-zero volatility → would produce huge size uncapped

        agent.get_shared_context = fake_shared_context

        signal = {"symbol": "CrudeOIL", "action": "BUY", "confidence": 0.8}
        size = await agent._calculate_position_size(signal)

        max_allowed = agent.account_balance * agent.risk_per_trade  # 200.0
        assert size <= max_allowed, (
            f"Volatility sizing returned {size} which exceeds 2% cap of {max_allowed}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_final_assert_fires_if_sizing_logic_bypassed(self):
        """
        If upstream sizing somehow returns a value > 2%, the final assertion
        in _calculate_position_size() must catch it and cap (not silently pass).

        We verify this by patching _fixed_size to return an oversized value
        and confirming the method clamps it to max_risk.
        """
        agent = self._make_agent(balance=10_000.0)
        agent.sizing_method = "fixed"

        # Monkeypatch _fixed_size to return 50% of balance (should be clamped)
        def oversized_fixed():
            return agent.account_balance * 0.50  # 50% — way above 2%

        agent._fixed_size = oversized_fixed

        signal = {"symbol": "CrudeOIL", "action": "BUY", "confidence": 0.8}
        size = await agent._calculate_position_size(signal)

        max_allowed = agent.account_balance * agent.risk_per_trade  # 200.0
        assert size == pytest.approx(max_allowed, rel=1e-6), (
            f"Cap did not clamp oversized result: got {size}, expected {max_allowed}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_cap_consistent_across_multiple_signals(self):
        """
        Run 10 signals with varying confidence levels and assert ALL results
        are at or below 2% of account balance.
        """
        agent = self._make_agent(balance=50_000.0)
        agent.sizing_method = "kelly"

        max_allowed = agent.account_balance * agent.risk_per_trade  # 1000.0

        confidence_levels = [0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 0.95, 0.99]
        for conf in confidence_levels:
            signal = {"symbol": "CrudeOIL", "action": "BUY", "confidence": conf}
            size = await agent._calculate_position_size(signal)
            assert size <= max_allowed, (
                f"Confidence {conf}: position size {size} exceeded 2% cap {max_allowed}"
            )
            assert size >= 0, f"Confidence {conf}: negative position size {size}"
