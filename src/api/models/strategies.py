"""
Pydantic models for strategy API responses.

These models define the structure and validation for strategy-related API responses
including strategies list, allocations, and performance metrics.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, ConfigDict


class StrategyResponse(BaseModel):
    """
    Response model for a single strategy.

    Contains strategy configuration including name, status, allocated capital,
    and parameters.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Strategy unique identifier")
    name: str = Field(..., description="Strategy name", max_length=255)
    description: Optional[str] = Field(None, description="Strategy description")
    status: str = Field(..., description="Strategy status (ACTIVE, PAUSED, DISABLED)")
    allocated_capital: Decimal = Field(
        ...,
        description="Currently allocated capital",
        ge=0,
        decimal_places=2
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Strategy configuration parameters (JSON)"
    )
    created_at: datetime = Field(..., description="Strategy creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class StrategyListResponse(BaseModel):
    """
    Response model for list of strategies.

    Contains array of strategies and total count for pagination.
    """
    model_config = ConfigDict(from_attributes=True)

    data: List[StrategyResponse] = Field(
        default_factory=list,
        description="List of strategies"
    )
    total: int = Field(..., description="Total number of strategies", ge=0)


class StrategyAllocationResponse(BaseModel):
    """
    Response model for a single strategy allocation record.

    Contains historical allocation data including capital amount, percentage,
    and allocation date.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Allocation record unique identifier")
    strategy_id: int = Field(..., description="Strategy identifier")
    allocated_capital: Decimal = Field(
        ...,
        description="Allocated capital amount",
        ge=0,
        decimal_places=2
    )
    allocated_percentage: Decimal = Field(
        ...,
        description="Allocation as percentage of total capital",
        ge=0,
        le=100,
        decimal_places=2
    )
    allocation_date: datetime = Field(..., description="Date of allocation change")
    notes: Optional[str] = Field(None, description="Allocation notes or reason")


class StrategyAllocationListResponse(BaseModel):
    """
    Response model for list of strategy allocations.

    Contains array of allocation records and total count.
    """
    model_config = ConfigDict(from_attributes=True)

    data: List[StrategyAllocationResponse] = Field(
        default_factory=list,
        description="List of allocation records"
    )
    total: int = Field(..., description="Total number of allocation records", ge=0)


class StrategyPerformanceResponse(BaseModel):
    """
    Response model for strategy performance metrics.

    Contains comprehensive performance statistics for a strategy including
    win rate, profit/loss, Sharpe ratio, and drawdown metrics.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Performance record unique identifier")
    strategy_id: int = Field(..., description="Strategy identifier")
    period: str = Field(
        ...,
        description="Performance period (daily, weekly, monthly, all_time)"
    )
    period_start: datetime = Field(..., description="Period start date")
    period_end: datetime = Field(..., description="Period end date")

    # Trade statistics
    total_trades: int = Field(..., description="Total number of trades", ge=0)
    winning_trades: int = Field(..., description="Number of winning trades", ge=0)
    losing_trades: int = Field(..., description="Number of losing trades", ge=0)
    win_rate: Decimal = Field(
        ...,
        description="Win rate percentage",
        ge=0,
        le=100,
        decimal_places=2
    )

    # Profit/Loss metrics
    total_profit: Decimal = Field(
        ...,
        description="Total profit from winning trades",
        decimal_places=2
    )
    total_loss: Decimal = Field(
        ...,
        description="Total loss from losing trades",
        decimal_places=2
    )
    net_profit: Decimal = Field(
        ...,
        description="Net profit (total profit - total loss)",
        decimal_places=2
    )

    # Risk metrics
    sharpe_ratio: Optional[Decimal] = Field(
        None,
        description="Sharpe ratio (risk-adjusted return)",
        decimal_places=4
    )
    max_drawdown: Optional[Decimal] = Field(
        None,
        description="Maximum drawdown percentage",
        ge=0,
        decimal_places=4
    )

    # Average metrics
    average_win: Optional[Decimal] = Field(
        None,
        description="Average profit per winning trade",
        decimal_places=2
    )
    average_loss: Optional[Decimal] = Field(
        None,
        description="Average loss per losing trade",
        decimal_places=2
    )
