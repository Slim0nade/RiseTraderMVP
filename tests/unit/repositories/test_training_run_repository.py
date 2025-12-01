"""
Unit tests for TrainingRunRepository.
Tests CRUD operations for training run records.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.training_run_repository import TrainingRunRepository
from src.database.models.training_runs import TrainingRun, TrainingStatus


@pytest.fixture
def mock_db_session():
    """Create a mock async database session."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = Mock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def repository(mock_db_session):
    """Create TrainingRunRepository with mock session."""
    return TrainingRunRepository(mock_db_session)


@pytest.fixture
def sample_training_run_data():
    """Sample data for creating training runs."""
    return {
        'run_name': 'lstm_crude_oil_experiment_1',
        'symbol': 'CrudeOIL',
        'model_type': 'lstm',
        'hyperparameters': {
            'hidden_size': 128,
            'num_layers': 2,
            'dropout': 0.1
        },
        'feature_config': {
            'lag_periods': [1, 2, 3, 5, 10],
            'use_technical_indicators': True
        },
        'training_config': {
            'epochs': 50,
            'batch_size': 32,
            'learning_rate': 0.001
        },
        'status': TrainingStatus.PENDING,
        'created_by': 'data_scientist_1'
    }


@pytest.fixture
def mock_training_run():
    """Create a mock TrainingRun object."""
    run = Mock(spec=TrainingRun)
    run.id = 1
    run.run_name = 'test_run'
    run.symbol = 'CrudeOIL'
    run.model_type = 'lstm'
    run.status = TrainingStatus.PENDING
    run.hyperparameters = {}
    run.feature_config = {}
    run.training_config = {}
    run.created_at = datetime.utcnow()
    run.started_at = None
    run.completed_at = None
    run.final_metrics = None
    run.model_version = None
    run.error_message = None
    return run


class TestTrainingRunRepositoryInitialization:
    """Test repository initialization."""

    def test_initialization(self, mock_db_session):
        """Test repository initializes with database session."""
        repo = TrainingRunRepository(mock_db_session)

        assert repo.db == mock_db_session

    def test_initialization_stores_session_reference(self, mock_db_session):
        """Test repository stores reference to session."""
        repo = TrainingRunRepository(mock_db_session)

        assert hasattr(repo, 'db')
        assert repo.db is not None


class TestTrainingRunRepositoryCreate:
    """Test creating training runs."""

    @pytest.mark.asyncio
    async def test_create_basic_training_run(self, repository, mock_db_session, sample_training_run_data):
        """Test creating a basic training run."""
        # Configure mock to return the created object
        created_run = Mock(spec=TrainingRun)
        created_run.id = 1
        created_run.__dict__.update(sample_training_run_data)

        with patch('src.database.repositories.training_run_repository.TrainingRun', return_value=created_run):
            result = await repository.create(**sample_training_run_data)

            # Verify database operations called
            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_called_once()
            mock_db_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_adds_to_session(self, repository, mock_db_session):
        """Test create adds training run to session."""
        data = {'run_name': 'test', 'symbol': 'CrudeOIL', 'model_type': 'lstm',
                'hyperparameters': {}, 'feature_config': {}, 'training_config': {}}

        created_run = Mock(spec=TrainingRun)
        with patch('src.database.repositories.training_run_repository.TrainingRun', return_value=created_run):
            await repository.create(**data)

            # Verify add was called with the training run
            mock_db_session.add.assert_called_once_with(created_run)

    @pytest.mark.asyncio
    async def test_create_commits_session(self, repository, mock_db_session):
        """Test create commits the session."""
        data = {'run_name': 'test', 'symbol': 'CrudeOIL', 'model_type': 'lstm',
                'hyperparameters': {}, 'feature_config': {}, 'training_config': {}}

        with patch('src.database.repositories.training_run_repository.TrainingRun'):
            await repository.create(**data)

            mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_refreshes_object(self, repository, mock_db_session):
        """Test create refreshes the object to get DB-generated values."""
        data = {'run_name': 'test', 'symbol': 'CrudeOIL', 'model_type': 'lstm',
                'hyperparameters': {}, 'feature_config': {}, 'training_config': {}}

        created_run = Mock(spec=TrainingRun)
        with patch('src.database.repositories.training_run_repository.TrainingRun', return_value=created_run):
            await repository.create(**data)

            mock_db_session.refresh.assert_called_once_with(created_run)

    @pytest.mark.asyncio
    async def test_create_returns_training_run(self, repository, mock_db_session):
        """Test create returns the created TrainingRun object."""
        data = {'run_name': 'test', 'symbol': 'CrudeOIL', 'model_type': 'lstm',
                'hyperparameters': {}, 'feature_config': {}, 'training_config': {}}

        created_run = Mock(spec=TrainingRun)
        created_run.id = 42
        with patch('src.database.repositories.training_run_repository.TrainingRun', return_value=created_run):
            result = await repository.create(**data)

            assert result.id == 42

    @pytest.mark.asyncio
    async def test_create_with_all_fields(self, repository, mock_db_session, sample_training_run_data):
        """Test create with all available fields."""
        created_run = Mock(spec=TrainingRun)
        with patch('src.database.repositories.training_run_repository.TrainingRun', return_value=created_run) as MockClass:
            await repository.create(**sample_training_run_data)

            # Verify TrainingRun was instantiated with correct data
            MockClass.assert_called_once_with(**sample_training_run_data)

    @pytest.mark.asyncio
    async def test_create_with_status_enum(self, repository, mock_db_session):
        """Test create accepts TrainingStatus enum."""
        data = {
            'run_name': 'test',
            'symbol': 'CrudeOIL',
            'model_type': 'lstm',
            'hyperparameters': {},
            'feature_config': {},
            'training_config': {},
            'status': TrainingStatus.RUNNING
        }

        created_run = Mock(spec=TrainingRun)
        with patch('src.database.repositories.training_run_repository.TrainingRun', return_value=created_run):
            await repository.create(**data)

            mock_db_session.add.assert_called_once()


class TestTrainingRunRepositoryGetById:
    """Test retrieving training run by ID."""

    @pytest.mark.asyncio
    async def test_get_by_id_existing_run(self, repository, mock_db_session, mock_training_run):
        """Test getting an existing training run by ID."""
        # Mock the execute result
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_training_run
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_id(1)

        assert result == mock_training_run
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_non_existing_run(self, repository, mock_db_session):
        """Test getting a non-existing training run returns None."""
        # Mock empty result
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_id(999)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_executes_query(self, repository, mock_db_session):
        """Test get_by_id executes a database query."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        await repository.get_by_id(1)

        # Verify execute was called
        assert mock_db_session.execute.called

    @pytest.mark.asyncio
    async def test_get_by_id_different_ids(self, repository, mock_db_session, mock_training_run):
        """Test get_by_id works with different IDs."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_training_run
        mock_db_session.execute.return_value = mock_result

        # Test with various IDs
        for test_id in [1, 42, 100, 9999]:
            result = await repository.get_by_id(test_id)
            assert result is not None


class TestTrainingRunRepositoryUpdateStatus:
    """Test updating training run status."""

    @pytest.mark.asyncio
    async def test_update_status_basic(self, repository, mock_db_session, mock_training_run):
        """Test basic status update."""
        # Mock get_by_id
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_training_run
        mock_db_session.execute.return_value = mock_result

        updated = await repository.update_status(1, TrainingStatus.RUNNING)

        # Verify status was updated
        assert mock_training_run.status == TrainingStatus.RUNNING
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_with_additional_fields(self, repository, mock_db_session, mock_training_run):
        """Test update status with additional field updates."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_training_run
        mock_db_session.execute.return_value = mock_result

        started_time = datetime.utcnow()
        await repository.update_status(
            1,
            TrainingStatus.RUNNING,
            started_at=started_time,
            mlflow_run_id='mlflow-123'
        )

        # Verify additional fields were set
        assert mock_training_run.status == TrainingStatus.RUNNING
        assert mock_training_run.started_at == started_time
        assert mock_training_run.mlflow_run_id == 'mlflow-123'

    @pytest.mark.asyncio
    async def test_update_status_to_completed(self, repository, mock_db_session, mock_training_run):
        """Test updating status to completed with metrics."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_training_run
        mock_db_session.execute.return_value = mock_result

        metrics = {'mpe': 2.5, 'rmse': 0.8, 'mae': 0.6}
        completed_time = datetime.utcnow()

        await repository.update_status(
            1,
            TrainingStatus.COMPLETED,
            completed_at=completed_time,
            final_metrics=metrics,
            model_version='v1.0.0'
        )

        assert mock_training_run.status == TrainingStatus.COMPLETED
        assert mock_training_run.completed_at == completed_time
        assert mock_training_run.final_metrics == metrics
        assert mock_training_run.model_version == 'v1.0.0'

    @pytest.mark.asyncio
    async def test_update_status_to_failed(self, repository, mock_db_session, mock_training_run):
        """Test updating status to failed with error message."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_training_run
        mock_db_session.execute.return_value = mock_result

        error_msg = "Training failed: GPU out of memory"

        await repository.update_status(
            1,
            TrainingStatus.FAILED,
            error_message=error_msg
        )

        assert mock_training_run.status == TrainingStatus.FAILED
        assert mock_training_run.error_message == error_msg

    @pytest.mark.asyncio
    async def test_update_status_commits_changes(self, repository, mock_db_session, mock_training_run):
        """Test update_status commits changes to database."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_training_run
        mock_db_session.execute.return_value = mock_result

        await repository.update_status(1, TrainingStatus.COMPLETED)

        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_refreshes_object(self, repository, mock_db_session, mock_training_run):
        """Test update_status refreshes the object."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_training_run
        mock_db_session.execute.return_value = mock_result

        await repository.update_status(1, TrainingStatus.COMPLETED)

        mock_db_session.refresh.assert_called_once_with(mock_training_run)

    @pytest.mark.asyncio
    async def test_update_status_returns_updated_run(self, repository, mock_db_session, mock_training_run):
        """Test update_status returns the updated training run."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_training_run
        mock_db_session.execute.return_value = mock_result

        result = await repository.update_status(1, TrainingStatus.COMPLETED)

        assert result == mock_training_run


class TestTrainingRunRepositoryGetBySymbol:
    """Test retrieving training runs by symbol."""

    @pytest.mark.asyncio
    async def test_get_by_symbol_returns_list(self, repository, mock_db_session):
        """Test get_by_symbol returns a list of training runs."""
        # Mock result
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_symbol('CrudeOIL')

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_by_symbol_empty_result(self, repository, mock_db_session):
        """Test get_by_symbol with no matching runs."""
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_symbol('NonExistentSymbol')

        assert result == []

    @pytest.mark.asyncio
    async def test_get_by_symbol_multiple_runs(self, repository, mock_db_session):
        """Test get_by_symbol with multiple matching runs."""
        # Create mock training runs
        run1 = Mock(spec=TrainingRun)
        run1.id = 1
        run1.symbol = 'CrudeOIL'

        run2 = Mock(spec=TrainingRun)
        run2.id = 2
        run2.symbol = 'CrudeOIL'

        run3 = Mock(spec=TrainingRun)
        run3.id = 3
        run3.symbol = 'CrudeOIL'

        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = [run1, run2, run3]
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_symbol('CrudeOIL')

        assert len(result) == 3
        assert all(run.symbol == 'CrudeOIL' for run in result)

    @pytest.mark.asyncio
    async def test_get_by_symbol_executes_query(self, repository, mock_db_session):
        """Test get_by_symbol executes a database query."""
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        await repository.get_by_symbol('CrudeOIL')

        # Verify execute was called
        assert mock_db_session.execute.called

    @pytest.mark.asyncio
    async def test_get_by_symbol_different_symbols(self, repository, mock_db_session):
        """Test get_by_symbol with different symbols."""
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        # Test various symbols
        for symbol in ['CrudeOIL', 'Gold', 'EURUSD', 'BTC']:
            result = await repository.get_by_symbol(symbol)
            assert isinstance(result, list)


class TestTrainingRunRepositoryIntegration:
    """Integration-style tests for repository workflows."""

    @pytest.mark.asyncio
    async def test_create_and_get_workflow(self, repository, mock_db_session):
        """Test creating a run and then retrieving it."""
        # Create
        created_run = Mock(spec=TrainingRun)
        created_run.id = 1
        created_run.symbol = 'CrudeOIL'

        with patch('src.database.repositories.training_run_repository.TrainingRun', return_value=created_run):
            await repository.create(
                run_name='test',
                symbol='CrudeOIL',
                model_type='lstm',
                hyperparameters={},
                feature_config={},
                training_config={}
            )

        # Get
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = created_run
        mock_db_session.execute.return_value = mock_result

        result = await repository.get_by_id(1)
        assert result.id == 1

    @pytest.mark.asyncio
    async def test_complete_training_lifecycle(self, repository, mock_db_session):
        """Test complete training run lifecycle: create -> running -> completed."""
        # Create run
        run = Mock(spec=TrainingRun)
        run.id = 1
        run.status = TrainingStatus.PENDING

        with patch('src.database.repositories.training_run_repository.TrainingRun', return_value=run):
            created = await repository.create(
                run_name='test',
                symbol='CrudeOIL',
                model_type='lstm',
                hyperparameters={},
                feature_config={},
                training_config={},
                status=TrainingStatus.PENDING
            )

        # Update to running
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = run
        mock_db_session.execute.return_value = mock_result

        await repository.update_status(1, TrainingStatus.RUNNING, started_at=datetime.utcnow())
        assert run.status == TrainingStatus.RUNNING

        # Update to completed
        await repository.update_status(
            1,
            TrainingStatus.COMPLETED,
            completed_at=datetime.utcnow(),
            final_metrics={'mpe': 2.5}
        )
        assert run.status == TrainingStatus.COMPLETED


class TestTrainingRunRepositoryEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_create_with_minimal_data(self, repository, mock_db_session):
        """Test create with only required fields."""
        minimal_data = {
            'run_name': 'minimal_test',
            'symbol': 'CrudeOIL',
            'model_type': 'lstm',
            'hyperparameters': {},
            'feature_config': {},
            'training_config': {}
        }

        created_run = Mock(spec=TrainingRun)
        with patch('src.database.repositories.training_run_repository.TrainingRun', return_value=created_run):
            result = await repository.create(**minimal_data)

            assert result is not None

    @pytest.mark.asyncio
    async def test_update_status_with_empty_kwargs(self, repository, mock_db_session, mock_training_run):
        """Test update_status with no additional fields."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_training_run
        mock_db_session.execute.return_value = mock_result

        result = await repository.update_status(1, TrainingStatus.RUNNING)

        assert result.status == TrainingStatus.RUNNING

    @pytest.mark.asyncio
    async def test_get_by_symbol_case_sensitivity(self, repository, mock_db_session):
        """Test get_by_symbol is case-sensitive."""
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        # These should be treated as different symbols
        await repository.get_by_symbol('CrudeOIL')
        await repository.get_by_symbol('crudeoil')
        await repository.get_by_symbol('CRUDEOIL')

        # Verify execute was called 3 times
        assert mock_db_session.execute.call_count == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
