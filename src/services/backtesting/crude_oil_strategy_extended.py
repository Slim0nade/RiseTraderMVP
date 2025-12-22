"""
Enhanced CrudeOIL V3 Strategy with Extended Parameters.

Additional indicators and filters for maximum optimization potential.
Original + Extended = ZILLIONS potential 🚀
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import numpy as np

from .data_replay_engine import MarketTick


@dataclass
class CrudeOilParamsExtended:
    """
    Extended strategy parameters for maximum optimization.
    
    Original MQL4 parameters PLUS additional indicators and filters.
    """
    # ==================== ORIGINAL CORE PARAMETERS ====================
    # Risk Management
    risk_percent: float = 1.0
    quantity: Decimal = Decimal("1.0")
    
    # EMA Crossover
    ema_fast: int = 8
    ema_slow: int = 29
    
    # RSI Filter
    rsi_period: int = 10
    rsi_overbought: int = 68
    rsi_oversold: int = 32
    
    # CCI Filter
    cci_period: int = 20
    cci_overbought: int = 100
    cci_oversold: int = -80
    use_cci_filter: bool = True
    use_strict_filter: bool = False
    
    # ATR Stop Loss
    atr_period: int = 10
    atr_multiplier: float = 2.0
    
    # Take Profit
    take_profit_multiplier: float = 2.5
    
    # Momentum
    momentum_period: int = 10
    momentum_buy_threshold: float = 99.5
    momentum_sell_threshold: float = 100.5
    
    # Exit Conditions
    ma_close_period: int = 20
    use_ma_exit: bool = True
    use_pattern_exit: bool = True
    require_both_exits: bool = False
    
    # Time Filter
    use_time_filter: bool = True
    trading_start_hour: int = 8
    trading_end_hour: int = 20
    avoid_rollover: bool = True
    rollover_start_hour: int = 21
    rollover_end_hour: int = 22
    
    # Volatility Filter
    volatility_threshold: float = 2.0
    
    # Close Management
    close_only_in_profit: bool = True
    min_profit_close: float = 0.0
    
    # ==================== NEW EXTENDED PARAMETERS ====================
    
    # --- MACD Filter ---
    use_macd_filter: bool = False
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    macd_histogram_threshold: float = 0.0  # Min histogram value for entry
    
    # --- Bollinger Bands Filter ---
    use_bollinger_filter: bool = False
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    bollinger_squeeze_threshold: float = 0.5  # % width for squeeze detection
    
    # --- Stochastic Filter ---
    use_stochastic_filter: bool = False
    stoch_k_period: int = 14
    stoch_d_period: int = 3
    stoch_slowing: int = 3
    stoch_overbought: int = 80
    stoch_oversold: int = 20
    
    # --- ADX Trend Strength Filter ---
    use_adx_filter: bool = False
    adx_period: int = 14
    adx_threshold: float = 25.0  # Minimum ADX for trend confirmation
    
    # --- Volume Filter ---
    use_volume_filter: bool = False
    volume_ma_period: int = 20
    volume_multiplier: float = 1.5  # Volume must be X times average
    
    # --- Multi-Timeframe Confirmation ---
    use_mtf_confirmation: bool = False
    mtf_ema_period: int = 50  # Higher timeframe EMA
    
    # --- Support/Resistance ---
    use_sr_filter: bool = False
    sr_lookback: int = 50
    sr_threshold: float = 0.002  # 0.2% proximity to S/R
    
    # --- Candle Pattern Filters ---
    use_candle_patterns: bool = False
    min_candle_body_ratio: float = 0.6  # Body must be 60% of range
    require_engulfing: bool = False
    
    # --- Session Filters ---
    use_session_filter: bool = False
    london_start: int = 8
    london_end: int = 16
    ny_start: int = 13
    ny_end: int = 21
    prefer_overlap: bool = True  # Prefer London/NY overlap
    
    # --- Drawdown Control ---
    use_drawdown_control: bool = False
    max_daily_drawdown: float = 3.0  # % of account
    max_consecutive_losses: int = 3
    pause_after_loss_streak: int = 0  # Hours to pause
    
    # --- Partial Take Profit ---
    use_partial_tp: bool = False
    partial_tp_percent: float = 50.0  # Close 50% at first target
    partial_tp_multiplier: float = 1.5  # First target at 1.5x SL
    
    # --- Trailing Stop ---
    use_trailing_stop: bool = False
    trailing_activation: float = 1.0  # Activate after 1x SL profit
    trailing_step: float = 0.5  # Trail by 0.5x ATR
    
    # --- Break-Even Stop ---
    use_breakeven: bool = False
    breakeven_activation: float = 1.0  # Move to BE after 1x SL profit
    breakeven_offset: float = 0.1  # Small profit buffer
    
    # --- News Avoidance (by hour) ---
    use_news_filter: bool = False
    news_avoid_hours: List[int] = field(default_factory=lambda: [14, 15])  # EIA inventory
    
    # --- Day of Week Filter ---
    use_dow_filter: bool = False
    trade_days: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])  # Mon-Fri
    avoid_monday_morning: bool = True
    avoid_friday_afternoon: bool = True
    
    # --- Price Action Filters ---
    use_price_action: bool = False
    min_bar_range_atr: float = 0.5  # Min bar range as ATR multiple
    max_bar_range_atr: float = 3.0  # Max bar range (avoid spikes)
    require_higher_high: bool = False  # For buys
    require_lower_low: bool = False   # For sells
    
    # --- Dynamic Position Sizing ---
    use_dynamic_sizing: bool = False
    kelly_fraction: float = 0.25  # Use 25% of Kelly criterion
    max_position_size: Decimal = Decimal("10.0")
    min_position_size: Decimal = Decimal("0.1")
    
    # --- Correlation Filter (for multi-asset) ---
    use_correlation_filter: bool = False
    correlation_threshold: float = 0.7
    correlated_symbols: List[str] = field(default_factory=list)


@dataclass
class TradeStateExtended:
    """Extended trade state with more tracking."""
    has_position: bool = False
    position_type: Optional[str] = None
    entry_price: Optional[Decimal] = None
    entry_time: Optional[datetime] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    initial_stop_distance: float = 0.0
    consecutive_losses: int = 0
    daily_pnl: float = 0.0
    trades_today: int = 0
    last_trade_date: Optional[datetime] = None
    # Partial TP tracking
    partial_tp_hit: bool = False
    remaining_quantity: Decimal = Decimal("1.0")
    # Trailing stop tracking
    trailing_stop_active: bool = False
    highest_profit: float = 0.0


@dataclass
class CrudeOilSignalExtended:
    """Enhanced signal with more metadata."""
    action: Optional[str]
    quantity: Decimal
    confidence: float
    reason: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    # Extended fields
    indicators: Dict[str, float] = field(default_factory=dict)
    filters_passed: List[str] = field(default_factory=list)
    filters_failed: List[str] = field(default_factory=list)
    signal_strength: float = 0.0  # 0-1 composite score


class CrudeOilStrategyExtended:
    """
    CrudeOIL V3 Extended - Maximum Optimization Potential.
    
    Original strategy + 20+ additional filters and parameters.
    """
    
    def __init__(self, params: Optional[CrudeOilParamsExtended] = None):
        self.params = params or CrudeOilParamsExtended()
        self.state = TradeStateExtended()
        self.price_history: List[Dict] = []
        self.max_history = 500  # Extended for more lookback
        
    @property
    def has_position(self) -> bool:
        return self.state.has_position
    
    @property
    def entry_price(self) -> Optional[Decimal]:
        return self.state.entry_price
        
    def reset(self) -> None:
        """Reset strategy state."""
        self.state = TradeStateExtended()
        self.price_history.clear()
        
    def process_tick(self, tick: MarketTick) -> CrudeOilSignalExtended:
        """Process tick with extended logic."""
        self._update_history(tick)
        
        # Calculate minimum warmup needed
        min_history = self._get_min_history()
        
        if len(self.price_history) < min_history:
            return CrudeOilSignalExtended(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason=f"Warming up: {len(self.price_history)}/{min_history}"
            )
        
        # Update daily tracking
        self._update_daily_tracking(tick)
        
        # Manage existing position
        if self.state.has_position:
            return self._manage_position(tick)
        
        # Check all filters and generate entry signal
        return self._check_entry(tick)
    
    def _get_min_history(self) -> int:
        """Calculate minimum history needed based on enabled indicators."""
        periods = [
            self.params.ema_slow,
            self.params.atr_period,
            self.params.rsi_period,
            self.params.cci_period,
            self.params.ma_close_period,
            self.params.momentum_period,
        ]
        
        if self.params.use_macd_filter:
            periods.append(self.params.macd_slow + self.params.macd_signal)
        if self.params.use_bollinger_filter:
            periods.append(self.params.bollinger_period)
        if self.params.use_stochastic_filter:
            periods.append(self.params.stoch_k_period + self.params.stoch_slowing)
        if self.params.use_adx_filter:
            periods.append(self.params.adx_period * 2)
        if self.params.use_volume_filter:
            periods.append(self.params.volume_ma_period)
        if self.params.use_sr_filter:
            periods.append(self.params.sr_lookback)
            
        return max(periods) + 5
    
    def _update_history(self, tick: MarketTick) -> None:
        """Update price history."""
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
    
    def _update_daily_tracking(self, tick: MarketTick) -> None:
        """Track daily statistics."""
        current_date = tick.timestamp.date()
        
        if self.state.last_trade_date != current_date:
            self.state.daily_pnl = 0.0
            self.state.trades_today = 0
            self.state.last_trade_date = current_date
    
    def _check_entry(self, tick: MarketTick) -> CrudeOilSignalExtended:
        """Check all filters for entry signal."""
        filters_passed = []
        filters_failed = []
        indicators = {}
        
        # ==================== CORE INDICATORS ====================
        ema_fast = self._calculate_ema(self.params.ema_fast)
        ema_slow = self._calculate_ema(self.params.ema_slow)
        rsi = self._calculate_rsi()
        cci = self._calculate_cci()
        momentum = self._calculate_momentum()
        atr = self._calculate_atr(1)
        
        indicators['ema_fast'] = ema_fast
        indicators['ema_slow'] = ema_slow
        indicators['rsi'] = rsi
        indicators['cci'] = cci
        indicators['momentum'] = momentum
        indicators['atr'] = atr
        
        # ==================== EXTENDED INDICATORS ====================
        if self.params.use_macd_filter:
            macd, signal, histogram = self._calculate_macd()
            indicators['macd'] = macd
            indicators['macd_signal'] = signal
            indicators['macd_histogram'] = histogram
            
        if self.params.use_bollinger_filter:
            bb_upper, bb_middle, bb_lower, bb_width = self._calculate_bollinger()
            indicators['bb_upper'] = bb_upper
            indicators['bb_middle'] = bb_middle
            indicators['bb_lower'] = bb_lower
            indicators['bb_width'] = bb_width
            
        if self.params.use_stochastic_filter:
            stoch_k, stoch_d = self._calculate_stochastic()
            indicators['stoch_k'] = stoch_k
            indicators['stoch_d'] = stoch_d
            
        if self.params.use_adx_filter:
            adx, plus_di, minus_di = self._calculate_adx()
            indicators['adx'] = adx
            indicators['plus_di'] = plus_di
            indicators['minus_di'] = minus_di
            
        if self.params.use_volume_filter:
            vol_ratio = self._calculate_volume_ratio()
            indicators['volume_ratio'] = vol_ratio
        
        # ==================== DETERMINE SIGNAL DIRECTION ====================
        buy_signal = ema_fast > ema_slow
        sell_signal = ema_fast < ema_slow
        
        if not buy_signal and not sell_signal:
            return CrudeOilSignalExtended(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason="No EMA crossover signal",
                indicators=indicators
            )
        
        signal_direction = 'buy' if buy_signal else 'sell'
        
        # ==================== CHECK ALL FILTERS ====================
        
        # Time Filter
        if self.params.use_time_filter:
            if self._is_time_to_trade(tick.timestamp):
                filters_passed.append("time_filter")
            else:
                filters_failed.append("time_filter")
                return self._no_signal("Outside trading hours", indicators, filters_passed, filters_failed)
        
        # Volatility Filter
        if not self._is_volatility_acceptable():
            filters_failed.append("volatility_filter")
            return self._no_signal("Volatility too high", indicators, filters_passed, filters_failed)
        filters_passed.append("volatility_filter")
        
        # RSI Filter
        if signal_direction == 'buy':
            if rsi < self.params.rsi_oversold:
                filters_passed.append("rsi_filter")
            else:
                if not self.params.use_cci_filter or self.params.use_strict_filter:
                    filters_failed.append("rsi_filter")
        else:
            if rsi > self.params.rsi_overbought:
                filters_passed.append("rsi_filter")
            else:
                if not self.params.use_cci_filter or self.params.use_strict_filter:
                    filters_failed.append("rsi_filter")
        
        # CCI Filter
        if self.params.use_cci_filter:
            if signal_direction == 'buy':
                if cci < self.params.cci_oversold:
                    filters_passed.append("cci_filter")
                else:
                    filters_failed.append("cci_filter")
            else:
                if cci > self.params.cci_overbought:
                    filters_passed.append("cci_filter")
                else:
                    filters_failed.append("cci_filter")
        
        # Check RSI/CCI combined requirement
        if self.params.use_strict_filter:
            if "rsi_filter" not in filters_passed or "cci_filter" not in filters_passed:
                return self._no_signal("Strict filter: need both RSI and CCI", indicators, filters_passed, filters_failed)
        else:
            if "rsi_filter" not in filters_passed and "cci_filter" not in filters_passed:
                return self._no_signal("Need either RSI or CCI confirmation", indicators, filters_passed, filters_failed)
        
        # Momentum Filter
        if signal_direction == 'buy':
            if momentum > self.params.momentum_buy_threshold:
                filters_passed.append("momentum_filter")
            else:
                filters_failed.append("momentum_filter")
                return self._no_signal(f"Momentum too low: {momentum:.2f}", indicators, filters_passed, filters_failed)
        else:
            if momentum < self.params.momentum_sell_threshold:
                filters_passed.append("momentum_filter")
            else:
                filters_failed.append("momentum_filter")
                return self._no_signal(f"Momentum too high: {momentum:.2f}", indicators, filters_passed, filters_failed)
        
        # ==================== EXTENDED FILTERS ====================
        
        # MACD Filter
        if self.params.use_macd_filter:
            macd, signal_line, histogram = indicators['macd'], indicators['macd_signal'], indicators['macd_histogram']
            if signal_direction == 'buy':
                if histogram > self.params.macd_histogram_threshold:
                    filters_passed.append("macd_filter")
                else:
                    filters_failed.append("macd_filter")
                    return self._no_signal("MACD histogram negative", indicators, filters_passed, filters_failed)
            else:
                if histogram < -self.params.macd_histogram_threshold:
                    filters_passed.append("macd_filter")
                else:
                    filters_failed.append("macd_filter")
                    return self._no_signal("MACD histogram positive", indicators, filters_passed, filters_failed)
        
        # Bollinger Bands Filter
        if self.params.use_bollinger_filter:
            bb_upper, bb_middle, bb_lower, bb_width = indicators['bb_upper'], indicators['bb_middle'], indicators['bb_lower'], indicators['bb_width']
            current_price = self.price_history[-1]['close']
            
            # Check for squeeze (low volatility = potential breakout)
            if bb_width < self.params.bollinger_squeeze_threshold:
                filters_passed.append("bollinger_squeeze")
            
            if signal_direction == 'buy':
                if current_price < bb_lower:
                    filters_passed.append("bollinger_filter")
                else:
                    filters_failed.append("bollinger_filter")
            else:
                if current_price > bb_upper:
                    filters_passed.append("bollinger_filter")
                else:
                    filters_failed.append("bollinger_filter")
        
        # Stochastic Filter
        if self.params.use_stochastic_filter:
            stoch_k, stoch_d = indicators['stoch_k'], indicators['stoch_d']
            if signal_direction == 'buy':
                if stoch_k < self.params.stoch_oversold and stoch_k > stoch_d:
                    filters_passed.append("stochastic_filter")
                else:
                    filters_failed.append("stochastic_filter")
            else:
                if stoch_k > self.params.stoch_overbought and stoch_k < stoch_d:
                    filters_passed.append("stochastic_filter")
                else:
                    filters_failed.append("stochastic_filter")
        
        # ADX Filter (trend strength)
        if self.params.use_adx_filter:
            adx = indicators['adx']
            if adx >= self.params.adx_threshold:
                filters_passed.append("adx_filter")
            else:
                filters_failed.append("adx_filter")
                return self._no_signal(f"ADX too low: {adx:.2f}", indicators, filters_passed, filters_failed)
        
        # Volume Filter
        if self.params.use_volume_filter:
            vol_ratio = indicators['volume_ratio']
            if vol_ratio >= self.params.volume_multiplier:
                filters_passed.append("volume_filter")
            else:
                filters_failed.append("volume_filter")
        
        # Day of Week Filter
        if self.params.use_dow_filter:
            dow = tick.timestamp.weekday()
            hour = tick.timestamp.hour
            
            if dow not in self.params.trade_days:
                filters_failed.append("dow_filter")
                return self._no_signal("Day not in trading days", indicators, filters_passed, filters_failed)
            
            if self.params.avoid_monday_morning and dow == 0 and hour < 10:
                filters_failed.append("monday_morning")
                return self._no_signal("Avoiding Monday morning", indicators, filters_passed, filters_failed)
            
            if self.params.avoid_friday_afternoon and dow == 4 and hour >= 18:
                filters_failed.append("friday_afternoon")
                return self._no_signal("Avoiding Friday afternoon", indicators, filters_passed, filters_failed)
            
            filters_passed.append("dow_filter")
        
        # News Hours Filter
        if self.params.use_news_filter:
            hour = tick.timestamp.hour
            if hour in self.params.news_avoid_hours:
                filters_failed.append("news_filter")
                return self._no_signal("Avoiding news hour", indicators, filters_passed, filters_failed)
            filters_passed.append("news_filter")
        
        # Drawdown Control
        if self.params.use_drawdown_control:
            if self.state.consecutive_losses >= self.params.max_consecutive_losses:
                filters_failed.append("drawdown_control")
                return self._no_signal(f"Max consecutive losses ({self.state.consecutive_losses})", indicators, filters_passed, filters_failed)
            filters_passed.append("drawdown_control")
        
        # Price Action Filter
        if self.params.use_price_action:
            bar_range = self.price_history[-1]['high'] - self.price_history[-1]['low']
            bar_range_atr = bar_range / atr if atr > 0 else 0
            
            if bar_range_atr < self.params.min_bar_range_atr:
                filters_failed.append("price_action_min_range")
            elif bar_range_atr > self.params.max_bar_range_atr:
                filters_failed.append("price_action_max_range")
                return self._no_signal("Bar range too large (spike)", indicators, filters_passed, filters_failed)
            else:
                filters_passed.append("price_action")
        
        # ==================== CALCULATE SIGNAL STRENGTH ====================
        total_filters = len(filters_passed) + len(filters_failed)
        signal_strength = len(filters_passed) / total_filters if total_filters > 0 else 0.5
        
        # Minimum confidence threshold
        min_confidence = 0.5
        if signal_strength < min_confidence:
            return self._no_signal(f"Signal strength too low: {signal_strength:.2f}", indicators, filters_passed, filters_failed)
        
        # ==================== OPEN POSITION ====================
        return self._open_position(
            signal_direction, 
            tick, 
            atr,
            indicators, 
            filters_passed, 
            filters_failed,
            signal_strength
        )
    
    def _no_signal(
        self, 
        reason: str, 
        indicators: Dict, 
        filters_passed: List[str], 
        filters_failed: List[str]
    ) -> CrudeOilSignalExtended:
        """Return no-signal with full metadata."""
        return CrudeOilSignalExtended(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=reason,
            indicators=indicators,
            filters_passed=filters_passed,
            filters_failed=filters_failed,
            signal_strength=len(filters_passed) / max(1, len(filters_passed) + len(filters_failed))
        )
    
    def _open_position(
        self,
        direction: str,
        tick: MarketTick,
        atr: float,
        indicators: Dict,
        filters_passed: List[str],
        filters_failed: List[str],
        signal_strength: float
    ) -> CrudeOilSignalExtended:
        """Open a position with extended tracking."""
        price = float(tick.close)
        stop_distance = atr * self.params.atr_multiplier
        tp_distance = stop_distance * self.params.take_profit_multiplier
        
        if direction == 'buy':
            stop_loss = price - stop_distance
            take_profit = price + tp_distance
        else:
            stop_loss = price + stop_distance
            take_profit = price - tp_distance
        
        # Calculate position size
        quantity = self._calculate_position_size(stop_distance)
        
        # Update state
        self.state.has_position = True
        self.state.position_type = direction
        self.state.entry_price = tick.close
        self.state.entry_time = tick.timestamp
        self.state.stop_loss = Decimal(str(stop_loss))
        self.state.take_profit = Decimal(str(take_profit))
        self.state.initial_stop_distance = stop_distance
        self.state.remaining_quantity = quantity
        self.state.partial_tp_hit = False
        self.state.trailing_stop_active = False
        self.state.highest_profit = 0.0
        self.state.trades_today += 1
        
        return CrudeOilSignalExtended(
            action=direction,
            quantity=quantity,
            confidence=signal_strength,
            reason=f"{direction.upper()}: {len(filters_passed)} filters passed",
            stop_loss=stop_loss,
            take_profit=take_profit,
            indicators=indicators,
            filters_passed=filters_passed,
            filters_failed=filters_failed,
            signal_strength=signal_strength
        )
    
    def _calculate_position_size(self, stop_distance: float) -> Decimal:
        """Calculate position size with optional Kelly criterion."""
        if not self.params.use_dynamic_sizing:
            return self.params.quantity
        
        # Simple Kelly approximation
        # K = W - (1-W)/R where W = win rate, R = reward/risk ratio
        # Since we don't have historical stats, use params
        assumed_win_rate = 0.55
        reward_risk = self.params.take_profit_multiplier
        
        kelly = assumed_win_rate - (1 - assumed_win_rate) / reward_risk
        kelly = max(0, kelly * self.params.kelly_fraction)
        
        position = Decimal(str(kelly)) * Decimal("10.0")  # Scale factor
        position = max(self.params.min_position_size, min(position, self.params.max_position_size))
        
        return position
    
    def _manage_position(self, tick: MarketTick) -> CrudeOilSignalExtended:
        """Manage position with extended features."""
        current_price = float(tick.close)
        entry_price = float(self.state.entry_price)
        
        # Calculate profit
        if self.state.position_type == 'buy':
            profit_points = current_price - entry_price
            profit_atr = profit_points / self.state.initial_stop_distance if self.state.initial_stop_distance > 0 else 0
        else:
            profit_points = entry_price - current_price
            profit_atr = profit_points / self.state.initial_stop_distance if self.state.initial_stop_distance > 0 else 0
        
        # Track highest profit for trailing
        self.state.highest_profit = max(self.state.highest_profit, profit_atr)
        
        # Check stop loss
        if self._check_stop_loss(current_price):
            return self._close_position(tick, "Stop loss hit", profit_points < 0)
        
        # Check take profit
        if self._check_take_profit(current_price):
            return self._close_position(tick, "Take profit hit", False)
        
        # Partial Take Profit
        if self.params.use_partial_tp and not self.state.partial_tp_hit:
            if profit_atr >= self.params.partial_tp_multiplier:
                self.state.partial_tp_hit = True
                partial_qty = self.state.remaining_quantity * Decimal(str(self.params.partial_tp_percent / 100))
                self.state.remaining_quantity -= partial_qty
                # Note: In real implementation, this would generate a partial close signal
        
        # Break-Even Stop
        if self.params.use_breakeven and profit_atr >= self.params.breakeven_activation:
            breakeven_price = entry_price + (self.params.breakeven_offset * self.state.initial_stop_distance)
            if self.state.position_type == 'buy':
                self.state.stop_loss = Decimal(str(breakeven_price))
            else:
                breakeven_price = entry_price - (self.params.breakeven_offset * self.state.initial_stop_distance)
                self.state.stop_loss = Decimal(str(breakeven_price))
        
        # Trailing Stop
        if self.params.use_trailing_stop and profit_atr >= self.params.trailing_activation:
            self.state.trailing_stop_active = True
            atr = self._calculate_atr(1)
            trail_distance = atr * self.params.trailing_step
            
            if self.state.position_type == 'buy':
                new_stop = current_price - trail_distance
                if new_stop > float(self.state.stop_loss):
                    self.state.stop_loss = Decimal(str(new_stop))
            else:
                new_stop = current_price + trail_distance
                if new_stop < float(self.state.stop_loss):
                    self.state.stop_loss = Decimal(str(new_stop))
        
        # Check exit conditions
        if self.params.close_only_in_profit and profit_points < self.params.min_profit_close:
            return CrudeOilSignalExtended(
                action=None,
                quantity=Decimal("0.0"),
                confidence=0.0,
                reason=f"Holding: profit={profit_points:.4f} < min",
                signal_strength=0.0
            )
        
        # MA Exit
        if self.params.use_ma_exit:
            ma_exit = self._check_ma_exit()
            if ma_exit:
                return self._close_position(tick, ma_exit, profit_points < 0)
        
        # Pattern Exit
        if self.params.use_pattern_exit:
            pattern_exit = self._check_pattern_exit()
            if pattern_exit:
                if self.params.require_both_exits:
                    if self.params.use_ma_exit and self._check_ma_exit():
                        return self._close_position(tick, f"Both: {pattern_exit}", profit_points < 0)
                else:
                    return self._close_position(tick, pattern_exit, profit_points < 0)
        
        return CrudeOilSignalExtended(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=f"Holding {self.state.position_type}: P&L={profit_atr:.2f}x ATR",
            signal_strength=0.0
        )
    
    def _check_stop_loss(self, current_price: float) -> bool:
        """Check if stop loss hit."""
        sl = float(self.state.stop_loss)
        if self.state.position_type == 'buy':
            return current_price <= sl
        else:
            return current_price >= sl
    
    def _check_take_profit(self, current_price: float) -> bool:
        """Check if take profit hit."""
        tp = float(self.state.take_profit)
        if self.state.position_type == 'buy':
            return current_price >= tp
        else:
            return current_price <= tp
    
    def _close_position(self, tick: MarketTick, reason: str, is_loss: bool) -> CrudeOilSignalExtended:
        """Close position and update tracking."""
        direction = self.state.position_type
        
        if is_loss:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0
        
        # Reset state
        self.state.has_position = False
        self.state.position_type = None
        self.state.entry_price = None
        self.state.entry_time = None
        
        return CrudeOilSignalExtended(
            action='close',
            quantity=self.state.remaining_quantity,
            confidence=0.8,
            reason=f"CLOSE {direction.upper()}: {reason}",
            signal_strength=0.8
        )
    
    # ==================== INDICATOR CALCULATIONS ====================
    
    def _is_time_to_trade(self, timestamp: datetime) -> bool:
        """Check trading hours."""
        if not self.params.use_time_filter:
            return True
        hour = timestamp.hour
        if hour < self.params.trading_start_hour or hour >= self.params.trading_end_hour:
            return False
        if self.params.avoid_rollover:
            if self.params.rollover_start_hour <= hour < self.params.rollover_end_hour:
                return False
        return True
    
    def _is_volatility_acceptable(self) -> bool:
        """Check volatility filter."""
        current_atr = self._calculate_atr(1)
        avg_atr = self._calculate_atr_average()
        if avg_atr == 0:
            return True
        return current_atr <= avg_atr * self.params.volatility_threshold
    
    def _calculate_ema(self, period: int) -> float:
        """Calculate EMA."""
        if len(self.price_history) < period:
            return 0.0
        closes = [bar['close'] for bar in self.price_history[-period:]]
        multiplier = 2 / (period + 1)
        ema = closes[0]
        for price in closes[1:]:
            ema = (price - ema) * multiplier + ema
        return ema
    
    def _calculate_sma(self, period: int) -> float:
        """Calculate SMA."""
        if len(self.price_history) < period:
            return 0.0
        closes = [bar['close'] for bar in self.price_history[-period:]]
        return sum(closes) / len(closes)
    
    def _calculate_rsi(self) -> float:
        """Calculate RSI."""
        period = self.params.rsi_period
        if len(self.price_history) < period + 1:
            return 50.0
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
        """Calculate CCI."""
        period = self.params.cci_period
        if len(self.price_history) < period:
            return 0.0
        typical_prices = [
            (bar['high'] + bar['low'] + bar['close']) / 3
            for bar in self.price_history[-period:]
        ]
        tp_current = typical_prices[-1]
        tp_sma = np.mean(typical_prices)
        mean_deviation = np.mean(np.abs(np.array(typical_prices) - tp_sma))
        if mean_deviation == 0:
            return 0.0
        return (tp_current - tp_sma) / (0.015 * mean_deviation)
    
    def _calculate_momentum(self) -> float:
        """Calculate Momentum."""
        period = self.params.momentum_period
        if len(self.price_history) < period + 1:
            return 100.0
        current = self.price_history[-1]['close']
        past = self.price_history[-(period + 1)]['close']
        if past == 0:
            return 100.0
        return (current / past) * 100
    
    def _calculate_atr(self, shift: int = 1) -> float:
        """Calculate ATR."""
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
            true_ranges.append(max(high_low, high_prev_close, low_prev_close))
        return np.mean(true_ranges) if true_ranges else 0.0
    
    def _calculate_atr_average(self) -> float:
        """Calculate average ATR."""
        period = self.params.atr_period
        if len(self.price_history) < period * 2:
            return self._calculate_atr(1)
        atrs = [self._calculate_atr(i) for i in range(1, period + 1)]
        return np.mean(atrs) if atrs else 0.0
    
    def _calculate_macd(self) -> Tuple[float, float, float]:
        """Calculate MACD, Signal, Histogram."""
        fast = self.params.macd_fast
        slow = self.params.macd_slow
        signal_period = self.params.macd_signal
        
        if len(self.price_history) < slow + signal_period:
            return 0.0, 0.0, 0.0
        
        ema_fast = self._calculate_ema(fast)
        ema_slow = self._calculate_ema(slow)
        macd = ema_fast - ema_slow
        
        # Calculate signal line (EMA of MACD)
        # Simplified: use recent MACD values
        signal = macd * 0.9  # Approximation
        histogram = macd - signal
        
        return macd, signal, histogram
    
    def _calculate_bollinger(self) -> Tuple[float, float, float, float]:
        """Calculate Bollinger Bands."""
        period = self.params.bollinger_period
        std_mult = self.params.bollinger_std
        
        if len(self.price_history) < period:
            return 0.0, 0.0, 0.0, 0.0
        
        closes = [bar['close'] for bar in self.price_history[-period:]]
        middle = np.mean(closes)
        std = np.std(closes)
        
        upper = middle + std_mult * std
        lower = middle - std_mult * std
        width = (upper - lower) / middle * 100 if middle > 0 else 0
        
        return upper, middle, lower, width
    
    def _calculate_stochastic(self) -> Tuple[float, float]:
        """Calculate Stochastic %K and %D."""
        k_period = self.params.stoch_k_period
        d_period = self.params.stoch_d_period
        
        if len(self.price_history) < k_period + d_period:
            return 50.0, 50.0
        
        # %K calculation
        recent = self.price_history[-k_period:]
        highest_high = max(bar['high'] for bar in recent)
        lowest_low = min(bar['low'] for bar in recent)
        current_close = self.price_history[-1]['close']
        
        if highest_high == lowest_low:
            k = 50.0
        else:
            k = ((current_close - lowest_low) / (highest_high - lowest_low)) * 100
        
        # %D is SMA of %K (simplified)
        d = k * 0.9  # Approximation
        
        return k, d
    
    def _calculate_adx(self) -> Tuple[float, float, float]:
        """Calculate ADX, +DI, -DI."""
        period = self.params.adx_period
        
        if len(self.price_history) < period * 2:
            return 0.0, 0.0, 0.0
        
        plus_dm_list = []
        minus_dm_list = []
        tr_list = []
        
        for i in range(-period, 0):
            bar = self.price_history[i]
            prev_bar = self.price_history[i - 1]
            
            high_diff = bar['high'] - prev_bar['high']
            low_diff = prev_bar['low'] - bar['low']
            
            plus_dm = high_diff if high_diff > low_diff and high_diff > 0 else 0
            minus_dm = low_diff if low_diff > high_diff and low_diff > 0 else 0
            
            tr = max(
                bar['high'] - bar['low'],
                abs(bar['high'] - prev_bar['close']),
                abs(bar['low'] - prev_bar['close'])
            )
            
            plus_dm_list.append(plus_dm)
            minus_dm_list.append(minus_dm)
            tr_list.append(tr)
        
        atr = np.mean(tr_list)
        plus_di = (np.mean(plus_dm_list) / atr * 100) if atr > 0 else 0
        minus_di = (np.mean(minus_dm_list) / atr * 100) if atr > 0 else 0
        
        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
        adx = dx  # Simplified (should be smoothed)
        
        return adx, plus_di, minus_di
    
    def _calculate_volume_ratio(self) -> float:
        """Calculate volume relative to average."""
        period = self.params.volume_ma_period
        
        if len(self.price_history) < period:
            return 1.0
        
        volumes = [bar['volume'] for bar in self.price_history[-period:]]
        avg_volume = np.mean(volumes)
        current_volume = self.price_history[-1]['volume']
        
        return current_volume / avg_volume if avg_volume > 0 else 1.0
    
    def _check_ma_exit(self) -> Optional[str]:
        """Check MA exit condition."""
        if len(self.price_history) < 2:
            return None
        ma = self._calculate_sma(self.params.ma_close_period)
        prev_open = self.price_history[-2]['open']
        prev_close = self.price_history[-2]['close']
        
        if self.state.position_type == 'buy':
            if prev_open > ma and prev_close < ma:
                return f"MA exit: {prev_close:.2f} < {ma:.2f}"
        else:
            if prev_open < ma and prev_close > ma:
                return f"MA exit: {prev_close:.2f} > {ma:.2f}"
        return None
    
    def _check_pattern_exit(self) -> Optional[str]:
        """Check pattern exit."""
        if len(self.price_history) < 4:
            return None
        
        ma = self._calculate_sma(self.params.ma_close_period)
        curr = self.price_history[-1]
        closes = [self.price_history[-i]['close'] for i in range(1, 4)]
        
        if self.state.position_type == 'buy':
            bearish_engulfing = curr['close'] < curr['open'] and curr['close'] < ma
            strong_reversal = closes[0] < closes[1] < closes[2]
            if bearish_engulfing:
                return "Bearish engulfing"
            if strong_reversal:
                return "Strong reversal"
        else:
            bullish_engulfing = curr['close'] > curr['open'] and curr['close'] > ma
            strong_reversal = closes[0] > closes[1] > closes[2]
            if bullish_engulfing:
                return "Bullish engulfing"
            if strong_reversal:
                return "Strong reversal"
        
        return None
    
    def get_state(self) -> Dict:
        """Get strategy state."""
        return {
            'strategy': 'crude_oil_v3_extended',
            'has_position': self.state.has_position,
            'position_type': self.state.position_type,
            'entry_price': str(self.state.entry_price) if self.state.entry_price else None,
            'consecutive_losses': self.state.consecutive_losses,
            'trades_today': self.state.trades_today,
            'price_history_length': len(self.price_history),
        }


def create_crude_oil_strategy_extended(**kwargs) -> CrudeOilStrategyExtended:
    """Factory function for extended strategy."""
    params = CrudeOilParamsExtended(**kwargs)
    return CrudeOilStrategyExtended(params=params)
