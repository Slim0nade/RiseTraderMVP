"""
Trade decision schemas for the TradeDecisionAgent.

Contains Pydantic models for:
- Trade direction and intent
- Conflict resolution between bull/bear cases
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


class TradeDirection(str, Enum):
    """Trade direction decision."""
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


class TradeIntent(BaseModel):
    """
    Trade decision output from TradeDecisionAgent.

    Represents the final go/no-go decision after evaluating
    the bull/bear debate outcome.
    """

    direction: TradeDirection = Field(
        ...,
        description="Final trade direction (LONG/SHORT/NO_TRADE)"
    )

    conviction: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Conviction level in this trade (0.0-1.0)"
    )

    rationale: str = Field(
        ...,
        min_length=100,
        description="Detailed rationale for the decision (minimum 100 characters)"
    )

    key_factors: List[str] = Field(
        ...,
        min_length=3,
        description="Key factors influencing the decision (minimum 3)"
    )

    risk_assessment: str = Field(
        ...,
        min_length=50,
        description="Risk assessment summary (minimum 50 characters)"
    )

    conflict_resolution: Optional[str] = Field(
        None,
        description="How conflicts between bull/bear cases were resolved"
    )

    expected_holding_period: Optional[str] = Field(
        None,
        description="Expected holding period (e.g., 'intraday', '1-3 days', '1-2 weeks')"
    )

    timestamp: str = Field(
        ...,
        description="Timestamp when decision was made (ISO format)"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional decision metadata"
    )


class ConflictResolution(str, Enum):
    """Method used to resolve bull/bear conflicts."""
    BULL_STRONGER = "bull_stronger"  # Bull case had higher conviction
    BEAR_STRONGER = "bear_stronger"  # Bear case had higher conviction
    EVIDENCE_QUALITY = "evidence_quality"  # One side had better evidence
    RISK_ADJUSTED = "risk_adjusted"  # Risk/reward ratio favored one side
    NO_CONSENSUS = "no_consensus"  # Could not resolve, resulted in NO_TRADE
