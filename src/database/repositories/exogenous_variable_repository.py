"""
ExogenousVariableRepository - Data access layer for exogenous variables.

Provides CRUD operations and time-alignment queries for external market indicators
(DXY, VIX) and news events.
"""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, insert, delete, update
from datetime import datetime
import logging

from src.database.models.exogenous_variables import ExogenousVariable


logger = logging.getLogger(__name__)


class ExogenousVariableRepository:
    """
    Repository for exogenous variable database operations.

    Supports:
    - CRUD operations for exogenous variables
    - Time-alignment queries for joining with OHLCV data
    - Bulk insert operations for efficiency
    - Symbol and type filtering
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize ExogenousVariableRepository.

        Args:
            session: AsyncSession for database operations
        """
        self.session = session

    async def create(
        self,
        symbol: str,
        timestamp: datetime,
        variable_type: str,
        value: float,
        source: str = 'yfinance'
    ) -> ExogenousVariable:
        """
        Create a new exogenous variable record.

        Args:
            symbol: Variable symbol (e.g., 'DXY', 'VIX')
            timestamp: Timestamp of the data point
            variable_type: Type of variable ('market_indicator', 'news_event')
            value: Variable value
            source: Data source identifier

        Returns:
            Created ExogenousVariable instance
        """
        variable = ExogenousVariable(
            symbol=symbol,
            timestamp=timestamp,
            variable_type=variable_type,
            value=value,
            source=source
        )

        self.session.add(variable)
        await self.session.commit()
        await self.session.refresh(variable)

        logger.debug(f"Created exogenous variable: {symbol} at {timestamp}")
        return variable

    async def bulk_create(self, data_list: List[dict]) -> None:
        """
        Bulk insert exogenous variable records.

        Args:
            data_list: List of dicts with keys: symbol, timestamp, variable_type, value, source

        Example:
            await repo.bulk_create([
                {'symbol': 'DXY', 'timestamp': dt1, 'variable_type': 'market_indicator', 'value': 102.5, 'source': 'yfinance'},
                {'symbol': 'DXY', 'timestamp': dt2, 'variable_type': 'market_indicator', 'value': 103.0, 'source': 'yfinance'}
            ])
        """
        if not data_list:
            return

        # Use bulk insert for performance
        stmt = insert(ExogenousVariable).values(data_list)
        await self.session.execute(stmt)
        await self.session.commit()

        logger.info(f"Bulk inserted {len(data_list)} exogenous variable records")

    async def get_by_id(self, variable_id: int) -> Optional[ExogenousVariable]:
        """
        Get exogenous variable by ID.

        Args:
            variable_id: Variable ID

        Returns:
            ExogenousVariable instance or None if not found
        """
        stmt = select(ExogenousVariable).where(ExogenousVariable.id == variable_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_symbol_and_daterange(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[ExogenousVariable]:
        """
        Get exogenous variables for a symbol within a date range.

        Args:
            symbol: Variable symbol (e.g., 'DXY', 'VIX')
            start_date: Start datetime (inclusive)
            end_date: End datetime (inclusive)

        Returns:
            List of ExogenousVariable instances ordered by timestamp
        """
        stmt = (
            select(ExogenousVariable)
            .where(
                and_(
                    ExogenousVariable.symbol == symbol,
                    ExogenousVariable.timestamp >= start_date,
                    ExogenousVariable.timestamp <= end_date
                )
            )
            .order_by(ExogenousVariable.timestamp)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_symbol_and_type(
        self,
        symbol: str,
        variable_type: str
    ) -> List[ExogenousVariable]:
        """
        Get exogenous variables by symbol and type.

        Args:
            symbol: Variable symbol
            variable_type: Type of variable ('market_indicator', 'news_event')

        Returns:
            List of ExogenousVariable instances
        """
        stmt = (
            select(ExogenousVariable)
            .where(
                and_(
                    ExogenousVariable.symbol == symbol,
                    ExogenousVariable.variable_type == variable_type
                )
            )
            .order_by(ExogenousVariable.timestamp)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_aligned_with_timestamps(
        self,
        symbol: str,
        timestamps: List[datetime]
    ) -> List[ExogenousVariable]:
        """
        Get exogenous variables aligned with specific timestamps.

        Uses nearest timestamp matching for time-alignment with OHLCV data.
        This method is critical for feature engineering.

        Args:
            symbol: Variable symbol
            timestamps: List of timestamps to align with

        Returns:
            List of ExogenousVariable instances matching the timestamps
        """
        stmt = (
            select(ExogenousVariable)
            .where(
                and_(
                    ExogenousVariable.symbol == symbol,
                    ExogenousVariable.timestamp.in_(timestamps)
                )
            )
            .order_by(ExogenousVariable.timestamp)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_id(self, variable_id: int) -> bool:
        """
        Delete exogenous variable by ID.

        Args:
            variable_id: Variable ID

        Returns:
            True if deleted, False if not found
        """
        variable = await self.get_by_id(variable_id)

        if not variable:
            return False

        await self.session.delete(variable)
        await self.session.commit()

        logger.debug(f"Deleted exogenous variable ID: {variable_id}")
        return True

    async def update_value(
        self,
        variable_id: int,
        new_value: float
    ) -> Optional[ExogenousVariable]:
        """
        Update exogenous variable value.

        Args:
            variable_id: Variable ID
            new_value: New value

        Returns:
            Updated ExogenousVariable or None if not found
        """
        variable = await self.get_by_id(variable_id)

        if not variable:
            return None

        variable.value = new_value
        await self.session.commit()
        await self.session.refresh(variable)

        return variable

    async def count_by_symbol(self, symbol: str) -> int:
        """
        Count exogenous variable records for a symbol.

        Args:
            symbol: Variable symbol

        Returns:
            Count of records
        """
        stmt = (
            select(func.count(ExogenousVariable.id))
            .where(ExogenousVariable.symbol == symbol)
        )

        result = await self.session.execute(stmt)
        return result.scalar()

    async def get_latest_by_symbol(
        self,
        symbol: str,
        limit: int = 1
    ) -> List[ExogenousVariable]:
        """
        Get latest exogenous variable records for a symbol.

        Args:
            symbol: Variable symbol
            limit: Number of latest records to return

        Returns:
            List of latest ExogenousVariable instances
        """
        stmt = (
            select(ExogenousVariable)
            .where(ExogenousVariable.symbol == symbol)
            .order_by(ExogenousVariable.timestamp.desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_symbol_and_daterange(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> int:
        """
        Delete exogenous variables for a symbol within a date range.

        Useful for data cleanup or re-fetching historical data.

        Args:
            symbol: Variable symbol
            start_date: Start datetime
            end_date: End datetime

        Returns:
            Number of deleted records
        """
        stmt = (
            delete(ExogenousVariable)
            .where(
                and_(
                    ExogenousVariable.symbol == symbol,
                    ExogenousVariable.timestamp >= start_date,
                    ExogenousVariable.timestamp <= end_date
                )
            )
        )

        result = await self.session.execute(stmt)
        await self.session.commit()

        deleted_count = result.rowcount
        logger.info(f"Deleted {deleted_count} {symbol} records from {start_date} to {end_date}")
        return deleted_count
