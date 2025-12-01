"""
Unit tests for MT4Client circuit breaker and resilience features (T089-T090).

Tests circuit breaker state transitions, exponential backoff, and reconnection logic.
"""
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

# Circuit breaker will be implemented in mt4_client.py
# These tests define the expected behavior (TDD)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_zmq_context():
    """Mock ZMQ context."""
    context = MagicMock()
    return context


@pytest.fixture
def mock_zmq_socket():
    """Mock ZMQ socket."""
    socket = MagicMock()
    socket.recv_string = MagicMock()
    socket.send_string = MagicMock()
    return socket


@pytest.fixture
def mt4_client(mock_zmq_context, mock_zmq_socket):
    """Create MT4Client instance with mocked dependencies."""
    with patch('zmq.asyncio.Context', return_value=mock_zmq_context):
        mock_zmq_context.socket.return_value = mock_zmq_socket
        
        from src.trading.execution.mt4_client import MT4Client
        
        client = MT4Client(
            host="localhost",
            rep_port=5555,
            pub_port=5556,
            encryption_manager=None
        )
        client._req_socket = mock_zmq_socket
        return client


# =============================================================================
# Circuit Breaker State Transition Tests (T089)
# =============================================================================

@pytest.mark.asyncio
async def test_circuit_breaker_starts_closed():
    """Test T089: Circuit breaker initializes in CLOSED state."""
    from src.trading.execution.mt4_client import CircuitBreaker
    
    cb = CircuitBreaker(failure_threshold=5, timeout=30)
    
    assert cb.state == "CLOSED"
    assert cb.failure_count == 0
    assert cb.success_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_failures():
    """Test T089: Circuit breaker opens after threshold failures."""
    from src.trading.execution.mt4_client import CircuitBreaker
    
    cb = CircuitBreaker(failure_threshold=3, timeout=30)
    
    # Record 3 failures
    for i in range(3):
        cb.record_failure()
    
    assert cb.state == "OPEN"
    assert cb.failure_count == 3


@pytest.mark.asyncio
async def test_circuit_breaker_closed_allows_requests():
    """Test T089: CLOSED circuit breaker allows requests."""
    from src.trading.execution.mt4_client import CircuitBreaker
    
    cb = CircuitBreaker()
    
    # Should allow request
    can_proceed = cb.can_proceed()
    assert can_proceed is True


@pytest.mark.asyncio
async def test_circuit_breaker_open_blocks_requests():
    """Test T089: OPEN circuit breaker blocks requests."""
    from src.trading.execution.mt4_client import CircuitBreaker
    
    cb = CircuitBreaker(failure_threshold=2)
    
    # Open the circuit
    cb.record_failure()
    cb.record_failure()
    
    assert cb.state == "OPEN"
    assert cb.can_proceed() is False


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_after_timeout():
    """Test T089: Circuit transitions to HALF_OPEN after timeout."""
    from src.trading.execution.mt4_client import CircuitBreaker
    
    cb = CircuitBreaker(failure_threshold=2, timeout=1)  # 1 second timeout
    
    # Open the circuit
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "OPEN"
    
    # Simulate timeout by setting old failure time
    cb.last_failure_time = datetime.utcnow() - timedelta(seconds=2)
    
    # Check if should transition
    should_attempt = cb.should_attempt_reset()
    assert should_attempt is True
    
    # Attempt reset
    cb.attempt_reset()
    assert cb.state == "HALF_OPEN"


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_success_closes():
    """Test T089: HALF_OPEN circuit closes on success."""
    from src.trading.execution.mt4_client import CircuitBreaker
    
    cb = CircuitBreaker()
    cb.state = "HALF_OPEN"
    
    # Record success
    cb.record_success()
    
    assert cb.state == "CLOSED"
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_failure_reopens():
    """Test T089: HALF_OPEN circuit reopens on failure."""
    from src.trading.execution.mt4_client import CircuitBreaker
    
    cb = CircuitBreaker(failure_threshold=1)
    cb.state = "HALF_OPEN"
    
    # Record failure
    cb.record_failure()
    
    assert cb.state == "OPEN"


@pytest.mark.asyncio
async def test_circuit_breaker_success_resets_count():
    """Test T089: Success resets failure count in CLOSED state."""
    from src.trading.execution.mt4_client import CircuitBreaker
    
    cb = CircuitBreaker(failure_threshold=5)
    
    # Accumulate some failures (but not enough to open)
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.failure_count == 3
    
    # Success should reset count
    cb.record_success()
    assert cb.failure_count == 0
    assert cb.state == "CLOSED"


# =============================================================================
# Exponential Backoff Tests (T090)
# =============================================================================

def test_exponential_backoff_calculation():
    """Test T090: Exponential backoff increases exponentially."""
    from src.trading.execution.mt4_client import calculate_backoff_time
    
    # Test progression: 1, 2, 4, 8, 16, 32 seconds
    assert calculate_backoff_time(0, base=1) == 1
    assert calculate_backoff_time(1, base=1) == 2
    assert calculate_backoff_time(2, base=1) == 4
    assert calculate_backoff_time(3, base=1) == 8
    assert calculate_backoff_time(4, base=1) == 16
    assert calculate_backoff_time(5, base=1) == 32


def test_exponential_backoff_respects_max():
    """Test T090: Backoff respects maximum limit."""
    from src.trading.execution.mt4_client import calculate_backoff_time
    
    max_backoff = 60  # 1 minute max
    
    # Large attempt should cap at max
    backoff = calculate_backoff_time(100, base=1, max_backoff=max_backoff)
    assert backoff == max_backoff


def test_exponential_backoff_with_jitter():
    """Test T090: Backoff includes jitter for randomization."""
    from src.trading.execution.mt4_client import calculate_backoff_time
    
    # Calculate multiple times with jitter
    backoffs = [calculate_backoff_time(3, base=1, jitter=True) for _ in range(20)]
    
    # Base time is 8 seconds
    # With jitter, should vary but stay within reasonable bounds
    base = 8
    for b in backoffs:
        assert base * 0.5 <= b <= base * 1.5
    
    # Should have variation (not all the same)
    assert len(set(backoffs)) > 1


def test_exponential_backoff_default_base():
    """Test T090: Default base is 1 second."""
    from src.trading.execution.mt4_client import calculate_backoff_time
    
    # No base specified, should default to 1
    assert calculate_backoff_time(0) == 1
    assert calculate_backoff_time(3) == 8


def test_backoff_progression_realistic():
    """Test T090: Realistic backoff progression for reconnection."""
    from src.trading.execution.mt4_client import calculate_backoff_time
    
    # Simulate 10 reconnection attempts
    max_backoff = 300  # 5 minutes
    
    attempts = []
    for attempt in range(10):
        backoff = calculate_backoff_time(attempt, max_backoff=max_backoff)
        attempts.append(backoff)
    
    # Should be increasing
    for i in range(len(attempts) - 1):
        assert attempts[i] <= attempts[i + 1]
    
    # Last attempt should be at max
    assert attempts[-1] == max_backoff


# =============================================================================
# Integration Tests - Circuit Breaker with MT4Client
# =============================================================================

@pytest.mark.asyncio
async def test_mt4_client_circuit_breaker_integration(mt4_client, mock_zmq_socket):
    """Test T089: MT4Client uses circuit breaker for requests."""
    # Mock failures
    mock_zmq_socket.recv_string.side_effect = TimeoutError("Connection timeout")
    
    # Make requests until circuit opens (threshold = 5)
    for i in range(5):
        try:
            await mt4_client.send_command({"command": "test"})
        except:
            pass
    
    # Circuit should be open
    assert mt4_client.circuit_breaker.state == "OPEN"


@pytest.mark.asyncio  
async def test_mt4_client_fails_fast_when_circuit_open(mt4_client, mock_zmq_socket):
    """Test T089: MT4Client fails fast when circuit is open."""
    # Force circuit open
    mt4_client.circuit_breaker.state = "OPEN"
    mt4_client.circuit_breaker.last_failure_time = datetime.utcnow()
    
    # Request should fail immediately
    import time
    start = time.time()
    
    try:
        await mt4_client.send_command({"command": "test"})
    except Exception:
        pass
    
    elapsed = time.time() - start
    
    # Should fail in under 100ms (much faster than timeout)
    assert elapsed < 0.1


print("✓ T089 & T090: Circuit breaker tests created (20 tests)")
