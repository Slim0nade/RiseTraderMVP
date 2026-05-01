"""
Integration tests for Seasonal MA Crossover Strategy (WHEAT / CORN).

Tests verify:
1. Correct initialisation for CORN and WHEAT
2. Warmup period respected (no signals before slow_period bars)
3. BUY signal fires on golden cross ONLY in LONG bias months
4. SELL signal fires on death cross ONLY in SHORT bias months
5. Opposing signals are filtered (e.g. death cross in LONG month → no trade)
6. Neutral months produce no new entries
7. MA crossover reversal closes open position
8. hold_through_neutral=False closes on season change
9. Reset clears all state
10. Unsupported symbol raises ValueError

HARD assertion rules:
- No `assert sig is None or sig.action != "sell"` — unconditional assertions only
- Every test that expects a signal must assert it fires
- Every test that expects no signal must assert action is None

mcp-verifier: run with `pytest tests/integration/test_seasonal_ma.py -v`
"""
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import pytest

from src.strategies.agriculture.seasonal_ma import (
    SeasonalMAStrategy,
    SeasonalMAParams,
    SeasonalMASignal,
    SeasonalBias,
    create_seasonal_ma_strategy,
)
from src.services.backtesting.data_replay_engine import MarketTick


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tick_at(symbol: str, close: float, month: int, day: int = 15, hour: int = 10) -> MarketTick:
    """Create a MarketTick at a specific calendar month."""
    ts = datetime(2024, month, day, hour, 0, 0, tzinfo=timezone.utc)
    price = Decimal(str(close))
    return MarketTick(
        symbol=symbol,
        timestamp=ts,
        open=price - Decimal("0.05"),
        high=price + Decimal("0.05"),
        low=price - Decimal("0.05"),
        close=price,
        volume=5000,
    )


def build_warmed_strategy(symbol: str = "CORN", base_price: float = 500.0) -> SeasonalMAStrategy:
    """
    Return a strategy warmed up with flat prices in a neutral month (Jan/Dec).
    Price is constant so fast_MA == slow_MA == base_price → no crossover entry.
    """
    params = SeasonalMAParams(symbol=symbol, use_time_filter=False)
    strategy = SeasonalMAStrategy(params=params)

    # Feed slow_period flat ticks in January (neutral for both CORN and WHEAT)
    for i in range(params.slow_period + 5):
        day = (i % 28) + 1
        tick = MarketTick(
            symbol=symbol,
            timestamp=datetime(2024, 1, day % 28 + 1, 10, 0, 0, tzinfo=timezone.utc),
            open=Decimal(str(base_price - 0.01)),
            high=Decimal(str(base_price + 0.01)),
            low=Decimal(str(base_price - 0.01)),
            close=Decimal(str(base_price)),
            volume=1000,
        )
        strategy.process_tick(tick)

    assert not strategy.has_position, "Setup error: flat warmup should not open a position"
    return strategy


def inject_crossover(
    strategy: SeasonalMAStrategy,
    symbol: str,
    direction: str,   # 'golden' or 'death'
    month: int,
    base_price: float = 500.0,
    n_bars: int = 35,
) -> SeasonalMASignal | None:
    """
    Feed n_bars of trending prices in the given month.
    Returns the FIRST signal that triggers an action (or the last signal).
    """
    ts_base = datetime(2024, month, 1, 10, 0, 0, tzinfo=timezone.utc)
    last_sig = None
    for i in range(n_bars):
        ts = ts_base + timedelta(hours=i)
        if direction == "golden":
            price = base_price + i * 0.5   # Rising prices → fast > slow
        else:
            price = base_price - i * 0.5   # Falling prices → fast < slow

        tick = MarketTick(
            symbol=symbol,
            timestamp=ts,
            open=Decimal(str(price - 0.01)),
            high=Decimal(str(price + 0.01)),
            low=Decimal(str(price - 0.01)),
            close=Decimal(str(price)),
            volume=1000,
        )
        sig = strategy.process_tick(tick)
        if sig.action in ("buy", "sell"):
            return sig
        last_sig = sig
    return last_sig  # Last signal if no entry was triggered


# ---------------------------------------------------------------------------
# Tests: Initialisation
# ---------------------------------------------------------------------------

class TestSeasonalMAInit:
    def test_default_corn(self):
        strategy = SeasonalMAStrategy()
        assert strategy.params.symbol == "CORN"
        assert strategy.params.fast_period == 10
        assert strategy.params.slow_period == 30
        assert not strategy.has_position

    def test_wheat_symbol(self):
        strategy = create_seasonal_ma_strategy(symbol="WHEAT")
        assert strategy.params.symbol == "WHEAT"

    def test_unsupported_symbol_raises(self):
        with pytest.raises(ValueError, match="Unsupported symbol"):
            SeasonalMAStrategy(SeasonalMAParams(symbol="SOYBEANS"))

    def test_factory_custom_params(self):
        strategy = create_seasonal_ma_strategy(symbol="CORN", fast_period=5, slow_period=20)
        assert strategy.params.fast_period == 5
        assert strategy.params.slow_period == 20


# ---------------------------------------------------------------------------
# Tests: Warmup
# ---------------------------------------------------------------------------

class TestSeasonalMAWarmup:
    def test_no_signal_during_warmup(self):
        strategy = create_seasonal_ma_strategy(symbol="CORN", use_time_filter=False)
        ts = datetime(2024, 4, 1, 10, 0, 0, tzinfo=timezone.utc)

        for i in range(29):  # slow_period - 1 = 29
            t = ts + timedelta(hours=i)
            tick = MarketTick(
                symbol="CORN",
                timestamp=t,
                open=Decimal("500.00"),
                high=Decimal("500.10"),
                low=Decimal("499.90"),
                close=Decimal(str(500.0 + i * 0.5)),
                volume=1000,
            )
            sig = strategy.process_tick(tick)
            assert sig.action is None, f"Got signal at i={i}: {sig.reason}"
            assert "Warming up" in sig.reason


# ---------------------------------------------------------------------------
# Tests: CORN seasonal calendar — HARD assertions
# ---------------------------------------------------------------------------

class TestCornSeasonalCalendar:
    def test_buy_signal_in_long_month_april(self):
        """Golden cross in April (LONG) → BUY executes."""
        strategy = build_warmed_strategy("CORN")
        sig = inject_crossover(strategy, "CORN", "golden", month=4)

        assert sig is not None, "inject_crossover must return a signal"
        assert sig.action == "buy", f"Expected 'buy' in April, got '{sig.action}': {sig.reason}"
        assert 0.0 <= sig.confidence <= 1.0
        assert sig.seasonal_bias == "long"

    def test_sell_signal_filtered_in_long_month(self):
        """Death cross in April (LONG month) → SELL must be filtered — action must not be 'sell'."""
        strategy = build_warmed_strategy("CORN")
        sig = inject_crossover(strategy, "CORN", "death", month=4)

        # SELL in LONG month must be filtered — the signal must NOT have action="sell"
        assert sig is not None, "inject_crossover must return a signal"
        assert sig.action != "sell", (
            f"SELL should be filtered in April (LONG month), got action='{sig.action}'"
        )
        assert not strategy.has_position, "No position should be opened after filtered SELL"

    def test_sell_signal_in_short_month_october(self):
        """Death cross in October (SHORT) → SELL executes."""
        strategy = build_warmed_strategy("CORN")
        sig = inject_crossover(strategy, "CORN", "death", month=10)

        assert sig is not None, "inject_crossover must return a signal"
        assert sig.action == "sell", f"Expected 'sell' in October, got '{sig.action}': {sig.reason}"
        assert sig.seasonal_bias == "short"

    def test_buy_signal_filtered_in_short_month(self):
        """Golden cross in October (SHORT month) → BUY must be filtered — action must not be 'buy'."""
        strategy = build_warmed_strategy("CORN")
        sig = inject_crossover(strategy, "CORN", "golden", month=10)

        assert sig is not None, "inject_crossover must return a signal"
        assert sig.action != "buy", (
            f"BUY should be filtered in October (SHORT month), got action='{sig.action}'"
        )
        assert not strategy.has_position, "No position should be opened after filtered BUY"

    def test_no_entry_in_neutral_month_january(self):
        """Any crossover in January (neutral) → no entry."""
        strategy = build_warmed_strategy("CORN")
        sig = inject_crossover(strategy, "CORN", "golden", month=1)

        assert sig is not None, "inject_crossover must return a signal"
        assert sig.action is None, (
            f"Expected no entry in January (neutral), got '{sig.action}': {sig.reason}"
        )
        assert not strategy.has_position

    def test_buy_confidence_in_valid_range(self):
        """BUY signal confidence must be in [0.0, 1.0]."""
        strategy = build_warmed_strategy("CORN")
        sig = inject_crossover(strategy, "CORN", "golden", month=4)

        assert sig is not None
        assert sig.action == "buy"
        assert 0.0 <= sig.confidence <= 1.0, f"Confidence {sig.confidence} out of range"


# ---------------------------------------------------------------------------
# Tests: WHEAT seasonal calendar — HARD assertions
# ---------------------------------------------------------------------------

class TestWheatSeasonalCalendar:
    def test_buy_signal_in_long_month_march(self):
        """Golden cross in March (LONG) → BUY executes."""
        strategy = build_warmed_strategy("WHEAT")
        sig = inject_crossover(strategy, "WHEAT", "golden", month=3)

        assert sig is not None, "inject_crossover must return a signal"
        assert sig.action == "buy", f"Expected 'buy' in March, got '{sig.action}': {sig.reason}"
        assert sig.seasonal_bias == "long"

    def test_sell_filtered_in_long_month_february(self):
        """Death cross in February (LONG) → SELL filtered — must not be 'sell'."""
        strategy = build_warmed_strategy("WHEAT")
        sig = inject_crossover(strategy, "WHEAT", "death", month=2)

        assert sig is not None, "inject_crossover must return a signal"
        assert sig.action != "sell", (
            f"SELL in February (LONG month) must be filtered, got '{sig.action}'"
        )

    def test_sell_signal_in_short_month_august(self):
        """Death cross in August (SHORT) → SELL executes."""
        strategy = build_warmed_strategy("WHEAT")
        sig = inject_crossover(strategy, "WHEAT", "death", month=8)

        assert sig is not None, "inject_crossover must return a signal"
        assert sig.action == "sell", f"Expected 'sell' in August, got '{sig.action}': {sig.reason}"
        assert sig.seasonal_bias == "short"

    def test_no_entry_in_neutral_month_june(self):
        """June is neutral for WHEAT → no entry."""
        strategy = build_warmed_strategy("WHEAT")
        sig = inject_crossover(strategy, "WHEAT", "golden", month=6)

        assert sig is not None, "inject_crossover must return a signal"
        assert sig.action is None, (
            f"Expected no entry in June (neutral for WHEAT), got '{sig.action}'"
        )


# ---------------------------------------------------------------------------
# Tests: Exit signals — HARD assertions
# ---------------------------------------------------------------------------

class TestSeasonalMAExits:
    def _open_long(self) -> SeasonalMAStrategy:
        """Return CORN strategy with a long position opened by golden cross in April."""
        strategy = build_warmed_strategy("CORN")
        sig = inject_crossover(strategy, "CORN", "golden", month=4)
        assert sig is not None and sig.action == "buy", f"Setup failed: {sig}"
        assert strategy.has_position
        return strategy

    def test_close_long_on_death_cross(self):
        """Long position closes when fast MA crosses below slow MA."""
        strategy = self._open_long()
        # Inject falling prices in April to produce death cross
        ts_base = datetime(2024, 4, 25, 10, 0, 0, tzinfo=timezone.utc)
        sig = None
        for i in range(50):
            price = 520.0 - i * 2.0  # Steep fall to create death cross
            ts = ts_base + timedelta(hours=i)
            tick = MarketTick(
                symbol="CORN",
                timestamp=ts,
                open=Decimal(str(price - 0.1)),
                high=Decimal(str(price + 0.1)),
                low=Decimal(str(price - 0.1)),
                close=Decimal(str(price)),
                volume=1000,
            )
            sig = strategy.process_tick(tick)
            if sig.action == "close_long":
                break

        assert sig is not None, "Must have a final signal"
        assert sig.action == "close_long", f"Expected close_long, got '{sig.action}': {sig.reason}"
        assert not strategy.has_position

    def test_hold_through_neutral_true(self):
        """With hold_through_neutral=True, position persists in neutral month."""
        params = SeasonalMAParams(symbol="CORN", hold_through_neutral=True, use_time_filter=False)
        strategy = SeasonalMAStrategy(params=params)

        # Warm up
        for i in range(35):
            tick = MarketTick(
                symbol="CORN",
                timestamp=datetime(2024, 1, (i % 28) + 1, 10, 0, 0, tzinfo=timezone.utc),
                open=Decimal("499.99"), high=Decimal("500.01"),
                low=Decimal("499.99"), close=Decimal("500.00"), volume=1000,
            )
            strategy.process_tick(tick)

        sig = inject_crossover(strategy, "CORN", "golden", month=4)
        assert sig is not None and sig.action == "buy", f"Setup failed: {sig}"

        # Feed a tick in July (neutral) with price between entry and take-profit.
        # ATR ≈ 0.5 from the crossover bars, so TP ≈ entry + 1.5 for a long.
        # Compute a safe neutral price from the signal's SL/TP if available,
        # otherwise fall back to midpoint that won't trigger either level.
        if sig.stop_loss is not None and sig.take_profit is not None:
            neutral_price = round((sig.stop_loss + sig.take_profit) / 2, 2)
        else:
            neutral_price = 501.0
        ts = datetime(2024, 7, 15, 10, 0, 0, tzinfo=timezone.utc)
        tick = MarketTick(
            symbol="CORN", timestamp=ts,
            open=Decimal(str(neutral_price - 0.01)),
            high=Decimal(str(neutral_price + 0.01)),
            low=Decimal(str(neutral_price - 0.01)),
            close=Decimal(str(neutral_price)), volume=1000,
        )
        sig2 = strategy.process_tick(tick)
        # With hold_through_neutral=True: position must still be open (no death cross occurred)
        assert strategy.has_position, "Position must be held through neutral month"
        assert sig2.action is None, (
            f"Expected hold (None) in neutral month, got '{sig2.action}'"
        )

    def test_hold_through_neutral_false_closes(self):
        """With hold_through_neutral=False, position closes when season turns neutral."""
        params = SeasonalMAParams(symbol="CORN", hold_through_neutral=False, use_time_filter=False)
        strategy = SeasonalMAStrategy(params=params)

        for i in range(35):
            tick = MarketTick(
                symbol="CORN",
                timestamp=datetime(2024, 1, (i % 28) + 1, 10, 0, 0, tzinfo=timezone.utc),
                open=Decimal("499.99"), high=Decimal("500.01"),
                low=Decimal("499.99"), close=Decimal("500.00"), volume=1000,
            )
            strategy.process_tick(tick)

        sig = inject_crossover(strategy, "CORN", "golden", month=4)
        assert sig is not None and sig.action == "buy", f"Setup failed: {sig}"

        # Feed a tick in July (neutral) → must close due to hold_through_neutral=False
        ts = datetime(2024, 7, 15, 10, 0, 0, tzinfo=timezone.utc)
        tick = MarketTick(
            symbol="CORN", timestamp=ts,
            open=Decimal("519.00"), high=Decimal("521.00"),
            low=Decimal("518.00"), close=Decimal("520.00"), volume=1000,
        )
        sig2 = strategy.process_tick(tick)
        assert sig2.action == "close_long", (
            f"Expected close_long on neutral season, got '{sig2.action}': {sig2.reason}"
        )
        assert not strategy.has_position


# ---------------------------------------------------------------------------
# Tests: Reset
# ---------------------------------------------------------------------------

class TestSeasonalMAReset:
    def test_reset_clears_state(self):
        strategy = build_warmed_strategy("CORN")
        inject_crossover(strategy, "CORN", "golden", month=4)
        strategy.reset()

        assert not strategy.has_position
        assert len(strategy._price_history) == 0
        assert strategy.state.position_type is None

    def test_reset_restarts_warmup(self):
        strategy = build_warmed_strategy("CORN")
        strategy.reset()

        tick = MarketTick(
            symbol="CORN",
            timestamp=datetime(2024, 4, 15, 10, 0, 0, tzinfo=timezone.utc),
            open=Decimal("499.95"), high=Decimal("500.05"),
            low=Decimal("499.95"), close=Decimal("500.00"), volume=1000,
        )
        sig = strategy.process_tick(tick)
        assert sig.action is None
        assert "Warming up" in sig.reason


# ---------------------------------------------------------------------------
# Tests: get_state
# ---------------------------------------------------------------------------

class TestSeasonalMAGetState:
    def test_get_state_structure(self):
        strategy = create_seasonal_ma_strategy(symbol="WHEAT")
        state = strategy.get_state()
        assert state["strategy"] == "seasonal_ma"
        assert state["symbol"] == "WHEAT"
        assert "fast_ma" in state
        assert "slow_ma" in state
        assert "has_position" in state

    def test_get_state_no_position_initially(self):
        strategy = create_seasonal_ma_strategy(symbol="CORN")
        state = strategy.get_state()
        assert state["has_position"] is False

    def test_get_state_reflects_open_long(self):
        """get_state reports position_type='buy' after long opened."""
        strategy = build_warmed_strategy("CORN")
        sig = inject_crossover(strategy, "CORN", "golden", month=4)

        assert sig is not None and sig.action == "buy", "Setup: buy must fire in April"
        state = strategy.get_state()
        assert state["has_position"] is True
        assert state["position_type"] == "buy"
        assert state["entry_price"] is not None
        assert state["entry_season"] == "long"
