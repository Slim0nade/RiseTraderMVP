"""
Historical data replay engine for backtesting.

Streams market data chronologically with efficient memory management
for large datasets (13.5M+ candles).
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import AsyncGenerator, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.market_data import MarketData
from src.database.repositories.market_data_repository import MarketDataRepository


@dataclass
class MarketTick:
    """
    Simplified market data tick for backtesting.

    Attributes:
        symbol: Trading symbol
        timestamp: Tick timestamp
        open: Open price
        high: High price
        low: Low price
        close: Close price
        volume: Volume
    """

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    @classmethod
    def from_market_data(cls, md: MarketData) -> "MarketTick":
        """
        Create MarketTick from MarketData model.

        Args:
            md: MarketData instance

        Returns:
            MarketTick instance
        """
        return cls(
            symbol=md.symbol,
            timestamp=md.time,
            open=md.open,
            high=md.high,
            low=md.low,
            close=md.last,
            volume=int(md.volume or 0),
        )


class DataReplayEngine:
    """
    Replays historical market data for backtesting.

    Efficiently streams candles from PostgreSQL in chronological order
    using chunked queries to handle large datasets without memory issues.

    Attributes:
        repository: MarketDataRepository for database access
        chunk_size: Number of candles to fetch per database query
    """

    def __init__(
        self,
        repository: MarketDataRepository,
        chunk_size: int = 1000,
    ):
        """
        Initialize data replay engine.

        Args:
            repository: MarketDataRepository instance
            chunk_size: Candles per chunk (default 1000)
        """
        self.repository = repository
        self.chunk_size = chunk_size

    async def replay_historical_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> AsyncGenerator[MarketTick, None]:
        """
        Stream historical market data chronologically.

        Yields candles one-by-one in timestamp order, fetching from database
        in chunks for memory efficiency.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., 'M1', 'M5', 'H1')
            start_date: Backtest start date
            end_date: Backtest end date

        Yields:
            MarketTick instances in chronological order

        Example:
            async for tick in engine.replay_historical_data(
                "CrudeOIL", "M5",
                datetime(2024, 1, 1),
                datetime(2024, 12, 1)
            ):
                # Process tick for backtest
                portfolio.update_market_price(tick.symbol, tick.close)
        """
        async for chunk in self.repository.get_historical_candles_streamed(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_date,
            end_time=end_date,
            chunk_size=self.chunk_size,
        ):
            for candle in chunk:
                yield MarketTick.from_market_data(candle)

    async def get_total_candles(
        self, symbol: str, timeframe: str, start_date: datetime, end_date: datetime
    ) -> int:
        """
        Get total number of candles for progress tracking.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            start_date: Start date
            end_date: End date

        Returns:
            Total candle count
        """
        return await self.repository.count_candles_in_range(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_date,
            end_time=end_date,
        )

    async def validate_data_availability(
        self, symbol: str, timeframe: str, start_date: datetime, end_date: datetime
    ) -> dict:
        """
        Validate that sufficient data exists for backtesting.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            start_date: Desired start date
            end_date: Desired end date

        Returns:
            Dictionary with validation results and statistics
        """
        validation = await self.repository.validate_data_continuity(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_date,
            end_time=end_date,
        )

        # Add recommendation
        if validation["total_candles"] == 0:
            validation["recommendation"] = "No data available. Cannot run backtest."
            validation["can_proceed"] = False
        elif validation["total_candles"] < 100:
            validation[
                "recommendation"
            ] = f"Only {validation['total_candles']} candles available. Consider longer date range."
            validation["can_proceed"] = False
        else:
            validation[
                "recommendation"
            ] = f"{validation['total_candles']} candles available. Ready for backtest."
            validation["can_proceed"] = True

        return validation

    async def get_price_at_timestamp(
        self, symbol: str, timeframe: str, timestamp: datetime
    ) -> Optional[MarketTick]:
        """
        Get the market price at a specific timestamp.

        Useful for initializing portfolio state or checking specific prices.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            timestamp: Target timestamp

        Returns:
            MarketTick at or immediately before timestamp, or None
        """
        candles = await self.repository.get_by_timeframe_range(
            symbol=symbol,
            timeframe=timeframe,
            start_time=timestamp,
            end_time=timestamp,
            limit=1,
        )

        if candles:
            return MarketTick.from_market_data(candles[0])

        # If no exact match, get the closest earlier candle
        from datetime import timedelta

        earlier_candles = await self.repository.get_by_timeframe_range(
            symbol=symbol,
            timeframe=timeframe,
            start_time=timestamp - timedelta(days=1),
            end_time=timestamp,
            limit=1,
        )

        if earlier_candles:
            return MarketTick.from_market_data(earlier_candles[-1])

        return None

    async def replay_with_progress(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        progress_callback: Optional[callable] = None,
    ) -> AsyncGenerator[tuple[MarketTick, int, int], None]:
        """
        Stream historical data with progress tracking.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            start_date: Start date
            end_date: End date
            progress_callback: Optional callback(processed, total) for progress updates

        Yields:
            Tuple of (MarketTick, candles_processed, total_candles)
        """
        total_candles = await self.get_total_candles(
            symbol, timeframe, start_date, end_date
        )

        processed = 0

        async for tick in self.replay_historical_data(
            symbol, timeframe, start_date, end_date
        ):
            processed += 1

            if progress_callback and processed % 100 == 0:
                progress_callback(processed, total_candles)

            yield tick, processed, total_candles
