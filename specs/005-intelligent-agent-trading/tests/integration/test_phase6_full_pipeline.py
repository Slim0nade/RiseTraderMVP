"""
Integration tests for Phase 6: Full Adversarial Debate & Safety Gates Pipeline.

Tests the complete flow:
1. Analysis Team → Bull/Bear Debate
2. Bull/Bear Debate → TradeDecisionAgent → TradeIntent
3. TradeIntent + Position Sizing → Risk Tolerance Debate (3-way)
4. Risk Tolerance Debate → Fund Manager Approval

This validates that all Phase 6 components integrate correctly end-to-end.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier
from src.agents.decision.trade_decision_agent import TradeDecisionAgent
from src.agents.teams.risk_debate_team import RiskDebateTeam
from src.agents.approval.fund_manager_agent import FundManagerAgent
from src.agents.schemas.debate import (
    DebateOutcome, BullCase, BearCase, EvidencePoint,
    RiskPerspective, RiskTolerance, RiskDebateOutcome
)
from src.agents.schemas.trade_decision import TradeIntent, TradeDirection
from src.agents.schemas.approval import (
    FundManagerApproval, ApprovalDecision, PortfolioLimits
)


@pytest.fixture
def trade_decision_config():
    """Trade decision agent config."""
    return AgentConfig(
        agent_type=AgentType.DECISION_MAKER,
        layer=AgentLayer.DECISION,
        llm_tier=LLMTier.DEEP_THINK,
        llm_model="deepseek-reasoner:14b",
        temperature=0.2,
        max_tokens=3000
    )


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
def fund_manager_config():
    """Fund manager config."""
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
    """Portfolio limits."""
    return PortfolioLimits(
        max_account_risk_percent=5.0,
        max_portfolio_risk_percent=15.0,
        max_correlated_positions=3,
        event_risk_veto_hours=24,
        min_trade_quality_score=0.4
    )


@pytest.fixture
def bull_bear_debate_outcome():
    """Sample bull/bear debate outcome."""
    return DebateOutcome(
        bull_case=BullCase(
            direction="LONG",
            conviction=0.75,
            primary_thesis="Strong uptrend with technical and fundamental support",
            supporting_evidence=[
                EvidencePoint(
                    claim="Price above 50-day MA",
                    source="TechnicalReport",
                    strength=0.8
                ),
                EvidencePoint(
                    claim="Positive GDP forecast",
                    source="FundamentalReport",
                    strength=0.7
                )
            ],
            risk_factors=["Minor resistance at 1.1050"],
            target_price=1.1200,
            invalidation_level=1.0850,
            time_horizon_hours=48,
            confidence=0.75,
            metadata={}
        ),
        bear_case=BearCase(
            direction="SHORT_BIAS",
            conviction=0.45,
            primary_thesis="Some overhead resistance but not strong enough to short",
            supporting_evidence=[
                EvidencePoint(
                    claim="RSI approaching overbought",
                    source="TechnicalReport",
                    strength=0.5
                )
            ],
            risk_factors=["Strong bullish momentum"],
            target_price=1.0900,
            invalidation_level=1.1100,
            time_horizon_hours=48,
            confidence=0.45,
            metadata={}
        ),
        consensus_direction="LONG",
        key_disagreements=["Bull expects 1.1200, bear expects resistance"],
        consolidated_risks=["Minor resistance at 1.1050"],
        debate_quality_score=0.80,
        timestamp=datetime.utcnow().isoformat(),
        metadata={"symbol": "EURUSD"}
    )


@pytest.fixture
def position_size_decision():
    """Position sizing decision."""
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
        "stop_loss_price": 1.0850,
        "distance_pips": 50,
        "confidence": 0.80
    }


@pytest.fixture
def portfolio_state():
    """Portfolio state."""
    return {
        "total_risk_percentage": 5.0,
        "open_positions_count": 2,
        "recent_pnl": 3000.0,
        "available_capacity_pct": 70.0
    }


class TestPhase6FullPipelineApproval:
    """Test full pipeline resulting in APPROVE decision."""

    @pytest.mark.asyncio
    async def test_clean_trade_full_approval_flow(
        self,
        trade_decision_config,
        risky_config,
        neutral_config,
        safe_config,
        fund_manager_config,
        portfolio_limits,
        bull_bear_debate_outcome,
        position_size_decision,
        stop_loss_decision,
        portfolio_state
    ):
        """
        Test complete flow for a clean trade that should be approved.

        Flow:
        1. Bull/Bear Debate → LONG with 0.75 conviction
        2. TradeDecisionAgent → TradeIntent (LONG, high conviction)
        3. Risk Debate → Consensus 1.0x (no adjustment)
        4. Fund Manager → APPROVE
        """
        # Step 1: Create agents
        trade_decision_agent = TradeDecisionAgent(trade_decision_config)
        risk_debate_team = RiskDebateTeam(risky_config, neutral_config, safe_config)
        fund_manager = FundManagerAgent(fund_manager_config, portfolio_limits)

        # Step 2: Mock TradeDecisionAgent output (from debate)
        trade_intent = TradeIntent(
            direction=TradeDirection.LONG,
            conviction=0.75,
            rationale=(
                "Bull case dominates with 0.75 conviction vs bear 0.45. "
                "Strong technical (above 50MA) and fundamental support (GDP). "
                "Clear invalidation at 1.0850. Target 1.1200 offers 3:1 R:R."
            ),
            key_factors=[
                "Price above 50-day MA (strength 0.8)",
                "Positive GDP forecast (strength 0.7)",
                "Clear invalidation level",
                "3:1 risk/reward ratio"
            ],
            risk_assessment=(
                "Minor resistance at 1.1050 acknowledged. "
                "Tight stop at 1.0850 limits downside to 50 pips. "
                "Strong bullish momentum reduces risk."
            ),
            conflict_resolution="Bull case significantly stronger than bear case",
            timestamp=datetime.utcnow().isoformat(),
            metadata={"symbol": "EURUSD"}
        )

        # Step 3: Mock Risk Debate Team output (consensus)
        risky_perspective = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.1,
            reasoning="High conviction justifies slight increase",
            key_factors=["High conviction", "Good R:R"],
            confidence=0.75
        )
        neutral_perspective = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=1.0,
            reasoning="Baseline Kelly calculation is sound",
            key_factors=["Valid inputs"],
            confidence=0.80
        )
        safe_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=0.95,
            reasoning="Some minor concerns but acceptable",
            key_factors=["Minor resistance present"],
            confidence=0.70
        )

        risk_debate_outcome = RiskDebateOutcome(
            risky_perspective=risky_perspective,
            neutral_perspective=neutral_perspective,
            safe_perspective=safe_perspective,
            consensus_adjustment=1.02,  # Simple average (within 20%)
            consensus_reached=True,
            final_position_size=1.53,  # 1.5 * 1.02
            final_risk_percentage=2.04,  # 2.0 * 1.02
            divergence_rationale=None,
            key_warnings=[],
            timestamp=datetime.utcnow().isoformat(),
            metadata={"symbol": "EURUSD"}
        )

        # Step 4: Mock Fund Manager output (APPROVE)
        fund_manager_approval = FundManagerApproval(
            decision=ApprovalDecision.APPROVE,
            rationale=(
                "Trade approved for execution. All criteria met: "
                "High conviction (0.75), appropriate risk (2.04%), "
                "portfolio has capacity (5% current + 2.04% = 7.04% < 15% max), "
                "no event risk, hard limits respected. "
                "Quality score 0.78 exceeds minimum. "
                "Risk/reward 3:1 is favorable. Green light to execute."
            ),
            approved_position_size=1.53,
            approved_risk_percentage=2.04,
            modifications=[],
            rejection_reason=None,
            portfolio_risk_after_trade=7.04,
            correlation_check_passed=True,
            correlated_positions_count=1,
            event_risk_present=False,
            hard_limits_passed=True,
            violated_limits=[],
            trade_quality_score=0.78,
            quality_concerns=[],
            confidence=0.85,
            recommended_action_timing="immediate",
            timestamp=datetime.utcnow().isoformat(),
            metadata={"symbol": "EURUSD"}
        )

        # Step 5: Patch all agent calls and run full flow
        with patch.object(trade_decision_agent, 'decide_from_debate', return_value=trade_intent):
            with patch.object(risk_debate_team, 'run_debate', return_value=risk_debate_outcome):
                with patch.object(fund_manager, 'run', return_value=fund_manager_approval):
                    # Execute full pipeline
                    # 1. Trade Decision from Debate
                    final_trade_intent = await trade_decision_agent.decide_from_debate(
                        debate_outcome=bull_bear_debate_outcome,
                        symbol="EURUSD",
                        current_price=1.0900
                    )

                    # 2. Risk Tolerance Debate
                    risk_outcome = await risk_debate_team.run_debate(
                        trade_intent=final_trade_intent.model_dump(),
                        position_size_decision=position_size_decision,
                        stop_loss_decision=stop_loss_decision,
                        account_balance=100000.0,
                        symbol="EURUSD"
                    )

                    # 3. Fund Manager Approval
                    final_approval = await fund_manager.run(
                        trade_intent=final_trade_intent.model_dump(),
                        risk_debate_outcome=risk_outcome.model_dump(),
                        portfolio_state=portfolio_state,
                        upcoming_events=[],
                        symbol="EURUSD"
                    )

        # Step 6: Verify final outcome
        assert final_approval.decision == ApprovalDecision.APPROVE
        assert final_approval.approved_position_size == 1.53
        assert final_approval.approved_risk_percentage == 2.04
        assert final_approval.hard_limits_passed is True
        assert final_approval.trade_quality_score > 0.4
        assert final_approval.portfolio_risk_after_trade < 15.0

        # Verify full chain maintained integrity
        assert final_trade_intent.direction == TradeDirection.LONG
        assert risk_outcome.consensus_reached is True
        assert risk_outcome.final_position_size > 0


class TestPhase6FullPipelineModify:
    """Test full pipeline resulting in MODIFY decision."""

    @pytest.mark.asyncio
    async def test_oversized_trade_modification_flow(
        self,
        trade_decision_config,
        risky_config,
        neutral_config,
        safe_config,
        fund_manager_config,
        portfolio_limits,
        bull_bear_debate_outcome,
        stop_loss_decision,
        portfolio_state
    ):
        """
        Test complete flow for oversized trade requiring modification.

        Flow:
        1. Bull/Bear Debate → LONG
        2. TradeDecisionAgent → TradeIntent
        3. Risk Debate → Divergence (risky wants increase, safe wants cut)
        4. Fund Manager → MODIFY (reduce size)
        """
        # Oversized position sizing
        oversized_position = {
            "position_size_lots": 3.0,
            "risk_percentage": 4.5,
            "kelly_fraction": 0.50,
            "win_rate": 0.60,
            "avg_win_loss_ratio": 2.0,
            "confidence": 0.65
        }

        trade_decision_agent = TradeDecisionAgent(trade_decision_config)
        risk_debate_team = RiskDebateTeam(risky_config, neutral_config, safe_config)
        fund_manager = FundManagerAgent(fund_manager_config, portfolio_limits)

        trade_intent = TradeIntent(
            direction=TradeDirection.LONG,
            conviction=0.70,
            rationale="Good setup but sizing may be aggressive",
            key_factors=["Technical breakout", "Volume support"],
            risk_assessment="Moderate risk but large size",
            timestamp=datetime.utcnow().isoformat(),
            metadata={}
        )

        # Risk debate with divergence
        risky_perspective = RiskPerspective(
            tolerance=RiskTolerance.RISKY,
            recommended_size_adjustment=1.2,
            reasoning="Conviction supports larger size",
            key_factors=["Good setup"],
            confidence=0.70
        )
        neutral_perspective = RiskPerspective(
            tolerance=RiskTolerance.NEUTRAL,
            recommended_size_adjustment=0.75,
            reasoning="Kelly fraction 0.50 too aggressive",
            key_factors=["Overoptimistic inputs"],
            confidence=0.75
        )
        safe_perspective = RiskPerspective(
            tolerance=RiskTolerance.SAFE,
            recommended_size_adjustment=0.5,
            reasoning="4.5% risk too high",
            key_factors=["Excessive risk"],
            confidence=0.85
        )

        # Safety-weighted consensus: (0.5*0.5) + (0.75*0.3) + (1.2*0.2) = 0.715
        risk_debate_outcome = RiskDebateOutcome(
            risky_perspective=risky_perspective,
            neutral_perspective=neutral_perspective,
            safe_perspective=safe_perspective,
            consensus_adjustment=0.715,
            consensus_reached=False,  # Divergent
            final_position_size=2.145,  # 3.0 * 0.715
            final_risk_percentage=3.22,  # 4.5 * 0.715
            divergence_rationale="Significant divergence: applying safety-weighted consensus",
            key_warnings=["Excessive risk", "Aggressive Kelly"],
            timestamp=datetime.utcnow().isoformat(),
            metadata={}
        )

        # Fund Manager MODIFY decision
        fund_manager_approval = FundManagerApproval(
            decision=ApprovalDecision.MODIFY,
            rationale=(
                "Trade has merit but requires further size reduction. "
                "Even after risk debate adjustment, 3.22% risk is high. "
                "Portfolio would reach 8.22% total risk. "
                "Recommend reducing to 1.5 lots (2.0% risk) for safety margin."
            ),
            approved_position_size=1.5,
            approved_risk_percentage=2.0,
            modifications=[
                TradeModification(
                    modification_type=ModificationType.REDUCE_SIZE,
                    current_value=2.145,
                    recommended_value=1.5,
                    rationale="Further reduce from 2.145 to 1.5 lots (2.0% risk)"
                )
            ],
            modification_summary="Reduce position size by 30% from debate outcome",
            rejection_reason=None,
            portfolio_risk_after_trade=7.0,
            correlation_check_passed=True,
            correlated_positions_count=1,
            event_risk_present=False,
            hard_limits_passed=False,
            violated_limits=["Approaching risk limits"],
            trade_quality_score=0.55,
            quality_concerns=["Risk near upper bound"],
            confidence=0.80,
            recommended_action_timing="immediate",
            timestamp=datetime.utcnow().isoformat(),
            metadata={}
        )

        with patch.object(trade_decision_agent, 'decide_from_debate', return_value=trade_intent):
            with patch.object(risk_debate_team, 'run_debate', return_value=risk_debate_outcome):
                with patch.object(fund_manager, 'run', return_value=fund_manager_approval):
                    final_trade_intent = await trade_decision_agent.decide_from_debate(
                        debate_outcome=bull_bear_debate_outcome,
                        symbol="EURUSD",
                        current_price=1.0900
                    )

                    risk_outcome = await risk_debate_team.run_debate(
                        trade_intent=final_trade_intent.model_dump(),
                        position_size_decision=oversized_position,
                        stop_loss_decision=stop_loss_decision,
                        account_balance=100000.0,
                        symbol="EURUSD"
                    )

                    final_approval = await fund_manager.run(
                        trade_intent=final_trade_intent.model_dump(),
                        risk_debate_outcome=risk_outcome.model_dump(),
                        portfolio_state=portfolio_state,
                        upcoming_events=[],
                        symbol="EURUSD"
                    )

        # Verify MODIFY decision
        assert final_approval.decision == ApprovalDecision.MODIFY
        assert len(final_approval.modifications) > 0
        assert final_approval.approved_position_size < oversized_position["position_size_lots"]
        assert final_approval.approved_risk_percentage < oversized_position["risk_percentage"]

        # Verify 2-layer reduction happened
        assert risk_outcome.consensus_reached is False  # Risk debate detected divergence
        assert final_approval.approved_position_size < risk_outcome.final_position_size  # FM further reduced


class TestPhase6FullPipelineReject:
    """Test full pipeline resulting in REJECT decision."""

    @pytest.mark.asyncio
    async def test_event_risk_rejection_flow(
        self,
        trade_decision_config,
        risky_config,
        neutral_config,
        safe_config,
        fund_manager_config,
        portfolio_limits,
        bull_bear_debate_outcome,
        position_size_decision,
        stop_loss_decision,
        portfolio_state
    ):
        """
        Test complete flow for trade rejected due to event risk.

        Flow:
        1. Bull/Bear Debate → LONG
        2. TradeDecisionAgent → TradeIntent
        3. Risk Debate → Consensus (trade looks fine)
        4. Fund Manager → REJECT (FOMC in 2 hours)
        """
        trade_decision_agent = TradeDecisionAgent(trade_decision_config)
        risk_debate_team = RiskDebateTeam(risky_config, neutral_config, safe_config)
        fund_manager = FundManagerAgent(fund_manager_config, portfolio_limits)

        trade_intent = TradeIntent(
            direction=TradeDirection.LONG,
            conviction=0.75,
            rationale="Strong setup but unaware of FOMC",
            key_factors=["Technical breakout"],
            risk_assessment="Normal risk",
            timestamp=datetime.utcnow().isoformat(),
            metadata={}
        )

        # Risk debate sees no issues
        risk_debate_outcome = RiskDebateOutcome(
            risky_perspective=RiskPerspective(
                tolerance=RiskTolerance.RISKY,
                recommended_size_adjustment=1.0,
                reasoning="Setup looks good",
                key_factors=["Valid"],
                confidence=0.75
            ),
            neutral_perspective=RiskPerspective(
                tolerance=RiskTolerance.NEUTRAL,
                recommended_size_adjustment=1.0,
                reasoning="Baseline acceptable",
                key_factors=["Valid"],
                confidence=0.80
            ),
            safe_perspective=RiskPerspective(
                tolerance=RiskTolerance.SAFE,
                recommended_size_adjustment=1.0,
                reasoning="No major concerns",
                key_factors=["Clean setup"],
                confidence=0.75
            ),
            consensus_adjustment=1.0,
            consensus_reached=True,
            final_position_size=1.5,
            final_risk_percentage=2.0,
            divergence_rationale=None,
            key_warnings=[],
            timestamp=datetime.utcnow().isoformat(),
            metadata={}
        )

        # Upcoming FOMC event
        upcoming_events = [
            {
                "title": "FOMC Rate Decision",
                "datetime": "2025-12-06T14:00:00Z",
                "impact": "HIGH"
            }
        ]

        # Fund Manager REJECT
        fund_manager_approval = FundManagerApproval(
            decision=ApprovalDecision.REJECT,
            rationale=(
                "Trade rejected due to imminent event risk. "
                "FOMC Rate Decision in 2 hours creates extreme volatility. "
                "Historical 2-3% moves with unpredictable slippage. "
                "Stop loss execution not guaranteed. "
                "Wait until after FOMC for stable conditions."
            ),
            approved_position_size=None,
            approved_risk_percentage=None,
            modifications=[],
            rejection_reason=RejectionReason.EVENT_RISK,
            rejection_details=[
                "FOMC Rate Decision within 24 hours",
                "Extreme volatility risk",
                "Slippage and gap risk"
            ],
            portfolio_risk_after_trade=7.0,
            correlation_check_passed=True,
            correlated_positions_count=1,
            event_risk_present=True,
            event_risk_description="FOMC Rate Decision at 2025-12-06T14:00:00Z (Impact: HIGH)",
            hard_limits_passed=False,
            violated_limits=["event_risk_veto_hours"],
            trade_quality_score=0.50,
            quality_concerns=["Event timing"],
            confidence=0.90,
            recommended_action_timing="after_event",
            timestamp=datetime.utcnow().isoformat(),
            metadata={}
        )

        with patch.object(trade_decision_agent, 'decide_from_debate', return_value=trade_intent):
            with patch.object(risk_debate_team, 'run_debate', return_value=risk_debate_outcome):
                with patch.object(fund_manager, 'run', return_value=fund_manager_approval):
                    final_trade_intent = await trade_decision_agent.decide_from_debate(
                        debate_outcome=bull_bear_debate_outcome,
                        symbol="EURUSD",
                        current_price=1.0900
                    )

                    risk_outcome = await risk_debate_team.run_debate(
                        trade_intent=final_trade_intent.model_dump(),
                        position_size_decision=position_size_decision,
                        stop_loss_decision=stop_loss_decision,
                        account_balance=100000.0,
                        symbol="EURUSD"
                    )

                    final_approval = await fund_manager.run(
                        trade_intent=final_trade_intent.model_dump(),
                        risk_debate_outcome=risk_outcome.model_dump(),
                        portfolio_state=portfolio_state,
                        upcoming_events=upcoming_events,
                        symbol="EURUSD"
                    )

        # Verify REJECT decision
        assert final_approval.decision == ApprovalDecision.REJECT
        assert final_approval.rejection_reason == RejectionReason.EVENT_RISK
        assert final_approval.event_risk_present is True
        assert final_approval.approved_position_size is None

        # Risk debate passed but Fund Manager overruled
        assert risk_outcome.consensus_reached is True
        assert final_approval.hard_limits_passed is False
