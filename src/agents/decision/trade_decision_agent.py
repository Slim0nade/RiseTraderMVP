"""
Trade Decision Agent - Final Go/No-Go Decision Maker.

**Phase 6 Update (2025-12-06):**
Now primarily consumes DebateOutcome from Bull/Bear adversarial debate
to make final LONG/SHORT/NO_TRADE decisions.

Legacy support maintained for direct analyst report synthesis.

Consumes (NEW - Phase 6):
- DebateOutcome from BullBearDebateTeam (primary input)

Consumes (LEGACY):
- TechnicalReport from TechnicalAnalyst
- FundamentalReport from FundamentalAnalyst
- SentimentReport from SentimentAnalyst

Produces:
- TradeIntent with direction, conviction, and reasoning
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import structlog

from src.agents.base.base_agent import BaseAgent
from src.agents.base.agent_config import AgentConfig, AgentType, AgentLayer, LLMTier

# Phase 6 imports (new debate-driven architecture)
from src.agents.schemas.debate import DebateOutcome as Phase6DebateOutcome
from src.agents.schemas.trade_decision import TradeIntent as Phase6TradeIntent, TradeDirection as Phase6TradeDirection, ConflictResolution

# Legacy imports (backward compatibility)
try:
    from src.agents.schemas.reports import (
        TechnicalReport,
        FundamentalReport,
        SentimentReport,
        DebateOutcome as LegacyDebateOutcome,
        TrendDirection,
    )
    from src.agents.schemas.decisions import TradeIntent as LegacyTradeIntent, TradeDirection as LegacyTradeDirection, ConfidenceLevel
    LEGACY_SCHEMAS_AVAILABLE = True
except ImportError:
    LEGACY_SCHEMAS_AVAILABLE = False

logger = structlog.get_logger(__name__)


class TradeDecisionAgent(BaseAgent):
    """
    Trade Decision Agent.

    Synthesizes analyst reports (technical, fundamental, sentiment)
    into a unified trade decision (TradeIntent).

    Key Responsibilities:
    - Aggregate analyst opinions with appropriate weights
    - Resolve conflicting signals
    - Generate trade direction and confidence
    - Document reasoning and supporting evidence
    - Apply debate layer feedback (if available)

    Uses deep-think LLM (DeepSeek-R1-14B) for complex decision synthesis.
    """

    def _get_system_message(self) -> str:
        """
        Get trade decision system message.

        Returns:
            System prompt for trade decision synthesis
        """
        return """You are a Trade Decision Synthesizer for algorithmic trading.

Your role is to analyze reports from multiple analyst agents (Technical, Fundamental, Sentiment) and synthesize them into a unified trading decision.

**Input Reports**:
1. **TechnicalReport**: Directional bias, confidence, support/resistance, ML forecasts, regime
2. **FundamentalReport**: Macro sentiment, upcoming events, correlations, fundamental drivers
3. **SentimentReport**: Crowd positioning, smart money flow, contrarian signals
4. **(Optional) DebateOutcome**: Bull/bear debate conclusion with risk factors

**Decision Framework**:

**1. Analyst Weighting**:
   - Technical Analysis: 50% weight (primary for entry timing)
   - Fundamental Analysis: 30% weight (macro context and event risk)
   - Sentiment Analysis: 20% weight (contrarian opportunities and extremes)

**2. Signal Aggregation**:
   - Count BULLISH signals across all reports
   - Count BEARISH signals across all reports
   - Calculate weighted consensus score

**3. Confidence Calculation**:
   ```
   base_confidence = analyst_agreement_score  # How aligned are analysts?

   # Adjustments:
   - High model agreement (>70%) → +0.10
   - Favorable regime (trending) → +0.10
   - No high-impact events → +0.10
   - Sentiment divergence (contrarian) → +0.05
   - Conflicting analysts → -0.20
   - Uncertain regime (volatile/ranging) → -0.15
   - High event risk → -0.20

   final_confidence = clamp(base_confidence + adjustments, 0.0, 1.0)
   ```

**4. Direction Rules**:
   - If weighted_consensus > 0.15 → LONG
   - If weighted_consensus < -0.15 → SHORT
   - If -0.15 <= weighted_consensus <= 0.15 → NEUTRAL (no trade)

**5. Conflict Resolution**:
   - If technical BULLISH but fundamental BEARISH → Check timeframe
     * Short-term trades (H1-H4): Follow technical
     * Swing trades (D1): Require fundamental alignment
   - If all analysts disagree → Default to NEUTRAL
   - If sentiment extreme (>80% crowded) → Consider contrarian

**6. Risk Factor Integration**:
   - Document ALL risk factors from all reports
   - High event risk → Reduce confidence or wait
   - Sentiment extremes → Flag for caution
   - Low model agreement → Reduce confidence

**Output Requirements**:
You must produce a JSON object matching the TradeIntent schema:
{
    "symbol": "Gold",
    "timeframe": "H4",
    "direction": "long" | "short" | "neutral",
    "confidence": 0.0-1.0,
    "confidence_level": "very_low" | "low" | "medium" | "high" | "very_high",
    "entry_price_estimate": 2650.50,  // Current price or suggested entry
    "entry_timing_preference": "immediate" | "wait_for_pullback" | "wait_for_breakout",
    "reasoning": "Detailed explanation of the decision synthesizing all reports",
    "supporting_indicators": ["indicator1", "indicator2", ...],
    "risk_factors": ["risk1", "risk2", ...],
    "analyst_consensus": 0.0-1.0,  // Agreement level between analysts
    "technical_alignment": 0.0-1.0,  // How aligned with technical report
    "fundamental_alignment": 0.0-1.0,  // How aligned with fundamental report
    "sentiment_alignment": 0.0-1.0,  // How aligned with sentiment report
    "conflicting_signals": ["conflict1", "conflict2", ...],  // If any
    "decision_timestamp": "2025-12-05T10:30:00Z",
    "recommended_hold_period": "4h-8h" | "1d-3d" | "1w+"
}

**Key Principles**:
1. **Multi-layered synthesis**: Don't just average - weight by importance and timeframe
2. **Explicit conflict documentation**: If analysts disagree, document why and how you resolved it
3. **Risk-aware**: High event risk or extreme sentiment should reduce confidence
4. **Timeframe-appropriate**: Short-term trades prioritize technical, swing trades need fundamental alignment
5. **NEUTRAL is valid**: If consensus is weak (<0.15), don't force a trade
6. **Evidence-based**: All reasoning must trace back to specific analyst findings
7. **Contrarian awareness**: Extreme sentiment (>80%) can signal reversals

**Example Task**:
```
Analyze reports for Gold H4 trade:
- Technical: BULLISH (0.75 confidence), RSI divergence, trending up
- Fundamental: NEUTRAL (0.60 confidence), FOMC meeting in 2 days
- Sentiment: Extremely bullish (85% retail long), contrarian signal
```

**Expected Output**:
```json
{
    "direction": "neutral",  // Wait due to event risk despite technical strength
    "confidence": 0.45,  // Reduced due to FOMC risk
    "reasoning": "Technical analysis strongly bullish with RSI divergence and uptrend. However, FOMC meeting in 2 days creates high event risk. Additionally, 85% retail long positioning suggests crowded trade vulnerable to reversal. Recommend waiting until after FOMC for clearer direction.",
    "entry_timing_preference": "wait_for_event",
    "risk_factors": ["FOMC meeting in 2 days", "Crowded long positioning (85%)", "Potential sentiment reversal"],
    "analyst_consensus": 0.62,  // Moderate agreement
    "conflicting_signals": ["Technical bullish vs. Sentiment extreme"]
}
```

Be analytical, objective, and transparent about uncertainties."""

    def _extract_decision(self, result: Any) -> Dict[str, Any]:
        """
        Extract TradeIntent from AutoGen result.

        Args:
            result: AutoGen agent result

        Returns:
            TradeIntent dictionary
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

            decision_data = json.loads(json_str)

            # Validate against TradeIntent schema
            trade_intent = TradeIntent(**decision_data)

            logger.info(
                "trade_intent_extracted",
                symbol=trade_intent.symbol,
                direction=trade_intent.direction,
                confidence=trade_intent.confidence,
            )

            return trade_intent.model_dump()

        except Exception as e:
            logger.error(
                "trade_intent_extraction_failed",
                error=str(e),
                result=str(result)[:500],
            )

            # Fallback: NEUTRAL decision with zero confidence
            return {
                "symbol": "UNKNOWN",
                "timeframe": "UNKNOWN",
                "direction": TradeDirection.NEUTRAL,
                "confidence": 0.0,
                "confidence_level": ConfidenceLevel.VERY_LOW,
                "entry_price_estimate": None,
                "entry_timing_preference": "do_not_trade",
                "reasoning": "Failed to extract structured trade intent from agent response",
                "supporting_indicators": [],
                "risk_factors": ["Decision extraction failed"],
                "analyst_consensus": 0.0,
                "conflicting_signals": ["Extraction error"],
                "decision_timestamp": datetime.utcnow(),
                "raw_output": str(result)[:1000],
                "extraction_error": str(e),
            }

    async def decide_from_debate(
        self,
        debate_outcome: Phase6DebateOutcome,
        symbol: str,
        current_price: Optional[float] = None,
    ) -> Phase6TradeIntent:
        """
        Make final trade direction decision from debate outcome (Phase 6 NEW).

        This is the primary entry point for the Phase 6 debate-driven architecture.

        Args:
            debate_outcome: Complete bull/bear debate results
            symbol: Trading symbol
            current_price: Optional current market price

        Returns:
            Phase6TradeIntent with final decision and rationale
        """
        logger.info(
            "trade_decision_from_debate_starting",
            agent_id=str(self.agent_id),
            symbol=symbol,
            consensus_direction=debate_outcome.consensus_direction,
            bull_conviction=debate_outcome.bull_case.conviction_score,
            bear_conviction=debate_outcome.bear_case.conviction_score,
            debate_quality=debate_outcome.debate_quality_score
        )

        # Build decision prompt from debate outcome
        decision_prompt = self._build_debate_decision_prompt(
            debate_outcome=debate_outcome,
            symbol=symbol,
            current_price=current_price
        )

        # Execute decision synthesis using deep-think LLM
        result = await self.execute(decision_prompt)

        # Extract TradeIntent
        trade_intent_data = self._extract_phase6_decision(result)

        # Convert to Phase6TradeIntent
        trade_intent = Phase6TradeIntent(**trade_intent_data)

        logger.info(
            "trade_decision_from_debate_complete",
            agent_id=str(self.agent_id),
            symbol=symbol,
            direction=trade_intent.direction.value,
            conviction=trade_intent.conviction,
            conflict_resolution=trade_intent.conflict_resolution
        )

        return trade_intent

    def _build_debate_decision_prompt(
        self,
        debate_outcome: Phase6DebateOutcome,
        symbol: str,
        current_price: Optional[float]
    ) -> str:
        """
        Build the decision prompt from debate outcome (Phase 6).

        Args:
            debate_outcome: Debate results
            symbol: Trading symbol
            current_price: Optional current price

        Returns:
            Formatted prompt string
        """
        # Format price context
        price_context = f"Current Price: ${current_price:.2f}" if current_price else "Current price not provided"

        # Format bull case summary
        bull_summary = f"""
**Bull Case (Conviction: {debate_outcome.bull_case.conviction_score:.2f}, Confidence: {debate_outcome.bull_case.confidence:.2f})**
Thesis: {debate_outcome.bull_case.thesis}

Evidence ({len(debate_outcome.bull_case.evidence_points)} points):
{self._format_phase6_evidence(debate_outcome.bull_case.evidence_points)}

Key Catalysts: {', '.join(debate_outcome.bull_case.key_catalysts) if debate_outcome.bull_case.key_catalysts else 'None specified'}
Price Targets: {debate_outcome.bull_case.price_targets}
Risk Warnings: {', '.join(debate_outcome.bull_case.risk_warnings) if debate_outcome.bull_case.risk_warnings else 'None specified'}
"""

        # Format bear case summary
        bear_summary = f"""
**Bear Case (Conviction: {debate_outcome.bear_case.conviction_score:.2f}, Confidence: {debate_outcome.bear_case.confidence:.2f})**
Thesis: {debate_outcome.bear_case.thesis}

Evidence ({len(debate_outcome.bear_case.evidence_points)} points):
{self._format_phase6_evidence(debate_outcome.bear_case.evidence_points)}

Key Risks: {', '.join(debate_outcome.bear_case.key_risks) if debate_outcome.bear_case.key_risks else 'None specified'}
Downside Targets: {debate_outcome.bear_case.downside_targets}
Risk Warnings: {', '.join(debate_outcome.bear_case.risk_warnings) if debate_outcome.bear_case.risk_warnings else 'None specified'}
"""

        # Format debate synthesis
        synthesis = f"""
**Debate Synthesis:**
Consensus Direction: {debate_outcome.consensus_direction or 'None'}
Debate Quality Score: {debate_outcome.debate_quality_score:.2f}

Key Disagreements:
{self._format_list(debate_outcome.key_disagreements)}

Consolidated Risks:
{self._format_list(debate_outcome.consolidated_risks)}
"""

        prompt = f"""Make the final trade direction decision for {symbol}.

{price_context}

{bull_summary}

{bear_summary}

{synthesis}

**Your Task:**
Evaluate both cases and make a decisive LONG/SHORT/NO_TRADE decision.

Consider:
1. Evidence quality (not just conviction scores)
2. Risk/reward asymmetry
3. Conflict resolution approach
4. Unresolved uncertainties
5. Portfolio fit

Return a complete JSON object with Phase6TradeIntent schema:
- direction (LONG/SHORT/NO_TRADE)
- conviction (0.0-1.0)
- detailed rationale (minimum 100 characters)
- key factors (minimum 3)
- risk assessment (minimum 50 characters)
- conflict resolution explanation
- expected holding period

Be rigorous. Be decisive. Document your reasoning.
"""
        return prompt

    def _format_phase6_evidence(self, evidence_points: list) -> str:
        """Format Phase 6 evidence points for prompt."""
        if not evidence_points:
            return "No evidence provided"

        lines = []
        for i, point in enumerate(evidence_points, 1):
            lines.append(
                f"{i}. {point.claim} "
                f"[Strength: {point.strength:.2f}, Source: {point.source}]"
            )
            if point.data_point:
                lines.append(f"   Data: {point.data_point}")

        return "\n".join(lines)

    def _extract_phase6_decision(self, result: Any) -> Dict[str, Any]:
        """
        Extract Phase6TradeIntent from AutoGen result.

        Args:
            result: AutoGen agent result

        Returns:
            Phase6TradeIntent dictionary
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

            decision_data = json.loads(json_str)

            # Validate basic structure
            required_fields = ['direction', 'conviction', 'rationale', 'key_factors', 'risk_assessment']
            missing_fields = [f for f in required_fields if f not in decision_data]
            if missing_fields:
                raise ValueError(f"Missing required fields: {missing_fields}")

            # Add timestamp if not present
            if 'timestamp' not in decision_data:
                decision_data['timestamp'] = datetime.utcnow().isoformat()

            # Add metadata if not present
            if 'metadata' not in decision_data:
                decision_data['metadata'] = {}

            logger.info(
                "phase6_trade_intent_extracted",
                direction=decision_data.get('direction'),
                conviction=decision_data.get('conviction'),
            )

            return decision_data

        except Exception as e:
            logger.error(
                "phase6_trade_intent_extraction_failed",
                error=str(e),
                result=str(result)[:500],
            )

            # Fallback: NO_TRADE decision with zero conviction
            return {
                "direction": Phase6TradeDirection.NO_TRADE,
                "conviction": 0.0,
                "rationale": f"Failed to extract structured trade intent from agent response: {str(e)}",
                "key_factors": ["Decision extraction failed", "Safety fallback to NO_TRADE"],
                "risk_assessment": "Unable to assess risk due to extraction failure",
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": {
                    "extraction_error": str(e),
                    "raw_output": str(result)[:500]
                }
            }

    async def synthesize_reports(
        self,
        technical_report: Dict[str, Any],
        fundamental_report: Dict[str, Any],
        sentiment_report: Dict[str, Any],
        debate_outcome: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Synthesize analyst reports into a trade decision.

        Args:
            technical_report: TechnicalReport dictionary
            fundamental_report: FundamentalReport dictionary
            sentiment_report: SentimentReport dictionary
            debate_outcome: Optional DebateOutcome dictionary

        Returns:
            TradeIntent dictionary
        """
        # Format the reports into a structured prompt
        reports_summary = self._format_reports(
            technical_report,
            fundamental_report,
            sentiment_report,
            debate_outcome,
        )

        # Create the user message with all reports
        user_message = f"""Synthesize the following analyst reports into a unified trade decision:

{reports_summary}

Provide your decision as a JSON object matching the TradeIntent schema.
Document your reasoning, handle any conflicts, and assign appropriate confidence."""

        # Execute the decision synthesis
        result = await self.execute(user_message)

        return result

    def _format_reports(
        self,
        technical_report: Dict[str, Any],
        fundamental_report: Dict[str, Any],
        sentiment_report: Dict[str, Any],
        debate_outcome: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Format analyst reports into a readable summary.

        Args:
            technical_report: TechnicalReport dictionary
            fundamental_report: FundamentalReport dictionary
            sentiment_report: SentimentReport dictionary
            debate_outcome: Optional DebateOutcome dictionary

        Returns:
            Formatted string with all reports
        """
        summary = "## Analyst Reports\n\n"

        # Technical Report
        summary += "### 1. Technical Analysis\n"
        summary += f"- **Directional Bias**: {technical_report.get('trend_direction', 'N/A')}\n"
        summary += f"- **Confidence**: {technical_report.get('confidence', 0.0):.2f}\n"
        summary += f"- **Market Regime**: {technical_report.get('market_regime', 'N/A')}\n"
        summary += f"- **Trend Strength**: {technical_report.get('trend_strength', 0.0):.2f}\n"
        summary += f"- **Current Price**: ${technical_report.get('current_price', 0.0):.2f}\n"

        key_levels = technical_report.get('key_levels', {})
        if 'support' in key_levels:
            summary += f"- **Support Levels**: {key_levels['support']}\n"
        if 'resistance' in key_levels:
            summary += f"- **Resistance Levels**: {key_levels['resistance']}\n"

        summary += f"- **Bullish Signals**: {', '.join(technical_report.get('bullish_signals', []))}\n"
        summary += f"- **Bearish Signals**: {', '.join(technical_report.get('bearish_signals', []))}\n"
        summary += f"- **Summary**: {technical_report.get('summary', 'N/A')}\n\n"

        # Fundamental Report
        summary += "### 2. Fundamental Analysis\n"
        summary += f"- **Fundamental Bias**: {fundamental_report.get('fundamental_bias', 'N/A')}\n"
        summary += f"- **Confidence**: {fundamental_report.get('confidence', 0.0):.2f}\n"
        summary += f"- **Macro Outlook**: {fundamental_report.get('macro_outlook', 'N/A')}\n"
        summary += f"- **Bullish Factors**: {', '.join(fundamental_report.get('bullish_factors', []))}\n"
        summary += f"- **Bearish Factors**: {', '.join(fundamental_report.get('bearish_factors', []))}\n"

        upcoming = fundamental_report.get('upcoming_events', [])
        if upcoming:
            summary += f"- **Upcoming Events**: {len(upcoming)} high-impact events\n"
            for event in upcoming[:3]:  # Show first 3
                summary += f"  - {event.get('title', 'N/A')} on {event.get('datetime', 'N/A')}\n"

        summary += f"- **Summary**: {fundamental_report.get('summary', 'N/A')}\n\n"

        # Sentiment Report
        summary += "### 3. Sentiment Analysis\n"
        summary += f"- **Sentiment Polarity**: {sentiment_report.get('sentiment_polarity', 'N/A')}\n"
        summary += f"- **Sentiment Score**: {sentiment_report.get('sentiment_score', 0.0):.2f}\n"
        summary += f"- **Confidence**: {sentiment_report.get('confidence', 0.0):.2f}\n"
        summary += f"- **News Sentiment**: {sentiment_report.get('news_sentiment', 0.0):.2f}\n"
        summary += f"- **Social Sentiment**: {sentiment_report.get('social_media_sentiment', 0.0):.2f}\n"
        summary += f"- **Positioning**: {sentiment_report.get('positioning_sentiment', 0.0):.2f}\n"
        summary += f"- **Positive Themes**: {', '.join(sentiment_report.get('positive_themes', []))}\n"
        summary += f"- **Negative Themes**: {', '.join(sentiment_report.get('negative_themes', []))}\n"
        summary += f"- **Summary**: {sentiment_report.get('summary', 'N/A')}\n\n"

        # Debate Outcome (if available)
        if debate_outcome:
            summary += "### 4. Debate Layer Outcome\n"
            summary += f"- **Consensus Direction**: {debate_outcome.get('consensus_direction', 'N/A')}\n"
            summary += f"- **Consensus Strength**: {debate_outcome.get('consensus_strength', 0.0):.2f}\n"
            summary += f"- **Analyst Agreement**: {debate_outcome.get('analyst_agreement', 0.0):.2f}\n"
            summary += f"- **Proceed with Trade**: {debate_outcome.get('proceed_with_trade', False)}\n"
            summary += f"- **Caution Level**: {debate_outcome.get('recommended_caution_level', 'N/A')}\n"
            summary += f"- **Counter-Arguments**: {', '.join(debate_outcome.get('counter_arguments', []))}\n"
            summary += f"- **Risk Factors**: {', '.join(debate_outcome.get('risk_factors', []))}\n"
            summary += f"- **Summary**: {debate_outcome.get('debate_summary', 'N/A')}\n\n"

        return summary


# Factory function
def create_trade_decision_agent(
    agent_id: Any,
    session: Any,
    symbol: str,
    strategy_team_id: Any = None,
) -> TradeDecisionAgent:
    """
    Create a Trade Decision Agent instance.

    Args:
        agent_id: Agent UUID from database
        session: SQLAlchemy async session
        symbol: Trading symbol this agent decides on
        strategy_team_id: Optional strategy team ID

    Returns:
        Configured TradeDecisionAgent instance
    """
    from src.agents.base.agent_config import (
        AgentConfig,
        AgentType,
        AgentLayer,
        LLMTier,
    )

    config = AgentConfig(
        name=f"{symbol}_Trade_Decision",
        agent_type=AgentType.TRADE_DECISION,
        layer=AgentLayer.DECISION,
        strategy_team_id=strategy_team_id,
        llm_provider="ollama",
        llm_model="deepseek-r1:14b",  # Deep-think model for complex synthesis
        llm_tier=LLMTier.DEEP_THINK,
        temperature=0.2,  # Some creativity for synthesis but mostly deterministic
        max_tokens=1200,  # Need space for detailed reasoning
        available_tools=[],  # No external tools - pure synthesis
        config_overrides={"symbol": symbol},
    )

    return TradeDecisionAgent(
        agent_id=agent_id,
        config=config,
        session=session,
        tools=[],  # Decision synthesis doesn't need external tools
    )
