"""
ML model performance tracking.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ModelPerformance(Base, TimestampMixin):
    """
    Model performance table storing ML model metrics.

    Tracks performance of forecasting models over time.
    """

    __tablename__ = "model_performance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Model identification
    model_type: Mapped[str] = mapped_column(String, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    forecast_horizon: Mapped[str] = mapped_column(String, nullable=False)

    # Prediction counts
    total_predictions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    validated_predictions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Error metrics
    mean_absolute_error: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    root_mean_squared_error: Mapped[Optional[Decimal]] = mapped_column(
        Numeric, nullable=True
    )
    mean_percentage_error: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Directional accuracy
    directional_accuracy: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Calculation period
    calculation_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    calculation_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<ModelPerformance(id={self.id}, model='{self.model_type}', "
            f"version='{self.model_version}', symbol='{self.symbol}', "
            f"mae={self.mean_absolute_error})>"
        )

    @property
    def validation_rate(self) -> Optional[Decimal]:
        """Calculate percentage of predictions that were validated."""
        if self.total_predictions is None or self.total_predictions == 0:
            return None
        if self.validated_predictions is None:
            return Decimal(0)
        return (Decimal(self.validated_predictions) / Decimal(self.total_predictions)) * 100

    @property
    def accuracy_score(self) -> Optional[Decimal]:
        """
        Calculate overall accuracy score (0-100).

        Uses directional accuracy as primary metric.
        """
        if self.directional_accuracy is None:
            return None
        return self.directional_accuracy * 100

    @property
    def is_performing_well(self) -> bool:
        """Check if model is performing above 50% directional accuracy."""
        if self.directional_accuracy is None:
            return False
        return self.directional_accuracy > Decimal(0.5)

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "model_type": self.model_type,
            "model_version": self.model_version,
            "symbol": self.symbol,
            "forecast_horizon": self.forecast_horizon,
            "total_predictions": self.total_predictions,
            "validated_predictions": self.validated_predictions,
            "mean_absolute_error": (
                float(self.mean_absolute_error) if self.mean_absolute_error else None
            ),
            "root_mean_squared_error": (
                float(self.root_mean_squared_error)
                if self.root_mean_squared_error
                else None
            ),
            "mean_percentage_error": (
                float(self.mean_percentage_error)
                if self.mean_percentage_error
                else None
            ),
            "directional_accuracy": (
                float(self.directional_accuracy) if self.directional_accuracy else None
            ),
            "calculation_start": (
                self.calculation_start.isoformat() if self.calculation_start else None
            ),
            "calculation_end": (
                self.calculation_end.isoformat() if self.calculation_end else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
