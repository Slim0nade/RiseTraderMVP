"""
MT4 utility functions and structured logging.

Provides structured JSON logging with correlation IDs for MT4 operations.
"""
import json
import logging
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import structlog


# =============================================================================
# Structured Logging Setup
# =============================================================================

def setup_mt4_logging(log_level: str = "INFO", json_format: bool = True):
    """
    Setup structured logging for MT4 integration.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Whether to output JSON format (True) or console format (False)
    """
    if json_format:
        # JSON format for production
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # Console format for development
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.dev.ConsoleRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,  # CRITICAL: MCP requires stdout for JSON only
        level=getattr(logging, log_level.upper())
    )


def get_mt4_logger(name: str = "mt4_integration"):
    """
    Get a structured logger for MT4 operations.

    Args:
        name: Logger name (defaults to 'mt4_integration')

    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


# =============================================================================
# Correlation ID Management
# =============================================================================

def generate_correlation_id() -> str:
    """
    Generate a new correlation ID for request tracing.

    Returns:
        UUID string for correlation tracking
    """
    return str(uuid.uuid4())


def log_mt4_operation(
    logger,
    operation: str,
    correlation_id: str,
    ea_id: Optional[str] = None,
    magic_number: Optional[int] = None,
    level: str = "info",
    **kwargs
):
    """
    Log an MT4 operation with structured context.

    Args:
        logger: Structured logger instance
        operation: Operation name (e.g., 'order_submit', 'position_update')
        correlation_id: Correlation ID for tracking
        ea_id: EA identifier
        magic_number: MT4 magic number
        level: Log level (debug, info, warning, error, critical)
        **kwargs: Additional context fields
    """
    log_func = getattr(logger, level.lower())

    context = {
        "operation": operation,
        "correlation_id": correlation_id,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if ea_id:
        context["ea_id"] = ea_id
    if magic_number:
        context["magic_number"] = magic_number

    context.update(kwargs)

    log_func("mt4_operation", **context)


def log_order_submitted(
    logger,
    correlation_id: str,
    ea_id: str,
    order_id: str,
    symbol: str,
    direction: str,
    volume: float,
    **kwargs
):
    """Log order submission."""
    log_mt4_operation(
        logger=logger,
        operation="order_submitted",
        correlation_id=correlation_id,
        ea_id=ea_id,
        level="info",
        order_id=order_id,
        symbol=symbol,
        direction=direction,
        volume=volume,
        **kwargs
    )


def log_order_confirmed(
    logger,
    correlation_id: str,
    ea_id: str,
    order_id: str,
    ticket_number: int,
    latency_ms: float,
    **kwargs
):
    """Log order confirmation."""
    log_mt4_operation(
        logger=logger,
        operation="order_confirmed",
        correlation_id=correlation_id,
        ea_id=ea_id,
        level="info",
        order_id=order_id,
        ticket_number=ticket_number,
        latency_ms=latency_ms,
        **kwargs
    )


def log_order_rejected(
    logger,
    correlation_id: str,
    ea_id: str,
    order_id: str,
    error_code: int,
    error_message: str,
    **kwargs
):
    """Log order rejection."""
    log_mt4_operation(
        logger=logger,
        operation="order_rejected",
        correlation_id=correlation_id,
        ea_id=ea_id,
        level="warning",
        order_id=order_id,
        error_code=error_code,
        error_message=error_message,
        **kwargs
    )


def log_connection_status(
    logger,
    ea_id: str,
    magic_number: int,
    status: str,
    **kwargs
):
    """Log connection status change."""
    correlation_id = generate_correlation_id()
    log_mt4_operation(
        logger=logger,
        operation="connection_status_changed",
        correlation_id=correlation_id,
        ea_id=ea_id,
        magic_number=magic_number,
        level="info" if status == "ACTIVE" else "warning",
        status=status,
        **kwargs
    )


def log_zmq_command(
    logger,
    correlation_id: str,
    command_type: str,
    duration_ms: float,
    success: bool,
    **kwargs
):
    """Log ZMQ command execution."""
    log_mt4_operation(
        logger=logger,
        operation="zmq_command",
        correlation_id=correlation_id,
        level="debug",
        command_type=command_type,
        duration_ms=duration_ms,
        success=success,
        **kwargs
    )


def log_circuit_breaker_event(
    logger,
    ea_id: str,
    event: str,
    state: str,
    failure_count: int = 0,
    **kwargs
):
    """Log circuit breaker state change."""
    correlation_id = generate_correlation_id()
    log_mt4_operation(
        logger=logger,
        operation="circuit_breaker_event",
        correlation_id=correlation_id,
        ea_id=ea_id,
        level="warning" if state == "OPEN" else "info",
        event=event,
        state=state,
        failure_count=failure_count,
        **kwargs
    )


# =============================================================================
# Helper Functions
# =============================================================================

def sanitize_zmq_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize ZMQ message for logging (remove sensitive data).

    Args:
        message: ZMQ message dictionary

    Returns:
        Sanitized message dictionary
    """
    sensitive_fields = [
        "password", "secret", "api_key", "token",
        "secret_key", "encryption_key"
    ]

    sanitized = message.copy()

    for field in sensitive_fields:
        if field in sanitized:
            sanitized[field] = "***REDACTED***"

    return sanitized


def format_mt4_response(response: Dict[str, Any]) -> str:
    """
    Format MT4 response for logging.

    Args:
        response: MT4 response dictionary

    Returns:
        JSON formatted string
    """
    sanitized = sanitize_zmq_message(response)
    return json.dumps(sanitized, indent=2)


def calculate_latency_ms(start_time: datetime, end_time: Optional[datetime] = None) -> float:
    """
    Calculate latency in milliseconds.

    Args:
        start_time: Operation start time
        end_time: Operation end time (defaults to now)

    Returns:
        Latency in milliseconds
    """
    if end_time is None:
        end_time = datetime.utcnow()

    delta = end_time - start_time
    return delta.total_seconds() * 1000


def truncate_log_field(value: str, max_length: int = 1000) -> str:
    """
    Truncate long log field values.

    Args:
        value: Field value to truncate
        max_length: Maximum length

    Returns:
        Truncated value with indicator
    """
    if len(value) <= max_length:
        return value

    return value[:max_length] + f"... (truncated {len(value) - max_length} chars)"


# =============================================================================
# Audit Logging
# =============================================================================

def log_audit_event(
    logger,
    event_type: str,
    actor: str,
    resource_type: str,
    resource_id: str,
    action: str,
    result: str,
    **kwargs
):
    """
    Log an audit event for compliance and security.

    Args:
        logger: Structured logger instance
        event_type: Type of audit event
        actor: Who performed the action (service, user, agent)
        resource_type: Type of resource (order, position, connection)
        resource_id: Resource identifier
        action: Action performed (CREATE, UPDATE, DELETE, EXECUTE)
        result: Result (SUCCESS, FAILURE, REJECTED)
        **kwargs: Additional audit context
    """
    correlation_id = generate_correlation_id()

    logger.info(
        "audit_event",
        event_type=event_type,
        correlation_id=correlation_id,
        timestamp=datetime.utcnow().isoformat(),
        actor=actor,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        result=result,
        **kwargs
    )


# =============================================================================
# Performance Logging
# =============================================================================

class PerformanceTimer:
    """Context manager for timing operations."""

    def __init__(self, logger, operation: str, correlation_id: str, **context):
        """
        Initialize performance timer.

        Args:
            logger: Structured logger instance
            operation: Operation name
            correlation_id: Correlation ID
            **context: Additional context fields
        """
        self.logger = logger
        self.operation = operation
        self.correlation_id = correlation_id
        self.context = context
        self.start_time = None

    def __enter__(self):
        """Start timer."""
        self.start_time = datetime.utcnow()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timer and log duration."""
        duration_ms = calculate_latency_ms(self.start_time)

        log_mt4_operation(
            logger=self.logger,
            operation=self.operation,
            correlation_id=self.correlation_id,
            level="debug",
            duration_ms=duration_ms,
            success=exc_type is None,
            **self.context
        )

        return False  # Don't suppress exceptions
