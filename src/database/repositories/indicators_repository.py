"""
Indicators repository for technical indicators queries.
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import and_, cast, desc, select, Text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.indicators import Indicators
from .base import BaseRepository


class IndicatorsRepository(BaseRepository[Indicators]):
    """
    Repository for technical indicators.

    Handles ~70K records of calculated indicators.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(Indicators, session)

    async def get_latest_indicators(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 1,
    ) -> Optional[Indicators]:
        """
        Get the latest indicator values for a symbol and timeframe.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            limit: Number of records (defaults to 1 for most recent)

        Returns:
            Latest Indicators instance or None
        """
        query = (
            select(Indicators)
            .where(
                and_(
                    Indicators.symbol == symbol,
                    cast(Indicators.timeframe, Text) == timeframe,
                )
            )
            .order_by(desc(Indicators.time))
            .limit(limit)
        )

        result = await self.session.execute(query)
        if limit == 1:
            return result.scalar_one_or_none()
        return list(result.scalars().all())

    async def get_indicators_range(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Indicators]:
        """
        Get indicators for a symbol within a time range.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of Indicators instances ordered by time
        """
        query = (
            select(Indicators)
            .where(
                and_(
                    Indicators.symbol == symbol,
                    cast(Indicators.timeframe, Text) == timeframe,
                    Indicators.time >= start_time,
                    Indicators.time <= end_time,
                )
            )
            .order_by(Indicators.time)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_market_data_id(
        self, market_data_id: int
    ) -> Optional[Indicators]:
        """
        Get indicators by market data ID.

        Args:
            market_data_id: Foreign key to market_data table

        Returns:
            Indicators instance or None
        """
        return await self.get_by(market_data_id=market_data_id)

    async def get_rsi_history(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> List[tuple[datetime, float]]:
        """
        Get RSI history for charting.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            limit: Number of records

        Returns:
            List of (time, rsi) tuples
        """
        query = (
            select(Indicators.time, Indicators.rsi)
            .where(
                and_(
                    Indicators.symbol == symbol,
                    cast(Indicators.timeframe, Text) == timeframe,
                    Indicators.rsi.isnot(None),
                )
            )
            .order_by(desc(Indicators.time))
            .limit(limit)
        )

        result = await self.session.execute(query)
        return [(row.time, float(row.rsi)) for row in result.all()]

    async def get_macd_history(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> List[tuple[datetime, float, float]]:
        """
        Get MACD history for charting.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            limit: Number of records

        Returns:
            List of (time, macd, signal) tuples
        """
        query = (
            select(Indicators.time, Indicators.macd, Indicators.macd_signal)
            .where(
                and_(
                    Indicators.symbol == symbol,
                    cast(Indicators.timeframe, Text) == timeframe,
                    Indicators.macd.isnot(None),
                )
            )
            .order_by(desc(Indicators.time))
            .limit(limit)
        )

        result = await self.session.execute(query)
        return [
            (row.time, float(row.macd), float(row.macd_signal))
            for row in result.all()
        ]

    async def get_bollinger_bands(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> List[tuple[datetime, float, float, float]]:
        """
        Get Bollinger Bands history for charting.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            limit: Number of records

        Returns:
            List of (time, upper, middle, lower) tuples
        """
        query = (
            select(
                Indicators.time,
                Indicators.bb_upper,
                Indicators.bb_middle,
                Indicators.bb_lower,
            )
            .where(
                and_(
                    Indicators.symbol == symbol,
                    cast(Indicators.timeframe, Text) == timeframe,
                    Indicators.bb_upper.isnot(None),
                )
            )
            .order_by(desc(Indicators.time))
            .limit(limit)
        )

        result = await self.session.execute(query)
        return [
            (row.time, float(row.bb_upper), float(row.bb_middle), float(row.bb_lower))
            for row in result.all()
        ]

    async def get_moving_averages(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> List[tuple[datetime, Optional[float], Optional[float], Optional[float]]]:
        """
        Get moving averages history for charting.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            limit: Number of records

        Returns:
            List of (time, ma_20, ma_50, ma_200) tuples
        """
        query = (
            select(
                Indicators.time,
                Indicators.ma_20,
                Indicators.ma_50,
                Indicators.ma_200,
            )
            .where(
                and_(
                    Indicators.symbol == symbol,
                    cast(Indicators.timeframe, Text) == timeframe,
                )
            )
            .order_by(desc(Indicators.time))
            .limit(limit)
        )

        result = await self.session.execute(query)
        return [
            (
                row.time,
                float(row.ma_20) if row.ma_20 else None,
                float(row.ma_50) if row.ma_50 else None,
                float(row.ma_200) if row.ma_200 else None,
            )
            for row in result.all()
        ]
