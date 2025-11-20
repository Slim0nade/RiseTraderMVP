"""
Pydantic models for Forecast API endpoints.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# Response Models
class ForecastResponse(BaseModel):
    """Response model for ML forecast."""

    id: int
    model_type: str
    model_version: str
    model_config_hash: Optional[str] = None
    symbol: str
    forecast_horizon: str
    prediction_timestamp: datetime
    target_timestamp: datetime
    predicted_price: Decimal
    confidence_lower: Optional[Decimal] = None
    confidence_upper: Optional[Decimal] = None
    confidence_level: Optional[Decimal] = None
    model_confidence: Optional[Decimal] = None
    actual_price: Optional[Decimal] = None
    prediction_error: Optional[Decimal] = None
    absolute_error: Optional[Decimal] = None
    percentage_error: Optional[Decimal] = None
    is_validated: Optional[bool] = None
    feature_importance: Optional[str] = None
    input_features: Optional[str] = None
    model_metadata: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "model_type": "XGBoost",
                "model_version": "1.0.0",
                "symbol": "CrudeOIL",
                "forecast_horizon": "1h",
                "prediction_timestamp": "2024-01-15T10:30:00Z",
                "target_timestamp": "2024-01-15T11:30:00Z",
                "predicted_price": 73.25,
                "confidence_lower": 72.80,
                "confidence_upper": 73.70,
                "confidence_level": 0.95,
                "model_confidence": 0.87,
                "is_validated": False,
            }
        }


class ForecastListResponse(BaseModel):
    """Response for listing forecasts."""

    forecasts: List[ForecastResponse]
    total: int
    page: int
    page_size: int
    symbol: Optional[str] = None
    model_type: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "forecasts": [],
                "total": 100,
                "page": 1,
                "page_size": 50,
                "symbol": "CrudeOIL",
                "model_type": "XGBoost",
            }
        }


class LatestForecastsResponse(BaseModel):
    """Response for latest forecasts by model."""

    symbol: str
    timestamp: datetime
    forecasts: List[ForecastResponse]

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "CrudeOIL",
                "timestamp": "2024-01-15T10:30:00Z",
                "forecasts": [],
            }
        }


class GenerateForecastRequest(BaseModel):
    """Request to generate new forecasts."""

    symbol: str = Field(..., description="Trading symbol")
    model_types: Optional[List[str]] = Field(
        None, description="Specific models to use (None = all models)"
    )
    horizons: Optional[List[str]] = Field(
        None, description="Forecast horizons (e.g., ['1h', '4h', '1d'])"
    )
    force: bool = Field(
        False, description="Force regeneration even if recent forecast exists"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "CrudeOIL",
                "model_types": ["XGBoost", "LSTM"],
                "horizons": ["1h", "4h"],
                "force": False,
            }
        }


class GenerateForecastResponse(BaseModel):
    """Response for forecast generation."""

    success: bool
    message: str
    symbol: str
    forecasts_generated: int
    generation_time_seconds: Optional[float] = None
    forecasts: Optional[List[ForecastResponse]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Forecasts generated successfully",
                "symbol": "CrudeOIL",
                "forecasts_generated": 6,
                "generation_time_seconds": 2.45,
            }
        }


class ForecastAccuracyMetrics(BaseModel):
    """Forecast accuracy metrics."""

    model_type: str
    symbol: str
    total_predictions: int
    validated_predictions: int
    mean_absolute_error: Optional[Decimal] = None
    mean_percentage_error: Optional[Decimal] = None
    directional_accuracy: Optional[float] = None  # Percentage
    confidence_coverage: Optional[float] = None  # Percentage within confidence bounds
    rmse: Optional[Decimal] = None

    class Config:
        json_schema_extra = {
            "example": {
                "model_type": "XGBoost",
                "symbol": "CrudeOIL",
                "total_predictions": 1000,
                "validated_predictions": 950,
                "mean_absolute_error": 0.25,
                "mean_percentage_error": 0.35,
                "directional_accuracy": 67.5,
                "confidence_coverage": 94.2,
                "rmse": 0.32,
            }
        }


class ForecastAccuracyResponse(BaseModel):
    """Response for forecast accuracy metrics."""

    metrics: List[ForecastAccuracyMetrics]
    period_start: datetime
    period_end: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "metrics": [],
                "period_start": "2024-01-01T00:00:00Z",
                "period_end": "2024-01-15T23:59:59Z",
            }
        }
