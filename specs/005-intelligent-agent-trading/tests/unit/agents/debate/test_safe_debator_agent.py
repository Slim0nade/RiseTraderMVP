"""
Unit tests for SafeDebatorAgent.

Tests the safe perspective in 3-way risk tolerance debate.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from src.agents.debate.safe_debator_agent import SafeDebatorAgent
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier
from src.agents.schemas.debate import RiskPerspective, RiskTolerance


@pytest.fixture
def agent_config():
    """Create safe debator agent config."""
    return AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.DEBATE,
        llm_tier=LLMTier.QUICK_THINK,
        llm_model="qwen2.5:14b-instruct",
        temperature=0.3,
        max_tokens=1500
    )


@pytest.fixture
def safe_agent(agent_config):
    """Create SafeDebatorAgent instance."""
    return SafeDebatorAgent(agent_config)


@pytest.fixture
def risky_trade():
    """Trade intent with risk factors."""
    return {
        "direction": "LONG",
        "conviction": 0.45,  # Low conviction
        "rationale": "Uncertain setup with mixed signals",
        "key_factors": ["Some support"],
        "risk_factors": [
            "High volatility",
            "FOMC meeting in 18 hours",
            "Unclear trend direction"
        ]
    }


@pytest.fixture
def clean_trade():
    """Clean trade with no risk factors."""
    return {
        "direction": "LONG",
        "conviction": 0.80,
        "rationale": "Strong setup with clear invalidation",
        "key_factors": ["Strong trend", "Volume confirmation", "Clear support"],
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


class TestSafeDebatorAgentInitialization:
    """Test SafeDebatorAgent initialization."""

    def test_initialization_success(self, safe_agent, agent_config):
        """Test successful agent initialization."""
        assert safe_agent.config.agent_type == AgentType.DEVILS_ADVOCATE
        assert safe_agent.config.layer == AgentLayer.DEBATE
        assert safe_agent.config.llm_tier == LLMTier.QUICK_THINK
        assert safe_agent.config.system_prompt is not None
        assert "Safe Debator" in safe_agent.config.system_prompt

    def test_initialization_with_wrong_agent_type(self):
        """Test initialization with wrong agent type logs warning."""
        config = AgentConfig(
            agent_type=AgentType.MARKET_DATA,  # Wrong type
            layer=AgentLayer.DEBATE,
            llm_tier=LLMTier.QUICK_THINK,
            llm_model="qwen2.5:14b-instruct"
        )

        with patch('src.agents.debate.safe_debator_agent.logger') as mock_logger:
            agent = SafeDebatorAgent(config)
            mock_logger.warning.assert_called_once()
            assert "safe_debator_agent_type_mismatch" in str(mock_logger.warning.call_args)


class TestSafeDebatorAgentRun:
    """Test SafeDebatorAgent run method."""

    @pytest.mark.asyncio
    async def test_run_risky_scenario(
        self,
        safe_agent,
        risky_trade,
        baseline_position_size,
        stop_loss_decision
    ):
        """Test safe perspective with risky trade setup."""
        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=0.5,  # 50% reduction
            reasoning=(
                "Multiple risk factors warrant significant reduction. "
                "Low conviction (0.45) indicates uncertainty. "
                "FOMC meeting in 18 hours creates event risk. "
                "High volatility increases slippage risk. "
                "Recommend 0.5x adjustment (0.75 lots instead of 1.5 lots)."
            ),
            key_factors=[
                "Low conviction (<0.5)",
                "Event risk: FOMC in 18 hours",
                "High volatility environment",
                "Unclear trend direction"
            ],
            confidence=0.85
        )

        with patch.object(safe_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.safe_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await safe_agent.run(
                    trade_intent=risky_trade,
                    position_size_decision=baseline_position_size,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD"
                )

        # Verify result
        assert isinstance(result, RiskPerspective)
        assert result.tolerance == RiskTolerance.SAFE
        assert result.recommended_size_adjustment < 1.0  # Should recommend reduction
        assert result.confidence > 0.0
        assert len(result.key_factors) >= 2

    @pytest.mark.asyncio
    async def test_run_clean_scenario(
        self,
        safe_agent,
        clean_trade,
        baseline_position_size,
        stop_loss_decision
    ):
        """Test safe perspective with clean trade setup."""
        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=1.0,  # No reduction needed
            reasoning=(
                "No significant risk factors identified. "
                "High conviction (0.80) with strong evidence. "
                "No imminent events. Volatility within normal range. "
                "Baseline sizing is appropriate."
            ),
            key_factors=[
                "High conviction >0.7",
                "No event risk present",
                "Clear trend direction",
                "Normal volatility"
            ],
            confidence=0.75
        )

        with patch.object(safe_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.safe_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await safe_agent.run(
                    trade_intent=clean_trade,
                    position_size_decision=baseline_position_size,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD"
                )

        assert result.recommended_size_adjustment == 1.0  # No reduction

    @pytest.mark.asyncio
    async def test_run_with_portfolio_drawdown(
        self,
        safe_agent,
        clean_trade,
        baseline_position_size,
        stop_loss_decision
    ):
        """Test safe perspective with portfolio in drawdown."""
        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=0.6,  # Reduce due to drawdown
            reasoning=(
                "Portfolio in drawdown (-$5,000) requires capital preservation. "
                "Need to protect capital and avoid compounding losses. "
                "Recommend 40% size reduction despite clean setup."
            ),
            key_factors=[
                "Portfolio in recent drawdown",
                "Capital preservation priority",
                "Avoid compounding losses"
            ],
            confidence=0.80
        )

        with patch.object(safe_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.safe_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await safe_agent.run(
                    trade_intent=clean_trade,
                    position_size_decision=baseline_position_size,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD",
                    recent_pnl=-5000.0  # Drawdown
                )

        assert result.recommended_size_adjustment < 1.0

    @pytest.mark.asyncio
    async def test_run_with_high_correlation(
        self,
        safe_agent,
        clean_trade,
        baseline_position_size,
        stop_loss_decision
    ):
        """Test safe perspective with high portfolio correlation."""
        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=0.7,  # Reduce due to correlation
            reasoning=(
                "Portfolio already 15% exposed to EUR pairs (high correlation). "
                "Adding this position would increase concentration risk. "
                "Recommend 30% size reduction to avoid overconcentration."
            ),
            key_factors=[
                "High correlation with existing positions",
                "15% EUR exposure already",
                "Concentration risk management"
            ],
            confidence=0.75
        )

        with patch.object(safe_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.safe_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await safe_agent.run(
                    trade_intent=clean_trade,
                    position_size_decision=baseline_position_size,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD",
                    portfolio_exposure={"EUR": 15.0, "USD": 10.0}
                )

        assert result.recommended_size_adjustment < 1.0

    @pytest.mark.asyncio
    async def test_run_exception_handling(
        self,
        safe_agent,
        risky_trade,
        baseline_position_size,
        stop_loss_decision
    ):
        """Test exception handling during LLM call."""
        with patch.object(safe_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_assistant.on_messages.side_effect = Exception("LLM API error")

            with patch('src.agents.debate.safe_debator_agent.AssistantAgent', return_value=mock_assistant):
                with pytest.raises(Exception, match="LLM API error"):
                    await safe_agent.run(
                        trade_intent=risky_trade,
                        position_size_decision=baseline_position_size,
                        stop_loss_decision=stop_loss_decision,
                        account_balance=100000.0,
                        symbol="EURUSD"
                    )


class TestSafeDebatorAgentPromptBuilding:
    """Test prompt building logic."""

    def test_build_assessment_prompt(
        self,
        safe_agent,
        risky_trade,
        baseline_position_size,
        stop_loss_decision
    ):
        """Test assessment prompt construction."""
        prompt = safe_agent._build_assessment_prompt(
            trade_intent=risky_trade,
            position_size_decision=baseline_position_size,
            stop_loss_decision=stop_loss_decision,
            account_balance=100000.0,
            symbol="EURUSD",
            portfolio_exposure={"EUR": 10.0},
            recent_pnl=-2000.0
        )

        # Verify critical information is included
        assert "EURUSD" in prompt
        assert "0.45" in prompt  # Conviction
        assert "1.5" in prompt or "1.50" in prompt  # Position size
        assert "EUR: 10" in prompt  # Portfolio exposure
        assert "loss" in prompt  # Recent P&L
        assert "REDUCTION" in prompt  # Key instruction
        assert "RiskPerspective" in prompt  # Expected output format

    def test_build_prompt_without_optional_data(
        self,
        safe_agent,
        risky_trade,
        baseline_position_size,
        stop_loss_decision
    ):
        """Test prompt building without optional portfolio data."""
        prompt = safe_agent._build_assessment_prompt(
            trade_intent=risky_trade,
            position_size_decision=baseline_position_size,
            stop_loss_decision=stop_loss_decision,
            account_balance=100000.0,
            symbol="EURUSD",
            portfolio_exposure=None,
            recent_pnl=None
        )

        # Should handle missing data gracefully
        assert "EURUSD" in prompt
        assert "Not provided" in prompt  # Placeholder for missing data


class TestSafeDebatorAgentHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, safe_agent):
        """Test successful health check."""
        with patch.object(safe_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            result = await safe_agent.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, safe_agent):
        """Test failed health check."""
        with patch.object(safe_agent, '_create_model_client') as mock_client_factory:
            mock_client_factory.side_effect = Exception("Connection error")

            result = await safe_agent.health_check()
            assert result is False


class TestSafeDebatorAgentEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_extreme_event_risk(
        self,
        safe_agent,
        baseline_position_size,
        stop_loss_decision
    ):
        """Test handling of extreme event risk (NFP, FOMC)."""
        extreme_event_trade = {
            "direction": "LONG",
            "conviction": 0.70,
            "rationale": "Good setup but NFP in 2 hours",
            "key_factors": ["Technical breakout"],
            "risk_factors": ["NFP announcement in 2 hours"]
        }

        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=0.3,  # Severe reduction
            reasoning=(
                "NFP announcement in 2 hours creates extreme volatility risk. "
                "Gold can move 2-3% in minutes on NFP. "
                "Recommend 70% size reduction or delay until after event."
            ),
            key_factors=[
                "NFP in 2 hours (extreme event risk)",
                "Historical 2-3% moves on NFP",
                "Slippage and gap risk"
            ],
            confidence=0.90
        )

        with patch.object(safe_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.safe_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await safe_agent.run(
                    trade_intent=extreme_event_trade,
                    position_size_decision=baseline_position_size,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="XAUUSD"
                )

        assert result.recommended_size_adjustment <= 0.4  # Severe reduction

    @pytest.mark.asyncio
    async def test_perfect_conditions(
        self,
        safe_agent,
        baseline_position_size,
        stop_loss_decision
    ):
        """Test handling of perfect risk-free conditions."""
        perfect_trade = {
            "direction": "LONG",
            "conviction": 0.90,
            "rationale": "Perfect setup with all confirmations",
            "key_factors": [
                "Multiple timeframe alignment",
                "Volume confirmation",
                "Clear invalidation",
                "Low volatility"
            ],
            "risk_factors": []
        }

        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=1.0,  # No reduction
            reasoning=(
                "No risk factors identified. Very high conviction (0.90). "
                "Perfect technical setup. Low volatility environment. "
                "No events. Baseline sizing is appropriate."
            ),
            key_factors=[
                "Very high conviction (0.90)",
                "No risk factors present",
                "Perfect technical alignment",
                "Low volatility"
            ],
            confidence=0.85
        )

        with patch.object(safe_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.safe_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await safe_agent.run(
                    trade_intent=perfect_trade,
                    position_size_decision=baseline_position_size,
                    stop_loss_decision=stop_loss_decision,
                    account_balance=100000.0,
                    symbol="EURUSD",
                    portfolio_exposure={},
                    recent_pnl=5000.0  # Profitable
                )

        assert result.recommended_size_adjustment == 1.0
        assert result.confidence >= 0.80

    @pytest.mark.asyncio
    async def test_questionable_stop_loss(
        self,
        safe_agent,
        clean_trade,
        baseline_position_size
    ):
        """Test handling of questionable stop loss placement."""
        questionable_stop = {
            "stop_loss_price": 98.00,
            "distance_pips": 200,  # Very wide stop
            "confidence": 0.50  # Low confidence
        }

        mock_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=0.65,
            reasoning=(
                "Stop loss placement questionable. 200 pips is very wide, "
                "and low confidence (0.50) suggests unclear invalidation level. "
                "Wide stop increases risk despite smaller position size. "
                "Recommend 35% reduction."
            ),
            key_factors=[
                "Very wide stop (200 pips)",
                "Low stop loss confidence (0.50)",
                "Unclear invalidation level"
            ],
            confidence=0.75
        )

        with patch.object(safe_agent, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_perspective
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.debate.safe_debator_agent.AssistantAgent', return_value=mock_assistant):
                result = await safe_agent.run(
                    trade_intent=clean_trade,
                    position_size_decision=baseline_position_size,
                    stop_loss_decision=questionable_stop,
                    account_balance=100000.0,
                    symbol="EURUSD"
                )

        assert result.recommended_size_adjustment < 1.0
