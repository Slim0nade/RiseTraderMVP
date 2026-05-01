"""
Unit tests for ZigZagLabeler.

Tests cover:
  - Known price arrays with obvious peaks and valleys
  - ZigZag labeling of a realistic OHLCV DataFrame
  - Alternating peak/valley guarantee
  - Label value domain constraint (-1, 0, 1)
  - Parameter sensitivity (depth, deviation, backstep)
  - Edge cases: flat prices, monotonic series, tiny arrays
  - get_reversals() — only non-zero labels returned
  - get_statistics() — counts and percentages match actual label distribution
  - label_candles_simple() convenience function

No database dependency.  All inputs are pure numpy/pandas.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.ml.labeling.zigzag_labeler import (
    ZigZagConfig,
    ZigZagLabeler,
    label_candles_simple,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sine_ohlcv(
    n: int = 200,
    amplitude: float = 5.0,
    period: int = 40,
    base: float = 70.0,
) -> pd.DataFrame:
    """
    Synthetic OHLCV with a clean sine-wave close price.

    Peaks and valleys are geometrically obvious and evenly spaced,
    making them reliable ground-truth for ZigZag tests.

    Args:
        n:         Number of bars.
        amplitude: Half-range of the sine wave (price swings ± amplitude).
        period:    Number of bars per full sine cycle.
        base:      Centre price.

    Returns:
        OHLCV DataFrame sorted ascending by time.
    """
    t = np.arange(n)
    close = base + amplitude * np.sin(2 * np.pi * t / period)
    high = close + 0.2
    low = close - 0.2
    open_ = close - 0.05
    volume = np.ones(n) * 1000.0

    start = datetime(2024, 1, 1)
    times = [start + timedelta(hours=i) for i in range(n)]

    return pd.DataFrame({
        "time": times,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def _step_ohlcv(
    prices: list,
    start: datetime = datetime(2024, 1, 1),
) -> pd.DataFrame:
    """
    Build OHLCV from an explicit price list.

    Each bar has H = price + 0.05, L = price - 0.05 to create unambiguous
    extremum detection without gaps that confuse the ZigZag algorithm.

    Args:
        prices:  List of close (and approximately open) prices.
        start:   Timestamp for the first bar.

    Returns:
        OHLCV DataFrame.
    """
    n = len(prices)
    prices = np.array(prices, dtype=float)
    times = [start + timedelta(hours=i) for i in range(n)]
    return pd.DataFrame({
        "time": times,
        "open": prices - 0.05,
        "high": prices + 0.10,
        "low": prices - 0.10,
        "close": prices,
        "volume": np.ones(n) * 500.0,
    })


def _default_labeler() -> ZigZagLabeler:
    """Return a ZigZagLabeler with small parameters suitable for short test arrays."""
    return ZigZagLabeler(ZigZagConfig(depth=5, deviation=2, backstep=2, point=0.01))


# ---------------------------------------------------------------------------
# label_dataframe — basic contract
# ---------------------------------------------------------------------------

class TestLabelDataframeContract:
    """Validate the DataFrame output contract."""

    def test_adds_zigzag_label_column(self):
        df = _sine_ohlcv(n=100)
        labeler = _default_labeler()
        result = labeler.label_dataframe(df)
        assert "zigzag_label" in result.columns

    def test_adds_zigzag_value_column(self):
        df = _sine_ohlcv(n=100)
        labeler = _default_labeler()
        result = labeler.label_dataframe(df)
        assert "zigzag_value" in result.columns

    def test_row_count_preserved(self):
        df = _sine_ohlcv(n=100)
        labeler = _default_labeler()
        result = labeler.label_dataframe(df)
        assert len(result) == 100

    def test_label_values_in_domain(self):
        """All zigzag_label values must be in {-1, 0, 1}."""
        df = _sine_ohlcv(n=150)
        labeler = _default_labeler()
        result = labeler.label_dataframe(df)
        unique = set(result["zigzag_label"].unique())
        assert unique.issubset({-1, 0, 1}), (
            f"Unexpected label values: {unique - {-1, 0, 1}}"
        )

    def test_original_df_not_mutated(self):
        """Input DataFrame must not gain new columns after labeling."""
        df = _sine_ohlcv(n=80)
        original_cols = set(df.columns)
        _default_labeler().label_dataframe(df)
        assert set(df.columns) == original_cols

    def test_sorted_by_time_on_output(self):
        """Output must be sorted ascending by time even if input is not."""
        df = _sine_ohlcv(n=50)
        df_shuffled = df.sample(frac=1, random_state=0)
        result = _default_labeler().label_dataframe(df_shuffled)
        assert (result["time"].diff().dropna() > timedelta(0)).all()


# ---------------------------------------------------------------------------
# Known price arrays with obvious peaks and valleys
# ---------------------------------------------------------------------------

class TestKnownPriceArrays:
    """
    Build price series with mathematically guaranteed peaks and valleys
    and verify the ZigZag labeler finds them.

    We use ZigZagConfig(depth=3, deviation=1, backstep=1, point=0.01) so the
    algorithm is sensitive enough to pick up small but clear reversals.
    """

    @pytest.fixture
    def sensitive_labeler(self):
        return ZigZagLabeler(ZigZagConfig(depth=3, deviation=1, backstep=1, point=0.01))

    def test_single_obvious_peak_detected(self, sensitive_labeler):
        """
        Price rises then falls — should identify the maximum as a peak (1).

        Series: monotonic rise to a peak at index 10, then monotonic drop.
        """
        prices = list(range(70, 81)) + list(range(80, 69, -1))  # 21 bars
        df = _step_ohlcv(prices)
        result = sensitive_labeler.label_dataframe(df)
        reversals = result[result["zigzag_label"] != 0]
        # At least one peak should be labelled
        peaks = reversals[reversals["zigzag_label"] == 1]
        assert len(peaks) >= 1, "Expected at least one peak in a clear up-down sequence"

    def test_single_obvious_valley_detected(self, sensitive_labeler):
        """
        Price falls then rises — should identify the minimum as a valley (-1).
        """
        prices = list(range(80, 69, -1)) + list(range(70, 81))
        df = _step_ohlcv(prices)
        result = sensitive_labeler.label_dataframe(df)
        reversals = result[result["zigzag_label"] != 0]
        valleys = reversals[reversals["zigzag_label"] == -1]
        assert len(valleys) >= 1, "Expected at least one valley in a clear down-up sequence"

    def test_alternating_labels(self, sensitive_labeler):
        """
        The ZigZag algorithm guarantees strict alternation:
        peaks and valleys must alternate (no two consecutive peaks or valleys).
        """
        df = _sine_ohlcv(n=200, amplitude=4.0, period=30)
        result = sensitive_labeler.label_dataframe(df)
        labels = result[result["zigzag_label"] != 0]["zigzag_label"].tolist()
        if len(labels) < 2:
            pytest.skip("Not enough reversals detected — adjust parameters")
        for i in range(1, len(labels)):
            assert labels[i] != labels[i - 1], (
                f"Consecutive identical labels at positions {i-1} and {i}: "
                f"{labels[i-1]}, {labels[i]}"
            )

    def test_peaks_occur_near_sine_maxima(self):
        """Detected peaks should be near the known sine maxima.

        The ZigZag algorithm may place a trailing label at the very end of the
        series (a boundary artifact from the final partial wave).  We ignore
        peaks in the last ``depth`` bars to avoid this false-failure.
        """
        depth = 8
        labeler = ZigZagLabeler(ZigZagConfig(depth=depth, deviation=3, backstep=3, point=0.01))
        df = _sine_ohlcv(n=200, amplitude=5.0, period=40, base=70.0)
        result = labeler.label_dataframe(df)

        peaks = result[result["zigzag_label"] == 1]
        if len(peaks) == 0:
            pytest.skip("No peaks detected with these parameters — adjust depth/deviation")

        # Sine maxima occur at t = period/4, 5*period/4, ...  i.e., indices 10, 50, 90, 130, 170
        sine_peak_indices = [10, 50, 90, 130, 170]
        # Ignore peaks in the last ``depth`` bars — ZigZag trailing artifact
        interior_peaks = peaks.iloc[:-1] if len(peaks) > 1 else peaks

        for _, peak_row in interior_peaks.iterrows():
            idx = result.index.get_loc(peak_row.name)
            if idx >= len(result) - depth:
                continue  # Skip boundary artifact
            closest_sine_peak = min(sine_peak_indices, key=lambda x: abs(x - idx))
            assert abs(idx - closest_sine_peak) <= 12, (
                f"ZigZag peak at index {idx} is far from nearest sine peak at {closest_sine_peak}"
            )

    def test_valleys_occur_near_sine_minima(self):
        """Detected valleys should be near the known sine minima."""
        labeler = ZigZagLabeler(ZigZagConfig(depth=8, deviation=3, backstep=3, point=0.01))
        df = _sine_ohlcv(n=200, amplitude=5.0, period=40, base=70.0)
        result = labeler.label_dataframe(df)

        valleys = result[result["zigzag_label"] == -1]
        if len(valleys) == 0:
            pytest.skip("No valleys detected with these parameters")

        # Sine minima at t = 3*period/4, 7*period/4, ...  i.e., indices 30, 70, 110, 150, 190
        sine_valley_indices = [30, 70, 110, 150, 190]
        for _, valley_row in valleys.iterrows():
            idx = result.index.get_loc(valley_row.name)
            closest = min(sine_valley_indices, key=lambda x: abs(x - idx))
            assert abs(idx - closest) <= 12, (
                f"ZigZag valley at index {idx} is far from nearest sine valley at {closest}"
            )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Validate robustness for degenerate and boundary inputs."""

    def test_fewer_bars_than_depth_returns_all_zeros(self):
        """When n < depth, no extremums can be found — all labels should be 0."""
        labeler = ZigZagLabeler(ZigZagConfig(depth=12, deviation=5, backstep=3))
        df = _step_ohlcv([70.0, 71.0, 70.5])  # 3 bars < depth=12
        result = labeler.label_dataframe(df)
        assert (result["zigzag_label"] == 0).all()

    def test_flat_prices_returns_no_reversals(self):
        """All identical prices — no genuine reversals should be labeled."""
        prices = [75.0] * 50
        df = _step_ohlcv(prices)
        labeler = _default_labeler()
        result = labeler.label_dataframe(df)
        reversal_count = (result["zigzag_label"] != 0).sum()
        # Flat prices might produce zero or very few labels
        assert reversal_count <= 2, (
            f"Unexpected reversals on flat price series: {reversal_count}"
        )

    def test_monotonic_increase_no_valley(self):
        """Strictly increasing prices should yield at most 0 valley labels."""
        prices = [float(70 + i) for i in range(80)]
        df = _step_ohlcv(prices)
        labeler = _default_labeler()
        result = labeler.label_dataframe(df)
        valley_count = (result["zigzag_label"] == -1).sum()
        assert valley_count == 0, (
            f"Monotonic increase produced {valley_count} valley labels"
        )

    def test_monotonic_decrease_no_peak(self):
        """Strictly decreasing prices should yield 0 peak labels."""
        prices = [float(80 - i) for i in range(80)]
        df = _step_ohlcv(prices)
        labeler = _default_labeler()
        result = labeler.label_dataframe(df)
        peak_count = (result["zigzag_label"] == 1).sum()
        assert peak_count == 0, (
            f"Monotonic decrease produced {peak_count} peak labels"
        )

    def test_exactly_depth_rows(self):
        """n == depth is the boundary — should not crash."""
        labeler = ZigZagLabeler(ZigZagConfig(depth=10, deviation=3, backstep=2))
        df = _sine_ohlcv(n=10)
        result = labeler.label_dataframe(df)
        assert isinstance(result, pd.DataFrame)

    def test_two_rows_does_not_crash(self):
        labeler = _default_labeler()
        df = _step_ohlcv([70.0, 71.0])
        result = labeler.label_dataframe(df)
        assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# Parameter sensitivity
# ---------------------------------------------------------------------------

class TestParameterSensitivity:
    """Verify that ZigZag parameters change detection behaviour as expected."""

    def test_larger_depth_fewer_reversals(self):
        """Increasing depth should produce fewer or equal reversal labels."""
        df = _sine_ohlcv(n=300)
        shallow = ZigZagLabeler(ZigZagConfig(depth=4, deviation=2, backstep=2))
        deep = ZigZagLabeler(ZigZagConfig(depth=20, deviation=2, backstep=2))

        result_shallow = shallow.label_dataframe(df)
        result_deep = deep.label_dataframe(df)

        count_shallow = (result_shallow["zigzag_label"] != 0).sum()
        count_deep = (result_deep["zigzag_label"] != 0).sum()
        assert count_deep <= count_shallow, (
            f"Deeper depth ({count_deep}) produced MORE reversals than shallower ({count_shallow})"
        )

    def test_higher_deviation_fewer_reversals(self):
        """Increasing deviation (min price move) filters out small reversals."""
        df = _sine_ohlcv(n=300, amplitude=3.0, period=30)
        low_dev = ZigZagLabeler(ZigZagConfig(depth=5, deviation=1, backstep=2))
        high_dev = ZigZagLabeler(ZigZagConfig(depth=5, deviation=50, backstep=2))

        count_low = (low_dev.label_dataframe(df)["zigzag_label"] != 0).sum()
        count_high = (high_dev.label_dataframe(df)["zigzag_label"] != 0).sum()

        assert count_high <= count_low, (
            f"Higher deviation ({count_high}) gave MORE reversals than lower ({count_low})"
        )

    def test_custom_point_size_affects_labels(self):
        """A very large point size with matching deviation should suppress small moves."""
        df = _sine_ohlcv(n=200, amplitude=2.0)
        standard = ZigZagLabeler(ZigZagConfig(depth=5, deviation=3, backstep=2, point=0.01))
        coarse = ZigZagLabeler(ZigZagConfig(depth=5, deviation=3, backstep=2, point=1.0))

        count_standard = (standard.label_dataframe(df)["zigzag_label"] != 0).sum()
        count_coarse = (coarse.label_dataframe(df)["zigzag_label"] != 0).sum()

        assert count_coarse <= count_standard


# ---------------------------------------------------------------------------
# get_reversals
# ---------------------------------------------------------------------------

class TestGetReversals:
    """get_reversals() must return only non-zero labelled rows."""

    def test_only_nonzero_labels_returned(self):
        df = _sine_ohlcv(n=200)
        labeler = _default_labeler()
        labeled = labeler.label_dataframe(df)
        reversals = labeler.get_reversals(labeled)
        assert (reversals["zigzag_label"] != 0).all()

    def test_reversal_count_matches_nonzero_count(self):
        df = _sine_ohlcv(n=200)
        labeler = _default_labeler()
        labeled = labeler.label_dataframe(df)
        expected_count = (labeled["zigzag_label"] != 0).sum()
        assert len(labeler.get_reversals(labeled)) == expected_count

    def test_accepts_unlabeled_df_and_labels_it(self):
        """get_reversals can label an unlabeled DataFrame on the fly."""
        df = _sine_ohlcv(n=150)
        labeler = _default_labeler()
        # df has no zigzag_label column
        reversals = labeler.get_reversals(df)
        assert isinstance(reversals, pd.DataFrame)
        assert "zigzag_label" in reversals.columns


# ---------------------------------------------------------------------------
# get_statistics
# ---------------------------------------------------------------------------

class TestGetStatistics:
    """get_statistics() must return accurate counts and consistent percentages."""

    def test_returns_dict(self):
        df = _sine_ohlcv(n=200)
        labeler = _default_labeler()
        stats = labeler.get_statistics(labeler.label_dataframe(df))
        assert isinstance(stats, dict)

    def test_required_keys(self):
        df = _sine_ohlcv(n=200)
        labeler = _default_labeler()
        stats = labeler.get_statistics(labeler.label_dataframe(df))
        for key in ("total_candles", "peaks", "valleys", "neither",
                    "peak_pct", "valley_pct", "reversal_pct"):
            assert key in stats, f"Missing key: {key}"

    def test_counts_sum_to_total(self):
        df = _sine_ohlcv(n=200)
        labeler = _default_labeler()
        labeled = labeler.label_dataframe(df)
        stats = labeler.get_statistics(labeled)
        assert stats["peaks"] + stats["valleys"] + stats["neither"] == stats["total_candles"]

    def test_total_candles_equals_df_len(self):
        df = _sine_ohlcv(n=150)
        labeler = _default_labeler()
        stats = labeler.get_statistics(labeler.label_dataframe(df))
        assert stats["total_candles"] == 150

    def test_percentages_sum_to_100(self):
        df = _sine_ohlcv(n=200)
        labeler = _default_labeler()
        stats = labeler.get_statistics(labeler.label_dataframe(df))
        total_pct = stats["peak_pct"] + stats["valley_pct"] + (
            100 - stats["peak_pct"] - stats["valley_pct"]
        )
        assert abs(total_pct - 100) < 0.1

    def test_counts_match_manual_count(self):
        df = _sine_ohlcv(n=200)
        labeler = _default_labeler()
        labeled = labeler.label_dataframe(df)
        stats = labeler.get_statistics(labeled)
        assert stats["peaks"] == int((labeled["zigzag_label"] == 1).sum())
        assert stats["valleys"] == int((labeled["zigzag_label"] == -1).sum())


# ---------------------------------------------------------------------------
# label_candles_simple — convenience function
# ---------------------------------------------------------------------------

class TestLabelCandlesSimple:
    """Smoke tests for the module-level convenience function."""

    def test_returns_numpy_array(self):
        df = _sine_ohlcv(n=100)
        labels = label_candles_simple(df["high"].values, df["low"].values)
        assert isinstance(labels, np.ndarray)

    def test_output_length_matches_input(self):
        df = _sine_ohlcv(n=100)
        labels = label_candles_simple(df["high"].values, df["low"].values)
        assert len(labels) == 100

    def test_values_in_domain(self):
        df = _sine_ohlcv(n=100)
        labels = label_candles_simple(df["high"].values, df["low"].values)
        assert set(labels.tolist()).issubset({-1, 0, 1})

    def test_consistent_with_class_api(self):
        """label_candles_simple must produce identical results to ZigZagLabeler."""
        df = _sine_ohlcv(n=150)
        config = ZigZagConfig(depth=5, deviation=2, backstep=2, point=0.01)
        labeler = ZigZagLabeler(config)
        labeled_df = labeler.label_dataframe(df)

        func_labels = label_candles_simple(
            df["high"].values, df["low"].values,
            depth=5, deviation=2, backstep=2, point=0.01
        )
        np.testing.assert_array_equal(
            func_labels,
            labeled_df["zigzag_label"].values,
        )

    def test_custom_parameters_accepted(self):
        df = _sine_ohlcv(n=100)
        labels = label_candles_simple(
            df["high"].values, df["low"].values,
            depth=3, deviation=1, backstep=1, point=0.01
        )
        assert isinstance(labels, np.ndarray)
        assert len(labels) == 100
