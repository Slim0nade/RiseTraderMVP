"""
Trading Pipeline: Orchestrates multi-stage decision workflow.

Coordinates the full trading decision process:
1. Analysis Team → Multi-analyst market analysis
2. Debate Team → Bull/Bear adversarial reasoning
3. Decision Agent → Trade intent decision
4. Execution Agent → Order placement

Can be implemented as Swarm (with handoffs) or as sequential team calls.
"""

from typing import Dict, Any, Optional
import structlog

from src.agents.teams.analysis_team import create_analysis_team
from src.agents.teams.debate_team import create_debate_team

logger = structlog.get_logger(__name__)


async def run_trading_pipeline(
    symbol: str,
    task: str = "Analyze current market and recommend trade",
) -> Dict[str, Any]:
    """
    Execute full trading decision pipeline.

    Workflow:
    1. Analysis team produces market assessment
    2. Debate team provides bull/bear perspectives
    3. Results combined for decision making

    Args:
        symbol: Trading symbol
        task: Task description for analysis team

    Returns:
        Dictionary with analysis, debate, and recommendation

    Example:
        >>> result = await run_trading_pipeline("Gold")
        >>> print(result['recommendation'])
    """

    logger.info("trading_pipeline_started", symbol=symbol)

    # Step 1: Run analysis team
    analysis_team = create_analysis_team(symbol)
    analysis_result = await analysis_team.run(task=task)

    # Extract summary from analysis messages
    analysis_summary = _extract_summary(analysis_result.messages)

    logger.info("analysis_complete", symbol=symbol, message_count=len(analysis_result.messages))

    # Step 2: Run debate team with analysis context
    debate_team = create_debate_team(
        symbol=symbol,
        analysis_summary=analysis_summary,
    )

    debate_task = f"Debate whether to go LONG or SHORT on {symbol} based on the analysis"
    debate_result = await debate_team.run(task=debate_task)

    logger.info("debate_complete", symbol=symbol, message_count=len(debate_result.messages))

    # Combine results
    return {
        "symbol": symbol,
        "analysis_messages": [
            {"source": msg.source, "content": msg.content}
            for msg in analysis_result.messages
        ],
        "debate_messages": [
            {"source": msg.source, "content": msg.content}
            for msg in debate_result.messages
        ],
        "recommendation": _extract_final_recommendation(
            analysis_result.messages,
            debate_result.messages,
        ),
    }


def _extract_summary(messages) -> str:
    """Extract text summary from message list."""
    return "\n\n".join([f"{msg.source}: {msg.content}" for msg in messages])


def _extract_final_recommendation(analysis_messages, debate_messages) -> Dict[str, Any]:
    """Extract final trading recommendation from pipeline results."""

    # Simple extraction - last message from sentiment analyst + debate conclusion
    sentiment_msg = [m for m in analysis_messages if m.source == "SentimentAnalyst"]
    last_sentiment = sentiment_msg[-1].content if sentiment_msg else "No sentiment analysis"

    debate_conclusion = debate_messages[-1].content if debate_messages else "No debate"

    return {
        "sentiment_analysis": last_sentiment,
        "debate_conclusion": debate_conclusion,
        "status": "pipeline_complete",
    }
