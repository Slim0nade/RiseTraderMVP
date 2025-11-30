"""Exogenous Variable Repository."""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime

from src.database.models.exogenous_variables import ExogenousVariable


class ExogenousVariableRepository:
    """Repository for exogenous variables."""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def create_or_update(self, **kwargs) -> ExogenousVariable:
        """Create or update exogenous variable."""
        var = ExogenousVariable(**kwargs)
        self.db.add(var)
        await self.db.commit()
        await self.db.refresh(var)
        return var
    
    async def get_by_time_range(
        self,
        variable_name: str,
        start: datetime,
        end: datetime
    ) -> List[ExogenousVariable]:
        """Get exogenous variables within time range."""
        result = await self.db.execute(
            select(ExogenousVariable).where(
                and_(
                    ExogenousVariable.variable_name == variable_name,
                    ExogenousVariable.timestamp >= start,
                    ExogenousVariable.timestamp <= end
                )
            ).order_by(ExogenousVariable.timestamp)
        )
        return list(result.scalars().all())
