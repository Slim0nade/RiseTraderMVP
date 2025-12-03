#!/usr/bin/env python3
"""
Simple MCPToolService Integration Test.

Tests MCPToolService without triggering the full agent import chain.
This avoids the autogen dependency issue for basic validation.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Direct import to avoid __init__.py imports
from src.services.mcp_tool_service import (
    MCPToolService,
    CircuitBreaker,
    CircuitBreakerState,
)


async def test_circuit_breaker_states():
    """Test circuit breaker state transitions."""
    print("\n" + "="*70)
    print("Testing Circuit Breaker State Machine")
    print("="*70)

    # Test 1: Initial state
    print("\n1. Testing initial state...")
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.can_execute() is True
    print("   ✓ Circuit breaker starts in CLOSED state")

    # Test 2: Record failures
    print("\n2. Testing failure accumulation...")
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.failure_count == 2
    print(f"   ✓ Recorded 2 failures, state still CLOSED (count: {cb.failure_count})")

    # Test 3: Threshold reached
    print("\n3. Testing threshold breach...")
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN
    assert cb.can_execute() is False
    print(f"   ✓ Circuit breaker opened after {cb.failure_threshold} failures")

    # Test 4: Success resets count
    print("\n4. Testing success reset...")
    cb2 = CircuitBreaker()
    cb2.record_failure()
    cb2.record_failure()
    assert cb2.failure_count == 2
    cb2.record_success()
    assert cb2.failure_count == 0
    print("   ✓ Success resets failure count in CLOSED state")

    # Test 5: HALF_OPEN state
    print("\n5. Testing HALF_OPEN state...")
    cb3 = CircuitBreaker(recovery_timeout=0)
    cb3.record_failure()
    cb3.record_failure()
    cb3.record_failure()
    assert cb3.state == CircuitBreakerState.OPEN

    # Should transition to HALF_OPEN
    can_exec = cb3.can_execute()
    assert can_exec is True
    assert cb3.state == CircuitBreakerState.HALF_OPEN
    print("   ✓ Circuit breaker transitioned to HALF_OPEN for testing")

    # Test 6: HALF_OPEN success closes circuit
    print("\n6. Testing HALF_OPEN recovery...")
    cb3.record_success()
    assert cb3.state == CircuitBreakerState.CLOSED
    print("   ✓ Successful test in HALF_OPEN closed circuit")


async def test_mcp_tool_service():
    """Test MCPToolService functionality."""
    print("\n" + "="*70)
    print("Testing MCPToolService")
    print("="*70)

    # Create mock dependencies
    db_session = MagicMock()
    redis_client = AsyncMock()
    redis_client.get = AsyncMock(return_value=None)
    redis_client.setex = AsyncMock()

    # Create service
    service = MCPToolService(db_session, redis_client)

    # Test 1: Tool registry
    print("\n1. Testing tool registry...")
    assert len(service.tool_functions) == 9
    print(f"   ✓ All 9 MCP tools registered")
    print(f"   Tools: {', '.join(service.tool_functions.keys())}")

    # Test 2: Invoke Kelly calculation
    print("\n2. Testing Kelly calculation...")
    result = await service.invoke_tool(
        tool_name="calculate_kelly",
        params={
            "win_probability": 0.55,
            "win_loss_ratio": 1.8,
            "bankroll": 40000.0,
            "max_kelly_fraction": 0.25,
        },
        use_cache=False,
    )

    assert "kelly_fraction" in result
    assert "recommended_position_size" in result
    print(f"   ✓ Kelly calculation successful")
    print(f"   Kelly Fraction: {result['kelly_fraction']:.3f}")
    print(f"   Capped Fraction: {result['capped_kelly_fraction']:.3f}")
    print(f"   Recommended Size: ${result['recommended_position_size']:,.2f}")

    # Test 3: Circuit breaker for Kelly is healthy
    print("\n3. Testing circuit breaker health...")
    cb = service._get_circuit_breaker("calculate_kelly")
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.failure_count == 0
    print(f"   ✓ Circuit breaker state: {cb.state}")
    print(f"   Failure count: {cb.failure_count}")

    # Test 4: Invoke TCN forecast (returns mock data)
    print("\n4. Testing TCN forecast...")
    result = await service.invoke_tool(
        tool_name="get_tcn_forecast",
        params={
            "symbol": "CrudeOIL",
            "horizon": "4h",
        },
        use_cache=False,
    )

    assert result["symbol"] == "CrudeOIL"
    assert "predictions" in result
    assert "direction_prob" in result
    print(f"   ✓ TCN forecast successful")
    print(f"   Symbol: {result['symbol']}")
    print(f"   Model: {result['model_version']}")
    print(f"   Direction Prob: {result['direction_prob']}")

    # Test 5: Tool status
    print("\n5. Testing tool status...")
    status = await service.get_tool_status()
    assert status["total_tools"] == 9
    print(f"   ✓ Total tools: {status['total_tools']}")
    print(f"   Registered circuit breakers: {status['registered_tools']}")

    # Test 6: Cache key generation
    print("\n6. Testing cache key generation...")
    key1 = service._generate_cache_key(
        "calculate_kelly",
        {"win_probability": 0.55, "bankroll": 40000.0},
    )
    key2 = service._generate_cache_key(
        "calculate_kelly",
        {"bankroll": 40000.0, "win_probability": 0.55},  # Different order
    )
    assert key1 == key2
    print("   ✓ Cache keys are deterministic (param order independent)")

    key3 = service._generate_cache_key(
        "calculate_kelly",
        {"win_probability": 0.60, "bankroll": 40000.0},
    )
    assert key1 != key3
    print("   ✓ Different params generate different cache keys")


async def test_all_mcp_tools():
    """Test all 9 MCP tools through service."""
    print("\n" + "="*70)
    print("Testing All MCP Tools Through Service")
    print("="*70)

    db_session = MagicMock()
    service = MCPToolService(db_session, redis_client=None)

    tools_to_test = [
        ("calculate_kelly", {
            "win_probability": 0.55,
            "win_loss_ratio": 1.8,
            "bankroll": 40000.0,
        }),
        ("calculate_atr", {
            "symbol": "CrudeOIL",
            "period": 14,
            "timeframe": "4h",
        }),
        ("get_tcn_forecast", {
            "symbol": "Gold",
            "horizon": "4h",
        }),
        ("get_tft_prediction", {
            "symbol": "Gold",
            "horizon": "4h",
        }),
        ("get_fedformer_regime", {
            "symbol": "CrudeOIL",
        }),
        ("get_support_resistance", {
            "symbol": "CrudeOIL",
            "lookback_periods": 100,
        }),
        ("detect_liquidity_clusters", {
            "symbol": "Gold",
            "lookback_periods": 100,
        }),
        ("get_economic_events", {
            "symbol": "CrudeOIL",
            "lookforward_hours": 48,
        }),
        ("get_cot_data", {
            "symbol": "CrudeOIL",
            "lookback_weeks": 4,
        }),
    ]

    for i, (tool_name, params) in enumerate(tools_to_test, 1):
        print(f"\n{i}. Testing {tool_name}...")
        try:
            result = await service.invoke_tool(
                tool_name=tool_name,
                params=params,
                use_cache=False,
            )

            # Verify circuit breaker
            cb = service._get_circuit_breaker(tool_name)
            assert cb.state == CircuitBreakerState.CLOSED

            print(f"   ✓ {tool_name} successful (circuit breaker: {cb.state})")

        except Exception as e:
            print(f"   ✗ {tool_name} failed: {e}")
            raise


async def main():
    """Run all tests."""
    print("""
╔════════════════════════════════════════════════════════════════╗
║       MCPToolService Integration Test Suite                    ║
║       Feature 005 - Phase 2 Validation                         ║
╚════════════════════════════════════════════════════════════════╝
""")

    try:
        # Test circuit breaker
        await test_circuit_breaker_states()

        # Test MCPToolService
        await test_mcp_tool_service()

        # Test all MCP tools
        await test_all_mcp_tools()

        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED")
        print("="*70)
        print("\nMCPToolService Integration Summary:")
        print("  ✓ Circuit breaker state machine working correctly")
        print("  ✓ Tool invocation with circuit breaker protection")
        print("  ✓ All 9 MCP tools accessible through service")
        print("  ✓ Cache key generation deterministic")
        print("  ✓ Tool status reporting functional")
        print("\nNext Steps:")
        print("  1. Integration test with live agents via API")
        print("  2. Performance benchmarks (latency, cache hit rate)")
        print("  3. Test circuit breaker recovery under load")
        print("  4. Proceed to User Story 1-3 implementation")

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
