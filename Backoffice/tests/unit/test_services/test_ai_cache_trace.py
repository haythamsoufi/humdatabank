"""Tests for AI cache trace diagnostics."""

import pytest


@pytest.fixture
def app_ctx(app):
    with app.app_context():
        yield app


class TestAICacheTrace:
    def test_build_payload_empty_after_reset(self, app_ctx):
        from app.services.ai.runtime.cache_trace import (
            build_ai_cache_trace_payload,
            reset_ai_cache_trace,
        )

        reset_ai_cache_trace()
        assert build_ai_cache_trace_payload() is None

    def test_records_hits_and_misses(self, app_ctx):
        from app.services.ai.runtime.cache_trace import (
            build_ai_cache_trace_payload,
            record_ai_cache_event,
            reset_ai_cache_trace,
        )

        reset_ai_cache_trace()
        record_ai_cache_event("agent_system_prompt", hit=True, detail={"ttl_seconds": 60})
        record_ai_cache_event("tool_result_cache", name="search_indicator_bank", hit=True)
        record_ai_cache_event("agent_system_prompt", hit=False, detail={"ttl_seconds": 60})

        payload = build_ai_cache_trace_payload()
        assert payload is not None
        assert payload["summary"]["total_events"] == 3
        assert payload["summary"]["hits"] == 2
        assert payload["summary"]["misses"] == 1
        assert "agent_system_prompt=hit" in payload["summary"]["line"]
        assert "tool_result_cache:search_indicator_bank=hit" in payload["summary"]["line"]

    def test_reset_clears_events(self, app_ctx):
        from flask import g

        from app.services.ai.runtime.cache_trace import (
            build_ai_cache_trace_payload,
            record_ai_cache_event,
            reset_ai_cache_trace,
        )

        record_ai_cache_event("tool_result_cache", name="get_indicator_value", hit=True)
        reset_ai_cache_trace()
        assert build_ai_cache_trace_payload() is None
        assert getattr(g, "ai_cache_trace_events", None) == []
