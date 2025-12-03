"""
Google (Gemini) LLM Client for RiseTrader Agents.

Provides access to Gemini models for fast, cost-effective inference.
Gemini 2.0 Flash offers excellent speed/cost ratio for high-volume decisions.

Use cases:
- High-frequency classification tasks
- Fast pattern recognition
- Cost-sensitive bulk operations
"""

import os
from typing import Optional
import structlog
from autogen_ext.models.openai import OpenAIChatCompletionClient

logger = structlog.get_logger(__name__)


def create_google_client(
    model: str = "gemini-2.0-flash-exp",
    temperature: float = 0.1,
    max_tokens: int = 1000,
    api_key: Optional[str] = None,
) -> OpenAIChatCompletionClient:
    """
    Create Google Gemini client using OpenAI-compatible interface.

    AutoGen 0.4 supports Gemini via LiteLLM proxy or OpenAI-compatible wrappers.

    Args:
        model: Gemini model name ("gemini-2.0-flash-exp", "gemini-pro")
        temperature: Sampling temperature (0.0-2.0)
        max_tokens: Maximum tokens to generate
        api_key: Optional API key (defaults to GOOGLE_API_KEY env var)

    Returns:
        Configured model client for Gemini

    Raises:
        ValueError: If API key not provided and GOOGLE_API_KEY not set

    Example:
        >>> client = create_google_client(model="gemini-2.0-flash-exp")
        >>> agent = AssistantAgent(name="classifier", model_client=client)
    """

    # Get API key from parameter or environment
    effective_api_key = api_key or os.getenv("GOOGLE_API_KEY")

    if not effective_api_key:
        raise ValueError(
            "Google API key required. Provide via 'api_key' parameter or "
            "set GOOGLE_API_KEY environment variable."
        )

    try:
        # Using OpenAI-compatible interface via LiteLLM
        base_url = os.getenv("LITELLM_BASE_URL", "http://localhost:4000")

        client = OpenAIChatCompletionClient(
            model=model,
            base_url=base_url,
            api_key=effective_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        logger.info(
            "google_client_created",
            model=model,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return client

    except Exception as e:
        logger.error(
            "google_client_creation_failed",
            model=model,
            error=str(e),
            exc_info=True,
        )
        raise


def create_gemini_flash_client(
    temperature: float = 0.1,
    api_key: Optional[str] = None,
) -> OpenAIChatCompletionClient:
    """
    Create Gemini 2.0 Flash client (fast, cost-effective).

    Use for:
    - High-volume classification tasks
    - Fast pattern recognition
    - Cost-sensitive operations

    Args:
        temperature: Sampling temperature
        api_key: Optional API key

    Returns:
        Gemini 2.0 Flash model client
    """
    return create_google_client(
        model="gemini-2.0-flash-exp",
        temperature=temperature,
        max_tokens=1000,
        api_key=api_key,
    )
