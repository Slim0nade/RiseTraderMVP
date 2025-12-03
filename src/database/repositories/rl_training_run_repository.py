"""
RLTrainingRun repository for tracking RL training experiments.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.rl_training_run import RLTrainingRun
from .base import BaseRepository


class RLTrainingRunRepository(BaseRepository[RLTrainingRun]):
    """Repository for RLTrainingRun model operations."""

    def __init__(self, session: AsyncSession):
        """Initialize RLTrainingRunRepository."""
        super().__init__(RLTrainingRun, session)

    async def get_by_id(self, run_id: UUID) -> Optional[RLTrainingRun]:
        """
        Get training run by UUID.

        Args:
            run_id: Training run UUID

        Returns:
            RLTrainingRun instance or None
        """
        query = select(RLTrainingRun).where(RLTrainingRun.id == run_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_mlflow_run_id(self, mlflow_run_id: str) -> Optional[RLTrainingRun]:
        """
        Get training run by MLflow run ID.

        Args:
            mlflow_run_id: MLflow run ID

        Returns:
            RLTrainingRun instance or None
        """
        query = select(RLTrainingRun).where(RLTrainingRun.mlflow_run_id == mlflow_run_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_agent_id(
        self,
        agent_id: UUID,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[RLTrainingRun]:
        """
        Get training runs for a specific agent.

        Args:
            agent_id: Agent UUID
            status: Optional status filter
            limit: Maximum results

        Returns:
            List of training runs
        """
        query = select(RLTrainingRun).where(RLTrainingRun.agent_id == agent_id)

        if status:
            query = query.where(RLTrainingRun.status == status)

        query = query.order_by(RLTrainingRun.created_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_agent_type(
        self,
        agent_type: str,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[RLTrainingRun]:
        """
        Get training runs for a specific agent type.

        Args:
            agent_type: Agent type
            status: Optional status filter
            limit: Maximum results

        Returns:
            List of training runs
        """
        query = select(RLTrainingRun).where(RLTrainingRun.agent_type == agent_type)

        if status:
            query = query.where(RLTrainingRun.status == status)

        query = query.order_by(RLTrainingRun.created_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_strategy_team(
        self,
        strategy_team_id: UUID,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[RLTrainingRun]:
        """
        Get training runs for a strategy team.

        Args:
            strategy_team_id: Strategy team UUID
            status: Optional status filter
            limit: Maximum results

        Returns:
            List of training runs
        """
        query = select(RLTrainingRun).where(RLTrainingRun.strategy_team_id == strategy_team_id)

        if status:
            query = query.where(RLTrainingRun.status == status)

        query = query.order_by(RLTrainingRun.created_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_validated_runs(
        self,
        min_sharpe: float = 1.2,
        agent_type: Optional[str] = None,
        limit: int = 50
    ) -> List[RLTrainingRun]:
        """
        Get training runs that passed validation (Sharpe >1.2).

        Args:
            min_sharpe: Minimum OOS Sharpe ratio threshold
            agent_type: Optional agent type filter
            limit: Maximum results

        Returns:
            List of validated training runs
        """
        query = select(RLTrainingRun).where(
            and_(
                RLTrainingRun.passed_validation == True,
                RLTrainingRun.test_sharpe_ratio >= min_sharpe
            )
        )

        if agent_type:
            query = query.where(RLTrainingRun.agent_type == agent_type)

        query = query.order_by(RLTrainingRun.test_sharpe_ratio.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_deployed_runs(
        self,
        agent_type: Optional[str] = None
    ) -> List[RLTrainingRun]:
        """
        Get deployed training runs (currently in production).

        Args:
            agent_type: Optional agent type filter

        Returns:
            List of deployed training runs
        """
        query = select(RLTrainingRun).where(
            and_(
                RLTrainingRun.model_registry_uri.isnot(None),
                RLTrainingRun.deployed_at.isnot(None)
            )
        )

        if agent_type:
            query = query.where(RLTrainingRun.agent_type == agent_type)

        query = query.order_by(RLTrainingRun.deployed_at.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_active_runs(self) -> List[RLTrainingRun]:
        """
        Get currently active (running) training runs.

        Returns:
            List of active training runs
        """
        query = select(RLTrainingRun).where(
            RLTrainingRun.status == 'running'
        ).order_by(RLTrainingRun.created_at)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_failed_runs(
        self,
        agent_type: Optional[str] = None,
        limit: int = 20
    ) -> List[RLTrainingRun]:
        """
        Get failed training runs for debugging.

        Args:
            agent_type: Optional agent type filter
            limit: Maximum results

        Returns:
            List of failed training runs
        """
        query = select(RLTrainingRun).where(RLTrainingRun.status == 'failed')

        if agent_type:
            query = query.where(RLTrainingRun.agent_type == agent_type)

        query = query.order_by(RLTrainingRun.created_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> RLTrainingRun:
        """
        Create a new training run.

        Args:
            **kwargs: RLTrainingRun fields

        Returns:
            Created training run
        """
        training_run = RLTrainingRun(**kwargs)
        self.session.add(training_run)
        await self.session.commit()
        await self.session.refresh(training_run)
        return training_run

    async def update_status(
        self,
        run_id: UUID,
        status: str,
        error_message: Optional[str] = None
    ) -> Optional[RLTrainingRun]:
        """
        Update training run status.

        Args:
            run_id: Training run UUID
            status: New status
            error_message: Optional error message if failed

        Returns:
            Updated training run or None
        """
        run = await self.get_by_id(run_id)
        if not run:
            return None

        run.status = status
        if error_message:
            run.error_message = error_message

        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def update_progress(
        self,
        run_id: UUID,
        current_timestep: int,
        train_mean_reward: Optional[float] = None,
        train_sharpe_ratio: Optional[float] = None
    ) -> Optional[RLTrainingRun]:
        """
        Update training progress.

        Args:
            run_id: Training run UUID
            current_timestep: Current training timestep
            train_mean_reward: Optional training reward
            train_sharpe_ratio: Optional training Sharpe

        Returns:
            Updated training run or None
        """
        run = await self.get_by_id(run_id)
        if not run:
            return None

        run.current_timestep = current_timestep
        if train_mean_reward is not None:
            run.train_mean_reward = train_mean_reward
        if train_sharpe_ratio is not None:
            run.train_sharpe_ratio = train_sharpe_ratio

        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def update_test_results(
        self,
        run_id: UUID,
        test_mean_reward: float,
        test_sharpe_ratio: float,
        test_max_drawdown: Optional[float] = None,
        test_win_rate: Optional[float] = None
    ) -> Optional[RLTrainingRun]:
        """
        Update out-of-sample test results.

        Args:
            run_id: Training run UUID
            test_mean_reward: OOS mean reward
            test_sharpe_ratio: OOS Sharpe ratio
            test_max_drawdown: Optional OOS max drawdown
            test_win_rate: Optional OOS win rate

        Returns:
            Updated training run or None
        """
        run = await self.get_by_id(run_id)
        if not run:
            return None

        run.test_mean_reward = test_mean_reward
        run.test_sharpe_ratio = test_sharpe_ratio
        run.test_max_drawdown = test_max_drawdown
        run.test_win_rate = test_win_rate

        # Check if passed validation (Sharpe >1.2)
        run.passed_validation = test_sharpe_ratio > 1.2

        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def mark_deployed(
        self,
        run_id: UUID,
        model_registry_uri: str
    ) -> Optional[RLTrainingRun]:
        """
        Mark training run as deployed to production.

        Args:
            run_id: Training run UUID
            model_registry_uri: MLflow model registry URI

        Returns:
            Updated training run or None
        """
        run = await self.get_by_id(run_id)
        if not run:
            return None

        run.model_registry_uri = model_registry_uri
        run.deployed_at = func.now()

        await self.session.commit()
        await self.session.refresh(run)
        return run
