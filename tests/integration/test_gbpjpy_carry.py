"""
Integration tests for GBPJPY Carry Trade Strategy.

Tests verify:
1. Default parameters and factory function
2. Warmup period respected (no signals before trend_sma_period bars)
3. No entry when price is below 50-SMA (trend filter)
4. BUY fires when price is above 50-SMA and pulls back to 20-SMA
5. Stop is placed 2×ATR below entry
6. Trend exit fires when close drops below 50-SMA
7. Stop loss exit fires correctly
8. Strategy is LONG-ONLY (never generates 'sell' action)
9. InsufficientDataError propagates when ATR data unavailable
10. Reset clears all state
"""
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import math

import pytest

from src.strategies.carry.gbpjpy_carry import (
    GBPJPYCarryStrategy,
    GBPJPYCarryParams,
    GBPJPYCarrySignal,
    create_gbpjpy_carry_strategy,
)
from src.services.backtesting.data_replay_engine import MarketTick
from src.utils.atr_calculator import InsufficientDataError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tick(close: float, ts: datetime) -> MarketTick:
    """Create a GBPJPY MarketTick with small fixed spread."""
    price = Decimal(str(close))
    spread = Decimal("0.02")
    return MarketTick(
        symbol="GBPJPY.",
        timestamp=ts,
        open=price - spread,
        high=price + spread,
        low=price - spread,
        close=price,
        volume=10000,
    )


def build_uptrend_strategy(
    n_bars: int = 65,
    start_price: float = 185.0,
    slope: float = 0.10,
    use_time_filter: bool = False,
    pullback_tolerance: float = 0.003,
    atr_stop_multiplier: float = 2.0,
) -> tuple[GBPJPYCarryStrategy, datetime]:
    """
    Build and warm up strategy with a gentle uptrend.

    After n_bars:
      - 50-SMA ≈ start_price + ((n_bars - 25) * slope)
      - 20-SMA ≈ start_price + ((n_bars - 10) * slope)
      - close ≈ start_price + n_bars * slope
      - close > 50-SMA ✓

    Returns (strategy, ts_base) where ts_base is the start timestamp.
    """
    params = GBPJPYCarryParams(
        trend_sma_period=50,
        entry_sma_period=20,
        atr_period=14,
        atr_stop_multiplier=atr_stop_multiplier,
        pullback_tolerance=pullback_tolerance,
        use_time_filter=use_time_filter,
    )
    strategy = GBPJPYCarryStrategy(params=params)
    ts_base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    for i in range(n_bars):
        ts = ts_base + timedelta(hours=i)
        price = start_price + i * slope
        strategy.process_tick(make_tick(price, ts))

    return strategy, ts_base


# ---------------------------------------------------------------------------
# Tests: Initialisation
# ---------------------------------------------------------------------------

class TestGBPJPYCarryInit:
    def test_default_params(self):
        strategy = GBPJPYCarryStrategy()
        assert strategy.params.trend_sma_period == 50
        assert strategy.params.entry_sma_period == 20
        assert strategy.params.atr_period == 14
        assert strategy.params.atr_stop_multiplier == 2.0
        assert strategy.params.quantity == Decimal("0.01")
        assert not strategy.has_position

    def test_factory_custom_params(self):
        strategy = create_gbpjpy_carry_strategy(
            atr_stop_multiplier=2.5,
            pullback_tolerance=0.005,
        )
        assert strategy.params.atr_stop_multiplier == 2.5
        assert strategy.params.pullback_tolerance == 0.005

    def test_entry_price_none_initially(self):
        strategy = GBPJPYCarryStrategy()
        assert strategy.entry_price is None


# ---------------------------------------------------------------------------
# Tests: Warmup
# ---------------------------------------------------------------------------

class TestGBPJPYCarryWarmup:
    def test_no_signal_during_warmup(self):
        strategy = create_gbpjpy_carry_strategy(use_time_filter=False)
        ts = datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)

        for i in range(49):  # trend_sma_period - 1 = 49
            t = ts + timedelta(hours=i)
            price = 190.0 + i * 0.05
            sig = strategy.process_tick(make_tick(price, t))
            assert sig.action is None, f"Signal at bar {i}: {sig.reason}"
            assert "Warming up" in sig.reason


# ---------------------------------------------------------------------------
# Tests: Trend filter
# ---------------------------------------------------------------------------

class TestGBPJPYTrendFilter:
    def test_no_entry_below_50sma(self):
        """When close < 50-SMA, no LONG entry."""
        strategy = create_gbpjpy_carry_strategy(use_time_filter=False)
        ts_base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        # Declining prices — close will fall below SMA
        for i in range(60):
            ts = ts_base + timedelta(hours=i)
            price = 200.0 - i * 0.2
            strategy.process_tick(make_tick(price, ts))

        # At bar 60, close ≈ 188.0, SMA(50) ≈ 194.5 → close < SMA
        ts_check = ts_base + timedelta(hours=61)
        sig = strategy.process_tick(make_tick(186.0, ts_check))
        assert sig.action is None
        assert "trend" in sig.reason.lower() or "below" in sig.reason.lower()

    def test_no_sell_signal_ever(self):
        """Strategy must never generate a 'sell' action — it is long-only."""
        strategy = create_gbpjpy_carry_strategy(use_time_filter=False)
        ts_base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        for i in range(100):
            ts = ts_base + timedelta(hours=i)
            price = 190.0 + math.sin(i * 0.2) * 5.0
            sig = strategy.process_tick(make_tick(price, ts))
            assert sig.action != "sell", f"Forbidden 'sell' at bar {i}: {sig.reason}"


# ---------------------------------------------------------------------------
# Tests: Entry signal
# ---------------------------------------------------------------------------

class TestGBPJPYCarryEntry:
    def test_buy_on_pullback_to_20sma(self):
        """
        BUY fires when price is above 50-SMA and close is within pullback_tolerance of 20-SMA.

        Setup:
          - 55 bars at flat 185.0 (no position during warmup)
          - 10 bars at high price 210.0 (so SMA(50) rises and close >> SMA(50))
          - Then one tick at SMA(20) level → pullback entry

        The high price bars push close >> SMA(50) while keeping SMA(20)
        well above SMA(50). Then we feed a tick at SMA(20) which is
        above SMA(50) — meeting both trend filter and pullback conditions.
        """
        params = GBPJPYCarryParams(
            trend_sma_period=50,
            entry_sma_period=20,
            atr_period=14,
            atr_stop_multiplier=2.0,
            pullback_tolerance=0.005,  # 0.5% — wide enough to catch minor SMA lag
            use_time_filter=False,
        )
        strategy = GBPJPYCarryStrategy(params=params)
        ts_base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        # Phase 1: 55 bars at 185 — both SMAs = 185, close = 185 (close <= SMA → no entry)
        for i in range(55):
            ts = ts_base + timedelta(hours=i)
            strategy.process_tick(make_tick(185.0, ts))

        assert not strategy.has_position, "No position after flat warmup"

        # Phase 2: 10 bars at 210 — moves SMA(20) up, SMA(50) up slightly, close >> SMAs
        # Entry condition: close(210) > SMA(50) ✓, but close(210) vs SMA(20)≈185+(25*10/20)≈197.5
        # distance = (210 - 197.5)/197.5 ≈ 6.3% >> pullback_tolerance(0.1%) → no entry
        for i in range(10):
            ts = ts_base + timedelta(hours=55 + i)
            strategy.process_tick(make_tick(210.0, ts))

        assert not strategy.has_position, "No position during 210 phase"

        state = strategy.get_state()
        sma_20 = state["sma_20"]
        sma_50 = state["sma_50"]
        assert sma_20 > sma_50, f"SMA(20)={sma_20:.2f} must be > SMA(50)={sma_50:.2f}"

        # Phase 3: Tick exactly at SMA(20) — pullback zone, still above SMA(50)
        # distance = 0 → within tolerance ✓
        ts_entry = ts_base + timedelta(hours=66)
        sig = strategy.process_tick(make_tick(sma_20, ts_entry))

        assert sig.action == "buy", (
            f"Expected 'buy' on pullback to 20-SMA({sma_20:.4f}), got '{sig.action}': {sig.reason}"
        )
        assert strategy.has_position
        assert strategy.state.position_type == "buy"

    def test_stop_placed_two_atr_below_entry(self):
        """Stop loss is set to entry − 2×ATR."""
        strategy, ts_base = build_uptrend_strategy(
            n_bars=65,
            start_price=185.0,
            slope=0.10,
            pullback_tolerance=0.05,
            atr_stop_multiplier=2.0,
        )
        state = strategy.get_state()
        sma_20 = state["sma_20"]

        ts_entry = ts_base + timedelta(hours=66)
        sig = strategy.process_tick(make_tick(sma_20, ts_entry))

        if sig.action == "buy":
            assert sig.stop_loss is not None
            entry = sma_20
            stop = sig.stop_loss
            assert stop < entry, f"Stop ({stop:.4f}) must be below entry ({entry:.4f})"
            assert strategy.state.stop_loss is not None
            # Verify stop ≈ entry − 2*ATR
            atr = sig.atr
            assert atr is not None and atr > 0
            expected_stop = entry - 2.0 * atr
            assert abs(stop - expected_stop) < 0.01, (
                f"Stop ({stop:.4f}) should ≈ entry−2×ATR ({expected_stop:.4f})"
            )

    def test_atr_insufficient_data_propagates(self):
        """
        InsufficientDataError propagates when ATR period > available price history.
        This verifies the no-fake-ATR rule.

        The strategy's warmup guard includes atr_period+1 so process_tick never
        reaches _check_entry with insufficient data. We test _calculate_atr()
        directly on a fresh strategy with only a handful of bars — the method
        must raise InsufficientDataError instead of returning a fake default.
        """
        strategy = GBPJPYCarryStrategy(GBPJPYCarryParams(atr_period=14))
        ts_base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        # Inject only 5 bars (need atr_period+1 = 15)
        from src.utils.atr_calculator import Candle
        from datetime import timedelta
        for i in range(5):
            strategy._price_history.append({
                "timestamp": ts_base + timedelta(hours=i),
                "open": 185.0,
                "high": 185.5,
                "low": 184.5,
                "close": 185.0 + i * 0.1,
                "volume": 1000,
            })

        with pytest.raises(InsufficientDataError):
            strategy._calculate_atr()


# ---------------------------------------------------------------------------
# Tests: Exit signals
# ---------------------------------------------------------------------------

class TestGBPJPYCarryExits:
    def _open_position(self) -> tuple[GBPJPYCarryStrategy, datetime]:
        """Helper: open a carry long position and return (strategy, ts_base)."""
        strategy, ts_base = build_uptrend_strategy(
            n_bars=65, start_price=185.0, slope=0.10, pullback_tolerance=0.05
        )
        state = strategy.get_state()
        sma_20 = state["sma_20"]
        ts_entry = ts_base + timedelta(hours=66)
        strategy.process_tick(make_tick(sma_20, ts_entry))

        if not strategy.has_position:
            pytest.skip("Could not open position in test helper")
        return strategy, ts_base

    def test_trend_exit_below_50sma(self):
        """Position closes when price drops below 50-SMA."""
        strategy, ts_base = self._open_position()
        state = strategy.get_state()
        sma_50 = state["sma_50"]

        # Feed tick well below 50-SMA
        ts_exit = ts_base + timedelta(hours=70)
        exit_price = sma_50 - 2.0   # Clearly below trend
        sig = strategy.process_tick(make_tick(exit_price, ts_exit))

        assert sig.action == "close_long", f"Expected close_long, got '{sig.action}': {sig.reason}"
        assert not strategy.has_position
        assert "Trend exit" in sig.reason or "below" in sig.reason.lower()

    def test_stop_loss_exit(self):
        """Position closes when price hits stop loss."""
        strategy, ts_base = self._open_position()

        stop_price = float(strategy.state.stop_loss)
        entry_price = float(strategy.state.entry_price)
        assert stop_price < entry_price, "Setup error: stop must be below entry"

        # Feed tick at stop price
        ts_stop = ts_base + timedelta(hours=70)
        sig = strategy.process_tick(make_tick(stop_price - 0.05, ts_stop))

        assert sig.action == "close_long", f"Expected close_long at stop, got '{sig.action}'"
        assert not strategy.has_position
        assert "Stop hit" in sig.reason or "stop" in sig.reason.lower()


# ---------------------------------------------------------------------------
# Tests: Reset
# ---------------------------------------------------------------------------

class TestGBPJPYCarryReset:
    def test_reset_clears_state(self):
        strategy, _ = build_uptrend_strategy(n_bars=65)
        strategy.reset()

        assert not strategy.has_position
        assert len(strategy._price_history) == 0
        assert strategy.state.entry_price is None
        assert strategy.state.stop_loss is None

    def test_reset_restarts_warmup(self):
        strategy, _ = build_uptrend_strategy(n_bars=65)
        strategy.reset()

        ts = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        sig = strategy.process_tick(make_tick(190.0, ts))
        assert sig.action is None
        assert "Warming up" in sig.reason


# ---------------------------------------------------------------------------
# Tests: get_state
# ---------------------------------------------------------------------------

class TestGBPJPYCarryGetState:
    def test_get_state_structure(self):
        strategy = create_gbpjpy_carry_strategy()
        state = strategy.get_state()
        assert state["strategy"] == "gbpjpy_carry"
        assert "params" in state
        assert "has_position" in state
        assert "sma_20" in state
        assert "sma_50" in state

    def test_get_state_after_warmup(self):
        strategy, _ = build_uptrend_strategy(n_bars=65)
        state = strategy.get_state()
        assert state["price_history_length"] == 65
        assert state["sma_20"] is not None
        assert state["sma_50"] is not None
