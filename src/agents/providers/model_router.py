"""
LLM Router for Intelligent Model Selection.

Routes tasks to appropriate LLM tier based on complexity and requirements:
- Quick-think: Local Ollama (Qwen3-14B) for fast classification
- Deep-think: Local Ollama (DeepSeek-R1-14B) for reasoning
- Structured: Claude 3.5 Sonnet for Pydantic-validated outputs
- Fast: Gemini 2.0 Flash for high-volume operations

Cost optimization strategy:
- 95%+ of decisions use free local Ollama models
- <5% use paid models for critical/structured outputs
- Target: <$10/month total LLM costs
"""

from enum import Enum
from typing import Optional
import structlog
from autogen_ext.models.openai import OpenAIChatCompletionClient

from src.agents.providers.ollama_client import (
    create_quick_think_client,
    create_deep_think_client,
)
from src.agents.providers.openai_client import create_gpt4o_mini_client
from src.agents.providers.anthropic_client import create_claude_sonnet_client
from src.agents.providers.google_client import create_gemini_flash_client

logger = structlog.get_logger(__name__)


class LLMTier(str, Enum):
    """LLM tier classification for task routing."""

    QUICK_THINK = "quick_think"  # Fast local (Qwen3-14B)
    DEEP_THINK = "deep_think"  # Reasoning local (DeepSeek-R1-14B)
    STRUCTURED = "structured"  # Structured output (Claude/GPT-4o-mini)
    FAST_CLOUD = "fast_cloud"  # Fast cloud (Gemini Flash)


class TaskType(str, Enum):
    """Task type classification for routing decisions."""

    CLASSIFICATION = "classification"  # Simple classification (5-10 options)
    PATTERN_RECOGNITION = "pattern_recognition"  # Technical pattern detection
    SENTIMENT_ANALYSIS = "sentiment_analysis"  # Text sentiment classification
    REASONING = "reasoning"  # Multi-step reasoning required
    STRATEGY_OPTIMIZATION = "strategy_optimization"  # Complex optimization
    RISK_ANALYSIS = "risk_analysis"  # Multi-factor risk assessment
    STRUCTURED_OUTPUT = "structured_output"  # Pydantic schema validation required
    CRITICAL_DECISION = "critical_decision"  # High-stakes decision requiring validation


class LLMRouter:
    """
    Intelligent LLM router for cost-optimized model selection.

    Routes tasks to appropriate model tier based on complexity and requirements.
    Prioritizes free local Ollama models, using paid models only when necessary.

    Example:
        >>> router = LLMRouter()
        >>> client = router.get_client(TaskType.CLASSIFICATION)  # Returns Qwen3
        >>> client = router.get_client(TaskType.REASONING)  # Returns DeepSeek-R1
        >>> client = router.get_client(TaskType.STRUCTURED_OUTPUT)  # Returns Claude
    """

    def __init__(
        self,
        ollama_base_url: str = "http://192.168.0.123:11434/v1",
        enable_paid_models: bool = True,
    ):
        """
        Initialize LLM router.

        Args:
            ollama_base_url: Base URL for Ollama server
            enable_paid_models: If False, fall back to local models for all tasks
        """
        self.ollama_base_url = ollama_base_url
        self.enable_paid_models = enable_paid_models

        # Cache clients to avoid recreation
        self._client_cache = {}

        logger.info(
            "llm_router_initialized",
            ollama_base_url=ollama_base_url,
            enable_paid_models=enable_paid_models,
        )

    def get_client(
        self,
        task_type: TaskType,
        force_tier: Optional[LLMTier] = None,
    ) -> OpenAIChatCompletionClient:
        """
        Get appropriate LLM client for the given task type.

        Args:
            task_type: Type of task to be performed
            force_tier: Optional tier to force (overrides routing logic)

        Returns:
            Configured model client for the task

        Example:
            >>> router = LLMRouter()
            >>> client = router.get_client(TaskType.CLASSIFICATION)
            >>> # Returns quick-think Ollama client (Qwen3-14B)
        """

        # Determine tier based on task type (unless forced)
        tier = force_tier or self._route_task_to_tier(task_type)

        # Return cached client if available
        cache_key = tier.value
        if cache_key in self._client_cache:
            return self._client_cache[cache_key]

        # Create client based on tier
        client = self._create_client_for_tier(tier)
        self._client_cache[cache_key] = client

        logger.info(
            "llm_client_selected",
            task_type=task_type.value,
            tier=tier.value,
            forced=force_tier is not None,
        )

        return client

    def _route_task_to_tier(self, task_type: TaskType) -> LLMTier:
        """
        Route task type to appropriate LLM tier.

        Routing strategy:
        - Simple tasks → Quick-think (local Qwen3)
        - Complex reasoning → Deep-think (local DeepSeek-R1)
        - Structured outputs → Structured tier (Claude/GPT-4o-mini)
        - High-volume fast → Fast cloud (Gemini Flash)

        Args:
            task_type: Type of task

        Returns:
            Appropriate LLM tier
        """

        routing_map = {
            TaskType.CLASSIFICATION: LLMTier.QUICK_THINK,
            TaskType.PATTERN_RECOGNITION: LLMTier.QUICK_THINK,
            TaskType.SENTIMENT_ANALYSIS: LLMTier.QUICK_THINK,
            TaskType.REASONING: LLMTier.DEEP_THINK,
            TaskType.STRATEGY_OPTIMIZATION: LLMTier.DEEP_THINK,
            TaskType.RISK_ANALYSIS: LLMTier.DEEP_THINK,
            TaskType.STRUCTURED_OUTPUT: LLMTier.STRUCTURED,
            TaskType.CRITICAL_DECISION: LLMTier.STRUCTURED,
        }

        return routing_map.get(task_type, LLMTier.QUICK_THINK)

    def _create_client_for_tier(self, tier: LLMTier) -> OpenAIChatCompletionClient:
        """
        Create LLM client for the specified tier.

        Args:
            tier: LLM tier

        Returns:
            Configured model client

        Raises:
            ValueError: If tier not supported or paid models disabled when required
        """

        if tier == LLMTier.QUICK_THINK:
            return create_quick_think_client(base_url=self.ollama_base_url)

        elif tier == LLMTier.DEEP_THINK:
            return create_deep_think_client(base_url=self.ollama_base_url)

        elif tier == LLMTier.STRUCTURED:
            if not self.enable_paid_models:
                logger.warning(
                    "structured_output_requested_but_paid_disabled",
                    falling_back="deep_think_local",
                )
                return create_deep_think_client(base_url=self.ollama_base_url)

            # Prefer Claude for structured outputs, fallback to GPT-4o-mini
            try:
                return create_claude_sonnet_client()
            except ValueError:
                logger.warning(
                    "claude_unavailable_falling_back_to_gpt4o_mini",
                )
                return create_gpt4o_mini_client()

        elif tier == LLMTier.FAST_CLOUD:
            if not self.enable_paid_models:
                logger.warning(
                    "fast_cloud_requested_but_paid_disabled",
                    falling_back="quick_think_local",
                )
                return create_quick_think_client(base_url=self.ollama_base_url)

            try:
                return create_gemini_flash_client()
            except ValueError:
                logger.warning(
                    "gemini_unavailable_falling_back_to_local",
                )
                return create_quick_think_client(base_url=self.ollama_base_url)

        else:
            raise ValueError(f"Unsupported LLM tier: {tier}")

    def get_tier_for_agent_type(self, agent_type: str) -> LLMTier:
        """
        Get recommended LLM tier for a specific agent type.

        Maps agent types to their optimal LLM tier based on the agent's
        typical task complexity and output requirements.

        Args:
            agent_type: Agent type string (e.g., "technical_analyst", "bull_researcher")

        Returns:
            Recommended LLM tier

        Example:
            >>> router = LLMRouter()
            >>> tier = router.get_tier_for_agent_type("technical_analyst")
            >>> # Returns LLMTier.QUICK_THINK
        """

        # Quick-think agents (classification, pattern recognition)
        quick_think_agents = {
            "technical_analyst",
            "fundamental_analyst",
            "sentiment_analyst",
            "position_monitor",
            "execution",
        }

        # Deep-think agents (reasoning, strategy, optimization)
        deep_think_agents = {
            "bull_researcher",
            "bear_researcher",
            "trade_decision",
            "position_sizing",
            "stop_loss",
            "take_profit",
            "risk_overseer",
        }

        if agent_type in quick_think_agents:
            return LLMTier.QUICK_THINK
        elif agent_type in deep_think_agents:
            return LLMTier.DEEP_THINK
        else:
            # Default to quick-think for unknown agents
            logger.warning(
                "unknown_agent_type_defaulting_to_quick_think",
                agent_type=agent_type,
            )
            return LLMTier.QUICK_THINK
