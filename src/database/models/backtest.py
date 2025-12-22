"""
SQLAlchemy models for backtesting engine.

This module defines the core database entities for the backtesting system:
- BacktestConfiguration: Reusable backtest parameter definitions
- BacktestRun: Individual backtest execution results
- ParameterGrid: Parameter combinations for batch optimization
- GridSearchResult: Links parameter grids to backtest results
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
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.database.models.base import Base


class ExecutionMode(str, PyEnum):
    """Backtest execution mode."""
    FULL_PIPELINE = "full_pipeline"
    SYNTHETIC_FAST = "synthetic_fast"


class RunStatus(str, PyEnum):
    """Backtest run status."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class BacktestConfiguration(Base):
    """
    Backtest configuration defining all parameters for a backtest run.

    Attributes:
        id: Unique identifier
        name: Human-readable name (e.g., "Q1 2023 Conservative")
        symbol: Trading symbol (e.g., "EURUSD", "BTC-USD")
        start_date: Backtest start date (UTC, inclusive)
        end_date: Backtest end date (UTC, inclusive)
        initial_capital: Starting account balance
        execution_mode: 'full_pipeline' or 'synthetic_fast'
        agent_config_ref: Reference to agent configuration (for full mode)
        slippage_pct: Slippage percentage (default 0.1%)
        commission_pct: Commission percentage (default 0.05%)
        commission_fixed: Fixed commission per trade
        max_leverage: Maximum leverage allowed (default 1.0 = no leverage)
        allow_short_selling: Whether short positions are allowed
        config_params: Mode-specific configuration (JSON)
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "backtest_configurations"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    initial_capital = Column(Numeric(18, 2), nullable=False)
    execution_mode = Column(
        SQLEnum(ExecutionMode, name="execution_mode", create_type=False),
        nullable=False
    )
    agent_config_ref = Column(String(255), nullable=True)
    slippage_pct = Column(Numeric(8, 6), nullable=False, default=Decimal("0.001"))
    commission_pct = Column(Numeric(8, 6), nullable=False, default=Decimal("0.0005"))
    commission_fixed = Column(Numeric(10, 2), nullable=False, default=Decimal("0.0"))
    max_leverage = Column(Numeric(5, 2), nullable=False, default=Decimal("1.0"))
    allow_short_selling = Column(Boolean, nullable=False, default=False)
    config_params = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    runs = relationship("BacktestRun", back_populates="configuration", cascade="all, delete-orphan")
    parameter_grids = relationship("ParameterGrid", back_populates="base_configuration")

    def __repr__(self) -> str:
        return f"<BacktestConfiguration(id={self.id}, name='{self.name}', mode={self.execution_mode})>"


class BacktestRun(Base):
    """
    Individual backtest execution with results and performance metrics.

    Attributes:
        id: Unique identifier
        config_id: Foreign key to BacktestConfiguration
        status: 'running', 'completed', 'failed', or 'timeout'
        start_time: Execution start time
        end_time: Execution end time (NULL if still running)
        random_seed: Random seed for deterministic replay
        total_return_pct: Total return percentage
        sharpe_ratio: Annualized Sharpe ratio
        max_drawdown_pct: Maximum drawdown percentage
        max_drawdown_duration_days: Drawdown duration in days
        win_rate: Percentage of winning trades (0-1)
        total_trades: Total number of trades executed
        avg_trade_duration_hours: Average holding period
        profit_factor: Gross profit / gross loss
        final_capital: Ending account balance
        metrics: Full metrics dictionary (JSON)
        error_message: Error details if status='failed'
        candles_processed: Number of candles replayed
        agent_decisions_count: Number of agent decisions logged
    """
    __tablename__ = "backtest_runs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    config_id = Column(PGUUID(as_uuid=True), ForeignKey("backtest_configurations.id"), nullable=False, index=True)
    status = Column(
        SQLEnum(RunStatus, name="run_status", create_type=False),
        nullable=False,
        index=True
    )
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    random_seed = Column(Integer, nullable=True)

    # Performance metrics
    total_return_pct = Column(Numeric(10, 4), nullable=True)
    sharpe_ratio = Column(Numeric(10, 4), nullable=True)
    max_drawdown_pct = Column(Numeric(10, 4), nullable=True)
    max_drawdown_duration_days = Column(Integer, nullable=True)
    win_rate = Column(Numeric(5, 4), nullable=True)
    total_trades = Column(Integer, nullable=False, default=0)
    avg_trade_duration_hours = Column(Numeric(10, 2), nullable=True)
    profit_factor = Column(Numeric(10, 4), nullable=True)
    final_capital = Column(Numeric(18, 2), nullable=True)

    # Extended data
    metrics = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    candles_processed = Column(Integer, nullable=False, default=0)
    agent_decisions_count = Column(Integer, nullable=False, default=0)

    # Relationships
    configuration = relationship("BacktestConfiguration", back_populates="runs")
    trades = relationship("SimulatedTrade", back_populates="backtest_run", cascade="all, delete-orphan")
    snapshots = relationship("PortfolioSnapshot", back_populates="backtest_run", cascade="all, delete-orphan")
    agent_decisions = relationship("AgentDecisionLog", back_populates="backtest_run", cascade="all, delete-orphan")
    grid_results = relationship("GridSearchResult", back_populates="backtest_run")

    def __repr__(self) -> str:
        return f"<BacktestRun(id={self.id}, status={self.status}, return={self.total_return_pct}%)>"


class ParameterGrid(Base):
    """
    Parameter grid for batch optimization and hyperparameter search.

    Attributes:
        id: Unique identifier
        name: Grid name (e.g., "RSI Threshold Sweep")
        base_config_id: Base configuration to vary
        parameters: Parameter definitions (JSON dict: {param: [values]})
        total_combinations: Total number of configurations to test
        created_at: Creation timestamp
    """
    __tablename__ = "parameter_grids"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False, index=True)
    base_config_id = Column(PGUUID(as_uuid=True), ForeignKey("backtest_configurations.id"), nullable=False)
    parameters = Column(JSONB, nullable=False)
    total_combinations = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    base_configuration = relationship("BacktestConfiguration", back_populates="parameter_grids")
    results = relationship("GridSearchResult", back_populates="grid", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ParameterGrid(id={self.id}, name='{self.name}', combinations={self.total_combinations})>"


class GridSearchResult(Base):
    """
    Links parameter grid combinations to their backtest results with rankings.

    Attributes:
        id: Unique identifier
        grid_id: Foreign key to ParameterGrid
        backtest_run_id: Foreign key to BacktestRun
        parameter_values: Specific parameter values for this run (JSON)
        rank_by_sharpe: Rank by Sharpe ratio (1 = best)
        rank_by_return: Rank by total return (1 = best)
        rank_by_drawdown: Rank by max drawdown (1 = lowest)
        is_statistically_significant: Whether results differ significantly from baseline
    """
    __tablename__ = "grid_search_results"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    grid_id = Column(PGUUID(as_uuid=True), ForeignKey("parameter_grids.id"), nullable=False, index=True)
    backtest_run_id = Column(PGUUID(as_uuid=True), ForeignKey("backtest_runs.id"), nullable=False, index=True)
    parameter_values = Column(JSONB, nullable=False)
    rank_by_sharpe = Column(Integer, nullable=True)
    rank_by_return = Column(Integer, nullable=True)
    rank_by_drawdown = Column(Integer, nullable=True)
    is_statistically_significant = Column(Boolean, nullable=False, default=False)

    # Relationships
    grid = relationship("ParameterGrid", back_populates="results")
    backtest_run = relationship("BacktestRun", back_populates="grid_results")

    def __repr__(self) -> str:
        return f"<GridSearchResult(id={self.id}, sharpe_rank={self.rank_by_sharpe})>"
