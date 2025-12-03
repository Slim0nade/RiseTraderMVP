"""
Agent repository for CRUD operations on agents table.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.agent import Agent
from .base import BaseRepository


class AgentRepository(BaseRepository[Agent]):
    """Repository for Agent model operations."""

    def __init__(self, session: AsyncSession):
        """Initialize AgentRepository."""
        super().__init__(Agent, session)

    async def get_by_id(self, agent_id: UUID) -> Optional[Agent]:
        """
        Get agent by UUID.

        Args:
            agent_id: Agent UUID

        Returns:
            Agent instance or None
        """
        query = select(Agent).where(Agent.id == agent_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_type(
        self,
        agent_type: str,
        strategy_team_id: Optional[UUID] = None,
        is_active: Optional[bool] = None
    ) -> List[Agent]:
        """
        Get agents by type with optional filters.

        Args:
            agent_type: Agent type (e.g., 'technical_analyst')
            strategy_team_id: Optional strategy team filter
            is_active: Optional active status filter

        Returns:
            List of matching agents
        """
        query = select(Agent).where(Agent.agent_type == agent_type)

        if strategy_team_id is not None:
            query = query.where(Agent.strategy_team_id == strategy_team_id)

        if is_active is not None:
            query = query.where(Agent.is_active == is_active)

        query = query.order_by(Agent.created_at)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_layer(
        self,
        layer: str,
        is_active: Optional[bool] = None
    ) -> List[Agent]:
        """
        Get all agents in a specific layer.

        Args:
            layer: Agent layer (analysis, debate, decision, execution, supervisory)
            is_active: Optional active status filter

        Returns:
            List of agents in the layer
        """
        query = select(Agent).where(Agent.layer == layer)

        if is_active is not None:
            query = query.where(Agent.is_active == is_active)

        query = query.order_by(Agent.created_at)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_strategy_team(
        self,
        strategy_team_id: UUID,
        is_active: Optional[bool] = None
    ) -> List[Agent]:
        """
        Get all agents in a strategy team.

        Args:
            strategy_team_id: Strategy team UUID
            is_active: Optional active status filter

        Returns:
            List of agents in the team
        """
        query = select(Agent).where(Agent.strategy_team_id == strategy_team_id)

        if is_active is not None:
            query = query.where(Agent.is_active == is_active)

        query = query.order_by(Agent.layer, Agent.agent_type)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_rl_enabled_agents(
        self,
        is_active: Optional[bool] = True
    ) -> List[Agent]:
        """
        Get all RL-enabled agents.

        Args:
            is_active: Optional active status filter

        Returns:
            List of RL-enabled agents
        """
        query = select(Agent).where(Agent.rl_enabled == True)

        if is_active is not None:
            query = query.where(Agent.is_active == is_active)

        query = query.order_by(Agent.agent_type)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_active_agents(self) -> List[Agent]:
        """
        Get all active agents.

        Returns:
            List of active agents
        """
        query = select(Agent).where(Agent.is_active == True).order_by(Agent.layer, Agent.agent_type)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_state(
        self,
        agent_id: UUID,
        state: str,
        last_active_at: Optional[str] = None
    ) -> Optional[Agent]:
        """
        Update agent state.

        Args:
            agent_id: Agent UUID
            state: New state (idle, processing, error, paused)
            last_active_at: Optional last active timestamp

        Returns:
            Updated agent or None
        """
        agent = await self.get_by_id(agent_id)
        if not agent:
            return None

        agent.state = state
        if last_active_at:
            agent.last_active_at = last_active_at

        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def increment_decisions(
        self,
        agent_id: UUID,
        decision_time_ms: Optional[float] = None
    ) -> Optional[Agent]:
        """
        Increment decision count and update average decision time.

        Args:
            agent_id: Agent UUID
            decision_time_ms: Decision latency in milliseconds

        Returns:
            Updated agent or None
        """
        agent = await self.get_by_id(agent_id)
        if not agent:
            return None

        agent.total_decisions += 1

        if decision_time_ms is not None:
            if agent.avg_decision_time_ms is None:
                agent.avg_decision_time_ms = decision_time_ms
            else:
                # Running average
                total_time = agent.avg_decision_time_ms * (agent.total_decisions - 1)
                agent.avg_decision_time_ms = (total_time + decision_time_ms) / agent.total_decisions

        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def increment_errors(
        self,
        agent_id: UUID,
        error_message: str
    ) -> Optional[Agent]:
        """
        Increment error count and update last error.

        Args:
            agent_id: Agent UUID
            error_message: Error message

        Returns:
            Updated agent or None
        """
        agent = await self.get_by_id(agent_id)
        if not agent:
            return None

        agent.error_count += 1
        agent.last_error_message = error_message

        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def create(self, **kwargs) -> Agent:
        """
        Create a new agent.

        Args:
            **kwargs: Agent fields

        Returns:
            Created agent
        """
        agent = Agent(**kwargs)
        self.session.add(agent)
        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def delete(self, agent_id: UUID) -> bool:
        """
        Delete an agent.

        Args:
            agent_id: Agent UUID

        Returns:
            True if deleted, False if not found
        """
        agent = await self.get_by_id(agent_id)
        if not agent:
            return False

        await self.session.delete(agent)
        await self.session.commit()
        return True
