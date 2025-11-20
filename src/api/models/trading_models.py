"""
Pydantic models for Trading API endpoints.
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# Enums
class PositionType(str, Enum):
    """Position type."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class TradingMode(str, Enum):
    """Trading mode."""

    PAPER = "PAPER"
    LIVE = "LIVE"


# Request Models
class PlaceOrderRequest(BaseModel):
    """Request to place a new order."""

    symbol: str = Field(..., description="Trading symbol (e.g., 'CrudeOIL')")
    order_type: OrderType = Field(..., description="Order type")
    position_type: PositionType = Field(..., description="BUY or SELL")
    size: Decimal = Field(..., gt=0, description="Position size")
    price: Optional[Decimal] = Field(
        None, description="Limit price (required for LIMIT orders)"
    )
    stop_loss: Optional[Decimal] = Field(None, description="Stop loss price")
    take_profit: Optional[Decimal] = Field(None, description="Take profit price")
    strategy: str = Field(default="manual", description="Strategy name")
    mode: TradingMode = Field(default=TradingMode.PAPER, description="Trading mode")
    comment: Optional[str] = Field(None, description="Order comment")

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "CrudeOIL",
                "order_type": "MARKET",
                "position_type": "BUY",
                "size": 0.1,
                "stop_loss": 70.50,
                "take_profit": 75.00,
                "strategy": "manual",
                "mode": "PAPER",
                "comment": "Test order",
            }
        }


class ClosePositionRequest(BaseModel):
    """Request to close a position."""

    size: Optional[Decimal] = Field(
        None, description="Partial close size (None = close all)"
    )
    reason: Optional[str] = Field(None, description="Close reason")


# Response Models
class PositionResponse(BaseModel):
    """Response model for open position."""

    id: int
    number: str
    type: str
    size: Decimal
    symbol: str
    price: Decimal
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    commission: Decimal
    last_profit: Optional[Decimal] = None
    last_update: datetime
    last_strategy: str
    simulation: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "number": "12345678",
                "type": "BUY",
                "size": 0.1,
                "symbol": "CrudeOIL",
                "price": 72.50,
                "stop_loss": 70.50,
                "take_profit": 75.00,
                "commission": 0.05,
                "last_profit": 25.0,
                "last_update": "2024-01-15T10:30:00Z",
                "last_strategy": "breakout",
                "simulation": False,
            }
        }


class TradingHistoryResponse(BaseModel):
    """Response model for trading history."""

    id: int
    number: str
    type: str
    size: Decimal
    symbol: str
    open_time: datetime
    open_price: Decimal
    close_time: datetime
    close_price: Decimal
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    commission: Decimal
    profit: Decimal
    strategy: str
    simulation: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "number": "12345678",
                "type": "BUY",
                "size": 0.1,
                "symbol": "CrudeOIL",
                "open_time": "2024-01-15T10:00:00Z",
                "open_price": 72.50,
                "close_time": "2024-01-15T11:00:00Z",
                "close_price": 73.00,
                "stop_loss": 70.50,
                "take_profit": 75.00,
                "commission": 0.05,
                "profit": 45.0,
                "strategy": "breakout",
                "simulation": False,
            }
        }


class PositionListResponse(BaseModel):
    """Response for listing positions."""

    positions: List[PositionResponse]
    total: int
    page: int
    page_size: int

    class Config:
        json_schema_extra = {
            "example": {
                "positions": [],
                "total": 5,
                "page": 1,
                "page_size": 50,
            }
        }


class TradingHistoryListResponse(BaseModel):
    """Response for listing trading history."""

    trades: List[TradingHistoryResponse]
    total: int
    page: int
    page_size: int

    class Config:
        json_schema_extra = {
            "example": {
                "trades": [],
                "total": 150,
                "page": 1,
                "page_size": 50,
            }
        }


class OrderResponse(BaseModel):
    """Response for order placement."""

    success: bool
    message: str
    order_number: Optional[str] = None
    position_id: Optional[int] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Order placed successfully",
                "order_number": "12345678",
                "position_id": 1,
            }
        }


class ClosePositionResponse(BaseModel):
    """Response for closing a position."""

    success: bool
    message: str
    closed_at: Optional[datetime] = None
    final_profit: Optional[Decimal] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Position closed successfully",
                "closed_at": "2024-01-15T11:00:00Z",
                "final_profit": 45.0,
            }
        }
