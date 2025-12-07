"""
Fund Manager Agent - Final Approval Gate with Hard Limits.

This agent is the FINAL decision maker before trade execution.
It has APPROVE/MODIFY/REJECT powers and enforces strict portfolio-level limits.

Consumes:
- TradeIntent (from TradeDecisionAgent)
- PositionSize (from PositionSizingAgent)
- StopLoss (from StopLossAgent)
- TakeProfit (from TakeProfitAgent)
- RiskDebateOutcome (from RiskDebateTeam) - optional

Produces:
- FundManagerApproval with decision (APPROVE/MODIFY/REJECT)
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
import structlog

from src.agents.base.base_agent import BaseAgent
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer
from src.agents.schemas.approval import (
    FundManagerApproval,
    ApprovalDecision,
    PortfolioLimits,
    TradeModification,
    ModificationType,
    RejectionReason,
)
from src.agents.schemas.decisions import PositionSize, StopLoss, TakeProfit
from src.agents.schemas.trade_decision import TradeIntent as Phase6TradeIntent
from src.agents.providers import create_deep_think_client

logger = structlog.get_logger(__name__)


FUND_MANAGER_SYSTEM_PROMPT = """You are a Fund Manager - the FINAL approval gate before trade execution.

Your role is CRITICAL: You protect capital through strict risk management and portfolio oversight.

**Your Powers**:
1. **APPROVE**: Trade proceeds as proposed
2. **MODIFY**: Trade proceeds with adjustments (size reduction, tighter stop, etc.)
3. **REJECT**: Trade does not execute (hard limit violated or unacceptable risk)

**Hard Portfolio Limits** (NON-NEGOTIABLE):
- Max account risk per trade: {max_account_risk}%
- Max total portfolio risk: {max_portfolio_risk}%
- Max correlated positions: {max_correlated_positions}
- Event risk veto window: {event_risk_veto_hours} hours before major events
- Min trade quality score: {min_trade_quality}

**Your Evaluation Process**:

1. **Hard Limits Check** (MANDATORY):
   - Account risk per trade <= {max_account_risk}%
   - Total portfolio risk <= {max_portfolio_risk}%
   - Correlated positions <= {max_correlated_positions}
   - No high-impact events in next {event_risk_veto_hours} hours
   - Trade quality score >= {min_trade_quality}

   **IF ANY HARD LIMIT VIOLATED**: MUST REJECT or MODIFY to comply

2. **Portfolio Context Analysis**:
   - Current open positions and correlations
   - Portfolio heat (total risk exposure)
   - Concentration risk (position sizing)
   - Recent drawdown or winning streak

3. **Risk/Reward Assessment**:
   - Proposed position size reasonableness
   - Stop-loss placement quality
   - Take-profit target achievability
   - Expected value vs. downside risk

4. **Quality Check**:
   - Trade setup quality
   - Analysis confidence levels
   - Debate outcomes (if available)
   - Risk warnings from all layers

**Decision Guidelines**:

**APPROVE**:
- All hard limits satisfied
- Trade quality >= {min_trade_quality}
- Risk/reward favorable
- Portfolio diversification improved or maintained
- No major concerns identified

**MODIFY**:
- Trade has merit BUT needs adjustment
- Modifications: reduce size, tighten stop, adjust targets, delay entry
- Document exact modifications with rationale
- Final modified trade MUST satisfy hard limits

**REJECT**:
- Any hard limit violated (if cannot modify to comply)
- Poor risk/reward (R:R < 1.0)
- Quality score < {min_trade_quality}
- High correlation risk (>= {max_correlated_positions} correlated positions)
- Event risk (major event in next {event_risk_veto_hours} hours)
- Portfolio concentration too high
- Insufficient edge or confidence

**Output Requirements**:
You MUST return a valid FundManagerApproval JSON object with:
- decision: APPROVE | MODIFY | REJECT
- rationale: Detailed explanation (minimum 100 characters)
- approved_position_size: Final approved size (if APPROVE/MODIFY)
- approved_risk_percentage: Final approved risk % (if APPROVE/MODIFY)
- modifications: List of changes (if MODIFY)
- rejection_reason: Primary reason (if REJECT)
- portfolio_risk_after_trade: Total portfolio risk if trade executes
- hard_limits_passed: Boolean indicating hard limit compliance
- trade_quality_score: Your assessment (0.0-1.0)
- confidence: Your confidence in this decision (0.0-1.0)
- recommended_action_timing: immediate | wait_for_pullback | after_event | do_not_trade

**Critical Principles**:
1. **Capital Preservation First**: When in doubt, reduce size or reject
2. **Enforce Hard Limits**: Non-negotiable constraints
3. **Portfolio-Level Thinking**: Individual trades impact overall portfolio
4. **Quality Over Quantity**: Better to skip mediocre trades
5. **Be Decisive**: Provide clear actionable decisions with explicit reasoning

Remember: You are the last line of defense against catastrophic losses.
Be rigorous. Be disciplined. Protect capital.
"""


class FundManagerAgent(BaseAgent):
    """
    Fund Manager Agent - Final approval gate with hard portfolio limits.

    This agent enforces strict risk management rules and has the authority to:
    - APPROVE trades as proposed
    - MODIFY trades (reduce size, adjust stops, delay entry)
    - REJECT trades (hard limit violations, poor quality)

    Critical for capital preservation and portfolio risk management.
    """

    def __init__(
        self,
        config: AgentConfig,
        portfolio_limits: Optional[PortfolioLimits] = None
    ):
        """
        Initialize Fund Manager Agent.

        Args:
            config: Agent configuration
            portfolio_limits: Hard portfolio limits (uses defaults if not provided)
        """
        # Validate agent type
        if config.agent_type != AgentType.RISK_OVERSEER:
            logger.warning(
                "fund_manager_agent_type_mismatch",
                expected=AgentType.RISK_OVERSEER.value,
                actual=config.agent_type.value
            )

        # Validate layer
        if config.layer != AgentLayer.DECISION:
            logger.warning(
                "fund_manager_agent_layer_mismatch",
                expected=AgentLayer.DECISION.value,
                actual=config.layer.value
            )

        super().__init__(config)

        # Set portfolio limits
        self.portfolio_limits = portfolio_limits or PortfolioLimits()

        # Override system prompt with portfolio limits
        if not config.system_prompt:
            self.config.system_prompt = FUND_MANAGER_SYSTEM_PROMPT.format(
                max_account_risk=self.portfolio_limits.max_account_risk_percent,
                max_portfolio_risk=self.portfolio_limits.max_portfolio_risk_percent,
                max_correlated_positions=self.portfolio_limits.max_correlated_positions,
                event_risk_veto_hours=self.portfolio_limits.event_risk_veto_hours,
                min_trade_quality=self.portfolio_limits.min_trade_quality_score
            )

        logger.info(
            "fund_manager_agent_initialized",
            agent_id=str(self.agent_id),
            llm_model=config.llm_model,
            max_account_risk=self.portfolio_limits.max_account_risk_percent,
            max_portfolio_risk=self.portfolio_limits.max_portfolio_risk_percent
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

    async def approve_trade(
        self,
        trade_intent: Phase6TradeIntent,
        position_size: PositionSize,
        stop_loss: StopLoss,
        take_profit: TakeProfit,
        current_portfolio: Dict[str, Any],
        symbol: str
    ) -> FundManagerApproval:
        """
        Make final approval decision on proposed trade.

        Args:
            trade_intent: Trade direction and conviction from TradeDecisionAgent
            position_size: Proposed position size from PositionSizingAgent
            stop_loss: Stop-loss placement from StopLossAgent
            take_profit: Take-profit targets from TakeProfitAgent
            current_portfolio: Current portfolio state with open positions
            symbol: Trading symbol

        Returns:
            FundManagerApproval with APPROVE/MODIFY/REJECT decision
        """
        logger.info(
            "fund_manager_approval_starting",
            agent_id=str(self.agent_id),
            symbol=symbol,
            direction=trade_intent.direction,
            proposed_lots=position_size.lot_size,
            proposed_risk=position_size.risk_percentage
        )

        # Build approval prompt
        approval_prompt = self._build_approval_prompt(
            trade_intent=trade_intent,
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            current_portfolio=current_portfolio,
            symbol=symbol
        )

        # Execute approval decision
        try:
            result = await self.execute(approval_prompt)

            # Extract FundManagerApproval from result
            approval = self._extract_approval(result)

            logger.info(
                "fund_manager_approval_complete",
                agent_id=str(self.agent_id),
                symbol=symbol,
                decision=approval.decision.value,
                approved_size=approval.approved_position_size,
                approved_risk=approval.approved_risk_percentage,
                portfolio_risk_after=approval.portfolio_risk_after_trade
            )

            return approval

        except Exception as e:
            logger.error(
                "fund_manager_approval_failed",
                agent_id=str(self.agent_id),
                symbol=symbol,
                error=str(e)
            )

            # Fallback: REJECT with safety
            return FundManagerApproval(
                decision=ApprovalDecision.REJECT,
                rationale=f"Fund Manager approval failed with error: {str(e)}. Safety fallback to REJECT.",
                rejection_reason=RejectionReason.QUALITY_CONCERNS,
                rejection_details=[
                    "Approval process error",
                    f"Error: {str(e)}",
                    "Safety fallback to reject trade"
                ],
                portfolio_risk_after_trade=0.0,
                correlation_check_passed=False,
                correlated_positions_count=0,
                max_correlated_positions=self.portfolio_limits.max_correlated_positions,
                event_risk_present=False,
                hard_limits_passed=False,
                violated_limits=["Approval process failed"],
                trade_quality_score=0.0,
                confidence=0.0,
                recommended_action_timing="do_not_trade",
                timestamp=datetime.utcnow().isoformat(),
                metadata={"error": str(e)}
            )

    def _build_approval_prompt(
        self,
        trade_intent: Phase6TradeIntent,
        position_size: PositionSize,
        stop_loss: StopLoss,
        take_profit: TakeProfit,
        current_portfolio: Dict[str, Any],
        symbol: str
    ) -> str:
        """
        Build the approval decision prompt.

        Args:
            trade_intent: Trade direction and conviction
            position_size: Proposed position size
            stop_loss: Stop-loss placement
            take_profit: Take-profit targets
            current_portfolio: Current portfolio state
            symbol: Trading symbol

        Returns:
            Formatted prompt string
        """
        # Format trade proposal
        trade_proposal = f"""
**Proposed Trade: {symbol}**
Direction: {trade_intent.direction}
Conviction: {trade_intent.conviction:.2f}

**Position Sizing**:
Lot Size: {position_size.lot_size:.2f} lots
Risk Percentage: {position_size.risk_percentage:.2f}%
Risk Amount: ${position_size.risk_amount:.2f}
Entry Price: ${position_size.entry_price:.2f}

**Risk Management**:
Stop-Loss: ${stop_loss.stop_price:.2f} ({stop_loss.distance_in_pips:.1f} pips)
Stop Type: {stop_loss.placement_type}
Probability of Stop Hit: {stop_loss.probability_of_stop_hit:.2f}

**Profit Targets**:
Primary Target: ${take_profit.primary_target:.2f}
Risk:Reward Ratio: {take_profit.risk_reward_ratio:.2f}:1
Expected Value: ${take_profit.expected_value:.2f}
Number of Targets: {len(take_profit.partial_targets)}

**Trade Rationale**:
{trade_intent.rationale}

**Key Factors**:
{self._format_list(trade_intent.key_factors)}

**Risk Assessment**:
{trade_intent.risk_assessment}
"""

        # Format portfolio context
        open_positions = current_portfolio.get("open_positions", [])
        total_exposure = current_portfolio.get("total_exposure_percent", 0.0)
        current_drawdown = current_portfolio.get("current_drawdown_percent", 0.0)

        portfolio_context = f"""
**Current Portfolio State**:
Open Positions: {len(open_positions)}
Total Exposure: {total_exposure:.2f}%
Current Drawdown: {current_drawdown:.2f}%
Available Capital: ${current_portfolio.get('available_capital', 0.0):.2f}

**Open Positions**:
{self._format_open_positions(open_positions)}
"""

        # Format hard limits
        limits_context = f"""
**Hard Portfolio Limits** (NON-NEGOTIABLE):
- Max Account Risk per Trade: {self.portfolio_limits.max_account_risk_percent}%
- Max Total Portfolio Risk: {self.portfolio_limits.max_portfolio_risk_percent}%
- Max Correlated Positions: {self.portfolio_limits.max_correlated_positions}
- Event Risk Veto Window: {self.portfolio_limits.event_risk_veto_hours} hours
- Min Trade Quality Score: {self.portfolio_limits.min_trade_quality_score}
"""

        prompt = f"""Make the FINAL approval decision on this trade.

{trade_proposal}

{portfolio_context}

{limits_context}

**Your Task**:
Evaluate this trade against all hard limits and portfolio context.
Make a decisive APPROVE/MODIFY/REJECT decision.

**Decision must include**:
- Explicit hard limits check (pass/fail for each limit)
- Portfolio risk calculation after this trade
- Trade quality score (0.0-1.0)
- Clear rationale (minimum 100 characters)
- If MODIFY: exact modifications with new values
- If REJECT: primary reason + detailed explanation

Return a complete FundManagerApproval JSON object.

Remember: You are the last line of defense. Be rigorous.
"""
        return prompt

    def _format_list(self, items: List[str]) -> str:
        """Format list of items for prompt."""
        if not items:
            return "None"
        return "\n".join(f"- {item}" for item in items)

    def _format_open_positions(self, positions: List[Dict[str, Any]]) -> str:
        """Format open positions for prompt."""
        if not positions:
            return "No open positions"

        lines = []
        for pos in positions:
            lines.append(
                f"- {pos.get('symbol')}: {pos.get('direction')} "
                f"{pos.get('lot_size', 0.0):.2f} lots, "
                f"risk {pos.get('risk_percent', 0.0):.2f}%"
            )
        return "\n".join(lines)

    def _extract_approval(self, result: Any) -> FundManagerApproval:
        """
        Extract FundManagerApproval from AutoGen result.

        Args:
            result: AutoGen agent result

        Returns:
            FundManagerApproval object
        """
        try:
            # Get the last message content
            if hasattr(result, 'messages') and result.messages:
                last_message = result.messages[-1]
                content = last_message.content if hasattr(last_message, 'content') else str(last_message)
            else:
                content = str(result)

            # Try to parse as JSON
            import json
            import re

            # Extract JSON from markdown code blocks if present
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                json_str = json_match.group(0) if json_match else content

            approval_data = json.loads(json_str)

            # Validate and create FundManagerApproval
            approval = FundManagerApproval(**approval_data)

            logger.info(
                "fund_manager_approval_extracted",
                decision=approval.decision.value,
                hard_limits_passed=approval.hard_limits_passed
            )

            return approval

        except Exception as e:
            logger.error(
                "fund_manager_approval_extraction_failed",
                error=str(e),
                result=str(result)[:500]
            )
            raise

    async def health_check(self) -> bool:
        """
        Check agent health status.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Verify model client can be created
            client = self._create_model_client()
            return client is not None
        except Exception as e:
            logger.error(
                "fund_manager_health_check_failed",
                agent_id=str(self.agent_id),
                error=str(e)
            )
            return False
