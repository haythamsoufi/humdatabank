"""
ai_agent – Sub-package for the AI agent execution pipeline.

Public API::

    from app.services.ai.agent import AIAgentExecutor

Module layout
─────────────
_circuit_breaker.py    – ``CircuitBreaker`` / ``CircuitBreakerState`` (used per tool execution run).
executor.py           – ``AIAgentExecutor`` (ReAct / OpenAI native function-calling loop).

``CircuitBreaker`` is also importable for tests and extensions; typical callers use ``AIAgentExecutor`` only.
"""

from app.services.ai.agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
from app.services.ai.agent.executor import AIAgentExecutor, AgentExecutionError

__all__ = [
    "AIAgentExecutor",
    "AgentExecutionError",
    "CircuitBreaker",
    "CircuitBreakerState",
]
