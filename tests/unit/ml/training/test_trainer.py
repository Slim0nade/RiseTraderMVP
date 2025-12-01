"""
Unit tests for ModelTrainer.
Tests training orchestration, metric calculation, and evaluation.
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from src.ml.training.trainer import ModelTrainer


@pytest.fixture
def mock_model():
    """Create a mock model for testing."""
    model = Mock()
    model.train = Mock(return_value={'train_loss': 0.5, 'val_loss': 0.6})
    model.predict = Mock(return_value=np.array([1.0, 2.0, 3.0]))
    return model


@pytest.fixture
def training_config():
    """Standard training configuration."""
    return {
        'training': {
            'epochs': 50,
            'batch_size': 32,
            'learning_rate': 0.001,
            'early_stopping_patience': 10
        }
    }


@pytest.fixture
def minimal_config():
    """Minimal training configuration."""
    return {}


@pytest.fixture
def sample_data():
    """Create sample training/validation data."""
    X_train = np.random.randn(100, 10).astype(np.float32)
    y_train = np.random.randn(100).astype(np.float32)
    X_val = np.random.randn(20, 10).astype(np.float32)
    y_val = np.random.randn(20).astype(np.float32)
    X_test = np.random.randn(30, 10).astype(np.float32)
    y_test = np.random.randn(30).astype(np.float32)

    return X_train, y_train, X_val, y_val, X_test, y_test


class TestModelTrainerInitialization:
    """Test ModelTrainer initialization."""

    def test_initialization_with_config(self, mock_model, training_config):
        """Test trainer initializes correctly with config."""
        trainer = ModelTrainer(mock_model, training_config)

        assert trainer.model == mock_model
        assert trainer.config == training_config
        assert trainer.training_history == []

    def test_initialization_with_minimal_config(self, mock_model, minimal_config):
        """Test trainer initializes with minimal config."""
        trainer = ModelTrainer(mock_model, minimal_config)

        assert trainer.model == mock_model
        assert trainer.config == minimal_config
        assert trainer.training_history == []

    def test_training_history_starts_empty(self, mock_model, training_config):
        """Test training history initializes as empty list."""
        trainer = ModelTrainer(mock_model, training_config)

        assert isinstance(trainer.training_history, list)
        assert len(trainer.training_history) == 0


class TestModelTrainerTraining:
    """Test training functionality."""

    def test_train_calls_model_train(self, mock_model, training_config, sample_data):
        """Test train method calls underlying model's train method."""
        X_train, y_train, X_val, y_val, _, _ = sample_data
        trainer = ModelTrainer(mock_model, training_config)

        trainer.train(X_train, y_train, X_val, y_val)

        mock_model.train.assert_called_once()

    def test_train_passes_training_config(self, mock_model, training_config, sample_data):
        """Test training configuration is passed to model."""
        X_train, y_train, X_val, y_val, _, _ = sample_data
        trainer = ModelTrainer(mock_model, training_config)

        trainer.train(X_train, y_train, X_val, y_val)

        call_args = mock_model.train.call_args
        assert call_args.kwargs.get('epochs') == 50
        assert call_args.kwargs.get('batch_size') == 32
        assert call_args.kwargs.get('learning_rate') == 0.001

    def test_train_without_validation_data(self, mock_model, training_config, sample_data):
        """Test training without validation data."""
        X_train, y_train, _, _, _, _ = sample_data
        trainer = ModelTrainer(mock_model, training_config)

        result = trainer.train(X_train, y_train)

        assert isinstance(result, dict)
        mock_model.train.assert_called_once()
        call_args = mock_model.train.call_args
        assert call_args.kwargs.get('X_val') is None
        assert call_args.kwargs.get('y_val') is None

    def test_train_with_validation_data(self, mock_model, training_config, sample_data):
        """Test training with validation data."""
        X_train, y_train, X_val, y_val, _, _ = sample_data
        trainer = ModelTrainer(mock_model, training_config)

        result = trainer.train(X_train, y_train, X_val, y_val)

        assert isinstance(result, dict)
        mock_model.train.assert_called_once()
        call_args = mock_model.train.call_args
        assert np.array_equal(call_args.kwargs.get('X_val'), X_val)
        assert np.array_equal(call_args.kwargs.get('y_val'), y_val)

    def test_train_returns_metrics(self, mock_model, training_config, sample_data):
        """Test train returns metrics dictionary."""
        X_train, y_train, X_val, y_val, _, _ = sample_data
        mock_model.train.return_value = {'train_loss': 0.3, 'val_loss': 0.4}
        trainer = ModelTrainer(mock_model, training_config)

        result = trainer.train(X_train, y_train, X_val, y_val)

        assert isinstance(result, dict)
        assert 'train_loss' in result
        assert 'val_loss' in result
        assert result['train_loss'] == 0.3
        assert result['val_loss'] == 0.4

    @patch('src.ml.training.trainer.datetime')
    def test_train_records_history(self, mock_datetime, mock_model, training_config, sample_data):
        """Test training history is recorded."""
        X_train, y_train, X_val, y_val, _, _ = sample_data
        fixed_time = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = fixed_time

        trainer = ModelTrainer(mock_model, training_config)
        metrics = trainer.train(X_train, y_train, X_val, y_val)

        assert len(trainer.training_history) == 1
        history_entry = trainer.training_history[0]
        assert 'timestamp' in history_entry
        assert 'metrics' in history_entry
        assert history_entry['timestamp'] == fixed_time
        assert history_entry['metrics'] == metrics

    def test_multiple_training_runs_append_history(self, mock_model, training_config, sample_data):
        """Test multiple training runs append to history."""
        X_train, y_train, X_val, y_val, _, _ = sample_data
        trainer = ModelTrainer(mock_model, training_config)

        trainer.train(X_train, y_train, X_val, y_val)
        trainer.train(X_train, y_train, X_val, y_val)
        trainer.train(X_train, y_train, X_val, y_val)

        assert len(trainer.training_history) == 3

    def test_train_with_empty_training_config(self, mock_model, sample_data):
        """Test training with no training configuration."""
        X_train, y_train, X_val, y_val, _, _ = sample_data
        config = {'model': {'hidden_size': 128}}  # No 'training' key
        trainer = ModelTrainer(mock_model, config)

        result = trainer.train(X_train, y_train, X_val, y_val)

        assert isinstance(result, dict)
        # Should still call model.train with basic args
        mock_model.train.assert_called_once()


class TestModelTrainerEvaluation:
    """Test evaluation functionality."""

    @patch('src.ml.training.trainer.calculate_metrics')
    def test_evaluate_calls_model_predict(self, mock_calc_metrics, mock_model, training_config, sample_data):
        """Test evaluate calls model.predict."""
        _, _, _, _, X_test, y_test = sample_data
        mock_calc_metrics.return_value = {'mpe': 2.5, 'rmse': 0.8}

        trainer = ModelTrainer(mock_model, training_config)
        trainer.evaluate(X_test, y_test)

        mock_model.predict.assert_called_once_with(X_test)

    @patch('src.ml.training.trainer.calculate_metrics')
    def test_evaluate_calculates_metrics(self, mock_calc_metrics, mock_model, training_config, sample_data):
        """Test evaluate calculates metrics using predictions."""
        _, _, _, _, X_test, y_test = sample_data
        predictions = np.array([1.0, 2.0, 3.0])
        mock_model.predict.return_value = predictions
        mock_calc_metrics.return_value = {'mpe': 2.5, 'rmse': 0.8}

        trainer = ModelTrainer(mock_model, training_config)
        result = trainer.evaluate(X_test, y_test)

        # Verify calculate_metrics was called with correct args
        mock_calc_metrics.assert_called_once_with(y_test, predictions)

    @patch('src.ml.training.trainer.calculate_metrics')
    def test_evaluate_returns_metrics_dict(self, mock_calc_metrics, mock_model, training_config, sample_data):
        """Test evaluate returns metrics dictionary."""
        _, _, _, _, X_test, y_test = sample_data
        expected_metrics = {
            'mpe': 2.5,
            'rmse': 0.8,
            'mae': 0.6,
            'mape': 3.2,
            'directional_accuracy': 65.5
        }
        mock_calc_metrics.return_value = expected_metrics

        trainer = ModelTrainer(mock_model, training_config)
        result = trainer.evaluate(X_test, y_test)

        assert isinstance(result, dict)
        assert result == expected_metrics

    @patch('src.ml.training.trainer.calculate_metrics')
    def test_evaluate_with_different_test_sizes(self, mock_calc_metrics, mock_model, training_config):
        """Test evaluation works with different test set sizes."""
        mock_calc_metrics.return_value = {'mpe': 2.0, 'rmse': 0.5}
        trainer = ModelTrainer(mock_model, training_config)

        # Small test set
        X_test_small = np.random.randn(10, 5)
        y_test_small = np.random.randn(10)
        result_small = trainer.evaluate(X_test_small, y_test_small)
        assert isinstance(result_small, dict)

        # Large test set
        X_test_large = np.random.randn(1000, 5)
        y_test_large = np.random.randn(1000)
        result_large = trainer.evaluate(X_test_large, y_test_large)
        assert isinstance(result_large, dict)


class TestModelTrainerIntegration:
    """Integration tests for complete training workflows."""

    @patch('src.ml.training.trainer.calculate_metrics')
    def test_full_training_and_evaluation_workflow(self, mock_calc_metrics, mock_model, training_config, sample_data):
        """Test complete train -> evaluate workflow."""
        X_train, y_train, X_val, y_val, X_test, y_test = sample_data
        mock_model.train.return_value = {'train_loss': 0.5, 'val_loss': 0.6}
        mock_calc_metrics.return_value = {'mpe': 2.5, 'rmse': 0.8}

        trainer = ModelTrainer(mock_model, training_config)

        # Train
        train_metrics = trainer.train(X_train, y_train, X_val, y_val)
        assert 'train_loss' in train_metrics
        assert len(trainer.training_history) == 1

        # Evaluate
        eval_metrics = trainer.evaluate(X_test, y_test)
        assert 'mpe' in eval_metrics
        assert 'rmse' in eval_metrics

    def test_configuration_variants(self, mock_model, sample_data):
        """Test trainer works with different configuration structures."""
        X_train, y_train, X_val, y_val, _, _ = sample_data

        configs = [
            {},  # Empty config
            {'training': {}},  # Empty training section
            {'training': {'epochs': 10}},  # Partial training config
            {'model': {'layers': 3}},  # No training section
        ]

        for config in configs:
            trainer = ModelTrainer(mock_model, config)
            result = trainer.train(X_train, y_train, X_val, y_val)
            assert isinstance(result, dict)

    def test_training_history_persists_across_evaluations(self, mock_model, training_config, sample_data):
        """Test training history is not affected by evaluations."""
        X_train, y_train, X_val, y_val, X_test, y_test = sample_data

        trainer = ModelTrainer(mock_model, training_config)
        trainer.train(X_train, y_train, X_val, y_val)

        initial_history_length = len(trainer.training_history)

        # Run multiple evaluations
        with patch('src.ml.training.trainer.calculate_metrics', return_value={'mpe': 2.0}):
            trainer.evaluate(X_test, y_test)
            trainer.evaluate(X_test, y_test)

        # History should not change
        assert len(trainer.training_history) == initial_history_length


class TestModelTrainerEdgeCases:
    """Test edge cases and error handling."""

    def test_train_with_model_that_raises_exception(self, training_config, sample_data):
        """Test behavior when model.train raises exception."""
        X_train, y_train, _, _, _, _ = sample_data

        error_model = Mock()
        error_model.train.side_effect = ValueError("Training failed")

        trainer = ModelTrainer(error_model, training_config)

        with pytest.raises(ValueError, match="Training failed"):
            trainer.train(X_train, y_train)

    def test_evaluate_with_model_that_raises_exception(self, training_config, sample_data):
        """Test behavior when model.predict raises exception."""
        _, _, _, _, X_test, y_test = sample_data

        error_model = Mock()
        error_model.predict.side_effect = RuntimeError("Prediction failed")

        trainer = ModelTrainer(error_model, training_config)

        with pytest.raises(RuntimeError, match="Prediction failed"):
            trainer.evaluate(X_test, y_test)

    def test_train_with_mismatched_data_shapes(self, mock_model, training_config):
        """Test training with mismatched X and y shapes."""
        X_train = np.random.randn(100, 10)
        y_train = np.random.randn(50)  # Mismatched length

        # The trainer itself doesn't validate - this is model's responsibility
        # But we can test that it passes data through
        trainer = ModelTrainer(mock_model, training_config)
        trainer.train(X_train, y_train)

        # Verify data was passed to model (even if shapes mismatch)
        call_args = mock_model.train.call_args
        assert np.array_equal(call_args.args[0], X_train)
        assert np.array_equal(call_args.args[1], y_train)

    @patch('src.ml.training.trainer.calculate_metrics')
    def test_evaluate_with_single_prediction(self, mock_calc_metrics, mock_model, training_config):
        """Test evaluation with single test sample."""
        X_test = np.random.randn(1, 10)
        y_test = np.array([5.0])
        mock_model.predict.return_value = np.array([4.8])
        mock_calc_metrics.return_value = {'mpe': 4.0, 'rmse': 0.2}

        trainer = ModelTrainer(mock_model, training_config)
        result = trainer.evaluate(X_test, y_test)

        assert isinstance(result, dict)
        mock_calc_metrics.assert_called_once()

    def test_trainer_state_after_failed_training(self, training_config, sample_data):
        """Test trainer state remains consistent after failed training."""
        X_train, y_train, _, _, _, _ = sample_data

        failing_model = Mock()
        failing_model.train.side_effect = Exception("Training error")

        trainer = ModelTrainer(failing_model, training_config)

        with pytest.raises(Exception):
            trainer.train(X_train, y_train)

        # History should still be empty since training failed before recording
        assert len(trainer.training_history) == 0


class TestModelTrainerConfigHandling:
    """Test configuration handling edge cases."""

    def test_nested_training_config_extraction(self, mock_model, sample_data):
        """Test extraction of deeply nested training config."""
        X_train, y_train, _, _, _, _ = sample_data

        config = {
            'training': {
                'optimizer': {
                    'type': 'adam',
                    'lr': 0.001
                },
                'scheduler': {
                    'type': 'step',
                    'step_size': 10
                }
            }
        }

        trainer = ModelTrainer(mock_model, config)
        trainer.train(X_train, y_train)

        # Verify nested config is passed through
        call_kwargs = mock_model.train.call_args.kwargs
        assert 'optimizer' in call_kwargs
        assert call_kwargs['optimizer']['type'] == 'adam'

    def test_config_with_none_values(self, mock_model, sample_data):
        """Test config with None values doesn't break training."""
        X_train, y_train, _, _, _, _ = sample_data

        config = {
            'training': {
                'epochs': None,
                'batch_size': 32,
                'learning_rate': None
            }
        }

        trainer = ModelTrainer(mock_model, config)
        result = trainer.train(X_train, y_train)

        assert isinstance(result, dict)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
