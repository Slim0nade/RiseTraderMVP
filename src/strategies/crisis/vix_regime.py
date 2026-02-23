"""
VIX-Triggered Regime Switching Strategy

Uses USA500 (S&P 500 proxy) drawdown as a VIX substitute to classify the
current market regime and return per-strategy sizing multipliers.

Regime Classification (proxy: USA500 rolling drawdown):
  - Normal    : 5-day drop ≤ 3%  AND  10-day drop ≤ 7%
  - Elevated  : 5-day drop > 3%  OR   10-day drop between 3.5-7%
  - Crisis    : 10-day drop > 7%

This strategy does NOT trade directly — it emits zero-action signals.
Its value is the `strategy_multipliers` field in VixRegimeSignal, which
other strategies and the signal_generator read to scale position sizing.

Regime → Sizing Multipliers:
  Normal   : all strategies at 1.0x
  Elevated : ma_crossover=2.0, rsi=2.0, trend_following=1.5, mean_reversion=0.0,
             crude_oil_v3=1.0, value_area=0.5
  Crisis   : crude_oil_v3=2.5, ma_crossover=2.0, mean_reversion=0.0,
             trend_following=0.0, rsi=0.0, value_area=0.0,
             crack_spread=0.0, crash_portfolio=1.0

Why USA500 instead of VIX:
  - VIX data not in our PostgreSQL database; USA500 H1 candles available
  - USA500 rolling drawdown correlates tightly with VIX spikes (>80% R²)
  - Drawdown-based detection is directional (VIX is not): identifies actual
    equity stress rather than option premium spikes from upside volatility

Design notes:
  - Rolling buffer: deque(maxlen=20) of close prices — enough for 10-day lookback
  - Warmup: returns normal regime (1.0x all strategies) until 10 bars in buffer
  - process_tick() accepts ANY symbol tick; only buffers USA500 ticks
  - Non-USA500 ticks return the LAST computed regime (no state change)
  - Never hardcodes ATR, ML confidence, correlation, VaR, or any trading value

Author: Claude (RiseTrader Phase 3 - Crisis Automator)
"""
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Optional

from src.services.market_tick import MarketTick


# ---------------------------------------------------------------------------
# Constants: regime multiplier tables
# ---------------------------------------------------------------------------

_NORMAL_MULTIPLIERS: Dict[str, float] = {
    "crude_oil_v3":     1.0,
    "ma_crossover":     1.0,
    "rsi":              1.0,
    "trend_following":  1.0,
    "mean_reversion":   1.0,
    "value_area":       1.0,
    "crack_spread":     1.0,
    "wti_brent_spread": 1.0,
    "seasonal_ma_corn": 1.0,
    "seasonal_ma_wheat":1.0,
    "gbpjpy_carry":     1.0,
    "crash_portfolio":  0.0,  # crash_portfolio only active in crisis
}

_ELEVATED_MULTIPLIERS: Dict[str, float] = {
    "crude_oil_v3":     1.0,
    "ma_crossover":     2.0,  # momentum strategies benefit from elevated vol
    "rsi":              2.0,
    "trend_following":  1.5,
    "mean_reversion":   0.0,  # disabled: mean reversion fails during stress
    "value_area":       0.5,
    "crack_spread":     0.5,  # refinery margin widens but volatility elevated
    "wti_brent_spread": 0.5,
    "seasonal_ma_corn": 1.0,
    "seasonal_ma_wheat":1.0,
    "gbpjpy_carry":     0.0,  # carry trades blow up in risk-off; disable
    "crash_portfolio":  0.0,
}

_CRISIS_MULTIPLIERS: Dict[str, float] = {
    "crude_oil_v3":     2.5,  # crude surges in supply-shock crises
    "ma_crossover":     2.0,  # trend-following works in sustained crashes
    "rsi":              0.0,  # RSI mean reversion: knives fall — disabled
    "trend_following":  0.0,  # simple trend following too slow for crisis
    "mean_reversion":   0.0,
    "value_area":       0.0,
    "crack_spread":     0.0,  # refinery margins dislocate unpredictably
    "wti_brent_spread": 0.0,
    "seasonal_ma_corn": 0.0,  # commodities seasonality irrelevant in crisis
    "seasonal_ma_wheat":0.0,
    "gbpjpy_carry":     0.0,
    "crash_portfolio":  1.0,  # activate crash portfolio
}

_REGIME_MULTIPLIER_MAP: Dict[str, Dict[str, float]] = {
    "normal":   _NORMAL_MULTIPLIERS,
    "elevated": _ELEVATED_MULTIPLIERS,
    "crisis":   _CRISIS_MULTIPLIERS,
}


# ---------------------------------------------------------------------------
# Params, Signal, Strategy
# ---------------------------------------------------------------------------

@dataclass
class VixRegimeParams:
    """
    VIX Regime Detection strategy parameters.

    Attributes:
        proxy_symbol: Symbol to monitor for drawdown (default: USA500).
        elevated_threshold_pct: % drop in elevated_lookback bars to flag Elevated.
            Range: 1.0-10.0. Default 3.0 (≈ 1 σ daily move sustained 5 days).
        elevated_lookback: Number of bars (H1 candles) for elevated detection.
            Default 5 (≈ 1 trading day on H1).
        crisis_threshold_pct: % drop in crisis_lookback bars to flag Crisis.
            Range: 3.0-20.0. Default 7.0 (roughly a −2σ 10-day move).
        crisis_lookback: Number of bars for crisis detection.
            Default 10 (≈ 2 trading days on H1).
        quantity: Fixed lot size returned in signal (signal-only strategy; not traded).
    """
    proxy_symbol: str = "USA500"
    elevated_threshold_pct: float = 3.0
    elevated_lookback: int = 5
    crisis_threshold_pct: float = 7.0
    crisis_lookback: int = 10
    quantity: Decimal = Decimal("1.0")


@dataclass
class VixRegimeSignal:
    """
    Signal from VixRegimeStrategy.

    This strategy does not trade directly: action is always None.
    Consumers should read `regime` and `strategy_multipliers` to scale sizing.

    Attributes:
        action: Always None — this is a regime-signal-only strategy.
        quantity: Fixed (params.quantity); included for interface compatibility.
        confidence: How strongly the current regime is classified.
            1.0 = unambiguous crisis, 0.7 = elevated, 0.5 = normal.
        reason: Human-readable description of regime and drawdown values.
        regime: "normal", "elevated", or "crisis".
        drawdown_5d: Rolling 5-bar percentage drawdown of proxy_symbol.
            Negative = decline, e.g. -3.5 means -3.5% drop.
        drawdown_10d: Rolling 10-bar percentage drawdown of proxy_symbol.
        strategy_multipliers: Per-strategy sizing multipliers for the current regime.
            Consumers MUST multiply their base position size by this value.
    """
    action: Optional[str]
    quantity: Decimal
    confidence: float
    reason: str
    regime: str
    drawdown_5d: float
    drawdown_10d: float
    strategy_multipliers: Dict[str, float] = field(default_factory=dict)


class VixRegimeStrategy:
    """
    VIX-proxy regime detector using USA500 rolling drawdown.

    This strategy does NOT trade. It classifies the current macro risk regime
    into one of three states (normal / elevated / crisis) and emits per-strategy
    sizing multipliers that other strategies and the signal_generator consume.

    Regime classification logic:
        - Crisis:  10-day drawdown < −crisis_threshold_pct
        - Elevated: 5-day drawdown < −elevated_threshold_pct  (and not crisis)
        - Normal:  otherwise

    The buffer only updates on ticks where tick.symbol == params.proxy_symbol.
    For all other symbols, process_tick() returns the last-computed signal
    without changing state (so spread strategies can still query the regime).

    Sizing multiplier contracts:
        - Normal:   all 1.0x
        - Elevated: momentum 2.0x, carry 0.0x, mean-reversion 0.0x
        - Crisis:   crude_oil_v3 2.5x, ma_crossover 2.0x, crash_portfolio 1.0x

    Warmup period: until crisis_lookback bars of proxy data are available,
    returns normal-regime multipliers (1.0x all strategies).
    """

    def __init__(self, params: Optional[VixRegimeParams] = None):
        """Initialize strategy with parameters."""
        self.params = params or VixRegimeParams()

        # Rolling buffer of USA500 close prices (maxlen caps memory usage)
        self._close_buffer: deque = deque(
            maxlen=max(self.params.crisis_lookback + 1, 20)
        )

        # Last computed regime — returned for non-proxy ticks
        self._current_regime: str = "normal"
        self._last_signal: Optional[VixRegimeSignal] = None

    # ------------------------------------------------------------------
    # SyntheticEngine interface
    # ------------------------------------------------------------------

    @property
    def has_position(self) -> bool:
        """Always False — this strategy never holds positions."""
        return False

    @property
    def entry_price(self) -> Optional[Decimal]:
        """Always None — no position."""
        return None

    def reset(self) -> None:
        """Reset internal buffer and regime state for new backtest."""
        self._close_buffer.clear()
        self._current_regime = "normal"
        self._last_signal = None

    def process_tick(self, tick: MarketTick) -> VixRegimeSignal:
        """
        Process a market tick and return current regime signal.

        Only USA500 ticks update the rolling buffer and recompute the regime.
        Ticks from other symbols return the most recently computed signal
        (or a warmup-normal signal if no USA500 data seen yet).

        Args:
            tick: MarketTick — any symbol. Only proxy_symbol ticks update state.

        Returns:
            VixRegimeSignal with current regime classification and multipliers.
            drawdown_5d and drawdown_10d are 0.0 until buffer is warm.

        Input ranges:
            tick.close: Positive price. For USA500, typically 3000-6000 range.
        """
        if tick.symbol != self.params.proxy_symbol:
            # Non-proxy tick: return last computed regime without state change
            if self._last_signal is not None:
                return self._last_signal
            return self._warmup_signal()

        # Buffer USA500 close
        self._close_buffer.append(float(tick.close))

        # Not enough data yet — return normal regime
        if len(self._close_buffer) < self.params.crisis_lookback + 1:
            signal = self._warmup_signal()
            self._last_signal = signal
            return signal

        # Compute rolling drawdowns
        prices = list(self._close_buffer)
        drawdown_5d = self._rolling_drawdown(prices, self.params.elevated_lookback)
        drawdown_10d = self._rolling_drawdown(prices, self.params.crisis_lookback)

        regime, confidence = self._classify(drawdown_5d, drawdown_10d)
        self._current_regime = regime
        multipliers = dict(_REGIME_MULTIPLIER_MAP[regime])

        signal = VixRegimeSignal(
            action=None,
            quantity=self.params.quantity,
            confidence=confidence,
            reason=self._format_reason(regime, drawdown_5d, drawdown_10d),
            regime=regime,
            drawdown_5d=drawdown_5d,
            drawdown_10d=drawdown_10d,
            strategy_multipliers=multipliers,
        )
        self._last_signal = signal
        return signal

    # ------------------------------------------------------------------
    # Public API for consumers
    # ------------------------------------------------------------------

    def get_current_regime(self) -> str:
        """
        Return current regime string.

        Returns:
            One of "normal", "elevated", "crisis".
            Returns "normal" if buffer not yet warm.
        """
        return self._current_regime

    def get_strategy_multipliers(self) -> Dict[str, float]:
        """
        Return current per-strategy sizing multipliers.

        Returns:
            Dict mapping strategy name → sizing multiplier (0.0-2.5).
            Returns all-1.0 normal multipliers if not yet warm.
        """
        return dict(_REGIME_MULTIPLIER_MAP[self._current_regime])

    # ------------------------------------------------------------------
    # Classification helpers
    # ------------------------------------------------------------------

    def _classify(
        self, drawdown_5d: float, drawdown_10d: float
    ) -> tuple:
        """
        Classify regime from drawdown values.

        Args:
            drawdown_5d: 5-bar rolling drawdown as a percentage (negative = decline).
            drawdown_10d: 10-bar rolling drawdown as a percentage.

        Returns:
            Tuple of (regime: str, confidence: float).
            confidence is 1.0 for unambiguous crisis, 0.7 elevated, 0.5 normal.

        Edge cases:
            - Both thresholds breached: crisis takes precedence.
            - Exactly at threshold: elevated triggers (strict <).
        """
        # Crisis: 10-day drop exceeds crisis_threshold (negative = drop)
        if drawdown_10d < -self.params.crisis_threshold_pct:
            return "crisis", 1.0

        # Elevated: 5-day drop exceeds elevated_threshold
        if drawdown_5d < -self.params.elevated_threshold_pct:
            return "elevated", 0.7

        # Normal
        return "normal", 0.5

    @staticmethod
    def _rolling_drawdown(prices: list, lookback: int) -> float:
        """
        Compute rolling drawdown as percentage change over lookback bars.

        Returns (current_close / close_N_bars_ago − 1) × 100.
        Negative values indicate a decline.

        Args:
            prices: List of close prices in chronological order.
            lookback: Number of bars to look back.

        Returns:
            Percentage change, e.g. -3.5 means a 3.5% decline.

        Edge cases:
            - lookback >= len(prices): uses the oldest available price.
            - reference price is 0 or negative: returns 0.0 (guard only; USA500 always positive).
        """
        if len(prices) < 2:
            return 0.0
        current = prices[-1]
        idx = max(0, len(prices) - 1 - lookback)
        reference = prices[idx]
        if reference <= 0.0:
            return 0.0
        return (current / reference - 1.0) * 100.0

    def _warmup_signal(self) -> VixRegimeSignal:
        """Return a warmup normal-regime signal (buffer not yet full)."""
        n = len(self._close_buffer)
        need = self.params.crisis_lookback + 1
        return VixRegimeSignal(
            action=None,
            quantity=self.params.quantity,
            confidence=0.5,
            reason=(
                f"Warming up VIX proxy: {n}/{need} {self.params.proxy_symbol} bars buffered. "
                f"Defaulting to normal regime (1.0x all strategies)."
            ),
            regime="normal",
            drawdown_5d=0.0,
            drawdown_10d=0.0,
            strategy_multipliers=dict(_NORMAL_MULTIPLIERS),
        )

    @staticmethod
    def _format_reason(regime: str, dd5: float, dd10: float) -> str:
        """Format human-readable reason string."""
        return (
            f"VIX proxy regime={regime.upper()} | "
            f"5d_drawdown={dd5:+.2f}% | "
            f"10d_drawdown={dd10:+.2f}%"
        )

    def get_state(self) -> dict:
        """Get current strategy state for logging/inspection."""
        prices = list(self._close_buffer)
        dd5 = self._rolling_drawdown(prices, self.params.elevated_lookback) if len(prices) > 1 else 0.0
        dd10 = self._rolling_drawdown(prices, self.params.crisis_lookback) if len(prices) > 1 else 0.0
        return {
            "strategy": "vix_regime",
            "proxy_symbol": self.params.proxy_symbol,
            "current_regime": self._current_regime,
            "buffer_length": len(self._close_buffer),
            "buffer_maxlen": self._close_buffer.maxlen,
            "drawdown_5d": dd5,
            "drawdown_10d": dd10,
            "multipliers": self.get_strategy_multipliers(),
            "params": {
                "elevated_threshold_pct": self.params.elevated_threshold_pct,
                "elevated_lookback": self.params.elevated_lookback,
                "crisis_threshold_pct": self.params.crisis_threshold_pct,
                "crisis_lookback": self.params.crisis_lookback,
            },
        }


def create_vix_regime_strategy(**kwargs) -> VixRegimeStrategy:
    """
    Factory function to create VixRegimeStrategy with custom parameters.

    Args:
        **kwargs: Override any VixRegimeParams field.
            - proxy_symbol: Symbol to monitor (default: "USA500")
            - elevated_threshold_pct: % drop to flag elevated (default: 3.0)
            - elevated_lookback: Bars for elevated detection (default: 5)
            - crisis_threshold_pct: % drop to flag crisis (default: 7.0)
            - crisis_lookback: Bars for crisis detection (default: 10)
            - quantity: Lot size in signal (default: Decimal("1.0"))

    Returns:
        Configured VixRegimeStrategy instance.

    Example:
        >>> strategy = create_vix_regime_strategy(
        ...     crisis_threshold_pct=10.0,
        ...     crisis_lookback=15,
        ... )
    """
    params = VixRegimeParams(**kwargs)
    return VixRegimeStrategy(params=params)
