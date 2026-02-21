"""
Unit tests for CircuitBreaker in the MT4 client module.

Tests state transitions, exponential backoff, and reset behavior.
No mocks needed -- CircuitBreaker is a pure state machine.
"""
import time
from unittest.mock import patch

import pytest

from src.trading.execution.mt4_client import CircuitBreaker


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def cb():
    """Default circuit breaker with threshold=5, recovery=30s, max_backoff=60s."""
    return CircuitBreaker(failure_threshold=5, recovery_timeout=30.0, max_backoff=60.0)


@pytest.fixture
def fast_cb():
    """Circuit breaker with low threshold for quicker state transitions."""
    return CircuitBreaker(failure_threshold=2, recovery_timeout=0.1, max_backoff=60.0)


# =============================================================================
# Initial State Tests
# =============================================================================

class TestInitialState:
    def test_starts_closed(self, cb):
        assert cb.state == "closed"

    def test_can_execute_when_closed(self, cb):
        assert cb.can_execute() is True

    def test_initial_backoff_time(self, cb):
        assert cb.get_backoff_time() == 1.0


# =============================================================================
# CLOSED -> OPEN Transition Tests
# =============================================================================

class TestClosedToOpen:
    def test_stays_closed_below_threshold(self, cb):
        """Circuit stays closed when failures are below threshold."""
        for _ in range(4):
            cb.record_failure()
        assert cb.state == "closed"
        assert cb.can_execute() is True

    def test_opens_at_threshold(self, cb):
        """Circuit opens after reaching failure threshold."""
        for _ in range(5):
            cb.record_failure()
        assert cb.state == "open"

    def test_cannot_execute_when_open(self, cb):
        """Requests are rejected when circuit is open."""
        for _ in range(5):
            cb.record_failure()
        assert cb.can_execute() is False

    def test_success_resets_failure_count(self, cb):
        """A success in CLOSED state resets the failure counter."""
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # After reset, need full threshold again
        for _ in range(4):
            cb.record_failure()
        assert cb.state == "closed"

    def test_opens_with_threshold_2(self, fast_cb):
        """Circuit opens after 2 failures with threshold=2."""
        fast_cb.record_failure()
        assert fast_cb.state == "closed"
        fast_cb.record_failure()
        assert fast_cb.state == "open"


# =============================================================================
# OPEN -> HALF_OPEN Transition Tests
# =============================================================================

class TestOpenToHalfOpen:
    def test_transitions_to_half_open_after_timeout(self, fast_cb):
        """Circuit moves to HALF_OPEN once recovery timeout elapses."""
        fast_cb.record_failure()
        fast_cb.record_failure()
        assert fast_cb.state == "open"

        # Wait for recovery timeout (0.1s)
        time.sleep(0.15)

        assert fast_cb.state == "half_open"
        assert fast_cb.can_execute() is True

    def test_stays_open_before_timeout(self, cb):
        """Circuit stays OPEN before recovery timeout elapses."""
        for _ in range(5):
            cb.record_failure()

        # Recovery timeout is 30s, no time has passed
        assert cb.state == "open"
        assert cb.can_execute() is False

    def test_can_execute_returns_true_in_half_open(self, fast_cb):
        """can_execute triggers the OPEN -> HALF_OPEN transition check."""
        fast_cb.record_failure()
        fast_cb.record_failure()
        assert fast_cb.can_execute() is False

        time.sleep(0.15)

        assert fast_cb.can_execute() is True
        assert fast_cb.state == "half_open"


# =============================================================================
# HALF_OPEN -> CLOSED Transition Tests
# =============================================================================

class TestHalfOpenToClosed:
    def test_closes_on_success_in_half_open(self, fast_cb):
        """A success in HALF_OPEN state closes the circuit."""
        fast_cb.record_failure()
        fast_cb.record_failure()
        time.sleep(0.15)

        assert fast_cb.state == "half_open"
        fast_cb.record_success()

        assert fast_cb.state == "closed"
        assert fast_cb.can_execute() is True

    def test_failure_count_resets_on_close(self, fast_cb):
        """Closing the circuit resets failure count to zero."""
        fast_cb.record_failure()
        fast_cb.record_failure()
        time.sleep(0.15)
        fast_cb.record_success()

        # Need full threshold failures to re-open
        fast_cb.record_failure()
        assert fast_cb.state == "closed"


# =============================================================================
# HALF_OPEN -> OPEN Transition Tests
# =============================================================================

class TestHalfOpenToOpen:
    def test_reopens_on_failure_in_half_open(self, fast_cb):
        """A failure in HALF_OPEN state re-opens the circuit."""
        fast_cb.record_failure()
        fast_cb.record_failure()
        time.sleep(0.15)

        assert fast_cb.state == "half_open"
        fast_cb.record_failure()

        assert fast_cb.state == "open"
        assert fast_cb.can_execute() is False

    def test_repeated_half_open_failures(self, fast_cb):
        """Multiple HALF_OPEN -> OPEN cycles track recovery failures."""
        # First trip
        fast_cb.record_failure()
        fast_cb.record_failure()
        time.sleep(0.15)

        # First recovery attempt fails
        assert fast_cb.state == "half_open"
        fast_cb.record_failure()
        assert fast_cb.state == "open"

        time.sleep(0.15)

        # Second recovery attempt fails
        assert fast_cb.state == "half_open"
        fast_cb.record_failure()
        assert fast_cb.state == "open"


# =============================================================================
# Exponential Backoff Tests
# =============================================================================

class TestExponentialBackoff:
    def test_initial_backoff(self, cb):
        """Initial backoff is 1 second."""
        assert cb.get_backoff_time() == 1.0

    def test_backoff_increases_after_recovery_failures(self, fast_cb):
        """Backoff doubles after each failed recovery attempt."""
        # Trip the circuit
        fast_cb.record_failure()
        fast_cb.record_failure()

        # First recovery failure
        time.sleep(0.15)
        fast_cb.record_failure()
        # consecutive_recovery_failures=1, backoff = 1 * 2^1 = 2.0
        assert fast_cb.get_backoff_time() == 2.0

        # Second recovery failure
        time.sleep(0.15)
        fast_cb.record_failure()
        # consecutive_recovery_failures=2, backoff = 1 * 2^2 = 4.0
        assert fast_cb.get_backoff_time() == 4.0

    def test_backoff_capped_at_max(self):
        """Backoff never exceeds max_backoff."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01, max_backoff=10.0)

        # Create many recovery failures to push backoff high
        cb.record_failure()
        for _ in range(20):
            time.sleep(0.02)
            cb.record_failure()

        assert cb.get_backoff_time() <= 10.0

    def test_backoff_resets_on_success(self, fast_cb):
        """Successful recovery resets backoff to initial value."""
        fast_cb.record_failure()
        fast_cb.record_failure()

        # One failed recovery
        time.sleep(0.15)
        fast_cb.record_failure()
        assert fast_cb.get_backoff_time() > 1.0

        # Successful recovery
        time.sleep(0.15)
        fast_cb.record_success()
        assert fast_cb.get_backoff_time() == 1.0


# =============================================================================
# Reset Tests
# =============================================================================

class TestReset:
    def test_reset_from_open(self, cb):
        """Reset clears all state from OPEN."""
        for _ in range(5):
            cb.record_failure()
        assert cb.state == "open"

        cb.reset()

        assert cb.state == "closed"
        assert cb.can_execute() is True
        assert cb.get_backoff_time() == 1.0

    def test_reset_from_half_open(self, fast_cb):
        """Reset clears all state from HALF_OPEN."""
        fast_cb.record_failure()
        fast_cb.record_failure()
        time.sleep(0.15)
        assert fast_cb.state == "half_open"

        fast_cb.reset()

        assert fast_cb.state == "closed"
        assert fast_cb.can_execute() is True

    def test_reset_from_closed_is_idempotent(self, cb):
        """Reset from CLOSED state is a no-op."""
        cb.reset()
        assert cb.state == "closed"
        assert cb.can_execute() is True

    def test_reset_clears_failure_count(self, cb):
        """After reset, full threshold failures needed to re-open."""
        for _ in range(4):
            cb.record_failure()
        cb.reset()

        for _ in range(4):
            cb.record_failure()
        assert cb.state == "closed"

    def test_reset_clears_recovery_failure_count(self, fast_cb):
        """Reset clears the recovery failure counter for backoff."""
        fast_cb.record_failure()
        fast_cb.record_failure()
        time.sleep(0.15)
        fast_cb.record_failure()  # recovery failure
        assert fast_cb.get_backoff_time() > 1.0

        fast_cb.reset()
        assert fast_cb.get_backoff_time() == 1.0


# =============================================================================
# Full Lifecycle Tests
# =============================================================================

class TestFullLifecycle:
    def test_full_trip_and_recovery(self, fast_cb):
        """Test complete lifecycle: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
        # Start closed
        assert fast_cb.state == "closed"

        # Trip the circuit
        fast_cb.record_failure()
        fast_cb.record_failure()
        assert fast_cb.state == "open"

        # Wait for recovery timeout
        time.sleep(0.15)
        assert fast_cb.state == "half_open"

        # Successful probe
        fast_cb.record_success()
        assert fast_cb.state == "closed"

        # Normal operation resumes
        assert fast_cb.can_execute() is True

    def test_trip_recover_trip_again(self, fast_cb):
        """Circuit can be tripped, recovered, and tripped again."""
        # First trip and recovery
        fast_cb.record_failure()
        fast_cb.record_failure()
        time.sleep(0.15)
        fast_cb.record_success()
        assert fast_cb.state == "closed"

        # Second trip
        fast_cb.record_failure()
        fast_cb.record_failure()
        assert fast_cb.state == "open"

    def test_state_property_is_consistent(self, fast_cb):
        """State property returns consistent values without side effects."""
        fast_cb.record_failure()
        fast_cb.record_failure()

        # Multiple reads should return the same state
        assert fast_cb.state == "open"
        assert fast_cb.state == "open"

        time.sleep(0.15)

        # After timeout, should consistently read half_open
        assert fast_cb.state == "half_open"
        assert fast_cb.state == "half_open"


# =============================================================================
# Constructor Parameter Tests
# =============================================================================

class TestConstructorParams:
    def test_default_parameters(self):
        """Default constructor values match specification."""
        cb = CircuitBreaker()
        assert cb.state == "closed"
        assert cb.can_execute() is True
        # Default threshold is 5
        for _ in range(4):
            cb.record_failure()
        assert cb.state == "closed"
        cb.record_failure()
        assert cb.state == "open"

    def test_custom_failure_threshold(self):
        """Custom failure threshold is respected."""
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"

    def test_custom_max_backoff(self):
        """Custom max_backoff caps the backoff time."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01, max_backoff=5.0)
        cb.record_failure()
        for _ in range(10):
            time.sleep(0.02)
            cb.record_failure()
        assert cb.get_backoff_time() <= 5.0
