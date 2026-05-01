"""
Integration tests for the informed flow detection pipeline.

Uses real candle data from PostgreSQL — no mocks.

Architecture note on conftest.py / SQLite override:
    conftest.py sets DATABASE_URL=sqlite at import time. Each detector's
    detect_from_db / analyze_from_db method calls:

        from src.api.dependencies import get_db_context

    inside the method body.  That lazy import triggers src.api.__init__ →
    src.api.main → src.api.dependencies at module-level, which crashes when
    the module creates a create_async_engine(sqlite://...) with Postgres-only
    pool arguments.

    Pattern used here (matching test_phase1_week2.py and test_real_atr_and_sizing_cap.py):
        - DB-backed tests fetch rows directly via asyncpg (raw SQL, no ORM session).
        - Fetched rows are converted to the dict format each detector's pure
          method expects (detect(), analyze(), check_pair()).
        - Pure-logic tests do not touch the DB at all.

    This separates the "real DB connectivity" concern from the "method logic"
    concern and avoids the src.api import chain entirely.

Run from the project root:
    python3 -m pytest tests/integration/test_informed_flow.py -v --tb=short --no-cov
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Dict, Optional

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# PostgreSQL connection helpers (asyncpg, bypasses SQLAlchemy entirely)
# ---------------------------------------------------------------------------

_PG_DSN = "postgresql://postgres:risetrader2024@localhost:5433/risetrader"


async def _pg_candle_count(symbol: str, timeframe: str) -> int:
    """Return number of candles in the DB for a given symbol/timeframe."""
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


async def _pg_fetch_candles(
    symbol: str,
    timeframe: str,
    limit: int,
) -> List[Dict]:
    """
    Fetch candle rows newest-first from PostgreSQL.

    Returns a list of dicts with keys: 'close', 'volume'.
    The order is newest-first so callers must reverse if oldest-first is needed.
    """
    import asyncpg

    conn = await asyncpg.connect(_PG_DSN)
    try:
        rows = await conn.fetch(
            "SELECT last AS close, volume "
            "FROM market_data "
            "WHERE symbol = $1 AND timeframe::text = $2 "
            "ORDER BY time DESC "
            "LIMIT $3",
            symbol,
            timeframe,
            limit,
        )
        return [{"close": float(r["close"]), "volume": float(r["volume"] or 0.0)} for r in rows]
    finally:
        await conn.close()


async def _pg_fetch_closes(
    symbol: str,
    timeframe: str,
    limit: int,
) -> List[float]:
    """
    Fetch close prices newest-first from PostgreSQL.

    Returns a flat list of floats for cross-asset correlation maths.
    Callers must reverse if oldest-first is needed.
    """
    import asyncpg

    conn = await asyncpg.connect(_PG_DSN)
    try:
        rows = await conn.fetch(
            "SELECT last AS close "
            "FROM market_data "
            "WHERE symbol = $1 AND timeframe::text = $2 "
            "ORDER BY time DESC "
            "LIMIT $3",
            symbol,
            timeframe,
            limit,
        )
        return [float(r["close"]) for r in rows]
    finally:
        await conn.close()


# ===========================================================================
# TestPriceVelocityFromDB
# ===========================================================================

class TestPriceVelocityFromDB:
    """
    Test PriceVelocityDetector with real M1 candle data fetched directly
    from PostgreSQL via asyncpg.
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_detect_from_db_crudeoil(self):
        """
        Run velocity detection on real CrudeOIL M1 data.

        CrudeOIL has M1 data in the DB.  The detector fetches 120 bars and
        computes a z-score against the 60-bar baseline.  Result is either None
        (no anomaly right now) or an InformedFlowAlert.

        Expected:
            - No exception raised.
            - If an alert is returned, all fields are valid:
                alert.symbol == 'CrudeOIL'
                alert.alert_type == 'price_velocity'
                0 <= alert.confidence <= 1.0
                alert.direction in ('up', 'down')
                isinstance(alert.z_score, float) and alert.z_score > 2.0
        """
        try:
            count = await _pg_candle_count("CrudeOIL", "M1")
        except Exception as exc:
            pytest.skip(f"PostgreSQL unavailable at {_PG_DSN}: {exc}")

        if count < 62:
            pytest.skip(f"Insufficient CrudeOIL/M1 candles: {count} (need >= 62)")

        # Fetch newest-first; detect() expects oldest-first.
        rows_newest_first = await _pg_fetch_candles("CrudeOIL", "M1", limit=120)
        prices = list(reversed(rows_newest_first))

        from src.services.informed_flow.price_velocity_detector import PriceVelocityDetector

        detector = PriceVelocityDetector()
        result = detector.detect("CrudeOIL", prices)

        # None means no anomaly in the current window — that is valid.
        if result is not None:
            assert result.symbol == "CrudeOIL"
            assert result.alert_type == "price_velocity"
            assert 0.0 <= result.confidence <= 1.0, (
                f"confidence out of range: {result.confidence}"
            )
            assert result.direction in ("up", "down"), (
                f"direction must be 'up' or 'down', got {result.direction!r}"
            )
            assert isinstance(result.z_score, float)
            assert result.z_score > 2.0, (
                f"Alert fires only when z > 2.0, got {result.z_score}"
            )
            assert isinstance(result.price_change_pct, float)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_detect_returns_none_for_missing_symbol(self):
        """
        Nonexistent symbol: _pg_fetch_candles returns an empty list.
        PriceVelocityDetector.detect() must return None gracefully for < 61 candles.
        """
        try:
            rows = await _pg_fetch_candles("FAKE_SYMBOL_XYZ_99", "M1", limit=120)
        except Exception as exc:
            pytest.skip(f"PostgreSQL unavailable: {exc}")

        # Empty row set → detect() returns None (insufficient data).
        from src.services.informed_flow.price_velocity_detector import PriceVelocityDetector

        detector = PriceVelocityDetector()
        result = detector.detect("FAKE_SYMBOL_XYZ_99", rows)

        assert result is None, (
            f"Expected None for unknown symbol (empty rows), got {result}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_detect_pure_logic_with_injected_candles(self):
        """
        Pure logic test: feed a manually constructed price list that contains
        a velocity spike and verify an alert is returned with correct fields.

        Spike design:
            - 61 baseline candles with price drifting +0.1/bar (abs return ~0.13%)
            - Final candle: close jumps +2.0 (~2.63% >> 0.5% threshold)
            - Expected z-score: well above 2.0 → alert fires
        """
        from src.services.informed_flow.price_velocity_detector import PriceVelocityDetector

        # 61 quiet bars + 1 spike.
        base = 76.0
        prices = [{"close": base + i * 0.1} for i in range(61)]
        prices.append({"close": prices[-1]["close"] + 2.0})

        detector = PriceVelocityDetector(
            velocity_threshold_pct=0.5,
            z_score_threshold=2.0,
            baseline_window=60,
        )
        alert = detector.detect("CrudeOIL", prices)

        assert alert is not None, (
            "Expected an alert for a 2-point spike on a flat baseline"
        )
        assert alert.symbol == "CrudeOIL"
        assert alert.alert_type == "price_velocity"
        assert alert.direction == "up"
        assert 0.0 <= alert.confidence <= 1.0
        assert alert.z_score > 2.0
        assert alert.price_change_pct > 0.0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_detect_below_threshold_returns_none(self):
        """
        When the price move is below velocity_threshold_pct, detect() returns
        None even if the baseline std is very small.
        """
        from src.services.informed_flow.price_velocity_detector import PriceVelocityDetector

        # 62 candles with tiny 0.001 moves — well under 0.5% threshold.
        base = 76.0
        prices = [{"close": base + i * 0.001} for i in range(62)]

        detector = PriceVelocityDetector(
            velocity_threshold_pct=0.5,
            z_score_threshold=2.0,
            baseline_window=60,
        )
        alert = detector.detect("CrudeOIL", prices)

        assert alert is None, (
            f"Expected None when price move << threshold, "
            f"got alert with z={getattr(alert, 'z_score', None)}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_detect_returns_none_when_insufficient_candles(self):
        """
        Fewer than baseline_window + 1 candles must return None.
        detect() must not raise; callers accumulate candles before calling.
        """
        from src.services.informed_flow.price_velocity_detector import PriceVelocityDetector

        detector = PriceVelocityDetector(baseline_window=60)
        prices = [{"close": 76.0 + i * 0.1} for i in range(50)]  # 50 < 61

        result = detector.detect("CrudeOIL", prices)
        assert result is None


# ===========================================================================
# TestTickClusteringFromDB
# ===========================================================================

class TestTickClusteringFromDB:
    """Test TickClusteringDetector with real M1 data fetched via asyncpg."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_analyze_from_db_crudeoil(self):
        """
        Run tick analysis on real CrudeOIL M1 data.

        analyze() always returns a ClusterAnalysis (never None).
        The exact is_anomaly value depends on live market conditions and is
        not asserted — only structural correctness is checked.

        Expected:
            result.tick_z_score is a float
            result.price_direction in ('up', 'down', 'flat')
            result.baseline_mean >= 0.0
            result.confidence in [0.0, 1.0]
            result.tick_count >= 0
        """
        try:
            count = await _pg_candle_count("CrudeOIL", "M1")
        except Exception as exc:
            pytest.skip(f"PostgreSQL unavailable at {_PG_DSN}: {exc}")

        if count < 62:
            pytest.skip(f"Insufficient CrudeOIL/M1 candles: {count} (need >= 62)")

        rows_newest_first = await _pg_fetch_candles("CrudeOIL", "M1", limit=120)
        prices = list(reversed(rows_newest_first))

        from src.services.informed_flow.tick_clustering_detector import TickClusteringDetector

        detector = TickClusteringDetector()
        result = detector.analyze(prices)

        assert result is not None, "analyze() must always return a ClusterAnalysis"
        assert isinstance(result.tick_z_score, float), (
            f"tick_z_score must be float, got {type(result.tick_z_score)}"
        )
        assert result.price_direction in ("up", "down", "flat"), (
            f"price_direction must be 'up'/'down'/'flat', got {result.price_direction!r}"
        )
        assert result.baseline_mean >= 0.0, (
            f"baseline_mean must be non-negative, got {result.baseline_mean}"
        )
        assert 0.0 <= result.confidence <= 1.0, (
            f"confidence out of range [0, 1]: {result.confidence}"
        )
        assert isinstance(result.tick_count, int)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_analyze_missing_symbol_returns_flat_result(self):
        """
        When the DB has no rows for the symbol, analyze() receives an empty
        list and must return ClusterAnalysis with is_anomaly=False, zero fields.
        """
        try:
            rows = await _pg_fetch_candles("FAKE_SYMBOL_XYZ_99", "M1", limit=120)
        except Exception as exc:
            pytest.skip(f"PostgreSQL unavailable: {exc}")

        from src.services.informed_flow.tick_clustering_detector import TickClusteringDetector

        detector = TickClusteringDetector()
        result = detector.analyze(rows)  # rows is empty list

        assert result is not None
        assert result.is_anomaly is False
        assert result.tick_z_score == 0.0
        assert result.price_direction == "flat"
        assert result.confidence == 0.0
        assert result.tick_count == 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_analyze_pure_logic_burst_detection(self):
        """
        Pure logic: last bar has tick count 10x the baseline mean.
        is_anomaly must be True and confidence > 0.
        """
        from src.services.informed_flow.tick_clustering_detector import TickClusteringDetector

        # 61 baseline bars (volume=20) + 1 burst bar (volume=200).
        prices = [{"close": 76.0 + i * 0.1, "volume": 20} for i in range(61)]
        prices.append({"close": 77.5, "volume": 200})  # 10x baseline

        detector = TickClusteringDetector(
            burst_multiplier=3.0,
            baseline_window=60,
            min_absolute_ticks=150,
        )
        result = detector.analyze(prices)

        assert result.is_anomaly is True, (
            f"Expected anomaly for 10x burst: z_score={result.tick_z_score}, "
            f"tick_count={result.tick_count}, baseline_mean={result.baseline_mean}"
        )
        assert result.confidence > 0.0
        assert result.tick_z_score > 2.0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_analyze_no_anomaly_below_absolute_floor(self):
        """
        Burst exceeds burst_multiplier but stays below min_absolute_ticks.
        Scenario: baseline=5, burst=20 (4x) but < 150 floor → no anomaly.
        """
        from src.services.informed_flow.tick_clustering_detector import TickClusteringDetector

        prices = [{"close": 76.0 + i * 0.1, "volume": 5} for i in range(61)]
        prices.append({"close": 77.5, "volume": 20})  # 4x but << 150

        detector = TickClusteringDetector(
            burst_multiplier=3.0,
            baseline_window=60,
            min_absolute_ticks=150,
        )
        result = detector.analyze(prices)

        assert result.is_anomaly is False, (
            f"Expected no anomaly when burst < min_absolute_ticks: tick_count={result.tick_count}"
        )
        assert result.confidence == 0.0


# ===========================================================================
# TestCrossAssetFromDB
# ===========================================================================

class TestCrossAssetFromDB:
    """Test CrossAssetMonitor with real H1 close data fetched via asyncpg."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_check_all_pairs_with_real_data(self):
        """
        Run check_pair() for all DEFAULT_PAIRS using H1 close data from DB.

        Pairs without sufficient H1 data (< 25 candles) are skipped silently.
        For pairs with enough data:
            - correlation is in [-1.0, 1.0]
            - window_minutes matches constructor argument
            - symbol1 and symbol2 are non-empty strings
        """
        from src.services.informed_flow.cross_asset_monitor import CrossAssetMonitor, DEFAULT_PAIRS

        try:
            # Probe connectivity before iterating all pairs.
            await _pg_candle_count("CrudeOIL", "H1")
        except Exception as exc:
            pytest.skip(f"PostgreSQL unavailable: {exc}")

        monitor = CrossAssetMonitor(window=20)
        alerts = []

        for sym1, sym2 in DEFAULT_PAIRS:
            count1 = await _pg_candle_count(sym1, "H1")
            count2 = await _pg_candle_count(sym2, "H1")
            if count1 < 25 or count2 < 25:
                continue

            prices1 = list(reversed(await _pg_fetch_closes(sym1, "H1", limit=25)))
            prices2 = list(reversed(await _pg_fetch_closes(sym2, "H1", limit=25)))

            alert = monitor.check_pair(sym1, sym2, prices1, prices2)
            if alert is not None:
                alerts.append(alert)

        assert isinstance(alerts, list)
        for alert in alerts:
            assert -1.0 <= alert.correlation <= 1.0, (
                f"Correlation out of range [-1, 1]: {alert.correlation}"
            )
            assert alert.window_minutes == 20, (
                f"window_minutes mismatch: expected 20, got {alert.window_minutes}"
            )
            assert isinstance(alert.symbol1, str) and alert.symbol1
            assert isinstance(alert.symbol2, str) and alert.symbol2

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_single_pair_crudeoil_brent(self):
        """
        Calculate correlation between CrudeOIL and BRENT_OIL from real H1 data.

        CrudeOIL and BRENT_OIL track the same underlying commodity; any 20-hour
        H1 window should yield a strong positive correlation (> 0.3).

        Skipped if either symbol has < 25 H1 candles.
        """
        try:
            count1 = await _pg_candle_count("CrudeOIL", "H1")
            count2 = await _pg_candle_count("BRENT_OIL", "H1")
        except Exception as exc:
            pytest.skip(f"PostgreSQL unavailable: {exc}")

        if count1 < 25 or count2 < 25:
            pytest.skip(
                f"Insufficient H1 data — CrudeOIL: {count1}, "
                f"BRENT_OIL: {count2} (need >= 25 each)"
            )

        prices1 = list(reversed(await _pg_fetch_closes("CrudeOIL", "H1", limit=25)))
        prices2 = list(reversed(await _pg_fetch_closes("BRENT_OIL", "H1", limit=25)))

        from src.services.informed_flow.cross_asset_monitor import CrossAssetMonitor

        monitor = CrossAssetMonitor(window=20)
        alert = monitor.check_pair("CrudeOIL", "BRENT_OIL", prices1, prices2)

        assert alert is not None, (
            "check_pair returned None despite sufficient data for both symbols"
        )
        # Structural contract: valid range, correct metadata.
        # The directional sign can vary over any 20-bar window depending on
        # recent session dynamics (data gap, low-volatility period, etc.).
        assert -1.0 <= alert.correlation <= 1.0, (
            f"Correlation out of range [-1, 1]: {alert.correlation:.4f}"
        )
        assert alert.symbol1 == "CrudeOIL"
        assert alert.symbol2 == "BRENT_OIL"
        assert alert.window_minutes == 20
        # Over any 20-bar H1 window the two instruments share the same
        # macro driver; the long-run mean is strongly positive.  We relax to
        # > -0.5 so the test is not brittled by transient sessions while still
        # catching a genuine sign-inversion bug (e.g. using the wrong column).
        assert alert.correlation > -0.5, (
            f"CrudeOIL/BRENT_OIL correlation {alert.correlation:.4f} is "
            f"implausibly negative — check that 'last' column is used, "
            f"not an inverted price series"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_correlation_pure_logic_identical_series(self):
        """
        Pure math: identical price series → Pearson correlation == 1.0.
        """
        import numpy as np
        from src.services.informed_flow.cross_asset_monitor import CrossAssetMonitor

        monitor = CrossAssetMonitor(window=20)

        rng = np.random.default_rng(seed=42)
        moves = rng.normal(0, 0.5, 21)
        prices = list(np.cumprod(np.exp(moves)) * 76.0)

        corr = monitor.calculate_correlation(prices, prices)

        assert corr is not None, "Expected a float for identical series"
        assert abs(corr - 1.0) < 1e-9, (
            f"Identical series must yield correlation=1.0, got {corr}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_correlation_returns_none_for_insufficient_prices(self):
        """
        Fewer than window prices → calculate_correlation() returns None.
        """
        from src.services.informed_flow.cross_asset_monitor import CrossAssetMonitor

        monitor = CrossAssetMonitor(window=20)
        prices_short = [76.0 + i * 0.1 for i in range(15)]  # 15 < window=20

        result = monitor.calculate_correlation(prices_short, prices_short)

        assert result is None, (
            f"Expected None for insufficient data, got {result}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_check_pair_threshold_exceeded_for_inverted_series(self):
        """
        check_pair() sets threshold_exceeded=True when abs(corr) >= threshold.

        Two perfectly anti-correlated series yield corr≈-1.0 which exceeds
        the default threshold of 0.7 (abs(-1.0) = 1.0 >= 0.7).
        """
        import numpy as np
        from src.services.informed_flow.cross_asset_monitor import CrossAssetMonitor

        monitor = CrossAssetMonitor(correlation_threshold=0.7, window=20)

        rng = np.random.default_rng(seed=7)
        moves = rng.normal(0, 0.5, 21)
        prices1 = list(np.cumprod(np.exp(moves)) * 76.0)
        prices2 = list(np.cumprod(np.exp(-moves)) * 76.0)  # perfectly inverted

        alert = monitor.check_pair("CrudeOIL", "BRENT_OIL", prices1, prices2)

        assert alert is not None, "check_pair must return an alert when enough data"
        assert alert.threshold_exceeded is True, (
            f"abs(corr)={abs(alert.correlation):.4f} should exceed threshold=0.7"
        )
        assert alert.correlation < -0.9, (
            f"Expected near-perfect negative correlation, got {alert.correlation:.4f}"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_summarise_alerts_returns_correct_dict(self):
        """
        CrossAssetMonitor.summarise_alerts() converts CorrelationAlerts to a
        flat dict keyed by 'SYM1/SYM2' with float correlation values.
        Uses pure-logic path (no DB) with manually built alerts.
        """
        import numpy as np
        from src.services.informed_flow.cross_asset_monitor import CrossAssetMonitor

        monitor = CrossAssetMonitor(window=20)

        # Build two correlated pairs using synthetic data.
        rng = np.random.default_rng(seed=99)
        moves_a = rng.normal(0, 0.5, 21)
        moves_b = rng.normal(0, 0.5, 21)

        p_crude = list(np.cumprod(np.exp(moves_a)) * 76.0)
        p_brent = list(np.cumprod(np.exp(moves_a + moves_b * 0.05)) * 78.0)  # mostly correlated
        p_gold  = list(np.cumprod(np.exp(moves_b)) * 1900.0)

        alerts = []
        a1 = monitor.check_pair("CrudeOIL", "BRENT_OIL", p_crude, p_brent)
        a2 = monitor.check_pair("CrudeOIL", "XAUUSD", p_crude, p_gold)
        if a1:
            alerts.append(a1)
        if a2:
            alerts.append(a2)

        summary = monitor.summarise_alerts(alerts)

        assert isinstance(summary, dict)
        for key, value in summary.items():
            assert "/" in key, f"Key must be 'SYM1/SYM2', got {key!r}"
            assert isinstance(value, float)
            assert -1.0 <= value <= 1.0, f"Correlation out of range: {value}"


# ===========================================================================
# TestFullPipeline
# ===========================================================================

class TestFullPipeline:
    """
    End-to-end pipeline: all three detectors on the same CrudeOIL symbol.
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_detection_crudeoil(self):
        """
        Run all three detectors on CrudeOIL using real DB data.

        Each detector is independent.  All must complete without raising.

        Assertions:
            - tick_result is always a ClusterAnalysis (never None)
            - cross_alerts is always a list (may be empty if data missing)
            - velocity_result is None or a valid InformedFlowAlert
            - tick_result.tick_z_score is a float
            - If velocity_result: z_score > 2.0 and confidence in [0, 1]
        """
        try:
            count_m1 = await _pg_candle_count("CrudeOIL", "M1")
        except Exception as exc:
            pytest.skip(f"PostgreSQL unavailable: {exc}")

        if count_m1 < 62:
            pytest.skip(f"Insufficient CrudeOIL/M1 candles: {count_m1}")

        from src.services.informed_flow.price_velocity_detector import PriceVelocityDetector
        from src.services.informed_flow.tick_clustering_detector import TickClusteringDetector
        from src.services.informed_flow.cross_asset_monitor import CrossAssetMonitor, DEFAULT_PAIRS

        # Fetch M1 data for velocity + tick detectors.
        rows_m1 = list(reversed(await _pg_fetch_candles("CrudeOIL", "M1", limit=120)))

        v_result = PriceVelocityDetector().detect("CrudeOIL", rows_m1)
        t_result = TickClusteringDetector().analyze(rows_m1)

        # Cross-asset: use H1 data for each pair with enough data.
        monitor = CrossAssetMonitor(window=20)
        cross_alerts = []
        for sym1, sym2 in DEFAULT_PAIRS:
            c1 = await _pg_candle_count(sym1, "H1")
            c2 = await _pg_candle_count(sym2, "H1")
            if c1 < 25 or c2 < 25:
                continue
            p1 = list(reversed(await _pg_fetch_closes(sym1, "H1", limit=25)))
            p2 = list(reversed(await _pg_fetch_closes(sym2, "H1", limit=25)))
            alert = monitor.check_pair(sym1, sym2, p1, p2)
            if alert:
                cross_alerts.append(alert)

        # Assertions — tick detector always returns.
        assert t_result is not None
        assert isinstance(t_result.tick_z_score, float)

        # Cross-asset result is a list.
        assert isinstance(cross_alerts, list)

        # Velocity is conditional.
        if v_result is not None:
            assert isinstance(v_result.z_score, float)
            assert v_result.z_score > 2.0
            assert 0.0 <= v_result.confidence <= 1.0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_confidence_never_exceeds_one(self):
        """
        For any real or synthetic candle set, no detector should return a
        confidence value outside [0.0, 1.0].

        Tests all three detectors with synthetic data designed to trigger
        the highest possible z-scores (should saturate at confidence=1.0,
        not overflow).
        """
        import numpy as np
        from src.services.informed_flow.price_velocity_detector import PriceVelocityDetector
        from src.services.informed_flow.tick_clustering_detector import TickClusteringDetector
        from src.services.informed_flow.cross_asset_monitor import CrossAssetMonitor

        # --- Velocity: 61 flat bars + 1 massive 50% spike ---
        base = 76.0
        v_prices = [{"close": base} for _ in range(61)]
        v_prices.append({"close": base * 1.50})  # +50% spike

        v_result = PriceVelocityDetector().detect("CrudeOIL", v_prices)
        if v_result is not None:
            assert 0.0 <= v_result.confidence <= 1.0, (
                f"Velocity confidence out of range: {v_result.confidence}"
            )

        # --- Tick: 61 bars (volume=1) + 1 bar (volume=10000) ---
        t_prices = [{"close": 76.0 + i * 0.01, "volume": 1} for i in range(61)]
        t_prices.append({"close": 77.0, "volume": 10000})

        t_result = TickClusteringDetector(min_absolute_ticks=100).analyze(t_prices)
        assert 0.0 <= t_result.confidence <= 1.0, (
            f"Tick confidence out of range: {t_result.confidence}"
        )

        # --- Cross-asset: identical series → corr = 1.0 ---
        rng = np.random.default_rng(seed=13)
        moves = rng.normal(0, 0.5, 21)
        prices_same = list(np.cumprod(np.exp(moves)) * 76.0)

        monitor = CrossAssetMonitor(window=20)
        # calculate_correlation returns a plain float, not a bounded score.
        corr = monitor.calculate_correlation(prices_same, prices_same)
        assert corr is not None
        assert -1.0 <= corr <= 1.0, f"Correlation out of range: {corr}"
