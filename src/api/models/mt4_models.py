"""
Pydantic models for MT4 REST API endpoints.

Request and response models for EA registration, connection management,
account info, positions, orders, and portfolio risk.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Request Models
# =============================================================================

class RegisterEARequest(BaseModel):
    """Request to register a new Expert Advisor."""

    name: str = Field(..., description="Unique EA identifier name")
    symbol: str = Field(..., description="Trading symbol for this EA (e.g., 'CrudeOIL')")
    host: str = Field(default="localhost", description="MT4 server host")
    strategy_name: Optional[str] = Field(None, description="Associated trading strategy")
    magic_number: Optional[int] = Field(
        None, description="Specific magic number (auto-allocated if not provided)"
    )
    max_positions: Optional[int] = Field(None, description="Maximum concurrent positions for this EA")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "crude_oil_breakout_ea",
                "symbol": "CrudeOIL",
                "host": "75.154.254.186",
                "strategy_name": "breakout",
                "magic_number": None,
                "max_positions": 5,
            }
        }


# =============================================================================
# Response Models
# =============================================================================

class RegisterEAResponse(BaseModel):
    """Response for EA registration."""

    ea_id: str = Field(..., description="Registered EA identifier")
    magic_number: int = Field(..., description="Allocated magic number")
    rep_port: int = Field(..., description="REP socket port for commands")
    pub_port: int = Field(..., description="PUB socket port for streaming")
    host: str = Field(..., description="MT4 server host")
    symbol: str = Field(..., description="Trading symbol")

    class Config:
        json_schema_extra = {
            "example": {
                "ea_id": "crude_oil_breakout_ea",
                "magic_number": 100000,
                "rep_port": 5555,
                "pub_port": 5556,
                "host": "75.154.254.186",
                "symbol": "CrudeOIL",
            }
        }


class EAInfoResponse(BaseModel):
    """Response for a single EA's information."""

    ea_id: str = Field(..., description="EA identifier")
    magic_number: int = Field(..., description="MT4 magic number")
    rep_port: int = Field(..., description="REP socket port")
    pub_port: int = Field(..., description="PUB socket port")
    host: str = Field(..., description="MT4 server host")
    symbol: str = Field(..., description="Trading symbol")
    strategy_name: Optional[str] = Field(None, description="Associated strategy")
    registered_at: Optional[datetime] = Field(None, description="Registration timestamp")
    health_status: Optional[str] = Field(None, description="Current health status")
    last_heartbeat: Optional[datetime] = Field(None, description="Last heartbeat timestamp")
    is_healthy: Optional[bool] = Field(None, description="Whether connection is healthy")

    class Config:
        json_schema_extra = {
            "example": {
                "ea_id": "crude_oil_breakout_ea",
                "magic_number": 100000,
                "rep_port": 5555,
                "pub_port": 5556,
                "host": "75.154.254.186",
                "symbol": "CrudeOIL",
                "strategy_name": "breakout",
                "registered_at": "2026-01-15T10:30:00Z",
                "health_status": "ACTIVE",
                "last_heartbeat": "2026-01-15T10:30:00Z",
                "is_healthy": True,
            }
        }


class EAListResponse(BaseModel):
    """Response for listing all registered EAs."""

    eas: List[EAInfoResponse] = Field(default_factory=list, description="List of registered EAs")
    total: int = Field(..., description="Total number of registered EAs")

    class Config:
        json_schema_extra = {
            "example": {
                "eas": [],
                "total": 3,
            }
        }


class AccountInfoResponse(BaseModel):
    """Response for MT4 account information."""

    balance: Optional[Decimal] = Field(None, description="Account balance")
    equity: Optional[Decimal] = Field(None, description="Account equity")
    margin: Optional[Decimal] = Field(None, description="Used margin")
    free_margin: Optional[Decimal] = Field(None, description="Available margin")
    leverage: Optional[int] = Field(None, description="Account leverage")
    account_number: Optional[int] = Field(None, description="MT4 account number")
    margin_level: Optional[Decimal] = Field(None, description="Margin level percentage")

    class Config:
        json_schema_extra = {
            "example": {
                "balance": 10000.00,
                "equity": 10250.50,
                "margin": 500.00,
                "free_margin": 9750.50,
                "leverage": 100,
                "account_number": 12345678,
                "margin_level": 2050.10,
            }
        }


class PortfolioRiskResponse(BaseModel):
    """Response for portfolio-level risk state."""

    total_equity: Decimal = Field(..., description="Total account equity")
    total_margin_used: Decimal = Field(..., description="Total margin in use")
    margin_level: Decimal = Field(..., description="Margin level percentage")
    total_open_positions: int = Field(..., description="Number of open positions")
    exposure_by_symbol: Dict[str, float] = Field(
        default_factory=dict, description="Net exposure per trading symbol"
    )
    exposure_by_ea: Dict[str, float] = Field(
        default_factory=dict, description="Margin used per EA (by magic number)"
    )
    is_margin_critical: bool = Field(False, description="Whether margin level is below safety threshold")
    last_updated: Optional[datetime] = Field(None, description="Last risk calculation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "total_equity": 10000.00,
                "total_margin_used": 500.00,
                "margin_level": 2000.00,
                "total_open_positions": 3,
                "exposure_by_symbol": {"CrudeOIL": 7250.00, "XAUUSD": 19500.00},
                "exposure_by_ea": {"100000": 7250.00, "100001": 19500.00},
                "is_margin_critical": False,
                "last_updated": "2026-01-15T10:30:00Z",
            }
        }


class PortfolioHealthResponse(BaseModel):
    """Response for system-level MT4 health check."""

    status: str = Field(..., description="Overall health status (healthy, degraded, unhealthy)")
    active_eas: int = Field(..., description="Number of active EAs")
    total_eas: int = Field(..., description="Total registered EAs")
    connection_status: Dict[str, Any] = Field(
        default_factory=dict, description="Per-EA connection health status"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Health check timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "active_eas": 3,
                "total_eas": 3,
                "connection_status": {
                    "crude_oil_breakout_ea": {
                        "is_healthy": True,
                        "health_status": "ACTIVE",
                        "seconds_since_heartbeat": 5.2,
                    }
                },
                "timestamp": "2026-01-15T10:30:00Z",
            }
        }


class MT4PositionResponse(BaseModel):
    """Response for a single MT4 position."""

    ticket: int = Field(..., description="MT4 position ticket number")
    symbol: str = Field(..., description="Trading symbol")
    direction: str = Field(..., description="Position direction (BUY or SELL)")
    lots: Decimal = Field(..., description="Position volume in lots")
    entry_price: Decimal = Field(..., description="Position open price")
    current_price: Optional[Decimal] = Field(None, description="Current market price")
    sl: Optional[Decimal] = Field(None, description="Stop loss level")
    tp: Optional[Decimal] = Field(None, description="Take profit level")
    profit: Optional[Decimal] = Field(None, description="Unrealized P&L")
    open_time: Optional[datetime] = Field(None, description="Position open time")
    magic_number: Optional[int] = Field(None, description="EA magic number")
    comment: Optional[str] = Field(None, description="Position comment")

    class Config:
        json_schema_extra = {
            "example": {
                "ticket": 98765432,
                "symbol": "CrudeOIL",
                "direction": "BUY",
                "lots": 0.10,
                "entry_price": 72.50,
                "current_price": 73.10,
                "sl": 71.00,
                "tp": 75.00,
                "profit": 60.00,
                "open_time": "2026-01-15T09:00:00Z",
                "magic_number": 100000,
                "comment": "breakout signal",
            }
        }


class MT4PositionListResponse(BaseModel):
    """Response for listing MT4 positions."""

    positions: List[MT4PositionResponse] = Field(
        default_factory=list, description="List of open MT4 positions"
    )
    total: int = Field(..., description="Total number of positions")

    class Config:
        json_schema_extra = {
            "example": {
                "positions": [],
                "total": 0,
            }
        }


class MT4OrderResponse(BaseModel):
    """Response for a single MT4 order."""

    ticket: Optional[int] = Field(None, description="MT4 ticket number")
    order_id: Optional[str] = Field(None, description="Internal order UUID")
    symbol: str = Field(..., description="Trading symbol")
    type: str = Field(..., description="Order type (MARKET, LIMIT, STOP)")
    direction: str = Field(..., description="Order direction (BUY or SELL)")
    lots: Decimal = Field(..., description="Order volume in lots")
    price: Optional[Decimal] = Field(None, description="Order price (execution or limit)")
    sl: Optional[Decimal] = Field(None, description="Stop loss level")
    tp: Optional[Decimal] = Field(None, description="Take profit level")
    status: str = Field(..., description="Order status (PENDING, CONFIRMED, REJECTED, CLOSED)")
    submitted_at: Optional[datetime] = Field(None, description="Order submission time")
    confirmed_at: Optional[datetime] = Field(None, description="Order confirmation time")
    error_message: Optional[str] = Field(None, description="Error message if rejected")

    class Config:
        json_schema_extra = {
            "example": {
                "ticket": 98765432,
                "order_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "symbol": "CrudeOIL",
                "type": "MARKET",
                "direction": "BUY",
                "lots": 0.10,
                "price": 72.50,
                "sl": 71.00,
                "tp": 75.00,
                "status": "CONFIRMED",
                "submitted_at": "2026-01-15T09:00:00Z",
                "confirmed_at": "2026-01-15T09:00:01Z",
                "error_message": None,
            }
        }


class MT4OrderListResponse(BaseModel):
    """Response for listing MT4 orders."""

    orders: List[MT4OrderResponse] = Field(
        default_factory=list, description="List of MT4 orders"
    )
    total: int = Field(..., description="Total number of matching orders")

    class Config:
        json_schema_extra = {
            "example": {
                "orders": [],
                "total": 0,
            }
        }
