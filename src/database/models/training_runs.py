"""
TrainingRun model - Tracks all model training executions
Based on spec: 003-ml-forecasting-pipeline/data-model.md
"""
from datetime import datetime
import enum

from sqlalchemy import Column, Integer, String, DateTime, Text, Enum, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class TrainingStatus(str, enum.Enum):
    """Training run status enum"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrainingRun(Base):
    """
    Model training run record

    Tracks all training executions for audit, debugging, and comparison.
    Stores configuration, status, and results for each training run.
    """

    __tablename__ = "training_runs"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identification
    run_name = Column(String(100), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    model_type = Column(String(20), nullable=False)
    mlflow_run_id = Column(String(100), unique=True)  # MLflow experiment run ID

    # Configuration (stored as JSON)
    hyperparameters = Column(JSONB, nullable=False)
    feature_config = Column(JSONB, nullable=False)
    training_config = Column(JSONB, nullable=False)

    # Execution status
    status = Column(Enum(TrainingStatus), default=TrainingStatus.PENDING, nullable=False)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_seconds = Column(Integer)

    # Results
    final_metrics = Column(JSONB)  # {"mpe": -0.5, "rmse": 0.42, ...}
    model_version = Column(String(50))  # Resulting model version if successful
    error_message = Column(Text)  # Error details if failed

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String(100))  # User or system that triggered training

    __table_args__ = (
        Index('idx_training_status', 'status', 'created_at'),
        Index('idx_training_symbol', 'symbol', 'model_type'),
    )

    def __repr__(self) -> str:
        return (
            f"<TrainingRun(id={self.id}, name='{self.run_name}', "
            f"status='{self.status.value}', model='{self.model_type}')>"
        )
