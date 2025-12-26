"""
OpenAI LLM Client for RiseTrader Agents.

Provides access to OpenAI models (GPT-4o, GPT-4o-mini, o1, o3) for critical decisions
requiring highest quality structured outputs.

Cost-optimized strategy:
- Use primarily for Pydantic-validated outputs and critical decisions
- Target: <$10/month total LLM costs
- Most agent decisions use free local Ollama models
"""

import os
from typing import Optional
import structlog
from autogen_ext.models.openai import OpenAIChatCompletionClient

logger = structlog.get_logger(__name__)


def create_openai_client(
    model: str = "gpt-4o-mini",
    temperature: float = 0.1,
    max_tokens: int = 1000,
    api_key: Optional[str] = None,
) -> OpenAIChatCompletionClient:
    """
    Create OpenAI model client for AutoGen agents.

    Args:
        model: OpenAI model name ("gpt-4o", "gpt-4o-mini", "o1-preview", "o3-mini")
        temperature: Sampling temperature (0.0-2.0)
        max_tokens: Maximum tokens to generate
        api_key: Optional API key (defaults to OPENAI_API_KEY env var)

    Returns:
        Configured OpenAIChatCompletionClient

    Raises:
        ValueError: If API key not provided and OPENAI_API_KEY not set

    Example:
        >>> client = create_openai_client(model="gpt-4o-mini")
        >>> agent = AssistantAgent(name="risk_analyzer", model_client=client)
    """

    # Get API key from parameter or environment
    effective_api_key = api_key or os.getenv("OPENAI_API_KEY")

    if not effective_api_key:
        raise ValueError(
            "OpenAI API key required. Provide via 'api_key' parameter or "
            "set OPENAI_API_KEY environment variable."
        )

    try:
        # Import ModelInfo for custom model definitions
        from autogen_core.models import ModelInfo

        # Create model_info for the model
        model_info = ModelInfo(
            vision=False,
            function_calling=True,
            json_output=True,
            family="openai"
        )

        client = OpenAIChatCompletionClient(
            model=model,
            api_key=effective_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            model_info=model_info,
        )

        logger.info(
            "openai_client_created",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return client

    except Exception as e:
        logger.error(
            "openai_client_creation_failed",
            model=model,
            error=str(e),
            exc_info=True,
        )
        raise


def create_gpt4o_client(
    temperature: float = 0.1,
    api_key: Optional[str] = None,
) -> OpenAIChatCompletionClient:
    """
    Create GPT-4o client (most capable, higher cost).

    Use for:
    - Critical trading decisions requiring highest accuracy
    - Complex multi-step reasoning
    - Structured output generation with strict schema validation

    Args:
        temperature: Sampling temperature
        api_key: Optional API key

    Returns:
        GPT-4o model client
    """
    return create_openai_client(
        model="gpt-4o",
        temperature=temperature,
        max_tokens=2000,
        api_key=api_key,
    )


def create_gpt4o_mini_client(
    temperature: float = 0.1,
    api_key: Optional[str] = None,
) -> OpenAIChatCompletionClient:
    """
    Create GPT-4o-mini client (cost-effective, good quality).

    Use for:
    - Structured outputs with Pydantic validation
    - Secondary validation of local model outputs
    - Non-critical decisions requiring high reliability

    Args:
        temperature: Sampling temperature
        api_key: Optional API key

    Returns:
        GPT-4o-mini model client
    """
    return create_openai_client(
        model="gpt-4o-mini",
        temperature=temperature,
        max_tokens=1000,
        api_key=api_key,
    )


def create_o1_client(
    api_key: Optional[str] = None,
) -> OpenAIChatCompletionClient:
    """
    Create o1-preview client (advanced reasoning model).

    Use for:
    - Complex strategy optimization requiring deep reasoning
    - Multi-step problem solving
    - Research and analysis tasks

    Note: o1 models have fixed temperature and use reasoning tokens.

    Args:
        api_key: Optional API key

    Returns:
        o1-preview model client
    """
    return create_openai_client(
        model="o1-preview",
        temperature=1.0,  # o1 models use fixed temperature
        max_tokens=4000,  # o1 can handle longer reasoning chains
        api_key=api_key,
    )
