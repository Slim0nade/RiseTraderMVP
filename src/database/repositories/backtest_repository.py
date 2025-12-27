"""
Repository for backtesting engine entities.

Handles CRUD operations for backtest configurations, runs, trades,
portfolio snapshots, and agent decision logs.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.backtest import (
    BacktestConfiguration,
    BacktestRun,
    ExecutionMode,
    RunStatus,
)
from ..models.simulated_trade import (
    AgentDecisionLog,
    PortfolioSnapshot,
    SimulatedTrade,
)
from .base import BaseRepository


class BacktestRepository(BaseRepository[BacktestConfiguration]):
    """
    Repository for backtest configurations and related entities.

    Provides specialized queries for backtest execution, performance analysis,
    and historical trade retrieval.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(BacktestConfiguration, session)

    # =============================================================================
    # BacktestConfiguration Operations
    # =============================================================================

    async def get_config(self, config_id: UUID) -> Optional[BacktestConfiguration]:
        """
        Get backtest configuration by ID with all relationships.

        Args:
            config_id: Configuration UUID

        Returns:
            BacktestConfiguration with loaded relationships or None
        """
        query = (
            select(BacktestConfiguration)
            .where(BacktestConfiguration.id == config_id)
            .options(
                selectinload(BacktestConfiguration.runs),
                selectinload(BacktestConfiguration.parameter_grids),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_configs_by_symbol(
        self,
        symbol: str,
        execution_mode: Optional[ExecutionMode] = None,
        limit: int = 100,
    ) -> List[BacktestConfiguration]:
        """
        Get all configurations for a symbol.

        Args:
            symbol: Trading symbol
            execution_mode: Optional filter by execution mode
            limit: Maximum number of results

        Returns:
            List of BacktestConfiguration instances
        """
        query = (
            select(BacktestConfiguration)
            .where(BacktestConfiguration.symbol == symbol)
            .order_by(desc(BacktestConfiguration.created_at))
            .limit(limit)
        )

        if execution_mode:
            query = query.where(BacktestConfiguration.execution_mode == execution_mode)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_config_by_name(self, name: str) -> Optional[BacktestConfiguration]:
        """
        Get configuration by name.

        Args:
            name: Configuration name

        Returns:
            BacktestConfiguration or None
        """
        query = select(BacktestConfiguration).where(
            BacktestConfiguration.name == name
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_configs(
        self,
        symbol: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[BacktestConfiguration]:
        """
        List backtest configurations with pagination.

        Args:
            symbol: Optional symbol filter
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of BacktestConfiguration instances
        """
        query = (
            select(BacktestConfiguration)
            .order_by(desc(BacktestConfiguration.created_at))
            .limit(limit)
            .offset(offset)
        )

        if symbol:
            query = query.where(BacktestConfiguration.symbol == symbol)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    # =============================================================================
    # BacktestRun Operations
    # =============================================================================

    async def create_run(self, run_data: Dict[str, Any]) -> BacktestRun:
        """
        Create a new backtest run.

        Args:
            run_data: Run attributes including config_id, status, start_time

        Returns:
            Created BacktestRun instance
        """
        run = BacktestRun(**run_data)
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def get_run(self, run_id: UUID) -> Optional[BacktestRun]:
        """
        Get backtest run by ID with all relationships.

        Args:
            run_id: Run UUID

        Returns:
            BacktestRun with loaded relationships or None
        """
        query = (
            select(BacktestRun)
            .where(BacktestRun.id == run_id)
            .options(
                selectinload(BacktestRun.configuration),
                selectinload(BacktestRun.trades),
                selectinload(BacktestRun.snapshots),
                selectinload(BacktestRun.agent_decisions),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update_run(
        self, run_id: UUID, update_data: Dict[str, Any]
    ) -> Optional[BacktestRun]:
        """
        Update backtest run with results and metrics.

        Args:
            run_id: Run UUID
            update_data: Fields to update (status, metrics, end_time, etc.)

        Returns:
            Updated BacktestRun or None
        """
        run = await self.session.get(BacktestRun, run_id)
        if not run:
            return None

        for key, value in update_data.items():
            setattr(run, key, value)

        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def get_runs_by_config(
        self,
        config_id: UUID,
        status: Optional[RunStatus] = None,
        limit: int = 100,
    ) -> List[BacktestRun]:
        """
        Get all runs for a configuration.

        Args:
            config_id: Configuration UUID
            status: Optional filter by run status
            limit: Maximum number of results

        Returns:
            List of BacktestRun instances ordered by start_time DESC
        """
        query = (
            select(BacktestRun)
            .where(BacktestRun.config_id == config_id)
            .order_by(desc(BacktestRun.start_time))
            .limit(limit)
        )

        if status:
            query = query.where(BacktestRun.status == status)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_runs(
        self,
        config_id: Optional[UUID] = None,
        status_filter: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[BacktestRun]:
        """
        List all backtest runs with optional filters.

        Args:
            config_id: Optional filter by configuration UUID
            status_filter: Optional filter by status string ('pending', 'running', 'completed', 'failed')
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of BacktestRun instances ordered by start_time DESC
        """
        query = select(BacktestRun).order_by(desc(BacktestRun.start_time))

        if config_id:
            query = query.where(BacktestRun.config_id == config_id)

        if status_filter:
            # Convert string to RunStatus enum
            try:
                status_enum = RunStatus(status_filter.upper())
                query = query.where(BacktestRun.status == status_enum)
            except ValueError:
                # Invalid status, ignore filter
                pass

        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_best_run_by_metric(
        self,
        config_id: UUID,
        metric: str = "sharpe_ratio",
        status: RunStatus = RunStatus.COMPLETED,
    ) -> Optional[BacktestRun]:
        """
        Get the best performing run for a configuration by metric.

        Args:
            config_id: Configuration UUID
            metric: Metric to optimize ('sharpe_ratio', 'total_return_pct', etc.)
            status: Only consider runs with this status

        Returns:
            Best BacktestRun or None
        """
        metric_column = getattr(BacktestRun, metric, None)
        if not metric_column:
            return None

        query = (
            select(BacktestRun)
            .where(
                and_(
                    BacktestRun.config_id == config_id,
                    BacktestRun.status == status,
                    metric_column.isnot(None),
                )
            )
            .order_by(desc(metric_column))
            .limit(1)
        )

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    # =============================================================================
    # SimulatedTrade Operations
    # =============================================================================

    async def create_trade(self, trade_data: Dict[str, Any]) -> SimulatedTrade:
        """
        Create a simulated trade record.

        Args:
            trade_data: Trade attributes

        Returns:
            Created SimulatedTrade instance
        """
        trade = SimulatedTrade(**trade_data)
        self.session.add(trade)
        await self.session.flush()
        await self.session.refresh(trade)
        return trade

    async def update_trade(
        self, trade_id: UUID, update_data: Dict[str, Any]
    ) -> Optional[SimulatedTrade]:
        """
        Update a simulated trade record (typically with exit details).

        Args:
            trade_id: Trade UUID
            update_data: Fields to update (exit_timestamp, exit_price, gross_pnl, net_pnl, etc.)

        Returns:
            Updated SimulatedTrade or None if not found
        """
        trade = await self.session.get(SimulatedTrade, trade_id)
        if not trade:
            return None

        for key, value in update_data.items():
            setattr(trade, key, value)

        await self.session.flush()
        await self.session.refresh(trade)
        return trade

    async def get_trades(
        self,
        run_id: UUID,
        symbol: Optional[str] = None,
        limit: int = 1000,
    ) -> List[SimulatedTrade]:
        """
        Get trades for a backtest run.

        Args:
            run_id: Backtest run UUID
            symbol: Optional symbol filter
            limit: Maximum number of trades

        Returns:
            List of SimulatedTrade instances ordered by entry_timestamp
        """
        query = (
            select(SimulatedTrade)
            .where(SimulatedTrade.backtest_run_id == run_id)
            .order_by(SimulatedTrade.entry_timestamp)
            .limit(limit)
        )

        if symbol:
            query = query.where(SimulatedTrade.symbol == symbol)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_open_trades(self, run_id: UUID) -> List[SimulatedTrade]:
        """
        Get all open trades for a backtest run.

        Args:
            run_id: Backtest run UUID

        Returns:
            List of open SimulatedTrade instances
        """
        query = select(SimulatedTrade).where(
            and_(
                SimulatedTrade.backtest_run_id == run_id,
                SimulatedTrade.exit_timestamp.is_(None),
            )
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def close_trade(
        self,
        trade_id: UUID,
        exit_timestamp: datetime,
        exit_price: float,
        gross_pnl: float,
        net_pnl: float,
    ) -> Optional[SimulatedTrade]:
        """
        Close a simulated trade by updating exit details.

        Args:
            trade_id: Trade UUID
            exit_timestamp: Exit time
            exit_price: Exit price
            gross_pnl: Gross profit/loss
            net_pnl: Net profit/loss after fees

        Returns:
            Updated SimulatedTrade or None
        """
        trade = await self.session.get(SimulatedTrade, trade_id)
        if not trade:
            return None

        trade.exit_timestamp = exit_timestamp
        trade.exit_price = exit_price
        trade.gross_pnl = gross_pnl
        trade.net_pnl = net_pnl
        trade.holding_duration_seconds = int(
            (exit_timestamp - trade.entry_timestamp).total_seconds()
        )

        await self.session.flush()
        await self.session.refresh(trade)
        return trade

    # =============================================================================
    # PortfolioSnapshot Operations
    # =============================================================================

    async def create_snapshot(
        self, snapshot_data: Dict[str, Any]
    ) -> PortfolioSnapshot:
        """
        Create a portfolio snapshot.

        Args:
            snapshot_data: Snapshot attributes

        Returns:
            Created PortfolioSnapshot instance
        """
        snapshot = PortfolioSnapshot(**snapshot_data)
        self.session.add(snapshot)
        await self.session.flush()
        await self.session.refresh(snapshot)
        return snapshot

    async def get_snapshots(
        self,
        run_id: UUID,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 10000,
    ) -> List[PortfolioSnapshot]:
        """
        Get portfolio snapshots for a backtest run.

        Args:
            run_id: Backtest run UUID
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum number of snapshots

        Returns:
            List of PortfolioSnapshot instances ordered by timestamp
        """
        query = (
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.backtest_run_id == run_id)
            .order_by(PortfolioSnapshot.timestamp)
            .limit(limit)
        )

        if start_time:
            query = query.where(PortfolioSnapshot.timestamp >= start_time)
        if end_time:
            query = query.where(PortfolioSnapshot.timestamp <= end_time)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_latest_snapshot(
        self, run_id: UUID
    ) -> Optional[PortfolioSnapshot]:
        """
        Get the most recent portfolio snapshot for a run.

        Args:
            run_id: Backtest run UUID

        Returns:
            Latest PortfolioSnapshot or None
        """
        query = (
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.backtest_run_id == run_id)
            .order_by(desc(PortfolioSnapshot.timestamp))
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    # =============================================================================
    # AgentDecisionLog Operations
    # =============================================================================

    async def create_decision_log(
        self, decision_data: Dict[str, Any]
    ) -> AgentDecisionLog:
        """
        Create an agent decision log entry.

        Args:
            decision_data: Decision log attributes

        Returns:
            Created AgentDecisionLog instance
        """
        decision = AgentDecisionLog(**decision_data)
        self.session.add(decision)
        await self.session.flush()
        await self.session.refresh(decision)
        return decision

    async def get_agent_decisions(
        self,
        run_id: UUID,
        agent_identifier: Optional[str] = None,
        correlation_id: Optional[UUID] = None,
        limit: int = 10000,
    ) -> List[AgentDecisionLog]:
        """
        Get agent decision logs for a backtest run.

        Args:
            run_id: Backtest run UUID
            agent_identifier: Optional filter by agent name
            correlation_id: Optional filter by correlation ID
            limit: Maximum number of logs

        Returns:
            List of AgentDecisionLog instances ordered by timestamp
        """
        query = (
            select(AgentDecisionLog)
            .where(AgentDecisionLog.backtest_run_id == run_id)
            .order_by(AgentDecisionLog.timestamp)
            .limit(limit)
        )

        if agent_identifier:
            query = query.where(
                AgentDecisionLog.agent_identifier == agent_identifier
            )
        if correlation_id:
            query = query.where(AgentDecisionLog.correlation_id == correlation_id)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_correlated_decisions(
        self, correlation_id: UUID
    ) -> List[AgentDecisionLog]:
        """
        Get all agent decisions for a correlation ID (same market event).

        Args:
            correlation_id: Correlation UUID linking related decisions

        Returns:
            List of correlated AgentDecisionLog instances
        """
        query = (
            select(AgentDecisionLog)
            .where(AgentDecisionLog.correlation_id == correlation_id)
            .order_by(AgentDecisionLog.timestamp)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    # =============================================================================
    # Analytics and Aggregations
    # =============================================================================

    async def get_run_summary(self, run_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive summary for a backtest run.

        Args:
            run_id: Backtest run UUID

        Returns:
            Dictionary with run metrics, trade counts, and portfolio stats
        """
        run = await self.get_run(run_id)
        if not run:
            return None

        # Get trade statistics
        trade_count_query = (
            select(
                func.count(SimulatedTrade.id).label("total_trades"),
                func.sum(
                    func.case((SimulatedTrade.net_pnl > 0, 1), else_=0)
                ).label("winning_trades"),
                func.avg(SimulatedTrade.net_pnl).label("avg_pnl"),
                func.sum(SimulatedTrade.net_pnl).label("total_pnl"),
                func.avg(SimulatedTrade.holding_duration_seconds).label(
                    "avg_duration"
                ),
            )
            .where(
                and_(
                    SimulatedTrade.backtest_run_id == run_id,
                    SimulatedTrade.exit_timestamp.isnot(None),
                )
            )
        )

        trade_stats_result = await self.session.execute(trade_count_query)
        trade_stats = trade_stats_result.one()

        # Get snapshot count
        snapshot_count_query = select(func.count()).select_from(
            PortfolioSnapshot
        ).where(PortfolioSnapshot.backtest_run_id == run_id)
        snapshot_count_result = await self.session.execute(snapshot_count_query)
        snapshot_count = snapshot_count_result.scalar() or 0

        return {
            "run_id": str(run.id),
            "config_id": str(run.config_id),
            "status": run.status,
            "start_time": run.start_time,
            "end_time": run.end_time,
            "total_return_pct": float(run.total_return_pct or 0),
            "sharpe_ratio": float(run.sharpe_ratio or 0),
            "max_drawdown_pct": float(run.max_drawdown_pct or 0),
            "win_rate": float(run.win_rate or 0),
            "total_trades": trade_stats.total_trades or 0,
            "winning_trades": trade_stats.winning_trades or 0,
            "avg_pnl_per_trade": float(trade_stats.avg_pnl or 0),
            "total_pnl": float(trade_stats.total_pnl or 0),
            "avg_holding_duration_hours": (
                float(trade_stats.avg_duration or 0) / 3600
            ),
            "final_capital": float(run.final_capital or 0),
            "candles_processed": run.candles_processed,
            "agent_decisions_count": run.agent_decisions_count,
            "portfolio_snapshots": snapshot_count,
        }

    async def count_runs_by_status(
        self, config_id: Optional[UUID] = None
    ) -> Dict[RunStatus, int]:
        """
        Count runs grouped by status.

        Args:
            config_id: Optional filter by configuration

        Returns:
            Dictionary mapping RunStatus to count
        """
        query = select(
            BacktestRun.status,
            func.count(BacktestRun.id).label("count"),
        ).group_by(BacktestRun.status)

        if config_id:
            query = query.where(BacktestRun.config_id == config_id)

        result = await self.session.execute(query)
        return {row.status: row.count for row in result.all()}

    async def create_agent_decision_log(
        self,
        decision_log: "AgentDecisionLog",
    ) -> "AgentDecisionLog":
        """
        Create agent decision log entry.

        Args:
            decision_log: AgentDecisionLog instance

        Returns:
            Created AgentDecisionLog
        """
        self.session.add(decision_log)
        await self.session.flush()
        return decision_log

    # Alias for backwards compatibility
    async def get_agent_decision_logs(
        self,
        run_id: UUID,
        limit: int = 10000,
    ) -> List[AgentDecisionLog]:
        """
        Alias for get_agent_decisions for backwards compatibility.
        
        Args:
            run_id: Backtest run UUID
            limit: Maximum number of logs
            
        Returns:
            List of AgentDecisionLog instances
        """
        return await self.get_agent_decisions(run_id=run_id, limit=limit)
