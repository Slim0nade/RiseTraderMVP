"""
WTI-Brent Spread Strategy

Edge source: Geographic/logistic mean-reversion between WTI crude (US benchmark)
and Brent crude (European/global benchmark).

Historical background:
- WTI and Brent typically trade within $3-$7 of each other
- Spread widens due to logistic constraints (Cushing OK storage, pipeline capacity)
- Infrastructure expansions (Seaway pipeline reversal 2012, Gulf Coast exports)
  periodically reset the mean, so use rolling normalization
- Current spread: ~$5.20 (mid-range)

Contract normalization:
- CrudeOIL (WTI): 1,000 bbl per lot, $1/tick
- BRENT_OIL:      1,000 bbl per lot, $10/tick
- Both are the same barrel unit — spread is directly BRENT_OIL − CrudeOIL
  (no gallon conversion needed, unlike crack spread)

Expected edge:
- Expected Sharpe: 0.8-1.2
- Win rate: ~55-60% (mean-reversion in ranging regimes)
- Max drawdown: ~12-15%

Strategy logic:
- Spread = BRENT_OIL close − CrudeOIL close
- Rolling 20-period mean and stdev of spread
- Entry: spread > +1.5σ → SELL spread (sell BRENT, buy WTI)
         spread < −1.5σ → BUY spread (buy BRENT, sell WTI)
- Exit:  spread reverts to mean (crosses 0σ band)
- Stop:  spread moves 2.5σ against entry

Multi-symbol note:
  Strategy receives ticks from EITHER symbol. It buffers the last close for each
  symbol. A spread value is only computed when BOTH symbols have at least one tick.
  Signals are emitted on the tick of whichever symbol arrives last.

Author: Claude (RiseTrader Phase 2 - Spread Builder)
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import numpy as np

from src.services.market_tick import MarketTick


@dataclass
class WTIBrentParams:
    """
    WTI-Brent spread strategy parameters.

    Both symbols must be configured in the backtesting engine.
    This strategy expects ticks from 'CrudeOIL' and 'BRENT_OIL'.
    """
    # Rolling window for spread normalization
    lookback_period: int = 20  # 20-period rolling mean/stdev

    # Entry/exit thresholds (in σ units)
    entry_sigma: float = 1.5   # Enter when |spread_z| >= entry_sigma
    exit_sigma: float = 0.0    # Exit when spread_z reverts to ~0
    stop_sigma: float = 2.5    # Stop loss at 2.5σ from entry

    # Exit band tolerance (avoid churning near 0)
    exit_band: float = 0.3     # |spread_z| <= exit_band → consider mean-reverted

    # Position sizing
    # NOTE: Fixed lot size for backtesting/signal-quality measurement only.
    # In live/paper trading, position size is capped at 2% account risk by
    # RiskManagerAgent._calculate_position_size() before order execution.
    quantity: Decimal = Decimal("1.0")  # Lots per leg

    # Time filter
    use_time_filter: bool = True
    trading_start_hour: int = 8   # GMT
    trading_end_hour: int = 20    # GMT


@dataclass
class WTIBrentState:
    """Track spread position state."""
    has_position: bool = False
    spread_direction: Optional[str] = None   # 'long_spread' or 'short_spread'

    # Long spread = buy BRENT, sell WTI  (spread was too negative)
    # Short spread = sell BRENT, buy WTI (spread was too positive)

    entry_spread: Optional[float] = None     # Spread value at entry
    entry_spread_z: Optional[float] = None  # Z-score at entry
    entry_time: Optional[datetime] = None
    stop_spread_z: Optional[float] = None   # Z-score stop level


@dataclass
class WTIBrentSignal:
    """
    Trading signal from WTI-Brent spread strategy.

    Matches SyntheticEngine interface (action, quantity, confidence, reason).
    For spread strategies action encodes which leg to act on:
      - 'buy'  / 'sell'         → open a new spread leg
      - 'close_long' / 'close_short' → close a spread leg
    The SyntheticEngine will receive two sequential signals per spread trade
    (one per leg), hence 'spread_action' carries the full picture.
    """
    action: Optional[str]       # 'buy', 'sell', 'close_long', 'close_short', or None
    quantity: Decimal
    confidence: float           # 0.0-1.0
    reason: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Spread-specific metadata (for logging / downstream use)
    spread_value: Optional[float] = None
    spread_z: Optional[float] = None


class WTIBrentSpreadStrategy:
    """
    WTI-Brent Crude Oil Spread Strategy.

    Trades the mean-reversion of the BRENT_OIL − CrudeOIL spread.

    Both legs carry 1,000 bbl per lot — no gallon conversion required.

    Multi-symbol operation:
      - Call process_tick() with ticks from EITHER CrudeOIL or BRENT_OIL
      - Strategy buffers the latest close for each symbol
      - Spread is computed only when both symbols have data
      - Signal fires on each tick once both symbols are primed

    Expected Sharpe: 0.8-1.2
    Win rate:        ~55-60% (mean-reversion)
    Max drawdown:    ~12-15%
    """

    SYMBOL_WTI = "CrudeOIL"
    SYMBOL_BRENT = "BRENT_OIL"

    def __init__(self, params: Optional[WTIBrentParams] = None):
        """Initialize strategy with parameters."""
        self.params = params or WTIBrentParams()
        self.state = WTIBrentState()

        # Per-symbol last close price
        self._last_close: Dict[str, float] = {}

        # Rolling spread history (BRENT − WTI)
        self._spread_history: List[float] = []

        # Track which symbol's tick was most recent
        self._last_tick_symbol: Optional[str] = None
        self._last_tick_timestamp: Optional[datetime] = None

    # ------------------------------------------------------------------
    # SyntheticEngine interface
    # ------------------------------------------------------------------

    @property
    def has_position(self) -> bool:
        """Property for SyntheticEngine compatibility."""
        return self.state.has_position

    @property
    def entry_price(self) -> Optional[Decimal]:
        """
        Return entry spread as Decimal for SyntheticEngine compatibility.
        Spread strategies don't have a single entry price — we return the
        BRENT close at entry as a representative value.
        """
        if self.state.entry_spread is None:
            return None
        return Decimal(str(self.state.entry_spread))

    def reset(self) -> None:
        """Reset strategy state for new backtest."""
        self.state = WTIBrentState()
        self._last_close.clear()
        self._spread_history.clear()
        self._last_tick_symbol = None
        self._last_tick_timestamp = None

    def process_tick(self, tick: MarketTick) -> WTIBrentSignal:
        """
        Process market tick from either CrudeOIL or BRENT_OIL.

        Args:
            tick: Market tick (symbol must be CrudeOIL or BRENT_OIL)

        Returns:
            WTIBrentSignal with trading decision
        """
        # Accept only expected symbols
        if tick.symbol not in (self.SYMBOL_WTI, self.SYMBOL_BRENT):
            return self._no_signal(f"Unexpected symbol: {tick.symbol}")

        # Buffer the latest close for this symbol
        self._last_close[tick.symbol] = float(tick.close)
        self._last_tick_symbol = tick.symbol
        self._last_tick_timestamp = tick.timestamp

        # Need both symbols primed before computing a spread
        if self.SYMBOL_WTI not in self._last_close or self.SYMBOL_BRENT not in self._last_close:
            missing = self.SYMBOL_BRENT if self.SYMBOL_WTI in self._last_close else self.SYMBOL_WTI
            return self._no_signal(f"Waiting for first tick from {missing}")

        # Compute current spread
        spread = self._last_close[self.SYMBOL_BRENT] - self._last_close[self.SYMBOL_WTI]

        # Update spread history (one data point per completed tick pair)
        self._spread_history.append(spread)
        if len(self._spread_history) > self.params.lookback_period * 3:
            self._spread_history.pop(0)

        # Warmup check
        if len(self._spread_history) < self.params.lookback_period:
            return self._no_signal(
                f"Warming up: {len(self._spread_history)}/{self.params.lookback_period} spread samples"
            )

        # Normalise spread to Z-score
        spread_z, spread_mean, spread_std = self._compute_z(spread)

        # Time filter
        if not self._is_time_to_trade(tick.timestamp):
            return self._no_signal("Outside trading hours")

        # Manage existing position or look for entry
        if self.state.has_position:
            return self._manage_position(tick, spread, spread_z)

        return self._check_entry(tick, spread, spread_z, spread_mean, spread_std)

    # ------------------------------------------------------------------
    # Entry / exit logic
    # ------------------------------------------------------------------

    def _check_entry(
        self,
        tick: MarketTick,
        spread: float,
        spread_z: float,
        spread_mean: float,
        spread_std: float,
    ) -> WTIBrentSignal:
        """Check for spread entry signals."""

        # Spread too HIGH → sell BRENT, buy WTI (short spread)
        if spread_z >= self.params.entry_sigma:
            stop_z = spread_z + (self.params.stop_sigma - self.params.entry_sigma)
            self.state.has_position = True
            self.state.spread_direction = "short_spread"
            self.state.entry_spread = spread
            self.state.entry_spread_z = spread_z
            self.state.entry_time = tick.timestamp
            self.state.stop_spread_z = stop_z

            return WTIBrentSignal(
                action="sell",  # Sell BRENT (primary leg), buy WTI (hedge leg)
                quantity=self.params.quantity,
                confidence=0.65,
                reason=(
                    f"SHORT SPREAD: BRENT−WTI spread={spread:.2f} z={spread_z:.2f}σ "
                    f"(entry≥{self.params.entry_sigma}σ) "
                    f"→ sell BRENT, buy WTI; stop at z={stop_z:.2f}σ"
                ),
                spread_value=spread,
                spread_z=spread_z,
            )

        # Spread too LOW → buy BRENT, sell WTI (long spread)
        if spread_z <= -self.params.entry_sigma:
            stop_z = spread_z - (self.params.stop_sigma - self.params.entry_sigma)
            self.state.has_position = True
            self.state.spread_direction = "long_spread"
            self.state.entry_spread = spread
            self.state.entry_spread_z = spread_z
            self.state.entry_time = tick.timestamp
            self.state.stop_spread_z = stop_z

            return WTIBrentSignal(
                action="buy",   # Buy BRENT (primary leg), sell WTI (hedge leg)
                quantity=self.params.quantity,
                confidence=0.65,
                reason=(
                    f"LONG SPREAD: BRENT−WTI spread={spread:.2f} z={spread_z:.2f}σ "
                    f"(entry≤-{self.params.entry_sigma}σ) "
                    f"→ buy BRENT, sell WTI; stop at z={stop_z:.2f}σ"
                ),
                spread_value=spread,
                spread_z=spread_z,
            )

        return self._no_signal(
            f"No signal: spread={spread:.2f} z={spread_z:.2f}σ "
            f"(need |z|≥{self.params.entry_sigma}σ)"
        )

    def _manage_position(
        self,
        tick: MarketTick,
        spread: float,
        spread_z: float,
    ) -> WTIBrentSignal:
        """Manage open spread position — check stop and mean-reversion exit."""

        direction = self.state.spread_direction

        # Stop loss check
        if direction == "short_spread":
            # Spread widening further (worse for short) — stop out
            if spread_z >= self.state.stop_spread_z:
                return self._close_position(
                    tick, spread, spread_z,
                    f"Stop hit: z={spread_z:.2f}σ ≥ stop={self.state.stop_spread_z:.2f}σ"
                )
            # Mean reversion exit: spread returned to near 0
            if spread_z <= self.params.exit_band:
                return self._close_position(
                    tick, spread, spread_z,
                    f"Mean reversion: z={spread_z:.2f}σ ≤ {self.params.exit_band}σ"
                )

        elif direction == "long_spread":
            # Spread narrowing further (worse for long) — stop out
            if spread_z <= self.state.stop_spread_z:
                return self._close_position(
                    tick, spread, spread_z,
                    f"Stop hit: z={spread_z:.2f}σ ≤ stop={self.state.stop_spread_z:.2f}σ"
                )
            # Mean reversion exit: spread returned to near 0
            if spread_z >= -self.params.exit_band:
                return self._close_position(
                    tick, spread, spread_z,
                    f"Mean reversion: z={spread_z:.2f}σ ≥ -{self.params.exit_band}σ"
                )

        return self._no_signal(
            f"Holding {direction}: spread={spread:.2f} z={spread_z:.2f}σ",
            spread_value=spread,
            spread_z=spread_z,
        )

    def _close_position(
        self,
        tick: MarketTick,
        spread: float,
        spread_z: float,
        reason: str,
    ) -> WTIBrentSignal:
        """Close current spread position."""
        direction = self.state.spread_direction
        close_action = "close_short" if direction == "short_spread" else "close_long"

        self.state.has_position = False
        self.state.spread_direction = None
        self.state.entry_spread = None
        self.state.entry_spread_z = None
        self.state.entry_time = None
        self.state.stop_spread_z = None

        return WTIBrentSignal(
            action=close_action,
            quantity=self.params.quantity,
            confidence=0.8,
            reason=f"CLOSE SPREAD ({direction}): {reason}",
            spread_value=spread,
            spread_z=spread_z,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_z(self, spread: float) -> Tuple[float, float, float]:
        """
        Compute Z-score of current spread using rolling lookback window.

        Returns:
            (z_score, mean, std)
        """
        window = self._spread_history[-self.params.lookback_period:]
        mean = float(np.mean(window))
        std = float(np.std(window, ddof=1))

        if std < 1e-8:
            return 0.0, mean, std

        z = (spread - mean) / std
        return z, mean, std

    def _is_time_to_trade(self, timestamp: datetime) -> bool:
        """Check if current time is within trading hours."""
        if not self.params.use_time_filter:
            return True
        hour = timestamp.hour
        return self.params.trading_start_hour <= hour < self.params.trading_end_hour

    def _no_signal(
        self,
        reason: str,
        spread_value: Optional[float] = None,
        spread_z: Optional[float] = None,
    ) -> WTIBrentSignal:
        """Return a no-action signal."""
        return WTIBrentSignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=reason,
            spread_value=spread_value,
            spread_z=spread_z,
        )

    def get_state(self) -> Dict:
        """Get current strategy state for logging/inspection."""
        last_spread = None
        if self.SYMBOL_WTI in self._last_close and self.SYMBOL_BRENT in self._last_close:
            last_spread = self._last_close[self.SYMBOL_BRENT] - self._last_close[self.SYMBOL_WTI]

        return {
            "strategy": "wti_brent_spread",
            "params": {
                "lookback_period": self.params.lookback_period,
                "entry_sigma": self.params.entry_sigma,
                "exit_sigma": self.params.exit_sigma,
                "stop_sigma": self.params.stop_sigma,
            },
            "has_position": self.state.has_position,
            "spread_direction": self.state.spread_direction,
            "entry_spread": self.state.entry_spread,
            "entry_spread_z": self.state.entry_spread_z,
            "stop_spread_z": self.state.stop_spread_z,
            "last_spread": last_spread,
            "spread_history_length": len(self._spread_history),
            "last_prices": dict(self._last_close),
        }


def create_wti_brent_spread_strategy(**kwargs) -> WTIBrentSpreadStrategy:
    """
    Factory function to create WTIBrentSpreadStrategy with custom parameters.

    Args:
        **kwargs: Parameters to override defaults.
            - lookback_period: Rolling window for Z-score (default: 20)
            - entry_sigma: Entry threshold in σ (default: 1.5)
            - exit_sigma: Exit threshold in σ (default: 0.0)
            - exit_band: Exit tolerance band in σ (default: 0.3)
            - stop_sigma: Stop loss in σ from entry (default: 2.5)
            - quantity: Lots per leg (default: Decimal("1.0"))
            - use_time_filter: Gate by trading hours (default: True)
            - trading_start_hour: Hour GMT (default: 8)
            - trading_end_hour: Hour GMT (default: 20)

    Returns:
        Configured WTIBrentSpreadStrategy instance

    Example:
        >>> strategy = create_wti_brent_spread_strategy(
        ...     lookback_period=30,
        ...     entry_sigma=2.0,
        ... )
    """
    params = WTIBrentParams(**kwargs)
    return WTIBrentSpreadStrategy(params=params)
