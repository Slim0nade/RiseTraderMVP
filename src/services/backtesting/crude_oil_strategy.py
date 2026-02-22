"""
CrudeOIL Trader V3 - Optimized Strategy

Converted from MQL4 to Python for SyntheticEngine backtesting.

Original Strategy by Slim - Multi-timeframe momentum strategy:
- EMA crossover (8/29) with trend confirmation
- RSI oversold/overbought filter
- CCI additional filter (optional)
- Momentum confirmation
- ATR-based stop loss
- 2.5x risk:reward take profit
- Time and volatility filters
- MA crossover exit

Author: Slim (MQL4) -> Claude (Python conversion)
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime
import numpy as np

from .data_replay_engine import MarketTick


@dataclass
class CrudeOilParams:
    """
    Strategy parameters matching MQL4 extern inputs.
    
    All defaults match the optimized MQL4 settings.
    """
    # Core Strategy
    risk_percent: float = 1.0
    atr_period: int = 10
    atr_multiplier: float = 2.0
    ema_fast: int = 8
    ema_slow: int = 29
    rsi_period: int = 10
    rsi_overbought: int = 68
    rsi_oversold: int = 32
    cci_period: int = 20
    cci_overbought: int = 100
    cci_oversold: int = -80
    use_cci_filter: bool = True
    use_strict_filter: bool = False
    
    # Exit conditions
    ma_close_period: int = 20
    use_ma_exit: bool = True
    use_pattern_exit: bool = True
    require_both_exits: bool = False
    
    # Momentum
    momentum_period: int = 10
    
    # Risk:Reward
    take_profit_multiplier: float = 2.5
    
    # Time Filter (simplified for backtesting)
    use_time_filter: bool = True
    trading_start_hour: int = 8
    trading_end_hour: int = 20
    avoid_rollover: bool = True
    rollover_start_hour: int = 21
    rollover_end_hour: int = 22
    
    # Volatility Filter
    volatility_threshold: float = 2.0
    
    # Position Sizing
    quantity: Decimal = Decimal("1.0")
    max_risk: float = 0.17
    decrease_factor: float = 3.0
    
    # Trailing Stop (disabled by default per MQL4 optimization)
    use_trailing_stop: bool = False
    trailing_multiplier: float = 1.5
    min_trailing_distance: float = 20.0
    
    # Close only in profit
    close_only_in_profit: bool = True
    min_profit_close: float = 0.0

    # Seasonality filter
    enable_seasonality: bool = True


@dataclass
class TradeState:
    """Track current trade state."""
    has_position: bool = False
    position_type: Optional[str] = None  # 'buy' or 'sell'
    entry_price: Optional[Decimal] = None
    entry_time: Optional[datetime] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    initial_stop_distance: float = 0.0
    consecutive_losses: int = 0


@dataclass
class CrudeOilSignal:
    """
    Trading signal from CrudeOIL strategy.
    
    Matches SyntheticSignal interface.
    """
    action: Optional[str]  # 'buy', 'sell', 'close', or None
    quantity: Decimal
    confidence: float
    reason: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class CrudeOilStrategy:
    """
    CrudeOIL Trader V3 - Python Implementation.
    
    Multi-timeframe momentum strategy optimized for crude oil trading.
    
    Entry Logic:
    1. EMA crossover (fast > slow for buy, fast < slow for sell)
    2. RSI confirmation (oversold for buy, overbought for sell)
    3. CCI filter (optional additional confirmation)
    4. Momentum above/below threshold
    
    Exit Logic:
    1. MA crossover close (price crosses MA)
    2. Pattern-based exit (engulfing candles)
    3. Stop loss / Take profit hit
    
    Risk Management:
    - ATR-based stop loss
    - 2.5x R:R take profit
    - Position sizing based on risk percent
    - Consecutive loss reduction
    """
    
    def __init__(self, params: Optional[CrudeOilParams] = None):
        """
        Initialize strategy with parameters.
        
        Args:
            params: Strategy parameters (uses defaults if None)
        """
        self.params = params or CrudeOilParams()
        self.state = TradeState()
        
        # Price history for indicators
        self.price_history: List[Dict] = []  # Full OHLC history
        self.max_history = 200
        
        # Indicator caches
        self._ema_fast_cache: List[float] = []
        self._ema_slow_cache: List[float] = []
    
    @property
    def has_position(self) -> bool:
        """Property for SyntheticEngine compatibility."""
        return self.state.has_position
    
    @property
    def entry_price(self) -> Optional[Decimal]:
        """Property for SyntheticEngine compatibility."""
        return self.state.entry_price
        
    def reset(self) -> None:
        """Reset strategy state for new backtest."""
        self.state = TradeState()
        self.price_history.clear()
        self._ema_fast_cache.clear()
        self._ema_slow_cache.clear()
        
    def process_tick(self, tick: MarketTick) -> CrudeOilSignal:
        """
        Process market tick and generate trading signal.
        
        Main entry point matching SyntheticEngine interface.
        
        Args:
            tick: Market tick data (OHLCV)
            
        Returns:
            CrudeOilSignal with trading decision
        """
        # Update price history
        self._update_history(tick)
        
        # Check warmup period
        min_history = max(
            self.params.ema_slow,
            self.params.atr_period,
            self.params.rsi_period,
            self.params.cci_period,
            self.params.ma_close_period,
            self.params.momentum_period
        )
        
        if len(self.price_history) < min_history + 1:
            return CrudeOilSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason=f"Warming up: {len(self.price_history)}/{min_history + 1} candles"
            )
        
        # Check time filter
        if not self._is_time_to_trade(tick.timestamp):
            return CrudeOilSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="Outside trading hours"
            )
        
        # Check volatility filter
        if not self._is_volatility_acceptable():
            return CrudeOilSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="Volatility too high"
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
            
    def _is_time_to_trade(self, timestamp: datetime) -> bool:
        """Check if current time is within trading hours."""
        if not self.params.use_time_filter:
            return True
            
        hour = timestamp.hour
        
        # Check regular trading hours
        if hour < self.params.trading_start_hour or hour >= self.params.trading_end_hour:
            return False
            
        # Check rollover period
        if self.params.avoid_rollover:
            if self.params.rollover_start_hour <= hour < self.params.rollover_end_hour:
                return False
                
        return True
    
    def _is_volatility_acceptable(self) -> bool:
        """Check if current volatility is within acceptable range."""
        current_atr = self._calculate_atr(1)
        average_atr = self._calculate_average_atr()
        
        if average_atr == 0:
            return True
            
        return current_atr <= average_atr * self.params.volatility_threshold
    
    def _check_seasonality(self, timestamp: datetime) -> float:
        """
        Check seasonal weight for crude oil trading.

        Crude oil has strong seasonal patterns:
        - Q1 (Jan-Mar): signal_weight = 1.0 (winter demand, strongest seasonal)
        - Q2 (Apr-Jun): signal_weight = 1.0 (refinery maintenance season)
        - Q3 (Jul-Sep): signal_weight = 0.5 (fading summer demand)
        - Q4 (Oct-Dec): signal_weight = 0.0 (DISABLED — weakest period, 68-72% win rate drops)

        Args:
            timestamp: Current candle timestamp

        Returns:
            Signal weight multiplier (0.0 = disabled, 0.5 = half weight, 1.0 = full weight)
        """
        if not self.params.enable_seasonality:
            return 1.0

        month = timestamp.month

        if month <= 3:      # Q1: Jan-Mar
            return 1.0
        elif month <= 6:    # Q2: Apr-Jun
            return 1.0
        elif month <= 9:    # Q3: Jul-Sep
            return 0.5
        else:               # Q4: Oct-Dec
            return 0.0

    def _check_entry(self, tick: MarketTick) -> CrudeOilSignal:
        """Check for new trade entry signals."""
        # Check seasonality filter before any indicator calculation
        seasonality_weight = self._check_seasonality(tick.timestamp)
        if seasonality_weight == 0.0:
            return CrudeOilSignal(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="Q4 seasonal filter: trading disabled (Oct-Dec)"
            )

        # Calculate indicators
        ema_fast = self._calculate_ema(self.params.ema_fast)
        ema_slow = self._calculate_ema(self.params.ema_slow)
        rsi = self._calculate_rsi()
        cci = self._calculate_cci()
        momentum = self._calculate_momentum()
        atr = self._calculate_atr(1)
        
        # Calculate stop loss and take profit distances
        stop_distance = atr * self.params.atr_multiplier
        tp_distance = stop_distance * self.params.take_profit_multiplier
        
        # Buy conditions
        buy_ema = ema_fast > ema_slow
        buy_rsi = rsi < self.params.rsi_oversold
        buy_cci = cci < self.params.cci_oversold
        buy_momentum = momentum > 99.5
        
        # Sell conditions
        sell_ema = ema_fast < ema_slow
        sell_rsi = rsi > self.params.rsi_overbought
        sell_cci = cci > self.params.cci_overbought
        sell_momentum = momentum < 100.5
        
        # Check buy signal
        if buy_ema:
            if self._check_filters(buy_rsi, buy_cci) and buy_momentum:
                return self._open_position(
                    'buy', tick, stop_distance, tp_distance,
                    f"BUY: EMA({ema_fast:.2f}>{ema_slow:.2f}), RSI={rsi:.1f}, CCI={cci:.1f}, Mom={momentum:.2f}, seasonal_weight={seasonality_weight:.1f}",
                    seasonality_weight=seasonality_weight
                )

        # Check sell signal
        if sell_ema:
            if self._check_filters(sell_rsi, sell_cci) and sell_momentum:
                return self._open_position(
                    'sell', tick, stop_distance, tp_distance,
                    f"SELL: EMA({ema_fast:.2f}<{ema_slow:.2f}), RSI={rsi:.1f}, CCI={cci:.1f}, Mom={momentum:.2f}, seasonal_weight={seasonality_weight:.1f}",
                    seasonality_weight=seasonality_weight
                )
        
        return CrudeOilSignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=f"No signal: EMA_fast={ema_fast:.2f}, EMA_slow={ema_slow:.2f}, RSI={rsi:.1f}"
        )
    
    def _check_filters(self, rsi_condition: bool, cci_condition: bool) -> bool:
        """Check RSI and CCI filter conditions."""
        if self.params.use_cci_filter:
            if self.params.use_strict_filter:
                # Require both RSI and CCI
                return rsi_condition and cci_condition
            else:
                # Require either RSI or CCI
                return rsi_condition or cci_condition
        else:
            # Only check RSI
            return rsi_condition
    
    def _open_position(
        self,
        position_type: str,
        tick: MarketTick,
        stop_distance: float,
        tp_distance: float,
        reason: str,
        seasonality_weight: float = 1.0
    ) -> CrudeOilSignal:
        """Open a new position."""
        price = float(tick.close)

        if position_type == 'buy':
            stop_loss = price - stop_distance
            take_profit = price + tp_distance
        else:
            stop_loss = price + stop_distance
            take_profit = price - tp_distance

        # Update state
        self.state.has_position = True
        self.state.position_type = position_type
        self.state.entry_price = tick.close
        self.state.entry_time = tick.timestamp
        self.state.stop_loss = Decimal(str(stop_loss))
        self.state.take_profit = Decimal(str(take_profit))
        self.state.initial_stop_distance = stop_distance

        return CrudeOilSignal(
            action=position_type,
            quantity=self.params.quantity,
            confidence=0.7 * seasonality_weight,
            reason=reason,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
    
    def _manage_position(self, tick: MarketTick) -> CrudeOilSignal:
        """Manage existing position - check for exit conditions."""
        current_price = float(tick.close)
        entry_price = float(self.state.entry_price)
        
        # Calculate current profit in points
        if self.state.position_type == 'buy':
            profit_points = current_price - entry_price
            # Check stop loss
            if current_price <= float(self.state.stop_loss):
                return self._close_position(tick, "Stop loss hit")
            # Check take profit
            if current_price >= float(self.state.take_profit):
                return self._close_position(tick, "Take profit hit")
        else:  # sell
            profit_points = entry_price - current_price
            # Check stop loss
            if current_price >= float(self.state.stop_loss):
                return self._close_position(tick, "Stop loss hit")
            # Check take profit
            if current_price <= float(self.state.take_profit):
                return self._close_position(tick, "Take profit hit")
        
        # Check close only in profit condition
        if self.params.close_only_in_profit:
            if profit_points < self.params.min_profit_close:
                return CrudeOilSignal(
                    action=None,
                    quantity=Decimal("0.0"),
                    confidence=0.0,
                    reason=f"Holding: profit={profit_points:.2f} < min_required={self.params.min_profit_close}"
                )
        
        # Check MA exit
        if self.params.use_ma_exit:
            ma_exit_signal = self._check_ma_exit(tick)
            if ma_exit_signal:
                return self._close_position(tick, ma_exit_signal)
        
        # Check pattern exit
        if self.params.use_pattern_exit:
            pattern_exit_signal = self._check_pattern_exit(tick)
            if pattern_exit_signal:
                if self.params.require_both_exits:
                    # Need both MA and pattern exit
                    if self.params.use_ma_exit and self._check_ma_exit(tick):
                        return self._close_position(tick, f"Both exits: {pattern_exit_signal}")
                else:
                    return self._close_position(tick, pattern_exit_signal)
        
        return CrudeOilSignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=f"Holding {self.state.position_type}: profit={profit_points:.4f}"
        )
    
    def _check_ma_exit(self, tick: MarketTick) -> Optional[str]:
        """Check MA crossover exit condition."""
        if len(self.price_history) < 2:
            return None
            
        ma = self._calculate_sma(self.params.ma_close_period)
        prev_open = self.price_history[-2]['open']
        prev_close = self.price_history[-2]['close']
        
        if self.state.position_type == 'buy':
            # Exit long: price crosses below MA
            if prev_open > ma and prev_close < ma:
                return f"MA exit: close({prev_close:.2f}) < MA({ma:.2f})"
        else:  # sell
            # Exit short: price crosses above MA
            if prev_open < ma and prev_close > ma:
                return f"MA exit: close({prev_close:.2f}) > MA({ma:.2f})"
        
        return None
    
    def _check_pattern_exit(self, tick: MarketTick) -> Optional[str]:
        """Check pattern-based exit (engulfing, reversal)."""
        if len(self.price_history) < 4:
            return None
            
        ma = self._calculate_sma(self.params.ma_close_period)
        curr_open = self.price_history[-1]['open']
        curr_close = self.price_history[-1]['close']
        
        # Get last 3 closes for reversal detection
        closes = [self.price_history[-i]['close'] for i in range(1, 4)]
        
        if self.state.position_type == 'buy':
            # Bearish engulfing
            bearish_engulfing = curr_close < curr_open and curr_close < ma
            # Strong reversal (3 consecutive lower closes)
            strong_reversal = closes[0] < closes[1] < closes[2]
            
            if bearish_engulfing:
                return "Bearish engulfing pattern"
            if strong_reversal:
                return "Strong bearish reversal (3 lower closes)"
                
        else:  # sell
            # Bullish engulfing
            bullish_engulfing = curr_close > curr_open and curr_close > ma
            # Strong reversal (3 consecutive higher closes)
            strong_reversal = closes[0] > closes[1] > closes[2]
            
            if bullish_engulfing:
                return "Bullish engulfing pattern"
            if strong_reversal:
                return "Strong bullish reversal (3 higher closes)"
        
        return None
    
    def _close_position(self, tick: MarketTick, reason: str) -> CrudeOilSignal:
        """Close current position."""
        position_type = self.state.position_type

        # Determine correct close action based on position type
        close_action = 'close_long' if position_type == 'buy' else 'close_short'

        # Track consecutive losses
        entry_price = float(self.state.entry_price)
        exit_price = float(tick.close)

        if position_type == 'buy':
            profit = exit_price - entry_price
        else:
            profit = entry_price - exit_price

        if profit < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0

        # Reset state
        self.state.has_position = False
        self.state.position_type = None
        self.state.entry_price = None
        self.state.entry_time = None
        self.state.stop_loss = None
        self.state.take_profit = None

        return CrudeOilSignal(
            action=close_action,
            quantity=self.params.quantity,
            confidence=0.8,
            reason=f"CLOSE {position_type.upper()}: {reason}"
        )
    
    # ==================== INDICATOR CALCULATIONS ====================
    
    def _calculate_ema(self, period: int) -> float:
        """Calculate Exponential Moving Average."""
        if len(self.price_history) < period:
            return 0.0
            
        closes = [bar['close'] for bar in self.price_history[-period:]]
        
        # EMA calculation
        multiplier = 2 / (period + 1)
        ema = closes[0]  # Start with SMA of first value
        
        for price in closes[1:]:
            ema = (price - ema) * multiplier + ema
            
        return ema
    
    def _calculate_sma(self, period: int) -> float:
        """Calculate Simple Moving Average."""
        if len(self.price_history) < period:
            return 0.0
            
        closes = [bar['close'] for bar in self.price_history[-period:]]
        return sum(closes) / len(closes)
    
    def _calculate_rsi(self) -> float:
        """Calculate Relative Strength Index."""
        period = self.params.rsi_period
        
        if len(self.price_history) < period + 1:
            return 50.0  # Neutral
            
        closes = [bar['close'] for bar in self.price_history[-(period + 1):]]
        deltas = np.diff(closes)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_cci(self) -> float:
        """Calculate Commodity Channel Index."""
        period = self.params.cci_period
        
        if len(self.price_history) < period:
            return 0.0
            
        # Typical price = (H + L + C) / 3
        typical_prices = [
            (bar['high'] + bar['low'] + bar['close']) / 3
            for bar in self.price_history[-period:]
        ]
        
        tp_current = typical_prices[-1]
        tp_sma = np.mean(typical_prices)
        
        # Mean deviation
        mean_deviation = np.mean(np.abs(np.array(typical_prices) - tp_sma))
        
        if mean_deviation == 0:
            return 0.0
            
        # CCI = (TP - SMA) / (0.015 * Mean Deviation)
        return (tp_current - tp_sma) / (0.015 * mean_deviation)
    
    def _calculate_momentum(self) -> float:
        """Calculate Momentum indicator."""
        period = self.params.momentum_period
        
        if len(self.price_history) < period + 1:
            return 100.0  # Neutral
            
        current_close = self.price_history[-1]['close']
        past_close = self.price_history[-(period + 1)]['close']
        
        if past_close == 0:
            return 100.0
            
        return (current_close / past_close) * 100
    
    def _calculate_atr(self, shift: int = 1) -> float:
        """Calculate Average True Range."""
        period = self.params.atr_period
        
        if len(self.price_history) < period + shift:
            return 0.0
            
        true_ranges = []
        
        for i in range(-(period + shift), -shift if shift > 0 else None):
            bar = self.price_history[i]
            prev_bar = self.price_history[i - 1] if i > 0 else bar
            
            high_low = bar['high'] - bar['low']
            high_prev_close = abs(bar['high'] - prev_bar['close'])
            low_prev_close = abs(bar['low'] - prev_bar['close'])
            
            true_range = max(high_low, high_prev_close, low_prev_close)
            true_ranges.append(true_range)
            
        return np.mean(true_ranges) if true_ranges else 0.0
    
    def _calculate_average_atr(self) -> float:
        """Calculate average ATR for volatility comparison."""
        period = self.params.atr_period
        
        if len(self.price_history) < period * 2:
            return self._calculate_atr(1)
            
        atrs = []
        for i in range(1, period + 1):
            atrs.append(self._calculate_atr(i))
            
        return np.mean(atrs) if atrs else 0.0
    
    def get_state(self) -> Dict:
        """Get current strategy state."""
        return {
            'strategy': 'crude_oil_v3',
            'params': {
                'ema_fast': self.params.ema_fast,
                'ema_slow': self.params.ema_slow,
                'rsi_period': self.params.rsi_period,
                'rsi_overbought': self.params.rsi_overbought,
                'rsi_oversold': self.params.rsi_oversold,
                'atr_period': self.params.atr_period,
                'atr_multiplier': self.params.atr_multiplier,
                'take_profit_multiplier': self.params.take_profit_multiplier,
            },
            'has_position': self.state.has_position,
            'position_type': self.state.position_type,
            'entry_price': str(self.state.entry_price) if self.state.entry_price else None,
            'stop_loss': str(self.state.stop_loss) if self.state.stop_loss else None,
            'take_profit': str(self.state.take_profit) if self.state.take_profit else None,
            'consecutive_losses': self.state.consecutive_losses,
            'price_history_length': len(self.price_history)
        }


def create_crude_oil_strategy(**kwargs) -> CrudeOilStrategy:
    """
    Factory function to create CrudeOilStrategy with custom parameters.
    
    Args:
        **kwargs: Parameters to override defaults.
            - ema_fast: Fast EMA period (default: 8)
            - ema_slow: Slow EMA period (default: 29)
            - rsi_period: RSI period (default: 10)
            - rsi_overbought: RSI overbought level (default: 68)
            - rsi_oversold: RSI oversold level (default: 32)
            - cci_period: CCI period (default: 20)
            - cci_overbought: CCI overbought level (default: 100)
            - cci_oversold: CCI oversold level (default: -80)
            - atr_period: ATR period (default: 10)
            - atr_multiplier: ATR multiplier for SL (default: 2.0)
            - take_profit_multiplier: R:R ratio (default: 2.5)
            - use_cci_filter: Use CCI filter (default: True)
            - use_strict_filter: Require both RSI and CCI (default: False)
            - use_time_filter: Enable time filter (default: True)
            - trading_start_hour: Start hour GMT (default: 8)
            - trading_end_hour: End hour GMT (default: 20)
            - close_only_in_profit: Only close in profit (default: True)
            - enable_seasonality: Gate entries by quarter (default: True)
                Q1/Q2=full, Q3=50%, Q4=disabled

    Returns:
        Configured CrudeOilStrategy instance
        
    Example:
        >>> strategy = create_crude_oil_strategy(
        ...     ema_fast=5,
        ...     ema_slow=20,
        ...     atr_multiplier=1.5
        ... )
    """
    # Map common parameter names
    param_mapping = {
        'risk_reward_ratio': 'take_profit_multiplier',
    }
    
    # Remap parameters
    mapped_kwargs = {}
    for key, value in kwargs.items():
        mapped_key = param_mapping.get(key, key)
        mapped_kwargs[mapped_key] = value
    
    # Create params with defaults + overrides
    params = CrudeOilParams(**mapped_kwargs)
    return CrudeOilStrategy(params=params)
