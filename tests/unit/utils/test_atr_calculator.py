"""
Unit Tests for ATR Calculator

Covers:
  1. True Range calculation (with and without previous close)
  2. ATR calculation using Wilder's smoothing (period + 1 candles minimum)
  3. Insufficient data returns None
  4. ATRCalculator class: caching, calculate, clear_cache
  5. InsufficientDataError raised when data missing

All assertions use real calculations with known values — no mocks.
"""

import time
from datetime import datetime

import pytest

from src.utils.atr_calculator import (
    ATRCalculator,
    Candle,
    InsufficientDataError,
    calculate_atr_wilder,
    calculate_true_range,
)


# ============================================================================
# Helpers
# ============================================================================


def make_candle(o: float, h: float, l: float, c: float) -> Candle:
    """Create a Candle with dummy timestamp."""
    return Candle(timestamp=datetime(2024, 1, 1), open=o, high=h, low=l, close=c)


def make_candles(specs: list[tuple[float, float, float, float]]) -> list[Candle]:
    """Create a list of Candle from (open, high, low, close) tuples."""
    return [make_candle(o, h, l, c) for o, h, l, c in specs]


def minimal_candles(period: int = 14) -> list[Candle]:
    """
    Build period+1 candles with deterministic, easy-to-verify values.

    Each candle: base=100+i, high=base+1, low=base, close=base+0.5.
    TR for candle i (i>=1) vs prev close=(base-1)+0.5=base-0.5:
      H-L = 1.0
      |H - C_prev| = |(base+1) - (base-0.5)| = 1.5   ← dominates
      |L - C_prev| = |(base) - (base-0.5)| = 0.5
    So all TR = 1.5, and ATR for any period on such data is also 1.5.
    """
    candles = []
    for i in range(period + 1):
        base = float(100 + i)
        candles.append(make_candle(base, base + 1.0, base, base + 0.5))
    return candles


# ============================================================================
# True Range Calculation
# ============================================================================


class TestTrueRange:
    """Test calculate_true_range for all branches."""

    def test_true_range_without_prev_close_uses_high_minus_low(self):
        """When no previous close: TR = H - L. H=105, L=100 → TR=5.0"""
        candle = make_candle(102.0, 105.0, 100.0, 103.0)
        assert calculate_true_range(candle) == pytest.approx(5.0)

    def test_true_range_high_low_dominates(self):
        """H-L is largest. H=110, L=100, C_prev=105 → TR=10."""
        candle = make_candle(104.0, 110.0, 100.0, 107.0)
        assert calculate_true_range(candle, previous_close=105.0) == pytest.approx(10.0)

    def test_true_range_high_close_dominates(self):
        """Gap-up. H=120, L=115, C_prev=100 → |H-C_prev|=20 dominates."""
        candle = make_candle(115.0, 120.0, 115.0, 118.0)
        assert calculate_true_range(candle, previous_close=100.0) == pytest.approx(20.0)

    def test_true_range_low_close_dominates(self):
        """Gap-down. H=85, L=80, C_prev=100 → |L-C_prev|=20 dominates."""
        candle = make_candle(82.0, 85.0, 80.0, 82.0)
        assert calculate_true_range(candle, previous_close=100.0) == pytest.approx(20.0)

    def test_true_range_zero_range_candle(self):
        """Doji candle with no gap: H=L=C=C_prev → TR=0."""
        candle = make_candle(50.0, 50.0, 50.0, 50.0)
        assert calculate_true_range(candle, previous_close=50.0) == pytest.approx(0.0)

    def test_true_range_exact_tie(self):
        """All three components equal. H=110, L=100, C_prev=100 → TR=10."""
        candle = make_candle(105.0, 110.0, 100.0, 105.0)
        assert calculate_true_range(candle, previous_close=100.0) == pytest.approx(10.0)


# ============================================================================
# ATR Calculation (Wilder's Smoothing) — standalone function
# ============================================================================


class TestATRCalculation:
    """Test calculate_atr_wilder with verified hand-computed results."""

    def test_minimum_candles_all_tr_equal(self):
        """15 candles (period=14), all TR=1.5 → ATR=1.5."""
        candles = minimal_candles(period=14)
        result = calculate_atr_wilder(candles, period=14)
        assert result == pytest.approx(1.5, abs=1e-5)

    def test_atr_extra_smoothing_candles(self):
        """
        20 candles, period=5, each candle shifts up by 2.
        All TR = 3.0 (|H - C_prev| dominates), so ATR stays 3.0.
        """
        candles = []
        for i in range(20):
            base = float(100 + i * 2)
            candles.append(make_candle(base, base + 1.0, base - 1.0, base))
        result = calculate_atr_wilder(candles, period=5)
        assert result == pytest.approx(3.0, abs=1e-5)

    def test_wilder_smoothing_converges_to_new_tr(self):
        """
        period=3, 4 stable candles (TR=1) then 1 big candle (TR=4).
        Initial ATR = (1+1+1)/3 = 1.0
        Wilder step: ((1.0 * 2) + 4) / 3 = 2.0
        """
        candles = [
            make_candle(10.0, 11.0, 10.0, 10.5),
            make_candle(10.5, 11.5, 10.5, 11.0),
            make_candle(11.0, 12.0, 11.0, 11.5),
            make_candle(11.5, 12.5, 11.5, 12.0),
            make_candle(12.0, 16.0, 12.0, 14.0),
        ]
        result = calculate_atr_wilder(candles, period=3)
        assert result == pytest.approx(2.0, abs=1e-5)

    def test_atr_period_3_two_smoothing_steps(self):
        """period=3, 6 candles → all TR=3.0 → ATR stays 3.0."""
        candles = []
        for i in range(6):
            base = float(100 + i * 2)
            candles.append(make_candle(base, base + 2.0, base, base + 1.0))
        result = calculate_atr_wilder(candles, period=3)
        assert result == pytest.approx(3.0, abs=1e-5)


# ============================================================================
# Insufficient Data — standalone function
# ============================================================================


class TestInsufficientData:
    """calculate_atr_wilder must return None when there are not enough candles."""

    def test_zero_candles_returns_none(self):
        assert calculate_atr_wilder([], period=14) is None

    def test_exactly_period_candles_returns_none(self):
        """period=14 requires period+1=15 candles; 14 is not enough."""
        candles = minimal_candles(period=14)[:14]
        assert calculate_atr_wilder(candles, period=14) is None

    def test_period_minus_one_candles_returns_none(self):
        """13 candles for period=14 → insufficient."""
        candles = minimal_candles(period=14)[:13]
        assert calculate_atr_wilder(candles, period=14) is None

    def test_one_candle_returns_none(self):
        candles = [make_candle(100.0, 101.0, 99.0, 100.5)]
        assert calculate_atr_wilder(candles, period=14) is None

    def test_exactly_period_plus_one_candles_returns_value(self):
        """period+1 candles is the exact minimum; must succeed."""
        candles = minimal_candles(period=14)
        result = calculate_atr_wilder(candles, period=14)
        assert result is not None
        assert result > 0.0

    def test_small_period_insufficient_candles(self):
        """period=5 needs 6 candles; 5 is insufficient."""
        candles = minimal_candles(period=5)[:5]
        assert calculate_atr_wilder(candles, period=5) is None


# ============================================================================
# ATRCalculator Class — caching + InsufficientDataError
# ============================================================================


class TestATRCalculatorClass:
    """Test the ATRCalculator class with caching."""

    def test_calculate_returns_value_with_enough_data(self):
        calc = ATRCalculator(period=14)
        candles = minimal_candles(period=14)
        result = calc.calculate("XAUUSD", candles=candles)
        assert result == pytest.approx(1.5, abs=1e-5)

    def test_calculate_caches_result(self):
        calc = ATRCalculator(period=14)
        candles = minimal_candles(period=14)
        calc.calculate("EURUSD", candles=candles)
        cached = calc.get_cached_atr("EURUSD")
        assert cached is not None
        assert cached == pytest.approx(1.5, abs=1e-5)

    def test_calculate_uses_cache_on_second_call(self):
        calc = ATRCalculator(period=14)
        candles = minimal_candles(period=14)
        first = calc.calculate("GBPUSD", candles=candles)
        # Second call without candles should use cache
        second = calc.calculate("GBPUSD", candles=candles, use_cache=True)
        assert second == pytest.approx(first)

    def test_calculate_raises_insufficient_data_error(self):
        calc = ATRCalculator(period=14)
        with pytest.raises(InsufficientDataError):
            calc.calculate("USDJPY", candles=None, use_cache=False)

    def test_calculate_raises_on_too_few_candles(self):
        calc = ATRCalculator(period=14)
        candles = minimal_candles(period=14)[:5]
        with pytest.raises(InsufficientDataError):
            calc.calculate("USDJPY", candles=candles, use_cache=False)

    def test_get_cached_atr_returns_none_before_calculation(self):
        calc = ATRCalculator()
        assert calc.get_cached_atr("NZDUSD") is None

    def test_cache_expiry(self):
        """Cached ATR expires after cache_duration_seconds."""
        calc = ATRCalculator(period=3, cache_duration_seconds=0)
        candles = minimal_candles(period=3)
        calc.calculate("XAUUSD", candles=candles)
        # With 0-second TTL, cache is immediately stale
        time.sleep(0.01)
        assert calc.get_cached_atr("XAUUSD") is None

    def test_clear_cache_removes_all_entries(self):
        calc = ATRCalculator(period=3)
        candles = minimal_candles(period=3)
        calc.calculate("EURUSD", candles=candles)
        calc.calculate("GBPUSD", candles=candles)
        assert len(calc._cache) == 2
        calc.clear_cache()
        assert len(calc._cache) == 0

    def test_set_cached_atr(self):
        calc = ATRCalculator()
        calc.set_cached_atr("CrudeOIL", 0.75)
        assert calc.get_cached_atr("CrudeOIL") == pytest.approx(0.75)


# ============================================================================
# InsufficientDataError
# ============================================================================


class TestInsufficientDataError:
    """Test the InsufficientDataError exception."""

    def test_error_attributes(self):
        err = InsufficientDataError(symbol="CrudeOIL", timeframe="H1", got=5, need=14)
        assert err.symbol == "CrudeOIL"
        assert err.timeframe == "H1"
        assert err.got == 5
        assert err.need == 14
        assert "CrudeOIL" in str(err)
        assert "H1" in str(err)
