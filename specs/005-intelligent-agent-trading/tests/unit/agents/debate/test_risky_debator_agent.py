"""
Unit tests for RiskyDebatorAgent.

Tests the risky perspective in 3-way risk tolerance debate.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from src.agents.debate.risky_debator_agent import RiskyDebatorAgent
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier
from src.agents.schemas.debate import RiskPerspective, RiskTolerance


@pytest.fixture
def agent_config():
    """Create risky debator agent config."""
    return AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.DEBATE,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="qwen2.5:14b-instruct",
        temperature=0.3,
        max_tokens=1500
    )


@pytest.fixture
def risky_agent(agent_config):
    """Create RiskyDebatorAgent instance."""
    return RiskyDebatorAgent(agent_config)


@pytest.fixture
def high_conviction_trade():
    """Trade intent with high conviction."""
    return {
        "direction": "LONG",
        "conviction": 0.85,
        "rationale": "Strong bullish setup with excellent risk/reward ratio",
        "key_factors": [
            "Strong technical breakout",
            "Positive fundamentals",
            "Low volatility environment"
        ],
        "risk_factors": []
    }


@pytest.fixture
def baseline_position_size():
    """Baseline position sizing decision."""
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
    """Stop loss decision."""
    return {
        "stop_loss_price": 99.50,
        "distance_pips": 50,
        "confidence": 0.80
    }


class TestRiskyDebatorAgentInitialization:
    """Test RiskyDebatorAgent initialization."""

    def test_initialization_success(self, risky_agent, agent_config):
        """Test successful agent initialization."""
        assert risky_agent.config.agent_type == AgentType.DEVILS_ADVOCATE
        assert risky_agent.config.layer == AgentLayer.DEBATE
        assert risky_agent.config.llm_tier == LLMTier.QUICK_THINK
        assert risky_agent.config.system_prompt is not None
        assert "Risky Debator" in risky_agent.config.system_prompt

    def test_initialization_with_wrong_agent_type(self):
        """Test initialization with wrong agent type logs warning."""
        config = AgentConfig(
            agent_type=AgentType.MARKET_DATA,  # Wrong type
            layer=AgentLayer.DEBATE,
            llm_tier=LLMTier.QUICK_THINK,
            llm_model="qwen2.5:14b-instruct"
        )

        with patch('src.agents.debate.risky_debator_agent.logger') as mock_logger:
            agent = RiskyDebatorAgent(config)
            mock_logger.warning.assert_called_once()
            assert "risky_debator_agent_type_mismatch" in str(mock_logger.warning.call_args)

    def test_initialization_with_wrong_layer(self):
        """Test initialization with wrong layer logs warning."""
        config = AgentConfig(
            agent_type=AgentType.DEVILS_ADVOCATE,
            layer=AgentLayer.EXECUTION,  # Wrong layer
            llm_tier=LLMTier.QUICK_THINK,
            llm_model="qwen2.5:14b-instruct"
        )

        with patch('src.agents.debate.risky_debator_agent.logger') as mock_logger:
            agent = RiskyDebatorAgent(config)
            mock_logger.warning.assert_called_once()
            assert "risky_debator_agent_layer_mismatch" in str(mock_logger.warning.call_args)


class TestRiskyDebatorAgentRun:
    """Test RiskyDebatorAgent run method."""

    @pytest.mark.asyncio
    async def test_run_high_conviction_scenario(
        self,
        risky_agent,
        high_conviction_trade,
        baseline_position_size,
        stop_loss_decision
    ):
        """Test risky perspective with high conviction trade."""
        # Mock LLM response
        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.3,  # Recommending 30% increase
            reasoning=(
                "High conviction (0.85) with excellent risk/reward (2.5:1). "
                "Low volatility environment reduces slippage risk. "
                "Strong technical setup warrants increased size."
            ),
            key_factors=[
                "High conviction >0.8 justifies size increase",
                "Excellent R:R ratio of 2.5:1",
                "Low volatility environment (predictable risk)"
            ],
            confidence=0.80
        )

        with patch.object(risky_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.risky_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await risky_agent.run(
                    trade_intent=high_conviction_trade,
                    position_size_decision=baseline_position_size,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD"
                )

        # Verify result
        assert isinstance(result, RiskPerspective)
        assert result.tolerance == RiskTolerance.RISKY
        assert result.recommended_size_adjustment > 1.0  # Should recommend increase
        assert result.confidence > 0.0
        assert len(result.key_factors) >= 2

    @pytest.mark.asyncio
    async def test_run_low_conviction_scenario(self, risky_agent, baseline_position_size, stop_loss_decision):
        """Test risky perspective with low conviction trade."""
        low_conviction_trade = {
            "direction": "LONG",
            "conviction": 0.4,
            "rationale": "Weak setup with uncertainty",
            "key_factors": ["Some support"],
            "risk_factors": ["High volatility", "Unclear trend"]
        }

        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.0,  # No increase for low conviction
            reasoning="Low conviction (0.4) and high volatility do not justify size increase.",
            key_factors=[
                "Conviction too low (<0.5)",
                "High volatility increases risk"
            ],
            confidence=0.70
        )

        with patch.object(risky_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.risky_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await risky_agent.run(
                    trade_intent=low_conviction_trade,
                    position_size_decision=baseline_position_size,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD"
                )

        assert result.recommended_size_adjustment == 1.0  # No increase

    @pytest.mark.asyncio
    async def test_run_exception_handling(
        self,
        risky_agent,
        high_conviction_trade,
        baseline_position_size,
        stop_loss_decision
    ):
        """Test exception handling during LLM call."""
        with patch.object(risky_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_assistant.on_messages.side_effect = Exception("LLM API error")

            with patch('src.agents.debate.risky_debator_agent.AssistantAgent', return_value=mock_assistant):
                with pytest.raises(Exception, match="LLM API error"):
                    await risky_agent.run(
                        trade_intent=high_conviction_trade,
                        position_size_decision=baseline_position_size,
                        stop_loss_decision=stop_loss_decision,
                        account_balance=100000.0,
                        symbol="EURUSD"
                    )


class TestRiskyDebatorAgentPromptBuilding:
    """Test prompt building logic."""

    def test_build_assessment_prompt(
        self,
        risky_agent,
        high_conviction_trade,
        baseline_position_size,
        stop_loss_decision
    ):
        """Test assessment prompt construction."""
        prompt = risky_agent._build_assessment_prompt(
            trade_intent=high_conviction_trade,
            position_size_decision=baseline_position_size,
            stop_loss_decision=stop_loss_decision,
            account_balance=100000.0,
            symbol="EURUSD"
        )

        # Verify critical information is included
        assert "EURUSD" in prompt
        assert "0.85" in prompt  # Conviction
        assert "1.5" in prompt or "1.50" in prompt  # Position size
        assert "2.0" in prompt or "2.00" in prompt  # Risk percentage
        assert "100000" in prompt  # Account balance
        assert "HIGHER" in prompt  # Key instruction
        assert "RiskPerspective" in prompt  # Expected output format


class TestRiskyDebatorAgentHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, risky_agent):
        """Test successful health check."""
        with patch.object(risky_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            result = await risky_agent.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, risky_agent):
        """Test failed health check."""
        with patch.object(risky_agent, '_create_model_client') as mock_client_factory:
            mock_client_factory.side_effect = Exception("Connection error")

            result = await risky_agent.health_check()
            assert result is False


class TestRiskyDebatorAgentEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_extreme_risk_reward_ratio(
        self,
        risky_agent,
        baseline_position_size,
        stop_loss_decision
    ):
        """Test handling of extreme risk/reward ratio (>5:1)."""
        extreme_rr_trade = {
            "direction": "LONG",
            "conviction": 0.75,
            "rationale": "Asymmetric setup with 6:1 R:R",
            "key_factors": ["Extreme asymmetry"],
            "risk_factors": []
        }

        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.5,
            reasoning="Extreme R:R of 6:1 justifies significant size increase despite moderate conviction.",
            key_factors=["6:1 risk/reward ratio", "Asymmetric opportunity"],
            confidence=0.75
        )

        with patch.object(risky_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.risky_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await risky_agent.run(
                    trade_intent=extreme_rr_trade,
                    position_size_decision=baseline_position_size,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD"
                )

        assert result.recommended_size_adjustment >= 1.3  # Should recommend significant increase

    @pytest.mark.asyncio
    async def test_zero_risk_factors(
        self,
        risky_agent,
        baseline_position_size,
        stop_loss_decision
    ):
        """Test handling of trade with no identified risk factors."""
        clean_trade = {
            "direction": "LONG",
            "conviction": 0.80,
            "rationale": "Clean setup with no red flags",
            "key_factors": ["Strong trend", "Volume confirmation"],
            "risk_factors": []  # No risk factors
        }

        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.4,
            reasoning="Clean setup with no risk factors and high conviction. Safe to increase size.",
            key_factors=["No risk factors identified", "High conviction", "Strong trend"],
            confidence=0.85
        )

        with patch.object(risky_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.risky_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await risky_agent.run(
                    trade_intent=clean_trade,
                    position_size_decision=baseline_position_size,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD"
                )

        assert result.recommended_size_adjustment > 1.0
