"""
Agent communication schemas.

Contains Pydantic models for structured inter-agent communication.
"""

from src.agents.schemas.debate import (
    DebatePosition,
    RiskTolerance,
    EvidencePoint,
    ArgumentCase,
    BullCase,
    BearCase,
    DebateOutcome,
    RiskPerspective,
    RiskDebateOutcome,
)

from src.agents.schemas.trade_decision import (
    TradeDirection,
    TradeIntent,
    ConflictResolution,
)

__all__ = [
    # Debate schemas
    "DebatePosition",
    "RiskTolerance",
    "EvidencePoint",
    "ArgumentCase",
    "BullCase",
    "BearCase",
    "DebateOutcome",
    "RiskPerspective",
    "RiskDebateOutcome",
    # Trade decision schemas
    "TradeDirection",
    "TradeIntent",
    "ConflictResolution",
]
