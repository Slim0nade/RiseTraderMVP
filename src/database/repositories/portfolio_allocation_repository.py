"""
PortfolioAllocation repository for capital allocation management.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.portfolio_allocation import PortfolioAllocation
from .base import BaseRepository


class PortfolioAllocationRepository(BaseRepository[PortfolioAllocation]):
    """Repository for PortfolioAllocation model operations."""

    def __init__(self, session: AsyncSession):
        """Initialize PortfolioAllocationRepository."""
        super().__init__(PortfolioAllocation, session)

    async def get_by_id(self, allocation_id: UUID) -> Optional[PortfolioAllocation]:
        """Get allocation by UUID."""
        query = select(PortfolioAllocation).where(PortfolioAllocation.id == allocation_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_strategy_team(
        self,
        strategy_team_id: UUID,
        is_active: Optional[bool] = True
    ) -> List[PortfolioAllocation]:
        """Get allocations for a strategy team."""
        query = select(PortfolioAllocation).where(
            PortfolioAllocation.strategy_team_id == strategy_team_id
        )

        if is_active is not None:
            query = query.where(PortfolioAllocation.is_active == is_active)

        query = query.order_by(PortfolioAllocation.effective_from.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_active_allocations(self) -> List[PortfolioAllocation]:
        """Get all currently active allocations."""
        now = datetime.utcnow()
        query = select(PortfolioAllocation).where(
            and_(
                PortfolioAllocation.is_active == True,
                PortfolioAllocation.effective_from <= now,
                (PortfolioAllocation.effective_until.is_(None)) |
                (PortfolioAllocation.effective_until >= now)
            )
        ).order_by(PortfolioAllocation.allocated_percentage.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_allocations_due_for_rebalance(self) -> List[PortfolioAllocation]:
        """Get allocations that are due for rebalancing."""
        now = datetime.utcnow()
        query = select(PortfolioAllocation).where(
            and_(
                PortfolioAllocation.is_active == True,
                PortfolioAllocation.next_rebalance_at <= now
            )
        ).order_by(PortfolioAllocation.next_rebalance_at)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_total_allocated_capital(self) -> float:
        """Get total allocated capital across all active allocations."""
        query = select(func.sum(PortfolioAllocation.allocated_capital_usd)).where(
            PortfolioAllocation.is_active == True
        )
        result = await self.session.execute(query)
        total = result.scalar_one_or_none()
        return float(total) if total else 0.0

    async def create(self, **kwargs) -> PortfolioAllocation:
        """Create a new allocation."""
        allocation = PortfolioAllocation(**kwargs)
        self.session.add(allocation)
        await self.session.commit()
        await self.session.refresh(allocation)
        return allocation

    async def update_pnl(
        self,
        allocation_id: UUID,
        realized_pnl_usd: Optional[float] = None,
        unrealized_pnl_usd: Optional[float] = None
    ) -> Optional[PortfolioAllocation]:
        """Update P&L for an allocation."""
        allocation = await self.get_by_id(allocation_id)
        if not allocation:
            return None

        if realized_pnl_usd is not None:
            allocation.realized_pnl_usd = realized_pnl_usd
        if unrealized_pnl_usd is not None:
            allocation.unrealized_pnl_usd = unrealized_pnl_usd

        # Update current capital
        total_pnl = (realized_pnl_usd or 0.0) + (unrealized_pnl_usd or 0.0)
        allocation.current_capital_usd = allocation.allocated_capital_usd + total_pnl

        await self.session.commit()
        await self.session.refresh(allocation)
        return allocation
