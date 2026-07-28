"""Unit tests for services.ai_agent — circuit breaker and tool helpers.

No database, no LLM calls.

Covers:
  - CircuitBreaker / CircuitBreakerState  (_circuit_breaker.py)
  - _tool_circuit_helpers.py (if public API exists)
"""
import time
import pytest


# ===========================================================================
# CircuitBreakerState
# ===========================================================================

class TestCircuitBreakerState:
    def test_enum_has_three_states(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreakerState
        states = {s.value for s in CircuitBreakerState}
        assert states == {"closed", "open", "half_open"}


# ===========================================================================
# CircuitBreaker — initial state
# ===========================================================================

class TestCircuitBreakerInitialState:
    def test_starts_closed(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
        cb = CircuitBreaker()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_allows_call_when_closed(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker
        assert CircuitBreaker().allow_call() is True

    def test_default_threshold_is_3(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker
        assert CircuitBreaker().failure_threshold == 3

    def test_custom_threshold_respected(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=5)
        assert cb.failure_threshold == 5

    def test_threshold_clamped_to_minimum_1(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=0)
        assert cb.failure_threshold == 1


# ===========================================================================
# CircuitBreaker — opening on failures
# ===========================================================================

class TestCircuitBreakerOpening:
    def test_opens_after_threshold_failures(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
        cb = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=60.0)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

    def test_blocks_calls_when_open(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=60.0)
        cb.record_failure()
        assert cb.allow_call() is False

    def test_single_failure_below_threshold_stays_closed(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_two_failures_below_threshold_stays_closed(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED


# ===========================================================================
# CircuitBreaker — recovery: success resets
# ===========================================================================

class TestCircuitBreakerRecovery:
    def test_success_resets_to_closed(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_success_after_closed_stays_closed(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
        cb = CircuitBreaker()
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_success_allows_call_after_open(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=60.0)
        cb.record_failure()
        cb.record_success()
        assert cb.allow_call() is True


# ===========================================================================
# CircuitBreaker — half-open probe after timeout
# ===========================================================================

class TestCircuitBreakerHalfOpen:
    def test_transitions_to_half_open_after_timeout(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
        cb = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=0.01)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        time.sleep(0.05)
        # allow_call triggers the half-open transition
        assert cb.allow_call() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_failure_in_half_open_reopens(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
        cb = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=0.01)
        cb.record_failure()
        time.sleep(0.05)
        cb.allow_call()  # → HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

    def test_success_in_half_open_closes(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
        cb = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=0.01)
        cb.record_failure()
        time.sleep(0.05)
        cb.allow_call()  # → HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_zero_reset_timeout_never_half_opens(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
        cb = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=0.0)
        cb.record_failure()
        time.sleep(0.05)
        assert cb.allow_call() is False
        assert cb.state == CircuitBreakerState.OPEN

    def test_allow_call_on_half_open_returns_true(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
        cb = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=0.01)
        cb.record_failure()
        time.sleep(0.05)
        cb.allow_call()  # transitions to HALF_OPEN
        assert cb.allow_call() is True


# ===========================================================================
# CircuitBreaker — independent instances
# ===========================================================================

class TestCircuitBreakerIsolation:
    def test_two_breakers_are_independent(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
        cb1 = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=60.0)
        cb2 = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=60.0)
        cb1.record_failure()
        assert cb1.state == CircuitBreakerState.OPEN
        assert cb2.state == CircuitBreakerState.CLOSED

    def test_failure_count_does_not_leak_between_instances(self):
        from app.services.ai.agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
        cb1 = CircuitBreaker(failure_threshold=3)
        cb2 = CircuitBreaker(failure_threshold=3)
        cb1.record_failure()
        cb1.record_failure()
        cb2.record_failure()
        assert cb1.state == CircuitBreakerState.CLOSED
        assert cb2.state == CircuitBreakerState.CLOSED
