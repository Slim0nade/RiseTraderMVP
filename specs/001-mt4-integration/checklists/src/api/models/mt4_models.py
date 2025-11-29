"""
API request/response models for MT4 integration endpoints.

Pydantic models for FastAPI request validation and response serialization.
"""
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Account Query Models (T087 - User Story 4)
# =============================================================================

class AccountInfoResponse(BaseModel):
    """Response model for account information query."""
    
    balance: Decimal = Field(..., description="Account balance")
    equity: Decimal = Field(..., description="Account equity (balance + floating P&L)")
    margin: Decimal = Field(..., description="Used margin")
    free_margin: Decimal = Field(..., description="Free margin available for trading")
    margin_level: Decimal = Field(..., description="Margin level percentage (equity/margin * 100)")
    profit: Decimal = Field(..., description="Total floating profit/loss")
    account_number: int = Field(..., description="MT4 account number")
    leverage: int = Field(..., description="Account leverage (e.g., 100 for 1:100)")
    currency: str = Field(..., description="Account currency (e.g., USD)")
    server: str = Field(..., description="MT4 server name")
    company: str = Field(..., description="Broker company name")

    class Config:
        json_encoders = {
            Decimal: lambda v: str(v),
        }


class PositionInfoResponse(BaseModel):
    """Response model for open position information."""
    
    ticket: int = Field(..., description="Position ticket number")
    symbol: str = Field(..., description="Trading symbol")
    type: Literal["BUY", "SELL"] = Field(..., description="Position type")
    volume: Decimal = Field(..., description="Position volume in lots")
    open_price: Decimal = Field(..., description="Opening price")
    current_price: Decimal = Field(..., description="Current market price")
    stop_loss: Optional[Decimal] = Field(None, description="Stop loss price")
    take_profit: Optional[Decimal] = Field(None, description="Take profit price")
    profit: Decimal = Field(..., description="Current profit/loss")
    open_time: datetime = Field(..., description="Position open time")
    magic_number: int = Field(..., description="EA magic number")

    class Config:
        json_encoders = {
            Decimal: lambda v: str(v),
            datetime: lambda v: v.isoformat(),
        }


class OpenPositionsResponse(BaseModel):
    """Response model for open positions query."""
    
    positions: List[PositionInfoResponse] = Field(
        default_factory=list,
        description="List of open positions"
    )
    count: int = Field(..., description="Total number of positions")


# =============================================================================
# EA Connection Management Models (T098-T102)
# =============================================================================

class RegisterEARequest(BaseModel):
    """Request model for registering a new EA."""
    
    ea_id: str = Field(..., description="Unique EA identifier", min_length=1, max_length=100)
    symbol: str = Field(..., description="Trading symbol for this EA", min_length=1)
    host: str = Field(default="localhost", description="MT4 server host")
    strategy_name: Optional[str] = Field(None, description="Strategy name for this EA")
    max_positions: Optional[int] = Field(None, description="Maximum open positions for this EA")
    
    @field_validator('ea_id')
    @classmethod
    def validate_ea_id(cls, v):
        """Validate EA ID format."""
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError("EA ID must be alphanumeric with optional underscores/hyphens")
        return v


class EAConnectionResponse(BaseModel):
    """Response model for EA connection information."""
    
    ea_id: str = Field(..., description="EA identifier")
    magic_number: int = Field(..., description="Allocated magic number")
    rep_port: int = Field(..., description="REP socket port")
    pub_port: int = Field(..., description="PUB socket port")
    host: str = Field(..., description="MT4 server host")
    symbol: str = Field(..., description="Trading symbol")
    status: Literal["ACTIVE", "INACTIVE", "ERROR", "RECONNECTING"] = Field(
        ..., description="Connection status"
    )
    last_heartbeat: Optional[datetime] = Field(None, description="Last heartbeat timestamp")
    encryption_enabled: bool = Field(..., description="Whether encryption is enabled")


class EAConnectionListResponse(BaseModel):
    """Response model for list of EA connections."""
    
    connections: List[EAConnectionResponse] = Field(
        default_factory=list,
        description="List of EA connections"
    )
    count: int = Field(..., description="Total number of connections")


class ReconnectEAResponse(BaseModel):
    """Response model for EA reconnection."""
    
    ea_id: str = Field(..., description="EA identifier")
    status: str = Field(..., description="Reconnection status")
    message: str = Field(..., description="Status message")


# =============================================================================
# Order Query Models (T103)
# =============================================================================

class OrderQueryParams(BaseModel):
    """Query parameters for order filtering."""
    
    magic_number: Optional[int] = Field(None, description="Filter by magic number")
    symbol: Optional[str] = Field(None, description="Filter by symbol")
    status: Optional[Literal["PENDING", "CONFIRMED", "EXECUTED", "REJECTED"]] = Field(
        None, description="Filter by order status"
    )
    start_date: Optional[datetime] = Field(None, description="Filter orders after this date")
    end_date: Optional[datetime] = Field(None, description="Filter orders before this date")
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum number of results")
    offset: int = Field(default=0, ge=0, description="Pagination offset")


class OrderResponse(BaseModel):
    """Response model for order information."""
    
    order_id: str = Field(..., description="Order ID")
    magic_number: int = Field(..., description="Magic number")
    symbol: str = Field(..., description="Trading symbol")
    direction: Literal["BUY", "SELL"] = Field(..., description="Order direction")
    volume: Decimal = Field(..., description="Order volume")
    status: str = Field(..., description="Order status")
    ticket_number: Optional[int] = Field(None, description="MT4 ticket number")
    execution_price: Optional[Decimal] = Field(None, description="Execution price")
    created_at: datetime = Field(..., description="Order creation time")
    updated_at: datetime = Field(..., description="Last update time")

    class Config:
        json_encoders = {
            Decimal: lambda v: str(v),
            datetime: lambda v: v.isoformat(),
        }


class OrderListResponse(BaseModel):
    """Response model for order list query."""
    
    orders: List[OrderResponse] = Field(default_factory=list, description="List of orders")
    count: int = Field(..., description="Total number of orders matching filters")
    limit: int = Field(..., description="Result limit")
    offset: int = Field(..., description="Result offset")


# =============================================================================
# Portfolio Risk Models (T105)
# =============================================================================

class PortfolioRiskResponse(BaseModel):
    """Response model for portfolio risk state."""
    
    total_equity: Decimal = Field(..., description="Total account equity")
    total_margin_used: Decimal = Field(..., description="Total margin used")
    margin_level: Decimal = Field(..., description="Margin level percentage")
    total_open_positions: int = Field(..., description="Number of open positions")
    exposure_by_symbol: Dict[str, Decimal] = Field(
        default_factory=dict,
        description="Net exposure per symbol"
    )
    exposure_by_ea: Dict[str, Decimal] = Field(
        default_factory=dict,
        description="Margin used per EA (by magic number)"
    )
    last_updated: datetime = Field(..., description="Last update timestamp")
    is_margin_critical: bool = Field(..., description="Whether margin level is critical (<120%)")
    available_margin_pct: Decimal = Field(..., description="Available margin as percentage")

    class Config:
        json_encoders = {
            Decimal: lambda v: str(v),
            datetime: lambda v: v.isoformat(),
        }


# =============================================================================
# Health Check Models (T106)
# =============================================================================

class ServiceHealthResponse(BaseModel):
    """Response model for service health check."""
    
    status: Literal["healthy", "degraded", "unhealthy"] = Field(
        ..., description="Overall service health status"
    )
    timestamp: datetime = Field(..., description="Health check timestamp")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    active_connections: int = Field(..., description="Number of active EA connections")
    total_orders_today: int = Field(..., description="Total orders processed today")
    total_positions_open: int = Field(..., description="Total open positions")
    errors_last_hour: int = Field(..., description="Error count in last hour")
    avg_order_latency_ms: Optional[float] = Field(None, description="Average order latency (ms)")
    
    # Component health
    database_healthy: bool = Field(..., description="Database connection status")
    redis_healthy: bool = Field(..., description="Redis connection status")
    mt4_connections_healthy: int = Field(..., description="Number of healthy MT4 connections")
    
    # Details if degraded/unhealthy
    issues: List[str] = Field(default_factory=list, description="List of current issues")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


# =============================================================================
# Common Response Models
# =============================================================================

class ErrorResponse(BaseModel):
    """Standard error response model."""
    
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class SuccessResponse(BaseModel):
    """Standard success response model."""
    
    success: bool = Field(True, description="Operation success status")
    message: str = Field(..., description="Success message")
    data: Optional[Dict] = Field(None, description="Additional response data")
