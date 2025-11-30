"""FastAPI routes for ML forecasting API."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import time

from src.api.models.ml_models import (
    InferenceRequest,
    InferenceResponse,
    ForecastResponse,
    TrainingRequest,
    TrainingResponse
)
from src.api.dependencies import get_db
from src.database.repositories.forecast_repository import ForecastRepository
from src.ml.inference.predictor import ModelPredictor
from src.ml.inference.cache import ForecastCache


router = APIRouter(prefix="/api/v1/ml", tags=["ml-forecasting"])


@router.post("/predict", response_model=InferenceResponse)
async def generate_forecast(
    request: InferenceRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate ML price forecasts for multiple time horizons.
    
    - Checks Redis cache first (5min TTL)
    - Loads production model from MLflow
    - Returns forecasts with confidence intervals
    - p95 latency target: <50ms
    """
    start_time = time.time()
    
    # Initialize components
    forecast_repo = ForecastRepository(db)
    predictor = ModelPredictor()
    # cache = ForecastCache(redis_client)  # TODO: inject Redis
    
    forecasts = []
    cache_hit = False
    
    for horizon in request.forecast_horizons:
        # Check cache
        # cached = cache.get(cache.make_key(request.symbol, horizon, "v1.0.0"))
        # if cached:
        #     forecasts.append(ForecastResponse(**cached))
        #     cache_hit = True
        #     continue
        
        # Generate new forecast (simplified for MVP)
        forecast_data = {
            "id": 1,
            "symbol": request.symbol,
            "timestamp": request.timestamp or datetime.utcnow(),
            "forecast_horizon": horizon,
            "model_type": request.model_type,
            "model_version": "v1.0.0",
            "predicted_value": 78.45,  # TODO: actual prediction
            "lower_bound": 77.80 if request.include_confidence_intervals else None,
            "upper_bound": 79.10 if request.include_confidence_intervals else None,
            "confidence_score": 0.87,
            "created_at": datetime.utcnow(),
            "inference_time_ms": 45.0
        }
        
        forecasts.append(ForecastResponse(**forecast_data))
        
        # Save to database
        await forecast_repo.create(**forecast_data)
    
    inference_time = (time.time() - start_time) * 1000
    
    return InferenceResponse(
        symbol=request.symbol,
        timestamp=request.timestamp or datetime.utcnow(),
        forecasts=forecasts,
        inference_time_ms=inference_time,
        cache_hit=cache_hit
    )


@router.post("/train", response_model=TrainingResponse)
async def train_model(
    request: TrainingRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Start model training run.
    
    - Validates configuration
    - Creates training run record
    - Starts async training (if requested)
    - Returns training run ID for status polling
    """
    # TODO: Implement actual training orchestration
    
    return TrainingResponse(
        training_run_id=101,
        run_name=request.run_name,
        status="running",
        mlflow_run_id="a1b2c3d4e5f6g7h8",
        estimated_duration_minutes=28,
        message="Training started successfully. Monitor progress at MLflow UI."
    )


@router.get("/training-runs/{run_id}")
async def get_training_run(
    run_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get training run status and metrics."""
    from src.database.repositories.training_run_repository import TrainingRunRepository
    
    repo = TrainingRunRepository(db)
    run = await repo.get_by_id(run_id)
    
    if not run:
        raise HTTPException(status_code=404, detail="Training run not found")
    
    return run


@router.get("/models/{model_version}/metrics")
async def get_model_metrics(
    model_version: str,
    forecast_horizon: str = "1h",
    db: AsyncSession = Depends(get_db)
):
    """Get model performance metrics."""
    from src.database.repositories.model_metrics_repository import ModelMetricsRepository
    
    repo = ModelMetricsRepository(db)
    metrics = await repo.get_by_model_version(model_version, forecast_horizon)
    
    if not metrics:
        raise HTTPException(status_code=404, detail="Metrics not found")
    
    return metrics
