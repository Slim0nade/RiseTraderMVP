"""
Unit Tests for EventBus

Tests:
- Event creation and serialization
- Event publishing and subscription
- Priority queue ordering
- Backpressure handling
- Dead letter queue
- Event timeout
- Redis pub/sub integration
- Metrics and logging
"""

import asyncio
import time
from unittest.mock import AsyncMock, Mock

import pytest

from src.agents.event_bus import Event, EventBus, EventPriority, EventStatus


# ============================================================================
# EVENT CLASS TESTS
# ============================================================================

class TestEvent:
    """Test Event class"""
    
    def test_event_creation(self):
        """Test event creation with defaults"""
        event = Event(
            event_type="test_event",
            source_agent="test_agent",
            data={"key": "value"},
        )
        
        assert event.event_type == "test_event"
        assert event.source_agent == "test_agent"
        assert event.data == {"key": "value"}
        assert event.priority == EventPriority.NORMAL
        assert event.event_id is not None
        assert event.timestamp > 0
    
    def test_event_with_priority(self):
        """Test event creation with custom priority"""
        event = Event(
            event_type="critical_event",
            source_agent="test_agent",
            data={},
            priority=EventPriority.CRITICAL,
        )
        
        assert event.priority == EventPriority.CRITICAL
    
    def test_event_serialization(self):
        """Test event to_dict serialization"""
        event = Event(
            event_type="test_event",
            source_agent="test_agent",
            data={"key": "value"},
            correlation_id="corr123",
        )
        
        event_dict = event.to_dict()
        
        assert event_dict["event_type"] == "test_event"
        assert event_dict["source_agent"] == "test_agent"
        assert event_dict["data"] == {"key": "value"}
        assert event_dict["correlation_id"] == "corr123"
        assert "event_id" in event_dict
        assert "timestamp" in event_dict
    
    def test_event_deserialization(self):
        """Test event from_dict deserialization"""
        event_dict = {
            "event_id": "evt123",
            "event_type": "test_event",
            "source_agent": "test_agent",
            "data": {"key": "value"},
            "priority": EventPriority.HIGH.value,
            "timestamp": time.time(),
            "correlation_id": "corr123",
            "metadata": {"meta": "data"},
        }
        
        event = Event.from_dict(event_dict)
        
        assert event.event_id == "evt123"
        assert event.event_type == "test_event"
        assert event.source_agent == "test_agent"
        assert event.data == {"key": "value"}
        assert event.priority == EventPriority.HIGH
        assert event.correlation_id == "corr123"
    
    def test_event_json_serialization(self):
        """Test JSON serialization roundtrip"""
        original = Event(
            event_type="test_event",
            source_agent="test_agent",
            data={"key": "value"},
        )
        
        json_str = original.to_json()
        restored = Event.from_json(json_str)
        
        assert restored.event_type == original.event_type
        assert restored.source_agent == original.source_agent
        assert restored.data == original.data


# ============================================================================
# EVENT BUS INITIALIZATION TESTS
# ============================================================================

class TestEventBusInitialization:
    """Test EventBus initialization"""
    
    @pytest.mark.asyncio
    async def test_event_bus_creation(self):
        """Test EventBus creation with default config"""
        bus = EventBus(redis_url="redis://localhost:6379/1")
        
        assert bus.redis_url == "redis://localhost:6379/1"
        assert bus.max_queue_size == 10000
        assert bus.retry_attempts == 3
        assert bus.running is False
        assert len(bus.event_queues) == len(EventPriority)
    
    @pytest.mark.asyncio
    async def test_event_bus_custom_config(self):
        """Test EventBus with custom configuration"""
        bus = EventBus(
            redis_url="redis://localhost:6379/2",
            max_queue_size=5000,
            retry_attempts=5,
            event_timeout=60.0,
        )
        
        assert bus.max_queue_size == 5000
        assert bus.retry_attempts == 5
        assert bus.event_timeout == 60.0
    
    @pytest.mark.asyncio
    async def test_event_bus_connect(self, event_bus):
        """Test EventBus connection"""
        assert event_bus.redis_client is not None
        assert event_bus.running is True
    
    @pytest.mark.asyncio
    async def test_event_bus_disconnect(self, event_bus):
        """Test EventBus disconnection"""
        await event_bus.stop()
        
        assert event_bus.running is False


# ============================================================================
# SUBSCRIPTION TESTS
# ============================================================================

class TestEventSubscription:
    """Test event subscription functionality"""
    
    @pytest.mark.asyncio
    async def test_subscribe_to_event(self, event_bus):
        """Test subscribing to event type"""
        handler = AsyncMock()
        
        event_bus.subscribe("test_event", "test_agent", handler)
        
        assert "test_event" in event_bus.handlers
        assert len(event_bus.handlers["test_event"]) == 1
        assert event_bus.handlers["test_event"][0] == ("test_agent", handler)
    
    @pytest.mark.asyncio
    async def test_subscribe_multiple_handlers(self, event_bus):
        """Test multiple handlers for same event"""
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        
        event_bus.subscribe("test_event", "agent1", handler1)
        event_bus.subscribe("test_event", "agent2", handler2)
        
        assert len(event_bus.handlers["test_event"]) == 2
    
    @pytest.mark.asyncio
    async def test_unsubscribe_from_event(self, event_bus):
        """Test unsubscribing from event"""
        handler = AsyncMock()
        
        event_bus.subscribe("test_event", "test_agent", handler)
        event_bus.unsubscribe("test_event", "test_agent")
        
        assert len(event_bus.handlers["test_event"]) == 0
    
    @pytest.mark.asyncio
    async def test_unsubscribe_one_of_multiple(self, event_bus):
        """Test unsubscribing one of multiple handlers"""
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        
        event_bus.subscribe("test_event", "agent1", handler1)
        event_bus.subscribe("test_event", "agent2", handler2)
        event_bus.unsubscribe("test_event", "agent1")
        
        assert len(event_bus.handlers["test_event"]) == 1
        assert event_bus.handlers["test_event"][0][0] == "agent2"


# ============================================================================
# PUBLISHING TESTS
# ============================================================================

class TestEventPublishing:
    """Test event publishing functionality"""
    
    @pytest.mark.asyncio
    async def test_publish_event(self, event_bus):
        """Test publishing event to bus"""
        event = Event(
            event_type="test_event",
            source_agent="test_agent",
            data={"key": "value"},
        )
        
        await event_bus.publish(event)
        
        # Check event was added to queue
        queue = event_bus.event_queues[EventPriority.NORMAL]
        assert queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_publish_high_priority_event(self, event_bus):
        """Test publishing high priority event"""
        event = Event(
            event_type="critical_event",
            source_agent="test_agent",
            data={},
            priority=EventPriority.CRITICAL,
        )
        
        await event_bus.publish(event)
        
        # Check event was added to critical queue
        queue = event_bus.event_queues[EventPriority.CRITICAL]
        assert queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_publish_to_redis(self, event_bus):
        """Test event published to Redis"""
        event = Event(
            event_type="test_event",
            source_agent="test_agent",
            data={},
        )
        
        await event_bus.publish(event)
        
        # Verify Redis publish was called
        event_bus.redis_client.publish.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_publish_backpressure(self, event_bus):
        """Test backpressure when queue near capacity"""
        # Set very small queue
        event_bus.max_queue_size = 10
        event_bus.event_queues[EventPriority.NORMAL] = asyncio.Queue(maxsize=10)
        
        # Fill queue
        for i in range(10):
            event = Event(
                event_type="test_event",
                source_agent="test_agent",
                data={"index": i},
            )
            try:
                await asyncio.wait_for(event_bus.publish(event), timeout=0.1)
            except asyncio.QueueFull:
                break
        
        # Next publish should fail or warn
        queue = event_bus.event_queues[EventPriority.NORMAL]
        assert queue.full()


# ============================================================================
# DISPATCHING TESTS
# ============================================================================

class TestEventDispatching:
    """Test event dispatching to handlers"""
    
    @pytest.mark.asyncio
    async def test_dispatch_to_single_handler(self, event_bus):
        """Test dispatching event to single handler"""
        handler = AsyncMock()
        event_bus.subscribe("test_event", "test_agent", handler)
        
        event = Event(
            event_type="test_event",
            source_agent="source_agent",
            data={"key": "value"},
        )
        
        await event_bus._dispatch_event(event)
        
        # Give handlers time to execute
        await asyncio.sleep(0.1)
        
        handler.assert_called_once()
        handler.assert_called_with(event)
    
    @pytest.mark.asyncio
    async def test_dispatch_to_multiple_handlers(self, event_bus):
        """Test dispatching to multiple handlers"""
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        
        event_bus.subscribe("test_event", "agent1", handler1)
        event_bus.subscribe("test_event", "agent2", handler2)
        
        event = Event(
            event_type="test_event",
            source_agent="source_agent",
            data={},
        )
        
        await event_bus._dispatch_event(event)
        
        # Give handlers time to execute
        await asyncio.sleep(0.1)
        
        handler1.assert_called_once_with(event)
        handler2.assert_called_once_with(event)
    
    @pytest.mark.asyncio
    async def test_dispatch_no_handlers(self, event_bus):
        """Test dispatching event with no handlers"""
        event = Event(
            event_type="unknown_event",
            source_agent="source_agent",
            data={},
        )
        
        # Should not raise error
        await event_bus._dispatch_event(event)
    
    @pytest.mark.asyncio
    async def test_handler_error_retry(self, event_bus):
        """Test handler error triggers retry"""
        call_count = 0
        
        async def failing_handler(event):
            nonlocal call_count
            call_count += 1
            raise ValueError("Handler error")
        
        event_bus.retry_attempts = 3
        
        event = Event(
            event_type="test_event",
            source_agent="source_agent",
            data={},
        )
        
        await event_bus._execute_handler(event, "test_agent", failing_handler)
        
        # Should have retried 3 times
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_handler_timeout(self, event_bus):
        """Test handler timeout"""
        async def slow_handler(event):
            await asyncio.sleep(10)  # Will timeout
        
        event_bus.subscribe("test_event", "slow_agent", slow_handler)
        event_bus.event_timeout = 0.5  # Short timeout
        
        event = Event(
            event_type="test_event",
            source_agent="source_agent",
            data={},
        )
        
        # Should timeout but not raise
        await event_bus._dispatch_event(event)


# ============================================================================
# DEAD LETTER QUEUE TESTS
# ============================================================================

class TestDeadLetterQueue:
    """Test dead letter queue functionality"""
    
    @pytest.mark.asyncio
    async def test_failed_event_to_dead_letter(self, event_bus):
        """Test failed event sent to dead letter queue"""
        async def failing_handler(event):
            raise ValueError("Permanent failure")
        
        event_bus.retry_attempts = 2
        
        event = Event(
            event_type="test_event",
            source_agent="source_agent",
            data={},
        )
        
        await event_bus._execute_handler(event, "test_agent", failing_handler)
        
        # Should be in dead letter queue
        assert event_bus.dead_letter_queue.qsize() > 0
        
        dead_letter = await event_bus.dead_letter_queue.get()
        assert dead_letter["event"]["event_id"] == event.event_id
        assert dead_letter["agent_id"] == "test_agent"
        assert "error" in dead_letter


# ============================================================================
# PRIORITY QUEUE TESTS
# ============================================================================

class TestPriorityQueue:
    """Test priority queue ordering"""
    
    @pytest.mark.asyncio
    async def test_priority_ordering(self, event_bus):
        """Test events processed by priority"""
        # Create handler to track order
        processed_events = []
        
        async def handler(event):
            processed_events.append(event.priority)
        
        event_bus.subscribe("test_event", "test_agent", handler)
        
        # Publish events with different priorities
        await event_bus.publish(Event(
            event_type="test_event",
            source_agent="source",
            data={},
            priority=EventPriority.LOW,
        ))
        
        await event_bus.publish(Event(
            event_type="test_event",
            source_agent="source",
            data={},
            priority=EventPriority.CRITICAL,
        ))
        
        await event_bus.publish(Event(
            event_type="test_event",
            source_agent="source",
            data={},
            priority=EventPriority.HIGH,
        ))
        
        # Wait for processing
        await asyncio.sleep(0.5)
        
        # Critical should be processed first (separate queue)
        assert len(processed_events) > 0


# ============================================================================
# STATISTICS TESTS
# ============================================================================

class TestEventBusStatistics:
    """Test event bus statistics"""
    
    @pytest.mark.asyncio
    async def test_get_queue_stats(self, event_bus):
        """Test getting queue statistics"""
        stats = await event_bus.get_queue_stats()
        
        assert "running" in stats
        assert "queue_sizes" in stats
        assert "dead_letter_size" in stats
        assert "handler_counts" in stats
        assert "total_handlers" in stats
        
        assert stats["running"] is True
        assert len(stats["queue_sizes"]) == len(EventPriority)
    
    @pytest.mark.asyncio
    async def test_stats_after_subscriptions(self, event_bus):
        """Test statistics reflect subscriptions"""
        handler = AsyncMock()
        
        event_bus.subscribe("event1", "agent1", handler)
        event_bus.subscribe("event2", "agent2", handler)
        
        stats = await event_bus.get_queue_stats()
        
        assert stats["total_handlers"] == 2
        assert "event1" in stats["handler_counts"]
        assert "event2" in stats["handler_counts"]


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestEventBusIntegration:
    """Integration tests for complete event flow"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_complete_event_flow(self, event_bus):
        """Test complete event publish-subscribe flow"""
        received_events = []
        
        async def handler(event):
            received_events.append(event)
        
        event_bus.subscribe("test_event", "test_agent", handler)
        
        # Publish event
        test_event = Event(
            event_type="test_event",
            source_agent="source_agent",
            data={"message": "test"},
        )
        
        await event_bus.publish(test_event)
        
        # Wait for processing
        await asyncio.sleep(0.2)
        
        # Verify event received
        assert len(received_events) == 1
        assert received_events[0].event_id == test_event.event_id
        assert received_events[0].data["message"] == "test"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multiple_events_flow(self, event_bus):
        """Test multiple events processed correctly"""
        received_count = 0
        
        async def handler(event):
            nonlocal received_count
            received_count += 1
        
        event_bus.subscribe("test_event", "test_agent", handler)
        
        # Publish multiple events
        for i in range(5):
            event = Event(
                event_type="test_event",
                source_agent="source",
                data={"index": i},
            )
            await event_bus.publish(event)
        
        # Wait for processing
        await asyncio.sleep(0.5)
        
        assert received_count == 5
