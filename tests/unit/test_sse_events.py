"""
Unit tests for SSE event emission (T040-T041).

These tests verify:
- T040: SSE event emission with proper format
- T041: Event sequence numbering is monotonically increasing
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.sse_events import SSEEvent, SSEEventManager


class TestSSEEvent:
    """Tests for SSEEvent dataclass."""

    def test_event_creation_with_defaults(self):
        """Test SSEEvent creation with default values."""
        event = SSEEvent(event="test_event", data={"key": "value"})

        assert event.event == "test_event"
        assert event.data == {"key": "value"}
        assert event.id is not None  # Auto-generated UUID
        assert event.timestamp is not None  # Auto-generated
        assert event.sequence == 0  # Default

    def test_event_creation_with_all_fields(self):
        """Test SSEEvent creation with all fields specified."""
        event = SSEEvent(
            event="custom_event",
            data={"foo": "bar"},
            id="custom-id-123",
            timestamp="2024-01-15T10:30:00+00:00",
            sequence=42,
        )

        assert event.event == "custom_event"
        assert event.data == {"foo": "bar"}
        assert event.id == "custom-id-123"
        assert event.timestamp == "2024-01-15T10:30:00+00:00"
        assert event.sequence == 42

    def test_to_dict(self):
        """Test SSEEvent.to_dict() serialization."""
        event = SSEEvent(
            event="test",
            data={"a": 1},
            id="id-1",
            timestamp="2024-01-01T00:00:00+00:00",
            sequence=5,
        )

        result = event.to_dict()

        assert result == {
            "event": "test",
            "data": {"a": 1},
            "id": "id-1",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "sequence": 5,
        }

    def test_to_sse_format(self):
        """Test SSEEvent.to_sse_format() wire format."""
        event = SSEEvent(
            event="job_progress",
            data={"job_id": "abc", "progress": 50},
            id="event-001",
        )

        result = event.to_sse_format()

        # SSE format: event, id, data lines followed by blank line
        assert "event: job_progress" in result
        assert "id: event-001" in result
        assert '"job_id": "abc"' in result
        assert '"progress": 50' in result
        assert result.endswith("\n")

    def test_to_sse_format_structure(self):
        """Test SSE format has correct line structure."""
        event = SSEEvent(event="test", data={}, id="id-1")
        result = event.to_sse_format()
        lines = result.split("\n")

        # Should have: event line, id line, data line, empty line
        assert len(lines) >= 4
        assert lines[0].startswith("event:")
        assert lines[1].startswith("id:")
        assert lines[2].startswith("data:")
        assert lines[3] == ""  # Empty line terminates event


@pytest.mark.asyncio
class TestSSEEventManagerEmission:
    """Tests for T040: SSE event emission."""

    async def test_emit_creates_event_with_sequence(self):
        """Test that emit() creates an event with proper sequence number."""
        manager = SSEEventManager()
        await manager.start()

        event = await manager.emit("test_event", {"key": "value"})

        assert event.event == "test_event"
        assert event.data == {"key": "value"}
        assert event.sequence == 1  # First event
        assert event.id is not None

        await manager.stop()

    async def test_emit_adds_to_buffer(self):
        """Test that emitted events are added to the buffer."""
        manager = SSEEventManager()
        await manager.start()

        await manager.emit("event1", {})
        await manager.emit("event2", {})

        assert len(manager._event_buffer) == 2

        await manager.stop()

    async def test_emit_job_started(self):
        """Test emit_job_started() helper method."""
        manager = SSEEventManager()
        await manager.start()

        event = await manager.emit_job_started("job-123", "ma_crossover", 100)

        assert event.event == "job_started"
        assert event.data["job_id"] == "job-123"
        assert event.data["strategy"] == "ma_crossover"
        assert event.data["total_combinations"] == 100
        assert event.data["status"] == "running"

        await manager.stop()

    async def test_emit_job_progress(self):
        """Test emit_job_progress() helper method."""
        manager = SSEEventManager()
        await manager.start()

        event = await manager.emit_job_progress(
            job_id="job-123",
            progress_pct=45.5,
            combinations_tested=45,
            total_combinations=100,
            best_params={"fast": 10},
            best_metric=1.5,
        )

        assert event.event == "job_progress"
        assert event.data["job_id"] == "job-123"
        assert event.data["progress_pct"] == 45.5
        assert event.data["combinations_tested"] == 45
        assert event.data["best_params"] == {"fast": 10}
        assert event.data["best_metric"] == 1.5

        await manager.stop()

    async def test_emit_job_complete(self):
        """Test emit_job_complete() helper method."""
        manager = SSEEventManager()
        await manager.start()

        event = await manager.emit_job_complete(
            job_id="job-123",
            best_params={"fast": 10, "slow": 30},
            best_metric=2.1,
            total_tested=100,
        )

        assert event.event == "job_complete"
        assert event.data["status"] == "completed"
        assert event.data["best_params"] == {"fast": 10, "slow": 30}
        assert event.data["best_metric"] == 2.1

        await manager.stop()

    async def test_emit_job_failed(self):
        """Test emit_job_failed() helper method."""
        manager = SSEEventManager()
        await manager.start()

        event = await manager.emit_job_failed("job-123", "Connection timeout")

        assert event.event == "job_failed"
        assert event.data["job_id"] == "job-123"
        assert event.data["status"] == "failed"
        assert event.data["error"] == "Connection timeout"

        await manager.stop()

    async def test_emit_job_cancelled(self):
        """Test emit_job_cancelled() helper method."""
        manager = SSEEventManager()
        await manager.start()

        event = await manager.emit_job_cancelled("job-123")

        assert event.event == "job_cancelled"
        assert event.data["job_id"] == "job-123"
        assert event.data["status"] == "cancelled"

        await manager.stop()

    async def test_emit_price_alert(self):
        """Test emit_price_alert() helper method."""
        manager = SSEEventManager()
        await manager.start()

        event = await manager.emit_price_alert(
            ticket=12345,
            alert_type="liquidity_sweep",
            price_level=56.50,
            current_price=56.48,
            direction="below",
        )

        assert event.event == "price_alert"
        assert event.data["ticket"] == 12345
        assert event.data["alert_type"] == "liquidity_sweep"
        assert event.data["price_level"] == 56.50
        assert event.data["current_price"] == 56.48
        assert event.data["direction"] == "below"
        assert "triggered_at" in event.data

        await manager.stop()


@pytest.mark.asyncio
class TestSSEEventSequencing:
    """Tests for T041: Event sequence numbering."""

    async def test_sequence_is_monotonically_increasing(self):
        """Test that sequence numbers always increase."""
        manager = SSEEventManager()
        await manager.start()

        events = []
        for i in range(10):
            event = await manager.emit(f"event_{i}", {"index": i})
            events.append(event)

        # Verify sequences are monotonically increasing
        sequences = [e.sequence for e in events]
        assert sequences == sorted(sequences)
        assert sequences == list(range(1, 11))

        await manager.stop()

    async def test_sequence_is_unique(self):
        """Test that each event has a unique sequence number."""
        manager = SSEEventManager()
        await manager.start()

        events = []
        for _ in range(50):
            event = await manager.emit("test", {})
            events.append(event)

        sequences = [e.sequence for e in events]
        assert len(sequences) == len(set(sequences))  # All unique

        await manager.stop()

    async def test_sequence_survives_concurrent_emissions(self):
        """Test that concurrent emissions still produce unique sequences."""
        manager = SSEEventManager()
        await manager.start()

        # Emit many events concurrently
        async def emit_event(idx):
            return await manager.emit(f"event_{idx}", {"idx": idx})

        events = await asyncio.gather(*[emit_event(i) for i in range(100)])

        sequences = [e.sequence for e in events]
        assert len(sequences) == len(set(sequences))  # All unique
        assert max(sequences) == 100

        await manager.stop()

    async def test_get_events_since_sequence(self):
        """Test retrieving events since a specific sequence."""
        manager = SSEEventManager()
        await manager.start()

        for i in range(10):
            await manager.emit(f"event_{i}", {})

        # Get events since sequence 5
        events = manager.get_events_since(5)

        assert len(events) == 5
        assert all(e.sequence > 5 for e in events)

        await manager.stop()

    async def test_get_events_since_returns_empty_for_latest(self):
        """Test that get_events_since returns empty for current sequence."""
        manager = SSEEventManager()
        await manager.start()

        for i in range(5):
            await manager.emit(f"event_{i}", {})

        # Get events since the latest sequence
        events = manager.get_events_since(5)
        assert len(events) == 0

        await manager.stop()


@pytest.mark.asyncio
class TestSSEEventBuffer:
    """Tests for event buffer management."""

    async def test_buffer_respects_size_limit(self):
        """Test that buffer does not exceed configured size."""
        buffer_size = 10
        manager = SSEEventManager(buffer_size=buffer_size)
        await manager.start()

        # Emit more events than buffer size
        for i in range(25):
            await manager.emit(f"event_{i}", {})

        assert len(manager._event_buffer) == buffer_size
        # Buffer should contain latest events
        assert manager._event_buffer[-1].event == "event_24"
        assert manager._event_buffer[0].event == "event_15"

        await manager.stop()

    async def test_buffer_maintains_sequence_order(self):
        """Test that buffer maintains chronological order."""
        manager = SSEEventManager(buffer_size=5)
        await manager.start()

        for i in range(8):
            await manager.emit(f"event_{i}", {})

        sequences = [e.sequence for e in manager._event_buffer]
        assert sequences == sorted(sequences)

        await manager.stop()


@pytest.mark.asyncio
class TestSSEEventSubscription:
    """Tests for event subscription."""

    async def test_subscriber_receives_events(self):
        """Test that subscribers receive emitted events."""
        manager = SSEEventManager()
        await manager.start()

        received_events = []

        async def collect_events():
            async for event in manager.subscribe():
                received_events.append(event)
                if len(received_events) >= 3:
                    break

        # Start subscription in background
        subscription_task = asyncio.create_task(collect_events())

        # Give subscription time to start
        await asyncio.sleep(0.01)

        # Emit events
        await manager.emit("event1", {"n": 1})
        await manager.emit("event2", {"n": 2})
        await manager.emit("event3", {"n": 3})

        # Wait for collection with timeout
        try:
            await asyncio.wait_for(subscription_task, timeout=1.0)
        except asyncio.TimeoutError:
            pass

        assert len(received_events) >= 3

        await manager.stop()

    async def test_multiple_subscribers(self):
        """Test that multiple subscribers all receive events."""
        manager = SSEEventManager()
        await manager.start()

        received_1 = []
        received_2 = []

        async def collect_1():
            async for event in manager.subscribe():
                received_1.append(event)
                if len(received_1) >= 2:
                    break

        async def collect_2():
            async for event in manager.subscribe():
                received_2.append(event)
                if len(received_2) >= 2:
                    break

        task1 = asyncio.create_task(collect_1())
        task2 = asyncio.create_task(collect_2())

        await asyncio.sleep(0.01)

        await manager.emit("event1", {})
        await manager.emit("event2", {})

        try:
            await asyncio.wait_for(asyncio.gather(task1, task2), timeout=1.0)
        except asyncio.TimeoutError:
            pass

        assert len(received_1) >= 2
        assert len(received_2) >= 2

        await manager.stop()


@pytest.mark.asyncio
class TestSSEEventRedisIntegration:
    """Tests for Redis pub/sub integration."""

    async def test_emit_publishes_to_redis(self):
        """Test that emit() publishes to Redis when available."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()

        manager = SSEEventManager(redis_client=mock_redis)
        manager._running = True  # Skip start() to avoid pubsub setup

        await manager.emit("test_event", {"key": "value"})

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "sse:events"  # Channel name (with colon)

    async def test_emit_works_without_redis(self):
        """Test that emit() works when Redis is not available."""
        manager = SSEEventManager(redis_client=None)
        await manager.start()

        # Should not raise
        event = await manager.emit("test_event", {"key": "value"})

        assert event is not None
        assert event.event == "test_event"

        await manager.stop()

    async def test_redis_publish_failure_does_not_break_emit(self):
        """Test that Redis publish failure does not prevent event emission."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock(side_effect=Exception("Redis connection error"))

        manager = SSEEventManager(redis_client=mock_redis)
        manager._running = True

        # Should not raise, just log warning
        event = await manager.emit("test_event", {"key": "value"})

        assert event is not None
        assert event.event == "test_event"
        assert len(manager._event_buffer) == 1
