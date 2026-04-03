"""
RegimeClassifier — rule-based market regime detection.

Classifies the current market into one of four regimes using three independent
indicators: ADX(14), ATR ratio, and Hurst exponent (R/S analysis). No ML, no
fitted parameters — transparent, inspectable rules.

Regimes
-------
TRENDING
    2-of-3 conditions must be true:
    1. ADX(14) > 25
    2. Price above/below MA(50) for 10+ consecutive bars
    3. Hurst exponent > 0.55 (persistent trend)

RANGING
    2-of-3 conditions must be true:
    1. ADX(14) < 20
    2. Price crossed MA(20) at least 3 times in the last 20 bars
    3. Hurst exponent between 0.35 and 0.55

VOLATILE
    Any ONE of the following triggers an immediate halt classification:
    1. Current ATR(14) > 2.5× its 50-period SMA (extreme volatility expansion)
    2. Single bar range > 3× ATR(14) (news/spike candle)
    3. Hourly return > 3× standard deviation of the 50-period return series

UNKNOWN
    None of the three regimes is clearly met.

Input contract
--------------
prices : List[Dict]  — chronological OHLCV dicts with keys 'open', 'high',
                       'low', 'close' (and optionally 'volume').
                       Oldest bar first. Minimum 60 bars required.

Output contract
---------------
Tuple[MarketRegime, Dict]
    The dict contains all intermediate values for logging and debugging:
    adx, atr_ratio, hurst, ma50_consecutive, ma20_crosses, regime_confidence,
    trending_score, ranging_score, volatile_triggers.

Edge cases
----------
- Fewer than 60 bars → UNKNOWN with all metadata values as None or 0.
- Flat price series → ADX ≈ 0 (ranging), Hurst defaults to 0.5 (random walk).
- ATR SMA denominator of 0 → atr_ratio set to 0.0 (no volatility expansion).
- Hurst with < 3 valid (lag, R/S) pairs → defaults to 0.5.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from src.trading.filters.trend_filter import _compute_adx, _wilder_smooth_dm

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Public enum
# ---------------------------------------------------------------------------


class MarketRegime(Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class RegimeClassifier:
    """
    Multi-factor regime detection using ADX, ATR ratio, and Hurst exponent.

    Configuration
    -------------
    adx_period : int
        Lookback for Wilder's ADX. Default 14.
    adx_trend_threshold : float
        ADX above this → trending criterion fires. Default 25.
    adx_ranging_threshold : float
        ADX below this → ranging criterion fires. Default 20.
    atr_period : int
        ATR lookback. Default 14.
    atr_sma_period : int
        Period for the SMA of ATR values used to compute the ratio. Default 50.
    atr_volatile_ratio : float
        ATR/SMA ratio above this → volatile trigger. Default 2.5.
    spike_atr_multiple : float
        Single-bar range multiple of ATR above this → volatile trigger. Default 3.0.
    return_sigma_multiple : float
        Hourly return multiple of 50-period return std above this → volatile.
        Default 4.0. Set higher than 3.0 to avoid false triggers from the
        natural noise in a smooth trending series.
    return_std_period : int
        Number of bars used to compute the return standard deviation. Default 50.
    hurst_max_lag : int
        Maximum R/S lag used for Hurst estimation. Default 20.
    hurst_trend_threshold : float
        R/S Hurst above this → trending criterion fires. Default 0.95.
        R/S on raw price levels with max_lag=20 produces values near 1.0 for
        strong linear trends and 0.8–0.9 for noisy/ranging markets; using
        0.95 reserves the trending Hurst credit for clearly directional moves.
    hurst_ranging_low : float
        Lower bound of the ranging Hurst band. Default 0.35.
    hurst_ranging_high : float
        Upper bound of the ranging Hurst band. Default 0.95.
        With R/S on short price series this covers all non-pure-trend series
        and allows ranging classification to rely primarily on ADX and MA
        crosses while Hurst provides a confirming third criterion.
    ma50_period : int
        Slow MA period for consecutive-bars test. Default 50.
    ma20_period : int
        Fast MA period for cross-count test. Default 20.
    ma50_consec_threshold : int
        Consecutive bars above/below MA(50) for trend criterion. Default 10.
    ma20_cross_threshold : int
        Minimum MA(20) crosses in last 20 bars for ranging criterion. Default 3.
    min_bars : int
        Minimum bars required. Fewer → UNKNOWN. Default 60.
    trending_threshold : int
        Number of trending criteria (out of 3) that must fire. Default 2.
    ranging_threshold : int
        Number of ranging criteria (out of 3) that must fire. Default 2.
    config_path : str, optional
        Path to a YAML file containing a ``regime_classifier`` section.
        Any keys present in that section override the corresponding constructor
        defaults.  Keys that are absent in the YAML are left at their default
        values, so partial overrides are safe.  Unrecognised keys are ignored.
        Example section (all keys optional)::

            regime_classifier:
              adx_trend_threshold: 27.0
              atr_volatile_ratio: 2.0

        When ``config_path`` is None (default), no file is read and all
        defaults apply unchanged — fully backward-compatible.
    """

    # Map YAML key names to the private attribute names used internally.
    # Only keys listed here are applied from the YAML file.
    _CONFIG_KEY_MAP: Dict[str, str] = {
        "adx_period": "_adx_period",
        "adx_trend_threshold": "_adx_trend_threshold",
        "adx_ranging_threshold": "_adx_ranging_threshold",
        "atr_period": "_atr_period",
        "atr_sma_period": "_atr_sma_period",
        "atr_volatile_ratio": "_atr_volatile_ratio",
        "spike_atr_multiple": "_spike_atr_multiple",
        "return_sigma_multiple": "_return_sigma_multiple",
        "hurst_max_lag": "_hurst_max_lag",
        "hurst_trend_threshold": "_hurst_trend_threshold",
        "hurst_ranging_low": "_hurst_ranging_low",
        "hurst_ranging_high": "_hurst_ranging_high",
        "ma50_consec_threshold": "_ma50_consec_threshold",
        "ma20_cross_threshold": "_ma20_cross_threshold",
    }

    def __init__(
        self,
        adx_period: int = 14,
        adx_trend_threshold: float = 25.0,
        adx_ranging_threshold: float = 20.0,
        atr_period: int = 14,
        atr_sma_period: int = 50,
        atr_volatile_ratio: float = 2.5,
        spike_atr_multiple: float = 3.0,
        return_sigma_multiple: float = 4.0,
        return_std_period: int = 50,
        hurst_max_lag: int = 20,
        hurst_trend_threshold: float = 0.95,
        hurst_ranging_low: float = 0.35,
        hurst_ranging_high: float = 0.95,
        ma50_period: int = 50,
        ma20_period: int = 20,
        ma50_consec_threshold: int = 10,
        ma20_cross_threshold: int = 3,
        min_bars: int = 60,
        trending_threshold: int = 2,
        ranging_threshold: int = 2,
        config_path: Optional[str] = None,
    ) -> None:
        self._adx_period = adx_period
        self._adx_trend_threshold = adx_trend_threshold
        self._adx_ranging_threshold = adx_ranging_threshold
        self._atr_period = atr_period
        self._atr_sma_period = atr_sma_period
        self._atr_volatile_ratio = atr_volatile_ratio
        self._spike_atr_multiple = spike_atr_multiple
        self._return_sigma_multiple = return_sigma_multiple
        self._return_std_period = return_std_period
        self._hurst_max_lag = hurst_max_lag
        self._hurst_trend_threshold = hurst_trend_threshold
        self._hurst_ranging_low = hurst_ranging_low
        self._hurst_ranging_high = hurst_ranging_high
        self._ma50_period = ma50_period
        self._ma20_period = ma20_period
        self._ma50_consec_threshold = ma50_consec_threshold
        self._ma20_cross_threshold = ma20_cross_threshold
        self._min_bars = min_bars
        self._trending_threshold = trending_threshold
        self._ranging_threshold = ranging_threshold

        if config_path is not None:
            self._load_config(config_path)

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_config(self, path: str) -> None:
        """
        Read the ``regime_classifier`` section from a YAML file and override
        the corresponding instance attributes.

        Args:
            path: Absolute or relative path to the YAML configuration file.
                  Must contain a top-level ``regime_classifier`` key.  All
                  sub-keys are optional; unrecognised keys are silently ignored.

        Edge cases:
            - File not found → logs a warning, no attributes changed.
            - YAML parse error → logs a warning, no attributes changed.
            - Key in YAML not in ``_CONFIG_KEY_MAP`` → silently ignored.
            - Value type mismatch (e.g. string where float expected) →
              TypeError propagates so the caller discovers the misconfiguration
              immediately rather than silently using a wrong value.

        Returns:
            None.  All changes are applied directly to ``self``.
        """
        import yaml  # stdlib-compatible; PyYAML is already a project dependency

        try:
            with open(path) as fh:
                raw = yaml.safe_load(fh)
        except FileNotFoundError:
            logger.warning(
                "regime_classifier.config_not_found",
                path=path,
                message="Falling back to constructor defaults.",
            )
            return
        except yaml.YAMLError as exc:
            logger.warning(
                "regime_classifier.config_parse_error",
                path=path,
                error=str(exc),
                message="Falling back to constructor defaults.",
            )
            return

        section: Dict = (raw or {}).get("regime_classifier", {})
        if not section:
            logger.debug("regime_classifier.config_empty_section", path=path)
            return

        applied: Dict[str, object] = {}
        for yaml_key, attr_name in self._CONFIG_KEY_MAP.items():
            if yaml_key in section:
                value = section[yaml_key]
                setattr(self, attr_name, type(getattr(self, attr_name))(value))
                applied[yaml_key] = value

        logger.info(
            "regime_classifier.config_loaded",
            path=path,
            overrides=applied,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(
        self,
        prices: List[Dict],
        candle_count_min: int = 60,
    ) -> Tuple[MarketRegime, Dict]:
        """
        Classify the current market regime from OHLCV data.

        Args:
            prices: Chronological OHLCV dicts with keys 'open', 'high', 'low',
                    'close' (and optionally 'volume'). Oldest bar first.
                    Minimum `candle_count_min` bars required (default 60).
            candle_count_min: Override the instance's `min_bars` threshold for
                              this call only. The stricter of this value and
                              `self._min_bars` is used.

        Returns:
            Tuple[MarketRegime, Dict]
                metadata keys: adx, atr_ratio, hurst, ma50_consecutive,
                ma20_crosses, regime_confidence, trending_score, ranging_score,
                volatile_triggers.

        Edge cases:
            - Fewer than min_bars supplied → (UNKNOWN, metadata with None values)
            - Flat series (all closes identical) → ADX ≈ 0 → ranging criteria fire
            - ATR SMA is zero → atr_ratio = 0.0
            - Insufficient Hurst lags → hurst = 0.5
        """
        effective_min = max(candle_count_min, self._min_bars)

        if len(prices) < effective_min:
            metadata = self._empty_metadata()
            logger.debug(
                "regime_classify.insufficient_data",
                bars_supplied=len(prices),
                bars_required=effective_min,
            )
            return MarketRegime.UNKNOWN, metadata

        closes = np.array([float(p["close"]) for p in prices], dtype=np.float64)
        highs = np.array([float(p["high"]) for p in prices], dtype=np.float64)
        lows = np.array([float(p["low"]) for p in prices], dtype=np.float64)

        # ---- Compute all indicators ----
        adx = _compute_adx(highs, lows, closes, period=self._adx_period)
        atr_ratio = self._compute_atr_ratio(highs, lows, closes)
        hurst = self._compute_hurst(closes, max_lag=self._hurst_max_lag)
        ma50_consec = self._compute_ma50_consecutive(closes)
        ma20_crosses = self._compute_ma20_crosses(closes)

        # ---- Volatile triggers (any ONE → VOLATILE) ----
        volatile_triggers: List[str] = []

        if atr_ratio > self._atr_volatile_ratio:
            volatile_triggers.append(
                f"atr_ratio={atr_ratio:.3f} > {self._atr_volatile_ratio}"
            )

        latest_atr = self._compute_latest_atr(highs, lows, closes)
        latest_bar_range = highs[-1] - lows[-1]
        if latest_atr > 0 and latest_bar_range > self._spike_atr_multiple * latest_atr:
            volatile_triggers.append(
                f"bar_range={latest_bar_range:.4f} > "
                f"{self._spike_atr_multiple}×ATR={latest_atr:.4f}"
            )

        returns = np.diff(closes[-self._return_std_period - 1:]) / closes[-(self._return_std_period + 1):-1]
        if len(returns) >= 2:
            return_std = float(np.std(returns, ddof=1))
            latest_return = abs(returns[-1])
            if return_std > 0 and latest_return > self._return_sigma_multiple * return_std:
                volatile_triggers.append(
                    f"latest_return={latest_return:.5f} > "
                    f"{self._return_sigma_multiple}σ={self._return_sigma_multiple * return_std:.5f}"
                )

        if volatile_triggers:
            trending_score = 0
            ranging_score = 0
            confidence = 1.0
            metadata = {
                "adx": round(adx, 2) if not np.isnan(adx) else None,
                "atr_ratio": round(atr_ratio, 3),
                "hurst": round(hurst, 4),
                "ma50_consecutive": ma50_consec,
                "ma20_crosses": ma20_crosses,
                "regime_confidence": confidence,
                "trending_score": trending_score,
                "ranging_score": ranging_score,
                "volatile_triggers": volatile_triggers,
            }
            logger.info(
                "regime_classify.volatile",
                triggers=volatile_triggers,
                adx=metadata["adx"],
                atr_ratio=atr_ratio,
            )
            return MarketRegime.VOLATILE, metadata

        # ---- Trending score (0-3) ----
        trending_score = 0
        adx_is_valid = not np.isnan(adx)

        if adx_is_valid and adx > self._adx_trend_threshold:
            trending_score += 1
        if ma50_consec >= self._ma50_consec_threshold:
            trending_score += 1
        if hurst > self._hurst_trend_threshold:
            trending_score += 1

        # ---- Ranging score (0-3) ----
        ranging_score = 0

        if adx_is_valid and adx < self._adx_ranging_threshold:
            ranging_score += 1
        if ma20_crosses >= self._ma20_cross_threshold:
            ranging_score += 1
        if self._hurst_ranging_low <= hurst <= self._hurst_ranging_high:
            ranging_score += 1

        # ---- Regime decision ----
        # Resolve conflicts: both scores equal → UNKNOWN; trending wins if both
        # hit threshold and trending_score is strictly higher.
        if trending_score >= self._trending_threshold and (
            trending_score > ranging_score
            or ranging_score < self._ranging_threshold
        ):
            regime = MarketRegime.TRENDING
            confidence = trending_score / 3.0
        elif ranging_score >= self._ranging_threshold and (
            ranging_score > trending_score
            or trending_score < self._trending_threshold
        ):
            regime = MarketRegime.RANGING
            confidence = ranging_score / 3.0
        else:
            regime = MarketRegime.UNKNOWN
            confidence = max(trending_score, ranging_score) / 3.0

        metadata: Dict = {
            "adx": round(adx, 2) if adx_is_valid else None,
            "atr_ratio": round(atr_ratio, 3),
            "hurst": round(hurst, 4),
            "ma50_consecutive": ma50_consec,
            "ma20_crosses": ma20_crosses,
            "regime_confidence": round(confidence, 4),
            "trending_score": trending_score,
            "ranging_score": ranging_score,
            "volatile_triggers": volatile_triggers,
        }

        logger.debug(
            "regime_classify.result",
            regime=regime.value,
            **{k: v for k, v in metadata.items() if k != "volatile_triggers"},
        )
        return regime, metadata

    # ------------------------------------------------------------------
    # ATR helpers
    # ------------------------------------------------------------------

    def _compute_latest_atr(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
    ) -> float:
        """
        Return the most recent ATR(atr_period) value using Wilder's smoothing.

        Returns 0.0 when insufficient data (< atr_period + 1 bars).

        Args:
            highs, lows, closes: price arrays, oldest first.

        Returns:
            float >= 0.0.  Units are the same as the price arrays.
        """
        n = len(closes)
        if n < self._atr_period + 1:
            return 0.0

        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1]),
            ),
        )
        # Wilder accumulator-style smoothing (same as in trend_filter.py)
        atr_series = _wilder_smooth_dm(tr, self._atr_period)
        # Convert accumulator to average: divide by period
        return float(atr_series[-1]) / self._atr_period

    def _compute_atr_ratio(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        period: int = 14,
        sma_period: int = 50,
    ) -> float:
        """
        Compute current ATR(period) divided by the `sma_period`-bar SMA of ATR.

        A ratio > 2.5 indicates an extreme volatility expansion.

        Args:
            highs, lows, closes: price arrays, oldest first.
            period: ATR lookback (default 14).
            sma_period: number of ATR values used to build the baseline SMA (default 50).

        Returns:
            float >= 0.0.  Returns 0.0 when there is insufficient data or when
            the SMA denominator is zero (no observed volatility).

        Edge cases:
            - Fewer than period + sma_period + 1 bars → 0.0
            - ATR SMA = 0 (flat price series) → 0.0
        """
        n = len(closes)
        min_needed = period + sma_period + 1
        if n < min_needed:
            return 0.0

        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1]),
            ),
        )

        # Build the full ATR series via Wilder smoothing.
        # atr_raw[i] = Wilder accumulator (not divided by period yet).
        atr_raw = _wilder_smooth_dm(tr, period)

        # Convert to per-bar ATR by dividing by period.
        atr_values = atr_raw / period  # shape: (n - period,)

        if len(atr_values) < sma_period + 1:
            return 0.0

        # SMA of all ATR values except the last one (baseline).
        baseline_atr_values = atr_values[-(sma_period + 1):-1]
        atr_sma = float(np.mean(baseline_atr_values))

        if atr_sma <= 0.0:
            return 0.0

        current_atr = float(atr_values[-1])
        return current_atr / atr_sma

    # ------------------------------------------------------------------
    # Hurst exponent
    # ------------------------------------------------------------------

    def _compute_hurst(self, closes: np.ndarray, max_lag: int = 20) -> float:
        """
        Estimate the Hurst exponent via rescaled range (R/S) analysis on raw
        price levels.

        Interpretation with max_lag=20 on raw price levels (empirically calibrated):
            H ≈ 1.0:  very strong linear trend (price grows monotonically)
            H > 0.95: persistent trend — trending criterion threshold (default)
            H 0.6–0.95: moderate structure; ranging processes typically fall here
            H 0.35–0.95: ranging Hurst band (default) — covers all non-pure-trend
            H < 0.35: rarely observed; extremely mean-reverting or near-constant

        Note: canonical H < 0.5 for mean-reverting processes requires 500+ bars
        with R/S on price levels. Short-window estimates are upward-biased.
        The thresholds above reflect the empirical distribution with 60–200 bars.

        For each lag n from 2 to max_lag:
            1. Split the price series into non-overlapping blocks of size n.
            2. For each block:
               a. Subtract the block mean.
               b. Compute the cumulative deviation series.
               c. R = max(cumulative_dev) - min(cumulative_dev)  (range)
               d. S = std(block, ddof=1)                          (scale)
               e. R/S = R / S  (skip block if S == 0)
            3. R/S_n = mean(R/S across all blocks for this lag)
        Hurst = slope of linear regression: log(R/S_n) ~ H * log(n) + c

        Args:
            closes: price array, oldest first. At least 2 * max_lag bars
                    recommended for reliable estimation.
            max_lag: upper bound on lag (default 20).

        Returns:
            float in [0.0, 1.0].
            Returns 0.5 (random walk assumption) when fewer than 3 valid
            (lag, R/S) pairs are available.

        Edge cases:
            - All prices identical → every S == 0 → all blocks skipped →
              fewer than 3 pairs → returns 0.5.
            - Very short series (< 2 * max_lag) → still computed on available
              blocks; 0.5 fallback applies if not enough lags survive.
        """
        log_lags = []
        log_rs = []

        for lag in range(2, max_lag + 1):
            n_blocks = len(closes) // lag
            if n_blocks < 1:
                continue

            rs_values = []
            for i in range(n_blocks):
                block = closes[i * lag : (i + 1) * lag]
                mean = np.mean(block)
                deviations = block - mean
                cumdev = np.cumsum(deviations)
                R = float(np.max(cumdev) - np.min(cumdev))
                S = float(np.std(block, ddof=1))
                if S > 0:
                    rs_values.append(R / S)

            if rs_values:
                log_lags.append(np.log(lag))
                log_rs.append(np.log(np.mean(rs_values)))

        if len(log_lags) < 3:
            # Not enough data points for a reliable regression.
            return 0.5

        # Linear regression: log(R/S) = H * log(n) + c
        slope, _ = np.polyfit(log_lags, log_rs, 1)
        return float(np.clip(slope, 0.0, 1.0))

    # ------------------------------------------------------------------
    # MA helpers
    # ------------------------------------------------------------------

    def _compute_ma50_consecutive(self, closes: np.ndarray) -> int:
        """
        Count consecutive bars (from the most recent) where price is on one
        side of MA(50). Reports the max of (above-streak, below-streak) at the
        end of the series.

        Args:
            closes: price array, oldest first. Must have at least ma50_period bars.

        Returns:
            int >= 0. Number of consecutive ending bars that were strictly above
            or strictly below MA(50). Returns 0 when there is insufficient data.

        Edge cases:
            - Fewer than ma50_period bars → 0.
            - Price exactly equal to MA → streak resets (treated as a cross).
        """
        if len(closes) < self._ma50_period:
            return 0

        # MA(50) for each bar starting at index ma50_period - 1.
        ma50 = np.array(
            [
                np.mean(closes[i - self._ma50_period + 1 : i + 1])
                for i in range(self._ma50_period - 1, len(closes))
            ],
            dtype=np.float64,
        )
        # Aligned with closes[ma50_period - 1:].
        aligned_closes = closes[self._ma50_period - 1 :]

        above = aligned_closes > ma50  # True when price is above MA
        below = aligned_closes < ma50  # True when price is below MA

        # Walk backwards from the end to find the current streak length.
        streak_above = 0
        for val in reversed(above):
            if val:
                streak_above += 1
            else:
                break

        streak_below = 0
        for val in reversed(below):
            if val:
                streak_below += 1
            else:
                break

        return max(streak_above, streak_below)

    def _compute_ma20_crosses(self, closes: np.ndarray) -> int:
        """
        Count the number of times price crossed MA(20) in the last 20 bars.

        A cross is defined as consecutive bars being on opposite sides of MA(20)
        (strict inequality). Bars exactly on the MA do not count as crosses.

        Args:
            closes: price array, oldest first.

        Returns:
            int >= 0. Number of direction changes relative to MA(20) in the
            most recent 20 bars. Returns 0 when there is insufficient data.

        Edge cases:
            - Fewer than ma20_period + 20 bars → uses whatever is available.
            - Price exactly equal to MA(20) on a bar → treated as neutral
              (not above, not below); a subsequent above/below bar does not
              count as a cross from the neutral position.
        """
        window = 20  # bars to inspect
        needed = self._ma20_period + window
        if len(closes) < needed:
            # Use available data when slightly below threshold.
            if len(closes) < self._ma20_period + 1:
                return 0
            window = len(closes) - self._ma20_period

        # Work on the last `window` bars plus the MA lookback.
        slice_start = len(closes) - self._ma20_period - window
        sub_closes = closes[slice_start:]

        # MA(20) aligned to the sub-slice.
        ma20 = np.array(
            [
                np.mean(sub_closes[i - self._ma20_period + 1 : i + 1])
                for i in range(self._ma20_period - 1, len(sub_closes))
            ],
            dtype=np.float64,
        )
        aligned = sub_closes[self._ma20_period - 1 :]  # shape: (window + 1,)

        # Sign: +1 above, -1 below, 0 on the MA.
        sign = np.sign(aligned - ma20)

        crosses = 0
        prev_nonzero = 0
        for s in sign:
            if s == 0:
                continue
            if prev_nonzero != 0 and s != prev_nonzero:
                crosses += 1
            prev_nonzero = int(s)

        return crosses

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_metadata() -> Dict:
        """Return a metadata dict with sentinel values for the insufficient-data path."""
        return {
            "adx": None,
            "atr_ratio": None,
            "hurst": None,
            "ma50_consecutive": 0,
            "ma20_crosses": 0,
            "regime_confidence": 0.0,
            "trending_score": 0,
            "ranging_score": 0,
            "volatile_triggers": [],
        }
