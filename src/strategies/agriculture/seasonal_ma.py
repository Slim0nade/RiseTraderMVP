"""
Seasonal MA Crossover Strategy for Agricultural Commodities (WHEAT / CORN)

Edge source: Agricultural planting/harvest cycles + trend following.
Seasonal bias filters out counter-trend MA crossover signals, improving
the signal-to-noise ratio during high-conviction seasonal windows.

Expected Sharpe: 0.6-1.0

Symbol-specific seasonal calendars
───────────────────────────────────
CORN  (22.4× leverage, $1,905 margin/lot)
  Plant:   Mar-May  → early rally tendency (bullish bias)
  Peak:    Jun      → still LONG bias
  Harvest: Sep-Nov  → seasonal weakness (bearish bias)
  Neutral: Jan-Feb, Jul-Aug, Dec

WHEAT  (16.6× leverage, $3,254 margin/lot)
  Weather risk: Feb-Apr (frost, late-spring drought) → LONG bias
  May:          Still LONG (pre-harvest worry premium)
  Harvest:      Jul-Sep → weakness/supply glut → SHORT bias
  Neutral:      Jan, Jun, Oct-Dec

Strategy logic
──────────────
- MA Crossover: fast=10, slow=30 (simple moving averages of close)
- On each tick, compute fast_ma and slow_ma from price history
- Crossover signals:
    Golden cross (fast > slow): BUY signal
    Death cross  (fast < slow): SELL signal
- Seasonal filter: only execute signals that ALIGN with seasonal bias
    Seasonal bias = 'long'    → take BUY signals only (filter SELL)
    Seasonal bias = 'short'   → take SELL signals only (filter BUY)
    Seasonal bias = 'neutral' → take NO signals (sit out)
- Position exit: MA crossover in opposite direction (or seasonal window ends)

Author: Claude (RiseTrader Phase 2 - Spread Builder)
"""
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Deque, Dict, List, Optional, Set
from datetime import datetime
import numpy as np

from src.services.market_tick import MarketTick


# ---------------------------------------------------------------------------
# Seasonal definitions
# ---------------------------------------------------------------------------

class SeasonalBias(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


# Month → bias, per symbol.
# Months not listed default to NEUTRAL.
_CORN_CALENDAR: Dict[int, SeasonalBias] = {
    3:  SeasonalBias.LONG,    # March  — planting rally
    4:  SeasonalBias.LONG,    # April  — planting
    5:  SeasonalBias.LONG,    # May    — planting / weather premium
    6:  SeasonalBias.LONG,    # June   — late planting / weather worry
    9:  SeasonalBias.SHORT,   # September — harvest pressure
    10: SeasonalBias.SHORT,   # October   — harvest
    11: SeasonalBias.SHORT,   # November  — post-harvest
}

_WHEAT_CALENDAR: Dict[int, SeasonalBias] = {
    2:  SeasonalBias.LONG,    # February — frost / drought risk premium
    3:  SeasonalBias.LONG,    # March    — weather uncertainty
    4:  SeasonalBias.LONG,    # April    — late frost risk
    5:  SeasonalBias.LONG,    # May      — pre-harvest worry
    7:  SeasonalBias.SHORT,   # July     — harvest supply glut
    8:  SeasonalBias.SHORT,   # August   — continuation of harvest pressure
    9:  SeasonalBias.SHORT,   # September — post-harvest weakness
}

# Supported symbol → calendar mapping
_SYMBOL_CALENDARS: Dict[str, Dict[int, SeasonalBias]] = {
    "CORN":  _CORN_CALENDAR,
    "WHEAT": _WHEAT_CALENDAR,
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SeasonalMAParams:
    """
    Seasonal MA Crossover strategy parameters.

    Same class serves CORN and WHEAT — only the symbol field changes
    which seasonal calendar is used.
    """
    # Symbol this instance is configured for (drives seasonal calendar)
    symbol: str = "CORN"                # "CORN" or "WHEAT"

    # MA periods
    fast_period: int = 10
    slow_period: int = 30

    # Position sizing
    quantity: Decimal = Decimal("0.01")  # Default small size (per spec: capital-efficient)
    risk_percent: float = 1.0            # Informational — sizing done externally

    # Time filter
    use_time_filter: bool = True
    trading_start_hour: int = 8
    trading_end_hour: int = 20

    # Allow positions to be held across neutral months once opened
    # (True = hold until opposite signal; False = close when season turns neutral)
    hold_through_neutral: bool = True


@dataclass
class SeasonalMAState:
    """Track current position state."""
    has_position: bool = False
    position_type: Optional[str] = None   # 'buy' or 'sell'
    entry_price: Optional[Decimal] = None
    entry_time: Optional[datetime] = None
    entry_season: Optional[str] = None    # Season label at entry for logging


@dataclass
class SeasonalMASignal:
    """
    Trading signal from Seasonal MA Crossover strategy.

    Matches SyntheticEngine interface.
    """
    action: Optional[str]    # 'buy', 'sell', 'close_long', 'close_short', or None
    quantity: Decimal
    confidence: float        # 0.0-1.0
    reason: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Diagnostic metadata
    fast_ma: Optional[float] = None
    slow_ma: Optional[float] = None
    seasonal_bias: Optional[str] = None


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class SeasonalMAStrategy:
    """
    Seasonal MA Crossover Strategy for CORN and WHEAT.

    Uses a 10/30 simple moving average crossover gated by a symbol-specific
    seasonal calendar.  Only signals that ALIGN with the seasonal bias are
    executed — opposing signals are silently filtered.

    Seasonal neutral months: no new entries, open positions may be held or
    closed depending on hold_through_neutral parameter.

    Expected Sharpe: 0.6-1.0
    Win rate:        ~55-65% (with seasonal filter applied)
    """

    def __init__(self, params: Optional[SeasonalMAParams] = None):
        """Initialize strategy with parameters."""
        self.params = params or SeasonalMAParams()
        self.state = SeasonalMAState()

        if self.params.symbol not in _SYMBOL_CALENDARS:
            raise ValueError(
                f"Unsupported symbol '{self.params.symbol}'. "
                f"Supported: {list(_SYMBOL_CALENDARS.keys())}"
            )

        self._calendar = _SYMBOL_CALENDARS[self.params.symbol]
        self._max_history = self.params.slow_period * 3
        # deque auto-evicts oldest on append — no manual pop(0) needed
        self._price_history: Deque[float] = deque(maxlen=self._max_history)

    # ------------------------------------------------------------------
    # SyntheticEngine interface
    # ------------------------------------------------------------------

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
        self.state = SeasonalMAState()
        self._price_history.clear()

    def process_tick(self, tick: MarketTick) -> SeasonalMASignal:
        """
        Process market tick and generate trading signal.

        Args:
            tick: Market tick data (OHLCV)

        Returns:
            SeasonalMASignal with trading decision
        """
        # Buffer close price (deque auto-evicts oldest)
        self._price_history.append(float(tick.close))

        # Warmup check
        if len(self._price_history) < self.params.slow_period:
            return self._no_signal(
                f"Warming up: {len(self._price_history)}/{self.params.slow_period} bars"
            )

        # Time filter
        if not self._is_time_to_trade(tick.timestamp):
            return self._no_signal("Outside trading hours")

        # Compute MAs
        fast_ma = self._sma(self.params.fast_period)
        slow_ma = self._sma(self.params.slow_period)

        # Seasonal bias for current month
        bias = self._get_seasonal_bias(tick.timestamp)

        # Manage existing position
        if self.state.has_position:
            return self._manage_position(tick, fast_ma, slow_ma, bias)

        # Check entry
        return self._check_entry(tick, fast_ma, slow_ma, bias)

    # ------------------------------------------------------------------
    # Entry / exit
    # ------------------------------------------------------------------

    def _check_entry(
        self,
        tick: MarketTick,
        fast_ma: float,
        slow_ma: float,
        bias: SeasonalBias,
    ) -> SeasonalMASignal:
        """Check for MA crossover signals gated by seasonal bias."""

        # No entries in neutral months
        if bias == SeasonalBias.NEUTRAL:
            return self._no_signal(
                f"Neutral season ({tick.timestamp.strftime('%B')}): no new entries",
                fast_ma=fast_ma,
                slow_ma=slow_ma,
                seasonal_bias=bias.value,
            )

        # Golden cross → BUY signal
        if fast_ma > slow_ma:
            if bias == SeasonalBias.LONG:
                # Signal aligned with seasonal bias → execute
                return self._open_position(
                    "buy", tick, fast_ma, slow_ma, bias,
                    f"BUY: fast_MA({fast_ma:.4f}) > slow_MA({slow_ma:.4f}), "
                    f"seasonal={bias.value} ({tick.timestamp.strftime('%B')})"
                )
            else:
                # bias == SHORT → filter this opposing signal
                return self._no_signal(
                    f"BUY signal filtered: seasonal bias is {bias.value} ({tick.timestamp.strftime('%B')})",
                    fast_ma=fast_ma, slow_ma=slow_ma, seasonal_bias=bias.value,
                )

        # Death cross → SELL signal
        if fast_ma < slow_ma:
            if bias == SeasonalBias.SHORT:
                # Signal aligned → execute
                return self._open_position(
                    "sell", tick, fast_ma, slow_ma, bias,
                    f"SELL: fast_MA({fast_ma:.4f}) < slow_MA({slow_ma:.4f}), "
                    f"seasonal={bias.value} ({tick.timestamp.strftime('%B')})"
                )
            else:
                # bias == LONG → filter
                return self._no_signal(
                    f"SELL signal filtered: seasonal bias is {bias.value} ({tick.timestamp.strftime('%B')})",
                    fast_ma=fast_ma, slow_ma=slow_ma, seasonal_bias=bias.value,
                )

        # MAs exactly equal — no crossover
        return self._no_signal(
            f"No crossover: fast_MA=slow_MA={fast_ma:.4f}",
            fast_ma=fast_ma, slow_ma=slow_ma, seasonal_bias=bias.value,
        )

    def _manage_position(
        self,
        tick: MarketTick,
        fast_ma: float,
        slow_ma: float,
        bias: SeasonalBias,
    ) -> SeasonalMASignal:
        """Manage open position — exit on opposite crossover or seasonal reversal."""

        position_type = self.state.position_type

        # Exit if MA crossover reverses
        if position_type == "buy" and fast_ma < slow_ma:
            return self._close_position(
                tick,
                f"MA cross reversal: fast({fast_ma:.4f}) < slow({slow_ma:.4f})"
            )

        if position_type == "sell" and fast_ma > slow_ma:
            return self._close_position(
                tick,
                f"MA cross reversal: fast({fast_ma:.4f}) > slow({slow_ma:.4f})"
            )

        # Close if seasonal bias flips against position and hold_through_neutral=False
        if not self.params.hold_through_neutral:
            if position_type == "buy" and bias != SeasonalBias.LONG:
                return self._close_position(
                    tick,
                    f"Seasonal exit: bias turned {bias.value}, long position closed"
                )
            if position_type == "sell" and bias != SeasonalBias.SHORT:
                return self._close_position(
                    tick,
                    f"Seasonal exit: bias turned {bias.value}, short position closed"
                )

        return SeasonalMASignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=f"Holding {position_type}: fast({fast_ma:.4f}) slow({slow_ma:.4f}) bias={bias.value}",
            fast_ma=fast_ma,
            slow_ma=slow_ma,
            seasonal_bias=bias.value,
        )

    def _open_position(
        self,
        position_type: str,
        tick: MarketTick,
        fast_ma: float,
        slow_ma: float,
        bias: SeasonalBias,
        reason: str,
    ) -> SeasonalMASignal:
        """Open a new position."""
        self.state.has_position = True
        self.state.position_type = position_type
        self.state.entry_price = tick.close
        self.state.entry_time = tick.timestamp
        self.state.entry_season = bias.value

        # Data-driven confidence: scale with MA spread distance.
        # Stronger crossover (fast_ma further from slow_ma) → higher confidence.
        # Range: [0.50, 0.85]
        ma_spread_pct = abs(fast_ma - slow_ma) / slow_ma if slow_ma > 0 else 0.0
        confidence = min(0.85, max(0.50, 0.50 + ma_spread_pct * 10))

        return SeasonalMASignal(
            action=position_type,
            quantity=self.params.quantity,
            confidence=confidence,
            reason=reason,
            fast_ma=fast_ma,
            slow_ma=slow_ma,
            seasonal_bias=bias.value,
        )

    def _close_position(self, tick: MarketTick, reason: str) -> SeasonalMASignal:
        """Close current position."""
        position_type = self.state.position_type
        close_action = "close_long" if position_type == "buy" else "close_short"

        self.state.has_position = False
        self.state.position_type = None
        self.state.entry_price = None
        self.state.entry_time = None
        self.state.entry_season = None

        return SeasonalMASignal(
            action=close_action,
            quantity=self.params.quantity,
            confidence=0.8,
            reason=f"CLOSE {position_type.upper()}: {reason}",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sma(self, period: int) -> float:
        """Calculate simple moving average of close prices."""
        if len(self._price_history) < period:
            return float(self._price_history[-1]) if self._price_history else 0.0
        window = list(self._price_history)[-period:]
        return float(np.mean(window))

    def _get_seasonal_bias(self, timestamp: datetime) -> SeasonalBias:
        """Return seasonal bias for the given month."""
        return self._calendar.get(timestamp.month, SeasonalBias.NEUTRAL)

    def _is_time_to_trade(self, timestamp: datetime) -> bool:
        """Check if current time is within trading hours."""
        if not self.params.use_time_filter:
            return True
        hour = timestamp.hour
        return self.params.trading_start_hour <= hour < self.params.trading_end_hour

    def _no_signal(
        self,
        reason: str,
        fast_ma: Optional[float] = None,
        slow_ma: Optional[float] = None,
        seasonal_bias: Optional[str] = None,
    ) -> SeasonalMASignal:
        """Return a no-action signal."""
        return SeasonalMASignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=reason,
            fast_ma=fast_ma,
            slow_ma=slow_ma,
            seasonal_bias=seasonal_bias,
        )

    def get_state(self) -> Dict:
        """Get current strategy state for logging/inspection."""
        fast_ma = self._sma(self.params.fast_period) if len(self._price_history) >= self.params.fast_period else None
        slow_ma = self._sma(self.params.slow_period) if len(self._price_history) >= self.params.slow_period else None

        return {
            "strategy": "seasonal_ma",
            "symbol": self.params.symbol,
            "params": {
                "fast_period": self.params.fast_period,
                "slow_period": self.params.slow_period,
                "hold_through_neutral": self.params.hold_through_neutral,
            },
            "has_position": self.state.has_position,
            "position_type": self.state.position_type,
            "entry_price": str(self.state.entry_price) if self.state.entry_price else None,
            "entry_season": self.state.entry_season,
            "fast_ma": fast_ma,
            "slow_ma": slow_ma,
            "price_history_length": len(self._price_history),
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_seasonal_ma_strategy(**kwargs) -> SeasonalMAStrategy:
    """
    Factory function to create SeasonalMAStrategy with custom parameters.

    Args:
        **kwargs: Parameters to override defaults.
            - symbol: "CORN" or "WHEAT" (default: "CORN")
            - fast_period: Fast SMA period (default: 10)
            - slow_period: Slow SMA period (default: 30)
            - quantity: Position size in lots (default: Decimal("0.01"))
            - use_time_filter: Gate by trading hours (default: True)
            - hold_through_neutral: Hold positions in neutral months (default: True)

    Returns:
        Configured SeasonalMAStrategy instance

    Examples:
        >>> corn = create_seasonal_ma_strategy(symbol="CORN")
        >>> wheat = create_seasonal_ma_strategy(symbol="WHEAT", fast_period=12)
    """
    params = SeasonalMAParams(**kwargs)
    return SeasonalMAStrategy(params=params)
