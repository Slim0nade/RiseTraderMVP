"""
Risk Debate Team - 3-Way Risk Tolerance Debate Orchestration.

Coordinates Risky, Neutral, and Safe debators to evaluate position sizing
from multiple risk tolerance perspectives. Produces a RiskDebateOutcome
with consensus adjustment and final position size.

This is the critical safety gate AFTER initial sizing but BEFORE execution.
"""

from datetime import datetime
from typing import Dict, Any, Optional
import structlog

from src.agents.debate.risky_debator_agent import RiskyDebatorAgent
from src.agents.debate.neutral_debator_agent import NeutralDebatorAgent
from src.agents.debate.safe_debator_agent import SafeDebatorAgent
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier
from src.agents.schemas.debate import RiskDebateOutcome, RiskPerspective

logger = structlog.get_logger(__name__)


class RiskDebateTeam:
    """
    Orchestrates 3-way risk tolerance debate.

    Runs Risky, Neutral, and Safe debators in parallel, then synthesizes
    their perspectives into a consensus position size adjustment.
    """

    def __init__(
        self,
        risky_config: AgentConfig,
        neutral_config: AgentConfig,
        safe_config: AgentConfig
    ):
        """
        Initialize Risk Debate Team.

        Args:
            risky_config: Configuration for risky debator
            neutral_config: Configuration for neutral debator
            safe_config: Configuration for safe debator
        """
        # Create debator agents
        self.risky_debator = RiskyDebatorAgent(risky_config)
        self.neutral_debator = NeutralDebatorAgent(neutral_config)
        self.safe_debator = SafeDebatorAgent(safe_config)

        logger.info(
            "risk_debate_team_initialized",
            risky_agent_id=str(self.risky_debator.agent_id),
            neutral_agent_id=str(self.neutral_debator.agent_id),
            safe_agent_id=str(self.safe_debator.agent_id)
        )

    async def run_debate(
        self,
        trade_intent: Dict[str, Any],
        position_size_decision: Dict[str, Any],
        stop_loss_decision: Dict[str, Any],
        account_balance: float,
        symbol: str,
        portfolio_exposure: Optional[Dict[str, float]] = None,
        recent_pnl: Optional[float] = None
    ) -> RiskDebateOutcome:
        """
        Run 3-way risk tolerance debate.

        Args:
            trade_intent: TradeIntent from TradeDecisionAgent
            position_size_decision: Initial position size from PositionSizingAgent
            stop_loss_decision: Stop loss from StopLossAgent
            account_balance: Current account balance
            symbol: Trading symbol
            portfolio_exposure: Optional existing portfolio exposures
            recent_pnl: Optional recent P&L for drawdown detection

        Returns:
            RiskDebateOutcome with consensus and final position size
        """
        logger.info(
            "risk_debate_starting",
            symbol=symbol,
            baseline_size=position_size_decision.get('position_size_lots'),
            baseline_risk_pct=position_size_decision.get('risk_percentage')
        )

        start_time = datetime.utcnow()
        baseline_size = position_size_decision.get('position_size_lots', 0.0)
        baseline_risk_pct = position_size_decision.get('risk_percentage', 0.0)

        # Run all three debators in parallel
        try:
            risky_perspective = await self.risky_debator.run(
                trade_intent=trade_intent,
                position_size_decision=position_size_decision,
                stop_loss_decision=stop_loss_decision,
                account_balance=account_balance,
                symbol=symbol
            )

            neutral_perspective = await self.neutral_debator.run(
                trade_intent=trade_intent,
                position_size_decision=position_size_decision,
                stop_loss_decision=stop_loss_decision,
                account_balance=account_balance,
                symbol=symbol
            )

            safe_perspective = await self.safe_debator.run(
                trade_intent=trade_intent,
                position_size_decision=position_size_decision,
                stop_loss_decision=stop_loss_decision,
                account_balance=account_balance,
                symbol=symbol,
                portfolio_exposure=portfolio_exposure,
                recent_pnl=recent_pnl
            )

            logger.info(
                "risk_perspectives_complete",
                symbol=symbol,
                risky_adjustment=risky_perspective.recommended_size_adjustment,
                neutral_adjustment=neutral_perspective.recommended_size_adjustment,
                safe_adjustment=safe_perspective.recommended_size_adjustment
            )

        except Exception as e:
            logger.error(
                "risk_debate_perspectives_failed",
                symbol=symbol,
                error=str(e)
            )
            raise

        # Synthesize debate outcome
        try:
            debate_outcome = self._synthesize_outcome(
                risky_perspective=risky_perspective,
                neutral_perspective=neutral_perspective,
                safe_perspective=safe_perspective,
                baseline_size=baseline_size,
                baseline_risk_pct=baseline_risk_pct,
                account_balance=account_balance,
                symbol=symbol,
                start_time=start_time
            )

            logger.info(
                "risk_debate_complete",
                symbol=symbol,
                consensus_adjustment=debate_outcome.consensus_adjustment,
                final_position_size=debate_outcome.final_position_size,
                final_risk_percentage=debate_outcome.final_risk_percentage,
                consensus_reached=debate_outcome.consensus_reached
            )

            return debate_outcome

        except Exception as e:
            logger.error(
                "risk_debate_synthesis_failed",
                symbol=symbol,
                error=str(e)
            )
            raise

    def _synthesize_outcome(
        self,
        risky_perspective: RiskPerspective,
        neutral_perspective: RiskPerspective,
        safe_perspective: RiskPerspective,
        baseline_size: float,
        baseline_risk_pct: float,
        account_balance: float,
        symbol: str,
        start_time: datetime
    ) -> RiskDebateOutcome:
        """
        Synthesize three perspectives into consensus outcome.

        Uses weighted average with higher weight on safe perspective when
        perspectives diverge significantly.

        Args:
            risky_perspective: Risky debator's view
            neutral_perspective: Neutral debator's view
            safe_perspective: Safe debator's view
            baseline_size: Original position size
            baseline_risk_pct: Original risk percentage
            account_balance: Account balance
            symbol: Trading symbol
            start_time: Debate start time

        Returns:
            RiskDebateOutcome with consensus
        """
        # Extract adjustments
        risky_adj = risky_perspective.recommended_size_adjustment
        neutral_adj = neutral_perspective.recommended_size_adjustment
        safe_adj = safe_perspective.recommended_size_adjustment

        # Check for consensus (all within 20% of each other)
        max_adj = max(risky_adj, neutral_adj, safe_adj)
        min_adj = min(risky_adj, neutral_adj, safe_adj)
        consensus_reached = (max_adj - min_adj) <= 0.2

        # Calculate consensus adjustment
        if consensus_reached:
            # Simple average when consensus exists
            consensus_adjustment = (risky_adj + neutral_adj + safe_adj) / 3.0
        else:
            # Weighted average favoring safety when divergent
            # Weights: Safe 50%, Neutral 30%, Risky 20%
            consensus_adjustment = (
                safe_adj * 0.5 +
                neutral_adj * 0.3 +
                risky_adj * 0.2
            )

        # Apply adjustment to baseline
        final_position_size = baseline_size * consensus_adjustment
        final_risk_percentage = baseline_risk_pct * consensus_adjustment

        # Consolidate warnings
        key_warnings = []
        if safe_perspective.confidence > 0.7:
            key_warnings.extend(safe_perspective.key_factors)
        if risky_perspective.confidence > 0.7 and risky_adj < 1.0:
            # Risky debator recommending reduction is a strong signal
            key_warnings.append(f"Even risky debator recommends caution: {risky_perspective.reasoning[:100]}")

        # Determine divergence rationale
        divergence_rationale = None
        if not consensus_reached:
            divergence_rationale = (
                f"Significant divergence detected: Risky={risky_adj:.2f}, "
                f"Neutral={neutral_adj:.2f}, Safe={safe_adj:.2f}. "
                f"Applying safety-weighted consensus (50% safe, 30% neutral, 20% risky)."
            )

        # Build metadata
        metadata = {
            "symbol": symbol,
            "debate_duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
            "baseline_size": baseline_size,
            "baseline_risk_pct": baseline_risk_pct,
            "adjustment_method": "simple_average" if consensus_reached else "safety_weighted",
            "risky_agent_id": str(self.risky_debator.agent_id),
            "neutral_agent_id": str(self.neutral_debator.agent_id),
            "safe_agent_id": str(self.safe_debator.agent_id)
        }

        return RiskDebateOutcome(
            risky_perspective=risky_perspective,
            neutral_perspective=neutral_perspective,
            safe_perspective=safe_perspective,
            consensus_adjustment=consensus_adjustment,
            consensus_reached=consensus_reached,
            final_position_size=final_position_size,
            final_risk_percentage=final_risk_percentage,
            divergence_rationale=divergence_rationale,
            key_warnings=key_warnings,
            timestamp=datetime.utcnow().isoformat(),
            metadata=metadata
        )

    async def health_check(self) -> bool:
        """
        Check health of risk debate team.

        Returns:
            True if all debators healthy
        """
        try:
            risky_healthy = await self.risky_debator.health_check()
            neutral_healthy = await self.neutral_debator.health_check()
            safe_healthy = await self.safe_debator.health_check()

            is_healthy = risky_healthy and neutral_healthy and safe_healthy

            logger.info(
                "risk_debate_team_health_check",
                risky_healthy=risky_healthy,
                neutral_healthy=neutral_healthy,
                safe_healthy=safe_healthy,
                overall_healthy=is_healthy
            )

            return is_healthy

        except Exception as e:
            logger.error(
                "risk_debate_team_health_check_failed",
                error=str(e)
            )
            return False
