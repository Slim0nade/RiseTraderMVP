"""Forecast Repository - CRUD operations for ML forecasts."""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime

from src.database.models.forecasts import Forecast


class ForecastRepository:
    """Repository for Forecast database operations."""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def create(self, **kwargs) -> Forecast:
        """Create new forecast."""
        forecast = Forecast(**kwargs)
        self.db.add(forecast)
        await self.db.commit()
        await self.db.refresh(forecast)
        return forecast
    
    async def get_latest(
        self,
        symbol: str,
        horizon: str,
        model_version: str
    ) -> Optional[Forecast]:
        """Get latest forecast for symbol/horizon/model."""
        result = await self.db.execute(
            select(Forecast).where(
                and_(
                    Forecast.symbol == symbol,
                    Forecast.forecast_horizon == horizon,
                    Forecast.model_version == model_version
                )
            ).order_by(Forecast.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_by_timestamp_range(
        self,
        symbol: str,
        start: datetime,
        end: datetime
    ) -> List[Forecast]:
        """Get forecasts within timestamp range."""
        result = await self.db.execute(
            select(Forecast).where(
                and_(
                    Forecast.symbol == symbol,
                    Forecast.timestamp >= start,
                    Forecast.timestamp <= end
                )
            ).order_by(Forecast.timestamp)
        )
        return list(result.scalars().all())
