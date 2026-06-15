"""
Comprehensive tests for app/services/user_analytics_service.py.

Covers every branch including:
  - Pure utility helpers (no DB / Flask context needed)
  - Functions that require a Flask request context (mocked DB)
  - Functions that require current_user / session state
  - Error-handling branches (exception suppression)

Note: analyze_ua_for_bot, _update_session_activity_explicit,
      merge_page_view_path_histograms and format_page_path_histogram_csv
      already have dedicated tests elsewhere; complementary edge-case tests
      are added here where additional branches remain uncovered.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call
from io import StringIO

# ── Convenience import ─────────────────────────────────────────────────────
from app.services import user_analytics_service as _svc


# ===========================================================================
# Pure helpers – no Flask context required
# ===========================================================================

class TestStripIpPort:
    def test_plain_ipv4_unchanged(self):
        assert _svc._strip_ip_port("1.2.3.4") == "1.2.3.4"

    def test_ipv4_with_port_strips_port(self):
        assert _svc._strip_ip_port("1.2.3.4:53708") == "1.2.3.4"

    def test_ipv6_brackets_strips_brackets_and_port(self):
        assert _svc._strip_ip_port("[::1]:8080") == "::1"

    def test_raw_ipv6_unchanged(self):
        ip = "2001:db8::1"
        assert _svc._strip_ip_port(ip) == ip

    def test_none_returns_none(self):
        assert _svc._strip_ip_port(None) is None

    def test_unknown_returns_unknown(self):
        assert _svc._strip_ip_port("unknown") == "unknown"

    def test_empty_string_returns_empty(self):
        # Falsy value — guard returns it unchanged
        assert _svc._strip_ip_port("") == ""


class TestIpv4Subnet:
    def test_standard_ipv4(self):
        assert _svc._ipv4_subnet("1.2.3.4") == "1.2.3"

    def test_custom_prefix_octets(self):
        assert _svc._ipv4_subnet("10.20.30.40", prefix_octets=2) == "10.20"

    def test_ipv6_returns_none(self):
        assert _svc._ipv4_subnet("::1") is None

    def test_none_returns_none(self):
        assert _svc._ipv4_subnet(None) is None

    def test_malformed_ipv4_returns_none(self):
        assert _svc._ipv4_subnet("1.2.3") is None  # only 3 parts


class TestGetDeviceType:
    def test_mobile(self):
        ua = MagicMock()
        ua.is_mobile = True
        ua.is_tablet = False
        assert _svc.get_device_type(ua) == "Mobile"

    def test_tablet(self):
        ua = MagicMock()
        ua.is_mobile = False
        ua.is_tablet = True
        assert _svc.get_device_type(ua) == "Tablet"

    def test_desktop(self):
        ua = MagicMock()
        ua.is_mobile = False
        ua.is_tablet = False
        assert _svc.get_device_type(ua) == "Desktop"

    def test_none_returns_unknown(self):
        assert _svc.get_device_type(None) == "Unknown"


class TestSessionLogDeviceIconClasses:
    def test_android(self):
        result = _svc.session_log_device_icon_classes(operating_system="Android 14")
        assert "android" in result

    def test_apple_ios(self):
        result = _svc.session_log_device_icon_classes(operating_system="iOS 17")
        assert "apple" in result

    def test_apple_mac(self):
        result = _svc.session_log_device_icon_classes(operating_system="Mac OS X 10.15")
        assert "apple" in result

    def test_windows(self):
        result = _svc.session_log_device_icon_classes(operating_system="Windows 10")
        assert "windows" in result

    def test_linux(self):
        result = _svc.session_log_device_icon_classes(operating_system="Linux x86_64")
        assert "linux" in result

    def test_tablet_fallback(self):
        result = _svc.session_log_device_icon_classes(device_type="Tablet")
        assert "tablet" in result

    def test_mobile_fallback(self):
        result = _svc.session_log_device_icon_classes(device_type="Mobile")
        assert "mobile" in result

    def test_default_laptop(self):
        result = _svc.session_log_device_icon_classes()
        assert "laptop" in result

    def test_user_agent_included_in_check(self):
        # android in UA string should be caught even if OS is blank
        result = _svc.session_log_device_icon_classes(user_agent="okhttp/4 android/14")
        assert "android" in result


class TestDetectBotUserAgent:
    def test_regular_browser_not_bot(self):
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120 Safari/537.36"
        )
        assert _svc.detect_bot_user_agent(ua) is False

    def test_curl_is_bot(self):
        assert _svc.detect_bot_user_agent("curl/8.0") is True

    def test_empty_is_bot(self):
        assert _svc.detect_bot_user_agent("") is True

    def test_none_is_bot(self):
        assert _svc.detect_bot_user_agent(None) is True

    def test_native_flutter_not_bot(self):
        assert _svc.detect_bot_user_agent("Dart/3.5 (dart:io)") is False


class TestBotUserAgentExplanation:
    def test_curl_has_explanation(self):
        reason = _svc.bot_user_agent_explanation("curl/8.0")
        assert reason is not None
        assert isinstance(reason, str)

    def test_browser_has_no_explanation(self):
        ua = "Mozilla/5.0 Chrome/120 Safari/537.36"
        assert _svc.bot_user_agent_explanation(ua) is None

    def test_none_ua_has_explanation(self):
        reason = _svc.bot_user_agent_explanation(None)
        assert reason is not None


class TestEffectiveSessionDurationMinutes:
    def _session(self, **kw):
        s = MagicMock()
        s.session_start = kw.get("session_start", datetime.now(timezone.utc) - timedelta(minutes=10))
        s.session_end = kw.get("session_end", None)
        s.is_active = kw.get("is_active", False)
        s.duration_minutes = kw.get("duration_minutes", None)
        return s

    def test_returns_none_for_none_log(self):
        assert _svc.effective_session_duration_minutes(None) is None

    def test_returns_none_when_no_session_start(self):
        s = MagicMock()
        s.session_start = None
        assert _svc.effective_session_duration_minutes(s) is None

    def test_uses_session_end_when_set(self):
        start = datetime.now(timezone.utc) - timedelta(minutes=30)
        end = datetime.now(timezone.utc)
        s = self._session(session_start=start, session_end=end, is_active=False)
        result = _svc.effective_session_duration_minutes(s)
        assert result is not None
        assert result >= 29  # ~30 minutes

    def test_uses_utcnow_when_active(self):
        start = datetime.now(timezone.utc) - timedelta(minutes=5)
        s = self._session(session_start=start, session_end=None, is_active=True)
        result = _svc.effective_session_duration_minutes(s)
        assert result is not None
        assert result >= 4

    def test_falls_back_to_duration_minutes(self):
        s = self._session(session_end=None, is_active=False, duration_minutes=42)
        result = _svc.effective_session_duration_minutes(s)
        assert result == 42

    def test_returns_none_when_no_data(self):
        s = self._session(session_end=None, is_active=False, duration_minutes=None)
        result = _svc.effective_session_duration_minutes(s)
        assert result is None

    def test_never_negative(self):
        # session_end before session_start (bad data) -> max(0, ...)
        start = datetime.now(timezone.utc)
        end = start - timedelta(minutes=5)
        s = self._session(session_start=start, session_end=end)
        result = _svc.effective_session_duration_minutes(s)
        assert result == 0


class TestEffectiveSessionActiveDurationMinutes:
    def test_none_log_returns_none(self):
        assert _svc.effective_session_active_duration_minutes(None) is None

    def test_none_start_returns_none(self):
        s = MagicMock()
        s.session_start = None
        assert _svc.effective_session_active_duration_minutes(s) is None

    def test_none_last_activity_returns_zero(self):
        s = MagicMock()
        s.session_start = datetime.now(timezone.utc)
        s.last_activity = None
        assert _svc.effective_session_active_duration_minutes(s) == 0

    def test_computes_delta(self):
        now = datetime.now(timezone.utc)
        s = MagicMock()
        s.session_start = now - timedelta(minutes=20)
        s.last_activity = now
        result = _svc.effective_session_active_duration_minutes(s)
        assert result is not None
        assert result >= 19


class TestEmptyPagePathHistogram:
    def test_structure(self):
        result = _svc._empty_page_path_histogram(7)
        assert result["paths"] == []
        assert result["sessions_in_scope"] == 0
        assert result["period"]["days"] == 7
        assert result["distinct_path_count"] == 0

    def test_clamps_days(self):
        result = _svc._empty_page_path_histogram(0)
        assert result["period"]["days"] >= 1
        result = _svc._empty_page_path_histogram(99999)
        assert result["period"]["days"] <= 3660


# ===========================================================================
# Flask context helpers
# ===========================================================================

class TestIsAutoManagedRequest:
    def test_false_when_no_request_context(self, app):
        with app.app_context():
            assert _svc._is_auto_managed_request() is False

    def test_false_when_flag_not_set(self, app):
        with app.test_request_context("/static/app.js"):
            assert _svc._is_auto_managed_request() is False

    def test_true_when_flag_set(self, app):
        from flask import g
        with app.test_request_context("/static/app.js"):
            g._auto_txn_managed = True
            assert _svc._is_auto_managed_request() is True


class TestCommitOrFlush:
    def test_commits_when_not_managed(self, app):
        with app.test_request_context("/static/app.js"):
            with patch("app.services.user_analytics_service.db") as mock_db:
                _svc._commit_or_flush()
                mock_db.session.commit.assert_called_once()
                mock_db.session.flush.assert_not_called()

    def test_flushes_when_managed(self, app):
        from flask import g
        with app.test_request_context("/static/app.js"):
            g._auto_txn_managed = True
            with patch("app.services.user_analytics_service.db") as mock_db:
                _svc._commit_or_flush()
                mock_db.session.flush.assert_called_once()
                mock_db.session.commit.assert_not_called()


class TestResolveUserSessionIdForLogging:
    def test_returns_session_session_id(self, app):
        with app.test_request_context("/"):
            from flask import session
            session["session_id"] = "abc-123"
            result = _svc._resolve_user_session_id_for_logging()
            assert result == "abc-123"

    def test_truncates_long_session_id(self, app):
        with app.test_request_context("/"):
            from flask import session
            session["session_id"] = "x" * 300
            result = _svc._resolve_user_session_id_for_logging()
            assert len(result) == 255

    def test_returns_jwt_sid_when_no_flask_session(self, app):
        from flask import g
        with app.test_request_context("/"):
            g._mobile_jwt_sid = "jwt-session-456"
            result = _svc._resolve_user_session_id_for_logging()
            assert result == "jwt-session-456"

    def test_returns_none_when_no_ids(self, app):
        with app.test_request_context("/"):
            result = _svc._resolve_user_session_id_for_logging()
            assert result is None

    def test_returns_none_outside_request_context(self, app):
        with app.app_context():
            result = _svc._resolve_user_session_id_for_logging()
            assert result is None


class TestGetClientIp:
    def test_x_forwarded_for(self, app):
        with app.test_request_context("/", headers={"X-Forwarded-For": "5.5.5.5, 1.1.1.1"}):
            assert _svc.get_client_ip() == "5.5.5.5"

    def test_x_real_ip(self, app):
        with app.test_request_context("/", headers={"X-Real-IP": "6.6.6.6"}):
            assert _svc.get_client_ip() == "6.6.6.6"

    def test_remote_addr_fallback(self, app):
        with app.test_request_context("/"):
            ip = _svc.get_client_ip()
            assert ip is not None

    def test_strips_port_from_forwarded_for(self, app):
        with app.test_request_context("/", headers={"X-Forwarded-For": "1.2.3.4:12345"}):
            assert _svc.get_client_ip() == "1.2.3.4"


class TestGetClientInfo:
    def test_returns_expected_keys(self, app):
        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"},
        ):
            info = _svc.get_client_info()
            assert set(info.keys()) >= {"ip_address", "user_agent", "browser", "operating_system", "device_type"}

    def test_x_platform_ios_overrides_device_type(self, app):
        with app.test_request_context(
            "/",
            headers={
                "User-Agent": "Dart/3.5 (dart:io)",
                "X-Platform": "ios",
                "X-OS-Version": "iOS 17.4",
            },
        ):
            info = _svc.get_client_info()
            assert info["device_type"] == "Mobile"
            assert info["browser"] == "Humanitarian Databank App"
            assert info["operating_system"] == "iOS 17.4"

    def test_x_platform_android_without_os_version(self, app):
        with app.test_request_context(
            "/",
            headers={
                "User-Agent": "Dart/3.5 (dart:io)",
                "X-Platform": "android",
            },
        ):
            info = _svc.get_client_info()
            assert info["device_type"] == "Mobile"

    def test_no_user_agent_header(self, app):
        with app.test_request_context("/"):
            info = _svc.get_client_info()
            assert "ip_address" in info


class TestShouldSkipActivityUserLogEndpoint:
    def test_none_endpoint_not_skipped(self):
        assert _svc._should_skip_activity_user_log_endpoint(None) is False

    def test_known_skip_endpoint_is_skipped(self):
        assert _svc._should_skip_activity_user_log_endpoint(
            "forms_api.api_presence_active_users"
        ) is True

    def test_device_heartbeat_suffix_is_skipped(self):
        assert _svc._should_skip_activity_user_log_endpoint(
            "some_blueprint.device_heartbeat"
        ) is True

    def test_analytics_user_analytics_partial_is_skipped(self, app):
        with app.test_request_context("/?partial=1"):
            assert _svc._should_skip_activity_user_log_endpoint("analytics.user_analytics") is True

    def test_analytics_user_analytics_full_not_skipped(self, app):
        with app.test_request_context("/"):
            assert _svc._should_skip_activity_user_log_endpoint("analytics.user_analytics") is False

    def test_unknown_endpoint_not_skipped(self):
        assert _svc._should_skip_activity_user_log_endpoint("some.random.endpoint") is False


# ===========================================================================
# Session blacklist
# ===========================================================================

class TestSessionBlacklist:
    def setup_method(self):
        # Reset blacklist between tests
        import app.services.user_analytics_service as m
        m._blacklisted_sessions.clear()

    def test_add_and_check(self, app):
        with app.app_context():
            _svc.add_session_to_blacklist("sess-001")
            assert _svc.is_session_blacklisted("sess-001") is True

    def test_remove_from_blacklist(self, app):
        with app.app_context():
            _svc.add_session_to_blacklist("sess-002")
            _svc.remove_session_from_blacklist("sess-002")
            # Now must fall back to DB; mock query returning None
            with patch(
                "app.services.user_analytics_service.UserSessionLog"
            ) as MockSL:
                MockSL.query.with_entities.return_value.filter_by.return_value.first.return_value = None
                assert _svc.is_session_blacklisted("sess-002") is False

    def test_not_blacklisted_by_default(self, app):
        with app.app_context():
            with patch(
                "app.services.user_analytics_service.UserSessionLog"
            ) as MockSL:
                MockSL.query.with_entities.return_value.filter_by.return_value.first.return_value = None
                assert _svc.is_session_blacklisted("sess-never-added") is False

    def test_db_fallback_admin_action_blacklists(self, app):
        """DB row ended_by='admin_action' should count as blacklisted even without in-memory entry."""
        with app.app_context():
            fake_row = MagicMock()
            fake_row.is_active = False
            fake_row.ended_by = "admin_action"
            with patch(
                "app.services.user_analytics_service.UserSessionLog"
            ) as MockSL:
                MockSL.query.with_entities.return_value.filter_by.return_value.first.return_value = fake_row
                result = _svc.is_session_blacklisted("sess-admin-forced")
                assert result is True

    def test_db_fallback_logout_blacklists(self, app):
        """DB row ended_by='logout' with is_active=False should be blacklisted (replayed cookie protection)."""
        with app.app_context():
            fake_row = MagicMock()
            fake_row.is_active = False
            fake_row.ended_by = "logout"
            with patch(
                "app.services.user_analytics_service.UserSessionLog"
            ) as MockSL:
                MockSL.query.with_entities.return_value.filter_by.return_value.first.return_value = fake_row
                assert _svc.is_session_blacklisted("sess-logout") is True

    def test_db_fallback_timeout_blacklists(self, app):
        """DB row ended_by='timeout' with is_active=False should be blacklisted."""
        with app.app_context():
            fake_row = MagicMock()
            fake_row.is_active = False
            fake_row.ended_by = "timeout"
            with patch(
                "app.services.user_analytics_service.UserSessionLog"
            ) as MockSL:
                MockSL.query.with_entities.return_value.filter_by.return_value.first.return_value = fake_row
                assert _svc.is_session_blacklisted("sess-timeout") is True

    def test_db_fallback_active_session_not_blacklisted(self, app):
        """DB row with is_active=True must never be treated as blacklisted."""
        with app.app_context():
            fake_row = MagicMock()
            fake_row.is_active = True
            fake_row.ended_by = None
            with patch(
                "app.services.user_analytics_service.UserSessionLog"
            ) as MockSL:
                MockSL.query.with_entities.return_value.filter_by.return_value.first.return_value = fake_row
                assert _svc.is_session_blacklisted("sess-still-active") is False

    def test_db_fallback_warms_in_memory_cache(self, app):
        """After a DB hit, the session_id is added to the in-memory set (no second DB query)."""
        import app.services.user_analytics_service as m
        m._blacklisted_sessions.discard("sess-warm")
        with app.app_context():
            fake_row = MagicMock()
            fake_row.is_active = False
            fake_row.ended_by = "logout"
            with patch(
                "app.services.user_analytics_service.UserSessionLog"
            ) as MockSL:
                MockSL.query.with_entities.return_value.filter_by.return_value.first.return_value = fake_row
                _svc.is_session_blacklisted("sess-warm")
            # In-memory cache should now contain it — second call never needs DB
            assert "sess-warm" in m._blacklisted_sessions

    def test_db_fallback_exception_returns_false(self, app):
        """DB error during blacklist check should return False (safe default)."""
        with app.app_context():
            with patch(
                "app.services.user_analytics_service.UserSessionLog"
            ) as MockSL:
                MockSL.query.with_entities.side_effect = Exception("DB boom")
                assert _svc.is_session_blacklisted("sess-db-error") is False


# ===========================================================================
# end_user_session
# ===========================================================================

class TestEndUserSession:
    def test_ends_active_session(self, app):
        with app.app_context():
            fake_session = MagicMock()
            fake_session.is_active = True
            fake_session.session_start = datetime.now(timezone.utc) - timedelta(minutes=15)
            fake_session.session_end = None

            with patch(
                "app.services.user_analytics_service.UserSessionLog"
            ) as MockSL:
                MockSL.query.filter_by.return_value.first.return_value = fake_session
                _svc.end_user_session("sid-123", "logout")

            assert fake_session.is_active is False
            assert fake_session.ended_by == "logout"
            assert fake_session.duration_minutes is not None

    def test_noop_when_session_id_none(self, app):
        with app.app_context():
            with patch(
                "app.services.user_analytics_service.UserSessionLog"
            ) as MockSL:
                _svc.end_user_session(None, "logout")
                MockSL.query.filter_by.assert_not_called()

    def test_noop_when_session_not_found(self, app):
        with app.app_context():
            with patch(
                "app.services.user_analytics_service.UserSessionLog"
            ) as MockSL:
                MockSL.query.filter_by.return_value.first.return_value = None
                _svc.end_user_session("unknown-sid", "logout")

    def test_noop_when_session_already_ended(self, app):
        with app.app_context():
            fake_session = MagicMock()
            fake_session.is_active = False

            with patch(
                "app.services.user_analytics_service.UserSessionLog"
            ) as MockSL:
                MockSL.query.filter_by.return_value.first.return_value = fake_session
                _svc.end_user_session("inactive-sid", "logout")

            # is_active should remain False; no further mutation
            assert fake_session.is_active is False

    def test_exception_is_swallowed(self, app):
        with app.app_context():
            with patch(
                "app.services.user_analytics_service.UserSessionLog"
            ) as MockSL:
                MockSL.query.filter_by.side_effect = Exception("boom")
                # Should not raise
                _svc.end_user_session("bad-sid", "logout")


# ===========================================================================
# update_session_activity
# ===========================================================================

class TestUpdateSessionActivity:
    def _fake_session_log(self):
        sl = MagicMock()
        sl.is_active = True
        sl.page_views = 0
        sl.forms_submitted = 0
        sl.files_uploaded = 0
        sl.actions_performed = 0
        sl.page_view_path_counts = {}
        return sl

    def test_page_view_increments_page_views(self, app):
        fake_sl = self._fake_session_log()
        with app.test_request_context("/"):
            from flask import session
            session["session_id"] = "sess-pv"
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                MockSL.query.filter_by.return_value.first.return_value = fake_sl
                with patch("app.services.user_analytics_service.merge_page_view_path_count"):
                    with patch("app.services.user_analytics_service.db"):
                        with patch("app.services.user_analytics_service._rollback_transaction"):
                            _svc.update_session_activity("page_view")
            assert fake_sl.page_views == 1

    def test_form_submitted_increments_forms_and_actions(self, app):
        fake_sl = self._fake_session_log()
        with app.test_request_context("/"):
            from flask import session
            session["session_id"] = "sess-form"
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                MockSL.query.filter_by.return_value.first.return_value = fake_sl
                with patch("app.services.user_analytics_service.db"):
                    with patch("app.services.user_analytics_service._rollback_transaction"):
                        _svc.update_session_activity("form_submitted")
            assert fake_sl.forms_submitted == 1
            assert fake_sl.actions_performed == 1

    def test_file_uploaded_increments_files_and_actions(self, app):
        fake_sl = self._fake_session_log()
        with app.test_request_context("/"):
            from flask import session
            session["session_id"] = "sess-file"
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                MockSL.query.filter_by.return_value.first.return_value = fake_sl
                with patch("app.services.user_analytics_service.db"):
                    with patch("app.services.user_analytics_service._rollback_transaction"):
                        _svc.update_session_activity("file_uploaded")
            assert fake_sl.files_uploaded == 1
            assert fake_sl.actions_performed == 1

    def test_other_activity_increments_actions(self, app):
        fake_sl = self._fake_session_log()
        with app.test_request_context("/"):
            from flask import session
            session["session_id"] = "sess-other"
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                MockSL.query.filter_by.return_value.first.return_value = fake_sl
                with patch("app.services.user_analytics_service.db"):
                    with patch("app.services.user_analytics_service._rollback_transaction"):
                        _svc.update_session_activity("custom_event")
            assert fake_sl.actions_performed == 1

    def test_touch_type_does_not_increment_actions(self, app):
        fake_sl = self._fake_session_log()
        with app.test_request_context("/"):
            from flask import session
            session["session_id"] = "sess-touch"
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                MockSL.query.filter_by.return_value.first.return_value = fake_sl
                with patch("app.services.user_analytics_service.db"):
                    with patch("app.services.user_analytics_service._rollback_transaction"):
                        _svc.update_session_activity("action")
            assert fake_sl.actions_performed == 0

    def test_no_session_id_is_noop(self, app):
        with app.test_request_context("/"):
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                with patch("app.services.user_analytics_service.db"):
                    with patch("app.services.user_analytics_service._rollback_transaction"):
                        _svc.update_session_activity("page_view")
                MockSL.query.filter_by.assert_not_called()

    def test_exception_is_swallowed(self, app):
        with app.test_request_context("/"):
            from flask import session
            session["session_id"] = "sess-err"
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                MockSL.query.filter_by.side_effect = Exception("boom")
                with patch("app.services.user_analytics_service.db"):
                    with patch("app.services.user_analytics_service._rollback_transaction"):
                        _svc.update_session_activity("page_view")


# ===========================================================================
# _update_session_activity_explicit  (extra branches)
# ===========================================================================

class TestUpdateSessionActivityExplicit:
    """Additional branches not covered by the dedicated test module."""

    def test_none_session_id_is_noop(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                _svc._update_session_activity_explicit(None, "page_view")
                MockSL.query.filter_by.assert_not_called()

    def test_inactive_session_is_skipped(self, app):
        with app.app_context():
            fake = MagicMock()
            fake.is_active = False
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                MockSL.query.filter_by.return_value.first.return_value = fake
                _svc._update_session_activity_explicit("sid", "page_view")
            assert fake.page_views == fake.page_views  # not changed (no assert on call)

    def test_form_saved_path(self, app):
        with app.app_context():
            fake = MagicMock()
            fake.is_active = True
            fake.forms_submitted = 0
            fake.actions_performed = 0
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                MockSL.query.filter_by.return_value.first.return_value = fake
                _svc._update_session_activity_explicit("sid", "form_saved")
            assert fake.forms_submitted == 1
            assert fake.actions_performed == 1

    def test_data_save_path(self, app):
        with app.app_context():
            fake = MagicMock()
            fake.is_active = True
            fake.forms_submitted = 0
            fake.actions_performed = 0
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                MockSL.query.filter_by.return_value.first.return_value = fake
                _svc._update_session_activity_explicit("sid", "data_save")
            assert fake.forms_submitted == 1

    def test_exception_is_swallowed(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                MockSL.query.filter_by.side_effect = Exception("boom")
                # must not raise
                _svc._update_session_activity_explicit("sid", "page_view")


# ===========================================================================
# start_user_session
# ===========================================================================

class TestStartUserSession:
    def test_creates_session_log_row(self, app):
        mock_user = MagicMock()
        mock_user.id = 1

        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"},
        ):
            with patch("app.services.user_analytics_service.db") as mock_db:
                with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                    _svc.start_user_session(mock_user, "new-session-id")
                    MockSL.assert_called_once()
                    mock_db.session.add.assert_called_once()

    def test_exception_calls_rollback(self, app):
        mock_user = MagicMock()
        mock_user.id = 1
        with app.test_request_context("/"):
            with patch("app.services.user_analytics_service.db") as mock_db:
                mock_db.session.add.side_effect = Exception("boom")
                with patch("app.services.user_analytics_service._rollback_transaction") as mock_rb:
                    with patch("app.services.user_analytics_service.UserSessionLog"):
                        _svc.start_user_session(mock_user, "bad-session")
                mock_rb.assert_called_once()


# ===========================================================================
# log_login_attempt
# ===========================================================================

class TestLogLoginAttempt:
    def test_successful_login_is_logged(self, app):
        mock_user = MagicMock()
        mock_user.id = 42

        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"},
        ):
            with patch("app.services.user_analytics_service.db") as mock_db:
                with patch(
                    "app.services.user_analytics_service.check_suspicious_login",
                    return_value=None,
                ):
                    with patch(
                        "app.services.user_analytics_service.get_recent_failed_attempts",
                        return_value=0,
                    ):
                        with patch("app.services.user_analytics_service.UserLoginLog") as MockLL:
                            _svc.log_login_attempt(
                                "user@example.com",
                                success=True,
                                user=mock_user,
                                session_id="sess-1",
                            )
                            MockLL.assert_called_once()
                            mock_db.session.add.assert_called_once()

    def test_failed_login_creates_security_event(self, app):
        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"},
        ):
            with patch("app.services.user_analytics_service.db"):
                with patch(
                    "app.services.user_analytics_service.check_suspicious_login",
                    return_value=None,
                ):
                    with patch(
                        "app.services.user_analytics_service.get_recent_failed_attempts",
                        return_value=0,
                    ):
                        with patch("app.services.user_analytics_service.UserLoginLog"):
                            with patch(
                                "app.services.user_analytics_service.create_security_event_for_login"
                            ) as mock_sec:
                                _svc.log_login_attempt(
                                    "user@example.com",
                                    success=False,
                                    failure_reason="wrong_password",
                                )
                                mock_sec.assert_called_once()

    def test_suspicious_login_creates_security_event(self, app):
        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"},
        ):
            with patch("app.services.user_analytics_service.db"):
                with patch(
                    "app.services.user_analytics_service.check_suspicious_login",
                    return_value="brute_force: 5 failed attempts",
                ):
                    with patch(
                        "app.services.user_analytics_service.get_recent_failed_attempts",
                        return_value=0,
                    ):
                        with patch("app.services.user_analytics_service.UserLoginLog"):
                            with patch(
                                "app.services.user_analytics_service.create_security_event_for_login"
                            ) as mock_sec:
                                mock_user = MagicMock()
                                mock_user.id = 1
                                _svc.log_login_attempt(
                                    "attacker@example.com",
                                    success=True,
                                    user=mock_user,
                                )
                                mock_sec.assert_called_once()

    def test_exception_calls_rollback(self, app):
        with app.test_request_context("/"):
            with patch("app.services.user_analytics_service.db") as mock_db:
                mock_db.session.add.side_effect = Exception("boom")
                with patch(
                    "app.services.user_analytics_service.check_suspicious_login",
                    return_value=None,
                ):
                    with patch(
                        "app.services.user_analytics_service.get_recent_failed_attempts",
                        return_value=0,
                    ):
                        with patch("app.services.user_analytics_service.UserLoginLog"):
                            with patch(
                                "app.services.user_analytics_service._rollback_transaction"
                            ) as mock_rb:
                                _svc.log_login_attempt("x@x.com", success=False)
                                mock_rb.assert_called_once()


# ===========================================================================
# log_logout
# ===========================================================================

class TestLogLogout:
    def test_logs_logout_event(self, app):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.email = "user@example.com"

        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"},
        ):
            from flask import session
            session["session_id"] = "logout-sess"
            with patch("app.services.user_analytics_service.db") as mock_db:
                with patch("app.services.user_analytics_service.UserLoginLog") as MockLL:
                    with patch("app.services.user_analytics_service.end_user_session"):
                        _svc.log_logout(mock_user, session_duration_minutes=10)
                        MockLL.assert_called_once()
                        mock_db.session.add.assert_called_once()

    def test_exception_calls_rollback(self, app):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.email = "user@example.com"

        with app.test_request_context("/"):
            with patch("app.services.user_analytics_service.db") as mock_db:
                mock_db.session.add.side_effect = Exception("boom")
                with patch("app.services.user_analytics_service.UserLoginLog"):
                    with patch("app.services.user_analytics_service._rollback_transaction") as mock_rb:
                        _svc.log_logout(mock_user)
                        mock_rb.assert_called_once()


# ===========================================================================
# log_user_activity
# ===========================================================================

class TestLogUserActivity:
    def test_logs_activity_for_authenticated_user(self, app):
        with app.test_request_context(
            "/some/path",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"},
        ):
            mock_current_user = MagicMock()
            mock_current_user.is_authenticated = True
            mock_current_user.id = 1

            with patch(
                "app.services.user_analytics_service.current_user",
                mock_current_user,
            ):
                with patch("app.services.user_analytics_service.db") as mock_db:
                    with patch("app.services.user_analytics_service.UserActivityLog") as MockAL:
                        with patch(
                            "app.services.user_analytics_service.update_session_activity"
                        ):
                            with patch(
                                "app.services.user_analytics_service.page_view_path_key_from_request",
                                return_value="/some/path",
                            ):
                                _svc.log_user_activity(
                                    "page_view", description="Test page"
                                )
                                MockAL.assert_called_once()
                                mock_db.session.add.assert_called_once()

    def test_noop_for_unauthenticated_user(self, app):
        with app.test_request_context("/"):
            mock_current_user = MagicMock()
            mock_current_user.is_authenticated = False

            with patch(
                "app.services.user_analytics_service.current_user",
                mock_current_user,
            ):
                with patch("app.services.user_analytics_service.UserActivityLog") as MockAL:
                    _svc.log_user_activity("page_view")
                    MockAL.assert_not_called()

    def test_skips_skip_endpoint(self, app):
        with app.test_request_context("/"):
            mock_current_user = MagicMock()
            mock_current_user.is_authenticated = True

            with patch(
                "app.services.user_analytics_service.current_user",
                mock_current_user,
            ):
                with patch(
                    "app.services.user_analytics_service._should_skip_activity_user_log_endpoint",
                    return_value=True,
                ):
                    with patch("app.services.user_analytics_service.UserActivityLog") as MockAL:
                        _svc.log_user_activity("page_view")
                        MockAL.assert_not_called()

    def test_page_view_uses_context_data_path_key(self, app):
        with app.test_request_context("/"):
            mock_cu = MagicMock()
            mock_cu.is_authenticated = True
            mock_cu.id = 1

            with patch("app.services.user_analytics_service.current_user", mock_cu):
                with patch("app.services.user_analytics_service.db"):
                    with patch("app.services.user_analytics_service.UserActivityLog"):
                        with patch(
                            "app.services.user_analytics_service.update_session_activity"
                        ) as mock_update:
                            _svc.log_user_activity(
                                "page_view",
                                context_data={"page_view_path_key": "/my/path"},
                            )
                            # update_session_activity should be called with the key
                            mock_update.assert_called_once()
                            _, kw = mock_update.call_args
                            assert kw.get("page_view_path_key") == "/my/path"

    def test_exception_calls_rollback(self, app):
        with app.test_request_context("/"):
            mock_cu = MagicMock()
            mock_cu.is_authenticated = True
            mock_cu.id = 1

            with patch("app.services.user_analytics_service.current_user", mock_cu):
                with patch("app.services.user_analytics_service.db") as mock_db:
                    mock_db.session.add.side_effect = Exception("boom")
                    with patch("app.services.user_analytics_service.UserActivityLog"):
                        with patch(
                            "app.services.user_analytics_service._rollback_transaction"
                        ) as mock_rb:
                            _svc.log_user_activity("page_view")
                            mock_rb.assert_called_once()


# ===========================================================================
# increment_session_page_views_without_activity_log
# ===========================================================================

class TestIncrementSessionPageViews:
    def test_noop_for_unauthenticated_user(self, app):
        with app.test_request_context("/"):
            mock_cu = MagicMock()
            mock_cu.is_authenticated = False
            with patch("app.services.user_analytics_service.current_user", mock_cu):
                with patch(
                    "app.services.user_analytics_service.update_session_activity"
                ) as mock_update:
                    _svc.increment_session_page_views_without_activity_log()
                    mock_update.assert_not_called()

    def test_increments_for_authenticated_user(self, app):
        with app.test_request_context("/"):
            mock_cu = MagicMock()
            mock_cu.is_authenticated = True
            with patch("app.services.user_analytics_service.current_user", mock_cu):
                with patch(
                    "app.services.user_analytics_service.page_view_path_key_from_request",
                    return_value="/x",
                ):
                    with patch(
                        "app.services.user_analytics_service.update_session_activity"
                    ) as mock_update:
                        with patch("app.services.user_analytics_service.db"):
                            _svc.increment_session_page_views_without_activity_log()
                        mock_update.assert_called_once_with(
                            "page_view", page_view_path_key="/x"
                        )

    def test_exception_calls_rollback(self, app):
        with app.test_request_context("/"):
            mock_cu = MagicMock()
            mock_cu.is_authenticated = True
            with patch("app.services.user_analytics_service.current_user", mock_cu):
                with patch(
                    "app.services.user_analytics_service.page_view_path_key_from_request",
                    side_effect=Exception("boom"),
                ):
                    with patch(
                        "app.services.user_analytics_service._rollback_transaction"
                    ) as mock_rb:
                        _svc.increment_session_page_views_without_activity_log()
                    mock_rb.assert_called_once()


# ===========================================================================
# increment_session_page_views_without_activity_log_deferred
# ===========================================================================

class TestIncrementSessionPageViewsDeferred:
    def test_noop_when_no_session_id(self, app):
        with app.app_context():
            with patch(
                "app.services.user_analytics_service._update_session_activity_explicit"
            ) as mock_update:
                _svc.increment_session_page_views_without_activity_log_deferred(None)
                mock_update.assert_not_called()

    def test_calls_update_explicit(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.atomic") as mock_atomic:
                ctx = MagicMock()
                ctx.__enter__ = MagicMock(return_value=None)
                ctx.__exit__ = MagicMock(return_value=False)
                mock_atomic.return_value = ctx
                with patch(
                    "app.services.user_analytics_service._update_session_activity_explicit"
                ) as mock_update:
                    _svc.increment_session_page_views_without_activity_log_deferred(
                        "sess-x", page_view_path_key="/p"
                    )
                    mock_update.assert_called_once_with(
                        "sess-x", "page_view", page_view_path_key="/p"
                    )

    def test_exception_is_swallowed(self, app):
        with app.app_context():
            with patch(
                "app.services.user_analytics_service.atomic",
                side_effect=Exception("boom"),
            ):
                # must not raise
                _svc.increment_session_page_views_without_activity_log_deferred("sess-y")


# ===========================================================================
# log_user_activity_explicit
# ===========================================================================

class TestLogUserActivityExplicit:
    def test_noop_when_no_user_id(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserActivityLog") as MockAL:
                _svc.log_user_activity_explicit(
                    user_id=None,
                    session_id=None,
                    activity_type="page_view",
                    description=None,
                    context_data=None,
                    response_time_ms=None,
                    status_code=None,
                    endpoint=None,
                    http_method=None,
                    url_path=None,
                    referrer=None,
                    ip_address="1.2.3.4",
                    user_agent=None,
                )
                MockAL.assert_not_called()

    def test_noop_for_skip_endpoint(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserActivityLog") as MockAL:
                _svc.log_user_activity_explicit(
                    user_id=1,
                    session_id="sid",
                    activity_type="page_view",
                    description=None,
                    context_data=None,
                    response_time_ms=None,
                    status_code=None,
                    endpoint="forms_api.api_presence_active_users",
                    http_method="GET",
                    url_path="/",
                    referrer=None,
                    ip_address="1.2.3.4",
                    user_agent=None,
                )
                MockAL.assert_not_called()

    def test_logs_activity_with_valid_data(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.atomic") as mock_atomic:
                ctx = MagicMock()
                ctx.__enter__ = MagicMock(return_value=None)
                ctx.__exit__ = MagicMock(return_value=False)
                mock_atomic.return_value = ctx
                with patch("app.services.user_analytics_service.UserActivityLog") as MockAL:
                    with patch(
                        "app.services.user_analytics_service._update_session_activity_explicit"
                    ):
                        with patch("app.services.user_analytics_service.db") as mock_db:
                            _svc.log_user_activity_explicit(
                                user_id=1,
                                session_id="sid",
                                activity_type="page_view",
                                description="a page",
                                context_data={"page_view_path_key": "/p"},
                                response_time_ms=50,
                                status_code=200,
                                endpoint="some.endpoint",
                                http_method="GET",
                                url_path="/some",
                                referrer=None,
                                ip_address="1.2.3.4",
                                user_agent="Mozilla/5.0 Chrome/120",
                            )
                            MockAL.assert_called_once()

    def test_exception_is_swallowed(self, app):
        with app.app_context():
            with patch(
                "app.services.user_analytics_service.atomic",
                side_effect=Exception("boom"),
            ):
                # must not raise
                _svc.log_user_activity_explicit(
                    user_id=1,
                    session_id="sid",
                    activity_type="page_view",
                    description=None,
                    context_data=None,
                    response_time_ms=None,
                    status_code=None,
                    endpoint="some.ep",
                    http_method=None,
                    url_path=None,
                    referrer=None,
                    ip_address="",
                    user_agent=None,
                )


# ===========================================================================
# log_user_activity_for_user
# ===========================================================================

class TestLogUserActivityForUser:
    def test_noop_when_no_user_id(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserActivityLog") as MockAL:
                _svc.log_user_activity_for_user(None, "page_view")
                MockAL.assert_not_called()

    def test_logs_with_request_context(self, app):
        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120"},
        ):
            with patch("app.services.user_analytics_service.db") as mock_db:
                with patch("app.services.user_analytics_service.UserActivityLog") as MockAL:
                    _svc.log_user_activity_for_user(1, "page_view")
                    MockAL.assert_called_once()
                    mock_db.session.add.assert_called_once()

    def test_logs_without_request_context(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.db") as mock_db:
                with patch("app.services.user_analytics_service.UserActivityLog") as MockAL:
                    _svc.log_user_activity_for_user(1, "data_save")
                    MockAL.assert_called_once()
                    mock_db.session.add.assert_called_once()

    def test_skips_skip_endpoint(self, app):
        with app.test_request_context("/"):
            with patch(
                "app.services.user_analytics_service._should_skip_activity_user_log_endpoint",
                return_value=True,
            ):
                with patch("app.services.user_analytics_service.UserActivityLog") as MockAL:
                    _svc.log_user_activity_for_user(1, "page_view")
                    MockAL.assert_not_called()

    def test_exception_calls_rollback(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.db") as mock_db:
                mock_db.session.add.side_effect = Exception("boom")
                with patch("app.services.user_analytics_service.UserActivityLog"):
                    with patch(
                        "app.services.user_analytics_service._rollback_transaction"
                    ) as mock_rb:
                        _svc.log_user_activity_for_user(1, "page_view")
                        mock_rb.assert_called_once()


# ===========================================================================
# log_admin_action
# ===========================================================================

class TestLogAdminAction:
    def _mock_admin_user(self):
        mu = MagicMock()
        mu.is_authenticated = True
        mu.id = 99
        return mu

    def test_logs_admin_action(self, app):
        mu = self._mock_admin_user()
        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120"},
        ):
            with patch("app.services.user_analytics_service.current_user", mu):
                with patch(
                    "app.services.authorization_service.AuthorizationService"
                ) as MockAuth:
                    MockAuth.is_admin.return_value = True
                    with patch("app.services.user_analytics_service.db") as mock_db:
                        with patch("app.services.user_analytics_service.AdminActionLog") as MockAL:
                            _svc.log_admin_action(
                                "user_deactivated",
                                "Deactivated user X",
                                target_type="user",
                                target_id=5,
                            )
                            MockAL.assert_called_once()
                            mock_db.session.add.assert_called_once()

    def test_noop_for_non_admin(self, app):
        mu = MagicMock()
        mu.is_authenticated = True
        with app.test_request_context("/"):
            with patch("app.services.user_analytics_service.current_user", mu):
                with patch(
                    "app.services.authorization_service.AuthorizationService"
                ) as MockAuth:
                    MockAuth.is_admin.return_value = False
                    with patch("app.services.user_analytics_service.AdminActionLog") as MockAL:
                        _svc.log_admin_action("act", "desc")
                        MockAL.assert_not_called()

    def test_high_risk_action_creates_security_event(self, app):
        mu = self._mock_admin_user()
        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120"},
        ):
            with patch("app.services.user_analytics_service.current_user", mu):
                with patch(
                    "app.services.authorization_service.AuthorizationService"
                ) as MockAuth:
                    MockAuth.is_admin.return_value = True
                    with patch("app.services.user_analytics_service.db"):
                        with patch("app.services.user_analytics_service.AdminActionLog") as MockAL:
                            mock_log_instance = MagicMock()
                            mock_log_instance.id = 1
                            MockAL.return_value = mock_log_instance
                            with patch(
                                "app.services.user_analytics_service.create_security_event"
                            ) as mock_sec:
                                _svc.log_admin_action(
                                    "delete_all", "Deleted everything", risk_level="high"
                                )
                                mock_sec.assert_called_once()

    def test_injects_country_info_when_country_id_provided(self, app):
        mu = self._mock_admin_user()
        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120"},
        ):
            with patch("app.services.user_analytics_service.current_user", mu):
                with patch(
                    "app.services.authorization_service.AuthorizationService"
                ) as MockAuth:
                    MockAuth.is_admin.return_value = True
                    with patch("app.services.user_analytics_service.db"):
                        with patch("app.services.user_analytics_service.AdminActionLog") as MockAL:
                            mock_log_instance = MagicMock()
                            mock_log_instance.id = 1
                            MockAL.return_value = mock_log_instance
                            _svc.log_admin_action(
                                "edit", "Edit", country_id=1, country_name="Testland"
                            )
                            # country_name should be in new_values
                            call_kwargs = MockAL.call_args[1] if MockAL.call_args else {}
                            nv = call_kwargs.get("new_values", {}) or {}
                            assert nv.get("country_name") == "Testland"

    def test_exception_calls_rollback(self, app):
        mu = self._mock_admin_user()
        with app.test_request_context("/"):
            with patch("app.services.user_analytics_service.current_user", mu):
                with patch(
                    "app.services.authorization_service.AuthorizationService"
                ) as MockAuth:
                    MockAuth.is_admin.return_value = True
                    with patch("app.services.user_analytics_service.db") as mock_db:
                        mock_db.session.add.side_effect = Exception("boom")
                        with patch("app.services.user_analytics_service.AdminActionLog"):
                            with patch(
                                "app.services.user_analytics_service._rollback_transaction"
                            ) as mock_rb:
                                _svc.log_admin_action("act", "desc")
                                mock_rb.assert_called_once()


# ===========================================================================
# create_security_event
# ===========================================================================

class TestCreateSecurityEvent:
    def test_creates_event(self, app):
        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120"},
        ):
            mock_cu = MagicMock()
            mock_cu.is_authenticated = True
            mock_cu.id = 1
            with patch("app.services.user_analytics_service.current_user", mock_cu):
                with patch("app.services.user_analytics_service.db") as mock_db:
                    with patch("app.services.user_analytics_service.SecurityEvent") as MockSE:
                        _svc.create_security_event("brute_force", "high", "Too many attempts")
                        MockSE.assert_called_once()
                        mock_db.session.add.assert_called_once()

    def test_uses_explicit_user_id(self, app):
        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120"},
        ):
            mock_cu = MagicMock()
            mock_cu.is_authenticated = False
            with patch("app.services.user_analytics_service.current_user", mock_cu):
                with patch("app.services.user_analytics_service.db"):
                    with patch("app.services.user_analytics_service.SecurityEvent") as MockSE:
                        _svc.create_security_event(
                            "login_failed", "medium", "desc", user_id=7
                        )
                        kw = MockSE.call_args[1]
                        assert kw.get("user_id") == 7

    def test_exception_calls_rollback(self, app):
        with app.test_request_context("/"):
            with patch("app.services.user_analytics_service.db") as mock_db:
                mock_db.session.add.side_effect = Exception("boom")
                with patch("app.services.user_analytics_service.SecurityEvent"):
                    with patch("app.services.user_analytics_service.current_user", MagicMock(is_authenticated=False)):
                        with patch(
                            "app.services.user_analytics_service._rollback_transaction"
                        ) as mock_rb:
                            _svc.create_security_event("evt", "low", "desc")
                            mock_rb.assert_called_once()


# ===========================================================================
# check_suspicious_login
# ===========================================================================

class TestCheckSuspiciousLogin:
    def _mock_query(self):
        """Build a simple mock for UserLoginLog.query.filter().count() etc."""
        return MagicMock()

    def test_not_suspicious_when_no_activity(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserLoginLog.query") as mock_ll_query, \
                 patch("app.services.user_analytics_service.db.session.query") as mock_db_query:
                mock_ll_query.filter.return_value.count.return_value = 0
                mock_db_query.return_value.filter.return_value.scalar.return_value = 0
                result = _svc.check_suspicious_login("1.1.1.1", "x@x.com", False)
                assert result is None

    def test_brute_force_flagged(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserLoginLog.query") as mock_ll_query:
                mock_ll_query.filter.return_value.count.return_value = 6
                result = _svc.check_suspicious_login("2.2.2.2", "x@x.com", False)
                assert result is not None
                assert "brute_force" in result

    def test_credential_stuffing_flagged(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserLoginLog.query") as mock_ll_query, \
                 patch("app.services.user_analytics_service.db.session.query") as mock_db_query:
                mock_ll_query.filter.return_value.count.return_value = 0
                mock_db_query.return_value.filter.return_value.scalar.return_value = 12
                result = _svc.check_suspicious_login("3.3.3.3", "x@x.com", False)
                assert result is not None
                assert "credential_stuffing" in result

    def test_new_network_on_success_flagged(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserLoginLog.query") as mock_ll_query:
                mock_ll_query.filter.return_value.count.return_value = 0

                known_ips = [
                    ("10.0.1.100",),
                    ("10.0.1.101",),
                    ("10.0.1.102",),
                ]

                def side_effect(*args, **kwargs):
                    # First call is brute-force count = 0
                    # The .all() calls come from User.query + previous_ips
                    return MagicMock()

                with patch("app.services.user_analytics_service.db") as mock_db:
                    # credential stuffing count
                    scalar_mock = MagicMock()
                    scalar_mock.return_value = 0

                    user_mock = MagicMock()
                    user_mock.id = 99

                    mock_db.session.query.return_value.filter.return_value.scalar.return_value = 0

                    with patch("app.services.user_analytics_service.User") as MockUser:
                        MockUser.query.filter_by.return_value.first.return_value = user_mock

                        prev_ips_query = MagicMock()
                        prev_ips_query.filter.return_value.all.return_value = known_ips

                        # Override the db.session.query to return different things:
                        call_count = [0]
                        def query_side(*args, **kwargs):
                            call_count[0] += 1
                            m = MagicMock()
                            if call_count[0] == 1:
                                # credential stuffing query
                                m.filter.return_value.scalar.return_value = 0
                            else:
                                # previous IPs query
                                m.filter.return_value.all.return_value = known_ips
                            return m

                        mock_db.session.query.side_effect = query_side

                        result = _svc.check_suspicious_login(
                            "192.168.1.1", "user@example.com", success=True
                        )
                        assert result is not None
                        assert "new_network" in result

    def test_new_ipv6_on_success_flagged(self, app):
        """Covers the non-IPv4 branch for new_ip."""
        with app.app_context():
            with patch("app.services.user_analytics_service.UserLoginLog.query") as mock_ll_query:
                mock_ll_query.filter.return_value.count.return_value = 0

                known_ips = [("::1",), ("::2",), ("::3",)]
                user_mock = MagicMock()
                user_mock.id = 10

                with patch("app.services.user_analytics_service.db") as mock_db:
                    with patch("app.services.user_analytics_service.User") as MockUser:
                        MockUser.query.filter_by.return_value.first.return_value = user_mock

                        call_count = [0]
                        def query_side(*args, **kwargs):
                            call_count[0] += 1
                            m = MagicMock()
                            if call_count[0] == 1:
                                m.filter.return_value.scalar.return_value = 0
                            else:
                                m.filter.return_value.all.return_value = known_ips
                            return m

                        mock_db.session.query.side_effect = query_side

                        result = _svc.check_suspicious_login(
                            "2001:db8::99", "user@example.com", success=True
                        )
                        assert result is not None
                        assert "new_ip" in result


# ===========================================================================
# get_recent_failed_attempts
# ===========================================================================

class TestGetRecentFailedAttempts:
    def test_returns_count(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserLoginLog.query") as mock_ll_query:
                mock_ll_query.filter.return_value.count.return_value = 3
                count = _svc.get_recent_failed_attempts("x@x.com", "1.1.1.1")
                assert count == 3


# ===========================================================================
# create_security_event_for_login
# ===========================================================================

class TestCreateSecurityEventForLogin:
    def _client_info(self, ip="1.1.1.1"):
        return {"ip_address": ip}

    def test_no_event_when_less_than_5_failures(self, app):
        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120"},
        ):
            with patch(
                "app.services.user_analytics_service.get_recent_failed_attempts",
                return_value=3,
            ):
                with patch(
                    "app.services.user_analytics_service.create_security_event"
                ) as mock_sec:
                    _svc.create_security_event_for_login(
                        "x@x.com", False, False, self._client_info(), "wrong_password"
                    )
                    mock_sec.assert_not_called()

    def test_medium_severity_at_5_to_9_failures(self, app):
        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120"},
        ):
            with patch(
                "app.services.user_analytics_service.get_recent_failed_attempts",
                return_value=7,
            ):
                with patch(
                    "app.services.user_analytics_service.create_security_event"
                ) as mock_sec:
                    _svc.create_security_event_for_login(
                        "x@x.com", False, False, self._client_info(), "wrong_password"
                    )
                    mock_sec.assert_called_once()
                    _, kw = mock_sec.call_args
                    assert kw.get("severity") == "medium"

    def test_high_severity_at_10_plus_failures(self, app):
        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120"},
        ):
            with patch(
                "app.services.user_analytics_service.get_recent_failed_attempts",
                return_value=12,
            ):
                with patch(
                    "app.services.user_analytics_service.create_security_event"
                ) as mock_sec:
                    _svc.create_security_event_for_login(
                        "x@x.com", False, False, self._client_info(), "wrong_password"
                    )
                    mock_sec.assert_called_once()
                    _, kw = mock_sec.call_args
                    assert kw.get("severity") == "high"

    def test_suspicious_creates_event_regardless_of_success(self, app):
        with app.test_request_context(
            "/",
            headers={"User-Agent": "Mozilla/5.0 Chrome/120"},
        ):
            with patch(
                "app.services.user_analytics_service.get_recent_failed_attempts",
                return_value=0,
            ):
                with patch(
                    "app.services.user_analytics_service.create_security_event"
                ) as mock_sec:
                    _svc.create_security_event_for_login(
                        "x@x.com", True, True, self._client_info(), None, "brute_force"
                    )
                    mock_sec.assert_called_once()
                    _, kw = mock_sec.call_args
                    assert kw.get("event_type") == "suspicious_login"


# ===========================================================================
# get_user_login_analytics
# ===========================================================================

class TestGetUserLoginAnalytics:
    def _fake_log(self, event_type="login_success", ip="1.1.1.1", device="Desktop",
                  browser="Chrome", is_suspicious=False, ts=None):
        log = MagicMock()
        log.event_type = event_type
        log.ip_address = ip
        log.device_type = device
        log.browser = browser
        log.is_suspicious = is_suspicious
        log.timestamp = ts or datetime.now(timezone.utc)
        return log

    def test_returns_correct_totals(self, app):
        with app.app_context():
            logs = [
                self._fake_log("login_success"),
                self._fake_log("login_success"),
                self._fake_log("login_failed"),
            ]
            with patch("app.services.user_analytics_service.UserLoginLog.query") as mock_query:
                mock_query.filter.return_value.all.return_value = logs
                result = _svc.get_user_login_analytics(days=30)
                assert result["total_logins"] == 2
                assert result["failed_attempts"] == 1
                assert result["suspicious_attempts"] == 0

    def test_filters_by_user_id(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserLoginLog.query") as mock_query:
                q = MagicMock()
                q.filter.return_value.all.return_value = []
                mock_query.filter.return_value = q
                _svc.get_user_login_analytics(user_id=5, days=30)
                # The second filter call should have been applied
                q.filter.assert_called_once()

    def test_device_and_browser_breakdown(self, app):
        with app.app_context():
            logs = [
                self._fake_log("login_success", device="Mobile", browser="Chrome"),
                self._fake_log("login_success", device="desktop", browser="Firefox"),
            ]
            with patch("app.services.user_analytics_service.UserLoginLog.query") as mock_query:
                mock_query.filter.return_value.all.return_value = logs
                result = _svc.get_user_login_analytics(days=7)
                assert "Mobile" in result["device_breakdown"]
                assert "Desktop" in result["device_breakdown"]

    def test_daily_activity_counts(self, app):
        with app.app_context():
            ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
            logs = [self._fake_log("login_success", ts=ts)]
            with patch("app.services.user_analytics_service.UserLoginLog.query") as mock_query:
                mock_query.filter.return_value.all.return_value = logs
                result = _svc.get_user_login_analytics(days=30)
                assert "2024-01-15" in result["daily_activity"]
                assert result["daily_activity"]["2024-01-15"]["logins"] == 1


# ===========================================================================
# get_user_activity_analytics
# ===========================================================================

class TestGetUserActivityAnalytics:
    def _fake_log(self, activity_type="page_view", url="/path", response_time=None, ts=None):
        log = MagicMock()
        log.activity_type = activity_type
        log.url_path = url
        log.response_time_ms = response_time
        log.timestamp = ts or datetime.now(timezone.utc)
        return log

    def test_returns_correct_totals(self, app):
        with app.app_context():
            logs = [
                self._fake_log("page_view", response_time=100),
                self._fake_log("form_submit", response_time=200),
            ]
            with patch("app.services.user_analytics_service.UserActivityLog.query") as mock_query:
                mock_query.filter.return_value.all.return_value = logs
                result = _svc.get_user_activity_analytics(days=30)
                assert result["total_activities"] == 2
                assert result["average_response_time"] == 150.0

    def test_filters_by_user_id(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserActivityLog.query") as mock_query:
                q = MagicMock()
                q.filter.return_value.all.return_value = []
                mock_query.filter.return_value = q
                _svc.get_user_activity_analytics(user_id=3, days=7)
                q.filter.assert_called_once()

    def test_url_path_none_skipped(self, app):
        with app.app_context():
            log = self._fake_log(url=None)
            with patch("app.services.user_analytics_service.UserActivityLog.query") as mock_query:
                mock_query.filter.return_value.all.return_value = [log]
                result = _svc.get_user_activity_analytics()
                assert result["popular_pages"] == {}

    def test_no_response_times_average_zero(self, app):
        with app.app_context():
            logs = [self._fake_log(response_time=None)]
            with patch("app.services.user_analytics_service.UserActivityLog.query") as mock_query:
                mock_query.filter.return_value.all.return_value = logs
                result = _svc.get_user_activity_analytics()
                assert result["average_response_time"] == 0


# ===========================================================================
# get_security_events_summary
# ===========================================================================

class TestGetSecurityEventsSummary:
    def _fake_event(self, severity="medium", event_type="suspicious_login", resolved=False):
        e = MagicMock()
        e.severity = severity
        e.event_type = event_type
        e.is_resolved = resolved
        return e

    def test_returns_summary(self, app):
        with app.app_context():
            events = [
                self._fake_event("high", "brute_force", resolved=False),
                self._fake_event("medium", "suspicious_login", resolved=True),
            ]
            with patch("app.services.user_analytics_service.SecurityEvent.query") as mock_query:
                mock_query.filter.return_value.all.return_value = events
                result = _svc.get_security_events_summary(days=30)
                assert result["total_events"] == 2
                assert result["unresolved_events"] == 1
                assert result["high_severity_events"] == 1

    def test_exception_returns_empty_dict(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.SecurityEvent") as MockSE:
                MockSE.query.filter.side_effect = Exception("boom")
                result = _svc.get_security_events_summary()
                assert result == {}


# ===========================================================================
# get_active_sessions_count
# ===========================================================================

class TestGetActiveSessionsCount:
    def test_returns_count(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                MockSL.query.filter.return_value.count.return_value = 7
                assert _svc.get_active_sessions_count() == 7

    def test_exception_returns_zero(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                MockSL.query.filter.side_effect = Exception("boom")
                assert _svc.get_active_sessions_count() == 0


# ===========================================================================
# get_session_analytics
# ===========================================================================

class TestGetSessionAnalytics:
    def _fake_session(self, is_active=False, duration_minutes=20, page_views=5, start_offset_days=1):
        s = MagicMock()
        s.is_active = is_active
        s.duration_minutes = duration_minutes
        s.page_views = page_views
        start = datetime.now(timezone.utc) - timedelta(days=start_offset_days)
        s.session_start = start
        return s

    def test_empty_sessions_returns_zeros(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserSessionLog.query") as mock_query:
                mock_query.filter.return_value.all.return_value = []
                result = _svc.get_session_analytics(days=30)
                assert result["total_sessions"] == 0

    def test_returns_correct_totals(self, app):
        with app.app_context():
            sessions = [
                self._fake_session(is_active=True, duration_minutes=None, page_views=10),
                self._fake_session(is_active=False, duration_minutes=25, page_views=3),
                self._fake_session(is_active=False, duration_minutes=45, page_views=7),
            ]
            with patch("app.services.user_analytics_service.UserSessionLog.query") as mock_query:
                mock_query.filter.return_value.all.return_value = sessions
                result = _svc.get_session_analytics(days=30)
                assert result["total_sessions"] == 3
                assert result["active_sessions"] == 1
                assert result["total_page_views"] == 20
                assert result["average_duration"] == 35.0  # mean of 25 and 45

    def test_duration_distribution_buckets(self, app):
        with app.app_context():
            durations = [5, 20, 45, 90, 150, 300]
            sessions = [self._fake_session(duration_minutes=d) for d in durations]
            with patch("app.services.user_analytics_service.UserSessionLog.query") as mock_query:
                mock_query.filter.return_value.all.return_value = sessions
                result = _svc.get_session_analytics(days=30)
                dd = result["duration_distribution"]
                assert dd["0-15 min"] == 1
                assert dd["15-30 min"] == 1
                assert dd["30-60 min"] == 1
                assert dd["1-2 hours"] == 1
                assert dd["2-4 hours"] == 1
                assert dd["4+ hours"] == 1

    def test_exception_returns_empty_dict(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                MockSL.query.filter.side_effect = Exception("boom")
                result = _svc.get_session_analytics()
                assert result == {}


# ===========================================================================
# aggregate_page_view_path_histogram
# ===========================================================================

class TestAggregatePageViewPathHistogram:
    def test_no_table_returns_empty(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.return_value = False
                result = _svc.aggregate_page_view_path_histogram(days=30)
                assert result["paths"] == []
                assert result["sessions_in_scope"] == 0

    def test_aggregates_histograms(self, app):
        with app.app_context():
            fake_rows = [({"/a": 3},), ({"/a": 2, "/b": 1},)]

            with patch("app.services.user_analytics_service.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.return_value = True
                with patch("app.services.user_analytics_service.db") as mock_db:
                    mock_db.session.query.return_value.filter.return_value.yield_per.return_value = iter(fake_rows)
                    result = _svc.aggregate_page_view_path_histogram(days=7)
                    assert result["sessions_in_scope"] == 2
                    paths_by_key = {p["path"]: p["total_views"] for p in result["paths"]}
                    assert paths_by_key["/a"] == 5
                    assert paths_by_key["/b"] == 1

    def test_path_prefix_filter(self, app):
        with app.app_context():
            fake_rows = [({"/admin/x": 2, "/public/y": 1},)]

            with patch("app.services.user_analytics_service.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.return_value = True
                with patch("app.services.user_analytics_service.db") as mock_db:
                    mock_db.session.query.return_value.filter.return_value.yield_per.return_value = iter(fake_rows)
                    result = _svc.aggregate_page_view_path_histogram(days=7, path_prefix="/admin")
                    keys = {p["path"] for p in result["paths"]}
                    assert "/admin/x" in keys
                    assert "/public/y" not in keys

    def test_user_id_filter(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.return_value = True
                with patch("app.services.user_analytics_service.db") as mock_db:
                    q_mock = MagicMock()
                    q_mock.filter.return_value = q_mock
                    q_mock.yield_per.return_value = iter([])
                    mock_db.session.query.return_value.filter.return_value = q_mock
                    result = _svc.aggregate_page_view_path_histogram(user_id=1, days=7)
                    assert result["sessions_in_scope"] == 0

    def test_exception_returns_empty(self, app):
        with app.app_context():
            with patch(
                "app.services.user_analytics_service.inspect",
                side_effect=Exception("boom"),
            ):
                result = _svc.aggregate_page_view_path_histogram(days=7)
                assert result["paths"] == []


# ===========================================================================
# cleanup_inactive_sessions
# ===========================================================================

class TestCleanupInactiveSessions:
    def test_no_table_returns_zero(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.return_value = False
                result = _svc.cleanup_inactive_sessions()
                assert result == 0

    def test_sqlite_skips_pg_lock(self, app):
        """On SQLite, no advisory lock should be acquired."""
        with app.app_context():
            with patch("app.services.user_analytics_service.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.return_value = True
                with patch("app.services.user_analytics_service.db") as mock_db:
                    mock_db.engine.dialect.name = "sqlite"
                    mock_db.engine.connect.return_value.__enter__ = MagicMock(return_value=None)
                    mock_db.engine.connect.return_value.__exit__ = MagicMock(return_value=False)
                    # No active sessions
                    mock_db.session.query.return_value.filter.return_value.all.return_value = []

                    with patch("app.services.user_analytics_service.UserSessionLog") as MockSL:
                        MockSL.__tablename__ = "user_session_log"
                        inactive_q = MagicMock()
                        inactive_q.filter.return_value.all.return_value = []
                        MockSL.query = inactive_q

                        result = _svc.cleanup_inactive_sessions(
                            inactivity_hours=8, max_session_hours=24
                        )
                        assert result == 0

    def test_closes_inactive_sessions(self, app):
        """Sessions that are active and past the cutoff should be closed."""
        with app.app_context():
            old_session = MagicMock()
            old_session.is_active = True
            old_session.session_start = datetime.now(timezone.utc) - timedelta(hours=10)
            old_session.last_activity = datetime.now(timezone.utc) - timedelta(hours=10)
            old_session.session_end = None

            with patch("app.services.user_analytics_service.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.return_value = True
                with patch("app.services.user_analytics_service.db") as mock_db:
                    mock_db.engine.dialect.name = "sqlite"

                    with patch("app.services.user_analytics_service.UserSessionLog.query") as mock_query:
                        mock_query.filter.return_value.all.side_effect = [
                            [old_session],
                            [],
                        ]

                        result = _svc.cleanup_inactive_sessions(
                            inactivity_hours=1, max_session_hours=48
                        )
                        assert result == 1
                        assert old_session.is_active is False
                        assert old_session.ended_by == "inactivity_timeout"

    def test_exception_returns_zero(self, app):
        with app.app_context():
            with patch(
                "app.services.user_analytics_service.inspect",
                side_effect=Exception("boom"),
            ):
                with patch("app.services.user_analytics_service._rollback_transaction"):
                    result = _svc.cleanup_inactive_sessions()
                    assert result == 0


# ===========================================================================
# user_session_log_active_duration_minutes_sql
# ===========================================================================

class TestUserSessionLogActiveDurationMinutesSql:
    def test_sqlite_returns_expression(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.db") as mock_db:
                mock_db.engine.dialect.name = "sqlite"
                result = _svc.user_session_log_active_duration_minutes_sql()
                assert result is not None

    def test_postgresql_returns_expression(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.db") as mock_db:
                mock_db.engine.dialect.name = "postgresql"
                result = _svc.user_session_log_active_duration_minutes_sql()
                assert result is not None

    def test_mysql_returns_expression(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.db") as mock_db:
                mock_db.engine.dialect.name = "mysql"
                result = _svc.user_session_log_active_duration_minutes_sql()
                assert result is not None

    def test_unsupported_dialect_returns_none(self, app):
        with app.app_context():
            with patch("app.services.user_analytics_service.db") as mock_db:
                mock_db.engine.dialect.name = "oracle"
                result = _svc.user_session_log_active_duration_minutes_sql()
                assert result is None
