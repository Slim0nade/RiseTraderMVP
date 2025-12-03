"""
Debate Team: SelectorGroupChat for Bull/Bear Adversarial Reasoning.

Implements adversarial debate between:
- Bull Researcher: Argues for LONG positions
- Bear Researcher: Argues for SHORT positions
- Moderator (model-based selector): Decides who speaks next

The debate produces balanced, well-reasoned trade recommendations.
"""

from typing import Optional
import structlog
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_ext.models.openai import OpenAIChatCompletionClient

from src.agents.providers import create_deep_think_client
from src.agents.tools import get_tcn_forecast, get_regime_classification

logger = structlog.get_logger(__name__)


def create_debate_team(
    symbol: str,
    analysis_summary: str,
    model_client: Optional[OpenAIChatCompletionClient] = None,
    max_turns: int = 4,
) -> SelectorGroupChat:
    """
    Create adversarial debate team using SelectorGroupChat.

    Bull and Bear researchers debate the market outlook based on
    the analysis team's findings. The model-based selector chooses
    which researcher speaks next based on the conversation flow.

    Args:
        symbol: Trading symbol
        analysis_summary: Summary from analysis team
        model_client: Optional model client (defaults to deep-think Ollama)
        max_turns: Maximum debate turns

    Returns:
        Configured SelectorGroupChat team
    """

    if model_client is None:
        model_client = create_deep_think_client()

    # Bull Researcher
    bull_researcher = AssistantAgent(
        name="BullResearcher",
        model_client=model_client,
        description="Argues for LONG/BUY positions with supporting evidence",
        tools=[get_tcn_forecast, get_regime_classification],
        system_message=f"""You are the Bull Researcher for {symbol}.

Your role: Build the strongest case for a LONG position.

Analysis context:
{analysis_summary}

Debate guidelines:
- Use ML forecasts and regime data to support bullish thesis
- Counter bear arguments with data and logic
- Identify asymmetric upside opportunities
- Acknowledge risks but emphasize reward potential
- End with clear conviction level (HIGH/MEDIUM/LOW)

Be rigorous, data-driven, and persuasive.""",
        reflect_on_tool_use=True,
    )

    # Bear Researcher
    bear_researcher = AssistantAgent(
        name="BearResearcher",
        model_client=model_client,
        description="Argues for SHORT/SELL positions with supporting evidence",
        tools=[get_tcn_forecast, get_regime_classification],
        system_message=f"""You are the Bear Researcher for {symbol}.

Your role: Build the strongest case for a SHORT position or staying out.

Analysis context:
{analysis_summary}

Debate guidelines:
- Use ML forecasts and regime data to support bearish thesis
- Counter bull arguments with data and logic
- Identify downside risks and catalysts
- Challenge optimistic assumptions
- End with clear conviction level (HIGH/MEDIUM/LOW)

Be rigorous, data-driven, and persuasive.""",
        reflect_on_tool_use=True,
    )

    # Termination: 4 messages (2 rounds of debate) or CONCLUSION keyword
    termination = (
        MaxMessageTermination(max_messages=max_turns)
        | TextMentionTermination("CONCLUSION")
    )

    # Selector prompt for model-based speaker selection
    selector_prompt = """Select the next speaker for the trading debate.

{roles}

Conversation so far:
{history}

Choose from {participants} to continue the debate.
- Start with Bull Researcher
- Alternate to allow counter-arguments
- If both sides presented, select either to conclude

Select ONE speaker."""

    team = SelectorGroupChat(
        participants=[bull_researcher, bear_researcher],
        model_client=model_client,
        termination_condition=termination,
        selector_prompt=selector_prompt,
        allow_repeated_speaker=False,  # Force alternation
    )

    logger.info(
        "debate_team_created",
        symbol=symbol,
        participants=["BullResearcher", "BearResearcher"],
        max_turns=max_turns,
    )

    return team
