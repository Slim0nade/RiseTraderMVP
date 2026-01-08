"""
Timeframe Aggregator Service

Converts M1 candle data into higher timeframes (M5, M15, H1, H4, D1, etc.)
on-the-fly without storing duplicate data in the database.

Benefits:
- Single source of truth (M1 data)
- No data discrepancies between timeframes
- Dynamic timeframe generation for any interval
- Memory efficient (streams data)
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum
import structlog

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.market_data import MarketData

logger = structlog.get_logger(__name__)


class Timeframe(Enum):
    """Standard timeframes with their M1 multipliers."""
    M1 = 1
    M2 = 2
    M3 = 3
    M5 = 5
    M10 = 10
    M15 = 15
    M20 = 20
    M30 = 30
    H1 = 60
    H2 = 120
    H3 = 180
    H4 = 240
    H6 = 360
    H8 = 480
    H12 = 720
    D1 = 1440
    W1 = 10080
    MN1 = 43200  # Approximate - 30 days


# Mapping from string to Timeframe enum
TIMEFRAME_MAP = {
    "M1": Timeframe.M1,
    "M2": Timeframe.M2,
    "M3": Timeframe.M3,
    "M5": Timeframe.M5,
    "M10": Timeframe.M10,
    "M15": Timeframe.M15,
    "M20": Timeframe.M20,
    "M30": Timeframe.M30,
    "H1": Timeframe.H1,
    "H2": Timeframe.H2,
    "H3": Timeframe.H3,
    "H4": Timeframe.H4,
    "H6": Timeframe.H6,
    "H8": Timeframe.H8,
    "H12": Timeframe.H12,
    "D1": Timeframe.D1,
    "W1": Timeframe.W1,
    "MN1": Timeframe.MN1,
}


class TimeframeAggregator:
    """
    Aggregates M1 candle data into higher timeframes.
    
    Uses pandas resample for efficient OHLCV aggregation.
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize with database session."""
        self.session = session
    
    @staticmethod
    def get_resample_rule(timeframe: Union[str, Timeframe]) -> str:
        """
        Convert timeframe to pandas resample rule.
        
        Args:
            timeframe: Timeframe string or enum
            
        Returns:
            Pandas offset string (e.g., '5min', '1h', '1D')
        """
        if isinstance(timeframe, str):
            tf = TIMEFRAME_MAP.get(timeframe.upper())
            if tf is None:
                raise ValueError(f"Unknown timeframe: {timeframe}")
        else:
            tf = timeframe
        
        minutes = tf.value
        
        if minutes < 60:
            return f"{minutes}min"
        elif minutes < 1440:
            hours = minutes // 60
            return f"{hours}h"
        elif minutes == 1440:
            return "1D"
        elif minutes == 10080:
            return "1W"
        else:
            return f"{minutes}min"
    
    @staticmethod
    def aggregate_ohlcv(df: pd.DataFrame, timeframe: Union[str, Timeframe]) -> pd.DataFrame:
        """
        Aggregate OHLCV data from M1 to target timeframe.
        
        Args:
            df: DataFrame with columns [open, high, low, close, volume] and datetime index
            timeframe: Target timeframe
            
        Returns:
            Aggregated DataFrame
        """
        if df.empty:
            return df
        
        rule = TimeframeAggregator.get_resample_rule(timeframe)
        
        # Ensure datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'time' in df.columns:
                df = df.set_index('time')
            else:
                raise ValueError("DataFrame must have datetime index or 'time' column")
        
        # Resample with OHLCV aggregation rules
        agg_dict = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
        }
        
        # Only aggregate columns that exist
        agg_dict = {k: v for k, v in agg_dict.items() if k in df.columns}
        
        # Handle 'last' column as alias for 'close'
        if 'last' in df.columns and 'close' not in df.columns:
            df = df.rename(columns={'last': 'close'})
            agg_dict['close'] = 'last'
        
        # Resample
        resampled = df.resample(rule, label='left', closed='left').agg(agg_dict)
        
        # Drop NaN rows (periods with no data)
        resampled = resampled.dropna()
        
        return resampled
    
    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        source_timeframe: str = "M1",
    ) -> pd.DataFrame:
        """
        Get candle data for any timeframe by aggregating from source.
        
        If the requested timeframe matches what's in the database, returns directly.
        Otherwise, fetches source timeframe and aggregates.
        
        Args:
            symbol: Trading symbol
            timeframe: Target timeframe
            start_date: Start date
            end_date: End date
            source_timeframe: Source timeframe in database (default M1)
            
        Returns:
            DataFrame with OHLCV data
        """
        # Check if we can use existing data directly
        if timeframe.upper() == source_timeframe.upper():
            return await self._fetch_candles(symbol, timeframe, start_date, end_date)
        
        # Check if target timeframe exists in database
        target_tf = TIMEFRAME_MAP.get(timeframe.upper())
        source_tf = TIMEFRAME_MAP.get(source_timeframe.upper())
        
        if target_tf is None:
            raise ValueError(f"Unknown timeframe: {timeframe}")
        
        # If target is smaller than source, we can't aggregate
        if target_tf.value < source_tf.value:
            raise ValueError(f"Cannot aggregate {source_timeframe} to smaller timeframe {timeframe}")
        
        # Fetch source data
        logger.info(
            "aggregating_timeframe",
            symbol=symbol,
            source=source_timeframe,
            target=timeframe,
            start=start_date,
            end=end_date,
        )
        
        # Try to fetch the target timeframe directly first
        df = await self._fetch_candles(symbol, timeframe, start_date, end_date)
        if not df.empty:
            logger.info(f"Found {len(df)} {timeframe} candles directly in database")
            return df
        
        # Fetch M1 and aggregate
        m1_df = await self._fetch_candles(symbol, source_timeframe, start_date, end_date)
        
        if m1_df.empty:
            logger.warning(f"No {source_timeframe} data found for {symbol}")
            return pd.DataFrame()
        
        logger.info(f"Aggregating {len(m1_df)} {source_timeframe} candles to {timeframe}")
        
        # Aggregate to target timeframe
        aggregated = self.aggregate_ohlcv(m1_df, timeframe)
        
        logger.info(f"Aggregation complete: {len(aggregated)} {timeframe} candles")
        
        return aggregated
    
    async def _fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """
        Fetch candles directly from database.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe string
            start_date: Start date
            end_date: End date
            
        Returns:
            DataFrame with candle data
        """
        query = select(MarketData).where(
            and_(
                MarketData.symbol == symbol,
                MarketData.timeframe == timeframe.upper(),
                MarketData.time >= start_date,
                MarketData.time <= end_date,
            )
        ).order_by(MarketData.time)
        
        result = await self.session.execute(query)
        rows = result.scalars().all()
        
        if not rows:
            return pd.DataFrame()
        
        # Convert to DataFrame
        data = []
        for row in rows:
            data.append({
                'time': row.time,
                'open': float(row.open),
                'high': float(row.high),
                'low': float(row.low),
                'close': float(row.last),  # 'last' is close
                'volume': row.volume,
            })
        
        df = pd.DataFrame(data)
        df = df.set_index('time')
        df = df.sort_index()
        
        return df
    
    async def get_candles_multi_timeframe(
        self,
        symbol: str,
        timeframes: List[str],
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, pd.DataFrame]:
        """
        Get candles for multiple timeframes efficiently.
        
        Fetches M1 once and aggregates to all requested timeframes.
        
        Args:
            symbol: Trading symbol
            timeframes: List of timeframes to generate
            start_date: Start date
            end_date: End date
            
        Returns:
            Dict mapping timeframe to DataFrame
        """
        # Find smallest timeframe to use as source
        sorted_tfs = sorted(
            [TIMEFRAME_MAP[tf.upper()] for tf in timeframes if tf.upper() in TIMEFRAME_MAP],
            key=lambda x: x.value
        )
        
        if not sorted_tfs:
            raise ValueError("No valid timeframes provided")
        
        source_tf = sorted_tfs[0]
        
        # Fetch source data
        source_df = await self._fetch_candles(
            symbol, source_tf.name, start_date, end_date
        )
        
        if source_df.empty:
            return {tf: pd.DataFrame() for tf in timeframes}
        
        # Generate all timeframes
        result = {}
        for tf_str in timeframes:
            tf = TIMEFRAME_MAP.get(tf_str.upper())
            if tf is None:
                continue
            
            if tf == source_tf:
                result[tf_str] = source_df.copy()
            else:
                result[tf_str] = self.aggregate_ohlcv(source_df, tf)
        
        return result


class TimeframeConverter:
    """
    Static utility methods for timeframe conversion.
    
    Use for quick conversions without database access.
    """
    
    @staticmethod
    def m1_to_timeframe(m1_data: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """
        Convert M1 DataFrame to any timeframe.
        
        Args:
            m1_data: DataFrame with M1 OHLCV data
            timeframe: Target timeframe string
            
        Returns:
            Aggregated DataFrame
        """
        return TimeframeAggregator.aggregate_ohlcv(m1_data, timeframe)
    
    @staticmethod
    def minutes_in_timeframe(timeframe: str) -> int:
        """Get number of minutes in a timeframe."""
        tf = TIMEFRAME_MAP.get(timeframe.upper())
        if tf is None:
            raise ValueError(f"Unknown timeframe: {timeframe}")
        return tf.value
    
    @staticmethod
    def candles_per_day(timeframe: str) -> int:
        """Get number of candles per day for a timeframe."""
        minutes = TimeframeConverter.minutes_in_timeframe(timeframe)
        return 1440 // minutes
    
    @staticmethod
    def estimate_candles(
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> int:
        """Estimate number of candles in a date range."""
        days = (end_date - start_date).days
        return days * TimeframeConverter.candles_per_day(timeframe)
