"""
Pydantic models for Backtesting API endpoints.

Request/response models for backtesting configuration, execution,
and results retrieval (Phase 3, T045-T051).
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# Enums (matching database enums)
class ExecutionMode(str, Enum):
    """Backtest execution mode."""

    FULL_PIPELINE = "full_pipeline"
    SYNTHETIC_FAST = "synthetic_fast"


class RunStatus(str, Enum):
    """Backtest run status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TradeAction(str, Enum):
    """Trade action type."""

    BUY = "buy"
    SELL = "sell"
    CLOSE = "close"


# Request Models


class CreateBacktestConfigRequest(BaseModel):
    """Request to create a new backtest configuration."""

    name: str = Field(..., min_length=1, max_length=255, description="Configuration name")
    symbol: str = Field(..., min_length=1, max_length=20, description="Trading symbol")
    start_date: datetime = Field(..., description="Backtest start date")
    end_date: datetime = Field(..., description="Backtest end date")
    initial_capital: Decimal = Field(..., gt=0, description="Initial capital")
    execution_mode: ExecutionMode = Field(..., description="Execution mode")
    agent_config_ref: Optional[str] = Field(
        None, description="Agent configuration reference (for full_pipeline mode)"
    )
    slippage_pct: Decimal = Field(
        default=Decimal("0.001"), ge=0, description="Slippage percentage"
    )
    commission_pct: Decimal = Field(
        default=Decimal("0.0005"), ge=0, description="Commission percentage"
    )
    commission_fixed: Decimal = Field(
        default=Decimal("0.0"), ge=0, description="Fixed commission per trade"
    )
    max_leverage: Decimal = Field(
        default=Decimal("1.0"), gt=0, description="Maximum leverage"
    )
    allow_short_selling: bool = Field(
        default=False, description="Allow short selling"
    )
    config_params: Optional[Dict[str, Any]] = Field(
        None, description="Mode-specific parameters (JSON)"
    )

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: datetime, info) -> datetime:
        """Validate end_date is after start_date."""
        if "start_date" in info.data and v <= info.data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "name": "MA Crossover EURUSD 2024",
                "symbol": "EURUSD",
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-12-31T23:59:59Z",
                "initial_capital": "10000.00",
                "execution_mode": "synthetic_fast",
                "slippage_pct": "0.001",
                "commission_pct": "0.0005",
                "commission_fixed": "0.0",
                "max_leverage": "1.0",
                "allow_short_selling": False,
                "config_params": {
                    "strategy": "ma_crossover",
                    "fast_period": 10,
                    "slow_period": 30,
                },
            }
        }


class RunBacktestRequest(BaseModel):
    """Request to execute a backtest run."""

    config_id: UUID = Field(..., description="Configuration UUID")
    timeframe: str = Field(
        default="M5", description="Market data timeframe (e.g., M5, H1, D1)"
    )
    random_seed: Optional[int] = Field(
        None, description="Random seed for deterministic replay"
    )
    synthetic_strategy: Optional[str] = Field(
        None,
        description="Synthetic strategy name (ma_crossover, rsi, trend_following, mean_reversion)",
    )
    synthetic_params: Optional[Dict[str, Any]] = Field(
        None, description="Strategy-specific parameters"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "config_id": "123e4567-e89b-12d3-a456-426614174000",
                "timeframe": "M5",
                "random_seed": 42,
                "synthetic_strategy": "ma_crossover",
                "synthetic_params": {
                    "fast_period": 10,
                    "slow_period": 30,
                    "quantity": "1.0",
                },
            }
        }


# Response Models


class BacktestConfigResponse(BaseModel):
    """Response model for backtest configuration."""

    id: UUID = Field(..., description="Configuration UUID")
    name: str = Field(..., description="Configuration name")
    symbol: str = Field(..., description="Trading symbol")
    start_date: datetime = Field(..., description="Start date")
    end_date: datetime = Field(..., description="End date")
    initial_capital: Decimal = Field(..., description="Initial capital")
    execution_mode: ExecutionMode = Field(..., description="Execution mode")
    agent_config_ref: Optional[str] = Field(None, description="Agent config reference")
    slippage_pct: Decimal = Field(..., description="Slippage percentage")
    commission_pct: Decimal = Field(..., description="Commission percentage")
    commission_fixed: Decimal = Field(..., description="Fixed commission")
    max_leverage: Decimal = Field(..., description="Maximum leverage")
    allow_short_selling: bool = Field(..., description="Short selling allowed")
    config_params: Optional[Dict[str, Any]] = Field(None, description="Config parameters")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        from_attributes = True


class BacktestConfigListResponse(BaseModel):
    """Response model for list of configurations."""

    total: int = Field(..., description="Total number of configurations")
    items: List[BacktestConfigResponse] = Field(..., description="Configuration items")


class PerformanceMetricsResponse(BaseModel):
    """Response model for backtest performance metrics."""

    total_return_pct: float = Field(..., description="Total return percentage")
    total_return_abs: float = Field(default=0.0, description="Total return (absolute)")
    sharpe_ratio: float = Field(..., description="Sharpe ratio")
    sortino_ratio: float = Field(..., description="Sortino ratio")
    max_drawdown_pct: float = Field(..., description="Maximum drawdown percentage")
    max_drawdown_abs: float = Field(default=0.0, description="Maximum drawdown (absolute)")
    max_drawdown_duration_days: Optional[float] = Field(
        None, description="Max drawdown duration (days)"
    )
    win_rate: float = Field(..., description="Win rate (0.0-1.0)")
    total_trades: int = Field(..., description="Total number of trades")
    winning_trades: int = Field(default=0, description="Winning trades count")
    losing_trades: int = Field(default=0, description="Losing trades count")
    avg_win: Optional[float] = Field(None, description="Average winning trade")
    avg_loss: Optional[float] = Field(None, description="Average losing trade")
    profit_factor: Optional[float] = Field(None, description="Profit factor")
    avg_trade_duration_hours: Optional[float] = Field(
        None, description="Average trade duration (hours)"
    )
    max_consecutive_wins: int = Field(default=0, description="Max consecutive wins")
    max_consecutive_losses: int = Field(default=0, description="Max consecutive losses")
    calmar_ratio: Optional[float] = Field(None, description="Calmar ratio")


class BacktestRunStatusResponse(BaseModel):
    """Response model for backtest run status."""

    run_id: UUID = Field(..., description="Run UUID", alias="id")
    config_id: UUID = Field(..., description="Configuration UUID")
    status: RunStatus = Field(..., description="Run status")
    start_time: datetime = Field(..., description="Start time")
    end_time: Optional[datetime] = Field(None, description="End time")
    candles_processed: int = Field(..., description="Candles processed")
    total_trades: int = Field(..., description="Total trades")
    agent_decisions_count: int = Field(
        default=0, description="Agent decisions logged"
    )
    final_capital: Optional[Decimal] = Field(None, description="Final capital")
    progress_pct: Optional[float] = Field(None, description="Progress percentage")
    error_message: Optional[str] = Field(None, description="Error message (if failed)")

    class Config:
        from_attributes = True
        populate_by_name = True


class BacktestRunResponse(BaseModel):
    """Response model for completed backtest run with metrics."""

    run_id: UUID = Field(..., description="Run UUID", alias="id")
    config_id: UUID = Field(..., description="Configuration UUID")
    status: RunStatus = Field(..., description="Run status")
    start_time: datetime = Field(..., description="Start time")
    end_time: Optional[datetime] = Field(None, description="End time")
    candles_processed: int = Field(..., description="Candles processed")
    final_capital: Optional[Decimal] = Field(None, description="Final capital")
    metrics: Optional[PerformanceMetricsResponse] = Field(
        None, description="Performance metrics"
    )
    error_message: Optional[str] = Field(None, description="Error message (if failed)")

    class Config:
        from_attributes = True
        populate_by_name = True


class SimulatedTradeResponse(BaseModel):
    """Response model for a simulated trade."""

    id: UUID = Field(..., description="Trade UUID")
    backtest_run_id: UUID = Field(..., description="Backtest run UUID")
    symbol: str = Field(..., description="Trading symbol")
    action: TradeAction = Field(..., description="Trade action")
    entry_timestamp: datetime = Field(..., description="Entry timestamp")
    entry_price: Decimal = Field(..., description="Entry price")
    quantity: Decimal = Field(..., description="Position size")
    exit_timestamp: Optional[datetime] = Field(None, description="Exit timestamp")
    exit_price: Optional[Decimal] = Field(None, description="Exit price")
    gross_pnl: Optional[Decimal] = Field(None, description="Gross P&L")
    net_pnl: Optional[Decimal] = Field(None, description="Net P&L (after fees)")
    commission: Decimal = Field(..., alias="fees_paid", description="Commission paid")
    slippage: Decimal = Field(..., alias="slippage_applied", description="Slippage")
    decision_context: Optional[Dict[str, Any]] = Field(
        None, description="Decision context (JSON)"
    )

    class Config:
        from_attributes = True
        populate_by_name = True


class TradeListResponse(BaseModel):
    """Response model for list of trades."""

    total: int = Field(..., description="Total number of trades")
    closed_trades: int = Field(..., description="Number of closed trades")
    open_trades: int = Field(..., description="Number of open trades")
    items: List[SimulatedTradeResponse] = Field(..., description="Trade items")


class ValidationResultResponse(BaseModel):
    """Response model for configuration validation."""

    config_id: UUID = Field(..., description="Configuration UUID")
    config_name: str = Field(..., description="Configuration name")
    can_proceed: bool = Field(..., description="Whether backtest can proceed")
    configuration_valid: bool = Field(..., description="Configuration is valid")
    data_validation: Dict[str, Any] = Field(..., description="Data validation details")


class CancelRunResponse(BaseModel):
    """Response model for run cancellation."""

    success: bool = Field(..., description="Cancellation success")
    run_id: UUID = Field(..., description="Run UUID")
    message: str = Field(..., description="Status message")


# Error Response (shared across all endpoints)


class ErrorDetail(BaseModel):
    """Error detail."""

    field: Optional[str] = Field(None, description="Field name (for validation errors)")
    message: str = Field(..., description="Error message")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")
    errors: Optional[List[ErrorDetail]] = Field(
        None, description="Validation errors (if applicable)"
    )


# Optimization Models (User Story 2)


class CreateParameterGridRequest(BaseModel):
    """Request to create a parameter optimization grid (T070)."""

    name: str = Field(..., min_length=1, max_length=255, description="Grid name")
    description: Optional[str] = Field(None, description="Grid description")
    symbol: str = Field(..., min_length=1, max_length=20, description="Trading symbol")
    start_date: datetime = Field(..., description="Backtest start date")
    end_date: datetime = Field(..., description="Backtest end date")
    timeframe: str = Field(..., description="Timeframe (M5, M15, H1, etc.)")
    initial_capital: Decimal = Field(..., gt=0, description="Initial capital")

    # Parameter grid specification
    parameters: Dict[str, List[Any]] = Field(
        ...,
        description="Parameter grid (e.g., {'ema_fast': [5,8,10], 'ema_slow': [20,25]})",
    )

    # Optimization settings
    max_workers: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Maximum parallel workers",
    )
    synthetic_strategy: str = Field(
        default="ma_crossover",
        description="Synthetic strategy to use",
    )

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: datetime, info) -> datetime:
        """Validate end_date is after start_date."""
        if "start_date" in info.data and v <= info.data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v


class ExecuteParameterGridRequest(BaseModel):
    """Request to execute a parameter grid optimization (T071)."""

    early_stop_threshold: Optional[float] = Field(
        None,
        description="Stop early if Sharpe ratio exceeds this threshold",
    )
    ranking_metric: str = Field(
        default="composite_score",
        description="Metric to rank results by (composite_score, sharpe_ratio, total_return)",
    )
    custom_weights: Optional[Dict[str, float]] = Field(
        None,
        description="Custom composite score weights",
    )


class ParameterGridResponse(BaseModel):
    """Response for parameter grid details (T070, T072)."""

    grid_id: UUID = Field(..., description="Parameter grid ID")
    name: str = Field(..., description="Grid name")
    description: Optional[str] = Field(None, description="Grid description")
    symbol: str = Field(..., description="Trading symbol")
    start_date: datetime = Field(..., description="Backtest start date")
    end_date: datetime = Field(..., description="Backtest end date")
    timeframe: str = Field(..., description="Timeframe")
    initial_capital: Decimal = Field(..., description="Initial capital")
    parameters: Dict[str, List[Any]] = Field(..., description="Parameter grid")
    total_combinations: int = Field(..., description="Total parameter combinations")
    max_workers: int = Field(..., description="Maximum parallel workers")
    synthetic_strategy: str = Field(..., description="Synthetic strategy")
    status: str = Field(..., description="Grid status (pending, running, completed, failed)")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        from_attributes = True


class OptimizationResultResponse(BaseModel):
    """Response for a single optimization result (T072)."""

    params: Dict[str, Any] = Field(..., description="Parameter combination")
    total_return: float = Field(..., description="Total return (percentage)")
    sharpe_ratio: float = Field(..., description="Sharpe ratio")
    sortino_ratio: float = Field(..., description="Sortino ratio")
    calmar_ratio: float = Field(..., description="Calmar ratio")
    max_drawdown: float = Field(..., description="Maximum drawdown (percentage)")
    win_rate: float = Field(..., description="Win rate (0-1)")
    profit_factor: float = Field(..., description="Profit factor")
    total_trades: int = Field(..., description="Total number of trades")
    winning_trades: int = Field(..., description="Number of winning trades")
    losing_trades: int = Field(..., description="Number of losing trades")
    avg_win: float = Field(..., description="Average winning trade")
    avg_loss: float = Field(..., description="Average losing trade")
    composite_score: float = Field(..., description="Composite optimization score")
    execution_time_seconds: float = Field(..., description="Execution time in seconds")
    error: Optional[str] = Field(None, description="Error message if failed")


class ParameterGridResultsResponse(BaseModel):
    """Response for parameter grid optimization results (T072)."""

    grid_id: UUID = Field(..., description="Parameter grid ID")
    status: str = Field(..., description="Execution status")
    total_combinations: int = Field(..., description="Total combinations")
    completed_combinations: int = Field(..., description="Completed combinations")
    successful_combinations: int = Field(..., description="Successful combinations")
    failed_combinations: int = Field(..., description="Failed combinations")

    # Top results
    top_results: List[OptimizationResultResponse] = Field(
        ...,
        description="Top optimization results (sorted by ranking metric)",
    )

    # Execution metadata
    started_at: Optional[datetime] = Field(None, description="Execution start time")
    completed_at: Optional[datetime] = Field(None, description="Execution completion time")
    total_execution_time_seconds: Optional[float] = Field(
        None, description="Total execution time"
    )

    class Config:
        from_attributes = True


# ============================================================================
# User Story 4: A/B Testing Comparison Models (T109)
# ============================================================================


class CompareRunsRequest(BaseModel):
    """Request to compare two backtest runs (T109)."""

    run_a_id: UUID = Field(..., description="First backtest run ID")
    run_b_id: UUID = Field(..., description="Second backtest run ID")
    time_window_minutes: int = Field(
        default=5,
        description="Time window for trade overlap analysis (minutes)",
    )
    generate_report: bool = Field(
        default=True,
        description="Whether to generate full comparison report",
    )


class StatisticalTestResponse(BaseModel):
    """Statistical test result response."""

    t_statistic: float = Field(..., description="T-statistic")
    p_value: float = Field(..., description="P-value")
    is_significant: bool = Field(..., description="Statistically significant (p < 0.05)")
    degrees_of_freedom: float = Field(..., description="Degrees of freedom")
    mean_difference: Optional[float] = Field(None, description="Mean difference")
    confidence_interval_lower: Optional[float] = Field(None, description="CI lower bound")
    confidence_interval_upper: Optional[float] = Field(None, description="CI upper bound")


class TradeOverlapResponse(BaseModel):
    """Trade overlap analysis response."""

    consensus_trades: int = Field(..., description="Trades taken by both runs")
    divergent_trades_a: int = Field(..., description="Trades only in run A")
    divergent_trades_b: int = Field(..., description="Trades only in run B")
    overlap_rate: float = Field(..., description="Overlap rate (0-1)")


class MetricsComparisonResponse(BaseModel):
    """Side-by-side metrics comparison."""

    run_a: Dict[str, Any] = Field(..., description="Run A metrics")
    run_b: Dict[str, Any] = Field(..., description="Run B metrics")
    differences: Dict[str, float] = Field(..., description="Metric differences (A - B)")


class CompareRunsResponse(BaseModel):
    """Response for backtest comparison (T109)."""

    run_a_id: UUID = Field(..., description="First run ID")
    run_b_id: UUID = Field(..., description="Second run ID")
    recommendation: str = Field(
        ...,
        description="Recommendation: 'run_a', 'run_b', or 'no_significant_difference'",
    )

    metrics_comparison: MetricsComparisonResponse = Field(
        ..., description="Side-by-side metrics"
    )
    statistical_tests: Dict[str, StatisticalTestResponse] = Field(
        ..., description="Statistical significance tests"
    )
    trade_overlap: TradeOverlapResponse = Field(..., description="Trade overlap analysis")

    equity_curves: Optional[Dict[str, List[Any]]] = Field(
        None, description="Aligned equity curves"
    )
    performance_breakdown: Optional[Dict[str, Any]] = Field(
        None, description="Performance breakdown by time period"
    )

    report: Optional[Dict[str, Any]] = Field(
        None, description="Full comparison report (if generate_report=True)"
    )
