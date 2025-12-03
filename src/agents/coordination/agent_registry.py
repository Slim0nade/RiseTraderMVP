"""
Agent Registry: Central tracking for all agent instances.

Provides:
- Agent instance registration and lifecycle tracking
- Health monitoring across all agents
- Agent discovery by symbol, type, team
- Graceful shutdown coordination
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import UUID
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.base.base_agent import BaseAgent
from src.agents.base.agent_config import AgentState
from src.database.repositories import AgentRepository

logger = structlog.get_logger(__name__)


class AgentRegistry:
    """
    In-memory registry of active agent instances.

    Tracks all running agents for health monitoring, coordination,
    and graceful shutdown. Thread-safe for concurrent access.
    """

    def __init__(self):
        """Initialize empty agent registry."""
        self._agents: Dict[UUID, BaseAgent] = {}
        self._agents_by_type: Dict[str, List[UUID]] = {}
        self._agents_by_symbol: Dict[str, List[UUID]] = {}
        self._agents_by_team: Dict[UUID, List[UUID]] = {}

        logger.info("agent_registry_initialized")

    def register(
        self,
        agent: BaseAgent,
        symbol: Optional[str] = None,
        team_id: Optional[UUID] = None,
    ):
        """
        Register an agent instance.

        Args:
            agent: Agent instance to register
            symbol: Trading symbol this agent handles
            team_id: Strategy team ID this agent belongs to
        """
        agent_id = agent.agent_id
        agent_type = agent.config.agent_type.value

        # Add to main registry
        self._agents[agent_id] = agent

        # Index by type
        if agent_type not in self._agents_by_type:
            self._agents_by_type[agent_type] = []
        self._agents_by_type[agent_type].append(agent_id)

        # Index by symbol
        if symbol:
            if symbol not in self._agents_by_symbol:
                self._agents_by_symbol[symbol] = []
            self._agents_by_symbol[symbol].append(agent_id)

        # Index by team
        if team_id:
            if team_id not in self._agents_by_team:
                self._agents_by_team[team_id] = []
            self._agents_by_team[team_id].append(agent_id)

        logger.info(
            "agent_registered",
            agent_id=str(agent_id),
            agent_type=agent_type,
            agent_name=agent.config.name,
            symbol=symbol,
            team_id=str(team_id) if team_id else None,
        )

    def unregister(self, agent_id: UUID):
        """
        Unregister an agent instance.

        Args:
            agent_id: Agent ID to unregister
        """
        if agent_id not in self._agents:
            logger.warning("agent_not_found_for_unregister", agent_id=str(agent_id))
            return

        agent = self._agents[agent_id]
        agent_type = agent.config.agent_type.value

        # Remove from all indexes
        del self._agents[agent_id]

        if agent_type in self._agents_by_type:
            self._agents_by_type[agent_type] = [
                aid for aid in self._agents_by_type[agent_type] if aid != agent_id
            ]

        for symbol in self._agents_by_symbol:
            self._agents_by_symbol[symbol] = [
                aid for aid in self._agents_by_symbol[symbol] if aid != agent_id
            ]

        for team_id in self._agents_by_team:
            self._agents_by_team[team_id] = [
                aid for aid in self._agents_by_team[team_id] if aid != agent_id
            ]

        logger.info("agent_unregistered", agent_id=str(agent_id), agent_type=agent_type)

    def get(self, agent_id: UUID) -> Optional[BaseAgent]:
        """Get agent instance by ID."""
        return self._agents.get(agent_id)

    def get_by_type(self, agent_type: str) -> List[BaseAgent]:
        """Get all agents of a specific type."""
        agent_ids = self._agents_by_type.get(agent_type, [])
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def get_by_symbol(self, symbol: str) -> List[BaseAgent]:
        """Get all agents handling a specific symbol."""
        agent_ids = self._agents_by_symbol.get(symbol, [])
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def get_by_team(self, team_id: UUID) -> List[BaseAgent]:
        """Get all agents in a specific team."""
        agent_ids = self._agents_by_team.get(team_id, [])
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def get_all(self) -> List[BaseAgent]:
        """Get all registered agents."""
        return list(self._agents.values())

    async def health_check_all(self) -> Dict[str, Any]:
        """
        Check health of all registered agents.

        Returns:
            Dictionary with overall health status and per-agent details
        """
        total = len(self._agents)
        healthy_count = 0
        unhealthy_count = 0
        agent_statuses = []

        for agent in self._agents.values():
            try:
                health = await agent.health_check()
                is_healthy = health.get("status") == "healthy"

                if is_healthy:
                    healthy_count += 1
                else:
                    unhealthy_count += 1

                agent_statuses.append(health)

            except Exception as e:
                unhealthy_count += 1
                agent_statuses.append({
                    "agent_id": str(agent.agent_id),
                    "status": "error",
                    "error": str(e),
                })

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_agents": total,
            "healthy": healthy_count,
            "unhealthy": unhealthy_count,
            "overall_status": "healthy" if unhealthy_count == 0 else "degraded",
            "agents": agent_statuses,
        }

    async def shutdown_all(self):
        """
        Gracefully shutdown all registered agents.

        Calls shutdown() on each agent and unregisters them.
        """
        logger.info("shutting_down_all_agents", count=len(self._agents))

        agent_ids = list(self._agents.keys())

        for agent_id in agent_ids:
            agent = self._agents.get(agent_id)
            if agent:
                try:
                    await agent.shutdown()
                    self.unregister(agent_id)
                except Exception as e:
                    logger.error(
                        "agent_shutdown_error",
                        agent_id=str(agent_id),
                        error=str(e),
                        exc_info=True,
                    )

        logger.info("all_agents_shutdown_complete")

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dictionary with agent counts by type, symbol, state
        """
        stats = {
            "total_agents": len(self._agents),
            "by_type": {},
            "by_symbol": {},
            "by_state": {},
        }

        # Count by type
        for agent_type, agent_ids in self._agents_by_type.items():
            stats["by_type"][agent_type] = len(agent_ids)

        # Count by symbol
        for symbol, agent_ids in self._agents_by_symbol.items():
            stats["by_symbol"][symbol] = len(agent_ids)

        # Count by state
        for agent in self._agents.values():
            state = agent._state.state.value
            if state not in stats["by_state"]:
                stats["by_state"][state] = 0
            stats["by_state"][state] += 1

        return stats


class AgentRegistryService:
    """
    Service layer for agent registry with database persistence.

    Provides higher-level operations combining in-memory registry
    with database persistence for agent lifecycle management.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize registry service.

        Args:
            session: SQLAlchemy async session
        """
        self.registry = AgentRegistry()
        self._session = session
        self._agent_repo = AgentRepository(session)

    async def register_agent(
        self,
        agent: BaseAgent,
        symbol: Optional[str] = None,
        team_id: Optional[UUID] = None,
    ):
        """
        Register agent in both memory and database.

        Args:
            agent: Agent instance
            symbol: Trading symbol
            team_id: Strategy team ID
        """
        # Register in memory
        self.registry.register(agent, symbol=symbol, team_id=team_id)

        # Update database record to mark as active
        try:
            await self._agent_repo.update(
                agent.agent_id,
                is_active=True,
                activated_at=datetime.utcnow(),
            )
        except Exception as e:
            logger.error(
                "agent_db_activation_error",
                agent_id=str(agent.agent_id),
                error=str(e),
            )

    async def unregister_agent(self, agent_id: UUID):
        """
        Unregister agent from memory and mark inactive in database.

        Args:
            agent_id: Agent ID to unregister
        """
        # Unregister from memory
        self.registry.unregister(agent_id)

        # Mark inactive in database
        try:
            await self._agent_repo.update(
                agent_id,
                is_active=False,
                deactivated_at=datetime.utcnow(),
            )
        except Exception as e:
            logger.error(
                "agent_db_deactivation_error",
                agent_id=str(agent_id),
                error=str(e),
            )

    async def get_active_agents_from_db(self) -> List[Dict[str, Any]]:
        """
        Get all active agents from database.

        Returns:
            List of agent records from database
        """
        return await self._agent_repo.get_active_agents()

    async def sync_registry_with_db(self):
        """
        Sync in-memory registry with database state.

        Useful after restart to ensure consistency.
        """
        db_active_agents = await self.get_active_agents_from_db()
        registry_agent_ids = set(self.registry._agents.keys())
        db_agent_ids = {agent["id"] for agent in db_active_agents}

        # Find agents in DB but not in registry (need to mark inactive)
        orphaned = db_agent_ids - registry_agent_ids

        for agent_id in orphaned:
            logger.warning(
                "orphaned_agent_found_in_db",
                agent_id=str(agent_id),
                action="marking_inactive",
            )
            await self._agent_repo.update(
                agent_id,
                is_active=False,
                deactivated_at=datetime.utcnow(),
            )

        logger.info(
            "registry_sync_complete",
            registry_count=len(registry_agent_ids),
            db_count=len(db_agent_ids),
            orphaned=len(orphaned),
        )


# Global singleton registry instance
_global_registry: Optional[AgentRegistry] = None


def get_global_registry() -> AgentRegistry:
    """
    Get or create the global agent registry instance.

    Returns:
        Global AgentRegistry singleton
    """
    global _global_registry

    if _global_registry is None:
        _global_registry = AgentRegistry()
        logger.info("global_agent_registry_created")

    return _global_registry
