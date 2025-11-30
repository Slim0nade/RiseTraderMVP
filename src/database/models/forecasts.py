"""
ML Forecast model - Price predictions from LSTM/XGBoost models
Based on spec: 003-ml-forecasting-pipeline/data-model.md
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Forecast(Base):
    """
    ML-generated price forecast

    Stores predictions from LSTM, XGBoost, or ensemble models with
    confidence intervals for trading agent decision-making.
    """

    __tablename__ = "forecasts"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identification
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    forecast_horizon = Column(String(10), nullable=False)  # "1h", "4h", "24h"

    # Model information
    model_type = Column(String(20), nullable=False)  # "lstm", "xgboost", "ensemble"
    model_version = Column(String(50), nullable=False)
    mlflow_run_id = Column(String(100))  # Reference to MLflow run

    # Prediction values
    predicted_value = Column(Float, nullable=False)
    lower_bound = Column(Float)  # 95% confidence interval lower
    upper_bound = Column(Float)  # 95% confidence interval upper
    confidence_score = Column(Float)  # Model confidence 0.0-1.0

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    inference_time_ms = Column(Float)  # Latency tracking

    # Composite indexes for fast lookups
    __table_args__ = (
        Index('idx_forecast_lookup', 'symbol', 'timestamp', 'forecast_horizon', 'model_version'),
        Index('idx_forecast_latest', 'symbol', 'forecast_horizon', 'created_at'),
    )

    def __repr__(self) -> str:
        return (
            f"<Forecast(id={self.id}, symbol='{self.symbol}', "
            f"horizon='{self.forecast_horizon}', value={self.predicted_value})>"
        )
