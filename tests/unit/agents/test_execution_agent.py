"""
Unit Tests for ExecutionAgent

Tests:
- ZMQ MT4 connection handling
- Trade execution with retry logic
- Slippage calculation and validation
- Error handling and recovery
- Connection timeout handling
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import time

from src.agents.event_bus import Event, EventPriority


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestExecutionAgentInitialization:
    """Test ExecutionAgent initialization"""
    
    @pytest.mark.asyncio
    @pytest.mark.agent
    async def test_agent_creation(self, execution_agent):
        """Test agent creation with default config"""
        assert execution_agent.agent_id == "execution_test"
        assert execution_agent.status.value == "running"
        assert execution_agent.priority == 3
    
    @pytest.mark.asyncio
    async def test_mt4_configuration(self, execution_agent):
        """Test MT4 configuration loaded"""
        assert execution_agent.mt4_host == "localhost"
        assert execution_agent.mt4_command_port == 5555
        assert execution_agent.max_retry == 3
    
    @pytest.mark.asyncio
    async def test_event_subscriptions(self, execution_agent):
        """Test agent subscribes to correct events"""
        assert "trade_validated" in execution_agent._subscribed_events


# ============================================================================
# TRADE EXECUTION TESTS
# ============================================================================

class TestTradeExecution:
    """Test trade execution logic"""
    
    @pytest.mark.asyncio
    @pytest.mark.agent
    @pytest.mark.critical
    async def test_execute_trade_success(self, execution_agent, sample_signal, event_bus):
        """Test successful trade execution"""
        # Mock MT4 connection
        execution_agent.mt4_connected = True
        execution_agent.zmq_socket = AsyncMock()
        execution_agent.zmq_socket.send_json = AsyncMock()
        execution_agent.zmq_socket.poll = AsyncMock(return_value=True)
        execution_agent.zmq_socket.recv_json = AsyncMock(return_value={
            "success": True,
            "order_id": "123456",
            "price": 1850.50,
            "timestamp": time.time(),
        })
        
        # Track events
        published_events = []
        
        async def capture_event(event):
            published_events.append(event)
        
        event_bus.subscribe("trade_executed", "test_capture", capture_event)
        
        trade_data = {
            **sample_signal,
            "position_size": 1.0,
        }
        
        trade_event = Event(
            event_type="trade_validated",
            source_agent="risk_manager",
            data=trade_data,
        )
        
        await execution_agent.process_event(trade_event)
        await asyncio.sleep(0.2)
        
        # Should emit trade_executed
        assert len(published_events) > 0
        assert published_events[0].event_type == "trade_executed"
        assert "order_id" in published_events[0].data
        assert "fill_price" in published_events[0].data
    
    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_execute_trade_with_retry(self, execution_agent, sample_signal, event_bus):
        """Test trade execution with retry on failure"""
        # Mock MT4 connection with failure then success
        execution_agent.mt4_connected = True
        execution_agent.zmq_socket = AsyncMock()
        execution_agent.zmq_socket.send_json = AsyncMock()
        execution_agent.zmq_socket.poll = AsyncMock(return_value=True)
        
        # First attempt fails, second succeeds
        execution_agent.zmq_socket.recv_json = AsyncMock(side_effect=[
            {"success": False, "error": "MT4 busy"},
            {"success": True, "order_id": "123456", "price": 1850.50, "timestamp": time.time()},
        ])
        
        trade_data = {
            **sample_signal,
            "position_size": 1.0,
        }
        
        trade_event = Event(
            event_type="trade_validated",
            source_agent="risk_manager",
            data=trade_data,
        )
        
        initial_retry_count = execution_agent.retry_count
        
        await execution_agent.process_event(trade_event)
        await asyncio.sleep(0.5)
        
        # Should have retried
        assert execution_agent.retry_count == initial_retry_count + 1
    
    @pytest.mark.asyncio
    async def test_execute_trade_max_retries_exceeded(self, execution_agent, sample_signal, event_bus):
        """Test trade fails after max retries"""
        # Mock MT4 connection with persistent failure
        execution_agent.mt4_connected = True
        execution_agent.zmq_socket = AsyncMock()
        execution_agent.zmq_socket.send_json = AsyncMock()
        execution_agent.zmq_socket.poll = AsyncMock(return_value=True)
        execution_agent.zmq_socket.recv_json = AsyncMock(return_value={
            "success": False,
            "error": "Insufficient margin",
        })
        
        # Track events
        published_events = []
        
        async def capture_event(event):
            published_events.append(event)
        
        event_bus.subscribe("trade_failed", "test_capture", capture_event)
        
        trade_data = {
            **sample_signal,
            "position_size": 1.0,
        }
        
        trade_event = Event(
            event_type="trade_validated",
            source_agent="risk_manager",
            data=trade_data,
        )
        
        await execution_agent.process_event(trade_event)
        await asyncio.sleep(2.0)  # Wait for retries
        
        # Should emit trade_failed
        assert len(published_events) > 0
        assert published_events[0].event_type == "trade_failed"
        assert execution_agent.trades_failed > 0


# ============================================================================
# SLIPPAGE TESTS
# ============================================================================

class TestSlippageHandling:
    """Test slippage calculation and validation"""
    
    @pytest.mark.asyncio
    async def test_calculate_slippage_positive(self, execution_agent):
        """Test positive slippage calculation"""
        expected_price = 1850.00
        fill_price = 1850.20  # Worse fill (buying)
        
        slippage = execution_agent._calculate_slippage(expected_price, fill_price)
        
        assert slippage > 0
        assert abs(slippage - 0.000108) < 0.00001  # Approximately 0.0108%
    
    @pytest.mark.asyncio
    async def test_calculate_slippage_negative(self, execution_agent):
        """Test negative slippage calculation"""
        expected_price = 1850.00
        fill_price = 1849.80  # Better fill
        
        slippage = execution_agent._calculate_slippage(expected_price, fill_price)
        
        assert slippage < 0
    
    @pytest.mark.asyncio
    async def test_calculate_slippage_zero(self, execution_agent):
        """Test zero slippage"""
        expected_price = 1850.00
        fill_price = 1850.00
        
        slippage = execution_agent._calculate_slippage(expected_price, fill_price)
        
        assert slippage == 0.0
    
    @pytest.mark.asyncio
    async def test_calculate_slippage_invalid_input(self, execution_agent):
        """Test slippage calculation with invalid input"""
        slippage = execution_agent._calculate_slippage(None, 1850.00)
        assert slippage == 0.0
        
        slippage = execution_agent._calculate_slippage(1850.00, None)
        assert slippage == 0.0
        
        slippage = execution_agent._calculate_slippage(None, None)
        assert slippage == 0.0
    
    @pytest.mark.asyncio
    async def test_high_slippage_warning_logged(self, execution_agent, sample_signal, event_bus):
        """Test warning logged when slippage is high"""
        # Mock MT4 with high slippage
        execution_agent.mt4_connected = True
        execution_agent.zmq_socket = AsyncMock()
        execution_agent.zmq_socket.send_json = AsyncMock()
        execution_agent.zmq_socket.poll = AsyncMock(return_value=True)
        execution_agent.zmq_socket.recv_json = AsyncMock(return_value={
            "success": True,
            "order_id": "123456",
            "price": 1855.00,  # High slippage from 1850
            "timestamp": time.time(),
        })
        
        trade_data = {
            **sample_signal,
            "position_size": 1.0,
            "current_price": 1850.00,
        }
        
        trade_event = Event(
            event_type="trade_validated",
            source_agent="risk_manager",
            data=trade_data,
        )
        
        await execution_agent.process_event(trade_event)
        await asyncio.sleep(0.2)
        
        # High slippage should be tracked
        assert execution_agent.total_slippage > 0


# ============================================================================
# CONNECTION TESTS
# ============================================================================

class TestMT4Connection:
    """Test MT4 ZMQ connection handling"""
    
    @pytest.mark.asyncio
    async def test_connection_timeout(self, execution_agent, sample_signal):
        """Test handling of connection timeout"""
        # Mock timeout
        execution_agent.mt4_connected = True
        execution_agent.zmq_socket = AsyncMock()
        execution_agent.zmq_socket.send_json = AsyncMock()
        execution_agent.zmq_socket.poll = AsyncMock(return_value=False)  # Timeout
        
        trade_data = {
            **sample_signal,
            "position_size": 1.0,
        }
        
        result = await execution_agent._execute_trade(trade_data)
        
        assert result["success"] is False
        assert "timeout" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_connection_not_established(self, execution_agent, sample_signal):
        """Test execution when MT4 not connected"""
        execution_agent.mt4_connected = False
        execution_agent.zmq_socket = None
        
        trade_data = {
            **sample_signal,
            "position_size": 1.0,
        }
        
        result = await execution_agent._execute_trade(trade_data)
        
        assert result["success"] is False
        assert "not connected" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_zmq_error_handling(self, execution_agent, sample_signal):
        """Test handling of ZMQ errors"""
        import zmq
        
        # Mock ZMQ error
        execution_agent.mt4_connected = True
        execution_agent.zmq_socket = AsyncMock()
        execution_agent.zmq_socket.send_json = AsyncMock(side_effect=zmq.error.ZMQError("Connection failed"))
        
        trade_data = {
            **sample_signal,
            "position_size": 1.0,
        }
        
        result = await execution_agent._execute_trade(trade_data)
        
        assert result["success"] is False
        assert "zmq" in result["error"].lower()
        assert execution_agent.mt4_connected is False  # Should mark as disconnected


# ============================================================================
# ORDER COMMAND TESTS
# ============================================================================

class TestOrderCommand:
    """Test order command formatting"""
    
    @pytest.mark.asyncio
    async def test_order_command_buy(self, execution_agent, sample_signal):
        """Test BUY order command formatting"""
        execution_agent.mt4_connected = True
        execution_agent.zmq_socket = AsyncMock()
        execution_agent.zmq_socket.send_json = AsyncMock()
        execution_agent.zmq_socket.poll = AsyncMock(return_value=True)
        execution_agent.zmq_socket.recv_json = AsyncMock(return_value={
            "success": True,
            "order_id": "123456",
            "price": 1850.50,
        })
        
        trade_data = {
            "symbol": "CrudeOIL",
            "action": "BUY",
            "position_size": 1.5,
            "current_price": 1850.00,
            "stop_loss": 1840.00,
            "take_profit": 1870.00,
        }
        
        await execution_agent._execute_trade(trade_data)
        
        # Check command sent
        execution_agent.zmq_socket.send_json.assert_called_once()
        command = execution_agent.zmq_socket.send_json.call_args[0][0]
        
        assert command["action"] == "OPEN_TRADE"
        assert command["type"] == "BUY"
        assert command["symbol"] == "CrudeOIL"
        assert command["volume"] == 1.5
    
    @pytest.mark.asyncio
    async def test_order_command_sell(self, execution_agent):
        """Test SELL order command formatting"""
        execution_agent.mt4_connected = True
        execution_agent.zmq_socket = AsyncMock()
        execution_agent.zmq_socket.send_json = AsyncMock()
        execution_agent.zmq_socket.poll = AsyncMock(return_value=True)
        execution_agent.zmq_socket.recv_json = AsyncMock(return_value={
            "success": True,
            "order_id": "123456",
            "price": 1850.50,
        })
        
        trade_data = {
            "symbol": "CrudeOIL",
            "action": "SELL",
            "position_size": 1.0,
            "current_price": 1850.00,
        }
        
        await execution_agent._execute_trade(trade_data)
        
        command = execution_agent.zmq_socket.send_json.call_args[0][0]
        
        assert command["type"] == "SELL"


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Test performance requirements"""
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_execution_performance(self, execution_agent, sample_signal):
        """Test execution completes within 500ms"""
        # Mock fast MT4 response
        execution_agent.mt4_connected = True
        execution_agent.zmq_socket = AsyncMock()
        execution_agent.zmq_socket.send_json = AsyncMock()
        execution_agent.zmq_socket.poll = AsyncMock(return_value=True)
        execution_agent.zmq_socket.recv_json = AsyncMock(return_value={
            "success": True,
            "order_id": "123456",
            "price": 1850.50,
            "timestamp": time.time(),
        })
        
        trade_data = {
            **sample_signal,
            "position_size": 1.0,
        }
        
        start_time = time.time()
        
        await execution_agent._execute_trade(trade_data)
        
        elapsed = time.time() - start_time
        
        assert elapsed < 0.5  # Less than 500ms


# ============================================================================
# STATISTICS TESTS
# ============================================================================

class TestStatistics:
    """Test statistics tracking"""
    
    @pytest.mark.asyncio
    async def test_trades_executed_counter(self, execution_agent, sample_signal, event_bus):
        """Test executed trades counter"""
        execution_agent.mt4_connected = True
        execution_agent.zmq_socket = AsyncMock()
        execution_agent.zmq_socket.send_json = AsyncMock()
        execution_agent.zmq_socket.poll = AsyncMock(return_value=True)
        execution_agent.zmq_socket.recv_json = AsyncMock(return_value={
            "success": True,
            "order_id": "123456",
            "price": 1850.50,
            "timestamp": time.time(),
        })
        
        initial_count = execution_agent.trades_executed
        
        trade_data = {
            **sample_signal,
            "position_size": 1.0,
        }
        
        trade_event = Event(
            event_type="trade_validated",
            source_agent="risk_manager",
            data=trade_data,
        )
        
        await execution_agent.process_event(trade_event)
        await asyncio.sleep(0.2)
        
        assert execution_agent.trades_executed == initial_count + 1
    
    @pytest.mark.asyncio
    async def test_slippage_tracking(self, execution_agent, sample_signal, event_bus):
        """Test slippage accumulation"""
        execution_agent.mt4_connected = True
        execution_agent.zmq_socket = AsyncMock()
        execution_agent.zmq_socket.send_json = AsyncMock()
        execution_agent.zmq_socket.poll = AsyncMock(return_value=True)
        execution_agent.zmq_socket.recv_json = AsyncMock(return_value={
            "success": True,
            "order_id": "123456",
            "price": 1850.50,
            "timestamp": time.time(),
        })
        
        trade_data = {
            **sample_signal,
            "position_size": 1.0,
            "current_price": 1850.00,
        }
        
        trade_event = Event(
            event_type="trade_validated",
            source_agent="risk_manager",
            data=trade_data,
        )
        
        await execution_agent.process_event(trade_event)
        await asyncio.sleep(0.2)
        
        assert execution_agent.total_slippage > 0
