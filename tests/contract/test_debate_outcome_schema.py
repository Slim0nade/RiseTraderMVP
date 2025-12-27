"""
Contract Tests: DebateOutcome Schema Validation (T101).

These tests verify that the Pydantic schemas for debate outcomes
enforce all required validation rules and constraints. Contract tests
protect against schema regressions that could allow invalid data.

Schema Coverage:
- EvidencePoint: Evidence validation with strength bounds
- ArgumentCase: Base argument structure with minimum evidence requirements
- BullCase: Bull-specific argument with catalysts and price targets
- BearCase: Bear-specific argument with risks and downside targets
- DebateOutcome: Complete bull/bear debate outcome
- RiskPerspective: Single risk tolerance perspective
- RiskDebateOutcome: 3-way risk debate outcome

Test Categories:
1. Valid Input Tests: Ensure valid data passes validation
2. Invalid Input Tests: Ensure invalid data is rejected with clear errors
3. Constraint Tests: Verify numeric bounds, string lengths, list minimums
4. Type Safety Tests: Ensure type coercion and validation work correctly
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from src.agents.schemas.debate import (
    EvidencePoint,
    ArgumentCase,
    BullCase,
    BearCase,
    DebateOutcome,
    RiskPerspective,
    RiskDebateOutcome,
    DebatePosition,
    RiskTolerance
)


# ============================================================================
# EvidencePoint Contract Tests
# ============================================================================

class TestEvidencePointContract:
    """Contract tests for EvidencePoint schema."""

    def test_valid_evidence_point(self):
        """Test valid evidence point creation."""
        evidence = EvidencePoint(
            claim="RSI shows bullish divergence",
            source="Technical Analyst",
            strength=0.75,
            data_point="RSI: 35.2 (oversold)"
        )

        assert evidence.claim == "RSI shows bullish divergence"
        assert evidence.source == "Technical Analyst"
        assert evidence.strength == 0.75
        assert evidence.data_point == "RSI: 35.2 (oversold)"

    def test_evidence_point_without_optional_data_point(self):
        """Test evidence point creation without optional data_point."""
        evidence = EvidencePoint(
            claim="Strong demand outlook",
            source="Fundamental Analyst",
            strength=0.85
        )

        assert evidence.data_point is None

    def test_evidence_strength_bounds_min(self):
        """Test strength cannot be below 0.0."""
        with pytest.raises(ValidationError) as exc_info:
            EvidencePoint(
                claim="Some claim",
                source="Some source",
                strength=-0.1
            )

        assert "greater than or equal to 0" in str(exc_info.value)

    def test_evidence_strength_bounds_max(self):
        """Test strength cannot exceed 1.0."""
        with pytest.raises(ValidationError) as exc_info:
            EvidencePoint(
                claim="Some claim",
                source="Some source",
                strength=1.5
            )

        assert "less than or equal to 1" in str(exc_info.value)

    def test_evidence_required_fields(self):
        """Test all required fields must be provided."""
        with pytest.raises(ValidationError) as exc_info:
            EvidencePoint(
                claim="Some claim"
                # Missing source and strength
            )

        errors = str(exc_info.value)
        assert "source" in errors
        assert "strength" in errors


# ============================================================================
# ArgumentCase Contract Tests
# ============================================================================

class TestArgumentCaseContract:
    """Contract tests for ArgumentCase schema."""

    def test_valid_argument_case(self):
        """Test valid argument case creation."""
        arg_case = ArgumentCase(
            position=DebatePosition.BULL,
            thesis="Strong technical breakout above resistance with high volume confirmation",
            evidence_points=[
                EvidencePoint(claim="Breakout above $75", source="Technical", strength=0.8),
                EvidencePoint(claim="Volume 2x average", source="Technical", strength=0.7),
                EvidencePoint(claim="MACD bullish cross", source="Technical", strength=0.6)
            ],
            counterarguments=["Potential false breakout", "Overbought RSI"],
            risk_warnings=["High volatility risk", "News event pending"],
            conviction_score=0.75,
            confidence=0.80
        )

        assert arg_case.position == DebatePosition.BULL
        assert len(arg_case.evidence_points) >= 3
        assert len(arg_case.counterarguments) == 2
        assert len(arg_case.risk_warnings) == 2

    def test_thesis_minimum_length(self):
        """Test thesis must be at least 50 characters."""
        with pytest.raises(ValidationError) as exc_info:
            ArgumentCase(
                position=DebatePosition.BULL,
                thesis="Too short",  # Only 9 characters
                evidence_points=[
                    EvidencePoint(claim="Claim 1", source="Source", strength=0.5),
                    EvidencePoint(claim="Claim 2", source="Source", strength=0.5),
                    EvidencePoint(claim="Claim 3", source="Source", strength=0.5)
                ],
                conviction_score=0.5,
                confidence=0.5
            )

        assert "at least 50 characters" in str(exc_info.value)

    def test_minimum_evidence_points(self):
        """Test minimum 3 evidence points required."""
        with pytest.raises(ValidationError) as exc_info:
            ArgumentCase(
                position=DebatePosition.BULL,
                thesis="This thesis is long enough to meet the minimum fifty character requirement",
                evidence_points=[
                    EvidencePoint(claim="Only one", source="Source", strength=0.5)
                ],  # Only 1 evidence point
                conviction_score=0.5,
                confidence=0.5
            )

        assert "at least 3 items" in str(exc_info.value)

    def test_conviction_score_bounds(self):
        """Test conviction_score must be between 0.0 and 1.0."""
        # Test below 0.0
        with pytest.raises(ValidationError):
            ArgumentCase(
                position=DebatePosition.BULL,
                thesis="This thesis is long enough to meet the minimum fifty character requirement",
                evidence_points=[
                    EvidencePoint(claim="E1", source="S", strength=0.5),
                    EvidencePoint(claim="E2", source="S", strength=0.5),
                    EvidencePoint(claim="E3", source="S", strength=0.5)
                ],
                conviction_score=-0.1,
                confidence=0.5
            )

        # Test above 1.0
        with pytest.raises(ValidationError):
            ArgumentCase(
                position=DebatePosition.BULL,
                thesis="This thesis is long enough to meet the minimum fifty character requirement",
                evidence_points=[
                    EvidencePoint(claim="E1", source="S", strength=0.5),
                    EvidencePoint(claim="E2", source="S", strength=0.5),
                    EvidencePoint(claim="E3", source="S", strength=0.5)
                ],
                conviction_score=1.5,
                confidence=0.5
            )


# ============================================================================
# BullCase Contract Tests
# ============================================================================

class TestBullCaseContract:
    """Contract tests for BullCase schema."""

    def test_valid_bull_case(self):
        """Test valid bull case creation."""
        bull_case = BullCase(
            thesis="Strong bullish breakout with multiple technical confirmations and fundamental support",
            evidence_points=[
                EvidencePoint(claim="Price above 200 MA", source="Technical", strength=0.8),
                EvidencePoint(claim="RSI trending up", source="Technical", strength=0.7),
                EvidencePoint(claim="Strong earnings", source="Fundamental", strength=0.75)
            ],
            key_catalysts=["OPEC+ production cuts", "Rising demand"],
            price_targets={"p75": 78.00, "p90": 80.00},
            conviction_score=0.80,
            confidence=0.75
        )

        assert bull_case.position == DebatePosition.BULL
        assert len(bull_case.key_catalysts) == 2
        assert "p75" in bull_case.price_targets
        assert "p90" in bull_case.price_targets

    def test_bull_case_position_always_bull(self):
        """Test BullCase position is always BULL."""
        bull_case = BullCase(
            thesis="This thesis is long enough to meet the minimum fifty character requirement",
            evidence_points=[
                EvidencePoint(claim="E1", source="S", strength=0.5),
                EvidencePoint(claim="E2", source="S", strength=0.5),
                EvidencePoint(claim="E3", source="S", strength=0.5)
            ],
            conviction_score=0.5,
            confidence=0.5
        )

        assert bull_case.position == DebatePosition.BULL


# ============================================================================
# BearCase Contract Tests
# ============================================================================

class TestBearCaseContract:
    """Contract tests for BearCase schema."""

    def test_valid_bear_case(self):
        """Test valid bear case creation."""
        bear_case = BearCase(
            thesis="Bearish reversal pattern forming with weakening fundamentals and negative sentiment",
            evidence_points=[
                EvidencePoint(claim="Head and shoulders pattern", source="Technical", strength=0.75),
                EvidencePoint(claim="Declining volume", source="Technical", strength=0.65),
                EvidencePoint(claim="Oversupply concerns", source="Fundamental", strength=0.80)
            ],
            key_risks=["Recession fears", "Oversupply"],
            downside_targets={"p25": 72.00, "p10": 70.00},
            conviction_score=0.70,
            confidence=0.75
        )

        assert bear_case.position == DebatePosition.BEAR
        assert len(bear_case.key_risks) == 2
        assert "p25" in bear_case.downside_targets
        assert "p10" in bear_case.downside_targets

    def test_bear_case_position_always_bear(self):
        """Test BearCase position is always BEAR."""
        bear_case = BearCase(
            thesis="This thesis is long enough to meet the minimum fifty character requirement",
            evidence_points=[
                EvidencePoint(claim="E1", source="S", strength=0.5),
                EvidencePoint(claim="E2", source="S", strength=0.5),
                EvidencePoint(claim="E3", source="S", strength=0.5)
            ],
            conviction_score=0.5,
            confidence=0.5
        )

        assert bear_case.position == DebatePosition.BEAR


# ============================================================================
# DebateOutcome Contract Tests
# ============================================================================

class TestDebateOutcomeContract:
    """Contract tests for DebateOutcome schema."""

    def test_valid_debate_outcome(self):
        """Test valid debate outcome creation."""
        bull_case = BullCase(
            thesis="Strong bullish case with technical and fundamental support for continuation",
            evidence_points=[
                EvidencePoint(claim="Bullish E1", source="Technical", strength=0.8),
                EvidencePoint(claim="Bullish E2", source="Fundamental", strength=0.75),
                EvidencePoint(claim="Bullish E3", source="Sentiment", strength=0.7)
            ],
            key_catalysts=["Catalyst 1", "Catalyst 2"],
            conviction_score=0.80,
            confidence=0.75
        )

        bear_case = BearCase(
            thesis="Bearish case identifying significant downside risks and potential reversal patterns",
            evidence_points=[
                EvidencePoint(claim="Bearish E1", source="Technical", strength=0.6),
                EvidencePoint(claim="Bearish E2", source="Fundamental", strength=0.65),
                EvidencePoint(claim="Bearish E3", source="Sentiment", strength=0.55)
            ],
            key_risks=["Risk 1", "Risk 2"],
            conviction_score=0.60,
            confidence=0.70
        )

        debate_outcome = DebateOutcome(
            bull_case=bull_case,
            bear_case=bear_case,
            consensus_direction="LONG",
            key_disagreements=["Direction disagreement", "Target disagreement"],
            consolidated_risks=["Risk 1", "Risk 2", "Risk 3"],
            debate_quality_score=0.75,
            timestamp=datetime.utcnow().isoformat(),
            metadata={"symbol": "CrudeOIL", "duration_ms": 1500}
        )

        assert debate_outcome.bull_case.position == DebatePosition.BULL
        assert debate_outcome.bear_case.position == DebatePosition.BEAR
        assert debate_outcome.consensus_direction == "LONG"
        assert len(debate_outcome.key_disagreements) == 2
        assert len(debate_outcome.consolidated_risks) == 3
        assert 0.0 <= debate_outcome.debate_quality_score <= 1.0

    def test_debate_outcome_required_fields(self):
        """Test all required fields must be provided."""
        with pytest.raises(ValidationError) as exc_info:
            DebateOutcome(
                # Missing bull_case and bear_case
                debate_quality_score=0.5,
                timestamp=datetime.utcnow().isoformat()
            )

        errors = str(exc_info.value)
        assert "bull_case" in errors
        assert "bear_case" in errors

    def test_debate_quality_score_bounds(self):
        """Test debate_quality_score must be between 0.0 and 1.0."""
        bull_case = BullCase(
            thesis="This thesis is long enough to meet the minimum fifty character requirement",
            evidence_points=[
                EvidencePoint(claim="E1", source="S", strength=0.5),
                EvidencePoint(claim="E2", source="S", strength=0.5),
                EvidencePoint(claim="E3", source="S", strength=0.5)
            ],
            conviction_score=0.5,
            confidence=0.5
        )

        bear_case = BearCase(
            thesis="This thesis is long enough to meet the minimum fifty character requirement",
            evidence_points=[
                EvidencePoint(claim="E1", source="S", strength=0.5),
                EvidencePoint(claim="E2", source="S", strength=0.5),
                EvidencePoint(claim="E3", source="S", strength=0.5)
            ],
            conviction_score=0.5,
            confidence=0.5
        )

        # Test below 0.0
        with pytest.raises(ValidationError):
            DebateOutcome(
                bull_case=bull_case,
                bear_case=bear_case,
                debate_quality_score=-0.1,
                timestamp=datetime.utcnow().isoformat()
            )

        # Test above 1.0
        with pytest.raises(ValidationError):
            DebateOutcome(
                bull_case=bull_case,
                bear_case=bear_case,
                debate_quality_score=1.5,
                timestamp=datetime.utcnow().isoformat()
            )


# ============================================================================
# RiskPerspective Contract Tests
# ============================================================================

class TestRiskPerspectiveContract:
    """Contract tests for RiskPerspective schema."""

    def test_valid_risk_perspective(self):
        """Test valid risk perspective creation."""
        perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=0.7,
            reasoning="Current market volatility and existing drawdown warrant reduced position sizing for capital preservation",
            key_factors=["High volatility", "12% drawdown"],
            confidence=0.80
        )

        assert perspective.tolerance == RiskTolerance.SAFE
        assert perspective.recommended_size_adjustment == 0.7
        assert len(perspective.key_factors) >= 2

    def test_reasoning_minimum_length(self):
        """Test reasoning must be at least 50 characters."""
        with pytest.raises(ValidationError) as exc_info:
            RiskPerspective(
                tolerance=RiskTolerance.NEUTRAL,
                recommended_size_adjustment=1.0,
                reasoning="Too short",  # Only 9 characters
                key_factors=["Factor 1", "Factor 2"],
                confidence=0.5
            )

        assert "at least 50 characters" in str(exc_info.value)

    def test_minimum_key_factors(self):
        """Test minimum 2 key factors required."""
        with pytest.raises(ValidationError) as exc_info:
            RiskPerspective(
                tolerance=RiskTolerance.NEUTRAL,
                recommended_size_adjustment=1.0,
                reasoning="This reasoning is long enough to meet the minimum fifty character length requirement",
                key_factors=["Only one factor"],  # Only 1 factor
                confidence=0.5
            )

        assert "at least 2 items" in str(exc_info.value)

    def test_size_adjustment_bounds(self):
        """Test recommended_size_adjustment must be between 0.0 and 2.0."""
        # Test below 0.0
        with pytest.raises(ValidationError):
            RiskPerspective(
                tolerance=RiskTolerance.SAFE,
                recommended_size_adjustment=-0.1,
                reasoning="This reasoning is long enough to meet the minimum fifty character length requirement",
                key_factors=["Factor 1", "Factor 2"],
                confidence=0.5
            )

        # Test above 2.0
        with pytest.raises(ValidationError):
            RiskPerspective(
                tolerance=RiskTolerance.RISKY,
                recommended_size_adjustment=2.5,
                reasoning="This reasoning is long enough to meet the minimum fifty character length requirement",
                key_factors=["Factor 1", "Factor 2"],
                confidence=0.5
            )


# ============================================================================
# RiskDebateOutcome Contract Tests
# ============================================================================

class TestRiskDebateOutcomeContract:
    """Contract tests for RiskDebateOutcome schema."""

    def test_valid_risk_debate_outcome(self):
        """Test valid risk debate outcome creation."""
        risky_perspective = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.3,
            reasoning="Strong edge with favorable conditions supports increased position sizing for maximum returns",
            key_factors=["High conviction", "Low volatility"],
            confidence=0.75
        )

        neutral_perspective = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=1.0,
            reasoning="Kelly calculation appears reasonable given current market conditions and edge parameters",
            key_factors=["Baseline validated", "Normal conditions"],
            confidence=0.80
        )

        safe_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=0.8,
            reasoning="Existing drawdown and correlation with open positions warrant slight reduction in sizing",
            key_factors=["Moderate drawdown", "2 correlated positions"],
            confidence=0.70
        )

        outcome = RiskDebateOutcome(
            risky_perspective=risky_perspective,
            neutral_perspective=neutral_perspective,
            safe_perspective=safe_perspective,
            consensus_adjustment=1.0,
            consensus_reached=True,
            final_position_size=2.0,
            final_risk_percentage=2.0,
            divergence_rationale=None,
            key_warnings=[],
            timestamp=datetime.utcnow().isoformat(),
            metadata={"symbol": "CrudeOIL", "baseline_lots": 2.0}
        )

        assert outcome.risky_perspective.tolerance == RiskTolerance.RISKY
        assert outcome.neutral_perspective.tolerance == RiskTolerance.NEUTRAL
        assert outcome.safe_perspective.tolerance == RiskTolerance.SAFE
        assert outcome.consensus_reached is True
        assert outcome.final_position_size > 0.0
        assert 0.0 <= outcome.final_risk_percentage <= 10.0

    def test_final_position_size_must_be_positive(self):
        """Test final_position_size must be greater than 0.0."""
        risky = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.0,
            reasoning="This reasoning is long enough to meet the minimum fifty character length requirement",
            key_factors=["F1", "F2"],
            confidence=0.5
        )

        neutral = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=1.0,
            reasoning="This reasoning is long enough to meet the minimum fifty character length requirement",
            key_factors=["F1", "F2"],
            confidence=0.5
        )

        safe = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=1.0,
            reasoning="This reasoning is long enough to meet the minimum fifty character length requirement",
            key_factors=["F1", "F2"],
            confidence=0.5
        )

        with pytest.raises(ValidationError) as exc_info:
            RiskDebateOutcome(
                risky_perspective=risky,
                neutral_perspective=neutral,
                safe_perspective=safe,
                consensus_adjustment=1.0,
                consensus_reached=True,
                final_position_size=0.0,  # Invalid: must be > 0.0
                final_risk_percentage=2.0,
                timestamp=datetime.utcnow().isoformat()
            )

        assert "greater than 0" in str(exc_info.value)

    def test_final_risk_percentage_bounds(self):
        """Test final_risk_percentage must be between 0.0 and 10.0."""
        risky = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.0,
            reasoning="This reasoning is long enough to meet the minimum fifty character length requirement",
            key_factors=["F1", "F2"],
            confidence=0.5
        )

        neutral = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=1.0,
            reasoning="This reasoning is long enough to meet the minimum fifty character length requirement",
            key_factors=["F1", "F2"],
            confidence=0.5
        )

        safe = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=1.0,
            reasoning="This reasoning is long enough to meet the minimum fifty character length requirement",
            key_factors=["F1", "F2"],
            confidence=0.5
        )

        # Test above 10.0
        with pytest.raises(ValidationError):
            RiskDebateOutcome(
                risky_perspective=risky,
                neutral_perspective=neutral,
                safe_perspective=safe,
                consensus_adjustment=1.0,
                consensus_reached=True,
                final_position_size=2.0,
                final_risk_percentage=15.0,  # Invalid: > 10.0
                timestamp=datetime.utcnow().isoformat()
            )

    def test_consensus_adjustment_bounds(self):
        """Test consensus_adjustment must be between 0.0 and 2.0."""
        risky = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.0,
            reasoning="This reasoning is long enough to meet the minimum fifty character length requirement",
            key_factors=["F1", "F2"],
            confidence=0.5
        )

        neutral = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=1.0,
            reasoning="This reasoning is long enough to meet the minimum fifty character length requirement",
            key_factors=["F1", "F2"],
            confidence=0.5
        )

        safe = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=1.0,
            reasoning="This reasoning is long enough to meet the minimum fifty character length requirement",
            key_factors=["F1", "F2"],
            confidence=0.5
        )

        # Test below 0.0
        with pytest.raises(ValidationError):
            RiskDebateOutcome(
                risky_perspective=risky,
                neutral_perspective=neutral,
                safe_perspective=safe,
                consensus_adjustment=-0.1,  # Invalid: < 0.0
                consensus_reached=True,
                final_position_size=2.0,
                final_risk_percentage=2.0,
                timestamp=datetime.utcnow().isoformat()
            )

        # Test above 2.0
        with pytest.raises(ValidationError):
            RiskDebateOutcome(
                risky_perspective=risky,
                neutral_perspective=neutral,
                safe_perspective=safe,
                consensus_adjustment=2.5,  # Invalid: > 2.0
                consensus_reached=True,
                final_position_size=2.0,
                final_risk_percentage=2.0,
                timestamp=datetime.utcnow().isoformat()
            )
