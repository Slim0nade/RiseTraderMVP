"""
Positions repository for open positions management.
"""
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.positions import OpenPosition
from .base import BaseRepository


class PositionsRepository(BaseRepository[OpenPosition]):
    """
    Repository for open positions management.

    Handles ~1,130 active positions.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(OpenPosition, session)

    async def get_open_positions(
        self,
        simulation: Optional[bool] = None,
    ) -> List[OpenPosition]:
        """
        Get all open positions.

        Args:
            simulation: Filter by simulation flag (None = all)

        Returns:
            List of OpenPosition instances
        """
        query = select(OpenPosition)

        if simulation is not None:
            query = query.where(OpenPosition.simulation == simulation)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_position_by_number(
        self, number: str
    ) -> Optional[OpenPosition]:
        """
        Get position by order number.

        Args:
            number: Order number (unique identifier)

        Returns:
            OpenPosition instance or None
        """
        return await self.get_by(number=number)

    async def get_positions_by_symbol(
        self,
        symbol: str,
        simulation: Optional[bool] = None,
    ) -> List[OpenPosition]:
        """
        Get all open positions for a symbol.

        Args:
            symbol: Trading symbol
            simulation: Filter by simulation flag

        Returns:
            List of OpenPosition instances
        """
        query = select(OpenPosition).where(OpenPosition.symbol == symbol)

        if simulation is not None:
            query = query.where(OpenPosition.simulation == simulation)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_positions_by_strategy(
        self, strategy: str
    ) -> List[OpenPosition]:
        """
        Get positions by strategy name.

        Args:
            strategy: Strategy name

        Returns:
            List of OpenPosition instances
        """
        return await self.get_many_by(last_strategy=strategy)

    async def close_position(self, position_id: int) -> bool:
        """
        Close (delete) a position.

        Args:
            position_id: Position ID

        Returns:
            True if closed, False if not found
        """
        return await self.delete(position_id)

    async def close_position_by_number(self, number: str) -> bool:
        """
        Close position by order number.

        Args:
            number: Order number

        Returns:
            True if closed, False if not found
        """
        position = await self.get_position_by_number(number)
        if position:
            return await self.delete(position.id)
        return False

    async def get_total_exposure(
        self,
        symbol: Optional[str] = None,
        simulation: Optional[bool] = None,
    ) -> Decimal:
        """
        Calculate total position exposure.

        Args:
            symbol: Optional symbol filter
            simulation: Optional simulation filter

        Returns:
            Total exposure (sum of position sizes * prices)
        """
        query = select(
            func.sum(OpenPosition.size * OpenPosition.price)
        ).select_from(OpenPosition)

        if symbol:
            query = query.where(OpenPosition.symbol == symbol)

        if simulation is not None:
            query = query.where(OpenPosition.simulation == simulation)

        result = await self.session.execute(query)
        total = result.scalar()
        return Decimal(total) if total else Decimal(0)

    async def get_position_summary(
        self, simulation: Optional[bool] = None
    ) -> Dict[str, any]:
        """
        Get summary statistics of open positions.

        Args:
            simulation: Optional simulation filter

        Returns:
            Dictionary with position statistics
        """
        query = select(OpenPosition)

        if simulation is not None:
            query = query.where(OpenPosition.simulation == simulation)

        result = await self.session.execute(query)
        positions = list(result.scalars().all())

        if not positions:
            return {
                "total_positions": 0,
                "total_long": 0,
                "total_short": 0,
                "total_profit": 0.0,
                "symbols": [],
            }

        total_long = sum(1 for p in positions if p.is_long)
        total_short = sum(1 for p in positions if p.is_short)
        total_profit = sum(
            float(p.last_profit) for p in positions if p.last_profit
        )
        symbols = list(set(p.symbol for p in positions))

        return {
            "total_positions": len(positions),
            "total_long": total_long,
            "total_short": total_short,
            "total_profit": total_profit,
            "symbols": symbols,
        }

    async def get_positions_by_type(
        self,
        position_type: str,
        simulation: Optional[bool] = None,
    ) -> List[OpenPosition]:
        """
        Get positions by type (BUY or SELL).

        Args:
            position_type: 'BUY' or 'SELL'
            simulation: Optional simulation filter

        Returns:
            List of OpenPosition instances
        """
        query = select(OpenPosition).where(
            OpenPosition.type == position_type.upper()
        )

        if simulation is not None:
            query = query.where(OpenPosition.simulation == simulation)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_positions_by_symbol(
        self, symbol: str, simulation: Optional[bool] = None
    ) -> int:
        """
        Count open positions for a symbol.

        Args:
            symbol: Trading symbol
            simulation: Optional simulation filter

        Returns:
            Number of open positions
        """
        query = select(func.count()).select_from(OpenPosition).where(
            OpenPosition.symbol == symbol
        )

        if simulation is not None:
            query = query.where(OpenPosition.simulation == simulation)

        result = await self.session.execute(query)
        return result.scalar() or 0
