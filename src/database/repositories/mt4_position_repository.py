"""
MT4 Position Repository for open positions management.

Handles persistence and queries for MT4Position model.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import uuid

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.mt4_positions import MT4Position
from .base import BaseRepository


class MT4PositionRepository(BaseRepository[MT4Position]):
    """
    Repository for MT4 open positions management.

    Handles CRUD operations for active positions with real-time P&L tracking.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(MT4Position, session)

    async def get_by_ticket_number(
        self,
        ticket_number: int
    ) -> Optional[MT4Position]:
        """
        Get position by MT4 ticket number.

        Args:
            ticket_number: MT4 position ticket

        Returns:
            MT4Position instance or None
        """
        query = select(MT4Position).where(
            MT4Position.ticket_number == ticket_number
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_magic_number(
        self,
        magic_number: int
    ) -> List[MT4Position]:
        """
        Get all positions for a magic number (EA).

        Args:
            magic_number: MT4 magic number

        Returns:
            List of MT4Position instances
        """
        query = select(MT4Position).where(
            MT4Position.magic_number == magic_number
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_symbol(
        self,
        symbol: str,
        magic_number: Optional[int] = None
    ) -> List[MT4Position]:
        """
        Get all positions for a symbol.

        Args:
            symbol: Trading symbol
            magic_number: Optional filter by magic number

        Returns:
            List of MT4Position instances
        """
        query = select(MT4Position).where(MT4Position.symbol == symbol)

        if magic_number is not None:
            query = query.where(MT4Position.magic_number == magic_number)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_all_open_positions(
        self,
        magic_number: Optional[int] = None
    ) -> List[MT4Position]:
        """
        Get all open positions.

        Args:
            magic_number: Optional filter by magic number

        Returns:
            List of MT4Position instances
        """
        query = select(MT4Position)

        if magic_number is not None:
            query = query.where(MT4Position.magic_number == magic_number)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def upsert_position(
        self,
        ticket_number: int,
        magic_number: int,
        symbol: str,
        direction: str,
        volume: Decimal,
        open_price: Decimal,
        current_price: Decimal,
        unrealized_pnl: Decimal,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        open_time: Optional[datetime] = None,
        last_updated: Optional[datetime] = None,
        order_id: Optional[uuid.UUID] = None
    ) -> MT4Position:
        """
        Insert or update position.

        If position with ticket_number exists, updates it.
        Otherwise, creates new position.

        Args:
            ticket_number: MT4 position ticket
            magic_number: MT4 magic number
            symbol: Trading symbol
            direction: Position direction (BUY or SELL)
            volume: Position size in lots
            open_price: Position open price
            current_price: Current market price
            unrealized_pnl: Current unrealized P&L
            stop_loss: Optional stop loss level
            take_profit: Optional take profit level
            open_time: Optional position open time (defaults to now)
            last_updated: Optional last update time (defaults to now)
            order_id: Optional reference to MT4Order

        Returns:
            MT4Position instance
        """
        # Check if position exists
        existing = await self.get_by_ticket_number(ticket_number)

        if existing:
            # Update existing position
            existing.current_price = current_price
            existing.unrealized_pnl = unrealized_pnl
            existing.stop_loss = stop_loss
            existing.take_profit = take_profit
            existing.last_updated = last_updated or datetime.utcnow()

            await self.session.commit()
            await self.session.refresh(existing)
            return existing
        else:
            # Create new position
            position = MT4Position(
                ticket_number=ticket_number,
                magic_number=magic_number,
                symbol=symbol,
                direction=direction,
                volume=volume,
                open_price=open_price,
                current_price=current_price,
                unrealized_pnl=unrealized_pnl,
                stop_loss=stop_loss,
                take_profit=take_profit,
                open_time=open_time or datetime.utcnow(),
                last_updated=last_updated or datetime.utcnow(),
                order_id=order_id
            )

            self.session.add(position)
            await self.session.commit()
            await self.session.refresh(position)
            return position

    async def delete_position(self, ticket_number: int) -> bool:
        """
        Delete position by ticket number.

        Args:
            ticket_number: MT4 position ticket

        Returns:
            True if deleted, False if not found
        """
        position = await self.get_by_ticket_number(ticket_number)
        if position:
            await self.session.delete(position)
            await self.session.commit()
            return True
        return False

    async def get_total_unrealized_pnl(
        self,
        magic_number: Optional[int] = None
    ) -> Decimal:
        """
        Calculate total unrealized P&L across all positions.

        Args:
            magic_number: Optional filter by magic number

        Returns:
            Total unrealized P&L
        """
        positions = await self.get_all_open_positions(magic_number)
        return sum(p.unrealized_pnl for p in positions)

    async def get_positions_by_direction(
        self,
        direction: str,
        magic_number: Optional[int] = None
    ) -> List[MT4Position]:
        """
        Get positions by direction (BUY or SELL).

        Args:
            direction: Position direction (BUY or SELL)
            magic_number: Optional filter by magic number

        Returns:
            List of MT4Position instances
        """
        query = select(MT4Position).where(MT4Position.direction == direction)

        if magic_number is not None:
            query = query.where(MT4Position.magic_number == magic_number)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_positions(
        self,
        symbol: Optional[str] = None,
        magic_number: Optional[int] = None
    ) -> int:
        """
        Count open positions.

        Args:
            symbol: Optional filter by symbol
            magic_number: Optional filter by magic number

        Returns:
            Number of open positions
        """
        positions = await self.get_all_open_positions(magic_number)

        if symbol:
            positions = [p for p in positions if p.symbol == symbol]

        return len(positions)
