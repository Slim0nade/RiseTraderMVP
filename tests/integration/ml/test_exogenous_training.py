"""
Integration tests for exogenous variable training workflow.
Tests end-to-end flow: fetch DXY/VIX → merge with OHLCV → train models.
"""

import pytest
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.ml.data.exogenous_data_loader import ExogenousDataLoader
from src.ml.data.feature_engineering import FeatureEngineering
from src.ml.data.market_data_loader import MarketDataLoader
from src.database.repositories.exogenous_variable_repository import ExogenousVariableRepository
from src.database.models.exogenous_variables import ExogenousVariable, Base


# Test database URL (use test database, not production)
TEST_DATABASE_URL = "postgresql+asyncpg://test:test@localhost/risetrader_test"


class TestExogenousVariableTraining:
    """Integration tests for exogenous variable training workflow."""

    @pytest.fixture
    async def db_session(self):
        """Create test database session."""
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)

        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Create session
        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async with async_session() as session:
            yield session

        # Cleanup
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        await engine.dispose()

    @pytest.fixture
    def sample_ohlcv_data(self):
        """Create sample OHLCV data."""
        dates = pd.date_range('2024-01-01', periods=100, freq='1H')

        return pd.DataFrame({
            'timestamp': dates,
            'open': np.random.uniform(100, 110, 100),
            'high': np.random.uniform(110, 120, 100),
            'low': np.random.uniform(90, 100, 100),
            'close': np.random.uniform(100, 110, 100),
            'volume': np.random.randint(1000, 10000, 100)
        })

    @pytest.fixture
    def sample_exogenous_data(self):
        """Create sample exogenous data (DXY, VIX)."""
        dates = pd.date_range('2024-01-01', periods=100, freq='1H')

        return pd.DataFrame({
            'timestamp': dates,
            'DXY': np.random.uniform(102, 104, 100),
            'VIX': np.random.uniform(15, 25, 100)
        })

    @pytest.mark.asyncio
    async def test_store_and_load_exogenous_data(self, db_session):
        """Test storing and loading exogenous data."""
        repo = ExogenousVariableRepository(db_session)
        loader = ExogenousDataLoader(repo)

        # Create sample data
        dates = pd.date_range('2024-01-01', periods=10, freq='1H')
        df = pd.DataFrame({
            'Close': np.random.uniform(102, 104, 10)
        }, index=dates)

        # Store data
        await loader.store_exogenous_data(
            symbol='DXY',
            variable_type='market_indicator',
            data=df
        )

        # Load data back
        loaded_df = await loader.load_exogenous_data(
            symbol='DXY',
            start_date=dates[0],
            end_date=dates[-1]
        )

        # Verify
        assert len(loaded_df) == 10
        assert 'value' in loaded_df.columns

    @pytest.mark.asyncio
    async def test_merge_exogenous_with_ohlcv(
        self,
        sample_ohlcv_data,
        sample_exogenous_data
    ):
        """Test merging exogenous variables with OHLCV data."""
        feature_eng = FeatureEngineering()

        # Merge data
        merged_df = feature_eng.merge_exogenous_features(
            df=sample_ohlcv_data,
            exogenous_df=sample_exogenous_data[['timestamp', 'DXY', 'VIX']].set_index('timestamp'),
            normalize=True
        )

        # Verify merged data
        assert len(merged_df) == len(sample_ohlcv_data)
        assert 'DXY' in merged_df.columns
        assert 'VIX' in merged_df.columns
        assert 'DXY_normalized' in merged_df.columns
        assert 'VIX_normalized' in merged_df.columns

        # Verify no NaN values
        assert not merged_df['DXY_normalized'].isna().any()
        assert not merged_df['VIX_normalized'].isna().any()

    @pytest.mark.asyncio
    async def test_exogenous_normalization(self, sample_exogenous_data):
        """Test Z-score normalization of exogenous variables."""
        feature_eng = FeatureEngineering()

        # Prepare data
        df = sample_exogenous_data.set_index('timestamp')

        # Normalize
        normalized_df = feature_eng.normalize_exogenous_variables(
            df=df,
            exogenous_columns=['DXY', 'VIX']
        )

        # Verify normalization
        assert 'DXY_normalized' in normalized_df.columns
        assert 'VIX_normalized' in normalized_df.columns

        # Check Z-score properties (mean≈0, std≈1)
        assert abs(normalized_df['DXY_normalized'].mean()) < 0.1
        assert abs(normalized_df['VIX_normalized'].mean()) < 0.1
        assert abs(normalized_df['DXY_normalized'].std() - 1.0) < 0.1
        assert abs(normalized_df['VIX_normalized'].std() - 1.0) < 0.1

    @pytest.mark.asyncio
    async def test_time_alignment(self, db_session):
        """Test time-alignment of exogenous data with OHLCV timestamps."""
        repo = ExogenousVariableRepository(db_session)
        loader = ExogenousDataLoader(repo)

        # Create data with specific timestamps
        timestamps = [
            datetime(2024, 1, 1, 10, 0),
            datetime(2024, 1, 1, 11, 0),
            datetime(2024, 1, 1, 12, 0)
        ]

        df = pd.DataFrame({
            'Close': [102.5, 103.0, 103.5]
        }, index=timestamps)

        # Store data
        await loader.store_exogenous_data(
            symbol='DXY',
            variable_type='market_indicator',
            data=df
        )

        # Request aligned data
        aligned_data = await loader.get_aligned_exogenous_data(
            symbols=['DXY'],
            timestamps=timestamps
        )

        # Verify alignment
        assert len(aligned_data) == 3
        assert 'DXY' in aligned_data.columns

    @pytest.mark.asyncio
    async def test_missing_exogenous_data_handling(
        self,
        sample_ohlcv_data
    ):
        """Test handling of missing exogenous data (forward fill)."""
        feature_eng = FeatureEngineering()

        # Create exogenous data with gaps
        dates = pd.date_range('2024-01-01', periods=100, freq='1H')
        exogenous_data = pd.DataFrame({
            'timestamp': dates,
            'DXY': np.random.uniform(102, 104, 100),
            'VIX': np.random.uniform(15, 25, 100)
        })

        # Introduce gaps (remove some rows)
        exogenous_data = exogenous_data.iloc[::3]  # Keep every 3rd row

        # Merge with OHLCV
        merged_df = feature_eng.merge_exogenous_features(
            df=sample_ohlcv_data,
            exogenous_df=exogenous_data.set_index('timestamp'),
            normalize=False
        )

        # Verify forward fill worked (no NaN values)
        assert not merged_df['DXY'].isna().any()
        assert not merged_df['VIX'].isna().any()

    @pytest.mark.asyncio
    async def test_feature_count_with_exogenous(
        self,
        sample_ohlcv_data,
        sample_exogenous_data
    ):
        """Test that exogenous variables increase feature count."""
        feature_eng = FeatureEngineering()

        # Features without exogenous variables
        df_without = feature_eng.create_lag_features(
            sample_ohlcv_data.copy(),
            lag_periods=[1, 2, 3]
        )
        features_without = len([c for c in df_without.columns if c not in ['timestamp']])

        # Features with exogenous variables
        merged_df = feature_eng.merge_exogenous_features(
            df=sample_ohlcv_data,
            exogenous_df=sample_exogenous_data.set_index('timestamp'),
            normalize=True
        )
        df_with = feature_eng.create_lag_features(
            merged_df,
            lag_periods=[1, 2, 3]
        )
        features_with = len([c for c in df_with.columns if c not in ['timestamp']])

        # Verify feature count increased
        assert features_with > features_without

    @pytest.mark.asyncio
    async def test_bulk_insert_performance(self, db_session):
        """Test bulk insert performance for large datasets."""
        repo = ExogenousVariableRepository(db_session)

        # Create large dataset
        dates = pd.date_range('2024-01-01', periods=10000, freq='1H')
        records = [
            {
                'symbol': 'DXY',
                'timestamp': dt,
                'variable_type': 'market_indicator',
                'value': float(np.random.uniform(102, 104)),
                'source': 'yfinance'
            }
            for dt in dates
        ]

        # Bulk insert
        import time
        start = time.time()
        await repo.bulk_create(records)
        duration = time.time() - start

        # Verify performance (should complete in reasonable time)
        assert duration < 10  # Less than 10 seconds for 10K records

        # Verify count
        count = await repo.count_by_symbol('DXY')
        assert count == 10000


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
