"""
ModelMetrics model - Model performance evaluation metrics
Based on spec: 003-ml-forecasting-pipeline/data-model.md
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class ModelMetrics(Base):
    """
    Model performance metrics

    Stores detailed evaluation metrics (MPE, RMSE, MAE, MAPE, directional accuracy)
    for each model version and forecast horizon.
    """

    __tablename__ = "model_metrics"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identification
    model_type = Column(String(20), nullable=False)
    model_version = Column(String(50), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    forecast_horizon = Column(String(10), nullable=False)

    # Metrics
    mpe = Column(Float, nullable=False)  # Mean Percentage Error
    rmse = Column(Float, nullable=False)  # Root Mean Squared Error
    mae = Column(Float, nullable=False)  # Mean Absolute Error
    mape = Column(Float, nullable=False)  # Mean Absolute Percentage Error
    directional_accuracy = Column(Float)  # % correct direction predictions

    # Metadata
    evaluation_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    sample_size = Column(Integer)  # Number of predictions evaluated
    mlflow_run_id = Column(String(100))

    __table_args__ = (
        Index('idx_metrics_lookup', 'model_version', 'forecast_horizon'),
    )

    def __repr__(self) -> str:
        return (
            f"<ModelMetrics(id={self.id}, version='{self.model_version}', "
            f"horizon='{self.forecast_horizon}', rmse={self.rmse})>"
        )
