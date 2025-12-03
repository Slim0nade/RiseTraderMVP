"""
ML Forecasting MCP Tools.

Provides ML model forecast interfaces for agents:
- TCN (Temporal Convolutional Network) forecasts
- TFT (Temporal Fusion Transformer) predictions with quantiles
- FEDformer regime classification
"""

import asyncio
import os
import time
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

# Import ML inference service (Feature 003)
# Note: These tools act as a bridge between the agent system and Feature 003's ML API


class TCNForecastInput(BaseModel):
    """Input schema for TCN forecast."""
    symbol: str = Field(..., pattern="^[A-Z][a-zA-Z0-9]{1,19}$")
    horizon: str = Field(..., pattern="^(1h|4h|1d)$")
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    include_uncertainty: bool = Field(default=True)


class TCNForecastOutput(BaseModel):
    """Output schema for TCN forecast."""
    symbol: str
    horizon: str
    predictions: List[float]
    confidence_scores: List[float]
    direction_prob: float = Field(..., ge=0.0, le=1.0)
    uncertainty_bounds: Optional[Dict[str, List[float]]] = None
    inference_time_ms: float
    model_version: str


class TFTPredictionInput(BaseModel):
    """Input schema for TFT prediction."""
    symbol: str
    horizon: str = Field(..., pattern="^(1h|4h|1d)$")
    include_attention: bool = Field(default=False)


class TFTPredictionOutput(BaseModel):
    """Output schema for TFT prediction."""
    symbol: str
    horizon: str
    predictions: List[float]
    quantiles: Dict[str, List[float]]  # p10, p25, p50, p75, p90
    attention_weights: Optional[Dict[str, Any]] = None
    inference_time_ms: float
    model_version: str


class FEDformerRegimeInput(BaseModel):
    """Input schema for FEDformer regime classification."""
    symbol: str
    lookback_periods: int = Field(default=100, ge=50, le=500)


class FEDformerRegimeOutput(BaseModel):
    """Output schema for FEDformer regime classification."""
    symbol: str
    regime: str  # TRENDING_BULLISH, TRENDING_BEARISH, MEAN_REVERTING, VOLATILE, TRANSITIONING
    regime_confidence: float = Field(..., ge=0.0, le=1.0)
    regime_duration_periods: int
    transition_probability: float = Field(..., ge=0.0, le=1.0)
    volatility_percentile: float = Field(..., ge=0.0, le=100.0)
    inference_time_ms: float
    model_version: str


# HTTP Client for ML Forecasting API (Feature 003)
ML_FORECASTING_API_URL = os.getenv("ML_FORECASTING_API_URL", "http://localhost:8004")
HTTP_TIMEOUT = 5.0  # 5 second timeout


async def get_tcn_forecast(
    symbol: str,
    horizon: str = "1h",
    confidence_threshold: float = 0.7,
    include_uncertainty: bool = True,
) -> Dict[str, Any]:
    """
    Get TCN model forecast with confidence scores and uncertainty quantification.

    This tool calls the ML Forecasting API (Feature 003) to get TCN forecasts.
    If the API is unavailable, returns mock data with low confidence.

    Args:
        symbol: Trading symbol (e.g., "CrudeOIL", "Gold")
        horizon: Forecast horizon ("1h", "4h", "1d")
        confidence_threshold: Minimum confidence threshold (0-1)
        include_uncertainty: Include uncertainty quantification

    Returns:
        TCN forecast with predictions, confidence scores, and uncertainty bounds

    Example:
        >>> forecast = await get_tcn_forecast("CrudeOIL", "4h")
        >>> print(forecast["predictions"])
        [75.42, 75.68, 75.91, 76.15]
    """
    start_time = time.time()

    try:
        # Validate input
        input_data = TCNForecastInput(
            symbol=symbol,
            horizon=horizon,
            confidence_threshold=confidence_threshold,
            include_uncertainty=include_uncertainty,
        )

        # Call ML Forecasting API (Feature 003)
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(
                f"{ML_FORECASTING_API_URL}/api/forecasts/tcn",
                json=input_data.model_dump(),
            )
            response.raise_for_status()
            forecast_data = response.json()

        inference_time_ms = (time.time() - start_time) * 1000

        # Validate output
        output = TCNForecastOutput(
            **forecast_data,
            inference_time_ms=inference_time_ms,
        )

        return output.model_dump()

    except (httpx.HTTPError, httpx.TimeoutException) as e:
        # ML API unavailable - return mock data with low confidence
        inference_time_ms = (time.time() - start_time) * 1000

        # Return neutral forecast with low confidence
        mock_output = TCNForecastOutput(
            symbol=symbol,
            horizon=horizon,
            predictions=[75.0, 75.0, 75.0, 75.0],  # Flat forecast
            confidence_scores=[0.3, 0.3, 0.3, 0.3],  # Low confidence
            direction_prob=0.5,  # Neutral
            uncertainty_bounds={
                "lower_95": [70.0, 70.0, 70.0, 70.0],
                "upper_95": [80.0, 80.0, 80.0, 80.0],
            } if include_uncertainty else None,
            inference_time_ms=inference_time_ms,
            model_version="mock_v0.0.1",
        )

        return mock_output.model_dump()


async def get_tft_prediction(
    symbol: str,
    horizon: str = "1h",
    include_attention: bool = False,
) -> Dict[str, Any]:
    """
    Get TFT (Temporal Fusion Transformer) prediction with quantiles.

    This tool calls the ML Forecasting API (Feature 003) to get TFT predictions.
    TFT provides quantile predictions (p10, p25, p50, p75, p90) for probabilistic
    forecasting, which is essential for take-profit targeting.

    Args:
        symbol: Trading symbol
        horizon: Forecast horizon ("1h", "4h", "1d")
        include_attention: Include attention weights for interpretability

    Returns:
        TFT prediction with quantiles and optional attention weights

    Example:
        >>> prediction = await get_tft_prediction("Gold", "4h")
        >>> print(prediction["quantiles"]["p50"])
        [2050.5, 2052.3, 2054.8]
    """
    start_time = time.time()

    try:
        # Validate input
        input_data = TFTPredictionInput(
            symbol=symbol,
            horizon=horizon,
            include_attention=include_attention,
        )

        # Call ML Forecasting API (Feature 003)
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(
                f"{ML_FORECASTING_API_URL}/api/forecasts/tft",
                json=input_data.model_dump(),
            )
            response.raise_for_status()
            prediction_data = response.json()

        inference_time_ms = (time.time() - start_time) * 1000

        # Validate output
        output = TFTPredictionOutput(
            **prediction_data,
            inference_time_ms=inference_time_ms,
        )

        return output.model_dump()

    except (httpx.HTTPError, httpx.TimeoutException) as e:
        # ML API unavailable - return mock data
        inference_time_ms = (time.time() - start_time) * 1000

        # Return neutral quantiles
        mock_output = TFTPredictionOutput(
            symbol=symbol,
            horizon=horizon,
            predictions=[75.0, 75.0, 75.0],
            quantiles={
                "p10": [70.0, 70.0, 70.0],
                "p25": [72.5, 72.5, 72.5],
                "p50": [75.0, 75.0, 75.0],
                "p75": [77.5, 77.5, 77.5],
                "p90": [80.0, 80.0, 80.0],
            },
            attention_weights=None,
            inference_time_ms=inference_time_ms,
            model_version="mock_v0.0.1",
        )

        return mock_output.model_dump()


async def get_fedformer_regime(
    symbol: str,
    lookback_periods: int = 100,
) -> Dict[str, Any]:
    """
    Get FEDformer regime classification.

    This tool calls the ML Forecasting API (Feature 003) to classify the current
    market regime. Regime classification is critical for position sizing and
    stop-loss adjustments.

    Regimes:
    - TRENDING_BULLISH: Strong uptrend
    - TRENDING_BEARISH: Strong downtrend
    - MEAN_REVERTING: Range-bound, oscillating
    - VOLATILE: High volatility, unpredictable
    - TRANSITIONING: Regime change in progress

    Args:
        symbol: Trading symbol
        lookback_periods: Number of periods to analyze (50-500)

    Returns:
        Regime classification with confidence and transition probability

    Example:
        >>> regime = await get_fedformer_regime("CrudeOIL")
        >>> print(regime["regime"])
        "TRENDING_BULLISH"
    """
    start_time = time.time()

    try:
        # Validate input
        input_data = FEDformerRegimeInput(
            symbol=symbol,
            lookback_periods=lookback_periods,
        )

        # Call ML Forecasting API (Feature 003)
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(
                f"{ML_FORECASTING_API_URL}/api/forecasts/regime",
                json=input_data.model_dump(),
            )
            response.raise_for_status()
            regime_data = response.json()

        inference_time_ms = (time.time() - start_time) * 1000

        # Validate output
        output = FEDformerRegimeOutput(
            **regime_data,
            inference_time_ms=inference_time_ms,
        )

        return output.model_dump()

    except (httpx.HTTPError, httpx.TimeoutException) as e:
        # ML API unavailable - return mock regime
        inference_time_ms = (time.time() - start_time) * 1000

        # Return neutral/mean-reverting regime with low confidence
        mock_output = FEDformerRegimeOutput(
            symbol=symbol,
            regime="MEAN_REVERTING",  # Safest default
            regime_confidence=0.4,  # Low confidence
            regime_duration_periods=10,
            transition_probability=0.5,  # Uncertain
            volatility_percentile=50.0,  # Median volatility
            inference_time_ms=inference_time_ms,
            model_version="mock_v0.0.1",
        )

        return mock_output.model_dump()
