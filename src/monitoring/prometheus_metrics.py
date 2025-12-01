"""
Prometheus metrics for ML forecasting system.

Provides metrics for:
- Training duration
- Inference latency
- Model accuracy (MAE, MAPE)
- Forecast generation rate
"""

import logging
from prometheus_client import Counter, Histogram, Gauge, Info
from typing import Optional

logger = logging.getLogger(__name__)


# Training Metrics
training_duration_seconds = Histogram(
    'ml_training_duration_seconds',
    'Time spent training a model',
    ['symbol', 'model_type', 'model_version'],
    buckets=(60, 300, 600, 1800, 3600, 7200, 14400)  # 1min to 4hours
)

training_runs_total = Counter(
    'ml_training_runs_total',
    'Total number of training runs',
    ['symbol', 'model_type', 'status']  # status: completed, failed
)

training_failure_total = Counter(
    'ml_training_failures_total',
    'Total number of failed training runs',
    ['symbol', 'model_type', 'error_type']
)


# Inference Metrics
inference_latency_seconds = Histogram(
    'ml_inference_latency_seconds',
    'Time to generate a forecast',
    ['symbol', 'model_type', 'forecast_horizon'],
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0)  # 10ms to 1s
)

inference_requests_total = Counter(
    'ml_inference_requests_total',
    'Total number of inference requests',
    ['symbol', 'model_type', 'forecast_horizon', 'cache_hit']
)

batch_inference_size = Histogram(
    'ml_batch_inference_size',
    'Number of forecasts in batch prediction',
    buckets=(1, 5, 10, 20, 50, 100)
)


# Model Accuracy Metrics
model_mae = Gauge(
    'ml_model_mae',
    'Mean Absolute Error for model',
    ['symbol', 'model_version', 'forecast_horizon']
)

model_mape = Gauge(
    'ml_model_mape_percent',
    'Mean Absolute Percentage Error for model (%)',
    ['symbol', 'model_version', 'forecast_horizon']
)

model_rmse = Gauge(
    'ml_model_rmse',
    'Root Mean Squared Error for model',
    ['symbol', 'model_version', 'forecast_horizon']
)

model_directional_accuracy = Gauge(
    'ml_model_directional_accuracy_percent',
    'Directional accuracy for model (%)',
    ['symbol', 'model_version', 'forecast_horizon']
)


# Forecast Generation Metrics
forecasts_generated_total = Counter(
    'ml_forecasts_generated_total',
    'Total forecasts generated',
    ['symbol', 'model_type', 'forecast_horizon']
)

forecast_cache_hits_total = Counter(
    'ml_forecast_cache_hits_total',
    'Total forecast cache hits',
    ['symbol', 'forecast_horizon']
)

forecast_cache_misses_total = Counter(
    'ml_forecast_cache_misses_total',
    'Total forecast cache misses',
    ['symbol', 'forecast_horizon']
)


# Model Registry Metrics
model_stage_transitions_total = Counter(
    'ml_model_stage_transitions_total',
    'Total model stage transitions',
    ['model_name', 'from_stage', 'to_stage']
)

models_in_production = Gauge(
    'ml_models_in_production',
    'Number of models currently in Production stage'
)

models_in_staging = Gauge(
    'ml_models_in_staging',
    'Number of models currently in Staging stage'
)


# Data Loading Metrics
market_data_load_duration_seconds = Histogram(
    'ml_market_data_load_duration_seconds',
    'Time to load market data for training',
    ['symbol', 'data_points'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0)
)

exogenous_data_load_duration_seconds = Histogram(
    'ml_exogenous_data_load_duration_seconds',
    'Time to load exogenous variables',
    ['variable_name', 'data_points'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0)
)


# MLflow Integration Metrics
mlflow_model_loads_total = Counter(
    'ml_mlflow_model_loads_total',
    'Total MLflow model loads',
    ['model_name', 'stage']
)

mlflow_model_registrations_total = Counter(
    'ml_mlflow_model_registrations_total',
    'Total model registrations to MLflow',
    ['model_name']
)


# System Health Metrics
model_info = Info(
    'ml_model_info',
    'Information about deployed ML models'
)


class PrometheusMetricsRecorder:
    """
    Helper class to record ML metrics to Prometheus.

    Provides convenient methods for instrumenting ML operations.
    """

    @staticmethod
    def record_training_duration(
        symbol: str,
        model_type: str,
        model_version: str,
        duration_seconds: float
    ):
        """Record training duration."""
        try:
            training_duration_seconds.labels(
                symbol=symbol,
                model_type=model_type,
                model_version=model_version
            ).observe(duration_seconds)
            logger.debug(f"Recorded training duration: {duration_seconds}s for {symbol} {model_type}")
        except Exception as e:
            logger.error(f"Failed to record training duration: {str(e)}")

    @staticmethod
    def record_training_completion(
        symbol: str,
        model_type: str,
        status: str
    ):
        """Record training run completion."""
        try:
            training_runs_total.labels(
                symbol=symbol,
                model_type=model_type,
                status=status
            ).inc()
        except Exception as e:
            logger.error(f"Failed to record training completion: {str(e)}")

    @staticmethod
    def record_training_failure(
        symbol: str,
        model_type: str,
        error_type: str
    ):
        """Record training failure."""
        try:
            training_failure_total.labels(
                symbol=symbol,
                model_type=model_type,
                error_type=error_type
            ).inc()
        except Exception as e:
            logger.error(f"Failed to record training failure: {str(e)}")

    @staticmethod
    def record_inference_latency(
        symbol: str,
        model_type: str,
        forecast_horizon: str,
        latency_seconds: float
    ):
        """Record inference latency."""
        try:
            inference_latency_seconds.labels(
                symbol=symbol,
                model_type=model_type,
                forecast_horizon=forecast_horizon
            ).observe(latency_seconds)
        except Exception as e:
            logger.error(f"Failed to record inference latency: {str(e)}")

    @staticmethod
    def record_inference_request(
        symbol: str,
        model_type: str,
        forecast_horizon: str,
        cache_hit: bool
    ):
        """Record inference request."""
        try:
            inference_requests_total.labels(
                symbol=symbol,
                model_type=model_type,
                forecast_horizon=forecast_horizon,
                cache_hit=str(cache_hit).lower()
            ).inc()

            if cache_hit:
                forecast_cache_hits_total.labels(
                    symbol=symbol,
                    forecast_horizon=forecast_horizon
                ).inc()
            else:
                forecast_cache_misses_total.labels(
                    symbol=symbol,
                    forecast_horizon=forecast_horizon
                ).inc()
        except Exception as e:
            logger.error(f"Failed to record inference request: {str(e)}")

    @staticmethod
    def record_model_accuracy(
        symbol: str,
        model_version: str,
        forecast_horizon: str,
        mae: float,
        mape: float,
        rmse: float,
        directional_accuracy: Optional[float] = None
    ):
        """Record model accuracy metrics."""
        try:
            model_mae.labels(
                symbol=symbol,
                model_version=model_version,
                forecast_horizon=forecast_horizon
            ).set(mae)

            model_mape.labels(
                symbol=symbol,
                model_version=model_version,
                forecast_horizon=forecast_horizon
            ).set(mape)

            model_rmse.labels(
                symbol=symbol,
                model_version=model_version,
                forecast_horizon=forecast_horizon
            ).set(rmse)

            if directional_accuracy is not None:
                model_directional_accuracy.labels(
                    symbol=symbol,
                    model_version=model_version,
                    forecast_horizon=forecast_horizon
                ).set(directional_accuracy)

            logger.debug(f"Recorded accuracy metrics for {symbol} {model_version} {forecast_horizon}")
        except Exception as e:
            logger.error(f"Failed to record model accuracy: {str(e)}")

    @staticmethod
    def record_forecast_generated(
        symbol: str,
        model_type: str,
        forecast_horizon: str
    ):
        """Record forecast generation."""
        try:
            forecasts_generated_total.labels(
                symbol=symbol,
                model_type=model_type,
                forecast_horizon=forecast_horizon
            ).inc()
        except Exception as e:
            logger.error(f"Failed to record forecast generation: {str(e)}")

    @staticmethod
    def record_model_stage_transition(
        model_name: str,
        from_stage: str,
        to_stage: str
    ):
        """Record model stage transition."""
        try:
            model_stage_transitions_total.labels(
                model_name=model_name,
                from_stage=from_stage,
                to_stage=to_stage
            ).inc()
        except Exception as e:
            logger.error(f"Failed to record stage transition: {str(e)}")

    @staticmethod
    def update_model_counts(production_count: int, staging_count: int):
        """Update model stage counts."""
        try:
            models_in_production.set(production_count)
            models_in_staging.set(staging_count)
        except Exception as e:
            logger.error(f"Failed to update model counts: {str(e)}")

    @staticmethod
    def record_data_load(
        symbol: str,
        duration_seconds: float,
        data_points: int,
        data_type: str = 'market'
    ):
        """Record data loading duration."""
        try:
            if data_type == 'market':
                market_data_load_duration_seconds.labels(
                    symbol=symbol,
                    data_points=str(data_points)
                ).observe(duration_seconds)
            elif data_type == 'exogenous':
                exogenous_data_load_duration_seconds.labels(
                    variable_name=symbol,
                    data_points=str(data_points)
                ).observe(duration_seconds)
        except Exception as e:
            logger.error(f"Failed to record data load: {str(e)}")

    @staticmethod
    def record_mlflow_model_load(model_name: str, stage: str):
        """Record MLflow model load."""
        try:
            mlflow_model_loads_total.labels(
                model_name=model_name,
                stage=stage
            ).inc()
        except Exception as e:
            logger.error(f"Failed to record MLflow model load: {str(e)}")

    @staticmethod
    def record_mlflow_model_registration(model_name: str):
        """Record MLflow model registration."""
        try:
            mlflow_model_registrations_total.labels(
                model_name=model_name
            ).inc()
        except Exception as e:
            logger.error(f"Failed to record MLflow model registration: {str(e)}")
