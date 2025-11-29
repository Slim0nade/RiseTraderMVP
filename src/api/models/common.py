"""
Common Pydantic models used across API endpoints.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response model for API errors."""

    error: str = Field(..., description="Error type or category")
    detail: str = Field(..., description="Human-readable error message")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Error occurrence timestamp"
    )
    request_id: Optional[str] = Field(
        None, description="Request ID for tracking/debugging"
    )
    path: Optional[str] = Field(None, description="API path where error occurred")
    status_code: Optional[int] = Field(None, description="HTTP status code")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "ValidationError",
                "detail": "Invalid timeframe provided. Must be one of: M1, M5, M15, M30, H1, H4, D1, W1, MN1",
                "timestamp": "2024-11-26T10:30:00Z",
                "request_id": "req_abc123xyz",
                "path": "/api/market-data/CrudeOIL",
                "status_code": 400,
            }
        }


class SuccessResponse(BaseModel):
    """Standard success response for operations without specific return data."""

    success: bool = True
    message: str = Field(..., description="Success message")
    data: Optional[Dict[str, Any]] = Field(None, description="Optional response data")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "data": {"items_affected": 1},
            }
        }
