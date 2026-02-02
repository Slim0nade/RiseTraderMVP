"""
Repository for optimization run entities.

Handles CRUD operations for OptimizationRun and PriceAlert models.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.optimization import (
    OptimizationRun,
    OptimizationStatus,
    PriceAlert,
    AlertType,
    AlertDirection,
)
from .base import BaseRepository


class OptimizationRepository(BaseRepository[OptimizationRun]):
    """
    Repository for optimization runs and price alerts.

    Provides specialized queries for optimization history, results retrieval,
    and price alert management.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(OptimizationRun, session)

    # =============================================================================
    # OptimizationRun Operations
    # =============================================================================

    async def get_by_job_id(self, job_id: str) -> Optional[OptimizationRun]:
        """
        Get optimization run by Redis job ID.

        Args:
            job_id: The Redis job ID

        Returns:
            OptimizationRun or None if not found
        """
        query = select(OptimizationRun).where(OptimizationRun.job_id == job_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_run(
        self,
        job_id: str,
        strategy: str,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        param_grid: Dict[str, List[Any]],
        total_combinations: int,
        optimization_target: str = "sharpe_ratio",
        initial_capital: float = 10000.0,
    ) -> OptimizationRun:
        """
        Create a new optimization run record.

        Args:
            job_id: Redis job ID for correlation
            strategy: Strategy name
            symbol: Trading symbol
            timeframe: Candle timeframe
            start_date: Optimization period start
            end_date: Optimization period end
            param_grid: Parameter grid being tested
            total_combinations: Total combinations to test
            optimization_target: Target metric
            initial_capital: Starting capital

        Returns:
            Created OptimizationRun instance
        """
        run = OptimizationRun(
            job_id=job_id,
            strategy=strategy,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            param_grid=param_grid,
            total_combinations=total_combinations,
            optimization_target=optimization_target,
            initial_capital=Decimal(str(initial_capital)),
            status=OptimizationStatus.PENDING.value,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def update_status(
        self,
        job_id: str,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Update the status of an optimization run.

        Args:
            job_id: Redis job ID
            status: New status
            started_at: When execution started
            completed_at: When execution completed
            error_message: Error details if failed
        """
        values = {"status": status}
        if started_at:
            values["started_at"] = started_at
        if completed_at:
            values["completed_at"] = completed_at
        if error_message:
            values["error_message"] = error_message

        stmt = (
            update(OptimizationRun)
            .where(OptimizationRun.job_id == job_id)
            .values(**values)
        )
        await self.session.execute(stmt)

    async def save_results(
        self,
        job_id: str,
        results: Dict[str, Any],
        best_params: Dict[str, Any],
        best_metric_value: float,
        combinations_tested: int,
    ) -> None:
        """
        Save optimization results to database.

        Args:
            job_id: Redis job ID
            results: Full results including all tested combinations
            best_params: Best performing parameters
            best_metric_value: Best metric value achieved
            combinations_tested: Number of combinations tested
        """
        stmt = (
            update(OptimizationRun)
            .where(OptimizationRun.job_id == job_id)
            .values(
                results=results,
                best_params=best_params,
                best_metric_value=Decimal(str(best_metric_value)),
                combinations_tested=combinations_tested,
                status=OptimizationStatus.COMPLETED.value,
                completed_at=datetime.now(timezone.utc),
            )
        )
        await self.session.execute(stmt)

    async def list_runs(
        self,
        strategy: Optional[str] = None,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[OptimizationRun]:
        """
        List optimization runs with optional filtering.

        Args:
            strategy: Filter by strategy name
            symbol: Filter by trading symbol
            status: Filter by status
            limit: Maximum results to return
            offset: Offset for pagination

        Returns:
            List of OptimizationRun instances
        """
        query = select(OptimizationRun)

        conditions = []
        if strategy:
            conditions.append(OptimizationRun.strategy == strategy)
        if symbol:
            conditions.append(OptimizationRun.symbol == symbol)
        if status:
            conditions.append(OptimizationRun.status == status)

        if conditions:
            query = query.where(and_(*conditions))

        query = (
            query
            .order_by(desc(OptimizationRun.created_at))
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_run_with_results(self, run_id: UUID) -> Optional[OptimizationRun]:
        """
        Get optimization run by ID with full results.

        Args:
            run_id: Optimization run UUID

        Returns:
            OptimizationRun or None
        """
        query = select(OptimizationRun).where(OptimizationRun.id == run_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_old_runs(self, days: int = 90) -> int:
        """
        Delete optimization runs older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Number of deleted runs
        """
        from sqlalchemy import delete

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = delete(OptimizationRun).where(OptimizationRun.created_at < cutoff)
        result = await self.session.execute(stmt)
        return result.rowcount

    # =============================================================================
    # PriceAlert Operations
    # =============================================================================

    async def create_alert(
        self,
        ticket: int,
        alert_type: str,
        price_level: float,
        direction: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PriceAlert:
        """
        Create a new price alert.

        Args:
            ticket: MT4 position ticket number
            alert_type: Type of alert (liquidity_sweep, breakeven, etc.)
            price_level: Price to monitor
            direction: Trigger direction (above/below)
            metadata: Additional alert data

        Returns:
            Created PriceAlert instance
        """
        alert = PriceAlert(
            ticket=ticket,
            alert_type=alert_type,
            price_level=Decimal(str(price_level)),
            direction=direction,
            alert_data=metadata or {},  # Maps API 'metadata' param to model's 'alert_data' column
        )
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def get_active_alerts(self, ticket: Optional[int] = None) -> List[PriceAlert]:
        """
        Get active (untriggered) price alerts.

        Args:
            ticket: Optional filter by position ticket

        Returns:
            List of active PriceAlert instances
        """
        query = select(PriceAlert).where(PriceAlert.triggered == False)

        if ticket is not None:
            query = query.where(PriceAlert.ticket == ticket)

        query = query.order_by(PriceAlert.created_at)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def trigger_alert(self, alert_id: UUID) -> None:
        """
        Mark an alert as triggered.

        Args:
            alert_id: Alert UUID
        """
        stmt = (
            update(PriceAlert)
            .where(PriceAlert.id == alert_id)
            .values(
                triggered=True,
                triggered_at=datetime.now(timezone.utc),
            )
        )
        await self.session.execute(stmt)

    async def delete_alerts_for_ticket(self, ticket: int) -> int:
        """
        Delete all alerts for a position ticket (e.g., when position is closed).

        Args:
            ticket: Position ticket number

        Returns:
            Number of deleted alerts
        """
        from sqlalchemy import delete

        stmt = delete(PriceAlert).where(PriceAlert.ticket == ticket)
        result = await self.session.execute(stmt)
        return result.rowcount
