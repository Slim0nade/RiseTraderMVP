"""
Integration tests for SSE event streaming (T047).

These tests verify:
- SSE endpoints are accessible
- Events are properly streamed to clients
- Reconnection with sequence recovery works
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from src.api.routes.events import router as events_router
from src.utils.sse_events import SSEEvent, SSEEventManager, get_sse_manager


@pytest.fixture
def test_app():
    """Create a test FastAPI app with events router."""
    app = FastAPI()
    app.include_router(events_router, prefix="/api")
    return app


@pytest.fixture
def mock_sse_manager():
    """Create a mock SSE manager for testing."""
    manager = SSEEventManager()
    manager._running = True
    return manager


@pytest.mark.asyncio
class TestSSEEndpoints:
    """Tests for SSE API endpoints."""

    async def test_events_health_endpoint(self, test_app, mock_sse_manager):
        """Test SSE health check endpoint."""
        with patch("src.api.routes.events.get_sse_manager", return_value=mock_sse_manager):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/events/health")

                assert response.status_code == 200
                data = response.json()
                assert "status" in data
                assert "current_sequence" in data
                assert "buffer_size" in data
                assert "active_subscribers" in data

    async def test_events_history_endpoint(self, test_app, mock_sse_manager):
        """Test event history endpoint."""
        # Add some events to the buffer
        mock_sse_manager._event_buffer = [
            SSEEvent(event="event1", data={"n": 1}, sequence=1),
            SSEEvent(event="event2", data={"n": 2}, sequence=2),
            SSEEvent(event="event3", data={"n": 3}, sequence=3),
        ]

        with patch("src.api.routes.events.get_sse_manager", return_value=mock_sse_manager):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/events/history")

                assert response.status_code == 200
                data = response.json()
                assert "events" in data
                assert len(data["events"]) == 3

    async def test_events_history_with_sequence_filter(self, test_app, mock_sse_manager):
        """Test event history with sequence filter."""
        mock_sse_manager._event_buffer = [
            SSEEvent(event="event1", data={}, sequence=1),
            SSEEvent(event="event2", data={}, sequence=2),
            SSEEvent(event="event3", data={}, sequence=3),
            SSEEvent(event="event4", data={}, sequence=4),
        ]

        with patch("src.api.routes.events.get_sse_manager", return_value=mock_sse_manager):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/events/history?since_sequence=2")

                assert response.status_code == 200
                data = response.json()
                # Should return events 3 and 4 (after sequence 2)
                assert len(data["events"]) == 2
                assert data["events"][0]["sequence"] == 3
                assert data["events"][1]["sequence"] == 4


@pytest.mark.asyncio
class TestSSEStreaming:
    """Tests for SSE streaming functionality."""

    async def test_stream_emits_events(self):
        """Test that the stream endpoint emits events."""
        manager = SSEEventManager()
        await manager.start()

        events_received = []

        async def collect_events():
            async for event in manager.subscribe():
                events_received.append(event)
                if len(events_received) >= 3:
                    break

        # Start collection task
        collect_task = asyncio.create_task(collect_events())

        # Give subscription time to register
        await asyncio.sleep(0.01)

        # Emit events
        await manager.emit("test1", {"n": 1})
        await manager.emit("test2", {"n": 2})
        await manager.emit("test3", {"n": 3})

        # Wait for collection
        try:
            await asyncio.wait_for(collect_task, timeout=1.0)
        except asyncio.TimeoutError:
            pass

        assert len(events_received) >= 3

        await manager.stop()

    async def test_missed_events_recovery(self):
        """Test that clients can recover missed events using sequence."""
        manager = SSEEventManager()
        await manager.start()

        # Emit events
        for i in range(5):
            await manager.emit(f"event_{i}", {"index": i})

        # Simulate reconnection - get events since sequence 2
        missed_events = manager.get_events_since(2)

        assert len(missed_events) == 3
        assert missed_events[0].sequence == 3
        assert missed_events[-1].sequence == 5

        await manager.stop()

    async def test_job_event_filtering(self):
        """Test filtering events by job_id."""
        manager = SSEEventManager()
        await manager.start()

        # Emit events for different jobs
        await manager.emit_job_progress(
            job_id="job-A",
            progress_pct=10,
            combinations_tested=10,
            total_combinations=100,
        )
        await manager.emit_job_progress(
            job_id="job-B",
            progress_pct=20,
            combinations_tested=20,
            total_combinations=100,
        )
        await manager.emit_job_progress(
            job_id="job-A",
            progress_pct=30,
            combinations_tested=30,
            total_combinations=100,
        )

        # Get all events and filter for job-A
        all_events = manager._event_buffer
        job_a_events = [e for e in all_events if e.data.get("job_id") == "job-A"]

        assert len(job_a_events) == 2

        await manager.stop()


@pytest.mark.asyncio
class TestSSEEventTypes:
    """Tests for different event types."""

    async def test_optimization_events_flow(self):
        """Test the full optimization event flow."""
        manager = SSEEventManager()
        await manager.start()

        job_id = "test-job-123"

        # Emit full lifecycle
        e1 = await manager.emit_job_started(job_id, "ma_crossover", 100)
        e2 = await manager.emit_job_progress(job_id, 50.0, 50, 100, {"fast": 10}, 1.5)
        e3 = await manager.emit_job_complete(job_id, {"fast": 10, "slow": 30}, 1.8, 100)

        assert e1.event == "job_started"
        assert e2.event == "job_progress"
        assert e3.event == "job_complete"

        # Verify sequence order
        assert e1.sequence < e2.sequence < e3.sequence

        await manager.stop()

    async def test_error_events(self):
        """Test error event emission."""
        manager = SSEEventManager()
        await manager.start()

        event = await manager.emit_job_failed("job-123", "Database connection lost")

        assert event.event == "job_failed"
        assert event.data["error"] == "Database connection lost"
        assert event.data["status"] == "failed"

        await manager.stop()

    async def test_price_alert_events(self):
        """Test price alert event emission."""
        manager = SSEEventManager()
        await manager.start()

        event = await manager.emit_price_alert(
            ticket=12345,
            alert_type="breakeven",
            price_level=57.50,
            current_price=57.52,
            direction="above",
        )

        assert event.event == "price_alert"
        assert event.data["ticket"] == 12345
        assert event.data["alert_type"] == "breakeven"

        await manager.stop()


@pytest.mark.asyncio
class TestSSEConcurrency:
    """Tests for concurrent SSE operations."""

    async def test_multiple_subscribers_isolation(self):
        """Test that multiple subscribers each receive all events."""
        manager = SSEEventManager()
        await manager.start()

        received_1 = []
        received_2 = []
        received_3 = []

        async def subscriber(received_list):
            async for event in manager.subscribe():
                received_list.append(event)
                if len(received_list) >= 5:
                    break

        # Start multiple subscribers
        tasks = [
            asyncio.create_task(subscriber(received_1)),
            asyncio.create_task(subscriber(received_2)),
            asyncio.create_task(subscriber(received_3)),
        ]

        await asyncio.sleep(0.01)

        # Emit events
        for i in range(5):
            await manager.emit(f"event_{i}", {"i": i})

        # Wait for completion
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=2.0)
        except asyncio.TimeoutError:
            pass

        # Each subscriber should have received all events
        assert len(received_1) >= 5
        assert len(received_2) >= 5
        assert len(received_3) >= 5

        await manager.stop()

    async def test_subscriber_cleanup_on_disconnect(self):
        """Test that disconnected subscribers are cleaned up."""
        manager = SSEEventManager()
        await manager.start()

        initial_subscribers = len(manager._subscribers)

        async def short_subscription():
            count = 0
            async for event in manager.subscribe():
                count += 1
                if count >= 2:
                    break

        # Start and complete a subscription
        await asyncio.sleep(0.01)
        task = asyncio.create_task(short_subscription())
        await asyncio.sleep(0.01)

        # Emit events
        await manager.emit("e1", {})
        await manager.emit("e2", {})

        # Wait for task
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            pass

        await asyncio.sleep(0.01)

        # Subscriber should be removed
        assert len(manager._subscribers) == initial_subscribers

        await manager.stop()


@pytest.mark.asyncio
class TestSSEBufferBehavior:
    """Tests for event buffer behavior."""

    async def test_buffer_overflow_keeps_latest(self):
        """Test that buffer overflow preserves most recent events."""
        buffer_size = 5
        manager = SSEEventManager(buffer_size=buffer_size)
        await manager.start()

        # Emit more than buffer size
        for i in range(10):
            await manager.emit(f"event_{i}", {"index": i})

        # Should only have last 5
        assert len(manager._event_buffer) == buffer_size

        # Most recent events preserved
        indices = [e.data["index"] for e in manager._event_buffer]
        assert indices == [5, 6, 7, 8, 9]

        await manager.stop()

    async def test_get_events_since_timestamp(self):
        """Test retrieving events by timestamp."""
        manager = SSEEventManager()
        await manager.start()

        # Emit events (they'll have auto-generated timestamps)
        await manager.emit("e1", {})
        await asyncio.sleep(0.01)
        mid_timestamp = datetime.now().isoformat()
        await asyncio.sleep(0.01)
        await manager.emit("e2", {})
        await manager.emit("e3", {})

        # Get events after mid_timestamp
        events = manager.get_events_since_timestamp(mid_timestamp)

        assert len(events) >= 2

        await manager.stop()
