"""
Risk Debate Team - 3-Way Risk Tolerance Debate for Position Sizing.

Evaluates proposed position sizes from three perspectives:
- RISKY: Argues for higher sizing when conditions warrant
- NEUTRAL: Validates baseline Kelly calculation
- SAFE: Identifies factors warranting risk reduction

This adversarial approach ensures position sizing decisions are stress-tested
before execution, catching potential oversizing or undersizing issues.
"""

from datetime import datetime
from typing import Dict, Any, Optional
import structlog

from src.agents.base.agent_config import AgentConfig, LLMTier
from src.agents.schemas.debate import (
    RiskDebateOutcome,
    RiskPerspective,
    RiskTolerance,
)
from src.agents.schemas.decisions import PositionSize
from src.agents.providers import create_deep_think_client
from src.database.repositories.decision_log_repository import DecisionLogRepository

logger = structlog.get_logger(__name__)


RISK_DEBATE_SYSTEM_PROMPT = """You are a Risk Debate Moderator conducting a 3-way debate on position sizing.

Your role is to generate THREE distinct perspectives on the proposed position size:

1. **RISKY Perspective**: Argues for HIGHER sizing
   - Identifies strong edge and favorable conditions
   - Highlights opportunities to maximize returns
   - Suggests size_adjustment > 1.0 (increase size)

2. **NEUTRAL Perspective**: Validates BASELINE sizing
   - Confirms Kelly criterion calculation
   - Assesses baseline reasonableness
   - Suggests size_adjustment ≈ 1.0 (keep as is)

3. **SAFE Perspective**: Argues for LOWER sizing
   - Identifies risks and uncertainty
   - Highlights reasons for caution
   - Suggests size_adjustment < 1.0 (reduce size)

**Input Context**:
- Proposed position size from PositionSizingAgent
- Trade conviction and rationale
- Market conditions (regime, volatility, correlation)
- Account state (balance, drawdown, open positions)
- Risk factors

**Your Task**:
Generate all THREE perspectives, then synthesize them into a consensus decision.

**Each Perspective Must Include**:
- tolerance: RISKY | NEUTRAL | SAFE
- recommended_size_adjustment: 0.0-2.0 (1.0 = no change)
- reasoning: Why this adjustment is appropriate (minimum 50 characters)
- key_factors: Supporting factors (minimum 2)
- confidence: Confidence in this perspective (0.0-1.0)

**Consensus Decision**:
- Calculate weighted average of all three adjustments
- Determine if perspectives agree (consensus_reached: true/false)
- Apply consensus adjustment to baseline position size
- Document final position size and risk percentage
- Flag any critical warnings from any perspective

**Output Requirements**:
Return a complete RiskDebateOutcome JSON object with:
- risky_perspective: RiskPerspective
- neutral_perspective: RiskPerspective
- safe_perspective: RiskPerspective
- consensus_adjustment: float (weighted average of all three)
- consensus_reached: bool (true if all within 0.3 of each other)
- final_position_size: float (baseline × consensus_adjustment)
- final_risk_percentage: float (recalculated risk %)
- divergence_rationale: str if perspectives diverge significantly
- key_warnings: List[str] from any perspective
- timestamp: str (ISO format)

**Decision Guidelines**:

**When to Increase Size** (Risky perspective wins):
- Very strong edge (win rate > 60%, R:R > 3:1)
- Calm market regime (low volatility)
- No correlated positions
- Fresh capital (no drawdown)
- High conviction (> 0.8)

**When to Keep Baseline** (Neutral perspective wins):
- Normal market conditions
- Moderate conviction (0.5-0.8)
- Standard risk parameters
- No major concerns

**When to Reduce Size** (Safe perspective wins):
- Uncertain conditions (choppy regime)
- Lower conviction (< 0.5)
- Existing drawdown
- High correlation with open positions
- Event risk present
- Portfolio heat already elevated

**Consensus Rules**:
- If all three within 0.3 of each other → consensus_reached = true
- If divergence > 0.3 → consensus_reached = false, explain divergence
- Final adjustment = weighted avg (Risky: 25%, Neutral: 50%, Safe: 25%)
- Safety bias: If safe perspective < 0.5, cap final adjustment at 0.7 max

Be intellectually honest. Each perspective should genuinely argue its position.
The debate quality depends on authentic adversarial reasoning.
"""


class RiskDebateTeam:
    """
    Risk Debate Team - 3-way adversarial debate on position sizing.

    Evaluates proposed position sizes from RISKY, NEUTRAL, and SAFE perspectives
    to ensure sizing decisions are robust and stress-tested.

    Simplified implementation: Uses single LLM call to generate all three perspectives
    instead of separate debater agents.
    """

    def __init__(
        self,
        llm_tier: LLMTier = LLMTier.DEEP_THINK,
        decision_log_repo: Optional[DecisionLogRepository] = None
    ):
        """
        Initialize Risk Debate Team.

        Args:
            llm_tier: LLM tier for debate moderation (default: DEEP_THINK)
            decision_log_repo: Optional repository for logging decisions
        """
        self.llm_tier = llm_tier
        self.decision_log_repo = decision_log_repo

        logger.info(
            "risk_debate_team_initialized",
            llm_tier=llm_tier.value,
            logging_enabled=decision_log_repo is not None
        )

    async def run_risk_debate(
        self,
        position_size: PositionSize,
        trade_context: Dict[str, Any],
        symbol: str
    ) -> RiskDebateOutcome:
        """
        Run 3-way risk tolerance debate on proposed position size.

        Args:
            position_size: Proposed position size from PositionSizingAgent
            trade_context: Trade context including conviction, regime, account state
            symbol: Trading symbol

        Returns:
            RiskDebateOutcome with all three perspectives and consensus
        """
        logger.info(
            "risk_debate_starting",
            symbol=symbol,
            proposed_lots=position_size.lot_size,
            proposed_risk=position_size.risk_percentage
        )

        start_time = datetime.utcnow()

        try:
            # Build debate prompt
            debate_prompt = self._build_debate_prompt(
                position_size=position_size,
                trade_context=trade_context,
                symbol=symbol
            )

            # Create LLM client for debate
            client = create_deep_think_client(
                temperature=0.7,  # Allow creativity for diverse perspectives
                response_format=RiskDebateOutcome
            )

            # Execute debate (single LLM call generates all perspectives)
            # Note: This is a simplified version. Full version would use separate agents.
            from autogen_agentchat.agents import AssistantAgent
            from autogen_agentchat.messages import TextMessage
            from autogen_core import CancellationToken

            assistant = AssistantAgent(
                name="risk_debate_moderator",
                model_client=client,
                system_message=RISK_DEBATE_SYSTEM_PROMPT
            )

            response = await assistant.on_messages(
                [TextMessage(content=debate_prompt, source="user")],
                cancellation_token=CancellationToken()
            )

            # Extract RiskDebateOutcome from response
            debate_outcome = response.chat_message.content

            # Add metadata
            if isinstance(debate_outcome, dict):
                debate_outcome["metadata"] = {
                    "symbol": symbol,
                    "debate_duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    "baseline_lot_size": position_size.lot_size,
                    "baseline_risk_percent": position_size.risk_percentage
                }
                debate_outcome = RiskDebateOutcome(**debate_outcome)
            else:
                # Already RiskDebateOutcome object
                debate_outcome.metadata = {
                    "symbol": symbol,
                    "debate_duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    "baseline_lot_size": position_size.lot_size,
                    "baseline_risk_percent": position_size.risk_percentage
                }

            logger.info(
                "risk_debate_complete",
                symbol=symbol,
                consensus_adjustment=debate_outcome.consensus_adjustment,
                final_lot_size=debate_outcome.final_position_size,
                final_risk=debate_outcome.final_risk_percentage,
                consensus_reached=debate_outcome.consensus_reached,
                warnings_count=len(debate_outcome.key_warnings)
            )

            # Log decision to database if repository provided
            if self.decision_log_repo:
                await self._log_risk_debate_decision(
                    debate_outcome=debate_outcome,
                    position_size=position_size,
                    trade_context=trade_context,
                    symbol=symbol
                )

            return debate_outcome

        except Exception as e:
            logger.error(
                "risk_debate_failed",
                symbol=symbol,
                error=str(e)
            )
            raise

    def _build_debate_prompt(
        self,
        position_size: PositionSize,
        trade_context: Dict[str, Any],
        symbol: str
    ) -> str:
        """
        Build the risk debate prompt.

        Args:
            position_size: Proposed position size
            trade_context: Trade context
            symbol: Trading symbol

        Returns:
            Formatted prompt string
        """
        # Extract context
        conviction = trade_context.get("conviction", 0.5)
        regime = trade_context.get("regime", "unknown")
        correlation_count = trade_context.get("correlation_count", 0)
        current_drawdown = trade_context.get("current_drawdown_percent", 0.0)
        account_balance = trade_context.get("account_balance", 100000.0)
        event_risk = trade_context.get("event_risk", False)

        prompt = f"""Conduct 3-way risk tolerance debate for {symbol} position sizing.

**Proposed Position Size** (Baseline from PositionSizingAgent):
- Lot Size: {position_size.lot_size:.2f} lots
- Risk Percentage: {position_size.risk_percentage:.2f}%
- Risk Amount: ${position_size.risk_amount:.2f}
- Entry Price: ${position_size.entry_price:.2f}

**Trade Context**:
- Conviction: {conviction:.2f} (0.0-1.0)
- Market Regime: {regime}
- Correlated Positions: {correlation_count}
- Current Drawdown: {current_drawdown:.2f}%
- Account Balance: ${account_balance:.2f}
- Event Risk Present: {event_risk}

**Position Sizing Logic Used**:
{position_size.calculation_details}

**Your Task**:
Generate THREE perspectives on this proposed position size:

1. **RISKY Perspective**: Argue for INCREASING size (adjustment > 1.0)
   - What conditions support higher sizing?
   - What opportunities might we miss by being too conservative?
   - Recommended adjustment: 1.0-2.0

2. **NEUTRAL Perspective**: Validate BASELINE sizing (adjustment ≈ 1.0)
   - Is the Kelly calculation reasonable?
   - Are baseline risk parameters appropriate?
   - Recommended adjustment: 0.9-1.1

3. **SAFE Perspective**: Argue for REDUCING size (adjustment < 1.0)
   - What risks or uncertainties exist?
   - What factors warrant caution?
   - Recommended adjustment: 0.0-1.0

Then synthesize these into a **consensus decision**:
- Calculate consensus_adjustment (weighted: Risky 25%, Neutral 50%, Safe 25%)
- Determine consensus_reached (true if all within 0.3 of each other)
- Calculate final_position_size (baseline × consensus_adjustment)
- Calculate final_risk_percentage
- Document divergence if perspectives conflict
- List key_warnings from any perspective

Return a complete RiskDebateOutcome JSON object with all three perspectives and consensus.

Be authentic in each perspective - genuine adversarial debate produces better decisions.
"""
        return prompt

    async def _log_risk_debate_decision(
        self,
        debate_outcome: RiskDebateOutcome,
        position_size: PositionSize,
        trade_context: Dict[str, Any],
        symbol: str
    ) -> None:
        """
        Log risk debate decision to decision_log table.

        Args:
            debate_outcome: Complete risk debate outcome
            position_size: Baseline position size
            trade_context: Trade context
            symbol: Trading symbol

        Schema note (migration 015):
            This method uses the pre-015 DecisionLog constructor directly with
            old field names (reasoning_trace, output_decision, confidence_score)
            that do not exist on the current ORM model.  It will raise an
            AttributeError at runtime and is already silently swallowed by the
            outer try/except.  Migration 015 signal-tag columns are NOT yet
            wired here — fix the column names first (decision_type,
            decision_data, reasoning), then add strategy_version etc.
        """
        try:
            from src.database.models.decision_log import DecisionLog
            from uuid import uuid4

            decision_log = DecisionLog(
                id=uuid4(),
                decided_at=datetime.utcnow(),
                agent_id=uuid4(),  # Placeholder - risk debate team doesn't have single agent ID
                agent_type="risk_debate_team",
                strategy_team_id=None,
                symbol=symbol,
                timeframe=None,
                input_data={
                    "baseline_position_size": position_size.model_dump(),
                    "trade_context": trade_context
                },
                reasoning_trace={
                    "risky_perspective": debate_outcome.risky_perspective.model_dump(),
                    "neutral_perspective": debate_outcome.neutral_perspective.model_dump(),
                    "safe_perspective": debate_outcome.safe_perspective.model_dump(),
                    "consensus_reached": debate_outcome.consensus_reached,
                    "divergence_rationale": debate_outcome.divergence_rationale
                },
                output_decision={
                    "consensus_adjustment": float(debate_outcome.consensus_adjustment),
                    "final_position_size": float(debate_outcome.final_position_size),
                    "final_risk_percentage": float(debate_outcome.final_risk_percentage),
                    "key_warnings": debate_outcome.key_warnings
                },
                confidence_score=float(debate_outcome.consensus_adjustment),  # Use adjustment as proxy for confidence
                execution_outcome=None,
                metadata=debate_outcome.metadata,
                llm_cost_usd=None,  # TODO: Track LLM costs
                processing_time_ms=debate_outcome.metadata.get("debate_duration_ms", 0)
            )

            await self.decision_log_repo.create(decision_log)

            logger.info(
                "risk_debate_decision_logged",
                symbol=symbol,
                decision_id=str(decision_log.id),
                consensus_adjustment=debate_outcome.consensus_adjustment
            )

        except Exception as e:
            logger.error(
                "risk_debate_decision_logging_failed",
                symbol=symbol,
                error=str(e)
            )
            # Don't raise - logging failure shouldn't break debate flow

    async def health_check(self) -> bool:
        """
        Check health of risk debate team.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Verify model client can be created
            client = create_deep_think_client()
            return client is not None
        except Exception as e:
            logger.error(
                "risk_debate_team_health_check_failed",
                error=str(e)
            )
            return False
