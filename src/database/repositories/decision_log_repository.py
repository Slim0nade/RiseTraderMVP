"""
DecisionLog repository with TimescaleDB-optimized time-series queries.
"""
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.decision_log import DecisionLog
from .base import BaseRepository


class DecisionLogRepository(BaseRepository[DecisionLog]):
    """Repository for DecisionLog model with TimescaleDB time-series queries."""

    def __init__(self, session: AsyncSession):
        """Initialize DecisionLogRepository."""
        super().__init__(DecisionLog, session)

    async def get_by_id(self, decision_id: UUID) -> Optional[DecisionLog]:
        """
        Get decision by UUID.

        Args:
            decision_id: Decision UUID

        Returns:
            DecisionLog instance or None
        """
        query = select(DecisionLog).where(DecisionLog.id == decision_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_agent_id(
        self,
        agent_id: UUID,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[DecisionLog]:
        """
        Get decisions for a specific agent with time range.

        Args:
            agent_id: Agent UUID
            start_time: Optional start timestamp
            end_time: Optional end timestamp
            limit: Maximum results

        Returns:
            List of decision logs
        """
        query = select(DecisionLog).where(DecisionLog.agent_id == agent_id)

        if start_time:
            query = query.where(DecisionLog.decided_at >= start_time)
        if end_time:
            query = query.where(DecisionLog.decided_at <= end_time)

        query = query.order_by(DecisionLog.decided_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_symbol(
        self,
        symbol: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[DecisionLog]:
        """
        Get decisions for a specific symbol with time range.

        Args:
            symbol: Trading symbol
            start_time: Optional start timestamp
            end_time: Optional end timestamp
            limit: Maximum results

        Returns:
            List of decision logs
        """
        query = select(DecisionLog).where(DecisionLog.symbol == symbol)

        if start_time:
            query = query.where(DecisionLog.decided_at >= start_time)
        if end_time:
            query = query.where(DecisionLog.decided_at <= end_time)

        query = query.order_by(DecisionLog.decided_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_strategy_team(
        self,
        strategy_team_id: UUID,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[DecisionLog]:
        """
        Get decisions for a strategy team with time range.

        Args:
            strategy_team_id: Strategy team UUID
            start_time: Optional start timestamp
            end_time: Optional end timestamp
            limit: Maximum results

        Returns:
            List of decision logs
        """
        query = select(DecisionLog).where(DecisionLog.strategy_team_id == strategy_team_id)

        if start_time:
            query = query.where(DecisionLog.decided_at >= start_time)
        if end_time:
            query = query.where(DecisionLog.decided_at <= end_time)

        query = query.order_by(DecisionLog.decided_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_recent_decisions(
        self,
        hours: int = 24,
        decision_type: Optional[str] = None,
        agent_type: Optional[str] = None,
        limit: int = 100
    ) -> List[DecisionLog]:
        """
        Get recent decisions within the last N hours.

        Args:
            hours: Number of hours to look back
            decision_type: Optional decision type filter
            agent_type: Optional agent type filter
            limit: Maximum results

        Returns:
            List of recent decision logs
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        query = select(DecisionLog).where(DecisionLog.decided_at >= cutoff_time)

        if decision_type:
            query = query.where(DecisionLog.decision_type == decision_type)
        if agent_type:
            query = query.where(DecisionLog.agent_type == agent_type)

        query = query.order_by(DecisionLog.decided_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_executed_decisions(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[DecisionLog]:
        """
        Get decisions that led to actual trade execution.

        Args:
            start_time: Optional start timestamp
            end_time: Optional end timestamp
            limit: Maximum results

        Returns:
            List of executed decision logs
        """
        query = select(DecisionLog).where(DecisionLog.was_executed == True)

        if start_time:
            query = query.where(DecisionLog.decided_at >= start_time)
        if end_time:
            query = query.where(DecisionLog.decided_at <= end_time)

        query = query.order_by(DecisionLog.decided_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_decision_count_by_agent(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get decision counts by agent for a time period.

        Args:
            start_time: Start timestamp
            end_time: End timestamp

        Returns:
            List of dicts with agent_type and decision_count
        """
        query = (
            select(
                DecisionLog.agent_type,
                func.count(DecisionLog.id).label('decision_count')
            )
            .where(
                and_(
                    DecisionLog.decided_at >= start_time,
                    DecisionLog.decided_at <= end_time
                )
            )
            .group_by(DecisionLog.agent_type)
            .order_by(func.count(DecisionLog.id).desc())
        )

        result = await self.session.execute(query)
        return [
            {'agent_type': row.agent_type, 'decision_count': row.decision_count}
            for row in result.all()
        ]

    async def get_avg_decision_latency_by_agent(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get average decision latency by agent type.

        Args:
            start_time: Start timestamp
            end_time: End timestamp

        Returns:
            List of dicts with agent_type and avg_latency_ms
        """
        query = (
            select(
                DecisionLog.agent_type,
                func.avg(DecisionLog.decision_latency_ms).label('avg_latency_ms')
            )
            .where(
                and_(
                    DecisionLog.decided_at >= start_time,
                    DecisionLog.decided_at <= end_time,
                    DecisionLog.decision_latency_ms.isnot(None)
                )
            )
            .group_by(DecisionLog.agent_type)
            .order_by(func.avg(DecisionLog.decision_latency_ms))
        )

        result = await self.session.execute(query)
        return [
            {'agent_type': row.agent_type, 'avg_latency_ms': float(row.avg_latency_ms)}
            for row in result.all()
        ]

    async def get_pnl_impact_by_decision_type(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get cumulative P&L impact by decision type.

        Args:
            start_time: Start timestamp
            end_time: End timestamp

        Returns:
            List of dicts with decision_type and total_pnl_impact
        """
        query = (
            select(
                DecisionLog.decision_type,
                func.sum(DecisionLog.pnl_impact).label('total_pnl_impact'),
                func.count(DecisionLog.id).label('decision_count')
            )
            .where(
                and_(
                    DecisionLog.decided_at >= start_time,
                    DecisionLog.decided_at <= end_time,
                    DecisionLog.pnl_impact.isnot(None)
                )
            )
            .group_by(DecisionLog.decision_type)
            .order_by(func.sum(DecisionLog.pnl_impact).desc())
        )

        result = await self.session.execute(query)
        return [
            {
                'decision_type': row.decision_type,
                'total_pnl_impact': float(row.total_pnl_impact) if row.total_pnl_impact else 0.0,
                'decision_count': row.decision_count
            }
            for row in result.all()
        ]

    async def create(self, **kwargs) -> DecisionLog:
        """
        Create a new decision log entry.

        Args:
            **kwargs: DecisionLog fields

        Returns:
            Created decision log
        """
        decision_log = DecisionLog(**kwargs)
        self.session.add(decision_log)
        await self.session.commit()
        await self.session.refresh(decision_log)
        return decision_log

    async def update_execution_result(
        self,
        decision_id: UUID,
        was_executed: bool,
        execution_result: Optional[Dict[str, Any]] = None,
        pnl_impact: Optional[float] = None
    ) -> Optional[DecisionLog]:
        """
        Update decision with execution result.

        Args:
            decision_id: Decision UUID
            was_executed: Whether decision was executed
            execution_result: Optional execution details
            pnl_impact: Optional P&L impact

        Returns:
            Updated decision log or None
        """
        decision = await self.get_by_id(decision_id)
        if not decision:
            return None

        decision.was_executed = was_executed
        if execution_result:
            decision.execution_result = execution_result
        if pnl_impact is not None:
            decision.pnl_impact = pnl_impact

        await self.session.commit()
        await self.session.refresh(decision)
        return decision
