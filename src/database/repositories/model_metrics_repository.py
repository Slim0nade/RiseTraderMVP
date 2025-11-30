"""ModelMetrics Repository - CRUD operations for model performance metrics."""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database.models.model_metrics import ModelMetrics


class ModelMetricsRepository:
    """Repository for ModelMetrics database operations."""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def create(self, **kwargs) -> ModelMetrics:
        """Create new model metrics record."""
        metrics = ModelMetrics(**kwargs)
        self.db.add(metrics)
        await self.db.commit()
        await self.db.refresh(metrics)
        return metrics
    
    async def get_by_model_version(self, model_version: str, horizon: str) -> Optional[ModelMetrics]:
        """Get metrics for specific model version and horizon."""
        result = await self.db.execute(
            select(ModelMetrics).where(
                ModelMetrics.model_version == model_version,
                ModelMetrics.forecast_horizon == horizon
            )
        )
        return result.scalar_one_or_none()
    
    async def get_all_for_model(self, model_version: str) -> List[ModelMetrics]:
        """Get all metrics for a model version."""
        result = await self.db.execute(
            select(ModelMetrics).where(ModelMetrics.model_version == model_version)
        )
        return list(result.scalars().all())
