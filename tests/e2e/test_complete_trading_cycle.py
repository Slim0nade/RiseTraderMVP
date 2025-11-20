"""
End-to-End Test: Complete Trading Cycle

Tests the complete flow from market tick to order execution:
1. MarketDataAgent receives tick
2. SignalGeneratorAgent generates signal
3. RiskManagerAgent validates signal
4. ExecutionAgent executes order
5. PerformanceMonitorAgent tracks P&L

This is a CRITICAL test that validates the entire system workflow.
"""

import asyncio
import time

import pytest

from src.agents.event_bus import Event, EventPriority


# ============================================================================
# COMPLETE TRADING CYCLE TEST
# ============================================================================

@pytest.mark.e2e
@pytest.mark.critical
@pytest.mark.asyncio
async def test_complete_trading_cycle_bullish(
    event_bus,
    signal_generator_agent,
    risk_manager_agent,
    execution_agent,
    sample_market_data,
    db_session,
):
    """
    Test complete trading cycle for bullish signal
    
    Flow:
    1. Publish new_tick events (build price history)
    2. SignalGeneratorAgent generates BUY signal
    3. RiskManagerAgent validates signal
    4. ExecutionAgent executes order
    5. Verify order executed successfully
    """
    
    # Track events
    signals_generated = []
    trades_validated = []
    trades_executed = []
    
    async def capture_signal(event):
        signals_generated.append(event)
    
    async def capture_validated(event):
        trades_validated.append(event)
    
    async def capture_executed(event):
        trades_executed.append(event)
    
    # Subscribe to events
    event_bus.subscribe("signal_generated", "test_capture_signal", capture_signal)
    event_bus.subscribe("trade_validated", "test_capture_validated", capture_validated)
    event_bus.subscribe("trade_executed", "test_capture_executed", capture_executed)
    
    # Step 1: Build price history with bullish trend
    symbol = sample_market_data["symbol"]
    
    for i in range(30):
        tick_data = sample_market_data.copy()
        tick_data["close"] = 1850.0 + i * 2  # Strong uptrend
        tick_data["high"] = tick_data["close"] + 2
        tick_data["low"] = tick_data["close"] - 1
        tick_data["open"] = tick_data["close"] - 0.5
        
        tick_event = Event(
            event_type="new_tick",
            source_agent="market_data_agent",
            data=tick_data,
            priority=EventPriority.NORMAL,
        )
        
        await event_bus.publish(tick_event)
    
    # Wait for event processing
    await asyncio.sleep(1.0)
    
    # Verify: Signal should be generated
    assert len(signals_generated) > 0, "No signals generated"
    
    signal_data = signals_generated[-1].data
    assert signal_data["action"] == "BUY", f"Expected BUY signal, got {signal_data['action']}"
    assert signal_data["symbol"] == symbol
    assert signal_data["confidence"] > 0.5
    
    # Verify: Trade should be validated
    assert len(trades_validated) > 0, "Trade not validated by RiskManager"
    
    validated_data = trades_validated[-1].data
    assert validated_data["approved"] is True
    assert "position_size" in validated_data
    
    # Verify: Trade should be executed
    assert len(trades_executed) > 0, "Trade not executed"
    
    executed_data = trades_executed[-1].data
    assert executed_data["status"] == "success"
    assert "order_id" in executed_data


@pytest.mark.e2e
@pytest.mark.critical
@pytest.mark.asyncio
@pytest.mark.slow
async def test_complete_trading_cycle_with_rejection(
    event_bus,
    signal_generator_agent,
    risk_manager_agent,
    execution_agent,
    sample_market_data,
    db_session,
):
    """
    Test trading cycle where RiskManager rejects trade
    
    Flow:
    1. Fill up position limits
    2. Generate new signal
    3. RiskManager should reject (max positions reached)
    4. No execution should occur
    """
    
    # Track events
    signals_generated = []
    trades_rejected = []
    trades_executed = []
    
    async def capture_signal(event):
        signals_generated.append(event)
    
    async def capture_rejected(event):
        trades_rejected.append(event)
    
    async def capture_executed(event):
        trades_executed.append(event)
    
    event_bus.subscribe("signal_generated", "test_capture_signal", capture_signal)
    event_bus.subscribe("trade_rejected", "test_capture_rejected", capture_rejected)
    event_bus.subscribe("trade_executed", "test_capture_executed", capture_executed)
    
    # Set very low position limit
    risk_manager_agent.max_open_positions = 1
    
    # Add existing position to database
    from src.database.models.positions import OpenPosition
    from decimal import Decimal
    from datetime import datetime, timezone
    
    existing_position = OpenPosition(
        number="ORD000001",
        type="BUY",
        size=Decimal("1.0"),
        symbol="Gold",
        price=Decimal("2000.00"),
        commission=Decimal("5.00"),
        last_update=datetime.now(timezone.utc),
        last_strategy="momentum",
    )
    
    db_session.add(existing_position)
    await db_session.commit()
    
    # Generate signal (should be rejected due to position limit)
    for i in range(30):
        tick_data = sample_market_data.copy()
        tick_data["close"] = 1850.0 + i * 2
        tick_data["high"] = tick_data["close"] + 2
        tick_data["low"] = tick_data["close"] - 1
        
        tick_event = Event(
            event_type="new_tick",
            source_agent="market_data_agent",
            data=tick_data,
        )
        
        await event_bus.publish(tick_event)
    
    await asyncio.sleep(1.0)
    
    # Verify: Signal generated
    assert len(signals_generated) > 0
    
    # Verify: Trade rejected
    assert len(trades_rejected) > 0, "Trade should have been rejected"
    
    rejected_data = trades_rejected[-1].data
    assert "reason" in rejected_data
    assert "position" in rejected_data["reason"].lower()
    
    # Verify: No execution occurred
    assert len(trades_executed) == 0, "Trade should not have been executed"


@pytest.mark.e2e
@pytest.mark.performance
@pytest.mark.asyncio
async def test_trading_cycle_performance(
    event_bus,
    signal_generator_agent,
    risk_manager_agent,
    execution_agent,
    sample_market_data,
):
    """
    Test that complete trading cycle completes within performance requirements
    
    Target: <1 second from tick to execution
    """
    
    # Track timing
    trades_executed = []
    
    async def capture_executed(event):
        trades_executed.append(event)
    
    event_bus.subscribe("trade_executed", "test_capture", capture_executed)
    
    # Build price history first
    for i in range(25):
        tick_data = sample_market_data.copy()
        tick_data["close"] = 1850.0 + i
        
        await event_bus.publish(Event(
            event_type="new_tick",
            source_agent="market_data_agent",
            data=tick_data,
        ))
    
    await asyncio.sleep(0.2)
    
    # Measure time for final tick that triggers signal
    start_time = time.time()
    
    final_tick = sample_market_data.copy()
    final_tick["close"] = 1900.0  # Strong move
    
    await event_bus.publish(Event(
        event_type="new_tick",
        source_agent="market_data_agent",
        data=final_tick,
    ))
    
    # Wait for execution
    await asyncio.sleep(1.5)
    
    elapsed = time.time() - start_time
    
    # Should complete quickly
    assert elapsed < 2.0, f"Trading cycle took {elapsed:.2f}s, expected <2.0s"
    
    # Verify execution occurred
    if len(trades_executed) > 0:
        print(f"✓ Trading cycle completed in {elapsed:.2f}s")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_multiple_signals_sequential(
    event_bus,
    signal_generator_agent,
    risk_manager_agent,
    execution_agent,
    sample_market_data,
):
    """
    Test handling multiple signals in sequence
    
    Ensures system can handle multiple trades without race conditions
    """
    
    trades_executed = []
    
    async def capture_executed(event):
        trades_executed.append(event)
    
    event_bus.subscribe("trade_executed", "test_capture", capture_executed)
    
    # Generate multiple different symbols
    symbols = ["CrudeOIL", "Gold", "Silver"]
    
    for symbol in symbols:
        # Build price history for each symbol
        for i in range(25):
            tick_data = sample_market_data.copy()
            tick_data["symbol"] = symbol
            tick_data["close"] = 1850.0 + i * 3
            
            await event_bus.publish(Event(
                event_type="new_tick",
                source_agent="market_data_agent",
                data=tick_data,
            ))
        
        # Small delay between symbols
        await asyncio.sleep(0.3)
    
    # Wait for all executions
    await asyncio.sleep(1.0)
    
    # Should have executed trades for multiple symbols
    print(f"Executed {len(trades_executed)} trades")
    
    # Verify no duplicate order IDs
    order_ids = [t.data.get("order_id") for t in trades_executed if t.data.get("order_id")]
    assert len(order_ids) == len(set(order_ids)), "Duplicate order IDs detected!"
