"""
ExogenousDataLoader - Fetch and manage exogenous variables (DXY, VIX, news events).

Provides integration with yfinance for market indicators and supports
time-alignment with OHLCV data for model training and inference.
"""

from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import logging

from src.database.repositories.exogenous_variable_repository import ExogenousVariableRepository


logger = logging.getLogger(__name__)


class ExogenousDataLoader:
    """
    Load exogenous variables (DXY, VIX) from yfinance and news events.

    Supports:
    - Fetching DXY (US Dollar Index) data
    - Fetching VIX (Volatility Index) data
    - Time-alignment with OHLCV data
    - Data quality validation
    - Bulk storage operations
    """

    # Yahoo Finance ticker symbols
    DXY_TICKER = 'DX-Y.NYB'  # US Dollar Index Futures
    VIX_TICKER = '^VIX'      # CBOE Volatility Index

    def __init__(self, repository: ExogenousVariableRepository):
        """
        Initialize ExogenousDataLoader.

        Args:
            repository: ExogenousVariableRepository for database operations
        """
        self.repository = repository

    async def fetch_dxy(
        self,
        start_date: datetime,
        end_date: datetime,
        interval: str = '1h'
    ) -> pd.DataFrame:
        """
        Fetch US Dollar Index (DXY) data from yfinance.

        Args:
            start_date: Start datetime for data fetch
            end_date: End datetime for data fetch
            interval: Data interval ('1h', '1d', etc.)

        Returns:
            DataFrame with DXY Close prices indexed by timestamp

        Raises:
            Exception: If yfinance API fails
        """
        try:
            logger.info(f"Fetching DXY data from {start_date} to {end_date}")

            # Fetch data from yfinance
            ticker = yf.Ticker(self.DXY_TICKER)
            df = ticker.history(
                start=start_date,
                end=end_date,
                interval=interval
            )

            if df.empty:
                logger.warning(f"No DXY data returned for {start_date} to {end_date}")
                return pd.DataFrame()

            # Keep only Close price and rename
            df = df[['Close']].copy()
            df.index.name = 'timestamp'

            logger.info(f"Fetched {len(df)} DXY records")
            return df

        except Exception as e:
            logger.error(f"Failed to fetch DXY data: {str(e)}")
            raise

    async def fetch_vix(
        self,
        start_date: datetime,
        end_date: datetime,
        interval: str = '1h'
    ) -> pd.DataFrame:
        """
        Fetch VIX (Volatility Index) data from yfinance.

        Args:
            start_date: Start datetime for data fetch
            end_date: End datetime for data fetch
            interval: Data interval ('1h', '1d', etc.')

        Returns:
            DataFrame with VIX Close prices indexed by timestamp

        Raises:
            Exception: If yfinance API fails
        """
        try:
            logger.info(f"Fetching VIX data from {start_date} to {end_date}")

            # Fetch data from yfinance
            ticker = yf.Ticker(self.VIX_TICKER)
            df = ticker.history(
                start=start_date,
                end=end_date,
                interval=interval
            )

            if df.empty:
                logger.warning(f"No VIX data returned for {start_date} to {end_date}")
                return pd.DataFrame()

            # Keep only Close price
            df = df[['Close']].copy()
            df.index.name = 'timestamp'

            logger.info(f"Fetched {len(df)} VIX records")
            return df

        except Exception as e:
            logger.error(f"Failed to fetch VIX data: {str(e)}")
            raise

    async def store_exogenous_data(
        self,
        symbol: str,
        variable_type: str,
        data: pd.DataFrame,
        source: str = 'yfinance'
    ) -> None:
        """
        Store exogenous variable data to database.

        Args:
            symbol: Variable symbol (e.g., 'DXY', 'VIX')
            variable_type: Type of variable ('market_indicator', 'news_event')
            data: DataFrame with timestamp index and 'Close' column
            source: Data source identifier
        """
        if data.empty:
            logger.warning(f"No data to store for {symbol}")
            return

        # Convert DataFrame to list of dicts for bulk insert
        records = []
        for timestamp, row in data.iterrows():
            records.append({
                'symbol': symbol,
                'timestamp': timestamp,
                'variable_type': variable_type,
                'value': float(row['Close']),
                'source': source
            })

        logger.info(f"Storing {len(records)} {symbol} records")
        await self.repository.bulk_create(records)

    async def load_exogenous_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> pd.DataFrame:
        """
        Load stored exogenous variable data from database.

        Args:
            symbol: Variable symbol (e.g., 'DXY', 'VIX')
            start_date: Start datetime
            end_date: End datetime

        Returns:
            DataFrame with timestamp, value columns
        """
        records = await self.repository.get_by_symbol_and_daterange(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )

        if not records:
            logger.warning(f"No stored data found for {symbol}")
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame([
            {
                'timestamp': r.timestamp,
                'value': r.value,
                'variable_type': r.variable_type
            }
            for r in records
        ])

        df = df.set_index('timestamp').sort_index()
        logger.info(f"Loaded {len(df)} {symbol} records from database")
        return df

    async def fetch_and_store_dxy(
        self,
        start_date: datetime,
        end_date: datetime,
        interval: str = '1h'
    ) -> pd.DataFrame:
        """
        Fetch DXY data from yfinance and store to database.

        Convenience method combining fetch + store operations.

        Args:
            start_date: Start datetime
            end_date: End datetime
            interval: Data interval

        Returns:
            Fetched DataFrame
        """
        df = await self.fetch_dxy(start_date, end_date, interval)

        if not df.empty:
            await self.store_exogenous_data(
                symbol='DXY',
                variable_type='market_indicator',
                data=df
            )

        return df

    async def fetch_and_store_vix(
        self,
        start_date: datetime,
        end_date: datetime,
        interval: str = '1h'
    ) -> pd.DataFrame:
        """
        Fetch VIX data from yfinance and store to database.

        Convenience method combining fetch + store operations.

        Args:
            start_date: Start datetime
            end_date: End datetime
            interval: Data interval

        Returns:
            Fetched DataFrame
        """
        df = await self.fetch_vix(start_date, end_date, interval)

        if not df.empty:
            await self.store_exogenous_data(
                symbol='VIX',
                variable_type='market_indicator',
                data=df
            )

        return df

    def validate_data_quality(self, df: pd.DataFrame) -> bool:
        """
        Validate data quality for exogenous variables.

        Checks:
        - Non-empty DataFrame
        - No NaN values in Close column
        - Reasonable value ranges

        Args:
            df: DataFrame to validate

        Returns:
            True if data is valid, False otherwise
        """
        if df.empty:
            logger.warning("Data validation failed: Empty DataFrame")
            return False

        if 'Close' not in df.columns:
            logger.warning("Data validation failed: Missing 'Close' column")
            return False

        if df['Close'].isna().any():
            logger.warning("Data validation failed: NaN values in Close column")
            return False

        return True

    async def get_aligned_exogenous_data(
        self,
        symbols: List[str],
        timestamps: List[datetime]
    ) -> pd.DataFrame:
        """
        Get exogenous data aligned with specific timestamps.

        Used for time-alignment with OHLCV data during feature engineering.

        Args:
            symbols: List of exogenous variable symbols
            timestamps: List of timestamps to align with

        Returns:
            DataFrame with columns for each symbol, indexed by timestamp
        """
        aligned_data = {}

        for symbol in symbols:
            records = await self.repository.get_aligned_with_timestamps(
                symbol=symbol,
                timestamps=timestamps
            )

            # Convert to Series
            values = pd.Series(
                [r.value for r in records],
                index=[r.timestamp for r in records]
            )

            # Reindex to match requested timestamps (forward fill missing)
            values = values.reindex(timestamps, method='ffill')
            aligned_data[symbol] = values

        df = pd.DataFrame(aligned_data)
        logger.info(f"Aligned {len(symbols)} exogenous variables with {len(timestamps)} timestamps")
        return df
