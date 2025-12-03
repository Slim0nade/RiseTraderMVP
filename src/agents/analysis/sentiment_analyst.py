"""
SentimentAnalyst Agent: Specialized in sentiment and positioning analysis.

Consumes:
- Sentiment scores
- Positioning data (COT, retail sentiment)
- Order flow information
- Volume profile

Produces:
- Structured sentiment report
- Crowd positioning metrics
- Smart money flow indicators
"""

from typing import Any, Dict
from pydantic import BaseModel, Field
from enum import Enum

from src.agents.base.base_agent import BaseAgent


class CrowdSentiment(str, Enum):
    """Crowd sentiment classification."""
    EXTREMELY_BULLISH = "EXTREMELY_BULLISH"
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    EXTREMELY_BEARISH = "EXTREMELY_BEARISH"


class SmartMoneyFlow(str, Enum):
    """Smart money flow direction."""
    ACCUMULATING = "ACCUMULATING"
    DISTRIBUTING = "DISTRIBUTING"
    NEUTRAL = "NEUTRAL"


class SentimentReport(BaseModel):
    """Structured sentiment analysis report output."""

    crowd_sentiment: CrowdSentiment = Field(
        ...,
        description="Overall crowd positioning/sentiment"
    )

    crowd_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Crowd positioning metrics (e.g., '85% retail long', 'extreme greed')"
    )

    smart_money_flow: SmartMoneyFlow = Field(
        ...,
        description="Smart money/institutional flow direction"
    )

    sentiment_divergence: bool = Field(
        ...,
        description="Whether there's divergence between crowd and smart money"
    )

    contrarian_signal: bool = Field(
        ...,
        description="Whether sentiment suggests contrarian opportunity"
    )

    order_flow_insights: Dict[str, Any] = Field(
        default_factory=dict,
        description="Order flow and volume profile insights"
    )

    sentiment_summary: str = Field(
        ...,
        description="Summary of sentiment analysis"
    )

    risk_factors: list[str] = Field(
        default_factory=list,
        description="Sentiment-related risk factors"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in sentiment assessment (0.0-1.0)"
    )


class SentimentAnalystAgent(BaseAgent):
    """
    Sentiment Analyst Agent.

    Specializes in sentiment and positioning analysis:
    - Retail vs. institutional positioning
    - Contrarian signals from extreme sentiment
    - Order flow analysis
    - Volume profile assessment

    Uses quick-think LLM (Qwen3-14B) for routine sentiment analysis.
    """

    def _get_system_message(self) -> str:
        """
        Get sentiment analyst system message.

        Returns:
            System prompt for sentiment analysis role
        """
        return """You are a Sentiment Analyst for algorithmic trading.

Your role is to analyze market sentiment, positioning data, and order flow to identify potential contrarian opportunities and gauge market psychology.

**Analysis Workflow**:
1. **Assess crowd sentiment**
   - Retail trader positioning (% long/short)
   - Social media sentiment scores
   - Options put/call ratios
   - Fear & Greed indicators
2. **Track smart money flow**
   - COT (Commitment of Traders) data for commercials vs. speculators
   - Institutional order flow
   - Dark pool activity
   - Large block trades
3. **Identify divergences**
   - Are retail traders extremely bullish while smart money distributes?
   - Is sentiment at extremes (>80% long or short)?
4. **Evaluate contrarian potential**
   - Extreme sentiment often precedes reversals
   - Crowded trades vulnerable to squeezes
5. **Analyze order flow and volume**
   - Where are large orders concentrated?
   - Volume profile: value areas and liquidity zones

**Output Requirements**:
You must produce a JSON object with this structure:
{
    "crowd_sentiment": "EXTREMELY_BULLISH" | "BULLISH" | "NEUTRAL" | "BEARISH" | "EXTREMELY_BEARISH",
    "crowd_metrics": {
        "retail_long_percent": 85,
        "fear_greed_index": 75,
        "sentiment_score": "Extreme greed"
    },
    "smart_money_flow": "ACCUMULATING" | "DISTRIBUTING" | "NEUTRAL",
    "sentiment_divergence": true | false,  // Crowd vs. smart money mismatch
    "contrarian_signal": true | false,     // Extreme sentiment suggesting reversal
    "order_flow_insights": {
        "large_buy_orders": "Concentrated above current price",
        "volume_profile": "High volume node at $2050",
        "institutional_flow": "Net selling over last 3 sessions"
    },
    "sentiment_summary": "Retail traders extremely bullish (85% long) while COT data shows commercials reducing long positions - potential bearish divergence",
    "risk_factors": [
        "Crowded long positioning vulnerable to squeeze",
        "Extreme sentiment readings (>80% bullish)"
    ],
    "confidence": 0.0-1.0
}

**Key Principles**:
- **Contrarian mindset**: Extreme sentiment often precedes reversals
  - >80% retail long = potential bearish signal
  - <20% retail long = potential bullish signal
- **Smart money vs. dumb money**: When retail and institutions diverge, follow the smart money
- **Sentiment is a timing indicator**, not a directional predictor
  - Useful for identifying overbought/oversold conditions
  - Works best in combination with technical and fundamental analysis
- **Document uncertainty**: If positioning data is mixed or inconclusive, reduce confidence
- **Order flow is forward-looking**: Large institutional orders can signal future moves

**Example Task**: "Analyze sentiment and positioning for Gold 4H swing trade"

Provide objective assessment of sentiment extremes and positioning divergences."""

    def _extract_decision(self, result: Any) -> Dict[str, Any]:
        """
        Extract sentiment report from AutoGen result.

        Args:
            result: AutoGen agent result

        Returns:
            Sentiment report dictionary
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

            # Validate against SentimentReport schema
            report = SentimentReport(**report_data)

            return report.model_dump()

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error(
                "sentiment_report_extraction_failed",
                error=str(e),
                result=str(result)[:500],
            )

            return {
                "crowd_sentiment": "NEUTRAL",
                "crowd_metrics": {},
                "smart_money_flow": "NEUTRAL",
                "sentiment_divergence": False,
                "contrarian_signal": False,
                "order_flow_insights": {},
                "sentiment_summary": "Failed to extract structured report",
                "risk_factors": ["Report extraction failed"],
                "confidence": 0.0,
                "raw_output": str(result)[:1000],
                "extraction_error": str(e),
            }


# Factory function
def create_sentiment_analyst(
    agent_id: Any,
    session: Any,
    symbol: str,
    strategy_team_id: Any = None,
) -> SentimentAnalystAgent:
    """
    Create a Sentiment Analyst agent instance.

    Args:
        agent_id: Agent UUID from database
        session: SQLAlchemy async session
        symbol: Trading symbol this analyst focuses on
        strategy_team_id: Optional strategy team ID

    Returns:
        Configured SentimentAnalystAgent instance
    """
    from src.agents.base.agent_config import (
        AgentConfig,
        AgentType,
        AgentLayer,
        LLMTier,
    )

    config = AgentConfig(
        name=f"{symbol}_Sentiment_Analyst",
        agent_type=AgentType.SENTIMENT_ANALYST,
        layer=AgentLayer.ANALYSIS,
        strategy_team_id=strategy_team_id,
        llm_provider="ollama",
        llm_model="qwen3:14b",
        llm_tier=LLMTier.QUICK_THINK,
        temperature=0.15,
        max_tokens=600,
        available_tools=[],  # Will add sentiment data tools in future
        config_overrides={"symbol": symbol},
    )

    return SentimentAnalystAgent(
        agent_id=agent_id,
        config=config,
        session=session,
        tools=[],  # No MCP tools yet for sentiment analysis
    )
