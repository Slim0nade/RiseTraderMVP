"""
Pydantic models for Strategy API endpoints.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# Response Models
class StrategyResponse(BaseModel):
    """Response model for trading strategy."""

    id: int
    name: str
    description: Optional[str] = None
    enabled: bool
    allocation_percent: Decimal
    max_positions: int
    max_position_size: Decimal
    symbols: List[str]
    parameters: Dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "name": "breakout",
                "description": "Breakout strategy with dynamic support/resistance",
                "enabled": True,
                "allocation_percent": 33.33,
                "max_positions": 3,
                "max_position_size": 0.5,
                "symbols": ["CrudeOIL"],
                "parameters": {
                    "lookback_period": 20,
                    "breakout_threshold": 0.02,
                    "stop_loss_atr": 2.0,
                },
                "created_at": "2024-01-01T00:00:00Z",
            }
        }


class StrategyListResponse(BaseModel):
    """Response for listing strategies."""

    strategies: List[StrategyResponse]
    total: int
    enabled_count: int
    disabled_count: int

    class Config:
        json_schema_extra = {
            "example": {
                "strategies": [],
                "total": 3,
                "enabled_count": 2,
                "disabled_count": 1,
            }
        }


class StrategyPerformanceResponse(BaseModel):
    """Performance metrics for a strategy."""

    strategy_id: int
    strategy_name: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    gross_profit: Decimal
    gross_loss: Decimal
    net_profit: Decimal
    average_profit: Decimal
    profit_factor: Optional[Decimal] = None
    max_drawdown: Optional[Decimal] = None
    sharpe_ratio: Optional[float] = None
    current_positions: int
    last_trade_at: Optional[datetime] = None
    period_start: datetime
    period_end: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "strategy_id": 1,
                "strategy_name": "breakout",
                "total_trades": 50,
                "winning_trades": 35,
                "losing_trades": 15,
                "win_rate": 70.0,
                "gross_profit": 5250.0,
                "gross_loss": 1750.0,
                "net_profit": 3500.0,
                "average_profit": 70.0,
                "profit_factor": 3.0,
                "max_drawdown": 800.0,
                "sharpe_ratio": 2.1,
                "current_positions": 2,
                "last_trade_at": "2024-01-15T10:30:00Z",
                "period_start": "2024-01-01T00:00:00Z",
                "period_end": "2024-01-15T23:59:59Z",
            }
        }


# Request Models
class UpdateStrategyRequest(BaseModel):
    """Request to update strategy configuration."""

    enabled: Optional[bool] = None
    allocation_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    max_positions: Optional[int] = Field(None, ge=0)
    max_position_size: Optional[Decimal] = Field(None, gt=0)
    symbols: Optional[List[str]] = None
    parameters: Optional[Dict[str, Any]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": True,
                "allocation_percent": 40.0,
                "max_positions": 5,
                "parameters": {
                    "lookback_period": 25,
                    "breakout_threshold": 0.025,
                },
            }
        }


class StrategyOperationResponse(BaseModel):
    """Response for strategy enable/disable operations."""

    success: bool
    message: str
    strategy_id: int
    strategy_name: str
    new_status: str  # enabled, disabled

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Strategy enabled successfully",
                "strategy_id": 1,
                "strategy_name": "breakout",
                "new_status": "enabled",
            }
        }


class StrategyUpdateResponse(BaseModel):
    """Response for strategy update operations."""

    success: bool
    message: str
    strategy: StrategyResponse

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Strategy updated successfully",
                "strategy": {
                    "id": 1,
                    "name": "breakout",
                    "enabled": True,
                },
            }
        }
