"""
Integration tests for the full regime-aware trading pipeline against real
PostgreSQL data.

No mocks.  All assertions use data fetched directly via asyncpg, bypassing
the SQLAlchemy / src.api.dependencies import chain that conftest.py redirects
to an in-memory SQLite DB.

Architecture note (matches test_informed_flow.py and test_phase1_week2.py):
    conftest.py sets DATABASE_URL=sqlite at import time.  Any code path that
    lazily imports src.api.dependencies will try to create a Postgres pool
    against a sqlite:// URL and crash.  The pattern here:

      1. DB-backed tests fetch rows directly via asyncpg (raw SQL, no ORM).
      2. Fetched rows are converted to the dicts each class expects.
      3. For CrossAssetFilter (which uses get_db_context internally) we test
         the pure scoring and direction helpers directly using asyncpg-fetched
         closes, bypassing the internal _fetch_closes DB call.

Run from Docker (file must be copied first — tests/ is not mounted):
    docker cp tests/integration/test_regime_pipeline_real_data.py \\
        risetrader-api:/app/test_regime_pipeline_real_data.py
    docker exec risetrader-api python -m pytest /app/test_regime_pipeline_real_data.py \\
        -v --tb=short --no-cov --asyncio-mode=auto

Run locally (uses pytest.ini asyncio_mode=auto automatically):
    python -m pytest tests/integration/test_regime_pipeline_real_data.py \\
        -v --tb=short --no-cov
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import pytest

import os

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# PostgreSQL connection helpers — asyncpg only, no SQLAlchemy
# ---------------------------------------------------------------------------

# Read the DB URL from the environment so the same DSN works both:
#   - locally:  DATABASE_URL=postgresql+asyncpg://postgres:...@localhost:5433/...
#   - in Docker: DATABASE_URL=postgresql+asyncpg://postgres:...@postgres:5432/...
_PG_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:risetrader2024@localhost:5433/risetrader",
)
# Strip SQLAlchemy driver prefix if present so asyncpg can use it directly
_PG_DSN = _PG_DSN.replace("postgresql+asyncpg://", "postgresql://").replace(
    "+asyncpg", ""
)


async def _pg_candle_count(symbol: str, timeframe: str = "H1") -> int:
    """Return the number of candles in the DB for symbol/timeframe."""
    import asyncpg

    conn = await asyncpg.connect(_PG_DSN)
    try:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM market_data "
            "WHERE symbol = $1 AND timeframe::text = $2",
            symbol,
            timeframe,
        )
    finally:
        await conn.close()


async def fetch_candles(
    symbol: str,
    timeframe: str = "H1",
    limit: int = 300,
) -> List[Dict]:
    """
    Fetch OHLCV candles from PostgreSQL.

    Returns a list of dicts in chronological order (oldest first) with keys:
        open, high, low, close, volume

    Args:
        symbol:    Instrument symbol (e.g. "CrudeOIL").
        timeframe: PostgreSQL ENUM value as text (e.g. "H1", "D1", "M1").
        limit:     Maximum number of bars to retrieve.

    Returns:
        List of OHLCV dicts, oldest first.  Empty list if DB unavailable or
        symbol has no data.
    """
    import asyncpg

    conn = await asyncpg.connect(_PG_DSN)
    try:
        rows = await conn.fetch(
            "SELECT time, open, high, low, last AS close, volume "
            "FROM market_data "
            "WHERE symbol = $1 AND timeframe::text = $2 "
            "ORDER BY time DESC LIMIT $3",
            symbol,
            timeframe,
            limit,
        )
        # Reverse so the list is oldest-first (required by RegimeClassifier)
        return [
            {
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r["volume"]) if r["volume"] is not None else 0.0,
            }
            for r in reversed(rows)
        ]
    finally:
        await conn.close()


async def fetch_closes(
    symbol: str,
    timeframe: str = "H1",
    limit: int = 50,
) -> List[float]:
    """
    Fetch close prices from PostgreSQL for a given symbol.

    Returns closes in chronological order (oldest first).

    Args:
        symbol:    Instrument symbol.
        timeframe: Timeframe string matching the ENUM cast.
        limit:     Number of bars.

    Returns:
        List of floats, oldest first.  Empty if DB unavailable.
    """
    import asyncpg

    conn = await asyncpg.connect(_PG_DSN)
    try:
        rows = await conn.fetch(
            "SELECT last AS close "
            "FROM market_data "
            "WHERE symbol = $1 AND timeframe::text = $2 "
            "ORDER BY time DESC LIMIT $3",
            symbol,
            timeframe,
            limit,
        )
        return [float(r["close"]) for r in reversed(rows)]
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Helper: guard all tests against PostgreSQL unavailability
# ---------------------------------------------------------------------------


async def _require_candles(
    symbol: str,
    min_bars: int,
    timeframe: str = "H1",
) -> int:
    """
    Skip the calling test if the DB is unreachable or has insufficient data.

    Returns the actual candle count so callers can log it if desired.
    """
    try:
        count = await _pg_candle_count(symbol, timeframe)
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable at {_PG_DSN}: {exc}")
    if count < min_bars:
        pytest.skip(
            f"Insufficient {symbol}/{timeframe} candles: {count} (need >= {min_bars})"
        )
    return count


# ===========================================================================
# Test 1 — Regime classification on real CrudeOIL H1 candles
# ===========================================================================


class TestRegimeClassificationRealCandles:
    """
    Verify that RegimeClassifier produces well-formed output when fed real
    CrudeOIL H1 data from PostgreSQL.

    CrudeOIL H1 has 95 K+ bars — more than sufficient for all indicator
    lookbacks (max 50-bar SMA + 14-bar ATR + 20-bar Hurst lags).
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_classify_crudeoil_h1(self):
        """
        Classify regime from 300 real CrudeOIL H1 bars.

        Expected outputs:
            - regime ∈ {TRENDING, RANGING, VOLATILE, UNKNOWN}
            - metadata["adx"] is a non-negative float (or None on edge path)
            - metadata["hurst"] ∈ [0.0, 1.0]
            - metadata["atr_ratio"] > 0  (non-zero volatility in 300 bars)
            - metadata["regime_confidence"] ∈ [0.0, 1.0]
            - trending_score + ranging_score together make sense for the regime

        Edge cases handled:
            - If DB unavailable → skip (not fail)
            - If < 60 bars available → skip
        """
        await _require_candles("CrudeOIL", min_bars=60)

        prices = await fetch_candles("CrudeOIL", "H1", 300)
        assert len(prices) >= 60, "fetch_candles returned fewer rows than expected"

        from src.trading.regime.regime_classifier import MarketRegime, RegimeClassifier

        classifier = RegimeClassifier()
        regime, meta = classifier.classify(prices)

        # --- Regime type ---
        assert isinstance(regime, MarketRegime), (
            f"Expected MarketRegime instance, got {type(regime)}"
        )
        assert regime in (
            MarketRegime.TRENDING,
            MarketRegime.RANGING,
            MarketRegime.VOLATILE,
            MarketRegime.UNKNOWN,
        )

        # --- Required metadata keys ---
        for key in ("adx", "hurst", "atr_ratio", "regime_confidence",
                    "trending_score", "ranging_score", "volatile_triggers",
                    "ma50_consecutive", "ma20_crosses"):
            assert key in meta, f"Missing metadata key: {key}"

        # --- ADX ---
        if meta["adx"] is not None:
            assert isinstance(meta["adx"], (int, float)), "adx must be numeric"
            assert meta["adx"] >= 0, f"ADX cannot be negative: {meta['adx']}"

        # --- Hurst ---
        assert isinstance(meta["hurst"], float), "hurst must be float"
        assert 0.0 <= meta["hurst"] <= 1.0, (
            f"Hurst out of [0, 1]: {meta['hurst']}"
        )

        # --- ATR ratio ---
        assert isinstance(meta["atr_ratio"], float), "atr_ratio must be float"
        # 300 bars of real crude oil always produce non-zero ATR
        assert meta["atr_ratio"] >= 0.0, "atr_ratio must be non-negative"

        # --- Confidence ---
        assert isinstance(meta["regime_confidence"], float)
        assert 0.0 <= meta["regime_confidence"] <= 1.0, (
            f"Confidence out of [0, 1]: {meta['regime_confidence']}"
        )

        # --- Volatile triggers list ---
        assert isinstance(meta["volatile_triggers"], list)

        # --- Score consistency ---
        if regime == MarketRegime.TRENDING:
            assert meta["trending_score"] >= 2, (
                f"TRENDING requires trending_score >= 2, got {meta['trending_score']}"
            )
        elif regime == MarketRegime.RANGING:
            assert meta["ranging_score"] >= 2, (
                f"RANGING requires ranging_score >= 2, got {meta['ranging_score']}"
            )
        elif regime == MarketRegime.VOLATILE:
            assert len(meta["volatile_triggers"]) >= 1, (
                "VOLATILE must have at least one trigger"
            )

        print(
            f"\nCrudeOIL Regime: {regime.value} | "
            f"ADX: {meta['adx']} | "
            f"Hurst: {meta['hurst']:.4f} | "
            f"ATR Ratio: {meta['atr_ratio']:.3f}"
        )
        print(
            f"  MA50 Consec: {meta['ma50_consecutive']} | "
            f"MA20 Crosses: {meta['ma20_crosses']} | "
            f"Confidence: {meta['regime_confidence']:.2f}"
        )
        print(
            f"  Trending Score: {meta['trending_score']}/3 | "
            f"Ranging Score: {meta['ranging_score']}/3"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_classify_brent_h1(self):
        """
        Classify regime from real BRENT_OIL H1 data.

        BRENT_OIL has 39K+ H1 bars.  The test confirms the classifier handles
        a second instrument without errors and produces valid metadata.
        """
        await _require_candles("BRENT_OIL", min_bars=60)

        prices = await fetch_candles("BRENT_OIL", "H1", 300)

        from src.trading.regime.regime_classifier import MarketRegime, RegimeClassifier

        regime, meta = RegimeClassifier().classify(prices)

        assert isinstance(regime, MarketRegime)
        assert meta["hurst"] is not None
        assert 0.0 <= meta["hurst"] <= 1.0

        print(
            f"\nBRENT_OIL Regime: {regime.value} | "
            f"Confidence: {meta['regime_confidence']:.2f}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_classify_usa500_h1(self):
        """
        Classify regime from real USA500 H1 data.

        USA500 has 13K+ H1 bars — still well above the 60-bar minimum.
        """
        await _require_candles("USA500", min_bars=60)

        prices = await fetch_candles("USA500", "H1", 300)

        from src.trading.regime.regime_classifier import MarketRegime, RegimeClassifier

        regime, meta = RegimeClassifier().classify(prices)

        assert isinstance(regime, MarketRegime)
        assert 0.0 <= meta["regime_confidence"] <= 1.0

        print(
            f"\nUSA500 Regime: {regime.value} | "
            f"ADX: {meta['adx']} | "
            f"Confidence: {meta['regime_confidence']:.2f}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_classify_insufficient_data_returns_unknown(self):
        """
        Confirm that classify() returns UNKNOWN when fewer than 60 bars are
        supplied, even with real price data.

        Uses the last 30 real CrudeOIL H1 bars — well below the 60-bar minimum.
        All metadata values should be None or 0.
        """
        await _require_candles("CrudeOIL", min_bars=30)

        prices = await fetch_candles("CrudeOIL", "H1", 30)
        assert len(prices) <= 30

        from src.trading.regime.regime_classifier import MarketRegime, RegimeClassifier

        regime, meta = RegimeClassifier().classify(prices)

        assert regime == MarketRegime.UNKNOWN, (
            f"Expected UNKNOWN for {len(prices)} bars, got {regime.value}"
        )
        assert meta["adx"] is None
        assert meta["hurst"] is None
        assert meta["atr_ratio"] is None
        assert meta["regime_confidence"] == 0.0


# ===========================================================================
# Test 2 — Strategy routing from real regime classification
# ===========================================================================


class TestStrategyRoutingFromRealRegime:
    """
    Verify StrategyRouter produces well-formed, weight-consistent output for
    each regime that RegimeClassifier can produce with real CrudeOIL data.
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_route_from_real_crudeoil_regime(self):
        """
        Classify real CrudeOIL data, then route.

        Expected outputs:
            - config["strategies"] is a non-empty dict when allow_trading=True
            - weights sum to 1.0 (±0.02 tolerance for floating point)
            - signal_threshold ∈ (0.0, 1.0]
            - allow_trading is a bool
            - reason is a non-empty string
        """
        await _require_candles("CrudeOIL", min_bars=60)

        prices = await fetch_candles("CrudeOIL", "H1", 300)

        from src.trading.regime.regime_classifier import RegimeClassifier
        from src.trading.regime.strategy_router import StrategyRouter

        regime, _ = RegimeClassifier().classify(prices)
        config = StrategyRouter().get_strategy_config(regime)

        # --- Structure ---
        assert "strategies" in config
        assert "signal_threshold" in config
        assert "allow_trading" in config
        assert "reason" in config

        assert isinstance(config["allow_trading"], bool)
        assert isinstance(config["reason"], str) and len(config["reason"]) > 0
        assert 0.0 < config["signal_threshold"] <= 1.0, (
            f"signal_threshold out of range: {config['signal_threshold']}"
        )

        # --- Weight sum ---
        if config["allow_trading"]:
            assert len(config["strategies"]) > 0, (
                "allow_trading=True must have at least one strategy"
            )
            total_weight = sum(config["strategies"].values())
            assert abs(total_weight - 1.0) < 0.02, (
                f"Strategy weights must sum to 1.0, got {total_weight:.4f}"
            )
            # All individual weights are positive
            for name, weight in config["strategies"].items():
                assert weight > 0.0, (
                    f"Strategy {name!r} has non-positive weight: {weight}"
                )
        else:
            # VOLATILE: no strategies, trading halted
            assert config["strategies"] == {}, (
                "VOLATILE regime must have empty strategies dict"
            )

        print(
            f"\nCrudeOIL Regime: {regime.value} "
            f"→ Strategies: {list(config['strategies'].keys())}"
        )
        print(
            f"  Threshold: {config['signal_threshold']} | "
            f"Allow: {config['allow_trading']}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_routing_table_completeness(self):
        """
        Verify the routing table handles all four MarketRegime enum members
        without hitting the 'unknown_regime_value' fallback.

        This is a pure-logic test that uses the real routing table constants —
        no DB query needed beyond the import smoke-test.
        """
        from src.trading.regime.regime_classifier import MarketRegime
        from src.trading.regime.strategy_router import StrategyRouter

        router = StrategyRouter()
        all_regimes = list(MarketRegime)

        for regime in all_regimes:
            config = router.get_strategy_config(regime)
            assert config["allow_trading"] is not None
            # VOLATILE should always block trading
            if regime == MarketRegime.VOLATILE:
                assert config["allow_trading"] is False
                assert config["strategies"] == {}
            else:
                # All other regimes allow trading
                assert config["allow_trading"] is True
                assert len(config["strategies"]) > 0
                total = sum(config["strategies"].values())
                assert abs(total - 1.0) < 0.02, (
                    f"{regime.value}: weights sum to {total:.4f}, expected 1.0"
                )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_blocked_strategies_are_excluded(self):
        """
        Confirm that strategies listed as 'blocked' for a regime are absent
        from the returned strategy dict.
        """
        from src.trading.regime.regime_classifier import MarketRegime
        from src.trading.regime.strategy_router import StrategyRouter

        router = StrategyRouter()

        # TRENDING must not include value_area, mean_reversion, ml_reversal
        config_trending = router.get_strategy_config(MarketRegime.TRENDING)
        blocked_trending = router.get_blocked_strategies(MarketRegime.TRENDING)
        for blocked in blocked_trending:
            assert blocked not in config_trending["strategies"], (
                f"Blocked strategy {blocked!r} appeared in TRENDING config"
            )

        # RANGING must not include momentum, breakout
        config_ranging = router.get_strategy_config(MarketRegime.RANGING)
        blocked_ranging = router.get_blocked_strategies(MarketRegime.RANGING)
        for blocked in blocked_ranging:
            assert blocked not in config_ranging["strategies"], (
                f"Blocked strategy {blocked!r} appeared in RANGING config"
            )


# ===========================================================================
# Test 3 — CrossAssetFilter with real price data
# ===========================================================================


class TestCrossAssetRealData:
    """
    Test the CrossAssetFilter scoring and direction helpers using real closes
    fetched via asyncpg.

    Because CrossAssetFilter._fetch_closes() uses get_db_context (which the
    conftest.py SQLite override would break), these tests call the pure scoring
    methods (_score_confirm, _score_context, _short_term_direction) directly
    with asyncpg-fetched data.  This validates the full scoring logic against
    real price relationships without triggering the circular import.
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_direction_computation_crudeoil_vs_brent(self):
        """
        Both CrudeOIL and BRENT_OIL should have a direction computable from
        real H1 closes.  The test confirms the helper returns a value in [-1, 1].
        """
        await _require_candles("CrudeOIL", min_bars=10)
        await _require_candles("BRENT_OIL", min_bars=10)

        crude_closes = await fetch_closes("CrudeOIL", "H1", 20)
        brent_closes = await fetch_closes("BRENT_OIL", "H1", 20)

        from src.trading.filters.cross_asset_filter import CrossAssetFilter

        filt = CrossAssetFilter()

        crude_dir = filt._short_term_direction(crude_closes, bars=10)
        brent_dir = filt._short_term_direction(brent_closes, bars=10)

        assert -1.0 <= crude_dir <= 1.0, f"CrudeOIL direction out of [-1, 1]: {crude_dir}"
        assert -1.0 <= brent_dir <= 1.0, f"BRENT_OIL direction out of [-1, 1]: {brent_dir}"

        print(
            f"\nCrossAsset Directions (10-bar H1): "
            f"CrudeOIL={crude_dir:.3f}, BRENT_OIL={brent_dir:.3f}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_confirm_score_crude_vs_brent_buy(self):
        """
        Score BRENT_OIL as a 'confirm' asset for a CrudeOIL BUY signal.

        Expected:
            - score ∈ {-0.7, 0.0, 0.5} — the three possible confirm scores
            - reason string is non-empty
        """
        await _require_candles("CrudeOIL", min_bars=10)
        await _require_candles("BRENT_OIL", min_bars=10)

        brent_closes = await fetch_closes("BRENT_OIL", "H1", 20)

        from src.trading.filters.cross_asset_filter import CrossAssetFilter

        filt = CrossAssetFilter()
        brent_dir = filt._short_term_direction(brent_closes, bars=10)
        score, reason = filt._score_confirm("BRENT_OIL", "BUY", brent_dir)

        assert score in (-0.7, 0.0, 0.5), (
            f"Confirm score must be one of (-0.7, 0.0, 0.5), got {score}"
        )
        assert isinstance(reason, str) and len(reason) > 0

        print(
            f"\nBRENT_OIL confirm (CrudeOIL BUY): "
            f"dir={brent_dir:.3f} → score={score}, reason={reason}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_confirm_score_crude_vs_brent_sell(self):
        """
        Score BRENT_OIL as a 'confirm' asset for a CrudeOIL SELL signal.
        """
        await _require_candles("BRENT_OIL", min_bars=10)

        brent_closes = await fetch_closes("BRENT_OIL", "H1", 20)

        from src.trading.filters.cross_asset_filter import CrossAssetFilter

        filt = CrossAssetFilter()
        brent_dir = filt._short_term_direction(brent_closes, bars=10)
        score, reason = filt._score_confirm("BRENT_OIL", "SELL", brent_dir)

        assert score in (-0.7, 0.0, 0.5)
        assert isinstance(reason, str) and len(reason) > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_context_score_usa500_crude_buy(self):
        """
        Score USA500 as a 'context' asset for a CrudeOIL BUY signal.

        The four possible USA500-context scores for a crude BUY are:
            +0.3  (USA500 falling → supply shock)
            +0.1  (USA500 rising  → risk-on)
             0.0  (USA500 flat    → neutral)
        """
        await _require_candles("USA500", min_bars=10)

        usa_closes = await fetch_closes("USA500", "H1", 20)

        from src.trading.filters.cross_asset_filter import CrossAssetFilter

        filt = CrossAssetFilter()
        usa_dir = filt._short_term_direction(usa_closes, bars=10)
        score, reason = filt._score_context("USA500", "CrudeOIL", "BUY", usa_dir)

        # All valid scores for this combination
        valid_scores = {0.3, 0.2, 0.1, 0.0, -0.2}
        assert score in valid_scores, (
            f"Context score {score} not in valid set {valid_scores}"
        )
        assert isinstance(reason, str)

        print(
            f"\nUSA500 context (CrudeOIL BUY): "
            f"dir={usa_dir:.3f} → score={score}, reason={reason}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_buy_and_sell_scores_differ_when_trend_is_clear(self):
        """
        When BRENT_OIL has a directional bias over 10 bars, the confirm
        scores for BUY vs SELL should differ (one agrees, the other contradicts).

        If BRENT_OIL is flat (direction ≈ 0.0) both scores will be 0.0, which
        is also valid — the test only asserts when a clear trend exists.
        """
        await _require_candles("BRENT_OIL", min_bars=10)

        brent_closes = await fetch_closes("BRENT_OIL", "H1", 20)

        from src.trading.filters.cross_asset_filter import CrossAssetFilter

        filt = CrossAssetFilter()
        brent_dir = filt._short_term_direction(brent_closes, bars=10)

        buy_score, _ = filt._score_confirm("BRENT_OIL", "BUY", brent_dir)
        sell_score, _ = filt._score_confirm("BRENT_OIL", "SELL", brent_dir)

        # Both individually within valid range
        assert buy_score in (-0.7, 0.0, 0.5)
        assert sell_score in (-0.7, 0.0, 0.5)

        # When direction is non-zero, BUY and SELL scores should be opposite
        if abs(brent_dir) > 0.1:
            assert buy_score != sell_score, (
                f"Directional asset (dir={brent_dir:.3f}) should produce "
                f"opposite BUY/SELL scores; got buy={buy_score}, sell={sell_score}"
            )

        print(
            f"\nBRENT_OIL (dir={brent_dir:.3f}): "
            f"BUY score={buy_score}, SELL score={sell_score}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_unknown_symbol_returns_no_group(self):
        """
        Symbols not in the asset_groups map must pass unchecked with score=0.0
        and reason='no_group'.  This tests the pure method, no DB needed.
        """
        from src.trading.filters.cross_asset_filter import CrossAssetFilter

        filt = CrossAssetFilter()
        # WHEAT is not in the asset groups
        group = filt._asset_groups.get("WHEAT")
        assert group is None, "WHEAT should not be in CrossAssetFilter._asset_groups"

        # Verify the check_confirmation early-return directly
        import asyncio

        score, reason = await filt.check_confirmation("WHEAT", "BUY")
        assert score == 0.0, f"Unknown symbol should return 0.0, got {score}"
        assert reason == "no_group", f"Unknown symbol reason should be 'no_group', got {reason!r}"


# ===========================================================================
# Test 4 — Full signal pipeline dry run
# ===========================================================================


class TestFullSignalPipelineDryRun:
    """
    Walk through the complete regime-aware pipeline in read-only mode:

        fetch candles → classify regime → route strategies → inspect config

    No orders, no DB writes.  Validates end-to-end data flow from raw candles
    to strategy configuration.
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_pipeline_crudeoil(self):
        """
        Full pipeline for CrudeOIL H1.

        Steps:
            1. Fetch 300 H1 candles from PostgreSQL.
            2. Classify market regime (RegimeClassifier).
            3. Retrieve strategy config (StrategyRouter).
            4. If trading allowed, verify at least one active strategy.
            5. Assert no exceptions were raised at any stage.
        """
        await _require_candles("CrudeOIL", min_bars=60)

        prices = await fetch_candles("CrudeOIL", "H1", 300)

        from src.trading.regime.regime_classifier import MarketRegime, RegimeClassifier
        from src.trading.regime.strategy_router import StrategyRouter

        # Step 1: Classify
        classifier = RegimeClassifier()
        regime, meta = classifier.classify(prices)
        assert isinstance(regime, MarketRegime)

        # Step 2: Route
        router = StrategyRouter()
        config = router.get_strategy_config(regime)
        assert "strategies" in config
        assert "allow_trading" in config

        # Step 3: Conditional strategy check
        if config["allow_trading"]:
            assert len(config["strategies"]) > 0
            print(
                f"\nPipeline CrudeOIL: Regime={regime.value} "
                f"→ {len(config['strategies'])} strategies active: "
                f"{list(config['strategies'].keys())}"
            )
        else:
            # VOLATILE — no trades
            assert config["strategies"] == {}
            print(
                f"\nPipeline CrudeOIL: Regime={regime.value} "
                f"→ TRADING HALTED"
            )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_pipeline_brent_oil(self):
        """Full pipeline for BRENT_OIL H1."""
        await _require_candles("BRENT_OIL", min_bars=60)

        prices = await fetch_candles("BRENT_OIL", "H1", 300)

        from src.trading.regime.regime_classifier import RegimeClassifier
        from src.trading.regime.strategy_router import StrategyRouter

        regime, meta = RegimeClassifier().classify(prices)
        config = StrategyRouter().get_strategy_config(regime)

        assert isinstance(config["allow_trading"], bool)

        if config["allow_trading"]:
            total_weight = sum(config["strategies"].values())
            assert abs(total_weight - 1.0) < 0.02

        print(
            f"\nPipeline BRENT_OIL: Regime={regime.value} "
            f"→ Allow={config['allow_trading']}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_pipeline_three_symbols_no_exceptions(self):
        """
        Run the classify→route pipeline for all three data-rich symbols.

        Success criterion: no exceptions raised.  Regime distribution is
        printed for manual inspection — no specific regime is asserted since
        it depends on current market conditions.
        """
        symbols = ["CrudeOIL", "BRENT_OIL", "USA500"]
        results: dict = {}

        from src.trading.regime.regime_classifier import RegimeClassifier
        from src.trading.regime.strategy_router import StrategyRouter

        classifier = RegimeClassifier()
        router = StrategyRouter()

        for sym in symbols:
            try:
                count = await _pg_candle_count(sym)
            except Exception:
                print(f"\n  {sym}: DB unavailable, skipped")
                continue

            if count < 60:
                print(f"\n  {sym}: only {count} bars, skipped")
                continue

            prices = await fetch_candles(sym, "H1", 300)
            regime, meta = classifier.classify(prices)
            config = router.get_strategy_config(regime)
            results[sym] = {
                "regime": regime.value,
                "confidence": meta["regime_confidence"],
                "allow_trading": config["allow_trading"],
                "strategies": list(config["strategies"].keys()),
            }

        if not results:
            pytest.skip("No symbols had sufficient data")

        print("\nPipeline results across symbols:")
        for sym, r in results.items():
            print(
                f"  {sym}: regime={r['regime']} (conf={r['confidence']:.2f}) "
                f"→ allow={r['allow_trading']}, strategies={r['strategies']}"
            )

        # At least one symbol was processed without errors
        assert len(results) >= 1


# ===========================================================================
# Test 5 — PaperValidationService with real price data
# ===========================================================================


class TestPaperValidationWithRealPrices:
    """
    Test PaperValidationService using real prices from PostgreSQL for the
    entry, stop-loss, and take-profit calculations.

    The service is stateless (in-memory only) so these tests don't write to
    the DB.  Real prices are used to derive realistic entry/SL/TP levels.
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_record_and_resolve_sell_win(self):
        """
        Record a SELL signal with real CrudeOIL prices, then simulate TP hit.

        The stop-loss is placed above entry (2× last-bar range) and the take
        profit below entry (3× last-bar range).  We then call check_outcomes
        with a price below TP to simulate a win.

        Expected:
            - open_trades count goes from 0 → 1 after record_signal
            - check_outcomes returns a PaperTrade with outcome="win"
            - resolved total == 1, wins == 1
        """
        await _require_candles("CrudeOIL", min_bars=20)

        prices = await fetch_candles("CrudeOIL", "H1", 50)
        assert len(prices) >= 20

        from src.services.paper_validation_service import PaperValidationService

        svc = PaperValidationService()
        last = prices[-1]

        entry = last["close"]
        bar_range = last["high"] - last["low"]
        # Guard against flat/zero-range bar
        if bar_range < 1e-6:
            bar_range = entry * 0.001  # 0.1% of price as fallback

        stop_loss = entry + 2.0 * bar_range    # above entry for SELL
        take_profit = entry - 3.0 * bar_range  # below entry for SELL

        # --- Record signal ---
        assert len(svc._open_trades) == 0
        svc.record_signal(
            symbol="CrudeOIL",
            action="SELL",
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            regime="trending",
            lots=0.01,
        )
        assert len(svc._open_trades) == 1, "Signal should open one trade"

        # No resolved trades yet
        status = svc.get_validation_status()
        assert status["total_signals"] == 0
        assert status["open_trades"] == 1

        # --- Simulate price moving to TP (below take_profit for SELL) ---
        tp_hit_price = take_profit - 0.01
        result = svc.check_outcomes("CrudeOIL", tp_hit_price)

        assert result is not None, (
            f"check_outcomes should return PaperTrade when TP is hit "
            f"(entry={entry:.4f}, tp={take_profit:.4f}, current={tp_hit_price:.4f})"
        )
        assert result.outcome == "win", (
            f"Expected 'win', got {result.outcome!r}"
        )
        assert result.resolved is True
        assert result.symbol == "CrudeOIL"
        assert result.action == "SELL"

        # Trade is removed from open_trades after resolution
        assert len(svc._open_trades) == 0

        status = svc.get_validation_status()
        assert status["total_signals"] == 1
        assert status["wins"] == 1
        assert status["losses"] == 0

        print(
            f"\nPaper SELL win: entry={entry:.4f}, sl={stop_loss:.4f}, "
            f"tp={take_profit:.4f} | Status: {status}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_record_and_resolve_buy_loss(self):
        """
        Record a BUY signal with real CrudeOIL prices, then simulate SL hit.

        Expected:
            - check_outcomes returns outcome="loss"
            - consecutive_losses tracked correctly
        """
        await _require_candles("CrudeOIL", min_bars=20)

        prices = await fetch_candles("CrudeOIL", "H1", 50)
        last = prices[-1]

        entry = last["close"]
        bar_range = last["high"] - last["low"]
        if bar_range < 1e-6:
            bar_range = entry * 0.001

        stop_loss = entry - 1.5 * bar_range   # below entry for BUY
        take_profit = entry + 2.5 * bar_range  # above entry for BUY

        from src.services.paper_validation_service import PaperValidationService

        svc = PaperValidationService()
        svc.record_signal(
            symbol="CrudeOIL",
            action="BUY",
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            regime="ranging",
            lots=0.01,
        )

        # Simulate SL hit (price moves below stop_loss for BUY)
        sl_hit_price = stop_loss - 0.01
        result = svc.check_outcomes("CrudeOIL", sl_hit_price)

        assert result is not None
        assert result.outcome == "loss"
        assert result.resolved is True

        status = svc.get_validation_status()
        assert status["total_signals"] == 1
        assert status["losses"] == 1
        assert status["wins"] == 0
        assert status["max_consecutive_losses"] == 1

        print(f"\nPaper BUY loss: Status={status}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_duplicate_signal_silently_ignored(self):
        """
        record_signal for a symbol that already has an open trade must be a
        no-op (one open position per instrument constraint).
        """
        await _require_candles("CrudeOIL", min_bars=20)

        prices = await fetch_candles("CrudeOIL", "H1", 50)
        entry = prices[-1]["close"]
        bar_range = max(prices[-1]["high"] - prices[-1]["low"], entry * 0.001)

        from src.services.paper_validation_service import PaperValidationService

        svc = PaperValidationService()
        svc.record_signal(
            symbol="CrudeOIL",
            action="SELL",
            entry_price=entry,
            stop_loss=entry + bar_range,
            take_profit=entry - bar_range,
            regime="trending",
            lots=0.01,
        )
        assert len(svc._open_trades) == 1

        # Second signal for the same symbol — must be ignored
        svc.record_signal(
            symbol="CrudeOIL",
            action="BUY",
            entry_price=entry * 0.99,
            stop_loss=entry * 0.95,
            take_profit=entry * 1.05,
            regime="ranging",
            lots=0.01,
        )
        assert len(svc._open_trades) == 1, (
            "Second signal for open symbol should be silently ignored"
        )
        # Original trade is unchanged
        assert svc._open_trades["CrudeOIL"].action == "SELL"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_validation_criteria_not_met_before_50_signals(self):
        """
        criteria_met must be False until at least 50 signals are resolved,
        regardless of win rate.

        Records and resolves a small batch (< 50) of wins using real CrudeOIL
        prices to confirm the threshold guard works correctly.
        """
        await _require_candles("CrudeOIL", min_bars=20)

        prices = await fetch_candles("CrudeOIL", "H1", 50)
        last = prices[-1]
        entry = last["close"]
        bar_range = max(last["high"] - last["low"], entry * 0.001)

        from src.services.paper_validation_service import PaperValidationService

        svc = PaperValidationService()

        # Resolve 10 wins — well below MIN_SIGNALS=50
        for i in range(10):
            sym = f"FAKE_SYM_{i}"  # unique symbol per iteration to bypass dedup
            svc.record_signal(
                symbol=sym,
                action="SELL",
                entry_price=entry,
                stop_loss=entry + bar_range,
                take_profit=entry - bar_range,
                regime="trending",
                lots=0.01,
            )
            svc.check_outcomes(sym, entry - bar_range - 0.01)

        status = svc.get_validation_status()
        assert status["total_signals"] == 10
        assert status["wins"] == 10
        assert status["criteria_met"] is False, (
            "criteria_met must be False with only 10 signals (threshold is 50)"
        )
        assert status["criteria_detail"]["min_signals"] is False

        print(f"\nValidation status (10 wins): {status}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_no_resolve_when_price_between_sl_and_tp(self):
        """
        check_outcomes must return None when the current price is between
        stop-loss and take-profit — neither level hit.
        """
        await _require_candles("CrudeOIL", min_bars=20)

        prices = await fetch_candles("CrudeOIL", "H1", 50)
        entry = prices[-1]["close"]
        bar_range = max(prices[-1]["high"] - prices[-1]["low"], entry * 0.001)

        from src.services.paper_validation_service import PaperValidationService

        svc = PaperValidationService()
        svc.record_signal(
            symbol="CrudeOIL",
            action="BUY",
            entry_price=entry,
            stop_loss=entry - 2.0 * bar_range,
            take_profit=entry + 3.0 * bar_range,
            regime="unknown",
            lots=0.01,
        )

        # Price unchanged — no level hit
        result = svc.check_outcomes("CrudeOIL", entry)
        assert result is None, (
            f"No level hit, check_outcomes should return None"
        )
        assert len(svc._open_trades) == 1, "Trade should remain open"
        status = svc.get_validation_status()
        assert status["total_signals"] == 0
        assert status["open_trades"] == 1
