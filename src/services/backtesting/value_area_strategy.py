"""
Value Area Trading Strategy

A mean-reversion strategy based on Volume Profile / Market Profile concepts.
Uses Time-Price-Opportunity (TPO) analysis to identify value areas.

Core Concepts:
- Value Area High (VAH): Upper boundary of 70% volume zone
- Value Area Low (VAL): Lower boundary of 70% volume zone
- Point of Control (POC): Price level with most time/volume
- Initial Balance (IB): First hour's trading range

Strategy Logic:
- BUY when price drops below VAL and shows rejection (bullish signal)
- SELL when price rises above VAH and shows rejection (bearish signal)
- Target POC as the mean-reversion point
- Stop loss beyond the extreme with ATR buffer

Best suited for:
- Range-bound markets
- High-liquidity instruments (Crude Oil, Gold, major Forex)
- Intraday to swing trading timeframes

Author: Claude (RiseTrader Strategy Development)
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
from collections import defaultdict

from .data_replay_engine import MarketTick


@dataclass
class ValueAreaParams:
    """
    Value Area Trading strategy parameters.

    Defaults tuned for commodities (Crude Oil, Gold).
    """
    # Value Area Calculation
    lookback_periods: int = 24  # Hours to calculate value area (1 day for H1)
    value_area_percent: float = 0.70  # 70% of volume/time = value area
    tpo_resolution: float = 0.10  # Price bucket size (0.10 = 10 cents for CL)

    # Entry Conditions
    require_rejection: bool = True  # Require bullish/bearish rejection candle
    min_penetration_atr: float = 0.3  # Min ATR multiples beyond VAH/VAL
    max_penetration_atr: float = 2.0  # Max ATR multiples (avoid breakouts)

    # Risk Management
    atr_period: int = 14
    stop_atr_multiplier: float = 1.5  # SL beyond entry by ATR multiple
    target_mode: str = "poc"  # "poc", "opposite_va", "fixed_rr"
    fixed_rr_ratio: float = 2.0  # If target_mode="fixed_rr"

    # Position Sizing
    quantity: Decimal = Decimal("1.0")
    risk_percent: float = 1.0

    # Time Filters
    use_time_filter: bool = True
    trading_start_hour: int = 8  # GMT
    trading_end_hour: int = 20  # GMT
    avoid_first_hour: bool = True  # Avoid trading in Initial Balance period

    # Exit Conditions
    use_poc_exit: bool = True  # Exit at POC
    use_opposite_va_exit: bool = False  # Exit at opposite VA boundary
    trailing_stop_atr: float = 0.0  # 0 = disabled, >0 = trailing stop ATR mult


@dataclass
class ValueAreaState:
    """Track current value area state."""
    vah: Optional[float] = None  # Value Area High
    val: Optional[float] = None  # Value Area Low
    poc: Optional[float] = None  # Point of Control
    ib_high: Optional[float] = None  # Initial Balance High
    ib_low: Optional[float] = None  # Initial Balance Low

    # Position tracking
    has_position: bool = False
    position_type: Optional[str] = None  # 'buy' or 'sell'
    entry_price: Optional[Decimal] = None
    entry_time: Optional[datetime] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None


@dataclass
class ValueAreaSignal:
    """Trading signal from Value Area strategy."""
    action: Optional[str]  # 'buy', 'sell', 'close_long', 'close_short', or None
    quantity: Decimal
    confidence: float
    reason: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class ValueAreaStrategy:
    """
    Value Area Trading Strategy Implementation.

    Uses TPO (Time-Price-Opportunity) profile as a proxy for volume profile.
    Trades mean reversion from value area extremes back to POC.

    Entry Logic:
    1. Calculate Value Area from recent price distribution
    2. Wait for price to move beyond VAH or VAL
    3. Confirm rejection (reversal candle pattern)
    4. Enter with target at POC

    Exit Logic:
    1. Take profit at POC or opposite VA boundary
    2. Stop loss beyond entry extreme
    3. Optional trailing stop
    """

    def __init__(self, params: Optional[ValueAreaParams] = None):
        """Initialize strategy with parameters."""
        self.params = params or ValueAreaParams()
        self.state = ValueAreaState()

        # Price history for calculations
        self.price_history: List[Dict] = []
        self.max_history = max(200, self.params.lookback_periods * 2)

        # TPO profile data structure
        self.tpo_profile: Dict[float, int] = defaultdict(int)

    @property
    def has_position(self) -> bool:
        return self.state.has_position

    @property
    def entry_price(self) -> Optional[Decimal]:
        return self.state.entry_price

    def reset(self) -> None:
        """Reset strategy state for new backtest."""
        self.state = ValueAreaState()
        self.price_history.clear()
        self.tpo_profile.clear()

    def process_tick(self, tick: MarketTick) -> ValueAreaSignal:
        """
        Process market tick and generate trading signal.

        Main entry point matching SyntheticEngine interface.
        """
        # Update price history
        self._update_history(tick)

        # Check warmup period
        if len(self.price_history) < self.params.lookback_periods + 1:
            return ValueAreaSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason=f"Warming up: {len(self.price_history)}/{self.params.lookback_periods + 1} candles"
            )

        # Update TPO profile and calculate value area
        self._update_tpo_profile()
        self._calculate_value_area()

        # Check time filter
        if not self._is_time_to_trade(tick.timestamp):
            return ValueAreaSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="Outside trading hours"
            )

        # Manage existing position
        if self.state.has_position:
            return self._manage_position(tick)

        # Check for new entry
        return self._check_entry(tick)

    def _update_history(self, tick: MarketTick) -> None:
        """Update price history with new tick."""
        self.price_history.append({
            'timestamp': tick.timestamp,
            'open': float(tick.open),
            'high': float(tick.high),
            'low': float(tick.low),
            'close': float(tick.close),
            'volume': tick.volume
        })

        if len(self.price_history) > self.max_history:
            self.price_history.pop(0)

    def _update_tpo_profile(self) -> None:
        """Update TPO (Time-Price-Opportunity) profile."""
        # Clear and rebuild from lookback window
        self.tpo_profile.clear()

        lookback_bars = self.price_history[-self.params.lookback_periods:]
        resolution = self.params.tpo_resolution

        for bar in lookback_bars:
            # Each price level touched gets a TPO count
            low_bucket = int(bar['low'] / resolution) * resolution
            high_bucket = int(bar['high'] / resolution) * resolution

            price = low_bucket
            while price <= high_bucket:
                self.tpo_profile[round(price, 4)] += 1
                price += resolution

    def _calculate_value_area(self) -> None:
        """Calculate VAH, VAL, and POC from TPO profile."""
        if not self.tpo_profile:
            return

        # Find POC (price with max TPO count)
        poc_price = max(self.tpo_profile, key=self.tpo_profile.get)
        self.state.poc = poc_price

        # Calculate total TPOs
        total_tpos = sum(self.tpo_profile.values())
        target_tpos = int(total_tpos * self.params.value_area_percent)

        # Build value area from POC outward
        sorted_prices = sorted(self.tpo_profile.keys())
        poc_idx = sorted_prices.index(poc_price)

        va_tpos = self.tpo_profile[poc_price]
        low_idx = poc_idx
        high_idx = poc_idx

        while va_tpos < target_tpos:
            # Expand to whichever side has more TPOs
            expand_low = low_idx > 0
            expand_high = high_idx < len(sorted_prices) - 1

            if expand_low and expand_high:
                low_tpos = self.tpo_profile[sorted_prices[low_idx - 1]]
                high_tpos = self.tpo_profile[sorted_prices[high_idx + 1]]

                if low_tpos >= high_tpos:
                    low_idx -= 1
                    va_tpos += low_tpos
                else:
                    high_idx += 1
                    va_tpos += high_tpos
            elif expand_low:
                low_idx -= 1
                va_tpos += self.tpo_profile[sorted_prices[low_idx]]
            elif expand_high:
                high_idx += 1
                va_tpos += self.tpo_profile[sorted_prices[high_idx]]
            else:
                break

        self.state.val = sorted_prices[low_idx]
        self.state.vah = sorted_prices[high_idx]

    def _is_time_to_trade(self, timestamp: datetime) -> bool:
        """Check if current time is within trading hours."""
        if not self.params.use_time_filter:
            return True

        hour = timestamp.hour

        # Check trading hours
        if hour < self.params.trading_start_hour or hour >= self.params.trading_end_hour:
            return False

        # Avoid first hour (Initial Balance period)
        if self.params.avoid_first_hour and hour == self.params.trading_start_hour:
            return False

        return True

    def _check_entry(self, tick: MarketTick) -> ValueAreaSignal:
        """Check for new trade entry signals."""
        if self.state.vah is None or self.state.val is None:
            return ValueAreaSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="Value area not calculated"
            )

        current_price = float(tick.close)
        atr = self._calculate_atr()

        if atr == 0:
            atr = abs(self.state.vah - self.state.val) * 0.1  # Fallback

        # Check for price below VAL (potential long)
        if current_price < self.state.val:
            penetration = (self.state.val - current_price) / atr

            if self.params.min_penetration_atr <= penetration <= self.params.max_penetration_atr:
                if not self.params.require_rejection or self._is_bullish_rejection():
                    stop_loss = current_price - (atr * self.params.stop_atr_multiplier)
                    take_profit = self._calculate_target('buy', current_price, atr)

                    return self._open_position(
                        'buy', tick, stop_loss, take_profit,
                        f"BUY: Price {current_price:.2f} below VAL {self.state.val:.2f}, "
                        f"target POC {self.state.poc:.2f}"
                    )

        # Check for price above VAH (potential short)
        if current_price > self.state.vah:
            penetration = (current_price - self.state.vah) / atr

            if self.params.min_penetration_atr <= penetration <= self.params.max_penetration_atr:
                if not self.params.require_rejection or self._is_bearish_rejection():
                    stop_loss = current_price + (atr * self.params.stop_atr_multiplier)
                    take_profit = self._calculate_target('sell', current_price, atr)

                    return self._open_position(
                        'sell', tick, stop_loss, take_profit,
                        f"SELL: Price {current_price:.2f} above VAH {self.state.vah:.2f}, "
                        f"target POC {self.state.poc:.2f}"
                    )

        return ValueAreaSignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=f"No signal: Price {current_price:.2f} | VAH {self.state.vah:.2f} | "
                   f"VAL {self.state.val:.2f} | POC {self.state.poc:.2f}"
        )

    def _is_bullish_rejection(self) -> bool:
        """Check for bullish rejection candle pattern."""
        if len(self.price_history) < 2:
            return False

        curr = self.price_history[-1]
        prev = self.price_history[-2]

        # Bullish: current close > current open AND current close > prev close
        bullish_candle = curr['close'] > curr['open']
        higher_close = curr['close'] > prev['close']

        # Long lower wick indicates rejection
        body = abs(curr['close'] - curr['open'])
        lower_wick = min(curr['open'], curr['close']) - curr['low']
        has_rejection_wick = lower_wick > body * 0.5

        return bullish_candle and (higher_close or has_rejection_wick)

    def _is_bearish_rejection(self) -> bool:
        """Check for bearish rejection candle pattern."""
        if len(self.price_history) < 2:
            return False

        curr = self.price_history[-1]
        prev = self.price_history[-2]

        # Bearish: current close < current open AND current close < prev close
        bearish_candle = curr['close'] < curr['open']
        lower_close = curr['close'] < prev['close']

        # Long upper wick indicates rejection
        body = abs(curr['close'] - curr['open'])
        upper_wick = curr['high'] - max(curr['open'], curr['close'])
        has_rejection_wick = upper_wick > body * 0.5

        return bearish_candle and (lower_close or has_rejection_wick)

    def _calculate_target(self, direction: str, entry_price: float, atr: float) -> float:
        """Calculate take profit target based on target_mode."""
        if self.params.target_mode == "poc":
            return self.state.poc
        elif self.params.target_mode == "opposite_va":
            return self.state.vah if direction == 'buy' else self.state.val
        else:  # fixed_rr
            distance = atr * self.params.stop_atr_multiplier * self.params.fixed_rr_ratio
            return entry_price + distance if direction == 'buy' else entry_price - distance

    def _open_position(
        self,
        position_type: str,
        tick: MarketTick,
        stop_loss: float,
        take_profit: float,
        reason: str
    ) -> ValueAreaSignal:
        """Open a new position."""
        # Update state
        self.state.has_position = True
        self.state.position_type = position_type
        self.state.entry_price = tick.close
        self.state.entry_time = tick.timestamp
        self.state.stop_loss = Decimal(str(stop_loss))
        self.state.take_profit = Decimal(str(take_profit))

        return ValueAreaSignal(
            action=position_type,
            quantity=self.params.quantity,
            confidence=0.7,
            reason=reason,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

    def _manage_position(self, tick: MarketTick) -> ValueAreaSignal:
        """Manage existing position - check for exit conditions."""
        current_price = float(tick.close)
        entry_price = float(self.state.entry_price)

        # Calculate profit
        if self.state.position_type == 'buy':
            profit_points = current_price - entry_price

            # Check stop loss
            if current_price <= float(self.state.stop_loss):
                return self._close_position(tick, "Stop loss hit")

            # Check take profit
            if current_price >= float(self.state.take_profit):
                return self._close_position(tick, "Take profit hit (POC reached)")

        else:  # sell
            profit_points = entry_price - current_price

            # Check stop loss
            if current_price >= float(self.state.stop_loss):
                return self._close_position(tick, "Stop loss hit")

            # Check take profit
            if current_price <= float(self.state.take_profit):
                return self._close_position(tick, "Take profit hit (POC reached)")

        return ValueAreaSignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=f"Holding {self.state.position_type}: profit={profit_points:.4f}"
        )

    def _close_position(self, tick: MarketTick, reason: str) -> ValueAreaSignal:
        """Close current position."""
        position_type = self.state.position_type
        close_action = 'close_long' if position_type == 'buy' else 'close_short'

        # Reset state
        self.state.has_position = False
        self.state.position_type = None
        self.state.entry_price = None
        self.state.entry_time = None
        self.state.stop_loss = None
        self.state.take_profit = None

        return ValueAreaSignal(
            action=close_action,
            quantity=self.params.quantity,
            confidence=0.8,
            reason=f"CLOSE {position_type.upper()}: {reason}"
        )

    def _calculate_atr(self) -> float:
        """Calculate Average True Range."""
        period = self.params.atr_period

        if len(self.price_history) < period + 1:
            return 0.0

        true_ranges = []

        for i in range(-period, 0):
            bar = self.price_history[i]
            prev_bar = self.price_history[i - 1]

            high_low = bar['high'] - bar['low']
            high_prev_close = abs(bar['high'] - prev_bar['close'])
            low_prev_close = abs(bar['low'] - prev_bar['close'])

            true_range = max(high_low, high_prev_close, low_prev_close)
            true_ranges.append(true_range)

        return np.mean(true_ranges) if true_ranges else 0.0

    def get_state(self) -> Dict:
        """Get current strategy state."""
        return {
            'strategy': 'value_area',
            'params': {
                'lookback_periods': self.params.lookback_periods,
                'value_area_percent': self.params.value_area_percent,
                'stop_atr_multiplier': self.params.stop_atr_multiplier,
                'target_mode': self.params.target_mode,
            },
            'value_area': {
                'vah': self.state.vah,
                'val': self.state.val,
                'poc': self.state.poc,
            },
            'has_position': self.state.has_position,
            'position_type': self.state.position_type,
            'entry_price': str(self.state.entry_price) if self.state.entry_price else None,
            'stop_loss': str(self.state.stop_loss) if self.state.stop_loss else None,
            'take_profit': str(self.state.take_profit) if self.state.take_profit else None,
            'price_history_length': len(self.price_history)
        }


def create_value_area_strategy(**kwargs) -> ValueAreaStrategy:
    """
    Factory function to create ValueAreaStrategy with custom parameters.

    Args:
        **kwargs: Parameters to override defaults.
            - lookback_periods: Periods for value area calc (default: 24)
            - value_area_percent: % for value area (default: 0.70)
            - tpo_resolution: Price bucket size (default: 0.10)
            - stop_atr_multiplier: ATR mult for SL (default: 1.5)
            - target_mode: "poc", "opposite_va", "fixed_rr" (default: "poc")
            - require_rejection: Require rejection candle (default: True)

    Returns:
        Configured ValueAreaStrategy instance

    Example:
        >>> strategy = create_value_area_strategy(
        ...     lookback_periods=48,
        ...     stop_atr_multiplier=2.0
        ... )
    """
    params = ValueAreaParams(**kwargs)
    return ValueAreaStrategy(params=params)
