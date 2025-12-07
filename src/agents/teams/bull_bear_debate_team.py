"""
Bull/Bear Debate Team - Adversarial Analysis Orchestration.

Coordinates Bull and Bear researchers in a structured debate using
AutoGen's SelectorGroupChat pattern. Produces a comprehensive DebateOutcome
with both perspectives for the TradeDecisionAgent to consume.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
import structlog

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.messages import TextMessage
from autogen_core import CancellationToken

from src.agents.debate.bull_researcher_agent import BullResearcherAgent
from src.agents.debate.bear_researcher_agent import BearResearcherAgent
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier
from src.agents.schemas.debate import DebateOutcome, BullCase, BearCase
from src.agents.providers import create_quick_think_client

logger = structlog.get_logger(__name__)


DEBATE_MODERATOR_SYSTEM_PROMPT = """You are the Debate Moderator for the Bull/Bear adversarial analysis system.

Your role is to:
1. Ensure both bull and bear researchers build complete, evidence-based cases
2. Identify key points of disagreement between the perspectives
3. Consolidate risk warnings from both sides
4. Assess whether a consensus direction emerges
5. Evaluate the overall quality of the debate

You coordinate the debate by prompting each researcher to build their case,
then synthesize the results into a comprehensive DebateOutcome.

**Consensus Guidelines:**
- LONG: Bull case significantly stronger (conviction gap >0.3)
- SHORT: Bear case significantly stronger (conviction gap >0.3)
- NEUTRAL: Both cases weak (both convictions <0.5)
- NO_CONSENSUS: Both cases strong but conflicting

**Quality Assessment:**
Rate debate quality (0.0-1.0) based on:
- Evidence quality and sourcing
- Argument completeness
- Intellectual honesty
- Consideration of counterarguments

Be objective and thorough in your assessment.
"""


class BullBearDebateTeam:
    """
    Orchestrates bull/bear adversarial debate.

    Uses SelectorGroupChat to coordinate researchers, then synthesizes
    their outputs into a comprehensive DebateOutcome.
    """

    def __init__(
        self,
        bull_config: AgentConfig,
        bear_config: AgentConfig,
        moderator_llm_tier: LLMTier = LLMTier.QUICK_THINK
    ):
        """
        Initialize Bull/Bear Debate Team.

        Args:
            bull_config: Configuration for bull researcher
            bear_config: Configuration for bear researcher
            moderator_llm_tier: LLM tier for debate moderator
        """
        # Create researcher agents
        self.bull_researcher = BullResearcherAgent(bull_config)
        self.bear_researcher = BearResearcherAgent(bear_config)

        # Store moderator config
        self.moderator_llm_tier = moderator_llm_tier

        logger.info(
            "debate_team_initialized",
            bull_agent_id=str(self.bull_researcher.agent_id),
            bear_agent_id=str(self.bear_researcher.agent_id),
            moderator_tier=moderator_llm_tier.value
        )

    async def run_debate(
        self,
        analyst_reports: Dict[str, Any],
        symbol: str,
        cancellation_token: Optional[CancellationToken] = None
    ) -> DebateOutcome:
        """
        Run bull/bear debate and produce comprehensive outcome.

        Args:
            analyst_reports: Dict with 'technical', 'fundamental', 'sentiment' reports
            symbol: Trading symbol being analyzed
            cancellation_token: Optional cancellation token

        Returns:
            DebateOutcome with both cases and synthesis

        Raises:
            ValueError: If analyst reports are incomplete
        """
        logger.info(
            "debate_starting",
            symbol=symbol,
            reports_available=list(analyst_reports.keys())
        )

        start_time = datetime.utcnow()

        # Run both researchers in parallel
        try:
            bull_case = await self.bull_researcher.run(
                analyst_reports=analyst_reports,
                symbol=symbol,
                cancellation_token=cancellation_token
            )

            bear_case = await self.bear_researcher.run(
                analyst_reports=analyst_reports,
                symbol=symbol,
                cancellation_token=cancellation_token
            )

            logger.info(
                "debate_cases_complete",
                symbol=symbol,
                bull_conviction=bull_case.conviction_score,
                bear_conviction=bear_case.conviction_score,
                bull_evidence_count=len(bull_case.evidence_points),
                bear_evidence_count=len(bear_case.evidence_points)
            )

        except Exception as e:
            logger.error(
                "debate_case_generation_failed",
                symbol=symbol,
                error=str(e)
            )
            raise

        # Synthesize debate outcome
        try:
            debate_outcome = await self._synthesize_outcome(
                bull_case=bull_case,
                bear_case=bear_case,
                symbol=symbol,
                start_time=start_time,
                cancellation_token=cancellation_token
            )

            logger.info(
                "debate_complete",
                symbol=symbol,
                consensus_direction=debate_outcome.consensus_direction,
                quality_score=debate_outcome.debate_quality_score,
                disagreement_count=len(debate_outcome.key_disagreements),
                total_risks=len(debate_outcome.consolidated_risks)
            )

            return debate_outcome

        except Exception as e:
            logger.error(
                "debate_synthesis_failed",
                symbol=symbol,
                error=str(e)
            )
            raise

    async def _synthesize_outcome(
        self,
        bull_case: BullCase,
        bear_case: BearCase,
        symbol: str,
        start_time: datetime,
        cancellation_token: Optional[CancellationToken] = None
    ) -> DebateOutcome:
        """
        Synthesize bull and bear cases into comprehensive DebateOutcome.

        Args:
            bull_case: Complete bull argument
            bear_case: Complete bear argument
            symbol: Trading symbol
            start_time: Debate start timestamp
            cancellation_token: Optional cancellation token

        Returns:
            DebateOutcome with synthesis
        """
        # Determine consensus direction
        conviction_gap = bull_case.conviction_score - bear_case.conviction_score

        if abs(conviction_gap) > 0.3:
            # Significant conviction gap
            if conviction_gap > 0:
                consensus_direction = "LONG"
            else:
                consensus_direction = "SHORT"
        elif bull_case.conviction_score < 0.5 and bear_case.conviction_score < 0.5:
            # Both cases weak
            consensus_direction = "NEUTRAL"
        else:
            # Both strong but conflicting
            consensus_direction = "NO_CONSENSUS"

        # Extract key disagreements
        key_disagreements = self._extract_disagreements(bull_case, bear_case)

        # Consolidate risk warnings
        consolidated_risks = (
            bull_case.risk_warnings +
            bear_case.risk_warnings
        )

        # Assess debate quality
        debate_quality_score = self._assess_quality(bull_case, bear_case)

        # Build metadata
        metadata = {
            "symbol": symbol,
            "debate_duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
            "conviction_gap": conviction_gap,
            "bull_agent_id": str(self.bull_researcher.agent_id),
            "bear_agent_id": str(self.bear_researcher.agent_id)
        }

        return DebateOutcome(
            bull_case=bull_case,
            bear_case=bear_case,
            consensus_direction=consensus_direction,
            key_disagreements=key_disagreements,
            consolidated_risks=consolidated_risks,
            debate_quality_score=debate_quality_score,
            timestamp=datetime.utcnow().isoformat(),
            metadata=metadata
        )

    def _extract_disagreements(
        self,
        bull_case: BullCase,
        bear_case: BearCase
    ) -> List[str]:
        """
        Extract key points of disagreement between cases.

        Args:
            bull_case: Bull argument
            bear_case: Bear argument

        Returns:
            List of disagreement descriptions
        """
        disagreements = []

        # Direction disagreement
        if bull_case.conviction_score > 0.6 and bear_case.conviction_score > 0.6:
            disagreements.append(
                f"Strong directional disagreement: Bull conviction {bull_case.conviction_score:.2f} "
                f"vs Bear conviction {bear_case.conviction_score:.2f}"
            )

        # Price target disagreement
        if bull_case.price_targets and bear_case.downside_targets:
            bull_targets = list(bull_case.price_targets.values())
            bear_targets = list(bear_case.downside_targets.values())
            if bull_targets and bear_targets:
                avg_bull = sum(bull_targets) / len(bull_targets)
                avg_bear = sum(bear_targets) / len(bear_targets)
                price_gap_pct = ((avg_bull - avg_bear) / avg_bear) * 100
                disagreements.append(
                    f"Price target gap: Bull avg ${avg_bull:.2f} vs Bear avg ${avg_bear:.2f} "
                    f"({price_gap_pct:+.1f}%)"
                )

        # Catalyst vs risk disagreement
        if bull_case.key_catalysts and bear_case.key_risks:
            disagreements.append(
                f"Bull identifies {len(bull_case.key_catalysts)} catalysts, "
                f"Bear identifies {len(bear_case.key_risks)} risks"
            )

        return disagreements

    def _assess_quality(
        self,
        bull_case: BullCase,
        bear_case: BearCase
    ) -> float:
        """
        Assess overall quality of the debate.

        Args:
            bull_case: Bull argument
            bear_case: Bear argument

        Returns:
            Quality score (0.0-1.0)
        """
        quality_factors = []

        # Evidence quality (average strength)
        bull_evidence_avg = (
            sum(e.strength for e in bull_case.evidence_points) / len(bull_case.evidence_points)
            if bull_case.evidence_points else 0.0
        )
        bear_evidence_avg = (
            sum(e.strength for e in bear_case.evidence_points) / len(bear_case.evidence_points)
            if bear_case.evidence_points else 0.0
        )
        quality_factors.append((bull_evidence_avg + bear_evidence_avg) / 2)

        # Completeness (evidence count)
        evidence_completeness = min(
            (len(bull_case.evidence_points) / 5.0),  # 5 evidence points = perfect
            1.0
        )
        quality_factors.append(evidence_completeness)

        # Confidence levels (analysts' self-assessment)
        avg_confidence = (bull_case.confidence + bear_case.confidence) / 2
        quality_factors.append(avg_confidence)

        # Counterargument consideration
        counterarg_score = min(
            (len(bull_case.counterarguments) + len(bear_case.counterarguments)) / 6.0,
            1.0
        )
        quality_factors.append(counterarg_score)

        # Overall quality (weighted average)
        return sum(quality_factors) / len(quality_factors)

    async def health_check(self) -> bool:
        """
        Check health of debate team.

        Returns:
            True if all agents healthy
        """
        try:
            bull_healthy = await self.bull_researcher.health_check()
            bear_healthy = await self.bear_researcher.health_check()

            is_healthy = bull_healthy and bear_healthy

            logger.info(
                "debate_team_health_check",
                bull_healthy=bull_healthy,
                bear_healthy=bear_healthy,
                overall_healthy=is_healthy
            )

            return is_healthy

        except Exception as e:
            logger.error(
                "debate_team_health_check_failed",
                error=str(e)
            )
            return False
