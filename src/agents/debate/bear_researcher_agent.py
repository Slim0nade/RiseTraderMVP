"""
Bear Researcher Agent - Adversarial Debate Layer.

Builds the strongest possible bear case from analyst reports,
identifying bearish risks, downside targets, and supporting evidence.
Part of the adversarial debate pattern that stress-tests trade ideas.
"""

from datetime import datetime
from typing import Dict, Any, Optional
import structlog

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core import CancellationToken

from src.agents.base.base_agent import BaseAgent
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer
from src.agents.schemas.debate import BearCase, DebatePosition, EvidencePoint
from src.agents.providers import create_deep_think_client

logger = structlog.get_logger(__name__)


BEAR_RESEARCHER_SYSTEM_PROMPT = """You are a Bear Researcher in an adversarial trading debate system.

Your role is to build the STRONGEST POSSIBLE BEAR CASE from the provided analyst reports.

**Your Objectives:**
1. Identify ALL bearish evidence across technical, fundamental, and sentiment analysis
2. Build a compelling thesis for SHORT positions or avoiding longs
3. Identify key risks that could drive prices lower
4. Provide realistic bearish price targets with percentile estimates
5. Acknowledge counterarguments but provide rebuttals
6. Warn of risks to traders even from a bear perspective

**Evidence Quality Standards:**
- Cite specific indicators, price levels, or data points
- Rate evidence strength honestly (0.0-1.0)
- Prefer quantitative over qualitative evidence
- Source all claims from analyst reports

**Output Requirements:**
You MUST return a valid BearCase JSON object with:
- position: Always "bear"
- thesis: Compelling 50+ character bear thesis
- evidence_points: Minimum 3 high-quality evidence points
- key_risks: List of bearish risks identified
- downside_targets: Dict with percentile keys (p25, p10) and price values
- conviction_score: Your conviction in this bear case (0.0-1.0)
- confidence: Your confidence in the analysis quality (0.0-1.0)
- counterarguments: Anticipated bull arguments with rebuttals
- risk_warnings: Risks to the bear case (e.g., short squeeze potential)

**Critical Guidelines:**
- Be intellectually honest - don't fabricate evidence
- Build the STRONGEST case possible, but acknowledge weaknesses
- Focus on what could go WRONG for bulls
- Your job is to advocate, not to be balanced (the debate provides balance)

**Example Evidence Point:**
{
  "claim": "Price rejected at resistance $2,750 three times, forming triple top",
  "source": "Technical Analyst Report - Pattern Recognition",
  "strength": 0.80,
  "data_point": "Resistance: $2,750, Current: $2,665"
}

Remember: You are building the bear case. Be thorough, be compelling, be honest.
"""


class BearResearcherAgent(BaseAgent):
    """
    Bear Researcher Agent for adversarial debate.

    Analyzes analyst reports to build the strongest possible bear case,
    providing evidence-backed arguments for short positions or avoiding longs.
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize Bear Researcher Agent.

        Args:
            config: Agent configuration with LLM settings
        """
        # Validate agent type
        if config.agent_type != AgentType.DEVILS_ADVOCATE:
            logger.warning(
                "bear_researcher_agent_type_mismatch",
                expected=AgentType.DEVILS_ADVOCATE.value,
                actual=config.agent_type.value
            )

        # Validate layer
        if config.layer != AgentLayer.DEBATE:
            logger.warning(
                "bear_researcher_agent_layer_mismatch",
                expected=AgentLayer.DEBATE.value,
                actual=config.layer.value
            )

        super().__init__(config)

        # Override system prompt if not provided
        if not config.system_prompt:
            self.config.system_prompt = BEAR_RESEARCHER_SYSTEM_PROMPT

        logger.info(
            "bear_researcher_agent_initialized",
            agent_id=str(self.agent_id),
            llm_model=config.llm_model,
            llm_tier=config.llm_tier.value
        )

    def _create_model_client(self):
        """
        Create LLM model client for bear research.

        Uses deep-think tier for complex reasoning about market evidence.

        Returns:
            AutoGen model client configured for structured output
        """
        return create_deep_think_client(
            temperature=self.config.temperature,
            response_format=BearCase  # Structured output as BearCase
        )

    async def run(
        self,
        analyst_reports: Dict[str, Any],
        symbol: str,
        cancellation_token: Optional[CancellationToken] = None
    ) -> BearCase:
        """
        Build the strongest bear case from analyst reports.

        Args:
            analyst_reports: Dict with keys 'technical', 'fundamental', 'sentiment'
            symbol: Trading symbol being analyzed
            cancellation_token: Optional cancellation token

        Returns:
            BearCase with complete bear argument and evidence

        Raises:
            ValueError: If analyst reports are incomplete
        """
        logger.info(
            "bear_researcher_starting",
            agent_id=str(self.agent_id),
            symbol=symbol,
            reports_available=list(analyst_reports.keys())
        )

        # Validate input
        required_reports = ["technical", "fundamental", "sentiment"]
        missing_reports = [r for r in required_reports if r not in analyst_reports]
        if missing_reports:
            raise ValueError(f"Missing analyst reports: {missing_reports}")

        # Prepare analysis prompt
        analysis_prompt = self._build_analysis_prompt(analyst_reports, symbol)

        # Create AutoGen assistant with structured output
        assistant = AssistantAgent(
            name="bear_researcher",
            model_client=self._create_model_client(),
            system_message=self.config.system_prompt
        )

        # Run analysis
        try:
            response = await assistant.on_messages(
                [TextMessage(content=analysis_prompt, source="user")],
                cancellation_token=cancellation_token or CancellationToken()
            )

            # Extract BearCase from response
            # AutoGen with response_format returns structured output
            bear_case = response.chat_message.content

            logger.info(
                "bear_case_generated",
                agent_id=str(self.agent_id),
                symbol=symbol,
                conviction_score=bear_case.conviction_score,
                evidence_count=len(bear_case.evidence_points),
                downside_targets=bear_case.downside_targets
            )

            return bear_case

        except Exception as e:
            logger.error(
                "bear_researcher_failed",
                agent_id=str(self.agent_id),
                symbol=symbol,
                error=str(e)
            )
            raise

    def _build_analysis_prompt(
        self,
        analyst_reports: Dict[str, Any],
        symbol: str
    ) -> str:
        """
        Build the analysis prompt from analyst reports.

        Args:
            analyst_reports: Dict with analyst reports
            symbol: Trading symbol

        Returns:
            Formatted prompt string
        """
        prompt = f"""Build the strongest BEAR CASE for {symbol}.

**Analyst Reports Provided:**

**Technical Analysis:**
{self._format_report(analyst_reports.get('technical', {}))}

**Fundamental Analysis:**
{self._format_report(analyst_reports.get('fundamental', {}))}

**Sentiment Analysis:**
{self._format_report(analyst_reports.get('sentiment', {}))}

**Your Task:**
Analyze these reports and build the most compelling bear case possible.
Extract ALL bearish signals, identify risks, and provide downside targets.

Return a complete BearCase JSON object with:
- Strong thesis statement
- Minimum 3 evidence points with sources
- Key bearish risks
- Realistic downside targets (p25, p10 percentiles)
- Counterarguments with rebuttals
- Risk warnings (e.g., short squeeze potential)

Focus on building the STRONGEST bear argument. Be thorough and evidence-based.
"""
        return prompt

    def _format_report(self, report: Dict[str, Any]) -> str:
        """
        Format a report dict for prompt inclusion.

        Args:
            report: Report dictionary

        Returns:
            Formatted string representation
        """
        if not report:
            return "No report available"

        # Format report as readable text
        lines = []
        for key, value in report.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                for sub_key, sub_value in value.items():
                    lines.append(f"  - {sub_key}: {sub_value}")
            else:
                lines.append(f"{key}: {value}")

        return "\n".join(lines)

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
                "bear_researcher_health_check_failed",
                agent_id=str(self.agent_id),
                error=str(e)
            )
            return False
