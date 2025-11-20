"""
E2E Tests - Risk Management Scenarios

Tests:
- Daily loss limit triggers emergency stop
- Max position limit enforcement
- Position correlation blocking
- Risk rejection scenarios
"""

import asyncio
import pytest
from src.agents.event_bus import Event, EventPriority


class TestDailyLossLimit:
    """Test daily loss limit enforcement"""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.critical
    async def test_daily_loss_stops_trading(
        self,
        signal_generator_agent,
        risk_manager_agent,
        event_bus,
        sample_signal,
    ):
        """Test trading stops when daily loss limit hit"""
        # Set daily loss to limit
        risk_manager_agent.daily_pnl = -1000.0
        risk_manager_agent.max_daily_loss = 1000.0
        
        # Track rejection
        rejections = []
        
        async def capture_rejection(event):
            rejections.append(event)
        
        event_bus.subscribe("trade_rejected", "test", capture_rejection)
        
        # Try to place trade
        signal_event = Event(
            event_type="signal_generated",
            source_agent="signal_generator",
            data=sample_signal,
        )
        
        await event_bus.publish(signal_event)
        await asyncio.sleep(0.3)
        
        # Should be rejected
        assert len(rejections) > 0
        assert rejections[0].data["reason"] == "daily_loss_limit_exceeded"


class TestMaxPositionsLimit:
    """Test maximum positions enforcement"""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.critical
    async def test_max_positions_blocks_new_trades(
        self,
        risk_manager_agent,
        event_bus,
        sample_signal,
    ):
        """Test new trades blocked when max positions reached"""
        # Fill up positions
        risk_manager_agent.open_positions = [
            {"symbol": f"SYM{i}", "side": "BUY"} for i in range(5)
        ]
        risk_manager_agent.max_open_positions = 5
        risk_manager_agent.daily_pnl = 0.0
        risk_manager_agent.account_balance = 10000.0
        
        # Track rejection
        rejections = []
        
        async def capture_rejection(event):
            rejections.append(event)
        
        event_bus.subscribe("trade_rejected", "test", capture_rejection)
        
        # Try to place another trade
        signal_event = Event(
            event_type="signal_generated",
            source_agent="signal_generator",
            data=sample_signal,
        )
        
        await event_bus.publish(signal_event)
        await asyncio.sleep(0.3)
        
        # Should be rejected
        assert len(rejections) > 0
        assert rejections[0].data["reason"] == "max_open_positions_exceeded"


class TestEmergencyStop:
    """Test emergency stop scenarios"""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_circuit_breaker_emergency_stop(
        self,
        signal_generator_agent,
        agent_registry,
        event_bus,
    ):
        """Test circuit breaker stops agent on repeated failures"""
        # Force multiple failures
        for _ in range(5):
            await agent_registry.record_error(
                signal_generator_agent.agent_id,
                "Simulated failure"
            )
        
        # Circuit should be open
        assert agent_registry.is_circuit_open(signal_generator_agent.agent_id)
        
        # Events should be blocked
        initial_count = signal_generator_agent.events_processed
        
        test_event = Event(
            event_type="new_tick",
            source_agent="test",
            data={"symbol": "TEST", "close": 1850.0},
        )
        
        await signal_generator_agent._handle_event(test_event)
        
        # Should not process
        assert signal_generator_agent.events_processed == initial_count
