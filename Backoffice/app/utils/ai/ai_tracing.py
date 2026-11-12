"""
Optional OpenTelemetry tracing for the AI stack.

When AI_OPENTELEMETRY_ENABLED is True and opentelemetry-api is installed,
spans are created for agent execution, chat, embeddings, and vector search.
Otherwise all functions are no-ops (no dependency required).

To enable: pip install opentelemetry-api opentelemetry-sdk
          Set AI_OPENTELEMETRY_ENABLED=true and optionally configure an exporter.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Dict, Generator, Optional

logger = logging.getLogger(__name__)

_TRACER = None
_ENABLED: Optional[bool] = None


def _enabled() -> bool:
    global _ENABLED
    if _ENABLED is not None:
        return _ENABLED
    try:
        from flask import current_app
        _ENABLED = bool(current_app.config.get("AI_OPENTELEMETRY_ENABLED", False))
    except RuntimeError:
        _ENABLED = False
    except Exception as e:
        logger.debug("ai_tracing enabled check failed: %s", e)
        _ENABLED = False
    return _ENABLED


def _get_tracer():
    global _TRACER
    if _TRACER is not None:
        return _TRACER
    if not _enabled():
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.trace import TracerProvider
        try:
            from flask import current_app
            name = current_app.config.get("OTEL_SERVICE_NAME", "hum-databank-backoffice-ai")
        except RuntimeError:
            name = "hum-databank-backoffice-ai"
        provider = trace.get_tracer_provider()
        if isinstance(provider, TracerProvider):
            _TRACER = trace.get_tracer(name, "1.0.0")
        else:
            _TRACER = trace.get_tracer(name, "1.0.0")
    except ImportError:
        logger.debug("OpenTelemetry not installed; AI tracing disabled")
        _TRACER = False  # mark as tried
    except Exception as e:
        logger.debug("OpenTelemetry tracer init failed: %s", e)
        _TRACER = False
    return _TRACER if _TRACER else None


def _set_attributes(span: Any, attributes: Optional[Dict[str, Any]]) -> None:
    if not span or not attributes:
        return
    try:
        for k, v in attributes.items():
            if v is None:
                continue
            if isinstance(v, bool):
                span.set_attribute(k, v)
            elif isinstance(v, (int, float)):
                span.set_attribute(k, v)
            else:
                span.set_attribute(k, str(v)[:1000])
    except Exception as e:
        logger.debug("set_attributes failed: %s", e)


@contextlib.contextmanager
def span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Context manager that creates an OpenTelemetry span when tracing is enabled.

    Use for AI operations (agent execute, chat, embedding, vector search).
    No-op when AI_OPENTELEMETRY_ENABLED is False or opentelemetry is not installed.
    """
    tracer = _get_tracer()
    if not tracer:
        yield None
        return
    try:
        with tracer.start_as_current_span(name) as s:
            _set_attributes(s, attributes)
            yield s
    except Exception as e:
        logger.debug("ai_tracing span %s failed: %s", name, e)
        yield None


def add_event(name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
    """Add an event to the current span if present. No-op otherwise."""
    try:
        from opentelemetry import trace
        current = trace.get_current_span()
        if current is not None and current.is_recording():
            current.add_event(name, attributes=(attributes or {}))
    except Exception:
        pass
