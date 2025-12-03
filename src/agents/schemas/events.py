"""
Base event schemas for agent communication.
All agent events inherit from BaseEvent for consistent message passing.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict


class EventType(str, Enum):
    """Event types for agent communication."""

    # Market data events
    MARKET_TICK = "market_tick"
    MARKET_DATA_UPDATE = "market_data_update"

    # Analysis events
    TECHNICAL_ANALYSIS_COMPLETE = "technical_analysis_complete"
    FUNDAMENTAL_ANALYSIS_COMPLETE = "fundamental_analysis_complete"
    SENTIMENT_ANALYSIS_COMPLETE = "sentiment_analysis_complete"

    # Debate events
    DEBATE_INITIATED = "debate_initiated"
    DEBATE_COMPLETE = "debate_complete"

    # Decision events
    TRADE_INTENT_GENERATED = "trade_intent_generated"
    POSITION_SIZE_CALCULATED = "position_size_calculated"
    STOP_LOSS_SET = "stop_loss_set"
    TAKE_PROFIT_SET = "take_profit_set"
    ENTRY_TIMING_DECIDED = "entry_timing_decided"

    # Execution events
    TRADE_EXECUTED = "trade_executed"
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    ORDER_CANCELLED = "order_cancelled"
    POSITION_CLOSED = "position_closed"

    # Risk events
    RISK_LIMIT_BREACHED = "risk_limit_breached"
    DRAWDOWN_ALERT = "drawdown_alert"
    CORRELATION_WARNING = "correlation_warning"

    # System events
    AGENT_STARTED = "agent_started"
    AGENT_STOPPED = "agent_stopped"
    AGENT_ERROR = "agent_error"
    REBALANCE_TRIGGERED = "rebalance_triggered"


class EventPriority(str, Enum):
    """Event priority levels for processing order."""

    CRITICAL = "critical"  # Risk alerts, system errors
    HIGH = "high"  # Trade execution, order fills
    NORMAL = "normal"  # Analysis results, decisions
    LOW = "low"  # Status updates, logging


class BaseEvent(BaseModel):
    """
    Base event schema for all agent communication.

    All events inherit from this base class to ensure consistent
    structure for event-driven agent coordination.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                "event_type": "market_tick",
                "timestamp": "2025-12-02T10:30:00Z",
                "source_agent_id": "agent-123",
                "source_agent_type": "market_data_agent",
                "strategy_team_id": "team-gold-001",
                "priority": "normal",
                "payload": {"symbol": "Gold", "price": 2650.50}
            }
        }
    )

    # Event identity
    event_id: UUID = Field(
        default_factory=uuid4,
        description="Unique event identifier"
    )

    event_type: EventType = Field(
        ...,
        description="Type of event being emitted"
    )

    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Event creation timestamp (UTC)"
    )

    # Source information
    source_agent_id: Optional[UUID] = Field(
        None,
        description="ID of agent that emitted this event"
    )

    source_agent_type: Optional[str] = Field(
        None,
        description="Type of agent that emitted this event"
    )

    strategy_team_id: Optional[UUID] = Field(
        None,
        description="Strategy team this event belongs to (NULL for global events)"
    )

    # Event metadata
    priority: EventPriority = Field(
        default=EventPriority.NORMAL,
        description="Event processing priority"
    )

    correlation_id: Optional[UUID] = Field(
        None,
        description="Correlation ID for tracking related events across agents"
    )

    parent_event_id: Optional[UUID] = Field(
        None,
        description="Parent event ID if this is a response/continuation"
    )

    # Payload
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific data payload"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (tags, context, etc.)"
    )

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}(id={self.event_id}, "
            f"type={self.event_type}, source={self.source_agent_type}, "
            f"priority={self.priority})>"
        )


class MarketTickEvent(BaseEvent):
    """Market tick event with price and volume data."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_type": "market_tick",
                "symbol": "Gold",
                "bid": 2650.25,
                "ask": 2650.50,
                "last": 2650.40,
                "volume": 1000
            }
        }
    )

    event_type: EventType = Field(
        default=EventType.MARKET_TICK,
        description="Event type (always market_tick)"
    )

    symbol: str = Field(
        ...,
        description="Trading symbol"
    )

    bid: float = Field(
        ...,
        description="Current bid price"
    )

    ask: float = Field(
        ...,
        description="Current ask price"
    )

    last: Optional[float] = Field(
        None,
        description="Last traded price"
    )

    volume: Optional[int] = Field(
        None,
        description="Tick volume"
    )


class AgentErrorEvent(BaseEvent):
    """Agent error event for exception tracking."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_type": "agent_error",
                "error_type": "ValueError",
                "error_message": "Invalid position size",
                "is_recoverable": True
            }
        }
    )

    event_type: EventType = Field(
        default=EventType.AGENT_ERROR,
        description="Event type (always agent_error)"
    )

    priority: EventPriority = Field(
        default=EventPriority.CRITICAL,
        description="Priority (always critical for errors)"
    )

    error_type: str = Field(
        ...,
        description="Exception type (e.g., 'ValueError', 'ConnectionError')"
    )

    error_message: str = Field(
        ...,
        description="Error message"
    )

    error_traceback: Optional[str] = Field(
        None,
        description="Full error traceback"
    )

    is_recoverable: bool = Field(
        default=True,
        description="Whether the error is recoverable"
    )

    recovery_action: Optional[str] = Field(
        None,
        description="Suggested recovery action"
    )
