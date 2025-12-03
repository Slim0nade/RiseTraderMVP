"""
MCP Tools: Function-based tools for AutoGen agents.

All tools are async functions compatible with AutoGen 0.4 AssistantAgent.
They provide access to:
- ML forecasting models
- Regime detection
- Position sizing calculations
- Technical indicators
- Market data queries

Usage with AutoGen:
    tools = [get_tcn_forecast, calculate_kelly_criterion]
    agent = AssistantAgent(name="analyst", model_client=client, tools=tools)
"""

from datetime import datetime
from typing import Dict, List, Literal, Optional, Any
import structlog
import httpx

logger = structlog.get_logger(__name__)

# ML API base URL (from Feature 003 - ML Forecasting Pipeline)
ML_API_BASE_URL = "http://localhost:8004"  # ML forecasting service


async def get_tcn_forecast(
    symbol: str,
    horizon: Literal["1h", "4h", "1d"] = "1h",
    confidence_threshold: float = 0.7,
    include_uncertainty: bool = True,
) -> Dict[str, Any]:
    """
    Get TCN (Temporal Convolutional Network) price forecast for a trading symbol.

    The TCN model excels at capturing long-term dependencies in time-series data.
    Provides multi-horizon forecasts with confidence intervals.

    Args:
        symbol: Trading symbol (e.g., "Gold", "CrudeOIL")
        horizon: Forecast horizon (1h, 4h, or 1d)
        confidence_threshold: Minimum confidence to include forecast (0.0-1.0)
        include_uncertainty: Include uncertainty/confidence bands

    Returns:
        Dictionary containing:
        - predictions: List of forecasted prices
        - confidence_scores: Confidence for each prediction
        - direction_prob: Probability of upward movement
        - uncertainty_lower: Lower confidence bound (if include_uncertainty=True)
        - uncertainty_upper: Upper confidence bound (if include_uncertainty=True)
        - inference_time_ms: Model inference time

    Example:
        >>> result = await get_tcn_forecast("Gold", horizon="4h")
        >>> print(f"Forecast: {result['predictions'][0]:.2f}")
        >>> print(f"Direction probability: {result['direction_prob']:.1%}")
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ML_API_BASE_URL}/forecast/tcn",
                json={
                    "symbol": symbol,
                    "horizon": horizon,
                    "confidence_threshold": confidence_threshold,
                    "include_uncertainty": include_uncertainty,
                },
            )
            response.raise_for_status()
            data = response.json()

            logger.info(
                "tcn_forecast_retrieved",
                symbol=symbol,
                horizon=horizon,
                predictions_count=len(data.get("predictions", [])),
                direction_prob=data.get("direction_prob"),
            )

            return data

    except Exception as e:
        logger.error(
            "tcn_forecast_error",
            symbol=symbol,
            horizon=horizon,
            error=str(e),
            exc_info=True,
        )
        return {
            "error": str(e),
            "predictions": [],
            "confidence_scores": [],
            "direction_prob": 0.5,
        }


async def get_xgboost_forecast(
    symbol: str,
    horizon: Literal["1h", "4h", "1d"] = "1h",
) -> Dict[str, Any]:
    """
    Get XGBoost price forecast for a trading symbol.

    XGBoost excels at capturing non-linear relationships and feature interactions.
    Faster inference than TCN, good for real-time decisions.

    Args:
        symbol: Trading symbol
        horizon: Forecast horizon

    Returns:
        Dictionary containing forecast data

    Example:
        >>> result = await get_xgboost_forecast("CrudeOIL", horizon="1h")
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ML_API_BASE_URL}/forecast/xgboost",
                json={"symbol": symbol, "horizon": horizon},
            )
            response.raise_for_status()
            return response.json()

    except Exception as e:
        logger.error("xgboost_forecast_error", symbol=symbol, error=str(e))
        return {"error": str(e), "predictions": []}


async def get_lstm_forecast(
    symbol: str,
    horizon: Literal["1h", "4h", "1d"] = "1h",
) -> Dict[str, Any]:
    """
    Get LSTM (Long Short-Term Memory) price forecast.

    LSTM is effective at learning sequential patterns and temporal dependencies.
    Best for medium-term forecasts.

    Args:
        symbol: Trading symbol
        horizon: Forecast horizon

    Returns:
        Dictionary containing forecast data

    Example:
        >>> result = await get_lstm_forecast("Gold", horizon="4h")
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ML_API_BASE_URL}/forecast/lstm",
                json={"symbol": symbol, "horizon": horizon},
            )
            response.raise_for_status()
            return response.json()

    except Exception as e:
        logger.error("lstm_forecast_error", symbol=symbol, error=str(e))
        return {"error": str(e), "predictions": []}


async def get_regime_classification(
    symbol: str,
    lookback_periods: int = 100,
) -> Dict[str, Any]:
    """
    Classify current market regime for trading strategy adaptation.

    Market regimes:
    - TRENDING_UP: Strong uptrend (ADX > 25, positive DI+)
    - TRENDING_DOWN: Strong downtrend (ADX > 25, positive DI-)
    - RANGING: Sideways/choppy market (ADX < 20)
    - VOLATILE: High volatility, unstable (ATR > 2 * avg)

    Args:
        symbol: Trading symbol
        lookback_periods: Number of periods to analyze for regime detection

    Returns:
        Dictionary containing:
        - regime: Current market regime classification
        - confidence: Confidence in classification (0.0-1.0)
        - indicators: Dict of regime indicators (ADX, ATR, volatility ratio)
        - recommended_strategy: Strategy type for current regime

    Example:
        >>> result = await get_regime_classification("Gold")
        >>> print(f"Regime: {result['regime']}, Confidence: {result['confidence']:.1%}")
        >>> print(f"Recommended: {result['recommended_strategy']}")
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ML_API_BASE_URL}/regime/classify",
                json={
                    "symbol": symbol,
                    "lookback_periods": lookback_periods,
                },
            )
            response.raise_for_status()
            data = response.json()

            logger.info(
                "regime_classified",
                symbol=symbol,
                regime=data.get("regime"),
                confidence=data.get("confidence"),
            )

            return data

    except Exception as e:
        logger.error("regime_classification_error", symbol=symbol, error=str(e))
        return {
            "error": str(e),
            "regime": "UNKNOWN",
            "confidence": 0.0,
        }


async def calculate_kelly_criterion(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    max_kelly_fraction: float = 0.25,
) -> Dict[str, float]:
    """
    Calculate Kelly Criterion for optimal position sizing.

    Kelly Criterion formula:
    K = (p * b - q) / b
    Where:
    - p = win rate
    - q = 1 - p (loss rate)
    - b = avg_win / avg_loss (win/loss ratio)

    Args:
        win_rate: Historical win rate (0.0-1.0)
        avg_win: Average winning trade size
        avg_loss: Average losing trade size (positive number)
        max_kelly_fraction: Maximum fraction of Kelly to use (default 0.25 = "quarter Kelly")

    Returns:
        Dictionary containing:
        - kelly_fraction: Optimal position size as fraction of capital
        - adjusted_fraction: Capped at max_kelly_fraction for risk management
        - win_loss_ratio: Calculated win/loss ratio
        - expected_value: Expected value per trade

    Example:
        >>> result = await calculate_kelly_criterion(0.55, 150.0, 100.0)
        >>> print(f"Optimal size: {result['adjusted_fraction']:.1%} of capital")
    """

    try:
        # Input validation
        if not (0 < win_rate < 1):
            raise ValueError("win_rate must be between 0 and 1")
        if avg_win <= 0 or avg_loss <= 0:
            raise ValueError("avg_win and avg_loss must be positive")

        # Calculate win/loss ratio
        win_loss_ratio = avg_win / avg_loss

        # Calculate Kelly fraction
        loss_rate = 1 - win_rate
        kelly_fraction = (win_rate * win_loss_ratio - loss_rate) / win_loss_ratio

        # Apply maximum fraction cap (risk management)
        adjusted_fraction = min(kelly_fraction, max_kelly_fraction)

        # Ensure non-negative
        adjusted_fraction = max(0.0, adjusted_fraction)

        # Calculate expected value
        expected_value = (win_rate * avg_win) - (loss_rate * avg_loss)

        result = {
            "kelly_fraction": round(kelly_fraction, 4),
            "adjusted_fraction": round(adjusted_fraction, 4),
            "win_loss_ratio": round(win_loss_ratio, 2),
            "expected_value": round(expected_value, 2),
        }

        logger.info(
            "kelly_criterion_calculated",
            win_rate=win_rate,
            kelly_fraction=result["kelly_fraction"],
            adjusted_fraction=result["adjusted_fraction"],
        )

        return result

    except Exception as e:
        logger.error(
            "kelly_calculation_error",
            win_rate=win_rate,
            error=str(e),
            exc_info=True,
        )
        return {
            "error": str(e),
            "kelly_fraction": 0.0,
            "adjusted_fraction": 0.0,
        }


async def get_technical_indicators(
    symbol: str,
    indicators: List[str],
    timeframe: Literal["1H", "4H", "1D"] = "1H",
    lookback_periods: int = 50,
) -> Dict[str, Any]:
    """
    Get technical indicators for a trading symbol.

    Available indicators:
    - RSI: Relative Strength Index (14-period)
    - MACD: Moving Average Convergence Divergence
    - BB: Bollinger Bands (20-period, 2 std dev)
    - EMA: Exponential Moving Average (multiple periods)
    - ATR: Average True Range (14-period)
    - ADX: Average Directional Index (14-period)
    - STOCH: Stochastic Oscillator

    Args:
        symbol: Trading symbol
        indicators: List of indicator codes (e.g., ["RSI", "MACD", "BB"])
        timeframe: Candlestick timeframe
        lookback_periods: Number of historical periods to include

    Returns:
        Dictionary with indicator values and metadata

    Example:
        >>> result = await get_technical_indicators(
        ...     "Gold",
        ...     indicators=["RSI", "MACD"],
        ...     timeframe="4H"
        ... )
        >>> print(f"RSI: {result['RSI']['value']}")
        >>> print(f"MACD signal: {result['MACD']['signal']}")
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ML_API_BASE_URL}/indicators",
                json={
                    "symbol": symbol,
                    "indicators": indicators,
                    "timeframe": timeframe,
                    "lookback_periods": lookback_periods,
                },
            )
            response.raise_for_status()
            return response.json()

    except Exception as e:
        logger.error(
            "technical_indicators_error",
            symbol=symbol,
            indicators=indicators,
            error=str(e),
        )
        return {"error": str(e), "indicators": {}}


async def get_market_data(
    symbol: str,
    timeframe: Literal["1H", "4H", "1D"] = "1H",
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Get historical OHLCV market data for a symbol.

    Args:
        symbol: Trading symbol
        timeframe: Candlestick timeframe
        limit: Number of candles to retrieve

    Returns:
        Dictionary containing:
        - data: List of OHLCV candles
        - symbol: Symbol queried
        - timeframe: Timeframe queried
        - count: Number of candles returned

    Example:
        >>> result = await get_market_data("CrudeOIL", timeframe="4H", limit=50)
        >>> candles = result['data']
        >>> last_close = candles[-1]['close']
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ML_API_BASE_URL}/market-data/{symbol}",
                params={"timeframe": timeframe, "limit": limit},
            )
            response.raise_for_status()
            return response.json()

    except Exception as e:
        logger.error(
            "market_data_error",
            symbol=symbol,
            timeframe=timeframe,
            error=str(e),
        )
        return {"error": str(e), "data": []}


async def get_forecast_accuracy(
    symbol: str,
    model_type: Literal["tcn", "xgboost", "lstm", "ensemble"] = "ensemble",
    horizon: Literal["1h", "4h", "1d"] = "1h",
    lookback_days: int = 30,
) -> Dict[str, Any]:
    """
    Get historical forecast accuracy metrics for a model.

    Useful for agents to assess model reliability before making decisions.

    Args:
        symbol: Trading symbol
        model_type: ML model type
        horizon: Forecast horizon
        lookback_days: Days of historical accuracy to analyze

    Returns:
        Dictionary containing:
        - mae: Mean Absolute Error
        - rmse: Root Mean Squared Error
        - mape: Mean Absolute Percentage Error
        - directional_accuracy: % of correct direction predictions
        - sharpe_if_traded: Sharpe ratio if traded on model signals
        - win_rate: Win rate if traded
        - avg_forecast_error: Average forecast error in points

    Example:
        >>> result = await get_forecast_accuracy("Gold", model_type="tcn", horizon="4h")
        >>> print(f"Directional accuracy: {result['directional_accuracy']:.1%}")
        >>> print(f"Sharpe if traded: {result['sharpe_if_traded']:.2f}")
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ML_API_BASE_URL}/forecast/accuracy",
                params={
                    "symbol": symbol,
                    "model_type": model_type,
                    "horizon": horizon,
                    "lookback_days": lookback_days,
                },
            )
            response.raise_for_status()
            data = response.json()

            logger.info(
                "forecast_accuracy_retrieved",
                symbol=symbol,
                model_type=model_type,
                directional_accuracy=data.get("directional_accuracy"),
                sharpe_if_traded=data.get("sharpe_if_traded"),
            )

            return data

    except Exception as e:
        logger.error(
            "forecast_accuracy_error",
            symbol=symbol,
            model_type=model_type,
            error=str(e),
        )
        return {
            "error": str(e),
            "directional_accuracy": 0.5,
            "sharpe_if_traded": 0.0,
        }
