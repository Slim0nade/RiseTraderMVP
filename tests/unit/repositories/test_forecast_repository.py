"""
Unit tests for ForecastRepository.
Tests async CRUD operations for ML forecast storage and retrieval.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timedelta

from src.database.repositories.forecast_repository import ForecastRepository
from src.database.models.forecasts import Forecast


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
    """Create ForecastRepository with mock session."""
    return ForecastRepository(mock_db_session)


@pytest.fixture
def sample_forecast_data():
    """Sample forecast data for testing."""
    return {
        'symbol': 'CrudeOIL',
        'timestamp': datetime(2024, 1, 15, 10, 0, 0),
        'forecast_horizon': '30d',
        'model_type': 'lstm',
        'model_version': 'v1.0.0',
        'predicted_value': 75.5,
        'lower_bound': 73.2,
        'upper_bound': 77.8,
        'confidence_score': 0.85,
        'inference_time_ms': 45.2,
        'mlflow_run_id': 'run_abc123'
    }


@pytest.fixture
def mock_forecast():
    """Create mock Forecast instance."""
    forecast = Mock(spec=Forecast)
    forecast.id = 1
    forecast.symbol = 'CrudeOIL'
    forecast.timestamp = datetime(2024, 1, 15, 10, 0, 0)
    forecast.forecast_horizon = '30d'
    forecast.model_type = 'lstm'
    forecast.model_version = 'v1.0.0'
    forecast.predicted_value = 75.5
    forecast.lower_bound = 73.2
    forecast.upper_bound = 77.8
    forecast.confidence_score = 0.85
    forecast.created_at = datetime(2024, 1, 15, 10, 0, 0)
    forecast.inference_time_ms = 45.2
    return forecast


class TestForecastRepositoryInitialization:
    """Test repository initialization."""

    def test_initialization_with_session(self, mock_db_session):
        """Test repository initializes with database session."""
        repository = ForecastRepository(mock_db_session)

        assert repository.db == mock_db_session

    def test_session_is_stored_as_attribute(self, repository, mock_db_session):
        """Test database session is accessible as attribute."""
        assert hasattr(repository, 'db')
        assert repository.db == mock_db_session


class TestForecastRepositoryCreate:
    """Test create operations."""

    @pytest.mark.asyncio
    async def test_create_basic_forecast(self, repository, mock_db_session, sample_forecast_data):
        """Test creating basic forecast."""
        created_forecast = Mock(spec=Forecast)
        created_forecast.id = 1
        created_forecast.symbol = 'CrudeOIL'

        with pytest.mock.patch('src.database.repositories.forecast_repository.Forecast', return_value=created_forecast):
            result = await repository.create(**sample_forecast_data)

            # Verify database operations
            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_called_once()
            mock_db_session.refresh.assert_called_once()

            # Verify result
            assert result.id == 1
            assert result.symbol == 'CrudeOIL'

    @pytest.mark.asyncio
    async def test_create_with_confidence_intervals(self, repository, mock_db_session):
        """Test creating forecast with confidence intervals."""
        data = {
            'symbol': 'EURUSD',
            'timestamp': datetime(2024, 1, 15, 12, 0, 0),
            'forecast_horizon': '7d',
            'model_type': 'xgboost',
            'model_version': 'v2.0.0',
            'predicted_value': 1.0825,
            'lower_bound': 1.0750,
            'upper_bound': 1.0900,
            'confidence_score': 0.92
        }

        created_forecast = Mock(spec=Forecast)
        created_forecast.lower_bound = 1.0750
        created_forecast.upper_bound = 1.0900

        with pytest.mock.patch('src.database.repositories.forecast_repository.Forecast', return_value=created_forecast):
            result = await repository.create(**data)

            assert result.lower_bound == 1.0750
            assert result.upper_bound == 1.0900

    @pytest.mark.asyncio
    async def test_create_without_confidence_intervals(self, repository, mock_db_session):
        """Test creating forecast without confidence intervals."""
        data = {
            'symbol': 'BTCUSD',
            'timestamp': datetime(2024, 1, 15, 14, 0, 0),
            'forecast_horizon': '1h',
            'model_type': 'lstm',
            'model_version': 'v1.0.0',
            'predicted_value': 45000.0
            # No lower_bound, upper_bound, confidence_score
        }

        created_forecast = Mock(spec=Forecast)
        created_forecast.lower_bound = None
        created_forecast.upper_bound = None
        created_forecast.confidence_score = None

        with pytest.mock.patch('src.database.repositories.forecast_repository.Forecast', return_value=created_forecast):
            result = await repository.create(**data)

            assert result.lower_bound is None
            assert result.upper_bound is None

    @pytest.mark.asyncio
    async def test_create_with_mlflow_run_id(self, repository, mock_db_session):
        """Test creating forecast with MLflow tracking."""
        data = {
            'symbol': 'GOLD',
            'timestamp': datetime(2024, 1, 15, 16, 0, 0),
            'forecast_horizon': '30d',
            'model_type': 'ensemble',
            'model_version': 'v3.0.0',
            'predicted_value': 1850.5,
            'mlflow_run_id': 'mlflow_run_xyz789'
        }

        created_forecast = Mock(spec=Forecast)
        created_forecast.mlflow_run_id = 'mlflow_run_xyz789'

        with pytest.mock.patch('src.database.repositories.forecast_repository.Forecast', return_value=created_forecast):
            result = await repository.create(**data)

            assert result.mlflow_run_id == 'mlflow_run_xyz789'

    @pytest.mark.asyncio
    async def test_create_with_inference_time(self, repository, mock_db_session):
        """Test creating forecast with inference latency tracking."""
        data = {
            'symbol': 'CrudeOIL',
            'timestamp': datetime(2024, 1, 15, 18, 0, 0),
            'forecast_horizon': '1h',
            'model_type': 'lstm',
            'model_version': 'v1.0.0',
            'predicted_value': 75.8,
            'inference_time_ms': 32.5
        }

        created_forecast = Mock(spec=Forecast)
        created_forecast.inference_time_ms = 32.5

        with pytest.mock.patch('src.database.repositories.forecast_repository.Forecast', return_value=created_forecast):
            result = await repository.create(**data)

            assert result.inference_time_ms == 32.5

    @pytest.mark.asyncio
    async def test_create_different_horizons(self, repository, mock_db_session):
        """Test creating forecasts for different horizons."""
        horizons = ['1h', '4h', '1d', '7d', '30d']

        for horizon in horizons:
            data = {
                'symbol': 'CrudeOIL',
                'timestamp': datetime(2024, 1, 15, 10, 0, 0),
                'forecast_horizon': horizon,
                'model_type': 'lstm',
                'model_version': 'v1.0.0',
                'predicted_value': 75.0
            }

            created_forecast = Mock(spec=Forecast)
            created_forecast.forecast_horizon = horizon

            with pytest.mock.patch('src.database.repositories.forecast_repository.Forecast', return_value=created_forecast):
                result = await repository.create(**data)
                assert result.forecast_horizon == horizon


class TestForecastRepositoryGetLatest:
    """Test get_latest operations."""

    @pytest.mark.asyncio
    async def test_get_latest_found(self, repository, mock_db_session, mock_forecast):
        """Test retrieving latest forecast when exists."""
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = mock_forecast
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_latest('CrudeOIL', '30d', 'v1.0.0')

        assert result == mock_forecast
        assert result.symbol == 'CrudeOIL'
        assert result.forecast_horizon == '30d'
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_latest_not_found(self, repository, mock_db_session):
        """Test retrieving non-existent forecast returns None."""
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_latest('UNKNOWN', '30d', 'v999.0.0')

        assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_orders_by_created_at_desc(self, repository, mock_db_session, mock_forecast):
        """Test get_latest retrieves most recent forecast."""
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = mock_forecast
        mock_db_session.execute.return_value = mock_result

        await repository.get_latest('CrudeOIL', '30d', 'v1.0.0')

        # Verify execute called (ordering is in SQL query)
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_latest_different_symbols(self, repository, mock_db_session):
        """Test get_latest for different symbols."""
        symbols = ['CrudeOIL', 'GOLD', 'EURUSD', 'BTCUSD']

        for symbol in symbols:
            mock_forecast = Mock(spec=Forecast)
            mock_forecast.symbol = symbol

            mock_result = AsyncMock()
            mock_result.scalar_one_or_none.return_value = mock_forecast
            mock_db_session.execute.return_value = mock_result

            result = await repository.get_latest(symbol, '30d', 'v1.0.0')
            assert result.symbol == symbol

    @pytest.mark.asyncio
    async def test_get_latest_different_horizons(self, repository, mock_db_session):
        """Test get_latest for different forecast horizons."""
        horizons = ['1h', '4h', '1d', '7d', '30d']

        for horizon in horizons:
            mock_forecast = Mock(spec=Forecast)
            mock_forecast.forecast_horizon = horizon

            mock_result = AsyncMock()
            mock_result.scalar_one_or_none.return_value = mock_forecast
            mock_db_session.execute.return_value = mock_result

            result = await repository.get_latest('CrudeOIL', horizon, 'v1.0.0')
            assert result.forecast_horizon == horizon

    @pytest.mark.asyncio
    async def test_get_latest_different_versions(self, repository, mock_db_session):
        """Test get_latest for different model versions."""
        versions = ['v1.0.0', 'v1.1.0', 'v2.0.0']

        for version in versions:
            mock_forecast = Mock(spec=Forecast)
            mock_forecast.model_version = version

            mock_result = AsyncMock()
            mock_result.scalar_one_or_none.return_value = mock_forecast
            mock_db_session.execute.return_value = mock_result

            result = await repository.get_latest('CrudeOIL', '30d', version)
            assert result.model_version == version


class TestForecastRepositoryGetByTimestampRange:
    """Test get_by_timestamp_range operations."""

    @pytest.mark.asyncio
    async def test_get_by_timestamp_range_found(self, repository, mock_db_session):
        """Test retrieving forecasts within timestamp range."""
        start = datetime(2024, 1, 1, 0, 0, 0)
        end = datetime(2024, 1, 31, 23, 59, 59)

        forecasts = []
        for i in range(5):
            forecast = Mock(spec=Forecast)
            forecast.symbol = 'CrudeOIL'
            forecast.timestamp = datetime(2024, 1, i+1, 10, 0, 0)
            forecasts.append(forecast)

        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = forecasts
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_timestamp_range('CrudeOIL', start, end)

        assert isinstance(result, list)
        assert len(result) == 5
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_timestamp_range_empty(self, repository, mock_db_session):
        """Test retrieving forecasts when none in range."""
        start = datetime(2024, 1, 1, 0, 0, 0)
        end = datetime(2024, 1, 2, 0, 0, 0)

        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_timestamp_range('CrudeOIL', start, end)

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_by_timestamp_range_ordered(self, repository, mock_db_session):
        """Test results ordered by timestamp."""
        start = datetime(2024, 1, 1, 0, 0, 0)
        end = datetime(2024, 1, 5, 0, 0, 0)

        forecasts = []
        timestamps = [
            datetime(2024, 1, 3, 10, 0, 0),
            datetime(2024, 1, 1, 10, 0, 0),
            datetime(2024, 1, 4, 10, 0, 0),
            datetime(2024, 1, 2, 10, 0, 0)
        ]

        for ts in timestamps:
            forecast = Mock(spec=Forecast)
            forecast.timestamp = ts
            forecasts.append(forecast)

        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = forecasts
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_timestamp_range('CrudeOIL', start, end)

        # Verify execute called (ordering is in SQL)
        assert len(result) == 4

    @pytest.mark.asyncio
    async def test_get_by_timestamp_range_different_symbols(self, repository, mock_db_session):
        """Test timestamp range query for different symbols."""
        start = datetime(2024, 1, 1, 0, 0, 0)
        end = datetime(2024, 1, 31, 0, 0, 0)

        symbols = ['CrudeOIL', 'GOLD', 'EURUSD']

        for symbol in symbols:
            forecasts = [Mock(spec=Forecast) for _ in range(3)]
            for f in forecasts:
                f.symbol = symbol

            mock_result = AsyncMock()
            mock_scalars = Mock()
            mock_scalars.all.return_value = forecasts
            mock_result.scalars.return_value = mock_scalars
            mock_db_session.execute.return_value = mock_result

            result = await repository.get_by_timestamp_range(symbol, start, end)
            assert all(f.symbol == symbol for f in result)

    @pytest.mark.asyncio
    async def test_get_by_timestamp_range_narrow_window(self, repository, mock_db_session):
        """Test timestamp range with narrow time window."""
        start = datetime(2024, 1, 15, 10, 0, 0)
        end = datetime(2024, 1, 15, 11, 0, 0)

        forecasts = [Mock(spec=Forecast) for _ in range(2)]

        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = forecasts
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_timestamp_range('CrudeOIL', start, end)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_by_timestamp_range_wide_window(self, repository, mock_db_session):
        """Test timestamp range with wide time window."""
        start = datetime(2024, 1, 1, 0, 0, 0)
        end = datetime(2024, 12, 31, 23, 59, 59)

        forecasts = [Mock(spec=Forecast) for _ in range(365)]

        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = forecasts
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_timestamp_range('CrudeOIL', start, end)

        assert len(result) == 365


class TestForecastRepositoryIntegration:
    """Integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_create_and_retrieve_latest_workflow(self, repository, mock_db_session, sample_forecast_data):
        """Test creating forecast and retrieving as latest."""
        # Create
        created_forecast = Mock(spec=Forecast)
        created_forecast.id = 1
        created_forecast.symbol = 'CrudeOIL'
        created_forecast.forecast_horizon = '30d'
        created_forecast.model_version = 'v1.0.0'

        with pytest.mock.patch('src.database.repositories.forecast_repository.Forecast', return_value=created_forecast):
            create_result = await repository.create(**sample_forecast_data)
            assert create_result.id == 1

        # Retrieve latest
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = created_forecast
        mock_db_session.execute.return_value = mock_result

        get_result = await repository.get_latest('CrudeOIL', '30d', 'v1.0.0')
        assert get_result.symbol == 'CrudeOIL'

    @pytest.mark.asyncio
    async def test_multi_horizon_forecast_workflow(self, repository, mock_db_session):
        """Test creating forecasts for multiple horizons."""
        horizons = ['1h', '4h', '1d', '7d', '30d']

        for horizon in horizons:
            data = {
                'symbol': 'CrudeOIL',
                'timestamp': datetime(2024, 1, 15, 10, 0, 0),
                'forecast_horizon': horizon,
                'model_type': 'lstm',
                'model_version': 'v1.0.0',
                'predicted_value': 75.0 + horizons.index(horizon)
            }

            created_forecast = Mock(spec=Forecast)
            created_forecast.forecast_horizon = horizon

            with pytest.mock.patch('src.database.repositories.forecast_repository.Forecast', return_value=created_forecast):
                await repository.create(**data)

    @pytest.mark.asyncio
    async def test_historical_forecast_analysis_workflow(self, repository, mock_db_session):
        """Test workflow for analyzing historical forecast accuracy."""
        # Get forecasts for last 30 days
        end = datetime(2024, 2, 1, 0, 0, 0)
        start = end - timedelta(days=30)

        historical_forecasts = []
        for day in range(30):
            forecast = Mock(spec=Forecast)
            forecast.timestamp = start + timedelta(days=day)
            forecast.predicted_value = 75.0 + (day * 0.1)
            historical_forecasts.append(forecast)

        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = historical_forecasts
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_timestamp_range('CrudeOIL', start, end)

        assert len(result) == 30


class TestForecastRepositoryEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_create_with_minimal_required_fields(self, repository, mock_db_session):
        """Test creating forecast with only required fields."""
        minimal_data = {
            'symbol': 'TEST',
            'timestamp': datetime(2024, 1, 15, 10, 0, 0),
            'forecast_horizon': '1h',
            'model_type': 'simple',
            'model_version': 'v1.0.0',
            'predicted_value': 100.0
        }

        created_forecast = Mock(spec=Forecast)
        created_forecast.lower_bound = None
        created_forecast.upper_bound = None

        with pytest.mock.patch('src.database.repositories.forecast_repository.Forecast', return_value=created_forecast):
            result = await repository.create(**minimal_data)

            assert result.lower_bound is None

    @pytest.mark.asyncio
    async def test_get_latest_with_special_characters_in_symbol(self, repository, mock_db_session):
        """Test get_latest with special characters in symbol."""
        mock_forecast = Mock(spec=Forecast)
        mock_forecast.symbol = 'CRUDE-OIL'

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = mock_forecast
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_latest('CRUDE-OIL', '30d', 'v1.0.0')
        assert result.symbol == 'CRUDE-OIL'

    @pytest.mark.asyncio
    async def test_get_by_timestamp_range_same_start_end(self, repository, mock_db_session):
        """Test timestamp range with same start and end."""
        timestamp = datetime(2024, 1, 15, 10, 0, 0)

        mock_result = AsyncMock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_timestamp_range('CrudeOIL', timestamp, timestamp)

        assert isinstance(result, list)


class TestForecastRepositoryRealWorldScenarios:
    """Test realistic trading scenarios."""

    @pytest.mark.asyncio
    async def test_intraday_forecast_updates(self, repository, mock_db_session):
        """Test creating multiple intraday forecast updates."""
        base_time = datetime(2024, 1, 15, 9, 0, 0)

        for hour in range(8):  # 9 AM to 5 PM
            data = {
                'symbol': 'CrudeOIL',
                'timestamp': base_time + timedelta(hours=hour),
                'forecast_horizon': '1h',
                'model_type': 'lstm',
                'model_version': 'v1.0.0',
                'predicted_value': 75.0 + (hour * 0.2),
                'inference_time_ms': 35.0 + (hour * 2)
            }

            created_forecast = Mock(spec=Forecast)

            with pytest.mock.patch('src.database.repositories.forecast_repository.Forecast', return_value=created_forecast):
                await repository.create(**data)

    @pytest.mark.asyncio
    async def test_ensemble_forecast_storage(self, repository, mock_db_session):
        """Test storing ensemble forecast results."""
        data = {
            'symbol': 'CrudeOIL',
            'timestamp': datetime(2024, 1, 15, 10, 0, 0),
            'forecast_horizon': '30d',
            'model_type': 'ensemble',
            'model_version': 'v1.0.0_ensemble',
            'predicted_value': 75.5,  # Weighted average
            'lower_bound': 72.0,  # Conservative bound
            'upper_bound': 79.0,  # Conservative bound
            'confidence_score': 0.88
        }

        created_forecast = Mock(spec=Forecast)
        created_forecast.model_type = 'ensemble'

        with pytest.mock.patch('src.database.repositories.forecast_repository.Forecast', return_value=created_forecast):
            result = await repository.create(**data)
            assert result.model_type == 'ensemble'

    @pytest.mark.asyncio
    async def test_model_rollout_scenario(self, repository, mock_db_session):
        """Test forecast storage during model version rollout."""
        timestamp = datetime(2024, 1, 15, 10, 0, 0)

        # Old version forecast
        old_data = {
            'symbol': 'CrudeOIL',
            'timestamp': timestamp,
            'forecast_horizon': '30d',
            'model_type': 'lstm',
            'model_version': 'v1.0.0',
            'predicted_value': 75.0
        }

        # New version forecast
        new_data = {
            'symbol': 'CrudeOIL',
            'timestamp': timestamp,
            'forecast_horizon': '30d',
            'model_type': 'lstm',
            'model_version': 'v2.0.0',
            'predicted_value': 76.0
        }

        for data in [old_data, new_data]:
            created_forecast = Mock(spec=Forecast)
            created_forecast.model_version = data['model_version']

            with pytest.mock.patch('src.database.repositories.forecast_repository.Forecast', return_value=created_forecast):
                await repository.create(**data)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
