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


@router.get("/models/{symbol}/{model_version}/metrics", response_model=List[ModelMetricsResponse])
async def get_model_metrics(
    symbol: str,
    model_version: str,
    forecast_horizon: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get performance metrics for a specific model.

    - Returns metrics for all horizons if forecast_horizon not specified
    - Includes MAE, MAPE, RMSE, directional accuracy
    - Ordered by calculation time (most recent first)
    """
    metrics_repo = ModelMetricsRepository(db)

    if forecast_horizon:
        # Get metrics for specific horizon
        metrics = await metrics_repo.get_by_model_version(
            symbol=symbol,
            model_version=model_version,
            forecast_horizon=forecast_horizon
        )
        if not metrics:
            raise HTTPException(status_code=404, detail="Metrics not found")
        return [metrics]
    else:
        # Get metrics for all horizons
        all_metrics = await metrics_repo.get_all_by_model(
            symbol=symbol,
            model_version=model_version
        )
        if not all_metrics:
            raise HTTPException(status_code=404, detail="No metrics found for this model")
        return all_metrics


@router.get("/metrics/compare/models", response_model=AccuracyComparisonResponse)
async def compare_model_accuracy(
    symbol: str,
    forecast_horizon: str,
    model_versions: List[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Compare accuracy across different model versions for the same horizon.

    Returns:
    - Metrics for each model version
    - Best and worst performers
    - Sorted by MAE (ascending)
    """
    metrics_repo = ModelMetricsRepository(db)

    # Get metrics for all specified models
    comparisons = []

    if model_versions:
        for version in model_versions:
            metrics = await metrics_repo.get_by_model_version(
                symbol=symbol,
                model_version=version,
                forecast_horizon=forecast_horizon
            )
            if metrics:
                comparisons.append({
                    'model_version': version,
                    'mae': metrics.mae,
                    'mape': metrics.mape,
                    'rmse': metrics.rmse,
                    'directional_accuracy': metrics.directional_accuracy,
                    'sample_count': metrics.sample_count
                })
    else:
        # Get all models for this symbol/horizon
        all_metrics = await metrics_repo.get_all_for_symbol_horizon(
            symbol=symbol,
            forecast_horizon=forecast_horizon
        )
        for metrics in all_metrics:
            comparisons.append({
                'model_version': metrics.model_version,
                'mae': metrics.mae,
                'mape': metrics.mape,
                'rmse': metrics.rmse,
                'directional_accuracy': metrics.directional_accuracy,
                'sample_count': metrics.sample_count
            })

    if not comparisons:
        raise HTTPException(status_code=404, detail="No metrics found for comparison")

    # Sort by MAE (lower is better)
    comparisons.sort(key=lambda x: x['mae'])

    return AccuracyComparisonResponse(
        comparison_type='models',
        items=comparisons,
        best_performer=comparisons[0],
        worst_performer=comparisons[-1]
    )


@router.get("/metrics/compare/horizons", response_model=AccuracyComparisonResponse)
async def compare_horizon_accuracy(
    symbol: str,
    model_version: str,
    forecast_horizons: List[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Compare accuracy across different forecast horizons for the same model.

    Returns:
    - Metrics for each horizon
    - Best and worst performing horizons
    - Sorted by MAE (ascending)
    """
    metrics_repo = ModelMetricsRepository(db)

    # Default horizons if not specified
    if not forecast_horizons:
        forecast_horizons = ['1h', '4h', '1d']

    comparisons = []

    for horizon in forecast_horizons:
        metrics = await metrics_repo.get_by_model_version(
            symbol=symbol,
            model_version=model_version,
            forecast_horizon=horizon
        )
        if metrics:
            comparisons.append({
                'forecast_horizon': horizon,
                'mae': metrics.mae,
                'mape': metrics.mape,
                'rmse': metrics.rmse,
                'directional_accuracy': metrics.directional_accuracy,
                'sample_count': metrics.sample_count
            })

    if not comparisons:
        raise HTTPException(status_code=404, detail="No metrics found for comparison")

    # Sort by MAE (lower is better)
    comparisons.sort(key=lambda x: x['mae'])

    return AccuracyComparisonResponse(
        comparison_type='horizons',
        items=comparisons,
        best_performer=comparisons[0],
        worst_performer=comparisons[-1]
    )


@router.post("/metrics/calculate")
async def trigger_metrics_calculation(
    symbol: str,
    model_version: str,
    forecast_horizon: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger calculation of accuracy metrics for a model.

    - Fetches recent forecasts
    - Compares with actual market data
    - Calculates and stores MAE, MAPE, RMSE, directional accuracy
    """
    from src.ml.monitoring.forecast_accuracy_tracker import ForecastAccuracyTracker
    from src.database.repositories.market_data_repository import MarketDataRepository

    forecast_repo = ForecastRepository(db)
    market_data_repo = MarketDataRepository(db)
    metrics_repo = ModelMetricsRepository(db)

    tracker = ForecastAccuracyTracker(
        forecast_repo=forecast_repo,
        market_data_repo=market_data_repo,
        metrics_repo=metrics_repo
    )

    # Calculate and store metrics
    success = await tracker.update_model_metrics(
        symbol=symbol,
        model_version=model_version,
        forecast_horizon=forecast_horizon
    )

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to calculate metrics. Check logs for details."
        )

    return {
        "status": "success",
        "message": f"Metrics calculated for {symbol} {model_version} {forecast_horizon}"
    }
