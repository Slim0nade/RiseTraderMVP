"""
Unit tests for FeatureDriftMonitor.

All tests are pure numpy math — no database, no mocks, no MagicMock.

Scenarios covered:
  - No drift when live features closely match training stats
  - Drift detected when 50% of features are 5 std devs away
  - Empty stats (missing file) → monitor disabled, always returns not-drifted
  - 2D input array → last row is evaluated, not the first
  - Zero-std features are skipped (not counted toward drift fraction)
  - Boundary: exactly at z_threshold is NOT drifted (strict >)
  - Boundary: drift_pct exactly at drift_pct_threshold is NOT drifted (strict >)
  - Features missing from stats are silently skipped
  - is_enabled() and tracked_features() introspection helpers
  - get_stats() returns correct values for known and unknown features
  - drift_pct is rounded to 4 decimal places
  - per_feature_zscores only contains drifted features
"""

import json
import tempfile
from pathlib import Path
from typing import Dict

import numpy as np
import pytest

from src.ml.monitoring.feature_drift import FeatureDriftMonitor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_stats(tmp_path: Path, stats: Dict[str, Dict[str, float]]) -> Path:
    """
    Write a training_stats.json to tmp_path and return the file path.

    Args:
        tmp_path: Directory to write into.
        stats:    Dict mapping feature_name → {"mean": x, "std": y}.

    Returns:
        Full path to the written JSON file.
    """
    p = tmp_path / "training_stats.json"
    with open(p, "w") as f:
        json.dump(stats, f)
    return p


def _make_monitor(tmp_path: Path, stats: Dict[str, Dict[str, float]]) -> FeatureDriftMonitor:
    """Convenience: write stats file then build a monitor from it."""
    stats_path = _write_stats(tmp_path, stats)
    return FeatureDriftMonitor(stats_path)


def _simple_stats(n: int, mean: float = 50.0, std: float = 10.0) -> Dict:
    """Build stats dict for ``n`` features, all sharing the same mean/std."""
    return {f"feat_{i}": {"mean": mean, "std": std} for i in range(n)}


# ---------------------------------------------------------------------------
# Disabled monitor (no stats file)
# ---------------------------------------------------------------------------

class TestDisabledMonitor:
    """When the stats file is absent the monitor must never flag drift."""

    def test_missing_file_returns_not_drifted(self, tmp_path):
        monitor = FeatureDriftMonitor(tmp_path / "nonexistent.json")
        features = np.array([9999.0, 9999.0, 9999.0])
        is_drifted, drift_pct, scores = monitor.check_drift(features, ["a", "b", "c"])
        assert is_drifted is False

    def test_missing_file_drift_pct_is_zero(self, tmp_path):
        monitor = FeatureDriftMonitor(tmp_path / "nonexistent.json")
        _, drift_pct, _ = monitor.check_drift(np.ones(5), [f"f{i}" for i in range(5)])
        assert drift_pct == 0.0

    def test_missing_file_scores_empty(self, tmp_path):
        monitor = FeatureDriftMonitor(tmp_path / "nonexistent.json")
        _, _, scores = monitor.check_drift(np.ones(5), [f"f{i}" for i in range(5)])
        assert scores == {}

    def test_is_enabled_false_when_no_file(self, tmp_path):
        monitor = FeatureDriftMonitor(tmp_path / "nonexistent.json")
        assert monitor.is_enabled() is False

    def test_empty_feature_names_returns_not_drifted(self, tmp_path):
        """Empty feature names list → nothing to check → not drifted."""
        stats_path = _write_stats(tmp_path, {"feat_0": {"mean": 0.0, "std": 1.0}})
        monitor = FeatureDriftMonitor(stats_path)
        is_drifted, drift_pct, scores = monitor.check_drift(np.array([999.0]), [])
        assert is_drifted is False
        assert drift_pct == 0.0
        assert scores == {}


# ---------------------------------------------------------------------------
# No drift — features close to training distribution
# ---------------------------------------------------------------------------

class TestNoDrift:
    """Features within 1 std dev must not trigger a drift alarm."""

    def test_features_at_mean_no_drift(self, tmp_path):
        """
        Live features equal to the training mean have z=0 for all features.
        None should be flagged regardless of thresholds.
        """
        n = 10
        stats = _simple_stats(n, mean=50.0, std=10.0)
        monitor = _make_monitor(tmp_path, stats)
        # Exactly at training mean
        features = np.full(n, 50.0)
        names = [f"feat_{i}" for i in range(n)]
        is_drifted, drift_pct, scores = monitor.check_drift(features, names)
        assert is_drifted is False
        assert drift_pct == 0.0
        assert scores == {}

    def test_features_within_1std_no_drift(self, tmp_path):
        """Features 0.5 std devs away should not exceed the default z=3 threshold."""
        n = 8
        stats = _simple_stats(n, mean=50.0, std=10.0)
        monitor = _make_monitor(tmp_path, stats)
        # All features 5 units away from mean → z=0.5
        features = np.full(n, 55.0)
        names = [f"feat_{i}" for i in range(n)]
        is_drifted, _, _ = monitor.check_drift(features, names)
        assert is_drifted is False

    def test_features_just_below_z_threshold_no_drift(self, tmp_path):
        """
        A feature exactly AT z_threshold=3.0 is NOT drifted (strict >).
        All 10 features at z=3.0 should result in drift_pct=0.0.
        """
        n = 10
        stats = _simple_stats(n, mean=0.0, std=1.0)
        monitor = _make_monitor(tmp_path, stats)
        # z = |3.0 - 0.0| / 1.0 = 3.0 — exactly at threshold, NOT drifted
        features = np.full(n, 3.0)
        names = [f"feat_{i}" for i in range(n)]
        is_drifted, drift_pct, scores = monitor.check_drift(features, names, z_threshold=3.0)
        assert is_drifted is False
        assert drift_pct == 0.0


# ---------------------------------------------------------------------------
# Drift detected — features far from training distribution
# ---------------------------------------------------------------------------

class TestDriftDetected:
    """Scenarios where drift should be flagged."""

    def test_all_features_5std_away_is_drifted(self, tmp_path):
        """
        If every feature is 5σ from its training mean, drift_pct=1.0
        which is well above the 30% default threshold.
        """
        n = 10
        stats = _simple_stats(n, mean=70.0, std=5.0)
        monitor = _make_monitor(tmp_path, stats)
        # Each feature is 25 units away from mean=70 → z=5.0
        features = np.full(n, 95.0)
        names = [f"feat_{i}" for i in range(n)]
        is_drifted, drift_pct, scores = monitor.check_drift(features, names)
        assert is_drifted is True
        assert drift_pct == pytest.approx(1.0)
        assert len(scores) == n

    def test_50pct_features_5std_away_is_drifted(self, tmp_path):
        """
        Half the features are 5σ away (z=5.0), half are at the mean (z=0.0).
        drift_pct=0.50 exceeds the 0.30 default threshold → drifted.
        """
        n = 10
        stats = _simple_stats(n, mean=0.0, std=1.0)
        monitor = _make_monitor(tmp_path, stats)
        features = np.array(
            [5.0] * 5 + [0.0] * 5  # first 5 features at z=5, rest at z=0
        )
        names = [f"feat_{i}" for i in range(n)]
        is_drifted, drift_pct, scores = monitor.check_drift(features, names)
        assert is_drifted is True
        assert drift_pct == pytest.approx(0.5)
        # Only the 5 drifted features appear in scores
        assert len(scores) == 5
        for i in range(5):
            assert f"feat_{i}" in scores
        for i in range(5, 10):
            assert f"feat_{i}" not in scores

    def test_drifted_zscores_match_expected_values(self, tmp_path):
        """Z-scores in the returned dict must equal abs(live - mean) / std."""
        stats = {"price": {"mean": 70.0, "std": 5.0}}
        monitor = _make_monitor(tmp_path, stats)
        # z = |93.5 - 70.0| / 5.0 = 4.7
        features = np.array([93.5])
        names = ["price"]
        is_drifted, _, scores = monitor.check_drift(features, names)
        assert is_drifted is True
        assert scores["price"] == pytest.approx(4.7, abs=0.01)

    def test_drift_pct_just_above_threshold_is_drifted(self, tmp_path):
        """
        With 10 features, 4 drifted → drift_pct=0.40 > default 0.30 threshold.
        """
        n = 10
        stats = _simple_stats(n, mean=0.0, std=1.0)
        monitor = _make_monitor(tmp_path, stats)
        features = np.array([5.0] * 4 + [0.0] * 6)
        names = [f"feat_{i}" for i in range(n)]
        is_drifted, drift_pct, _ = monitor.check_drift(features, names)
        assert is_drifted is True
        assert drift_pct == pytest.approx(0.4)

    def test_drift_pct_exactly_at_threshold_not_drifted(self, tmp_path):
        """
        drift_pct=0.30 exactly is NOT drifted (strict >).
        With 10 features, 3 drifted → drift_pct=0.30 should NOT trigger.
        """
        n = 10
        stats = _simple_stats(n, mean=0.0, std=1.0)
        monitor = _make_monitor(tmp_path, stats)
        features = np.array([5.0] * 3 + [0.0] * 7)  # exactly 30%
        names = [f"feat_{i}" for i in range(n)]
        is_drifted, drift_pct, _ = monitor.check_drift(features, names, drift_pct_threshold=0.30)
        assert is_drifted is False
        assert drift_pct == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# 2D array handling — last row used
# ---------------------------------------------------------------------------

class TestTwoDArrayHandling:
    """2-D feature arrays must evaluate only the last row."""

    def test_2d_uses_last_row(self, tmp_path):
        """
        First row is far OOD, last row is at mean.
        Result must reflect the last row (not drifted).
        """
        n = 4
        stats = _simple_stats(n, mean=50.0, std=5.0)
        monitor = _make_monitor(tmp_path, stats)
        # Row 0: all features at z=10 (OOD)
        # Row 1: all features at mean (in distribution)
        features_2d = np.array([
            [100.0] * n,   # row 0: z=10, far OOD
            [50.0] * n,    # row 1: z=0, perfectly in distribution
        ])
        names = [f"feat_{i}" for i in range(n)]
        is_drifted, drift_pct, scores = monitor.check_drift(features_2d, names)
        assert is_drifted is False
        assert drift_pct == 0.0
        assert scores == {}

    def test_2d_last_row_drifted(self, tmp_path):
        """
        First row is at mean, last row is OOD.
        The monitor should detect drift from the last row.
        """
        n = 6
        stats = _simple_stats(n, mean=0.0, std=1.0)
        monitor = _make_monitor(tmp_path, stats)
        features_2d = np.array([
            [0.0] * n,    # row 0: in distribution
            [10.0] * n,   # row 1: z=10, all features OOD
        ])
        names = [f"feat_{i}" for i in range(n)]
        is_drifted, drift_pct, scores = monitor.check_drift(features_2d, names)
        assert is_drifted is True
        assert drift_pct == pytest.approx(1.0)

    def test_2d_many_rows_only_last_matters(self, tmp_path):
        """With 100 rows of OOD data and a normal last row, result is not drifted."""
        n = 5
        stats = _simple_stats(n, mean=0.0, std=1.0)
        monitor = _make_monitor(tmp_path, stats)
        ood_rows = np.full((99, n), 99.0)  # far OOD
        last_row = np.zeros((1, n))         # at mean
        features_2d = np.vstack([ood_rows, last_row])
        names = [f"feat_{i}" for i in range(n)]
        is_drifted, _, _ = monitor.check_drift(features_2d, names)
        assert is_drifted is False

    def test_1d_and_2d_give_identical_results(self, tmp_path):
        """1-D and a 2-D wrapper of the same data must produce identical output."""
        n = 6
        stats = _simple_stats(n, mean=50.0, std=5.0)
        monitor = _make_monitor(tmp_path, stats)
        row = np.array([75.0] * n)  # z=5 for every feature
        names = [f"feat_{i}" for i in range(n)]

        res_1d = monitor.check_drift(row, names)
        res_2d = monitor.check_drift(row.reshape(1, n), names)

        assert res_1d[0] == res_2d[0]  # is_drifted
        assert res_1d[1] == pytest.approx(res_2d[1])  # drift_pct
        assert res_1d[2] == res_2d[2]  # per_feature_zscores


# ---------------------------------------------------------------------------
# Zero-std features are skipped
# ---------------------------------------------------------------------------

class TestZeroStdSkipped:
    """Features with std == 0 in training stats must be excluded from the count."""

    def test_zero_std_features_not_counted(self, tmp_path):
        """
        2 features with std=1, 3 features with std=0.
        Only the 2 valid features are checked; drifting the zero-std ones
        must not affect drift_pct.
        """
        stats = {
            "feat_0": {"mean": 0.0, "std": 1.0},   # valid
            "feat_1": {"mean": 0.0, "std": 1.0},   # valid
            "feat_2": {"mean": 0.0, "std": 0.0},   # zero std — skipped
            "feat_3": {"mean": 0.0, "std": 0.0},   # zero std — skipped
            "feat_4": {"mean": 0.0, "std": 0.0},   # zero std — skipped
        }
        monitor = _make_monitor(tmp_path, stats)
        # Live values: feat_0 and feat_1 are at mean (z=0)
        # feat_2/3/4 have std=0 → skipped
        features = np.array([0.0, 0.0, 999.0, 999.0, 999.0])
        names = [f"feat_{i}" for i in range(5)]
        is_drifted, drift_pct, scores = monitor.check_drift(features, names)
        assert is_drifted is False
        assert drift_pct == 0.0

    def test_all_zero_std_returns_not_drifted(self, tmp_path):
        """
        If every feature has std=0 in training stats, checked==0 and
        the function must return (False, 0.0, {}) without division by zero.
        """
        stats = {f"feat_{i}": {"mean": 0.0, "std": 0.0} for i in range(5)}
        monitor = _make_monitor(tmp_path, stats)
        features = np.array([999.0] * 5)
        names = [f"feat_{i}" for i in range(5)]
        is_drifted, drift_pct, scores = monitor.check_drift(features, names)
        assert is_drifted is False
        assert drift_pct == 0.0
        assert scores == {}

    def test_zero_std_with_valid_drifted_features(self, tmp_path):
        """
        Mix: 2 valid drifted features + 3 zero-std features.
        Only the 2 valid features count → drift_pct = 2/2 = 1.0 (drifted).
        """
        stats = {
            "feat_0": {"mean": 0.0, "std": 1.0},
            "feat_1": {"mean": 0.0, "std": 1.0},
            "feat_2": {"mean": 0.0, "std": 0.0},
            "feat_3": {"mean": 0.0, "std": 0.0},
            "feat_4": {"mean": 0.0, "std": 0.0},
        }
        monitor = _make_monitor(tmp_path, stats)
        features = np.array([10.0, 10.0, 0.0, 0.0, 0.0])  # feat_0/1 at z=10
        names = [f"feat_{i}" for i in range(5)]
        is_drifted, drift_pct, scores = monitor.check_drift(features, names)
        assert is_drifted is True
        assert drift_pct == pytest.approx(1.0)
        assert len(scores) == 2


# ---------------------------------------------------------------------------
# Features missing from stats — silently skipped
# ---------------------------------------------------------------------------

class TestFeatureArrayShorterThanNames:
    """When the features array is shorter than feature_names, extra names are ignored."""

    def test_short_array_does_not_raise(self, tmp_path):
        """
        4 feature names but only 2 values in the array.
        The loop must break at i==2 without IndexError or crash.
        """
        stats = {f"feat_{i}": {"mean": 0.0, "std": 1.0} for i in range(4)}
        monitor = _make_monitor(tmp_path, stats)
        features = np.array([0.0, 0.0])  # only 2 values for 4 names
        names = [f"feat_{i}" for i in range(4)]
        is_drifted, drift_pct, scores = monitor.check_drift(features, names)
        # Only 2 features could be checked; both are at mean so not drifted
        assert is_drifted is False
        assert drift_pct == 0.0

    def test_short_array_drifted_features_counted_correctly(self, tmp_path):
        """
        2 drifted values out of 2 checked (4 names but 2 values).
        drift_pct should be 1.0 based on the 2 values that were checked.
        """
        stats = {f"feat_{i}": {"mean": 0.0, "std": 1.0} for i in range(4)}
        monitor = _make_monitor(tmp_path, stats)
        features = np.array([5.0, 5.0])  # both at z=5, both drifted
        names = [f"feat_{i}" for i in range(4)]
        is_drifted, drift_pct, scores = monitor.check_drift(features, names)
        assert is_drifted is True
        assert drift_pct == pytest.approx(1.0)
        assert len(scores) == 2


class TestMissingFeaturesSkipped:
    """Features absent from the stats file are skipped without error."""

    def test_unknown_feature_names_skipped(self, tmp_path):
        """
        Stats file has 3 features; feature_names contains 2 extra unknown ones.
        The 2 unknown features do not affect drift_pct.
        """
        stats = {
            "rsi":  {"mean": 50.0, "std": 15.0},
            "macd": {"mean":  0.0, "std":  0.5},
            "atr":  {"mean":  1.5, "std":  0.3},
        }
        monitor = _make_monitor(tmp_path, stats)
        # Values at training means → z=0 for all tracked features
        features = np.array([50.0, 0.0, 1.5, 999.0, 999.0])
        names = ["rsi", "macd", "atr", "new_feature_a", "new_feature_b"]
        is_drifted, drift_pct, scores = monitor.check_drift(features, names)
        assert is_drifted is False
        assert drift_pct == 0.0

    def test_all_features_unknown_returns_not_drifted(self, tmp_path):
        """
        When none of the live feature names appear in the stats file,
        checked==0 and the result must be (False, 0.0, {}).
        """
        stats = {"known_feat": {"mean": 0.0, "std": 1.0}}
        monitor = _make_monitor(tmp_path, stats)
        features = np.array([999.0, 999.0])
        names = ["unknown_a", "unknown_b"]
        is_drifted, drift_pct, scores = monitor.check_drift(features, names)
        assert is_drifted is False
        assert drift_pct == 0.0
        assert scores == {}


# ---------------------------------------------------------------------------
# Custom thresholds
# ---------------------------------------------------------------------------

class TestCustomThresholds:
    """Verify that z_threshold and drift_pct_threshold parameters are respected."""

    def test_tighter_z_threshold_catches_mild_drift(self, tmp_path):
        """
        At z_threshold=1.5, a feature 2σ away is flagged.
        At the default z_threshold=3.0, the same feature would not be flagged.
        """
        stats = {"rsi": {"mean": 50.0, "std": 10.0}}
        monitor = _make_monitor(tmp_path, stats)
        features = np.array([70.0])  # z = |70 - 50| / 10 = 2.0
        names = ["rsi"]
        # Default z_threshold=3.0: z=2.0 is NOT drifted
        not_drifted, _, _ = monitor.check_drift(features, names, z_threshold=3.0)
        assert not_drifted is False
        # Tighter z_threshold=1.5: z=2.0 IS drifted
        is_drifted, drift_pct, _ = monitor.check_drift(features, names, z_threshold=1.5)
        assert is_drifted is True
        assert drift_pct == pytest.approx(1.0)

    def test_lower_drift_pct_threshold_triggers_sooner(self, tmp_path):
        """
        20% drift_pct threshold: 2 out of 10 features drifted (20%) should trigger.
        30% drift_pct threshold: the same 2/10 (20%) should NOT trigger.
        """
        n = 10
        stats = _simple_stats(n, mean=0.0, std=1.0)
        monitor = _make_monitor(tmp_path, stats)
        features = np.array([5.0] * 2 + [0.0] * 8)  # 20% drifted
        names = [f"feat_{i}" for i in range(n)]

        # At 30% threshold (default): 20% is not enough
        not_drifted, _, _ = monitor.check_drift(features, names, drift_pct_threshold=0.30)
        assert not_drifted is False

        # At 20% threshold: 20% exactly is still NOT drifted (strict >)
        still_not, _, _ = monitor.check_drift(features, names, drift_pct_threshold=0.20)
        assert still_not is False  # strict >, so 0.20 > 0.20 is False

        # At 19% threshold: 20% exceeds 19% → drifted
        is_drifted, _, _ = monitor.check_drift(features, names, drift_pct_threshold=0.19)
        assert is_drifted is True


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------

class TestIntrospectionHelpers:
    """Tests for is_enabled(), tracked_features(), and get_stats()."""

    def test_is_enabled_true_when_stats_loaded(self, tmp_path):
        stats = {"rsi": {"mean": 50.0, "std": 10.0}}
        monitor = _make_monitor(tmp_path, stats)
        assert monitor.is_enabled() is True

    def test_tracked_features_returns_sorted_names(self, tmp_path):
        stats = {"zzz": {"mean": 0.0, "std": 1.0}, "aaa": {"mean": 0.0, "std": 1.0}}
        monitor = _make_monitor(tmp_path, stats)
        names = monitor.tracked_features()
        assert names == ["aaa", "zzz"]

    def test_get_stats_known_feature(self, tmp_path):
        stats = {"rsi": {"mean": 52.3, "std": 14.7}}
        monitor = _make_monitor(tmp_path, stats)
        result = monitor.get_stats("rsi")
        assert result["mean"] == pytest.approx(52.3)
        assert result["std"] == pytest.approx(14.7)

    def test_get_stats_unknown_feature_returns_empty(self, tmp_path):
        stats = {"rsi": {"mean": 50.0, "std": 10.0}}
        monitor = _make_monitor(tmp_path, stats)
        assert monitor.get_stats("nonexistent_feature") == {}

    def test_tracked_features_empty_when_disabled(self, tmp_path):
        monitor = FeatureDriftMonitor(tmp_path / "no_file.json")
        assert monitor.tracked_features() == []


# ---------------------------------------------------------------------------
# Numerical precision
# ---------------------------------------------------------------------------

class TestNumericalPrecision:
    """Verify rounding and floating-point behaviour."""

    def test_drift_pct_rounded_to_4_decimal_places(self, tmp_path):
        """drift_pct must be rounded to 4 decimal places."""
        # 1 feature drifted out of 3 → 0.3333...
        stats = _simple_stats(3, mean=0.0, std=1.0)
        monitor = _make_monitor(tmp_path, stats)
        features = np.array([5.0, 0.0, 0.0])  # only feat_0 drifted
        names = [f"feat_{i}" for i in range(3)]
        _, drift_pct, _ = monitor.check_drift(features, names)
        assert drift_pct == pytest.approx(round(1 / 3, 4), abs=1e-6)

    def test_per_feature_zscore_rounded_to_2_decimal_places(self, tmp_path):
        """Z-scores in the returned dict must be rounded to 2 decimal places."""
        stats = {"price": {"mean": 70.0, "std": 3.0}}
        monitor = _make_monitor(tmp_path, stats)
        # z = |79.5 - 70.0| / 3.0 = 9.5 / 3.0 = 3.1666...
        features = np.array([79.5])
        names = ["price"]
        _, _, scores = monitor.check_drift(features, names)
        assert "price" in scores
        assert scores["price"] == pytest.approx(round(9.5 / 3.0, 2), abs=1e-6)

    def test_large_zscore_does_not_overflow(self, tmp_path):
        """Very large feature values must not cause numerical overflow."""
        stats = {"feat_0": {"mean": 0.0, "std": 1e-6}}
        monitor = _make_monitor(tmp_path, stats)
        features = np.array([1e10])
        names = ["feat_0"]
        # Should not raise; z will be very large but finite
        is_drifted, drift_pct, scores = monitor.check_drift(features, names)
        assert is_drifted is True
        assert np.isfinite(scores["feat_0"])
