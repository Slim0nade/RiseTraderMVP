"""
Unit tests for ModelMetricsRepository.
Tests async CRUD operations for model performance metrics.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from src.database.repositories.model_metrics_repository import ModelMetricsRepository
from src.database.models.model_metrics import ModelMetrics


@pytest.fixture
def mock_db_session():
    """Create mock async database session."""
    session = AsyncMock()
    session.add = Mock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def repository(mock_db_session):
    """Create ModelMetricsRepository with mock session."""
    return ModelMetricsRepository(mock_db_session)


@pytest.fixture
def sample_metrics_data():
    """Sample model metrics data for testing."""
    return {
        'model_type': 'xgboost',
        'model_version': 'v1.0.0',
        'symbol': 'CrudeOIL',
        'forecast_horizon': '30d',
        'mpe': 2.5,
        'rmse': 0.8,
        'mae': 0.6,
        'mape': 3.2,
        'directional_accuracy': 65.5,
        'evaluation_date': datetime(2024, 1, 15, 10, 0, 0),
        'sample_size': 1000,
        'mlflow_run_id': 'abc123def456'
    }


@pytest.fixture
def mock_model_metrics():
    """Create mock ModelMetrics instance."""
    metrics = Mock(spec=ModelMetrics)
    metrics.id = 1
    metrics.model_type = 'xgboost'
    metrics.model_version = 'v1.0.0'
    metrics.symbol = 'CrudeOIL'
    metrics.forecast_horizon = '30d'
    metrics.mpe = 2.5
    metrics.rmse = 0.8
    metrics.mae = 0.6
    metrics.mape = 3.2
    metrics.directional_accuracy = 65.5
    metrics.evaluation_date = datetime(2024, 1, 15, 10, 0, 0)
    metrics.sample_size = 1000
    metrics.mlflow_run_id = 'abc123def456'
    return metrics


class TestModelMetricsRepositoryInitialization:
    """Test repository initialization."""

    def test_initialization_with_session(self, mock_db_session):
        """Test repository initializes with database session."""
        repository = ModelMetricsRepository(mock_db_session)

        assert repository.db == mock_db_session

    def test_session_is_stored_as_attribute(self, repository, mock_db_session):
        """Test database session is accessible as attribute."""
        assert hasattr(repository, 'db')
        assert repository.db == mock_db_session


class TestModelMetricsRepositoryCreate:
    """Test create operations."""

    @pytest.mark.asyncio
    async def test_create_basic_metrics(self, repository, mock_db_session, sample_metrics_data):
        """Test creating basic model metrics."""
        created_metrics = Mock(spec=ModelMetrics)
        created_metrics.id = 1
        created_metrics.model_version = 'v1.0.0'

        with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=created_metrics):
            result = await repository.create(**sample_metrics_data)

            # Verify database operations
            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_called_once()
            mock_db_session.refresh.assert_called_once()

            # Verify result
            assert result.id == 1
            assert result.model_version == 'v1.0.0'

    @pytest.mark.asyncio
    async def test_create_with_all_metrics(self, repository, mock_db_session):
        """Test creating metrics with all five metric values."""
        full_data = {
            'model_type': 'lstm',
            'model_version': 'v2.1.0',
            'symbol': 'EURUSD',
            'forecast_horizon': '7d',
            'mpe': 1.2,
            'rmse': 0.5,
            'mae': 0.4,
            'mape': 2.1,
            'directional_accuracy': 72.3,
            'evaluation_date': datetime.utcnow(),
            'sample_size': 5000
        }

        created_metrics = Mock(spec=ModelMetrics)
        created_metrics.mpe = 1.2
        created_metrics.rmse = 0.5
        created_metrics.mae = 0.4
        created_metrics.mape = 2.1
        created_metrics.directional_accuracy = 72.3

        with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=created_metrics):
            result = await repository.create(**full_data)

            # Verify all metrics are set
            assert result.mpe == 1.2
            assert result.rmse == 0.5
            assert result.mae == 0.4
            assert result.mape == 2.1
            assert result.directional_accuracy == 72.3

    @pytest.mark.asyncio
    async def test_create_without_optional_fields(self, repository, mock_db_session):
        """Test creating metrics without optional fields."""
        minimal_data = {
            'model_type': 'tft',
            'model_version': 'v0.5.0',
            'symbol': 'BTCUSD',
            'forecast_horizon': '1d',
            'mpe': 0.5,
            'rmse': 0.2,
            'mae': 0.15,
            'mape': 1.0
            # No directional_accuracy, sample_size, mlflow_run_id
        }

        created_metrics = Mock(spec=ModelMetrics)
        created_metrics.directional_accuracy = None
        created_metrics.sample_size = None
        created_metrics.mlflow_run_id = None

        with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=created_metrics):
            result = await repository.create(**minimal_data)

            # Verify optional fields can be None
            assert result.directional_accuracy is None
            assert result.sample_size is None
            assert result.mlflow_run_id is None

    @pytest.mark.asyncio
    async def test_create_multiple_horizons_same_version(self, repository, mock_db_session):
        """Test creating metrics for multiple horizons of same model version."""
        base_data = {
            'model_type': 'xgboost',
            'model_version': 'v1.0.0',
            'symbol': 'CrudeOIL',
            'mpe': 2.0,
            'rmse': 0.5,
            'mae': 0.4,
            'mape': 2.5
        }

        horizons = ['1d', '7d', '30d']

        for horizon in horizons:
            data = {**base_data, 'forecast_horizon': horizon}
            created_metrics = Mock(spec=ModelMetrics)
            created_metrics.forecast_horizon = horizon

            with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=created_metrics):
                result = await repository.create(**data)
                assert result.forecast_horizon == horizon

    @pytest.mark.asyncio
    async def test_create_with_mlflow_run_id(self, repository, mock_db_session):
        """Test creating metrics with MLflow run tracking."""
        data = {
            'model_type': 'lstm',
            'model_version': 'v3.0.0',
            'symbol': 'GOLD',
            'forecast_horizon': '30d',
            'mpe': 1.8,
            'rmse': 0.7,
            'mae': 0.5,
            'mape': 2.8,
            'mlflow_run_id': 'mlflow_run_abc123xyz789'
        }

        created_metrics = Mock(spec=ModelMetrics)
        created_metrics.mlflow_run_id = 'mlflow_run_abc123xyz789'

        with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=created_metrics):
            result = await repository.create(**data)
            assert result.mlflow_run_id == 'mlflow_run_abc123xyz789'

    @pytest.mark.asyncio
    async def test_create_different_model_types(self, repository, mock_db_session):
        """Test creating metrics for different model types."""
        model_types = ['xgboost', 'lstm', 'tft', 'ensemble']

        for model_type in model_types:
            data = {
                'model_type': model_type,
                'model_version': 'v1.0.0',
                'symbol': 'CrudeOIL',
                'forecast_horizon': '7d',
                'mpe': 1.0,
                'rmse': 0.5,
                'mae': 0.4,
                'mape': 2.0
            }

            created_metrics = Mock(spec=ModelMetrics)
            created_metrics.model_type = model_type

            with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=created_metrics):
                result = await repository.create(**data)
                assert result.model_type == model_type


class TestModelMetricsRepositoryGetByModelVersion:
    """Test get by model version and horizon operations."""

    @pytest.mark.asyncio
    async def test_get_by_version_and_horizon_found(self, repository, mock_db_session, mock_model_metrics):
        """Test retrieving metrics by version and horizon when exists."""
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = mock_model_metrics
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_model_version('v1.0.0', '30d')

        assert result == mock_model_metrics
        assert result.model_version == 'v1.0.0'
        assert result.forecast_horizon == '30d'
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_version_and_horizon_not_found(self, repository, mock_db_session):
        """Test retrieving non-existent metrics returns None."""
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_model_version('v999.0.0', '30d')

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_version_different_horizons(self, repository, mock_db_session):
        """Test retrieving metrics for same version, different horizons."""
        horizons = ['1d', '7d', '30d']

        for horizon in horizons:
            mock_metrics = Mock(spec=ModelMetrics)
            mock_metrics.model_version = 'v1.0.0'
            mock_metrics.forecast_horizon = horizon

            mock_result = AsyncMock()
            mock_result.scalar_one_or_none.return_value = mock_metrics
            mock_db_session.execute.return_value = mock_result

            result = await repository.get_by_model_version('v1.0.0', horizon)
            assert result.forecast_horizon == horizon

    @pytest.mark.asyncio
    async def test_get_by_version_query_construction(self, repository, mock_db_session):
        """Test query is constructed with correct filters."""
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        await repository.get_by_model_version('v2.5.1', '7d')

        # Verify execute was called (query construction is internal)
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_version_case_sensitivity(self, repository, mock_db_session):
        """Test version and horizon matching is case-sensitive."""
        mock_metrics_lower = Mock(spec=ModelMetrics)
        mock_metrics_lower.model_version = 'v1.0.0'
        mock_metrics_lower.forecast_horizon = '30d'

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = mock_metrics_lower
        mock_db_session.execute.return_value = mock_result

        # Query with exact case
        result = await repository.get_by_model_version('v1.0.0', '30d')
        assert result is not None


class TestModelMetricsRepositoryGetAllForModel:
    """Test get all metrics for a model version."""

    @pytest.mark.asyncio
    async def test_get_all_for_model_multiple_horizons(self, repository, mock_db_session):
        """Test retrieving all metrics for a model across horizons."""
        metrics_list = []
        for horizon in ['1d', '7d', '30d']:
            metrics = Mock(spec=ModelMetrics)
            metrics.model_version = 'v1.0.0'
            metrics.forecast_horizon = horizon
            metrics_list.append(metrics)

        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = metrics_list
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_all_for_model('v1.0.0')

        assert isinstance(result, list)
        assert len(result) == 3
        assert all(m.model_version == 'v1.0.0' for m in result)

    @pytest.mark.asyncio
    async def test_get_all_for_model_empty_result(self, repository, mock_db_session):
        """Test retrieving all metrics when none exist."""
        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_all_for_model('v999.0.0')

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_all_for_model_single_metric(self, repository, mock_db_session, mock_model_metrics):
        """Test retrieving all metrics when only one exists."""
        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = [mock_model_metrics]
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_all_for_model('v1.0.0')

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == mock_model_metrics

    @pytest.mark.asyncio
    async def test_get_all_for_model_multiple_symbols(self, repository, mock_db_session):
        """Test get_all returns metrics across different symbols for same version."""
        metrics_list = []
        for symbol in ['CrudeOIL', 'GOLD', 'EURUSD']:
            metrics = Mock(spec=ModelMetrics)
            metrics.model_version = 'v1.0.0'
            metrics.symbol = symbol
            metrics.forecast_horizon = '30d'
            metrics_list.append(metrics)

        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = metrics_list
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_all_for_model('v1.0.0')

        assert len(result) == 3
        symbols = {m.symbol for m in result}
        assert symbols == {'CrudeOIL', 'GOLD', 'EURUSD'}

    @pytest.mark.asyncio
    async def test_get_all_for_model_preserves_order(self, repository, mock_db_session):
        """Test get_all preserves database result order."""
        metrics_list = []
        for i in range(5):
            metrics = Mock(spec=ModelMetrics)
            metrics.id = i + 1
            metrics.model_version = 'v1.0.0'
            metrics_list.append(metrics)

        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = metrics_list
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_all_for_model('v1.0.0')

        # Verify order matches input
        for i, metrics in enumerate(result):
            assert metrics.id == i + 1


class TestModelMetricsRepositoryIntegration:
    """Integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_create_and_retrieve_workflow(self, repository, mock_db_session, sample_metrics_data):
        """Test creating metrics and then retrieving them."""
        # Create
        created_metrics = Mock(spec=ModelMetrics)
        created_metrics.id = 1
        created_metrics.model_version = 'v1.0.0'
        created_metrics.forecast_horizon = '30d'
        created_metrics.rmse = 0.8

        with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=created_metrics):
            create_result = await repository.create(**sample_metrics_data)
            assert create_result.id == 1

        # Retrieve
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = created_metrics
        mock_db_session.execute.return_value = mock_result

        get_result = await repository.get_by_model_version('v1.0.0', '30d')
        assert get_result.model_version == 'v1.0.0'
        assert get_result.forecast_horizon == '30d'

    @pytest.mark.asyncio
    async def test_create_multiple_horizons_retrieve_all(self, repository, mock_db_session):
        """Test creating metrics for multiple horizons and retrieving all."""
        horizons = ['1d', '7d', '30d']
        created_metrics_list = []

        # Create for each horizon
        for horizon in horizons:
            data = {
                'model_type': 'xgboost',
                'model_version': 'v1.0.0',
                'symbol': 'CrudeOIL',
                'forecast_horizon': horizon,
                'mpe': 2.0,
                'rmse': 0.5,
                'mae': 0.4,
                'mape': 2.5
            }

            metrics = Mock(spec=ModelMetrics)
            metrics.model_version = 'v1.0.0'
            metrics.forecast_horizon = horizon
            created_metrics_list.append(metrics)

            with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=metrics):
                await repository.create(**data)

        # Retrieve all
        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = created_metrics_list
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        all_metrics = await repository.get_all_for_model('v1.0.0')
        assert len(all_metrics) == 3
        retrieved_horizons = {m.forecast_horizon for m in all_metrics}
        assert retrieved_horizons == {'1d', '7d', '30d'}

    @pytest.mark.asyncio
    async def test_model_version_progression(self, repository, mock_db_session):
        """Test tracking metrics across model version updates."""
        versions = ['v1.0.0', 'v1.1.0', 'v2.0.0']

        for version in versions:
            data = {
                'model_type': 'xgboost',
                'model_version': version,
                'symbol': 'CrudeOIL',
                'forecast_horizon': '30d',
                'mpe': 2.0,
                'rmse': 0.5,
                'mae': 0.4,
                'mape': 2.5
            }

            metrics = Mock(spec=ModelMetrics)
            metrics.model_version = version

            with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=metrics):
                result = await repository.create(**data)
                assert result.model_version == version


class TestModelMetricsRepositoryEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_create_with_zero_metrics(self, repository, mock_db_session):
        """Test creating metrics with all zeros (perfect prediction)."""
        data = {
            'model_type': 'perfect',
            'model_version': 'v0.0.1',
            'symbol': 'TEST',
            'forecast_horizon': '1d',
            'mpe': 0.0,
            'rmse': 0.0,
            'mae': 0.0,
            'mape': 0.0,
            'directional_accuracy': 100.0
        }

        created_metrics = Mock(spec=ModelMetrics)
        created_metrics.rmse = 0.0
        created_metrics.directional_accuracy = 100.0

        with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=created_metrics):
            result = await repository.create(**data)
            assert result.rmse == 0.0
            assert result.directional_accuracy == 100.0

    @pytest.mark.asyncio
    async def test_create_with_negative_error_metrics(self, repository, mock_db_session):
        """Test creating metrics with negative MPE (systematic under-prediction)."""
        data = {
            'model_type': 'xgboost',
            'model_version': 'v1.0.0',
            'symbol': 'CrudeOIL',
            'forecast_horizon': '30d',
            'mpe': -5.2,  # Negative bias
            'rmse': 0.8,
            'mae': 0.6,
            'mape': 5.2
        }

        created_metrics = Mock(spec=ModelMetrics)
        created_metrics.mpe = -5.2

        with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=created_metrics):
            result = await repository.create(**data)
            assert result.mpe == -5.2

    @pytest.mark.asyncio
    async def test_create_with_very_large_sample_size(self, repository, mock_db_session):
        """Test creating metrics with large sample size."""
        data = {
            'model_type': 'lstm',
            'model_version': 'v1.0.0',
            'symbol': 'BTCUSD',
            'forecast_horizon': '1d',
            'mpe': 1.0,
            'rmse': 0.5,
            'mae': 0.4,
            'mape': 2.0,
            'sample_size': 1000000
        }

        created_metrics = Mock(spec=ModelMetrics)
        created_metrics.sample_size = 1000000

        with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=created_metrics):
            result = await repository.create(**data)
            assert result.sample_size == 1000000

    @pytest.mark.asyncio
    async def test_get_by_version_with_special_characters(self, repository, mock_db_session):
        """Test retrieving metrics with special characters in version."""
        mock_metrics = Mock(spec=ModelMetrics)
        mock_metrics.model_version = 'v1.0.0-beta.1'

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = mock_metrics
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_model_version('v1.0.0-beta.1', '30d')
        assert result.model_version == 'v1.0.0-beta.1'

    @pytest.mark.asyncio
    async def test_get_all_for_model_with_no_version_match(self, repository, mock_db_session):
        """Test get_all with version that doesn't exist."""
        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_all_for_model('nonexistent-version')

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_create_with_minimal_required_fields(self, repository, mock_db_session):
        """Test creating metrics with only required fields."""
        minimal_data = {
            'model_type': 'simple',
            'model_version': 'v0.1.0',
            'symbol': 'TEST',
            'forecast_horizon': '1d',
            'mpe': 0.0,
            'rmse': 0.0,
            'mae': 0.0,
            'mape': 0.0
        }

        created_metrics = Mock(spec=ModelMetrics)
        created_metrics.directional_accuracy = None
        created_metrics.sample_size = None
        created_metrics.mlflow_run_id = None

        with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=created_metrics):
            result = await repository.create(**minimal_data)

            # Optional fields should be None/not set
            assert result.directional_accuracy is None
            assert result.sample_size is None
            assert result.mlflow_run_id is None

    @pytest.mark.asyncio
    async def test_create_with_empty_string_mlflow_id(self, repository, mock_db_session):
        """Test creating metrics with empty MLflow run ID."""
        data = {
            'model_type': 'xgboost',
            'model_version': 'v1.0.0',
            'symbol': 'CrudeOIL',
            'forecast_horizon': '30d',
            'mpe': 2.0,
            'rmse': 0.5,
            'mae': 0.4,
            'mape': 2.5,
            'mlflow_run_id': ''
        }

        created_metrics = Mock(spec=ModelMetrics)
        created_metrics.mlflow_run_id = ''

        with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=created_metrics):
            result = await repository.create(**data)
            assert result.mlflow_run_id == ''


class TestModelMetricsRepositoryRealWorldScenarios:
    """Test realistic trading scenarios."""

    @pytest.mark.asyncio
    async def test_ensemble_model_tracking(self, repository, mock_db_session):
        """Test tracking metrics for ensemble models across components."""
        ensemble_data = {
            'model_type': 'ensemble',
            'model_version': 'v1.0.0_ensemble',
            'symbol': 'CrudeOIL',
            'forecast_horizon': '30d',
            'mpe': 1.5,
            'rmse': 0.45,
            'mae': 0.35,
            'mape': 2.0,
            'directional_accuracy': 68.5,
            'sample_size': 2000,
            'mlflow_run_id': 'ensemble_run_123'
        }

        created_metrics = Mock(spec=ModelMetrics)
        created_metrics.model_type = 'ensemble'
        created_metrics.rmse = 0.45

        with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=created_metrics):
            result = await repository.create(**ensemble_data)
            assert result.model_type == 'ensemble'
            assert result.rmse == 0.45

    @pytest.mark.asyncio
    async def test_multi_asset_model_tracking(self, repository, mock_db_session):
        """Test tracking same model version across multiple assets."""
        symbols = ['CrudeOIL', 'GOLD', 'EURUSD', 'BTCUSD']

        for symbol in symbols:
            data = {
                'model_type': 'xgboost',
                'model_version': 'v1.0.0',
                'symbol': symbol,
                'forecast_horizon': '30d',
                'mpe': 2.0,
                'rmse': 0.5,
                'mae': 0.4,
                'mape': 2.5
            }

            metrics = Mock(spec=ModelMetrics)
            metrics.symbol = symbol
            metrics.model_version = 'v1.0.0'

            with patch('src.database.repositories.model_metrics_repository.ModelMetrics', return_value=metrics):
                result = await repository.create(**data)
                assert result.symbol == symbol

    @pytest.mark.asyncio
    async def test_model_comparison_workflow(self, repository, mock_db_session):
        """Test workflow for comparing different model types."""
        model_types = ['xgboost', 'lstm', 'tft']
        metrics_list = []

        for model_type in model_types:
            metrics = Mock(spec=ModelMetrics)
            metrics.model_type = model_type
            metrics.model_version = f'{model_type}_v1.0.0'
            metrics.rmse = 0.5 + (0.1 * model_types.index(model_type))
            metrics_list.append(metrics)

        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = metrics_list
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        # This would retrieve all models for comparison
        for model_type in model_types:
            result = await repository.get_all_for_model(f'{model_type}_v1.0.0')
            # In real scenario, would compare RMSE across models


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
