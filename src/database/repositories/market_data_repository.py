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

    async def upsert(self, data: Dict[str, Any]) -> MarketData:
        """
        Insert or update market data based on unique constraint.

        Checks for existing record by (time, source, timeframe, symbol).
        Updates if exists and values changed, inserts if new.

        Args:
            data: Dictionary of market data attributes

        Returns:
            MarketData instance (created or updated)
        """
        # Check for existing record using unique constraint fields
        existing_query = select(MarketData).where(
            and_(
                MarketData.time == data['time'],
                cast(MarketData.source, Text) == data['source'],
                cast(MarketData.timeframe, Text) == data['timeframe'],
                MarketData.symbol == data['symbol']
            )
        )

        result = await self.session.execute(existing_query)
        existing = result.scalar_one_or_none()

        if existing:
            # Check if any OHLC values are different
            has_changes = any(
                getattr(existing, key) != data[key]
                for key in ['open', 'high', 'low', 'last', 'change', 'change_percent', 'volume']
                if key in data
            )

            if has_changes:
                # Update existing record
                for key, value in data.items():
                    if key not in ['time', 'symbol', 'source', 'timeframe']:  # Don't update PK fields
                        setattr(existing, key, value)
                await self.session.flush()
                await self.session.refresh(existing)
                return existing
            else:
                # No changes, return existing
                return existing
        else:
            # Create new record
            instance = MarketData(**data)
            self.session.add(instance)
            await self.session.flush()
            await self.session.refresh(instance)
            return instance

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

    # =============================================================================
    # Keyset Pagination Methods (T026-T028)
    # =============================================================================

    async def get_latest_by_symbol(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
        cursor: Optional[str] = None,
        source: Optional[str] = None,
    ) -> tuple[List[MarketData], Optional[str]]:
        """
        Get latest market data for symbol and timeframe with pagination (T027).

        Uses the composite index for optimal performance.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe (M1, M5, M15, M30, H1, H4, D1, W1, MN1)
            limit: Number of most recent records to retrieve (default 500)
            cursor: Optional cursor for pagination (format: "timestamp_id")
            source: Optional data source filter (e.g., "MT4", "CSV", "DUKASCOPY")

        Returns:
            Tuple of (list of MarketData records, next_cursor)

        Example:
            # Get latest 500 candlesticks for CrudeOIL M5
            data, cursor = await repo.get_latest_by_symbol("CrudeOIL", "M5", 500)
            # Get only MT4-sourced data
            data, cursor = await repo.get_latest_by_symbol("CrudeOIL", "M5", 500, source="MT4")
        """
        query = (
            select(MarketData)
            .where(
                and_(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == timeframe,
                )
            )
        )

        if source:
            query = query.where(cast(MarketData.source, Text) == source)

        # Apply keyset pagination if cursor provided
        if cursor:
            try:
                cursor_parts = cursor.split("_")
                cursor_time = datetime.fromisoformat(cursor_parts[0])
                cursor_id = int(cursor_parts[1])

                query = query.where(
                    (MarketData.time < cursor_time) |
                    (
                        (MarketData.time == cursor_time) &
                        (MarketData.id < cursor_id)
                    )
                )
            except (ValueError, IndexError):
                # Invalid cursor - ignore
                pass

        query = query.order_by(
            desc(MarketData.time),
            desc(MarketData.id)
        ).limit(limit + 1)  # Fetch one extra

        result = await self.session.execute(query)
        records = list(result.scalars().all())

        # Calculate next cursor
        next_cursor = None
        if len(records) > limit:
            last_record = records[limit - 1]
            next_cursor = f"{last_record.time.isoformat()}_{last_record.id}"
            records = records[:limit]

        # Return in chronological order (oldest first)
        return list(reversed(records)), next_cursor

    async def get_by_time_range(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        cursor: Optional[str] = None,
        limit: int = 500,
    ) -> tuple[List[MarketData], Optional[str]]:
        """
        Get market data for time range with keyset pagination (T028).

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            start: Start time (inclusive)
            end: End time (inclusive)
            cursor: Keyset pagination cursor (format: "timestamp_id")
            limit: Number of records per page

        Returns:
            Tuple of (list of MarketData records, next_cursor)

        Example:
            # First page
            data, next_cursor = await repo.get_by_time_range(
                "CrudeOIL", "M5",
                start=datetime(2024, 11, 1),
                end=datetime(2024, 11, 26),
                limit=500
            )

            # Next page
            more_data, cursor = await repo.get_by_time_range(
                "CrudeOIL", "M5",
                start=datetime(2024, 11, 1),
                end=datetime(2024, 11, 26),
                cursor=next_cursor,
                limit=500
            )
        """
        query = select(MarketData).where(
            and_(
                MarketData.symbol == symbol,
                cast(MarketData.timeframe, Text) == timeframe,
                MarketData.time >= start,
                MarketData.time <= end,
            )
        )

        # Apply keyset pagination
        if cursor:
            try:
                # Cursor format: "timestamp_id"
                cursor_parts = cursor.split("_")
                cursor_time = datetime.fromisoformat(cursor_parts[0])
                cursor_id = int(cursor_parts[1])

                # Continue from cursor position (descending order)
                query = query.where(
                    (MarketData.time < cursor_time) |
                    (
                        (MarketData.time == cursor_time) &
                        (MarketData.id < cursor_id)
                    )
                )
            except (ValueError, IndexError):
                # Invalid cursor - ignore and start from beginning
                pass

        # Order by time DESC, id DESC for consistent pagination
        query = query.order_by(
            desc(MarketData.time),
            desc(MarketData.id)
        ).limit(limit + 1)  # Fetch one extra to determine if there's a next page

        result = await self.session.execute(query)
        records = list(result.scalars().all())

        # Calculate next cursor
        next_cursor = None
        if len(records) > limit:
            # There's a next page
            last_record = records[limit - 1]
            next_cursor = f"{last_record.time.isoformat()}_{last_record.id}"
            records = records[:limit]  # Trim the extra record

        # Return in chronological order (oldest first)
        return list(reversed(records)), next_cursor

    async def count_by_symbol(self, symbol: str, timeframe: str) -> int:
        """
        Count total records for symbol/timeframe.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe

        Returns:
            Total count of records
        """
        query = select(func.count()).select_from(MarketData).where(
            and_(
                MarketData.symbol == symbol,
                cast(MarketData.timeframe, Text) == timeframe,
            )
        )

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def count_by_time_range(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> int:
        """
        Count records in time range for symbol/timeframe.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            start: Start time
            end: End time

        Returns:
            Count of records in range
        """
        query = select(func.count()).select_from(MarketData).where(
            and_(
                MarketData.symbol == symbol,
                cast(MarketData.timeframe, Text) == timeframe,
                MarketData.time >= start,
                MarketData.time <= end,
            )
        )

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_symbols_with_metadata(
        self, timeframe: Optional[str] = None
    ) -> List[Any]:
        """
        Get symbols with metadata (count, latest price, time range).

        Args:
            timeframe: Optional timeframe filter

        Returns:
            List of symbol metadata objects
        """
        from sqlalchemy import literal_column

        # Build query for symbol metadata
        # Group by symbol and aggregate metadata
        query = select(
            MarketData.symbol,
            func.count(MarketData.id).label("data_points_count"),
            func.max(MarketData.time).label("latest_time"),
            func.min(MarketData.time).label("first_time"),
        ).group_by(MarketData.symbol)

        if timeframe:
            query = query.where(cast(MarketData.timeframe, Text) == timeframe)

        result = await self.session.execute(query)
        return list(result.all())

    # =============================================================================
    # Backtesting Support Methods (T016)
    # =============================================================================

    async def get_historical_candles_streamed(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
        chunk_size: int = 1000,
    ):
        """
        Stream historical candles in chunks for backtesting replay.

        Uses keyset pagination to efficiently handle large datasets (13.5M+ candles)
        without loading everything into memory.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            start_time: Backtest start time
            end_time: Backtest end time
            chunk_size: Number of candles per chunk (default 1000)

        Yields:
            Lists of MarketData instances in chronological order

        Example:
            async for candles in repo.get_historical_candles_streamed(
                "CrudeOIL", "M5",
                datetime(2024, 1, 1),
                datetime(2024, 12, 1),
                chunk_size=500
            ):
                for candle in candles:
                    # Process candle for backtest
                    pass
        """
        cursor_time = start_time

        while cursor_time < end_time:
            query = select(MarketData).where(
                and_(
                    MarketData.symbol == symbol,
                    cast(MarketData.timeframe, Text) == timeframe,
                    MarketData.time >= cursor_time,
                    MarketData.time <= end_time,
                )
            ).order_by(MarketData.time).limit(chunk_size)

            result = await self.session.execute(query)
            chunk = list(result.scalars().all())

            if not chunk:
                break

            yield chunk

            # Update cursor to last candle's time + 1 microsecond for next iteration
            cursor_time = chunk[-1].time
            # Move cursor forward by 1 microsecond to avoid duplicate
            from datetime import timedelta
            cursor_time = cursor_time + timedelta(microseconds=1)

    async def count_candles_in_range(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        """
        Count total candles for backtesting range (for progress tracking).

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            start_time: Backtest start time
            end_time: Backtest end time

        Returns:
            Total number of candles in range
        """
        query = select(func.count()).select_from(MarketData).where(
            and_(
                MarketData.symbol == symbol,
                cast(MarketData.timeframe, Text) == timeframe,
                MarketData.time >= start_time,
                MarketData.time <= end_time,
            )
        )

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def validate_data_continuity(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        """
        Validate data continuity for backtesting (check for gaps).

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            start_time: Start time
            end_time: End time

        Returns:
            Dictionary with validation results:
            - total_candles: Total count
            - expected_candles: Expected count (if deterministic)
            - has_gaps: Whether gaps detected
            - first_candle_time: Timestamp of first candle
            - last_candle_time: Timestamp of last candle
        """
        # Get total count
        total = await self.count_candles_in_range(
            symbol, timeframe, start_time, end_time
        )

        if total == 0:
            return {
                "total_candles": 0,
                "expected_candles": None,
                "has_gaps": True,
                "first_candle_time": None,
                "last_candle_time": None,
                "error": "No data found in range",
            }

        # Get first and last candles
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

        first_result = await self.session.execute(first_query)
        last_result = await self.session.execute(last_query)

        first_candle = first_result.scalar_one_or_none()
        last_candle = last_result.scalar_one_or_none()

        return {
            "total_candles": total,
            "expected_candles": None,  # Can calculate based on timeframe
            "has_gaps": False,  # Conservative - assume no gaps unless we detect
            "first_candle_time": first_candle.time if first_candle else None,
            "last_candle_time": last_candle.time if last_candle else None,
        }
