"""
Unit tests for MarketDataLoader
Tests OHLCV data fetching from database for ML training
"""

import pytest
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from unittest.mock import Mock, AsyncMock, patch

from src.ml.data.market_data_loader import MarketDataLoader


@pytest.fixture
def mock_db_session():
    """Mock database session"""
    session = Mock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def sample_market_data():
    """Sample OHLCV data for testing"""
    dates = pd.date_range(start='2025-11-01', periods=100, freq='1H')
    data = pd.DataFrame({
        'timestamp': dates,
        'open': np.random.uniform(75, 80, 100),
        'high': np.random.uniform(80, 85, 100),
        'low': np.random.uniform(70, 75, 100),
        'close': np.random.uniform(75, 80, 100),
        'volume': np.random.uniform(1000, 5000, 100),
    })
    return data


class TestMarketDataLoader:
    """Test suite for MarketDataLoader"""

    @pytest.mark.asyncio
    async def test_load_ohlcv_data(self, mock_db_session, sample_market_data):
        """Test loading OHLCV data for a symbol and date range"""
        loader = MarketDataLoader(mock_db_session)

        # Mock database query result
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_market_data.to_dict('records')
        mock_db_session.execute.return_value = mock_result

        # Load data
        start_date = datetime(2025, 11, 1)
        end_date = datetime(2025, 11, 5)
        df = await loader.load_ohlcv(
            symbol="CrudeOIL",
            start_date=start_date,
            end_date=end_date
        )

        assert df is not None
        assert len(df) > 0
        assert 'open' in df.columns
        assert 'high' in df.columns
        assert 'low' in df.columns
        assert 'close' in df.columns
        assert 'volume' in df.columns

    @pytest.mark.asyncio
    async def test_load_data_with_minimum_data_points(self, mock_db_session, sample_market_data):
        """Test validation of minimum data points requirement"""
        loader = MarketDataLoader(mock_db_session)

        # Mock insufficient data
        insufficient_data = sample_market_data.head(50)
        mock_result = Mock()
        mock_result.fetchall.return_value = insufficient_data.to_dict('records')
        mock_db_session.execute.return_value = mock_result

        # Should raise error if minimum not met
        with pytest.raises(ValueError, match="Insufficient data"):
            await loader.load_ohlcv(
                symbol="CrudeOIL",
                start_date=datetime(2025, 11, 1),
                end_date=datetime(2025, 11, 5),
                min_data_points=1000
            )

    @pytest.mark.asyncio
    async def test_load_data_with_missing_values(self, mock_db_session):
        """Test handling of missing values in OHLCV data"""
        loader = MarketDataLoader(mock_db_session)

        # Create data with missing values
        dates = pd.date_range(start='2025-11-01', periods=100, freq='1H')
        data_with_nans = pd.DataFrame({
            'timestamp': dates,
            'open': [75.0] * 50 + [None] * 50,  # Missing values
            'high': np.random.uniform(80, 85, 100),
            'low': np.random.uniform(70, 75, 100),
            'close': np.random.uniform(75, 80, 100),
            'volume': np.random.uniform(1000, 5000, 100),
        })

        mock_result = Mock()
        mock_result.fetchall.return_value = data_with_nans.to_dict('records')
        mock_db_session.execute.return_value = mock_result

        df = await loader.load_ohlcv(
            symbol="CrudeOIL",
            start_date=datetime(2025, 11, 1),
            end_date=datetime(2025, 11, 5)
        )

        # Should handle missing values (forward fill)
        assert df['open'].isna().sum() == 0

    @pytest.mark.asyncio
    async def test_load_data_for_multiple_symbols(self, mock_db_session, sample_market_data):
        """Test loading data for multiple symbols"""
        loader = MarketDataLoader(mock_db_session)

        symbols = ["CrudeOIL", "Gold", "EUR_USD"]

        mock_result = Mock()
        mock_result.fetchall.return_value = sample_market_data.to_dict('records')
        mock_db_session.execute.return_value = mock_result

        results = {}
        for symbol in symbols:
            df = await loader.load_ohlcv(
                symbol=symbol,
                start_date=datetime(2025, 11, 1),
                end_date=datetime(2025, 11, 5)
            )
            results[symbol] = df

        assert len(results) == 3
        for symbol, df in results.items():
            assert len(df) > 0

    @pytest.mark.asyncio
    async def test_load_data_validates_timestamp_order(self, mock_db_session):
        """Test that timestamps are in ascending order"""
        loader = MarketDataLoader(mock_db_session)

        # Create unordered data
        dates = pd.date_range(start='2025-11-01', periods=100, freq='1H')
        shuffled_dates = dates.to_series().sample(frac=1).reset_index(drop=True)

        unordered_data = pd.DataFrame({
            'timestamp': shuffled_dates,
            'open': np.random.uniform(75, 80, 100),
            'high': np.random.uniform(80, 85, 100),
            'low': np.random.uniform(70, 75, 100),
            'close': np.random.uniform(75, 80, 100),
            'volume': np.random.uniform(1000, 5000, 100),
        })

        mock_result = Mock()
        mock_result.fetchall.return_value = unordered_data.to_dict('records')
        mock_db_session.execute.return_value = mock_result

        df = await loader.load_ohlcv(
            symbol="CrudeOIL",
            start_date=datetime(2025, 11, 1),
            end_date=datetime(2025, 11, 5)
        )

        # Should be sorted by timestamp
        assert df['timestamp'].is_monotonic_increasing

    @pytest.mark.asyncio
    async def test_load_data_caches_results(self, mock_db_session, sample_market_data):
        """Test that loader caches results for performance"""
        loader = MarketDataLoader(mock_db_session, enable_cache=True)

        mock_result = Mock()
        mock_result.fetchall.return_value = sample_market_data.to_dict('records')
        mock_db_session.execute.return_value = mock_result

        # First call
        df1 = await loader.load_ohlcv(
            symbol="CrudeOIL",
            start_date=datetime(2025, 11, 1),
            end_date=datetime(2025, 11, 5)
        )

        # Second call (should use cache)
        df2 = await loader.load_ohlcv(
            symbol="CrudeOIL",
            start_date=datetime(2025, 11, 1),
            end_date=datetime(2025, 11, 5)
        )

        # Database should only be queried once
        assert mock_db_session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_load_data_for_walk_forward_windows(self, mock_db_session, sample_market_data):
        """Test loading data for walk-forward validation windows"""
        loader = MarketDataLoader(mock_db_session)

        mock_result = Mock()
        mock_result.fetchall.return_value = sample_market_data.to_dict('records')
        mock_db_session.execute.return_value = mock_result

        # Load 30-day training window
        train_start = datetime(2025, 11, 1)
        train_end = train_start + timedelta(days=30)

        df = await loader.load_ohlcv(
            symbol="CrudeOIL",
            start_date=train_start,
            end_date=train_end
        )

        assert df is not None
        assert len(df) > 0

    @pytest.mark.asyncio
    async def test_load_data_validates_ohlc_constraints(self, mock_db_session):
        """Test validation of OHLC constraints (high >= low, etc.)"""
        loader = MarketDataLoader(mock_db_session)

        # Create invalid data where high < low
        dates = pd.date_range(start='2025-11-01', periods=100, freq='1H')
        invalid_data = pd.DataFrame({
            'timestamp': dates,
            'open': np.random.uniform(75, 80, 100),
            'high': np.random.uniform(70, 75, 100),  # High < Low (invalid)
            'low': np.random.uniform(80, 85, 100),
            'close': np.random.uniform(75, 80, 100),
            'volume': np.random.uniform(1000, 5000, 100),
        })

        mock_result = Mock()
        mock_result.fetchall.return_value = invalid_data.to_dict('records')
        mock_db_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Invalid OHLC data"):
            await loader.load_ohlcv(
                symbol="CrudeOIL",
                start_date=datetime(2025, 11, 1),
                end_date=datetime(2025, 11, 5),
                validate_ohlc=True
            )
