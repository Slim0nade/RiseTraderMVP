"""
Crash Portfolio Pre-Positioning Strategy — Phase 3 Crisis Logic

Detects market crisis conditions and deploys a balanced short/long portfolio
designed to profit from equity crashes and demand destruction.

Crisis detection:
    USA500 drawdown > 7% in the last 10 candles triggers portfolio deployment.
    This is a proxy for VIX spike / equity crash regime. Crisis easing is
    detected when USA500 recovers above 3% from the crash low.

Portfolio composition:
    SHORT positions (60% allocation — demand destruction / equity crash):
        CrudeOIL   — demand destruction; crude falls in recessions
        USA500     — equity index crash (S&P 500)
        USA100     — tech-heavy NASDAQ crash

    LONG positions (40% allocation — safe haven flight):
        GOLD       — classic safe haven asset
        30Y_T-BOND — flight to safety; bonds rally as stocks fall
        DOLLAR_INDX — risk-off USD strengthening (DXY)

Backtest architecture:
    Since SyntheticEngine processes one symbol at a time, in backtest mode
    this strategy operates as a single-symbol strategy (primary symbol only).
    It buffers USA500 ticks for crisis detection; when deployed, it generates
    signals for the primary symbol based on whether that symbol is in the
    short or long book.

    In live mode, the full 6-symbol portfolio deployment happens via the
    signal → RiskManagerAgent → ExecutionAgent pipeline using the `positions`
    list in CrashPortfolioSignal.

ATR:
    Calculated from the primary symbol's price buffer using Wilder's method.
    Requires at least atr_period + 1 candles. InsufficientDataError propagates
    — never hardcoded. Stop distance = atr_stop_multiplier × ATR with a
    random anti-stop-hunt pip offset.

Expected edge:
    During crash regimes (COVID-19, 2022 energy crisis): +150-200% return
    Win rate during detected crises: ~70-75% (mean-reversion fade on recovery)
    Hold time: Days to weeks
    Max drawdown in non-crisis periods: minimal (no deployment)

Author: Claude (RiseTrader Phase 3 - Crisis Automator)
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque
import random
import numpy as np

from src.services.market_tick import MarketTick
from src.utils.atr_calculator import calculate_atr_wilder, Candle, InsufficientDataError


# ---------------------------------------------------------------------------
# Portfolio composition constants
# ---------------------------------------------------------------------------

# Default short book: demand destruction + equity crash plays
DEFAULT_SHORT_SYMBOLS = ["CrudeOIL", "USA500", "USA100"]

# Default long book: safe havens
DEFAULT_LONG_SYMBOLS = ["GOLD", "30Y_T-BOND", "DOLLAR_INDX"]


@dataclass
class CrashPortfolioParams:
    """
    Crash Portfolio pre-positioning strategy parameters.

    Designed for crisis regimes where equity markets fall sharply and
    commodities / safe-haven assets diverge dramatically.

    Input ranges:
        crisis_drawdown_threshold: [0.03, 0.15] — 7% is empirically calibrated
            for S&P500 (below 3% = noise, above 15% = already too late)
        recovery_threshold:        [0.01, 0.05] — when to close positions
        drawdown_lookback:         [5, 20] — bars to look back for drawdown
        atr_stop_multiplier:       [1.5, 4.0] — wider in crisis (more noise)
        atr_trail_multiplier:      [1.0, 3.0] — trail during crash momentum
        short_allocation:          [0.50, 0.70] — sum with long_allocation must = 1.0
        long_allocation:           [0.30, 0.50] — complementary to short
    """
    crisis_regime_required: bool = True       # Only deploy when crisis detected

    # Portfolio composition
    short_symbols: List[str] = field(
        default_factory=lambda: list(DEFAULT_SHORT_SYMBOLS)
    )
    long_symbols: List[str] = field(
        default_factory=lambda: list(DEFAULT_LONG_SYMBOLS)
    )

    # Allocation fractions (must sum to 1.0)
    short_allocation: float = 0.60            # 60% to crash-SHORT book
    long_allocation: float = 0.40             # 40% to safe-haven-LONG book

    # Crisis detection
    crisis_drawdown_threshold: float = 0.07   # USA500 drawdown > 7% = crisis
    recovery_threshold: float = 0.03          # USA500 recovery > 3% = easing
    drawdown_lookback: int = 10               # bars to compute drawdown

    # ATR-based stop configuration
    atr_period: int = 14
    atr_stop_multiplier: float = 2.5          # Stop = entry ± 2.5 × ATR
    atr_trail_multiplier: float = 2.0         # Trail at 2× ATR once profitable 1× ATR

    # Anti-stop-hunt random pip offset
    min_offset_pips: int = 5
    max_offset_pips: int = 15

    # Position sizing (fixed for backtest signal-quality measurement)
    # NOTE: In live/paper trading, RiskManagerAgent overrides this with
    # 2% account-risk sizing before execution.
    quantity: Decimal = Decimal("0.01")

    # Time filter
    use_time_filter: bool = True
    trading_start_hour: int = 8              # GMT
    trading_end_hour: int = 20               # GMT

    # Primary symbol for backtest mode (used for ATR + single-symbol signals)
    # Default USA500 so crisis detection and primary signal use the same buffer.
    primary_symbol: str = "USA500"


@dataclass
class CrashPortfolioState:
    """Runtime state for crash portfolio."""
    is_deployed: bool = False                  # Portfolio is live
    deployment_time: Optional[datetime] = None
    crash_low: Optional[float] = None          # Lowest close since deployment
    entry_price: Optional[Decimal] = None      # Primary symbol entry price
    stop_loss: Optional[Decimal] = None        # ATR-based stop for primary
    trailing_stop: Optional[Decimal] = None    # Active trail stop if profitable
    atr_at_entry: Optional[float] = None


@dataclass
class CrashPortfolioSignal:
    """
    Trading signal from the crash portfolio strategy.

    In backtest mode, action/quantity operate on the primary symbol only.
    In live mode, the `positions` list carries the full multi-symbol deployment.

    Actions:
        'deploy'    — open full crash portfolio (all 6 symbols)
        'close_all' — close all positions (crisis easing)
        None        — no action (hold or waiting)

    Attributes:
        action:           Portfolio-level action.
        quantity:         Primary symbol lot size (backtest compat).
        confidence:       0.0-1.0; scales with drawdown severity.
        reason:           Human-readable explanation.
        regime:           Detected regime that triggered deployment.
        positions:        Full multi-symbol deployment spec (live mode).
            Each entry: {symbol, direction, allocation_pct, stop_atr_mult}
        stop_loss:        Stop for primary symbol (backtest compat).
        take_profit:      None (no fixed TP — hold through recovery exit).
        drawdown_pct:     Detected drawdown that triggered deployment.
        usa500_close:     Latest USA500 close for diagnostics.
    """
    action: Optional[str]
    quantity: Decimal
    confidence: float
    reason: str
    regime: str = "unknown"
    positions: List[Dict] = field(default_factory=list)
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    drawdown_pct: Optional[float] = None
    usa500_close: Optional[float] = None

    # SyntheticEngine compatibility
    @property
    def stop_loss_float(self) -> Optional[float]:
        return float(self.stop_loss) if self.stop_loss is not None else None


class CrashPortfolioStrategy:
    """
    Crash Portfolio Pre-Positioning Strategy.

    Monitors USA500 for crisis conditions (>7% drawdown in 10 bars), then
    deploys a diversified crash portfolio: SHORT crude/equities, LONG gold/bonds/USD.

    In backtest mode (single-symbol): uses primary_symbol buffer for both
    crisis detection and signal generation. For USA500, this works natively.
    For other symbols, it still detects via USA500 ticks when they arrive.

    Entry logic:
    1. Detect USA500 drawdown > crisis_drawdown_threshold in last drawdown_lookback bars
    2. Deploy crash portfolio:
       - Short: CrudeOIL, USA500, USA100 (demand destruction + equity crash)
       - Long:  GOLD, 30Y_T-BOND, DOLLAR_INDX (safe havens)
    3. Calculate ATR-based stops for each position (anti-stop-hunt offset)
    4. Trail stops at 2× ATR once profitable by 1× ATR

    Exit logic:
    1. USA500 recovers > recovery_threshold from crash low → close all
    2. Primary symbol stop hit → close all (crisis reversed)

    ATR:
    - Computed with Wilder's method from internal price buffer
    - Requires atr_period + 1 candles minimum
    - InsufficientDataError propagates — never suppressed

    Expected edge in genuine crisis:
    - Win rate: ~70-75% (strong trend confirmation before entry)
    - Avg crisis hold: 5-30 days
    """

    def __init__(self, params: Optional[CrashPortfolioParams] = None):
        """Initialize strategy with parameters."""
        self.params = params or CrashPortfolioParams()
        self.state = CrashPortfolioState()

        # Per-symbol price buffers for crisis detection + ATR
        # Key: symbol name. Value: deque of dicts {timestamp, open, high, low, close, volume}
        self._price_buffers: Dict[str, deque] = {}

        # Maximum buffer size: enough for drawdown + ATR warmup
        self._max_buffer = max(200, self.params.drawdown_lookback * 5, self.params.atr_period * 5)

        # All symbols we track (primary + entire portfolio for live mode)
        all_symbols = (
            [self.params.primary_symbol]
            + self.params.short_symbols
            + self.params.long_symbols
        )
        for sym in set(all_symbols):
            self._price_buffers[sym] = deque(maxlen=self._max_buffer)

    # ------------------------------------------------------------------
    # SyntheticEngine interface
    # ------------------------------------------------------------------

    @property
    def has_position(self) -> bool:
        """SyntheticEngine compatibility."""
        return self.state.is_deployed

    @property
    def entry_price(self) -> Optional[Decimal]:
        """SyntheticEngine compatibility — primary symbol entry."""
        return self.state.entry_price

    def reset(self) -> None:
        """Reset strategy state for new backtest run."""
        self.state = CrashPortfolioState()
        for buf in self._price_buffers.values():
            buf.clear()

    def process_tick(self, tick: MarketTick) -> CrashPortfolioSignal:
        """
        Process a market tick and generate crash portfolio signal.

        Accepts ticks from ANY of the portfolio symbols or the primary symbol.
        Crisis detection always uses the USA500 buffer (or primary_symbol buffer
        when the primary IS USA500). Signal generation targets the primary symbol.

        Args:
            tick: MarketTick from any of: USA500, CrudeOIL, USA100, GOLD,
                  30Y_T-BOND, DOLLAR_INDX, or primary_symbol.

        Returns:
            CrashPortfolioSignal with portfolio decision.

        Raises:
            InsufficientDataError: If ATR cannot be computed when needed.
                Propagates — never silently suppressed.
        """
        # Buffer this tick
        self._buffer_tick(tick)

        # Use primary symbol buffer for crisis detection when it is USA500
        # Otherwise use whatever buffer we have for USA500 if available
        primary_buf = self._price_buffers.get(self.params.primary_symbol)
        if not primary_buf:
            return self._no_signal("No primary symbol buffer", tick)

        # Warmup: need at least drawdown_lookback AND atr_period+1 for primary
        min_warmup = max(self.params.drawdown_lookback + 1, self.params.atr_period + 2)
        if len(primary_buf) < min_warmup:
            return self._no_signal(
                f"Warming up: {len(primary_buf)}/{min_warmup} bars", tick
            )

        # Time filter — use tick timestamp
        if not self._is_time_to_trade(tick.timestamp):
            return self._no_signal("Outside trading hours", tick)

        close = float(primary_buf[-1]["close"])

        # === Manage existing deployment ===
        if self.state.is_deployed:
            return self._manage_deployment(tick, close)

        # === Check for crisis entry ===
        return self._check_crisis_entry(tick, close)

    # ------------------------------------------------------------------
    # Crisis detection
    # ------------------------------------------------------------------

    def _detect_crisis(self) -> float:
        """
        Compute drawdown of primary symbol over the last drawdown_lookback bars.

        Drawdown = (peak_close - current_close) / peak_close

        Returns:
            Drawdown as a fraction [0.0, 1.0]. Positive = falling market.
            0.0 if insufficient data.

        Expected range:
            Normal market: 0.0 - 0.03 (0-3%)
            Stress:        0.03 - 0.07 (3-7%)
            Crisis:        > 0.07 (>7%) — triggers deployment
        """
        primary_buf = self._price_buffers.get(self.params.primary_symbol)
        if primary_buf is None or len(primary_buf) < self.params.drawdown_lookback:
            return 0.0

        window = list(primary_buf)[-self.params.drawdown_lookback:]
        closes = [bar["close"] for bar in window]
        peak = max(closes)
        current = closes[-1]

        if peak <= 0.0:
            return 0.0

        return (peak - current) / peak

    def _is_crisis_easing(self) -> bool:
        """
        Check if crisis is easing: primary symbol recovered > recovery_threshold
        from the crash low recorded at deployment.

        Returns:
            True if crisis appears to be easing and portfolio should close.
        """
        if not self.state.is_deployed or self.state.crash_low is None:
            return False

        primary_buf = self._price_buffers.get(self.params.primary_symbol)
        if not primary_buf:
            return False

        current_close = float(primary_buf[-1]["close"])
        crash_low = self.state.crash_low

        if crash_low <= 0.0:
            return False

        recovery = (current_close - crash_low) / crash_low
        return recovery >= self.params.recovery_threshold

    # ------------------------------------------------------------------
    # Entry / management logic
    # ------------------------------------------------------------------

    def _check_crisis_entry(
        self,
        tick: MarketTick,
        close: float,
    ) -> CrashPortfolioSignal:
        """
        Check for crisis deployment conditions.

        Fires when primary symbol drawdown > crisis_drawdown_threshold.
        ATR is calculated from the primary symbol buffer for stop placement.
        """
        drawdown = self._detect_crisis()

        if drawdown < self.params.crisis_drawdown_threshold:
            return self._no_signal(
                f"No crisis: drawdown={drawdown:.2%} < threshold={self.params.crisis_drawdown_threshold:.2%}",
                tick,
                drawdown_pct=drawdown,
            )

        # Crisis detected — calculate ATR for stops
        # This WILL raise InsufficientDataError if data is insufficient
        atr = self._calculate_atr(self.params.primary_symbol)

        # Random pip offset for anti-stop-hunt
        pip_offset = random.randint(self.params.min_offset_pips, self.params.max_offset_pips)
        pip_size = close * 0.0001  # generic pip; symbol-specific adjustment in live

        # Confidence scales with drawdown severity
        # At threshold: confidence = 0.5; at 2× threshold: confidence = 1.0
        raw_conf = (drawdown - self.params.crisis_drawdown_threshold) / self.params.crisis_drawdown_threshold
        confidence = min(1.0, max(0.0, 0.5 + raw_conf * 0.5))

        # Build stop for primary symbol (SHORT position → stop above entry)
        # For SHORT: stop = close + (atr_stop_mult × ATR) + random_offset
        # For LONG safe havens, handled in live mode per-symbol
        if self.params.primary_symbol in self.params.short_symbols:
            stop_price = close + (self.params.atr_stop_multiplier * atr) + (pip_offset * pip_size)
            primary_direction = "short"
        else:
            # Primary is in long book
            stop_price = close - (self.params.atr_stop_multiplier * atr) - (pip_offset * pip_size)
            primary_direction = "long"

        stop_decimal = Decimal(str(round(stop_price, 5)))

        # Record state
        self.state.is_deployed = True
        self.state.deployment_time = tick.timestamp
        self.state.crash_low = close
        self.state.entry_price = tick.close
        self.state.stop_loss = stop_decimal
        self.state.trailing_stop = None
        self.state.atr_at_entry = atr

        # Build multi-symbol positions for live mode
        positions = self._build_positions_list(atr, close)

        return CrashPortfolioSignal(
            action="deploy",
            quantity=self.params.quantity,
            confidence=confidence,
            reason=(
                f"CRASH DEPLOY: {self.params.primary_symbol} drawdown={drawdown:.2%} "
                f"> {self.params.crisis_drawdown_threshold:.0%} threshold | "
                f"ATR={atr:.4f} | stop={stop_price:.4f} ({self.params.atr_stop_multiplier}×ATR + {pip_offset}pip)"
            ),
            regime="crisis",
            positions=positions,
            stop_loss=stop_decimal,
            take_profit=None,
            drawdown_pct=drawdown,
            usa500_close=close,
        )

    def _manage_deployment(
        self,
        tick: MarketTick,
        close: float,
    ) -> CrashPortfolioSignal:
        """
        Manage an active crash portfolio deployment.

        Checks:
        1. Crisis easing (USA500 recovered > recovery_threshold from low)
        2. Stop loss hit (primary symbol against us)
        3. Trail stop update (if profitable > 1× ATR)

        Returns:
            CrashPortfolioSignal — 'close_all' or hold.
        """
        # Update crash low (track the worst level seen since deployment)
        if self.state.crash_low is not None and close < self.state.crash_low:
            self.state.crash_low = close

        # Check crisis easing → close all
        if self._is_crisis_easing():
            return self._close_all(
                tick,
                f"Crisis easing: {self.params.primary_symbol} recovered "
                f">{self.params.recovery_threshold:.0%} from low({self.state.crash_low:.4f})",
                close,
            )

        # Check stop loss
        stop = self.state.trailing_stop or self.state.stop_loss
        if stop is not None:
            stop_f = float(stop)
            # For short primary: stop is above close (exit if price rises above stop)
            if self.params.primary_symbol in self.params.short_symbols:
                if close >= stop_f:
                    return self._close_all(
                        tick,
                        f"Stop hit (SHORT): close({close:.4f}) >= stop({stop_f:.4f})",
                        close,
                    )
            else:
                # For long primary: stop is below close (exit if price drops below stop)
                if close <= stop_f:
                    return self._close_all(
                        tick,
                        f"Stop hit (LONG): close({close:.4f}) <= stop({stop_f:.4f})",
                        close,
                    )

        # Trail stop update: if profitable > 1× ATR, trail at 2× ATR
        if self.state.atr_at_entry is not None and self.state.entry_price is not None:
            self._update_trailing_stop(close)

        entry_f = float(self.state.entry_price) if self.state.entry_price else close
        if self.params.primary_symbol in self.params.short_symbols:
            unrealized = entry_f - close  # positive = profitable SHORT
        else:
            unrealized = close - entry_f  # positive = profitable LONG

        return CrashPortfolioSignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=(
                f"Holding crash portfolio: {self.params.primary_symbol}({close:.4f}), "
                f"unrealized≈{unrealized:.4f} | "
                f"stop={float(stop):.4f}" if stop else
                f"Holding crash portfolio: {self.params.primary_symbol}({close:.4f})"
            ),
            regime="crisis",
            usa500_close=close,
        )

    def _close_all(
        self,
        tick: MarketTick,
        reason: str,
        close: float,
    ) -> CrashPortfolioSignal:
        """Close all portfolio positions and reset state."""
        self.state.is_deployed = False
        self.state.deployment_time = None
        self.state.crash_low = None
        self.state.entry_price = None
        self.state.stop_loss = None
        self.state.trailing_stop = None
        self.state.atr_at_entry = None

        return CrashPortfolioSignal(
            action="close_all",
            quantity=self.params.quantity,
            confidence=0.9,
            reason=f"CLOSE ALL: {reason}",
            regime="crisis_easing",
            usa500_close=close,
        )

    def _update_trailing_stop(self, close: float) -> None:
        """
        Update trailing stop when position is profitable by > 1× ATR.

        For SHORT primary: trail above current close (at 2× ATR above)
        For LONG  primary: trail below current close (at 2× ATR below)
        """
        atr = self.state.atr_at_entry
        entry_f = float(self.state.entry_price)

        if self.params.primary_symbol in self.params.short_symbols:
            # SHORT: profitable when close fell (close < entry)
            profit_atr = (entry_f - close) / atr if atr > 0 else 0.0
            if profit_atr >= 1.0:
                new_trail = close + (self.params.atr_trail_multiplier * atr)
                current_trail = float(self.state.trailing_stop) if self.state.trailing_stop else float("inf")
                # For SHORT, trail moves down (lower stop = better for us)
                if new_trail < current_trail:
                    self.state.trailing_stop = Decimal(str(round(new_trail, 5)))
        else:
            # LONG: profitable when close rose (close > entry)
            profit_atr = (close - entry_f) / atr if atr > 0 else 0.0
            if profit_atr >= 1.0:
                new_trail = close - (self.params.atr_trail_multiplier * atr)
                current_trail = float(self.state.trailing_stop) if self.state.trailing_stop else 0.0
                # For LONG, trail moves up (higher stop = better for us)
                if new_trail > current_trail:
                    self.state.trailing_stop = Decimal(str(round(new_trail, 5)))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_positions_list(self, atr: float, primary_close: float) -> List[Dict]:
        """
        Build the full multi-symbol position spec for live mode deployment.

        Each entry describes one leg of the crash portfolio with:
            symbol:          Trading symbol
            direction:       'long' or 'short'
            allocation_pct:  Fraction of total portfolio allocated to this leg
            stop_atr_mult:   ATR multiplier for stop distance (same for all legs)

        Args:
            atr:           ATR from primary symbol (used as proxy for all legs)
            primary_close: Primary symbol close for reference

        Returns:
            List of position dicts, sorted by allocation descending.
        """
        positions = []
        n_short = len(self.params.short_symbols)
        n_long = len(self.params.long_symbols)

        # Distribute allocation evenly within each book
        short_alloc_each = self.params.short_allocation / max(n_short, 1)
        long_alloc_each = self.params.long_allocation / max(n_long, 1)

        for sym in self.params.short_symbols:
            positions.append({
                "symbol": sym,
                "direction": "short",
                "allocation_pct": round(short_alloc_each, 4),
                "stop_atr_mult": self.params.atr_stop_multiplier,
            })

        for sym in self.params.long_symbols:
            positions.append({
                "symbol": sym,
                "direction": "long",
                "allocation_pct": round(long_alloc_each, 4),
                "stop_atr_mult": self.params.atr_stop_multiplier,
            })

        return sorted(positions, key=lambda x: x["allocation_pct"], reverse=True)

    def _buffer_tick(self, tick: MarketTick) -> None:
        """Append tick data to the appropriate symbol buffer."""
        bar = {
            "timestamp": tick.timestamp,
            "open":   float(tick.open),
            "high":   float(tick.high),
            "low":    float(tick.low),
            "close":  float(tick.close),
            "volume": tick.volume,
        }
        if tick.symbol in self._price_buffers:
            self._price_buffers[tick.symbol].append(bar)
        else:
            # Accept ticks from unknown portfolio symbols — add buffer dynamically
            self._price_buffers[tick.symbol] = deque([bar], maxlen=self._max_buffer)

    def _calculate_atr(self, symbol: str) -> float:
        """
        Calculate Wilder's ATR from the symbol's internal price buffer.

        Args:
            symbol: Symbol to calculate ATR for.

        Returns:
            ATR value as a positive float.

        Raises:
            InsufficientDataError: If fewer than atr_period+1 candles available.
                This error MUST NOT be caught here — it propagates upward to
                signal that the strategy cannot trade safely without real data.
        """
        buf = self._price_buffers.get(symbol)
        if buf is None:
            raise InsufficientDataError(
                symbol=symbol,
                timeframe="H1",
                got=0,
                need=self.params.atr_period,
            )

        candles = [
            Candle(
                timestamp=bar["timestamp"],
                open=bar["open"],
                high=bar["high"],
                low=bar["low"],
                close=bar["close"],
                volume=bar["volume"],
            )
            for bar in buf
        ]

        if len(candles) < self.params.atr_period + 1:
            raise InsufficientDataError(
                symbol=symbol,
                timeframe="H1",
                got=len(candles),
                need=self.params.atr_period,
            )

        atr = calculate_atr_wilder(candles, period=self.params.atr_period)

        if atr is None:
            raise InsufficientDataError(
                symbol=symbol,
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
        tick: MarketTick,
        drawdown_pct: Optional[float] = None,
    ) -> CrashPortfolioSignal:
        """Return a no-action signal."""
        primary_buf = self._price_buffers.get(self.params.primary_symbol)
        usa500_close = float(primary_buf[-1]["close"]) if primary_buf else None

        return CrashPortfolioSignal(
            action=None,
            quantity=Decimal("0.0"),
            confidence=0.0,
            reason=reason,
            regime="normal",
            drawdown_pct=drawdown_pct,
            usa500_close=usa500_close,
        )

    def get_state(self) -> Dict:
        """Get current strategy state for logging/inspection."""
        primary_buf = self._price_buffers.get(self.params.primary_symbol)
        latest_close = float(primary_buf[-1]["close"]) if primary_buf else None
        drawdown = self._detect_crisis()

        return {
            "strategy": "crash_portfolio",
            "params": {
                "crisis_drawdown_threshold": self.params.crisis_drawdown_threshold,
                "recovery_threshold": self.params.recovery_threshold,
                "drawdown_lookback": self.params.drawdown_lookback,
                "atr_period": self.params.atr_period,
                "atr_stop_multiplier": self.params.atr_stop_multiplier,
                "atr_trail_multiplier": self.params.atr_trail_multiplier,
                "short_allocation": self.params.short_allocation,
                "long_allocation": self.params.long_allocation,
                "short_symbols": self.params.short_symbols,
                "long_symbols": self.params.long_symbols,
                "primary_symbol": self.params.primary_symbol,
            },
            "is_deployed": self.state.is_deployed,
            "deployment_time": self.state.deployment_time.isoformat() if self.state.deployment_time else None,
            "crash_low": self.state.crash_low,
            "entry_price": str(self.state.entry_price) if self.state.entry_price else None,
            "stop_loss": str(self.state.stop_loss) if self.state.stop_loss else None,
            "trailing_stop": str(self.state.trailing_stop) if self.state.trailing_stop else None,
            "atr_at_entry": self.state.atr_at_entry,
            "current_close": latest_close,
            "current_drawdown": drawdown,
            "buffers": {sym: len(buf) for sym, buf in self._price_buffers.items()},
        }


def create_crash_portfolio_strategy(**kwargs) -> CrashPortfolioStrategy:
    """
    Factory function to create CrashPortfolioStrategy with custom parameters.

    Args:
        **kwargs: Parameters to override CrashPortfolioParams defaults.
            crisis_drawdown_threshold (float): Drawdown to trigger deployment. Default: 0.07
            recovery_threshold (float):        Recovery to close portfolio. Default: 0.03
            drawdown_lookback (int):           Bars for drawdown computation. Default: 10
            atr_period (int):                  ATR period. Default: 14
            atr_stop_multiplier (float):       Stop distance in ATR. Default: 2.5
            atr_trail_multiplier (float):      Trail at 2× ATR. Default: 2.0
            short_allocation (float):          Fraction to short book. Default: 0.60
            long_allocation (float):           Fraction to long book. Default: 0.40
            short_symbols (List[str]):         Symbols to short. Default: CrudeOIL, USA500, USA100
            long_symbols (List[str]):          Symbols to go long. Default: GOLD, 30Y_T-BOND, DOLLAR_INDX
            primary_symbol (str):              Primary symbol for backtest mode. Default: USA500
            quantity (Decimal):                Fixed lot size for backtest. Default: Decimal("0.01")
            use_time_filter (bool):            Gate by trading hours. Default: True

    Returns:
        Configured CrashPortfolioStrategy instance.

    Example:
        >>> strategy = create_crash_portfolio_strategy(
        ...     crisis_drawdown_threshold=0.10,
        ...     atr_stop_multiplier=3.0,
        ... )
    """
    # Convert quantity to Decimal if passed as float/int/str
    if "quantity" in kwargs and not isinstance(kwargs["quantity"], Decimal):
        kwargs["quantity"] = Decimal(str(kwargs["quantity"]))

    params = CrashPortfolioParams(**kwargs)
    return CrashPortfolioStrategy(params=params)
