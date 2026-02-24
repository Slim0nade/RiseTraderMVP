"""
GBPJPY Carry Trade Strategy

Edge source: Positive swap (interest rate differential) + trend momentum.

Why GBPJPY:
  - Bank of England rate: significantly higher than Bank of Japan
  - Swap on 0.01 lot long position: +8 pts/day
  - Swap on 0.01 lot short position: -15 pts/day
  - Strategy is LONG-ONLY (to capture the positive carry)

Contract spec:
  Symbol:   GBPJPY.
  Leverage: 2,560×
  Margin:   ~$81 per 0.01 lot
  Swap:     +8 pts/day long, -15 pts/day short

Strategy logic:
  Trend filter:  50-period SMA of close price
    → ONLY enter LONG when close > 50-SMA (carry direction = uptrend)
  Entry signal:  Price pulls back to touch or dip below 20-SMA while above 50-SMA
    → Enter LONG on the pullback to 20-SMA
  Stop loss:     2 × ATR(14) below entry price
    → ATR calculated via Wilder's method from in-memory candle buffer
    → NEVER hardcoded — InsufficientDataError propagates if < 15 candles
  Exit signal:   Price closes below 50-SMA on any tick
    → Trend has reversed; exit to avoid negative carry + drawdown

Expected edge:
  Expected Sharpe: 0.5-0.8
  Win rate:        ~55% (trend-following in uptrends)
  Hold time:       Days to weeks (earning swap daily)
  Max drawdown:    ~15-20%

Design notes:
  - LONG-ONLY: short positions have negative swap — never short GBPJPY in this strategy
  - ATR is computed from the strategy's own price_history buffer (MarketTick data)
    using src.utils.atr_calculator.calculate_atr_wilder + Candle objects
  - InsufficientDataError must propagate — no fallback hardcoded ATR values

Author: Claude (RiseTrader Phase 2 - Spread Builder)
"""
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Deque, Dict, List, Optional
from datetime import datetime
import random
import numpy as np

from src.services.market_tick import MarketTick
from src.utils.atr_calculator import calculate_atr_wilder, Candle, InsufficientDataError


@dataclass
class GBPJPYCarryParams:
    """
    GBPJPY Carry Trade strategy parameters.

    Defaults tuned for the GBPJPY. symbol on H1 candles.
    """
    # Trend filter: only LONG when price > 50-SMA
    trend_sma_period: int = 50

    # Entry: pullback to 20-SMA while price > 50-SMA
    entry_sma_period: int = 20

    # ATR for stop loss
    atr_period: int = 14
    atr_stop_multiplier: float = 2.0   # Stop = entry − 2 × ATR

    # Pullback tolerance: enter when price is within this % of 20-SMA
    # (0.003 = 0.3% — for GBPJPY at ~190, that's ~0.57 JPY)
    pullback_tolerance: float = 0.003

    # Position sizing — ultra-capital-efficient as per spec
    quantity: Decimal = Decimal("0.01")

    # Time filter
    use_time_filter: bool = True
    trading_start_hour: int = 8    # GMT
    trading_end_hour: int = 20     # GMT


@dataclass
class GBPJPYCarryState:
    """Track carry trade position state."""
    has_position: bool = False
    position_type: Optional[str] = None   # Always 'buy' for carry strategy
    entry_price: Optional[Decimal] = None
    entry_time: Optional[datetime] = None
    stop_loss: Optional[Decimal] = None
    atr_at_entry: Optional[float] = None


@dataclass
class GBPJPYCarrySignal:
    """
    Trading signal from GBPJPY Carry Trade strategy.

    Matches SyntheticEngine interface.
    """
    action: Optional[str]    # 'buy', 'close_long', or None (never 'sell' — long-only)
    quantity: Decimal
    confidence: float        # 0.0-1.0
    reason: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Diagnostic metadata
    close_price: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    atr: Optional[float] = None


class GBPJPYCarryStrategy:
    """
    GBPJPY Carry Trade Strategy.

    Long-only trend-following strategy that earns positive swap (+8 pts/day)
    while riding GBP/JPY uptrends.

    Entry logic:
    1. Price is above 50-SMA (uptrend confirmed)
    2. Price pulls back to within pullback_tolerance of 20-SMA (entry zone)
    3. Open long position

    Exit logic:
    1. Price closes below 50-SMA → exit immediately (trend reversal)
    2. Stop loss hit (2 × ATR below entry)

    ATR:
    - Computed with Wilder's method from internal candle buffer
    - Requires at least atr_period + 1 = 15 candles in history
    - InsufficientDataError is raised (not caught) if data is missing

    Expected Sharpe: 0.5-0.8
    """

    def __init__(self, params: Optional[GBPJPYCarryParams] = None):
        """Initialize strategy with parameters."""
        self.params = params or GBPJPYCarryParams()
        self.state = GBPJPYCarryState()

        # Price history as plain dicts (for SMA) and as Candle objects (for ATR)
        self._max_history = max(self.params.trend_sma_period, self.params.atr_period) * 3
        # deque auto-evicts oldest on append — no manual pop(0) needed
        self._price_history: Deque[Dict] = deque(maxlen=self._max_history)

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
        self.state = GBPJPYCarryState()
        self._price_history.clear()

    def process_tick(self, tick: MarketTick) -> GBPJPYCarrySignal:
        """
        Process market tick and generate trading signal.

        Args:
            tick: Market tick data (OHLCV)

        Returns:
            GBPJPYCarrySignal with trading decision

        Raises:
            InsufficientDataError: If ATR cannot be computed when needed
                (propagates from calculate_atr_wilder — never silently suppressed)
        """
        # Buffer history (deque auto-evicts oldest)
        self._price_history.append({
            "timestamp": tick.timestamp,
            "open":  float(tick.open),
            "high":  float(tick.high),
            "low":   float(tick.low),
            "close": float(tick.close),
            "volume": tick.volume,
        })

        # Warmup: need at least trend_sma_period bars for SMA
        min_warmup = max(self.params.trend_sma_period, self.params.atr_period + 1)
        if len(self._price_history) < min_warmup:
            return self._no_signal(
                f"Warming up: {len(self._price_history)}/{min_warmup} bars"
            )

        # Time filter
        if not self._is_time_to_trade(tick.timestamp):
            return self._no_signal("Outside trading hours")

        # Compute indicators
        close = float(tick.close)
        sma_20 = self._sma(self.params.entry_sma_period)
        sma_50 = self._sma(self.params.trend_sma_period)

        # Manage position
        if self.state.has_position:
            return self._manage_position(tick, close, sma_50)

        # Check entry
        return self._check_entry(tick, close, sma_20, sma_50)

    # ------------------------------------------------------------------
    # Entry / exit logic
    # ------------------------------------------------------------------

    def _check_entry(
        self,
        tick: MarketTick,
        close: float,
        sma_20: float,
        sma_50: float,
    ) -> GBPJPYCarrySignal:
        """Check for carry trade entry conditions."""

        # 1. Trend filter: price must be above 50-SMA
        if close <= sma_50:
            return self._no_signal(
                f"Below trend: close({close:.4f}) ≤ 50-SMA({sma_50:.4f}) — long-only strategy",
                close_price=close, sma_20=sma_20, sma_50=sma_50,
            )

        # 2. Pullback to 20-SMA entry zone
        distance_pct = abs(close - sma_20) / sma_20
        if distance_pct > self.params.pullback_tolerance:
            return self._no_signal(
                f"Not in pullback zone: close({close:.4f}) distance to 20-SMA({sma_20:.4f}) "
                f"= {distance_pct:.4%} > tolerance({self.params.pullback_tolerance:.4%})",
                close_price=close, sma_20=sma_20, sma_50=sma_50,
            )

        # 3. Calculate ATR for stop — NEVER hardcode; let InsufficientDataError propagate
        atr = self._calculate_atr()  # Raises InsufficientDataError if insufficient data

        # Anti-stop-hunt: add random 5-15 pip offset below the ATR-based stop.
        # GBPJPY pip_size = 0.01 (JPY pair), so 5-15 pips = 0.05-0.15 JPY.
        # This prevents market makers from hunting exact ATR multiples.
        offset = random.uniform(0.05, 0.15)
        stop_loss = close - (self.params.atr_stop_multiplier * atr) - offset

        # Data-driven confidence: scale with trend strength (distance above 50-SMA).
        # Stronger uptrend → higher conviction → higher confidence.
        # Range: [0.5, 0.85]
        trend_strength = (close - sma_50) / sma_50
        confidence = min(0.85, max(0.5, 0.5 + trend_strength * 10))

        # Open long position
        self.state.has_position = True
        self.state.position_type = "buy"
        self.state.entry_price = tick.close
        self.state.entry_time = tick.timestamp
        self.state.stop_loss = Decimal(str(stop_loss))
        self.state.atr_at_entry = atr

        return GBPJPYCarrySignal(
            action="buy",
            quantity=self.params.quantity,
            confidence=confidence,
            reason=(
                f"CARRY BUY: close({close:.4f}) pulled back to 20-SMA({sma_20:.4f}), "
                f"above 50-SMA({sma_50:.4f}), ATR={atr:.4f}, "
                f"stop={stop_loss:.4f} ({self.params.atr_stop_multiplier}×ATR + {offset:.4f} offset), "
                f"confidence={confidence:.3f} (trend_strength={trend_strength:.5f})"
            ),
            stop_loss=stop_loss,
            take_profit=None,  # No fixed TP — hold and earn carry until trend ends
            close_price=close,
            sma_20=sma_20,
            sma_50=sma_50,
            atr=atr,
        )

    def _manage_position(
        self,
        tick: MarketTick,
        close: float,
        sma_50: float,
    ) -> GBPJPYCarrySignal:
        """Manage open carry position — check stop and trend exit."""

        # Primary exit: price closes below 50-SMA → trend reversal
        if close < sma_50:
            return self._close_position(
                tick,
                f"Trend exit: close({close:.4f}) < 50-SMA({sma_50:.4f})"
            )

        # Stop loss exit
        if self.state.stop_loss is not None:
            if close <= float(self.state.stop_loss):
                return self._close_position(
                    tick,
                    f"Stop hit: close({close:.4f}) ≤ stop({float(self.state.stop_loss):.4f})"
                )

        entry_price = float(self.state.entry_price)
        unrealized_pips = (close - entry_price) * 100  # Rough pip proxy

        return GBPJPYCarrySignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=(
                f"Holding CARRY LONG: close({close:.4f}) above 50-SMA({sma_50:.4f}), "
                f"unrealized≈{unrealized_pips:.1f} pips"
            ),
            close_price=close,
            sma_50=sma_50,
        )

    def _close_position(self, tick: MarketTick, reason: str) -> GBPJPYCarrySignal:
        """Close carry long position."""
        self.state.has_position = False
        self.state.position_type = None
        self.state.entry_price = None
        self.state.entry_time = None
        self.state.stop_loss = None
        self.state.atr_at_entry = None

        return GBPJPYCarrySignal(
            action="close_long",
            quantity=self.params.quantity,
            confidence=0.85,
            reason=f"CLOSE CARRY LONG: {reason}",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sma(self, period: int) -> float:
        """Simple moving average of close prices."""
        if len(self._price_history) < period:
            return float(self._price_history[-1]["close"]) if self._price_history else 0.0
        window = [bar["close"] for bar in list(self._price_history)[-period:]]
        return float(np.mean(window))

    def _calculate_atr(self) -> float:
        """
        Calculate ATR using Wilder's method from internal price history.

        Converts internal dict history to Candle objects for atr_calculator.

        Returns:
            ATR value

        Raises:
            InsufficientDataError: If fewer than atr_period+1 candles in history.
                This must NOT be caught — it propagates to the caller to signal
                that the strategy cannot trade safely without real ATR data.
        """
        candles = [
            Candle(
                timestamp=bar["timestamp"],
                open=bar["open"],
                high=bar["high"],
                low=bar["low"],
                close=bar["close"],
                volume=bar["volume"],
            )
            for bar in self._price_history
        ]

        if len(candles) < self.params.atr_period + 1:
            raise InsufficientDataError(
                symbol="GBPJPY.",
                timeframe="H1",
                got=len(candles),
                need=self.params.atr_period,
            )

        atr = calculate_atr_wilder(candles, period=self.params.atr_period)

        if atr is None:
            # calculate_atr_wilder returned None → insufficient data
            raise InsufficientDataError(
                symbol="GBPJPY.",
                timeframe="H1",
                got=len(candles),
                need=self.params.atr_period,
            )

        return atr

    def _is_time_to_trade(self, timestamp: datetime) -> bool:
        """Check if current time is within trading hours."""
        if not self.params.use_time_filter:
            return True
        hour = timestamp.hour
        return self.params.trading_start_hour <= hour < self.params.trading_end_hour

    def _no_signal(
        self,
        reason: str,
        close_price: Optional[float] = None,
        sma_20: Optional[float] = None,
        sma_50: Optional[float] = None,
        atr: Optional[float] = None,
    ) -> GBPJPYCarrySignal:
        """Return a no-action signal."""
        return GBPJPYCarrySignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=reason,
            close_price=close_price,
            sma_20=sma_20,
            sma_50=sma_50,
            atr=atr,
        )

    def get_state(self) -> Dict:
        """Get current strategy state for logging/inspection."""
        close = self._price_history[-1]["close"] if self._price_history else None
        sma_20 = self._sma(self.params.entry_sma_period) if len(self._price_history) >= self.params.entry_sma_period else None
        sma_50 = self._sma(self.params.trend_sma_period) if len(self._price_history) >= self.params.trend_sma_period else None

        return {
            "strategy": "gbpjpy_carry",
            "params": {
                "trend_sma_period": self.params.trend_sma_period,
                "entry_sma_period": self.params.entry_sma_period,
                "atr_period": self.params.atr_period,
                "atr_stop_multiplier": self.params.atr_stop_multiplier,
                "pullback_tolerance": self.params.pullback_tolerance,
                "quantity": str(self.params.quantity),
            },
            "has_position": self.state.has_position,
            "position_type": self.state.position_type,
            "entry_price": str(self.state.entry_price) if self.state.entry_price else None,
            "stop_loss": str(self.state.stop_loss) if self.state.stop_loss else None,
            "atr_at_entry": self.state.atr_at_entry,
            "current_close": close,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "price_history_length": len(self._price_history),
        }


def create_gbpjpy_carry_strategy(**kwargs) -> GBPJPYCarryStrategy:
    """
    Factory function to create GBPJPYCarryStrategy with custom parameters.

    Args:
        **kwargs: Parameters to override defaults.
            - trend_sma_period: Trend filter SMA period (default: 50)
            - entry_sma_period: Pullback entry SMA period (default: 20)
            - atr_period: ATR period for stop calculation (default: 14)
            - atr_stop_multiplier: ATR × multiplier for stop distance (default: 2.0)
            - pullback_tolerance: Max distance from 20-SMA to enter (default: 0.003)
            - quantity: Lot size (default: Decimal("0.01"))
            - use_time_filter: Gate by trading hours (default: True)

    Returns:
        Configured GBPJPYCarryStrategy instance

    Example:
        >>> strategy = create_gbpjpy_carry_strategy(
        ...     atr_stop_multiplier=2.5,
        ...     pullback_tolerance=0.005,
        ... )
    """
    params = GBPJPYCarryParams(**kwargs)
    return GBPJPYCarryStrategy(params=params)
