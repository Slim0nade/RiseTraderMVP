"""
Reversal Prediction API Endpoints

Provides real-time reversal predictions using trained ML classifier.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from src.database.config import get_session
from src.ml.inference.reversal_predictor import get_predictor, clear_predictor_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reversals", tags=["Reversal Predictions"])


# Request/Response Models
class ReversalPredictionRequest(BaseModel):
    """Request model for reversal prediction."""
    symbol: str = Field(..., description="Trading symbol (e.g., 'CrudeOIL')")
    timeframe: str = Field(..., description="Candle timeframe (e.g., 'H1')")
    timestamp: Optional[datetime] = Field(None, description="Time to predict for (default: now)")
    lookback_bars: int = Field(100, ge=20, le=500, description="Number of historical bars for features")
    model_version: str = Field('latest', description="Model version to use (e.g., 'v1', 'latest')")


class ReversalPredictionResponse(BaseModel):
    """Response model for reversal prediction."""
    symbol: str
    timeframe: str
    timestamp: str
    valley_prob: float = Field(..., description="Probability of valley (long signal)")
    neutral_prob: float = Field(..., description="Probability of neutral (no trade)")
    peak_prob: float = Field(..., description="Probability of peak (short signal)")
    signal: str = Field(..., description="Trading signal: 'LONG', 'SHORT', or 'WAIT'")
    confidence: float = Field(..., description="Confidence score for the signal")


class BatchPredictionRequest(BaseModel):
    """Request model for batch predictions."""
    symbol: str
    timeframe: str
    timestamps: List[datetime]
    lookback_bars: int = Field(100, ge=20, le=500)
    model_version: str = Field('latest')


class ModelInfoResponse(BaseModel):
    """Response model for model information."""
    model_type: str
    threshold_peak: float
    threshold_valley: float
    feature_count: int | str
    feature_names: Optional[List[str]]


# API Endpoints

@router.post("/predict", response_model=ReversalPredictionResponse)
async def predict_reversal(
    request: ReversalPredictionRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Predict reversal probability for current or specified candle.

    Returns probabilities for valley/neutral/peak and a trading signal
    if confidence exceeds threshold.

    Example:
    ```
    POST /api/v1/reversals/predict
    {
        "symbol": "CrudeOIL",
        "timeframe": "H1",
        "timestamp": "2024-01-15T12:00:00",
        "model_version": "latest"
    }
    ```

    Response:
    ```
    {
        "symbol": "CrudeOIL",
        "timeframe": "H1",
        "timestamp": "2024-01-15T12:00:00",
        "valley_prob": 0.15,
        "neutral_prob": 0.10,
        "peak_prob": 0.75,
        "signal": "SHORT",
        "confidence": 0.75
    }
    ```
    """
    try:
        # Get predictor (cached by model version)
        predictor = await get_predictor(
            session=session,
            model_version=request.model_version
        )

        # Make prediction
        result = await predictor.predict(
            symbol=request.symbol,
            timeframe=request.timeframe,
            current_time=request.timestamp,
            lookback_bars=request.lookback_bars
        )

        return ReversalPredictionResponse(**result)

    except Exception as e:
        logger.error(f"Prediction failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")


@router.post("/predict/batch", response_model=List[ReversalPredictionResponse])
async def predict_reversal_batch(
    request: BatchPredictionRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Predict reversals for multiple time points.

    Useful for backtesting or generating historical signals.

    Example:
    ```
    POST /api/v1/reversals/predict/batch
    {
        "symbol": "CrudeOIL",
        "timeframe": "H1",
        "timestamps": [
            "2024-01-15T12:00:00",
            "2024-01-15T13:00:00",
            "2024-01-15T14:00:00"
        ],
        "model_version": "latest"
    }
    ```
    """
    try:
        predictor = await get_predictor(
            session=session,
            model_version=request.model_version
        )

        results = await predictor.predict_batch(
            symbol=request.symbol,
            timeframe=request.timeframe,
            times=request.timestamps,
            lookback_bars=request.lookback_bars
        )

        return [ReversalPredictionResponse(**r) for r in results]

    except Exception as e:
        logger.error(f"Batch prediction failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Batch prediction failed: {str(e)}")


@router.get("/model/info", response_model=ModelInfoResponse)
async def get_model_info(
    model_version: str = Query('latest', description="Model version"),
    session: AsyncSession = Depends(get_session)
):
    """
    Get information about the loaded model.

    Returns model type, thresholds, and feature information.

    Example:
    ```
    GET /api/v1/reversals/model/info?model_version=latest
    ```
    """
    try:
        predictor = await get_predictor(
            session=session,
            model_version=model_version
        )

        info = predictor.get_model_info()
        return ModelInfoResponse(**info)

    except Exception as e:
        logger.error(f"Failed to get model info: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get model info: {str(e)}")


@router.post("/model/reload")
async def reload_model(
    model_version: str = Query('latest', description="Model version to reload"),
    session: AsyncSession = Depends(get_session)
):
    """
    Reload model from MLflow registry.

    Clears cache and loads fresh model. Useful after training new version.

    Example:
    ```
    POST /api/v1/reversals/model/reload?model_version=v2
    ```
    """
    try:
        # Clear cache
        clear_predictor_cache()

        # Load fresh model
        predictor = await get_predictor(
            session=session,
            model_version=model_version
        )

        info = predictor.get_model_info()

        return {
            "status": "success",
            "message": f"Model {model_version} reloaded successfully",
            "model_info": info
        }

    except Exception as e:
        logger.error(f"Failed to reload model: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reload model: {str(e)}")


@router.put("/model/thresholds")
async def update_thresholds(
    peak_threshold: float = Query(..., ge=0.0, le=1.0, description="Peak probability threshold"),
    valley_threshold: float = Query(..., ge=0.0, le=1.0, description="Valley probability threshold"),
    model_version: str = Query('latest', description="Model version"),
    session: AsyncSession = Depends(get_session)
):
    """
    Update probability thresholds for signal generation.

    Higher thresholds = fewer but more confident signals.
    Lower thresholds = more signals but less confident.

    Recommended: 0.70 - 0.85 range

    Example:
    ```
    PUT /api/v1/reversals/model/thresholds?peak_threshold=0.80&valley_threshold=0.80
    ```
    """
    try:
        predictor = await get_predictor(
            session=session,
            model_version=model_version
        )

        predictor.set_thresholds(peak=peak_threshold, valley=valley_threshold)

        return {
            "status": "success",
            "message": "Thresholds updated successfully",
            "peak_threshold": peak_threshold,
            "valley_threshold": valley_threshold
        }

    except Exception as e:
        logger.error(f"Failed to update thresholds: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update thresholds: {str(e)}")


@router.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns:
        Status of the reversal prediction service
    """
    return {
        "status": "healthy",
        "service": "reversal_predictions",
        "timestamp": datetime.utcnow().isoformat()
    }
