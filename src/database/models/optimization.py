"""
SQLAlchemy models for async optimization engine.

This module defines database entities for:
- OptimizationRun: Persistent record of optimization runs with results
- PriceAlert: Configured price levels to monitor for open positions
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.sql import func

from src.database.models.base import Base


class OptimizationStatus(str, PyEnum):
    """Status of an optimization run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AlertType(str, PyEnum):
    """Type of price alert."""
    LIQUIDITY_SWEEP = "liquidity_sweep"
    BREAKEVEN = "breakeven"
    KEY_LEVEL = "key_level"
    CUSTOM = "custom"


class AlertDirection(str, PyEnum):
    """Direction for price alert trigger."""
    ABOVE = "above"
    BELOW = "below"


class OptimizationRun(Base):
    """
    Persistent record of optimization runs with results.

    Stores the full optimization history including parameter grid,
    results, and best performing parameters for later analysis.

    Attributes:
        id: Unique identifier (UUID)
        job_id: Redis job ID for correlation (unique, indexed)
        strategy: Strategy name being optimized (e.g., "crude_oil_v3")
        symbol: Trading symbol (e.g., "CrudeOIL")
        timeframe: Candle timeframe (e.g., "H1")
        start_date: Optimization period start (UTC)
        end_date: Optimization period end (UTC)
        param_grid: Full parameter grid tested (JSONB)
        results: Complete results with all tested combinations (JSONB)
        status: Current status (pending/running/completed/failed/cancelled)
        total_combinations: Total parameter combinations to test
        combinations_tested: Progress counter
        best_params: Best performing parameters (JSONB)
        best_metric_value: Best metric value achieved
        optimization_target: Target metric for optimization
        initial_capital: Starting capital for backtest runs
        created_at: Creation timestamp
        started_at: Execution start time
        completed_at: Execution end time
        error_message: Error details if failed
    """
    __tablename__ = "optimization_runs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id = Column(String(36), nullable=False, unique=True, index=True)
    strategy = Column(String(100), nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)

    # Flexible JSONB storage for parameters and results
    param_grid = Column(JSONB, nullable=False)
    results = Column(JSONB, nullable=True)  # Populated on completion

    # Status and progress tracking
    status = Column(String(20), nullable=False, default="pending", index=True)
    total_combinations = Column(Integer, nullable=False)
    combinations_tested = Column(Integer, nullable=False, default=0)

    # Best result tracking
    best_params = Column(JSONB, nullable=True)
    best_metric_value = Column(Numeric(10, 4), nullable=True)
    optimization_target = Column(String(50), nullable=False, default="sharpe_ratio")

    # Configuration
    initial_capital = Column(Numeric(18, 2), nullable=False, default=Decimal("10000.0"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Error handling
    error_message = Column(Text, nullable=True)

    # Indexes for common queries
    __table_args__ = (
        Index('idx_optimization_runs_strategy_symbol', 'strategy', 'symbol'),
        Index('idx_optimization_runs_created_at', 'created_at', postgresql_using='btree'),
    )

    def __repr__(self) -> str:
        return f"<OptimizationRun(id={self.id}, job_id='{self.job_id}', status={self.status})>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "job_id": self.job_id,
            "strategy": self.strategy,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "param_grid": self.param_grid,
            "status": self.status,
            "total_combinations": self.total_combinations,
            "combinations_tested": self.combinations_tested,
            "best_params": self.best_params,
            "best_metric_value": float(self.best_metric_value) if self.best_metric_value else None,
            "optimization_target": self.optimization_target,
            "initial_capital": float(self.initial_capital) if self.initial_capital else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
        }


class PriceAlert(Base):
    """
    Configured price levels to monitor for open positions.

    Supports various alert types including liquidity sweeps,
    breakeven levels, key support/resistance, and custom levels.

    Attributes:
        id: Unique identifier (UUID)
        ticket: MT4 position ticket number
        alert_type: Type of alert (liquidity_sweep, breakeven, key_level, custom)
        price_level: Price to monitor
        direction: Trigger when price goes above/below the level
        triggered: Whether the alert has fired
        triggered_at: When the alert was triggered
        created_at: Creation timestamp
        alert_data: Additional alert data (JSONB)
    """
    __tablename__ = "price_alerts"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    ticket = Column(Integer, nullable=False, index=True)
    alert_type = Column(String(50), nullable=False)
    price_level = Column(Numeric(18, 6), nullable=False)
    direction = Column(String(10), nullable=False)
    triggered = Column(Boolean, nullable=False, default=False)
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    alert_data = Column(JSONB, nullable=True)  # Named alert_data to avoid SQLAlchemy reserved 'metadata'

    # Indexes and constraints
    __table_args__ = (
        Index('idx_price_alerts_ticket', 'ticket'),
        Index('idx_price_alerts_active', 'ticket', 'triggered', postgresql_where=(triggered == False)),
        UniqueConstraint('ticket', 'alert_type', 'price_level', name='uq_price_alert_ticket_type_level'),
    )

    def __repr__(self) -> str:
        return f"<PriceAlert(id={self.id}, ticket={self.ticket}, type={self.alert_type}, level={self.price_level})>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "ticket": self.ticket,
            "alert_type": self.alert_type,
            "price_level": float(self.price_level),
            "direction": self.direction,
            "triggered": self.triggered,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.alert_data,  # Keep API field as 'metadata' for backward compatibility
        }
