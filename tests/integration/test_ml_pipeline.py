"""
Integration Tests: ML Pipeline End-to-End

Tests the full pipeline:
  compute_features_from_ohlcv → ZigZag labels → XGBoost training → predict

All tests use synthetic OHLCV DataFrames — no database connection is
required.  The integration tests validate that each stage produces
output that the next stage accepts without error, mirroring the real
production data flow.

Design:
  - Tier-2 (Integration): Real data structures, real code paths.
  - No unittest.mock, MagicMock, or @patch.
  - Each test class covers one interface boundary.

Test classes:
  1. TestFeatureZigZagIntegration     — features feed into ZigZag labeler
  2. TestZigZagTrainingIntegration    — ZigZag labels feed into XGBoost
  3. TestTrainingPredictionIntegration — trained model feeds into predictor
  4. TestFullPipelineSmoke            — end-to-end smoke test of all stages
  5. TestReversalPredictorGraceful    — graceful degradation paths
"""

import json
import tempfile
from collections import deque
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xgboost as xgb

from src.ml.features.reversal_features import (
    compute_features_from_ohlcv,
    get_feature_columns,
)
from src.ml.labeling.zigzag_labeler import ZigZagConfig, ZigZagLabeler
from src.ml.inference.reversal_predictor import ReversalPredictor
from src.services.indicator_compute_service import compute_indicators_df


# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(
    n: int = 350,
    base: float = 75.0,
    vol: float = 0.008,
    seed: int = 7,
) -> pd.DataFrame:
    """
    Realistic random-walk OHLCV DataFrame.

    Args:
        n:    Number of bars (H1).
        base: Starting close price.
        vol:  Per-bar return volatility.
        seed: Reproducibility seed.

    Returns:
        DataFrame sorted ascending by time with columns:
        time, open, high, low, close, volume.
    """
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, vol, size=n)
    close = base * np.cumprod(1 + returns)

    bar_range = close * rng.uniform(0.003, 0.015, size=n)
    high = close + bar_range * rng.uniform(0.2, 0.8, size=n)
    low = close - bar_range * rng.uniform(0.2, 0.8, size=n)
    open_ = close + rng.uniform(-0.3, 0.3, size=n) * bar_range

    # Ensure OHLCV sanity
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    volume = rng.integers(300, 8000, size=n).astype(float)
    start = datetime(2024, 1, 2, 0, 0)
    times = [start + timedelta(hours=i) for i in range(n)]

    return pd.DataFrame({
        "time": times,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def _train_tiny_xgboost(X: np.ndarray, y: np.ndarray) -> xgb.Booster:
    """
    Train a minimal XGBoost booster on numpy arrays in-memory.

    Labels must be in {0, 1, 2} (mapped from {-1, 0, 1} by caller).

    Args:
        X: Feature matrix (N, F) float32.
        y: Labels (N,) int {0, 1, 2}.

    Returns:
        Trained xgb.Booster using multi:softprob objective.
    """
    dtrain = xgb.DMatrix(X.astype(np.float32), label=y.astype(np.float32))
    params = {
        "objective": "multi:softprob",
        "num_class": 3,
        "max_depth": 3,
        "learning_rate": 0.3,
        "tree_method": "hist",
        "eval_metric": "mlogloss",
    }
    booster = xgb.train(params, dtrain, num_boost_round=10, verbose_eval=False)
    return booster


def _save_booster_to_dir(
    booster: xgb.Booster,
    feature_names: list,
    model_dir: Path,
) -> Path:
    """
    Save booster + feature_names.json + metadata.json to model_dir.

    Returns the model_dir path.
    """
    model_dir.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(model_dir / "model.json"))
    with open(model_dir / "feature_names.json", "w") as f:
        json.dump(feature_names, f)
    metadata = {
        "model_name": "integration_test",
        "model_type": "xgboost",
        "reversal_f1": 0.10,
    }
    with open(model_dir / "metadata.json", "w") as f:
        json.dump(metadata, f)
    return model_dir


# ---------------------------------------------------------------------------
# Stage 1: compute_indicators_df
# ---------------------------------------------------------------------------

class TestIndicatorComputeIntegration:
    """Validate compute_indicators_df produces well-formed indicator columns."""

    def test_indicator_columns_present(self):
        raw = _make_ohlcv(n=300)
        df = compute_indicators_df(raw)
        for col in ["rsi", "macd", "macd_signal", "atr",
                    "bb_upper", "bb_middle", "bb_lower",
                    "ma_20", "ma_50", "ma_200"]:
            assert col in df.columns, f"Missing indicator column: {col}"

    def test_rsi_non_nan_after_warmup(self):
        """RSI(14) needs 14 bars — rows 14+ must have non-NaN RSI."""
        raw = _make_ohlcv(n=50)
        df = compute_indicators_df(raw)
        rsi_after_warmup = df["rsi"].iloc[14:]
        assert rsi_after_warmup.notna().all(), (
            "RSI has NaN values after the 14-bar warm-up period"
        )

    def test_macd_non_nan_after_warmup(self):
        """MACD(12,26) needs 26 bars for the slow EMA to stabilize."""
        raw = _make_ohlcv(n=60)
        df = compute_indicators_df(raw)
        macd_tail = df["macd"].iloc[26:]
        assert macd_tail.notna().all()

    def test_ma200_requires_200_bars(self):
        """MA_200 must be NaN for the first 199 rows."""
        raw = _make_ohlcv(n=250)
        df = compute_indicators_df(raw)
        # First 199 rows must be NaN
        assert df["ma_200"].iloc[:199].isna().all()
        # Row 199 (0-indexed) must be non-NaN
        assert pd.notna(df["ma_200"].iloc[199])

    def test_output_shapes_preserved(self):
        raw = _make_ohlcv(n=300)
        df = compute_indicators_df(raw)
        assert len(df) == 300

    def test_atr_positive_where_non_nan(self):
        """ATR must be positive everywhere it is non-NaN (ATR >= 0 by definition)."""
        raw = _make_ohlcv(n=100)
        df = compute_indicators_df(raw)
        atr = df["atr"].dropna()
        assert (atr >= 0).all()


# ---------------------------------------------------------------------------
# Stage 2: Features → ZigZag labels
# ---------------------------------------------------------------------------

class TestFeatureZigZagIntegration:
    """Features computed from OHLCV must be compatible with ZigZag output."""

    @pytest.fixture(scope="class")
    def featured(self):
        raw = _make_ohlcv(n=350)
        return compute_features_from_ohlcv(raw)

    @pytest.fixture(scope="class")
    def labeled(self):
        raw = _make_ohlcv(n=350)
        featured = compute_features_from_ohlcv(raw)
        labeler = ZigZagLabeler(ZigZagConfig(depth=8, deviation=3, backstep=3, point=0.01))
        return labeler.label_dataframe(featured)

    def test_zigzag_operates_on_featured_df(self, featured):
        """ZigZag labeler must accept a featured DataFrame as input."""
        labeler = ZigZagLabeler(ZigZagConfig(depth=8, deviation=3, backstep=3))
        result = labeler.label_dataframe(featured)
        assert "zigzag_label" in result.columns

    def test_zigzag_label_overrides_placeholder(self, labeled):
        """After labeling, at least some non-zero labels must be present."""
        non_zero = (labeled["zigzag_label"] != 0).sum()
        # With 350 bars and default params we expect at least a handful of reversals
        assert non_zero > 0, "ZigZag produced zero reversals on 350-bar sine-ish data"

    def test_feature_columns_survive_labeling(self, labeled):
        """All feature columns computed before labeling must still be present."""
        for col in ["rsi", "atr", "macd", "bb_distance_pct", "volume_spike"]:
            assert col in labeled.columns

    def test_row_count_unchanged_after_labeling(self, labeled):
        """Labeling must not drop any rows."""
        assert len(labeled) == 350

    def test_label_values_valid(self, labeled):
        unique = set(labeled["zigzag_label"].unique())
        assert unique.issubset({-1, 0, 1})


# ---------------------------------------------------------------------------
# Stage 3: ZigZag labels → XGBoost training
# ---------------------------------------------------------------------------

class TestZigZagTrainingIntegration:
    """
    Simulate the training pipeline: feature matrix + zigzag labels → XGBoost.

    Uses in-process training (no DB, no SMOTE) to keep the test fast.
    """

    @pytest.fixture(scope="class")
    def training_data(self):
        raw = _make_ohlcv(n=350, seed=42)
        featured = compute_features_from_ohlcv(raw)

        labeler = ZigZagLabeler(ZigZagConfig(depth=8, deviation=3, backstep=3))
        labeled = labeler.label_dataframe(featured)

        # Drop warm-up NaN rows (first ~200 bars)
        labeled = labeled.dropna(subset=get_feature_columns(featured))

        feature_cols = get_feature_columns(labeled)
        X = labeled[feature_cols].values.astype(np.float32)
        y = labeled["zigzag_label"].values  # {-1, 0, 1}
        return X, y, feature_cols

    def test_feature_matrix_is_finite(self, training_data):
        X, y, _ = training_data
        assert np.isfinite(X).all(), "Feature matrix contains NaN or inf"

    def test_class_distribution_not_all_zeros(self, training_data):
        """All samples should NOT be class 0 (neutral) — reversals must exist."""
        _, y, _ = training_data
        unique_classes = set(y.tolist())
        assert unique_classes != {0}, (
            "All labels are neutral (0) — ZigZag produced no reversal labels"
        )

    def test_xgboost_trains_without_error(self, training_data):
        X, y, _ = training_data
        # Map labels from {-1, 0, 1} to {0, 1, 2}
        y_mapped = y + 1
        booster = _train_tiny_xgboost(X, y_mapped)
        assert booster is not None

    def test_booster_predict_returns_correct_shape(self, training_data):
        X, y, _ = training_data
        y_mapped = y + 1
        booster = _train_tiny_xgboost(X, y_mapped)

        # Predict on a held-out slice
        X_test = X[:20]
        dtest = xgb.DMatrix(X_test)
        probs = booster.predict(dtest)
        assert probs.shape == (20, 3), (
            f"Expected (20, 3) probability array, got {probs.shape}"
        )

    def test_probabilities_sum_to_one(self, training_data):
        X, y, _ = training_data
        y_mapped = y + 1
        booster = _train_tiny_xgboost(X, y_mapped)
        X_test = X[:30]
        probs = booster.predict(xgb.DMatrix(X_test))
        row_sums = probs.sum(axis=1)
        np.testing.assert_allclose(row_sums, np.ones(30), atol=1e-5)

    def test_feature_names_passthrough(self, training_data):
        """Feature names must round-trip through DMatrix without corruption."""
        X, y, feature_cols = training_data
        y_mapped = (y + 1).astype(np.float32)
        dtrain = xgb.DMatrix(X, label=y_mapped, feature_names=feature_cols)
        assert dtrain.feature_names == feature_cols


# ---------------------------------------------------------------------------
# Stage 4: Trained booster → ReversalPredictor
# ---------------------------------------------------------------------------

class TestTrainingPredictionIntegration:
    """
    Verify that a booster trained on synthetic data loads correctly into
    ReversalPredictor and produces valid signal output.
    """

    @pytest.fixture(scope="class")
    def predictor_from_trained_model(self, tmp_path_factory):
        """
        Build feature matrix → train booster → save to tmp dir → load predictor.
        """
        tmp = tmp_path_factory.mktemp("trained")
        raw = _make_ohlcv(n=350, seed=99)
        featured = compute_features_from_ohlcv(raw)
        labeled = ZigZagLabeler(
            ZigZagConfig(depth=8, deviation=3, backstep=3)
        ).label_dataframe(featured)
        labeled = labeled.dropna(subset=get_feature_columns(featured))

        feature_cols = get_feature_columns(labeled)
        X = labeled[feature_cols].values.astype(np.float32)
        y = (labeled["zigzag_label"].values + 1).astype(np.float32)

        booster = _train_tiny_xgboost(X, y)
        model_dir = _save_booster_to_dir(booster, feature_cols, tmp / "model")

        return ReversalPredictor(session=None, model_path=model_dir)

    def test_predictor_loaded(self, predictor_from_trained_model):
        assert predictor_from_trained_model.is_loaded() is True

    def test_feature_names_match_training_feature_count(self, predictor_from_trained_model):
        """Feature count stored in predictor must match what was trained on."""
        assert predictor_from_trained_model.feature_names is not None
        # Must have at least 30 features (consistent with get_feature_columns guarantee)
        assert len(predictor_from_trained_model.feature_names) >= 30

    def test_booster_predict_on_fresh_features(self, predictor_from_trained_model):
        """Generate a fresh feature row and run it through the booster."""
        raw = _make_ohlcv(n=300, seed=123)
        featured = compute_features_from_ohlcv(raw)
        feature_cols = predictor_from_trained_model.feature_names

        # Use last row that has no NaN
        available = [c for c in feature_cols if c in featured.columns]
        last_row = featured[available].dropna().tail(1)
        assert len(last_row) == 1, "No NaN-free row found in feature DataFrame tail"

        X = last_row.values.astype(np.float32)
        dmatrix = xgb.DMatrix(X, feature_names=feature_cols)
        probs = predictor_from_trained_model.booster.predict(dmatrix)
        # Shape: (1, 3) for single sample
        assert probs.shape == (1, 3)
        np.testing.assert_allclose(probs.sum(axis=1), [1.0], atol=1e-5)

    def test_signal_interpretation_uses_thresholds(self, predictor_from_trained_model):
        """
        Simulate a scenario where peak_prob is clearly highest and above threshold.
        Verify _generate_signal returns SHORT.
        """
        signal, conf = predictor_from_trained_model._generate_signal(
            valley_prob=0.05,
            peak_prob=0.90,
            neutral_prob=0.05,
        )
        assert signal == "SHORT"
        assert conf == pytest.approx(0.90)

    def test_wait_when_no_threshold_exceeded(self, predictor_from_trained_model):
        signal, conf = predictor_from_trained_model._generate_signal(
            valley_prob=0.35,
            peak_prob=0.35,
            neutral_prob=0.30,
        )
        assert signal == "WAIT"


# ---------------------------------------------------------------------------
# Full pipeline smoke test
# ---------------------------------------------------------------------------

class TestFullPipelineSmoke:
    """
    End-to-end test: OHLCV → indicators → features → labels → train → predict.

    Does not require DB, MLflow, SMOTE, or any external service.
    Validates that all five stages chain together without error and
    that every output satisfies its downstream contract.
    """

    def test_pipeline_runs_end_to_end(self, tmp_path):
        # ---- Stage 1: raw OHLCV ----
        raw = _make_ohlcv(n=350, seed=5)
        assert len(raw) == 350

        # ---- Stage 2: indicators + reversal features ----
        featured = compute_features_from_ohlcv(raw)
        assert "rsi" in featured.columns
        assert "bb_distance_pct" in featured.columns

        # ---- Stage 3: ZigZag labels ----
        labeler = ZigZagLabeler(ZigZagConfig(depth=8, deviation=3, backstep=3))
        labeled = labeler.label_dataframe(featured)
        assert "zigzag_label" in labeled.columns

        # ---- Stage 4: Feature selection + drop NaN ----
        feature_cols = get_feature_columns(labeled)
        clean = labeled.dropna(subset=feature_cols)
        assert len(clean) > 0, "All rows dropped after NaN filter"

        X = clean[feature_cols].values.astype(np.float32)
        y = (clean["zigzag_label"].values + 1).astype(np.float32)
        assert np.isfinite(X).all()

        # ---- Stage 5: Train XGBoost ----
        booster = _train_tiny_xgboost(X, y)
        assert booster is not None

        # ---- Stage 6: Save model ----
        model_dir = _save_booster_to_dir(booster, feature_cols, tmp_path / "model")
        assert (model_dir / "model.json").exists()
        assert (model_dir / "feature_names.json").exists()

        # ---- Stage 7: Load into ReversalPredictor ----
        predictor = ReversalPredictor(session=None, model_path=model_dir)
        assert predictor.is_loaded() is True

        # ---- Stage 8: Inference on fresh features ----
        fresh_raw = _make_ohlcv(n=300, seed=77)
        fresh_featured = compute_features_from_ohlcv(fresh_raw)
        available = [c for c in feature_cols if c in fresh_featured.columns]
        last_row = fresh_featured[available].dropna().tail(1)
        assert len(last_row) == 1

        X_infer = last_row.values.astype(np.float32)
        dmatrix = xgb.DMatrix(X_infer, feature_names=feature_cols)
        probs = predictor.booster.predict(dmatrix)
        assert probs.shape == (1, 3)

        # Probability row must sum to 1
        np.testing.assert_allclose(probs.sum(axis=1), [1.0], atol=1e-5)

        # Signal generation must not crash
        valley_p, neutral_p, peak_p = float(probs[0, 0]), float(probs[0, 1]), float(probs[0, 2])
        signal, conf = predictor._generate_signal(valley_p, peak_p, neutral_p)
        assert signal in ("LONG", "SHORT", "WAIT")
        assert 0.0 <= conf <= 1.0

    def test_pipeline_consistent_feature_count(self, tmp_path):
        """
        Feature count must be identical between training and inference runs
        when both use the same compute_features_from_ohlcv call.
        """
        raw_train = _make_ohlcv(n=350, seed=11)
        raw_infer = _make_ohlcv(n=300, seed=22)

        feat_train = compute_features_from_ohlcv(raw_train)
        feat_infer = compute_features_from_ohlcv(raw_infer)

        cols_train = set(get_feature_columns(feat_train))
        cols_infer = set(get_feature_columns(feat_infer))

        assert cols_train == cols_infer, (
            f"Feature column mismatch between training and inference:\n"
            f"  Only in train: {cols_train - cols_infer}\n"
            f"  Only in infer: {cols_infer - cols_train}"
        )


# ---------------------------------------------------------------------------
# Graceful degradation paths
# ---------------------------------------------------------------------------

class TestReversalPredictorGraceful:
    """
    Verify ReversalPredictor handles missing models gracefully
    without raising unhandled exceptions.
    """

    def test_no_model_path_gives_unloaded_predictor(self):
        pred = ReversalPredictor(session=None)
        assert pred.is_loaded() is False

    def test_empty_prediction_has_correct_structure(self):
        pred = ReversalPredictor(session=None)
        ts = datetime(2024, 3, 15, 9, 0, 0)
        result = pred._empty_prediction(ts)

        assert result["signal"] == "WAIT"
        assert result["confidence"] == 0.0
        assert result["valley_prob"] == 0.0
        assert result["peak_prob"] == 0.0
        assert result["neutral_prob"] == 1.0

    def test_nonexistent_model_dir_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ReversalPredictor(
                session=None,
                model_path=tmp_path / "does_not_exist",
            )

    def test_model_dir_with_corrupt_json_raises(self, tmp_path):
        """A model.json that is not valid XGBoost format must raise on load."""
        bad_dir = tmp_path / "bad_model"
        bad_dir.mkdir()
        (bad_dir / "model.json").write_text("this is not valid json for xgboost")
        with pytest.raises(Exception):
            ReversalPredictor(session=None, model_path=bad_dir)

    def test_get_model_info_safe_when_not_loaded(self):
        pred = ReversalPredictor(session=None)
        info = pred.get_model_info()
        assert isinstance(info, dict)
        assert info["model_loaded"] is False

    def test_production_crude_oil_model_inference_if_present(self):
        """
        If CrudeOIL_H1 model exists on disk, run a real inference pass
        to confirm the booster + feature pipeline is consistent.

        Skipped when model file is absent.
        """
        model_path = (
            Path(__file__).resolve().parent.parent.parent
            / "models" / "reversal_classifier" / "CrudeOIL_H1"
        )
        if not (model_path / "model.json").exists():
            pytest.skip("CrudeOIL_H1 model not on disk")

        pred = ReversalPredictor(session=None, model_path=model_path)
        assert pred.is_loaded()

        # Build feature row using the same OHLCV → feature pipeline
        raw = _make_ohlcv(n=300, seed=55)
        featured = compute_features_from_ohlcv(raw)
        feature_cols = pred.feature_names
        available = [c for c in feature_cols if c in featured.columns]

        # Warn if feature count diverges significantly from training
        if len(available) < len(feature_cols) * 0.8:
            pytest.fail(
                f"Only {len(available)}/{len(feature_cols)} features available for "
                "CrudeOIL_H1 model — feature parity broken"
            )

        last_row = featured[available].dropna().tail(1)
        assert len(last_row) == 1, "No clean tail row found"

        X = last_row.values.astype(np.float32)
        dmatrix = xgb.DMatrix(X, feature_names=feature_cols)
        probs = pred.booster.predict(dmatrix)

        assert probs.shape == (1, 3)
        np.testing.assert_allclose(probs.sum(axis=1), [1.0], atol=1e-5)

        signal, conf = pred._generate_signal(
            float(probs[0, 0]), float(probs[0, 2]), float(probs[0, 1])
        )
        assert signal in ("LONG", "SHORT", "WAIT")
        assert 0.0 <= conf <= 1.0
