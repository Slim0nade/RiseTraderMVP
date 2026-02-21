"""
Unit tests for FundManagerAgent.

Tests the final approval gate with APPROVE/MODIFY/REJECT powers.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from src.agents.approval.fund_manager_agent import FundManagerAgent
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier
from src.agents.schemas.approval import (
    FundManagerApproval,
    ApprovalDecision,
    PortfolioLimits,
    RejectionReason,
    TradeModification,
    ModificationType
)


@pytest.fixture
def agent_config():
    """Create fund manager agent config."""
    return AgentConfig(
        agent_type=AgentType.DEVILS_ADVOCATE,
        layer=AgentLayer.APPROVAL,
        llm_tier=LLMTier.DEEP_THINK,
        llm_model="deepseek-reasoner:14b",
        temperature=0.2,
        max_tokens=3000
    )


@pytest.fixture
def portfolio_limits():
    """Standard portfolio limits."""
    return PortfolioLimits(
        max_account_risk_percent=5.0,
        max_portfolio_risk_percent=15.0,
        max_correlated_positions=3,
        event_risk_veto_hours=24,
        min_trade_quality_score=0.4
    )


@pytest.fixture
def fund_manager(agent_config, portfolio_limits):
    """Create FundManagerAgent instance."""
    return FundManagerAgent(
        config=agent_config,
        portfolio_limits=portfolio_limits
    )


@pytest.fixture
def clean_trade_intent():
    """Clean trade intent passing all checks."""
    return {
        "direction": "LONG",
        "conviction": 0.80,
        "rationale": "Strong technical and fundamental alignment with clear risk management",
        "key_factors": ["Trend confirmation", "Volume support", "Clear invalidation"],
        "risk_assessment": "Moderate risk with tight stop loss and 3:1 R:R ratio"
    }


@pytest.fixture
def risk_debate_outcome_approved():
    """Risk debate outcome that should pass approval."""
    return {
        "final_position_size": 1.2,
        "final_risk_percentage": 2.0,
        "consensus_reached": True,
        "consensus_adjustment": 0.8,
        "key_warnings": []
    }


@pytest.fixture
def healthy_portfolio_state():
    """Healthy portfolio state."""
    return {
        "total_risk_percentage": 5.0,
        "open_positions_count": 2,
        "recent_pnl": 3000.0,
        "available_capacity_pct": 70.0
    }


@pytest.fixture
def upcoming_events_none():
    """No upcoming events."""
    return []


class TestFundManagerAgentInitialization:
    """Test FundManagerAgent initialization."""

    def test_initialization_success(self, fund_manager, agent_config, portfolio_limits):
        """Test successful agent initialization."""
        assert fund_manager.config.agent_type == AgentType.DEVILS_ADVOCATE
        assert fund_manager.config.llm_tier == LLMTier.DEEP_THINK
        assert fund_manager.portfolio_limits == portfolio_limits
        assert fund_manager.config.system_prompt is not None
        assert "Fund Manager" in fund_manager.config.system_prompt

    def test_initialization_with_default_limits(self, agent_config):
        """Test initialization with default portfolio limits."""
        manager = FundManagerAgent(config=agent_config)
        assert manager.portfolio_limits is not None
        assert manager.portfolio_limits.max_account_risk_percent == 5.0
        assert manager.portfolio_limits.max_portfolio_risk_percent == 15.0

    def test_initialization_with_wrong_agent_type(self, portfolio_limits):
        """Test initialization with wrong agent type logs warning."""
        config = AgentConfig(
            agent_type=AgentType.MARKET_DATA,  # Wrong type
            layer=AgentLayer.APPROVAL,
            llm_tier=LLMTier.DEEP_THINK,
            llm_model="deepseek-reasoner:14b"
        )

        with patch('src.agents.approval.fund_manager_agent.logger') as mock_logger:
            agent = FundManagerAgent(config, portfolio_limits)
            mock_logger.warning.assert_called_once()
            assert "fund_manager_agent_type_mismatch" in str(mock_logger.warning.call_args)


class TestFundManagerAgentRun:
    """Test FundManagerAgent run method."""

    @pytest.mark.asyncio
    async def test_run_approve_decision(
        self,
        fund_manager,
        clean_trade_intent,
        risk_debate_outcome_approved,
        healthy_portfolio_state,
        upcoming_events_none
    ):
        """Test APPROVE decision for clean trade."""
        mock_approval = FundManagerApproval(
            decision=ApprovalDecision.APPROVE,
            rationale=(
                "Trade meets all approval criteria. Conviction is high (0.80), "
                "risk is appropriate (2.0%), portfolio has capacity, "
                "no event risk present, and hard limits respected. "
                "Risk/reward ratio is favorable at 3:1. Approved for execution."
            ),
            approved_position_size=1.2,
            approved_risk_percentage=2.0,
            modifications=[],
            rejection_reason=None,
            portfolio_risk_after_trade=7.0,
            correlation_check_passed=True,
            correlated_positions_count=0,
            event_risk_present=False,
            hard_limits_passed=True,
            violated_limits=[],
            trade_quality_score=0.75,
            quality_concerns=[],
            confidence=0.85,
            recommended_action_timing="immediate",
            timestamp=datetime.utcnow().isoformat(),
            metadata={}
        )

        with patch.object(fund_manager, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_approval
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.approval.fund_manager_agent.AssistantAgent', return_value=mock_assistant):
                result = await fund_manager.run(
                    trade_intent=clean_trade_intent,
                    risk_debate_outcome=risk_debate_outcome_approved,
                    portfolio_state=healthy_portfolio_state,
                    upcoming_events=upcoming_events_none,
                    symbol="EURUSD"
                )

        # Verify result
        assert isinstance(result, FundManagerApproval)
        assert result.decision == ApprovalDecision.APPROVE
        assert result.approved_position_size == 1.2
        assert result.approved_risk_percentage == 2.0
        assert result.hard_limits_passed is True
        assert len(result.modifications) == 0

    @pytest.mark.asyncio
    async def test_run_modify_decision(
        self,
        fund_manager,
        healthy_portfolio_state,
        upcoming_events_none
    ):
        """Test MODIFY decision for oversized trade."""
        oversized_trade = {
            "direction": "LONG",
            "conviction": 0.70,
            "rationale": "Good setup but position size too large",
            "key_factors": ["Technical breakout"],
            "risk_assessment": "Moderate"
        }
        oversized_debate = {
            "final_position_size": 2.5,
            "final_risk_percentage": 4.5,  # Near upper limit
            "consensus_reached": False,
            "consensus_adjustment": 1.2,
            "key_warnings": ["High size relative to account"]
        }

        mock_approval = FundManagerApproval(
            decision=ApprovalDecision.MODIFY,
            rationale=(
                "Trade has merit but requires size reduction. "
                "Current 4.5% risk is near the 5% max limit. "
                "Portfolio already at 5% risk, bringing total to 9.5%. "
                "Recommend reducing position size to 1.5 lots (2.5% risk) "
                "for better portfolio balance."
            ),
            approved_position_size=1.5,
            approved_risk_percentage=2.5,
            modifications=[
                TradeModification(
                    modification_type=ModificationType.REDUCE_SIZE,
                    current_value=2.5,
                    recommended_value=1.5,
                    rationale="Reduce size from 2.5 to 1.5 lots to bring risk to 2.5%"
                )
            ],
            modification_summary="Reduce position size by 40% to respect portfolio risk limits",
            rejection_reason=None,
            portfolio_risk_after_trade=7.5,
            correlation_check_passed=True,
            correlated_positions_count=1,
            event_risk_present=False,
            hard_limits_passed=False,
            violated_limits=["Approaching max account risk"],
            trade_quality_score=0.65,
            quality_concerns=["Risk near upper limit"],
            confidence=0.80,
            recommended_action_timing="immediate",
            timestamp=datetime.utcnow().isoformat(),
            metadata={}
        )

        with patch.object(fund_manager, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_approval
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.approval.fund_manager_agent.AssistantAgent', return_value=mock_assistant):
                result = await fund_manager.run(
                    trade_intent=oversized_trade,
                    risk_debate_outcome=oversized_debate,
                    portfolio_state=healthy_portfolio_state,
                    upcoming_events=upcoming_events_none,
                    symbol="EURUSD"
                )

        assert result.decision == ApprovalDecision.MODIFY
        assert len(result.modifications) > 0
        assert result.approved_position_size < oversized_debate["final_position_size"]

    @pytest.mark.asyncio
    async def test_run_reject_excessive_risk(
        self,
        fund_manager,
        healthy_portfolio_state,
        upcoming_events_none
    ):
        """Test REJECT decision for excessive risk."""
        excessive_risk_trade = {
            "direction": "LONG",
            "conviction": 0.60,
            "rationale": "Speculative setup",
            "key_factors": ["Potential breakout"],
            "risk_assessment": "High risk"
        }
        excessive_risk_debate = {
            "final_position_size": 5.0,
            "final_risk_percentage": 8.0,  # Exceeds 5% limit
            "consensus_reached": False,
            "consensus_adjustment": 1.5,
            "key_warnings": ["Excessive risk", "Low conviction"]
        }

        mock_approval = FundManagerApproval(
            decision=ApprovalDecision.REJECT,
            rationale=(
                "Trade rejected due to excessive account risk. "
                "Requested 8.0% risk exceeds hard limit of 5.0%. "
                "Additionally, portfolio would reach 13% total risk, "
                "approaching the 15% maximum. Conviction is only moderate (0.60). "
                "Risk/reward does not justify the exposure. "
                "Capital preservation is paramount."
            ),
            approved_position_size=None,
            approved_risk_percentage=None,
            modifications=[],
            rejection_reason=RejectionReason.EXCESSIVE_RISK,
            rejection_details=[
                "Account risk 8.0% exceeds max 5.0%",
                "Total portfolio risk would reach 13%",
                "Moderate conviction insufficient for high risk"
            ],
            portfolio_risk_after_trade=13.0,
            correlation_check_passed=True,
            correlated_positions_count=1,
            event_risk_present=False,
            hard_limits_passed=False,
            violated_limits=["max_account_risk_percent (8.0% > 5.0%)"],
            trade_quality_score=0.35,
            quality_concerns=["Excessive risk", "Low conviction"],
            confidence=0.90,
            recommended_action_timing="do_not_trade",
            timestamp=datetime.utcnow().isoformat(),
            metadata={}
        )

        with patch.object(fund_manager, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_approval
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.approval.fund_manager_agent.AssistantAgent', return_value=mock_assistant):
                result = await fund_manager.run(
                    trade_intent=excessive_risk_trade,
                    risk_debate_outcome=excessive_risk_debate,
                    portfolio_state=healthy_portfolio_state,
                    upcoming_events=upcoming_events_none,
                    symbol="EURUSD"
                )

        assert result.decision == ApprovalDecision.REJECT
        assert result.rejection_reason == RejectionReason.EXCESSIVE_RISK
        assert result.hard_limits_passed is False
        assert len(result.violated_limits) > 0

    @pytest.mark.asyncio
    async def test_run_reject_event_risk(
        self,
        fund_manager,
        clean_trade_intent,
        risk_debate_outcome_approved,
        healthy_portfolio_state
    ):
        """Test REJECT decision for imminent event risk."""
        upcoming_events = [
            {
                "title": "FOMC Rate Decision",
                "datetime": "2025-12-06T14:00:00Z",
                "impact": "HIGH"
            }
        ]

        mock_approval = FundManagerApproval(
            decision=ApprovalDecision.REJECT,
            rationale=(
                "Trade rejected due to event risk. FOMC Rate Decision in 2 hours "
                "creates extreme volatility risk. Historical data shows 2-3% moves "
                "on FOMC announcements with significant slippage. "
                "Stop loss may not execute at intended price. "
                "Recommend waiting until after event for better risk control."
            ),
            approved_position_size=None,
            approved_risk_percentage=None,
            modifications=[],
            rejection_reason=RejectionReason.EVENT_RISK,
            rejection_details=[
                "FOMC Rate Decision within 24 hours",
                "High-impact event creates unpredictable volatility",
                "Slippage and gap risk unacceptable"
            ],
            portfolio_risk_after_trade=7.0,
            correlation_check_passed=True,
            correlated_positions_count=1,
            event_risk_present=True,
            event_risk_description="FOMC Rate Decision at 2025-12-06T14:00:00Z (Impact: HIGH)",
            hard_limits_passed=False,
            violated_limits=["event_risk_veto_hours (event within 24h)"],
            trade_quality_score=0.50,
            quality_concerns=["Event risk", "Timing inappropriate"],
            confidence=0.85,
            recommended_action_timing="after_event",
            timestamp=datetime.utcnow().isoformat(),
            metadata={}
        )

        with patch.object(fund_manager, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_approval
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.approval.fund_manager_agent.AssistantAgent', return_value=mock_assistant):
                result = await fund_manager.run(
                    trade_intent=clean_trade_intent,
                    risk_debate_outcome=risk_debate_outcome_approved,
                    portfolio_state=healthy_portfolio_state,
                    upcoming_events=upcoming_events,
                    symbol="EURUSD"
                )

        assert result.decision == ApprovalDecision.REJECT
        assert result.rejection_reason == RejectionReason.EVENT_RISK
        assert result.event_risk_present is True

    @pytest.mark.asyncio
    async def test_run_exception_handling(
        self,
        fund_manager,
        clean_trade_intent,
        risk_debate_outcome_approved,
        healthy_portfolio_state,
        upcoming_events_none
    ):
        """Test exception handling during LLM call."""
        with patch.object(fund_manager, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_assistant.on_messages.side_effect = Exception("LLM API error")

            with patch('src.agents.approval.fund_manager_agent.AssistantAgent', return_value=mock_assistant):
                with pytest.raises(Exception, match="LLM API error"):
                    await fund_manager.run(
                        trade_intent=clean_trade_intent,
                        risk_debate_outcome=risk_debate_outcome_approved,
                        portfolio_state=healthy_portfolio_state,
                        upcoming_events=upcoming_events_none,
                        symbol="EURUSD"
                    )


class TestFundManagerAgentPromptBuilding:
    """Test prompt building logic."""

    def test_build_evaluation_prompt(
        self,
        fund_manager,
        clean_trade_intent,
        risk_debate_outcome_approved,
        healthy_portfolio_state,
        upcoming_events_none
    ):
        """Test evaluation prompt construction."""
        prompt = fund_manager._build_evaluation_prompt(
            trade_intent=clean_trade_intent,
            risk_debate_outcome=risk_debate_outcome_approved,
            portfolio_state=healthy_portfolio_state,
            upcoming_events=upcoming_events_none,
            symbol="EURUSD"
        )

        # Verify critical information is included
        assert "EURUSD" in prompt
        assert "0.80" in prompt or "0.8" in prompt  # Conviction
        assert "1.2" in prompt  # Final position size
        assert "2.0" in prompt or "2.00" in prompt  # Final risk percentage
        assert "5.0" in prompt or "5.00" in prompt  # Portfolio risk
        assert "APPROVE" in prompt  # Decision options
        assert "MODIFY" in prompt
        assert "REJECT" in prompt
        assert "Hard Limits" in prompt  # Must check limits
        assert "FundManagerApproval" in prompt  # Expected output

    def test_build_prompt_with_events(
        self,
        fund_manager,
        clean_trade_intent,
        risk_debate_outcome_approved,
        healthy_portfolio_state
    ):
        """Test prompt includes upcoming events."""
        events = [
            {"title": "NFP", "datetime": "2025-12-06T13:30:00Z", "impact": "HIGH"},
            {"title": "GDP", "datetime": "2025-12-07T08:30:00Z", "impact": "MEDIUM"}
        ]

        prompt = fund_manager._build_evaluation_prompt(
            trade_intent=clean_trade_intent,
            risk_debate_outcome=risk_debate_outcome_approved,
            portfolio_state=healthy_portfolio_state,
            upcoming_events=events,
            symbol="EURUSD"
        )

        assert "NFP" in prompt
        assert "GDP" in prompt
        assert "HIGH" in prompt


class TestFundManagerAgentHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, fund_manager):
        """Test successful health check."""
        with patch.object(fund_manager, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            result = await fund_manager.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, fund_manager):
        """Test failed health check."""
        with patch.object(fund_manager, '_create_model_client') as mock_client_factory:
            mock_client_factory.side_effect = Exception("Connection error")

            result = await fund_manager.health_check()
            assert result is False


class TestFundManagerAgentEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_portfolio_in_drawdown(
        self,
        fund_manager,
        clean_trade_intent,
        risk_debate_outcome_approved,
        upcoming_events_none
    ):
        """Test handling of portfolio in drawdown."""
        drawdown_portfolio = {
            "total_risk_percentage": 8.0,
            "open_positions_count": 3,
            "recent_pnl": -12000.0,  # -12% drawdown
            "available_capacity_pct": 40.0
        }

        mock_approval = FundManagerApproval(
            decision=ApprovalDecision.REJECT,
            rationale=(
                "Portfolio is in significant drawdown (-12%). "
                "Capital preservation is paramount. "
                "Current risk exposure at 8% is already high. "
                "Need to reduce risk, not add to it. "
                "Recommend waiting for portfolio recovery before new trades."
            ),
            approved_position_size=None,
            approved_risk_percentage=None,
            modifications=[],
            rejection_reason=RejectionReason.DRAWDOWN_PROTECTION,
            rejection_details=["Portfolio in 12% drawdown", "Risk exposure already at 8%"],
            portfolio_risk_after_trade=10.0,
            correlation_check_passed=True,
            correlated_positions_count=2,
            event_risk_present=False,
            hard_limits_passed=False,
            violated_limits=["Portfolio drawdown protection triggered"],
            trade_quality_score=0.45,
            quality_concerns=["Portfolio in drawdown"],
            confidence=0.85,
            recommended_action_timing="do_not_trade",
            timestamp=datetime.utcnow().isoformat(),
            metadata={}
        )

        with patch.object(fund_manager, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_approval
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.approval.fund_manager_agent.AssistantAgent', return_value=mock_assistant):
                result = await fund_manager.run(
                    trade_intent=clean_trade_intent,
                    risk_debate_outcome=risk_debate_outcome_approved,
                    portfolio_state=drawdown_portfolio,
                    upcoming_events=upcoming_events_none,
                    symbol="EURUSD"
                )

        assert result.decision == ApprovalDecision.REJECT
        assert result.rejection_reason == RejectionReason.DRAWDOWN_PROTECTION

    @pytest.mark.asyncio
    async def test_excessive_correlation(
        self,
        fund_manager,
        clean_trade_intent,
        risk_debate_outcome_approved,
        upcoming_events_none
    ):
        """Test rejection due to correlation limit."""
        correlated_portfolio = {
            "total_risk_percentage": 6.0,
            "open_positions_count": 4,  # 3 EUR pairs + this would be 4th
            "recent_pnl": 2000.0,
            "available_capacity_pct": 60.0
        }

        mock_approval = FundManagerApproval(
            decision=ApprovalDecision.REJECT,
            rationale=(
                "Portfolio already has 3 highly correlated EUR positions. "
                "Adding EURUSD would exceed max_correlated_positions limit of 3. "
                "Excessive concentration in single currency creates systemic risk. "
                "One adverse EUR event would impact all positions simultaneously. "
                "Recommend diversifying into uncorrelated assets."
            ),
            approved_position_size=None,
            approved_risk_percentage=None,
            modifications=[],
            rejection_reason=RejectionReason.CORRELATION_LIMIT,
            rejection_details=[
                "Already 3 EUR pairs in portfolio",
                "Would exceed max_correlated_positions limit",
                "Currency concentration risk"
            ],
            portfolio_risk_after_trade=8.0,
            correlation_check_passed=False,
            correlated_positions_count=3,
            max_correlated_positions=3,
            event_risk_present=False,
            hard_limits_passed=False,
            violated_limits=["max_correlated_positions (4 > 3)"],
            trade_quality_score=0.55,
            quality_concerns=["Correlation limit", "Concentration risk"],
            confidence=0.90,
            recommended_action_timing="do_not_trade",
            timestamp=datetime.utcnow().isoformat(),
            metadata={}
        )

        with patch.object(fund_manager, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_approval
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.approval.fund_manager_agent.AssistantAgent', return_value=mock_assistant):
                result = await fund_manager.run(
                    trade_intent=clean_trade_intent,
                    risk_debate_outcome=risk_debate_outcome_approved,
                    portfolio_state=correlated_portfolio,
                    upcoming_events=upcoming_events_none,
                    symbol="EURUSD"
                )

        assert result.decision == ApprovalDecision.REJECT
        assert result.rejection_reason == RejectionReason.CORRELATION_LIMIT
        assert result.correlation_check_passed is False

    @pytest.mark.asyncio
    async def test_poor_quality_score(
        self,
        fund_manager,
        risk_debate_outcome_approved,
        healthy_portfolio_state,
        upcoming_events_none
    ):
        """Test rejection due to poor trade quality."""
        poor_quality_trade = {
            "direction": "LONG",
            "conviction": 0.35,  # Very low
            "rationale": "Weak setup with unclear edge",
            "key_factors": ["Hoping for bounce"],
            "risk_assessment": "Uncertain"
        }

        mock_approval = FundManagerApproval(
            decision=ApprovalDecision.REJECT,
            rationale=(
                "Trade quality score 0.30 is below minimum threshold of 0.40. "
                "Very low conviction (0.35) indicates weak edge. "
                "Rationale lacks concrete analysis. "
                "Key factors are vague and hope-based. "
                "This does not meet institutional trading standards. "
                "Only take trades with clear statistical edge."
            ),
            approved_position_size=None,
            approved_risk_percentage=None,
            modifications=[],
            rejection_reason=RejectionReason.QUALITY_CONCERNS,
            rejection_details=[
                "Trade quality 0.30 < minimum 0.40",
                "Very low conviction (0.35)",
                "Vague rationale and factors",
                "No clear statistical edge"
            ],
            portfolio_risk_after_trade=7.0,
            correlation_check_passed=True,
            correlated_positions_count=1,
            event_risk_present=False,
            hard_limits_passed=False,
            violated_limits=["min_trade_quality_score (0.30 < 0.40)"],
            trade_quality_score=0.30,
            quality_concerns=[
                "Below minimum quality threshold",
                "Low conviction",
                "Weak analysis"
            ],
            confidence=0.95,
            recommended_action_timing="do_not_trade",
            timestamp=datetime.utcnow().isoformat(),
            metadata={}
        )

        with patch.object(fund_manager, '_create_model_client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client

            mock_assistant = AsyncMock()
            mock_response = Mock()
            mock_response.chat_message.content = mock_approval
            mock_assistant.on_messages.return_value = mock_response

            with patch('src.agents.approval.fund_manager_agent.AssistantAgent', return_value=mock_assistant):
                result = await fund_manager.run(
                    trade_intent=poor_quality_trade,
                    risk_debate_outcome=risk_debate_outcome_approved,
                    portfolio_state=healthy_portfolio_state,
                    upcoming_events=upcoming_events_none,
                    symbol="EURUSD"
                )

        assert result.decision == ApprovalDecision.REJECT
        assert result.rejection_reason == RejectionReason.QUALITY_CONCERNS
        assert result.trade_quality_score < 0.4
