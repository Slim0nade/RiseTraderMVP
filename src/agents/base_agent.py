"""
Base Agent Class for RiseTrader

Abstract base class for all trading agents. Provides core functionality:
- Event subscription and publishing
- Lifecycle management (start/stop)
- Health monitoring and heartbeat
- Error handling and circuit breaker integration
- Configuration management
- Shared context access via Redis

All 10 trading agents inherit from this base class.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
import structlog
from prometheus_client import Counter, Histogram

from .agent_registry import AgentRegistry, AgentStatus, AgentMetadata
from .event_bus import Event, EventBus, EventPriority

logger = structlog.get_logger(__name__)

# Prometheus metrics
AGENT_EVENTS_PROCESSED = Counter(
    "agent_events_processed_total",
    "Total events processed by agent",
    ["agent_id", "event_type"],
)
AGENT_PROCESSING_TIME = Histogram(
    "agent_event_processing_seconds",
    "Agent event processing time",
    ["agent_id", "event_type"],
)
AGENT_ERRORS = Counter(
    "agent_errors_total",
    "Total agent errors",
    ["agent_id", "error_type"],
)


class BaseAgent(ABC):
    """
    Abstract base class for all RiseTrader agents

    Provides:
    - Event-driven communication via EventBus
    - Registration with AgentRegistry
    - Health monitoring with heartbeat
    - Shared context via Redis
    - Lifecycle management (start/stop)
    - Error handling with circuit breaker integration

    Subclasses must implement:
    - initialize(): Agent-specific setup
    - process_event(): Handle incoming events
    - cleanup(): Agent-specific cleanup
    """

    def __init__(
        self,
        agent_id: str,
        event_bus: EventBus,
        agent_registry: AgentRegistry,
        config: Optional[Dict[str, Any]] = None,
        priority: int = 5,
    ):
        """
        Initialize base agent

        Args:
            agent_id: Unique agent identifier
            event_bus: Event bus for communication
            agent_registry: Agent registry for registration
            config: Agent-specific configuration
            priority: Execution priority (1-10, lower = higher priority)
        """
        self.agent_id = agent_id
        self.event_bus = event_bus
        self.agent_registry = agent_registry
        self.config = config or {}
        self.priority = priority

        # Agent state
        self.status = AgentStatus.STOPPED
        self.running = False
        self.metadata: Optional[AgentMetadata] = None

        # Redis for shared context
        self.redis_client: Optional[redis.Redis] = None
        self.redis_url = self.config.get("redis_url", "redis://localhost:6379")

        # Heartbeat configuration
        self.heartbeat_interval = self.config.get("heartbeat_interval", 30.0)
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Event subscriptions
        self._subscribed_events: List[str] = []

        # Processing statistics
        self.events_processed = 0
        self.errors_count = 0
        self.start_time: Optional[float] = None

        # Logger with agent context
        self.logger = logger.bind(agent_id=agent_id, agent_class=self.__class__.__name__)

    async def start(self) -> None:
        """
        Start agent lifecycle

        1. Register with registry
        2. Connect to Redis
        3. Subscribe to events
        4. Initialize agent-specific components
        5. Start heartbeat
        """
        if self.running:
            self.logger.warning("agent_already_running")
            return

        try:
            self.logger.info("agent_starting")
            self.status = AgentStatus.STARTING
            self.start_time = time.time()

            # Register with agent registry
            self.metadata = await self.agent_registry.register(
                agent_id=self.agent_id,
                agent_class=f"{self.__class__.__module__}.{self.__class__.__name__}",
                priority=self.priority,
                config=self.config,
            )

            # Connect to Redis for shared context
            await self._connect_redis()

            # Subscribe to events
            await self._subscribe_events()

            # Agent-specific initialization
            await self.initialize()

            # Update status
            self.running = True
            self.status = AgentStatus.RUNNING
            await self.agent_registry.update_status(self.agent_id, AgentStatus.RUNNING)

            # Start heartbeat
            self._heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(), name=f"{self.agent_id}_heartbeat"
            )

            self.logger.info(
                "agent_started",
                subscribed_events=self._subscribed_events,
                priority=self.priority,
            )

        except Exception as e:
            self.logger.error("agent_start_failed", error=str(e), exc_info=True)
            self.status = AgentStatus.FAILED
            await self.agent_registry.update_status(self.agent_id, AgentStatus.FAILED)
            await self.agent_registry.record_error(self.agent_id, str(e))
            raise

    async def stop(self) -> None:
        """
        Stop agent lifecycle

        1. Stop heartbeat
        2. Unsubscribe from events
        3. Cleanup agent-specific components
        4. Disconnect Redis
        5. Unregister from registry
        """
        if not self.running:
            return

        try:
            self.logger.info("agent_stopping")
            self.status = AgentStatus.STOPPING
            self.running = False

            # Stop heartbeat
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

            # Unsubscribe from events
            await self._unsubscribe_events()

            # Agent-specific cleanup
            await self.cleanup()

            # Disconnect Redis
            await self._disconnect_redis()

            # Unregister
            await self.agent_registry.unregister(self.agent_id)

            self.status = AgentStatus.STOPPED

            uptime = time.time() - self.start_time if self.start_time else 0
            self.logger.info(
                "agent_stopped",
                events_processed=self.events_processed,
                errors=self.errors_count,
                uptime_seconds=uptime,
            )

        except Exception as e:
            self.logger.error("agent_stop_failed", error=str(e), exc_info=True)
            self.status = AgentStatus.FAILED

    async def pause(self) -> None:
        """Pause agent processing (stop processing events but maintain connection)"""
        if self.status != AgentStatus.RUNNING:
            return

        self.status = AgentStatus.PAUSED
        await self.agent_registry.update_status(self.agent_id, AgentStatus.PAUSED)
        self.logger.info("agent_paused")

    async def resume(self) -> None:
        """Resume agent processing"""
        if self.status != AgentStatus.PAUSED:
            return

        self.status = AgentStatus.RUNNING
        await self.agent_registry.update_status(self.agent_id, AgentStatus.RUNNING)
        self.logger.info("agent_resumed")

    @abstractmethod
    async def initialize(self) -> None:
        """
        Agent-specific initialization

        Called during start() after registration and event subscription.
        Implement to set up agent-specific components, load models, etc.
        """
        pass

    @abstractmethod
    async def process_event(self, event: Event) -> None:
        """
        Process incoming event

        Called when subscribed event is received.
        Implement agent-specific event processing logic.

        Args:
            event: Event to process
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """
        Agent-specific cleanup

        Called during stop() before unregistration.
        Implement to clean up resources, save state, etc.
        """
        pass

    def subscribe_to_event(self, event_type: str) -> None:
        """
        Declare event type subscription

        Call in initialize() to subscribe to events.

        Args:
            event_type: Event type to subscribe to (e.g., 'new_tick')
        """
        self._subscribed_events.append(event_type)

    async def _subscribe_events(self) -> None:
        """Subscribe to declared event types"""
        for event_type in self._subscribed_events:
            self.event_bus.subscribe(event_type, self.agent_id, self._handle_event)

        self.logger.debug(
            "events_subscribed",
            event_types=self._subscribed_events,
        )

    async def _unsubscribe_events(self) -> None:
        """Unsubscribe from all events"""
        for event_type in self._subscribed_events:
            self.event_bus.unsubscribe(event_type, self.agent_id)

        self.logger.debug("events_unsubscribed")

    async def _handle_event(self, event: Event) -> None:
        """
        Internal event handler wrapper

        Adds error handling, metrics, and circuit breaker integration.

        Args:
            event: Event to handle
        """
        # Check if circuit is open
        if self.agent_registry.is_circuit_open(self.agent_id):
            self.logger.warning(
                "event_rejected_circuit_open",
                event_id=event.event_id,
                event_type=event.event_type,
            )
            return

        # Check if paused
        if self.status == AgentStatus.PAUSED:
            self.logger.debug(
                "event_skipped_paused",
                event_id=event.event_id,
                event_type=event.event_type,
            )
            return

        start_time = time.time()

        try:
            # Process event
            await self.process_event(event)

            # Update metrics
            self.events_processed += 1
            processing_time = time.time() - start_time

            AGENT_EVENTS_PROCESSED.labels(
                agent_id=self.agent_id, event_type=event.event_type
            ).inc()

            AGENT_PROCESSING_TIME.labels(
                agent_id=self.agent_id, event_type=event.event_type
            ).observe(processing_time)

            # Record success with registry (for circuit breaker)
            await self.agent_registry.heartbeat(self.agent_id)

            self.logger.debug(
                "event_processed",
                event_id=event.event_id,
                event_type=event.event_type,
                processing_time=processing_time,
            )

        except Exception as e:
            self.errors_count += 1
            processing_time = time.time() - start_time

            AGENT_ERRORS.labels(
                agent_id=self.agent_id, error_type=type(e).__name__
            ).inc()

            # Record error with registry (for circuit breaker)
            await self.agent_registry.record_error(self.agent_id, str(e))

            self.logger.error(
                "event_processing_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                processing_time=processing_time,
                error=str(e),
                exc_info=True,
            )

    async def publish_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        priority: EventPriority = EventPriority.NORMAL,
        correlation_id: Optional[str] = None,
    ) -> None:
        """
        Publish event to event bus

        Args:
            event_type: Event type (e.g., 'signal_generated')
            data: Event payload
            priority: Event priority
            correlation_id: For tracking related events
        """
        event = Event(
            event_type=event_type,
            source_agent=self.agent_id,
            data=data,
            priority=priority,
            correlation_id=correlation_id,
        )

        try:
            await self.event_bus.publish(event)

            self.logger.debug(
                "event_published",
                event_id=event.event_id,
                event_type=event_type,
                priority=priority.name,
            )

        except Exception as e:
            self.logger.error(
                "event_publish_failed",
                event_type=event_type,
                error=str(e),
            )
            raise

    async def _connect_redis(self) -> None:
        """Connect to Redis for shared context"""
        try:
            self.redis_client = await redis.from_url(
                self.redis_url, encoding="utf-8", decode_responses=True
            )
            await self.redis_client.ping()
            self.logger.debug("redis_connected")
        except Exception as e:
            self.logger.error("redis_connection_failed", error=str(e))
            raise

    async def _disconnect_redis(self) -> None:
        """Disconnect from Redis"""
        if self.redis_client:
            await self.redis_client.close()
            self.logger.debug("redis_disconnected")

    async def set_context(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set shared context value in Redis

        Args:
            key: Context key (automatically prefixed with agent_id)
            value: Value to store (must be JSON serializable)
            ttl: Time to live in seconds (optional)
        """
        if not self.redis_client:
            self.logger.warning("redis_not_connected")
            return

        full_key = f"mcp:context:{self.agent_id}:{key}"

        try:
            if ttl:
                await self.redis_client.set(full_key, str(value), ex=ttl)
            else:
                await self.redis_client.set(full_key, str(value))

            self.logger.debug("context_set", key=key, ttl=ttl)

        except Exception as e:
            self.logger.error("context_set_failed", key=key, error=str(e))

    async def get_context(self, key: str, default: Any = None) -> Any:
        """
        Get shared context value from Redis

        Args:
            key: Context key (automatically prefixed with agent_id)
            default: Default value if key not found

        Returns:
            Stored value or default
        """
        if not self.redis_client:
            self.logger.warning("redis_not_connected")
            return default

        full_key = f"mcp:context:{self.agent_id}:{key}"

        try:
            value = await self.redis_client.get(full_key)
            return value if value is not None else default

        except Exception as e:
            self.logger.error("context_get_failed", key=key, error=str(e))
            return default

    async def get_shared_context(self, agent_id: str, key: str, default: Any = None) -> Any:
        """
        Get context value from another agent

        Args:
            agent_id: Other agent's ID
            key: Context key
            default: Default value if key not found

        Returns:
            Stored value or default
        """
        if not self.redis_client:
            self.logger.warning("redis_not_connected")
            return default

        full_key = f"mcp:context:{agent_id}:{key}"

        try:
            value = await self.redis_client.get(full_key)
            return value if value is not None else default

        except Exception as e:
            self.logger.error(
                "shared_context_get_failed",
                agent_id=agent_id,
                key=key,
                error=str(e),
            )
            return default

    async def _heartbeat_loop(self) -> None:
        """Background heartbeat loop"""
        while self.running:
            try:
                await self.agent_registry.heartbeat(self.agent_id)
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("heartbeat_failed", error=str(e))
                await asyncio.sleep(self.heartbeat_interval)

    async def get_status(self) -> Dict[str, Any]:
        """
        Get agent status information

        Returns:
            Dictionary with agent status, metrics, and configuration
        """
        uptime = time.time() - self.start_time if self.start_time else 0

        return {
            "agent_id": self.agent_id,
            "agent_class": f"{self.__class__.__module__}.{self.__class__.__name__}",
            "status": self.status.value,
            "running": self.running,
            "priority": self.priority,
            "events_processed": self.events_processed,
            "errors_count": self.errors_count,
            "uptime_seconds": uptime,
            "subscribed_events": self._subscribed_events,
            "circuit_breaker_open": self.agent_registry.is_circuit_open(self.agent_id),
        }
