"""
MCP (Model Context Protocol) Server

Central coordination hub for RiseTrader's 10 autonomous trading agents.
Provides event-driven agent communication, lifecycle management, and monitoring.

Performance Targets:
- <50ms event processing
- 100+ events/second throughput
- 99.9% uptime
"""

import asyncio
import importlib
import os
import signal
from typing import Any, Dict, List, Optional, Type

import structlog
import yaml
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Gauge, make_asgi_app
from pydantic import BaseModel

from .agent_registry import AgentRegistry, AgentStatus
from .base_agent import BaseAgent
from .event_bus import Event, EventBus, EventPriority

logger = structlog.get_logger(__name__)

# Prometheus metrics
MCP_SERVER_STATUS = Gauge("mcp_server_status", "MCP Server status (1=running, 0=stopped)")
MCP_AGENT_LOAD_TIME = Counter(
    "mcp_agent_load_seconds_total", "Time to load agents", ["agent_id"]
)


class CommandRequest(BaseModel):
    """Agent command request"""

    action: str
    parameters: Dict[str, Any] = {}


class CommandResponse(BaseModel):
    """Agent command response"""

    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class MCPServer:
    """
    MCP Server - Central coordination hub for autonomous trading agents

    Responsibilities:
    - Agent lifecycle management (start/stop/pause/resume)
    - Event bus coordination
    - Agent registry management
    - Health monitoring
    - Configuration management
    - API endpoints for control and monitoring

    The 10 RiseTrader Agents:
    1. SignalGeneratorAgent - Multi-strategy signal generation
    2. RiskManagerAgent - Pre-trade validation & position sizing
    3. ExecutionAgent - MT4 order execution
    4. MarketDataAgent - Real-time data streaming
    5. MLPredictionAgent - ML-powered forecasts
    6. RegimeDetectionAgent - Market regime classification
    7. PerformanceMonitorAgent - Real-time P&L tracking
    8. RiskOverseerAgent - System-wide risk monitoring
    9. StrategyOptimizerAgent - Continuous optimization
    10. DataQualityAgent - Pipeline validation
    """

    def __init__(
        self,
        config_path: str = "config/agents.yaml",
        redis_url: str = "redis://localhost:6379",
    ):
        """
        Initialize MCP Server

        Args:
            config_path: Path to agents.yaml configuration
            redis_url: Redis connection URL
        """
        self.config_path = config_path
        self.redis_url = redis_url

        # Load configuration
        self.config = self._load_config()

        # Core components
        self.event_bus: Optional[EventBus] = None
        self.agent_registry: Optional[AgentRegistry] = None

        # Agent instances: agent_id -> BaseAgent
        self.agents: Dict[str, BaseAgent] = {}

        # FastAPI app for HTTP endpoints
        self.app = FastAPI(
            title="RiseTrader MCP Server",
            description="Model Context Protocol server for agent coordination",
            version="1.0.0",
        )
        self._setup_routes()

        # Running state
        self.running = False

        self.logger = logger.bind(component="mcp_server")

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)
            logger.info("config_loaded", config_path=self.config_path)
            return config
        except Exception as e:
            logger.error("config_load_failed", config_path=self.config_path, error=str(e))
            raise

    async def start(self) -> None:
        """
        Start MCP Server

        1. Initialize EventBus
        2. Initialize AgentRegistry
        3. Load and start agents
        4. Set up signal handlers
        """
        if self.running:
            self.logger.warning("mcp_server_already_running")
            return

        try:
            self.logger.info("mcp_server_starting")

            # Initialize EventBus
            event_config = self.config.get("events", {})
            self.event_bus = EventBus(
                redis_url=self.redis_url,
                max_queue_size=event_config.get("max_queue_size", 10000),
                retry_attempts=event_config.get("retry_max_attempts", 3),
                retry_delay=event_config.get("retry_delay", 1.0),
                event_timeout=event_config.get("timeout", 30.0),
            )
            await self.event_bus.start()

            # Initialize AgentRegistry
            mcp_config = self.config.get("mcp_server", {})
            circuit_config = self.config.get("circuit_breaker", {})
            health_config = self.config.get("health_check", {})

            self.agent_registry = AgentRegistry(
                redis_url=self.redis_url,
                heartbeat_interval=mcp_config.get("heartbeat_interval", 30.0),
                heartbeat_timeout=mcp_config.get("heartbeat_interval", 30.0) * 3,
                circuit_breaker_enabled=circuit_config.get("enabled", True),
                failure_threshold=circuit_config.get("failure_threshold", 5),
                recovery_timeout=circuit_config.get("recovery_timeout", 60.0),
            )
            await self.agent_registry.start()

            # Load and start agents
            await self._load_agents()
            await self._start_agents()

            self.running = True
            MCP_SERVER_STATUS.set(1)

            # Set up signal handlers for graceful shutdown
            self._setup_signal_handlers()

            self.logger.info(
                "mcp_server_started",
                agents_loaded=len(self.agents),
                redis_url=self.redis_url,
            )

        except Exception as e:
            self.logger.error("mcp_server_start_failed", error=str(e), exc_info=True)
            MCP_SERVER_STATUS.set(0)
            raise

    async def stop(self) -> None:
        """
        Stop MCP Server

        1. Stop all agents
        2. Stop AgentRegistry
        3. Stop EventBus
        """
        if not self.running:
            return

        try:
            self.logger.info("mcp_server_stopping")
            self.running = False

            # Stop all agents
            await self._stop_agents()

            # Stop registry
            if self.agent_registry:
                await self.agent_registry.stop()

            # Stop event bus
            if self.event_bus:
                await self.event_bus.stop()

            MCP_SERVER_STATUS.set(0)

            self.logger.info("mcp_server_stopped")

        except Exception as e:
            self.logger.error("mcp_server_stop_failed", error=str(e), exc_info=True)

    async def _load_agents(self) -> None:
        """Load agent classes from configuration"""
        agents_config = self.config.get("agents", {})

        for agent_name, agent_config in agents_config.items():
            if not agent_config.get("enabled", True):
                self.logger.info("agent_disabled", agent_name=agent_name)
                continue

            try:
                # Import agent class
                agent_class_path = agent_config.get("class")
                if not agent_class_path:
                    self.logger.error("agent_class_missing", agent_name=agent_name)
                    continue

                agent_class = self._import_agent_class(agent_class_path)

                # Create agent instance
                agent_id = agent_name
                priority = agent_config.get("priority", 5)
                config = agent_config.get("config", {})

                # Add Redis URL to config
                config["redis_url"] = self.redis_url

                agent = agent_class(
                    agent_id=agent_id,
                    event_bus=self.event_bus,
                    agent_registry=self.agent_registry,
                    config=config,
                    priority=priority,
                )

                self.agents[agent_id] = agent

                self.logger.info(
                    "agent_loaded",
                    agent_id=agent_id,
                    agent_class=agent_class_path,
                    priority=priority,
                )

            except Exception as e:
                self.logger.error(
                    "agent_load_failed",
                    agent_name=agent_name,
                    error=str(e),
                    exc_info=True,
                )

    def _import_agent_class(self, class_path: str) -> Type[BaseAgent]:
        """
        Dynamically import agent class

        Args:
            class_path: Fully qualified class path (e.g., 'src.agents.execution.signal_generator.SignalGeneratorAgent')

        Returns:
            Agent class
        """
        try:
            # Split module and class name
            module_path, class_name = class_path.rsplit(".", 1)

            # Import module
            module = importlib.import_module(module_path)

            # Get class
            agent_class = getattr(module, class_name)

            return agent_class

        except Exception as e:
            self.logger.error(
                "agent_import_failed",
                class_path=class_path,
                error=str(e),
            )
            raise

    async def _start_agents(self) -> None:
        """Start all loaded agents in priority order"""
        # Sort agents by priority (lower number = higher priority)
        sorted_agents = sorted(self.agents.items(), key=lambda x: x[1].priority)

        for agent_id, agent in sorted_agents:
            try:
                await agent.start()
                self.logger.info("agent_started", agent_id=agent_id)
            except Exception as e:
                self.logger.error(
                    "agent_start_failed",
                    agent_id=agent_id,
                    error=str(e),
                    exc_info=True,
                )

    async def _stop_agents(self) -> None:
        """Stop all agents"""
        # Stop in reverse priority order
        sorted_agents = sorted(
            self.agents.items(), key=lambda x: x[1].priority, reverse=True
        )

        for agent_id, agent in sorted_agents:
            try:
                await agent.stop()
                self.logger.info("agent_stopped", agent_id=agent_id)
            except Exception as e:
                self.logger.error(
                    "agent_stop_failed",
                    agent_id=agent_id,
                    error=str(e),
                    exc_info=True,
                )

    async def pause_agent(self, agent_id: str) -> None:
        """
        Pause specific agent

        Args:
            agent_id: Agent to pause
        """
        if agent_id not in self.agents:
            raise ValueError(f"Agent not found: {agent_id}")

        await self.agents[agent_id].pause()
        self.logger.info("agent_paused", agent_id=agent_id)

    async def resume_agent(self, agent_id: str) -> None:
        """
        Resume specific agent

        Args:
            agent_id: Agent to resume
        """
        if agent_id not in self.agents:
            raise ValueError(f"Agent not found: {agent_id}")

        await self.agents[agent_id].resume()
        self.logger.info("agent_resumed", agent_id=agent_id)

    async def send_command(
        self, agent_id: str, action: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send command to agent

        Args:
            agent_id: Target agent
            action: Command action
            parameters: Command parameters

        Returns:
            Command result
        """
        if agent_id not in self.agents:
            raise ValueError(f"Agent not found: {agent_id}")

        agent = self.agents[agent_id]

        # Check if agent has command handler
        if not hasattr(agent, "handle_command"):
            raise ValueError(f"Agent does not support commands: {agent_id}")

        try:
            result = await agent.handle_command(action, parameters)
            return result
        except Exception as e:
            self.logger.error(
                "command_failed",
                agent_id=agent_id,
                action=action,
                error=str(e),
            )
            raise

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown"""

        def handle_shutdown(signum, frame):
            self.logger.info("shutdown_signal_received", signal=signum)
            asyncio.create_task(self.stop())

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

    def _setup_routes(self) -> None:
        """Set up FastAPI routes"""

        @self.app.get("/")
        async def root():
            """Root endpoint"""
            return {
                "name": "RiseTrader MCP Server",
                "version": "1.0.0",
                "status": "running" if self.running else "stopped",
            }

        @self.app.get("/health")
        async def health():
            """Health check endpoint"""
            if not self.running:
                raise HTTPException(status_code=503, detail="MCP Server not running")

            return {
                "status": "healthy",
                "agents_running": len(
                    [a for a in self.agents.values() if a.status == AgentStatus.RUNNING]
                ),
                "agents_total": len(self.agents),
            }

        @self.app.get("/agents")
        async def list_agents():
            """List all agents"""
            if not self.agent_registry:
                raise HTTPException(status_code=503, detail="Agent registry not initialized")

            agents = await self.agent_registry.list_agents()
            return {
                "agents": [agent.to_dict() for agent in agents],
                "total": len(agents),
            }

        @self.app.get("/agents/{agent_id}")
        async def get_agent(agent_id: str):
            """Get agent details"""
            if agent_id not in self.agents:
                raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

            agent = self.agents[agent_id]
            status = await agent.get_status()

            return status

        @self.app.post("/agents/{agent_id}/pause")
        async def pause_agent_endpoint(agent_id: str):
            """Pause agent"""
            try:
                await self.pause_agent(agent_id)
                return {"success": True, "message": f"Agent paused: {agent_id}"}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.post("/agents/{agent_id}/resume")
        async def resume_agent_endpoint(agent_id: str):
            """Resume agent"""
            try:
                await self.resume_agent(agent_id)
                return {"success": True, "message": f"Agent resumed: {agent_id}"}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.post("/agents/{agent_id}/command")
        async def send_command_endpoint(agent_id: str, request: CommandRequest):
            """Send command to agent"""
            try:
                result = await self.send_command(
                    agent_id, request.action, request.parameters
                )
                return CommandResponse(
                    success=True,
                    message="Command executed successfully",
                    data=result,
                )
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.get("/events/stats")
        async def event_stats():
            """Get event bus statistics"""
            if not self.event_bus:
                raise HTTPException(status_code=503, detail="Event bus not initialized")

            stats = await self.event_bus.get_queue_stats()
            return stats

        @self.app.get("/registry/stats")
        async def registry_stats():
            """Get agent registry statistics"""
            if not self.agent_registry:
                raise HTTPException(status_code=503, detail="Agent registry not initialized")

            stats = await self.agent_registry.get_stats()
            return stats

        # Mount Prometheus metrics endpoint
        metrics_app = make_asgi_app()
        self.app.mount("/metrics", metrics_app)


async def main():
    """
    Main entry point for MCP Server

    Run with: python -m src.agents.mcp_server
    """
    # Configure structured logging
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Get configuration from environment
    config_path = os.getenv("AGENT_CONFIG_PATH", "config/agents.yaml")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Create and start MCP server
    server = MCPServer(config_path=config_path, redis_url=redis_url)

    try:
        await server.start()

        # Run FastAPI app
        import uvicorn

        mcp_config = server.config.get("mcp_server", {})
        host = mcp_config.get("host", "0.0.0.0")
        port = mcp_config.get("port", 7000)

        config = uvicorn.Config(
            server.app,
            host=host,
            port=port,
            log_level="info",
        )
        uvicorn_server = uvicorn.Server(config)

        await uvicorn_server.serve()

    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
