"""
Safe Debator Agent - Risk Tolerance Debate Layer.

Identifies factors warranting RISK REDUCTION in position sizing.
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


SAFE_DEBATOR_SYSTEM_PROMPT = """You are the Safe Debator in a 3-way risk tolerance debate.

Your role is to identify factors warranting RISK REDUCTION in position sizing.

**Your Objectives:**
1. Spot hidden risks not captured in baseline calculation
2. Identify conditions requiring conservative sizing
3. Protect capital during uncertain or dangerous setups
4. Challenge overconfident sizing that ignores tail risks

**When to Argue for Lower Sizing:**
- Low conviction (<0.5) or high uncertainty
- High volatility environment (unpredictable risk)
- Major upcoming events (FOMC, NFP, earnings)
- Poor technical setup (unclear invalidation level)
- High correlation with existing positions (concentration risk)
- Recent drawdown period (need to preserve capital)
- Extreme sentiment (crowded trades vulnerable to reversal)
- Questionable Kelly inputs (overestimated win rate or avg win/loss)

**Critical Risk Factors:**
- Event risk: Is there a catalyst that could invalidate the thesis?
- Correlation risk: Will this amplify existing portfolio exposure?
- Liquidity risk: Can we exit at stop loss price during volatility?
- Model risk: Are Kelly inputs based on solid data or guesses?
- Psychological risk: Is trader on tilt after recent losses?

**Output Requirements:**
Return a RiskPerspective JSON object with:
- tolerance: Always "safe"
- recommended_size_adjustment: 0.0-1.0 (1.0 = no change, <1.0 = reduce)
- reasoning: Why reduction is warranted (minimum 50 characters)
- key_factors: Minimum 2 factors supporting risk reduction
- confidence: Your confidence in this recommendation (0.0-1.0)

**Example Argument:**
"FOMC meeting in 18 hours creates high event risk. Gold historically moves 2%+ on Fed decisions. Current volatility (15% annualized) is 50% above 3-month average, increasing slippage risk. Portfolio already 12% exposed to gold miners (high correlation). Recommend 0.6x size adjustment (1.2 lots instead of 2.0 lots) to protect capital."

Be the guardian of capital - conservative is better than blown up.
"""


class SafeDebatorAgent(BaseAgent):
    """
    Safe Debator Agent for risk tolerance debate.

    Argues for position size reduction when risk factors are present.
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize Safe Debator Agent.

        Args:
            config: Agent configuration with LLM settings
        """
        # Validate agent type
        if config.agent_type != AgentType.DEVILS_ADVOCATE:
            logger.warning(
                "safe_debator_agent_type_mismatch",
                expected=AgentType.DEVILS_ADVOCATE.value,
                actual=config.agent_type.value
            )

        # Validate layer
        if config.layer != AgentLayer.DEBATE:
            logger.warning(
                "safe_debator_agent_layer_mismatch",
                expected=AgentLayer.DEBATE.value,
                actual=config.layer.value
            )

        super().__init__(config)

        # Override system prompt if not provided
        if not config.system_prompt:
            self.config.system_prompt = SAFE_DEBATOR_SYSTEM_PROMPT

        logger.info(
            "safe_debator_agent_initialized",
            agent_id=str(self.agent_id),
            llm_model=config.llm_model,
            llm_tier=config.llm_tier.value
        )

    def _create_model_client(self):
        """
        Create LLM model client for safe debate.

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
        portfolio_exposure: Optional[Dict[str, float]] = None,
        recent_pnl: Optional[float] = None,
        cancellation_token: Optional[CancellationToken] = None
    ) -> RiskPerspective:
        """
        Identify risk reduction factors from safe perspective.

        Args:
            trade_intent: TradeIntent dictionary
            position_size_decision: PositionSizeDecision dictionary
            stop_loss_decision: StopLossDecision dictionary
            account_balance: Current account balance
            symbol: Trading symbol
            portfolio_exposure: Optional dict of existing exposures
            recent_pnl: Optional recent P&L for drawdown detection
            cancellation_token: Optional cancellation token

        Returns:
            RiskPerspective with safe viewpoint
        """
        logger.info(
            "safe_debator_starting",
            agent_id=str(self.agent_id),
            symbol=symbol,
            baseline_size=position_size_decision.get('position_size_lots'),
            conviction=trade_intent.get('conviction')
        )

        # Prepare risk assessment prompt
        assessment_prompt = self._build_assessment_prompt(
            trade_intent=trade_intent,
            position_size_decision=position_size_decision,
            stop_loss_decision=stop_loss_decision,
            account_balance=account_balance,
            symbol=symbol,
            portfolio_exposure=portfolio_exposure,
            recent_pnl=recent_pnl
        )

        # Create AutoGen assistant with structured output
        assistant = AssistantAgent(
            name="safe_debator",
            model_client=self._create_model_client(),
            system_message=self.config.system_prompt
        )

        # Run risk assessment
        try:
            response = await assistant.on_messages(
                [TextMessage(content=assessment_prompt, source="user")],
                cancellation_token=cancellation_token or CancellationToken()
            )

            # Extract RiskPerspective from response
            risk_perspective = response.chat_message.content

            logger.info(
                "safe_perspective_generated",
                agent_id=str(self.agent_id),
                symbol=symbol,
                size_adjustment=risk_perspective.recommended_size_adjustment,
                confidence=risk_perspective.confidence
            )

            return risk_perspective

        except Exception as e:
            logger.error(
                "safe_debator_failed",
                agent_id=str(self.agent_id),
                symbol=symbol,
                error=str(e)
            )
            raise

    def _build_assessment_prompt(
        self,
        trade_intent: Dict[str, Any],
        position_size_decision: Dict[str, Any],
        stop_loss_decision: Dict[str, Any],
        account_balance: float,
        symbol: str,
        portfolio_exposure: Optional[Dict[str, float]],
        recent_pnl: Optional[float]
    ) -> str:
        """Build the risk assessment prompt."""
        baseline_size = position_size_decision.get('position_size_lots', 0.0)
        baseline_risk_pct = position_size_decision.get('risk_percentage', 0.0)
        conviction = trade_intent.get('conviction', 0.0)
        risk_factors = trade_intent.get('risk_factors', [])
        
        # Format portfolio exposure
        exposure_text = "Not provided"
        if portfolio_exposure:
            exposure_text = ", ".join([f"{k}: {v:.1f}%" for k, v in portfolio_exposure.items()])
        
        # Format recent P&L
        pnl_text = "Not provided"
        if recent_pnl is not None:
            pnl_text = f"${recent_pnl:+.2f} ({'profit' if recent_pnl > 0 else 'loss'})"
        
        prompt = f"""Identify risk reduction factors from SAFE perspective for {symbol}.

**Trade Decision:**
- Direction: {trade_intent.get('direction', 'N/A')}
- Conviction: {conviction:.2f}
- Rationale: {trade_intent.get('rationale', 'N/A')}
- Risk Factors: {', '.join(risk_factors) if risk_factors else 'None listed'}

**Baseline Position Sizing:**
- Position Size: {baseline_size:.2f} lots
- Risk Percentage: {baseline_risk_pct:.2f}%
- Account Balance: ${account_balance:.2f}

**Stop Loss:**
- Stop Loss Price: ${stop_loss_decision.get('stop_loss_price', 0.0):.2f}
- Confidence: {stop_loss_decision.get('confidence', 0.0):.2f}

**Portfolio Context:**
- Current Exposures: {exposure_text}
- Recent P&L: {pnl_text}

**Your Task:**
Identify factors warranting RISK REDUCTION in position sizing.

Evaluate:
1. Is conviction low or uncertain (<0.6)?
2. Are there major upcoming events (within 48 hours)?
3. Is volatility elevated (unpredictable risk)?
4. Is there high correlation with existing positions?
5. Is trader in drawdown (need capital preservation)?
6. Are there hidden tail risks?
7. Are Kelly inputs questionable or overoptimistic?

Return a RiskPerspective JSON object with:
- tolerance: "safe"
- recommended_size_adjustment: 0.0-1.0 (how much to scale down)
- reasoning: Why reduction is needed
- key_factors: Risk factors requiring reduction
- confidence: Your confidence in this recommendation

If no significant risk factors exist, recommend 1.0x (no change).
Err on the side of caution - capital preservation is paramount.
"""
        return prompt

    async def health_check(self) -> bool:
        """Check agent health status."""
        try:
            client = self._create_model_client()
            return client is not None
        except Exception as e:
            logger.error(
                "safe_debator_health_check_failed",
                agent_id=str(self.agent_id),
                error=str(e)
            )
            return False
