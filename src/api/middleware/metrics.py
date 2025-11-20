"""
Prometheus Metrics Middleware

Collects and exposes metrics for API performance monitoring.
"""
import time
from typing import Callable

from fastapi import Request, Response
from prometheus_client import Counter, Histogram, Gauge
from starlette.middleware.base import BaseHTTPMiddleware

# Prometheus metrics
REQUEST_COUNT = Counter(
    "api_requests_total",
    "Total number of API requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_DURATION = Histogram(
    "api_request_duration_seconds",
    "API request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

REQUEST_SIZE = Histogram(
    "api_request_size_bytes",
    "API request size in bytes",
    ["method", "endpoint"],
)

RESPONSE_SIZE = Histogram(
    "api_response_size_bytes",
    "API response size in bytes",
    ["method", "endpoint"],
)

ACTIVE_REQUESTS = Gauge(
    "api_active_requests",
    "Number of active API requests",
)

ERROR_COUNT = Counter(
    "api_errors_total",
    "Total number of API errors",
    ["method", "endpoint", "error_type"],
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Metrics collection middleware for Prometheus monitoring.

    Collects:
    - Request counts by method/endpoint/status
    - Request duration histograms
    - Request/response size histograms
    - Active request gauge
    - Error counts
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and collect metrics.

        Args:
            request: Incoming request
            call_next: Next middleware/endpoint

        Returns:
            Response from endpoint
        """
        # Extract request information
        method = request.method
        endpoint = request.url.path

        # Skip metrics endpoint itself
        if endpoint == "/metrics":
            return await call_next(request)

        # Increment active requests
        ACTIVE_REQUESTS.inc()

        # Get request size
        request_size = int(request.headers.get("content-length", 0))
        REQUEST_SIZE.labels(method=method, endpoint=endpoint).observe(request_size)

        # Start timing
        start_time = time.time()

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Record metrics
            REQUEST_COUNT.labels(
                method=method, endpoint=endpoint, status_code=response.status_code
            ).inc()

            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

            # Get response size (if available)
            response_size = int(response.headers.get("content-length", 0))
            if response_size > 0:
                RESPONSE_SIZE.labels(method=method, endpoint=endpoint).observe(
                    response_size
                )

            return response

        except Exception as e:
            # Record error
            ERROR_COUNT.labels(
                method=method,
                endpoint=endpoint,
                error_type=type(e).__name__,
            ).inc()

            # Re-raise
            raise

        finally:
            # Decrement active requests
            ACTIVE_REQUESTS.dec()


# Additional custom metrics for trading operations
TRADING_OPERATIONS = Counter(
    "trading_operations_total",
    "Total number of trading operations",
    ["operation_type", "status"],
)

AGENT_OPERATIONS = Counter(
    "agent_operations_total",
    "Total number of agent operations",
    ["agent_id", "operation_type", "status"],
)

POSITION_COUNT = Gauge(
    "open_positions_count",
    "Number of open trading positions",
    ["symbol"],
)

ML_PREDICTIONS = Counter(
    "ml_predictions_total",
    "Total number of ML predictions",
    ["model_type", "symbol"],
)

ML_PREDICTION_DURATION = Histogram(
    "ml_prediction_duration_seconds",
    "ML prediction generation duration",
    ["model_type"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)


def record_trading_operation(operation_type: str, status: str) -> None:
    """
    Record a trading operation.

    Args:
        operation_type: Type of operation (e.g., 'place_order', 'close_position')
        status: Operation status ('success', 'failure')
    """
    TRADING_OPERATIONS.labels(operation_type=operation_type, status=status).inc()


def record_agent_operation(agent_id: str, operation_type: str, status: str) -> None:
    """
    Record an agent operation.

    Args:
        agent_id: Agent identifier
        operation_type: Type of operation
        status: Operation status
    """
    AGENT_OPERATIONS.labels(
        agent_id=agent_id, operation_type=operation_type, status=status
    ).inc()


def update_position_count(symbol: str, count: int) -> None:
    """
    Update open position count for a symbol.

    Args:
        symbol: Trading symbol
        count: Number of open positions
    """
    POSITION_COUNT.labels(symbol=symbol).set(count)


def record_ml_prediction(model_type: str, symbol: str, duration: float) -> None:
    """
    Record an ML prediction.

    Args:
        model_type: Type of ML model
        symbol: Trading symbol
        duration: Prediction generation duration in seconds
    """
    ML_PREDICTIONS.labels(model_type=model_type, symbol=symbol).inc()
    ML_PREDICTION_DURATION.labels(model_type=model_type).observe(duration)
