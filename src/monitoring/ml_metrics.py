"""Prometheus metrics for ML pipeline."""

from prometheus_client import Counter, Histogram, Gauge


# Training metrics
training_runs_total = Counter(
    'ml_training_runs_total',
    'Total number of training runs',
    ['model_type', 'status']
)

training_duration_seconds = Histogram(
    'ml_training_duration_seconds',
    'Training duration in seconds',
    ['model_type']
)

# Inference metrics
inference_requests_total = Counter(
    'ml_inference_requests_total',
    'Total number of inference requests',
    ['model_type', 'horizon']
)

inference_latency_ms = Histogram(
    'ml_inference_latency_milliseconds',
    'Inference latency in milliseconds',
    ['model_type', 'cache_hit']
)

# Model accuracy metrics
model_accuracy_mpe = Gauge(
    'ml_model_accuracy_mpe',
    'Model Mean Percentage Error',
    ['model_version', 'horizon']
)

model_accuracy_rmse = Gauge(
    'ml_model_accuracy_rmse',
    'Model Root Mean Squared Error',
    ['model_version', 'horizon']
)
