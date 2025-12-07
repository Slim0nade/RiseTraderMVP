"""
Agent Team Factory for creating strategy-specific teams.

Provides factory methods to create teams with appropriate configurations
based on symbol, strategy type, and requirements.
"""

from typing import Optional
import structlog
from autogen_ext.models.openai import OpenAIChatCompletionClient

# TODO: Temporarily commented out until ollama_client.py is created
# from src.agents.teams.analysis_team import create_analysis_team
# from src.agents.teams.debate_team import create_debate_team
from src.agents.providers import LLMRouter, LLMTier

logger = structlog.get_logger(__name__)


class AgentTeamFactory:
    """
    Factory for creating AutoGen agent teams.

    Provides consistent team creation with appropriate LLM clients
    and configurations based on trading requirements.
    """

    def __init__(
        self,
        llm_router: Optional[LLMRouter] = None,
        ollama_base_url: str = "http://192.168.0.123:11434/v1",
    ):
        """
        Initialize team factory.

        Args:
            llm_router: Optional LLM router for intelligent model selection
            ollama_base_url: Ollama server URL
        """
        self.llm_router = llm_router or LLMRouter(ollama_base_url=ollama_base_url)

    def create_analysis_team(
        self,
        symbol: str,
        max_rounds: int = 1,
        force_tier: Optional[LLMTier] = None,
    ):
        """
        Create analysis team for a symbol.

        Args:
            symbol: Trading symbol
            max_rounds: Analysis rounds
            force_tier: Optional LLM tier override

        Returns:
            Configured RoundRobinGroupChat
        """

        # Get quick-think client for fast analysis
        tier = force_tier or LLMTier.QUICK_THINK
        model_client = self.llm_router.get_client(
            task_type=self.llm_router._route_task_to_tier.__self__.TaskType.CLASSIFICATION,
            force_tier=tier,
        )

        return create_analysis_team(
            symbol=symbol,
            model_client=model_client,
            max_rounds=max_rounds,
        )

    def create_debate_team(
        self,
        symbol: str,
        analysis_summary: str,
        max_turns: int = 4,
        force_tier: Optional[LLMTier] = None,
    ):
        """
        Create debate team for a symbol.

        Args:
            symbol: Trading symbol
            analysis_summary: Analysis team output
            max_turns: Maximum debate turns
            force_tier: Optional LLM tier override

        Returns:
            Configured SelectorGroupChat
        """

        # Get deep-think client for reasoning
        tier = force_tier or LLMTier.DEEP_THINK
        model_client = self.llm_router.get_client(
            task_type=self.llm_router._route_task_to_tier.__self__.TaskType.REASONING,
            force_tier=tier,
        )

        return create_debate_team(
            symbol=symbol,
            analysis_summary=analysis_summary,
            model_client=model_client,
            max_turns=max_turns,
        )
