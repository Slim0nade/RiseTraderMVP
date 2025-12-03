"""
TechnicalAnalyst Agent: Specialized in technical analysis with ML forecasts.

Consumes:
- ML forecasting models (TCN, XGBoost, LSTM)
- Regime detection
- Technical indicators
- Support/resistance levels

Produces:
- Structured technical report with directional bias
- Confidence levels
- Key price levels
- Model agreement metrics
"""

from typing import Any, Dict
from pydantic import BaseModel, Field
from enum import Enum

from src.agents.base.base_agent import BaseAgent
from src.agents.tools.mcp_tools import (
    get_tcn_forecast,
    get_xgboost_forecast,
    get_lstm_forecast,
    get_regime_classification,
    get_technical_indicators,
    get_market_data,
    get_forecast_accuracy,
)


class DirectionalBias(str, Enum):
    """Directional bias classification."""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class TechnicalReport(BaseModel):
    """Structured technical analysis report output."""

    directional_bias: DirectionalBias = Field(
        ...,
        description="Overall directional bias from technical analysis"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in the directional bias (0.0-1.0)"
    )

    current_price: float = Field(
        ...,
        description="Current market price"
    )

    support_levels: list[float] = Field(
        default_factory=list,
        description="Key support price levels"
    )

    resistance_levels: list[float] = Field(
        default_factory=list,
        description="Key resistance price levels"
    )

    model_agreement: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Agreement rate among ML models (0.0-1.0)"
    )

    regime: str = Field(
        ...,
        description="Current market regime (TRENDING_UP, TRENDING_DOWN, RANGING, VOLATILE)"
    )

    key_indicators: Dict[str, Any] = Field(
        default_factory=dict,
        description="Key technical indicators (RSI, MACD, ATR, etc.)"
    )

    forecast_summary: str = Field(
        ...,
        description="Summary of ML forecast predictions"
    )

    risk_factors: list[str] = Field(
        default_factory=list,
        description="Technical risk factors identified"
    )


class TechnicalAnalystAgent(BaseAgent):
    """
    Technical Analyst Agent.

    Specializes in technical analysis using:
    - Multiple ML forecasting models
    - Regime detection
    - Technical indicators
    - Support/resistance identification

    Uses quick-think LLM (Qwen3-14B) for routine technical analysis.
    """

    def _get_system_message(self) -> str:
        """
        Get technical analyst system message.

        Returns:
            System prompt for technical analysis role
        """
        return """You are a Technical Analyst for algorithmic trading.

Your role is to analyze market data using ML forecasts, technical indicators, and regime detection to produce structured technical analysis reports.

**Available Tools**:
- get_tcn_forecast: Get TCN model price forecast with confidence intervals
- get_xgboost_forecast: Get XGBoost model forecast (fast inference)
- get_lstm_forecast: Get LSTM model forecast
- get_regime_classification: Classify market regime (TRENDING_UP/DOWN, RANGING, VOLATILE)
- get_technical_indicators: Get RSI, MACD, Bollinger Bands, ATR, ADX, etc.
- get_market_data: Get historical OHLCV data
- get_forecast_accuracy: Get model accuracy metrics

**Analysis Workflow**:
1. **Fetch market data** for the symbol with appropriate timeframe
2. **Get ML forecasts** from multiple models (TCN, XGBoost, LSTM)
3. **Classify market regime** to understand current conditions
4. **Calculate technical indicators** (RSI, MACD, Bollinger Bands, ATR, ADX)
5. **Check forecast accuracy** to assess model reliability
6. **Identify support/resistance levels** from price action and indicators
7. **Synthesize findings** into a structured report

**Output Requirements**:
You must produce a JSON object with this structure:
{
    "directional_bias": "BULLISH" | "BEARISH" | "NEUTRAL",
    "confidence": 0.0-1.0,
    "current_price": float,
    "support_levels": [price1, price2, ...],
    "resistance_levels": [price1, price2, ...],
    "model_agreement": 0.0-1.0,  // % of models agreeing on direction
    "regime": "TRENDING_UP" | "TRENDING_DOWN" | "RANGING" | "VOLATILE",
    "key_indicators": {
        "rsi": float,
        "macd_signal": "BULLISH" | "BEARISH",
        "atr": float,
        "adx": float
    },
    "forecast_summary": "Brief summary of what ML models are predicting",
    "risk_factors": ["factor1", "factor2", ...]  // Technical risks identified
}

**Key Principles**:
- Always call multiple ML models to check agreement
- Check forecast accuracy before trusting predictions heavily
- Adjust confidence based on model agreement and regime clarity
- In VOLATILE or RANGING regimes, reduce confidence in directional predictions
- Identify at least 2 support levels and 2 resistance levels when possible
- Consider RSI for overbought/oversold conditions
- Use ADX to confirm trend strength
- Document risk factors (e.g., "RSI overbought >70", "Low model agreement <50%")

**Example Task**: "Analyze Gold technical conditions for a 4H swing trade"

Your analysis must be data-driven and objective. Avoid confirmation bias by reporting conflicting signals."""

    def _extract_decision(self, result: Any) -> Dict[str, Any]:
        """
        Extract technical report from AutoGen result.

        Args:
            result: AutoGen agent result

        Returns:
            Technical report dictionary
        """
        # AutoGen result is typically a TaskResult with messages
        # Extract the last message content which should contain the JSON report
        try:
            # Get the last message content
            if hasattr(result, 'messages') and result.messages:
                last_message = result.messages[-1]
                content = last_message.content if hasattr(last_message, 'content') else str(last_message)
            else:
                content = str(result)

            # Try to parse as JSON if it's a structured report
            import json
            import re

            # Extract JSON from markdown code blocks if present
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find JSON object directly
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                json_str = json_match.group(0) if json_match else content

            report_data = json.loads(json_str)

            # Validate against TechnicalReport schema
            report = TechnicalReport(**report_data)

            return report.model_dump()

        except Exception as e:
            # Fallback: return raw content with error flag
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error(
                "technical_report_extraction_failed",
                error=str(e),
                result=str(result)[:500],
            )

            return {
                "directional_bias": "NEUTRAL",
                "confidence": 0.0,
                "current_price": 0.0,
                "support_levels": [],
                "resistance_levels": [],
                "model_agreement": 0.0,
                "regime": "UNKNOWN",
                "key_indicators": {},
                "forecast_summary": "Failed to extract structured report",
                "risk_factors": ["Report extraction failed"],
                "raw_output": str(result)[:1000],
                "extraction_error": str(e),
            }


# Factory function for easy agent creation
def create_technical_analyst(
    agent_id: Any,
    session: Any,
    symbol: str,
    strategy_team_id: Any = None,
) -> TechnicalAnalystAgent:
    """
    Create a Technical Analyst agent instance.

    Args:
        agent_id: Agent UUID from database
        session: SQLAlchemy async session
        symbol: Trading symbol this analyst focuses on
        strategy_team_id: Optional strategy team ID

    Returns:
        Configured TechnicalAnalystAgent instance
    """
    from src.agents.base.agent_config import (
        AgentConfig,
        AgentType,
        AgentLayer,
        LLMTier,
    )

    config = AgentConfig(
        name=f"{symbol} Technical Analyst",
        agent_type=AgentType.TECHNICAL_ANALYST,
        layer=AgentLayer.ANALYSIS,
        strategy_team_id=strategy_team_id,
        llm_provider="ollama",
        llm_model="qwen3:14b",  # Quick-think model for routine analysis
        llm_tier=LLMTier.QUICK_THINK,
        temperature=0.1,  # Low temperature for factual analysis
        max_tokens=800,  # Enough for detailed report
        available_tools=[
            "get_tcn_forecast",
            "get_xgboost_forecast",
            "get_lstm_forecast",
            "get_regime_classification",
            "get_technical_indicators",
            "get_market_data",
            "get_forecast_accuracy",
        ],
        config_overrides={"symbol": symbol},
    )

    # Provide all MCP tools to the agent
    tools = [
        get_tcn_forecast,
        get_xgboost_forecast,
        get_lstm_forecast,
        get_regime_classification,
        get_technical_indicators,
        get_market_data,
        get_forecast_accuracy,
    ]

    return TechnicalAnalystAgent(
        agent_id=agent_id,
        config=config,
        session=session,
        tools=tools,
    )
