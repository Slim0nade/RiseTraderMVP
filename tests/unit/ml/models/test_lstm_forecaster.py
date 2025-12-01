"""
Unit tests for LSTM Forecaster model.
Tests bidirectional LSTM with attention mechanism.
Based on research.md TD-001
"""

import pytest
import numpy as np
import torch
from pathlib import Path


class TestLSTMForecasterInitialization:
    """Test suite for LSTM model initialization."""

    def test_lstm_forecaster_imports(self):
        """Test LSTM forecaster can be imported."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        assert LSTMForecaster is not None

    def test_lstm_init_with_default_params(self):
        """Test LSTM initialization with default parameters."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        model = LSTMForecaster(
            input_size=10,
            hidden_size=128,
            num_layers=2
        )
        
        assert model.input_size == 10
        assert model.hidden_size == 128
        assert model.num_layers == 2
        assert model.bidirectional is True  # Default from research.md
        assert model.attention is True  # Default from research.md

    def test_lstm_init_with_custom_params(self):
        """Test LSTM initialization with custom parameters."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        model = LSTMForecaster(
            input_size=15,
            hidden_size=64,
            num_layers=3,
            dropout=0.3,
            bidirectional=False,
            attention=False
        )
        
        assert model.input_size == 15
        assert model.hidden_size == 64
        assert model.num_layers == 3
        assert model.dropout == 0.3
        assert model.bidirectional is False
        assert model.attention is False

    def test_lstm_creates_pytorch_layers(self):
        """Test that LSTM creates proper PyTorch layers."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        model = LSTMForecaster(input_size=10, hidden_size=128, num_layers=2)
        
        assert hasattr(model, 'lstm')
        assert hasattr(model, 'fc')
        assert isinstance(model.lstm, torch.nn.LSTM)


class TestLSTMForecasterTraining:
    """Test suite for LSTM training."""

    def test_train_with_valid_data(self):
        """Test training with valid input data."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        model = LSTMForecaster(input_size=5, hidden_size=64, num_layers=2)
        
        # Create sample data (batch_size=32, seq_len=60, features=5)
        X_train = np.random.randn(32, 60, 5).astype(np.float32)
        y_train = np.random.randn(32, 1).astype(np.float32)
        X_val = np.random.randn(8, 60, 5).astype(np.float32)
        y_val = np.random.randn(8, 1).astype(np.float32)
        
        metrics = model.train(
            X_train, y_train, X_val, y_val,
            epochs=2, learning_rate=0.001
        )
        
        assert isinstance(metrics, dict)
        assert 'train_loss' in metrics
        assert 'val_loss' in metrics
        assert model.is_trained is True

    def test_train_updates_model_weights(self):
        """Test that training updates model weights."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        model = LSTMForecaster(input_size=5, hidden_size=32, num_layers=1)
        
        # Get initial weights
        initial_weights = model.fc.weight.data.clone()
        
        # Train model
        X_train = np.random.randn(16, 30, 5).astype(np.float32)
        y_train = np.random.randn(16, 1).astype(np.float32)
        
        model.train(X_train, y_train, epochs=1, learning_rate=0.01)
        
        # Check weights changed
        final_weights = model.fc.weight.data
        assert not torch.equal(initial_weights, final_weights)

    def test_train_with_early_stopping(self):
        """Test early stopping prevents overfitting."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        model = LSTMForecaster(input_size=5, hidden_size=32, num_layers=1)
        
        X_train = np.random.randn(16, 30, 5).astype(np.float32)
        y_train = np.random.randn(16, 1).astype(np.float32)
        X_val = np.random.randn(4, 30, 5).astype(np.float32)
        y_val = np.random.randn(4, 1).astype(np.float32)
        
        metrics = model.train(
            X_train, y_train, X_val, y_val,
            epochs=100, early_stopping_patience=3
        )
        
        assert 'epochs_trained' in metrics
        # Should stop before 100 epochs
        assert metrics['epochs_trained'] < 100

    def test_train_requires_3d_input(self):
        """Test that training requires 3D input (batch, seq, features)."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        model = LSTMForecaster(input_size=5, hidden_size=32, num_layers=1)
        
        # 2D input should fail
        X_train = np.random.randn(16, 5).astype(np.float32)
        y_train = np.random.randn(16, 1).astype(np.float32)
        
        with pytest.raises(ValueError, match="3D.*shape"):
            model.train(X_train, y_train, epochs=1)


class TestLSTMForecasterPrediction:
    """Test suite for LSTM prediction."""

    def test_predict_returns_correct_shape(self):
        """Test predict returns correct output shape."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        model = LSTMForecaster(input_size=5, hidden_size=32, num_layers=1)
        
        # Train model first
        X_train = np.random.randn(16, 30, 5).astype(np.float32)
        y_train = np.random.randn(16, 1).astype(np.float32)
        model.train(X_train, y_train, epochs=1)
        
        # Predict
        X_test = np.random.randn(8, 30, 5).astype(np.float32)
        predictions = model.predict(X_test)
        
        assert predictions.shape == (8, 1)
        assert isinstance(predictions, np.ndarray)

    def test_predict_requires_trained_model(self):
        """Test prediction requires trained model."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        model = LSTMForecaster(input_size=5, hidden_size=32, num_layers=1)
        X_test = np.random.randn(8, 30, 5).astype(np.float32)
        
        with pytest.raises(ValueError, match="not.*trained"):
            model.predict(X_test)

    def test_predict_batch_and_single(self):
        """Test prediction works for both batch and single inputs."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        model = LSTMForecaster(input_size=5, hidden_size=32, num_layers=1)
        
        # Train
        X_train = np.random.randn(16, 30, 5).astype(np.float32)
        y_train = np.random.randn(16, 1).astype(np.float32)
        model.train(X_train, y_train, epochs=1)
        
        # Batch prediction
        X_batch = np.random.randn(10, 30, 5).astype(np.float32)
        pred_batch = model.predict(X_batch)
        assert pred_batch.shape == (10, 1)
        
        # Single prediction
        X_single = np.random.randn(1, 30, 5).astype(np.float32)
        pred_single = model.predict(X_single)
        assert pred_single.shape == (1, 1)


class TestLSTMForecasterSaveLoad:
    """Test suite for LSTM save/load functionality."""

    def test_save_creates_checkpoint_file(self, tmp_path):
        """Test save creates model checkpoint."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        model = LSTMForecaster(input_size=5, hidden_size=32, num_layers=1)
        
        # Train model
        X_train = np.random.randn(16, 30, 5).astype(np.float32)
        y_train = np.random.randn(16, 1).astype(np.float32)
        model.train(X_train, y_train, epochs=1)
        
        # Save
        model_path = tmp_path / "lstm_model.pt"
        model.save(str(model_path))
        
        assert model_path.exists()

    def test_load_restores_model_weights(self, tmp_path):
        """Test load restores exact model weights."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        # Train and save model
        model1 = LSTMForecaster(input_size=5, hidden_size=32, num_layers=1)
        X_train = np.random.randn(16, 30, 5).astype(np.float32)
        y_train = np.random.randn(16, 1).astype(np.float32)
        model1.train(X_train, y_train, epochs=1)
        
        model_path = tmp_path / "lstm_model.pt"
        model1.save(str(model_path))
        
        # Create new model and load weights
        model2 = LSTMForecaster(input_size=5, hidden_size=32, num_layers=1)
        model2.load(str(model_path))
        
        # Verify predictions match
        X_test = np.random.randn(4, 30, 5).astype(np.float32)
        pred1 = model1.predict(X_test)
        pred2 = model2.predict(X_test)
        
        np.testing.assert_array_almost_equal(pred1, pred2, decimal=5)

    def test_load_sets_trained_flag(self, tmp_path):
        """Test load sets is_trained flag."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        # Save trained model
        model1 = LSTMForecaster(input_size=5, hidden_size=32, num_layers=1)
        X_train = np.random.randn(16, 30, 5).astype(np.float32)
        y_train = np.random.randn(16, 1).astype(np.float32)
        model1.train(X_train, y_train, epochs=1)
        
        model_path = tmp_path / "lstm_model.pt"
        model1.save(str(model_path))
        
        # Load into new model
        model2 = LSTMForecaster(input_size=5, hidden_size=32, num_layers=1)
        assert model2.is_trained is False
        
        model2.load(str(model_path))
        assert model2.is_trained is True


class TestLSTMForecasterAttentionMechanism:
    """Test suite for attention mechanism."""

    def test_attention_layer_exists_when_enabled(self):
        """Test attention layer is created when enabled."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        model = LSTMForecaster(
            input_size=5, hidden_size=32, num_layers=1,
            attention=True
        )
        
        assert hasattr(model, 'attention')
        assert model.attention is not None

    def test_no_attention_layer_when_disabled(self):
        """Test no attention layer when disabled."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        model = LSTMForecaster(
            input_size=5, hidden_size=32, num_layers=1,
            attention=False
        )
        
        # Attention attribute should be None or False
        assert model.attention in [None, False]


class TestLSTMForecasterBidirectional:
    """Test suite for bidirectional LSTM."""

    def test_bidirectional_doubles_hidden_size(self):
        """Test bidirectional LSTM has 2x hidden size."""
        from src.ml.models.lstm_forecaster import LSTMForecaster
        
        model_bi = LSTMForecaster(
            input_size=5, hidden_size=32, num_layers=1,
            bidirectional=True
        )
        
        model_uni = LSTMForecaster(
            input_size=5, hidden_size=32, num_layers=1,
            bidirectional=False
        )
        
        # Bidirectional should have more parameters
        bi_params = sum(p.numel() for p in model_bi.parameters())
        uni_params = sum(p.numel() for p in model_uni.parameters())
        
        assert bi_params > uni_params
