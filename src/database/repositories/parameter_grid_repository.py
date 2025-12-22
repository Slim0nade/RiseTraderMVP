"""
Repository for parameter grid optimization and grid search results.

Handles parameter grid definitions and tracks grid search execution results
for hyperparameter optimization.
"""
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.backtest import (
    GridSearchResult,
    ParameterGrid,
)
from .base import BaseRepository


class ParameterGridRepository(BaseRepository[ParameterGrid]):
    """
    Repository for parameter grids and grid search results.

    Provides methods for creating parameter grids, tracking search results,
    and retrieving best-performing parameter combinations.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(ParameterGrid, session)

    # =============================================================================
    # ParameterGrid Operations
    # =============================================================================

    async def create_grid(self, grid_data: Dict[str, Any]) -> ParameterGrid:
        """
        Create a parameter grid for optimization.

        Args:
            grid_data: Grid attributes including name, base_config_id, parameters

        Returns:
            Created ParameterGrid instance
        """
        grid = ParameterGrid(**grid_data)
        self.session.add(grid)
        await self.session.flush()
        await self.session.refresh(grid)
        return grid

    async def get_grid(self, grid_id: UUID) -> Optional[ParameterGrid]:
        """
        Get parameter grid by ID with all relationships.

        Args:
            grid_id: Grid UUID

        Returns:
            ParameterGrid with loaded results or None
        """
        query = (
            select(ParameterGrid)
            .where(ParameterGrid.id == grid_id)
            .options(
                selectinload(ParameterGrid.base_configuration),
                selectinload(ParameterGrid.results),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_grid_by_name(self, name: str) -> Optional[ParameterGrid]:
        """
        Get parameter grid by name.

        Args:
            name: Grid name

        Returns:
            ParameterGrid or None
        """
        query = select(ParameterGrid).where(ParameterGrid.name == name)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_grids_by_config(
        self, config_id: UUID, limit: int = 100
    ) -> List[ParameterGrid]:
        """
        Get all grids for a base configuration.

        Args:
            config_id: Base configuration UUID
            limit: Maximum number of results

        Returns:
            List of ParameterGrid instances
        """
        query = (
            select(ParameterGrid)
            .where(ParameterGrid.base_config_id == config_id)
            .order_by(desc(ParameterGrid.created_at))
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    # =============================================================================
    # GridSearchResult Operations
    # =============================================================================

    async def create_grid_result(
        self, result_data: Dict[str, Any]
    ) -> GridSearchResult:
        """
        Create a grid search result linking parameters to backtest run.

        Args:
            result_data: Result attributes including grid_id, backtest_run_id, parameter_values

        Returns:
            Created GridSearchResult instance
        """
        grid_result = GridSearchResult(**result_data)
        self.session.add(grid_result)
        await self.session.flush()
        await self.session.refresh(grid_result)
        return grid_result

    async def get_grid_results(
        self, grid_id: UUID, limit: int = 1000
    ) -> List[GridSearchResult]:
        """
        Get all results for a parameter grid.

        Args:
            grid_id: Grid UUID
            limit: Maximum number of results

        Returns:
            List of GridSearchResult instances
        """
        query = (
            select(GridSearchResult)
            .where(GridSearchResult.grid_id == grid_id)
            .options(selectinload(GridSearchResult.backtest_run))
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_grid_rankings(self, grid_id: UUID) -> int:
        """
        Calculate and update rankings for all results in a grid.

        Computes rank_by_sharpe, rank_by_return, rank_by_drawdown based on
        completed backtest runs.

        Args:
            grid_id: Grid UUID

        Returns:
            Number of results updated
        """
        from sqlalchemy import case, literal_column
        from sqlalchemy.sql import over

        # Get all results with their backtest run metrics
        results = await self.get_grid_results(grid_id)

        if not results:
            return 0

        # Sort and rank by Sharpe ratio (descending - higher is better)
        sharpe_sorted = sorted(
            [
                r
                for r in results
                if r.backtest_run and r.backtest_run.sharpe_ratio is not None
            ],
            key=lambda x: x.backtest_run.sharpe_ratio,
            reverse=True,
        )

        for rank, result in enumerate(sharpe_sorted, start=1):
            result.rank_by_sharpe = rank

        # Sort and rank by total return (descending - higher is better)
        return_sorted = sorted(
            [
                r
                for r in results
                if r.backtest_run and r.backtest_run.total_return_pct is not None
            ],
            key=lambda x: x.backtest_run.total_return_pct,
            reverse=True,
        )

        for rank, result in enumerate(return_sorted, start=1):
            result.rank_by_return = rank

        # Sort and rank by drawdown (ascending - lower is better)
        drawdown_sorted = sorted(
            [
                r
                for r in results
                if r.backtest_run and r.backtest_run.max_drawdown_pct is not None
            ],
            key=lambda x: abs(x.backtest_run.max_drawdown_pct),
        )

        for rank, result in enumerate(drawdown_sorted, start=1):
            result.rank_by_drawdown = rank

        await self.session.flush()
        return len(results)

    async def get_top_results_by_metric(
        self,
        grid_id: UUID,
        metric: str = "sharpe",
        limit: int = 10,
    ) -> List[GridSearchResult]:
        """
        Get top N results by metric ranking.

        Args:
            grid_id: Grid UUID
            metric: Ranking metric ('sharpe', 'return', or 'drawdown')
            limit: Number of top results to return

        Returns:
            List of top GridSearchResult instances with loaded backtest runs
        """
        rank_column_map = {
            "sharpe": GridSearchResult.rank_by_sharpe,
            "return": GridSearchResult.rank_by_return,
            "drawdown": GridSearchResult.rank_by_drawdown,
        }

        rank_column = rank_column_map.get(metric, GridSearchResult.rank_by_sharpe)

        query = (
            select(GridSearchResult)
            .where(
                and_(
                    GridSearchResult.grid_id == grid_id,
                    rank_column.isnot(None),
                )
            )
            .options(selectinload(GridSearchResult.backtest_run))
            .order_by(rank_column)
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_best_parameters(
        self, grid_id: UUID, metric: str = "sharpe"
    ) -> Optional[Dict[str, Any]]:
        """
        Get the best-performing parameter combination for a metric.

        Args:
            grid_id: Grid UUID
            metric: Metric to optimize ('sharpe', 'return', or 'drawdown')

        Returns:
            Dictionary with parameter values and metrics, or None
        """
        top_results = await self.get_top_results_by_metric(
            grid_id, metric=metric, limit=1
        )

        if not top_results or not top_results[0].backtest_run:
            return None

        result = top_results[0]
        run = result.backtest_run

        return {
            "parameter_values": result.parameter_values,
            "rank": getattr(result, f"rank_by_{metric}", None),
            "sharpe_ratio": float(run.sharpe_ratio or 0),
            "total_return_pct": float(run.total_return_pct or 0),
            "max_drawdown_pct": float(run.max_drawdown_pct or 0),
            "win_rate": float(run.win_rate or 0),
            "total_trades": run.total_trades,
            "backtest_run_id": str(run.id),
        }

    async def mark_statistically_significant(
        self,
        grid_id: UUID,
        result_ids: List[UUID],
        is_significant: bool = True,
    ) -> int:
        """
        Mark grid search results as statistically significant.

        Args:
            grid_id: Grid UUID
            result_ids: List of result UUIDs to mark
            is_significant: Whether results are significant

        Returns:
            Number of results updated
        """
        count = 0
        for result_id in result_ids:
            result = await self.session.get(GridSearchResult, result_id)
            if result and result.grid_id == grid_id:
                result.is_statistically_significant = is_significant
                count += 1

        await self.session.flush()
        return count

    async def get_grid_summary(self, grid_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get summary statistics for a parameter grid search.

        Args:
            grid_id: Grid UUID

        Returns:
            Dictionary with grid metadata and result statistics
        """
        grid = await self.get_grid(grid_id)
        if not grid:
            return None

        # Count total and completed results
        total_query = select(func.count()).select_from(GridSearchResult).where(
            GridSearchResult.grid_id == grid_id
        )
        total_result = await self.session.execute(total_query)
        total_count = total_result.scalar() or 0

        # Get best results for each metric
        best_sharpe = await self.get_best_parameters(grid_id, metric="sharpe")
        best_return = await self.get_best_parameters(grid_id, metric="return")
        best_drawdown = await self.get_best_parameters(grid_id, metric="drawdown")

        # Count significant results
        significant_query = (
            select(func.count())
            .select_from(GridSearchResult)
            .where(
                and_(
                    GridSearchResult.grid_id == grid_id,
                    GridSearchResult.is_statistically_significant.is_(True),
                )
            )
        )
        significant_result = await self.session.execute(significant_query)
        significant_count = significant_result.scalar() or 0

        return {
            "grid_id": str(grid.id),
            "name": grid.name,
            "base_config_id": str(grid.base_config_id),
            "total_combinations": grid.total_combinations,
            "completed_runs": total_count,
            "completion_pct": (
                (total_count / grid.total_combinations * 100)
                if grid.total_combinations > 0
                else 0
            ),
            "statistically_significant_count": significant_count,
            "best_by_sharpe": best_sharpe,
            "best_by_return": best_return,
            "best_by_drawdown": best_drawdown,
            "created_at": grid.created_at,
        }

    async def get_parameter_ranges(
        self, grid_id: UUID
    ) -> Optional[Dict[str, List[Any]]]:
        """
        Get the parameter ranges defined in a grid.

        Args:
            grid_id: Grid UUID

        Returns:
            Dictionary mapping parameter names to their value ranges
        """
        grid = await self.session.get(ParameterGrid, grid_id)
        if not grid:
            return None

        return grid.parameters
