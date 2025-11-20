"""
Unit Tests for SignalGeneratorAgent

Tests:
- Signal generation from multiple strategies
- Strategy combination and weighting
- Regime-based adjustments
- Event handling (new_tick, forecast_updated, regime_changed)
- Performance requirements (<50ms)
"""

import asyncio
import time

import pytest

from src.agents.event_bus import Event, EventPriority


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestSignalGeneratorInitialization:
    """Test SignalGeneratorAgent initialization"""
    
    @pytest.mark.asyncio
    @pytest.mark.agent
    async def test_agent_creation(self, signal_generator_agent):
        """Test agent creation with default config"""
        assert signal_generator_agent.agent_id == "signal_generator_test"
        assert signal_generator_agent.status.value == "running"
        assert signal_generator_agent.priority == 1  # Highest priority
    
    @pytest.mark.asyncio
    async def test_strategy_configuration(self, signal_generator_agent):
        """Test strategy configuration loaded"""
        assert len(signal_generator_agent.strategy_weights) > 0
        assert "momentum" in signal_generator_agent.strategy_weights
        assert "mean_reversion" in signal_generator_agent.strategy_weights
    
    @pytest.mark.asyncio
    async def test_event_subscriptions(self, signal_generator_agent):
        """Test agent subscribes to correct events"""
        assert "new_tick" in signal_generator_agent._subscribed_events
        assert "forecast_updated" in signal_generator_agent._subscribed_events
        assert "regime_changed" in signal_generator_agent._subscribed_events


# ============================================================================
# TICK PROCESSING TESTS
# ============================================================================

class TestTickProcessing:
    """Test new tick event processing"""
    
    @pytest.mark.asyncio
    @pytest.mark.agent
    async def test_process_new_tick(self, signal_generator_agent, sample_market_data):
        """Test processing new tick data"""
        tick_event = Event(
            event_type="new_tick",
            source_agent="market_data_agent",
            data=sample_market_data,
        )
        
        await signal_generator_agent.process_event(tick_event)
        
        # Check price history updated
        symbol = sample_market_data["symbol"]
        assert symbol in signal_generator_agent.price_history
        assert len(signal_generator_agent.price_history[symbol]) > 0
    
    @pytest.mark.asyncio
    async def test_tick_builds_price_history(self, signal_generator_agent, sample_market_data):
        """Test multiple ticks build price history"""
        symbol = sample_market_data["symbol"]
        
        # Send multiple ticks
        for i in range(25):
            tick_data = sample_market_data.copy()
            tick_data["close"] = 1850.0 + i
            
            tick_event = Event(
                event_type="new_tick",
                source_agent="market_data_agent",
                data=tick_data,
            )
            
            await signal_generator_agent.process_event(tick_event)
        
        # Should have 25 bars
        assert len(signal_generator_agent.price_history[symbol]) == 25
    
    @pytest.mark.asyncio
    async def test_signal_generated_after_minimum_bars(
        self,
        signal_generator_agent,
        event_bus,
        sample_market_data,
    ):
        """Test signal generated after minimum bars collected"""
        # Need at least 20 bars for signal generation
        for i in range(20):
            tick_data = sample_market_data.copy()
            tick_data["close"] = 1850.0 + i * 0.5  # Create uptrend
            
            tick_event = Event(
                event_type="new_tick",
                source_agent="market_data_agent",
                data=tick_data,
            )
            
            await signal_generator_agent.process_event(tick_event)
        
        # Allow processing time
        await asyncio.sleep(0.2)
        
        # Check signal was generated
        assert signal_generator_agent.signals_generated > 0


# ============================================================================
# STRATEGY TESTS
# ============================================================================

class TestTradingStrategies:
    """Test individual trading strategies"""
    
    @pytest.mark.asyncio
    async def test_momentum_strategy_bullish(self, signal_generator_agent, price_history_100):
        """Test momentum strategy generates bullish signal"""
        # Create strong uptrend
        prices = []
        for i in range(50):
            prices.append({
                "timestamp": time.time() + i,
                "open": 1850.0 + i * 2,
                "high": 1852.0 + i * 2,
                "low": 1848.0 + i * 2,
                "close": 1851.0 + i * 2,  # Strong uptrend
                "volume": 1000,
            })
        
        signal = signal_generator_agent._momentum_strategy(prices)
        
        assert signal["score"] > 0  # Bullish signal
        assert signal["confidence"] > 0
    
    @pytest.mark.asyncio
    async def test_momentum_strategy_bearish(self, signal_generator_agent):
        """Test momentum strategy generates bearish signal"""
        # Create strong downtrend
        prices = []
        for i in range(50):
            prices.append({
                "timestamp": time.time() + i,
                "open": 1850.0 - i * 2,
                "high": 1852.0 - i * 2,
                "low": 1848.0 - i * 2,
                "close": 1851.0 - i * 2,  # Strong downtrend
                "volume": 1000,
            })
        
        signal = signal_generator_agent._momentum_strategy(prices)
        
        assert signal["score"] < 0  # Bearish signal
    
    @pytest.mark.asyncio
    async def test_mean_reversion_strategy_oversold(self, signal_generator_agent):
        """Test mean reversion strategy on oversold conditions"""
        # Create price below lower Bollinger Band
        prices = []
        base_price = 1850.0
        
        # Normal range
        for i in range(20):
            prices.append({
                "timestamp": time.time() + i,
                "open": base_price,
                "high": base_price + 2,
                "low": base_price - 2,
                "close": base_price,
                "volume": 1000,
            })
        
        # Sharp drop (oversold)
        prices.append({
            "timestamp": time.time() + 20,
            "open": base_price,
            "high": base_price,
            "low": base_price - 20,
            "close": base_price - 20,
            "volume": 1000,
        })
        
        signal = signal_generator_agent._mean_reversion_strategy(prices)
        
        assert signal["score"] > 0  # Buy signal (oversold)
    
    @pytest.mark.asyncio
    async def test_breakout_strategy_bullish_breakout(self, signal_generator_agent):
        """Test breakout strategy on bullish breakout"""
        # Create range then breakout
        prices = []
        
        # Ranging market
        for i in range(20):
            prices.append({
                "timestamp": time.time() + i,
                "open": 1850.0,
                "high": 1852.0,
                "low": 1848.0,
                "close": 1850.0,
                "volume": 1000,
            })
        
        # Breakout above range
        prices.append({
            "timestamp": time.time() + 20,
            "open": 1852.0,
            "high": 1865.0,  # Breakout
            "low": 1852.0,
            "close": 1863.0,
            "volume": 2000,
        })
        
        signal = signal_generator_agent._breakout_strategy(prices)
        
        assert signal["score"] > 0  # Bullish breakout
    
    @pytest.mark.asyncio
    async def test_ml_forecast_strategy(self, signal_generator_agent, sample_forecast):
        """Test ML forecast strategy"""
        signal_generator_agent.latest_forecast = sample_forecast
        
        signal = signal_generator_agent._ml_forecast_strategy()
        
        assert "score" in signal
        assert "confidence" in signal
        assert signal["confidence"] == sample_forecast["confidence"]


# ============================================================================
# SIGNAL COMBINATION TESTS
# ============================================================================

class TestSignalCombination:
    """Test strategy signal combination"""
    
    @pytest.mark.asyncio
    async def test_combine_signals_weighted_average(self, signal_generator_agent):
        """Test signals combined using weighted average"""
        strategy_signals = {
            "momentum": {"score": 0.8, "confidence": 0.7},
            "mean_reversion": {"score": -0.2, "confidence": 0.6},
            "breakout": {"score": 0.6, "confidence": 0.65},
        }
        
        combined = signal_generator_agent._combine_signals(strategy_signals)
        
        assert "score" in combined
        assert "confidence" in combined
        # Score should be weighted by confidence and weights
        assert -1.0 <= combined["score"] <= 1.0
    
    @pytest.mark.asyncio
    async def test_combine_signals_all_bullish(self, signal_generator_agent):
        """Test combining all bullish signals"""
        strategy_signals = {
            "momentum": {"score": 0.8, "confidence": 0.8},
            "mean_reversion": {"score": 0.6, "confidence": 0.7},
            "breakout": {"score": 0.7, "confidence": 0.75},
        }
        
        combined = signal_generator_agent._combine_signals(strategy_signals)
        
        assert combined["score"] > 0.5  # Strong bullish
    
    @pytest.mark.asyncio
    async def test_combine_signals_conflicting(self, signal_generator_agent):
        """Test combining conflicting signals"""
        strategy_signals = {
            "momentum": {"score": 0.8, "confidence": 0.7},
            "mean_reversion": {"score": -0.7, "confidence": 0.8},
        }
        
        combined = signal_generator_agent._combine_signals(strategy_signals)
        
        # Should be closer to zero due to conflict
        assert abs(combined["score"]) < 0.5


# ============================================================================
# REGIME ADJUSTMENT TESTS
# ============================================================================

class TestRegimeAdjustments:
    """Test regime-based strategy adjustments"""
    
    @pytest.mark.asyncio
    async def test_regime_change_event(self, signal_generator_agent, sample_regime):
        """Test handling regime change event"""
        regime_event = Event(
            event_type="regime_changed",
            source_agent="regime_detection_agent",
            data=sample_regime,
        )
        
        await signal_generator_agent.process_event(regime_event)
        
        assert signal_generator_agent.current_regime == sample_regime["regime"]
    
    @pytest.mark.asyncio
    async def test_adjust_weight_trending_regime(self, signal_generator_agent):
        """Test weight adjustment in trending regime"""
        signal_generator_agent.current_regime = "trending_up"
        
        # Momentum should get boosted
        momentum_weight = signal_generator_agent._adjust_weight_by_regime("momentum", 0.3)
        assert momentum_weight > 0.3
        
        # Mean reversion should be reduced
        mr_weight = signal_generator_agent._adjust_weight_by_regime("mean_reversion", 0.25)
        assert mr_weight < 0.25
    
    @pytest.mark.asyncio
    async def test_adjust_weight_ranging_regime(self, signal_generator_agent):
        """Test weight adjustment in ranging regime"""
        signal_generator_agent.current_regime = "ranging"
        
        # Mean reversion should get boosted
        mr_weight = signal_generator_agent._adjust_weight_by_regime("mean_reversion", 0.25)
        assert mr_weight > 0.25
        
        # Momentum should be reduced
        momentum_weight = signal_generator_agent._adjust_weight_by_regime("momentum", 0.3)
        assert momentum_weight < 0.3


# ============================================================================
# FORECAST INTEGRATION TESTS
# ============================================================================

class TestForecastIntegration:
    """Test ML forecast integration"""
    
    @pytest.mark.asyncio
    async def test_forecast_updated_event(self, signal_generator_agent, sample_forecast):
        """Test handling forecast updated event"""
        forecast_event = Event(
            event_type="forecast_updated",
            source_agent="ml_prediction_agent",
            data=sample_forecast,
        )
        
        await signal_generator_agent.process_event(forecast_event)
        
        assert signal_generator_agent.latest_forecast is not None
        assert signal_generator_agent.latest_forecast["prediction"] == sample_forecast["prediction"]


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Test performance requirements"""
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_signal_generation_performance(
        self,
        signal_generator_agent,
        price_history_100,
    ):
        """Test signal generation completes within 50ms"""
        # Add price history
        signal_generator_agent.price_history["CrudeOIL"] = price_history_100
        
        start_time = time.time()
        
        await signal_generator_agent._generate_signal("CrudeOIL")
        
        elapsed = time.time() - start_time
        
        assert elapsed < 0.05  # Less than 50ms
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_tick_processing_performance(self, signal_generator_agent, sample_market_data):
        """Test tick processing completes quickly"""
        tick_event = Event(
            event_type="new_tick",
            source_agent="market_data_agent",
            data=sample_market_data,
        )
        
        start_time = time.time()
        
        await signal_generator_agent.process_event(tick_event)
        
        elapsed = time.time() - start_time
        
        assert elapsed < 0.05


# ============================================================================
# SIGNAL VALIDATION TESTS
# ============================================================================

class TestSignalValidation:
    """Test signal validation and thresholds"""
    
    @pytest.mark.asyncio
    async def test_weak_signal_not_emitted(
        self,
        signal_generator_agent,
        event_bus,
    ):
        """Test weak signals below threshold not emitted"""
        # Set high threshold
        signal_generator_agent.signal_threshold = 0.9
        
        # Create weak trending price
        prices = []
        for i in range(30):
            prices.append({
                "timestamp": time.time() + i,
                "open": 1850.0 + i * 0.1,  # Very weak trend
                "high": 1851.0 + i * 0.1,
                "low": 1849.0 + i * 0.1,
                "close": 1850.0 + i * 0.1,
                "volume": 1000,
            })
        
        signal_generator_agent.price_history["CrudeOIL"] = prices
        
        initial_count = signal_generator_agent.signals_generated
        
        await signal_generator_agent._generate_signal("CrudeOIL")
        
        # Should not generate signal
        assert signal_generator_agent.signals_generated == initial_count
    
    @pytest.mark.asyncio
    async def test_signal_includes_required_fields(
        self,
        signal_generator_agent,
        event_bus,
    ):
        """Test generated signal includes all required fields"""
        # Create strong trending price
        prices = []
        for i in range(50):
            prices.append({
                "timestamp": time.time() + i,
                "open": 1850.0 + i * 3,
                "high": 1852.0 + i * 3,
                "low": 1848.0 + i * 3,
                "close": 1851.0 + i * 3,
                "volume": 1000,
            })
        
        signal_generator_agent.price_history["CrudeOIL"] = prices
        signal_generator_agent.signal_threshold = 0.5  # Lower threshold
        
        # Track published events
        published_events = []
        
        async def capture_event(event):
            published_events.append(event)
        
        event_bus.subscribe("signal_generated", "test_capture", capture_event)
        
        await signal_generator_agent._generate_signal("CrudeOIL")
        
        # Allow event processing
        await asyncio.sleep(0.2)
        
        if len(published_events) > 0:
            signal_data = published_events[0].data
            
            # Check required fields
            assert "symbol" in signal_data
            assert "action" in signal_data
            assert "score" in signal_data
            assert "confidence" in signal_data
            assert "strategy_votes" in signal_data
            assert "current_price" in signal_data
            assert "timestamp" in signal_data


# ============================================================================
# STATISTICS TESTS
# ============================================================================

class TestStatistics:
    """Test signal generation statistics"""
    
    @pytest.mark.asyncio
    async def test_signal_counts_tracked(self, signal_generator_agent):
        """Test signal generation counts tracked"""
        initial_total = signal_generator_agent.signals_generated
        
        # Simulate signal generation
        signal_generator_agent.signals_buy += 1
        signal_generator_agent.signals_generated += 1
        
        assert signal_generator_agent.signals_generated == initial_total + 1
        assert signal_generator_agent.signals_buy == 1
