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
    TrainingResponse,
    TrainingRunStatusResponse,
    ModelMetricsResponse,
    AccuracyComparisonResponse
)
from src.api.dependencies import get_db
from src.database.repositories.forecast_repository import ForecastRepository
from src.database.repositories.training_run_repository import TrainingRunRepository
from src.database.repositories.model_metrics_repository import ModelMetricsRepository
from src.ml.inference.predictor import ModelPredictor
from src.ml.inference.cache import ForecastCache
from src.ml.data.market_data_loader import MarketDataLoader
from src.services.ml_inference_service import MLInferenceService
from src.services.ml_training_service import MLTrainingService
from src.ml.training.config import load_config


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

    # Initialize components (in production, these would be dependency-injected)
    forecast_repo = ForecastRepository(db)
    predictor = ModelPredictor()

    # TODO: Inject Redis client from dependencies in production
    # For now, create mock cache that always misses
    from unittest.mock import Mock
    mock_redis = Mock()
    mock_redis.get = Mock(return_value=None)
    mock_redis.setex = Mock()
    cache = ForecastCache(mock_redis)

    data_loader = MarketDataLoader(db)

    # Initialize inference service
    inference_service = MLInferenceService(
        predictor=predictor,
        cache=cache,
        forecast_repo=forecast_repo,
        data_loader=data_loader
    )

    # Generate forecasts for all requested horizons
    model_version = "v1.0.0"  # TODO: Get from model registry/config

    forecast_results = await inference_service.generate_forecasts(
        symbol=request.symbol,
        horizons=request.forecast_horizons,
        model_version=model_version,
        model_type=request.model_type,
        include_confidence=request.include_confidence_intervals
    )

    # Convert to ForecastResponse objects
    forecasts = [ForecastResponse(**result) for result in forecast_results]

    inference_time = (time.time() - start_time) * 1000
    cache_hit = all(f.get('cache_hit', False) for f in forecast_results) if forecast_results else False

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
    # Initialize repositories
    training_run_repo = TrainingRunRepository(db)
    metrics_repo = ModelMetricsRepository(db)
    data_loader = MarketDataLoader(db)

    # Load configuration (use override if provided, otherwise use defaults)
    if request.config_override:
        config = request.config_override
    else:
        # Load default config for model type
        config = load_config(f'config/ml/{request.model_type}_config.yaml')

    # Initialize training service
    training_service = MLTrainingService(
        data_loader=data_loader,
        training_run_repo=training_run_repo,
        metrics_repo=metrics_repo
    )

    # Start training (async or blocking based on request)
    if request.async_training:
        # For MVP, we'll run synchronously but mark as "running"
        # In production, this would use Celery/background tasks
        try:
            result = await training_service.train_model(
                symbol=request.symbol,
                model_type=request.model_type,
                config=config,
                run_name=request.run_name
            )

            return TrainingResponse(
                training_run_id=result['training_run_id'],
                run_name=request.run_name,
                status="completed",
                mlflow_run_id=result.get('mlflow_run_id'),
                estimated_duration_minutes=result.get('training_duration_seconds', 0) / 60,
                message=f"Training completed. Model version: {result.get('model_version', 'unknown')}"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")
    else:
        # Synchronous training
        result = await training_service.train_model(
            symbol=request.symbol,
            model_type=request.model_type,
            config=config,
            run_name=request.run_name
        )

        return TrainingResponse(
            training_run_id=result['training_run_id'],
            run_name=request.run_name,
            status="completed",
            mlflow_run_id=None,
            estimated_duration_minutes=None,
            message="Training completed successfully"
        )


@router.get("/training-runs/{run_id}", response_model=TrainingRunStatusResponse)
async def get_training_run(
    run_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed training run status and metrics.

    - Returns training run metadata from database
    - Fetches MLflow run details if available
    - Includes hyperparameters, metrics, and current model stage
    - Provides error information if training failed
    """
    training_run_repo = TrainingRunRepository(db)
    run = await training_run_repo.get_by_id(run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Training run not found")

    # Build base response from database record
    response_data = {
        'training_run_id': run.id,
        'run_name': run.run_name,
        'symbol': run.symbol,
        'model_type': run.model_type,
        'status': run.status,
        'model_version': run.model_version,
        'mlflow_run_id': run.mlflow_run_id,
        'started_at': run.started_at,
        'completed_at': run.completed_at,
        'duration_seconds': run.duration_seconds,
        'error_message': run.error_message
    }

    # If MLflow run exists, fetch additional metadata
    if run.mlflow_run_id:
        try:
            from src.ml.tracking.model_registry import ModelRegistry
            import mlflow

            # Initialize MLflow client
            registry = ModelRegistry()
            mlflow_client = registry.client

            # Get MLflow run details
            mlflow_run = mlflow_client.get_run(run.mlflow_run_id)

            # Extract hyperparameters
            response_data['hyperparameters'] = dict(mlflow_run.data.params)

            # Extract metrics
            response_data['metrics'] = dict(mlflow_run.data.metrics)

            # Get artifact URI
            response_data['artifact_uri'] = mlflow_run.info.artifact_uri

            # Get model stage if model was registered
            if run.model_version:
                try:
                    # Parse model name from run tags or use default pattern
                    model_name = mlflow_run.data.tags.get('model_name', f"{run.model_type}_forecaster_{run.symbol}")

                    # Get latest version for this model
                    versions = registry.list_model_versions(model_name)
                    if versions:
                        # Find version matching this run
                        for version in versions:
                            if version.run_id == run.mlflow_run_id:
                                response_data['current_stage'] = version.current_stage
                                break
                except Exception as e:
                    # Model may not be registered yet - not an error
                    pass

        except Exception as e:
            # Log error but don't fail the request - database info is still valuable
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to fetch MLflow metadata for run {run.mlflow_run_id}: {str(e)}")

    return TrainingRunStatusResponse(**response_data)


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
