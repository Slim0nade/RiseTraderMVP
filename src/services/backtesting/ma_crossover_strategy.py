"""
Simple MA Crossover Strategy - Clean and Fast

Strategy:
- BUY: When MA20 crosses above MA50 (Golden Cross)
- SELL: When MA20 crosses below MA50 (Death Cross)
- Stop Loss: 2% ATR
- Take Profit: 3x Stop Loss
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from datetime import datetime
import numpy as np

from .data_replay_engine import MarketTick


@dataclass
class MACrossoverParams:
    """Simple MA crossover parameters."""
    fast_ma: int = 20
    slow_ma: int = 50
    quantity: Decimal = Decimal("1.0")
    atr_period: int = 14
    atr_multiplier: float = 2.0
    take_profit_multiplier: float = 3.0


@dataclass
class MACrossoverState:
    """Strategy state."""
    has_position: bool = False
    position_type: Optional[str] = None
    entry_price: Optional[Decimal] = None
    entry_time: Optional[datetime] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None

    # MA tracking
    prev_fast_ma: Optional[float] = None
    prev_slow_ma: Optional[float] = None


@dataclass
class MASignal:
    """Trading signal."""
    action: Optional[str]  # 'buy', 'sell', 'close_long', 'close_short', None
    quantity: Decimal
    confidence: float
    reason: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class MACrossoverStrategy:
    """
    Simple and robust MA crossover strategy.

    NO complex filters - just pure crossover logic.
    """

    def __init__(self, params: Optional[MACrossoverParams] = None):
        self.params = params or MACrossoverParams()
        self.state = MACrossoverState()
        self.price_history = []

    def on_tick(self, tick: MarketTick) -> MASignal:
        """Process new tick and return trading signal."""
        # Add to price history
        self.price_history.append({
            'timestamp': tick.timestamp,
            'close': float(tick.close),
            'high': float(tick.high),
            'low': float(tick.low),
        })

        # Need enough data for slow MA
        if len(self.price_history) < self.params.slow_ma + 1:
            return MASignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason=f"Warming up: {len(self.price_history)}/{self.params.slow_ma + 1}"
            )

        # Calculate MAs
        closes = [p['close'] for p in self.price_history]
        fast_ma = np.mean(closes[-self.params.fast_ma:])
        slow_ma = np.mean(closes[-self.params.slow_ma:])

        # If we have a position, check exit conditions
        if self.state.has_position:
            return self._manage_position(tick)

        # Check for crossover entry signals
        if self.state.prev_fast_ma is not None and self.state.prev_slow_ma is not None:
            # Golden Cross: Fast MA crosses above Slow MA
            if (self.state.prev_fast_ma <= self.state.prev_slow_ma and
                fast_ma > slow_ma):
                signal = self._open_position('buy', tick)
                self.state.prev_fast_ma = fast_ma
                self.state.prev_slow_ma = slow_ma
                return signal

            # Death Cross: Fast MA crosses below Slow MA
            if (self.state.prev_fast_ma >= self.state.prev_slow_ma and
                fast_ma < slow_ma):
                signal = self._open_position('sell', tick)
                self.state.prev_fast_ma = fast_ma
                self.state.prev_slow_ma = slow_ma
                return signal

        # Update previous MAs
        self.state.prev_fast_ma = fast_ma
        self.state.prev_slow_ma = slow_ma

        return MASignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=f"No crossover (Fast: {fast_ma:.2f}, Slow: {slow_ma:.2f})"
        )

    def _calculate_atr(self) -> float:
        """Calculate Average True Range."""
        if len(self.price_history) < self.params.atr_period:
            return 1.0

        highs = [p['high'] for p in self.price_history[-self.params.atr_period:]]
        lows = [p['low'] for p in self.price_history[-self.params.atr_period:]]
        closes = [p['close'] for p in self.price_history[-self.params.atr_period-1:-1]]

        true_ranges = []
        for i in range(len(highs)):
            if i == 0:
                tr = highs[i] - lows[i]
            else:
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i-1]),
                    abs(lows[i] - closes[i-1])
                )
            true_ranges.append(tr)

        return np.mean(true_ranges)

    def _open_position(self, direction: str, tick: MarketTick) -> MASignal:
        """Open a new position."""
        price = float(tick.close)
        atr = self._calculate_atr()
        stop_distance = atr * self.params.atr_multiplier
        tp_distance = stop_distance * self.params.take_profit_multiplier

        if direction == 'buy':
            stop_loss = price - stop_distance
            take_profit = price + tp_distance
        else:
            stop_loss = price + stop_distance
            take_profit = price - tp_distance

        # Update state
        self.state.has_position = True
        self.state.position_type = direction
        self.state.entry_price = tick.close
        self.state.entry_time = tick.timestamp
        self.state.stop_loss = Decimal(str(stop_loss))
        self.state.take_profit = Decimal(str(take_profit))

        return MASignal(
            action=direction,
            quantity=self.params.quantity,
            confidence=0.9,
            reason=f"MA Crossover {direction.upper()}",
            stop_loss=stop_loss,
            take_profit=take_profit
        )

    def _manage_position(self, tick: MarketTick) -> MASignal:
        """Manage open position - check stops and targets."""
        current_price = float(tick.close)

        # Check stop loss
        if self.state.position_type == 'buy':
            if current_price <= float(self.state.stop_loss):
                return self._close_position(tick, "Stop loss hit")
            if current_price >= float(self.state.take_profit):
                return self._close_position(tick, "Take profit hit")
        else:  # sell
            if current_price >= float(self.state.stop_loss):
                return self._close_position(tick, "Stop loss hit")
            if current_price <= float(self.state.take_profit):
                return self._close_position(tick, "Take profit hit")

        return MASignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason="Holding position"
        )

    def _close_position(self, tick: MarketTick, reason: str) -> MASignal:
        """Close current position."""
        close_action = 'close_long' if self.state.position_type == 'buy' else 'close_short'

        # Reset state
        self.state.has_position = False
        self.state.position_type = None
        self.state.entry_price = None
        self.state.entry_time = None
        self.state.stop_loss = None
        self.state.take_profit = None

        return MASignal(
            action=close_action,
            quantity=self.params.quantity,
            confidence=0.8,
            reason=reason
        )
