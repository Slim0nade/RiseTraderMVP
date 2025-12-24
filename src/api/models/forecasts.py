"""
Pydantic models for forecast API responses.

These models define the structure and validation for forecast-related API responses.
NOTE: Field list matches actual database schema.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class ForecastResponse(BaseModel):
    """Response model for a single forecast."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Forecast unique identifier")
    symbol: str = Field(..., description="Trading symbol")
    forecast_horizon: Optional[str] = Field(None, description="Forecast horizon (1h, 4h, 24h)")
    model_type: Optional[str] = Field(None, description="Model type (lstm, xgboost, ensemble)")
    model_version: Optional[str] = Field(None, description="Model version")
    predicted_value: Optional[float] = Field(None, description="Predicted price value")
    lower_bound: Optional[float] = Field(None, description="95% CI lower bound")
    upper_bound: Optional[float] = Field(None, description="95% CI upper bound")
    confidence_score: Optional[float] = Field(None, description="Model confidence (0-1)")
    created_at: Optional[datetime] = Field(None, description="Forecast creation timestamp")


class ForecastListResponse(BaseModel):
    """Response model for list of forecasts with pagination."""
    model_config = ConfigDict(from_attributes=True)

    data: List[ForecastResponse] = Field(default_factory=list, description="List of forecasts")
    total: int = Field(..., description="Total number of forecasts", ge=0)
    page: int = Field(default=1, description="Current page number", ge=1)
    page_size: int = Field(default=50, description="Items per page", ge=1, le=1000)
    next_cursor: Optional[str] = Field(None, description="Cursor for next page")
