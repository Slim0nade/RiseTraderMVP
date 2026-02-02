"""
Server-Sent Events (SSE) utilities for real-time notifications.

This module provides event management for SSE streaming, including
event creation, sequencing, and pub/sub integration with Redis.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

import structlog

logger = structlog.get_logger(__name__)

# Redis channel for SSE events
SSE_EVENTS_CHANNEL = "sse:events"

# Event buffer size for recent event storage
EVENT_BUFFER_SIZE = 100


@dataclass
class SSEEvent:
    """
    Server-Sent Event data structure.

    Attributes:
        event: Event type (e.g., 'job_started', 'job_progress', 'price_alert')
        data: Event payload as dictionary
        id: Unique event identifier
        timestamp: Event creation timestamp (ISO format)
        sequence: Monotonically increasing sequence number
    """
    event: str
    data: Dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sequence: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event": self.event,
            "data": self.data,
            "id": self.id,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
        }

    def to_sse_format(self) -> str:
        """
        Convert to SSE wire format.

        Returns:
            String in SSE format:
            event: <event_type>
            id: <event_id>
            data: <json_payload>
        """
        lines = [
            f"event: {self.event}",
            f"id: {self.id}",
            f"data: {json.dumps(self.data)}",
            "",  # Empty line terminates the event
        ]
        return "\n".join(lines)


class SSEEventManager:
    """
    Manager for SSE event emission, buffering, and retrieval.

    Provides:
    - Event creation with automatic sequencing
    - In-memory event buffer for recent events
    - Redis pub/sub integration for distributed notifications
    - Async generator for SSE streaming
    """

    def __init__(self, redis_client: Optional[Any] = None, buffer_size: int = EVENT_BUFFER_SIZE):
        """
        Initialize the SSE event manager.

        Args:
            redis_client: Optional Redis client for pub/sub
            buffer_size: Size of the in-memory event buffer
        """
        self._redis = redis_client
        self._buffer_size = buffer_size
        self._event_buffer: List[SSEEvent] = []
        self._sequence = 0
        self._sequence_lock = asyncio.Lock()
        self._subscribers: List[asyncio.Queue] = []
        self._running = False
        self._pubsub_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the event manager and subscribe to Redis if available."""
        if self._running:
            return

        self._running = True

        if self._redis:
            try:
                pubsub = self._redis.pubsub()
                await pubsub.subscribe(SSE_EVENTS_CHANNEL)
                self._pubsub_task = asyncio.create_task(self._process_redis_events(pubsub))
                logger.info("sse_manager_started_with_redis", channel=SSE_EVENTS_CHANNEL)
            except Exception as e:
                logger.warning("sse_manager_redis_subscribe_failed", error=str(e))
        else:
            logger.info("sse_manager_started_local_only")

    async def stop(self) -> None:
        """Stop the event manager and cleanup resources."""
        self._running = False

        if self._pubsub_task:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass

        # Signal all subscribers to stop
        for queue in self._subscribers:
            await queue.put(None)

        logger.info("sse_manager_stopped")

    async def emit(
        self,
        event_type: str,
        data: Dict[str, Any],
        publish_to_redis: bool = True,
    ) -> SSEEvent:
        """
        Emit an SSE event.

        Args:
            event_type: Type of event (e.g., 'job_progress')
            data: Event payload
            publish_to_redis: Whether to publish to Redis (for distributed)

        Returns:
            The created SSEEvent
        """
        async with self._sequence_lock:
            self._sequence += 1
            event = SSEEvent(
                event=event_type,
                data=data,
                sequence=self._sequence,
            )

        # Add to buffer
        self._event_buffer.append(event)
        if len(self._event_buffer) > self._buffer_size:
            self._event_buffer.pop(0)

        # Notify local subscribers
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("sse_subscriber_queue_full")

        # Publish to Redis for distributed notification
        if publish_to_redis and self._redis:
            try:
                await self._redis.publish(SSE_EVENTS_CHANNEL, json.dumps(event.to_dict()))
            except Exception as e:
                logger.warning("sse_redis_publish_failed", error=str(e))

        logger.debug(
            "sse_event_emitted",
            event_type=event_type,
            sequence=event.sequence,
            event_id=event.id,
        )

        return event

    async def emit_job_started(self, job_id: str, strategy: str, total_combinations: int) -> SSEEvent:
        """Emit a job_started event."""
        return await self.emit("job_started", {
            "job_id": job_id,
            "strategy": strategy,
            "total_combinations": total_combinations,
            "status": "running",
        })

    async def emit_job_progress(
        self,
        job_id: str,
        progress_pct: float,
        combinations_tested: int,
        total_combinations: int,
        best_params: Optional[Dict[str, Any]] = None,
        best_metric: Optional[float] = None,
    ) -> SSEEvent:
        """Emit a job_progress event."""
        data = {
            "job_id": job_id,
            "progress_pct": round(progress_pct, 1),
            "combinations_tested": combinations_tested,
            "total_combinations": total_combinations,
        }
        if best_params:
            data["best_params"] = best_params
        if best_metric is not None:
            data["best_metric"] = best_metric

        return await self.emit("job_progress", data)

    async def emit_job_complete(
        self,
        job_id: str,
        best_params: Dict[str, Any],
        best_metric: float,
        total_tested: int,
    ) -> SSEEvent:
        """Emit a job_complete event."""
        return await self.emit("job_complete", {
            "job_id": job_id,
            "status": "completed",
            "best_params": best_params,
            "best_metric": best_metric,
            "total_tested": total_tested,
        })

    async def emit_job_failed(self, job_id: str, error: str) -> SSEEvent:
        """Emit a job_failed event."""
        return await self.emit("job_failed", {
            "job_id": job_id,
            "status": "failed",
            "error": error,
        })

    async def emit_job_cancelled(self, job_id: str) -> SSEEvent:
        """Emit a job_cancelled event."""
        return await self.emit("job_cancelled", {
            "job_id": job_id,
            "status": "cancelled",
        })

    async def emit_price_alert(
        self,
        ticket: int,
        alert_type: str,
        price_level: float,
        current_price: float,
        direction: str,
    ) -> SSEEvent:
        """Emit a price_alert event."""
        return await self.emit("price_alert", {
            "ticket": ticket,
            "alert_type": alert_type,
            "price_level": price_level,
            "current_price": current_price,
            "direction": direction,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        })

    def get_events_since(self, sequence: int) -> List[SSEEvent]:
        """
        Get all events since a given sequence number.

        Args:
            sequence: Sequence number to start from (exclusive)

        Returns:
            List of events with sequence > given sequence
        """
        return [e for e in self._event_buffer if e.sequence > sequence]

    def get_events_since_timestamp(self, timestamp: str) -> List[SSEEvent]:
        """
        Get all events since a given timestamp.

        Args:
            timestamp: ISO format timestamp to start from

        Returns:
            List of events after the given timestamp
        """
        return [e for e in self._event_buffer if e.timestamp > timestamp]

    async def subscribe(self) -> AsyncGenerator[SSEEvent, None]:
        """
        Subscribe to SSE events.

        Yields:
            SSEEvent objects as they are emitted
        """
        queue: asyncio.Queue[Optional[SSEEvent]] = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)

        try:
            while self._running:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    if event is None:
                        break
                    yield event
                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent connection timeout
                    continue
        finally:
            self._subscribers.remove(queue)

    async def _process_redis_events(self, pubsub) -> None:
        """Process events from Redis pub/sub."""
        try:
            async for message in pubsub.listen():
                if not self._running:
                    break

                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        # Re-emit locally (without re-publishing to Redis)
                        event = SSEEvent(
                            event=data["event"],
                            data=data["data"],
                            id=data["id"],
                            timestamp=data["timestamp"],
                            sequence=data["sequence"],
                        )

                        # Notify local subscribers only
                        for queue in self._subscribers:
                            try:
                                queue.put_nowait(event)
                            except asyncio.QueueFull:
                                pass

                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning("sse_redis_message_parse_error", error=str(e))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("sse_redis_listener_error", error=str(e))


# Global SSE manager instance
_sse_manager: Optional[SSEEventManager] = None


async def get_sse_manager(redis_client: Optional[Any] = None) -> SSEEventManager:
    """
    Get or create the global SSE event manager.

    Args:
        redis_client: Optional Redis client (used only on first call)

    Returns:
        The global SSEEventManager instance
    """
    global _sse_manager

    if _sse_manager is None:
        _sse_manager = SSEEventManager(redis_client=redis_client)
        await _sse_manager.start()

    return _sse_manager


async def shutdown_sse_manager() -> None:
    """Shutdown the global SSE manager."""
    global _sse_manager

    if _sse_manager:
        await _sse_manager.stop()
        _sse_manager = None
