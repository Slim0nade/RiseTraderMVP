"""
LLM Provider Clients for RiseTrader Multi-Agent System.

Provides unified interface for different LLM providers using AutoGen 0.4 model clients:
- OllamaClient: Local Qwen3-14B and DeepSeek-R1-14B models
- OpenAIClient: GPT-4o, GPT-4o-mini, o1, o3 models
- AnthropicClient: Claude 3.5 Sonnet for structured outputs
- GoogleClient: Gemini 2.0 Flash for fast inference

All clients return AutoGen-compatible model clients that can be used with AssistantAgent.
"""

from src.agents.providers.ollama_client import create_ollama_client
from src.agents.providers.openai_client import create_openai_client
from src.agents.providers.anthropic_client import create_anthropic_client
from src.agents.providers.google_client import create_google_client
from src.agents.providers.model_router import LLMRouter, LLMTier

__all__ = [
    "create_ollama_client",
    "create_openai_client",
    "create_anthropic_client",
    "create_google_client",
    "LLMRouter",
    "LLMTier",
]
