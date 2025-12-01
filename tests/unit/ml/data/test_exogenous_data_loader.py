"""
Unit tests for ExogenousDataLoader.
Tests data fetching from yfinance and storage validation.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import pandas as pd
import numpy as np

from src.ml.data.exogenous_data_loader import ExogenousDataLoader
from src.database.repositories.exogenous_variable_repository import ExogenousVariableRepository


class TestExogenousDataLoader:
    """Test ExogenousDataLoader functionality."""

    @pytest.fixture
    def mock_repo(self):
        """Create mock ExogenousVariableRepository."""
        repo = Mock(spec=ExogenousVariableRepository)
        repo.create = AsyncMock()
        repo.bulk_create = AsyncMock()
        repo.get_by_symbol_and_daterange = AsyncMock()
        return repo

    @pytest.fixture
    def loader(self, mock_repo):
        """Create ExogenousDataLoader instance."""
        return ExogenousDataLoader(repository=mock_repo)

    def test_initialization(self, loader, mock_repo):
        """Test ExogenousDataLoader initialization."""
        assert loader.repository == mock_repo
        assert hasattr(loader, 'fetch_dxy')
        assert hasattr(loader, 'fetch_vix')

    @patch('src.ml.data.exogenous_data_loader.yf.download')
    @pytest.mark.asyncio
    async def test_fetch_dxy_success(self, mock_yf_download, loader):
        """Test successful DXY data fetching."""
        # Mock yfinance response
        mock_data = pd.DataFrame({
            'Close': [102.5, 103.0, 102.8],
            'Volume': [1000, 1100, 1050]
        }, index=pd.date_range('2024-01-01', periods=3, freq='1H'))

        mock_yf_download.return_value = mock_data

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 3)

        result = await loader.fetch_dxy(start_date, end_date)

        # Verify yfinance was called correctly
        mock_yf_download.assert_called_once()
        call_args = mock_yf_download.call_args
        assert 'DX-Y.NYB' in call_args[0] or 'DX-Y.NYB' in str(call_args)

        # Verify result
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3
        assert 'Close' in result.columns

    @patch('src.ml.data.exogenous_data_loader.yf.download')
    @pytest.mark.asyncio
    async def test_fetch_vix_success(self, mock_yf_download, loader):
        """Test successful VIX data fetching."""
        # Mock yfinance response
        mock_data = pd.DataFrame({
            'Close': [18.5, 19.0, 18.8],
            'Volume': [5000, 5100, 5050]
        }, index=pd.date_range('2024-01-01', periods=3, freq='1H'))

        mock_yf_download.return_value = mock_data

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 3)

        result = await loader.fetch_vix(start_date, end_date)

        # Verify yfinance was called correctly
        mock_yf_download.assert_called_once()
        call_args = mock_yf_download.call_args
        assert '^VIX' in call_args[0] or '^VIX' in str(call_args)

        # Verify result
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3
        assert 'Close' in result.columns

    @patch('src.ml.data.exogenous_data_loader.yf.download')
    @pytest.mark.asyncio
    async def test_fetch_dxy_empty_response(self, mock_yf_download, loader):
        """Test handling of empty DXY response."""
        mock_yf_download.return_value = pd.DataFrame()

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 3)

        result = await loader.fetch_dxy(start_date, end_date)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    @patch('src.ml.data.exogenous_data_loader.yf.download')
    @pytest.mark.asyncio
    async def test_fetch_vix_api_error(self, mock_yf_download, loader):
        """Test handling of VIX API error."""
        mock_yf_download.side_effect = Exception("API connection failed")

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 3)

        with pytest.raises(Exception) as exc_info:
            await loader.fetch_vix(start_date, end_date)

        assert "API connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_store_exogenous_data_success(self, loader, mock_repo):
        """Test successful storage of exogenous data."""
        df = pd.DataFrame({
            'Close': [102.5, 103.0],
        }, index=pd.date_range('2024-01-01', periods=2, freq='1H'))

        await loader.store_exogenous_data(
            symbol='DXY',
            variable_type='market_indicator',
            data=df
        )

        # Verify repository was called
        mock_repo.bulk_create.assert_called_once()
        call_args = mock_repo.bulk_create.call_args[0][0]

        assert len(call_args) == 2
        assert all('symbol' in item for item in call_args)
        assert all('variable_type' in item for item in call_args)
        assert all('value' in item for item in call_args)

    @pytest.mark.asyncio
    async def test_store_exogenous_data_empty_dataframe(self, loader, mock_repo):
        """Test storage with empty DataFrame."""
        df = pd.DataFrame()

        await loader.store_exogenous_data(
            symbol='DXY',
            variable_type='market_indicator',
            data=df
        )

        # Verify repository was NOT called
        mock_repo.bulk_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_exogenous_data_success(self, loader, mock_repo):
        """Test successful loading of stored exogenous data."""
        # Mock repository response
        mock_repo.get_by_symbol_and_daterange.return_value = [
            {
                'symbol': 'DXY',
                'timestamp': datetime(2024, 1, 1, 10, 0),
                'value': 102.5,
                'variable_type': 'market_indicator'
            },
            {
                'symbol': 'DXY',
                'timestamp': datetime(2024, 1, 1, 11, 0),
                'value': 103.0,
                'variable_type': 'market_indicator'
            }
        ]

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 3)

        result = await loader.load_exogenous_data(
            symbol='DXY',
            start_date=start_date,
            end_date=end_date
        )

        # Verify repository was called
        mock_repo.get_by_symbol_and_daterange.assert_called_once_with(
            symbol='DXY',
            start_date=start_date,
            end_date=end_date
        )

        # Verify result
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        assert 'value' in result.columns
        assert 'timestamp' in result.columns

    @pytest.mark.asyncio
    async def test_load_exogenous_data_no_data(self, loader, mock_repo):
        """Test loading when no data exists."""
        mock_repo.get_by_symbol_and_daterange.return_value = []

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 3)

        result = await loader.load_exogenous_data(
            symbol='DXY',
            start_date=start_date,
            end_date=end_date
        )

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_fetch_and_store_workflow(self, loader, mock_repo):
        """Test complete workflow: fetch from API and store."""
        with patch('src.ml.data.exogenous_data_loader.yf.download') as mock_yf:
            # Mock yfinance response
            mock_data = pd.DataFrame({
                'Close': [102.5, 103.0],
            }, index=pd.date_range('2024-01-01', periods=2, freq='1H'))

            mock_yf.return_value = mock_data

            start_date = datetime(2024, 1, 1)
            end_date = datetime(2024, 1, 3)

            # Fetch data
            df = await loader.fetch_dxy(start_date, end_date)

            # Store data
            await loader.store_exogenous_data(
                symbol='DXY',
                variable_type='market_indicator',
                data=df
            )

            # Verify both operations completed
            mock_yf.assert_called_once()
            mock_repo.bulk_create.assert_called_once()

    def test_validate_data_quality_success(self, loader):
        """Test data quality validation with good data."""
        df = pd.DataFrame({
            'Close': [102.5, 103.0, 102.8],
        }, index=pd.date_range('2024-01-01', periods=3, freq='1H'))

        # Should not raise exception
        is_valid = loader.validate_data_quality(df)
        assert is_valid is True

    def test_validate_data_quality_missing_values(self, loader):
        """Test data quality validation with missing values."""
        df = pd.DataFrame({
            'Close': [102.5, np.nan, 102.8],
        }, index=pd.date_range('2024-01-01', periods=3, freq='1H'))

        is_valid = loader.validate_data_quality(df)
        assert is_valid is False

    def test_validate_data_quality_empty_dataframe(self, loader):
        """Test data quality validation with empty DataFrame."""
        df = pd.DataFrame()

        is_valid = loader.validate_data_quality(df)
        assert is_valid is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
