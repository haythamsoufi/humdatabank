"""
Comprehensive tests for app/services/chatbot_telemetry.py.

Covers:
  - ChatbotMetrics dataclass
  - ChatbotTelemetryService: track_interaction, _flush_metrics, _ensure_telemetry_table
  - ChatbotTelemetryService: get_usage_stats, get_error_analysis, get_function_usage_stats
  - ChatbotTelemetryService: estimate_token_usage, estimate_cost
  - track_chatbot_interaction (module-level function)
  - get_chatbot_analytics
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.services.chatbot_telemetry import (
    ChatbotMetrics,
    ChatbotTelemetryService,
    get_chatbot_analytics,
    track_chatbot_interaction,
)


def _make_metrics(**kwargs):
    """Build a ChatbotMetrics with sensible defaults."""
    defaults = dict(
        user_id=1,
        session_id="test-session",
        timestamp=datetime.now(timezone.utc),
        message_length=50,
        language="en",
        page_context=None,
        llm_provider="openai",
        model_name="gpt-4o-mini",
        function_calls_made=[],
        response_time_ms=250.0,
        success=True,
        error_type=None,
        input_tokens=12,
        output_tokens=20,
        estimated_cost_usd=0.0001,
        response_length=100,
        used_provenance=False,
    )
    defaults.update(kwargs)
    return ChatbotMetrics(**defaults)


# ---------------------------------------------------------------------------
# ChatbotMetrics dataclass
# ---------------------------------------------------------------------------
class TestChatbotMetrics:
    def test_creation_with_all_fields(self):
        m = _make_metrics()
        assert m.user_id == 1
        assert m.llm_provider == "openai"
        assert m.success is True

    def test_optional_fields_can_be_none(self):
        m = _make_metrics(page_context=None, model_name=None, error_type=None)
        assert m.page_context is None
        assert m.model_name is None

    def test_function_calls_list(self):
        m = _make_metrics(function_calls_made=["search_indicators", "get_data"])
        assert "search_indicators" in m.function_calls_made


# ---------------------------------------------------------------------------
# ChatbotTelemetryService.estimate_token_usage
# ---------------------------------------------------------------------------
class TestEstimateTokenUsage:
    def test_short_text(self):
        svc = ChatbotTelemetryService()
        result = svc.estimate_token_usage("Hello")
        assert result >= 1

    def test_long_text(self):
        svc = ChatbotTelemetryService()
        text = "word " * 100
        result = svc.estimate_token_usage(text)
        assert result > 1

    def test_minimum_is_one(self):
        svc = ChatbotTelemetryService()
        # Even empty string should return at least 1
        result = svc.estimate_token_usage("")
        assert result >= 1

    def test_is_input_flag_no_effect_on_math(self):
        svc = ChatbotTelemetryService()
        t = "test text here"
        assert svc.estimate_token_usage(t, is_input=True) == svc.estimate_token_usage(t, is_input=False)


# ---------------------------------------------------------------------------
# ChatbotTelemetryService.estimate_cost
# ---------------------------------------------------------------------------
class TestEstimateCost:
    def test_non_openai_returns_zero(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            cost = svc.estimate_cost("anthropic", 100, 50)
            assert cost == 0.0

    def test_openai_calls_pricing_util(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            # estimate_chat_cost is lazily imported inside the method
            with patch("app.utils.ai_pricing.estimate_chat_cost", return_value=0.05) as mock_cost:
                cost = svc.estimate_cost("openai", 100, 50, model="gpt-4o-mini")
                assert cost == 0.05
                mock_cost.assert_called_once()

    def test_openai_exception_returns_zero(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            with patch(
                "app.utils.ai_pricing.estimate_chat_cost",
                side_effect=Exception("pricing error"),
            ):
                cost = svc.estimate_cost("openai", 100, 50)
                assert cost == 0.0

    def test_openai_uses_config_model_when_none(self, app):
        with app.app_context():
            app.config["OPENAI_MODEL"] = "gpt-5-mini"
            svc = ChatbotTelemetryService()
            with patch("app.utils.ai_pricing.estimate_chat_cost", return_value=0.01) as mock_cost:
                svc.estimate_cost("openai", 10, 5, model=None)
                call_args = mock_cost.call_args[0]
                assert "gpt-5-mini" in call_args


# ---------------------------------------------------------------------------
# ChatbotTelemetryService.track_interaction + _flush_metrics
# ---------------------------------------------------------------------------
class TestTrackInteraction:
    def test_metrics_added_to_buffer(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            m = _make_metrics()
            svc.track_interaction(m)
            assert len(svc.metrics_buffer) == 1

    def test_buffer_flushed_when_full(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            svc.buffer_size = 2
            svc._flush_metrics = MagicMock()
            m = _make_metrics()
            svc.track_interaction(m)  # 1st – no flush
            svc.track_interaction(m)  # 2nd – flush triggered
            svc._flush_metrics.assert_called_once()

    def test_track_interaction_exception_logged(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            # Pass non-ChatbotMetrics to trigger internal error
            with patch.object(svc, "_lock") as mock_lock:
                mock_lock.__enter__ = MagicMock(side_effect=RuntimeError("lock error"))
                mock_lock.__exit__ = MagicMock(return_value=False)
                # Should not raise
                svc.track_interaction(_make_metrics())


class TestFlushMetrics:
    def test_empty_buffer_returns_immediately(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            svc.metrics_buffer = []
            # Should not raise and not call DB
            with patch("app.services.chatbot_telemetry.db") as mock_db:
                svc._flush_metrics()
                mock_db.session.execute.assert_not_called()

    def test_flush_inserts_records(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            svc.metrics_buffer = [_make_metrics()]
            ChatbotTelemetryService._table_ensured = True  # Skip table creation

            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.session.execute = MagicMock()
                mock_db.session.commit = MagicMock()
                svc._flush_metrics()
                mock_db.session.execute.assert_called()
                mock_db.session.commit.assert_called_once()

    def test_flush_requeues_on_error(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            metrics = [_make_metrics()]
            svc.metrics_buffer = list(metrics)
            ChatbotTelemetryService._table_ensured = True

            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.session.execute = MagicMock(side_effect=Exception("db error"))
                mock_db.session.rollback = MagicMock()
                svc._flush_metrics()
                # Original metrics re-queued
                assert len(svc.metrics_buffer) >= 1

    def test_flush_rollback_error_handled(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            svc.metrics_buffer = [_make_metrics()]
            ChatbotTelemetryService._table_ensured = True

            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.session.execute = MagicMock(side_effect=Exception("insert fail"))
                mock_db.session.rollback = MagicMock(side_effect=Exception("rollback fail"))
                # Should not raise
                svc._flush_metrics()


# ---------------------------------------------------------------------------
# ChatbotTelemetryService._ensure_telemetry_table
# ---------------------------------------------------------------------------
class TestEnsureTelemetryTable:
    def test_sqlite_dialect_creates_table(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_engine = MagicMock()
                mock_dialect = MagicMock()
                mock_dialect.name = "sqlite"
                mock_engine.dialect = mock_dialect
                mock_db.engine = mock_engine
                mock_db.session.execute = MagicMock()
                mock_db.session.commit = MagicMock()
                svc._ensure_telemetry_table()
                assert mock_db.session.execute.call_count >= 2

    def test_postgres_dialect_creates_table(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_engine = MagicMock()
                mock_dialect = MagicMock()
                mock_dialect.name = "postgresql"
                mock_engine.dialect = mock_dialect
                mock_db.engine = mock_engine
                mock_db.session.execute = MagicMock()
                mock_db.session.commit = MagicMock()
                svc._ensure_telemetry_table()
                assert mock_db.session.execute.call_count >= 2

    def test_exception_during_create_handled(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.engine = MagicMock()
                mock_db.engine.dialect = MagicMock()
                mock_db.engine.dialect.name = "sqlite"
                mock_db.session.execute = MagicMock(side_effect=Exception("table error"))
                mock_db.session.rollback = MagicMock()
                svc._ensure_telemetry_table()
                # Should not raise

    def test_dialect_detection_exception_handled(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.engine = None  # triggers getattr chain to fail
                mock_db.session.execute = MagicMock()
                mock_db.session.commit = MagicMock()
                # Should not raise, defaults to non-sqlite path
                svc._ensure_telemetry_table()


# ---------------------------------------------------------------------------
# ChatbotTelemetryService.get_usage_stats
# ---------------------------------------------------------------------------
class TestGetUsageStats:
    def test_returns_dict_on_success(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            fake_row = MagicMock()
            fake_row._mapping = {
                "total_interactions": 10,
                "unique_users": 3,
                "avg_response_time": 200.0,
                "successful_interactions": 9,
                "openai_usage": 10,
                "other_usage": 0,
                "total_estimated_cost": 0.5,
                "avg_message_length": 50.0,
                "avg_response_length": 100.0,
                "function_calls_total": 2,
            }

            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.session.execute.return_value.fetchone.return_value = fake_row
                result = svc.get_usage_stats(days=7)
                assert result["total_interactions"] == 10
                assert "success_rate" in result
                assert "provider_distribution" in result

    def test_returns_empty_dict_when_no_rows(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.session.execute.return_value.fetchone.return_value = None
                result = svc.get_usage_stats()
                assert result == {}

    def test_returns_empty_dict_on_exception(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.session.execute.side_effect = Exception("db error")
                result = svc.get_usage_stats()
                assert result == {}

    def test_success_rate_zero_division_avoided(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            fake_row = MagicMock()
            fake_row._mapping = {
                "total_interactions": 0,
                "unique_users": 0,
                "avg_response_time": None,
                "successful_interactions": 0,
                "openai_usage": 0,
                "other_usage": 0,
                "total_estimated_cost": None,
                "avg_message_length": None,
                "avg_response_length": None,
                "function_calls_total": 0,
            }
            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.session.execute.return_value.fetchone.return_value = fake_row
                result = svc.get_usage_stats()
                # total is 0, uses "or 1" fallback
                assert result["success_rate"] == 0.0


# ---------------------------------------------------------------------------
# ChatbotTelemetryService.get_error_analysis
# ---------------------------------------------------------------------------
class TestGetErrorAnalysis:
    def test_returns_errors_list(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            fake_row = MagicMock()
            fake_row.error_type = "timeout"
            fake_row.error_count = 3
            fake_row.avg_response_time = 5000.0

            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.session.execute.return_value.fetchall.return_value = [fake_row]
                result = svc.get_error_analysis()
                assert result["errors"][0]["error_type"] == "timeout"
                assert result["errors"][0]["count"] == 3

    def test_empty_result_returns_empty_list(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.session.execute.return_value.fetchall.return_value = []
                result = svc.get_error_analysis()
                assert result == {"errors": []}

    def test_exception_returns_empty_errors(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.session.execute.side_effect = Exception("db fail")
                result = svc.get_error_analysis()
                assert result == {"errors": []}


# ---------------------------------------------------------------------------
# ChatbotTelemetryService.get_function_usage_stats
# ---------------------------------------------------------------------------
class TestGetFunctionUsageStats:
    def test_counts_function_calls(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            fake_row = MagicMock()
            fake_row.function_calls_made = json.dumps(["search_indicators", "get_data", "search_indicators"])

            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.session.execute.return_value.fetchall.return_value = [fake_row]
                result = svc.get_function_usage_stats()
                assert result["total_function_calls"] == 3
                assert result["function_distribution"]["search_indicators"] == 2
                assert result["most_used_function"] == "search_indicators"

    def test_invalid_json_rows_skipped(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            fake_row = MagicMock()
            fake_row.function_calls_made = "invalid_json{{{"

            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.session.execute.return_value.fetchall.return_value = [fake_row]
                result = svc.get_function_usage_stats()
                assert result["total_function_calls"] == 0
                assert result["most_used_function"] is None

    def test_empty_results_returns_none_for_most_used(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.session.execute.return_value.fetchall.return_value = []
                result = svc.get_function_usage_stats()
                assert result["most_used_function"] is None

    def test_exception_returns_empty_dict(self, app):
        with app.app_context():
            svc = ChatbotTelemetryService()
            with patch("app.services.chatbot_telemetry.db") as mock_db:
                mock_db.session.execute.side_effect = Exception("db fail")
                result = svc.get_function_usage_stats()
                assert result == {}


# ---------------------------------------------------------------------------
# track_chatbot_interaction (module-level function)
# ---------------------------------------------------------------------------
class TestTrackChatbotInteraction:
    def test_authenticated_user(self, app):
        with app.app_context():
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            mock_user.id = 42
            mock_user.session_id = "session-abc"

            with patch("app.services.chatbot_telemetry.current_user", mock_user):
                with patch("app.services.chatbot_telemetry.telemetry_service") as mock_svc:
                    track_chatbot_interaction(
                        message="Hello",
                        response="Hi there",
                        llm_provider="openai",
                        model_name="gpt-4o-mini",
                        response_time_ms=100.0,
                        success=True,
                    )
                    mock_svc.track_interaction.assert_called_once()
                    call_args = mock_svc.track_interaction.call_args[0][0]
                    assert call_args.user_id == 42

    def test_unauthenticated_user_uses_zero(self, app):
        with app.app_context():
            mock_user = MagicMock()
            mock_user.is_authenticated = False

            with patch("app.services.chatbot_telemetry.current_user", mock_user):
                with patch("app.services.chatbot_telemetry.telemetry_service") as mock_svc:
                    track_chatbot_interaction(
                        message="Query",
                        response="Answer",
                        llm_provider="openai",
                        model_name=None,
                        response_time_ms=50.0,
                        success=True,
                    )
                    call_args = mock_svc.track_interaction.call_args[0][0]
                    assert call_args.user_id == 0

    def test_with_optional_params(self, app):
        with app.app_context():
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            mock_user.id = 1
            mock_user.session_id = "s1"

            with patch("app.services.chatbot_telemetry.current_user", mock_user):
                with patch("app.services.chatbot_telemetry.telemetry_service") as mock_svc:
                    track_chatbot_interaction(
                        message="Tell me about X",
                        response="X is ...",
                        llm_provider="openai",
                        model_name="gpt-4",
                        response_time_ms=200.0,
                        success=False,
                        error_type="timeout",
                        function_calls=["search"],
                        page_context="dashboard",
                        language="fr",
                        used_provenance=True,
                    )
                    call_args = mock_svc.track_interaction.call_args[0][0]
                    assert call_args.language == "fr"
                    assert call_args.used_provenance is True
                    assert call_args.error_type == "timeout"

    def test_exception_in_tracking_logged(self, app):
        with app.app_context():
            with patch(
                "app.services.chatbot_telemetry.telemetry_service",
                side_effect=Exception("crash"),
            ):
                # Should not raise
                track_chatbot_interaction(
                    message="m", response="r", llm_provider="openai",
                    model_name=None, response_time_ms=1, success=True,
                )

    def test_session_id_fallback_to_anonymous(self, app):
        with app.app_context():
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            mock_user.id = 1
            del mock_user.session_id  # no session_id attribute

            with patch("app.services.chatbot_telemetry.current_user", mock_user):
                with patch("app.services.chatbot_telemetry.telemetry_service") as mock_svc:
                    track_chatbot_interaction(
                        message="m", response="r", llm_provider="openai",
                        model_name=None, response_time_ms=1, success=True,
                    )
                    call_args = mock_svc.track_interaction.call_args[0][0]
                    assert call_args.session_id == "anonymous"


# ---------------------------------------------------------------------------
# get_chatbot_analytics
# ---------------------------------------------------------------------------
class TestGetChatbotAnalytics:
    def test_returns_combined_analytics(self, app):
        with app.app_context():
            with patch("app.services.chatbot_telemetry.telemetry_service") as mock_svc:
                mock_svc.get_usage_stats.return_value = {"total_interactions": 5}
                mock_svc.get_error_analysis.return_value = {"errors": []}
                mock_svc.get_function_usage_stats.return_value = {"total_function_calls": 2}

                result = get_chatbot_analytics()
                assert result["usage_stats"]["total_interactions"] == 5
                assert result["error_analysis"] == {"errors": []}
                assert "generated_at" in result

    def test_exception_returns_empty_dict(self, app):
        with app.app_context():
            with patch("app.services.chatbot_telemetry.telemetry_service") as mock_svc:
                mock_svc.get_usage_stats.side_effect = Exception("analytics crash")
                result = get_chatbot_analytics()
                assert result == {}
