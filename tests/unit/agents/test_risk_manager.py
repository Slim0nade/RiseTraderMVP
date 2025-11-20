"""
Unit Tests for RiskManagerAgent

Tests:
- Risk validation checks (position size, daily loss, open positions, correlation)
- Position sizing methods (Kelly, fixed, volatility-adjusted)
- Trade rejection scenarios
- Position tracking
- Account balance management
"""

import asyncio
import pytest
from decimal import Decimal

from src.agents.event_bus import Event, EventPriority


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestRiskManagerInitialization:
    """Test RiskManagerAgent initialization"""
    
    @pytest.mark.asyncio
    @pytest.mark.agent
    async def test_agent_creation(, risk_manager_agent):
        """Test agent creation with default config"""
        assert risk_manager_agent.agent_id == "risk_manager_test"
        assert risk_manager_agent.status.value == "running"
        assert risk_manager_agent.priority == 2  # High priority
    
    @pytest.mark.asyncio
    async def test_risk_limits_configured(self, risk_manager_agent):
        """Test risk limits loaded from config"""
        assert risk_manager_agent.max_position_size == 10.0
        assert risk_manager_agent.max_daily_loss == 1000.0
        assert risk_manager_agent.max_open_positions == 5
    
    @pytest.mark.asyncio
    async def test_event_subscriptions(self, risk_manager_agent):
        """Test agent subscribes to correct events"""
        assert "signal_generated" in risk_manager_agent._subscribed_events
        assert "trade_executed" in risk_manager_agent._subscribed_events
        assert "position_updated" in risk_manager_agent._subscribed_events


# ============================================================================
# RISK VALIDATION TESTS
# ============================================================================

class TestRiskValidation:
    """Test trade validation logic"""
    
    @pytest.mark.asyncio
    @pytest.mark.agent
    @pytest.mark.critical
    async def test_validate_trade_success(self, risk_manager_agent, sample_signal):
        """Test valid trade passes all checks"""
        # Setup clean state
        risk_manager_agent.open_positions = []
        risk_manager_agent.daily_pnl = 0.0
        risk_manager_agent.account_balance = 10000.0
        
        is_valid, reason = await risk_manager_agent._validate_trade(sample_signal)
        
        assert is_valid is True
        assert reason is None
    
    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_reject_daily_loss_exceeded(self, risk_manager_agent, sample_signal):
        """Test trade rejected when daily loss limit exceeded"""
        risk_manager_agent.daily_pnl = -1500.0  # Exceeds -1000 limit
        risk_manager_agent.max_daily_loss = 1000.0
        
        is_valid, reason = await risk_manager_agent._validate_trade(sample_signal)
        
        assert is_valid is False
        assert reason == "daily_loss_limit_exceeded"
    
    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_reject_max_positions_exceeded(self, risk_manager_agent, sample_signal):
        """Test trade rejected when max positions exceeded"""
        # Fill up positions
        risk_manager_agent.open_positions = [
            {"symbol": f"SYMBOL{i}", "side": "BUY"} for i in range(5)
        ]
        risk_manager_agent.max_open_positions = 5
        
        is_valid, reason = await risk_manager_agent._validate_trade(sample_signal)
        
        assert is_valid is False
        assert reason == "max_open_positions_exceeded"
    
    @pytest.mark.asyncio
    async def test_reject_opposing_position(self, risk_manager_agent, sample_signal):
        """Test trade rejected when opposing position exists"""
        # Existing SELL position
        risk_manager_agent.open_positions = [
            {"symbol": "CrudeOIL", "side": "SELL"}
        ]
        
        # Try to BUY same symbol
        signal = sample_signal.copy()
        signal["action"] = "BUY"
        signal["symbol"] = "CrudeOIL"
        
        is_valid, reason = await risk_manager_agent._validate_trade(signal)
        
        assert is_valid is False
        assert reason == "opposing_position_exists"
    
    @pytest.mark.asyncio
    async def test_reject_position_already_exists(self, risk_manager_agent, sample_signal):
        """Test trade rejected when position already exists in same direction"""
        # Existing BUY position
        risk_manager_agent.open_positions = [
            {"symbol": "CrudeOIL", "side": "BUY"}
        ]
        
        # Try to BUY same symbol again
        signal = sample_signal.copy()
        signal["action"] = "BUY"
        signal["symbol"] = "CrudeOIL"
        
        is_valid, reason = await risk_manager_agent._validate_trade(signal)
        
        assert is_valid is False
        assert reason == "position_already_exists"
    
    @pytest.mark.asyncio
    async def test_reject_insufficient_balance(self, risk_manager_agent, sample_signal):
        """Test trade rejected when account balance insufficient"""
        risk_manager_agent.account_balance = 0.0
        
        is_valid, reason = await risk_manager_agent._validate_trade(sample_signal)
        
        assert is_valid is False
        assert reason == "insufficient_balance"
    
    @pytest.mark.asyncio
    async def test_reject_low_confidence(self, risk_manager_agent, sample_signal):
        """Test trade rejected when signal confidence too low"""
        signal = sample_signal.copy()
        signal["confidence"] = 0.3  # Below 0.5 minimum
        
        is_valid, reason = await risk_manager_agent._validate_trade(signal)
        
        assert is_valid is False
        assert reason == "low_signal_confidence"


# ============================================================================
# POSITION SIZING TESTS
# ============================================================================

class TestPositionSizing:
    """Test position sizing calculations"""
    
    @pytest.mark.asyncio
    async def test_kelly_criterion_sizing(self, risk_manager_agent):
        """Test Kelly Criterion position sizing"""
        risk_manager_agent.sizing_method = "kelly"
        risk_manager_agent.account_balance = 10000.0
        risk_manager_agent.max_position_size = 1000.0
        
        # High confidence signal
        size = risk_manager_agent._kelly_criterion_size(confidence=0.7)
        
        assert size > 0
        assert size <= risk_manager_agent.max_position_size
    
    @pytest.mark.asyncio
    async def test_kelly_sizing_respects_max_limit(self, risk_manager_agent):
        """Test Kelly sizing respects max position size"""
        risk_manager_agent.account_balance = 100000.0  # Large balance
        risk_manager_agent.max_position_size = 500.0
        
        size = risk_manager_agent._kelly_criterion_size(confidence=0.9)
        
        assert size <= 500.0
    
    @pytest.mark.asyncio
    async def test_kelly_sizing_low_confidence(self, risk_manager_agent):
        """Test Kelly sizing with low confidence"""
        risk_manager_agent.account_balance = 10000.0
        
        size_high = risk_manager_agent._kelly_criterion_size(confidence=0.8)
        size_low = risk_manager_agent._kelly_criterion_size(confidence=0.5)
        
        # Higher confidence = larger size
        assert size_high > size_low
    
    @pytest.mark.asyncio
    async def test_fixed_sizing(self, risk_manager_agent):
        """Test fixed percentage sizing"""
        risk_manager_agent.sizing_method = "fixed"
        risk_manager_agent.account_balance = 10000.0
        risk_manager_agent.risk_per_trade = 0.02  # 2%
        risk_manager_agent.max_position_size = 1000.0
        
        size = risk_manager_agent._fixed_size()
        
        assert size == 200.0  # 2% of 10000
    
    @pytest.mark.asyncio
    async def test_fixed_sizing_respects_max(self, risk_manager_agent):
        """Test fixed sizing respects max limit"""
        risk_manager_agent.account_balance = 100000.0
        risk_manager_agent.risk_per_trade = 0.1  # 10%
        risk_manager_agent.max_position_size = 500.0
        
        size = risk_manager_agent._fixed_size()
        
        assert size == 500.0  # Capped at max
    
    @pytest.mark.asyncio
    async def test_volatility_adjusted_sizing(self, risk_manager_agent, sample_signal):
        """Test volatility-adjusted sizing"""
        risk_manager_agent.sizing_method = "volatility"
        risk_manager_agent.account_balance = 10000.0
        risk_manager_agent.risk_per_trade = 0.02
        risk_manager_agent.max_position_size = 1000.0
        
        # Mock volatility in context
        await risk_manager_agent.set_context("volatility_CrudeOIL", "0.01")  # Low vol
        
        size = await risk_manager_agent._volatility_adjusted_size(sample_signal)
        
        assert size > 0
        assert size <= risk_manager_agent.max_position_size


# ============================================================================
# EVENT HANDLING TESTS
# ============================================================================

class TestEventHandling:
    """Test event processing"""
    
    @pytest.mark.asyncio
    @pytest.mark.agent
    async def test_process_signal_generated_event(self, risk_manager_agent, sample_signal, event_bus):
        """Test processing signal_generated event"""
        # Setup valid state
        risk_manager_agent.open_positions = []
        risk_manager_agent.daily_pnl = 0.0
        risk_manager_agent.account_balance = 10000.0
        
        # Track published events
        published_events = []
        
        async def capture_event(event):
            published_events.append(event)
        
        event_bus.subscribe("trade_validated", "test_capture", capture_event)
        
        signal_event = Event(
            event_type="signal_generated",
            source_agent="signal_generator",
            data=sample_signal,
        )
        
        await risk_manager_agent.process_event(signal_event)
        
        # Allow processing
        await asyncio.sleep(0.2)
        
        # Should emit trade_validated
        assert len(published_events) > 0
        assert published_events[0].event_type == "trade_validated"
        assert "position_size" in published_events[0].data
    
    @pytest.mark.asyncio
    async def test_process_trade_executed_event(self, risk_manager_agent):
        """Test processing trade_executed event"""
        initial_positions = len(risk_manager_agent.open_positions)
        
        trade_data = {
            "symbol": "CrudeOIL",
            "action": "BUY",
            "position_size": 1.0,
            "fill_price": 1850.50,
        }
        
        trade_event = Event(
            event_type="trade_executed",
            source_agent="execution_agent",
            data=trade_data,
        )
        
        await risk_manager_agent.process_event(trade_event)
        
        # Should add to open positions
        assert len(risk_manager_agent.open_positions) == initial_positions + 1
        assert risk_manager_agent.open_positions[-1]["symbol"] == "CrudeOIL"
    
    @pytest.mark.asyncio
    async def test_process_position_closed_event(self, risk_manager_agent):
        """Test processing position closed event"""
        # Setup open position
        risk_manager_agent.open_positions = [
            {"symbol": "CrudeOIL", "side": "BUY", "size": 1.0}
        ]
        risk_manager_agent.account_balance = 10000.0
        
        position_data = {
            "symbol": "CrudeOIL",
            "status": "CLOSED",
            "pnl": 150.0,
        }
        
        position_event = Event(
            event_type="position_updated",
            source_agent="mt4_connector",
            data=position_data,
        )
        
        await risk_manager_agent.process_event(position_event)
        
        # Position should be removed
        assert len(risk_manager_agent.open_positions) == 0
        
        # P&L should be updated
        assert risk_manager_agent.daily_pnl == 150.0
        assert risk_manager_agent.account_balance == 10150.0


# ============================================================================
# TRADE REJECTION TESTS
# ============================================================================

class TestTradeRejection:
    """Test trade rejection scenarios"""
    
    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_rejection_event_emitted(self, risk_manager_agent, sample_signal, event_bus):
        """Test trade_rejected event emitted on rejection"""
        # Force rejection
        risk_manager_agent.daily_pnl = -1500.0
        risk_manager_agent.max_daily_loss = 1000.0
        
        # Track events
        published_events = []
        
        async def capture_event(event):
            published_events.append(event)
        
        event_bus.subscribe("trade_rejected", "test_capture", capture_event)
        
        signal_event = Event(
            event_type="signal_generated",
            source_agent="signal_generator",
            data=sample_signal,
        )
        
        await risk_manager_agent.process_event(signal_event)
        await asyncio.sleep(0.2)
        
        # Should emit trade_rejected
        assert len(published_events) > 0
        assert published_events[0].event_type == "trade_rejected"
        assert "reason" in published_events[0].data
    
    @pytest.mark.asyncio
    async def test_rejection_reasons_tracked(self, risk_manager_agent, sample_signal):
        """Test rejection reasons are tracked"""
        # Force rejection
        risk_manager_agent.account_balance = 0.0
        
        signal_event = Event(
            event_type="signal_generated",
            source_agent="signal_generator",
            data=sample_signal,
        )
        
        await risk_manager_agent.process_event(signal_event)
        
        # Rejection reason should be tracked
        assert "insufficient_balance" in risk_manager_agent.rejection_reasons
        assert risk_manager_agent.rejection_reasons["insufficient_balance"] > 0


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Test performance requirements"""
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_validation_performance(self, risk_manager_agent, sample_signal):
        """Test validation completes within 30ms"""
        import time
        
        # Setup valid state
        risk_manager_agent.open_positions = []
        risk_manager_agent.daily_pnl = 0.0
        risk_manager_agent.account_balance = 10000.0
        
        start_time = time.time()
        
        await risk_manager_agent._validate_trade(sample_signal)
        
        elapsed = time.time() - start_time
        
        assert elapsed < 0.03  # Less than 30ms


# ============================================================================
# CORRELATION TESTS
# ============================================================================

class TestCorrelationChecks:
    """Test position correlation checks"""
    
    @pytest.mark.asyncio
    async def test_correlation_check_no_positions(self, risk_manager_agent):
        """Test correlation check with no open positions"""
        risk_manager_agent.open_positions = []
        
        result = await risk_manager_agent._check_correlation("CrudeOIL")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_correlation_check_different_symbols(self, risk_manager_agent):
        """Test correlation check with different symbols"""
        risk_manager_agent.open_positions = [
            {"symbol": "EURUSD", "side": "BUY"}
        ]
        
        result = await risk_manager_agent._check_correlation("CrudeOIL")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_correlation_check_same_symbol(self, risk_manager_agent):
        """Test correlation check rejects same symbol"""
        risk_manager_agent.open_positions = [
            {"symbol": "CrudeOIL", "side": "BUY"}
        ]
        
        result = await risk_manager_agent._check_correlation("CrudeOIL")
        
        assert result is False


# ============================================================================
# STATISTICS TESTS
# ============================================================================

class TestStatistics:
    """Test statistics tracking"""
    
    @pytest.mark.asyncio
    async def test_trades_validated_counter(self, risk_manager_agent, sample_signal):
        """Test validated trades counter"""
        risk_manager_agent.open_positions = []
        risk_manager_agent.daily_pnl = 0.0
        risk_manager_agent.account_balance = 10000.0
        
        initial_count = risk_manager_agent.trades_validated
        
        signal_event = Event(
            event_type="signal_generated",
            source_agent="signal_generator",
            data=sample_signal,
        )
        
        await risk_manager_agent.process_event(signal_event)
        await asyncio.sleep(0.1)
        
        assert risk_manager_agent.trades_validated == initial_count + 1
    
    @pytest.mark.asyncio
    async def test_trades_rejected_counter(self, risk_manager_agent, sample_signal):
        """Test rejected trades counter"""
        risk_manager_agent.account_balance = 0.0  # Force rejection
        
        initial_count = risk_manager_agent.trades_rejected
        
        signal_event = Event(
            event_type="signal_generated",
            source_agent="signal_generator",
            data=sample_signal,
        )
        
        await risk_manager_agent.process_event(signal_event)
        await asyncio.sleep(0.1)
        
        assert risk_manager_agent.trades_rejected == initial_count + 1
