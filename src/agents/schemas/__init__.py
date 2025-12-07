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

# Phase 6: Adversarial Debate & Safety Gates (NEW - 2025-12-06)
from .debate import (
    ArgumentCase,
    BearCase,
    BullCase,
    DebatePosition,
    DebateOutcome as Phase6DebateOutcome,
    EvidencePoint,
    RiskDebateOutcome,
    RiskPerspective,
    RiskTolerance,
)
from .trade_decision import (
    ConflictResolution,
    TradeDirection as Phase6TradeDirection,
    TradeIntent as Phase6TradeIntent,
)
from .approval import (
    ApprovalDecision,
    FundManagerApproval,
    ModificationType,
    PortfolioLimits,
    RejectionReason,
    TradeModification,
)

__all__ = [
    # Events
    "BaseEvent",
    "EventType",
    "EventPriority",
    "MarketTickEvent",
    "AgentErrorEvent",
    # Decisions (Legacy)
    "TradeDirection",
    "OrderType",
    "ConfidenceLevel",
    "TradeIntent",
    "PositionSize",
    "StopLoss",
    "TakeProfit",
    "EntryTiming",
    # Reports (Legacy)
    "TrendDirection",
    "MarketRegime",
    "SentimentPolarity",
    "TechnicalReport",
    "FundamentalReport",
    "SentimentReport",
    "DebateOutcome",
    # Phase 6: Debate schemas
    "ArgumentCase",
    "BearCase",
    "BullCase",
    "DebatePosition",
    "Phase6DebateOutcome",
    "EvidencePoint",
    "RiskDebateOutcome",
    "RiskPerspective",
    "RiskTolerance",
    # Phase 6: Trade decision schemas
    "ConflictResolution",
    "Phase6TradeDirection",
    "Phase6TradeIntent",
    # Phase 6: Approval schemas
    "ApprovalDecision",
    "FundManagerApproval",
    "ModificationType",
    "PortfolioLimits",
    "RejectionReason",
    "TradeModification",
]
