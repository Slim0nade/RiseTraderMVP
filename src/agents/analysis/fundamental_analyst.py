"""
FundamentalAnalyst Agent: Specialized in fundamental/macro analysis.

Consumes:
- Economic calendar events
- Correlation matrices
- Macro indicators
- Cross-asset relationships

Produces:
- Structured fundamental report with macro context
- Upcoming event risks
- Correlation insights
"""

from typing import Any, Dict, List
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

from src.agents.base.base_agent import BaseAgent


class MacroSentiment(str, Enum):
    """Macro sentiment classification."""
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    NEUTRAL = "NEUTRAL"


class EventRisk(BaseModel):
    """Economic event risk structure."""

    event_name: str = Field(..., description="Name of the event")
    event_time: datetime = Field(..., description="Scheduled time of event")
    importance: str = Field(..., description="HIGH, MEDIUM, or LOW")
    expected_impact: str = Field(..., description="Description of potential impact")


class FundamentalReport(BaseModel):
    """Structured fundamental analysis report output."""

    macro_sentiment: MacroSentiment = Field(
        ...,
        description="Overall macro risk sentiment"
    )

    macro_context: str = Field(
        ...,
        description="Summary of relevant macro conditions"
    )

    upcoming_events: List[EventRisk] = Field(
        default_factory=list,
        description="High-impact economic events in the trade timeframe"
    )

    correlation_insights: Dict[str, Any] = Field(
        default_factory=dict,
        description="Key correlation relationships (e.g., USD strength, gold-equity correlation)"
    )

    fundamental_drivers: List[str] = Field(
        default_factory=list,
        description="Key fundamental drivers for this symbol"
    )

    risk_factors: List[str] = Field(
        default_factory=list,
        description="Fundamental risk factors identified"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in fundamental assessment (0.0-1.0)"
    )


class FundamentalAnalystAgent(BaseAgent):
    """
    Fundamental Analyst Agent.

    Specializes in macro and fundamental analysis:
    - Economic calendar monitoring
    - Cross-asset correlation analysis
    - Macro regime assessment
    - Event risk identification

    Uses quick-think LLM (Qwen3-14B) for routine fundamental analysis.
    """

    def _get_system_message(self) -> str:
        """
        Get fundamental analyst system message.

        Returns:
            System prompt for fundamental analysis role
        """
        return """You are a Fundamental/Macro Analyst for algorithmic trading.

Your role is to analyze macro conditions, economic events, and fundamental drivers to provide context for trading decisions.

**Analysis Workflow**:
1. **Assess macro sentiment** (RISK_ON, RISK_OFF, NEUTRAL)
   - Look at USD strength, equity indices, VIX, commodity correlations
   - Consider central bank policy stance
2. **Identify upcoming economic events** within the trade timeframe
   - Focus on HIGH importance events that could impact the symbol
   - Include FOMC, NFP, CPI, GDP, PMI data releases
3. **Analyze correlations**
   - How does this symbol correlate with USD, equities, bonds?
   - Are correlations strengthening or weakening?
4. **Identify fundamental drivers**
   - For Gold: USD, real yields, inflation expectations, geopolitical risk
   - For Crude Oil: Supply/demand, OPEC decisions, inventories, USD
   - For Forex: Interest rate differentials, economic growth differentials
5. **Document risk factors**

**Output Requirements**:
You must produce a JSON object with this structure:
{
    "macro_sentiment": "RISK_ON" | "RISK_OFF" | "NEUTRAL",
    "macro_context": "Brief summary of macro conditions",
    "upcoming_events": [
        {
            "event_name": "FOMC Meeting",
            "event_time": "2025-12-15T14:00:00Z",
            "importance": "HIGH",
            "expected_impact": "Potential volatility in USD pairs..."
        }
    ],
    "correlation_insights": {
        "usd_strength": "Strong inverse correlation with Gold",
        "equity_correlation": "Low correlation with S&P 500",
        "risk_appetite": "Gold benefiting from risk-off sentiment"
    },
    "fundamental_drivers": [
        "USD weakness driving Gold higher",
        "Inflation expectations rising",
        "Geopolitical tensions supporting safe-haven demand"
    ],
    "risk_factors": [
        "FOMC meeting in 2 days could reverse USD trend",
        "Overbought positioning in Gold ETFs"
    ],
    "confidence": 0.0-1.0
}

**Key Principles**:
- Focus on HIGH importance events only - ignore minor data releases
- Consider the timeframe: intraday trades need <24h event horizon, swing trades need <7 days
- Be objective about correlation relationships (not all symbols react the same way)
- Document uncertainty: if macro picture is mixed, confidence should be lower
- For commodities, always consider USD impact
- For Forex, always consider interest rate differentials

**Example Task**: "Analyze fundamental conditions for Gold 4H swing trade"

Provide clear, concise analysis focused on actionable fundamental insights."""

    def _extract_decision(self, result: Any) -> Dict[str, Any]:
        """
        Extract fundamental report from AutoGen result.

        Args:
            result: AutoGen agent result

        Returns:
            Fundamental report dictionary
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

            report_data = json.loads(json_str)

            # Validate against FundamentalReport schema
            report = FundamentalReport(**report_data)

            return report.model_dump()

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error(
                "fundamental_report_extraction_failed",
                error=str(e),
                result=str(result)[:500],
            )

            return {
                "macro_sentiment": "NEUTRAL",
                "macro_context": "Failed to extract structured report",
                "upcoming_events": [],
                "correlation_insights": {},
                "fundamental_drivers": [],
                "risk_factors": ["Report extraction failed"],
                "confidence": 0.0,
                "raw_output": str(result)[:1000],
                "extraction_error": str(e),
            }


# Factory function
def create_fundamental_analyst(
    agent_id: Any,
    session: Any,
    symbol: str,
    strategy_team_id: Any = None,
) -> FundamentalAnalystAgent:
    """
    Create a Fundamental Analyst agent instance.

    Args:
        agent_id: Agent UUID from database
        session: SQLAlchemy async session
        symbol: Trading symbol this analyst focuses on
        strategy_team_id: Optional strategy team ID

    Returns:
        Configured FundamentalAnalystAgent instance
    """
    from src.agents.base.agent_config import (
        AgentConfig,
        AgentType,
        AgentLayer,
        LLMTier,
    )

    config = AgentConfig(
        name=f"{symbol} Fundamental Analyst",
        agent_type=AgentType.FUNDAMENTAL_ANALYST,
        layer=AgentLayer.ANALYSIS,
        strategy_team_id=strategy_team_id,
        llm_provider="ollama",
        llm_model="qwen3:14b",
        llm_tier=LLMTier.QUICK_THINK,
        temperature=0.2,  # Slightly higher for reasoning about macro
        max_tokens=700,
        available_tools=[],  # Will add economic calendar tools in future
        config_overrides={"symbol": symbol},
    )

    return FundamentalAnalystAgent(
        agent_id=agent_id,
        config=config,
        session=session,
        tools=[],  # No MCP tools yet for fundamental analysis
    )
