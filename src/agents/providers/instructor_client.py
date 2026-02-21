"""
Instructor-based LLM Client for RiseTrader Agents.

Uses the `instructor` library with OpenAI SDK pointed at Ollama's
OpenAI-compatible endpoint (/v1) for guaranteed JSON schema compliance.

Key Features:
- Automatic retries on validation failure
- Pydantic model validation built-in
- Works via Ollama's /v1/chat/completions endpoint
- Uses OpenAI SDK for reliability

Recommended Models (by speed):
- mistral:7b-instruct: 5-10s, excellent JSON
- llama3.1:8b: 6-10s, good JSON  
- phi4-mini: 6-10s, good JSON
- mistral-small3.1: 60-70s, excellent JSON (slow but reliable)

NOT Recommended (too slow or poor JSON):
- qwen3:14b: 90s+, poor schema compliance
- deepseek-r1:14b: 90s+, poor schema compliance
"""

import os
import structlog
from typing import Type, TypeVar, Optional
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

# Generic type for Pydantic models
T = TypeVar("T", bound=BaseModel)


def create_instructor_client(
    model: str = "mistral:7b-instruct",
    base_url: Optional[str] = None,
    timeout: float = 60.0,
):
    """
    Create an Instructor-wrapped client using OpenAI SDK with Ollama backend.
    
    Uses Ollama's OpenAI-compatible endpoint at /v1/chat/completions.
    
    Args:
        model: Ollama model name (e.g., "mistral:7b-instruct")
        base_url: Ollama server URL (default: from OLLAMA_BASE_URL env or localhost)
        timeout: Request timeout in seconds
    
    Returns:
        Instructor client ready for structured output
    """
    import instructor
    from openai import OpenAI
    
    # Get Ollama host from environment or default
    if base_url is None:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://75.154.254.174:11434")
    
    # Ensure base_url ends with /v1 for OpenAI compatibility
    base_url = base_url.rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    
    logger.info(
        "creating_instructor_client",
        model=model,
        base_url=base_url,
        timeout=timeout,
    )
    
    # Create OpenAI client pointed at Ollama
    openai_client = OpenAI(
        base_url=base_url,
        api_key="ollama",  # Ollama doesn't need a real API key
        timeout=timeout,
    )
    
    # Wrap with instructor for structured output
    # Use JSON mode for Ollama compatibility
    return instructor.from_openai(
        openai_client,
        mode=instructor.Mode.JSON,
    ), model


class InstructorOllamaClient:
    """
    High-level Instructor client for Ollama with built-in error handling.
    
    Uses OpenAI SDK pointed at Ollama's /v1 endpoint for maximum compatibility.
    
    Example:
        >>> client = InstructorOllamaClient(model="mistral:7b-instruct")
        >>> result = client.get_structured_response(
        ...     response_model=PositionSizeDecision,
        ...     system_prompt="You are a position sizing expert.",
        ...     user_prompt="Size a Gold trade with 0.25 Kelly...",
        ... )
        >>> print(result.lot_quantity)  # Guaranteed to be float
    """
    
    def __init__(
        self,
        model: str = "mistral:7b-instruct",
        base_url: Optional[str] = None,
        mode: str = "JSON",  # Kept for API compatibility
        default_max_retries: int = 3,
        default_timeout: float = 60.0,
    ):
        """
        Initialize the Instructor Ollama client.
        
        Args:
            model: Ollama model name
            base_url: Ollama server URL
            mode: Instructor mode (only JSON supported for Ollama)
            default_max_retries: Default number of retries
            default_timeout: Default timeout in seconds
        """
        self.model = model
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://75.154.254.174:11434")
        self.mode = mode
        self.default_max_retries = default_max_retries
        self.default_timeout = default_timeout
        self._client = None
        self._model_name = None
    
    @property
    def client(self):
        """Lazy initialization of instructor client."""
        if self._client is None:
            self._client, self._model_name = create_instructor_client(
                model=self.model,
                base_url=self.base_url,
                timeout=self.default_timeout,
            )
        return self._client
    
    def get_structured_response(
        self,
        response_model: Type[T],
        system_prompt: str,
        user_prompt: str,
        max_retries: Optional[int] = None,
        timeout: Optional[float] = None,
        temperature: float = 0.0,
    ) -> T:
        """
        Get a validated structured response (synchronous).
        
        Args:
            response_model: Pydantic model class
            system_prompt: System message
            user_prompt: User message
            max_retries: Number of retries (default: self.default_max_retries)
            timeout: Timeout in seconds (default: self.default_timeout)
            temperature: LLM temperature
            
        Returns:
            Validated Pydantic model instance
        """
        import time
        
        start_time = time.time()
        
        try:
            # Use instructor's create method with model specified
            result = self.client.chat.completions.create(
                model=self.model,
                response_model=response_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_retries=max_retries or self.default_max_retries,
                temperature=temperature,
            )
            
            elapsed = time.time() - start_time
            logger.info(
                "instructor_response_received",
                model=self.model,
                response_model=response_model.__name__,
                elapsed_seconds=round(elapsed, 2),
            )
            
            return result
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                "instructor_response_failed",
                model=self.model,
                response_model=response_model.__name__,
                elapsed_seconds=round(elapsed, 2),
                error=str(e),
            )
            raise
    
    async def get_structured_response_async(
        self,
        response_model: Type[T],
        system_prompt: str,
        user_prompt: str,
        max_retries: Optional[int] = None,
        timeout: Optional[float] = None,
        temperature: float = 0.0,
    ) -> T:
        """
        Get a validated structured response (asynchronous).
        
        For async usage in FastAPI/async agents.
        """
        import asyncio
        
        # Run sync method in thread pool
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.get_structured_response(
                response_model=response_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_retries=max_retries,
                timeout=timeout,
                temperature=temperature,
            )
        )


# Pre-configured clients for common use cases
def create_fast_json_client(base_url: Optional[str] = None) -> InstructorOllamaClient:
    """
    Create a fast JSON-mode client (mistral:7b-instruct).
    
    Best for:
    - Position sizing decisions
    - Simple structured outputs
    - Fast response times (5-10s)
    """
    return InstructorOllamaClient(
        model="mistral:7b-instruct",
        base_url=base_url,
        mode="JSON",
        default_max_retries=3,
        default_timeout=30.0,
    )


def create_reliable_json_client(base_url: Optional[str] = None) -> InstructorOllamaClient:
    """
    Create a reliable JSON-mode client (mistral-small3.1).
    
    Best for:
    - Complex structured outputs
    - When accuracy matters more than speed
    - Slower but more reliable (60-70s)
    """
    return InstructorOllamaClient(
        model="mistral-small3.1",
        base_url=base_url,
        mode="JSON",
        default_max_retries=2,
        default_timeout=120.0,
    )


def create_llama_json_client(base_url: Optional[str] = None) -> InstructorOllamaClient:
    """
    Create a Llama 3.1 JSON-mode client.
    
    Alternative to Mistral with good JSON compliance.
    """
    return InstructorOllamaClient(
        model="llama3.1:8b",
        base_url=base_url,
        mode="JSON",
        default_max_retries=3,
        default_timeout=30.0,
    )
