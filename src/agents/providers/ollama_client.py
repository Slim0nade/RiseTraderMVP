"""
Ollama LLM Client for RiseTrader Agents.

Provides access to local Ollama models (Qwen3-14B, DeepSeek-R1-14B) via OpenAI-compatible API.
Ollama runs at 192.168.0.123:11434 with OpenAI-compatible endpoints at /v1/chat/completions.

Models:
- qwen3:14b: Quick-think tier for classification, pattern recognition (fast, < 2s latency)
- deepseek-r1:14b: Deep-think tier for reasoning, strategy optimization (slower, ~10s latency)
"""

import os
from typing import Optional
import structlog
from autogen_core.models import ModelInfo
from autogen_ext.models.openai import OpenAIChatCompletionClient

logger = structlog.get_logger(__name__)


def _get_default_ollama_url() -> str:
    """
    Get default Ollama URL based on environment.

    Uses host.docker.internal when running in Docker, otherwise local network IP.
    Can be overridden with OLLAMA_BASE_URL environment variable.
    """
    # Check if explicit URL is set
    env_url = os.getenv("OLLAMA_BASE_URL")
    if env_url:
        # Ensure it has /v1 suffix
        return env_url if env_url.endswith("/v1") else f"{env_url}/v1"

    # Check if running in Docker (common indicators)
    in_docker = (
        os.path.exists("/.dockerenv") or
        os.path.exists("/app") or
        os.getenv("RUNNING_IN_DOCKER") == "true"
    )

    if in_docker:
        return "http://host.docker.internal:11434/v1"
    else:
        return "http://192.168.0.123:11434/v1"


def create_ollama_client(
    model: str = "qwen3:14b",
    base_url: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 500,
    api_key: Optional[str] = None,
) -> OpenAIChatCompletionClient:
    """
    Create an OpenAI-compatible client for Ollama local models.

    Ollama provides an OpenAI-compatible API at /v1/chat/completions, allowing
    us to use AutoGen's OpenAIChatCompletionClient with local models.

    Args:
        model: Model name (e.g., "qwen3:14b", "deepseek-r1:14b")
        base_url: Ollama server URL with /v1 endpoint (auto-detects if None)
        temperature: Sampling temperature (0.0-2.0)
        max_tokens: Maximum tokens to generate
        api_key: Optional API key (Ollama doesn't require it, but client needs something)

    Returns:
        Configured OpenAIChatCompletionClient for Ollama

    Example:
        >>> client = create_ollama_client(model="qwen3:14b", temperature=0.1)
        >>> agent = AssistantAgent(name="analyst", model_client=client)
    """

    # Auto-detect base URL if not provided
    if base_url is None:
        base_url = _get_default_ollama_url()
    else:
        # Ensure /v1 suffix for OpenAI-compatible API
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

    # Extract model family for ModelInfo (e.g., "qwen3" from "qwen3:14b")
    model_family = model.split(":")[0]

    # Create ModelInfo for the Ollama model
    model_info = ModelInfo(
        vision=False,  # Text-only models
        function_calling=True,  # Both Qwen3 and DeepSeek-R1 support function calling
        json_output=True,  # Both support JSON mode
        family=model_family,  # Model family identifier
    )

    # Use "ollama" as placeholder API key (Ollama doesn't require authentication)
    effective_api_key = api_key or "ollama"

    try:
        client = OpenAIChatCompletionClient(
            model=model,
            base_url=base_url,
            api_key=effective_api_key,
            model_info=model_info,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        logger.info(
            "ollama_client_created",
            model=model,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return client

    except Exception as e:
        logger.error(
            "ollama_client_creation_failed",
            model=model,
            base_url=base_url,
            error=str(e),
            exc_info=True,
        )
        raise


def create_quick_think_client(
    base_url: Optional[str] = None,
) -> OpenAIChatCompletionClient:
    """
    Create a quick-think Ollama client (Qwen3-14B).

    Optimized for fast inference (<2s latency):
    - Low temperature (0.1) for consistent output
    - Limited tokens (500) for fast responses
    - Used for classification, pattern recognition, simple analysis

    Args:
        base_url: Ollama server URL (auto-detects if None)

    Returns:
        Quick-think model client
    """
    return create_ollama_client(
        model="qwen3:14b",
        base_url=base_url,
        temperature=0.1,
        max_tokens=500,
    )


def create_deep_think_client(
    base_url: Optional[str] = None,
) -> OpenAIChatCompletionClient:
    """
    Create a deep-think Ollama client (DeepSeek-R1-14B).

    Optimized for reasoning and analysis (~10s latency):
    - Higher temperature (0.7) for creative reasoning
    - More tokens (2000) for detailed analysis
    - Used for strategy optimization, complex risk analysis, debate

    Args:
        base_url: Ollama server URL (auto-detects if None)

    Returns:
        Deep-think model client
    """
    return create_ollama_client(
        model="deepseek-r1:14b",
        base_url=base_url,
        temperature=0.7,
        max_tokens=2000,
    )
