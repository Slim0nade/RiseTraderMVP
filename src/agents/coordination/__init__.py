"""
Agent Coordination Infrastructure.

Provides:
- AgentRegistry: Central registry for agent instance tracking
- Health monitoring across all active agents
- Agent lifecycle management
"""

from src.agents.coordination.agent_registry import AgentRegistry, AgentRegistryService

__all__ = ["AgentRegistry", "AgentRegistryService"]
