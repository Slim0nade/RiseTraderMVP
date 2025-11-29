"""
Strategy repository for trading strategy management.

Handles database operations for strategies, allocations, and performance records.
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models.strategy import (
    Strategy,
    StrategyAllocation,
    StrategyPerformance,
    StrategyStatus,
    PerformancePeriod,
)
from .base import BaseRepository


class StrategyRepository(BaseRepository[Strategy]):
    """
    Repository for trading strategy operations.

    Manages strategies, capital allocations, and performance metrics with
    efficient querying and relationship loading.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(Strategy, session)

    async def get_all_strategies(
        self,
        status_filter: Optional[StrategyStatus] = None
    ) -> List[Strategy]:
        """
        Get all strategies, optionally filtered by status.

        Args:
            status_filter: Optional status to filter by (ACTIVE, PAUSED, DISABLED)

        Returns:
            List of Strategy instances
        """
        query = select(Strategy).order_by(desc(Strategy.created_at))

        if status_filter:
            query = query.where(Strategy.status == status_filter)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_strategy_by_id(
        self,
        strategy_id: int,
        load_allocations: bool = False,
        load_performance: bool = False
    ) -> Optional[Strategy]:
        """
        Get a strategy by ID with optional relationship loading.

        Args:
            strategy_id: Strategy ID
            load_allocations: Whether to load allocation history
            load_performance: Whether to load performance records

        Returns:
            Strategy instance or None if not found
        """
        query = select(Strategy).where(Strategy.id == strategy_id)

        if load_allocations:
            query = query.options(selectinload(Strategy.allocations))

        if load_performance:
            query = query.options(selectinload(Strategy.performance_records))

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_strategy_allocations(
        self,
        strategy_id: int
    ) -> List[StrategyAllocation]:
        """
        Get allocation history for a strategy.

        Returns allocations ordered by date (most recent first).

        Args:
            strategy_id: Strategy ID

        Returns:
            List of StrategyAllocation instances
        """
        query = (
            select(StrategyAllocation)
            .where(StrategyAllocation.strategy_id == strategy_id)
            .order_by(desc(StrategyAllocation.allocation_date))
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_strategy_performance(
        self,
        strategy_id: int,
        period: Optional[str] = None
    ) -> Optional[StrategyPerformance]:
        """
        Get performance metrics for a strategy.

        If period is specified, returns performance for that specific period.
        If period is None, returns the most recent performance record.

        Args:
            strategy_id: Strategy ID
            period: Performance period (daily, weekly, monthly, all_time)

        Returns:
            StrategyPerformance instance or None
        """
        query = (
            select(StrategyPerformance)
            .where(StrategyPerformance.strategy_id == strategy_id)
        )

        if period:
            query = query.where(StrategyPerformance.period == period)

        # Order by period_end DESC to get most recent
        query = query.order_by(desc(StrategyPerformance.period_end))

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_performance_by_period(
        self,
        strategy_id: int,
        period: PerformancePeriod
    ) -> List[StrategyPerformance]:
        """
        Get all performance records for a strategy by period type.

        Args:
            strategy_id: Strategy ID
            period: Performance period enum

        Returns:
            List of StrategyPerformance instances
        """
        query = (
            select(StrategyPerformance)
            .where(
                and_(
                    StrategyPerformance.strategy_id == strategy_id,
                    StrategyPerformance.period == period
                )
            )
            .order_by(desc(StrategyPerformance.period_start))
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_strategy(self, strategy: Strategy) -> Strategy:
        """
        Create a new strategy.

        Args:
            strategy: Strategy instance to create

        Returns:
            Created Strategy instance with ID
        """
        self.session.add(strategy)
        await self.session.flush()
        await self.session.refresh(strategy)
        return strategy

    async def update_strategy(self, strategy: Strategy) -> Strategy:
        """
        Update an existing strategy.

        Args:
            strategy: Strategy instance with updates

        Returns:
            Updated Strategy instance
        """
        await self.session.flush()
        await self.session.refresh(strategy)
        return strategy

    async def add_allocation(
        self,
        allocation: StrategyAllocation
    ) -> StrategyAllocation:
        """
        Add a new allocation record for a strategy.

        Args:
            allocation: StrategyAllocation instance

        Returns:
            Created StrategyAllocation with ID
        """
        self.session.add(allocation)
        await self.session.flush()
        await self.session.refresh(allocation)
        return allocation

    async def add_performance_record(
        self,
        performance: StrategyPerformance
    ) -> StrategyPerformance:
        """
        Add a new performance record for a strategy.

        Args:
            performance: StrategyPerformance instance

        Returns:
            Created StrategyPerformance with ID
        """
        self.session.add(performance)
        await self.session.flush()
        await self.session.refresh(performance)
        return performance

    async def get_active_strategies(self) -> List[Strategy]:
        """
        Get all active strategies.

        Returns:
            List of active Strategy instances
        """
        return await self.get_all_strategies(status_filter=StrategyStatus.ACTIVE)

    async def get_strategies_by_capital_range(
        self,
        min_capital: float,
        max_capital: float
    ) -> List[Strategy]:
        """
        Get strategies within a capital allocation range.

        Args:
            min_capital: Minimum allocated capital
            max_capital: Maximum allocated capital

        Returns:
            List of Strategy instances
        """
        query = (
            select(Strategy)
            .where(
                and_(
                    Strategy.allocated_capital >= min_capital,
                    Strategy.allocated_capital <= max_capital
                )
            )
            .order_by(desc(Strategy.allocated_capital))
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())
