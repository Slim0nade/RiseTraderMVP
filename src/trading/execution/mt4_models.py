"""
Pydantic models for MT4 integration.

Defines all data models for MT4 messages, events, and responses.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Base Event Model
# =============================================================================

class BaseEvent(BaseModel):
    """
    Base event model for all MT4 events.

    All events inherit from this base class to ensure consistent structure.
    """

    event_type: str = Field(..., description="Event type identifier")
    version: str = Field(default="1.0.0", description="Event schema version (semver)")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Event timestamp"
    )
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID for request tracing"
    )
    source: str = Field(
        default="mt4_integration_service",
        description="Event source identifier"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: str(v),
        }


# =============================================================================
# Order Events
# =============================================================================

class OrderConfirmedData(BaseModel):
    """Data payload for order_confirmed event."""

    order_id: str = Field(..., description="External order ID (UUID)")
    magic_number: int = Field(..., description="MT4 magic number")
    ticket_number: int = Field(..., description="MT4 ticket number")
    symbol: str = Field(..., description="Trading symbol")
    direction: Literal["BUY", "SELL"] = Field(..., description="Order direction")
    volume: Decimal = Field(..., description="Order volume in lots")
    execution_price: Decimal = Field(..., description="Execution price")
    execution_time: datetime = Field(..., description="Execution timestamp")


class OrderConfirmedEvent(BaseEvent):
    """Event emitted when MT4 confirms order receipt."""

    event_type: Literal["order_confirmed"] = "order_confirmed"
    data: OrderConfirmedData


class OrderRejectedData(BaseModel):
    """Data payload for order_rejected event."""

    order_id: str
    magic_number: int
    symbol: str
    direction: Literal["BUY", "SELL"]
    volume: Decimal
    error_code: int
    error_message: str
    rejected_at: datetime


class OrderRejectedEvent(BaseEvent):
    """Event emitted when MT4 rejects an order."""

    event_type: Literal["order_rejected"] = "order_rejected"
    data: OrderRejectedData


# =============================================================================
# Position Events
# =============================================================================

class PositionUpdatedData(BaseModel):
    """Data payload for position_updated event."""

    ticket_number: int = Field(..., description="MT4 position ticket")
    magic_number: int = Field(..., description="MT4 magic number")
    symbol: str = Field(..., description="Trading symbol")
    direction: Literal["BUY", "SELL"] = Field(..., description="Position direction")
    volume: Decimal = Field(..., description="Position size in lots")
    open_price: Decimal = Field(..., description="Position open price")
    current_price: Decimal = Field(..., description="Current market price")
    unrealized_pnl: Decimal = Field(..., description="Current P&L")
    stop_loss: Optional[Decimal] = Field(None, description="Stop loss level")
    take_profit: Optional[Decimal] = Field(None, description="Take profit level")
    open_time: datetime = Field(..., description="Position open time")
    last_updated: datetime = Field(..., description="Last update time")


class PositionUpdatedEvent(BaseEvent):
    """Event emitted when position P&L is updated."""

    event_type: Literal["position_updated"] = "position_updated"
    data: PositionUpdatedData


class PositionClosedData(BaseModel):
    """Data payload for position_closed event."""

    ticket_number: int
    magic_number: int
    symbol: str
    direction: Literal["BUY", "SELL"]
    volume: Decimal
    open_price: Decimal
    close_price: Decimal
    realized_pnl: Decimal
    open_time: datetime
    close_time: datetime
    close_reason: str  # "manual", "stop_loss", "take_profit", "margin_call"


class PositionClosedEvent(BaseEvent):
    """Event emitted when position is closed."""

    event_type: Literal["position_closed"] = "position_closed"
    data: PositionClosedData


# =============================================================================
# Market Data Events
# =============================================================================

class MarketTick(BaseModel):
    """Real-time market tick data."""

    symbol: str = Field(..., description="Trading symbol")
    bid: Decimal = Field(..., description="Bid price")
    ask: Decimal = Field(..., description="Ask price")
    timestamp: datetime = Field(..., description="Tick timestamp")
    volume: Optional[int] = Field(None, description="Tick volume")


class MarketTickEvent(BaseEvent):
    """Event emitted for each market tick."""

    event_type: Literal["market_tick"] = "market_tick"
    data: MarketTick


# =============================================================================
# Connection Events
# =============================================================================

class ConnectionStatusData(BaseModel):
    """Data payload for connection_status_changed event."""

    ea_id: str = Field(..., description="EA identifier")
    magic_number: int = Field(..., description="MT4 magic number")
    status: Literal["ACTIVE", "INACTIVE", "ERROR", "RECONNECTING"]
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConnectionStatusChangedEvent(BaseEvent):
    """Event emitted when EA connection status changes."""

    event_type: Literal["connection_status_changed"] = "connection_status_changed"
    data: ConnectionStatusData


# =============================================================================
# Portfolio Risk Events
# =============================================================================

class PortfolioRiskState(BaseModel):
    """Portfolio-level risk aggregation."""

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
    last_updated: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update timestamp"
    )

    @property
    def is_margin_critical(self) -> bool:
        """Check if margin level is below safety threshold."""
        return self.margin_level < Decimal('120.00')

    @property
    def available_margin_pct(self) -> Decimal:
        """Calculate available margin as percentage."""
        if self.total_equity == 0:
            return Decimal('0')
        return ((self.total_equity - self.total_margin_used) / self.total_equity) * 100


class PortfolioRiskUpdatedEvent(BaseEvent):
    """Event emitted when portfolio risk state changes."""

    event_type: Literal["portfolio_risk_updated"] = "portfolio_risk_updated"
    data: PortfolioRiskState


# =============================================================================
# MT4 Command/Response Models
# =============================================================================

class MT4Command(BaseModel):
    """Base model for commands sent to MT4."""

    command: str = Field(..., description="Command type")
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID for request tracing"
    )


class CreateInstantOrderCommand(MT4Command):
    """Command to create a market order."""

    command: Literal["create_instant_order"] = "create_instant_order"
    symbol: str
    order_type: Literal["BUY", "SELL"]  # EA expects "order_type" not "direction"
    volume: Decimal
    magic_number: int
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    comment: Optional[str] = None

    @field_validator('volume')
    @classmethod
    def validate_volume(cls, v):
        """Validate volume is positive."""
        if v <= 0:
            raise ValueError("Volume must be positive")
        return v


class CreatePendingOrderCommand(MT4Command):
    """Command to create a pending order (BUY_STOP, SELL_STOP, BUY_LIMIT, SELL_LIMIT)."""

    command: Literal["create_pending_order"] = "create_pending_order"
    symbol: str
    order_type: Literal["BUY_STOP", "SELL_STOP", "BUY_LIMIT", "SELL_LIMIT"]
    volume: Decimal
    price: Decimal  # Entry price for pending order
    magic_number: int
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    comment: Optional[str] = None
    expiration: Optional[str] = None  # ISO datetime string

    @field_validator('volume')
    @classmethod
    def validate_volume(cls, v):
        """Validate volume is positive."""
        if v <= 0:
            raise ValueError("Volume must be positive")
        return v

    @field_validator('price')
    @classmethod
    def validate_price(cls, v):
        """Validate price is positive."""
        if v <= 0:
            raise ValueError("Price must be positive")
        return v


class DeletePendingOrderCommand(MT4Command):
    """Command to delete/cancel a pending order."""

    command: Literal["delete_pending_order"] = "delete_pending_order"
    ticket: int
    magic_number: int


class ModifyPositionCommand(MT4Command):
    """
    Command to modify stop loss and/or take profit of an open position.
    
    Used for:
    - Adjusting stops to non-obvious "weird" levels (anti-stop-hunting)
    - Implementing trailing stops
    - Moving stops to breakeven
    """

    command: Literal["modify_position"] = "modify_position"
    ticket: int
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None

    @field_validator('stop_loss', 'take_profit', mode='before')
    @classmethod
    def coerce_to_decimal(cls, v):
        """Convert numeric values to Decimal."""
        if v is None:
            return None
        return Decimal(str(v))


class GetPendingOrdersCommand(MT4Command):
    """Command to get all pending orders."""

    command: Literal["get_pending_orders"] = "get_pending_orders"
    magic_number: Optional[int] = None  # Filter by magic number


class GetAccountInfoCommand(MT4Command):
    """Command to retrieve account information."""

    command: Literal["get_account_info"] = "get_account_info"
    magic_number: int


class GetOpenPositionsCommand(MT4Command):
    """Command to retrieve open positions."""

    command: Literal["get_open_positions"] = "get_open_positions"
    magic_number: Optional[int] = None  # None = all positions


class ClosePositionCommand(MT4Command):
    """Command to close an open position."""

    command: Literal["close_position"] = "close_position"
    ticket: int  # EA expects "ticket" not "ticket_number"
    magic_number: int
    volume: Optional[Decimal] = None  # None = close entire position


class GetSymbolsCommand(MT4Command):
    """Command to retrieve available trading symbols."""

    command: Literal["get_symbols"] = "get_symbols"
    magic_number: int


class MT4Response(BaseModel):
    """Base model for responses from MT4."""

    success: bool = Field(..., description="Whether command succeeded")
    correlation_id: str = Field(..., description="Correlation ID from request")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    error_code: Optional[int] = None
    error_message: Optional[str] = None


class OrderResponse(MT4Response):
    """Response for order creation commands."""

    ticket_number: Optional[int] = None
    execution_price: Optional[Decimal] = None
    execution_time: Optional[datetime] = None


class AccountInfoResponse(MT4Response):
    """Response for account info queries."""

    account_number: Optional[int] = None
    balance: Optional[Decimal] = None
    equity: Optional[Decimal] = None
    margin: Optional[Decimal] = None
    free_margin: Optional[Decimal] = None
    margin_level: Optional[Decimal] = None
    leverage: Optional[int] = None


class PositionInfo(BaseModel):
    """Information about a single position."""

    ticket_number: int
    symbol: str
    direction: Literal["BUY", "SELL"]
    volume: Decimal
    open_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    open_time: datetime
    magic_number: int
    comment: Optional[str] = None


class PositionsResponse(MT4Response):
    """Response for open positions query."""

    positions: list[PositionInfo] = Field(default_factory=list)


class SymbolsResponse(MT4Response):
    """Response for get_symbols query."""

    symbols: list[str] = Field(default_factory=list)
    count: int = 0


# =============================================================================
# Utility Models
# =============================================================================

class CircuitBreakerState(BaseModel):
    """Circuit breaker state for connection resilience."""

    state: Literal["CLOSED", "OPEN", "HALF_OPEN"] = Field(default="CLOSED")
    failure_count: int = Field(default=0)
    last_failure_time: Optional[datetime] = None
    success_count: int = Field(default=0)


class ConnectionHealth(BaseModel):
    """Health status of an EA connection."""

    ea_id: str
    magic_number: int
    status: Literal["ACTIVE", "INACTIVE", "ERROR", "RECONNECTING"]
    last_heartbeat: Optional[datetime] = None
    error_count: int = 0
    circuit_breaker_state: CircuitBreakerState = Field(
        default_factory=CircuitBreakerState
    )

    def is_healthy(self, heartbeat_timeout_seconds: int = 90) -> bool:
        """Check if connection is healthy."""
        if self.status != "ACTIVE":
            return False

        if self.last_heartbeat is None:
            return False

        elapsed = (datetime.utcnow() - self.last_heartbeat).total_seconds()
        return elapsed < heartbeat_timeout_seconds


# =============================================================================
# User Story 4: Account Information Models (T083)
# =============================================================================

class AccountInfo(BaseModel):
    """
    Account information from MT4.

    Contains balance, equity, margin, and other account metrics.
    """

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

    @field_validator('balance', 'equity', 'margin', 'free_margin', 'margin_level', 'profit', mode='before')
    @classmethod
    def coerce_to_decimal(cls, v):
        """Convert numeric values to Decimal."""
        if v is None:
            return None
        return Decimal(str(v))

    class Config:
        json_encoders = {
            Decimal: lambda v: str(v),
        }


class PositionInfo(BaseModel):
    """
    Open position information from MT4.

    Represents a single open trade position.
    """

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

    @field_validator('volume', 'open_price', 'current_price', 'stop_loss', 'take_profit', 'profit', mode='before')
    @classmethod
    def coerce_to_decimal(cls, v):
        """Convert numeric values to Decimal."""
        if v is None:
            return None
        return Decimal(str(v))

    @field_validator('open_time', mode='before')
    @classmethod
    def parse_datetime(cls, v):
        """Parse datetime from string if needed."""
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace('Z', '+00:00'))
        return v

    class Config:
        json_encoders = {
            Decimal: lambda v: str(v),
            datetime: lambda v: v.isoformat(),
        }


class GetAccountInfoCommand(BaseModel):
    """Command to request account information from MT4."""

    command: Literal["get_account_info"] = "get_account_info"
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID for request tracing"
    )


class GetOpenPositionsCommand(BaseModel):
    """Command to request open positions from MT4."""

    command: Literal["get_open_positions"] = "get_open_positions"
    magic_number: Optional[int] = Field(
        None,
        description="Optional magic number to filter positions"
    )
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID for request tracing"
    )
