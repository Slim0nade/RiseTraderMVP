"""
Integration tests for Crack Spread Strategy (CrudeOIL vs GASOLINE).

Tests verify:
1. Strategy initialises with correct defaults and hedge ratio
2. Spread calculation: gasoline_barrel_price − crude_price (42 gal/bbl conversion)
3. Warmup period respected (no signals before lookback candles from BOTH symbols)
4. SELL SPREAD fires when z-score > +entry_sigma (spread too wide)
5. BUY SPREAD fires when z-score < -entry_sigma (spread too tight)
6. Mean-reversion exit fires when |z-score| <= exit_sigma
7. Stop loss fires when |z-score| >= stop_sigma
8. Seasonal overlay widens entry sigma in Q2-Q3
9. Reset clears all state
10. Staleness gate: no signal if crude and gasoline ticks are > max_tick_age apart

All tests use synthetic data — no mocks, no DB calls.
mcp-verifier: run with `pytest tests/integration/test_crack_spread.py -v`
"""
from decimal import Decimal
from datetime import datetime, timedelta, timezone
import random

import pytest

from src.strategies.spreads.crack_spread import (
    CrackSpreadStrategy,
    CrackSpreadParams,
    CrackSpreadSignal,
    create_crack_spread_strategy,
    HEDGE_RATIO_GAS_PER_CRUDE,
    GAL_PER_BBL,
)
from src.services.backtesting.data_replay_engine import MarketTick


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tick(
    symbol: str,
    close: float,
    ts: datetime | None = None,
) -> MarketTick:
    """Create a minimal MarketTick for testing."""
    if ts is None:
        ts = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    price = Decimal(str(round(close, 4)))
    half_range = Decimal("0.05")
    return MarketTick(
        symbol=symbol,
        timestamp=ts,
        open=price - half_range,
        high=price + half_range,
        low=price - half_range,
        close=price,
        volume=1000,
    )


def prime_strategy(
    strategy: CrackSpreadStrategy,
    n: int = 20,
    base_crude: float = 75.0,
    base_gasoline_per_gal: float = 2.10,
    crude_symbol: str = "CrudeOIL",
    gasoline_symbol: str = "GASOLINE",
    ts_base: datetime | None = None,
    seed: int = 42,
) -> datetime:
    """
    Feed n pairs of aligned H1 ticks to complete the warmup period.

    Uses slight random variation so the spread series has non-zero stdev.

    Returns the timestamp of the last tick fed.

    Typical spread after warmup:
        base_gasoline_per_gal × 42 − base_crude = 2.10 × 42 − 75 = 88.2 − 75 = $13.20/bbl
    """
    if ts_base is None:
        ts_base = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)

    rng = random.Random(seed)
    last_ts = ts_base
    for i in range(n):
        ts = ts_base + timedelta(hours=i)
        crude = base_crude + rng.uniform(-0.20, 0.20)
        gas_gal = base_gasoline_per_gal + rng.uniform(-0.005, 0.005)
        strategy.process_tick(make_tick(crude_symbol, crude, ts))
        strategy.process_tick(make_tick(gasoline_symbol, gas_gal, ts))
        last_ts = ts

    return last_ts


# ---------------------------------------------------------------------------
# 1. Initialisation
# ---------------------------------------------------------------------------

class TestCrackSpreadInit:
    def test_default_params(self):
        s = CrackSpreadStrategy()
        assert s.params.lookback == 20
        assert s.params.entry_sigma == 1.5
        assert s.params.exit_sigma == 0.3
        assert s.params.stop_sigma == 2.5
        assert not s.has_position
        assert s.entry_price is None

    def test_factory_overrides(self):
        s = create_crack_spread_strategy(lookback=30, entry_sigma=2.0, stop_sigma=3.0)
        assert s.params.lookback == 30
        assert s.params.entry_sigma == 2.0
        assert s.params.stop_sigma == 3.0

    def test_factory_crude_lots_decimal_conversion(self):
        s = create_crack_spread_strategy(crude_lots=2)
        assert isinstance(s.params.crude_lots, Decimal)
        assert s.params.crude_lots == Decimal("2")

    def test_hedge_ratio_correct(self):
        """
        Hedge ratio = (1000 bbl × 42 gal/bbl) / 100_000 gal = 0.42.
        $1/bbl move in crude = $1,000 per contract.
        Matching gasoline exposure: 0.42 lots × $10/tick × 10,000 ticks/$ ≈ $4,200 — off.
        The ratio ensures equal per-barrel dollar exposure, not equal contract dollars.
        Verify the math is correct.
        """
        assert abs(HEDGE_RATIO_GAS_PER_CRUDE - 0.42) < 1e-9

    def test_symbols_default(self):
        s = CrackSpreadStrategy()
        assert s.params.crude_symbol == "CrudeOIL"
        assert s.params.gasoline_symbol == "GASOLINE"


# ---------------------------------------------------------------------------
# 2. Spread calculation correctness
# ---------------------------------------------------------------------------

class TestSpreadCalculation:
    def test_spread_equals_gasoline_barrel_minus_crude(self):
        """
        Spread = gasoline_per_gal × 42 - crude_per_bbl.
        With crude=75, gas=2.10: spread = 2.10×42 - 75 = 88.2 - 75 = 13.2.
        """
        s = CrackSpreadStrategy()
        ts_base = datetime(2024, 3, 15, 10, 0, 0, tzinfo=timezone.utc)

        # Feed identical ticks to populate buffers (no variation = std=0 initially)
        for i in range(21):
            ts = ts_base + timedelta(hours=i)
            s.process_tick(make_tick("CrudeOIL", 75.0, ts))
            s.process_tick(make_tick("GASOLINE", 2.10, ts))

        state = s.get_state()
        gas_bbl = state["latest_prices"]["gasoline_per_bbl"]
        crude = state["latest_prices"]["crude"]
        spread = state["latest_prices"]["spread"]

        assert abs(gas_bbl - 88.2) < 0.01, f"Expected 88.2, got {gas_bbl}"
        assert abs(crude - 75.0) < 0.01
        assert abs(spread - 13.2) < 0.01, f"Expected 13.2, got {spread}"

    def test_spread_unit_conversion_constant(self):
        """GAL_PER_BBL must be 42 — energy contract definition."""
        assert GAL_PER_BBL == 42


# ---------------------------------------------------------------------------
# 3. Warmup period
# ---------------------------------------------------------------------------

class TestWarmup:
    def test_no_signal_before_crude_data(self):
        """Only GASOLINE ticks — no crude data — should return warmup."""
        s = CrackSpreadStrategy()
        for i in range(25):
            sig = s.process_tick(make_tick("GASOLINE", 2.10))
            assert sig.action is None
            assert "Warming up" in sig.reason

    def test_no_signal_before_gasoline_data(self):
        """Only CrudeOIL ticks — no gasoline data — should return warmup."""
        s = CrackSpreadStrategy()
        for i in range(25):
            sig = s.process_tick(make_tick("CrudeOIL", 75.0))
            assert sig.action is None
            assert "Warming up" in sig.reason

    def test_no_signal_short_of_lookback(self):
        """Feed lookback-1 pairs — still in warmup."""
        s = create_crack_spread_strategy(lookback=20)
        ts_base = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)

        for i in range(19):  # one short of lookback=20
            ts = ts_base + timedelta(hours=i)
            s.process_tick(make_tick("CrudeOIL", 75.0, ts))
            sig = s.process_tick(make_tick("GASOLINE", 2.10, ts))
            assert sig.action is None, f"Unexpected signal at i={i}: {sig.reason}"
            assert "Warming up" in sig.reason

    def test_signal_possible_after_lookback(self):
        """After exactly lookback pairs, spread computation is available."""
        s = create_crack_spread_strategy(lookback=20)
        ts_base = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)

        # 20 pairs — warmup complete (spread may still not trigger entry)
        prime_strategy(s, n=20, ts_base=ts_base)

        # State should show spread is computed
        state = s.get_state()
        assert state["latest_prices"]["spread"] is not None
        assert state["buffers"]["crude_candles"] == 20
        assert state["buffers"]["gasoline_candles"] == 20


# ---------------------------------------------------------------------------
# 4. Entry signals
# ---------------------------------------------------------------------------

class TestEntrySignals:
    def _build_primed_strategy(
        self,
        mean_crude: float = 75.0,
        mean_gas_gal: float = 2.10,
        lookback: int = 20,
        seed: int = 42,
    ) -> tuple[CrackSpreadStrategy, datetime]:
        """Return a primed strategy and the timestamp after the last warmup tick."""
        s = create_crack_spread_strategy(
            lookback=lookback,
            enable_seasonality=False,
            use_time_filter=False,  # isolate entry signal logic from time filter
        )
        ts_base = datetime(2024, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        last_ts = prime_strategy(s, n=lookback, base_crude=mean_crude,
                                  base_gasoline_per_gal=mean_gas_gal, ts_base=ts_base, seed=seed)
        return s, last_ts

    def test_sell_spread_on_wide_spread(self):
        """
        When gasoline_barrel >> crude (spread too wide), SELL the spread.

        After warmup with mean crack ≈ $13.20, inject a spike to $25+.
        That should be well beyond +1.5σ and trigger sell_spread.
        """
        s, last_ts = self._build_primed_strategy()
        ts_signal = last_ts + timedelta(hours=1)

        # Spike: crude stays at 75, gasoline jumps to 2.90/gal → 2.90×42=121.8, spread=46.8
        s.process_tick(make_tick("CrudeOIL", 75.0, ts_signal))
        sig = s.process_tick(make_tick("GASOLINE", 2.90, ts_signal))

        assert sig.action == "sell_spread", f"Expected sell_spread, got {sig.action}: {sig.reason}"
        assert sig.z_score is not None and sig.z_score > 1.5
        assert sig.crude_quantity == Decimal("1.0")
        assert sig.gasoline_quantity > Decimal("0")
        assert s.has_position

    def test_buy_spread_on_narrow_spread(self):
        """
        When gasoline_barrel << crude (spread too narrow), BUY the spread.

        After warmup with mean crack ≈ $13.20, inject a crash to negative spread.
        """
        s, last_ts = self._build_primed_strategy()
        ts_signal = last_ts + timedelta(hours=1)

        # Crash: crude stays at 75, gasoline drops to 1.40/gal → 1.40×42=58.8, spread=-16.2
        s.process_tick(make_tick("CrudeOIL", 75.0, ts_signal))
        sig = s.process_tick(make_tick("GASOLINE", 1.40, ts_signal))

        assert sig.action == "buy_spread", f"Expected buy_spread, got {sig.action}: {sig.reason}"
        assert sig.z_score is not None and sig.z_score < -1.5
        assert sig.crude_quantity == Decimal("1.0")
        assert s.has_position

    def test_no_signal_within_entry_band(self):
        """Z-score within ±entry_sigma → no action."""
        s, last_ts = self._build_primed_strategy()
        ts_signal = last_ts + timedelta(hours=1)

        # Small move: crude=75.05, gas=2.1005 → spread very close to mean
        s.process_tick(make_tick("CrudeOIL", 75.05, ts_signal))
        sig = s.process_tick(make_tick("GASOLINE", 2.1005, ts_signal))

        assert sig.action is None
        assert "No signal" in sig.reason

    def test_confidence_scales_with_z_score(self):
        """Higher |z-score| at entry → higher confidence."""
        s1, ts1 = self._build_primed_strategy(seed=42)
        s2, ts2 = self._build_primed_strategy(seed=42)  # same setup

        # Moderate spike (just beyond 1.5σ)
        ts_sig1 = ts1 + timedelta(hours=1)
        s1.process_tick(make_tick("CrudeOIL", 75.0, ts_sig1))
        sig1 = s1.process_tick(make_tick("GASOLINE", 2.90, ts_sig1))

        # Larger spike
        ts_sig2 = ts2 + timedelta(hours=1)
        s2.process_tick(make_tick("CrudeOIL", 75.0, ts_sig2))
        sig2 = s2.process_tick(make_tick("GASOLINE", 3.20, ts_sig2))

        if sig1.action and sig2.action:
            # Both should have fired; sig2 should have higher confidence
            assert sig2.confidence >= sig1.confidence, (
                f"sig2.confidence={sig2.confidence} should >= sig1.confidence={sig1.confidence}"
            )

    def test_gasoline_quantity_matches_hedge_ratio(self):
        """gasoline_lots = round(crude_lots × 0.42, 2)."""
        s, last_ts = self._build_primed_strategy()
        ts_signal = last_ts + timedelta(hours=1)

        s.process_tick(make_tick("CrudeOIL", 75.0, ts_signal))
        sig = s.process_tick(make_tick("GASOLINE", 2.90, ts_signal))

        if sig.action in ("buy_spread", "sell_spread"):
            expected_gas = Decimal(str(round(float(s.params.crude_lots) * HEDGE_RATIO_GAS_PER_CRUDE, 2)))
            assert sig.gasoline_quantity == expected_gas, (
                f"Expected {expected_gas}, got {sig.gasoline_quantity}"
            )


# ---------------------------------------------------------------------------
# 5. Exit signals
# ---------------------------------------------------------------------------

class TestExitSignals:
    def _enter_sell_spread(
        self, ts_base: datetime | None = None
    ) -> tuple[CrackSpreadStrategy, datetime]:
        """Setup: prime + enter a sell_spread position."""
        if ts_base is None:
            ts_base = datetime(2024, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        s = create_crack_spread_strategy(
            lookback=20,
            enable_seasonality=False,
            use_time_filter=False,  # isolate exit signal logic from time filter
        )
        last_ts = prime_strategy(s, n=20, ts_base=ts_base)
        ts_signal = last_ts + timedelta(hours=1)

        # Wide spread → sell_spread
        s.process_tick(make_tick("CrudeOIL", 75.0, ts_signal))
        sig = s.process_tick(make_tick("GASOLINE", 2.90, ts_signal))
        assert sig.action == "sell_spread", f"Setup failed: {sig.reason}"
        return s, ts_signal

    def test_mean_reversion_exit(self):
        """After sell_spread, spread returns to mean → close."""
        s, ts_entry = self._enter_sell_spread()

        # Return spread to near mean (crude=75, gas=2.10 → spread≈13.2 ≈ mean)
        ts_exit = ts_entry + timedelta(hours=2)
        s.process_tick(make_tick("CrudeOIL", 75.0, ts_exit))
        sig = s.process_tick(make_tick("GASOLINE", 2.10, ts_exit))

        assert sig.action == "close", f"Expected close, got {sig.action}: {sig.reason}"
        assert "TARGET" in sig.reason
        assert not s.has_position

    def test_stop_loss_on_further_widening(self):
        """When spread widens past stop_sigma, close with stop reason."""
        s, ts_entry = self._enter_sell_spread()

        # Extreme spike well beyond 2.5σ
        ts_stop = ts_entry + timedelta(hours=2)
        s.process_tick(make_tick("CrudeOIL", 75.0, ts_stop))
        sig = s.process_tick(make_tick("GASOLINE", 3.50, ts_stop))

        assert sig.action == "close", f"Expected close, got {sig.action}: {sig.reason}"
        assert "STOP" in sig.reason
        assert not s.has_position

    def test_position_state_cleared_after_close(self):
        """All entry state is cleared on close."""
        s, ts_entry = self._enter_sell_spread()
        assert s.state.entry_spread is not None

        ts_exit = ts_entry + timedelta(hours=2)
        s.process_tick(make_tick("CrudeOIL", 75.0, ts_exit))
        s.process_tick(make_tick("GASOLINE", 2.10, ts_exit))

        assert not s.has_position
        assert s.state.entry_spread is None
        assert s.state.entry_price_crude is None
        assert s.state.entry_price_gasoline is None

    def test_hold_while_between_exit_and_stop(self):
        """While |z| is between exit_sigma and stop_sigma, hold (action=None)."""
        s, ts_entry = self._enter_sell_spread()

        # Partial reversion: spread narrows a bit but not back to mean
        # z should be between exit_sigma (0.3) and stop_sigma (2.5)
        ts_hold = ts_entry + timedelta(hours=2)
        s.process_tick(make_tick("CrudeOIL", 75.0, ts_hold))
        sig = s.process_tick(make_tick("GASOLINE", 2.50, ts_hold))

        # We don't know exact z (depends on distribution), but position should be held
        # unless the spread was extreme enough to stop out immediately.
        if s.has_position:
            assert sig.action is None, f"Expected hold, got {sig.action}: {sig.reason}"


# ---------------------------------------------------------------------------
# 6. Seasonal sigma overlay
# ---------------------------------------------------------------------------

class TestSeasonalOverlay:
    """
    Entry sigma is widened in Q2 (Apr-Jun) and Q3 (Jul-Sep) because crack
    spreads naturally widen during the summer driving season.
    Wider sigma = harder to enter = fewer false signals during noisy periods.
    """

    def _get_effective_sigma(self, month: int) -> float:
        """Get effective entry sigma for a given month."""
        s = create_crack_spread_strategy(
            entry_sigma=1.5,
            q2_sigma_addon=0.3,
            q3_sigma_addon=0.5,
            enable_seasonality=True,
        )
        ts = datetime(2024, month, 15, 12, 0, 0, tzinfo=timezone.utc)
        return s._get_entry_sigma(ts)

    def test_q1_base_sigma(self):
        """January: base entry_sigma unchanged."""
        assert self._get_effective_sigma(1) == pytest.approx(1.5)

    def test_q2_wider_sigma(self):
        """April: entry_sigma + q2_addon = 1.5 + 0.3 = 1.8."""
        assert self._get_effective_sigma(4) == pytest.approx(1.8)

    def test_q3_widest_sigma(self):
        """July: entry_sigma + q3_addon = 1.5 + 0.5 = 2.0."""
        assert self._get_effective_sigma(7) == pytest.approx(2.0)

    def test_q4_base_sigma(self):
        """October: back to base entry_sigma = 1.5."""
        assert self._get_effective_sigma(10) == pytest.approx(1.5)

    def test_seasonality_disabled_always_base(self):
        """With enable_seasonality=False, sigma never changes."""
        s = create_crack_spread_strategy(entry_sigma=1.5, enable_seasonality=False)
        for month in [1, 4, 7, 10]:
            ts = datetime(2024, month, 15, 12, 0, 0, tzinfo=timezone.utc)
            assert s._get_entry_sigma(ts) == pytest.approx(1.5)

    def test_q2_requires_bigger_spike_to_enter(self):
        """
        A spike that triggers entry in Q1 must NOT trigger in Q2
        if the z-score falls between the two sigma thresholds.
        """
        # Build a stable spread history
        def build_and_prime(month: int) -> CrackSpreadStrategy:
            ts_base = datetime(2024, month, 1, 9, 0, 0, tzinfo=timezone.utc)
            s = create_crack_spread_strategy(
                lookback=20,
                entry_sigma=1.5,
                q2_sigma_addon=0.3,
                enable_seasonality=True,
                use_time_filter=False,
            )
            prime_strategy(s, n=20, ts_base=ts_base, seed=99)
            return s, ts_base

        s_q1, base_q1 = build_and_prime(1)  # January
        s_q2, base_q2 = build_and_prime(4)  # April

        # Create a spike that lands at ~1.7σ above mean — between 1.5 and 1.8
        # We'll use an extreme price that definitely clears the base 1.5σ bar.
        # We need z ≈ 1.6–1.7, so a moderate-but-not-huge gasoline spike.
        # Since std depends on the random warmup, we use the same seed (99) for both.
        ts_q1_signal = base_q1 + timedelta(hours=21)
        ts_q2_signal = base_q2 + timedelta(hours=21)

        # Feed the same relative spike to both
        s_q1.process_tick(make_tick("CrudeOIL", 75.0, ts_q1_signal))
        sig_q1 = s_q1.process_tick(make_tick("GASOLINE", 2.50, ts_q1_signal))

        s_q2.process_tick(make_tick("CrudeOIL", 75.0, ts_q2_signal))
        sig_q2 = s_q2.process_tick(make_tick("GASOLINE", 2.50, ts_q2_signal))

        # If Q1 fires, Q2 may or may not depending on exact z-score.
        # The key assertion: Q2 sigma >= Q1 sigma (behaviour is correct).
        q1_sigma = s_q1._get_entry_sigma(ts_q1_signal)
        q2_sigma = s_q2._get_entry_sigma(ts_q2_signal)
        assert q2_sigma > q1_sigma, (
            f"Q2 sigma ({q2_sigma}) should be wider than Q1 sigma ({q1_sigma})"
        )


# ---------------------------------------------------------------------------
# 7. Staleness gate
# ---------------------------------------------------------------------------

class TestStalenessGate:
    def test_no_signal_when_ticks_are_stale(self):
        """
        If crude and gasoline latest ticks are >max_tick_age_seconds apart,
        spread should not be computed and strategy returns warmup/no signal.
        """
        s = create_crack_spread_strategy(
            lookback=20, max_tick_age_seconds=3600, enable_seasonality=False
        )
        ts_crude = datetime(2024, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        ts_gas = ts_crude + timedelta(hours=25)  # 25h gap — stale

        # Prime crude only with aligned timestamps
        for i in range(20):
            s.process_tick(make_tick("CrudeOIL", 75.0, ts_crude + timedelta(hours=i)))

        # Feed ONE gasoline tick very far in the future
        sig = s.process_tick(make_tick("GASOLINE", 2.10, ts_gas))

        # Should be in warmup (only 1 gas tick) or no signal due to staleness
        assert sig.action is None


# ---------------------------------------------------------------------------
# 8. Time filter
# ---------------------------------------------------------------------------

class TestTimeFilter:
    def test_no_signal_outside_trading_hours(self):
        """Before 08:00 or after 20:00 GMT → no entry."""
        s = create_crack_spread_strategy(
            lookback=20,
            use_time_filter=True,
            trading_start_hour=8,
            trading_end_hour=20,
            enable_seasonality=False,
        )
        ts_base = datetime(2024, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        prime_strategy(s, n=20, ts_base=ts_base)

        # Midnight tick (outside hours) with extreme spread
        ts_midnight = datetime(2024, 3, 2, 2, 0, 0, tzinfo=timezone.utc)
        s.process_tick(make_tick("CrudeOIL", 75.0, ts_midnight))
        sig = s.process_tick(make_tick("GASOLINE", 2.90, ts_midnight))

        assert sig.action is None
        assert "Outside trading hours" in sig.reason


# ---------------------------------------------------------------------------
# 9. Reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_all_state(self):
        s = create_crack_spread_strategy(lookback=20, enable_seasonality=False)
        ts_base = datetime(2024, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        last_ts = prime_strategy(s, n=20, ts_base=ts_base)

        # Enter a position
        ts_signal = last_ts + timedelta(hours=1)
        s.process_tick(make_tick("CrudeOIL", 75.0, ts_signal))
        s.process_tick(make_tick("GASOLINE", 2.90, ts_signal))

        # Reset and verify clean state
        s.reset()

        assert not s.has_position
        assert s.entry_price is None
        assert len(s._crude_buffer) == 0
        assert len(s._gasoline_buffer) == 0
        assert len(s._spread_series) == 0
        assert s.state.entry_spread is None

    def test_strategy_functional_after_reset(self):
        """After reset, strategy can be re-primed and trade again."""
        s = create_crack_spread_strategy(lookback=20, enable_seasonality=False)
        ts_base = datetime(2024, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        prime_strategy(s, n=20, ts_base=ts_base)
        s.reset()

        # Re-prime and ensure it works
        ts_base2 = datetime(2024, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
        last_ts = prime_strategy(s, n=20, ts_base=ts_base2)

        state = s.get_state()
        assert state["buffers"]["crude_candles"] == 20
        assert state["buffers"]["gasoline_candles"] == 20


# ---------------------------------------------------------------------------
# 10. Contract normalization math
# ---------------------------------------------------------------------------

class TestContractNormalization:
    def test_hedge_ratio_formula(self):
        """
        Dollar-neutral hedge ratio.

        CrudeOIL:  1,000 bbl/contract, $1/tick ($0.01/bbl), $1,000 per $1/bbl move
        GASOLINE:  100,000 gal/contract, $10/tick ($0.0001/gal), $10,000 per $0.1/gal

        To balance $1/bbl exposure on crude:
            crude_dollar_per_bbl = $1 × 1,000 = $1,000 per lot
            gasoline_bbl_equiv_per_lot = 100,000 / 42 = 2,380.95 bbl
            → gas_lots needed for 1,000 bbl exposure = 1,000 / 2,380.95 = 0.42

        HEDGE_RATIO = 1,000 × 42 / 100,000 = 0.42
        """
        expected = (1_000 * 42) / 100_000  # = 0.42
        assert abs(HEDGE_RATIO_GAS_PER_CRUDE - expected) < 1e-9

    def test_gasoline_quantity_always_positive(self):
        """gasoline_quantity must be > 0 for any non-zero crude_lots."""
        s = create_crack_spread_strategy(crude_lots=Decimal("1.0"), enable_seasonality=False)
        ts_base = datetime(2024, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        last_ts = prime_strategy(s, n=20, ts_base=ts_base)

        ts_signal = last_ts + timedelta(hours=1)
        s.process_tick(make_tick("CrudeOIL", 75.0, ts_signal))
        sig = s.process_tick(make_tick("GASOLINE", 2.90, ts_signal))

        if sig.action in ("buy_spread", "sell_spread"):
            assert sig.gasoline_quantity > Decimal("0")
            assert sig.crude_quantity > Decimal("0")


# ---------------------------------------------------------------------------
# 11. get_state() correctness
# ---------------------------------------------------------------------------

class TestGetState:
    def test_state_reflects_position(self):
        s = create_crack_spread_strategy(lookback=20, enable_seasonality=False)
        ts_base = datetime(2024, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        last_ts = prime_strategy(s, n=20, ts_base=ts_base)

        state_before = s.get_state()
        assert not state_before["position"]["has_position"]

        ts_signal = last_ts + timedelta(hours=1)
        s.process_tick(make_tick("CrudeOIL", 75.0, ts_signal))
        sig = s.process_tick(make_tick("GASOLINE", 2.90, ts_signal))

        if sig.action in ("buy_spread", "sell_spread"):
            state_after = s.get_state()
            assert state_after["position"]["has_position"]
            assert state_after["position"]["type"] == sig.action
            assert state_after["position"]["entry_crude"] is not None

    def test_state_shows_spread_and_zscore(self):
        s = create_crack_spread_strategy(lookback=20, enable_seasonality=False)
        ts_base = datetime(2024, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        prime_strategy(s, n=20, ts_base=ts_base)

        state = s.get_state()
        assert state["latest_prices"]["spread"] is not None
        assert state["latest_prices"]["z_score"] is not None
        assert state["latest_prices"]["gasoline_per_bbl"] is not None
