"""
Event Bus Implementation for MCP Server

High-performance async event bus using Redis pub/sub for inter-agent communication.
Supports event routing, message queuing, and backpressure handling.

Performance Target: <50ms event processing
Throughput: 100+ events/second
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

import redis.asyncio as redis
import structlog
from prometheus_client import Counter, Histogram, Gauge

logger = structlog.get_logger(__name__)

# Prometheus metrics
EVENT_PUBLISHED = Counter(
    "mcp_events_published_total", "Total events published", ["event_type"]
)
EVENT_CONSUMED = Counter(
    "mcp_events_consumed_total", "Total events consumed", ["event_type", "agent_id"]
)
EVENT_PROCESSING_TIME = Histogram(
    "mcp_event_processing_seconds", "Event processing time", ["event_type"]
)
EVENT_QUEUE_SIZE = Gauge("mcp_event_queue_size", "Current event queue size")


class EventPriority(Enum):
    """Event priority levels for queue ordering"""

    CRITICAL = 0  # Emergency stops, system failures
    HIGH = 1  # Trade execution, risk alerts
    NORMAL = 2  # Signals, data updates
    LOW = 3  # Performance reports, optimization


class EventStatus(Enum):
    """Event lifecycle status"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


@dataclass
class Event:
    """
    Standard event structure for agent communication

    Attributes:
        event_id: Unique event identifier
        event_type: Event category (e.g., 'new_tick', 'signal_generated')
        source_agent: Agent that emitted the event
        data: Event payload
        priority: Event priority for queue ordering
        timestamp: Event creation timestamp
        correlation_id: For tracking related events
        metadata: Additional context
    """

    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    source_agent: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source_agent": self.source_agent,
            "data": self.data,
            "priority": self.priority.value,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Deserialize event from dictionary"""
        priority = EventPriority(data.get("priority", EventPriority.NORMAL.value))
        return cls(
            event_id=data.get("event_id", str(uuid4())),
            event_type=data.get("event_type", ""),
            source_agent=data.get("source_agent", ""),
            data=data.get("data", {}),
            priority=priority,
            timestamp=data.get("timestamp", time.time()),
            correlation_id=data.get("correlation_id"),
            metadata=data.get("metadata", {}),
        )

    def to_json(self) -> str:
        """Serialize event to JSON"""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "Event":
        """Deserialize event from JSON"""
        return cls.from_dict(json.loads(json_str))


class EventBus:
    """
    High-performance async event bus for agent coordination

    Features:
    - Redis pub/sub for message distribution
    - Priority queue support
    - Backpressure handling
    - Dead letter queue for failed events
    - Circuit breaker integration
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        max_queue_size: int = 10000,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
        event_timeout: float = 30.0,
    ):
        """
        Initialize EventBus

        Args:
            redis_url: Redis connection URL
            max_queue_size: Maximum events in queue before backpressure
            retry_attempts: Number of retries for failed events
            retry_delay: Delay between retries (seconds)
            event_timeout: Event processing timeout (seconds)
        """
        self.redis_url = redis_url
        self.max_queue_size = max_queue_size
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.event_timeout = event_timeout

        # Redis connections
        self.redis_client: Optional[redis.Redis] = None
        self.redis_pubsub: Optional[redis.client.PubSub] = None

        # Event handlers: event_type -> [(agent_id, handler_func)]
        self.handlers: Dict[str, List[tuple[str, Callable]]] = {}

        # Event queues by priority
        self.event_queues: Dict[EventPriority, asyncio.Queue] = {
            priority: asyncio.Queue(maxsize=max_queue_size)
            for priority in EventPriority
        }

        # Dead letter queue for failed events
        self.dead_letter_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

        # Running state
        self.running = False
        self._tasks: List[asyncio.Task] = []

        self.logger = logger.bind(component="event_bus")

    async def connect(self) -> None:
        """Establish Redis connections"""
        try:
            self.redis_client = await redis.from_url(
                self.redis_url, encoding="utf-8", decode_responses=True
            )
            await self.redis_client.ping()

            self.redis_pubsub = self.redis_client.pubsub()

            self.logger.info("event_bus_connected", redis_url=self.redis_url)
        except Exception as e:
            self.logger.error("event_bus_connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Close Redis connections"""
        if self.redis_pubsub:
            await self.redis_pubsub.close()
        if self.redis_client:
            await self.redis_client.close()
        self.logger.info("event_bus_disconnected")

    async def start(self) -> None:
        """Start event bus processing"""
        if self.running:
            self.logger.warning("event_bus_already_running")
            return

        await self.connect()
        self.running = True

        # Start event processing tasks for each priority
        for priority in EventPriority:
            task = asyncio.create_task(
                self._process_queue(priority), name=f"process_queue_{priority.name}"
            )
            self._tasks.append(task)

        # Start Redis subscriber task
        subscriber_task = asyncio.create_task(
            self._subscribe_redis(), name="redis_subscriber"
        )
        self._tasks.append(subscriber_task)

        self.logger.info("event_bus_started")

    async def stop(self) -> None:
        """Stop event bus processing"""
        if not self.running:
            return

        self.running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        await self.disconnect()
        self.logger.info("event_bus_stopped")

    def subscribe(
        self, event_type: str, agent_id: str, handler: Callable
    ) -> None:
        """
        Subscribe agent to event type

        Args:
            event_type: Event type to subscribe to (e.g., 'new_tick')
            agent_id: Subscribing agent identifier
            handler: Async callback function to handle event
        """
        if event_type not in self.handlers:
            self.handlers[event_type] = []

        self.handlers[event_type].append((agent_id, handler))

        self.logger.info(
            "agent_subscribed",
            event_type=event_type,
            agent_id=agent_id,
            handler_count=len(self.handlers[event_type]),
        )

    def unsubscribe(self, event_type: str, agent_id: str) -> None:
        """
        Unsubscribe agent from event type

        Args:
            event_type: Event type to unsubscribe from
            agent_id: Unsubscribing agent identifier
        """
        if event_type in self.handlers:
            self.handlers[event_type] = [
                (aid, handler)
                for aid, handler in self.handlers[event_type]
                if aid != agent_id
            ]

            self.logger.info(
                "agent_unsubscribed",
                event_type=event_type,
                agent_id=agent_id,
            )

    async def publish(self, event: Event) -> None:
        """
        Publish event to all subscribed agents

        Args:
            event: Event to publish

        Raises:
            asyncio.QueueFull: If queue is at max capacity (backpressure)
        """
        start_time = time.time()

        try:
            # Check queue size for backpressure
            queue = self.event_queues[event.priority]
            if queue.qsize() >= self.max_queue_size * 0.9:
                self.logger.warning(
                    "event_queue_near_capacity",
                    priority=event.priority.name,
                    size=queue.qsize(),
                    max_size=self.max_queue_size,
                )

            # Add to priority queue
            await queue.put(event)

            # Publish to Redis for distributed subscribers
            if self.redis_client:
                channel = f"mcp:events:{event.event_type}"
                await self.redis_client.publish(channel, event.to_json())

            # Update metrics
            EVENT_PUBLISHED.labels(event_type=event.event_type).inc()
            EVENT_QUEUE_SIZE.inc()

            processing_time = time.time() - start_time
            self.logger.debug(
                "event_published",
                event_id=event.event_id,
                event_type=event.event_type,
                source=event.source_agent,
                priority=event.priority.name,
                processing_time=processing_time,
            )

        except asyncio.QueueFull:
            self.logger.error(
                "event_queue_full",
                event_type=event.event_type,
                priority=event.priority.name,
            )
            raise
        except Exception as e:
            self.logger.error(
                "event_publish_failed",
                event_id=event.event_id,
                error=str(e),
            )
            raise

    async def _process_queue(self, priority: EventPriority) -> None:
        """
        Process events from priority queue

        Args:
            priority: Queue priority level to process
        """
        queue = self.event_queues[priority]

        while self.running:
            try:
                # Get event from queue with timeout
                event = await asyncio.wait_for(queue.get(), timeout=1.0)

                # Process event handlers
                await self._dispatch_event(event)

                queue.task_done()
                EVENT_QUEUE_SIZE.dec()

            except asyncio.TimeoutError:
                # No events in queue, continue
                continue
            except Exception as e:
                self.logger.error(
                    "queue_processing_error",
                    priority=priority.name,
                    error=str(e),
                )

    async def _dispatch_event(self, event: Event) -> None:
        """
        Dispatch event to subscribed handlers

        Args:
            event: Event to dispatch
        """
        start_time = time.time()

        if event.event_type not in self.handlers:
            self.logger.debug(
                "no_handlers_for_event",
                event_type=event.event_type,
                event_id=event.event_id,
            )
            return

        handlers = self.handlers[event.event_type]
        tasks = []

        # Create tasks for all handlers
        for agent_id, handler in handlers:
            task = asyncio.create_task(
                self._execute_handler(event, agent_id, handler)
            )
            tasks.append(task)

        # Wait for all handlers to complete (with timeout)
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.event_timeout,
            )

            processing_time = time.time() - start_time
            EVENT_PROCESSING_TIME.labels(event_type=event.event_type).observe(
                processing_time
            )

            self.logger.debug(
                "event_dispatched",
                event_id=event.event_id,
                event_type=event.event_type,
                handler_count=len(handlers),
                processing_time=processing_time,
            )

        except asyncio.TimeoutError:
            self.logger.error(
                "event_dispatch_timeout",
                event_id=event.event_id,
                event_type=event.event_type,
                timeout=self.event_timeout,
            )

    async def _execute_handler(
        self, event: Event, agent_id: str, handler: Callable
    ) -> None:
        """
        Execute single event handler with retry logic

        Args:
            event: Event to process
            agent_id: Handler's agent identifier
            handler: Handler callback function
        """
        for attempt in range(self.retry_attempts):
            try:
                await handler(event)

                EVENT_CONSUMED.labels(
                    event_type=event.event_type, agent_id=agent_id
                ).inc()

                self.logger.debug(
                    "handler_executed",
                    event_id=event.event_id,
                    agent_id=agent_id,
                    attempt=attempt + 1,
                )
                return

            except Exception as e:
                self.logger.error(
                    "handler_execution_failed",
                    event_id=event.event_id,
                    agent_id=agent_id,
                    attempt=attempt + 1,
                    error=str(e),
                )

                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    # Max retries reached, send to dead letter queue
                    await self._send_to_dead_letter(event, agent_id, str(e))

    async def _send_to_dead_letter(
        self, event: Event, agent_id: str, error: str
    ) -> None:
        """
        Send failed event to dead letter queue

        Args:
            event: Failed event
            agent_id: Handler that failed
            error: Error message
        """
        try:
            dead_letter_event = {
                "event": event.to_dict(),
                "agent_id": agent_id,
                "error": error,
                "timestamp": time.time(),
            }

            await self.dead_letter_queue.put(dead_letter_event)

            self.logger.warning(
                "event_sent_to_dead_letter",
                event_id=event.event_id,
                agent_id=agent_id,
                error=error,
            )

        except asyncio.QueueFull:
            self.logger.error(
                "dead_letter_queue_full",
                event_id=event.event_id,
            )

    async def _subscribe_redis(self) -> None:
        """Subscribe to Redis pub/sub channels"""
        if not self.redis_pubsub:
            return

        # Subscribe to all event type channels
        await self.redis_pubsub.psubscribe("mcp:events:*")

        while self.running:
            try:
                message = await self.redis_pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )

                if message and message["type"] == "pmessage":
                    event_json = message["data"]
                    event = Event.from_json(event_json)

                    # Add to appropriate priority queue
                    queue = self.event_queues[event.priority]
                    await queue.put(event)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error("redis_subscribe_error", error=str(e))

    async def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get current event bus statistics

        Returns:
            Dictionary with queue sizes and status
        """
        return {
            "running": self.running,
            "queue_sizes": {
                priority.name: self.event_queues[priority].qsize()
                for priority in EventPriority
            },
            "dead_letter_size": self.dead_letter_queue.qsize(),
            "handler_counts": {
                event_type: len(handlers)
                for event_type, handlers in self.handlers.items()
            },
            "total_handlers": sum(len(h) for h in self.handlers.values()),
        }
