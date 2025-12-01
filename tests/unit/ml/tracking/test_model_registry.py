"""
Unit tests for ModelRegistry.
Tests model stage transitions and version management.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.ml.tracking.model_registry import ModelRegistry


class TestModelRegistry:
    """Test ModelRegistry functionality."""

    @pytest.fixture
    def mock_mlflow_client(self):
        """Mock MLflow MlflowClient."""
        with patch('src.ml.tracking.model_registry.MlflowClient') as mock:
            yield mock.return_value

    @pytest.fixture
    def registry(self, mock_mlflow_client):
        """Create ModelRegistry instance."""
        return ModelRegistry(tracking_uri="http://localhost:5000")

    def test_initialization(self, registry):
        """Test ModelRegistry initialization."""
        assert registry.tracking_uri == "http://localhost:5000"
        assert hasattr(registry, 'register_model')
        assert hasattr(registry, 'promote_model')

    def test_register_model(self, registry, mock_mlflow_client):
        """Test registering a new model."""
        mock_version = Mock()
        mock_version.version = "1"
        mock_mlflow_client.create_registered_model.return_value = Mock()
        mock_mlflow_client.create_model_version.return_value = mock_version

        version = registry.register_model(
            name="lstm_forecaster",
            run_id="run_123",
            description="LSTM model for CrudeOIL forecasting"
        )

        assert version == "1"
        mock_mlflow_client.create_model_version.assert_called_once()

    def test_get_model_version(self, registry, mock_mlflow_client):
        """Test getting specific model version."""
        mock_version = Mock()
        mock_version.version = "1"
        mock_version.current_stage = "Production"
        mock_mlflow_client.get_model_version.return_value = mock_version

        version = registry.get_model_version("lstm_forecaster", "1")

        assert version.version == "1"
        assert version.current_stage == "Production"

    def test_promote_to_staging(self, registry, mock_mlflow_client):
        """Test promoting model to Staging."""
        registry.promote_model(
            name="lstm_forecaster",
            version="1",
            stage="Staging"
        )

        mock_mlflow_client.transition_model_version_stage.assert_called_once_with(
            name="lstm_forecaster",
            version="1",
            stage="Staging"
        )

    def test_promote_to_production(self, registry, mock_mlflow_client):
        """Test promoting model to Production."""
        registry.promote_model(
            name="lstm_forecaster",
            version="2",
            stage="Production"
        )

        mock_mlflow_client.transition_model_version_stage.assert_called_once_with(
            name="lstm_forecaster",
            version="2",
            stage="Production"
        )

    def test_archive_model(self, registry, mock_mlflow_client):
        """Test archiving a model version."""
        registry.archive_model(
            name="lstm_forecaster",
            version="1"
        )

        mock_mlflow_client.transition_model_version_stage.assert_called_once_with(
            name="lstm_forecaster",
            version="1",
            stage="Archived"
        )

    def test_get_production_model(self, registry, mock_mlflow_client):
        """Test getting latest production model."""
        mock_versions = [
            Mock(version="1", current_stage="Archived"),
            Mock(version="2", current_stage="Production"),
            Mock(version="3", current_stage="Staging")
        ]
        mock_mlflow_client.search_model_versions.return_value = mock_versions

        prod_version = registry.get_latest_version(
            name="lstm_forecaster",
            stage="Production"
        )

        assert prod_version.version == "2"

    def test_list_model_versions(self, registry, mock_mlflow_client):
        """Test listing all versions of a model."""
        mock_versions = [
            Mock(version="1", current_stage="Archived"),
            Mock(version="2", current_stage="Production"),
            Mock(version="3", current_stage="Staging")
        ]
        mock_mlflow_client.search_model_versions.return_value = mock_versions

        versions = registry.list_model_versions("lstm_forecaster")

        assert len(versions) == 3

    def test_delete_model_version(self, registry, mock_mlflow_client):
        """Test deleting a model version."""
        registry.delete_model_version(
            name="lstm_forecaster",
            version="1"
        )

        mock_mlflow_client.delete_model_version.assert_called_once_with(
            name="lstm_forecaster",
            version="1"
        )

    def test_update_model_description(self, registry, mock_mlflow_client):
        """Test updating model description."""
        registry.update_model_description(
            name="lstm_forecaster",
            version="2",
            description="Updated description"
        )

        mock_mlflow_client.update_model_version.assert_called_once()

    def test_get_model_uri(self, registry):
        """Test getting model URI for loading."""
        uri = registry.get_model_uri("lstm_forecaster", "Production")

        assert uri == "models:/lstm_forecaster/Production"

    def test_get_model_uri_by_version(self, registry):
        """Test getting model URI by specific version."""
        uri = registry.get_model_uri("lstm_forecaster", version="2")

        assert uri == "models:/lstm_forecaster/2"

    def test_search_models_by_tag(self, registry, mock_mlflow_client):
        """Test searching models by tag."""
        mock_models = [
            Mock(name="model1", tags={"symbol": "CrudeOIL"}),
            Mock(name="model2", tags={"symbol": "CrudeOIL"})
        ]
        mock_mlflow_client.search_registered_models.return_value = mock_models

        models = registry.search_models(filter_string="tags.symbol='CrudeOIL'")

        assert len(models) == 2

    def test_add_model_alias(self, registry, mock_mlflow_client):
        """Test adding model alias."""
        registry.set_model_alias(
            name="lstm_forecaster",
            version="2",
            alias="champion"
        )

        mock_mlflow_client.set_registered_model_alias.assert_called_once_with(
            name="lstm_forecaster",
            alias="champion",
            version="2"
        )

    def test_get_model_by_alias(self, registry, mock_mlflow_client):
        """Test getting model by alias."""
        mock_version = Mock(version="2")
        mock_mlflow_client.get_model_version_by_alias.return_value = mock_version

        version = registry.get_model_by_alias("lstm_forecaster", "champion")

        assert version.version == "2"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
