"""
Request/response logging for MT4 ZMQ communications (T110).

Provides comprehensive logging with sensitive data masking and performance tracking.
"""
import json
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from src.utils.mt4_helpers import get_mt4_logger

logger = get_mt4_logger("mt4_request_logger")


# Fields that should be masked in logs
SENSITIVE_FIELDS = {
    "password",
    "api_key",
    "secret",
    "token",
    "auth_token",
    "encryption_key",
    "private_key",
    "account_number",  # Mask account numbers for privacy
}


class MT4RequestLogger:
    """Logger for MT4 ZMQ request/response communications (T110)."""

    @staticmethod
    def mask_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mask sensitive fields in request/response data.

        Args:
            data: Data dictionary to mask

        Returns:
            Masked data dictionary (new copy)
        """
        masked = {}

        for key, value in data.items():
            key_lower = key.lower()

            # Check if field should be masked
            if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
                masked[key] = "***MASKED***"
            # Recursively mask nested dicts
            elif isinstance(value, dict):
                masked[key] = MT4RequestLogger.mask_sensitive_data(value)
            # Handle lists
            elif isinstance(value, list):
                masked[key] = [
                    MT4RequestLogger.mask_sensitive_data(item)
                    if isinstance(item, dict) else item
                    for item in value
                ]
            # Keep other values
            else:
                masked[key] = value

        return masked

    @staticmethod
    def serialize_for_logging(data: Any) -> Any:
        """
        Serialize data for JSON logging (handles Decimal, datetime, etc.).

        Args:
            data: Data to serialize

        Returns:
            JSON-serializable data
        """
        if isinstance(data, dict):
            return {k: MT4RequestLogger.serialize_for_logging(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [MT4RequestLogger.serialize_for_logging(item) for item in data]
        elif isinstance(data, Decimal):
            return float(data)
        elif isinstance(data, datetime):
            return data.isoformat()
        else:
            return data

    @staticmethod
    def log_request(
        command_type: str,
        correlation_id: str,
        magic_number: int,
        request_data: Dict[str, Any],
        encrypted: bool = False
    ) -> float:
        """
        Log outgoing MT4 request.

        Args:
            command_type: Type of command (e.g., "CREATE_INSTANT_ORDER")
            correlation_id: Unique request ID for tracking
            magic_number: EA magic number
            request_data: Full request payload
            encrypted: Whether encryption is enabled

        Returns:
            Request timestamp (for latency calculation)
        """
        request_time = time.time()

        # Mask sensitive data
        masked_data = MT4RequestLogger.mask_sensitive_data(request_data)
        serializable_data = MT4RequestLogger.serialize_for_logging(masked_data)

        # Calculate request size
        request_size = len(json.dumps(serializable_data))

        logger.info(
            "mt4_request_sent",
            command_type=command_type,
            correlation_id=correlation_id,
            magic_number=magic_number,
            encrypted=encrypted,
            request_size_bytes=request_size,
            request_data=serializable_data,
            timestamp=datetime.utcnow().isoformat()
        )

        return request_time

    @staticmethod
    def log_response(
        command_type: str,
        correlation_id: str,
        magic_number: int,
        response_data: Dict[str, Any],
        request_time: float,
        success: bool,
        error_code: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> None:
        """
        Log incoming MT4 response.

        Args:
            command_type: Type of command
            correlation_id: Request correlation ID
            magic_number: EA magic number
            response_data: Full response payload
            request_time: Original request timestamp
            success: Whether request was successful
            error_code: Optional MT4 error code
            error_message: Optional error message
        """
        response_time = time.time()
        latency_ms = (response_time - request_time) * 1000

        # Mask sensitive data
        masked_data = MT4RequestLogger.mask_sensitive_data(response_data)
        serializable_data = MT4RequestLogger.serialize_for_logging(masked_data)

        # Calculate response size
        response_size = len(json.dumps(serializable_data))

        log_method = logger.info if success else logger.error
        event_name = "mt4_response_received" if success else "mt4_response_error"

        log_data = {
            "command_type": command_type,
            "correlation_id": correlation_id,
            "magic_number": magic_number,
            "success": success,
            "latency_ms": round(latency_ms, 2),
            "response_size_bytes": response_size,
            "response_data": serializable_data,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Add error details if present
        if not success:
            log_data["error_code"] = error_code
            log_data["error_message"] = error_message

        log_method(event_name, **log_data)

    @staticmethod
    def log_timeout(
        command_type: str,
        correlation_id: str,
        magic_number: int,
        request_time: float,
        timeout_ms: int
    ) -> None:
        """
        Log request timeout.

        Args:
            command_type: Type of command
            correlation_id: Request correlation ID
            magic_number: EA magic number
            request_time: Original request timestamp
            timeout_ms: Configured timeout
        """
        elapsed_ms = (time.time() - request_time) * 1000

        logger.error(
            "mt4_request_timeout",
            command_type=command_type,
            correlation_id=correlation_id,
            magic_number=magic_number,
            timeout_ms=timeout_ms,
            elapsed_ms=round(elapsed_ms, 2),
            timestamp=datetime.utcnow().isoformat()
        )

    @staticmethod
    def log_circuit_breaker_blocked(
        command_type: str,
        correlation_id: str,
        magic_number: int,
        circuit_state: str,
        failure_count: int
    ) -> None:
        """
        Log request blocked by circuit breaker.

        Args:
            command_type: Type of command
            correlation_id: Request correlation ID
            magic_number: EA magic number
            circuit_state: Circuit breaker state (OPEN/HALF_OPEN)
            failure_count: Current failure count
        """
        logger.warning(
            "mt4_request_blocked_circuit_breaker",
            command_type=command_type,
            correlation_id=correlation_id,
            magic_number=magic_number,
            circuit_state=circuit_state,
            failure_count=failure_count,
            timestamp=datetime.utcnow().isoformat()
        )

    @staticmethod
    def log_zmq_error(
        command_type: str,
        correlation_id: str,
        magic_number: int,
        request_time: float,
        error_type: str,
        error_details: str
    ) -> None:
        """
        Log ZMQ-level error.

        Args:
            command_type: Type of command
            correlation_id: Request correlation ID
            magic_number: EA magic number
            request_time: Original request timestamp
            error_type: Type of ZMQ error
            error_details: Error details
        """
        elapsed_ms = (time.time() - request_time) * 1000

        logger.error(
            "mt4_zmq_error",
            command_type=command_type,
            correlation_id=correlation_id,
            magic_number=magic_number,
            error_type=error_type,
            error_details=error_details,
            elapsed_ms=round(elapsed_ms, 2),
            timestamp=datetime.utcnow().isoformat()
        )

    @staticmethod
    def log_connection_event(
        event_type: str,
        magic_number: int,
        host: str,
        port: int,
        encrypted: bool,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log connection-level events (connect, disconnect, reconnect).

        Args:
            event_type: Type of event (CONNECT, DISCONNECT, RECONNECT)
            magic_number: EA magic number
            host: MT4 host
            port: MT4 port
            encrypted: Whether encryption is enabled
            details: Optional additional details
        """
        event_name = f"mt4_connection_{event_type.lower()}"

        log_data = {
            "magic_number": magic_number,
            "host": host,
            "port": port,
            "encrypted": encrypted,
            "timestamp": datetime.utcnow().isoformat()
        }

        if details:
            log_data.update(details)

        logger.info(event_name, **log_data)


# Helper function for backwards compatibility
def log_mt4_request(
    command_type: str,
    correlation_id: str,
    magic_number: int,
    request_data: Dict[str, Any],
    encrypted: bool = False
) -> float:
    """Convenience function for logging requests."""
    return MT4RequestLogger.log_request(
        command_type, correlation_id, magic_number, request_data, encrypted
    )


def log_mt4_response(
    command_type: str,
    correlation_id: str,
    magic_number: int,
    response_data: Dict[str, Any],
    request_time: float,
    success: bool,
    error_code: Optional[int] = None,
    error_message: Optional[str] = None
) -> None:
    """Convenience function for logging responses."""
    MT4RequestLogger.log_response(
        command_type, correlation_id, magic_number, response_data,
        request_time, success, error_code, error_message
    )


# Module loaded - logging ready (print removed for MCP compatibility)
