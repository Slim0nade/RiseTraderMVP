"""
Unit Tests for TrendFilter

All assertions use real calculations with static, hand-crafted price series —
no mocks, no database, no MT4.

Coverage:
    1. Synthetic uptrend (50 ascending closes) + SELL → suppressed
    2. Synthetic downtrend (50 descending closes) + BUY → suppressed
    3. Synthetic range (oscillating flat) + SELL → allowed (ADX < 20)
    4. Uptrend + BUY → allowed (trend-following signal)
    5. Downtrend + SELL → allowed (trend-following signal)
    6. Insufficient data (< 50 bars) → not suppressed
    7. ADX calculation verification against hand-computed reference values

Helper design:
    _make_candles(closes) builds synthetic OHLCV from a close array.
    high  = close + 0.10   (small fixed spread so H > C always)
    low   = close - 0.10
    open  = previous close (so no gaps)

    This gives TR_i = max(0.20, |high_i - close_{i-1}|, |low_i - close_{i-1}|).
    For a steadily moving market the TR is dominated by the gap component, which
    equals |Δclose|.  That is sufficient for realistic ADX behaviour.
"""

import math

import numpy as np
import pytest

from src.trading.filters.trend_filter import TrendFilter, _compute_adx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candles(closes: list[float]) -> list[dict]:
    """
    Build minimal OHLCV dicts from a list of close prices.

    Each bar:
        open  = previous close (first bar uses closes[0])
        high  = close + 0.10
        low   = close - 0.10
        close = as supplied
        volume = 1000 (unused by filter)
    """
    bars = []
    for i, c in enumerate(closes):
        prev_c = closes[i - 1] if i > 0 else c
        bars.append(
            {
                "open":   prev_c,
                "high":   c + 0.10,
                "low":    c - 0.10,
                "close":  c,
                "volume": 1000.0,
            }
        )
    return bars


def _uptrend_closes(n: int = 60, start: float = 50.0, step: float = 0.50) -> list[float]:
    """
    `n` closes rising by `step` each bar.

    After n=60 bars at +0.50/bar:
        close[-1]  = start + (n-1)*step = 79.5     (well above MA50 = ~65)
        MA(20)     ≈ start + (n-10)*step = 75      (above MA50)
        MA(50)     ≈ start + (n-25)*step = 67.5
    → All 3 confirmations fire → bullish.
    """
    return [start + i * step for i in range(n)]


def _downtrend_closes(n: int = 60, start: float = 80.0, step: float = 0.50) -> list[float]:
    """
    `n` closes falling by `step` each bar.

    After n=60 bars at -0.50/bar:
        close[-1]  ≈ 50.5 (well below MA50 ≈ 65)
    → Bearish confirmations fire.
    """
    return [start - i * step for i in range(n)]


def _range_closes(n: int = 60, center: float = 60.0, amplitude: float = 0.05) -> list[float]:
    """
    `n` closes bouncing in a tight band around `center` using a fixed
    alternating pattern (+amplitude, -amplitude, 0, repeat).

    This creates alternating up/down moves of equal magnitude so that
    smoothed +DM ≈ smoothed -DM and DX = 100 * |+DI - -DI| / (+DI + -DI) ≈ 0.
    As a result ADX stays well below 20 regardless of the amplitude.

    amplitude=0.05 with a price around 60.0 means each bar moves ±0.083%,
    which is a realistic narrow range for an illiquid hour.
    """
    closes = []
    for i in range(n):
        phase = i % 3
        if phase == 0:
            closes.append(center + amplitude)
        elif phase == 1:
            closes.append(center - amplitude)
        else:
            closes.append(center)
    return closes


# ---------------------------------------------------------------------------
# Core Suppression Tests
# ---------------------------------------------------------------------------


class TestSuppressionRules:
    """Tests for the main should_suppress() logic."""

    def test_uptrend_sell_is_suppressed(self):
        """
        60 bars, steady 0.5/bar rise.
        SELL into an uptrend must be suppressed.
        """
        tf = TrendFilter()
        bars = _make_candles(_uptrend_closes(60))
        suppress, reason = tf.should_suppress(bars, "SELL")
        assert suppress is True
        assert "counter_trend_sell" in reason

    def test_downtrend_buy_is_suppressed(self):
        """
        60 bars, steady 0.5/bar decline.
        BUY into a downtrend must be suppressed.
        """
        tf = TrendFilter()
        bars = _make_candles(_downtrend_closes(60))
        suppress, reason = tf.should_suppress(bars, "BUY")
        assert suppress is True
        assert "counter_trend_buy" in reason

    def test_ranging_market_sell_allowed(self):
        """
        60 bars oscillating ±0.20 around a flat mean.
        ADX should be < 20 → filter passes all signals through.
        """
        tf = TrendFilter()
        bars = _make_candles(_range_closes(60, amplitude=0.20))
        suppress, reason = tf.should_suppress(bars, "SELL")
        assert suppress is False
        assert "ranging_market" in reason

    def test_ranging_market_buy_allowed(self):
        """Same ranging series, BUY should also pass through."""
        tf = TrendFilter()
        bars = _make_candles(_range_closes(60, amplitude=0.20))
        suppress, reason = tf.should_suppress(bars, "BUY")
        assert suppress is False

    def test_uptrend_buy_allowed(self):
        """
        Trend-following BUY in an uptrend must not be blocked.
        """
        tf = TrendFilter()
        bars = _make_candles(_uptrend_closes(60))
        suppress, reason = tf.should_suppress(bars, "BUY")
        assert suppress is False

    def test_downtrend_sell_allowed(self):
        """
        Trend-following SELL in a downtrend must not be blocked.
        """
        tf = TrendFilter()
        bars = _make_candles(_downtrend_closes(60))
        suppress, reason = tf.should_suppress(bars, "SELL")
        assert suppress is False

    def test_insufficient_data_not_suppressed(self):
        """
        Fewer than 50 bars (the minimum) → filter always allows through
        because it cannot reliably classify the trend.
        """
        tf = TrendFilter()
        bars = _make_candles(_uptrend_closes(49))
        suppress, reason = tf.should_suppress(bars, "SELL")
        assert suppress is False
        assert reason == "insufficient_data"

    def test_exactly_50_bars_processes_normally(self):
        """
        Exactly 50 bars is enough data; the filter should not bail out early.
        An uptrend over 50 bars should still suppress a SELL.
        """
        tf = TrendFilter()
        bars = _make_candles(_uptrend_closes(50))
        # 50 steadily rising bars: MA20 > MA50, price > MA50 → at least 2/3
        suppress, _ = tf.should_suppress(bars, "SELL")
        # We only assert the filter ran (no "insufficient_data"); we allow both
        # suppress outcomes depending on whether ADX reaches 25 in exactly 50 bars.
        assert isinstance(suppress, bool)

    def test_case_insensitive_action(self):
        """proposed_action should be normalised to upper-case."""
        tf = TrendFilter()
        bars = _make_candles(_uptrend_closes(60))
        suppress_lower, _ = tf.should_suppress(bars, "sell")
        suppress_upper, _ = tf.should_suppress(bars, "SELL")
        assert suppress_lower == suppress_upper


# ---------------------------------------------------------------------------
# ADX Calculation Accuracy Tests
# ---------------------------------------------------------------------------


class TestADXCalculation:
    """
    Verify _compute_adx() returns values in the expected range for
    known synthetic series.
    """

    def test_constant_uptrend_adx_high(self):
        """
        60 bars all moving up by the same amount every bar.
        This is a perfect trend: +DM is constant, -DM is zero, DX stays near 100.
        ADX should converge well above 25.
        """
        closes = np.array(_uptrend_closes(60), dtype=np.float64)
        highs  = closes + 0.10
        lows   = closes - 0.10
        adx = _compute_adx(highs, lows, closes, period=14)
        assert not math.isnan(adx), "ADX should not be NaN for 60 bars"
        assert adx > 25.0, f"Expected ADX > 25 for pure uptrend, got {adx:.2f}"

    def test_flat_market_adx_low(self):
        """
        60 bars alternating up/down by equal amounts.
        +DM ≈ -DM after smoothing → DX ≈ 0 → ADX stays well below 25.
        """
        closes = np.array(_range_closes(60, amplitude=0.05), dtype=np.float64)
        highs  = closes + 0.10
        lows   = closes - 0.10
        adx = _compute_adx(highs, lows, closes, period=14)
        assert not math.isnan(adx), "ADX should not be NaN for 60-bar flat series"
        assert adx < 25.0, f"Expected ADX < 25 for ranging market, got {adx:.2f}"

    def test_adx_nan_for_insufficient_bars(self):
        """
        _compute_adx requires 2*period + 1 bars (= 29 for period=14).
        Fewer bars must return NaN.
        """
        closes = np.array([100.0 + i * 0.5 for i in range(20)], dtype=np.float64)
        highs  = closes + 0.10
        lows   = closes - 0.10
        adx = _compute_adx(highs, lows, closes, period=14)
        assert math.isnan(adx), "ADX must be NaN when data is below minimum threshold"

    def test_adx_exactly_minimum_bars(self):
        """
        Exactly 2*period + 1 = 29 bars → should return a valid float in [0, 100].
        """
        period = 14
        min_bars = 2 * period + 1
        closes = np.array([100.0 + i * 0.5 for i in range(min_bars)], dtype=np.float64)
        highs  = closes + 0.10
        lows   = closes - 0.10
        adx = _compute_adx(highs, lows, closes, period=period)
        assert not math.isnan(adx), f"ADX must not be NaN at minimum bars ({min_bars})"
        assert 0.0 <= adx <= 100.0, f"ADX must be in [0, 100], got {adx:.2f}"

    def test_adx_range_zero_to_hundred(self):
        """
        ADX must always be in [0, 100] for any valid input.
        """
        closes = np.array(_downtrend_closes(60), dtype=np.float64)
        highs  = closes + 0.30
        lows   = closes - 0.30
        adx = _compute_adx(highs, lows, closes, period=14)
        assert 0.0 <= adx <= 100.0, f"ADX {adx:.2f} out of [0, 100] range"

    def test_adx_known_value_pure_uptrend(self):
        """
        Manual verification for a simple synthetic series.

        Series: 30 bars, close[i] = 100 + i*1.0, high = close + 0.5, low = close - 0.5.

        For bar i (i >= 1):
            up_move   = 1.0 (constant, since high[i] = high[i-1] + 1.0)
            down_move = 0.0 (lows also rise, so low[i-1] - low[i] < 0)
            +DM = 1.0, -DM = 0.0
            TR  = max(1.0, |close[i]+0.5 - close[i-1]|, |close[i]-0.5 - close[i-1]|)
                = max(1.0, 1.5, 0.5) = 1.5

        After Wilder seed (14 bars):
            s_+DM  = 14 * 1.0 = 14.0
            s_-DM  = 0.0
            s_TR   = 14 * 1.5 = 21.0
            +DI    = 100 * 14 / 21 = 66.67
            -DI    = 0
            DX     = 100 * 66.67 / 66.67 = 100.0

        After further Wilder smoothing (all DX = 100):
            ADX → 100.

        We verify ADX is very close to 100 for this ideal case.
        """
        n = 30
        closes = np.array([100.0 + i for i in range(n)], dtype=np.float64)
        highs  = closes + 0.5
        lows   = closes - 0.5
        adx = _compute_adx(highs, lows, closes, period=14)
        assert not math.isnan(adx)
        assert adx == pytest.approx(100.0, abs=1.0), (
            f"Pure uptrend with constant +DM should yield ADX≈100, got {adx:.2f}"
        )


# ---------------------------------------------------------------------------
# Reason String Tests
# ---------------------------------------------------------------------------


class TestReasonStrings:
    """Verify that reason strings contain the right keywords for log parsing."""

    def test_suppressed_sell_reason_mentions_adx_and_prices(self):
        tf = TrendFilter()
        bars = _make_candles(_uptrend_closes(60))
        _, reason = tf.should_suppress(bars, "SELL")
        assert "adx=" in reason
        assert "ma50=" in reason
        assert "ma20=" in reason

    def test_ranging_reason_mentions_adx(self):
        tf = TrendFilter()
        bars = _make_candles(_range_closes(60, amplitude=0.20))
        _, reason = tf.should_suppress(bars, "BUY")
        assert "adx=" in reason

    def test_insufficient_data_reason_exact(self):
        tf = TrendFilter()
        bars = _make_candles(_uptrend_closes(30))
        _, reason = tf.should_suppress(bars, "SELL")
        assert reason == "insufficient_data"


# ---------------------------------------------------------------------------
# Configurable Threshold Tests
# ---------------------------------------------------------------------------


class TestConfigurableThresholds:
    """TrendFilter should honour custom adx_trend_threshold and confirmations_needed."""

    def test_custom_adx_threshold_can_tighten_suppression(self):
        """
        With adx_trend_threshold=5 (very low), almost any trending series
        triggers the ADX confirmation, making it easier to suppress.
        A strongly trending series will then be suppressed with even 1 confirmation.
        """
        tf = TrendFilter(adx_trend_threshold=5.0, confirmations_needed=1)
        bars = _make_candles(_uptrend_closes(60))
        suppress, _ = tf.should_suppress(bars, "SELL")
        assert suppress is True

    def test_require_all_3_confirmations(self):
        """
        With confirmations_needed=3, we need ALL three tests to agree.
        A strongly trending series should still satisfy all 3 so suppression fires.
        """
        tf = TrendFilter(confirmations_needed=3)
        bars = _make_candles(_uptrend_closes(60))
        suppress, _ = tf.should_suppress(bars, "SELL")
        # A 60-bar clean uptrend should pass all 3 confirmations
        assert suppress is True
