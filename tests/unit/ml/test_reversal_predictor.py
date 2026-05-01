"""
Unit tests for ReversalPredictor.

Tests cover:
  - Initialization with and without a model path
  - is_loaded() state reporting
  - _generate_signal() threshold logic
  - _empty_prediction() output contract
  - get_model_info() output structure
  - set_thresholds() mutation
  - _load_from_disk() with a real model file (when CrudeOIL_H1 exists)

The DB-backed ``predict()`` method is NOT tested here because it requires
an async database session and live market data — that is covered by the
integration test file (tests/integration/test_ml_pipeline.py).

No ``unittest.mock``, ``MagicMock``, or ``@patch()`` usage.  All inputs
are real synthetic data structures.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict

import numpy as np
import pytest
import xgboost as xgb

from src.ml.inference.reversal_predictor import ReversalPredictor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dummy_booster(n_features: int = 10, tmp_dir: Path = None) -> Path:
    """
    Train a minimal XGBoost booster on random data and save it to disk.

    Returns the directory containing model.json and feature_names.json.
    The booster uses multi:softprob with 3 classes matching the production
    model's training objective.

    Args:
        n_features:  Number of input features.
        tmp_dir:     Directory to write files into (created if None).

    Returns:
        Path to the model directory.
    """
    if tmp_dir is None:
        tmp_dir = Path(tempfile.mkdtemp())

    tmp_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(0)
    X = rng.standard_normal((90, n_features)).astype(np.float32)
    # Labels 0/1/2 (valley / neutral / peak)
    y = np.tile([0, 1, 2], 30).astype(np.float32)

    dtrain = xgb.DMatrix(X, label=y)
    params = {
        "objective": "multi:softprob",
        "num_class": 3,
        "max_depth": 2,
        "n_estimators": 5,
        "tree_method": "hist",
    }
    booster = xgb.train(params, dtrain, num_boost_round=5, verbose_eval=False)
    model_path = tmp_dir / "model.json"
    booster.save_model(str(model_path))

    feature_names = [f"feat_{i}" for i in range(n_features)]
    with open(tmp_dir / "feature_names.json", "w") as f:
        json.dump(feature_names, f)

    metadata = {
        "model_name": "test_model",
        "model_type": "xgboost",
        "reversal_f1": 0.15,
        "symbol": "TEST",
        "timeframe": "H1",
    }
    with open(tmp_dir / "metadata.json", "w") as f:
        json.dump(metadata, f)

    return tmp_dir


def _make_predictor_no_model() -> ReversalPredictor:
    """Return a ReversalPredictor with no session and no model path."""
    return ReversalPredictor(session=None)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestReversalPredictorInit:
    """Tests for __init__ behavior."""

    def test_default_thresholds(self):
        """Default peak/valley thresholds must be 0.65."""
        pred = _make_predictor_no_model()
        assert pred.threshold_peak == 0.65
        assert pred.threshold_valley == 0.65

    def test_custom_thresholds(self):
        """Custom thresholds are stored correctly."""
        pred = ReversalPredictor(session=None, threshold_peak=0.70, threshold_valley=0.60)
        assert pred.threshold_peak == 0.70
        assert pred.threshold_valley == 0.60

    def test_not_loaded_without_model_path(self):
        """is_loaded() must be False when no model_path provided."""
        pred = _make_predictor_no_model()
        assert pred.is_loaded() is False

    def test_booster_none_without_model(self):
        pred = _make_predictor_no_model()
        assert pred.booster is None

    def test_feature_names_none_without_model(self):
        pred = _make_predictor_no_model()
        assert pred.feature_names is None

    def test_nonexistent_model_path_raises_file_not_found(self, tmp_path):
        """Passing a path that has no model.json must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Model file not found"):
            ReversalPredictor(session=None, model_path=tmp_path / "nonexistent")

    def test_empty_dir_raises_file_not_found(self, tmp_path):
        """An existing but empty directory must also raise FileNotFoundError."""
        empty_dir = tmp_path / "empty_model"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            ReversalPredictor(session=None, model_path=empty_dir)


# ---------------------------------------------------------------------------
# _load_from_disk
# ---------------------------------------------------------------------------

class TestLoadFromDisk:
    """Tests for model loading from disk."""

    def test_loads_real_dummy_model(self, tmp_path):
        """A freshly-trained tiny booster should load without error."""
        model_dir = _make_dummy_booster(n_features=10, tmp_dir=tmp_path / "model")
        model_dir.mkdir(exist_ok=True)
        # Re-run to actually populate the dir (already done above)
        pred = ReversalPredictor(session=None, model_path=model_dir)
        assert pred.is_loaded() is True
        assert pred.booster is not None

    def test_feature_names_loaded_from_json(self, tmp_path):
        """feature_names.json is parsed into a list of strings."""
        model_dir = _make_dummy_booster(n_features=10, tmp_dir=tmp_path / "model")
        pred = ReversalPredictor(session=None, model_path=model_dir)
        assert isinstance(pred.feature_names, list)
        assert len(pred.feature_names) == 10
        assert pred.feature_names[0] == "feat_0"

    def test_metadata_loaded(self, tmp_path):
        """metadata.json is parsed into a dict."""
        model_dir = _make_dummy_booster(n_features=10, tmp_dir=tmp_path / "model")
        pred = ReversalPredictor(session=None, model_path=model_dir)
        assert isinstance(pred.metadata, dict)
        assert pred.metadata["model_name"] == "test_model"

    def test_feature_names_txt_fallback(self, tmp_path):
        """If only feature_names.txt exists, it should be read line-by-line."""
        model_dir = _make_dummy_booster(n_features=5, tmp_dir=tmp_path / "model")
        # Remove .json, replace with .txt
        json_path = model_dir / "feature_names.json"
        txt_path = model_dir / "feature_names.txt"
        feature_names_from_json = json.loads(json_path.read_text())
        json_path.unlink()
        txt_path.write_text("\n".join(feature_names_from_json))

        pred = ReversalPredictor(session=None, model_path=model_dir)
        assert pred.feature_names == feature_names_from_json

    def test_loads_production_crude_oil_model_if_present(self):
        """
        If the CrudeOIL_H1 model exists on disk, it must load without error.

        This test is skipped when the model file is absent (CI or fresh checkout).
        """
        model_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "models" / "reversal_classifier" / "CrudeOIL_H1"
        )
        if not (model_path / "model.json").exists():
            pytest.skip("CrudeOIL_H1 model not on disk — skipping production load test")

        pred = ReversalPredictor(session=None, model_path=model_path)
        assert pred.is_loaded() is True
        assert pred.feature_names is not None
        assert len(pred.feature_names) > 0


# ---------------------------------------------------------------------------
# is_loaded
# ---------------------------------------------------------------------------

class TestIsLoaded:
    def test_false_before_load(self):
        pred = _make_predictor_no_model()
        assert pred.is_loaded() is False

    def test_true_after_load(self, tmp_path):
        model_dir = _make_dummy_booster(n_features=10, tmp_dir=tmp_path / "m")
        pred = ReversalPredictor(session=None, model_path=model_dir)
        assert pred.is_loaded() is True


# ---------------------------------------------------------------------------
# _generate_signal — threshold logic
# ---------------------------------------------------------------------------

class TestGenerateSignal:
    """
    _generate_signal(valley_prob, peak_prob, neutral_prob) is a pure function.
    Tests exercise the threshold logic with controlled probability inputs.

    Contract:
      - peak_prob > threshold_peak  → ('SHORT', peak_prob)
      - valley_prob > threshold_valley → ('LONG', valley_prob)
      - otherwise                   → ('WAIT', max(valley_prob, peak_prob))
      - peak threshold takes priority when both exceed threshold simultaneously
    """

    def setup_method(self):
        self.pred = ReversalPredictor(
            session=None,
            threshold_peak=0.65,
            threshold_valley=0.65,
        )

    def test_short_signal_on_high_peak_prob(self):
        signal, conf = self.pred._generate_signal(
            valley_prob=0.10, peak_prob=0.80, neutral_prob=0.10
        )
        assert signal == "SHORT"
        assert conf == pytest.approx(0.80)

    def test_long_signal_on_high_valley_prob(self):
        signal, conf = self.pred._generate_signal(
            valley_prob=0.75, peak_prob=0.10, neutral_prob=0.15
        )
        assert signal == "LONG"
        assert conf == pytest.approx(0.75)

    def test_wait_when_neither_threshold_met(self):
        signal, conf = self.pred._generate_signal(
            valley_prob=0.30, peak_prob=0.30, neutral_prob=0.40
        )
        assert signal == "WAIT"
        assert conf == pytest.approx(0.30)  # max(0.30, 0.30)

    def test_wait_exactly_at_threshold(self):
        """Exactly at the threshold boundary — must return WAIT (strict >)."""
        signal, conf = self.pred._generate_signal(
            valley_prob=0.65, peak_prob=0.64, neutral_prob=0.01
        )
        # 0.65 is NOT strictly greater than 0.65
        assert signal == "WAIT"

    def test_peak_threshold_priority_when_both_high(self):
        """When both probabilities exceed their thresholds, peak takes priority."""
        signal, conf = self.pred._generate_signal(
            valley_prob=0.70, peak_prob=0.80, neutral_prob=0.00
        )
        assert signal == "SHORT"

    def test_confidence_equals_winning_probability(self):
        """Confidence must equal the probability of the winning class."""
        signal, conf = self.pred._generate_signal(
            valley_prob=0.10, peak_prob=0.90, neutral_prob=0.00
        )
        assert conf == pytest.approx(0.90)

    def test_custom_thresholds_respected(self):
        """Lower custom thresholds should fire at lower probabilities."""
        pred = ReversalPredictor(
            session=None,
            threshold_peak=0.50,
            threshold_valley=0.50,
        )
        signal, conf = pred._generate_signal(
            valley_prob=0.55, peak_prob=0.30, neutral_prob=0.15
        )
        assert signal == "LONG"

    def test_all_zero_probabilities(self):
        """Degenerate all-zero probabilities must return WAIT without crashing."""
        signal, conf = self.pred._generate_signal(
            valley_prob=0.0, peak_prob=0.0, neutral_prob=0.0
        )
        assert signal == "WAIT"
        assert conf == 0.0


# ---------------------------------------------------------------------------
# _empty_prediction
# ---------------------------------------------------------------------------

class TestEmptyPrediction:
    """_empty_prediction must always return the correct contract dict."""

    def test_returns_dict(self):
        pred = _make_predictor_no_model()
        ts = datetime(2024, 6, 15, 12, 0, 0)
        result = pred._empty_prediction(ts)
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        pred = _make_predictor_no_model()
        ts = datetime(2024, 6, 15, 12, 0, 0)
        result = pred._empty_prediction(ts)
        for key in ("valley_prob", "neutral_prob", "peak_prob", "signal", "confidence"):
            assert key in result, f"Key '{key}' missing from empty prediction"

    def test_probabilities_neutral_on_empty(self):
        pred = _make_predictor_no_model()
        ts = datetime(2024, 1, 1)
        result = pred._empty_prediction(ts)
        assert result["valley_prob"] == pytest.approx(0.0)
        assert result["peak_prob"] == pytest.approx(0.0)
        assert result["neutral_prob"] == pytest.approx(1.0)

    def test_signal_is_wait_on_empty(self):
        pred = _make_predictor_no_model()
        result = pred._empty_prediction(datetime(2024, 1, 1))
        assert result["signal"] == "WAIT"

    def test_confidence_zero_on_empty(self):
        pred = _make_predictor_no_model()
        result = pred._empty_prediction(datetime(2024, 1, 1))
        assert result["confidence"] == pytest.approx(0.0)

    def test_timestamp_serialized_as_string(self):
        pred = _make_predictor_no_model()
        ts = datetime(2024, 6, 15, 12, 30, 0)
        result = pred._empty_prediction(ts)
        assert isinstance(result["timestamp"], str)
        assert "2024-06-15" in result["timestamp"]


# ---------------------------------------------------------------------------
# set_thresholds
# ---------------------------------------------------------------------------

class TestSetThresholds:
    def test_updates_peak_threshold(self):
        pred = _make_predictor_no_model()
        pred.set_thresholds(peak=0.70, valley=0.65)
        assert pred.threshold_peak == pytest.approx(0.70)

    def test_updates_valley_threshold(self):
        pred = _make_predictor_no_model()
        pred.set_thresholds(peak=0.65, valley=0.72)
        assert pred.threshold_valley == pytest.approx(0.72)

    def test_thresholds_affect_signal_generation(self):
        pred = _make_predictor_no_model()
        # At default 0.65 threshold a 0.60 peak does NOT trigger SHORT
        s1, _ = pred._generate_signal(0.10, 0.60, 0.30)
        assert s1 == "WAIT"

        # After lowering threshold to 0.55 it DOES trigger SHORT
        pred.set_thresholds(peak=0.55, valley=0.65)
        s2, _ = pred._generate_signal(0.10, 0.60, 0.30)
        assert s2 == "SHORT"


# ---------------------------------------------------------------------------
# get_model_info
# ---------------------------------------------------------------------------

class TestGetModelInfo:
    def test_structure_when_not_loaded(self):
        pred = _make_predictor_no_model()
        info = pred.get_model_info()
        assert info["model_loaded"] is False
        assert info["feature_count"] == 0

    def test_structure_when_loaded(self, tmp_path):
        model_dir = _make_dummy_booster(n_features=10, tmp_dir=tmp_path / "m")
        pred = ReversalPredictor(session=None, model_path=model_dir)
        info = pred.get_model_info()
        assert info["model_loaded"] is True
        assert info["feature_count"] == 10
        assert "threshold_peak" in info
        assert "threshold_valley" in info
        assert "metadata" in info

    def test_thresholds_reported_in_info(self):
        pred = ReversalPredictor(
            session=None,
            threshold_peak=0.72,
            threshold_valley=0.68,
        )
        info = pred.get_model_info()
        assert info["threshold_peak"] == pytest.approx(0.72)
        assert info["threshold_valley"] == pytest.approx(0.68)


# ---------------------------------------------------------------------------
# Booster inference sanity check (no DB, synthetic DMatrix)
# ---------------------------------------------------------------------------

class TestBoosterInferenceSanity:
    """
    Exercise the loaded booster directly with a synthetic feature array.

    Validates that output shape and probability constraints hold without
    needing a real database session.
    """

    @pytest.fixture(scope="class")
    def predictor_with_model(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("booster")
        model_dir = _make_dummy_booster(n_features=10, tmp_dir=tmp / "m")
        return ReversalPredictor(session=None, model_path=model_dir)

    def test_booster_predict_returns_probabilities(self, predictor_with_model):
        """booster.predict on a DMatrix must return (n_samples, 3) float array."""
        rng = np.random.default_rng(1)
        X = rng.standard_normal((5, 10)).astype(np.float32)
        dmatrix = xgb.DMatrix(X)
        probs = predictor_with_model.booster.predict(dmatrix)
        # multi:softprob returns (n_samples, n_classes)
        assert probs.shape == (5, 3), f"Expected shape (5,3), got {probs.shape}"

    def test_probabilities_sum_to_one(self, predictor_with_model):
        """Each row's probabilities must sum to approximately 1.0."""
        rng = np.random.default_rng(2)
        X = rng.standard_normal((20, 10)).astype(np.float32)
        dmatrix = xgb.DMatrix(X)
        probs = predictor_with_model.booster.predict(dmatrix)
        row_sums = probs.sum(axis=1)
        np.testing.assert_allclose(row_sums, np.ones(20), atol=1e-5)

    def test_probabilities_non_negative(self, predictor_with_model):
        rng = np.random.default_rng(3)
        X = rng.standard_normal((10, 10)).astype(np.float32)
        dmatrix = xgb.DMatrix(X)
        probs = predictor_with_model.booster.predict(dmatrix)
        assert (probs >= 0).all(), "Some probabilities are negative"

    def test_signal_generation_from_synthetic_probs(self, predictor_with_model):
        """
        Build a synthetic probability row that should trigger LONG,
        then verify _generate_signal interprets it correctly.
        """
        valley_prob = 0.75
        peak_prob = 0.10
        neutral_prob = 0.15
        signal, conf = predictor_with_model._generate_signal(
            valley_prob, peak_prob, neutral_prob
        )
        assert signal == "LONG"
        assert conf == pytest.approx(valley_prob)
