"""
Per-run circuit breaker for tool failure isolation.

Used by ``AIAgentExecutor`` to stop hammering a repeatedly failing tool within
a single execution. A fresh breaker map is created for each ``execute()`` call.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Optional


class CircuitBreakerState(Enum):
    """Circuit state: closed (normal), open (fail fast), half_open (probe)."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-tool breaker: opens after *failure_threshold* failures; may half-open after *reset_timeout_seconds*."""

    def __init__(self, failure_threshold: int = 3, reset_timeout_seconds: float = 30.0):
        self.failure_threshold = max(1, int(failure_threshold))
        self.reset_timeout_seconds = max(0.0, float(reset_timeout_seconds))
        self._state = CircuitBreakerState.CLOSED
        self._failures = 0
        self._opened_at: float = 0.0

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    def record_success(self) -> None:
        self._failures = 0
        self._state = CircuitBreakerState.CLOSED

    def record_failure(self) -> None:
        """Count a failed tool invocation toward opening the circuit."""
        now = time.time()
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.OPEN
            self._opened_at = now
            self._failures = self.failure_threshold
            return

        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._state = CircuitBreakerState.OPEN
            self._opened_at = now

    def allow_call(self) -> bool:
        """Return False when the circuit is open and cooldown has not elapsed."""
        now = time.time()

        if self._state == CircuitBreakerState.CLOSED:
            return True

        if self._state == CircuitBreakerState.HALF_OPEN:
            return True

        if self._state == CircuitBreakerState.OPEN:
            if self.reset_timeout_seconds <= 0:
                return False
            if now - self._opened_at >= self.reset_timeout_seconds:
                self._state = CircuitBreakerState.HALF_OPEN
                return True
            return False

        return True
