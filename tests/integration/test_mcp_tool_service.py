"""
Integration tests for MCPToolService.

Tests the complete flow of:
1. Tool invocation through service
2. Circuit breaker behavior
3. Response caching
4. Error handling
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.services.mcp_tool_service import (
    MCPToolService,
    CircuitBreaker,
    CircuitBreakerState,
)


class TestCircuitBreaker:
    """Test circuit breaker state machine."""

    def test_initial_state_is_closed(self):
        """Circuit breaker should start in CLOSED state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.can_execute() is True

    def test_transitions_to_open_after_threshold_failures(self):
        """Circuit breaker should open after threshold consecutive failures."""
        cb = CircuitBreaker(failure_threshold=3)

        # Record failures
        for i in range(3):
            cb.record_failure()
            if i < 2:
                assert cb.state == CircuitBreakerState.CLOSED
            else:
                assert cb.state == CircuitBreakerState.OPEN

        # Should reject requests
        assert cb.can_execute() is False

    def test_resets_failure_count_on_success(self):
        """Success should reset failure count in CLOSED state."""
        cb = CircuitBreaker(failure_threshold=3)

        # Record 2 failures
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2

        # Record success
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitBreakerState.CLOSED

    def test_transitions_to_half_open_after_timeout(self):
        """Circuit breaker should transition to HALF_OPEN after recovery timeout."""
        cb = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0,  # Immediate recovery for testing
        )

        # Open circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        # Should transition to HALF_OPEN
        assert cb.can_execute() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_half_open_success_closes_circuit(self):
        """Successful call in HALF_OPEN should close circuit."""
        cb = CircuitBreaker()
        cb.state = CircuitBreakerState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_failure_reopens_circuit(self):
        """Failed call in HALF_OPEN should reopen circuit."""
        cb = CircuitBreaker()
        cb.state = CircuitBreakerState.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN


@pytest.mark.asyncio
class TestMCPToolService:
    """Test MCPToolService functionality."""

    @pytest.fixture
    async def service(self):
        """Create MCPToolService instance for testing."""
        # Mock database session
        db_session = MagicMock()

        # Mock Redis client
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=None)
        redis_client.setex = AsyncMock()

        service = MCPToolService(db_session, redis_client)
        return service

    async def test_invoke_tool_success(self, service):
        """Successful tool invocation should work."""
        # Mock the tool function
        with patch('src.services.mcp_tool_service.calculate_kelly') as mock_tool:
            mock_tool.return_value = {
                "kelly_fraction": 0.3,
                "capped_kelly_fraction": 0.25,
                "recommended_position_size": 10000.0,
                "recommended_position_pct": 25.0,
                "expected_growth_rate": 0.042,
                "calculation_time_ms": 2.1,
            }

            result = await service.invoke_tool(
                tool_name="calculate_kelly",
                params={
                    "win_probability": 0.55,
                    "win_loss_ratio": 1.8,
                    "bankroll": 40000.0,
                },
            )

            assert result["kelly_fraction"] == 0.3
            assert result["recommended_position_size"] == 10000.0

            # Circuit breaker should be in CLOSED state
            cb = service._get_circuit_breaker("calculate_kelly")
            assert cb.state == CircuitBreakerState.CLOSED
            assert cb.failure_count == 0

    async def test_invoke_tool_with_caching(self, service):
        """Tool invocation should use caching."""
        params = {
            "win_probability": 0.55,
            "win_loss_ratio": 1.8,
            "bankroll": 40000.0,
        }

        # First call - cache miss
        with patch('src.services.mcp_tool_service.calculate_kelly') as mock_tool:
            mock_result = {
                "kelly_fraction": 0.3,
                "capped_kelly_fraction": 0.25,
                "recommended_position_size": 10000.0,
                "recommended_position_pct": 25.0,
                "expected_growth_rate": 0.042,
                "calculation_time_ms": 2.1,
            }
            mock_tool.return_value = mock_result

            result1 = await service.invoke_tool(
                tool_name="calculate_kelly",
                params=params,
                use_cache=True,
            )

            # Tool should be called
            mock_tool.assert_called_once()

            # Response should be cached
            service.redis_client.setex.assert_called_once()

        # Second call - cache hit
        service.redis_client.get = AsyncMock(
            return_value='{"kelly_fraction": 0.3, "capped_kelly_fraction": 0.25, "recommended_position_size": 10000.0, "recommended_position_pct": 25.0, "expected_growth_rate": 0.042, "calculation_time_ms": 2.1}'
        )

        with patch('src.services.mcp_tool_service.calculate_kelly') as mock_tool:
            result2 = await service.invoke_tool(
                tool_name="calculate_kelly",
                params=params,
                use_cache=True,
            )

            # Tool should NOT be called (cache hit)
            mock_tool.assert_not_called()

            # Results should match
            assert result2["kelly_fraction"] == 0.3

    async def test_circuit_breaker_opens_on_failures(self, service):
        """Circuit breaker should open after consecutive failures."""
        # Mock tool to raise exceptions
        with patch('src.services.mcp_tool_service.get_tcn_forecast') as mock_tool:
            mock_tool.side_effect = Exception("API unavailable")

            # Record 5 failures
            for i in range(5):
                with pytest.raises(Exception):
                    await service.invoke_tool(
                        tool_name="get_tcn_forecast",
                        params={"symbol": "Gold", "horizon": "4h"},
                        use_cache=False,
                    )

            # Circuit breaker should be OPEN
            cb = service._get_circuit_breaker("get_tcn_forecast")
            assert cb.state == CircuitBreakerState.OPEN
            assert cb.failure_count == 5

            # Next call should be rejected
            with pytest.raises(RuntimeError, match="Circuit breaker is open"):
                await service.invoke_tool(
                    tool_name="get_tcn_forecast",
                    params={"symbol": "Gold", "horizon": "4h"},
                    use_cache=False,
                )

    async def test_unknown_tool_raises_error(self, service):
        """Invoking unknown tool should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown tool"):
            await service.invoke_tool(
                tool_name="non_existent_tool",
                params={},
            )

    async def test_get_tool_status(self, service):
        """get_tool_status should return circuit breaker states."""
        # Initialize some circuit breakers
        service._get_circuit_breaker("calculate_kelly")
        service._get_circuit_breaker("get_tcn_forecast")

        status = await service.get_tool_status()

        assert status["total_tools"] == 9
        assert status["registered_tools"] == 2
        assert "calculate_kelly" in status["tools"]
        assert "get_tcn_forecast" in status["tools"]

        # Check circuit breaker state
        assert status["tools"]["calculate_kelly"]["state"] == CircuitBreakerState.CLOSED

    async def test_cache_key_generation(self, service):
        """Cache keys should be deterministic and unique."""
        key1 = service._generate_cache_key(
            "calculate_kelly",
            {"win_probability": 0.55, "bankroll": 40000.0},
        )

        key2 = service._generate_cache_key(
            "calculate_kelly",
            {"bankroll": 40000.0, "win_probability": 0.55},  # Different order
        )

        # Keys should be the same (params sorted)
        assert key1 == key2

        # Different params should generate different key
        key3 = service._generate_cache_key(
            "calculate_kelly",
            {"win_probability": 0.60, "bankroll": 40000.0},
        )

        assert key1 != key3


@pytest.mark.asyncio
class TestMCPToolServiceIntegration:
    """Integration tests with real MCP tools."""

    @pytest.fixture
    async def service(self):
        """Create service with real tools (no Redis for simplicity)."""
        db_session = MagicMock()
        service = MCPToolService(db_session, redis_client=None)
        return service

    async def test_calculate_kelly_integration(self, service):
        """Test real Kelly calculation through service."""
        result = await service.invoke_tool(
            tool_name="calculate_kelly",
            params={
                "win_probability": 0.55,
                "win_loss_ratio": 1.8,
                "bankroll": 40000.0,
                "max_kelly_fraction": 0.25,
            },
            use_cache=False,  # No Redis
        )

        # Verify calculation
        assert 0.29 < result["kelly_fraction"] < 0.31  # ~0.3
        assert result["capped_kelly_fraction"] == 0.25  # Capped
        assert result["recommended_position_size"] == 10000.0  # 25% of 40000

        # Circuit breaker should be healthy
        cb = service._get_circuit_breaker("calculate_kelly")
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_get_tcn_forecast_integration(self, service):
        """Test TCN forecast through service (returns mock data)."""
        result = await service.invoke_tool(
            tool_name="get_tcn_forecast",
            params={
                "symbol": "CrudeOIL",
                "horizon": "4h",
            },
            use_cache=False,
        )

        # Should return mock data (ML API not running)
        assert result["symbol"] == "CrudeOIL"
        assert "predictions" in result
        assert "direction_prob" in result
        assert result["model_version"] == "mock_v0.0.1"

    async def test_multiple_tools_independent_circuit_breakers(self, service):
        """Different tools should have independent circuit breakers."""
        # Tool 1 - success
        result1 = await service.invoke_tool(
            tool_name="calculate_kelly",
            params={
                "win_probability": 0.55,
                "win_loss_ratio": 1.8,
                "bankroll": 40000.0,
            },
            use_cache=False,
        )

        # Tool 2 - success
        result2 = await service.invoke_tool(
            tool_name="get_tcn_forecast",
            params={"symbol": "Gold", "horizon": "4h"},
            use_cache=False,
        )

        # Both should have healthy circuit breakers
        cb1 = service._get_circuit_breaker("calculate_kelly")
        cb2 = service._get_circuit_breaker("get_tcn_forecast")

        assert cb1.state == CircuitBreakerState.CLOSED
        assert cb2.state == CircuitBreakerState.CLOSED
        assert cb1 is not cb2  # Different instances


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
