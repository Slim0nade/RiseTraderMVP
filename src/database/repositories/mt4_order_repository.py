"""
MT4 Order Repository for order lifecycle management.

Handles CRUD operations for MT4 orders with status tracking and querying.
"""
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.mt4_orders import MT4Order
from .base import BaseRepository


class MT4OrderRepository(BaseRepository[MT4Order]):
    """
    Repository for MT4 order management.

    Provides methods for order tracking, status updates, and performance metrics.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize MT4 order repository.

        Args:
            session: Async database session
        """
        super().__init__(MT4Order, session)

    async def get_by_order_id(self, order_id: str) -> Optional[MT4Order]:
        """
        Get order by external order ID.

        Args:
            order_id: External UUID order identifier

        Returns:
            MT4Order instance or None
        """
        query = select(MT4Order).where(MT4Order.order_id == order_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_ticket_number(self, ticket_number: int) -> Optional[MT4Order]:
        """
        Get order by MT4 ticket number.

        Args:
            ticket_number: MT4 ticket number

        Returns:
            MT4Order instance or None
        """
        query = select(MT4Order).where(MT4Order.ticket_number == ticket_number)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_correlation_id(self, correlation_id: str) -> Optional[MT4Order]:
        """
        Get order by correlation ID for tracing.

        Args:
            correlation_id: Correlation UUID

        Returns:
            MT4Order instance or None
        """
        query = select(MT4Order).where(MT4Order.correlation_id == correlation_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_magic_number(
        self,
        magic_number: int,
        limit: int = 100
    ) -> List[MT4Order]:
        """
        Get orders for specific EA (by magic number).

        Args:
            magic_number: MT4 magic number
            limit: Maximum number of orders to return

        Returns:
            List of MT4Order instances
        """
        query = (
            select(MT4Order)
            .where(MT4Order.magic_number == magic_number)
            .order_by(MT4Order.submitted_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_active_orders(
        self,
        magic_number: Optional[int] = None
    ) -> List[MT4Order]:
        """
        Get all active orders (PENDING or CONFIRMED status).

        Args:
            magic_number: Optional filter by EA magic number

        Returns:
            List of active MT4Order instances
        """
        query = select(MT4Order).where(
            MT4Order.status.in_(['PENDING', 'CONFIRMED'])
        )

        if magic_number is not None:
            query = query.where(MT4Order.magic_number == magic_number)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_status(
        self,
        status: str,
        magic_number: Optional[int] = None,
        limit: int = 100
    ) -> List[MT4Order]:
        """
        Get orders by status.

        Args:
            status: Order status (PENDING, CONFIRMED, EXECUTED, REJECTED, CANCELLED)
            magic_number: Optional filter by EA magic number
            limit: Maximum number of orders to return

        Returns:
            List of MT4Order instances
        """
        query = (
            select(MT4Order)
            .where(MT4Order.status == status)
            .order_by(MT4Order.submitted_at.desc())
            .limit(limit)
        )

        if magic_number is not None:
            query = query.where(MT4Order.magic_number == magic_number)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_recent_orders(
        self,
        hours: int = 24,
        magic_number: Optional[int] = None,
        limit: int = 100
    ) -> List[MT4Order]:
        """
        Get recent orders within time window.

        Args:
            hours: Number of hours to look back
            magic_number: Optional filter by EA magic number
            limit: Maximum number of orders to return

        Returns:
            List of MT4Order instances
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        query = (
            select(MT4Order)
            .where(MT4Order.submitted_at >= cutoff_time)
            .order_by(MT4Order.submitted_at.desc())
            .limit(limit)
        )

        if magic_number is not None:
            query = query.where(MT4Order.magic_number == magic_number)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(
        self,
        order_id: str,
        status: str,
        **kwargs
    ) -> Optional[MT4Order]:
        """
        Update order status and related fields.

        Args:
            order_id: External order ID
            status: New status
            **kwargs: Additional fields to update (e.g., ticket_number, execution_price)

        Returns:
            Updated MT4Order instance or None
        """
        values = {
            "status": status,
            "updated_at": datetime.utcnow(),
            **kwargs
        }

        # Set status-specific timestamps
        if status == 'CONFIRMED' and 'confirmed_at' not in kwargs:
            values['confirmed_at'] = datetime.utcnow()
        elif status == 'EXECUTED' and 'executed_at' not in kwargs:
            values['executed_at'] = datetime.utcnow()

        query = (
            update(MT4Order)
            .where(MT4Order.order_id == order_id)
            .values(**values)
            .returning(MT4Order)
        )
        result = await self.session.execute(query)
        await self.session.commit()
        return result.scalar_one_or_none()

    async def update_by_ticket(
        self,
        ticket_number: int,
        **kwargs
    ) -> Optional[MT4Order]:
        """
        Update order by MT4 ticket number.

        Args:
            ticket_number: MT4 ticket number
            **kwargs: Fields to update

        Returns:
            Updated MT4Order instance or None
        """
        values = {
            "updated_at": datetime.utcnow(),
            **kwargs
        }

        query = (
            update(MT4Order)
            .where(MT4Order.ticket_number == ticket_number)
            .values(**values)
            .returning(MT4Order)
        )
        result = await self.session.execute(query)
        await self.session.commit()
        return result.scalar_one_or_none()

    async def count_by_status(
        self,
        status: str,
        magic_number: Optional[int] = None
    ) -> int:
        """
        Count orders by status.

        Args:
            status: Order status
            magic_number: Optional filter by EA magic number

        Returns:
            Count of orders
        """
        query = select(func.count(MT4Order.id)).where(MT4Order.status == status)

        if magic_number is not None:
            query = query.where(MT4Order.magic_number == magic_number)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_average_latency_ms(
        self,
        magic_number: Optional[int] = None,
        hours: int = 24
    ) -> float:
        """
        Calculate average order confirmation latency.

        Args:
            magic_number: Optional filter by EA magic number
            hours: Number of hours to look back

        Returns:
            Average latency in milliseconds
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        query = (
            select(MT4Order)
            .where(
                MT4Order.status.in_(['CONFIRMED', 'EXECUTED']),
                MT4Order.confirmed_at.isnot(None),
                MT4Order.submitted_at >= cutoff_time
            )
        )

        if magic_number is not None:
            query = query.where(MT4Order.magic_number == magic_number)

        result = await self.session.execute(query)
        orders = list(result.scalars().all())

        if not orders:
            return 0.0

        latencies = [order.calculate_latency_ms() for order in orders]
        latencies = [l for l in latencies if l is not None]

        if not latencies:
            return 0.0

        return sum(latencies) / len(latencies)

    async def get_success_rate(
        self,
        magic_number: Optional[int] = None,
        hours: int = 24
    ) -> float:
        """
        Calculate order success rate (EXECUTED / total).

        Args:
            magic_number: Optional filter by EA magic number
            hours: Number of hours to look back

        Returns:
            Success rate as percentage (0-100)
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        query = select(MT4Order).where(MT4Order.submitted_at >= cutoff_time)

        if magic_number is not None:
            query = query.where(MT4Order.magic_number == magic_number)

        result = await self.session.execute(query)
        orders = list(result.scalars().all())

        if not orders:
            return 0.0

        executed_count = sum(1 for o in orders if o.status == 'EXECUTED')
        return (executed_count / len(orders)) * 100

    async def get_order_statistics(
        self,
        magic_number: Optional[int] = None,
        hours: int = 24
    ) -> dict:
        """
        Get comprehensive order statistics.

        Args:
            magic_number: Optional filter by EA magic number
            hours: Number of hours to look back

        Returns:
            Dictionary with order statistics
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        query = select(MT4Order).where(MT4Order.submitted_at >= cutoff_time)

        if magic_number is not None:
            query = query.where(MT4Order.magic_number == magic_number)

        result = await self.session.execute(query)
        orders = list(result.scalars().all())

        stats = {
            "total": len(orders),
            "pending": 0,
            "confirmed": 0,
            "executed": 0,
            "rejected": 0,
            "cancelled": 0,
            "success_rate": 0.0,
            "average_latency_ms": 0.0,
        }

        for order in orders:
            stats[order.status.lower()] = stats.get(order.status.lower(), 0) + 1

        if orders:
            executed_count = stats["executed"]
            stats["success_rate"] = (executed_count / len(orders)) * 100

            latencies = [o.calculate_latency_ms() for o in orders if o.calculate_latency_ms() is not None]
            if latencies:
                stats["average_latency_ms"] = sum(latencies) / len(latencies)

        return stats
