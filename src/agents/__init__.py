"""
RiseTrader Agent System

Model Context Protocol (MCP) Server for autonomous trading agent coordination.

This module provides the core infrastructure for RiseTrader's 10 trading agents:

Execution Layer:
- SignalGeneratorAgent - Multi-strategy signal generation
- RiskManagerAgent - Pre-trade validation & position sizing
- ExecutionAgent - MT4 order execution

Data/ML Layer:
- MarketDataAgent - Real-time data streaming
- MLPredictionAgent - ML-powered forecasts
- RegimeDetectionAgent - Market regime classification

Supervisory Layer:
- PerformanceMonitorAgent - Real-time P&L tracking
- RiskOverseerAgent - System-wide risk monitoring
- StrategyOptimizerAgent - Continuous parameter optimization

Usage:
    from src.agents import MCPServer, BaseAgent, EventBus

    # Start MCP server
    server = MCPServer(config_path="config/agents.yaml")
    await server.start()

    # Agents are automatically loaded from configuration
    # Access via HTTP API at http://localhost:7000
"""

from .agent_registry import (
    AgentRegistry,
    AgentMetadata,
    AgentStatus,
    CircuitBreaker,
    CircuitBreakerState,
)
from .base_agent import BaseAgent
from .event_bus import Event, EventBus, EventPriority, EventStatus
from .mcp_server import MCPServer, CommandRequest, CommandResponse

__version__ = "1.0.0"

__all__ = [
    # Main server
    "MCPServer",
    # Core components
    "EventBus",
    "AgentRegistry",
    "BaseAgent",
    # Event types
    "Event",
    "EventPriority",
    "EventStatus",
    # Registry types
    "AgentMetadata",
    "AgentStatus",
    "CircuitBreaker",
    "CircuitBreakerState",
    # API types
    "CommandRequest",
    "CommandResponse",
]
