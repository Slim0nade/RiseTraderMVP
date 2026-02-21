"""
Approval schemas for the Fund Manager approval gate.

Contains Pydantic models for:
- Final trade approval decisions
- Modification requests
- Rejection rationales
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


class ApprovalDecision(str, Enum):
    """Fund Manager approval decision."""
    APPROVE = "APPROVE"
    MODIFY = "MODIFY"
    REJECT = "REJECT"


class ModificationType(str, Enum):
    """Type of modification requested by fund manager."""
    REDUCE_SIZE = "reduce_size"
    TIGHTEN_STOP = "tighten_stop"
    WIDEN_STOP = "widen_stop"
    ADJUST_TARGET = "adjust_target"
    DELAY_ENTRY = "delay_entry"


class RejectionReason(str, Enum):
    """Reason for trade rejection."""
    EXCESSIVE_RISK = "excessive_risk"
    CORRELATION_LIMIT = "correlation_limit"
    EVENT_RISK = "event_risk"
    PORTFOLIO_CONCENTRATION = "portfolio_concentration"
    POOR_RISK_REWARD = "poor_risk_reward"
    QUALITY_CONCERNS = "quality_concerns"
    DRAWDOWN_PROTECTION = "drawdown_protection"


class TradeModification(BaseModel):
    """Specific modification requested by fund manager."""

    modification_type: ModificationType = Field(
        ...,
        description="Type of modification"
    )

    current_value: float = Field(
        ...,
        description="Current value of the parameter"
    )

    recommended_value: float = Field(
        ...,
        description="Recommended new value"
    )

    rationale: str = Field(
        ...,
        min_length=30,
        description="Why this modification is needed"
    )


class FundManagerApproval(BaseModel):
    """
    Complete approval decision from Fund Manager.

    This is the FINAL gate before trade execution. Fund Manager has
    APPROVE/MODIFY/REJECT powers with hard portfolio-level limits.
    """

    decision: ApprovalDecision = Field(
        ...,
        description="Final decision: APPROVE, MODIFY, or REJECT"
    )

    rationale: str = Field(
        ...,
        min_length=100,
        description="Detailed rationale for the decision (minimum 100 characters)"
    )

    # Approval-specific fields
    approved_position_size: Optional[float] = Field(
        None,
        gt=0.0,
        description="Final approved position size in lots (if APPROVE or MODIFY)"
    )

    approved_risk_percentage: Optional[float] = Field(
        None,
        ge=0.0,
        le=10.0,
        description="Final approved risk as % of capital (if APPROVE or MODIFY)"
    )

    # Modification-specific fields
    modifications: List[TradeModification] = Field(
        default_factory=list,
        description="List of modifications if decision is MODIFY"
    )

    modification_summary: Optional[str] = Field(
        None,
        description="Summary of all modifications requested"
    )

    # Rejection-specific fields
    rejection_reason: Optional[RejectionReason] = Field(
        None,
        description="Primary reason for rejection (if REJECT)"
    )

    rejection_details: List[str] = Field(
        default_factory=list,
        description="Detailed reasons for rejection"
    )

    # Portfolio-level checks
    portfolio_risk_after_trade: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Total portfolio risk percentage if trade is executed"
    )

    correlation_check_passed: bool = Field(
        ...,
        description="Whether correlation limits are respected"
    )

    correlated_positions_count: int = Field(
        ...,
        ge=0,
        description="Number of existing correlated positions"
    )

    max_correlated_positions: int = Field(
        default=3,
        description="Maximum allowed correlated positions"
    )

    event_risk_present: bool = Field(
        ...,
        description="Whether high-impact events are imminent"
    )

    event_risk_description: Optional[str] = Field(
        None,
        description="Description of event risk if present"
    )

    # Hard limits enforcement
    hard_limits_passed: bool = Field(
        ...,
        description="Whether all hard portfolio limits are respected"
    )

    violated_limits: List[str] = Field(
        default_factory=list,
        description="List of any violated hard limits"
    )

    # Quality assessment
    trade_quality_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall trade quality assessment (0.0-1.0)"
    )

    quality_concerns: List[str] = Field(
        default_factory=list,
        description="Any quality concerns identified"
    )

    # Confidence and timing
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this approval decision (0.0-1.0)"
    )

    recommended_action_timing: str = Field(
        ...,
        description="When to act: 'immediate', 'wait_for_pullback', 'after_event', 'do_not_trade'"
    )

    # Metadata
    timestamp: str = Field(
        ...,
        description="Timestamp when approval decision was made (ISO format)"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional approval metadata"
    )


class PortfolioLimits(BaseModel):
    """
    Hard portfolio limits enforced by Fund Manager.
    
    These are non-negotiable constraints that protect capital.
    """

    max_account_risk_percent: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Maximum risk per trade as % of account (typically 5%)"
    )

    max_portfolio_risk_percent: float = Field(
        default=15.0,
        ge=0.0,
        le=50.0,
        description="Maximum total portfolio risk as % of capital"
    )

    max_correlated_positions: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum number of highly correlated positions"
    )

    correlation_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Correlation coefficient threshold for position grouping"
    )

    event_risk_veto_hours: int = Field(
        default=24,
        ge=0,
        le=72,
        description="Hours before major event to veto new trades"
    )

    max_position_size_percent: float = Field(
        default=10.0,
        ge=0.0,
        le=50.0,
        description="Maximum single position as % of portfolio"
    )

    min_trade_quality_score: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Minimum quality score to approve trade"
    )
