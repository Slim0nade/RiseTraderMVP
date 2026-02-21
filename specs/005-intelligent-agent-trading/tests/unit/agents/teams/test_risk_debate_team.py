"""
Unit tests for RiskDebateTeam.

Tests the 3-way risk tolerance debate orchestration and consensus synthesis.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from src.agents.teams.risk_debate_team import RiskDebateTeam
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier
from src.agents.schemas.debate import RiskPerspective, RiskTolerance, RiskDebateOutcome


@pytest.fixture
def risky_config():
    """Risky debator config."""
    return AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.DEBATE,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="qwen2.5:14b-instruct",
        temperature=0.3
    )


@pytest.fixture
def neutral_config():
    """Neutral debator config."""
    return AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.DEBATE,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="qwen2.5:14b-instruct",
        temperature=0.3
    )


@pytest.fixture
def safe_config():
    """Safe debator config."""
    return AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.DEBATE,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="qwen2.5:14b-instruct",
        temperature=0.3
    )


@pytest.fixture
def debate_team(risky_config, neutral_config, safe_config):
    """Create RiskDebateTeam instance."""
    return RiskDebateTeam(
        risky_config=risky_config,
        neutral_config=neutral_config,
        safe_config=safe_config
    )


@pytest.fixture
def trade_intent():
    """Trade intent fixture."""
    return {
        "direction": "LONG",
        "conviction": 0.70,
        "rationale": "Strong technical setup",
        "key_factors": ["Trend confirmation", "Volume support"],
        "risk_factors": []
    }


@pytest.fixture
def position_size_decision():
    """Position size decision fixture."""
    return {
        "position_size_lots": 1.5,
        "risk_percentage": 2.0,
        "kelly_fraction": 0.25,
        "win_rate": 0.55,
        "avg_win_loss_ratio": 2.5,
        "confidence": 0.75
    }


@pytest.fixture
def stop_loss_decision():
    """Stop loss decision fixture."""
    return {
        "stop_loss_price": 99.50,
        "distance_pips": 50,
        "confidence": 0.80
    }


class TestRiskDebateTeamInitialization:
    """Test RiskDebateTeam initialization."""

    def test_initialization_success(self, debate_team):
        """Test successful team initialization."""
        assert debate_team.risky_debator is not None
        assert debate_team.neutral_debator is not None
        assert debate_team.safe_debator is not None

    def test_initialization_creates_debator_agents(self, debate_team):
        """Test that initialization creates all three debator agents."""
        assert hasattr(debate_team.risky_debator, 'agent_id')
        assert hasattr(debate_team.neutral_debator, 'agent_id')
        assert hasattr(debate_team.safe_debator, 'agent_id')


class TestRiskDebateTeamRunDebate:
    """Test RiskDebateTeam run_debate method."""

    @pytest.mark.asyncio
    async def test_run_debate_with_consensus(
        self,
        debate_team,
        trade_intent,
        position_size_decision,
        stop_loss_decision
    ):
        """Test debate when all three perspectives reach consensus."""
        # Mock perspectives in agreement (within 20%)
        risky_perspective = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.1,
            reasoning="Good setup, slight increase warranted",
            key_factors=["High conviction", "Good R:R"],
            confidence=0.75
        )
        neutral_perspective = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=1.0,
            reasoning="Baseline is sound",
            key_factors=["Valid Kelly inputs"],
            confidence=0.80
        )
        safe_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=0.95,
            reasoning="Minor concerns but acceptable",
            key_factors=["Some risk factors present"],
            confidence=0.70
        )

        with patch.object(debate_team.risky_debator, 'run', return_value=risky_perspective):
            with patch.object(debate_team.neutral_debator, 'run', return_value=neutral_perspective):
                with patch.object(debate_team.safe_debator, 'run', return_value=safe_perspective):
                    result = await debate_team.run_debate(
                        trade_intent=trade_intent,
                        position_size_decision=position_size_decision,
                        stop_loss_decision=stop_loss_decision,
                        account_balance=100000.0,
                        symbol="EURUSD"
                    )

        # Verify result
        assert isinstance(result, RiskDebateOutcome)
        assert result.consensus_reached is True  # Within 20%
        assert result.final_position_size > 0.0
        assert 0.95 <= result.consensus_adjustment <= 1.1  # Simple average
        assert result.risky_perspective == risky_perspective
        assert result.neutral_perspective == neutral_perspective
        assert result.safe_perspective == safe_perspective

    @pytest.mark.asyncio
    async def test_run_debate_with_divergence(
        self,
        debate_team,
        trade_intent,
        position_size_decision,
        stop_loss_decision
    ):
        """Test debate when perspectives diverge significantly."""
        # Mock divergent perspectives (>20% spread)
        risky_perspective = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.5,  # Want to increase 50%
            reasoning="Excellent setup",
            key_factors=["Very high conviction"],
            confidence=0.80
        )
        neutral_perspective = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=1.0,
            reasoning="Baseline is acceptable",
            key_factors=["Valid inputs"],
            confidence=0.75
        )
        safe_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=0.5,  # Want to cut 50%
            reasoning="Significant risks present",
            key_factors=["Event risk", "High volatility"],
            confidence=0.85
        )

        with patch.object(debate_team.risky_debator, 'run', return_value=risky_perspective):
            with patch.object(debate_team.neutral_debator, 'run', return_value=neutral_perspective):
                with patch.object(debate_team.safe_debator, 'run', return_value=safe_perspective):
                    result = await debate_team.run_debate(
                        trade_intent=trade_intent,
                        position_size_decision=position_size_decision,
                        stop_loss_decision=stop_loss_decision,
                        account_balance=100000.0,
                        symbol="EURUSD"
                    )

        # Verify result
        assert result.consensus_reached is False  # >20% spread
        # Should use safety-weighted consensus: 50% safe, 30% neutral, 20% risky
        expected_consensus = (0.5 * 0.5) + (1.0 * 0.3) + (1.5 * 0.2)
        assert abs(result.consensus_adjustment - expected_consensus) < 0.01
        assert result.divergence_rationale is not None
        assert "divergence" in result.divergence_rationale.lower()

    @pytest.mark.asyncio
    async def test_run_debate_calculates_final_sizes(
        self,
        debate_team,
        trade_intent,
        position_size_decision,
        stop_loss_decision
    ):
        """Test that final sizes are calculated correctly."""
        baseline_size = position_size_decision["position_size_lots"]
        baseline_risk = position_size_decision["risk_percentage"]

        # Mock consensus perspectives
        risky_perspective = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.0,
            reasoning="Baseline acceptable",
            key_factors=["Valid"],
            confidence=0.75
        )
        neutral_perspective = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=1.0,
            reasoning="Baseline acceptable",
            key_factors=["Valid"],
            confidence=0.75
        )
        safe_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=1.0,
            reasoning="Baseline acceptable",
            key_factors=["Valid"],
            confidence=0.75
        )

        with patch.object(debate_team.risky_debator, 'run', return_value=risky_perspective):
            with patch.object(debate_team.neutral_debator, 'run', return_value=neutral_perspective):
                with patch.object(debate_team.safe_debator, 'run', return_value=safe_perspective):
                    result = await debate_team.run_debate(
                        trade_intent=trade_intent,
                        position_size_decision=position_size_decision,
                        stop_loss_decision=stop_loss_decision,
                        account_balance=100000.0,
                        symbol="EURUSD"
                    )

        # Final sizes should equal baseline (1.0x adjustment)
        assert result.final_position_size == baseline_size
        assert result.final_risk_percentage == baseline_risk

    @pytest.mark.asyncio
    async def test_run_debate_consolidates_warnings(
        self,
        debate_team,
        trade_intent,
        position_size_decision,
        stop_loss_decision
    ):
        """Test that key warnings are consolidated from safe perspective."""
        risky_perspective = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.2,
            reasoning="Looks good",
            key_factors=["Strong setup"],
            confidence=0.60  # Low confidence - won't trigger warning
        )
        neutral_perspective = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=1.0,
            reasoning="Baseline OK",
            key_factors=["Valid"],
            confidence=0.75
        )
        safe_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=0.7,
            reasoning="Risk factors present",
            key_factors=["Event risk within 24h", "High volatility"],
            confidence=0.85  # High confidence - should add warnings
        )

        with patch.object(debate_team.risky_debator, 'run', return_value=risky_perspective):
            with patch.object(debate_team.neutral_debator, 'run', return_value=neutral_perspective):
                with patch.object(debate_team.safe_debator, 'run', return_value=safe_perspective):
                    result = await debate_team.run_debate(
                        trade_intent=trade_intent,
                        position_size_decision=position_size_decision,
                        stop_loss_decision=stop_loss_decision,
                        account_balance=100000.0,
                        symbol="EURUSD"
                    )

        # Should include safe perspective warnings
        assert len(result.key_warnings) > 0
        assert any("Event risk" in w or "volatility" in w for w in result.key_warnings)

    @pytest.mark.asyncio
    async def test_run_debate_exception_in_debator(
        self,
        debate_team,
        trade_intent,
        position_size_decision,
        stop_loss_decision
    ):
        """Test exception handling when debator fails."""
        with patch.object(debate_team.risky_debator, 'run', side_effect=Exception("LLM error")):
            with pytest.raises(Exception, match="LLM error"):
                await debate_team.run_debate(
                    trade_intent=trade_intent,
                    position_size_decision=position_size_decision,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD"
                )


class TestRiskDebateTeamSynthesizeOutcome:
    """Test consensus synthesis logic."""

    def test_synthesize_with_strong_consensus(self, debate_team):
        """Test synthesis when all perspectives agree."""
        risky = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.0,
            reasoning="OK",
            key_factors=["Valid"],
            confidence=0.75
        )
        neutral = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=1.0,
            reasoning="OK",
            key_factors=["Valid"],
            confidence=0.80
        )
        safe = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=1.0,
            reasoning="OK",
            key_factors=["Valid"],
            confidence=0.70
        )

        result = debate_team._synthesize_outcome(
            risky_perspective=risky,
            neutral_perspective=neutral,
            safe_perspective=safe,
            baseline_size=1.5,
            baseline_risk_pct=2.0,
            account_balance=100000.0,
            symbol="EURUSD",
            start_time=datetime.utcnow()
        )

        assert result.consensus_reached is True
        assert result.consensus_adjustment == 1.0  # Simple average
        assert result.final_position_size == 1.5
        assert result.final_risk_percentage == 2.0

    def test_synthesize_with_divergence(self, debate_team):
        """Test safety-weighted synthesis when perspectives diverge."""
        risky = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.8,
            reasoning="Increase size",
            key_factors=["High conviction"],
            confidence=0.75
        )
        neutral = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=1.0,
            reasoning="Baseline OK",
            key_factors=["Valid"],
            confidence=0.80
        )
        safe = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=0.4,
            reasoning="High risk",
            key_factors=["Event risk"],
            confidence=0.85
        )

        result = debate_team._synthesize_outcome(
            risky_perspective=risky,
            neutral_perspective=neutral,
            safe_perspective=safe,
            baseline_size=1.5,
            baseline_risk_pct=2.0,
            account_balance=100000.0,
            symbol="EURUSD",
            start_time=datetime.utcnow()
        )

        assert result.consensus_reached is False  # >20% spread
        # Expected: (0.4 * 0.5) + (1.0 * 0.3) + (1.8 * 0.2) = 0.2 + 0.3 + 0.36 = 0.86
        expected_adjustment = (0.4 * 0.5) + (1.0 * 0.3) + (1.8 * 0.2)
        assert abs(result.consensus_adjustment - expected_adjustment) < 0.01
        assert result.divergence_rationale is not None

    def test_synthesize_metadata_populated(self, debate_team):
        """Test that metadata is properly populated."""
        risky = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.0,
            reasoning="OK",
            key_factors=["Valid"],
            confidence=0.75
        )
        neutral = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=1.0,
            reasoning="OK",
            key_factors=["Valid"],
            confidence=0.80
        )
        safe = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=1.0,
            reasoning="OK",
            key_factors=["Valid"],
            confidence=0.70
        )

        result = debate_team._synthesize_outcome(
            risky_perspective=risky,
            neutral_perspective=neutral,
            safe_perspective=safe,
            baseline_size=1.5,
            baseline_risk_pct=2.0,
            account_balance=100000.0,
            symbol="EURUSD",
            start_time=datetime.utcnow()
        )

        assert "symbol" in result.metadata
        assert result.metadata["symbol"] == "EURUSD"
        assert "baseline_size" in result.metadata
        assert "risky_agent_id" in result.metadata
        assert "adjustment_method" in result.metadata


class TestRiskDebateTeamHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(self, debate_team):
        """Test health check when all debators are healthy."""
        with patch.object(debate_team.risky_debator, 'health_check', return_value=True):
            with patch.object(debate_team.neutral_debator, 'health_check', return_value=True):
                with patch.object(debate_team.safe_debator, 'health_check', return_value=True):
                    result = await debate_team.health_check()
                    assert result is True

    @pytest.mark.asyncio
    async def test_health_check_one_unhealthy(self, debate_team):
        """Test health check when one debator is unhealthy."""
        with patch.object(debate_team.risky_debator, 'health_check', return_value=True):
            with patch.object(debate_team.neutral_debator, 'health_check', return_value=False):
                with patch.object(debate_team.safe_debator, 'health_check', return_value=True):
                    result = await debate_team.health_check()
                    assert result is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self, debate_team):
        """Test health check handles exceptions."""
        with patch.object(debate_team.risky_debator, 'health_check', side_effect=Exception("Error")):
            result = await debate_team.health_check()
            assert result is False


class TestRiskDebateTeamEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_risky_debator_recommends_caution(
        self,
        debate_team,
        trade_intent,
        position_size_decision,
        stop_loss_decision
    ):
        """Test when even risky debator recommends reduction."""
        risky_perspective = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=0.8,  # Risky recommending reduction!
            reasoning="Even from risky perspective, this is concerning",
            key_factors=["Multiple red flags"],
            confidence=0.85  # High confidence
        )
        neutral_perspective = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=0.7,
            reasoning="Baseline too aggressive",
            key_factors=["Overoptimistic"],
            confidence=0.80
        )
        safe_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=0.5,
            reasoning="High risk",
            key_factors=["Event risk"],
            confidence=0.90
        )

        with patch.object(debate_team.risky_debator, 'run', return_value=risky_perspective):
            with patch.object(debate_team.neutral_debator, 'run', return_value=neutral_perspective):
                with patch.object(debate_team.safe_debator, 'run', return_value=safe_perspective):
                    result = await debate_team.run_debate(
                        trade_intent=trade_intent,
                        position_size_decision=position_size_decision,
                        stop_loss_decision=stop_loss_decision,
                        account_balance=100000.0,
                        symbol="EURUSD"
                    )

        # Should include warning about risky debator's caution
        assert any("risky debator" in w.lower() for w in result.key_warnings)
        assert result.consensus_adjustment < 1.0
