"""
Integration tests for MCP Server

Tests the full agent coordination system including:
- EventBus communication
- AgentRegistry health monitoring
- Agent lifecycle (start/stop/pause/resume)
- Event flows between agents
- Circuit breaker behavior
"""

import asyncio
import pytest
from typing import Dict, Any

from src.agents import (
    MCPServer,
    BaseAgent,
    EventBus,
    AgentRegistry,
    Event,
    EventPriority,
    AgentStatus,
)


# Test Agent Implementations
class TestProducerAgent(BaseAgent):
    """Agent that produces events"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events_sent = 0

    async def initialize(self) -> None:
        self.logger.info("test_producer_initialized")

    async def process_event(self, event: Event) -> None:
        # This agent doesn't process events, only produces
        pass

    async def cleanup(self) -> None:
        self.logger.info("test_producer_cleanup")

    async def send_test_event(self, data: Dict[str, Any]) -> None:
        """Send a test event"""
        await self.publish_event(
            event_type="test_event",
            data=data,
            priority=EventPriority.NORMAL,
        )
        self.events_sent += 1


class TestConsumerAgent(BaseAgent):
    """Agent that consumes events"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events_received = 0
        self.last_event_data = None

    async def initialize(self) -> None:
        self.subscribe_to_event("test_event")
        self.logger.info("test_consumer_initialized")

    async def process_event(self, event: Event) -> None:
        if event.event_type == "test_event":
            self.events_received += 1
            self.last_event_data = event.data
            self.logger.info(
                "test_event_received",
                event_id=event.event_id,
                data=event.data,
            )

    async def cleanup(self) -> None:
        self.logger.info("test_consumer_cleanup")


class TestFailingAgent(BaseAgent):
    """Agent that fails on purpose for circuit breaker testing"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.failure_count = 0

    async def initialize(self) -> None:
        self.subscribe_to_event("fail_event")

    async def process_event(self, event: Event) -> None:
        if event.event_type == "fail_event":
            self.failure_count += 1
            raise ValueError("Intentional failure for testing")

    async def cleanup(self) -> None:
        pass


# Fixtures
@pytest.fixture
async def event_bus():
    """Create and start EventBus"""
    bus = EventBus(redis_url="redis://localhost:6379")
    await bus.start()
    yield bus
    await bus.stop()


@pytest.fixture
async def agent_registry():
    """Create and start AgentRegistry"""
    registry = AgentRegistry(
        redis_url="redis://localhost:6379",
        heartbeat_interval=1.0,  # Faster for testing
        heartbeat_timeout=3.0,
    )
    await registry.start()
    yield registry
    await registry.stop()


@pytest.fixture
async def producer_agent(event_bus, agent_registry):
    """Create producer agent"""
    agent = TestProducerAgent(
        agent_id="test_producer",
        event_bus=event_bus,
        agent_registry=agent_registry,
        priority=1,
    )
    await agent.start()
    yield agent
    await agent.stop()


@pytest.fixture
async def consumer_agent(event_bus, agent_registry):
    """Create consumer agent"""
    agent = TestConsumerAgent(
        agent_id="test_consumer",
        event_bus=event_bus,
        agent_registry=agent_registry,
        priority=2,
    )
    await agent.start()
    yield agent
    await agent.stop()


# Tests
@pytest.mark.asyncio
class TestEventBusIntegration:
    """Test EventBus functionality"""

    async def test_event_publishing_and_subscription(
        self, producer_agent, consumer_agent
    ):
        """Test that events flow from producer to consumer"""
        # Send test event
        test_data = {"symbol": "CrudeOIL", "price": 75.50}
        await producer_agent.send_test_event(test_data)

        # Wait for event to be processed
        await asyncio.sleep(0.5)

        # Verify consumer received event
        assert consumer_agent.events_received == 1
        assert consumer_agent.last_event_data == test_data
        assert producer_agent.events_sent == 1

    async def test_multiple_events(self, producer_agent, consumer_agent):
        """Test multiple event delivery"""
        # Send multiple events
        for i in range(10):
            await producer_agent.send_test_event({"count": i})
            await asyncio.sleep(0.05)

        # Wait for all events to be processed
        await asyncio.sleep(1.0)

        # Verify all events received
        assert consumer_agent.events_received == 10
        assert consumer_agent.last_event_data["count"] == 9

    async def test_priority_ordering(self, event_bus):
        """Test that high priority events are processed first"""
        received_priorities = []

        async def handler(event: Event):
            received_priorities.append(event.priority)

        event_bus.subscribe("priority_test", "test", handler)

        # Publish events in reverse priority order
        for priority in [EventPriority.LOW, EventPriority.NORMAL, EventPriority.HIGH]:
            event = Event(
                event_type="priority_test",
                source_agent="test",
                data={},
                priority=priority,
            )
            await event_bus.publish(event)

        # Wait for processing
        await asyncio.sleep(1.0)

        # Verify high priority processed first
        assert received_priorities[0] == EventPriority.HIGH


@pytest.mark.asyncio
class TestAgentRegistryIntegration:
    """Test AgentRegistry functionality"""

    async def test_agent_registration(self, agent_registry, event_bus):
        """Test agent registration and metadata"""
        agent = TestProducerAgent(
            agent_id="test_agent",
            event_bus=event_bus,
            agent_registry=agent_registry,
            priority=5,
        )

        await agent.start()

        # Check registration
        metadata = await agent_registry.get_agent("test_agent")
        assert metadata is not None
        assert metadata.agent_id == "test_agent"
        assert metadata.status == AgentStatus.RUNNING
        assert metadata.priority == 5

        await agent.stop()

    async def test_heartbeat_monitoring(self, agent_registry, event_bus):
        """Test heartbeat health monitoring"""
        agent = TestProducerAgent(
            agent_id="heartbeat_test",
            event_bus=event_bus,
            agent_registry=agent_registry,
        )

        await agent.start()

        # Wait for heartbeat
        await asyncio.sleep(2.0)

        # Check agent is still running
        metadata = await agent_registry.get_agent("heartbeat_test")
        assert metadata.status == AgentStatus.RUNNING

        await agent.stop()

    async def test_agent_lifecycle_states(self, agent_registry, event_bus):
        """Test agent transitions through lifecycle states"""
        agent = TestProducerAgent(
            agent_id="lifecycle_test",
            event_bus=event_bus,
            agent_registry=agent_registry,
        )

        # Start agent
        await agent.start()
        metadata = await agent_registry.get_agent("lifecycle_test")
        assert metadata.status == AgentStatus.RUNNING

        # Pause agent
        await agent.pause()
        await asyncio.sleep(0.1)
        metadata = await agent_registry.get_agent("lifecycle_test")
        assert metadata.status == AgentStatus.PAUSED

        # Resume agent
        await agent.resume()
        await asyncio.sleep(0.1)
        metadata = await agent_registry.get_agent("lifecycle_test")
        assert metadata.status == AgentStatus.RUNNING

        # Stop agent
        await agent.stop()
        # After unregister, agent should not be in registry
        metadata = await agent_registry.get_agent("lifecycle_test")
        assert metadata is None


@pytest.mark.asyncio
class TestCircuitBreakerIntegration:
    """Test circuit breaker fault tolerance"""

    async def test_circuit_breaker_opens_on_failures(
        self, event_bus, agent_registry
    ):
        """Test that circuit breaker opens after repeated failures"""
        # Create failing agent with low failure threshold
        agent_registry.failure_threshold = 3  # Lower for testing

        agent = TestFailingAgent(
            agent_id="failing_agent",
            event_bus=event_bus,
            agent_registry=agent_registry,
        )

        await agent.start()

        # Send events that will cause failures
        for i in range(5):
            event = Event(
                event_type="fail_event",
                source_agent="test",
                data={},
                priority=EventPriority.NORMAL,
            )
            await event_bus.publish(event)
            await asyncio.sleep(0.2)

        # Wait for failures to be processed
        await asyncio.sleep(1.0)

        # Check that circuit breaker is open
        assert agent_registry.is_circuit_open("failing_agent")

        # Check agent status is FAILED
        metadata = await agent_registry.get_agent("failing_agent")
        assert metadata.status == AgentStatus.FAILED

        await agent.stop()


@pytest.mark.asyncio
class TestSharedContext:
    """Test shared context via Redis"""

    async def test_context_storage_and_retrieval(
        self, producer_agent, consumer_agent
    ):
        """Test agents can share context via Redis"""
        # Producer sets context
        await producer_agent.set_context("test_key", "test_value")

        # Consumer reads producer's context
        value = await consumer_agent.get_shared_context(
            "test_producer", "test_key"
        )

        assert value == "test_value"

    async def test_context_with_ttl(self, producer_agent):
        """Test context expiration with TTL"""
        # Set context with 1 second TTL
        await producer_agent.set_context("ttl_key", "ttl_value", ttl=1)

        # Immediately retrieve
        value = await producer_agent.get_context("ttl_key")
        assert value == "ttl_value"

        # Wait for expiration
        await asyncio.sleep(2)

        # Should be expired
        value = await producer_agent.get_context("ttl_key", default="expired")
        assert value == "expired"


@pytest.mark.asyncio
class TestAgentCommunicationPatterns:
    """Test common agent communication patterns"""

    async def test_request_response_pattern(
        self, producer_agent, consumer_agent
    ):
        """Test request-response pattern with correlation IDs"""
        # Producer sends request with correlation ID
        correlation_id = "test-correlation-123"
        await producer_agent.publish_event(
            event_type="test_event",
            data={"request": "get_data"},
            priority=EventPriority.HIGH,
            correlation_id=correlation_id,
        )

        # Wait for processing
        await asyncio.sleep(0.5)

        # Verify consumer received correlated event
        assert consumer_agent.events_received == 1
        assert consumer_agent.last_event_data["request"] == "get_data"

    async def test_event_chain(self, event_bus, agent_registry):
        """Test chained event processing"""
        events_chain = []

        # Create chain of agents
        class ChainAgent1(BaseAgent):
            async def initialize(self):
                self.subscribe_to_event("start_chain")

            async def process_event(self, event: Event):
                if event.event_type == "start_chain":
                    events_chain.append("agent1")
                    await self.publish_event(
                        "chain_step2",
                        {"step": 2},
                        priority=EventPriority.HIGH,
                    )

            async def cleanup(self):
                pass

        class ChainAgent2(BaseAgent):
            async def initialize(self):
                self.subscribe_to_event("chain_step2")

            async def process_event(self, event: Event):
                if event.event_type == "chain_step2":
                    events_chain.append("agent2")
                    await self.publish_event(
                        "chain_complete",
                        {"step": 3},
                        priority=EventPriority.HIGH,
                    )

            async def cleanup(self):
                pass

        # Start agents
        agent1 = ChainAgent1("chain1", event_bus, agent_registry, priority=1)
        agent2 = ChainAgent2("chain2", event_bus, agent_registry, priority=2)

        await agent1.start()
        await agent2.start()

        # Start chain
        await event_bus.publish(
            Event(
                event_type="start_chain",
                source_agent="test",
                data={},
                priority=EventPriority.HIGH,
            )
        )

        # Wait for chain to complete
        await asyncio.sleep(1.0)

        # Verify chain executed in order
        assert events_chain == ["agent1", "agent2"]

        await agent1.stop()
        await agent2.stop()


@pytest.mark.asyncio
class TestPerformance:
    """Test performance characteristics"""

    async def test_event_throughput(self, event_bus):
        """Test event throughput capacity"""
        events_processed = 0

        async def fast_handler(event: Event):
            nonlocal events_processed
            events_processed += 1

        event_bus.subscribe("throughput_test", "test", fast_handler)

        # Send 100 events as fast as possible
        start_time = asyncio.get_event_loop().time()

        for i in range(100):
            event = Event(
                event_type="throughput_test",
                source_agent="test",
                data={"count": i},
                priority=EventPriority.NORMAL,
            )
            await event_bus.publish(event)

        # Wait for all events to be processed
        await asyncio.sleep(2.0)

        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time

        # Verify all events processed
        assert events_processed == 100

        # Calculate throughput (events per second)
        throughput = events_processed / duration
        print(f"\nEvent throughput: {throughput:.2f} events/second")

        # Should handle at least 50 events/second
        assert throughput > 50


# Mark tests that require Redis
pytestmark = pytest.mark.integration
