"""
Anthropic (Claude) LLM Client for RiseTrader Agents.

Provides access to Claude models for structured output generation and high-reliability decisions.
Claude 3.5 Sonnet excels at following strict output schemas and safety-critical reasoning.

Use cases:
- Generating Pydantic-validated structured outputs
- Critical decision validation requiring highest reliability
- Complex reasoning with strong safety guarantees
"""

import os
from typing import Optional
import structlog
from autogen_ext.models.openai import OpenAIChatCompletionClient

logger = structlog.get_logger(__name__)


def create_anthropic_client(
    model: str = "claude-3-5-sonnet-20250219",
    temperature: float = 0.1,
    max_tokens: int = 1000,
    api_key: Optional[str] = None,
) -> OpenAIChatCompletionClient:
    """
    Create Anthropic Claude client using OpenAI-compatible interface.

    AutoGen 0.4 supports Anthropic via the OpenAI-compatible API provided by
    Anthropic's API or via LiteLLM proxy.

    Args:
        model: Claude model name
        temperature: Sampling temperature (0.0-1.0 for Claude)
        max_tokens: Maximum tokens to generate
        api_key: Optional API key (defaults to ANTHROPIC_API_KEY env var)

    Returns:
        Configured model client for Claude

    Raises:
        ValueError: If API key not provided and ANTHROPIC_API_KEY not set

    Example:
        >>> client = create_anthropic_client(model="claude-3-5-sonnet-20250219")
        >>> agent = AssistantAgent(name="validator", model_client=client)
    """

    # Get API key from parameter or environment
    effective_api_key = api_key or os.getenv("ANTHROPIC_API_KEY")

    if not effective_api_key:
        raise ValueError(
            "Anthropic API key required. Provide via 'api_key' parameter or "
            "set ANTHROPIC_API_KEY environment variable."
        )

    # Note: This assumes you're using LiteLLM or similar proxy to convert
    # Anthropic API to OpenAI-compatible format. If using Anthropic directly,
    # you'd need the anthropic-specific client from autogen_ext.models.anthropic

    try:
        # Using OpenAI-compatible interface via LiteLLM or similar
        # Base URL should point to your LiteLLM proxy endpoint
        base_url = os.getenv("LITELLM_BASE_URL", "http://localhost:4000")

        client = OpenAIChatCompletionClient(
            model=model,
            base_url=base_url,
            api_key=effective_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        logger.info(
            "anthropic_client_created",
            model=model,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return client

    except Exception as e:
        logger.error(
            "anthropic_client_creation_failed",
            model=model,
            error=str(e),
            exc_info=True,
        )
        raise


def create_claude_sonnet_client(
    temperature: float = 0.1,
    api_key: Optional[str] = None,
) -> OpenAIChatCompletionClient:
    """
    Create Claude 3.5 Sonnet client (best for structured outputs).

    Use for:
    - Pydantic schema-validated outputs
    - High-stakes decision validation
    - Safety-critical reasoning

    Args:
        temperature: Sampling temperature
        api_key: Optional API key

    Returns:
        Claude 3.5 Sonnet model client
    """
    return create_anthropic_client(
        model="claude-3-5-sonnet-20250219",
        temperature=temperature,
        max_tokens=2000,
        api_key=api_key,
    )
