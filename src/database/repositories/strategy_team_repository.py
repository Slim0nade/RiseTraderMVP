"""
StrategyTeam repository for multi-agent team management.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.strategy_team import StrategyTeam
from .base import BaseRepository


class StrategyTeamRepository(BaseRepository[StrategyTeam]):
    """Repository for StrategyTeam model operations."""

    def __init__(self, session: AsyncSession):
        """Initialize StrategyTeamRepository."""
        super().__init__(StrategyTeam, session)

    async def get_by_id(self, team_id: UUID) -> Optional[StrategyTeam]:
        """Get team by UUID."""
        query = select(StrategyTeam).where(StrategyTeam.id == team_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_team_name(self, team_name: str) -> Optional[StrategyTeam]:
        """Get team by unique team name."""
        query = select(StrategyTeam).where(StrategyTeam.team_name == team_name)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_symbol(
        self,
        symbol: str,
        is_active: Optional[bool] = None
    ) -> List[StrategyTeam]:
        """Get teams trading a specific symbol."""
        query = select(StrategyTeam).where(StrategyTeam.symbol == symbol)

        if is_active is not None:
            query = query.where(StrategyTeam.is_active == is_active)

        query = query.order_by(StrategyTeam.created_at)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_active_teams(
        self,
        is_paper_trading: Optional[bool] = None
    ) -> List[StrategyTeam]:
        """Get all active teams."""
        query = select(StrategyTeam).where(StrategyTeam.is_active == True)

        if is_paper_trading is not None:
            query = query.where(StrategyTeam.is_paper_trading == is_paper_trading)

        query = query.order_by(StrategyTeam.symbol)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_live_trading_teams(self) -> List[StrategyTeam]:
        """Get teams in live trading mode (not paper)."""
        query = select(StrategyTeam).where(
            StrategyTeam.is_active == True,
            StrategyTeam.is_paper_trading == False
        ).order_by(StrategyTeam.symbol)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> StrategyTeam:
        """Create a new strategy team."""
        team = StrategyTeam(**kwargs)
        self.session.add(team)
        await self.session.commit()
        await self.session.refresh(team)
        return team

    async def update_performance(
        self,
        team_id: UUID,
        total_trades: Optional[int] = None,
        win_rate: Optional[float] = None,
        current_sharpe_ratio: Optional[float] = None,
        current_drawdown_pct: Optional[float] = None
    ) -> Optional[StrategyTeam]:
        """Update team performance metrics."""
        team = await self.get_by_id(team_id)
        if not team:
            return None

        if total_trades is not None:
            team.total_trades = total_trades
        if win_rate is not None:
            team.win_rate = win_rate
        if current_sharpe_ratio is not None:
            team.current_sharpe_ratio = current_sharpe_ratio
        if current_drawdown_pct is not None:
            team.current_drawdown_pct = current_drawdown_pct

        await self.session.commit()
        await self.session.refresh(team)
        return team

    async def activate(self, team_id: UUID) -> Optional[StrategyTeam]:
        """Activate a team."""
        team = await self.get_by_id(team_id)
        if not team:
            return None

        team.is_active = True
        team.activated_at = func.now()

        await self.session.commit()
        await self.session.refresh(team)
        return team

    async def deactivate(self, team_id: UUID) -> Optional[StrategyTeam]:
        """Deactivate a team."""
        team = await self.get_by_id(team_id)
        if not team:
            return None

        team.is_active = False
        team.deactivated_at = func.now()

        await self.session.commit()
        await self.session.refresh(team)
        return team
