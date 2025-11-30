"""TrainingRun Repository - CRUD operations for training runs."""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from src.database.models.training_runs import TrainingRun, TrainingStatus


class TrainingRunRepository:
    """Repository for TrainingRun database operations."""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def create(self, **kwargs) -> TrainingRun:
        """Create new training run."""
        run = TrainingRun(**kwargs)
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run
    
    async def get_by_id(self, run_id: int) -> Optional[TrainingRun]:
        """Get training run by ID."""
        result = await self.db.execute(
            select(TrainingRun).where(TrainingRun.id == run_id)
        )
        return result.scalar_one_or_none()
    
    async def update_status(self, run_id: int, status: TrainingStatus, **kwargs) -> TrainingRun:
        """Update training run status."""
        run = await self.get_by_id(run_id)
        run.status = status
        for key, value in kwargs.items():
            setattr(run, key, value)
        await self.db.commit()
        await self.db.refresh(run)
        return run
    
    async def get_by_symbol(self, symbol: str) -> List[TrainingRun]:
        """Get all training runs for a symbol."""
        result = await self.db.execute(
            select(TrainingRun).where(TrainingRun.symbol == symbol)
            .order_by(TrainingRun.created_at.desc())
        )
        return list(result.scalars().all())
