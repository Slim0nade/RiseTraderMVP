"""
Performance Tests - System Throughput

Tests:
- Event processing throughput (100+ events/sec)
- Concurrent event handling
- Database query performance
- API request throughput
"""

import asyncio
import time
import pytest
from src.agents.event_bus import Event, EventPriority


class TestEventThroughput:
    """Test event processing throughput"""
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_event_bus_throughput(self, event_bus):
        """Test event bus can handle 100+ events/second"""
        num_events = 200
        events_received = []
        
        async def handler(event):
            events_received.append(event)
        
        event_bus.subscribe("performance_test", "handler", handler)
        
        start_time = time.time()
        
        # Publish events
        for i in range(num_events):
            await event_bus.publish(Event(
                event_type="performance_test",
                source_agent="test",
                data={"sequence": i},
            ))
        
        # Wait for processing
        await asyncio.sleep(2.0)
        
        elapsed = time.time() - start_time
        
        throughput = len(events_received) / elapsed
        
        # Should handle at least 100 events/sec
        assert throughput >= 100, f"Throughput: {throughput:.2f} events/sec"
