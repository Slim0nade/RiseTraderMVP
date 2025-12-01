"""Pydantic models for ML forecasting API requests/responses."""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class InferenceRequest(BaseModel):
    """Request for ML forecast prediction."""
    symbol: str = Field(..., min_length=1, max_length=20)
    timestamp: Optional[datetime] = None
    forecast_horizons: List[str] = Field(..., min_items=1)
    model_type: str = Field("ensemble", pattern="^(lstm|xgboost|ensemble)$")
    include_confidence_intervals: bool = True


class ForecastResponse(BaseModel):
    """Individual forecast response."""
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
    """Request to start model training."""
    run_name: str
    symbol: str
    model_type: str = Field(..., pattern="^(lstm|xgboost)$")
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


class TrainingRunStatusResponse(BaseModel):
    """Detailed training run status response."""
    training_run_id: int
    run_name: str
    symbol: str
    model_type: str
    status: str
    model_version: Optional[str]
    mlflow_run_id: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]

    # MLflow metadata (if available)
    hyperparameters: Optional[dict] = None
    metrics: Optional[dict] = None
    current_stage: Optional[str] = None
    artifact_uri: Optional[str] = None

    # Error information
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class ModelMetricsResponse(BaseModel):
    """Model performance metrics response."""
    id: int
    symbol: str
    model_version: str
    forecast_horizon: str
    mae: float
    mse: float
    rmse: float
    mape: float
    directional_accuracy: Optional[float]
    sample_count: int
    calculated_at: datetime

    class Config:
        from_attributes = True


class AccuracyComparisonResponse(BaseModel):
    """Compare accuracy across models/horizons."""
    comparison_type: str  # 'models' or 'horizons'
    items: List[dict]  # List of metric comparisons
    best_performer: dict  # Best performing model/horizon
    worst_performer: dict  # Worst performing model/horizon
