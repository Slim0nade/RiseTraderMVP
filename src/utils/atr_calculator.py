"""
ATR (Average True Range) Calculator

Implements Wilder's smoothed ATR calculation for the stealth stop manager.
Used for dynamic stop loss calculations based on market volatility.

Reference: Welles Wilder's "New Concepts in Technical Trading Systems" (1978)
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger("atr-calculator")


class InsufficientDataError(Exception):
    """Raised when insufficient candle data is available to compute ATR.

    This is a hard error — callers must NOT fall back to hardcoded defaults.
    Upstream code must surface this failure so the operator knows data is missing.
    """

    def __init__(self, symbol: str, timeframe: str, got: int, need: int):
        self.symbol = symbol
        self.timeframe = timeframe
        self.got = got
        self.need = need
        super().__init__(
            f"Insufficient candle data for ATR({need}) on {symbol}/{timeframe}: "
            f"got {got} candles, need at least {need + 1}"
        )


@dataclass
class Candle:
    """OHLC candle data for ATR calculation."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


def calculate_true_range(current: Candle, previous_close: Optional[float] = None) -> float:
    """
    Calculate True Range for a single candle.

    True Range = max(
        High - Low,
        abs(High - Previous Close),
        abs(Low - Previous Close)
    )

    Args:
        current: Current candle OHLC data
        previous_close: Previous candle's close price (None for first candle)

    Returns:
        True Range value
    """
    high_low = current.high - current.low

    if previous_close is None:
        return high_low

    high_prev_close = abs(current.high - previous_close)
    low_prev_close = abs(current.low - previous_close)

    return max(high_low, high_prev_close, low_prev_close)


def calculate_atr_simple(candles: List[Candle], period: int = 14) -> Optional[float]:
    """
    Calculate ATR using Simple Moving Average (SMA).

    This is the initial ATR calculation method, simpler but less smooth.

    Args:
        candles: List of candles (oldest first)
        period: ATR period (default 14)

    Returns:
        ATR value or None if insufficient data
    """
    if len(candles) < period + 1:
        logger.warning(f"Insufficient candles for ATR calculation: {len(candles)} < {period + 1}")
        return None

    true_ranges = []

    for i in range(1, len(candles)):
        tr = calculate_true_range(candles[i], candles[i - 1].close)
        true_ranges.append(tr)

    # Take last 'period' true ranges
    if len(true_ranges) < period:
        return None

    recent_tr = true_ranges[-period:]
    return sum(recent_tr) / period


def calculate_atr_wilder(candles: List[Candle], period: int = 14) -> Optional[float]:
    """
    Calculate ATR using Wilder's Smoothed Moving Average.

    This is the standard ATR calculation used by most trading platforms.

    Formula:
        Initial ATR = SMA(TR, period)
        Subsequent ATR = (Previous ATR × (period - 1) + Current TR) / period

    This is equivalent to an EMA with smoothing factor = 1/period

    Args:
        candles: List of candles (oldest first)
        period: ATR period (default 14)

    Returns:
        ATR value or None if insufficient data
    """
    if len(candles) < period + 1:
        logger.warning(f"Insufficient candles for Wilder's ATR: {len(candles)} < {period + 1}")
        return None

    # Calculate True Range for all candles
    true_ranges = []
    for i in range(1, len(candles)):
        tr = calculate_true_range(candles[i], candles[i - 1].close)
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    # Initial ATR = SMA of first 'period' true ranges
    initial_atr = sum(true_ranges[:period]) / period

    # Apply Wilder's smoothing for remaining values
    atr = initial_atr
    for i in range(period, len(true_ranges)):
        atr = (atr * (period - 1) + true_ranges[i]) / period

    return atr


def calculate_atr_from_ohlc(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
    method: str = "wilder"
) -> Optional[float]:
    """
    Calculate ATR from separate OHLC arrays.

    Convenience function for when data is in array format.

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of close prices
        period: ATR period (default 14)
        method: "wilder" (default) or "simple"

    Returns:
        ATR value or None if insufficient data
    """
    if len(highs) != len(lows) or len(lows) != len(closes):
        raise ValueError("OHLC arrays must have same length")

    if len(highs) < period + 1:
        return None

    # Convert to Candle objects
    candles = []
    for i in range(len(highs)):
        candles.append(Candle(
            timestamp=datetime.now(),  # Timestamp not used for ATR
            open=closes[i] if i == 0 else closes[i - 1],  # Approximate open
            high=highs[i],
            low=lows[i],
            close=closes[i]
        ))

    if method == "wilder":
        return calculate_atr_wilder(candles, period)
    else:
        return calculate_atr_simple(candles, period)



# estimate_atr_from_symbol() REMOVED — Phase 1 fake elimination.
# The hardcoded atr_defaults dict (CrudeOIL=0.75, XAUUSD=15.0, etc.) was
# Fake #1 in CLAUDE.md. All ATR must now come from real candle data via
# calculate_atr_wilder(). If candles are unavailable, raise InsufficientDataError.


def calculate_atr_percentage(atr: float, price: float) -> float:
    """
    Convert ATR to percentage of price.

    Useful for comparing volatility across different instruments.

    Args:
        atr: ATR value in price units
        price: Current price

    Returns:
        ATR as percentage (e.g., 0.0125 for 1.25%)
    """
    if price <= 0:
        return 0.0
    return atr / price


class ATRCalculator:
    """
    ATR Calculator with caching for the stealth stop manager.

    Maintains a cache of recent ATR values to avoid recalculating
    on every position check cycle.
    """

    def __init__(self, period: int = 14, cache_duration_seconds: int = 300):
        """
        Initialize ATR Calculator.

        Args:
            period: ATR period (default 14)
            cache_duration_seconds: Cache validity duration (default 5 minutes)
        """
        self.period = period
        self.cache_duration = cache_duration_seconds
        self._cache: dict[str, Tuple[float, datetime]] = {}

    def get_cached_atr(self, symbol: str) -> Optional[float]:
        """Get cached ATR if still valid."""
        if symbol not in self._cache:
            return None

        atr, cached_at = self._cache[symbol]
        age = (datetime.now() - cached_at).total_seconds()

        if age > self.cache_duration:
            del self._cache[symbol]
            return None

        return atr

    def set_cached_atr(self, symbol: str, atr: float) -> None:
        """Cache an ATR value."""
        self._cache[symbol] = (atr, datetime.now())

    def calculate(
        self,
        symbol: str,
        candles: Optional[List[Candle]] = None,
        use_cache: bool = True
    ) -> float:
        """
        Calculate or retrieve ATR for a symbol.

        Args:
            symbol: Trading symbol
            candles: Optional candle data for calculation
            use_cache: Whether to use cached value if available

        Returns:
            ATR value (uses estimate if calculation not possible)
        """
        # Check cache first
        if use_cache:
            cached = self.get_cached_atr(symbol)
            if cached is not None:
                return cached

        # Calculate from candles if provided
        if candles is not None and len(candles) >= self.period + 1:
            atr = calculate_atr_wilder(candles, self.period)
            if atr is not None:
                self.set_cached_atr(symbol, atr)
                return atr

        # No fallback — hardcoded estimates are banned (Phase 1 fake elimination)
        raise InsufficientDataError(
            symbol=symbol,
            timeframe="unknown",
            got=len(candles) if candles else 0,
            need=self.period + 1,
        )

    def clear_cache(self) -> None:
        """Clear the ATR cache."""
        self._cache.clear()

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "cached_symbols": len(self._cache),
            "symbols": list(self._cache.keys())
        }
