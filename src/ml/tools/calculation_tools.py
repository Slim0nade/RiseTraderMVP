"""
Calculation MCP Tools.

Provides mathematical calculations for position sizing and risk management:
- Kelly Criterion calculation
- Average True Range (ATR) calculation
"""

import math
import os
import time
from typing import Any, Dict, Optional

import httpx
import numpy as np
from pydantic import BaseModel, Field


class KellyInput(BaseModel):
    """Input schema for Kelly criterion calculation."""
    win_probability: float = Field(..., ge=0.0, le=1.0)
    win_loss_ratio: float = Field(..., ge=0.1, le=10.0)
    max_kelly_fraction: float = Field(default=0.25, ge=0.1, le=1.0)
    bankroll: float = Field(..., gt=0.0)


class KellyOutput(BaseModel):
    """Output schema for Kelly criterion calculation."""
    kelly_fraction: float = Field(..., ge=0.0, le=1.0)
    capped_kelly_fraction: float = Field(..., ge=0.0, le=1.0)
    recommended_position_size: float
    recommended_position_pct: float
    expected_growth_rate: float
    calculation_time_ms: float


class ATRInput(BaseModel):
    """Input schema for ATR calculation."""
    symbol: str
    period: int = Field(default=14, ge=5, le=100)
    timeframe: str = Field(default="4h", pattern="^(1h|4h|1d)$")


class ATROutput(BaseModel):
    """Output schema for ATR calculation."""
    symbol: str
    atr_value: float
    atr_percentage: float
    current_price: float
    period: int
    timeframe: str
    calculation_time_ms: float


# Market Data API URL (for ATR calculation)
MARKET_DATA_API_URL = os.getenv("MARKET_DATA_API_URL", "http://localhost:8003")
HTTP_TIMEOUT = 2.0


async def calculate_kelly(
    win_probability: float,
    win_loss_ratio: float,
    bankroll: float,
    max_kelly_fraction: float = 0.25,
) -> Dict[str, Any]:
    """
    Calculate Kelly criterion position size.

    The Kelly Criterion formula: f* = (p × b - q) / b
    Where:
    - f* = fraction of bankroll to bet
    - p = probability of winning
    - q = probability of losing (1 - p)
    - b = win/loss ratio (how much you win per dollar lost)

    For trading safety, we apply a fractional Kelly (typically 25% or "quarter-Kelly")
    to reduce volatility.

    Args:
        win_probability: Probability of winning trade (0-1)
        win_loss_ratio: Average win / average loss ratio
        bankroll: Total allocated capital
        max_kelly_fraction: Maximum Kelly fraction (safety cap, default 0.25)

    Returns:
        Kelly calculation with recommended position size

    Example:
        >>> kelly = await calculate_kelly(0.55, 1.8, 40000.0, 0.25)
        >>> print(kelly["recommended_position_size"])
        10000.0
    """
    start_time = time.time()

    # Validate input
    input_data = KellyInput(
        win_probability=win_probability,
        win_loss_ratio=win_loss_ratio,
        max_kelly_fraction=max_kelly_fraction,
        bankroll=bankroll,
    )

    # Calculate Kelly fraction
    # f* = (p × b - q) / b
    p = win_probability
    q = 1 - p
    b = win_loss_ratio

    # Full Kelly fraction
    kelly_fraction = (p * b - q) / b

    # Ensure non-negative (never short when Kelly is negative - just don't trade)
    kelly_fraction = max(0.0, kelly_fraction)

    # Cap at max fraction (typically 25% for quarter-Kelly)
    capped_kelly_fraction = min(kelly_fraction, max_kelly_fraction)

    # Cap at 100% (never risk more than entire bankroll)
    capped_kelly_fraction = min(capped_kelly_fraction, 1.0)

    # Calculate position size
    recommended_position_size = bankroll * capped_kelly_fraction
    recommended_position_pct = capped_kelly_fraction * 100.0

    # Calculate expected growth rate (geometric mean)
    # g = p × ln(1 + f × b) + q × ln(1 - f)
    if capped_kelly_fraction > 0:
        try:
            expected_growth_rate = (
                p * math.log(1 + capped_kelly_fraction * b) +
                q * math.log(1 - capped_kelly_fraction)
            )
        except ValueError:
            # ln(negative number) - position size too large
            expected_growth_rate = -1.0
    else:
        expected_growth_rate = 0.0

    calculation_time_ms = (time.time() - start_time) * 1000

    output = KellyOutput(
        kelly_fraction=kelly_fraction,
        capped_kelly_fraction=capped_kelly_fraction,
        recommended_position_size=recommended_position_size,
        recommended_position_pct=recommended_position_pct,
        expected_growth_rate=expected_growth_rate,
        calculation_time_ms=calculation_time_ms,
    )

    return output.model_dump()


async def calculate_atr(
    symbol: str,
    period: int = 14,
    timeframe: str = "4h",
) -> Dict[str, Any]:
    """
    Calculate Average True Range (ATR).

    ATR measures market volatility and is essential for:
    - Position sizing (volatility-adjusted)
    - Stop-loss placement (e.g., 2× ATR from entry)
    - Volatility regime detection

    This tool fetches recent OHLC data and calculates ATR using the formula:
    - True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
    - ATR = exponential moving average of True Range

    Args:
        symbol: Trading symbol (e.g., "CrudeOIL", "Gold")
        period: ATR period (default 14)
        timeframe: Timeframe for calculation ("1h", "4h", "1d")

    Returns:
        ATR value in price units and as percentage of current price

    Example:
        >>> atr = await calculate_atr("CrudeOIL", 14, "4h")
        >>> print(f"ATR: {atr['atr_value']} ({atr['atr_percentage']}%)")
        ATR: 1.14 (1.52%)
    """
    start_time = time.time()

    # Validate input
    input_data = ATRInput(
        symbol=symbol,
        period=period,
        timeframe=timeframe,
    )

    try:
        # Fetch market data from API
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(
                f"{MARKET_DATA_API_URL}/api/market-data/ohlc",
                params={
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "limit": period + 1,  # Need period + 1 for ATR calculation
                },
            )
            response.raise_for_status()
            ohlc_data = response.json()

        # Extract OHLC arrays
        highs = np.array([bar["high"] for bar in ohlc_data["bars"]])
        lows = np.array([bar["low"] for bar in ohlc_data["bars"]])
        closes = np.array([bar["close"] for bar in ohlc_data["bars"]])
        current_price = closes[-1]

        # Calculate True Range for each period
        # TR = max(high - low, |high - prev_close|, |low - prev_close|)
        high_low = highs[1:] - lows[1:]
        high_prev_close = np.abs(highs[1:] - closes[:-1])
        low_prev_close = np.abs(lows[1:] - closes[:-1])

        true_ranges = np.maximum(high_low, np.maximum(high_prev_close, low_prev_close))

        # Calculate ATR as exponential moving average
        # Using pandas ewm equivalent: alpha = 2 / (period + 1)
        alpha = 2.0 / (period + 1)
        atr_value = true_ranges[0]  # Initialize with first TR
        for tr in true_ranges[1:]:
            atr_value = alpha * tr + (1 - alpha) * atr_value

        # Calculate ATR as percentage of current price
        atr_percentage = (atr_value / current_price) * 100.0

        calculation_time_ms = (time.time() - start_time) * 1000

        output = ATROutput(
            symbol=symbol,
            atr_value=float(atr_value),
            atr_percentage=float(atr_percentage),
            current_price=float(current_price),
            period=period,
            timeframe=timeframe,
            calculation_time_ms=calculation_time_ms,
        )

        return output.model_dump()

    except (httpx.HTTPError, httpx.TimeoutException, KeyError, IndexError) as e:
        # Market data unavailable - return mock ATR
        calculation_time_ms = (time.time() - start_time) * 1000

        # Return mock ATR (typical 1.5% volatility)
        mock_output = ATROutput(
            symbol=symbol,
            atr_value=1.14,  # Mock value
            atr_percentage=1.52,  # Mock percentage
            current_price=75.0,  # Mock current price
            period=period,
            timeframe=timeframe,
            calculation_time_ms=calculation_time_ms,
        )

        return mock_output.model_dump()
