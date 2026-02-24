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

HARD assertion rules:
- No conditional assertion paths based on `if strategy.has_position`
- Entry tests assert the signal fires (use setup helpers designed to guarantee entry)
- Exit tests assert the exit signal fires
- No `pytest.skip` unless truly impossible to construct test (DB not available)

mcp-verifier: run with `pytest tests/integration/test_gbpjpy_carry.py -v`
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


def _open_carry_position() -> tuple[GBPJPYCarryStrategy, datetime]:
    """
    Build a strategy and open a carry long position.

    Phase 1: 55 flat bars at 185 → both SMAs = 185
    Phase 2: 10 bars at 210 → SMA(20) rises to ~198, SMA(50) rises slightly, close=210
    Phase 3: Tick exactly at SMA(20) → pullback entry triggers

    Returns (strategy, ts_base). Asserts position is open.
    """
    params = GBPJPYCarryParams(
        trend_sma_period=50,
        entry_sma_period=20,
        atr_period=14,
        atr_stop_multiplier=2.0,
        pullback_tolerance=0.005,
        use_time_filter=False,
    )
    strategy = GBPJPYCarryStrategy(params=params)
    ts_base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    # Phase 1: 55 flat bars at 185
    for i in range(55):
        ts = ts_base + timedelta(hours=i)
        strategy.process_tick(make_tick(185.0, ts))

    assert not strategy.has_position, "No position expected after flat warmup"

    # Phase 2: 10 bars at 210
    for i in range(10):
        ts = ts_base + timedelta(hours=55 + i)
        strategy.process_tick(make_tick(210.0, ts))

    assert not strategy.has_position, "No position during 210 phase (too far from SMA)"

    state = strategy.get_state()
    sma_20 = state["sma_20"]
    sma_50 = state["sma_50"]
    assert sma_20 is not None and sma_50 is not None
    assert sma_20 > sma_50, f"SMA(20)={sma_20:.2f} must be > SMA(50)={sma_50:.2f}"

    # Phase 3: Tick at SMA(20) — pullback entry
    ts_entry = ts_base + timedelta(hours=66)
    sig = strategy.process_tick(make_tick(sma_20, ts_entry))

    assert sig.action == "buy", (
        f"Expected 'buy' on pullback to 20-SMA({sma_20:.4f}), got '{sig.action}': {sig.reason}"
    )
    assert strategy.has_position, "Position must be open after buy signal"

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
# Tests: Entry signal — HARD assertions
# ---------------------------------------------------------------------------

class TestGBPJPYCarryEntry:
    def test_buy_on_pullback_to_20sma(self):
        """
        BUY fires when price is above 50-SMA and pulls back to within pullback_tolerance of 20-SMA.
        """
        strategy, ts_base = _open_carry_position()  # Helper asserts signal fires

        assert strategy.has_position
        assert strategy.state.position_type == "buy"
        assert strategy.state.entry_price is not None
        assert strategy.state.stop_loss is not None

    def test_stop_placed_two_atr_below_entry(self):
        """Stop loss is set to entry − 2×ATR and is always below entry."""
        strategy, ts_base = _open_carry_position()

        state = strategy.get_state()
        entry_price = float(strategy.state.entry_price)
        stop_price = float(strategy.state.stop_loss)

        assert stop_price < entry_price, (
            f"Stop ({stop_price:.4f}) must be below entry ({entry_price:.4f})"
        )
        # ATR at entry must have been positive
        assert strategy.state.atr_at_entry is not None
        assert strategy.state.atr_at_entry > 0.0

        expected_stop = entry_price - 2.0 * strategy.state.atr_at_entry
        # Tolerance of 0.15 accounts for floating-point rounding in ATR computation
        assert abs(stop_price - expected_stop) < 0.15, (
            f"Stop ({stop_price:.4f}) should ≈ entry−2×ATR ({expected_stop:.4f}), "
            f"diff={abs(stop_price - expected_stop):.4f}"
        )

    def test_buy_confidence_in_valid_range(self):
        """BUY confidence must be in [0.0, 1.0]."""
        params = GBPJPYCarryParams(
            trend_sma_period=50, entry_sma_period=20, atr_period=14,
            atr_stop_multiplier=2.0, pullback_tolerance=0.005, use_time_filter=False,
        )
        strategy = GBPJPYCarryStrategy(params=params)
        ts_base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        for i in range(55):
            strategy.process_tick(make_tick(185.0, ts_base + timedelta(hours=i)))
        for i in range(10):
            strategy.process_tick(make_tick(210.0, ts_base + timedelta(hours=55 + i)))

        sma_20 = strategy.get_state()["sma_20"]
        ts_entry = ts_base + timedelta(hours=66)
        sig = strategy.process_tick(make_tick(sma_20, ts_entry))

        assert sig.action == "buy"
        assert 0.0 <= sig.confidence <= 1.0, f"Confidence {sig.confidence} out of range"

    def test_atr_insufficient_data_propagates(self):
        """
        InsufficientDataError propagates when ATR period > available price history.
        This verifies the no-fake-ATR rule.
        """
        strategy = GBPJPYCarryStrategy(GBPJPYCarryParams(atr_period=14))
        ts_base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        # Inject only 5 bars (need atr_period+1 = 15)
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
# Tests: Exit signals — HARD assertions
# ---------------------------------------------------------------------------

class TestGBPJPYCarryExits:
    def test_trend_exit_below_50sma(self):
        """Position closes when price drops below 50-SMA."""
        strategy, ts_base = _open_carry_position()
        state = strategy.get_state()
        sma_50 = state["sma_50"]

        # Feed tick well below 50-SMA
        ts_exit = ts_base + timedelta(hours=70)
        exit_price = sma_50 - 5.0   # Clearly below trend
        sig = strategy.process_tick(make_tick(exit_price, ts_exit))

        assert sig.action == "close_long", f"Expected close_long, got '{sig.action}': {sig.reason}"
        assert not strategy.has_position
        assert "Trend exit" in sig.reason or "below" in sig.reason.lower()

    def test_stop_loss_exit(self):
        """Position closes when price hits stop loss."""
        strategy, ts_base = _open_carry_position()

        stop_price = float(strategy.state.stop_loss)
        entry_price = float(strategy.state.entry_price)
        assert stop_price < entry_price, "Setup error: stop must be below entry"

        # Feed tick below stop price
        ts_stop = ts_base + timedelta(hours=70)
        sig = strategy.process_tick(make_tick(stop_price - 0.05, ts_stop))

        assert sig.action == "close_long", f"Expected close_long at stop, got '{sig.action}'"
        assert not strategy.has_position
        assert "Stop hit" in sig.reason or "stop" in sig.reason.lower()

    def test_position_state_cleared_after_trend_exit(self):
        """All state fields are None after trend exit."""
        strategy, ts_base = _open_carry_position()
        state = strategy.get_state()
        sma_50 = state["sma_50"]

        ts_exit = ts_base + timedelta(hours=70)
        strategy.process_tick(make_tick(sma_50 - 5.0, ts_exit))

        assert not strategy.has_position
        assert strategy.state.entry_price is None
        assert strategy.state.stop_loss is None
        assert strategy.state.atr_at_entry is None
        assert strategy.state.entry_time is None

    def test_hold_while_above_50sma_and_above_stop(self):
        """Position holds while close > 50-SMA and > stop_loss."""
        strategy, ts_base = _open_carry_position()
        state = strategy.get_state()
        sma_50 = state["sma_50"]
        stop_price = float(strategy.state.stop_loss)
        entry_price = float(strategy.state.entry_price)

        # Feed a tick above both 50-SMA and stop (safe zone)
        safe_price = max(sma_50 + 1.0, entry_price + 0.5)
        ts_hold = ts_base + timedelta(hours=70)
        sig = strategy.process_tick(make_tick(safe_price, ts_hold))

        assert strategy.has_position, "Position must remain open in safe zone"
        assert sig.action is None, f"Expected hold (None), got '{sig.action}': {sig.reason}"


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

    def test_get_state_reflects_open_position(self):
        """After opening a position, get_state reports it correctly."""
        strategy, ts_base = _open_carry_position()

        state = strategy.get_state()
        assert state["has_position"] is True
        assert state["entry_price"] is not None
        assert state["stop_loss"] is not None
        assert state["atr_at_entry"] is not None
        assert float(state["atr_at_entry"]) > 0.0
