"""
Pydantic models for Market Data API endpoints.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


# Response Models
class MarketDataResponse(BaseModel):
    """Response model for market data tick."""

    id: int
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Optional[int] = None
    tick_volume: Optional[int] = None
    spread: Optional[int] = None
    real_volume: Optional[int] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "symbol": "CrudeOIL",
                "timestamp": "2024-01-15T10:30:00Z",
                "open": 72.45,
                "high": 72.65,
                "low": 72.40,
                "close": 72.55,
                "volume": 1500,
                "tick_volume": 150,
                "spread": 2,
                "real_volume": 1500,
            }
        }


class MarketDataListResponse(BaseModel):
    """Response for listing market data."""

    data: List[MarketDataResponse]
    total: int
    page: int
    page_size: int
    symbol: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "data": [],
                "total": 1000,
                "page": 1,
                "page_size": 50,
                "symbol": "CrudeOIL",
                "start_time": "2024-01-15T00:00:00Z",
                "end_time": "2024-01-15T23:59:59Z",
            }
        }


class SymbolInfoResponse(BaseModel):
    """Response model for symbol information."""

    symbol: str
    description: Optional[str] = None
    latest_price: Optional[Decimal] = None
    latest_timestamp: Optional[datetime] = None
    data_points_count: int
    first_timestamp: Optional[datetime] = None
    last_timestamp: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "CrudeOIL",
                "description": "Crude Oil Futures",
                "latest_price": 72.55,
                "latest_timestamp": "2024-01-15T10:30:00Z",
                "data_points_count": 50000,
                "first_timestamp": "2024-01-01T00:00:00Z",
                "last_timestamp": "2024-01-15T10:30:00Z",
            }
        }


class SymbolListResponse(BaseModel):
    """Response for listing available symbols."""

    symbols: List[SymbolInfoResponse]
    total: int

    class Config:
        json_schema_extra = {
            "example": {
                "symbols": [
                    {
                        "symbol": "CrudeOIL",
                        "description": "Crude Oil Futures",
                        "latest_price": 72.55,
                        "data_points_count": 50000,
                    }
                ],
                "total": 1,
            }
        }


class StreamControlResponse(BaseModel):
    """Response for stream control operations."""

    success: bool
    message: str
    symbol: Optional[str] = None
    status: Optional[str] = None  # RUNNING, STOPPED

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Data streaming started",
                "symbol": "CrudeOIL",
                "status": "RUNNING",
            }
        }


# Request Models
class StreamControlRequest(BaseModel):
    """Request to control data streaming."""

    symbol: str = Field(..., description="Symbol to stream")
    interval: Optional[str] = Field(
        "1m", description="Data interval (1m, 5m, 15m, 1h, etc.)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "CrudeOIL",
                "interval": "1m",
            }
        }
