"""
Integration tests for ML training API endpoints.
Tests complete training workflow including MLflow integration.
"""

import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.training_runs import TrainingRun


class TestTrainingRunStatusAPI:
    """Test GET /api/v1/ml/training-runs/{run_id} endpoint."""

    @pytest.fixture
    async def sample_training_run(self, db_session: AsyncSession):
        """Create sample training run in database."""
        run = TrainingRun(
            run_name="test_training_run",
            symbol="CrudeOIL",
            model_type="lstm",
            status="completed",
            model_version="v1.0.0",
            mlflow_run_id="abc123",
            started_at=datetime.utcnow() - timedelta(minutes=10),
            completed_at=datetime.utcnow(),
            duration_seconds=600.0
        )
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)
        return run

    @pytest.fixture
    def mock_mlflow_run(self):
        """Mock MLflow run response."""
        mock_run = Mock()
        mock_run.data.params = {
            'learning_rate': '0.001',
            'batch_size': '32',
            'epochs': '100',
            'hidden_size': '128'
        }
        mock_run.data.metrics = {
            'train_loss': 0.0123,
            'val_loss': 0.0156,
            'val_mse': 0.0089,
            'val_mae': 0.067
        }
        mock_run.data.tags = {
            'model_name': 'lstm_forecaster_CrudeOIL'
        }
        mock_run.info.artifact_uri = 'mlflow-artifacts:/abc123/artifacts'
        return mock_run

    @pytest.fixture
    def mock_model_version(self):
        """Mock MLflow model version."""
        mock_version = Mock()
        mock_version.run_id = "abc123"
        mock_version.current_stage = "Production"
        mock_version.version = "1"
        return mock_version

    @pytest.mark.asyncio
    async def test_get_training_run_not_found(self, async_client: AsyncClient):
        """Test getting non-existent training run returns 404."""
        response = await async_client.get("/api/v1/ml/training-runs/99999")

        assert response.status_code == 404
        assert "not found" in response.json()['detail'].lower()

    @pytest.mark.asyncio
    async def test_get_training_run_basic_info(
        self,
        async_client: AsyncClient,
        sample_training_run: TrainingRun
    ):
        """Test getting basic training run info without MLflow."""
        # Create run without MLflow ID
        run = sample_training_run
        run.mlflow_run_id = None

        response = await async_client.get(f"/api/v1/ml/training-runs/{run.id}")

        assert response.status_code == 200
        data = response.json()

        assert data['training_run_id'] == run.id
        assert data['run_name'] == "test_training_run"
        assert data['symbol'] == "CrudeOIL"
        assert data['model_type'] == "lstm"
        assert data['status'] == "completed"
        assert data['model_version'] == "v1.0.0"
        assert data['mlflow_run_id'] is None
        assert data['duration_seconds'] == 600.0

    @pytest.mark.asyncio
    @patch('src.ml.tracking.model_registry.MlflowClient')
    async def test_get_training_run_with_mlflow(
        self,
        mock_mlflow_client_class,
        async_client: AsyncClient,
        sample_training_run: TrainingRun,
        mock_mlflow_run,
        mock_model_version
    ):
        """Test getting training run with MLflow metadata."""
        # Setup mocks
        mock_client = Mock()
        mock_client.get_run.return_value = mock_mlflow_run
        mock_client.search_model_versions.return_value = [mock_model_version]
        mock_mlflow_client_class.return_value = mock_client

        run = sample_training_run

        response = await async_client.get(f"/api/v1/ml/training-runs/{run.id}")

        assert response.status_code == 200
        data = response.json()

        # Basic info
        assert data['training_run_id'] == run.id
        assert data['mlflow_run_id'] == "abc123"

        # MLflow hyperparameters
        assert data['hyperparameters'] is not None
        assert data['hyperparameters']['learning_rate'] == '0.001'
        assert data['hyperparameters']['batch_size'] == '32'
        assert data['hyperparameters']['epochs'] == '100'

        # MLflow metrics
        assert data['metrics'] is not None
        assert data['metrics']['train_loss'] == 0.0123
        assert data['metrics']['val_loss'] == 0.0156
        assert data['metrics']['val_mse'] == 0.0089

        # Model stage
        assert data['current_stage'] == "Production"

        # Artifact URI
        assert data['artifact_uri'] == 'mlflow-artifacts:/abc123/artifacts'

    @pytest.mark.asyncio
    async def test_get_failed_training_run(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession
    ):
        """Test getting training run that failed."""
        run = TrainingRun(
            run_name="failed_run",
            symbol="CrudeOIL",
            model_type="xgboost",
            status="failed",
            started_at=datetime.utcnow() - timedelta(minutes=5),
            error_message="Insufficient training data: only 100 samples available, need at least 1000"
        )
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        response = await async_client.get(f"/api/v1/ml/training-runs/{run.id}")

        assert response.status_code == 200
        data = response.json()

        assert data['status'] == "failed"
        assert data['error_message'] is not None
        assert "Insufficient training data" in data['error_message']
        assert data['completed_at'] is None

    @pytest.mark.asyncio
    @patch('src.ml.tracking.model_registry.MlflowClient')
    async def test_get_training_run_mlflow_error_graceful(
        self,
        mock_mlflow_client_class,
        async_client: AsyncClient,
        sample_training_run: TrainingRun
    ):
        """Test that MLflow errors don't break the endpoint."""
        # Setup mock to raise error
        mock_client = Mock()
        mock_client.get_run.side_effect = Exception("MLflow server unavailable")
        mock_mlflow_client_class.return_value = mock_client

        run = sample_training_run

        response = await async_client.get(f"/api/v1/ml/training-runs/{run.id}")

        # Should still return 200 with basic database info
        assert response.status_code == 200
        data = response.json()

        assert data['training_run_id'] == run.id
        assert data['mlflow_run_id'] == "abc123"

        # MLflow fields should be None since fetch failed
        assert data['hyperparameters'] is None
        assert data['metrics'] is None
        assert data['current_stage'] is None

    @pytest.mark.asyncio
    async def test_get_running_training_run(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession
    ):
        """Test getting in-progress training run."""
        run = TrainingRun(
            run_name="in_progress_run",
            symbol="CrudeOIL",
            model_type="lstm",
            status="running",
            started_at=datetime.utcnow() - timedelta(minutes=2)
        )
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        response = await async_client.get(f"/api/v1/ml/training-runs/{run.id}")

        assert response.status_code == 200
        data = response.json()

        assert data['status'] == "running"
        assert data['completed_at'] is None
        assert data['duration_seconds'] is None
        assert data['model_version'] is None


class TestTrainingRunListAPI:
    """Test listing training runs (future endpoint)."""

    @pytest.mark.asyncio
    async def test_list_training_runs_by_symbol(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession
    ):
        """Test listing training runs filtered by symbol."""
        # Create multiple training runs
        runs = [
            TrainingRun(
                run_name=f"run_{i}",
                symbol="CrudeOIL" if i % 2 == 0 else "EURUSD",
                model_type="lstm",
                status="completed",
                started_at=datetime.utcnow() - timedelta(hours=i)
            )
            for i in range(5)
        ]

        for run in runs:
            db_session.add(run)
        await db_session.commit()

        # TODO: Implement list endpoint in Phase 7
        # response = await async_client.get("/api/v1/ml/training-runs?symbol=CrudeOIL")
        # assert response.status_code == 200
        # data = response.json()
        # assert len(data['training_runs']) == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
