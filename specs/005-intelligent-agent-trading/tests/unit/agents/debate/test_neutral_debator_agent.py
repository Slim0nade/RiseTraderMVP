"""
Unit tests for NeutralDebatorAgent.

Tests the neutral perspective in 3-way risk tolerance debate.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from src.agents.debate.neutral_debator_agent import NeutralDebatorAgent
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier
from src.agents.schemas.debate import RiskPerspective, RiskTolerance


@pytest.fixture
def agent_config():
    """Create neutral debator agent config."""
    return AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.DEBATE,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="qwen2.5:14b-instruct",
        temperature=0.3,
        max_tokens=1500
    )


@pytest.fixture
def neutral_agent(agent_config):
    """Create NeutralDebatorAgent instance."""
    return NeutralDebatorAgent(agent_config)


@pytest.fixture
def valid_baseline_sizing():
    """Valid baseline position sizing decision."""
    return {
        "position_size_lots": 1.5,
        "risk_percentage": 2.0,
        "kelly_fraction": 0.25,
        "win_rate": 0.55,
        "avg_win_loss_ratio": 2.5,
        "confidence": 0.75,
        "kelly_rationale": "Using 25% Kelly with validated backtest data"
    }


@pytest.fixture
def questionable_baseline_sizing():
    """Questionable baseline sizing with overoptimistic inputs."""
    return {
        "position_size_lots": 2.5,
        "risk_percentage": 4.0,
        "kelly_fraction": 0.5,  # Too aggressive
        "win_rate": 0.70,  # Overestimated
        "avg_win_loss_ratio": 3.5,  # Overoptimistic
        "confidence": 0.60,
        "kelly_rationale": "Estimated win rate based on recent trades"
    }


@pytest.fixture
def trade_intent():
    """Standard trade intent."""
    return {
        "direction": "LONG",
        "conviction": 0.70,
        "rationale": "Technical and fundamental alignment",
        "key_factors": ["Trend confirmation", "Support level"],
        "risk_factors": []
    }


@pytest.fixture
def stop_loss_decision():
    """Stop loss decision."""
    return {
        "stop_loss_price": 99.50,
        "distance_pips": 50,
        "confidence": 0.80
    }


class TestNeutralDebatorAgentInitialization:
    """Test NeutralDebatorAgent initialization."""

    def test_initialization_success(self, neutral_agent, agent_config):
        """Test successful agent initialization."""
        assert neutral_agent.config.agent_type == AgentType.DEVILS_ADVOCATE
        assert neutral_agent.config.layer == AgentLayer.DEBATE
        assert neutral_agent.config.llm_tier == LLMTier.QUICK_THINK
        assert neutral_agent.config.system_prompt is not None
        assert "Neutral Debator" in neutral_agent.config.system_prompt

    def test_initialization_with_wrong_agent_type(self):
        """Test initialization with wrong agent type logs warning."""
        config = AgentConfig(
            agent_type=AgentType.MARKET_DATA,  # Wrong type
            layer=AgentLayer.DEBATE,
            llm_tier=LLMTier.QUICK_THINK,
            llm_model="qwen2.5:14b-instruct"
        )

        with patch('src.agents.debate.neutral_debator_agent.logger') as mock_logger:
            agent = NeutralDebatorAgent(config)
            mock_logger.warning.assert_called_once()
            assert "neutral_debator_agent_type_mismatch" in str(mock_logger.warning.call_args)


class TestNeutralDebatorAgentRun:
    """Test NeutralDebatorAgent run method."""

    @pytest.mark.asyncio
    async def test_run_valid_baseline(
        self,
        neutral_agent,
        trade_intent,
        valid_baseline_sizing,
        stop_loss_decision
    ):
        """Test neutral perspective with valid baseline sizing."""
        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=1.0,  # No change - baseline is sound
            reasoning=(
                "Baseline Kelly calculation is sound. Win rate 0.55 based on backtest data, "
                "avg win/loss 2.5:1 matches setup. Using 0.25 Kelly fraction is conservative. "
                "2% account risk is within limits. No adjustments needed."
            ),
            key_factors=[
                "Kelly inputs validated against backtest",
                "0.25 Kelly fraction is conservative",
                "2% account risk respects limits"
            ],
            confidence=0.85
        )

        with patch.object(neutral_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.neutral_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await neutral_agent.run(
                    trade_intent=trade_intent,
                    position_size_decision=valid_baseline_sizing,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD"
                )

        # Verify result
        assert isinstance(result, RiskPerspective)
        assert result.tolerance == RiskTolerance.NEUTRAL
        assert result.recommended_size_adjustment == 1.0  # No adjustment
        assert result.confidence > 0.7
        assert len(result.key_factors) >= 2

    @pytest.mark.asyncio
    async def test_run_questionable_baseline(
        self,
        neutral_agent,
        trade_intent,
        questionable_baseline_sizing,
        stop_loss_decision
    ):
        """Test neutral perspective with questionable baseline sizing."""
        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=0.7,  # Recommend reduction
            reasoning=(
                "Baseline Kelly inputs appear overoptimistic. Win rate 0.70 and 3.5:1 avg win/loss "
                "are not backed by sufficient backtest data. Using 0.5 Kelly fraction is too aggressive. "
                "4% account risk is near upper limit. Recommend 30% size reduction."
            ),
            key_factors=[
                "Win rate estimate questionable (no backtest validation)",
                "0.5 Kelly fraction too aggressive",
                "4% risk near upper limit"
            ],
            confidence=0.75
        )

        with patch.object(neutral_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.neutral_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await neutral_agent.run(
                    trade_intent=trade_intent,
                    position_size_decision=questionable_baseline_sizing,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD"
                )

        assert result.recommended_size_adjustment < 1.0  # Should recommend reduction

    @pytest.mark.asyncio
    async def test_run_exception_handling(
        self,
        neutral_agent,
        trade_intent,
        valid_baseline_sizing,
        stop_loss_decision
    ):
        """Test exception handling during LLM call."""
        with patch.object(neutral_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_assistant.on_messages.side_effect = Exception("LLM API error")

            with patch('src.agents.debate.neutral_debator_agent.AssistantAgent', return_value=mock_assistant):
                with pytest.raises(Exception, match="LLM API error"):
                    await neutral_agent.run(
                        trade_intent=trade_intent,
                        position_size_decision=valid_baseline_sizing,
                        stop_loss_decision=stop_loss_decision,
                        account_balance=100000.0,
                        symbol="EURUSD"
                    )


class TestNeutralDebatorAgentPromptBuilding:
    """Test prompt building logic."""

    def test_build_assessment_prompt(
        self,
        neutral_agent,
        trade_intent,
        valid_baseline_sizing,
        stop_loss_decision
    ):
        """Test assessment prompt construction."""
        prompt = neutral_agent._build_assessment_prompt(
            trade_intent=trade_intent,
            position_size_decision=valid_baseline_sizing,
            stop_loss_decision=stop_loss_decision,
            account_balance=100000.0,
            symbol="EURUSD"
        )

        # Verify critical information is included
        assert "EURUSD" in prompt
        assert "0.70" in prompt  # Conviction
        assert "1.5" in prompt or "1.50" in prompt  # Position size
        assert "0.55" in prompt  # Win rate
        assert "2.5" in prompt  # Avg win/loss ratio
        assert "VALIDATE" in prompt  # Key instruction
        assert "RiskPerspective" in prompt  # Expected output format
        assert "Kelly" in prompt  # Kelly Criterion validation

    def test_build_prompt_with_missing_kelly_data(
        self,
        neutral_agent,
        trade_intent,
        stop_loss_decision
    ):
        """Test prompt building with incomplete Kelly data."""
        incomplete_sizing = {
            "position_size_lots": 1.0,
            "risk_percentage": 1.5,
            # Missing Kelly inputs
        }

        prompt = neutral_agent._build_assessment_prompt(
            trade_intent=trade_intent,
            position_size_decision=incomplete_sizing,
            stop_loss_decision=stop_loss_decision,
            account_balance=100000.0,
            symbol="EURUSD"
        )

        # Should handle missing data gracefully
        assert "EURUSD" in prompt
        assert "1.0" in prompt or "1.00" in prompt


class TestNeutralDebatorAgentHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, neutral_agent):
        """Test successful health check."""
        with patch.object(neutral_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            result = await neutral_agent.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, neutral_agent):
        """Test failed health check."""
        with patch.object(neutral_agent, '_create_model_client') as mock_client_factory:
            mock_client_factory.side_effect = Exception("Connection error")

            result = await neutral_agent.health_check()
            assert result is False


class TestNeutralDebatorAgentEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_extremely_aggressive_kelly_fraction(
        self,
        neutral_agent,
        trade_intent,
        stop_loss_decision
    ):
        """Test handling of extremely aggressive Kelly fraction (>0.5)."""
        aggressive_sizing = {
            "position_size_lots": 3.0,
            "risk_percentage": 5.0,
            "kelly_fraction": 0.75,  # Way too aggressive
            "win_rate": 0.60,
            "avg_win_loss_ratio": 2.0,
            "confidence": 0.70
        }

        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=0.5,  # Significant reduction
            reasoning=(
                "Kelly fraction of 0.75 is dangerously aggressive. "
                "Even with 0.60 win rate, this exposes to severe drawdowns. "
                "Recommend reducing to 0.25-0.33 Kelly maximum."
            ),
            key_factors=[
                "0.75 Kelly fraction is reckless",
                "5% account risk at upper limit",
                "High drawdown risk with current sizing"
            ],
            confidence=0.90
        )

        with patch.object(neutral_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.neutral_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await neutral_agent.run(
                    trade_intent=trade_intent,
                    position_size_decision=aggressive_sizing,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD"
                )

        assert result.recommended_size_adjustment <= 0.6  # Should recommend significant cut

    @pytest.mark.asyncio
    async def test_perfect_kelly_setup(
        self,
        neutral_agent,
        trade_intent,
        stop_loss_decision
    ):
        """Test handling of perfectly calibrated Kelly inputs."""
        perfect_sizing = {
            "position_size_lots": 1.0,
            "risk_percentage": 1.5,
            "kelly_fraction": 0.25,
            "win_rate": 0.55,
            "avg_win_loss_ratio": 2.5,
            "confidence": 0.85,
            "kelly_rationale": "Based on 500+ trades backtest, validated on out-of-sample data"
        }

        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=1.0,  # Perfect - no change
            reasoning=(
                "Baseline calculation is exemplary. Win rate and R:R backed by robust backtest. "
                "Conservative 0.25 Kelly with 1.5% risk is textbook position sizing. "
                "No adjustments warranted."
            ),
            key_factors=[
                "Validated backtest data (500+ trades)",
                "Conservative Kelly fraction",
                "Risk well within limits"
            ],
            confidence=0.95
        )

        with patch.object(neutral_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.neutral_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await neutral_agent.run(
                    trade_intent=trade_intent,
                    position_size_decision=perfect_sizing,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD"
                )

        assert result.recommended_size_adjustment == 1.0
        assert result.confidence >= 0.90

    @pytest.mark.asyncio
    async def test_unrealistic_win_rate(
        self,
        neutral_agent,
        trade_intent,
        stop_loss_decision
    ):
        """Test handling of unrealistic win rate (>0.70)."""
        unrealistic_sizing = {
            "position_size_lots": 2.0,
            "risk_percentage": 3.0,
            "kelly_fraction": 0.40,
            "win_rate": 0.85,  # Unrealistically high
            "avg_win_loss_ratio": 2.0,
            "confidence": 0.65
        }

        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=0.6,
            reasoning=(
                "Win rate of 0.85 is unrealistic for most trading strategies. "
                "This appears to be curve-fitted or cherry-picked data. "
                "Conservative adjustment warranted until proven in live trading."
            ),
            key_factors=[
                "Win rate >0.70 is statistically unlikely",
                "Risk of overfitting to backtest",
                "Lack of live validation"
            ],
            confidence=0.80
        )

        with patch.object(neutral_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.neutral_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await neutral_agent.run(
                    trade_intent=trade_intent,
                    position_size_decision=unrealistic_sizing,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD"
                )

        assert result.recommended_size_adjustment < 1.0
