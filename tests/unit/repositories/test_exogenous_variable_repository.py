"""
Unit tests for ExogenousVariableRepository.
Tests CRUD operations and time-alignment queries.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database.repositories.exogenous_variable_repository import ExogenousVariableRepository
from src.database.models.exogenous_variables import ExogenousVariable


class TestExogenousVariableRepository:
    """Test ExogenousVariableRepository CRUD operations."""

    @pytest.fixture
    def mock_session(self):
        """Create mock AsyncSession."""
        session = AsyncMock(spec=AsyncSession)
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create ExogenousVariableRepository instance."""
        return ExogenousVariableRepository(mock_session)

    def test_initialization(self, repository, mock_session):
        """Test repository initialization."""
        assert repository.session == mock_session
        assert hasattr(repository, 'create')
        assert hasattr(repository, 'get_by_id')
        assert hasattr(repository, 'get_by_symbol_and_daterange')

    @pytest.mark.asyncio
    async def test_create_success(self, repository, mock_session):
        """Test creating a new exogenous variable record."""
        data = {
            'symbol': 'DXY',
            'timestamp': datetime(2024, 1, 1, 10, 0),
            'variable_type': 'market_indicator',
            'value': 102.5,
            'source': 'yfinance'
        }

        mock_variable = ExogenousVariable(**data, id=1)
        mock_session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, 'id', 1))

        result = await repository.create(**data)

        # Verify session operations
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_create_success(self, repository, mock_session):
        """Test bulk creating multiple exogenous variable records."""
        data_list = [
            {
                'symbol': 'DXY',
                'timestamp': datetime(2024, 1, 1, 10, 0),
                'variable_type': 'market_indicator',
                'value': 102.5,
                'source': 'yfinance'
            },
            {
                'symbol': 'DXY',
                'timestamp': datetime(2024, 1, 1, 11, 0),
                'variable_type': 'market_indicator',
                'value': 103.0,
                'source': 'yfinance'
            }
        ]

        await repository.bulk_create(data_list)

        # Verify bulk operations
        assert mock_session.add_all.called or mock_session.execute.called
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_create_empty_list(self, repository, mock_session):
        """Test bulk create with empty list."""
        await repository.bulk_create([])

        # Should not commit
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_by_id_success(self, repository, mock_session):
        """Test getting exogenous variable by ID."""
        mock_variable = ExogenousVariable(
            id=1,
            symbol='DXY',
            timestamp=datetime(2024, 1, 1, 10, 0),
            variable_type='market_indicator',
            value=102.5,
            source='yfinance'
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_variable
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_id(1)

        assert result is not None
        assert result.id == 1
        assert result.symbol == 'DXY'
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repository, mock_session):
        """Test getting non-existent exogenous variable."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_id(999)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_symbol_and_daterange_success(self, repository, mock_session):
        """Test getting exogenous variables by symbol and date range."""
        mock_variables = [
            ExogenousVariable(
                id=1,
                symbol='DXY',
                timestamp=datetime(2024, 1, 1, 10, 0),
                variable_type='market_indicator',
                value=102.5,
                source='yfinance'
            ),
            ExogenousVariable(
                id=2,
                symbol='DXY',
                timestamp=datetime(2024, 1, 1, 11, 0),
                variable_type='market_indicator',
                value=103.0,
                source='yfinance'
            )
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_variables
        mock_session.execute.return_value = mock_result

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 3)

        result = await repository.get_by_symbol_and_daterange(
            symbol='DXY',
            start_date=start_date,
            end_date=end_date
        )

        assert len(result) == 2
        assert all(v.symbol == 'DXY' for v in result)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_symbol_and_daterange_no_results(self, repository, mock_session):
        """Test getting exogenous variables with no matching results."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 3)

        result = await repository.get_by_symbol_and_daterange(
            symbol='UNKNOWN',
            start_date=start_date,
            end_date=end_date
        )

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_by_symbol_and_type_success(self, repository, mock_session):
        """Test getting exogenous variables by symbol and type."""
        mock_variables = [
            ExogenousVariable(
                id=1,
                symbol='DXY',
                timestamp=datetime(2024, 1, 1, 10, 0),
                variable_type='market_indicator',
                value=102.5,
                source='yfinance'
            )
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_variables
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_symbol_and_type(
            symbol='DXY',
            variable_type='market_indicator'
        )

        assert len(result) == 1
        assert result[0].variable_type == 'market_indicator'

    @pytest.mark.asyncio
    async def test_get_aligned_with_timestamps_success(self, repository, mock_session):
        """Test time-alignment query for joining with OHLCV data."""
        timestamps = [
            datetime(2024, 1, 1, 10, 0),
            datetime(2024, 1, 1, 11, 0)
        ]

        mock_variables = [
            ExogenousVariable(
                id=1,
                symbol='DXY',
                timestamp=datetime(2024, 1, 1, 10, 0),
                variable_type='market_indicator',
                value=102.5,
                source='yfinance'
            ),
            ExogenousVariable(
                id=2,
                symbol='DXY',
                timestamp=datetime(2024, 1, 1, 11, 0),
                variable_type='market_indicator',
                value=103.0,
                source='yfinance'
            )
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_variables
        mock_session.execute.return_value = mock_result

        result = await repository.get_aligned_with_timestamps(
            symbol='DXY',
            timestamps=timestamps
        )

        assert len(result) == 2
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_by_id_success(self, repository, mock_session):
        """Test deleting exogenous variable by ID."""
        mock_variable = ExogenousVariable(
            id=1,
            symbol='DXY',
            timestamp=datetime(2024, 1, 1, 10, 0),
            variable_type='market_indicator',
            value=102.5,
            source='yfinance'
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_variable
        mock_session.execute.return_value = mock_result

        result = await repository.delete_by_id(1)

        assert result is True
        mock_session.delete.assert_called_once_with(mock_variable)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_by_id_not_found(self, repository, mock_session):
        """Test deleting non-existent exogenous variable."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.delete_by_id(999)

        assert result is False
        mock_session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_value_success(self, repository, mock_session):
        """Test updating exogenous variable value."""
        mock_variable = ExogenousVariable(
            id=1,
            symbol='DXY',
            timestamp=datetime(2024, 1, 1, 10, 0),
            variable_type='market_indicator',
            value=102.5,
            source='yfinance'
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_variable
        mock_session.execute.return_value = mock_result

        new_value = 103.5
        result = await repository.update_value(1, new_value)

        assert result is not None
        assert mock_variable.value == new_value
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_by_symbol_success(self, repository, mock_session):
        """Test counting records by symbol."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 100
        mock_session.execute.return_value = mock_result

        count = await repository.count_by_symbol('DXY')

        assert count == 100
        mock_session.execute.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
