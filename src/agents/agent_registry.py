"""
Agent Registry for MCP Server

Manages agent registration, discovery, and health monitoring.
Provides circuit breaker functionality for fault tolerance.

Performance Target: <100ms health check per agent
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
import structlog
from prometheus_client import Gauge, Counter

logger = structlog.get_logger(__name__)

# Prometheus metrics
AGENT_COUNT = Gauge("mcp_agents_total", "Total registered agents", ["status"])
AGENT_HEALTH_CHECK = Counter(
    "mcp_agent_health_checks_total",
    "Total agent health checks",
    ["agent_id", "status"],
)
CIRCUIT_BREAKER_STATE = Gauge(
    "mcp_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["agent_id"],
)


class AgentStatus(Enum):
    """Agent lifecycle status"""

    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    UNKNOWN = "unknown"


class CircuitBreakerState(Enum):
    """Circuit breaker states"""

    CLOSED = 0  # Normal operation
    OPEN = 1  # Failing, reject all requests
    HALF_OPEN = 2  # Testing recovery


@dataclass
class AgentMetadata:
    """
    Agent registration metadata

    Attributes:
        agent_id: Unique agent identifier
        agent_class: Fully qualified class name
        status: Current agent status
        priority: Agent execution priority (1-10)
        config: Agent-specific configuration
        registered_at: Registration timestamp
        last_heartbeat: Last health check timestamp
        error_count: Cumulative error count
        circuit_breaker_state: Current circuit breaker state
    """

    agent_id: str
    agent_class: str
    status: AgentStatus = AgentStatus.STARTING
    priority: int = 5
    config: Dict[str, Any] = field(default_factory=dict)
    registered_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    error_count: int = 0
    circuit_breaker_state: CircuitBreakerState = CircuitBreakerState.CLOSED
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "agent_id": self.agent_id,
            "agent_class": self.agent_class,
            "status": self.status.value,
            "priority": self.priority,
            "config": self.config,
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
            "error_count": self.error_count,
            "circuit_breaker_state": self.circuit_breaker_state.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMetadata":
        """Deserialize from dictionary"""
        return cls(
            agent_id=data["agent_id"],
            agent_class=data["agent_class"],
            status=AgentStatus(data.get("status", AgentStatus.UNKNOWN.value)),
            priority=data.get("priority", 5),
            config=data.get("config", {}),
            registered_at=data.get("registered_at", time.time()),
            last_heartbeat=data.get("last_heartbeat", time.time()),
            error_count=data.get("error_count", 0),
            circuit_breaker_state=CircuitBreakerState(
                data.get("circuit_breaker_state", CircuitBreakerState.CLOSED.value)
            ),
            metadata=data.get("metadata", {}),
        )


class CircuitBreaker:
    """
    Circuit breaker for agent fault tolerance

    Protects system from cascading failures by opening circuit after
    threshold failures and allowing controlled recovery testing.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
    ):
        """
        Initialize circuit breaker

        Args:
            failure_threshold: Failures before opening circuit
            recovery_timeout: Time before testing recovery (seconds)
            half_open_max_calls: Max calls in half-open state
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_calls = 0

    def record_success(self) -> None:
        """Record successful operation"""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                self._close()
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitBreakerState.HALF_OPEN:
            self._open()
        elif self.failure_count >= self.failure_threshold:
            self._open()

    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)"""
        if self.state == CircuitBreakerState.OPEN:
            # Check if recovery timeout elapsed
            if (
                self.last_failure_time
                and time.time() - self.last_failure_time >= self.recovery_timeout
            ):
                self._half_open()

        return self.state == CircuitBreakerState.OPEN

    def _open(self) -> None:
        """Open circuit (block all requests)"""
        self.state = CircuitBreakerState.OPEN
        self.last_failure_time = time.time()

    def _half_open(self) -> None:
        """Enter half-open state (test recovery)"""
        self.state = CircuitBreakerState.HALF_OPEN
        self.half_open_calls = 0

    def _close(self) -> None:
        """Close circuit (normal operation)"""
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.half_open_calls = 0


class AgentRegistry:
    """
    Agent registration and discovery service

    Features:
    - Agent registration and metadata storage
    - Health monitoring with heartbeat checks
    - Circuit breaker for fault tolerance
    - Agent discovery and lookup
    - Status tracking and metrics
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        heartbeat_interval: float = 30.0,
        heartbeat_timeout: float = 90.0,
        circuit_breaker_enabled: bool = True,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ):
        """
        Initialize AgentRegistry

        Args:
            redis_url: Redis connection URL for distributed state
            heartbeat_interval: Health check interval (seconds)
            heartbeat_timeout: Consider agent dead after timeout (seconds)
            circuit_breaker_enabled: Enable circuit breaker protection
            failure_threshold: Failures before circuit opens
            recovery_timeout: Recovery test timeout (seconds)
        """
        self.redis_url = redis_url
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.circuit_breaker_enabled = circuit_breaker_enabled

        # Redis client
        self.redis_client: Optional[redis.Redis] = None

        # Local registry: agent_id -> AgentMetadata
        self.agents: Dict[str, AgentMetadata] = {}

        # Circuit breakers: agent_id -> CircuitBreaker
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}

        # Health check task
        self.health_check_task: Optional[asyncio.Task] = None
        self.running = False

        self.logger = logger.bind(component="agent_registry")

        # Circuit breaker config
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

    async def connect(self) -> None:
        """Establish Redis connection"""
        try:
            self.redis_client = await redis.from_url(
                self.redis_url, encoding="utf-8", decode_responses=True
            )
            await self.redis_client.ping()
            self.logger.info("agent_registry_connected", redis_url=self.redis_url)
        except Exception as e:
            self.logger.error("agent_registry_connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
        self.logger.info("agent_registry_disconnected")

    async def start(self) -> None:
        """Start registry health monitoring"""
        if self.running:
            return

        await self.connect()
        self.running = True

        # Start health check task
        self.health_check_task = asyncio.create_task(
            self._health_check_loop(), name="health_check_loop"
        )

        self.logger.info("agent_registry_started")

    async def stop(self) -> None:
        """Stop registry health monitoring"""
        if not self.running:
            return

        self.running = False

        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass

        await self.disconnect()
        self.logger.info("agent_registry_stopped")

    async def register(
        self,
        agent_id: str,
        agent_class: str,
        priority: int = 5,
        config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentMetadata:
        """
        Register new agent

        Args:
            agent_id: Unique agent identifier
            agent_class: Fully qualified class name
            priority: Execution priority (1-10)
            config: Agent configuration
            metadata: Additional metadata

        Returns:
            AgentMetadata: Registered agent metadata
        """
        agent_metadata = AgentMetadata(
            agent_id=agent_id,
            agent_class=agent_class,
            priority=priority,
            config=config or {},
            metadata=metadata or {},
            status=AgentStatus.STARTING,
        )

        # Store locally
        self.agents[agent_id] = agent_metadata

        # Create circuit breaker
        if self.circuit_breaker_enabled:
            self.circuit_breakers[agent_id] = CircuitBreaker(
                failure_threshold=self.failure_threshold,
                recovery_timeout=self.recovery_timeout,
            )

        # Store in Redis for distributed access
        if self.redis_client:
            key = f"mcp:agent:{agent_id}"
            await self.redis_client.set(key, str(agent_metadata.to_dict()))

        # Update metrics
        AGENT_COUNT.labels(status=agent_metadata.status.value).inc()

        self.logger.info(
            "agent_registered",
            agent_id=agent_id,
            agent_class=agent_class,
            priority=priority,
        )

        return agent_metadata

    async def unregister(self, agent_id: str) -> None:
        """
        Unregister agent

        Args:
            agent_id: Agent to unregister
        """
        if agent_id not in self.agents:
            self.logger.warning("agent_not_found", agent_id=agent_id)
            return

        agent = self.agents[agent_id]

        # Update metrics
        AGENT_COUNT.labels(status=agent.status.value).dec()

        # Remove from local storage
        del self.agents[agent_id]

        # Remove circuit breaker
        if agent_id in self.circuit_breakers:
            del self.circuit_breakers[agent_id]

        # Remove from Redis
        if self.redis_client:
            key = f"mcp:agent:{agent_id}"
            await self.redis_client.delete(key)

        self.logger.info("agent_unregistered", agent_id=agent_id)

    async def update_status(self, agent_id: str, status: AgentStatus) -> None:
        """
        Update agent status

        Args:
            agent_id: Agent identifier
            status: New status
        """
        if agent_id not in self.agents:
            self.logger.warning("agent_not_found", agent_id=agent_id)
            return

        agent = self.agents[agent_id]
        old_status = agent.status

        # Update metrics
        AGENT_COUNT.labels(status=old_status.value).dec()
        AGENT_COUNT.labels(status=status.value).inc()

        agent.status = status

        # Update Redis
        if self.redis_client:
            key = f"mcp:agent:{agent_id}"
            await self.redis_client.set(key, str(agent.to_dict()))

        self.logger.info(
            "agent_status_updated",
            agent_id=agent_id,
            old_status=old_status.value,
            new_status=status.value,
        )

    async def heartbeat(self, agent_id: str) -> bool:
        """
        Record agent heartbeat

        Args:
            agent_id: Agent sending heartbeat

        Returns:
            bool: True if heartbeat recorded successfully
        """
        if agent_id not in self.agents:
            self.logger.warning("heartbeat_from_unknown_agent", agent_id=agent_id)
            return False

        agent = self.agents[agent_id]
        agent.last_heartbeat = time.time()

        # Record circuit breaker success
        if agent_id in self.circuit_breakers:
            self.circuit_breakers[agent_id].record_success()
            agent.circuit_breaker_state = self.circuit_breakers[agent_id].state

            # Update metric
            CIRCUIT_BREAKER_STATE.labels(agent_id=agent_id).set(
                agent.circuit_breaker_state.value
            )

        # Update Redis
        if self.redis_client:
            key = f"mcp:agent:{agent_id}:heartbeat"
            await self.redis_client.set(
                key, str(agent.last_heartbeat), ex=int(self.heartbeat_timeout)
            )

        AGENT_HEALTH_CHECK.labels(agent_id=agent_id, status="success").inc()

        return True

    async def record_error(self, agent_id: str, error: str) -> None:
        """
        Record agent error

        Args:
            agent_id: Agent with error
            error: Error message
        """
        if agent_id not in self.agents:
            return

        agent = self.agents[agent_id]
        agent.error_count += 1

        # Update circuit breaker
        if agent_id in self.circuit_breakers:
            self.circuit_breakers[agent_id].record_failure()
            agent.circuit_breaker_state = self.circuit_breakers[agent_id].state

            # Update metric
            CIRCUIT_BREAKER_STATE.labels(agent_id=agent_id).set(
                agent.circuit_breaker_state.value
            )

            if self.circuit_breakers[agent_id].is_open():
                await self.update_status(agent_id, AgentStatus.FAILED)

        AGENT_HEALTH_CHECK.labels(agent_id=agent_id, status="error").inc()

        self.logger.error(
            "agent_error_recorded",
            agent_id=agent_id,
            error_count=agent.error_count,
            circuit_state=agent.circuit_breaker_state.name,
            error=error,
        )

    def is_circuit_open(self, agent_id: str) -> bool:
        """
        Check if agent's circuit breaker is open

        Args:
            agent_id: Agent to check

        Returns:
            bool: True if circuit is open (agent unavailable)
        """
        if agent_id not in self.circuit_breakers:
            return False

        return self.circuit_breakers[agent_id].is_open()

    async def get_agent(self, agent_id: str) -> Optional[AgentMetadata]:
        """
        Get agent metadata

        Args:
            agent_id: Agent identifier

        Returns:
            AgentMetadata if found, None otherwise
        """
        return self.agents.get(agent_id)

    async def list_agents(
        self, status: Optional[AgentStatus] = None
    ) -> List[AgentMetadata]:
        """
        List all registered agents

        Args:
            status: Filter by status (optional)

        Returns:
            List of agent metadata
        """
        agents = list(self.agents.values())

        if status:
            agents = [agent for agent in agents if agent.status == status]

        # Sort by priority
        agents.sort(key=lambda a: a.priority)

        return agents

    async def get_agents_by_priority(self, priority: int) -> List[AgentMetadata]:
        """
        Get agents with specific priority

        Args:
            priority: Priority level (1-10)

        Returns:
            List of agents with matching priority
        """
        return [
            agent for agent in self.agents.values() if agent.priority == priority
        ]

    async def _health_check_loop(self) -> None:
        """Background health check loop"""
        while self.running:
            try:
                await self._check_agent_health()
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                self.logger.error("health_check_loop_error", error=str(e))

    async def _check_agent_health(self) -> None:
        """Check health of all registered agents"""
        current_time = time.time()

        for agent_id, agent in list(self.agents.items()):
            time_since_heartbeat = current_time - agent.last_heartbeat

            if time_since_heartbeat > self.heartbeat_timeout:
                self.logger.warning(
                    "agent_heartbeat_timeout",
                    agent_id=agent_id,
                    time_since_heartbeat=time_since_heartbeat,
                    timeout=self.heartbeat_timeout,
                )

                if agent.status != AgentStatus.FAILED:
                    await self.update_status(agent_id, AgentStatus.FAILED)
                    await self.record_error(agent_id, "Heartbeat timeout")

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get registry statistics

        Returns:
            Dictionary with agent counts and status
        """
        status_counts = {}
        for status in AgentStatus:
            count = sum(1 for a in self.agents.values() if a.status == status)
            status_counts[status.value] = count

        circuit_states = {}
        for agent_id, breaker in self.circuit_breakers.items():
            circuit_states[agent_id] = breaker.state.name

        return {
            "total_agents": len(self.agents),
            "status_counts": status_counts,
            "circuit_breaker_states": circuit_states,
            "running": self.running,
        }
