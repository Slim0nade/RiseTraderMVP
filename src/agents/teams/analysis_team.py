"""
Analysis Team: RoundRobinGroupChat for Sequential Analyst Collaboration.

Coordinates three analyst agents in a structured round-robin pattern:
1. Technical Analyst → Analyzes charts, patterns, indicators
2. Fundamental Analyst → Analyzes economic data, supply/demand
3. Sentiment Analyst → Analyzes news, COT data, market sentiment

Each agent analyzes the market sequentially, building on previous insights.
"""

from typing import List, Optional
import structlog
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_ext.models.openai import OpenAIChatCompletionClient

from src.agents.providers import create_quick_think_client
from src.agents.tools import (
    get_technical_indicators,
    get_market_data,
    get_forecast_accuracy,
)

logger = structlog.get_logger(__name__)


def create_analysis_team(
    symbol: str,
    model_client: Optional[OpenAIChatCompletionClient] = None,
    max_rounds: int = 1,
) -> RoundRobinGroupChat:
    """
    Create an analysis team using RoundRobinGroupChat pattern.

    The team follows a fixed rotation:
    Technical → Fundamental → Sentiment → (repeat if max_rounds > 1)

    Each analyst:
    - Has access to relevant MCP tools
    - Provides structured analysis in their domain
    - Can reference previous analysts' findings

    Args:
        symbol: Trading symbol to analyze
        model_client: Optional model client (defaults to quick-think Ollama)
        max_rounds: Maximum number of round-robin cycles

    Returns:
        Configured RoundRobinGroupChat team

    Example:
        >>> team = create_analysis_team("Gold")
        >>> result = await team.run(task="Analyze current market conditions")
        >>> # Returns combined analysis from all three analysts
    """

    # Use quick-think model for fast analysis
    if model_client is None:
        model_client = create_quick_think_client()

    # 1. Technical Analyst Agent
    technical_analyst = AssistantAgent(
        name="TechnicalAnalyst",
        model_client=model_client,
        tools=[get_technical_indicators, get_market_data],
        system_message=f"""You are a Technical Analyst for {symbol} trading.

Your role:
- Analyze price charts, patterns, and technical indicators
- Identify support/resistance levels, trend direction, momentum
- Use tools to get RSI, MACD, Bollinger Bands, moving averages
- Provide actionable technical signals (BUY/SELL/HOLD)

Analysis format:
**Technical Analysis for {symbol}**
- Trend: [UP/DOWN/SIDEWAYS]
- Key Levels: Support X, Resistance Y
- Indicators: RSI=X, MACD=[signal], BB=[position]
- Pattern: [if any notable patterns detected]
- Signal: [BUY/SELL/HOLD] with confidence
- Rationale: [brief explanation]

Be concise. Focus on actionable insights.""",
        reflect_on_tool_use=True,
    )

    # 2. Fundamental Analyst Agent
    fundamental_analyst = AssistantAgent(
        name="FundamentalAnalyst",
        model_client=model_client,
        tools=[],  # Could add economic data tools in future
        system_message=f"""You are a Fundamental Analyst for {symbol} trading.

Your role:
- Analyze supply/demand fundamentals, macroeconomic factors
- Consider inventory levels, production data, economic indicators
- Assess longer-term value and fair price levels
- Review the Technical Analyst's findings and add fundamental context

Analysis format:
**Fundamental Analysis for {symbol}**
- Supply/Demand: [current balance assessment]
- Economic Drivers: [key factors affecting price]
- Fair Value: [estimated fair price range]
- Outlook: [BULLISH/BEARISH/NEUTRAL] (short-term / medium-term)
- Fundamental Signal: [BUY/SELL/HOLD]
- Rationale: [brief explanation]

Reference the technical analysis if it provides relevant context.
Be concise and actionable.""",
        reflect_on_tool_use=False,
    )

    # 3. Sentiment Analyst Agent
    sentiment_analyst = AssistantAgent(
        name="SentimentAnalyst",
        model_client=model_client,
        tools=[get_forecast_accuracy],  # Can check ML model confidence
        system_message=f"""You are a Sentiment Analyst for {symbol} trading.

Your role:
- Analyze market sentiment, positioning, and crowd behavior
- Consider COT (Commitment of Traders) data if available
- Assess contrarian indicators and extreme positioning
- Synthesize insights from Technical and Fundamental analysts

Analysis format:
**Sentiment Analysis for {symbol}**
- Market Sentiment: [BULLISH/BEARISH/NEUTRAL]
- Positioning: [if extreme long/short detected]
- Contrarian Signal: [if sentiment is overly one-sided]
- ML Model Confidence: [check forecast_accuracy tool]
- Final Recommendation: [BUY/SELL/HOLD]
- Conviction Level: [HIGH/MEDIUM/LOW]
- Summary: [synthesize all three analyses into 2-3 sentences]

Review both previous analyses and provide a final synthesis.
Be decisive and clear.""",
        reflect_on_tool_use=True,
    )

    # Create RoundRobinGroupChat with fixed rotation
    # Termination after one complete round (all 3 agents speak once)
    termination = MaxMessageTermination(max_messages=3 * max_rounds)

    team = RoundRobinGroupChat(
        participants=[technical_analyst, fundamental_analyst, sentiment_analyst],
        termination_condition=termination,
    )

    logger.info(
        "analysis_team_created",
        symbol=symbol,
        participants=["TechnicalAnalyst", "FundamentalAnalyst", "SentimentAnalyst"],
        max_rounds=max_rounds,
    )

    return team
