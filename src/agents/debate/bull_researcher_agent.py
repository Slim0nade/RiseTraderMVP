"""
Bull Researcher Agent - Adversarial Debate Layer.

Builds the strongest possible bull case from analyst reports,
identifying bullish catalysts, price targets, and supporting evidence.
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
from src.agents.schemas.debate import BullCase, DebatePosition, EvidencePoint
from src.agents.providers import create_deep_think_client

logger = structlog.get_logger(__name__)


BULL_RESEARCHER_SYSTEM_PROMPT = """You are a Bull Researcher in an adversarial trading debate system.

Your role is to build the STRONGEST POSSIBLE BULL CASE from the provided analyst reports.

**Your Objectives:**
1. Identify ALL bullish evidence across technical, fundamental, and sentiment analysis
2. Build a compelling thesis for LONG positions with supporting evidence
3. Identify key catalysts that could drive prices higher
4. Provide realistic bullish price targets with percentile estimates
5. Acknowledge counterarguments but provide rebuttals
6. Warn of risks even from a bull perspective

**Evidence Quality Standards:**
- Cite specific indicators, price levels, or data points
- Rate evidence strength honestly (0.0-1.0)
- Prefer quantitative over qualitative evidence
- Source all claims from analyst reports

**Output Requirements:**
You MUST return a valid BullCase JSON object with:
- position: Always "bull"
- thesis: Compelling 50+ character bull thesis
- evidence_points: Minimum 3 high-quality evidence points
- key_catalysts: List of bullish catalysts identified
- price_targets: Dict with percentile keys (p75, p90) and price values
- conviction_score: Your conviction in this bull case (0.0-1.0)
- confidence: Your confidence in the analysis quality (0.0-1.0)
- counterarguments: Anticipated bear arguments with rebuttals
- risk_warnings: Risks to the bull case

**Critical Guidelines:**
- Be intellectually honest - don't fabricate evidence
- Build the STRONGEST case possible, but acknowledge weaknesses
- Focus on what could go RIGHT for bulls
- Your job is to advocate, not to be balanced (the debate provides balance)

**Example Evidence Point:**
{
  "claim": "RSI oversold at 28, historically precedes 5% rallies",
  "source": "Technical Analyst Report - RSI Analysis",
  "strength": 0.75,
  "data_point": "RSI: 28 (oversold threshold: 30)"
}

Remember: You are building the bull case. Be thorough, be compelling, be honest.
"""


class BullResearcherAgent(BaseAgent):
    """
    Bull Researcher Agent for adversarial debate.

    Analyzes analyst reports to build the strongest possible bull case,
    providing evidence-backed arguments for long positions.
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize Bull Researcher Agent.

        Args:
            config: Agent configuration with LLM settings
        """
        # Validate agent type
        if config.agent_type != AgentType.DEVILS_ADVOCATE:
            logger.warning(
                "bull_researcher_agent_type_mismatch",
                expected=AgentType.DEVILS_ADVOCATE.value,
                actual=config.agent_type.value
            )

        # Validate layer
        if config.layer != AgentLayer.DEBATE:
            logger.warning(
                "bull_researcher_agent_layer_mismatch",
                expected=AgentLayer.DEBATE.value,
                actual=config.layer.value
            )

        super().__init__(config)

        # Override system prompt if not provided
        if not config.system_prompt:
            self.config.system_prompt = BULL_RESEARCHER_SYSTEM_PROMPT

        logger.info(
            "bull_researcher_agent_initialized",
            agent_id=str(self.agent_id),
            llm_model=config.llm_model,
            llm_tier=config.llm_tier.value
        )

    def _create_model_client(self):
        """
        Create LLM model client for bull research.

        Uses deep-think tier for complex reasoning about market evidence.

        Returns:
            AutoGen model client configured for structured output
        """
        return create_deep_think_client(
            temperature=self.config.temperature,
            response_format=BullCase  # Structured output as BullCase
        )

    async def run(
        self,
        analyst_reports: Dict[str, Any],
        symbol: str,
        cancellation_token: Optional[CancellationToken] = None
    ) -> BullCase:
        """
        Build the strongest bull case from analyst reports.

        Args:
            analyst_reports: Dict with keys 'technical', 'fundamental', 'sentiment'
            symbol: Trading symbol being analyzed
            cancellation_token: Optional cancellation token

        Returns:
            BullCase with complete bull argument and evidence

        Raises:
            ValueError: If analyst reports are incomplete
        """
        logger.info(
            "bull_researcher_starting",
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
            name="bull_researcher",
            model_client=self._create_model_client(),
            system_message=self.config.system_prompt
        )

        # Run analysis
        try:
            response = await assistant.on_messages(
                [TextMessage(content=analysis_prompt, source="user")],
                cancellation_token=cancellation_token or CancellationToken()
            )

            # Extract BullCase from response
            # AutoGen with response_format returns structured output
            bull_case = response.chat_message.content

            logger.info(
                "bull_case_generated",
                agent_id=str(self.agent_id),
                symbol=symbol,
                conviction_score=bull_case.conviction_score,
                evidence_count=len(bull_case.evidence_points),
                price_targets=bull_case.price_targets
            )

            return bull_case

        except Exception as e:
            logger.error(
                "bull_researcher_failed",
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
        prompt = f"""Build the strongest BULL CASE for {symbol}.

**Analyst Reports Provided:**

**Technical Analysis:**
{self._format_report(analyst_reports.get('technical', {}))}

**Fundamental Analysis:**
{self._format_report(analyst_reports.get('fundamental', {}))}

**Sentiment Analysis:**
{self._format_report(analyst_reports.get('sentiment', {}))}

**Your Task:**
Analyze these reports and build the most compelling bull case possible.
Extract ALL bullish signals, identify catalysts, and provide price targets.

Return a complete BullCase JSON object with:
- Strong thesis statement
- Minimum 3 evidence points with sources
- Key bullish catalysts
- Realistic price targets (p75, p90 percentiles)
- Counterarguments with rebuttals
- Risk warnings

Focus on building the STRONGEST bull argument. Be thorough and evidence-based.
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
                "bull_researcher_health_check_failed",
                agent_id=str(self.agent_id),
                error=str(e)
            )
            return False
