"""
MarketDataLoader - Fetch OHLCV data from database for ML training
Loads historical market data with validation and caching
"""

from datetime import datetime
from typing import Optional
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.database.models.market_data import MarketData


class MarketDataLoader:
    """
    Loads historical OHLCV data from database for ML model training

    Features:
    - Async database queries
    - Data validation (OHLC constraints, minimum data points)
    - Optional caching for performance
    - Missing value handling
    """

    def __init__(self, db_session: AsyncSession, enable_cache: bool = False):
        """
        Initialize MarketDataLoader

        Args:
            db_session: Async SQLAlchemy database session
            enable_cache: Enable in-memory caching of loaded data
        """
        self.db_session = db_session
        self.enable_cache = enable_cache
        self._cache = {} if enable_cache else None

    async def load_ohlcv(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        min_data_points: int = 100,
        validate_ohlc: bool = False
    ) -> pd.DataFrame:
        """
        Load OHLCV data for a symbol and date range

        Args:
            symbol: Trading symbol (e.g., "CrudeOIL")
            start_date: Start datetime for data range
            end_date: End datetime for data range
            min_data_points: Minimum required data points
            validate_ohlc: Validate OHLC constraints (high >= low, etc.)

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume

        Raises:
            ValueError: If insufficient data or invalid OHLC data
        """
        # Check cache first
        cache_key = f"{symbol}_{start_date}_{end_date}"
        if self.enable_cache and cache_key in self._cache:
            return self._cache[cache_key].copy()

        # Query database
        query = select(MarketData).where(
            and_(
                MarketData.symbol == symbol,
                MarketData.timestamp >= start_date,
                MarketData.timestamp <= end_date
            )
        ).order_by(MarketData.timestamp)

        result = await self.db_session.execute(query)
        rows = result.fetchall()

        if not rows:
            raise ValueError(f"No data found for {symbol} between {start_date} and {end_date}")

        # Convert to DataFrame
        data = []
        for row in rows:
            market_data = row[0]
            data.append({
                'timestamp': market_data.timestamp,
                'open': float(market_data.open),
                'high': float(market_data.high),
                'low': float(market_data.low),
                'close': float(market_data.close),
                'volume': float(market_data.volume) if market_data.volume else 0.0
            })

        df = pd.DataFrame(data)

        # Validate minimum data points
        if len(df) < min_data_points:
            raise ValueError(
                f"Insufficient data: {len(df)} rows (minimum: {min_data_points})"
            )

        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)

        # Handle missing values
        df = self._handle_missing_values(df)

        # Validate OHLC constraints
        if validate_ohlc:
            self._validate_ohlc_data(df)

        # Cache result
        if self.enable_cache:
            self._cache[cache_key] = df.copy()

        return df

    def _handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Handle missing values in OHLCV data using forward fill

        Args:
            df: DataFrame with potential missing values

        Returns:
            DataFrame with missing values filled
        """
        # Forward fill missing values
        df = df.fillna(method='ffill')

        # If still have NaNs at beginning, backward fill
        df = df.fillna(method='bfill')

        return df

    def _validate_ohlc_data(self, df: pd.DataFrame) -> None:
        """
        Validate OHLC constraints

        Args:
            df: DataFrame to validate

        Raises:
            ValueError: If OHLC constraints violated
        """
        # Check high >= low
        if not (df['high'] >= df['low']).all():
            raise ValueError("Invalid OHLC data: high must be >= low")

        # Check open, close within high-low range
        if not ((df['open'] >= df['low']) & (df['open'] <= df['high'])).all():
            raise ValueError("Invalid OHLC data: open must be within high-low range")

        if not ((df['close'] >= df['low']) & (df['close'] <= df['high'])).all():
            raise ValueError("Invalid OHLC data: close must be within high-low range")

        # Check no negative values
        price_columns = ['open', 'high', 'low', 'close']
        if (df[price_columns] < 0).any().any():
            raise ValueError("Invalid OHLC data: negative prices found")

    def clear_cache(self):
        """Clear cached data"""
        if self._cache:
            self._cache.clear()
