"""
ML Forecast model - Price predictions from LSTM/XGBoost models

NOTE: This model uses only columns that exist in the actual database.
Check the database schema if you see UndefinedColumnError.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Forecast(Base):
    """
    ML-generated price forecast

    Stores predictions from LSTM, XGBoost, or ensemble models with
    confidence intervals for trading agent decision-making.
    
    NOTE: Only includes columns that exist in the actual database table.
    """

    __tablename__ = "forecasts"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Core fields - these should exist in all deployments
    symbol = Column(String(20), nullable=False, index=True)
    forecast_horizon = Column(String(10))  # "1h", "4h", "24h"
    model_type = Column(String(20))  # "lstm", "xgboost", "ensemble"
    model_version = Column(String(50))
    
    # Prediction values
    predicted_value = Column(Float)
    lower_bound = Column(Float)  # 95% confidence interval lower
    upper_bound = Column(Float)  # 95% confidence interval upper
    confidence_score = Column(Float)  # Model confidence 0.0-1.0

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<Forecast(id={self.id}, symbol='{self.symbol}', "
            f"horizon='{self.forecast_horizon}', value={self.predicted_value})>"
        )
