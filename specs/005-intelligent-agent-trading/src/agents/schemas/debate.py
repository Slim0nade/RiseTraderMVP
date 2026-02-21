"""
Debate schemas for adversarial agent analysis.

Contains Pydantic models for:
- Bull/Bear debate outcomes
- Risk tolerance debate outcomes
- Evidence tracking and argument structures
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


class DebatePosition(str, Enum):
    """Position in the debate."""
    BULL = "bull"
    BEAR = "bear"
    NEUTRAL = "neutral"


class RiskTolerance(str, Enum):
    """Risk tolerance position."""
    RISKY = "risky"
    NEUTRAL = "neutral"
    SAFE = "safe"


class EvidencePoint(BaseModel):
    """Single piece of evidence supporting an argument."""

    claim: str = Field(
        ...,
        description="The specific claim being made"
    )

    source: str = Field(
        ...,
        description="Source of evidence (analyst report, indicator, etc.)"
    )

    strength: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Strength of this evidence (0.0-1.0)"
    )

    data_point: Optional[str] = Field(
        None,
        description="Specific data point supporting this claim"
    )


class ArgumentCase(BaseModel):
    """Complete argument case with evidence."""

    position: DebatePosition = Field(
        ...,
        description="Position being argued (BULL or BEAR)"
    )

    thesis: str = Field(
        ...,
        min_length=50,
        description="Core thesis statement (minimum 50 characters)"
    )

    evidence_points: List[EvidencePoint] = Field(
        ...,
        min_length=3,
        description="Supporting evidence (minimum 3 points)"
    )

    counterarguments: List[str] = Field(
        default_factory=list,
        description="Anticipated counterarguments and rebuttals"
    )

    risk_warnings: List[str] = Field(
        default_factory=list,
        description="Risk factors identified from this perspective"
    )

    conviction_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Conviction level in this argument (0.0-1.0)"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in the analysis quality (0.0-1.0)"
    )


class BullCase(ArgumentCase):
    """Bull argument case."""

    position: DebatePosition = Field(
        default=DebatePosition.BULL,
        description="Always BULL for this model"
    )

    key_catalysts: List[str] = Field(
        default_factory=list,
        description="Key bullish catalysts identified"
    )

    price_targets: Dict[str, float] = Field(
        default_factory=dict,
        description="Bullish price targets (e.g., 'p75': 2685.0, 'p90': 2700.0)"
    )


class BearCase(ArgumentCase):
    """Bear argument case."""

    position: DebatePosition = Field(
        default=DebatePosition.BEAR,
        description="Always BEAR for this model"
    )

    key_risks: List[str] = Field(
        default_factory=list,
        description="Key bearish risks identified"
    )

    downside_targets: Dict[str, float] = Field(
        default_factory=dict,
        description="Bearish price targets (e.g., 'p25': 2620.0, 'p10': 2600.0)"
    )


class DebateOutcome(BaseModel):
    """
    Complete debate outcome from Bull/Bear adversarial analysis.

    Contains both perspectives with evidence, enabling the TradeDecisionAgent
    to make an informed decision considering all angles.
    """

    bull_case: BullCase = Field(
        ...,
        description="Complete bull argument with evidence"
    )

    bear_case: BearCase = Field(
        ...,
        description="Complete bear argument with evidence"
    )

    consensus_direction: Optional[str] = Field(
        None,
        description="Consensus direction if one emerges (LONG/SHORT/NEUTRAL/NO_CONSENSUS)"
    )

    key_disagreements: List[str] = Field(
        default_factory=list,
        description="Major points of disagreement between bull and bear"
    )

    consolidated_risks: List[str] = Field(
        default_factory=list,
        description="All risk warnings from both perspectives"
    )

    debate_quality_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall quality of the debate (0.0-1.0)"
    )

    timestamp: str = Field(
        ...,
        description="Timestamp when debate completed (ISO format)"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional debate metadata"
    )


class RiskPerspective(BaseModel):
    """Single perspective on risk tolerance for position sizing."""

    tolerance: RiskTolerance = Field(
        ...,
        description="Risk tolerance position (RISKY/NEUTRAL/SAFE)"
    )

    recommended_size_adjustment: float = Field(
        ...,
        ge=0.0,
        le=2.0,
        description="Recommended adjustment to position size (1.0 = no change, <1.0 = reduce, >1.0 = increase)"
    )

    reasoning: str = Field(
        ...,
        min_length=50,
        description="Reasoning for this position (minimum 50 characters)"
    )

    key_factors: List[str] = Field(
        ...,
        min_length=2,
        description="Key factors supporting this perspective (minimum 2)"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this perspective (0.0-1.0)"
    )


class RiskDebateOutcome(BaseModel):
    """
    Outcome from 3-way risk tolerance debate (Risky/Neutral/Safe).

    Evaluates the proposed position size from three perspectives,
    providing a balanced risk assessment before execution.
    """

    risky_perspective: RiskPerspective = Field(
        ...,
        description="Risky debator's perspective (argues for higher sizing)"
    )

    neutral_perspective: RiskPerspective = Field(
        ...,
        description="Neutral debator's perspective (validates baseline)"
    )

    safe_perspective: RiskPerspective = Field(
        ...,
        description="Safe debator's perspective (identifies reduction factors)"
    )

    consensus_adjustment: float = Field(
        ...,
        ge=0.0,
        le=2.0,
        description="Consensus position size adjustment (1.0 = no change)"
    )

    consensus_reached: bool = Field(
        ...,
        description="Whether all three perspectives agree on direction"
    )

    final_position_size: float = Field(
        ...,
        gt=0.0,
        description="Final recommended position size after debate (lots)"
    )

    final_risk_percentage: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="Final risk as % of capital after adjustments"
    )

    divergence_rationale: Optional[str] = Field(
        None,
        description="Explanation if perspectives diverge significantly"
    )

    key_warnings: List[str] = Field(
        default_factory=list,
        description="Critical warnings from any perspective"
    )

    timestamp: str = Field(
        ...,
        description="Timestamp when debate completed (ISO format)"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional debate metadata"
    )
