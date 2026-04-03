"""
TrendFilter — suppresses reversal signals that oppose the dominant trend.

Problem this solves:
    The ML reversal model labels every new high as a "peak" SELL signal, even
    during strong uptrends.  Executing those shorts causes consistent losses.
    This filter uses three independent trend-confirmation tests to detect when
    the market is in a sustained directional move and blocks counter-trend
    entries.

Three-confirmation logic:
    1. Price vs MA(50)  : close[-1] > MA50  → bullish pressure
    2. MA(20) vs MA(50) : MA20 > MA50       → medium-term uptrend (golden-cross)
    3. ADX(14) > 25     : market is trending (directional, not ranging)

    Suppression rules:
        - 2 of 3 confirm uptrend  AND proposed action == "SELL" → suppress
        - 2 of 3 confirm downtrend AND proposed action == "BUY"  → suppress
        - ADX < 20 (ranging market)                              → allow all
          (reversal detectors are appropriate in ranging conditions)
        - < 50 bars supplied                                     → allow all
          (insufficient data to reliably classify trend)

ADX implementation: Wilder's Smoothed ADX(14), computed from scratch.

Input contract:
    prices : List[Dict]  — OHLCV dicts with keys 'open', 'high', 'low', 'close'
                           (and optionally 'volume').  Oldest bar first.
                           Minimum 50 entries required for reliable output.
    proposed_action : str — "BUY" or "SELL"

Output contract:
    (should_suppress: bool, reason: str)
    reason is a short human-readable string for log messages.

Edge cases:
    - All closes identical (flat market): ADX → 0 (or near 0) → ranging → allow
    - Exactly 50 bars: calculations proceed normally
    - 49 bars or fewer: returns (False, "insufficient_data")
    - DI denominator of 0 (no directional movement): DX set to 0
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# ADX Calculation — Wilder's Smoothed ADX(14)
# ---------------------------------------------------------------------------


def _wilder_smooth_dm(values: np.ndarray, period: int) -> np.ndarray:
    """
    Wilder's running-sum smoothing for DM+, DM-, and TR.

    Seed:      smoothed[0] = sum(values[:period])
    Recurrence: smoothed[i] = smoothed[i-1] - smoothed[i-1]/period + values[period-1+i]

    This accumulates raw DM/TR magnitudes.  The output has the same unit as the
    input (price units) and stays proportional to the instrument's ATR scale.

    Args:
        values: 1-D array, length >= period.  All values should be >= 0.
        period: smoothing lookback (14 for standard ADX).

    Returns:
        1-D array of length (len(values) - period + 1).  Element [0] is the seed.
    """
    n = len(values)
    out = np.empty(n - period + 1, dtype=np.float64)
    out[0] = float(np.sum(values[:period]))
    for i in range(1, len(out)):
        out[i] = out[i - 1] - out[i - 1] / period + values[period - 1 + i]
    return out


def _wilder_smooth_adx(dx_values: np.ndarray, period: int) -> np.ndarray:
    """
    Wilder's running-mean smoothing for ADX.

    This is a true Wilder EMA (running mean), not the accumulator used for DM/TR.

    Seed:      adx[0] = mean(dx_values[:period])
    Recurrence: adx[i] = adx[i-1] - adx[i-1]/period + dx_values[period-1+i]/period
              = adx[i-1] * (period-1)/period + dx_values[period-1+i]/period

    When DX is constant at c:
        Seed = c.  Next step = c - c/period + c/period = c.  Stable at c. ✓
    This keeps ADX bounded in [0, 100] since DX itself is in [0, 100].

    Args:
        dx_values: 1-D array of DX values in [0, 100], length >= period.
        period:    smoothing lookback (14 for standard ADX).

    Returns:
        1-D array of length (len(dx_values) - period + 1), values in [0, 100].
    """
    n = len(dx_values)
    out = np.empty(n - period + 1, dtype=np.float64)
    out[0] = float(np.mean(dx_values[:period]))
    for i in range(1, len(out)):
        out[i] = out[i - 1] - out[i - 1] / period + dx_values[period - 1 + i] / period
    return out


def _compute_adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    """
    Compute the final ADX value for the supplied price arrays using Wilder's
    smoothed method.

    Requires at least 2*period + 1 bars to produce a non-NaN ADX (one period
    to seed the smoothing + one period to smooth the DX values into ADX).
    Returns np.nan when there is insufficient data.

    Args:
        highs:   1-D array of bar high prices, oldest first.
        lows:    1-D array of bar low prices, oldest first.
        closes:  1-D array of bar close prices, oldest first.
        period:  ADX period (default 14).

    Returns:
        float in [0, 100].  Values > 25 indicate a trending market.
        Returns np.nan when data is insufficient.

    Wilder's ADX steps:
        For each bar i (starting at i=1, using i-1 as the previous bar):
            up_move   = high[i] - high[i-1]
            down_move = low[i-1] - low[i]
            +DM = up_move   if up_move > down_move and up_move > 0 else 0
            -DM = down_move if down_move > up_move and down_move > 0 else 0
            TR  = max(high[i] - low[i],
                      |high[i] - close[i-1]|,
                      |low[i]  - close[i-1]|)

        Smooth +DM, -DM, TR over `period` bars using Wilder smoothing.
        +DI = 100 * smooth(+DM) / smooth(TR)
        -DI = 100 * smooth(-DM) / smooth(TR)
        DX  = 100 * |+DI - -DI| / (+DI + -DI)   (0 when denominator == 0)
        ADX = Wilder smooth of DX over `period` bars → take final value.
    """
    n = len(highs)
    min_bars = 2 * period + 1
    if n < min_bars:
        return float("nan")

    # ---- Per-bar directional movement and true range ----
    # These arrays have n-1 elements (each bar vs its predecessor).
    up_move   = highs[1:]   - highs[:-1]          # positive = higher high
    down_move = lows[:-1]   - lows[1:]             # positive = lower low

    plus_dm  = np.where((up_move > down_move)   & (up_move   > 0), up_move,   0.0)
    minus_dm = np.where((down_move > up_move)   & (down_move > 0), down_move, 0.0)

    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:]  - closes[:-1]),
        ),
    )

    # ---- Wilder smoothing (accumulator for DM/TR) ----
    s_plus_dm  = _wilder_smooth_dm(plus_dm,  period)
    s_minus_dm = _wilder_smooth_dm(minus_dm, period)
    s_tr       = _wilder_smooth_dm(tr,       period)

    # ---- DI values (avoid divide-by-zero on perfectly flat TR) ----
    with np.errstate(invalid="ignore", divide="ignore"):
        plus_di  = np.where(s_tr > 0, 100.0 * s_plus_dm  / s_tr, 0.0)
        minus_di = np.where(s_tr > 0, 100.0 * s_minus_dm / s_tr, 0.0)

    # ---- DX ----
    di_sum  = plus_di + minus_di
    di_diff = np.abs(plus_di - minus_di)
    with np.errstate(invalid="ignore", divide="ignore"):
        dx = np.where(di_sum > 0, 100.0 * di_diff / di_sum, 0.0)

    # ---- ADX = Wilder mean-smoothing of DX (keeps output in [0, 100]) ----
    if len(dx) < period:
        return float("nan")

    adx_series = _wilder_smooth_adx(dx, period)
    return float(adx_series[-1])


# ---------------------------------------------------------------------------
# Public filter class
# ---------------------------------------------------------------------------


class TrendFilter:
    """
    Suppresses reversal signals that oppose the dominant trend.

    Configuration:
        ma_fast  (int): Fast MA period. Default 20.
        ma_slow  (int): Slow MA period. Default 50.
        adx_period (int): ADX lookback period. Default 14.
        adx_trend_threshold  (float): ADX level above which market is
            considered trending. Default 25.
        adx_ranging_threshold (float): ADX level below which market is
            considered ranging and ALL signals are allowed. Default 20.
        confirmations_needed (int): How many of the 3 tests must agree
            before suppression is applied. Default 2.
        min_bars (int): Minimum candle history required. If fewer bars are
            supplied, the filter always allows the signal. Default 50.

    Thread safety: instances are stateless between calls — safe to share.
    """

    def __init__(
        self,
        ma_fast: int = 20,
        ma_slow: int = 50,
        adx_period: int = 14,
        adx_trend_threshold: float = 25.0,
        adx_ranging_threshold: float = 20.0,
        confirmations_needed: int = 2,
        min_bars: int = 50,
    ) -> None:
        self._ma_fast = ma_fast
        self._ma_slow = ma_slow
        self._adx_period = adx_period
        self._adx_trend_threshold = adx_trend_threshold
        self._adx_ranging_threshold = adx_ranging_threshold
        self._confirmations_needed = confirmations_needed
        self._min_bars = min_bars

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_suppress(
        self,
        prices: List[Dict],
        proposed_action: str,
    ) -> Tuple[bool, str]:
        """
        Decide whether to suppress a proposed entry signal.

        Args:
            prices: OHLCV dicts with keys 'open', 'high', 'low', 'close'.
                    Must be sorted oldest-first.  Minimum self.min_bars
                    entries for reliable output; fewer returns (False,
                    "insufficient_data").
            proposed_action: "BUY" or "SELL" (case-insensitive).

        Returns:
            (should_suppress, reason)
                should_suppress: True  → caller should discard the signal.
                                 False → caller may proceed.
                reason: short description suitable for log messages.

        Edge cases:
            - Fewer than min_bars supplied → (False, "insufficient_data")
            - Ranging market (ADX < adx_ranging_threshold) → (False, "ranging_market_adx={adx:.1f}")
            - Trend confirmed but signal is WITH the trend → (False, "signal_with_trend")
            - Trend confirmed and signal is AGAINST the trend → (True, reason string)
        """
        action = proposed_action.upper()

        if len(prices) < self._min_bars:
            return False, "insufficient_data"

        closes = np.array([float(p["close"]) for p in prices], dtype=np.float64)
        highs  = np.array([float(p["high"])  for p in prices], dtype=np.float64)
        lows   = np.array([float(p["low"])   for p in prices], dtype=np.float64)

        # ---- Compute indicators ----
        ma_fast = float(np.mean(closes[-self._ma_fast:]))
        ma_slow = float(np.mean(closes[-self._ma_slow:]))
        current_close = closes[-1]

        adx = _compute_adx(highs, lows, closes, period=self._adx_period)

        # ---- Ranging guard: ADX below floor → allow all signals ----
        if not np.isnan(adx) and adx < self._adx_ranging_threshold:
            return False, f"ranging_market_adx={adx:.1f}"

        # ---- Count bullish / bearish confirmations ----
        # Test 1: price vs slow MA
        price_vs_ma_bullish  = current_close > ma_slow
        price_vs_ma_bearish  = current_close < ma_slow

        # Test 2: fast MA vs slow MA (trend alignment / golden-cross region)
        ma_cross_bullish = ma_fast > ma_slow
        ma_cross_bearish = ma_fast < ma_slow

        # Test 3: ADX confirms trending
        adx_trending = (not np.isnan(adx)) and (adx >= self._adx_trend_threshold)

        bullish_count = sum([price_vs_ma_bullish, ma_cross_bullish, adx_trending])
        bearish_count = sum([price_vs_ma_bearish, ma_cross_bearish, adx_trending])

        # ---- Suppression decision ----
        if action == "SELL" and bullish_count >= self._confirmations_needed:
            return (
                True,
                (
                    f"counter_trend_sell: uptrend confirmed "
                    f"({bullish_count}/3 tests, adx={adx:.1f}, "
                    f"close={current_close:.5f}, ma50={ma_slow:.5f}, ma20={ma_fast:.5f})"
                ),
            )

        if action == "BUY" and bearish_count >= self._confirmations_needed:
            return (
                True,
                (
                    f"counter_trend_buy: downtrend confirmed "
                    f"({bearish_count}/3 tests, adx={adx:.1f}, "
                    f"close={current_close:.5f}, ma50={ma_slow:.5f}, ma20={ma_fast:.5f})"
                ),
            )

        return False, "signal_with_trend_or_ambiguous"
