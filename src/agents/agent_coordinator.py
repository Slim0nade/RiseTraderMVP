"""
Agent Coordinator - Initialize and Manage All 10 RiseTrader Agents

Coordinates the lifecycle of all trading agents:
- Initialization in priority order
- Graceful shutdown
- Health monitoring
- Agent discovery
"""

import asyncio
import os
import re
from typing import Dict, Any, List, Optional

import structlog
import yaml

from .base_agent import BaseAgent
from .event_bus import EventBus
from .agent_registry import AgentRegistry

# Import all agents
from .execution import SignalGeneratorAgent, RiskManagerAgent, ExecutionAgent
from .data_ml import MarketDataAgent, MLPredictionAgent, RegimeDetectionAgent, DataQualityAgent
from .supervisory import PerformanceMonitorAgent, RiskOverseerAgent, StrategyOptimizerAgent

logger = structlog.get_logger(__name__)


class AgentCoordinator:
    """
    Coordinates all 10 RiseTrader agents

    Manages:
    - Agent initialization and registration
    - Event bus and agent registry setup
    - Graceful shutdown
    - Configuration loading
    - Health monitoring
    """

    def __init__(
        self,
        config_path: str = "/Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/config/agents.yaml",
        redis_url: str = "redis://localhost:6379",
        database_url: str = "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader",
    ):
        """
        Initialize AgentCoordinator

        Args:
            config_path: Path to agents.yaml configuration
            redis_url: Redis connection URL
            database_url: PostgreSQL connection URL
        """
        self.config_path = config_path
        self.redis_url = redis_url
        self.database_url = database_url

        # Core components
        self.event_bus: Optional[EventBus] = None
        self.agent_registry: Optional[AgentRegistry] = None

        # Agent instances
        self.agents: List[BaseAgent] = []
        self.agent_map: Dict[str, BaseAgent] = {}

        # Configuration
        self.config: Dict[str, Any] = {}

        # Running state
        self.running = False

        self.logger = logger.bind(component="agent_coordinator")

    async def start(self) -> None:
        """
        Start all agents

        1. Load configuration
        2. Initialize event bus and registry
        3. Create agent instances
        4. Start agents in priority order
        """
        try:
            self.logger.info("agent_coordinator_starting")

            # Load configuration
            await self._load_config()

            # Initialize event bus
            self.event_bus = EventBus(
                redis_url=self.redis_url,
                max_queue_size=10000,
                retry_attempts=3,
            )
            await self.event_bus.start()

            # Initialize agent registry
            self.agent_registry = AgentRegistry(
                redis_url=self.redis_url,
                circuit_breaker_enabled=True,
            )
            await self.agent_registry.start()

            # Create agent instances
            await self._create_agents()

            # Start agents in priority order
            await self._start_agents()

            self.running = True

            self.logger.info(
                "agent_coordinator_started",
                agent_count=len(self.agents),
            )

        except Exception as e:
            self.logger.error("agent_coordinator_start_failed", error=str(e), exc_info=True)
            await self.stop()
            raise

    async def stop(self) -> None:
        """
        Stop all agents gracefully

        1. Stop agents in reverse priority order
        2. Stop event bus
        3. Stop agent registry
        """
        if not self.running:
            return

        try:
            self.logger.info("agent_coordinator_stopping")

            # Stop agents in reverse priority order
            for agent in reversed(self.agents):
                try:
                    await agent.stop()
                except Exception as e:
                    self.logger.error(
                        "agent_stop_failed",
                        agent_id=agent.agent_id,
                        error=str(e),
                    )

            # Stop event bus
            if self.event_bus:
                await self.event_bus.stop()

            # Stop agent registry
            if self.agent_registry:
                await self.agent_registry.stop()

            self.running = False

            self.logger.info("agent_coordinator_stopped")

        except Exception as e:
            self.logger.error("agent_coordinator_stop_failed", error=str(e))

    async def _load_config(self) -> None:
        """Load agent configuration from YAML and expand environment variables"""
        try:
            with open(self.config_path, "r") as f:
                self.config = yaml.safe_load(f)

            # Expand environment variables in config
            self.config = self._expand_env_vars(self.config)

            self.logger.info(
                "config_loaded",
                config_path=self.config_path,
            )

        except Exception as e:
            self.logger.error("config_load_failed", error=str(e))
            raise

    def _expand_env_vars(self, obj: Any) -> Any:
        """
        Recursively expand environment variables in config

        Replaces ${VAR_NAME} with os.environ.get('VAR_NAME')
        """
        if isinstance(obj, dict):
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._expand_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            # Replace ${VAR_NAME} with environment variable value
            pattern = re.compile(r'\$\{([^}]+)\}')

            def replace_var(match):
                var_name = match.group(1)
                value = os.environ.get(var_name)
                if value is None:
                    self.logger.warning(
                        "env_var_not_found",
                        var_name=var_name,
                        original_value=obj
                    )
                    return match.group(0)  # Return original if not found
                return value

            return pattern.sub(replace_var, obj)
        else:
            return obj

    async def _create_agents(self) -> None:
        """
        Create all agent instances

        Creates instances in priority order:
        1. SignalGeneratorAgent (priority 1)
        2. RiskManagerAgent (priority 2)
        3. ExecutionAgent (priority 3)
        4. MarketDataAgent (priority 4)
        5. MLPredictionAgent (priority 5)
        6. RegimeDetectionAgent (priority 6)
        7. PerformanceMonitorAgent (priority 7)
        8. DataQualityAgent (priority 7)
        9. RiskOverseerAgent (priority 8)
        10. StrategyOptimizerAgent (priority 9)
        """
        agent_configs = self.config.get("agents", {})

        # Add shared config (database, redis)
        shared_config = {
            "redis_url": self.redis_url,
            "database_url": self.database_url,
        }

        # Execution Layer
        if agent_configs.get("signal_generator", {}).get("enabled", True):
            config = {**agent_configs["signal_generator"]["config"], **shared_config}
            agent = SignalGeneratorAgent(
                agent_id="signal_generator",
                event_bus=self.event_bus,
                agent_registry=self.agent_registry,
                config=config,
            )
            self.agents.append(agent)
            self.agent_map["signal_generator"] = agent

        if agent_configs.get("risk_manager", {}).get("enabled", True):
            config = {**agent_configs["risk_manager"]["config"], **shared_config}
            agent = RiskManagerAgent(
                agent_id="risk_manager",
                event_bus=self.event_bus,
                agent_registry=self.agent_registry,
                config=config,
            )
            self.agents.append(agent)
            self.agent_map["risk_manager"] = agent

        if agent_configs.get("execution", {}).get("enabled", True):
            config = {**agent_configs["execution"]["config"], **shared_config}
            agent = ExecutionAgent(
                agent_id="execution",
                event_bus=self.event_bus,
                agent_registry=self.agent_registry,
                config=config,
            )
            self.agents.append(agent)
            self.agent_map["execution"] = agent

        # Data/ML Layer
        if agent_configs.get("market_data", {}).get("enabled", True):
            config = {**agent_configs["market_data"]["config"], **shared_config}
            agent = MarketDataAgent(
                agent_id="market_data",
                event_bus=self.event_bus,
                agent_registry=self.agent_registry,
                config=config,
            )
            self.agents.append(agent)
            self.agent_map["market_data"] = agent

        if agent_configs.get("ml_prediction", {}).get("enabled", True):
            config = {**agent_configs["ml_prediction"]["config"], **shared_config}
            agent = MLPredictionAgent(
                agent_id="ml_prediction",
                event_bus=self.event_bus,
                agent_registry=self.agent_registry,
                config=config,
            )
            self.agents.append(agent)
            self.agent_map["ml_prediction"] = agent

        if agent_configs.get("regime_detection", {}).get("enabled", True):
            config = {**agent_configs["regime_detection"]["config"], **shared_config}
            agent = RegimeDetectionAgent(
                agent_id="regime_detection",
                event_bus=self.event_bus,
                agent_registry=self.agent_registry,
                config=config,
            )
            self.agents.append(agent)
            self.agent_map["regime_detection"] = agent

        # Supervisory Layer
        if agent_configs.get("performance_monitor", {}).get("enabled", True):
            config = {**agent_configs["performance_monitor"]["config"], **shared_config}
            agent = PerformanceMonitorAgent(
                agent_id="performance_monitor",
                event_bus=self.event_bus,
                agent_registry=self.agent_registry,
                config=config,
            )
            self.agents.append(agent)
            self.agent_map["performance_monitor"] = agent

        # Data Quality Agent
        agent = DataQualityAgent(
            agent_id="data_quality",
            event_bus=self.event_bus,
            agent_registry=self.agent_registry,
            config=shared_config,
        )
        self.agents.append(agent)
        self.agent_map["data_quality"] = agent

        if agent_configs.get("risk_overseer", {}).get("enabled", True):
            config = {**agent_configs["risk_overseer"]["config"], **shared_config}
            agent = RiskOverseerAgent(
                agent_id="risk_overseer",
                event_bus=self.event_bus,
                agent_registry=self.agent_registry,
                config=config,
            )
            self.agents.append(agent)
            self.agent_map["risk_overseer"] = agent

        if agent_configs.get("strategy_optimizer", {}).get("enabled", True):
            config = {**agent_configs["strategy_optimizer"]["config"], **shared_config}
            agent = StrategyOptimizerAgent(
                agent_id="strategy_optimizer",
                event_bus=self.event_bus,
                agent_registry=self.agent_registry,
                config=config,
            )
            self.agents.append(agent)
            self.agent_map["strategy_optimizer"] = agent

        # Sort by priority
        self.agents.sort(key=lambda a: a.priority)

        self.logger.info(
            "agents_created",
            count=len(self.agents),
            agents=[a.agent_id for a in self.agents],
        )

    async def _start_agents(self) -> None:
        """Start all agents in priority order"""
        for agent in self.agents:
            try:
                await agent.start()

                self.logger.info(
                    "agent_started",
                    agent_id=agent.agent_id,
                    priority=agent.priority,
                )

            except Exception as e:
                self.logger.error(
                    "agent_start_failed",
                    agent_id=agent.agent_id,
                    error=str(e),
                    exc_info=True,
                )
                # Continue starting other agents

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """Get agent by ID"""
        return self.agent_map.get(agent_id)

    def get_all_agents(self) -> List[BaseAgent]:
        """Get all agents"""
        return self.agents

    async def get_status(self) -> Dict[str, Any]:
        """
        Get coordinator and agent status

        Returns:
            Status dictionary
        """
        agent_statuses = []
        for agent in self.agents:
            agent_statuses.append(await agent.get_status())

        event_bus_stats = await self.event_bus.get_queue_stats() if self.event_bus else {}
        registry_stats = await self.agent_registry.get_stats() if self.agent_registry else {}

        return {
            "running": self.running,
            "total_agents": len(self.agents),
            "agents": agent_statuses,
            "event_bus": event_bus_stats,
            "agent_registry": registry_stats,
        }


# Convenience function for easy initialization
async def create_coordinator(
    config_path: str = "/Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/config/agents.yaml",
    redis_url: str = "redis://localhost:6379",
    database_url: str = "postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader",
) -> AgentCoordinator:
    """
    Create and start agent coordinator

    Args:
        config_path: Path to agents.yaml
        redis_url: Redis connection URL
        database_url: PostgreSQL connection URL

    Returns:
        Initialized AgentCoordinator
    """
    coordinator = AgentCoordinator(
        config_path=config_path,
        redis_url=redis_url,
        database_url=database_url,
    )

    await coordinator.start()

    return coordinator
