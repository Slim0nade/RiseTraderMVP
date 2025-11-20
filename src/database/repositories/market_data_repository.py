"""
Market data repository for time-series optimized queries.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, cast, desc, func, select, Text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.market_data import MarketData
from .base import BaseRepository


class MarketDataRepository(BaseRepository[MarketData]):
    """
    Repository for market data with time-series optimizations.

    Handles 13.5M+ records with efficient queries for OHLCV data.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(MarketData, session)

    async def get_by_timeframe_range(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
        source: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[MarketData]:
        """
        Get market data for a symbol and timeframe within a time range.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., '1m', '5m', '1h', '1d')
            start_time: Start of time range
            end_time: End of time range
            source: Optional data source filter
            limit: Optional limit on number of records

        Returns:
            List of MarketData instances ordered by time
        """
        query = select(MarketData).where(
            and_(
                MarketData.symbol == symbol,
                cast(MarketData.timeframe, Text) == timeframe,
                MarketData.time >= start_time,
                MarketData.time <= end_time,
            )
        )

        if source:
            query = query.where(cast(MarketData.source, Text) == source)

        query = query.order_by(MarketData.time)

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_latest_ticks(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 100,
        source: Optional[str] = None,
    ) -> List[MarketData]:
        """
        Get the latest N ticks for a symbol.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe (defaults to '1m')
            limit: Number of most recent ticks to retrieve
            source: Optional data source filter

        Returns:
            List of MarketData instances ordered by time (newest first)
        """
        query = (
            select(MarketData)
            .where(
                and_(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == timeframe,
                )
            )
            .order_by(desc(MarketData.time))
            .limit(limit)
        )

        if source:
            query = query.where(cast(MarketData.source, Text) == source)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_latest_tick(
        self,
        symbol: str,
        timeframe: str = "1m",
        source: Optional[str] = None,
    ) -> Optional[MarketData]:
        """
        Get the most recent tick for a symbol.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe (defaults to '1m')
            source: Optional data source filter

        Returns:
            Latest MarketData instance or None
        """
        query = (
            select(MarketData)
            .where(
                and_(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == timeframe,
                )
            )
            .order_by(desc(MarketData.time))
            .limit(1)
        )

        if source:
            query = query.where(cast(MarketData.source, Text) == source)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def bulk_insert_ticks(self, ticks: List[Dict[str, Any]]) -> int:
        """
        Bulk insert market data ticks.

        Optimized for high-volume tick ingestion.

        Args:
            ticks: List of tick data dictionaries

        Returns:
            Number of ticks inserted
        """
        if not ticks:
            return 0

        instances = [MarketData(**tick) for tick in ticks]
        self.session.add_all(instances)
        await self.session.flush()
        return len(instances)

    async def get_ohlcv_aggregates(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        timeframe: str = "1m",
    ) -> Optional[Dict[str, Any]]:
        """
        Get OHLCV aggregates for a time period.

        Args:
            symbol: Trading symbol
            start_time: Start of time range
            end_time: End of time range
            timeframe: Source timeframe

        Returns:
            Dictionary with aggregated OHLCV data
        """
        # Get first and last records for open/close
        first_query = (
            select(MarketData)
            .where(
                and_(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == timeframe,
                    MarketData.time >= start_time,
                    MarketData.time <= end_time,
                )
            )
            .order_by(MarketData.time)
            .limit(1)
        )

        last_query = (
            select(MarketData)
            .where(
                and_(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == timeframe,
                    MarketData.time >= start_time,
                    MarketData.time <= end_time,
                )
            )
            .order_by(desc(MarketData.time))
            .limit(1)
        )

        # Get high, low, and total volume
        agg_query = select(
            func.max(MarketData.high).label("high"),
            func.min(MarketData.low).label("low"),
            func.sum(MarketData.volume).label("total_volume"),
        ).where(
            and_(
                MarketData.symbol == symbol,
                cast(MarketData.timeframe, Text) == timeframe,
                MarketData.time >= start_time,
                MarketData.time <= end_time,
            )
        )

        # Execute queries
        first_result = await self.session.execute(first_query)
        last_result = await self.session.execute(last_query)
        agg_result = await self.session.execute(agg_query)

        first_tick = first_result.scalar_one_or_none()
        last_tick = last_result.scalar_one_or_none()
        aggregates = agg_result.one()

        if not first_tick or not last_tick:
            return None

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "start_time": start_time,
            "end_time": end_time,
            "open": float(first_tick.open),
            "high": float(aggregates.high),
            "low": float(aggregates.low),
            "close": float(last_tick.last),
            "volume": int(aggregates.total_volume or 0),
        }

    async def get_symbols(self, timeframe: Optional[str] = None) -> List[str]:
        """
        Get list of unique symbols in database.

        Args:
            timeframe: Optional timeframe filter

        Returns:
            List of unique symbols
        """
        query = select(MarketData.symbol).distinct()

        if timeframe:
            query = query.where(cast(MarketData.timeframe, Text) == timeframe)

        result = await self.session.execute(query)
        return [symbol for symbol in result.scalars().all()]

    async def get_timeframes(self, symbol: Optional[str] = None) -> List[str]:
        """
        Get list of unique timeframes in database.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of unique timeframes
        """
        query = select(MarketData.timeframe).distinct()

        if symbol:
            query = query.where(MarketData.symbol == symbol)

        result = await self.session.execute(query)
        return [timeframe for timeframe in result.scalars().all()]

    async def get_data_range(
        self, symbol: str, timeframe: str
    ) -> Optional[Dict[str, datetime]]:
        """
        Get the time range of available data for a symbol/timeframe.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe

        Returns:
            Dictionary with 'start' and 'end' datetimes, or None if no data
        """
        query = select(
            func.min(MarketData.time).label("start"),
            func.max(MarketData.time).label("end"),
        ).where(and_(MarketData.symbol == symbol, cast(MarketData.timeframe, Text) == timeframe))

        result = await self.session.execute(query)
        data_range = result.one()

        if not data_range.start or not data_range.end:
            return None

        return {
            "start": data_range.start,
            "end": data_range.end,
        }

    async def count_by_symbol_timeframe(
        self, symbol: str, timeframe: str
    ) -> int:
        """
        Count records for a specific symbol and timeframe.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe

        Returns:
            Number of records
        """
        query = select(func.count()).select_from(MarketData).where(
            and_(
                MarketData.symbol == symbol,
                cast(MarketData.timeframe, Text) == timeframe,
            )
        )

        result = await self.session.execute(query)
        return result.scalar() or 0
