"""
Global Error Handling Middleware

Provides consistent error responses across the API with proper HTTP status codes,
error messages, and structured error details.
"""
from typing import Any, Dict, Optional

import structlog
from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)


class ErrorResponse:
    """
    Standardized error response format.
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        """
        Initialize error response.

        Args:
            status_code: HTTP status code
            message: Error message
            error_code: Application-specific error code
            details: Additional error details
            request_id: Request ID for tracking
        """
        self.status_code = status_code
        self.message = message
        self.error_code = error_code or f"ERROR_{status_code}"
        self.details = details or {}
        self.request_id = request_id

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON response.

        Returns:
            Error response dictionary
        """
        response = {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "status_code": self.status_code,
            }
        }

        if self.details:
            response["error"]["details"] = self.details

        if self.request_id:
            response["error"]["request_id"] = self.request_id

        return response


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handle FastAPI HTTPException.

    Args:
        request: Request that caused the error
        exc: HTTPException instance

    Returns:
        JSONResponse with error details
    """
    request_id = getattr(request.state, "request_id", None)

    error_response = ErrorResponse(
        status_code=exc.status_code,
        message=exc.detail,
        error_code=f"HTTP_{exc.status_code}",
        request_id=request_id,
    )

    logger.warning(
        "http_exception",
        request_id=request_id,
        status_code=exc.status_code,
        message=exc.detail,
        url=str(request.url),
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.to_dict(),
    )


async def starlette_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """
    Handle Starlette HTTPException.

    Args:
        request: Request that caused the error
        exc: StarletteHTTPException instance

    Returns:
        JSONResponse with error details
    """
    request_id = getattr(request.state, "request_id", None)

    error_response = ErrorResponse(
        status_code=exc.status_code,
        message=exc.detail,
        error_code=f"HTTP_{exc.status_code}",
        request_id=request_id,
    )

    logger.warning(
        "starlette_exception",
        request_id=request_id,
        status_code=exc.status_code,
        message=exc.detail,
        url=str(request.url),
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.to_dict(),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle request validation errors.

    Args:
        request: Request that caused the error
        exc: RequestValidationError instance

    Returns:
        JSONResponse with validation error details
    """
    request_id = getattr(request.state, "request_id", None)

    # Extract validation errors
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )

    error_response = ErrorResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message="Request validation failed",
        error_code="VALIDATION_ERROR",
        details={"validation_errors": errors},
        request_id=request_id,
    )

    logger.warning(
        "validation_error",
        request_id=request_id,
        errors=errors,
        url=str(request.url),
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.to_dict(),
    )


async def pydantic_validation_exception_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors.

    Args:
        request: Request that caused the error
        exc: ValidationError instance

    Returns:
        JSONResponse with validation error details
    """
    request_id = getattr(request.state, "request_id", None)

    # Extract validation errors
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )

    error_response = ErrorResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message="Data validation failed",
        error_code="PYDANTIC_VALIDATION_ERROR",
        details={"validation_errors": errors},
        request_id=request_id,
    )

    logger.warning(
        "pydantic_validation_error",
        request_id=request_id,
        errors=errors,
        url=str(request.url),
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.to_dict(),
    )


async def sqlalchemy_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """
    Handle SQLAlchemy database errors.

    Args:
        request: Request that caused the error
        exc: SQLAlchemyError instance

    Returns:
        JSONResponse with error details
    """
    request_id = getattr(request.state, "request_id", None)

    error_response = ErrorResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="Database error occurred",
        error_code="DATABASE_ERROR",
        details={"error_type": type(exc).__name__},
        request_id=request_id,
    )

    logger.error(
        "database_error",
        request_id=request_id,
        error=str(exc),
        error_type=type(exc).__name__,
        url=str(request.url),
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.to_dict(),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle all other exceptions.

    Args:
        request: Request that caused the error
        exc: Exception instance

    Returns:
        JSONResponse with error details
    """
    request_id = getattr(request.state, "request_id", None)

    error_response = ErrorResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="Internal server error",
        error_code="INTERNAL_ERROR",
        details={"error_type": type(exc).__name__},
        request_id=request_id,
    )

    logger.error(
        "internal_error",
        request_id=request_id,
        error=str(exc),
        error_type=type(exc).__name__,
        url=str(request.url),
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.to_dict(),
    )


def register_exception_handlers(app) -> None:
    """
    Register all exception handlers with FastAPI app.

    Args:
        app: FastAPI application instance
    """
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, starlette_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
