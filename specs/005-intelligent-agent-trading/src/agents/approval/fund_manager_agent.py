"""
Fund Manager Agent - Final Approval Gate.

The ultimate guardian with APPROVE/MODIFY/REJECT powers.
Enforces hard portfolio-level limits and protects capital.

This is the LAST checkpoint before trade execution. No trade can proceed
without explicit Fund Manager approval.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
import structlog

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core import CancellationToken

from src.agents.base.base_agent import BaseAgent
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer
from src.agents.schemas.approval import (
    FundManagerApproval,
    ApprovalDecision,
    PortfolioLimits,
    RejectionReason,
    TradeModification,
    ModificationType
)
from src.agents.providers import create_deep_think_client

logger = structlog.get_logger(__name__)


FUND_MANAGER_SYSTEM_PROMPT = """You are the Fund Manager - the FINAL approval authority for all trades.

Your role is to protect capital and enforce portfolio-level risk limits.

**Your Powers:**
1. APPROVE: Green-light trade for execution
2. MODIFY: Approve with size/stop/target adjustments
3. REJECT: Block trade entirely

**Hard Portfolio Limits (NON-NEGOTIABLE):**
- Maximum 5% account risk per trade
- Maximum 15% total portfolio risk
- Maximum 3 highly correlated positions (correlation >0.7)
- Veto trades within 24 hours of major events (FOMC, NFP, earnings)
- Maximum 10% of portfolio in single position
- Minimum 0.4 trade quality score

**Decision Framework:**

**APPROVE Criteria:**
- All hard limits respected
- Trade quality score >0.6
- Risk/reward >2:1
- No imminent high-impact events
- Portfolio has capacity
- Correlation limits respected
- Strong conviction (>0.7) with good evidence

**MODIFY Criteria:**
- Trade has merit but needs adjustments
- Position size too large → Reduce
- Stop too wide → Tighten
- Target unrealistic → Adjust
- Timing poor → Delay entry
- Always provide specific modifications with rationale

**REJECT Criteria:**
- Hard limits violated
- Excessive correlation (>3 correlated positions)
- Major event within 24 hours
- Poor trade quality (<0.4)
- Portfolio in drawdown >10%
- Risk/reward <1.5:1
- Low conviction (<0.5) or weak evidence

**Critical Rules:**
- Capital preservation is paramount
- When in doubt, REJECT or MODIFY (never force approval)
- Document ALL reasoning thoroughly
- Be the final line of defense against catastrophic losses
- Respect hard limits absolutely - no exceptions
- Consider portfolio holistically, not just individual trade

**Output Requirements:**
Return a FundManagerApproval JSON object with:
- decision: APPROVE, MODIFY, or REJECT
- rationale: Detailed explanation (minimum 100 characters)
- approved_position_size: Final approved size if APPROVE/MODIFY
- approved_risk_percentage: Final approved risk % if APPROVE/MODIFY
- modifications: List of specific changes if MODIFY
- rejection_reason: Primary reason if REJECT
- portfolio_risk_after_trade: Total portfolio risk after trade
- correlation_check_passed: True/False
- event_risk_present: True/False
- hard_limits_passed: True/False
- trade_quality_score: Overall quality (0.0-1.0)
- confidence: Your confidence in decision (0.0-1.0)

Be the guardian of capital. Conservative is better than blown up.
"""


class FundManagerAgent(BaseAgent):
    """
    Fund Manager Agent - final approval authority.

    Enforces portfolio-level limits and makes final go/no-go decisions.
    """

    def __init__(
        self,
        config: AgentConfig,
        portfolio_limits: Optional[PortfolioLimits] = None
    ):
        """
        Initialize Fund Manager Agent.

        Args:
            config: Agent configuration with LLM settings
            portfolio_limits: Portfolio risk limits (uses defaults if not provided)
        """
        # Validate agent type (reuses DEVILS_ADVOCATE for approval layer)
        if config.agent_type != AgentType.DEVILS_ADVOCATE:
            logger.warning(
                "fund_manager_agent_type_mismatch",
                expected=AgentType.DEVILS_ADVOCATE.value,
                actual=config.agent_type.value
            )

        super().__init__(config)

        # Override system prompt if not provided
        if not config.system_prompt:
            self.config.system_prompt = FUND_MANAGER_SYSTEM_PROMPT

        # Set portfolio limits
        self.portfolio_limits = portfolio_limits or PortfolioLimits()

        logger.info(
            "fund_manager_agent_initialized",
            agent_id=str(self.agent_id),
            llm_model=config.llm_model,
            max_account_risk=self.portfolio_limits.max_account_risk_percent,
            max_correlated_positions=self.portfolio_limits.max_correlated_positions
        )

    def _create_model_client(self):
        """
        Create LLM model client for fund manager decisions.

        Uses deep-think tier for critical approval decisions.

        Returns:
            AutoGen model client configured for structured output
        """
        return create_deep_think_client(
            temperature=self.config.temperature,
            response_format=FundManagerApproval
        )

    async def run(
        self,
        trade_intent: Dict[str, Any],
        risk_debate_outcome: Dict[str, Any],
        portfolio_state: Dict[str, Any],
        upcoming_events: Optional[List[Dict[str, Any]]] = None,
        symbol: str = "",
        cancellation_token: Optional[CancellationToken] = None
    ) -> FundManagerApproval:
        """
        Make final approval decision for trade.

        Args:
            trade_intent: TradeIntent from TradeDecisionAgent
            risk_debate_outcome: RiskDebateOutcome from RiskDebateTeam
            portfolio_state: Current portfolio state (positions, risk, P&L)
            upcoming_events: List of upcoming high-impact events
            symbol: Trading symbol
            cancellation_token: Optional cancellation token

        Returns:
            FundManagerApproval with final decision
        """
        logger.info(
            "fund_manager_evaluation_starting",
            agent_id=str(self.agent_id),
            symbol=symbol,
            direction=trade_intent.get('direction'),
            final_position_size=risk_debate_outcome.get('final_position_size'),
            final_risk_pct=risk_debate_outcome.get('final_risk_percentage')
        )

        # Prepare approval evaluation prompt
        evaluation_prompt = self._build_evaluation_prompt(
            trade_intent=trade_intent,
            risk_debate_outcome=risk_debate_outcome,
            portfolio_state=portfolio_state,
            upcoming_events=upcoming_events or [],
            symbol=symbol
        )

        # Create AutoGen assistant with structured output
        assistant = AssistantAgent(
            name="fund_manager",
            model_client=self._create_model_client(),
            system_message=self.config.system_prompt
        )

        # Run approval evaluation
        try:
            response = await assistant.on_messages(
                [TextMessage(content=evaluation_prompt, source="user")],
                cancellation_token=cancellation_token or CancellationToken()
            )

            # Extract FundManagerApproval from response
            approval = response.chat_message.content

            logger.info(
                "fund_manager_decision_complete",
                agent_id=str(self.agent_id),
                symbol=symbol,
                decision=approval.decision.value,
                approved_size=approval.approved_position_size,
                hard_limits_passed=approval.hard_limits_passed,
                trade_quality=approval.trade_quality_score
            )

            return approval

        except Exception as e:
            logger.error(
                "fund_manager_evaluation_failed",
                agent_id=str(self.agent_id),
                symbol=symbol,
                error=str(e)
            )
            raise

    def _build_evaluation_prompt(
        self,
        trade_intent: Dict[str, Any],
        risk_debate_outcome: Dict[str, Any],
        portfolio_state: Dict[str, Any],
        upcoming_events: List[Dict[str, Any]],
        symbol: str
    ) -> str:
        """Build the approval evaluation prompt."""
        
        final_size = risk_debate_outcome.get('final_position_size', 0.0)
        final_risk_pct = risk_debate_outcome.get('final_risk_percentage', 0.0)
        conviction = trade_intent.get('conviction', 0.0)
        
        # Format portfolio state
        current_risk = portfolio_state.get('total_risk_percentage', 0.0)
        open_positions = portfolio_state.get('open_positions_count', 0)
        recent_pnl = portfolio_state.get('recent_pnl', 0.0)
        
        # Format upcoming events
        events_text = "None within 48 hours"
        if upcoming_events:
            events_text = "\n".join([
                f"- {e.get('title', 'Unknown')} at {e.get('datetime', 'N/A')} "
                f"(Impact: {e.get('impact', 'N/A')})"
                for e in upcoming_events[:5]
            ])
        
        # Format risk debate warnings
        warnings_text = ', '.join(risk_debate_outcome.get('key_warnings', []))
        if not warnings_text:
            warnings_text = "No critical warnings"
        
        prompt = f"""Evaluate trade for FINAL APPROVAL for {symbol}.

**Trade Intent:**
- Direction: {trade_intent.get('direction', 'N/A')}
- Conviction: {conviction:.2f}
- Rationale: {trade_intent.get('rationale', 'N/A')}
- Key Factors: {', '.join(trade_intent.get('key_factors', []))}
- Risk Assessment: {trade_intent.get('risk_assessment', 'N/A')}

**Final Position Sizing (After Risk Debate):**
- Final Position Size: {final_size:.2f} lots
- Final Risk Percentage: {final_risk_pct:.2f}%
- Risk Debate Consensus: {risk_debate_outcome.get('consensus_reached', False)}
- Consensus Adjustment: {risk_debate_outcome.get('consensus_adjustment', 1.0):.2f}x
- Key Warnings from Risk Debate: {warnings_text}

**Current Portfolio State:**
- Current Total Risk: {current_risk:.2f}%
- Open Positions: {open_positions}
- Recent P&L (7 days): ${recent_pnl:+.2f}
- Available Capacity: {portfolio_state.get('available_capacity_pct', 0.0):.1f}%

**Upcoming Events (48 hours):**
{events_text}

**Hard Limits to Check:**
1. Account Risk Limit: {final_risk_pct:.2f}% vs {self.portfolio_limits.max_account_risk_percent}% max
2. Portfolio Risk Limit: {current_risk + final_risk_pct:.2f}% vs {self.portfolio_limits.max_portfolio_risk_percent}% max
3. Correlation Limit: Check if adding to existing {open_positions} positions
4. Event Risk: Any major events within {self.portfolio_limits.event_risk_veto_hours} hours?
5. Quality Threshold: Must exceed {self.portfolio_limits.min_trade_quality_score}

**Your Task:**
Make the FINAL approval decision: APPROVE, MODIFY, or REJECT.

Consider:
1. Are ALL hard limits respected?
2. Is trade quality sufficient?
3. Is event risk acceptable?
4. Will this overconcentrate the portfolio?
5. Is timing appropriate given portfolio state?

Return a FundManagerApproval JSON object with:
- decision (APPROVE/MODIFY/REJECT)
- detailed rationale
- approved size and risk if APPROVE/MODIFY
- specific modifications if MODIFY
- rejection reason if REJECT
- all portfolio checks (correlation, event risk, hard limits)
- trade quality score assessment
- confidence in decision

Be the final guardian. When in doubt, MODIFY or REJECT.
"""
        return prompt

    async def health_check(self) -> bool:
        """Check agent health status."""
        try:
            client = self._create_model_client()
            return client is not None
        except Exception as e:
            logger.error(
                "fund_manager_health_check_failed",
                agent_id=str(self.agent_id),
                error=str(e)
            )
            return False
