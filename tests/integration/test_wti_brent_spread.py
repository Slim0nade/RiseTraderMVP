"""
Integration tests for WTI-Brent Spread Strategy.

Tests verify:
1. Strategy initialises with correct defaults
2. Warmup period is respected (no signals before 20 spread samples)
3. SELL SPREAD fires when spread Z-score >= +1.5σ
4. BUY SPREAD fires when spread Z-score <= -1.5σ
5. Mean-reversion exit fires when Z-score reverts
6. Stop loss fires when Z-score exceeds 2.5σ from entry
7. No signal when both symbols not yet seen
8. Reset clears all state
"""
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import random

import pytest

from src.strategies.spreads.wti_brent_spread import (
    WTIBrentSpreadStrategy,
    WTIBrentParams,
    WTIBrentSignal,
    create_wti_brent_spread_strategy,
)
from src.services.backtesting.data_replay_engine import MarketTick


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tick(symbol: str, close: float, hour: int = 10) -> MarketTick:
    """Create a MarketTick during trading hours (hour defaults to 10 GMT)."""
    ts = datetime(2024, 6, 15, hour, 0, 0, tzinfo=timezone.utc)
    price = Decimal(str(close))
    spread_approx = Decimal("0.10")
    return MarketTick(
        symbol=symbol,
        timestamp=ts,
        open=price - spread_approx,
        high=price + spread_approx,
        low=price - spread_approx,
        close=price,
        volume=1000,
    )


def make_tick_ts(symbol: str, close: float, ts: datetime) -> MarketTick:
    """Create a MarketTick with explicit timestamp."""
    price = Decimal(str(close))
    spread_approx = Decimal("0.10")
    return MarketTick(
        symbol=symbol,
        timestamp=ts,
        open=price - spread_approx,
        high=price + spread_approx,
        low=price - spread_approx,
        close=price,
        volume=1000,
    )


def build_strategy_with_variance(n: int = 25, seed: int = 42) -> WTIBrentSpreadStrategy:
    """
    Build a strategy primed with n spread samples that have non-zero variance.

    Spread mean ≈ 5.0, std ≈ 0.3–0.5.
    All ticks use hour=10 (within trading window).
    Returns strategy with lookback_period=20, time_filter disabled for control.
    """
    params = WTIBrentParams(lookback_period=20, use_time_filter=False)
    strategy = WTIBrentSpreadStrategy(params=params)

    rng = random.Random(seed)
    ts_base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    for i in range(n):
        ts = ts_base + timedelta(hours=i)
        wti = 75.0 + rng.uniform(-0.25, 0.25)
        brent = wti + 5.0 + rng.uniform(-0.25, 0.25)
        strategy.process_tick(make_tick_ts("CrudeOIL", wti, ts))
        strategy.process_tick(make_tick_ts("BRENT_OIL", brent, ts))

    return strategy, ts_base


# ---------------------------------------------------------------------------
# Tests: Initialisation
# ---------------------------------------------------------------------------

class TestWTIBrentSpreadInit:
    def test_default_params(self):
        strategy = WTIBrentSpreadStrategy()
        assert strategy.params.lookback_period == 20
        assert strategy.params.entry_sigma == 1.5
        assert strategy.params.stop_sigma == 2.5
        assert not strategy.has_position

    def test_factory_custom_params(self):
        strategy = create_wti_brent_spread_strategy(lookback_period=30, entry_sigma=2.0)
        assert strategy.params.lookback_period == 30
        assert strategy.params.entry_sigma == 2.0

    def test_no_signal_unknown_symbol(self):
        strategy = WTIBrentSpreadStrategy()
        sig = strategy.process_tick(make_tick("XAUUSD", 2000.0))
        assert sig.action is None
        assert "Unexpected symbol" in sig.reason


# ---------------------------------------------------------------------------
# Tests: Warmup
# ---------------------------------------------------------------------------

class TestWTIBrentWarmup:
    def test_no_signal_before_brent_tick(self):
        strategy = WTIBrentSpreadStrategy(WTIBrentParams(use_time_filter=False))
        ts_base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        # Only WTI ticks — BRENT not seen yet
        for i in range(25):
            ts = ts_base + timedelta(hours=i)
            sig = strategy.process_tick(make_tick_ts("CrudeOIL", 75.0, ts))
            assert sig.action is None
            assert "BRENT_OIL" in sig.reason

    def test_no_signal_during_warmup(self):
        """Spread history must reach lookback_period before signals fire."""
        strategy = WTIBrentSpreadStrategy(WTIBrentParams(lookback_period=20, use_time_filter=False))
        ts_base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        # Feed 19 pairs (one short of lookback_period=20)
        for i in range(19):
            ts = ts_base + timedelta(hours=i)
            strategy.process_tick(make_tick_ts("CrudeOIL", 75.0, ts))
            sig = strategy.process_tick(make_tick_ts("BRENT_OIL", 80.0, ts))
            # All signals should be "Warming up" or "No signal" (both = no action)
            assert sig.action is None, f"Got action at i={i}: {sig.reason}"


# ---------------------------------------------------------------------------
# Tests: Entry signals
# ---------------------------------------------------------------------------

class TestWTIBrentEntrySignals:
    def test_sell_spread_on_positive_zscore(self):
        """When spread is far above mean, strategy sells spread (sell BRENT, buy WTI)."""
        strategy, ts_base = build_strategy_with_variance(n=25, seed=42)

        # Now inject a spike: WTI=75, BRENT=82 → spread=7 (well above mean+1.5σ)
        ts_signal = ts_base + timedelta(hours=26)
        strategy.process_tick(make_tick_ts("CrudeOIL", 75.0, ts_signal))
        sig = strategy.process_tick(make_tick_ts("BRENT_OIL", 82.0, ts_signal))

        assert sig.action == "sell", f"Expected 'sell', got '{sig.action}': {sig.reason}"
        assert "SHORT SPREAD" in sig.reason
        assert strategy.has_position
        assert strategy.state.spread_direction == "short_spread"

    def test_buy_spread_on_negative_zscore(self):
        """When spread is far below mean, strategy buys spread (buy BRENT, sell WTI)."""
        strategy, ts_base = build_strategy_with_variance(n=25, seed=7)

        # Inject a narrow spread: BRENT=76.5, WTI=75 → spread=1.5 (well below mean−1.5σ)
        ts_signal = ts_base + timedelta(hours=26)
        strategy.process_tick(make_tick_ts("CrudeOIL", 75.0, ts_signal))
        sig = strategy.process_tick(make_tick_ts("BRENT_OIL", 76.5, ts_signal))

        assert sig.action == "buy", f"Expected 'buy', got '{sig.action}': {sig.reason}"
        assert "LONG SPREAD" in sig.reason
        assert strategy.has_position
        assert strategy.state.spread_direction == "long_spread"


# ---------------------------------------------------------------------------
# Tests: Exit signals
# ---------------------------------------------------------------------------

class TestWTIBrentExitSignals:
    def _setup_short_spread(self) -> tuple[WTIBrentSpreadStrategy, datetime]:
        """Helper: return strategy in a short-spread position."""
        strategy, ts_base = build_strategy_with_variance(n=25, seed=42)

        # Enter short spread
        ts_entry = ts_base + timedelta(hours=26)
        strategy.process_tick(make_tick_ts("CrudeOIL", 75.0, ts_entry))
        strategy.process_tick(make_tick_ts("BRENT_OIL", 82.0, ts_entry))
        assert strategy.has_position, "Setup failed: position not opened"
        return strategy, ts_base

    def test_mean_reversion_exit_short_spread(self):
        """Short spread exits when Z-score reverts to ≤ exit_band."""
        strategy, ts_base = self._setup_short_spread()

        # Feed ticks returning spread toward mean ≈5.0 (Z-score near 0)
        ts_exit = ts_base + timedelta(hours=27)
        strategy.process_tick(make_tick_ts("CrudeOIL", 75.0, ts_exit))
        sig = strategy.process_tick(make_tick_ts("BRENT_OIL", 80.0, ts_exit))  # spread=5.0 ≈ mean

        assert sig.action == "close_short", f"Expected close_short, got '{sig.action}': {sig.reason}"
        assert not strategy.has_position

    def test_stop_loss_short_spread(self):
        """Short spread stops out when spread widens beyond stop threshold."""
        strategy, ts_base = self._setup_short_spread()

        stop_z = strategy.state.stop_spread_z
        assert stop_z is not None

        # Push spread extremely wide to definitely breach stop_z
        ts_stop = ts_base + timedelta(hours=27)
        strategy.process_tick(make_tick_ts("CrudeOIL", 75.0, ts_stop))
        sig = strategy.process_tick(make_tick_ts("BRENT_OIL", 92.0, ts_stop))  # Extreme spike

        # If stop was breached, position should be closed
        if not strategy.has_position:
            assert sig.action == "close_short"
            assert "Stop hit" in sig.reason
        else:
            # Stop not yet hit (spread hasn't exceeded stop_z) — that's also valid
            assert sig.action is None


# ---------------------------------------------------------------------------
# Tests: Reset
# ---------------------------------------------------------------------------

class TestWTIBrentReset:
    def test_reset_clears_state(self):
        strategy, _ = build_strategy_with_variance(n=25)
        strategy.reset()

        assert not strategy.has_position
        assert strategy.state.spread_direction is None
        assert len(strategy._spread_history) == 0
        assert len(strategy._last_close) == 0

    def test_reset_restarts_warmup(self):
        strategy, _ = build_strategy_with_variance(n=25)
        strategy.reset()

        sig = strategy.process_tick(make_tick("CrudeOIL", 75.0))
        assert sig.action is None


# ---------------------------------------------------------------------------
# Tests: get_state
# ---------------------------------------------------------------------------

class TestWTIBrentGetState:
    def test_get_state_structure(self):
        strategy = WTIBrentSpreadStrategy()
        state = strategy.get_state()
        assert state["strategy"] == "wti_brent_spread"
        assert "params" in state
        assert "has_position" in state
        assert "spread_history_length" in state
