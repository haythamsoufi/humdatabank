"""Tests for api_tracker.py — targeting 100% coverage."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from flask import g

from app.middleware.api_tracker import (
    _should_skip_api_usage_tracking,
    _api_tracker_logger,
    track_api_request,
    track_api_response,
    track_api_usage,
)


# ────────────────────────────────────────────────────────────────────────────
# _should_skip_api_usage_tracking
# ────────────────────────────────────────────────────────────────────────────

class TestShouldSkipApiUsageTracking:
    def test_notifications_path_skipped(self, app):
        with app.test_request_context("/api/notifications/list"):
            assert _should_skip_api_usage_tracking() is True

    def test_refresh_csrf_token_skipped(self, app):
        with app.test_request_context("/api/refresh-csrf-token"):
            assert _should_skip_api_usage_tracking() is True

    def test_presence_path_skipped(self, app):
        with app.test_request_context("/api/forms/presence/abc"):
            assert _should_skip_api_usage_tracking() is True

    def test_ai_ws_skipped(self, app):
        with app.test_request_context("/api/ai/v2/ws"):
            assert _should_skip_api_usage_tracking() is True

    def test_ai_documents_ws_skipped(self, app):
        with app.test_request_context("/api/ai/documents/ws"):
            assert _should_skip_api_usage_tracking() is True

    def test_ai_chat_stream_skipped(self, app):
        with app.test_request_context("/api/ai/v2/chat/stream"):
            assert _should_skip_api_usage_tracking() is True

    def test_ai_chat_cancel_skipped(self, app):
        with app.test_request_context("/api/ai/v2/chat/cancel"):
            assert _should_skip_api_usage_tracking() is True

    def test_ai_documents_workflow_tour_skipped(self, app):
        with app.test_request_context("/api/ai/documents/workflows/abc/tour"):
            assert _should_skip_api_usage_tracking() is True

    def test_ai_documents_workflow_tour_no_skip_if_not_ending_in_tour(self, app):
        with app.test_request_context("/api/ai/documents/workflows/abc/steps"):
            assert _should_skip_api_usage_tracking() is False

    def test_lookup_lists_options_skipped(self, app):
        with app.test_request_context("/api/forms/lookup-lists/123/options"):
            assert _should_skip_api_usage_tracking() is True

    def test_lookup_lists_non_options_not_skipped(self, app):
        with app.test_request_context("/api/forms/lookup-lists/123/details"):
            assert _should_skip_api_usage_tracking() is False

    def test_render_pending_skipped(self, app):
        with app.test_request_context("/api/forms/dynamic-indicators/render-pending"):
            assert _should_skip_api_usage_tracking() is True

    def test_ai_v2_token_skipped(self, app):
        with app.test_request_context("/api/ai/v2/token"):
            assert _should_skip_api_usage_tracking() is True

    def test_variables_resolve_skipped(self, app):
        with app.test_request_context("/api/v1/variables/resolve"):
            assert _should_skip_api_usage_tracking() is True

    def test_ai_v2_conversations_get_skipped(self, app):
        with app.test_request_context("/api/ai/v2/conversations", method="GET"):
            assert _should_skip_api_usage_tracking() is True

    def test_ai_v2_conversations_post_not_skipped(self, app):
        with app.test_request_context("/api/ai/v2/conversations", method="POST"):
            assert _should_skip_api_usage_tracking() is False

    def test_ai_v2_single_conversation_get_skipped(self, app):
        with app.test_request_context("/api/ai/v2/conversations/abc123", method="GET"):
            assert _should_skip_api_usage_tracking() is True

    def test_ai_v2_single_conversation_get_with_sub_path_not_skipped(self, app):
        # Has a slash after the ID — not a single conversation
        with app.test_request_context("/api/ai/v2/conversations/abc123/messages", method="GET"):
            assert _should_skip_api_usage_tracking() is False

    def test_ai_v2_conversations_delete_not_skipped(self, app):
        with app.test_request_context("/api/ai/v2/conversations/abc", method="DELETE"):
            assert _should_skip_api_usage_tracking() is False

    def test_normal_api_path_not_skipped(self, app):
        with app.test_request_context("/api/v1/users"):
            assert _should_skip_api_usage_tracking() is False


# ────────────────────────────────────────────────────────────────────────────
# _api_tracker_logger
# ────────────────────────────────────────────────────────────────────────────

class TestApiTrackerLogger:
    def test_returns_logger_and_level_debug(self, app):
        with app.app_context():
            app.config["API_TRACKER_LOG_LEVEL"] = "DEBUG"
            with app.test_request_context("/api/test"):
                import logging
                logger, level = _api_tracker_logger()
                assert level == logging.DEBUG

    def test_returns_logger_and_level_info(self, app):
        with app.app_context():
            app.config["API_TRACKER_LOG_LEVEL"] = "INFO"
            with app.test_request_context("/api/test"):
                import logging
                logger, level = _api_tracker_logger()
                assert level == logging.INFO

    def test_returns_logger_and_level_warning(self, app):
        with app.app_context():
            app.config["API_TRACKER_LOG_LEVEL"] = "WARNING"
            with app.test_request_context("/api/test"):
                import logging
                logger, level = _api_tracker_logger()
                assert level == logging.WARNING

    def test_invalid_log_level_defaults_to_debug(self, app):
        with app.app_context():
            app.config["API_TRACKER_LOG_LEVEL"] = "INVALID_LEVEL"
            with app.test_request_context("/api/test"):
                import logging
                logger, level = _api_tracker_logger()
                assert level == logging.DEBUG

    def test_none_log_level_defaults_to_debug(self, app):
        with app.app_context():
            app.config["API_TRACKER_LOG_LEVEL"] = None
            with app.test_request_context("/api/test"):
                import logging
                logger, level = _api_tracker_logger()
                assert level == logging.DEBUG


# ────────────────────────────────────────────────────────────────────────────
# track_api_request
# ────────────────────────────────────────────────────────────────────────────

class TestTrackApiRequest:
    @staticmethod
    def _clear_api_start_time():
        """Drop stale api_start_time left on app-context g by prior client requests."""
        g.pop("api_start_time", None)

    def test_non_api_path_does_nothing(self, app):
        with app.test_request_context("/dashboard"):
            self._clear_api_start_time()
            track_api_request()
            assert getattr(g, "api_start_time", None) is None

    def test_api_path_sets_start_time(self, app):
        with app.test_request_context("/api/v1/users"):
            with patch("app.middleware.api_tracker._should_skip_api_usage_tracking",
                       return_value=False):
                self._clear_api_start_time()
                track_api_request()
                start = getattr(g, "api_start_time", None)
                assert start is not None
                assert isinstance(start, float)

    def test_skipped_api_path_no_start_time(self, app):
        with app.test_request_context("/api/notifications/list"):
            self._clear_api_start_time()
            track_api_request()
            assert getattr(g, "api_start_time", None) is None


# ────────────────────────────────────────────────────────────────────────────
# track_api_response
# ────────────────────────────────────────────────────────────────────────────

class TestTrackApiResponse:
    def test_non_api_path_returns_response_unchanged(self, app):
        with app.test_request_context("/dashboard"):
            from flask import make_response
            resp = make_response("ok", 200)
            result = track_api_response(resp)
            assert result is resp

    def test_skipped_path_returns_response_unchanged(self, app):
        with app.test_request_context("/api/notifications/list"):
            from flask import make_response
            resp = make_response("ok", 200)
            result = track_api_response(resp)
            assert result is resp

    def test_missing_start_time_returns_response(self, app):
        with app.test_request_context("/api/v1/users"):
            with patch("app.middleware.api_tracker._should_skip_api_usage_tracking",
                       return_value=False):
                # Don't set g.api_start_time
                from flask import make_response
                resp = make_response("ok", 200)
                result = track_api_response(resp)
                assert result is resp

    def test_tracks_api_usage_successfully(self, app, db_session):
        with app.test_request_context("/api/v1/users", method="GET"):
            g.api_start_time = time.time() - 0.1
            g.api_key_usage_id = None
            g.api_key_record = None

            with patch("app.middleware.api_tracker._should_skip_api_usage_tracking",
                       return_value=False), \
                 patch("app.middleware.api_tracker.get_json_safe", return_value=None), \
                 patch("sqlalchemy.orm.sessionmaker") as mock_sm:

                mock_session = MagicMock()
                mock_sm.return_value.return_value = mock_session

                from flask import make_response
                resp = make_response("ok", 200)
                result = track_api_response(resp)
                assert result is resp
                mock_session.add.assert_called_once()
                mock_session.commit.assert_called_once()
                mock_session.close.assert_called_once()

    def test_tracks_with_sensitive_data_redacted(self, app, db_session):
        sensitive_data = {"password": "secret123", "username": "user1"}
        with app.test_request_context("/api/v1/auth", method="POST",
                                       json=sensitive_data):
            g.api_start_time = time.time() - 0.05
            g.api_key_usage_id = None
            g.api_key_record = None

            with patch("app.middleware.api_tracker._should_skip_api_usage_tracking",
                       return_value=False), \
                 patch("app.middleware.api_tracker.get_json_safe",
                       return_value=sensitive_data), \
                 patch("sqlalchemy.orm.sessionmaker") as mock_sm:

                mock_session = MagicMock()
                mock_sm.return_value.return_value = mock_session

                from flask import make_response
                resp = make_response("ok", 200)
                track_api_response(resp)

                # Find the APIUsage object that was added
                add_call = mock_session.add.call_args_list[0]
                usage_obj = add_call[0][0]
                # password should be redacted
                assert usage_obj.request_data.get("password") == "***REDACTED***"
                assert usage_obj.request_data.get("username") == "user1"

    def test_tracks_with_api_key_id_from_g(self, app, db_session):
        with app.test_request_context("/api/v1/users"):
            g.api_start_time = time.time()
            g.api_key_usage_id = 5
            g.api_key_usage_client_name = "Test Client"

            with patch("app.middleware.api_tracker._should_skip_api_usage_tracking",
                       return_value=False), \
                 patch("app.middleware.api_tracker.get_json_safe", return_value=None), \
                 patch("sqlalchemy.orm.sessionmaker") as mock_sm:

                mock_session = MagicMock()
                mock_sm.return_value.return_value = mock_session

                from flask import make_response
                resp = make_response("ok", 200)
                track_api_response(resp)

                # Should add both APIUsage and APIKeyUsage
                assert mock_session.add.call_count == 2

    def test_tracks_with_api_key_record_from_g(self, app, db_session):
        with app.test_request_context("/api/v1/data"):
            g.api_start_time = time.time()
            g.api_key_usage_id = None

            mock_key_record = MagicMock()
            g.api_key_record = mock_key_record

            with patch("app.middleware.api_tracker._should_skip_api_usage_tracking",
                       return_value=False), \
                 patch("app.middleware.api_tracker.get_json_safe", return_value=None), \
                 patch("sqlalchemy.orm.sessionmaker") as mock_sm, \
                 patch("sqlalchemy.inspect") as mock_insp:

                insp_instance = MagicMock()
                insp_instance.identity = [10]
                mock_insp.return_value = insp_instance

                mock_session = MagicMock()
                mock_sm.return_value.return_value = mock_session

                from flask import make_response
                resp = make_response("ok", 200)
                track_api_response(resp)

    def test_db_error_is_caught_and_rollback(self, app):
        with app.test_request_context("/api/v1/users"):
            g.api_start_time = time.time()
            g.api_key_usage_id = None
            g.api_key_record = None

            with patch("app.middleware.api_tracker._should_skip_api_usage_tracking",
                       return_value=False), \
                 patch("app.middleware.api_tracker.get_json_safe", return_value=None), \
                 patch("sqlalchemy.orm.sessionmaker") as mock_sm:

                mock_session = MagicMock()
                mock_session.commit.side_effect = Exception("DB connection lost")
                mock_sm.return_value.return_value = mock_session

                from flask import make_response
                resp = make_response("ok", 200)
                # Should not raise
                result = track_api_response(resp)
                assert result is resp
                mock_session.rollback.assert_called_once()
                mock_session.close.assert_called_once()

    def test_outer_exception_caught(self, app):
        """Exception in setup phase (before sessionmaker) is caught."""
        with app.test_request_context("/api/v1/users"):
            g.api_start_time = time.time()

            with patch("app.middleware.api_tracker._should_skip_api_usage_tracking",
                       return_value=False), \
                 patch("app.middleware.api_tracker.get_json_safe",
                       side_effect=Exception("JSON parse error")), \
                 patch("sqlalchemy.orm.sessionmaker") as mock_sm:

                mock_session = MagicMock()
                mock_sm.return_value.return_value = mock_session

                from flask import make_response
                resp = make_response("ok", 200)
                result = track_api_response(resp)
                assert result is resp


# ────────────────────────────────────────────────────────────────────────────
# track_api_usage decorator
# ────────────────────────────────────────────────────────────────────────────

class TestTrackApiUsageDecorator:
    def test_decorator_calls_track_request_and_response(self, app):
        with app.test_request_context("/api/v1/test"):
            with patch("app.middleware.api_tracker.track_api_request") as mock_req, \
                 patch("app.middleware.api_tracker.track_api_response") as mock_resp:
                from flask import make_response
                fake_resp = make_response("ok", 200)
                mock_resp.return_value = fake_resp

                @track_api_usage
                def view_func():
                    return fake_resp

                result = view_func()
                mock_req.assert_called_once()
                mock_resp.assert_called_once_with(fake_resp)

    def test_decorator_propagates_exception(self, app):
        with app.test_request_context("/api/v1/test"):
            with patch("app.middleware.api_tracker.track_api_request"), \
                 patch("app.middleware.api_tracker.track_api_response"):

                @track_api_usage
                def failing_view():
                    raise RuntimeError("view failed")

                with pytest.raises(RuntimeError, match="view failed"):
                    failing_view()

    def test_decorator_logs_exception_without_mocking_internals(self, app):
        with app.test_request_context("/api/v1/test"):
            with patch("app.middleware.api_tracker.track_api_request"), \
                 patch("app.middleware.api_tracker.track_api_response"), \
                 patch.object(app.logger, "error") as mock_error:

                @track_api_usage
                def failing_view():
                    raise RuntimeError("view failed")

                with pytest.raises(RuntimeError, match="view failed"):
                    failing_view()
                mock_error.assert_called_once()


class TestTrackApiRequestLogging:
    def test_api_path_logs_start_message(self, app):
        with app.test_request_context("/api/v1/users"):
            g.pop("api_start_time", None)
            with patch("app.middleware.api_tracker._should_skip_api_usage_tracking",
                       return_value=False), \
                 patch.object(app.logger, "log") as mock_log:
                track_api_request()
                mock_log.assert_called_once()
                assert getattr(g, "api_start_time", None) is not None


class TestApiKeyRecordIdentity:
    def test_empty_identity_does_not_add_key_usage_row(self, app, db_session):
        with app.test_request_context("/api/v1/data"):
            g.pop("api_start_time", None)
            g.api_start_time = time.time()
            g.api_key_usage_id = None
            g.api_key_record = MagicMock()

            with patch("app.middleware.api_tracker._should_skip_api_usage_tracking",
                       return_value=False), \
                 patch("app.middleware.api_tracker.get_json_safe", return_value=None), \
                 patch("sqlalchemy.orm.sessionmaker") as mock_sm, \
                 patch("sqlalchemy.inspect") as mock_insp:

                insp_instance = MagicMock()
                insp_instance.identity = None
                mock_insp.return_value = insp_instance

                mock_session = MagicMock()
                mock_sm.return_value.return_value = mock_session

                from flask import make_response
                track_api_response(make_response("ok", 200))

                assert mock_session.add.call_count == 1
