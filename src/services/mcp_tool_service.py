"""
MCP Tool Service.

This service manages MCP (Model Context Protocol) tool registration, invocation,
circuit breaking, and caching for the intelligent agent system.

Responsibilities:
- Tool registration from contracts/mcp-tools.yaml
- Tool invocation with circuit breaker protection
- Response caching (Redis, 300s TTL)
- Prometheus metrics for tool performance
"""

import asyncio
import hashlib
import json
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from ..database.models.mcp_tool import MCPTool
from ..database.repositories.mcp_tool_repository import MCPToolRepository
from ..ml.tools import (
    get_tcn_forecast,
    get_tft_prediction,
    get_fedformer_regime,
    calculate_kelly,
    calculate_atr,
    get_support_resistance,
    detect_liquidity_clusters,
    get_economic_events,
    get_cot_data,
)

logger = structlog.get_logger(__name__)


class CircuitBreakerState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker for MCP tool calls.

    Protects against cascading failures when external APIs are down.
    State transitions:
    - CLOSED → OPEN: After threshold consecutive failures
    - OPEN → HALF_OPEN: After recovery timeout
    - HALF_OPEN → CLOSED: After successful test call
    - HALF_OPEN → OPEN: If test call fails
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Consecutive failures before opening circuit
            recovery_timeout: Seconds to wait before testing recovery (HALF_OPEN)
            half_open_max_calls: Max calls allowed in HALF_OPEN state
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0

    def can_execute(self) -> bool:
        """Check if request can be executed."""
        if self.state == CircuitBreakerState.CLOSED:
            return True

        elif self.state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has elapsed
            if (
                self.last_failure_time
                and (datetime.utcnow() - self.last_failure_time).total_seconds()
                >= self.recovery_timeout
            ):
                # Transition to HALF_OPEN for testing
                self.state = CircuitBreakerState.HALF_OPEN
                self.half_open_calls = 0
                logger.info(
                    "circuit_breaker_state_change",
                    from_state="open",
                    to_state="half_open",
                )
                return True
            return False

        elif self.state == CircuitBreakerState.HALF_OPEN:
            # Allow limited calls for testing
            return self.half_open_calls < self.half_open_max_calls

        return False

    def record_success(self):
        """Record successful call."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            # Transition back to CLOSED (service recovered)
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.half_open_calls = 0
            logger.info(
                "circuit_breaker_state_change",
                from_state="half_open",
                to_state="closed",
            )
        elif self.state == CircuitBreakerState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def record_failure(self):
        """Record failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()

        if self.state == CircuitBreakerState.HALF_OPEN:
            # Test failed, go back to OPEN
            self.state = CircuitBreakerState.OPEN
            self.half_open_calls = 0
            logger.warning(
                "circuit_breaker_state_change",
                from_state="half_open",
                to_state="open",
                reason="test_call_failed",
            )

        elif self.state == CircuitBreakerState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                # Too many failures, open circuit
                self.state = CircuitBreakerState.OPEN
                logger.error(
                    "circuit_breaker_opened",
                    failure_count=self.failure_count,
                    threshold=self.failure_threshold,
                )

        if self.state == CircuitBreakerState.HALF_OPEN:
            self.half_open_calls += 1


class MCPToolService:
    """
    Service for MCP tool management.

    Provides:
    - Tool registration from YAML contracts
    - Tool invocation with circuit breaker
    - Response caching (Redis)
    - Performance metrics
    """

    def __init__(self, db_session: AsyncSession, redis_client: Any = None):
        """
        Initialize MCP Tool Service.

        Args:
            db_session: Database session for tool registration
            redis_client: Redis client for caching (optional)
        """
        self.db_session = db_session
        self.redis_client = redis_client
        self.repository = MCPToolRepository(db_session)

        # Circuit breakers per tool (keyed by tool name)
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}

        # Tool function mapping
        self.tool_functions = {
            "get_tcn_forecast": get_tcn_forecast,
            "get_tft_prediction": get_tft_prediction,
            "get_fedformer_regime": get_fedformer_regime,
            "calculate_kelly": calculate_kelly,
            "calculate_atr": calculate_atr,
            "get_support_resistance": get_support_resistance,
            "detect_liquidity_clusters": detect_liquidity_clusters,
            "get_economic_events": get_economic_events,
            "get_cot_data": get_cot_data,
        }

        self.logger = logger.bind(service="mcp_tool_service")

    def _get_circuit_breaker(self, tool_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for tool."""
        if tool_name not in self.circuit_breakers:
            self.circuit_breakers[tool_name] = CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=60,
                half_open_max_calls=3,
            )
        return self.circuit_breakers[tool_name]

    def _generate_cache_key(self, tool_name: str, params: Dict[str, Any]) -> str:
        """Generate cache key for tool call."""
        # Sort params for consistent key generation
        sorted_params = json.dumps(params, sort_keys=True)
        param_hash = hashlib.md5(sorted_params.encode()).hexdigest()
        return f"mcp_tool:{tool_name}:{param_hash}"

    async def _get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached tool response from Redis."""
        if not self.redis_client:
            return None

        try:
            cached = await self.redis_client.get(cache_key)
            if cached:
                self.logger.debug("cache_hit", cache_key=cache_key)
                return json.loads(cached)
        except Exception as e:
            self.logger.warning("cache_get_failed", error=str(e))

        return None

    async def _set_cached_response(
        self, cache_key: str, response: Dict[str, Any], ttl: int = 300
    ):
        """Cache tool response in Redis."""
        if not self.redis_client:
            return

        try:
            await self.redis_client.setex(
                cache_key, ttl, json.dumps(response)
            )
            self.logger.debug("cache_set", cache_key=cache_key, ttl=ttl)
        except Exception as e:
            self.logger.warning("cache_set_failed", error=str(e))

    async def invoke_tool(
        self, tool_name: str, params: Dict[str, Any], use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Invoke MCP tool with circuit breaker and caching.

        Args:
            tool_name: Name of tool to invoke
            params: Tool parameters
            use_cache: Whether to use caching (default True)

        Returns:
            Tool response

        Raises:
            ValueError: If tool not found
            RuntimeError: If circuit breaker is OPEN
        """
        start_time = time.time()

        # Check if tool exists
        if tool_name not in self.tool_functions:
            raise ValueError(f"Unknown tool: {tool_name}")

        # Check circuit breaker
        circuit_breaker = self._get_circuit_breaker(tool_name)
        if not circuit_breaker.can_execute():
            self.logger.error(
                "circuit_breaker_reject",
                tool_name=tool_name,
                state=circuit_breaker.state,
            )
            raise RuntimeError(
                f"Circuit breaker is {circuit_breaker.state} for tool {tool_name}"
            )

        # Check cache
        cache_key = self._generate_cache_key(tool_name, params)
        if use_cache:
            cached_response = await self._get_cached_response(cache_key)
            if cached_response:
                return cached_response

        # Invoke tool
        try:
            tool_func = self.tool_functions[tool_name]
            response = await tool_func(**params)

            # Record success
            circuit_breaker.record_success()

            # Cache response
            if use_cache:
                await self._set_cached_response(cache_key, response)

            # Log metrics
            execution_time = (time.time() - start_time) * 1000
            self.logger.info(
                "tool_invoked",
                tool_name=tool_name,
                execution_time_ms=execution_time,
                circuit_breaker_state=circuit_breaker.state,
            )

            return response

        except Exception as e:
            # Record failure
            circuit_breaker.record_failure()

            self.logger.error(
                "tool_invocation_failed",
                tool_name=tool_name,
                error=str(e),
                circuit_breaker_state=circuit_breaker.state,
                failure_count=circuit_breaker.failure_count,
            )

            raise

    async def get_tool_status(self) -> Dict[str, Any]:
        """
        Get status of all MCP tools.

        Returns:
            Dictionary with tool names and circuit breaker states
        """
        status = {}
        for tool_name, circuit_breaker in self.circuit_breakers.items():
            status[tool_name] = {
                "state": circuit_breaker.state,
                "failure_count": circuit_breaker.failure_count,
                "last_failure_time": (
                    circuit_breaker.last_failure_time.isoformat()
                    if circuit_breaker.last_failure_time
                    else None
                ),
            }

        return {
            "tools": status,
            "total_tools": len(self.tool_functions),
            "registered_tools": len(self.circuit_breakers),
        }

    async def register_tools_from_contracts(self, contracts_path: str):
        """
        Register MCP tools from contracts YAML file.

        This loads tool schemas from contracts/mcp-tools.yaml and
        registers them in the database.

        Args:
            contracts_path: Path to mcp-tools.yaml
        """
        # This is a placeholder - actual implementation would:
        # 1. Load YAML file
        # 2. Parse tool definitions
        # 3. Create MCPTool database records
        # 4. Register tool schemas

        self.logger.info(
            "register_tools_placeholder",
            contracts_path=contracts_path,
            note="Implementation pending for T044",
        )

        # TODO (T044): Implement tool registration from YAML
