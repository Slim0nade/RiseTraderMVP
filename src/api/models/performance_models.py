"""
Pydantic models for Performance API endpoints.
"""
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# Response Models
class PerformanceSummaryResponse(BaseModel):
    """Summary of trading performance."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float  # Percentage
    total_profit: Decimal
    total_loss: Decimal
    net_profit: Decimal
    average_win: Decimal
    average_loss: Decimal
    profit_factor: Optional[Decimal] = None
    max_drawdown: Optional[Decimal] = None
    max_drawdown_percent: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    current_balance: Decimal
    period_start: datetime
    period_end: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "total_trades": 150,
                "winning_trades": 95,
                "losing_trades": 55,
                "win_rate": 63.33,
                "total_profit": 15000.0,
                "total_loss": 7500.0,
                "net_profit": 7500.0,
                "average_win": 157.89,
                "average_loss": 136.36,
                "profit_factor": 2.0,
                "max_drawdown": 2500.0,
                "max_drawdown_percent": 8.5,
                "sharpe_ratio": 1.75,
                "current_balance": 57500.0,
                "period_start": "2024-01-01T00:00:00Z",
                "period_end": "2024-01-15T23:59:59Z",
            }
        }


class PerformanceMetricsResponse(BaseModel):
    """Detailed performance metrics."""

    # Basic metrics
    total_trades: int
    open_positions: int
    closed_positions: int

    # Profitability
    gross_profit: Decimal
    gross_loss: Decimal
    net_profit: Decimal
    profit_factor: Optional[Decimal] = None

    # Win/Loss stats
    win_rate: float
    average_win: Decimal
    average_loss: Decimal
    largest_win: Decimal
    largest_loss: Decimal
    average_trade: Decimal

    # Risk metrics
    max_drawdown: Optional[Decimal] = None
    max_drawdown_percent: Optional[float] = None
    current_drawdown: Optional[Decimal] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None

    # Consistency
    consecutive_wins: int
    consecutive_losses: int
    max_consecutive_wins: int
    max_consecutive_losses: int

    # Account
    starting_balance: Decimal
    current_balance: Decimal
    peak_balance: Decimal
    total_return: Decimal
    total_return_percent: float

    # Time period
    period_start: datetime
    period_end: datetime
    trading_days: int

    class Config:
        json_schema_extra = {
            "example": {
                "total_trades": 150,
                "open_positions": 5,
                "closed_positions": 145,
                "gross_profit": 15000.0,
                "gross_loss": 7500.0,
                "net_profit": 7500.0,
                "profit_factor": 2.0,
                "win_rate": 63.33,
                "average_win": 157.89,
                "average_loss": 136.36,
                "largest_win": 850.0,
                "largest_loss": 450.0,
                "average_trade": 50.0,
                "max_drawdown": 2500.0,
                "max_drawdown_percent": 8.5,
                "sharpe_ratio": 1.75,
                "consecutive_wins": 3,
                "consecutive_losses": 0,
                "max_consecutive_wins": 12,
                "max_consecutive_losses": 5,
                "starting_balance": 50000.0,
                "current_balance": 57500.0,
                "peak_balance": 58200.0,
                "total_return": 7500.0,
                "total_return_percent": 15.0,
                "period_start": "2024-01-01T00:00:00Z",
                "period_end": "2024-01-15T23:59:59Z",
                "trading_days": 15,
            }
        }


class StrategyPerformance(BaseModel):
    """Performance metrics for a specific strategy."""

    strategy_name: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    net_profit: Decimal
    average_profit: Decimal
    profit_factor: Optional[Decimal] = None
    max_drawdown: Optional[Decimal] = None
    sharpe_ratio: Optional[float] = None
    allocation_percent: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "strategy_name": "breakout",
                "total_trades": 50,
                "winning_trades": 35,
                "losing_trades": 15,
                "win_rate": 70.0,
                "net_profit": 3500.0,
                "average_profit": 70.0,
                "profit_factor": 2.5,
                "max_drawdown": 800.0,
                "sharpe_ratio": 2.1,
                "allocation_percent": 33.33,
            }
        }


class PerformanceByStrategyResponse(BaseModel):
    """Performance breakdown by strategy."""

    strategies: List[StrategyPerformance]
    total_strategies: int
    overall_performance: PerformanceSummaryResponse

    class Config:
        json_schema_extra = {
            "example": {
                "strategies": [],
                "total_strategies": 3,
                "overall_performance": {
                    "total_trades": 150,
                    "net_profit": 7500.0,
                },
            }
        }


class EquityCurvePoint(BaseModel):
    """Single point on equity curve."""

    timestamp: datetime
    balance: Decimal
    equity: Decimal
    drawdown: Decimal
    drawdown_percent: float

    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2024-01-15T10:30:00Z",
                "balance": 57500.0,
                "equity": 57850.0,
                "drawdown": 350.0,
                "drawdown_percent": 0.6,
            }
        }


class PerformanceChartResponse(BaseModel):
    """Chart data for performance visualization."""

    equity_curve: List[EquityCurvePoint]
    start_date: datetime
    end_date: datetime
    period_type: str  # daily, hourly, etc.

    class Config:
        json_schema_extra = {
            "example": {
                "equity_curve": [],
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-01-15T23:59:59Z",
                "period_type": "daily",
            }
        }


class MonthlyPerformance(BaseModel):
    """Monthly performance summary."""

    year: int
    month: int
    month_name: str
    trades: int
    net_profit: Decimal
    return_percent: float
    win_rate: float

    class Config:
        json_schema_extra = {
            "example": {
                "year": 2024,
                "month": 1,
                "month_name": "January",
                "trades": 150,
                "net_profit": 7500.0,
                "return_percent": 15.0,
                "win_rate": 63.33,
            }
        }


class MonthlyPerformanceResponse(BaseModel):
    """Monthly performance breakdown."""

    monthly_data: List[MonthlyPerformance]
    total_months: int

    class Config:
        json_schema_extra = {
            "example": {
                "monthly_data": [],
                "total_months": 12,
            }
        }
