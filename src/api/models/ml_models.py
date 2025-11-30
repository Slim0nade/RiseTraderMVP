"""Pydantic models for ML forecasting API requests/responses."""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class InferenceRequest(BaseModel):
    """Request for ML forecast prediction."""
    symbol: str = Field(..., min_length=1, max_length=20)
    timestamp: Optional[datetime] = None
    forecast_horizons: List[str] = Field(..., min_items=1)
    model_type: str = Field(
        "ensemble",
        pattern="^(lstm|xgboost|ensemble|tcn|bigru|fedformer|tft|moe|ppo)$"
    )
    include_confidence_intervals: bool = True
    include_feature_importance: bool = False  # NEW: For SOTA models with interpretability


class ForecastResponse(BaseModel):
    """Individual forecast response (enhanced for SOTA models)."""
    id: int
    symbol: str
    timestamp: datetime
    forecast_horizon: str
    model_type: str
    model_version: str
    predicted_value: float
    lower_bound: Optional[float]
    upper_bound: Optional[float]
    confidence_score: Optional[float]
    created_at: datetime
    inference_time_ms: Optional[float]

    # Enhanced fields for SOTA models
    direction_prob: Optional[float] = None  # Probability of price moving up (0-1)
    feature_importance: Optional[dict] = None  # Feature importance scores from interpretable models

    class Config:
        from_attributes = True


class InferenceResponse(BaseModel):
    """Response containing ML forecasts."""
    symbol: str
    timestamp: datetime
    forecasts: List[ForecastResponse]
    inference_time_ms: float
    cache_hit: bool


class TrainingRequest(BaseModel):
    """Request to start model training (supports both MVP and SOTA models)."""
    run_name: str
    symbol: str
    model_type: str = Field(
        ...,
        pattern="^(lstm|xgboost|tcn|bigru|fedformer|tft|moe|ppo)$"
    )
    config_override: Optional[dict] = None
    async_training: bool = True


class TrainingResponse(BaseModel):
    """Response after starting training."""
    training_run_id: int
    run_name: str
    status: str
    mlflow_run_id: Optional[str]
    estimated_duration_minutes: Optional[int]
    message: str
