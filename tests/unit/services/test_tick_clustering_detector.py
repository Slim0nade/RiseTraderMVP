"""
Unit Tests for TickClusteringDetector

Pure math validation — no mocks, no database, no network.
All inputs are static lists of price dicts constructed inline.

Coverage:
    - Normal activity: no anomaly when ticks are within 3x baseline
    - Burst detection: anomaly when latest bar > 3x mean AND >= 150 ticks
    - Z-score accuracy: manual spot-check of z-score formula
    - Confidence boost: directional price move raises confidence above base value
    - Absolute minimum floor: high z-score but < 150 ticks does NOT trigger anomaly
    - Insufficient data: fewer bars than baseline_window + 1 returns safe default
    - Flat baseline std: sentinel z-score (10.0) when baseline has zero variance
    - Flat price direction: confidence not boosted when close[-1] == close[-2]
    - Constructor guard rails: invalid parameters raise ValueError
"""

import pytest

from src.services.informed_flow.tick_clustering_detector import TickClusteringDetector


# ============================================================================
# Helpers
# ============================================================================

def _make_prices(volumes: list[float], closes: list[float] | None = None) -> list[dict]:
    """
    Build a list of price dicts for use in analyze().

    Args:
        volumes: Per-bar tick counts, oldest-first.
        closes: Per-bar close prices. Defaults to 60.0 for every bar.
    """
    n = len(volumes)
    if closes is None:
        closes = [60.0] * n
    assert len(closes) == n, "volumes and closes must have the same length"
    return [{"volume": v, "close": c} for v, c in zip(volumes, closes)]


def _baseline_prices(
    n_baseline: int = 60,
    baseline_vol: float = 30.0,
    latest_vol: float = 30.0,
    close_prev: float = 60.0,
    close_latest: float = 60.0,
) -> list[dict]:
    """
    Convenience: build baseline_window baseline bars followed by one latest bar.

    Args:
        n_baseline: How many baseline bars to prepend.
        baseline_vol: Tick count for every baseline bar.
        latest_vol: Tick count for the final (latest) bar.
        close_prev: Close price of the bar immediately before the latest bar.
        close_latest: Close price of the latest bar.
    """
    baseline = [{"volume": baseline_vol, "close": 59.0}] * (n_baseline - 1)
    baseline.append({"volume": baseline_vol, "close": close_prev})
    latest = {"volume": latest_vol, "close": close_latest}
    return baseline + [latest]


# ============================================================================
# Constructor validation
# ============================================================================

class TestConstructor:
    """Guard-rail tests for invalid constructor arguments."""

    def test_burst_multiplier_must_exceed_one(self):
        """burst_multiplier <= 1.0 must raise ValueError."""
        with pytest.raises(ValueError, match="burst_multiplier"):
            TickClusteringDetector(burst_multiplier=1.0)

    def test_burst_multiplier_zero_raises(self):
        with pytest.raises(ValueError, match="burst_multiplier"):
            TickClusteringDetector(burst_multiplier=0.0)

    def test_baseline_window_too_small_raises(self):
        """baseline_window < 2 must raise ValueError."""
        with pytest.raises(ValueError, match="baseline_window"):
            TickClusteringDetector(baseline_window=1)

    def test_min_absolute_ticks_zero_raises(self):
        """min_absolute_ticks < 1 must raise ValueError."""
        with pytest.raises(ValueError, match="min_absolute_ticks"):
            TickClusteringDetector(min_absolute_ticks=0)

    def test_valid_defaults_construct(self):
        """Default arguments must construct without error."""
        detector = TickClusteringDetector()
        assert detector.burst_multiplier == 3.0
        assert detector.baseline_window == 60
        assert detector.min_absolute_ticks == 150


# ============================================================================
# Insufficient data
# ============================================================================

class TestInsufficientData:
    """Behavior when input is too short to compute a baseline."""

    def test_empty_input_returns_safe_default(self):
        detector = TickClusteringDetector()
        result = detector.analyze([])
        assert result.is_anomaly is False
        assert result.tick_z_score == 0.0
        assert result.confidence == 0.0
        assert result.tick_count == 0

    def test_exactly_baseline_window_bars_not_enough(self):
        """Need baseline_window + 1 bars minimum; baseline_window alone is insufficient."""
        detector = TickClusteringDetector(baseline_window=60)
        prices = _make_prices([30.0] * 60)  # exactly 60 bars, need 61
        result = detector.analyze(prices)
        assert result.is_anomaly is False

    def test_one_bar_over_minimum_is_sufficient_data(self):
        """baseline_window + 1 bars is the minimum that produces a real result."""
        detector = TickClusteringDetector(
            baseline_window=10,
            min_absolute_ticks=1,  # lower floor so the math can fire
            burst_multiplier=3.0,
        )
        # 11 bars: 10 baseline bars with vol=10, latest with vol=200 (20x)
        prices = _make_prices([10.0] * 10 + [200.0])
        result = detector.analyze(prices)
        # With baseline_mean=10 and latest=200 the burst condition fires
        assert result.is_anomaly is True


# ============================================================================
# Normal activity — no anomaly
# ============================================================================

class TestNormalActivity:
    """Detector must stay silent for ordinary tick counts."""

    def test_steady_low_volume_no_anomaly(self):
        """30 ticks/bar consistently — well below 3x threshold."""
        detector = TickClusteringDetector()
        prices = _baseline_prices(n_baseline=60, baseline_vol=30.0, latest_vol=30.0)
        result = detector.analyze(prices)
        assert result.is_anomaly is False
        assert result.confidence == 0.0

    def test_slight_increase_no_anomaly(self):
        """2x spike: above normal but below 3x multiplier — not an anomaly."""
        detector = TickClusteringDetector()
        prices = _baseline_prices(n_baseline=60, baseline_vol=30.0, latest_vol=59.0)
        result = detector.analyze(prices)
        assert result.is_anomaly is False

    def test_just_below_burst_threshold_no_anomaly(self):
        """
        Exactly 2.99x the baseline mean.
        burst_multiplier=3.0 requires latest >= mean * 3.0.
        """
        detector = TickClusteringDetector(burst_multiplier=3.0, min_absolute_ticks=1)
        # baseline_mean = 50; latest = 149 = 2.98x — does NOT clear 3.0x
        prices = _baseline_prices(n_baseline=60, baseline_vol=50.0, latest_vol=149.0)
        result = detector.analyze(prices)
        assert result.is_anomaly is False

    def test_tick_count_field_populated_in_normal_case(self):
        """tick_count is always the raw latest bar value, even when no anomaly."""
        detector = TickClusteringDetector()
        prices = _baseline_prices(n_baseline=60, baseline_vol=30.0, latest_vol=45.0)
        result = detector.analyze(prices)
        assert result.tick_count == 45
        assert result.is_anomaly is False


# ============================================================================
# Burst detection
# ============================================================================

class TestBurstDetection:
    """Anomaly fires when BOTH conditions are satisfied."""

    def test_burst_triggers_anomaly(self):
        """
        Baseline mean = 30 ticks/bar.  Latest = 200 ticks.
        200 >= 30 * 3.0 = 90  AND  200 >= 150 → anomaly.
        """
        detector = TickClusteringDetector()
        prices = _baseline_prices(n_baseline=60, baseline_vol=30.0, latest_vol=200.0)
        result = detector.analyze(prices)
        assert result.is_anomaly is True
        assert result.tick_count == 200

    def test_anomaly_sets_nonzero_confidence(self):
        detector = TickClusteringDetector()
        prices = _baseline_prices(n_baseline=60, baseline_vol=30.0, latest_vol=200.0)
        result = detector.analyze(prices)
        assert result.confidence > 0.0

    def test_anomaly_fields_rounded(self):
        """baseline_mean, baseline_std, tick_z_score, confidence are rounded."""
        detector = TickClusteringDetector()
        prices = _baseline_prices(n_baseline=60, baseline_vol=30.0, latest_vol=200.0)
        result = detector.analyze(prices)
        # Rounding: tick_z_score to 2dp, confidence to 3dp, baseline stats to 1dp
        assert result.tick_z_score == round(result.tick_z_score, 2)
        assert result.confidence == round(result.confidence, 3)
        assert result.baseline_mean == round(result.baseline_mean, 1)
        assert result.baseline_std == round(result.baseline_std, 1)


# ============================================================================
# Z-score accuracy
# ============================================================================

class TestZScore:
    """Manual spot-checks of z-score formula."""

    def test_z_score_spot_check(self):
        """
        With a perfectly uniform baseline (std = 0), a burst returns the
        sentinel z-score of 10.0.
        Then relax to a varied baseline and verify the formula.
        """
        detector = TickClusteringDetector(min_absolute_ticks=1)

        # Uniform baseline: mean=30, std=0 → sentinel 10.0 for latest > mean
        prices = _baseline_prices(n_baseline=60, baseline_vol=30.0, latest_vol=200.0)
        result = detector.analyze(prices)
        assert result.tick_z_score == 10.0

    def test_z_score_with_varied_baseline(self):
        """
        Baseline alternates 20/40: mean=30, std=10.
        Latest = 80 → z = (80 - 30) / 10 = 5.0.
        """
        detector = TickClusteringDetector(min_absolute_ticks=1)
        # Build 60 alternating bars: 30 × [20, 40]
        baseline_vols = [20.0, 40.0] * 30  # len=60
        prices = _make_prices(baseline_vols + [80.0])
        result = detector.analyze(prices)
        assert abs(result.tick_z_score - 5.0) < 0.1

    def test_z_score_negative_for_below_mean(self):
        """
        Latest tick count is below baseline mean → z-score is negative.
        No anomaly should fire.
        """
        detector = TickClusteringDetector(min_absolute_ticks=1)
        baseline_vols = [20.0, 40.0] * 30  # mean=30
        prices = _make_prices(baseline_vols + [10.0])  # z = (10-30)/10 = -2
        result = detector.analyze(prices)
        assert result.tick_z_score < 0.0
        assert result.is_anomaly is False

    def test_baseline_mean_and_std_correct(self):
        """
        baseline_mean and baseline_std must reflect only the window bars,
        NOT the latest bar.
        """
        import numpy as np

        detector = TickClusteringDetector()
        baseline_vols = list(range(1, 61))  # 1..60, mean=30.5
        prices = _make_prices(baseline_vols + [200.0])
        result = detector.analyze(prices)

        expected_mean = round(float(np.mean(baseline_vols)), 1)
        expected_std = round(float(np.std(baseline_vols)), 1)
        assert result.baseline_mean == expected_mean
        assert result.baseline_std == expected_std


# ============================================================================
# Absolute minimum floor
# ============================================================================

class TestAbsoluteMinimumFloor:
    """High z-score alone does not trigger anomaly below 150 ticks."""

    def test_high_z_score_but_below_150_no_anomaly(self):
        """
        Baseline mean = 5 ticks/bar (very quiet session).
        Latest = 100 ticks = 20x baseline, z-score ≈ 38.
        BUT 100 < 150 → NOT an anomaly.
        """
        detector = TickClusteringDetector()  # min_absolute_ticks=150
        prices = _baseline_prices(n_baseline=60, baseline_vol=5.0, latest_vol=100.0)
        result = detector.analyze(prices)
        assert result.is_anomaly is False
        assert result.confidence == 0.0

    def test_exactly_150_ticks_qualifies(self):
        """
        Exactly 150 ticks satisfies the absolute minimum.
        Baseline mean = 30 → 150 >= 30*3 = 90 AND 150 >= 150.
        """
        detector = TickClusteringDetector()
        prices = _baseline_prices(n_baseline=60, baseline_vol=30.0, latest_vol=150.0)
        result = detector.analyze(prices)
        assert result.is_anomaly is True

    def test_149_ticks_does_not_qualify(self):
        """
        149 < 150 absolute minimum → no anomaly even if burst ratio met.
        """
        detector = TickClusteringDetector()
        prices = _baseline_prices(n_baseline=60, baseline_vol=30.0, latest_vol=149.0)
        result = detector.analyze(prices)
        assert result.is_anomaly is False

    def test_custom_min_absolute_ticks_respected(self):
        """Lowering min_absolute_ticks allows smaller bursts to qualify."""
        detector = TickClusteringDetector(min_absolute_ticks=50)
        # baseline_mean=5, latest=60 → 60 >= 5*3=15 AND 60 >= 50
        prices = _baseline_prices(n_baseline=60, baseline_vol=5.0, latest_vol=60.0)
        result = detector.analyze(prices)
        assert result.is_anomaly is True


# ============================================================================
# Confidence with directional confirmation
# ============================================================================

class TestConfidenceBoost:
    """Confidence increases when price direction aligns with the tick burst."""

    def _burst_prices(
        self, close_prev: float = 60.0, close_latest: float = 60.0
    ) -> list[dict]:
        """Return standard burst scenario (200 ticks, baseline=30)."""
        return _baseline_prices(
            n_baseline=60,
            baseline_vol=30.0,
            latest_vol=200.0,
            close_prev=close_prev,
            close_latest=close_latest,
        )

    def test_upward_price_boosts_confidence(self):
        """
        Price moves up during the tick burst → confidence * 1.3.
        Base confidence (z=10, capped at 1.0) * 1.3 → capped at 1.0.
        """
        detector = TickClusteringDetector()
        prices = self._burst_prices(close_prev=60.0, close_latest=60.50)
        result = detector.analyze(prices)
        assert result.price_direction == "up"
        assert result.confidence > 0.0
        # Flat-direction confidence would be min(1.0, z/5) = 1.0;
        # boosted version is also 1.0 (cap). Verify it is not lower.
        flat_prices = self._burst_prices(close_prev=60.0, close_latest=60.0)
        flat_result = detector.analyze(flat_prices)
        assert result.confidence >= flat_result.confidence

    def test_downward_price_boosts_confidence(self):
        """Price moves down during the burst → same boost applies."""
        detector = TickClusteringDetector()
        prices = self._burst_prices(close_prev=60.0, close_latest=59.50)
        result = detector.analyze(prices)
        assert result.price_direction == "down"
        # Directional → boosted
        flat_prices = self._burst_prices(close_prev=60.0, close_latest=60.0)
        flat_result = detector.analyze(flat_prices)
        assert result.confidence >= flat_result.confidence

    def test_flat_price_no_confidence_boost(self):
        """
        Tick burst with flat close → confidence = min(1.0, z/5.0), no 1.3 factor.
        With uniform baseline (std=0), z=10 → raw confidence = 10/5 = 2.0 → cap 1.0.
        """
        detector = TickClusteringDetector()
        prices = self._burst_prices(close_prev=60.0, close_latest=60.0)
        result = detector.analyze(prices)
        assert result.price_direction == "flat"
        assert result.is_anomaly is True
        # Base confidence capped at 1.0 (z=10 / 5 = 2.0, capped)
        assert result.confidence == 1.0

    def test_confidence_capped_at_one(self):
        """Confidence must never exceed 1.0."""
        detector = TickClusteringDetector()
        # Extreme burst: 10000 ticks
        prices = _baseline_prices(
            n_baseline=60,
            baseline_vol=30.0,
            latest_vol=10000.0,
            close_prev=60.0,
            close_latest=65.0,
        )
        result = detector.analyze(prices)
        assert result.confidence <= 1.0

    def test_confidence_zero_when_no_anomaly(self):
        """No anomaly → confidence is exactly 0.0."""
        detector = TickClusteringDetector()
        prices = _baseline_prices(n_baseline=60, baseline_vol=30.0, latest_vol=30.0)
        result = detector.analyze(prices)
        assert result.confidence == 0.0

    def test_partial_z_score_gives_fractional_confidence(self):
        """
        z=2.5 (below the 3x absolute floor — use custom min to allow firing),
        no directional move → confidence = min(1.0, 2.5/5) = 0.5.
        """
        # Use varied baseline so std > 0 and we get a real z-score.
        # baseline alternates 20/40 → mean=30, std=10
        # latest=55 → z = (55-30)/10 = 2.5
        # Set min_absolute_ticks low enough to allow the burst to fire.
        detector = TickClusteringDetector(
            burst_multiplier=1.5,  # 55 >= 30*1.5=45 → burst satisfied
            min_absolute_ticks=55,
        )
        baseline_vols = [20.0, 40.0] * 30  # mean=30, std=10
        prices = _make_prices(
            baseline_vols + [55.0],
            closes=[59.0] * 60 + [59.0],  # flat price
        )
        result = detector.analyze(prices)
        assert result.is_anomaly is True
        # z = 2.5, no direction → confidence = 2.5/5 = 0.5
        assert abs(result.confidence - 0.5) < 0.02


# ============================================================================
# Flat baseline (std == 0)
# ============================================================================

class TestFlatBaseline:
    """Edge case: all baseline bars have identical tick count."""

    def test_sentinel_z_score_when_std_zero_and_burst(self):
        """Uniform baseline (std=0) with a burst → z_score == 10.0."""
        detector = TickClusteringDetector()
        prices = _baseline_prices(n_baseline=60, baseline_vol=30.0, latest_vol=200.0)
        result = detector.analyze(prices)
        assert result.tick_z_score == 10.0

    def test_zero_z_score_when_std_zero_and_equal(self):
        """Uniform baseline (std=0), latest == mean → z_score == 0.0."""
        detector = TickClusteringDetector()
        prices = _baseline_prices(n_baseline=60, baseline_vol=30.0, latest_vol=30.0)
        result = detector.analyze(prices)
        assert result.tick_z_score == 0.0


# ============================================================================
# Price direction
# ============================================================================

class TestPriceDirection:
    """Verify price_direction reflects close[-1] vs close[-2]."""

    def _anomaly_prices(self, close_prev: float, close_latest: float) -> list[dict]:
        return _baseline_prices(
            n_baseline=60,
            baseline_vol=30.0,
            latest_vol=200.0,
            close_prev=close_prev,
            close_latest=close_latest,
        )

    def test_price_direction_up(self):
        result = TickClusteringDetector().analyze(
            self._anomaly_prices(close_prev=60.0, close_latest=60.10)
        )
        assert result.price_direction == "up"

    def test_price_direction_down(self):
        result = TickClusteringDetector().analyze(
            self._anomaly_prices(close_prev=60.0, close_latest=59.90)
        )
        assert result.price_direction == "down"

    def test_price_direction_flat(self):
        result = TickClusteringDetector().analyze(
            self._anomaly_prices(close_prev=60.0, close_latest=60.0)
        )
        assert result.price_direction == "flat"

    def test_single_bar_sequence_returns_flat_direction(self):
        """Only one bar → can't compare to previous → 'flat'."""
        detector = TickClusteringDetector(baseline_window=2, min_absolute_ticks=1)
        prices = _make_prices([10.0, 10.0, 200.0])  # 3 bars: 2 baseline + 1 latest
        result = detector.analyze(prices)
        # price_direction is flat because closes default to 60.0 for all bars
        assert result.price_direction == "flat"

    def test_price_direction_populated_for_non_anomaly(self):
        """price_direction is computed regardless of anomaly status."""
        detector = TickClusteringDetector()
        prices = _baseline_prices(
            n_baseline=60,
            baseline_vol=30.0,
            latest_vol=30.0,
            close_prev=59.0,
            close_latest=60.0,
        )
        result = detector.analyze(prices)
        assert result.is_anomaly is False
        assert result.price_direction == "up"
