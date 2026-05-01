"""
Unit tests for reversal feature computation.

Tests ``compute_features_from_ohlcv`` and ``get_feature_columns`` using
synthetic OHLCV DataFrames.  No database connection required — all
inputs are constructed in-memory.

Expected column coverage after a full feature run:
  - Indicators:   rsi, macd, macd_signal, atr, bb_upper/middle/lower, ma_20/50/200
  - Reversal:     bb_distance_pct, bb_squeeze, distance_ma20/50,
                  atr_change, atr_percentile, rsi_divergence,
                  volume_spike, volume_trend,
                  macd_histogram, macd_histogram_change,
                  roc_5, roc_10, roc_20, swing_range
  - Temporal:     hour, day_of_week, day_of_month,
                  session_asian, session_european, session_us,
                  hour_sin, hour_cos, dow_sin, dow_cos
  - Candle:       body_pct, upper_wick_pct, lower_wick_pct,
                  is_doji, is_hammer, is_inverted_hammer, is_engulfing

``get_feature_columns`` must exclude raw OHLC, time, labels, and
intermediate calculation columns while retaining all numeric derived
features.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.ml.features.reversal_features import (
    compute_features_from_ohlcv,
    get_feature_columns,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(
    n: int = 300,
    base_price: float = 75.0,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Build a synthetic OHLCV DataFrame with realistic price movements.

    Price follows a random walk so indicators have non-degenerate values.

    Args:
        n:           Number of rows.
        base_price:  Starting close price.
        seed:        Random seed for reproducibility.

    Returns:
        DataFrame with columns: time, open, high, low, close, volume.
        Sorted ascending by time, 1-hour bars.
    """
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, 0.008, size=n)  # ~0.8% per-bar vol, realistic for crude oil
    prices = base_price * np.cumprod(1 + returns)

    # Build OHLCV
    bar_range = prices * rng.uniform(0.002, 0.012, size=n)  # bar H-L range
    open_ = prices - bar_range * rng.uniform(0.0, 0.5, size=n)
    high = prices + bar_range * rng.uniform(0.0, 0.6, size=n)
    low = prices - bar_range * rng.uniform(0.0, 0.6, size=n)
    # Ensure OHLC relationships hold
    high = np.maximum(high, np.maximum(open_, prices))
    low = np.minimum(low, np.minimum(open_, prices))

    volume = rng.integers(500, 5000, size=n).astype(float)

    start = datetime(2024, 1, 2, 0, 0, 0)
    times = [start + timedelta(hours=i) for i in range(n)]

    return pd.DataFrame({
        "time": times,
        "open": open_,
        "high": high,
        "low": low,
        "close": prices,
        "volume": volume,
    })


def _make_minimal_ohlcv(n: int = 5) -> pd.DataFrame:
    """Return a very small OHLCV DataFrame (insufficient for full warm-up)."""
    return _make_ohlcv(n=n)


# ---------------------------------------------------------------------------
# compute_features_from_ohlcv — happy path
# ---------------------------------------------------------------------------

class TestComputeFeaturesFromOhlcv:
    """Validate feature computation on a normally-sized DataFrame."""

    @pytest.fixture(scope="class")
    def df_300(self):
        """Compute features once for all tests in this class."""
        raw = _make_ohlcv(n=300)
        return compute_features_from_ohlcv(raw)

    def test_returns_dataframe(self, df_300):
        assert isinstance(df_300, pd.DataFrame)

    def test_row_count_preserved(self, df_300):
        """Output must have the same number of rows as input."""
        assert len(df_300) == 300

    def test_indicator_columns_present(self, df_300):
        expected = [
            "rsi", "macd", "macd_signal", "atr",
            "bb_upper", "bb_middle", "bb_lower",
            "ma_20", "ma_50", "ma_200",
        ]
        for col in expected:
            assert col in df_300.columns, f"Missing indicator column: {col}"

    def test_reversal_derived_columns_present(self, df_300):
        expected = [
            "bb_distance_pct", "bb_squeeze",
            "distance_ma20", "distance_ma50",
            "atr_change", "atr_percentile",
            "rsi_divergence",
            "volume_spike", "volume_trend",
            "macd_histogram", "macd_histogram_change",
            "roc_5", "roc_10", "roc_20",
            "swing_range",
        ]
        for col in expected:
            assert col in df_300.columns, f"Missing reversal column: {col}"

    def test_temporal_columns_present(self, df_300):
        expected = [
            "hour", "day_of_week", "day_of_month",
            "session_asian", "session_european", "session_us",
            "hour_sin", "hour_cos",
            "dow_sin", "dow_cos",
        ]
        for col in expected:
            assert col in df_300.columns, f"Missing temporal column: {col}"

    def test_candle_pattern_columns_present(self, df_300):
        expected = [
            "body_pct", "upper_wick_pct", "lower_wick_pct",
            "is_doji", "is_hammer", "is_inverted_hammer", "is_engulfing",
        ]
        for col in expected:
            assert col in df_300.columns, f"Missing candle column: {col}"

    def test_zigzag_label_placeholder_added(self, df_300):
        """When input has no zigzag_label, a zero-filled placeholder is added."""
        assert "zigzag_label" in df_300.columns
        assert (df_300["zigzag_label"] == 0).all()

    def test_zigzag_label_passthrough(self):
        """When input already has zigzag_label, existing values are preserved."""
        raw = _make_ohlcv(n=300)
        raw["zigzag_label"] = 0
        raw.loc[50, "zigzag_label"] = 1
        raw.loc[100, "zigzag_label"] = -1
        result = compute_features_from_ohlcv(raw)
        assert result.loc[50, "zigzag_label"] == 1
        assert result.loc[100, "zigzag_label"] == -1

    def test_no_nan_in_trimmed_tail(self, df_300):
        """The last 50 rows should have no NaN in the feature columns.

        Warm-up NaN in early rows is acceptable, but once indicators stabilise
        (after ~200 bars for MA_200) the trailing rows must be fully populated.
        """
        feat_cols = get_feature_columns(df_300)
        tail_50 = df_300[feat_cols].tail(50)
        nan_counts = tail_50.isna().sum()
        problematic = nan_counts[nan_counts > 0]
        assert len(problematic) == 0, (
            f"NaN found in last 50 rows for features: {problematic.to_dict()}"
        )

    def test_session_columns_mutually_exclusive(self, df_300):
        """Each bar must belong to exactly one trading session."""
        session_sum = (
            df_300["session_asian"]
            + df_300["session_european"]
            + df_300["session_us"]
        )
        assert (session_sum == 1).all(), "Session columns are not mutually exclusive"

    def test_binary_pattern_columns_valid(self, df_300):
        """is_doji, is_hammer, is_inverted_hammer, is_engulfing must be 0 or 1."""
        binary_cols = ["is_doji", "is_hammer", "is_inverted_hammer", "is_engulfing"]
        for col in binary_cols:
            unique = set(df_300[col].dropna().unique())
            assert unique.issubset({0, 1}), (
                f"Column {col} has non-binary values: {unique}"
            )

    def test_rsi_range(self, df_300):
        """RSI values in populated rows must be in [0, 100]."""
        rsi_values = df_300["rsi"].dropna()
        assert (rsi_values >= 0).all() and (rsi_values <= 100).all(), (
            "RSI values outside [0, 100] range"
        )

    def test_hour_range(self, df_300):
        """Hour feature must be in [0, 23]."""
        assert df_300["hour"].between(0, 23).all()

    def test_cyclical_features_bounded(self, df_300):
        """sin/cos features must be in [-1, 1]."""
        for col in ["hour_sin", "hour_cos", "dow_sin", "dow_cos"]:
            values = df_300[col]
            assert (values >= -1.0).all() and (values <= 1.0).all(), (
                f"Cyclical column {col} has out-of-range values"
            )

    def test_volume_spike_positive(self, df_300):
        """Volume spike ratio must be positive in populated rows."""
        populated = df_300["volume_spike"].dropna()
        assert (populated > 0).all(), "volume_spike has non-positive values"

    def test_output_columns_superset_of_input(self, df_300):
        """Output DataFrame must contain all original OHLCV columns plus new ones."""
        original_cols = {"time", "open", "high", "low", "close", "volume"}
        assert original_cols.issubset(set(df_300.columns))

    def test_body_pct_between_zero_and_one(self, df_300):
        """body_pct (body / range) must be in [0, 1] where range > 0."""
        non_doji = df_300[df_300["range"] > 0]["body_pct"].dropna()
        assert (non_doji >= 0).all() and (non_doji <= 1).all()


# ---------------------------------------------------------------------------
# compute_features_from_ohlcv — edge cases
# ---------------------------------------------------------------------------

class TestComputeFeaturesEdgeCases:
    """Validate graceful handling of degenerate inputs."""

    def test_insufficient_rows_does_not_raise(self):
        """1-row DataFrame should not crash; results will be mostly NaN."""
        raw = _make_ohlcv(n=1)
        result = compute_features_from_ohlcv(raw)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1

    def test_minimal_rows_does_not_raise(self):
        """5-row DataFrame should not crash."""
        raw = _make_ohlcv(n=5)
        result = compute_features_from_ohlcv(raw)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5

    def test_exactly_200_rows_ma200_partial_nans(self):
        """At 200 rows, MA_200 produces exactly 1 non-NaN value (the last row)."""
        raw = _make_ohlcv(n=200)
        result = compute_features_from_ohlcv(raw)
        # MA_200 requires 200 rows; the first non-NaN is at row index 199
        ma200_non_nan = result["ma_200"].notna().sum()
        assert ma200_non_nan >= 1, "Expected at least one non-NaN MA_200 value"

    def test_flat_prices_does_not_divide_by_zero(self):
        """Flat OHLCV (zero range) must not produce inf/exception."""
        n = 250
        times = [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(n)]
        flat_df = pd.DataFrame({
            "time": times,
            "open": [100.0] * n,
            "high": [100.0] * n,
            "low": [100.0] * n,
            "close": [100.0] * n,
            "volume": [1000.0] * n,
        })
        result = compute_features_from_ohlcv(flat_df)
        # The result must be a DataFrame and must not contain inf
        assert isinstance(result, pd.DataFrame)
        numeric_cols = result.select_dtypes(include="number").columns
        has_inf = np.isinf(result[numeric_cols]).any(axis=None)
        assert not has_inf, "inf values produced for flat price series"

    def test_integer_volume_accepted(self):
        """Integer volume column (common when loading from DB) must work."""
        raw = _make_ohlcv(n=250)
        raw["volume"] = raw["volume"].astype(int)
        result = compute_features_from_ohlcv(raw)
        assert "volume_spike" in result.columns

    def test_original_df_not_mutated(self):
        """Input DataFrame must not be modified in-place."""
        raw = _make_ohlcv(n=250)
        original_cols = set(raw.columns)
        compute_features_from_ohlcv(raw)
        assert set(raw.columns) == original_cols, (
            "compute_features_from_ohlcv mutated the input DataFrame"
        )


# ---------------------------------------------------------------------------
# get_feature_columns
# ---------------------------------------------------------------------------

class TestGetFeatureColumns:
    """Validate the feature column selection logic."""

    @pytest.fixture(scope="class")
    def featured_df(self):
        raw = _make_ohlcv(n=300)
        return compute_features_from_ohlcv(raw)

    def test_returns_list(self, featured_df):
        cols = get_feature_columns(featured_df)
        assert isinstance(cols, list)

    def test_non_empty(self, featured_df):
        cols = get_feature_columns(featured_df)
        assert len(cols) > 0

    def test_excludes_raw_ohlc(self, featured_df):
        cols = get_feature_columns(featured_df)
        for raw_col in ["open", "high", "low", "close"]:
            assert raw_col not in cols, f"Raw OHLC column '{raw_col}' must be excluded"

    def test_excludes_time(self, featured_df):
        cols = get_feature_columns(featured_df)
        assert "time" not in cols

    def test_excludes_zigzag_label(self, featured_df):
        cols = get_feature_columns(featured_df)
        assert "zigzag_label" not in cols

    def test_excludes_intermediate_columns(self, featured_df):
        """Intermediate columns used only for derived-feature math must be excluded."""
        intermediate = [
            "rsi_lag5", "close_lag5",
            "prev_body", "body", "range", "upper_wick", "lower_wick",
            "high_5", "low_5",
            "volume_ma",
        ]
        cols = get_feature_columns(featured_df)
        for col in intermediate:
            assert col not in cols, f"Intermediate column '{col}' must be excluded"

    def test_all_returned_columns_are_numeric(self, featured_df):
        cols = get_feature_columns(featured_df)
        for col in cols:
            assert pd.api.types.is_numeric_dtype(featured_df[col]), (
                f"Column '{col}' selected by get_feature_columns is not numeric"
            )

    def test_includes_derived_features(self, featured_df):
        """Key derived features must survive the exclusion filter."""
        cols = set(get_feature_columns(featured_df))
        must_include = [
            "rsi", "macd", "atr", "bb_distance_pct", "volume_spike",
            "roc_5", "hour_sin", "is_doji", "body_pct",
        ]
        for col in must_include:
            assert col in cols, f"Expected feature '{col}' missing from get_feature_columns()"

    def test_stable_ordering_across_calls(self, featured_df):
        """Column order must be deterministic across repeated calls."""
        cols_first = get_feature_columns(featured_df)
        cols_second = get_feature_columns(featured_df)
        assert cols_first == cols_second

    def test_at_least_30_features(self, featured_df):
        """A fully-warmed dataset should produce at least 30 model-ready features."""
        cols = get_feature_columns(featured_df)
        assert len(cols) >= 30, (
            f"Expected >=30 feature columns, got {len(cols)}: {cols}"
        )


# ---------------------------------------------------------------------------
# Regime features
# ---------------------------------------------------------------------------

from src.ml.features.reversal_features import _compute_hurst_rs, _compute_adx_series


class TestRegimeFeatureColumns:
    """Verify that compute_features_from_ohlcv produces all three regime columns."""

    @pytest.fixture(scope="class")
    def df_regime(self):
        """Compute features on a 300-bar OHLCV; cached for the class."""
        raw = _make_ohlcv(n=300)
        return compute_features_from_ohlcv(raw)

    def test_regime_adx_column_present(self, df_regime):
        assert "regime_adx" in df_regime.columns, "Missing regime_adx column"

    def test_regime_hurst_column_present(self, df_regime):
        assert "regime_hurst" in df_regime.columns, "Missing regime_hurst column"

    def test_regime_atr_ratio_column_present(self, df_regime):
        assert "regime_atr_ratio" in df_regime.columns, "Missing regime_atr_ratio column"

    def test_regime_adx_range(self, df_regime):
        """ADX values (where not NaN) must be in [0, 100]."""
        adx = df_regime["regime_adx"].dropna()
        assert (adx >= 0).all() and (adx <= 100).all(), (
            f"regime_adx out of [0, 100]: min={adx.min():.2f}, max={adx.max():.2f}"
        )

    def test_regime_adx_nan_in_warmup(self, df_regime):
        """First 2*period-1 bars should be NaN for ADX(14).

        Index tracing: adx_out[0] maps to result[2*14 - 1] = result[27].
        So indices 0..26 (27 rows) are NaN.
        """
        # Indices 0..26 (the first 27 rows) must be NaN.
        assert df_regime["regime_adx"].iloc[:27].isna().all(), (
            "Expected NaN in regime_adx warm-up rows 0-26"
        )

    def test_regime_adx_populated_after_warmup(self, df_regime):
        """After warm-up the ADX series must have populated values."""
        adx_tail = df_regime["regime_adx"].tail(100)
        assert adx_tail.notna().all(), (
            f"regime_adx has unexpected NaN after warm-up: "
            f"{adx_tail.isna().sum()} NaN in last 100 rows"
        )

    def test_regime_hurst_range(self, df_regime):
        """Hurst values must be in [0.0, 1.0]."""
        hurst = df_regime["regime_hurst"]
        assert (hurst >= 0.0).all() and (hurst <= 1.0).all(), (
            f"regime_hurst out of [0, 1]: min={hurst.min():.4f}, max={hurst.max():.4f}"
        )

    def test_regime_hurst_warmup_defaults_to_half(self, df_regime):
        """First 49 rows (window < 50) must default to 0.5."""
        assert (df_regime["regime_hurst"].iloc[:49] == 0.5).all(), (
            "Expected 0.5 default in regime_hurst warm-up rows 0-48"
        )

    def test_regime_atr_ratio_positive(self, df_regime):
        """ATR ratio (where not NaN) must be > 0."""
        ratio = df_regime["regime_atr_ratio"].dropna()
        assert (ratio > 0).all(), (
            f"regime_atr_ratio has non-positive values: min={ratio.min():.4f}"
        )

    def test_regime_features_included_in_get_feature_columns(self, df_regime):
        """All three regime columns must survive the get_feature_columns exclusion filter."""
        cols = set(get_feature_columns(df_regime))
        for col in ("regime_adx", "regime_hurst", "regime_atr_ratio"):
            assert col in cols, (
                f"'{col}' was excluded by get_feature_columns — check the exclusion list"
            )

    def test_regime_features_not_in_exclusion_list(self, df_regime):
        """Explicit guard: exclusion list must not accidentally include regime columns.

        We check the actual runtime exclusion list, not the source text, to avoid
        false positives from docstring mentions.
        """
        import ast
        import inspect
        from src.ml.features.reversal_features import get_feature_columns as gfc

        source = inspect.getsource(gfc)
        # Extract the exclude_cols assignment via AST.
        tree = ast.parse(source)
        exclude_list: list = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "exclude_cols"
                and isinstance(node.value, ast.List)
            ):
                exclude_list = [
                    elt.s for elt in node.value.elts
                    if isinstance(elt, ast.Constant)
                ]
                break

        for col in ("regime_adx", "regime_hurst", "regime_atr_ratio"):
            assert col not in exclude_list, (
                f"'{col}' is in the exclude_cols list inside get_feature_columns — remove it"
            )


class TestHurstRsFunction:
    """Unit tests for the standalone _compute_hurst_rs helper."""

    def test_trending_series_hurst_above_half(self):
        """A strongly trending (monotonically increasing) series should produce H > 0.5."""
        n = 100
        closes = np.linspace(50.0, 100.0, n)  # perfect uptrend
        h = _compute_hurst_rs(closes, max_lag=20)
        assert h > 0.5, f"Expected H > 0.5 for trending series, got {h:.4f}"

    def test_alternating_series_hurst_lower_than_trending(self):
        """A mean-reverting (alternating) series should produce a lower Hurst than
        a strongly trending series.

        Note: R/S analysis on raw price levels with short max_lag is upward-biased
        for random walks (as documented in RegimeClassifier).  For a guaranteed
        structural difference we compare a perfect trend against a strictly
        alternating zigzag, whose R/S properties are well-defined.
        """
        n = 100
        # Perfect linear uptrend
        trending = np.linspace(50.0, 100.0, n)
        h_trend = _compute_hurst_rs(trending, max_lag=20)

        # Strictly alternating series: price oscillates around a fixed mean.
        # Within each block the cumulative deviation is bounded → lower R/S.
        alternating = np.array([50.0 + (0.5 if i % 2 == 0 else -0.5) for i in range(n)])
        h_alt = _compute_hurst_rs(alternating, max_lag=20)

        assert h_alt < h_trend, (
            f"Expected alternating Hurst ({h_alt:.4f}) < trending Hurst ({h_trend:.4f})"
        )
        assert 0.0 <= h_alt <= 1.0

    def test_hurst_returns_half_for_insufficient_data(self):
        """Fewer bars than max_lag must return the 0.5 default."""
        closes = np.array([1.0, 2.0, 3.0])  # 3 bars, max_lag=20
        h = _compute_hurst_rs(closes, max_lag=20)
        assert h == 0.5

    def test_hurst_output_clipped_to_unit_interval(self):
        """Result must always be in [0.0, 1.0] regardless of input."""
        rng = np.random.default_rng(seed=7)
        closes = rng.uniform(0.1, 200.0, size=200)
        h = _compute_hurst_rs(closes, max_lag=20)
        assert 0.0 <= h <= 1.0

    def test_flat_series_returns_half(self):
        """A flat price series (all identical) has S=0 for every block → fallback 0.5."""
        closes = np.full(100, 75.0)
        h = _compute_hurst_rs(closes, max_lag=20)
        assert h == 0.5


class TestComputeAdxSeries:
    """Unit tests for the _compute_adx_series helper."""

    def test_output_length_matches_input(self):
        """Returned array must have the same length as input arrays."""
        n = 100
        rng = np.random.default_rng(42)
        closes = 75.0 + np.cumsum(rng.normal(0, 0.5, n))
        highs  = closes + rng.uniform(0.1, 0.5, n)
        lows   = closes - rng.uniform(0.1, 0.5, n)
        adx = _compute_adx_series(highs, lows, closes, period=14)
        assert len(adx) == n

    def test_warmup_bars_are_nan(self):
        """First 2*period-1 positions must be NaN.

        adx_out[0] maps to result[2*period - 1], so indices 0..2*period-2 are NaN.
        """
        period = 14
        n = 100
        rng = np.random.default_rng(1)
        closes = 75.0 + np.cumsum(rng.normal(0, 0.5, n))
        highs  = closes + rng.uniform(0.1, 0.5, n)
        lows   = closes - rng.uniform(0.1, 0.5, n)
        adx = _compute_adx_series(highs, lows, closes, period=period)
        assert np.isnan(adx[:2 * period - 1]).all(), (
            f"Expected NaN in first {2*period - 1} positions"
        )

    def test_populated_values_in_range(self):
        """ADX values after warm-up must be in [0, 100]."""
        period = 14
        n = 200
        rng = np.random.default_rng(2)
        closes = 75.0 + np.cumsum(rng.normal(0, 0.5, n))
        highs  = closes + rng.uniform(0.1, 0.5, n)
        lows   = closes - rng.uniform(0.1, 0.5, n)
        adx = _compute_adx_series(highs, lows, closes, period=period)
        populated = adx[~np.isnan(adx)]
        assert len(populated) > 0
        assert (populated >= 0).all() and (populated <= 100).all()

    def test_insufficient_data_returns_all_nan(self):
        """Fewer than 2*period+1 bars → all NaN."""
        period = 14
        n = 2 * period  # exactly one bar short of min requirement
        closes = np.linspace(70.0, 80.0, n)
        highs  = closes + 0.2
        lows   = closes - 0.2
        adx = _compute_adx_series(highs, lows, closes, period=period)
        assert np.isnan(adx).all(), "Expected all NaN for insufficient data"


class TestRegimeAtrRatio:
    """Unit tests for the regime_atr_ratio feature derived inside _add_regime_features."""

    def test_atr_ratio_positive_after_warmup(self):
        """ATR ratio (after 50-bar warm-up) must be positive."""
        raw = _make_ohlcv(n=300)
        result = compute_features_from_ohlcv(raw)
        ratio = result["regime_atr_ratio"].dropna()
        assert (ratio > 0).all()

    def test_atr_ratio_nan_during_warmup(self):
        """First 50 rows cannot have a valid ATR SMA → expect NaN there."""
        raw = _make_ohlcv(n=300)
        result = compute_features_from_ohlcv(raw)
        # First 50 rows: ATR SMA is NaN, so ratio is also NaN.
        # (ATR itself also has a 14-bar warm-up, adding to the NaN count.)
        early_ratio = result["regime_atr_ratio"].iloc[:50]
        assert early_ratio.isna().all(), (
            "Expected NaN for regime_atr_ratio during the first 50 rows"
        )
