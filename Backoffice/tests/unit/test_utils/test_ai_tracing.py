"""
Unit tests for app.utils.ai_tracing (optional OpenTelemetry).
"""

import pytest


class TestAITracing:
    """Tests for span() and add_event() when tracing disabled or unavailable."""

    def test_span_no_op_when_disabled(self, app):
        """span() context manager runs body without error when AI_OPENTELEMETRY_ENABLED is False."""
        from app.utils.ai_tracing import span

        with app.app_context():
            app.config["AI_OPENTELEMETRY_ENABLED"] = False
            ran = []

            with span("test.operation", {"key": "value"}):
                ran.append(1)

            assert ran == [1]

    def test_span_no_op_without_app_context(self):
        """span() can be used without app context (no-op)."""
        from app.utils.ai_tracing import span

        ran = []
        with span("test.operation"):
            ran.append(1)
        assert ran == [1]

    def test_add_event_no_op(self, app):
        """add_event() does not raise when no active span."""
        from app.utils.ai_tracing import add_event

        with app.app_context():
            add_event("test.event", {"a": 1})
        add_event("test.event")
