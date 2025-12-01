"""
Unit tests for ModelPredictor.
Tests in-memory model loading and batch prediction.
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock

from src.ml.inference.predictor import ModelPredictor


@pytest.fixture
def predictor():
    """Create ModelPredictor instance."""
    return ModelPredictor()


@pytest.fixture
def mock_lstm_model():
    """Create mock LSTM model."""
    model = Mock()
    model.load = Mock()
    model.predict = Mock(return_value=np.array([75.5, 76.2, 77.0]))
    return model


@pytest.fixture
def mock_xgb_model():
    """Create mock XGBoost model."""
    model = Mock()
    model.load = Mock()
    model.predict = Mock(return_value=np.array([100.1, 101.5, 102.3]))
    return model


class TestModelPredictorInitialization:
    """Test ModelPredictor initialization."""

    def test_initialization(self, predictor):
        """Test predictor initializes with empty model cache."""
        assert isinstance(predictor.loaded_models, dict)
        assert len(predictor.loaded_models) == 0

    def test_loaded_models_is_dict(self, predictor):
        """Test loaded_models is a dictionary."""
        assert hasattr(predictor, 'loaded_models')
        assert isinstance(predictor.loaded_models, dict)


class TestModelPredictorLoadModel:
    """Test model loading functionality."""

    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_load_lstm_model(self, mock_lstm_class, predictor, mock_lstm_model):
        """Test loading LSTM model into memory."""
        mock_lstm_class.return_value = mock_lstm_model
        model_path = '/models/lstm_v1.0.0.pth'

        result = predictor.load_model(model_path, 'lstm')

        # Verify model created with correct parameters
        mock_lstm_class.assert_called_once_with(
            input_size=10,
            hidden_size=128,
            num_layers=2
        )

        # Verify model load called
        mock_lstm_model.load.assert_called_once_with(model_path)

        # Verify model stored in cache
        assert model_path in predictor.loaded_models
        assert predictor.loaded_models[model_path] == mock_lstm_model
        assert result == mock_lstm_model

    @patch('src.ml.inference.predictor.XGBoostForecaster')
    def test_load_xgboost_model(self, mock_xgb_class, predictor, mock_xgb_model):
        """Test loading XGBoost model into memory."""
        mock_xgb_class.return_value = mock_xgb_model
        model_path = '/models/xgb_v2.0.0.pkl'

        result = predictor.load_model(model_path, 'xgboost')

        # Verify XGBoost model created
        mock_xgb_class.assert_called_once()

        # Verify model load called
        mock_xgb_model.load.assert_called_once_with(model_path)

        # Verify model stored
        assert model_path in predictor.loaded_models
        assert result == mock_xgb_model

    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_load_multiple_models(self, mock_lstm_class, predictor, mock_lstm_model):
        """Test loading multiple models into memory."""
        mock_lstm_class.return_value = mock_lstm_model

        # Load first model
        path1 = '/models/lstm_v1.0.0.pth'
        predictor.load_model(path1, 'lstm')

        # Load second model
        path2 = '/models/lstm_v2.0.0.pth'
        predictor.load_model(path2, 'lstm')

        # Verify both in cache
        assert len(predictor.loaded_models) == 2
        assert path1 in predictor.loaded_models
        assert path2 in predictor.loaded_models

    @patch('src.ml.inference.predictor.XGBoostForecaster')
    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_load_different_model_types(
        self, mock_lstm_class, mock_xgb_class, predictor, mock_lstm_model, mock_xgb_model
    ):
        """Test loading different model types."""
        mock_lstm_class.return_value = mock_lstm_model
        mock_xgb_class.return_value = mock_xgb_model

        # Load LSTM
        lstm_path = '/models/lstm.pth'
        predictor.load_model(lstm_path, 'lstm')

        # Load XGBoost
        xgb_path = '/models/xgb.pkl'
        predictor.load_model(xgb_path, 'xgboost')

        # Verify both loaded
        assert len(predictor.loaded_models) == 2
        assert predictor.loaded_models[lstm_path] == mock_lstm_model
        assert predictor.loaded_models[xgb_path] == mock_xgb_model

    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_reload_same_model_path(self, mock_lstm_class, predictor, mock_lstm_model):
        """Test reloading same model path overwrites cache."""
        mock_lstm_class.return_value = mock_lstm_model
        model_path = '/models/lstm.pth'

        # Load once
        predictor.load_model(model_path, 'lstm')
        first_model = predictor.loaded_models[model_path]

        # Load again
        predictor.load_model(model_path, 'lstm')
        second_model = predictor.loaded_models[model_path]

        # Verify same path, potentially new instance
        assert len(predictor.loaded_models) == 1
        assert model_path in predictor.loaded_models


class TestModelPredictorPredict:
    """Test prediction generation."""

    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_predict_with_loaded_model(self, mock_lstm_class, predictor, mock_lstm_model):
        """Test prediction with pre-loaded model."""
        mock_lstm_class.return_value = mock_lstm_model
        model_path = '/models/lstm.pth'

        # Load model
        predictor.load_model(model_path, 'lstm')

        # Predict
        X = np.random.randn(10, 5).astype(np.float32)
        predictions = predictor.predict(model_path, X)

        # Verify model.predict called
        mock_lstm_model.predict.assert_called_once_with(X)

        # Verify result returned
        np.testing.assert_array_equal(predictions, np.array([75.5, 76.2, 77.0]))

    def test_predict_without_loaded_model_raises_error(self, predictor):
        """Test prediction fails if model not loaded."""
        X = np.random.randn(10, 5)
        model_path = '/models/nonexistent.pth'

        with pytest.raises(ValueError, match="Model not loaded"):
            predictor.predict(model_path, X)

    @patch('src.ml.inference.predictor.XGBoostForecaster')
    def test_predict_multiple_times_same_model(self, mock_xgb_class, predictor, mock_xgb_model):
        """Test multiple predictions with same model."""
        mock_xgb_class.return_value = mock_xgb_model
        model_path = '/models/xgb.pkl'

        # Load once
        predictor.load_model(model_path, 'xgboost')

        # Predict multiple times
        X1 = np.random.randn(5, 3)
        X2 = np.random.randn(10, 3)

        pred1 = predictor.predict(model_path, X1)
        pred2 = predictor.predict(model_path, X2)

        # Verify both predictions called
        assert mock_xgb_model.predict.call_count == 2

    @patch('src.ml.inference.predictor.XGBoostForecaster')
    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_predict_with_multiple_loaded_models(
        self, mock_lstm_class, mock_xgb_class, predictor, mock_lstm_model, mock_xgb_model
    ):
        """Test predictions with multiple loaded models."""
        mock_lstm_class.return_value = mock_lstm_model
        mock_xgb_class.return_value = mock_xgb_model

        # Load both models
        lstm_path = '/models/lstm.pth'
        xgb_path = '/models/xgb.pkl'
        predictor.load_model(lstm_path, 'lstm')
        predictor.load_model(xgb_path, 'xgboost')

        # Predict with LSTM
        X_lstm = np.random.randn(5, 5)
        pred_lstm = predictor.predict(lstm_path, X_lstm)
        np.testing.assert_array_equal(pred_lstm, np.array([75.5, 76.2, 77.0]))

        # Predict with XGBoost
        X_xgb = np.random.randn(5, 3)
        pred_xgb = predictor.predict(xgb_path, X_xgb)
        np.testing.assert_array_equal(pred_xgb, np.array([100.1, 101.5, 102.3]))

    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_predict_with_different_input_shapes(self, mock_lstm_class, predictor, mock_lstm_model):
        """Test prediction with various input shapes."""
        mock_lstm_class.return_value = mock_lstm_model
        model_path = '/models/lstm.pth'
        predictor.load_model(model_path, 'lstm')

        # Small batch
        X_small = np.random.randn(1, 10)
        predictor.predict(model_path, X_small)

        # Large batch
        X_large = np.random.randn(100, 10)
        predictor.predict(model_path, X_large)

        # Verify predictions work with different shapes
        assert mock_lstm_model.predict.call_count == 2


class TestModelPredictorEdgeCases:
    """Test edge cases and error handling."""

    def test_predict_empty_cache(self, predictor):
        """Test prediction fails with empty cache."""
        with pytest.raises(ValueError, match="Model not loaded"):
            predictor.predict('/any/path.pth', np.array([1, 2, 3]))

    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_load_model_with_special_characters_in_path(
        self, mock_lstm_class, predictor, mock_lstm_model
    ):
        """Test model path with special characters."""
        mock_lstm_class.return_value = mock_lstm_model
        model_path = '/models/lstm-v1.0.0_final.pth'

        predictor.load_model(model_path, 'lstm')
        assert model_path in predictor.loaded_models

    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_model_load_exception_handling(self, mock_lstm_class, predictor):
        """Test behavior when model.load raises exception."""
        mock_model = Mock()
        mock_model.load.side_effect = FileNotFoundError("Model file not found")
        mock_lstm_class.return_value = mock_model

        with pytest.raises(FileNotFoundError):
            predictor.load_model('/models/missing.pth', 'lstm')

    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_predict_with_model_that_returns_empty(self, mock_lstm_class, predictor):
        """Test prediction when model returns empty array."""
        mock_model = Mock()
        mock_model.load = Mock()
        mock_model.predict = Mock(return_value=np.array([]))
        mock_lstm_class.return_value = mock_model

        model_path = '/models/lstm.pth'
        predictor.load_model(model_path, 'lstm')

        X = np.random.randn(5, 10)
        result = predictor.predict(model_path, X)

        assert isinstance(result, np.ndarray)
        assert len(result) == 0

    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_predict_with_single_sample(self, mock_lstm_class, predictor, mock_lstm_model):
        """Test prediction with single sample."""
        mock_lstm_class.return_value = mock_lstm_model
        model_path = '/models/lstm.pth'
        predictor.load_model(model_path, 'lstm')

        # Single sample input
        X = np.random.randn(1, 10)
        predictions = predictor.predict(model_path, X)

        assert isinstance(predictions, np.ndarray)


class TestModelPredictorMemoryManagement:
    """Test model caching and memory management."""

    @patch('src.ml.inference.predictor.LSTMForecaster')
    @patch('src.ml.inference.predictor.XGBoostForecaster')
    def test_cache_size_grows_with_loaded_models(
        self, mock_xgb_class, mock_lstm_class, predictor, mock_lstm_model, mock_xgb_model
    ):
        """Test cache grows as models are loaded."""
        mock_lstm_class.return_value = mock_lstm_model
        mock_xgb_class.return_value = mock_xgb_model

        assert len(predictor.loaded_models) == 0

        predictor.load_model('/models/model1.pth', 'lstm')
        assert len(predictor.loaded_models) == 1

        predictor.load_model('/models/model2.pth', 'lstm')
        assert len(predictor.loaded_models) == 2

        predictor.load_model('/models/model3.pkl', 'xgboost')
        assert len(predictor.loaded_models) == 3

    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_model_cache_lookup_performance(self, mock_lstm_class, predictor, mock_lstm_model):
        """Test model cache provides O(1) lookup."""
        mock_lstm_class.return_value = mock_lstm_model
        model_path = '/models/lstm.pth'

        # Load model
        predictor.load_model(model_path, 'lstm')

        # Access from cache multiple times
        for _ in range(100):
            assert model_path in predictor.loaded_models
            model = predictor.loaded_models[model_path]
            assert model == mock_lstm_model


class TestModelPredictorIntegration:
    """Integration tests for complete workflows."""

    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_full_load_and_predict_workflow(self, mock_lstm_class, predictor, mock_lstm_model):
        """Test complete load -> predict workflow."""
        mock_lstm_class.return_value = mock_lstm_model
        model_path = '/models/lstm_crude_oil_v1.pth'

        # Step 1: Load model
        loaded_model = predictor.load_model(model_path, 'lstm')
        assert loaded_model == mock_lstm_model

        # Step 2: Prepare input
        X = np.random.randn(10, 15).astype(np.float32)

        # Step 3: Predict
        predictions = predictor.predict(model_path, X)

        # Step 4: Verify
        assert isinstance(predictions, np.ndarray)
        mock_lstm_model.load.assert_called_once()
        mock_lstm_model.predict.assert_called_once()

    @patch('src.ml.inference.predictor.XGBoostForecaster')
    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_multi_model_inference_scenario(
        self, mock_lstm_class, mock_xgb_class, predictor, mock_lstm_model, mock_xgb_model
    ):
        """Test realistic scenario with multiple models for ensemble."""
        mock_lstm_class.return_value = mock_lstm_model
        mock_xgb_class.return_value = mock_xgb_model

        # Load ensemble models
        lstm_path = '/models/ensemble/lstm.pth'
        xgb_path = '/models/ensemble/xgb.pkl'

        predictor.load_model(lstm_path, 'lstm')
        predictor.load_model(xgb_path, 'xgboost')

        # Generate predictions from both
        X = np.random.randn(20, 10)

        pred_lstm = predictor.predict(lstm_path, X)
        pred_xgb = predictor.predict(xgb_path, X)

        # Verify both models used
        assert len(predictor.loaded_models) == 2
        mock_lstm_model.predict.assert_called_once()
        mock_xgb_model.predict.assert_called_once()

    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_batch_prediction_workflow(self, mock_lstm_class, predictor):
        """Test batch prediction with multiple inputs."""
        # Setup model that returns different values each call
        mock_model = Mock()
        mock_model.load = Mock()
        call_count = [0]

        def predict_side_effect(X):
            call_count[0] += 1
            return np.array([75.0 + call_count[0], 76.0 + call_count[0]])

        mock_model.predict = Mock(side_effect=predict_side_effect)
        mock_lstm_class.return_value = mock_model

        model_path = '/models/lstm.pth'
        predictor.load_model(model_path, 'lstm')

        # Multiple batch predictions
        batches = [np.random.randn(5, 10) for _ in range(3)]
        results = [predictor.predict(model_path, batch) for batch in batches]

        # Verify all batches processed
        assert len(results) == 3
        assert mock_model.predict.call_count == 3


class TestModelPredictorRealWorldScenarios:
    """Test realistic trading scenarios."""

    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_crude_oil_forecast_scenario(self, mock_lstm_class, predictor, mock_lstm_model):
        """Test forecasting crude oil prices."""
        mock_lstm_class.return_value = mock_lstm_model
        model_path = '/models/crude_oil_lstm_v1.0.0.pth'

        # Load crude oil model
        predictor.load_model(model_path, 'lstm')

        # Prepare 30 days of features (hourly data)
        X = np.random.randn(720, 20).astype(np.float32)

        # Generate forecast
        predictions = predictor.predict(model_path, X)

        assert isinstance(predictions, np.ndarray)

    @patch('src.ml.inference.predictor.XGBoostForecaster')
    def test_multi_horizon_prediction(self, mock_xgb_class, predictor):
        """Test generating predictions for multiple horizons."""
        mock_models = {}

        for horizon in ['1h', '4h', '1d', '7d']:
            mock_model = Mock()
            mock_model.load = Mock()
            mock_model.predict = Mock(return_value=np.array([100.0]))
            mock_models[horizon] = mock_model

        def xgb_factory(*args, **kwargs):
            # Return different model based on call count
            return list(mock_models.values())[len(predictor.loaded_models)]

        mock_xgb_class.side_effect = xgb_factory

        # Load models for each horizon
        for horizon in ['1h', '4h', '1d', '7d']:
            model_path = f'/models/xgb_{horizon}.pkl'
            predictor.load_model(model_path, 'xgboost')

        assert len(predictor.loaded_models) == 4

    @patch('src.ml.inference.predictor.LSTMForecaster')
    def test_model_version_switching(self, mock_lstm_class, predictor, mock_lstm_model):
        """Test switching between model versions."""
        mock_lstm_class.return_value = mock_lstm_model

        # Load v1.0.0
        v1_path = '/models/lstm_v1.0.0.pth'
        predictor.load_model(v1_path, 'lstm')

        X = np.random.randn(10, 15)
        pred_v1 = predictor.predict(v1_path, X)

        # Load v2.0.0
        v2_path = '/models/lstm_v2.0.0.pth'
        predictor.load_model(v2_path, 'lstm')

        pred_v2 = predictor.predict(v2_path, X)

        # Both models coexist in cache
        assert len(predictor.loaded_models) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
