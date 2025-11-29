"""
Pydantic models for forecast API responses.

These models define the structure and validation for forecast-related API responses
including latest forecasts and symbol-specific forecast lists.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class ForecastResponse(BaseModel):
    """
    Response model for a single forecast.

    Contains ML model prediction including predicted price, confidence level,
    model information, and forecast horizon.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Forecast unique identifier")
    symbol: str = Field(..., description="Trading symbol", max_length=50)
    timeframe: str = Field(..., description="Timeframe (M1, M5, H1, H4, D1, etc.)")
    horizon: str = Field(..., description="Forecast horizon (1h, 4h, 24h, etc.)")
    predicted_price: Decimal = Field(
        ...,
        description="Predicted price",
        gt=0,
        decimal_places=8
    )
    confidence: Decimal = Field(
        ...,
        description="Model confidence level (0-1)",
        ge=0,
        le=1,
        decimal_places=4
    )
    model_name: str = Field(..., description="Model name (e.g., XGBoost_v1, LSTM_v1)")
    created_at: datetime = Field(..., description="Forecast creation timestamp")
    forecast_time: datetime = Field(..., description="Target timestamp for forecast")


class ForecastListResponse(BaseModel):
    """
    Response model for list of forecasts with pagination.

    Contains array of forecasts, total count, and pagination metadata.
    """
    model_config = ConfigDict(from_attributes=True)

    data: List[ForecastResponse] = Field(
        default_factory=list,
        description="List of forecasts"
    )
    total: int = Field(..., description="Total number of forecasts", ge=0)
    page: int = Field(default=1, description="Current page number", ge=1)
    page_size: int = Field(default=50, description="Items per page", ge=1, le=1000)
    next_cursor: Optional[str] = Field(
        None,
        description="Cursor for next page (keyset pagination)"
    )
