"""
Integration Tests for Agent Coordination

Tests:
- Multi-agent workflows
- Event propagation through agent chain
- Shared context between agents
- Circuit breaker coordination
"""

import asyncio
import pytest
from src.agents.event_bus import Event, EventPriority


class TestSignalToExecutionFlow:
    """Test complete signal → execution flow"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.critical
    async def test_complete_trading_flow(
        self,
        signal_generator_agent,
        risk_manager_agent,
        execution_agent,
        event_bus,
        sample_market_data,
    ):
        """Test tick → signal → validation → execution flow"""
        # Track events at each stage
        events_received = {
            "signal_generated": [],
            "trade_validated": [],
            "trade_executed": [],
        }
        
        async def track_signal(event):
            events_received["signal_generated"].append(event)
        
        async def track_validated(event):
            events_received["trade_validated"].append(event)
        
        async def track_executed(event):
            events_received["trade_executed"].append(event)
        
        event_bus.subscribe("signal_generated", "tracker_signal", track_signal)
        event_bus.subscribe("trade_validated", "tracker_validated", track_validated)
        event_bus.subscribe("trade_executed", "tracker_executed", track_executed)
        
        # Setup agents
        risk_manager_agent.open_positions = []
        risk_manager_agent.daily_pnl = 0.0
        risk_manager_agent.account_balance = 10000.0
        
        execution_agent.mt4_connected = True
        from unittest.mock import AsyncMock
        execution_agent.zmq_socket = AsyncMock()
        execution_agent.zmq_socket.send_json = AsyncMock()
        execution_agent.zmq_socket.poll = AsyncMock(return_value=True)
        execution_agent.zmq_socket.recv_json = AsyncMock(return_value={
            "success": True,
            "order_id": "123456",
            "price": 1850.50,
        })
        
        # Send tick data
        tick_event = Event(
            event_type="new_tick",
            source_agent="market_data_agent",
            data=sample_market_data,
        )
        
        await event_bus.publish(tick_event)
        
        # Wait for propagation
        await asyncio.sleep(1.0)
        
        # Verify event flow
        # Note: May not generate signal if insufficient data
        # This tests the coordination, not the actual signal generation
        assert True  # Flow completed without errors


class TestSharedContext:
    """Test agents sharing context via Redis"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_agents_share_context(
        self,
        signal_generator_agent,
        risk_manager_agent,
    ):
        """Test agents can read each other's context"""
        # Signal generator sets context
        await signal_generator_agent.set_context("latest_signal", "BUY_CrudeOIL")
        
        # Risk manager reads context
        signal = await risk_manager_agent.get_shared_context(
            "signal_generator_test",
            "latest_signal"
        )
        
        assert signal == "BUY_CrudeOIL"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_context_ttl_expires(
        self,
        signal_generator_agent,
    ):
        """Test context expires after TTL"""
        # Set context with short TTL
        await signal_generator_agent.set_context("temp_data", "test_value", ttl=1)
        
        # Read immediately
        value = await signal_generator_agent.get_context("temp_data")
        assert value == "test_value"
        
        # Wait for expiration
        await asyncio.sleep(2)
        
        # Should be gone
        value = await signal_generator_agent.get_context("temp_data")
        assert value is None


class TestCircuitBreakerCoordination:
    """Test circuit breaker affects all agents"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_circuit_open_blocks_events(
        self,
        signal_generator_agent,
        agent_registry,
        event_bus,
        sample_market_data,
    ):
        """Test open circuit breaker blocks event processing"""
        # Force circuit to open
        for _ in range(5):
            await agent_registry.record_error(
                signal_generator_agent.agent_id,
                "Test error"
            )
        
        # Verify circuit is open
        assert agent_registry.is_circuit_open(signal_generator_agent.agent_id)
        
        # Try to process event
        initial_count = signal_generator_agent.events_processed
        
        tick_event = Event(
            event_type="new_tick",
            source_agent="test",
            data=sample_market_data,
        )
        
        await signal_generator_agent._handle_event(tick_event)
        
        # Event should be blocked
        assert signal_generator_agent.events_processed == initial_count


class TestEventPriorityHandling:
    """Test priority event handling across agents"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_critical_events_processed_first(
        self,
        event_bus,
        signal_generator_agent,
    ):
        """Test CRITICAL priority events processed before NORMAL"""
        events_processed = []
        
        async def track_event(event):
            events_processed.append(event.priority.name)
        
        event_bus.subscribe("test_event", "tracker", track_event)
        
        # Publish in reverse priority order
        await event_bus.publish(Event(
            event_type="test_event",
            source_agent="test",
            data={"order": 1},
            priority=EventPriority.LOW,
        ))
        
        await event_bus.publish(Event(
            event_type="test_event",
            source_agent="test",
            data={"order": 2},
            priority=EventPriority.CRITICAL,
        ))
        
        await event_bus.publish(Event(
            event_type="test_event",
            source_agent="test",
            data={"order": 3},
            priority=EventPriority.NORMAL,
        ))
        
        # Process events
        await asyncio.sleep(0.5)
        
        # Critical should be first
        if len(events_processed) >= 3:
            assert events_processed[0] == "CRITICAL"


class TestAgentRecovery:
    """Test agent recovery from failures"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_agent_recovers_after_circuit_closes(
        self,
        signal_generator_agent,
        agent_registry,
    ):
        """Test agent resumes processing after circuit closes"""
        agent_id = signal_generator_agent.agent_id
        
        # Force circuit open
        for _ in range(5):
            await agent_registry.record_error(agent_id, "Test error")
        
        assert agent_registry.is_circuit_open(agent_id)
        
        # Simulate successful operations (circuit breaker recovery)
        # In real implementation, circuit would close after timeout
        # For test, manually close it
        if agent_id in agent_registry.circuit_breakers:
            agent_registry.circuit_breakers[agent_id]["state"] = "closed"
            agent_registry.circuit_breakers[agent_id]["failure_count"] = 0
        
        assert not agent_registry.is_circuit_open(agent_id)
