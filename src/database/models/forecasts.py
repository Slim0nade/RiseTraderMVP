"""
ML forecasts model.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Forecast(Base, TimestampMixin):
    """
    ML forecasts table storing model predictions.

    Contains predictions from various ML models with confidence intervals.
    """

    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Model information
    model_type: Mapped[str] = mapped_column(String, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    model_config_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Forecast target
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    forecast_horizon: Mapped[str] = mapped_column(String, nullable=False)  # e.g., '1h', '4h', '1d'

    # Timestamps
    prediction_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    target_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Prediction values
    predicted_price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    confidence_lower: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    confidence_upper: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    confidence_level: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)  # e.g., 0.95
    model_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Validation (once actual price is known)
    actual_price: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    prediction_error: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    absolute_error: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    percentage_error: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    is_validated: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Model metadata (JSON stored as text)
    feature_importance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_features: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_forecasts_model_type", "model_type"),
        Index("ix_forecasts_model_version", "model_version"),
        Index("ix_forecasts_symbol", "symbol"),
        Index("ix_forecasts_forecast_horizon", "forecast_horizon"),
        Index("ix_forecasts_prediction_timestamp", "prediction_timestamp"),
        Index("ix_forecasts_target_timestamp", "target_timestamp"),
        Index("ix_forecasts_is_validated", "is_validated"),
        Index(
            "ix_forecasts_symbol_target",
            "symbol",
            "target_timestamp",
            "model_type"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Forecast(id={self.id}, model='{self.model_type}', "
            f"symbol='{self.symbol}', horizon='{self.forecast_horizon}', "
            f"predicted={self.predicted_price})>"
        )

    @property
    def is_within_confidence(self) -> Optional[bool]:
        """Check if actual price falls within confidence interval."""
        if not self.is_validated or self.actual_price is None:
            return None
        if self.confidence_lower is None or self.confidence_upper is None:
            return None
        return self.confidence_lower <= self.actual_price <= self.confidence_upper

    @property
    def directional_accuracy(self) -> Optional[bool]:
        """Check if prediction correctly predicted price direction."""
        if not self.is_validated or self.actual_price is None:
            return None
        # Would need previous price to calculate this properly
        # This is a placeholder
        return None

    def validate_prediction(self, actual_price: Decimal) -> None:
        """
        Validate the prediction against actual price.

        Args:
            actual_price: The actual observed price
        """
        self.actual_price = actual_price
        self.prediction_error = actual_price - self.predicted_price
        self.absolute_error = abs(self.prediction_error)
        if actual_price != 0:
            self.percentage_error = (self.prediction_error / actual_price) * 100
        self.is_validated = True

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "model_type": self.model_type,
            "model_version": self.model_version,
            "model_config_hash": self.model_config_hash,
            "symbol": self.symbol,
            "forecast_horizon": self.forecast_horizon,
            "prediction_timestamp": (
                self.prediction_timestamp.isoformat()
                if self.prediction_timestamp
                else None
            ),
            "target_timestamp": (
                self.target_timestamp.isoformat() if self.target_timestamp else None
            ),
            "predicted_price": float(self.predicted_price),
            "confidence_lower": (
                float(self.confidence_lower) if self.confidence_lower else None
            ),
            "confidence_upper": (
                float(self.confidence_upper) if self.confidence_upper else None
            ),
            "confidence_level": (
                float(self.confidence_level) if self.confidence_level else None
            ),
            "model_confidence": (
                float(self.model_confidence) if self.model_confidence else None
            ),
            "actual_price": float(self.actual_price) if self.actual_price else None,
            "prediction_error": (
                float(self.prediction_error) if self.prediction_error else None
            ),
            "absolute_error": (
                float(self.absolute_error) if self.absolute_error else None
            ),
            "percentage_error": (
                float(self.percentage_error) if self.percentage_error else None
            ),
            "is_validated": self.is_validated,
            "feature_importance": self.feature_importance,
            "input_features": self.input_features,
            "model_metadata": self.model_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
