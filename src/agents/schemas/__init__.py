"""
Pydantic schemas for agent communication.
All schemas use Pydantic v2 with model_config.
"""
from .decisions import (
    ConfidenceLevel,
    EntryTiming,
    OrderType,
    PositionSize,
    StopLoss,
    TakeProfit,
    TradeDirection,
    TradeIntent,
)
from .events import (
    AgentErrorEvent,
    BaseEvent,
    EventPriority,
    EventType,
    MarketTickEvent,
)
from .reports import (
    DebateOutcome,
    FundamentalReport,
    MarketRegime,
    SentimentPolarity,
    SentimentReport,
    TechnicalReport,
    TrendDirection,
)

__all__ = [
    # Events
    "BaseEvent",
    "EventType",
    "EventPriority",
    "MarketTickEvent",
    "AgentErrorEvent",
    # Decisions
    "TradeDirection",
    "OrderType",
    "ConfidenceLevel",
    "TradeIntent",
    "PositionSize",
    "StopLoss",
    "TakeProfit",
    "EntryTiming",
    # Reports
    "TrendDirection",
    "MarketRegime",
    "SentimentPolarity",
    "TechnicalReport",
    "FundamentalReport",
    "SentimentReport",
    "DebateOutcome",
]
