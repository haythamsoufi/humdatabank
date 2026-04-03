"""
Per-run circuit-breaker state for tool failure isolation.

Reserved for future use when the executor isolates repeated tool failures
(e.g. open/closed/half-open). Currently the executor does not use these;
they are exported so the package API remains stable.
"""

from enum import Enum
from typing import Optional


class CircuitBreakerState(Enum):
    """Circuit state: closed (normal), open (fail fast), half_open (probe)."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Placeholder for per-tool or per-run circuit breaker. Not yet used by executor."""

    def __init__(self, failure_threshold: int = 3, reset_timeout_seconds: float = 60.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self._state = CircuitBreakerState.CLOSED
        self._failures = 0

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    def record_success(self) -> None:
        self._failures = 0
        self._state = CircuitBreakerState.CLOSED

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._state = CircuitBreakerState.OPEN

    def allow_call(self) -> bool:
        return self._state != CircuitBreakerState.OPEN
