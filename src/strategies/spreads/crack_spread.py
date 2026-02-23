"""
Crack Spread Strategy — CrudeOIL vs GASOLINE

The "crack spread" is the refinery margin: the dollar differential between
crude oil input cost and refined product (gasoline) output value.

Spread definition:
    spread = gasoline_barrel_price - crude_price
    where gasoline_barrel_price = GASOLINE_price_per_gallon × 42

When the spread widens beyond historical norms, refiners are earning excess
margins (gasoline is expensive relative to crude). Mean reversion logic
bets on the spread contracting back toward its 20-period mean.

Contract normalization:
    CrudeOIL:  1,000 bbl/contract, $1/tick, tick = $0.01/bbl
    GASOLINE:  100,000 gal/contract, $10/tick, tick = $0.0001/gal

    1 barrel = 42 gallons
    1 CrudeOIL contract = 1,000 bbl × 42 gal/bbl = 42,000 gal equivalent
    1 GASOLINE contract = 100,000 gal

    Dollar-neutral lot ratio:
        To match $1 move in crude_barrel_price (= $1,000/contract):
            gasoline move needed = $1,000 / (100,000 gal × 42 gal/bbl factor)
        Simpler: express everything per barrel:
            crude_dollar = crude_price × 1,000 (bbl per contract)
            gas_dollar   = gasoline_barrel_price × 1,000 (matching crude barrels)
            → trade 1 CrudeOIL lot vs (42,000 / 100,000) = 0.42 GASOLINE lots
            → round to practical minimum: 1 CrudeOIL : 0.42 GASOLINE (or 5:2 ratio)

Signal logic:
    z_score = (spread - rolling_mean) / rolling_stdev
    z > +entry_sigma → SELL spread (sell GASOLINE, buy CrudeOIL)
    z < -entry_sigma → BUY spread (buy GASOLINE, sell CrudeOIL)
    |z| < exit_sigma → close (spread mean-reverted)
    |z| > stop_sigma → stop loss (spread continuing against us)

Seasonal overlay (crack spreads naturally widen in summer driving season):
    Q1 (Jan-Mar):  entry threshold = 1.5σ (normal)
    Q2 (Apr-Jun):  entry threshold = 1.8σ (spreads naturally wide, need bigger edge)
    Q3 (Jul-Sep):  entry threshold = 2.0σ (peak summer driving — most noise)
    Q4 (Oct-Dec):  entry threshold = 1.5σ (normal, colder weather)

Multi-symbol architecture:
    The strategy maintains internal buffers for BOTH symbols.
    process_tick() accepts ticks from either symbol.
    Signal generation fires only when both buffers have >= lookback candles
    AND the latest ticks for each symbol are within max_tick_age_seconds of
    each other (to avoid stale spread calculations).

Targets:
    Win rate:       60-65%
    Profit factor:  1.8-2.2×
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np

from src.services.market_tick import MarketTick


# ---------------------------------------------------------------------------
# Contract constants — never change without updating contract_normalization.md
# ---------------------------------------------------------------------------
CRUDE_BBL_PER_CONTRACT = 1_000          # barrels per CrudeOIL lot
GASOLINE_GAL_PER_CONTRACT = 100_000     # gallons per GASOLINE lot
GAL_PER_BBL = 42                        # unit conversion

# Dollar-neutral hedge ratio: crude_lots : gasoline_lots
# $1/bbl move in crude = $1,000/contract
# To match on gasoline side per barrel basis:
#   gasoline_lots = (crude_bbl_per_contract × gal_per_bbl) / gasoline_gal_per_contract
#                 = (1,000 × 42) / 100,000 = 0.42
HEDGE_RATIO_GAS_PER_CRUDE = (CRUDE_BBL_PER_CONTRACT * GAL_PER_BBL) / GASOLINE_GAL_PER_CONTRACT
# = 0.42 GASOLINE lots per 1 CrudeOIL lot


@dataclass
class CrackSpreadParams:
    """
    Crack spread strategy parameters.

    All entry/exit thresholds are expressed in standard deviations of the
    20-period rolling spread distribution.

    Input ranges:
        lookback:        [10, 50] — shorter = more responsive, longer = more stable
        entry_sigma:     [1.0, 3.0] — higher = fewer but higher-quality trades
        exit_sigma:      [0.0, 1.0] — 0.0 = exit at mean exactly
        stop_sigma:      [2.0, 5.0] — must be > entry_sigma
        crude_lots:      [0.1, 10.0]
    """
    # Spread statistics window
    lookback: int = 20                   # rolling periods for mean/stdev

    # Entry/exit thresholds (σ)
    entry_sigma: float = 1.5             # enter when |z| > entry_sigma
    exit_sigma: float = 0.3             # exit when |z| < exit_sigma (near mean)
    stop_sigma: float = 2.5             # stop when |z| > stop_sigma (spread accelerating)

    # Seasonal sigma adjustments (added to base entry_sigma by quarter)
    q2_sigma_addon: float = 0.3          # Q2 Apr-Jun: wider entry (+0.3σ)
    q3_sigma_addon: float = 0.5          # Q3 Jul-Sep: peak noise (+0.5σ)

    # Position sizing
    # NOTE: Fixed lot size for backtesting/signal-quality measurement only.
    # In live/paper trading, position size is capped at 2% account risk by
    # RiskManagerAgent._calculate_position_size() before order execution.
    crude_lots: Decimal = Decimal("1.0")  # CrudeOIL lots per trade
    # gasoline_lots auto-calculated = crude_lots × HEDGE_RATIO_GAS_PER_CRUDE

    # Symbol names (match DB exactly)
    crude_symbol: str = "CrudeOIL"
    gasoline_symbol: str = "GASOLINE"

    # Staleness gate: max seconds between crude and gasoline ticks
    # to treat spread as "current". At H1 candles this is 3600s.
    max_tick_age_seconds: int = 3600

    # Time filter
    use_time_filter: bool = True
    trading_start_hour: int = 8          # GMT
    trading_end_hour: int = 20           # GMT

    # Seasonality
    enable_seasonality: bool = True


@dataclass
class CrackSpreadState:
    """Runtime state for one spread position."""
    has_position: bool = False
    position_type: Optional[str] = None  # 'buy_spread' or 'sell_spread'
    entry_price_crude: Optional[Decimal] = None
    entry_price_gasoline: Optional[Decimal] = None
    entry_spread: Optional[float] = None
    entry_time: Optional[datetime] = None

    # σ at which this trade stops out (computed from params at entry time)
    stop_sigma_at_entry: float = 2.5


@dataclass
class CrackSpreadSignal:
    """
    Trading signal from the crack spread strategy.

    For spread trades action encodes both legs:
        'buy_spread'  → BUY  GASOLINE + SELL CrudeOIL
        'sell_spread' → SELL GASOLINE + BUY  CrudeOIL
        'close'       → flatten both legs
        None          → no action

    Attributes:
        action:          Trade direction or None.
        crude_quantity:  CrudeOIL lots (Decimal, always positive).
        gasoline_quantity: GASOLINE lots (Decimal, always positive).
        confidence:      0.0-1.0. Scales with distance beyond entry_sigma.
        reason:          Human-readable explanation.
        spread_value:    Current computed spread (gas_barrel - crude).
        z_score:         Current spread z-score.
        stop_spread:     Spread level that triggers stop (on spread units).
        target_spread:   Spread level targeted for exit.
    """
    action: Optional[str]
    crude_quantity: Decimal
    gasoline_quantity: Decimal
    confidence: float
    reason: str
    spread_value: Optional[float] = None
    z_score: Optional[float] = None
    stop_spread: Optional[float] = None
    target_spread: Optional[float] = None

    # SyntheticEngine compat shims (single-leg strategies use these)
    @property
    def quantity(self) -> Decimal:
        """Return crude quantity for SyntheticEngine compat."""
        return self.crude_quantity

    @property
    def stop_loss(self) -> Optional[float]:
        return self.stop_spread

    @property
    def take_profit(self) -> Optional[float]:
        return self.target_spread


class CrackSpreadStrategy:
    """
    Crack spread mean-reversion strategy.

    Accepts ticks from EITHER CrudeOIL or GASOLINE. Maintains separate
    price buffers for each leg. Computes the crack spread as:

        spread[t] = gasoline_barrel_price[t] - crude_price[t]
        gasoline_barrel_price = gasoline_close_per_gallon × GAL_PER_BBL

    Entry fires when both buffers have >= lookback candles AND the most
    recent ticks for each leg are within max_tick_age_seconds of each other.

    Expected input ranges:
        CrudeOIL close:  $50–$120 (USD per barrel)
        GASOLINE close:  $1.00–$4.00 (USD per gallon, multiply × 42 for barrel)
        Spread (gas_bbl - crude): typically −$5 to +$30 (seasonal variation)
    """

    def __init__(self, params: Optional[CrackSpreadParams] = None):
        """
        Initialize with optional params (uses defaults if None).

        Args:
            params: CrackSpreadParams instance or None for defaults.
        """
        self.params = params or CrackSpreadParams()
        self.state = CrackSpreadState()

        # Per-symbol price buffers: list of dicts with timestamp + close
        self._crude_buffer: List[Dict] = []
        self._gasoline_buffer: List[Dict] = []

        # Derived spread series (aligned by position in buffer)
        # Populated by _try_compute_spread() after both buffers have data
        self._spread_series: List[float] = []

        # Maximum buffer size (keep 3× lookback to handle misalignment)
        self._max_buffer = max(200, self.params.lookback * 3)

    # ------------------------------------------------------------------
    # SyntheticEngine interface
    # ------------------------------------------------------------------

    @property
    def has_position(self) -> bool:
        """SyntheticEngine compatibility."""
        return self.state.has_position

    @property
    def entry_price(self) -> Optional[Decimal]:
        """SyntheticEngine compatibility. Returns crude entry price."""
        return self.state.entry_price_crude

    def reset(self) -> None:
        """Reset all state for a fresh backtest run."""
        self.state = CrackSpreadState()
        self._crude_buffer.clear()
        self._gasoline_buffer.clear()
        self._spread_series.clear()

    def process_tick(self, tick: MarketTick) -> CrackSpreadSignal:
        """
        Accept a tick from either CrudeOIL or GASOLINE.

        Strategy logic:
        1. Buffer the tick in the appropriate per-symbol buffer.
        2. Try to compute the aligned spread series.
        3. If insufficient data → return warmup signal.
        4. If outside trading hours → return no-signal.
        5. If in position → manage (check stop/target).
        6. Else → check entry conditions.

        Args:
            tick: MarketTick with .symbol matching crude_symbol or gasoline_symbol.

        Returns:
            CrackSpreadSignal with trading decision.
        """
        self._buffer_tick(tick)

        # Attempt spread computation
        spread, z_score = self._compute_spread_zscore()
        if spread is None:
            return self._warmup_signal()

        if not self._is_time_to_trade(tick.timestamp):
            return CrackSpreadSignal(
                action=None,
                crude_quantity=Decimal("0"),
                gasoline_quantity=Decimal("0"),
                confidence=0.0,
                reason="Outside trading hours",
                spread_value=spread,
                z_score=z_score,
            )

        if self.state.has_position:
            return self._manage_position(spread, z_score, tick.timestamp)

        return self._check_entry(spread, z_score, tick.timestamp)

    def get_state(self) -> Dict:
        """Return current strategy state for monitoring/logging."""
        crude_latest = self._crude_buffer[-1] if self._crude_buffer else None
        gas_latest = self._gasoline_buffer[-1] if self._gasoline_buffer else None

        spread, z_score = self._compute_spread_zscore()

        return {
            "strategy": "crack_spread",
            "params": {
                "lookback": self.params.lookback,
                "entry_sigma": self.params.entry_sigma,
                "exit_sigma": self.params.exit_sigma,
                "stop_sigma": self.params.stop_sigma,
                "hedge_ratio_gas_per_crude": round(HEDGE_RATIO_GAS_PER_CRUDE, 4),
            },
            "buffers": {
                "crude_candles": len(self._crude_buffer),
                "gasoline_candles": len(self._gasoline_buffer),
                "spread_series_length": len(self._spread_series),
            },
            "latest_prices": {
                "crude": float(crude_latest["close"]) if crude_latest else None,
                "gasoline_per_gal": float(gas_latest["close"]) if gas_latest else None,
                "gasoline_per_bbl": float(gas_latest["close"]) * GAL_PER_BBL if gas_latest else None,
                "spread": spread,
                "z_score": z_score,
            },
            "position": {
                "has_position": self.state.has_position,
                "type": self.state.position_type,
                "entry_crude": str(self.state.entry_price_crude) if self.state.entry_price_crude else None,
                "entry_gasoline": str(self.state.entry_price_gasoline) if self.state.entry_price_gasoline else None,
                "entry_spread": self.state.entry_spread,
                "entry_time": self.state.entry_time.isoformat() if self.state.entry_time else None,
            },
        }

    # ------------------------------------------------------------------
    # Internal: data management
    # ------------------------------------------------------------------

    def _buffer_tick(self, tick: MarketTick) -> None:
        """Append tick to the correct per-symbol buffer."""
        entry = {
            "timestamp": tick.timestamp,
            "close": float(tick.close),
            "high": float(tick.high),
            "low": float(tick.low),
        }
        if tick.symbol == self.params.crude_symbol:
            self._crude_buffer.append(entry)
            if len(self._crude_buffer) > self._max_buffer:
                self._crude_buffer.pop(0)
        elif tick.symbol == self.params.gasoline_symbol:
            self._gasoline_buffer.append(entry)
            if len(self._gasoline_buffer) > self._max_buffer:
                self._gasoline_buffer.pop(0)

    def _compute_spread_zscore(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Compute the current crack spread and its z-score.

        Spread = gasoline_barrel_price - crude_price
               = (gasoline_close × 42) - crude_close

        Returns:
            (spread, z_score) or (None, None) if insufficient data or ticks stale.

        Expected ranges:
            spread:  −$5 to +$30 (normal crack spread range)
            z_score: typically −3 to +3 during trading periods
        """
        if (len(self._crude_buffer) < self.params.lookback or
                len(self._gasoline_buffer) < self.params.lookback):
            return None, None

        # Staleness check: latest ticks must be within max_tick_age_seconds
        crude_ts = self._crude_buffer[-1]["timestamp"]
        gas_ts = self._gasoline_buffer[-1]["timestamp"]
        age_diff = abs((crude_ts - gas_ts).total_seconds())
        if age_diff > self.params.max_tick_age_seconds:
            return None, None

        # Build aligned spread series using the lookback most-recent ticks.
        # Since both buffers are updated independently, we take the last
        # `lookback` entries from each buffer — they should be time-aligned
        # for H1 data where both symbols tick at the same candle boundaries.
        crude_closes = np.array([b["close"] for b in self._crude_buffer[-self.params.lookback:]])
        gas_closes = np.array([b["close"] for b in self._gasoline_buffer[-self.params.lookback:]])

        # Convert gasoline from $/gallon → $/barrel
        gas_barrel_prices = gas_closes * GAL_PER_BBL

        spread_series = gas_barrel_prices - crude_closes

        spread_mean = float(np.mean(spread_series))
        spread_stdev = float(np.std(spread_series, ddof=1))

        if spread_stdev < 1e-8:
            # Degenerate: no spread variation (should not happen in live markets)
            return float(spread_series[-1]), 0.0

        current_spread = float(spread_series[-1])
        z_score = (current_spread - spread_mean) / spread_stdev

        # Store for state introspection
        self._spread_series = list(spread_series)

        return current_spread, z_score

    def _spread_stats(self) -> Tuple[float, float]:
        """Return (mean, stdev) of the current spread series."""
        if len(self._spread_series) < 2:
            return 0.0, 1.0
        arr = np.array(self._spread_series)
        return float(np.mean(arr)), float(np.std(arr, ddof=1))

    # ------------------------------------------------------------------
    # Internal: signal generation
    # ------------------------------------------------------------------

    def _get_entry_sigma(self, timestamp: datetime) -> float:
        """
        Return the entry sigma threshold adjusted for seasonality.

        Crack spreads naturally widen in summer driving season, so we
        require a larger edge to enter in Q2-Q3.

        Args:
            timestamp: Current bar timestamp.

        Returns:
            Effective entry sigma threshold (>= params.entry_sigma).
        """
        if not self.params.enable_seasonality:
            return self.params.entry_sigma

        month = timestamp.month
        if 4 <= month <= 6:       # Q2: Apr-Jun — refinery maintenance, spreads widen
            return self.params.entry_sigma + self.params.q2_sigma_addon
        elif 7 <= month <= 9:     # Q3: Jul-Sep — peak summer driving, most noise
            return self.params.entry_sigma + self.params.q3_sigma_addon
        else:                      # Q1 + Q4: normal
            return self.params.entry_sigma

    def _check_entry(
        self, spread: float, z_score: float, timestamp: datetime
    ) -> CrackSpreadSignal:
        """
        Check entry conditions against the current z-score.

        Buy spread  (long gas, short crude): z_score < -entry_sigma
        Sell spread (short gas, long crude): z_score > +entry_sigma

        Confidence scales linearly between entry_sigma and stop_sigma:
            confidence = (|z| - entry_sigma) / (stop_sigma - entry_sigma)
            clamped to [0.0, 1.0]

        Args:
            spread:    Current spread value (gas_bbl - crude).
            z_score:   Current z-score.
            timestamp: Current bar timestamp.

        Returns:
            CrackSpreadSignal with action or None.
        """
        entry_sigma = self._get_entry_sigma(timestamp)
        spread_mean, spread_stdev = self._spread_stats()

        abs_z = abs(z_score)
        if abs_z <= entry_sigma:
            return CrackSpreadSignal(
                action=None,
                crude_quantity=Decimal("0"),
                gasoline_quantity=Decimal("0"),
                confidence=0.0,
                reason=f"No signal: z={z_score:.2f}, threshold=±{entry_sigma:.1f}σ",
                spread_value=spread,
                z_score=z_score,
            )

        # Confidence: how far past entry_sigma are we?
        sigma_range = self.params.stop_sigma - entry_sigma
        raw_conf = (abs_z - entry_sigma) / sigma_range if sigma_range > 0 else 1.0
        confidence = min(1.0, max(0.0, raw_conf))

        # Compute stop and target levels on the spread
        stop_spread, target_spread = self._compute_levels(spread_mean, spread_stdev, z_score)

        # gasoline_lots = crude_lots × hedge_ratio
        crude_qty = self.params.crude_lots
        gasoline_qty = Decimal(str(round(float(crude_qty) * HEDGE_RATIO_GAS_PER_CRUDE, 2)))

        if z_score > entry_sigma:
            # Spread too wide → SELL spread (short gas, long crude)
            action = "sell_spread"
            reason = (
                f"SELL spread: z={z_score:.2f} > +{entry_sigma:.1f}σ | "
                f"spread={spread:.2f} (mean={spread_mean:.2f}) | "
                f"crude_lots={crude_qty} gas_lots={gasoline_qty}"
            )
        else:
            # Spread too tight → BUY spread (long gas, short crude)
            action = "buy_spread"
            reason = (
                f"BUY spread: z={z_score:.2f} < -{entry_sigma:.1f}σ | "
                f"spread={spread:.2f} (mean={spread_mean:.2f}) | "
                f"crude_lots={crude_qty} gas_lots={gasoline_qty}"
            )

        # Record entry state
        crude_latest = self._crude_buffer[-1]["close"]
        gas_latest = self._gasoline_buffer[-1]["close"]

        self.state.has_position = True
        self.state.position_type = action
        self.state.entry_price_crude = Decimal(str(crude_latest))
        self.state.entry_price_gasoline = Decimal(str(gas_latest))
        self.state.entry_spread = spread
        self.state.entry_time = timestamp
        self.state.stop_sigma_at_entry = self.params.stop_sigma

        return CrackSpreadSignal(
            action=action,
            crude_quantity=crude_qty,
            gasoline_quantity=gasoline_qty,
            confidence=confidence,
            reason=reason,
            spread_value=spread,
            z_score=z_score,
            stop_spread=stop_spread,
            target_spread=target_spread,
        )

    def _manage_position(
        self, spread: float, z_score: float, timestamp: datetime
    ) -> CrackSpreadSignal:
        """
        Manage existing position. Check stop and target conditions.

        Stop: |z_score| > stop_sigma (spread accelerating away from mean)
        Target: |z_score| < exit_sigma (spread has mean-reverted)

        Args:
            spread:    Current spread value.
            z_score:   Current z-score.
            timestamp: Current bar timestamp.

        Returns:
            CrackSpreadSignal — 'close' or None (hold).
        """
        crude_qty = self.params.crude_lots
        gasoline_qty = Decimal(str(round(float(crude_qty) * HEDGE_RATIO_GAS_PER_CRUDE, 2)))

        abs_z = abs(z_score)

        # Stop loss: spread moving further from mean
        if abs_z >= self.state.stop_sigma_at_entry:
            return self._close_position(
                crude_qty, gasoline_qty, spread, z_score,
                f"STOP: z={z_score:.2f} exceeded ±{self.state.stop_sigma_at_entry:.1f}σ"
            )

        # Target: spread has returned near mean
        if abs_z <= self.params.exit_sigma:
            return self._close_position(
                crude_qty, gasoline_qty, spread, z_score,
                f"TARGET: z={z_score:.2f} within ±{self.params.exit_sigma:.1f}σ of mean"
            )

        return CrackSpreadSignal(
            action=None,
            crude_quantity=Decimal("0"),
            gasoline_quantity=Decimal("0"),
            confidence=0.0,
            reason=f"Holding {self.state.position_type}: z={z_score:.2f}",
            spread_value=spread,
            z_score=z_score,
        )

    def _close_position(
        self,
        crude_qty: Decimal,
        gasoline_qty: Decimal,
        spread: float,
        z_score: float,
        reason: str,
    ) -> CrackSpreadSignal:
        """Reset position state and emit a close signal."""
        self.state.has_position = False
        self.state.position_type = None
        self.state.entry_price_crude = None
        self.state.entry_price_gasoline = None
        self.state.entry_spread = None
        self.state.entry_time = None

        return CrackSpreadSignal(
            action="close",
            crude_quantity=crude_qty,
            gasoline_quantity=gasoline_qty,
            confidence=0.9,
            reason=f"CLOSE: {reason}",
            spread_value=spread,
            z_score=z_score,
        )

    def _compute_levels(
        self, spread_mean: float, spread_stdev: float, z_score: float
    ) -> Tuple[float, float]:
        """
        Compute stop and target spread values from the current distribution.

        Stop:   mean ± stop_sigma × stdev  (in the direction that hurts us)
        Target: mean (z=0)

        Args:
            spread_mean:  Rolling mean of spread.
            spread_stdev: Rolling stdev of spread.
            z_score:      Current z-score (direction indicator).

        Returns:
            (stop_spread, target_spread)
        """
        target_spread = spread_mean  # mean reversion target

        if z_score > 0:
            # We're selling the spread → stop is if spread widens further
            stop_spread = spread_mean + self.params.stop_sigma * spread_stdev
        else:
            # We're buying the spread → stop is if spread narrows further
            stop_spread = spread_mean - self.params.stop_sigma * spread_stdev

        return stop_spread, target_spread

    def _is_time_to_trade(self, timestamp: datetime) -> bool:
        """Check GMT hour filter."""
        if not self.params.use_time_filter:
            return True
        hour = timestamp.hour
        return self.params.trading_start_hour <= hour < self.params.trading_end_hour

    def _warmup_signal(self) -> CrackSpreadSignal:
        """Return a no-signal during warmup period."""
        crude_n = len(self._crude_buffer)
        gas_n = len(self._gasoline_buffer)
        return CrackSpreadSignal(
            action=None,
            crude_quantity=Decimal("0"),
            gasoline_quantity=Decimal("0"),
            confidence=0.0,
            reason=(
                f"Warming up: crude={crude_n}/{self.params.lookback} "
                f"gasoline={gas_n}/{self.params.lookback} candles"
            ),
        )


def create_crack_spread_strategy(**kwargs) -> CrackSpreadStrategy:
    """
    Factory function for CrackSpreadStrategy with parameter overrides.

    Args:
        **kwargs: Any CrackSpreadParams field names and values.
            lookback (int):           Rolling window for mean/stdev. Default: 20.
            entry_sigma (float):      Entry threshold in σ. Default: 1.5.
            exit_sigma (float):       Exit threshold in σ. Default: 0.3.
            stop_sigma (float):       Stop threshold in σ. Default: 2.5.
            q2_sigma_addon (float):   Extra σ in Q2 (Apr-Jun). Default: 0.3.
            q3_sigma_addon (float):   Extra σ in Q3 (Jul-Sep). Default: 0.5.
            crude_lots (Decimal):     Crude position size. Default: Decimal("1.0").
            crude_symbol (str):       Crude DB symbol name. Default: "CrudeOIL".
            gasoline_symbol (str):    Gasoline DB symbol name. Default: "GASOLINE".
            max_tick_age_seconds (int): Staleness gate. Default: 3600.
            enable_seasonality (bool): Apply seasonal sigma overlay. Default: True.

    Returns:
        CrackSpreadStrategy instance.

    Example:
        >>> s = create_crack_spread_strategy(lookback=30, entry_sigma=2.0)
        >>> signal = s.process_tick(crude_tick)
    """
    # Convert crude_lots to Decimal if passed as float/int
    if "crude_lots" in kwargs and not isinstance(kwargs["crude_lots"], Decimal):
        kwargs["crude_lots"] = Decimal(str(kwargs["crude_lots"]))

    params = CrackSpreadParams(**kwargs)
    return CrackSpreadStrategy(params=params)
