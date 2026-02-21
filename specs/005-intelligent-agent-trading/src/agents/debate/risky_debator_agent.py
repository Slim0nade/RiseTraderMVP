"""
Risky Debator Agent - Risk Tolerance Debate Layer.

Argues for HIGHER position sizing when conditions warrant.
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


RISKY_DEBATOR_SYSTEM_PROMPT = """You are the Risky Debator in a 3-way risk tolerance debate.

Your role is to argue for HIGHER position sizing when conditions warrant it.

**Your Objectives:**
1. Identify factors that support increasing position size above baseline
2. Recognize high-conviction, high-edge opportunities
3. Spot favorable risk/reward asymmetry
4. Challenge overly conservative sizing that leaves money on the table

**When to Argue for Higher Sizing:**
- Very high conviction (>0.8) with strong evidence
- Extreme risk/reward asymmetry (>4:1)
- Multiple confirming signals across all analysts
- Low volatility environment (predictable risk)
- Strong technical setup with clear invalidation level
- Portfolio has room for risk (low correlation with existing positions)

**Critical Rules:**
- NEVER advocate reckless position sizing
- Always base arguments on concrete factors, not gut feeling
- Acknowledge when baseline sizing is appropriate
- Focus on mathematical edge, not gambling
- Consider correlation with existing positions
- Respect hard portfolio limits (never exceed max account risk)

**Output Requirements:**
Return a RiskPerspective JSON object with:
- tolerance: Always "risky"
- recommended_size_adjustment: 1.0-2.0 (1.0 = no change, >1.0 = increase)
- reasoning: Why higher sizing is justified (minimum 50 characters)
- key_factors: Minimum 2 factors supporting this view
- confidence: Your confidence in this recommendation (0.0-1.0)

**Example Argument:**
"Conviction is 0.85 with 5 confirming technical signals. Risk/reward is 5:1 with tight stop loss at $2,640. Market volatility at 6-month lows provides predictable risk. Portfolio exposure to gold only 15%, room for 2.5% allocation. Recommend 1.3x size adjustment (2.6 lots instead of 2.0 lots)."

Be aggressive when warranted, but always mathematically grounded.
"""


class RiskyDebatorAgent(BaseAgent):
    """
    Risky Debator Agent for risk tolerance debate.

    Argues for higher position sizing when favorable conditions exist.
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize Risky Debator Agent.

        Args:
            config: Agent configuration with LLM settings
        """
        # Validate agent type (uses DEVILS_ADVOCATE type for debate layer)
        if config.agent_type != AgentType.DEVILS_ADVOCATE:
            logger.warning(
                "risky_debator_agent_type_mismatch",
                expected=AgentType.DEVILS_ADVOCATE.value,
                actual=config.agent_type.value
            )

        # Validate layer
        if config.layer != AgentLayer.DEBATE:
            logger.warning(
                "risky_debator_agent_layer_mismatch",
                expected=AgentLayer.DEBATE.value,
                actual=config.layer.value
            )

        super().__init__(config)

        # Override system prompt if not provided
        if not config.system_prompt:
            self.config.system_prompt = RISKY_DEBATOR_SYSTEM_PROMPT

        logger.info(
            "risky_debator_agent_initialized",
            agent_id=str(self.agent_id),
            llm_model=config.llm_model,
            llm_tier=config.llm_tier.value
        )

    def _create_model_client(self):
        """
        Create LLM model client for risky debate.

        Uses quick-think tier for fast evaluation.

        Returns:
            AutoGen model client configured for structured output
        """
        return create_quick_think_client(
            temperature=self.config.temperature,
            response_format=RiskPerspective  # Structured output as RiskPerspective
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
        Argue for position size adjustment from risky perspective.

        Args:
            trade_intent: TradeIntent dictionary
            position_size_decision: PositionSizeDecision dictionary
            stop_loss_decision: StopLossDecision dictionary
            account_balance: Current account balance
            symbol: Trading symbol
            cancellation_token: Optional cancellation token

        Returns:
            RiskPerspective with risky viewpoint
        """
        logger.info(
            "risky_debator_starting",
            agent_id=str(self.agent_id),
            symbol=symbol,
            baseline_size=position_size_decision.get('position_size_lots'),
            conviction=trade_intent.get('conviction')
        )

        # Prepare evaluation prompt
        evaluation_prompt = self._build_evaluation_prompt(
            trade_intent=trade_intent,
            position_size_decision=position_size_decision,
            stop_loss_decision=stop_loss_decision,
            account_balance=account_balance,
            symbol=symbol
        )

        # Create AutoGen assistant with structured output
        assistant = AssistantAgent(
            name="risky_debator",
            model_client=self._create_model_client(),
            system_message=self.config.system_prompt
        )

        # Run evaluation
        try:
            response = await assistant.on_messages(
                [TextMessage(content=evaluation_prompt, source="user")],
                cancellation_token=cancellation_token or CancellationToken()
            )

            # Extract RiskPerspective from response
            risk_perspective = response.chat_message.content

            logger.info(
                "risky_perspective_generated",
                agent_id=str(self.agent_id),
                symbol=symbol,
                size_adjustment=risk_perspective.recommended_size_adjustment,
                confidence=risk_perspective.confidence
            )

            return risk_perspective

        except Exception as e:
            logger.error(
                "risky_debator_failed",
                agent_id=str(self.agent_id),
                symbol=symbol,
                error=str(e)
            )
            raise

    def _build_evaluation_prompt(
        self,
        trade_intent: Dict[str, Any],
        position_size_decision: Dict[str, Any],
        stop_loss_decision: Dict[str, Any],
        account_balance: float,
        symbol: str
    ) -> str:
        """
        Build the evaluation prompt.

        Args:
            trade_intent: Trade decision
            position_size_decision: Position sizing decision
            stop_loss_decision: Stop loss decision
            account_balance: Account balance
            symbol: Trading symbol

        Returns:
            Formatted prompt string
        """
        baseline_size = position_size_decision.get('position_size_lots', 0.0)
        baseline_risk_pct = position_size_decision.get('risk_percentage', 0.0)
        conviction = trade_intent.get('conviction', 0.0)
        
        prompt = f"""Evaluate position sizing from RISKY perspective for {symbol}.

**Trade Decision:**
- Direction: {trade_intent.get('direction', 'N/A')}
- Conviction: {conviction:.2f}
- Rationale: {trade_intent.get('rationale', 'N/A')}
- Key Factors: {', '.join(trade_intent.get('key_factors', []))}

**Baseline Position Sizing:**
- Position Size: {baseline_size:.2f} lots
- Risk Percentage: {baseline_risk_pct:.2f}%
- Account Balance: ${account_balance:.2f}
- Kelly Fraction: {position_size_decision.get('kelly_fraction', 0.0):.2f}

**Stop Loss:**
- Stop Loss Price: ${stop_loss_decision.get('stop_loss_price', 0.0):.2f}
- Risk Per Lot: ${stop_loss_decision.get('risk_per_lot', 0.0):.2f}

**Your Task:**
Argue for HIGHER position sizing if conditions warrant it.

Consider:
1. Is conviction exceptionally high (>0.75)?
2. Is risk/reward ratio very favorable (>3:1)?
3. Are multiple signals confirming?
4. Is volatility low (predictable risk)?
5. Is there portfolio capacity for larger position?

Return a RiskPerspective JSON object with:
- tolerance: "risky"
- recommended_size_adjustment: 1.0-2.0 (how much to scale up)
- reasoning: Why increase is justified
- key_factors: Factors supporting higher sizing
- confidence: Your confidence in this recommendation

If baseline sizing is already appropriate, recommend 1.0x (no change).
Never recommend reckless sizing - be mathematically grounded.
"""
        return prompt

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
                "risky_debator_health_check_failed",
                agent_id=str(self.agent_id),
                error=str(e)
            )
            return False
