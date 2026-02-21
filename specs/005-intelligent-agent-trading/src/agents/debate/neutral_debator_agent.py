"""
Neutral Debator Agent - Risk Tolerance Debate Layer.

Validates BASELINE position sizing calculated by Kelly Criterion.
Part of the 3-way risk tolerance debate (Risky/Neutral/Safe) that validates
position sizing AFTER initial decision but BEFORE execution.
"""

from datetime import datetime
from typing import Dict, Any, Optional
import structlog

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core import CancellationToken

from src.agents.base.base_agent import BaseAgent
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer
from src.agents.schemas.debate import RiskPerspective, RiskTolerance
from src.agents.providers import create_quick_think_client

logger = structlog.get_logger(__name__)


NEUTRAL_DEBATOR_SYSTEM_PROMPT = """You are the Neutral Debator in a 3-way risk tolerance debate.

Your role is to VALIDATE the baseline Kelly Criterion calculation.

**Your Objectives:**
1. Verify that baseline sizing is mathematically sound
2. Check that Kelly inputs (win rate, avg win/loss) are reasonable
3. Confirm that the sizing aligns with conviction level
4. Serve as the rational middle ground between risky and safe perspectives

**When Baseline is Appropriate:**
- Kelly calculation inputs are reasonable and well-justified
- Position size aligns with conviction (higher conviction → higher size)
- Risk percentage is within portfolio guidelines (typically 1-3%)
- No extreme conditions warrant major adjustments
- Trade setup is "normal" - neither exceptional nor problematic

**Critical Validation Checks:**
- Win rate estimate: Is it based on backtests or reasonable assumptions?
- Avg win/loss ratio: Does it match the actual risk/reward setup?
- Kelly fraction multiplier: Is 0.25-0.5x Kelly appropriate for this trade?
- Account risk: Does position size respect max risk per trade limits?

**Output Requirements:**
Return a RiskPerspective JSON object with:
- tolerance: Always "neutral"
- recommended_size_adjustment: Typically 1.0 (no change) if baseline is sound
- reasoning: Why baseline is appropriate or what minor adjustments needed
- key_factors: Minimum 2 factors validating baseline
- confidence: Your confidence in the baseline calculation (0.0-1.0)

**Example Validation:**
"Kelly inputs are reasonable: 58% win rate from 200-trade backtest, 1.8:1 avg win/loss matches current risk/reward setup. 0.25x Kelly fraction appropriate for discretionary overlay. Position size 2.0 lots = 2.1% account risk, within 3% limit. Baseline validated. Recommend 1.0x (no adjustment)."

Be the voice of reason - validate sound math, question faulty assumptions.
"""


class NeutralDebatorAgent(BaseAgent):
    """
    Neutral Debator Agent for risk tolerance debate.

    Validates baseline position sizing calculations.
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize Neutral Debator Agent.

        Args:
            config: Agent configuration with LLM settings
        """
        # Validate agent type
        if config.agent_type != AgentType.DEVILS_ADVOCATE:
            logger.warning(
                "neutral_debator_agent_type_mismatch",
                expected=AgentType.DEVILS_ADVOCATE.value,
                actual=config.agent_type.value
            )

        # Validate layer
        if config.layer != AgentLayer.DEBATE:
            logger.warning(
                "neutral_debator_agent_layer_mismatch",
                expected=AgentLayer.DEBATE.value,
                actual=config.layer.value
            )

        super().__init__(config)

        # Override system prompt if not provided
        if not config.system_prompt:
            self.config.system_prompt = NEUTRAL_DEBATOR_SYSTEM_PROMPT

        logger.info(
            "neutral_debator_agent_initialized",
            agent_id=str(self.agent_id),
            llm_model=config.llm_model,
            llm_tier=config.llm_tier.value
        )

    def _create_model_client(self):
        """
        Create LLM model client for neutral validation.

        Uses quick-think tier for fast evaluation.

        Returns:
            AutoGen model client configured for structured output
        """
        return create_quick_think_client(
            temperature=self.config.temperature,
            response_format=RiskPerspective
        )

    async def run(
        self,
        trade_intent: Dict[str, Any],
        position_size_decision: Dict[str, Any],
        stop_loss_decision: Dict[str, Any],
        account_balance: float,
        symbol: str,
        cancellation_token: Optional[CancellationToken] = None
    ) -> RiskPerspective:
        """
        Validate baseline position sizing from neutral perspective.

        Args:
            trade_intent: TradeIntent dictionary
            position_size_decision: PositionSizeDecision dictionary
            stop_loss_decision: StopLossDecision dictionary
            account_balance: Current account balance
            symbol: Trading symbol
            cancellation_token: Optional cancellation token

        Returns:
            RiskPerspective with neutral validation
        """
        logger.info(
            "neutral_debator_starting",
            agent_id=str(self.agent_id),
            symbol=symbol,
            baseline_size=position_size_decision.get('position_size_lots'),
            kelly_fraction=position_size_decision.get('kelly_fraction')
        )

        # Prepare validation prompt
        validation_prompt = self._build_validation_prompt(
            trade_intent=trade_intent,
            position_size_decision=position_size_decision,
            stop_loss_decision=stop_loss_decision,
            account_balance=account_balance,
            symbol=symbol
        )

        # Create AutoGen assistant with structured output
        assistant = AssistantAgent(
            name="neutral_debator",
            model_client=self._create_model_client(),
            system_message=self.config.system_prompt
        )

        # Run validation
        try:
            response = await assistant.on_messages(
                [TextMessage(content=validation_prompt, source="user")],
                cancellation_token=cancellation_token or CancellationToken()
            )

            # Extract RiskPerspective from response
            risk_perspective = response.chat_message.content

            logger.info(
                "neutral_perspective_generated",
                agent_id=str(self.agent_id),
                symbol=symbol,
                size_adjustment=risk_perspective.recommended_size_adjustment,
                confidence=risk_perspective.confidence
            )

            return risk_perspective

        except Exception as e:
            logger.error(
                "neutral_debator_failed",
                agent_id=str(self.agent_id),
                symbol=symbol,
                error=str(e)
            )
            raise

    def _build_validation_prompt(
        self,
        trade_intent: Dict[str, Any],
        position_size_decision: Dict[str, Any],
        stop_loss_decision: Dict[str, Any],
        account_balance: float,
        symbol: str
    ) -> str:
        """Build the validation prompt."""
        baseline_size = position_size_decision.get('position_size_lots', 0.0)
        baseline_risk_pct = position_size_decision.get('risk_percentage', 0.0)
        kelly_fraction = position_size_decision.get('kelly_fraction', 0.0)
        win_rate = position_size_decision.get('estimated_win_rate', 0.0)
        avg_win_loss = position_size_decision.get('avg_win_loss_ratio', 0.0)
        
        prompt = f"""Validate baseline position sizing from NEUTRAL perspective for {symbol}.

**Trade Decision:**
- Direction: {trade_intent.get('direction', 'N/A')}
- Conviction: {trade_intent.get('conviction', 0.0):.2f}
- Rationale: {trade_intent.get('rationale', 'N/A')}

**Baseline Kelly Calculation:**
- Position Size: {baseline_size:.2f} lots
- Risk Percentage: {baseline_risk_pct:.2f}%
- Kelly Fraction: {kelly_fraction:.4f}
- Estimated Win Rate: {win_rate:.2f}
- Avg Win/Loss Ratio: {avg_win_loss:.2f}
- Account Balance: ${account_balance:.2f}

**Stop Loss:**
- Stop Loss Price: ${stop_loss_decision.get('stop_loss_price', 0.0):.2f}
- Risk Per Lot: ${stop_loss_decision.get('risk_per_lot', 0.0):.2f}

**Sizing Justification:**
{position_size_decision.get('sizing_justification', 'N/A')}

**Your Task:**
Validate that the baseline Kelly Criterion sizing is mathematically sound.

Check:
1. Are Kelly inputs (win rate, avg win/loss) reasonable?
2. Is the Kelly fraction multiplier (0.25-0.5x) appropriate?
3. Does position size align with conviction level?
4. Is risk percentage within portfolio limits (typically 1-3%)?
5. Are there any calculation errors or faulty assumptions?

Return a RiskPerspective JSON object with:
- tolerance: "neutral"
- recommended_size_adjustment: 1.0 if baseline valid, adjust if errors found
- reasoning: Validation results
- key_factors: Factors confirming or questioning baseline
- confidence: Confidence in baseline calculation

Be the rational validator - approve sound math, flag questionable assumptions.
"""
        return prompt

    async def health_check(self) -> bool:
        """Check agent health status."""
        try:
            client = self._create_model_client()
            return client is not None
        except Exception as e:
            logger.error(
                "neutral_debator_health_check_failed",
                agent_id=str(self.agent_id),
                error=str(e)
            )
            return False
