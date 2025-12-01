"""
Unit tests for MLflowTracker.
Tests experiment tracking, artifact logging, and parameter management.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import os

from src.ml.tracking.mlflow_tracker import MLflowTracker


class TestMLflowTracker:
    """Test MLflowTracker functionality."""

    @pytest.fixture
    def mock_mlflow(self):
        """Mock MLflow module."""
        with patch('src.ml.tracking.mlflow_tracker.mlflow') as mock:
            yield mock

    @pytest.fixture
    def tracker(self, mock_mlflow):
        """Create MLflowTracker instance with mocked MLflow."""
        return MLflowTracker(
            experiment_name="test_experiment",
            tracking_uri="http://localhost:5000"
        )

    def test_initialization(self, tracker, mock_mlflow):
        """Test MLflowTracker initialization."""
        assert tracker.experiment_name == "test_experiment"
        assert tracker.tracking_uri == "http://localhost:5000"
        mock_mlflow.set_tracking_uri.assert_called_once_with("http://localhost:5000")

    def test_start_run(self, tracker, mock_mlflow):
        """Test starting an MLflow run."""
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_123"
        mock_mlflow.start_run.return_value.__enter__.return_value = mock_run

        run_id = tracker.start_run(run_name="test_run")

        mock_mlflow.start_run.assert_called_once()
        assert run_id == "test_run_123"

    def test_log_params(self, tracker, mock_mlflow):
        """Test logging parameters."""
        params = {
            "learning_rate": 0.001,
            "batch_size": 32,
            "epochs": 100
        }

        tracker.log_params(params)

        mock_mlflow.log_params.assert_called_once_with(params)

    def test_log_param(self, tracker, mock_mlflow):
        """Test logging single parameter."""
        tracker.log_param("learning_rate", 0.001)

        mock_mlflow.log_param.assert_called_once_with("learning_rate", 0.001)

    def test_log_metrics(self, tracker, mock_mlflow):
        """Test logging metrics."""
        metrics = {
            "mpe": 2.5,
            "rmse": 0.45,
            "mae": 0.38
        }

        tracker.log_metrics(metrics, step=10)

        assert mock_mlflow.log_metric.call_count == 3

    def test_log_metric(self, tracker, mock_mlflow):
        """Test logging single metric."""
        tracker.log_metric("mpe", 2.5, step=10)

        mock_mlflow.log_metric.assert_called_once_with("mpe", 2.5, step=10)

    def test_log_artifact(self, tracker, mock_mlflow):
        """Test logging artifact file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("test artifact")
            artifact_path = f.name

        try:
            tracker.log_artifact(artifact_path)
            mock_mlflow.log_artifact.assert_called_once_with(artifact_path)
        finally:
            os.unlink(artifact_path)

    def test_log_model(self, tracker, mock_mlflow):
        """Test logging model artifact."""
        mock_model = Mock()
        model_path = "models/test_model"

        tracker.log_model(mock_model, artifact_path=model_path)

        mock_mlflow.pytorch.log_model.assert_called_once()

    def test_log_dict(self, tracker, mock_mlflow):
        """Test logging dictionary as JSON."""
        data = {"key1": "value1", "key2": [1, 2, 3]}

        tracker.log_dict(data, "test_dict.json")

        mock_mlflow.log_dict.assert_called_once_with(data, "test_dict.json")

    def test_set_tags(self, tracker, mock_mlflow):
        """Test setting tags."""
        tags = {
            "model_type": "lstm",
            "symbol": "CrudeOIL",
            "env": "production"
        }

        tracker.set_tags(tags)

        mock_mlflow.set_tags.assert_called_once_with(tags)

    def test_set_tag(self, tracker, mock_mlflow):
        """Test setting single tag."""
        tracker.set_tag("model_type", "lstm")

        mock_mlflow.set_tag.assert_called_once_with("model_type", "lstm")

    def test_end_run(self, tracker, mock_mlflow):
        """Test ending MLflow run."""
        tracker.end_run()

        mock_mlflow.end_run.assert_called_once()

    def test_get_experiment_by_name(self, tracker, mock_mlflow):
        """Test getting experiment by name."""
        mock_experiment = Mock()
        mock_experiment.experiment_id = "123"
        mock_mlflow.get_experiment_by_name.return_value = mock_experiment

        exp_id = tracker.get_experiment_id()

        assert exp_id == "123"
        mock_mlflow.get_experiment_by_name.assert_called_once_with("test_experiment")

    def test_create_experiment_if_not_exists(self, tracker, mock_mlflow):
        """Test creating experiment if it doesn't exist."""
        mock_mlflow.get_experiment_by_name.return_value = None
        mock_mlflow.create_experiment.return_value = "new_exp_123"

        exp_id = tracker.get_experiment_id()

        mock_mlflow.create_experiment.assert_called_once_with("test_experiment")
        assert exp_id == "new_exp_123"

    def test_search_runs(self, tracker, mock_mlflow):
        """Test searching runs."""
        mock_runs = [Mock(), Mock()]
        mock_mlflow.search_runs.return_value = mock_runs

        runs = tracker.search_runs(filter_string="metrics.rmse < 0.5")

        assert len(runs) == 2
        mock_mlflow.search_runs.assert_called_once()

    def test_get_run(self, tracker, mock_mlflow):
        """Test getting specific run."""
        mock_run = Mock()
        mock_run.info.run_id = "run_123"
        mock_mlflow.get_run.return_value = mock_run

        run = tracker.get_run("run_123")

        assert run.info.run_id == "run_123"
        mock_mlflow.get_run.assert_called_once_with("run_123")

    def test_log_training_metadata(self, tracker, mock_mlflow):
        """Test logging complete training metadata."""
        metadata = {
            "run_name": "lstm_training_v1",
            "params": {"learning_rate": 0.001, "epochs": 100},
            "metrics": {"mpe": 2.5, "rmse": 0.45},
            "tags": {"model_type": "lstm", "symbol": "CrudeOIL"}
        }

        tracker.log_training_metadata(metadata)

        # Verify all components were logged
        mock_mlflow.log_params.assert_called_once()
        assert mock_mlflow.log_metric.call_count >= 2
        mock_mlflow.set_tags.assert_called_once()

    def test_context_manager(self, tracker, mock_mlflow):
        """Test using MLflowTracker as context manager."""
        mock_run = MagicMock()
        mock_run.info.run_id = "context_run_123"
        mock_mlflow.start_run.return_value.__enter__.return_value = mock_run

        with tracker.run("test_run") as run_id:
            assert run_id == "context_run_123"

        mock_mlflow.end_run.assert_called_once()

    def test_log_figure(self, tracker, mock_mlflow):
        """Test logging matplotlib figure."""
        with patch('matplotlib.pyplot.figure') as mock_fig:
            fig = mock_fig.return_value

            tracker.log_figure(fig, "test_plot.png")

            mock_mlflow.log_figure.assert_called_once()

    def test_error_handling_on_log_param(self, tracker, mock_mlflow):
        """Test error handling when logging parameter fails."""
        mock_mlflow.log_param.side_effect = Exception("MLflow connection error")

        # Should not raise exception, just log error
        try:
            tracker.log_param("test_param", "value")
        except Exception:
            pytest.fail("Should handle MLflow errors gracefully")

    def test_auto_log_enable(self, tracker, mock_mlflow):
        """Test enabling auto-logging."""
        tracker.enable_autolog(pytorch=True)

        mock_mlflow.pytorch.autolog.assert_called_once()

    def test_log_model_with_signature(self, tracker, mock_mlflow):
        """Test logging model with input/output signature."""
        mock_model = Mock()
        mock_signature = Mock()

        tracker.log_model(
            model=mock_model,
            artifact_path="model",
            signature=mock_signature
        )

        mock_mlflow.pytorch.log_model.assert_called_once()
        call_args = mock_mlflow.pytorch.log_model.call_args
        assert 'signature' in call_args[1] or len(call_args[0]) >= 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
