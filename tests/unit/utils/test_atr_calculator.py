"""
Unit Tests for ATRCalculator

Covers:
  1. True Range calculation (with and without previous close)
  2. ATR calculation using Wilder's smoothing (period + 1 candles minimum)
  3. Insufficient data returns None
  4. Caching: get_or_calculate returns cached value; cache TTL expiry
  5. Fallback distance calculation
  6. Cache clearing (by symbol and all symbols)

All assertions use real calculations with known values — no mocks.
"""

import time

import pytest

from src.utils.atr_calculator import ATRCalculator, OHLCCandle


# ============================================================================
# Helpers
# ============================================================================


def make_candles(specs: list[tuple[float, float, float, float]]) -> list[OHLCCandle]:
    """Create a list of OHLCCandle from (open, high, low, close) tuples."""
    return [OHLCCandle(open=o, high=h, low=l, close=c) for o, h, l, c in specs]


def minimal_candles(period: int = 14) -> list[OHLCCandle]:
    """
    Build period+1 candles with deterministic, easy-to-verify values.

    Each candle has high=low+1 (TR=1 when standalone) and prev_close == low,
    so all true ranges are 1.0.  ATR for any period on such data is also 1.0.
    """
    candles = []
    for i in range(period + 1):
        base = float(100 + i)
        candles.append(OHLCCandle(open=base, high=base + 1.0, low=base, close=base + 0.5))
    return candles


# ============================================================================
# True Range Calculation
# ============================================================================


class TestTrueRange:
    """Test calculate_true_range for all branches."""

    def test_true_range_without_prev_close_uses_high_minus_low(self):
        """
        When no previous close is supplied TR = H - L.
        Candle: H=105, L=100  →  TR = 5.0
        """
        calc = ATRCalculator()
        candle = OHLCCandle(open=102.0, high=105.0, low=100.0, close=103.0)
        assert calc.calculate_true_range(candle) == pytest.approx(5.0)

    def test_true_range_high_low_dominates(self):
        """
        H-L is larger than both |H-C_prev| and |L-C_prev|.
        H=110, L=100, C_prev=105  →  H-L=10, |H-C|=5, |L-C|=5  →  TR=10.
        """
        calc = ATRCalculator()
        candle = OHLCCandle(open=104.0, high=110.0, low=100.0, close=107.0)
        assert calc.calculate_true_range(candle, prev_close=105.0) == pytest.approx(10.0)

    def test_true_range_high_close_dominates(self):
        """
        Gap-up: previous close well below today's low.
        H=120, L=115, C_prev=100  →  H-L=5, |H-C|=20, |L-C|=15  →  TR=20.
        """
        calc = ATRCalculator()
        candle = OHLCCandle(open=115.0, high=120.0, low=115.0, close=118.0)
        assert calc.calculate_true_range(candle, prev_close=100.0) == pytest.approx(20.0)

    def test_true_range_low_close_dominates(self):
        """
        Gap-down: previous close well above today's high.
        H=85, L=80, C_prev=100  →  H-L=5, |H-C|=15, |L-C|=20  →  TR=20.
        """
        calc = ATRCalculator()
        candle = OHLCCandle(open=82.0, high=85.0, low=80.0, close=82.0)
        assert calc.calculate_true_range(candle, prev_close=100.0) == pytest.approx(20.0)

    def test_true_range_zero_range_candle(self):
        """Doji candle with no gap: H=L=C=C_prev → TR=0."""
        calc = ATRCalculator()
        candle = OHLCCandle(open=50.0, high=50.0, low=50.0, close=50.0)
        assert calc.calculate_true_range(candle, prev_close=50.0) == pytest.approx(0.0)

    def test_true_range_exact_tie_high_low_and_high_close(self):
        """
        All three components equal.
        H=110, L=100, C_prev=100  →  H-L=10, |H-C|=10, |L-C|=0  →  TR=10.
        """
        calc = ATRCalculator()
        candle = OHLCCandle(open=105.0, high=110.0, low=100.0, close=105.0)
        assert calc.calculate_true_range(candle, prev_close=100.0) == pytest.approx(10.0)


# ============================================================================
# ATR Calculation (Wilder's Smoothing)
# ============================================================================


class TestATRCalculation:
    """Test calculate() with verified hand-computed results."""

    def test_minimum_candles_all_tr_equal(self):
        """
        15 candles (period=14), each successive candle shifts up by 1 point.

        Candle i: open=100+i, high=101+i, low=100+i, close=100.5+i
        TR for candle i (i>=1) vs prev close=(100.5+i-1):
          H-L = 1.0
          |H - C_prev| = |(101+i) - (99.5+i)| = 1.5   ← dominates
          |L - C_prev| = |(100+i) - (99.5+i)| = 0.5
        So all TR = 1.5, and ATR = 1.5 (no extra smoothing candles).
        """
        calc = ATRCalculator()
        candles = minimal_candles(period=14)
        result = calc.calculate(candles, period=14)
        assert result == pytest.approx(1.5, abs=1e-5)

    def test_atr_extra_smoothing_candles(self):
        """
        20 candles, period=5, with all TR equal (Wilder smoothing stays flat).

        Candle i: base=100+2*i, H=base+1, L=base-1, C=base
        TR for candle i (i>=1) vs prev close = 100+2*(i-1):
          H-L = 2
          |H - C_prev| = |(base+1) - (base-2)| = 3  ← dominates
          |L - C_prev| = |(base-1) - (base-2)| = 1
        All TR = 3.0.

        Initial ATR (first 5 TR values) = 3.0
        Wilder steps: ATR = ((3*4) + 3)/5 = 3.0  (stays 3.0)
        """
        candles = []
        for i in range(20):
            base = float(100 + i * 2)
            candles.append(OHLCCandle(open=base, high=base + 1.0, low=base - 1.0, close=base))
        calc = ATRCalculator()
        result = calc.calculate(candles, period=5)
        assert result == pytest.approx(3.0, abs=1e-5)

    def test_wilder_smoothing_converges_to_new_tr(self):
        """
        After stable candles, a single large TR smooths in via Wilder's formula.

        Setup: period=3, 4 candles all TR=1 (stable), then 1 candle with TR=4.

        Candles (open, high, low, close):
          0: (10, 11, 10, 10.5)  — seed
          1: (10.5, 11.5, 10.5, 11.0)  TR vs close=10.5: max(1, 1, 0)=1
          2: (11.0, 12.0, 11.0, 11.5)  TR vs close=11.0: max(1, 1, 0)=1
          3: (11.5, 12.5, 11.5, 12.0)  TR vs close=11.5: max(1, 1, 0)=1
          4: (12.0, 16.0, 12.0, 14.0)  TR vs close=12.0: max(4, 4, 0)=4

        true_ranges: [1, 1, 1, 4]  (4 ranges for 5 candles, period=3 needs >=3)
        Initial ATR = (1+1+1)/3 = 1.0
        Wilder step 1: ((1.0 * 2) + 4) / 3 = 6/3 = 2.0
        """
        candles = [
            OHLCCandle(open=10.0,  high=11.0,  low=10.0,  close=10.5),
            OHLCCandle(open=10.5, high=11.5, low=10.5, close=11.0),
            OHLCCandle(open=11.0, high=12.0, low=11.0, close=11.5),
            OHLCCandle(open=11.5, high=12.5, low=11.5, close=12.0),
            OHLCCandle(open=12.0, high=16.0, low=12.0, close=14.0),
        ]
        calc = ATRCalculator()
        result = calc.calculate(candles, period=3)
        assert result == pytest.approx(2.0, abs=1e-5)

    def test_atr_period_3_two_smoothing_steps(self):
        """
        period=3, 6 candles → 5 TR values → initial ATR from first 3, then 2 smoothing steps.

        Candle i: base=100+2*i, H=base+2, L=base, C=base+1
        TR for candle i (i>=1) vs prev close = (base-2)+1 = base-1:
          H-L = 2
          |H - C_prev| = |(base+2) - (base-1)| = 3  ← dominates
          |L - C_prev| = |(base)   - (base-1)| = 1
        All TR = 3.0.

        Initial ATR = (3+3+3)/3 = 3.0
        Step 1: ((3*2) + 3)/3 = 3.0
        Step 2: ((3*2) + 3)/3 = 3.0
        Result: 3.0
        """
        candles = []
        for i in range(6):
            base = float(100 + i * 2)
            candles.append(OHLCCandle(open=base, high=base + 2.0, low=base, close=base + 1.0))
        calc = ATRCalculator()
        result = calc.calculate(candles, period=3)
        assert result == pytest.approx(3.0, abs=1e-5)

    def test_atr_result_is_rounded_to_six_decimal_places(self):
        """calculate() always returns a value rounded to 6 decimal places."""
        candles = minimal_candles(period=3)
        calc = ATRCalculator()
        result = calc.calculate(candles, period=3)
        assert result is not None
        # Verify no more than 6 decimal places
        formatted = f"{result:.10f}"
        decimal_part = formatted.split(".")[1]
        assert decimal_part[6:] == "0" * (len(decimal_part) - 6)

    def test_atr_without_symbol_does_not_cache(self):
        """When symbol='' (default), result is not stored in cache."""
        calc = ATRCalculator()
        candles = minimal_candles(period=14)
        calc.calculate(candles, period=14, symbol="")
        assert len(calc._cache) == 0

    def test_atr_with_symbol_stores_in_cache(self):
        """When a symbol is provided, the result is stored in the cache."""
        calc = ATRCalculator()
        candles = minimal_candles(period=14)
        result = calc.calculate(candles, period=14, symbol="XAUUSD", timeframe="H1")
        assert "XAUUSD:H1:14" in calc._cache
        assert calc._cache["XAUUSD:H1:14"].value == result


# ============================================================================
# Insufficient Data
# ============================================================================


class TestInsufficientData:
    """calculate() must return None when there are not enough candles."""

    def test_zero_candles_returns_none(self):
        calc = ATRCalculator()
        assert calc.calculate([], period=14) is None

    def test_exactly_period_candles_returns_none(self):
        """period=14 requires period+1=15 candles; 14 is not enough."""
        calc = ATRCalculator()
        candles = minimal_candles(period=14)[:14]  # only 14
        assert calc.calculate(candles, period=14) is None

    def test_period_minus_one_candles_returns_none(self):
        """13 candles for period=14 → insufficient."""
        calc = ATRCalculator()
        candles = minimal_candles(period=14)[:13]
        assert calc.calculate(candles, period=14) is None

    def test_one_candle_returns_none(self):
        calc = ATRCalculator()
        candles = [OHLCCandle(open=100.0, high=101.0, low=99.0, close=100.5)]
        assert calc.calculate(candles, period=14) is None

    def test_exactly_period_plus_one_candles_returns_value(self):
        """period+1 candles is the exact minimum; must succeed."""
        calc = ATRCalculator()
        candles = minimal_candles(period=14)  # exactly 15
        result = calc.calculate(candles, period=14)
        assert result is not None
        assert result > 0.0

    def test_small_period_insufficient_candles(self):
        """period=5 needs 6 candles; 5 is insufficient."""
        calc = ATRCalculator()
        candles = minimal_candles(period=5)[:5]
        assert calc.calculate(candles, period=5) is None


# ============================================================================
# Caching Behaviour
# ============================================================================


class TestCaching:
    """Test get_cached, get_or_calculate caching, and TTL expiry."""

    def test_get_cached_returns_none_before_any_calculation(self):
        calc = ATRCalculator()
        assert calc.get_cached("EURUSD", "H1", 14) is None

    def test_get_cached_returns_value_after_calculate(self):
        calc = ATRCalculator()
        candles = minimal_candles(period=14)
        expected = calc.calculate(candles, period=14, symbol="EURUSD", timeframe="H1")
        cached = calc.get_cached("EURUSD", "H1", 14)
        assert cached == pytest.approx(expected)

    def test_get_or_calculate_returns_cached_without_recalculating(self):
        """
        After the first call, get_or_calculate returns the cached value
        even when called with candles=None.
        """
        calc = ATRCalculator()
        candles = minimal_candles(period=14)
        first = calc.get_or_calculate("GBPUSD", candles=candles, timeframe="H4", period=14)
        # Second call: no candles supplied → must use cache
        second = calc.get_or_calculate("GBPUSD", candles=None, timeframe="H4", period=14)
        assert first is not None
        assert second == pytest.approx(first)

    def test_get_or_calculate_returns_none_when_no_cache_and_no_candles(self):
        calc = ATRCalculator()
        result = calc.get_or_calculate("USDJPY", candles=None, timeframe="H1", period=14)
        assert result is None

    def test_cache_ttl_expiry_removes_stale_entry(self):
        """
        A cache entry older than cache_ttl_seconds must not be returned.
        Use ttl=0.01 seconds so we can expire it without sleeping long.
        """
        calc = ATRCalculator(cache_ttl_seconds=0.01)
        candles = minimal_candles(period=14)
        calc.calculate(candles, period=14, symbol="USDCAD", timeframe="M15")

        # Value should be cached immediately
        assert calc.get_cached("USDCAD", "M15", 14) is not None

        # Wait for TTL to expire
        time.sleep(0.05)

        # Now the cache entry must be gone
        assert calc.get_cached("USDCAD", "M15", 14) is None

    def test_expired_entry_is_removed_from_cache_dict(self):
        """
        After expiry, get_cached deletes the entry from _cache so the dict
        does not grow unboundedly with stale keys.
        """
        calc = ATRCalculator(cache_ttl_seconds=0.01)
        candles = minimal_candles(period=14)
        calc.calculate(candles, period=14, symbol="AUDUSD", timeframe="H1")
        assert "AUDUSD:H1:14" in calc._cache

        time.sleep(0.05)
        calc.get_cached("AUDUSD", "H1", 14)  # triggers deletion

        assert "AUDUSD:H1:14" not in calc._cache

    def test_cache_key_includes_symbol_timeframe_period(self):
        """Different (symbol, timeframe, period) combinations are stored separately."""
        calc = ATRCalculator()
        candles = minimal_candles(period=14)
        calc.calculate(candles, period=14, symbol="XAUUSD", timeframe="H1")
        calc.calculate(candles, period=14, symbol="XAUUSD", timeframe="H4")
        calc.calculate(candles, period=5, symbol="XAUUSD", timeframe="H1")

        assert "XAUUSD:H1:14" in calc._cache
        assert "XAUUSD:H4:14" in calc._cache
        assert "XAUUSD:H1:5" in calc._cache

    def test_fresh_cache_entry_is_not_expired(self):
        """A newly stored entry (ttl=60s) is returned without delay."""
        calc = ATRCalculator(cache_ttl_seconds=60.0)
        candles = minimal_candles(period=14)
        calc.calculate(candles, period=14, symbol="NZDUSD", timeframe="D1")
        assert calc.get_cached("NZDUSD", "D1", 14) is not None


# ============================================================================
# Fallback Distance Calculation
# ============================================================================


class TestFallbackDistance:
    """Test get_fallback_distance using percentage of entry price."""

    def test_default_two_percent_fallback(self):
        """Default fallback_percentage=0.02; distance = entry * 0.02."""
        calc = ATRCalculator()
        assert calc.get_fallback_distance(100.0) == pytest.approx(2.0)

    def test_crude_oil_price_fallback(self):
        """Crude oil at $75.50 → 2% = $1.51."""
        calc = ATRCalculator()
        assert calc.get_fallback_distance(75.50) == pytest.approx(1.51)

    def test_gold_price_fallback(self):
        """Gold at $2650 → 2% = $53.00."""
        calc = ATRCalculator()
        assert calc.get_fallback_distance(2650.0) == pytest.approx(53.0)

    def test_custom_fallback_percentage(self):
        """A 1% fallback_percentage → distance = entry * 0.01."""
        calc = ATRCalculator(fallback_percentage=0.01)
        assert calc.get_fallback_distance(200.0) == pytest.approx(2.0)

    def test_fallback_distance_always_positive(self):
        """Fallback distance must be strictly positive for any valid price."""
        calc = ATRCalculator()
        assert calc.get_fallback_distance(0.001) > 0.0
        assert calc.get_fallback_distance(10_000.0) > 0.0


# ============================================================================
# Cache Clearing
# ============================================================================


class TestCacheClearing:
    """Test clear_cache for a specific symbol and for all symbols."""

    def _populate_cache(self, calc: ATRCalculator) -> None:
        """Helper: store three distinct cache entries."""
        candles = minimal_candles(period=14)
        calc.calculate(candles, period=14, symbol="EURUSD", timeframe="H1")
        calc.calculate(candles, period=14, symbol="GBPUSD", timeframe="H1")
        calc.calculate(candles, period=14, symbol="EURUSD", timeframe="H4")

    def test_clear_all_removes_every_entry(self):
        calc = ATRCalculator()
        self._populate_cache(calc)
        assert len(calc._cache) == 3

        calc.clear_cache()  # no symbol → clear all

        assert len(calc._cache) == 0

    def test_clear_by_symbol_removes_only_that_symbol(self):
        calc = ATRCalculator()
        self._populate_cache(calc)

        calc.clear_cache(symbol="EURUSD")

        # EURUSD entries gone
        assert "EURUSD:H1:14" not in calc._cache
        assert "EURUSD:H4:14" not in calc._cache
        # GBPUSD entry untouched
        assert "GBPUSD:H1:14" in calc._cache

    def test_clear_by_symbol_removes_all_timeframes_for_that_symbol(self):
        """Clearing by symbol removes entries across multiple timeframes."""
        calc = ATRCalculator()
        candles = minimal_candles(period=14)
        calc.calculate(candles, period=14, symbol="USDJPY", timeframe="M15")
        calc.calculate(candles, period=14, symbol="USDJPY", timeframe="H1")
        calc.calculate(candles, period=14, symbol="USDJPY", timeframe="D1")

        calc.clear_cache(symbol="USDJPY")

        assert len(calc._cache) == 0

    def test_clear_nonexistent_symbol_is_safe(self):
        """Clearing a symbol that has no cache entries does not raise."""
        calc = ATRCalculator()
        self._populate_cache(calc)
        # Should not raise even if symbol not in cache
        calc.clear_cache(symbol="XAUUSD")
        assert len(calc._cache) == 3  # other entries unaffected

    def test_clear_all_on_empty_cache_is_safe(self):
        """Calling clear_cache() on an empty cache does not raise."""
        calc = ATRCalculator()
        calc.clear_cache()  # no entries, must not raise
        assert len(calc._cache) == 0

    def test_cached_value_not_returned_after_clear(self):
        """After clearing, get_cached returns None for the cleared symbol."""
        calc = ATRCalculator()
        candles = minimal_candles(period=14)
        calc.calculate(candles, period=14, symbol="CHFJPY", timeframe="H1")

        assert calc.get_cached("CHFJPY", "H1", 14) is not None

        calc.clear_cache(symbol="CHFJPY")

        assert calc.get_cached("CHFJPY", "H1", 14) is None


# ============================================================================
# Integration: end-to-end get_or_calculate flow
# ============================================================================


class TestGetOrCalculateIntegration:
    """End-to-end scenarios combining calculation, caching, and clearing."""

    def test_full_flow_calculate_cache_retrieve_clear(self):
        """
        1. Calculate ATR with candles → cached.
        2. Retrieve from cache (candles=None).
        3. Clear cache.
        4. Next call with candles=None returns None.
        """
        calc = ATRCalculator()
        candles = minimal_candles(period=14)

        # Step 1: calculate and cache
        value = calc.get_or_calculate("AUDNZD", candles=candles, timeframe="H1", period=14)
        assert value is not None

        # Step 2: retrieve from cache
        from_cache = calc.get_or_calculate("AUDNZD", candles=None, timeframe="H1", period=14)
        assert from_cache == pytest.approx(value)

        # Step 3: clear cache
        calc.clear_cache(symbol="AUDNZD")

        # Step 4: no candles → None
        after_clear = calc.get_or_calculate("AUDNZD", candles=None, timeframe="H1", period=14)
        assert after_clear is None

    def test_recalculate_after_expiry_stores_fresh_entry(self):
        """
        After TTL expiry, providing new candles recalculates and re-caches.
        """
        calc = ATRCalculator(cache_ttl_seconds=0.01)
        candles = minimal_candles(period=14)

        first = calc.get_or_calculate("CADCHF", candles=candles, timeframe="H1", period=14)
        assert first is not None

        time.sleep(0.05)  # let TTL expire

        # Provide candles again → must recalculate
        second = calc.get_or_calculate("CADCHF", candles=candles, timeframe="H1", period=14)
        assert second is not None
        assert second == pytest.approx(first)

        # Fresh entry must now be in cache again
        assert calc.get_cached("CADCHF", "H1", 14) is not None
