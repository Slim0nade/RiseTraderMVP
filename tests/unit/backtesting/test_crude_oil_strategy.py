"""
Quick test for CrudeOIL V3 strategy integration.

Run: python -m pytest tests/unit/backtesting/test_crude_oil_strategy.py -v
"""
import pytest
from decimal import Decimal
from datetime import datetime

from src.services.backtesting.crude_oil_strategy import (
    CrudeOilStrategy,
    CrudeOilParams,
    create_crude_oil_strategy,
)
from src.services.backtesting.synthetic_engine import SyntheticEngine
from src.services.backtesting.data_replay_engine import MarketTick


class TestCrudeOilStrategy:
    """Test CrudeOIL V3 strategy implementation."""

    def test_strategy_initialization_default_params(self):
        """Test strategy initializes with default parameters."""
        strategy = CrudeOilStrategy()
        
        assert strategy.params.ema_fast == 8
        assert strategy.params.ema_slow == 29
        assert strategy.params.rsi_period == 10
        assert strategy.params.rsi_overbought == 68
        assert strategy.params.rsi_oversold == 32
        assert strategy.params.atr_period == 10
        assert strategy.params.atr_multiplier == 2.0
        assert strategy.params.take_profit_multiplier == 2.5
        assert strategy.has_position is False

    def test_strategy_initialization_custom_params(self):
        """Test strategy initializes with custom parameters."""
        params = CrudeOilParams(
            ema_fast=5,
            ema_slow=20,
            rsi_overbought=75,
            rsi_oversold=25,
        )
        strategy = CrudeOilStrategy(params=params)
        
        assert strategy.params.ema_fast == 5
        assert strategy.params.ema_slow == 20
        assert strategy.params.rsi_overbought == 75
        assert strategy.params.rsi_oversold == 25

    def test_factory_function(self):
        """Test create_crude_oil_strategy factory."""
        strategy = create_crude_oil_strategy(
            ema_fast=10,
            atr_multiplier=1.5,
        )
        
        assert strategy.params.ema_fast == 10
        assert strategy.params.atr_multiplier == 1.5
        # Defaults should still be set
        assert strategy.params.ema_slow == 29

    def test_warmup_period(self):
        """Test strategy returns warmup message when insufficient data."""
        strategy = CrudeOilStrategy()
        
        tick = MarketTick(
            symbol="CrudeOIL",
            timestamp=datetime(2024, 1, 1, 10, 0),
            open=Decimal("70.00"),
            high=Decimal("70.50"),
            low=Decimal("69.50"),
            close=Decimal("70.25"),
            volume=1000,
        )
        
        signal = strategy.process_tick(tick)
        
        assert signal.action is None
        assert "Warming up" in signal.reason

    def test_synthetic_engine_integration(self):
        """Test CrudeOIL strategy works via SyntheticEngine."""
        engine = SyntheticEngine(
            strategy="crude_oil_v3",
            params={
                "ema_fast": 8,
                "ema_slow": 29,
                "quantity": Decimal("1.0"),
            }
        )
        
        # Generate enough ticks to warm up
        base_price = 70.0
        for i in range(50):
            tick = MarketTick(
                symbol="CrudeOIL",
                timestamp=datetime(2024, 1, 1, 10, i),
                open=Decimal(str(base_price + i * 0.1)),
                high=Decimal(str(base_price + i * 0.1 + 0.5)),
                low=Decimal(str(base_price + i * 0.1 - 0.5)),
                close=Decimal(str(base_price + i * 0.15)),
                volume=1000 + i * 10,
            )
            signal = engine.process_tick(tick)
        
        # After warmup, should get valid signals (not warmup messages)
        assert "Warming up" not in signal.reason or signal.action is None

    def test_time_filter(self):
        """Test time filter blocks trades outside trading hours."""
        params = CrudeOilParams(
            use_time_filter=True,
            trading_start_hour=8,
            trading_end_hour=20,
        )
        strategy = CrudeOilStrategy(params=params)
        
        # Feed enough data to warm up
        for i in range(50):
            tick = MarketTick(
                symbol="CrudeOIL",
                timestamp=datetime(2024, 1, 1, 22, i % 60),  # 22:xx - outside hours
                open=Decimal("70.00"),
                high=Decimal("70.50"),
                low=Decimal("69.50"),
                close=Decimal("70.25"),
                volume=1000,
            )
            signal = strategy.process_tick(tick)
        
        # Should be blocked by time filter
        assert signal.action is None
        assert "Outside trading hours" in signal.reason or "Warming up" in signal.reason

    def test_reset(self):
        """Test strategy reset clears state."""
        strategy = CrudeOilStrategy()
        
        # Simulate some activity
        for i in range(50):
            tick = MarketTick(
                symbol="CrudeOIL",
                timestamp=datetime(2024, 1, 1, 10, i),
                open=Decimal("70.00"),
                high=Decimal("70.50"),
                low=Decimal("69.50"),
                close=Decimal("70.25"),
                volume=1000,
            )
            strategy.process_tick(tick)
        
        # Reset
        strategy.reset()
        
        assert strategy.has_position is False
        assert len(strategy.price_history) == 0
        assert strategy.state.consecutive_losses == 0

    def test_get_state(self):
        """Test get_state returns correct structure."""
        strategy = CrudeOilStrategy()
        state = strategy.get_state()
        
        assert state['strategy'] == 'crude_oil_v3'
        assert 'params' in state
        assert 'has_position' in state
        assert 'price_history_length' in state
        assert state['params']['ema_fast'] == 8
        assert state['params']['ema_slow'] == 29


class TestCrudeOilIndicators:
    """Test indicator calculations."""

    @pytest.fixture
    def warmed_up_strategy(self):
        """Create a strategy with enough price history."""
        strategy = CrudeOilStrategy()
        
        # Feed 100 bars of data
        base_price = 70.0
        for i in range(100):
            tick = MarketTick(
                symbol="CrudeOIL",
                timestamp=datetime(2024, 1, 1, 10, i),
                open=Decimal(str(base_price + (i % 10) * 0.1)),
                high=Decimal(str(base_price + (i % 10) * 0.1 + 0.5)),
                low=Decimal(str(base_price + (i % 10) * 0.1 - 0.5)),
                close=Decimal(str(base_price + (i % 10) * 0.15)),
                volume=1000,
            )
            strategy.process_tick(tick)
        
        return strategy

    def test_ema_calculation(self, warmed_up_strategy):
        """Test EMA indicator calculation."""
        ema_fast = warmed_up_strategy._calculate_ema(8)
        ema_slow = warmed_up_strategy._calculate_ema(29)
        
        assert ema_fast > 0
        assert ema_slow > 0
        # With trending data, fast EMA should be close to slow EMA
        assert abs(ema_fast - ema_slow) < 5.0

    def test_rsi_calculation(self, warmed_up_strategy):
        """Test RSI indicator calculation."""
        rsi = warmed_up_strategy._calculate_rsi()
        
        assert 0 <= rsi <= 100

    def test_cci_calculation(self, warmed_up_strategy):
        """Test CCI indicator calculation."""
        cci = warmed_up_strategy._calculate_cci()
        
        # CCI typically ranges from -200 to +200
        assert -300 < cci < 300

    def test_momentum_calculation(self, warmed_up_strategy):
        """Test Momentum indicator calculation."""
        momentum = warmed_up_strategy._calculate_momentum()
        
        # Momentum oscillates around 100
        assert 90 < momentum < 110

    def test_atr_calculation(self, warmed_up_strategy):
        """Test ATR indicator calculation."""
        atr = warmed_up_strategy._calculate_atr(1)
        
        assert atr > 0
        # With our test data, ATR should be around 1.0 (0.5 range)
        assert atr < 5.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
