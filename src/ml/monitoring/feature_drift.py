"""
FeatureDriftMonitor - Detects out-of-distribution feature values.

Uses z-score method: if >30% of features have |z| > 3.0 relative to
training stats, the model is operating out-of-distribution (OOD) and
predictions should be suppressed.

Intended use: load once per model at startup, call ``check_drift()``
before every inference call.

Expected training_stats.json format (written by ReversalTrainingService):
    {
        "rsi":            {"mean": 53.2, "std": 14.1},
        "macd":           {"mean":  0.04, "std": 0.22},
        "bb_distance_pct": {"mean": -0.01, "std": 0.31},
        ...
    }

Z-score formula per feature:  z = |live_value - training_mean| / training_std

A feature is flagged as drifted when z > z_threshold (default 3.0).
The call returns ``is_drifted=True`` when the *fraction* of flagged
features exceeds ``drift_pct_threshold`` (default 30%).

Edge cases:
- Missing stats file: monitor is disabled — always returns not-drifted.
- Feature name not in stats: skipped (not counted toward total).
- std == 0: feature skipped (constant features can't drift meaningfully).
- 2D input array: only the last row (most-recent bar) is evaluated.
- All features missing from stats: returns (False, 0.0, {}).
"""
import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class FeatureDriftMonitor:
    """
    Detects when live feature values are outside the training distribution.

    Loads training feature statistics (mean, std) from a JSON file saved
    alongside the model and compares live feature values against them using
    per-feature z-scores.

    Attributes:
        _stats:  Dict mapping feature_name → {"mean": float, "std": float}.
                 Empty when stats file is absent (monitor disabled).
        _source: Path that was loaded, or None.

    Example::

        monitor = FeatureDriftMonitor(
            Path("models/reversal_classifier/CrudeOIL_H1/training_stats.json")
        )
        is_drifted, drift_pct, scores = monitor.check_drift(X[-1], feature_names)
        if is_drifted:
            logger.warning("OOD features — skipping ML prediction")
    """

    def __init__(self, training_stats_path: Path) -> None:
        """
        Load feature means and stds from a training run JSON file.

        If the file does not exist the monitor is silently disabled:
        ``check_drift()`` will always return ``(False, 0.0, {})``.

        Args:
            training_stats_path: Absolute or relative path to the JSON
                file produced during training.  Expected format::

                    {"feature_name": {"mean": float, "std": float}, ...}
        """
        self._stats: Dict[str, Dict[str, float]] = {}
        self._source: Path | None = None

        training_stats_path = Path(training_stats_path)
        if training_stats_path.exists():
            with open(training_stats_path) as f:
                self._stats = json.load(f)
            self._source = training_stats_path
            logger.info(
                "feature_drift_monitor_loaded",
                path=str(training_stats_path),
                n_features=len(self._stats),
            )
        else:
            logger.debug(
                "feature_drift_monitor_disabled",
                reason="stats_file_not_found",
                path=str(training_stats_path),
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_drift(
        self,
        features: np.ndarray,
        feature_names: List[str],
        z_threshold: float = 3.0,
        drift_pct_threshold: float = 0.30,
    ) -> Tuple[bool, float, Dict[str, float]]:
        """
        Check whether live feature values are drifted from training distribution.

        Args:
            features: 1-D array of shape ``(n_features,)`` *or* 2-D array of
                shape ``(n_bars, n_features)``.  When 2-D, only the **last
                row** (most-recent bar) is evaluated.
            feature_names: List of feature names corresponding to the columns
                of ``features``.  Length must match ``features.shape[-1]``.
            z_threshold: Minimum absolute z-score that marks a feature as
                out-of-distribution.  Default 3.0 (>3σ from training mean).
                Range: (0, ∞).
            drift_pct_threshold: Fraction of checked features that must
                exceed ``z_threshold`` before the batch is flagged as drifted.
                Default 0.30 (30%).  Range: (0, 1].

        Returns:
            A 3-tuple ``(is_drifted, drift_pct, per_feature_zscores)`` where:

            - ``is_drifted`` (bool): True when the drifted fraction exceeds
              ``drift_pct_threshold``.
            - ``drift_pct`` (float): Fraction of checked features with
              ``|z| > z_threshold``.  In [0.0, 1.0], rounded to 4 decimal
              places.  0.0 when no features could be checked.
            - ``per_feature_zscores`` (Dict[str, float]): Mapping of
              feature_name → z-score for every *drifted* feature only.
              Empty dict when nothing is drifted or when the monitor is
              disabled.

        Notes:
            - Features absent from the training stats file are skipped and
              do **not** count toward the drift fraction.
            - Features with ``std == 0`` are skipped (constant training
              distribution cannot be meaningfully compared).
            - When the stats file was absent at construction time this method
              always returns ``(False, 0.0, {})``.
        """
        # Monitor disabled — stats file was not found at construction time.
        if not self._stats or len(feature_names) == 0:
            return False, 0.0, {}

        # Normalise to 1-D: use last row for 2-D arrays.
        arr = np.asarray(features, dtype=float)
        if arr.ndim == 2:
            arr = arr[-1]

        drifted_features: Dict[str, float] = {}
        checked = 0
        drifted_count = 0

        for i, name in enumerate(feature_names):
            if i >= len(arr):
                break
            if name not in self._stats:
                continue  # feature not tracked — skip silently

            stats = self._stats[name]
            mean = float(stats.get("mean", 0.0))
            std = float(stats.get("std", 1.0))

            if std <= 0:
                continue  # constant feature — cannot compute z-score

            z = abs(float(arr[i]) - mean) / std
            checked += 1

            if z > z_threshold:
                drifted_count += 1
                drifted_features[name] = round(z, 2)

        if checked == 0:
            return False, 0.0, {}

        drift_pct = drifted_count / checked
        is_drifted = drift_pct > drift_pct_threshold

        if is_drifted:
            logger.warning(
                "feature_drift_detected",
                drift_pct=round(drift_pct, 3),
                drifted_count=drifted_count,
                total_checked=checked,
                top_drifted=dict(
                    sorted(drifted_features.items(), key=lambda x: -x[1])[:5]
                ),
            )

        return is_drifted, round(drift_pct, 4), drifted_features

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    def is_enabled(self) -> bool:
        """Return True when a stats file was successfully loaded."""
        return bool(self._stats)

    def tracked_features(self) -> List[str]:
        """Return sorted list of feature names present in the stats file."""
        return sorted(self._stats.keys())

    def get_stats(self, feature_name: str) -> Dict[str, float]:
        """
        Return training statistics for a single feature.

        Args:
            feature_name: Name of the feature to look up.

        Returns:
            Dict with ``"mean"`` and ``"std"`` keys, or empty dict if
            the feature is not tracked.
        """
        return dict(self._stats.get(feature_name, {}))
