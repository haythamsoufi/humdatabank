"""Tests for session_timeout.py — targeting 100% coverage."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest
from flask import session

from app.middleware.session_timeout import (
    check_session_timeout,
    handle_session_timeout,
    register_session_timeout_middleware,
)


# ────────────────────────────────────────────────────────────────────────────
# Config assertions — ensure the values that control session length are set
# correctly and don't silently revert to longer defaults.
# ────────────────────────────────────────────────────────────────────────────

class TestSessionConfig:
    """Guard against accidental config regressions for session lifetimes."""

    def test_permanent_session_lifetime_is_ten_hours(self):
        """PERMANENT_SESSION_LIFETIME must be 10 h (not the old 7-day default)."""
        from config import Config
        assert Config.PERMANENT_SESSION_LIFETIME == timedelta(hours=10), (
            "PERMANENT_SESSION_LIFETIME was changed away from 10 hours. "
            "Update this test only if you intentionally changed the lifetime."
        )

    def test_inactivity_timeout_default_is_two_hours(self):
        """Default SESSION_INACTIVITY_TIMEOUT must be 2 hours."""
        from config import Config
        assert Config.SESSION_INACTIVITY_TIMEOUT == timedelta(hours=2)

    def test_permanent_session_lifetime_propagated_to_flask_app(self, app):
        """The Flask app config must carry the 10-hour lifetime from Config."""
        assert app.config['PERMANENT_SESSION_LIFETIME'] == timedelta(hours=10)


# ────────────────────────────────────────────────────────────────────────────
# check_session_timeout
# ────────────────────────────────────────────────────────────────────────────

class TestCheckSessionTimeout:
    def test_unauthenticated_user_returns_false(self, app):
        with app.test_request_context("/dashboard"):
            with patch("app.middleware.session_timeout.current_user") as mock_user:
                mock_user.is_authenticated = False
                assert check_session_timeout() is False

    def test_no_last_activity_returns_false(self, app):
        with app.test_request_context("/dashboard"):
            with patch("app.middleware.session_timeout.current_user") as mock_user:
                mock_user.is_authenticated = True
                with app.test_client() as c:
                    with c.session_transaction() as sess:
                        # No 'last_activity' key
                        pass
                    # Simulate request context with empty session
                    result = check_session_timeout()
                    assert result is False

    def test_recent_activity_returns_false(self, app):
        with app.test_request_context("/dashboard"):
            with patch("app.middleware.session_timeout.current_user") as mock_user, \
                 patch("app.middleware.session_timeout.session",
                       {"last_activity": datetime.now(timezone.utc).isoformat()}):
                mock_user.is_authenticated = True
                result = check_session_timeout()
                assert result is False

    def test_expired_activity_returns_true(self, app):
        old_time = datetime.now(timezone.utc) - timedelta(hours=10)
        with app.test_request_context("/dashboard"):
            with patch("app.middleware.session_timeout.current_user") as mock_user, \
                 patch("app.middleware.session_timeout.session",
                       {"last_activity": old_time.isoformat()}):
                mock_user.is_authenticated = True
                result = check_session_timeout()
                assert result is True

    def test_naive_datetime_normalized_to_utc(self, app):
        """Naive datetime strings (no timezone) are treated as UTC."""
        old_time = datetime.utcnow() - timedelta(hours=12)
        naive_iso = old_time.isoformat()  # no tzinfo
        with app.test_request_context("/dashboard"):
            with patch("app.middleware.session_timeout.current_user") as mock_user, \
                 patch("app.middleware.session_timeout.session",
                       {"last_activity": naive_iso}):
                mock_user.is_authenticated = True
                result = check_session_timeout()
                assert result is True

    def test_invalid_last_activity_value_returns_false(self, app):
        """ValueError/KeyError during fromisoformat parsing is suppressed."""
        with app.test_request_context("/dashboard"):
            with patch("app.middleware.session_timeout.current_user") as mock_user, \
                 patch("app.middleware.session_timeout.session",
                       {"last_activity": "not-a-valid-datetime"}):
                mock_user.is_authenticated = True
                # suppress() should eat the ValueError
                result = check_session_timeout()
                assert result is False


# ────────────────────────────────────────────────────────────────────────────
# handle_session_timeout
# ────────────────────────────────────────────────────────────────────────────

class TestHandleSessionTimeout:
    def test_static_asset_returns_none(self, app):
        with app.test_request_context("/static/file.css"):
            with patch("app.middleware.session_timeout.is_static_asset_request",
                       return_value=True):
                result = handle_session_timeout()
                assert result is None

    def test_api_v1_returns_none(self, app):
        with app.test_request_context("/api/v1/users"):
            result = handle_session_timeout()
            assert result is None

    def test_api_mobile_returns_none(self, app):
        with app.test_request_context("/api/mobile/v1/data"):
            result = handle_session_timeout()
            assert result is None

    def test_login_path_returns_none(self, app):
        with app.test_request_context("/login"):
            result = handle_session_timeout()
            assert result is None

    def test_auth_prefix_returns_none(self, app):
        with app.test_request_context("/auth/login/azure"):
            result = handle_session_timeout()
            assert result is None

    def test_register_path_returns_none(self, app):
        with app.test_request_context("/register"):
            result = handle_session_timeout()
            assert result is None

    def test_forgot_password_path_returns_none(self, app):
        with app.test_request_context("/forgot-password"):
            result = handle_session_timeout()
            assert result is None

    def test_reset_password_path_returns_none(self, app):
        with app.test_request_context("/reset-password/abc123"):
            result = handle_session_timeout()
            assert result is None

    def test_blacklisted_session_redirects_to_login(self, app):
        with app.test_request_context("/dashboard"):
            with patch("app.middleware.session_timeout.is_static_asset_request",
                       return_value=False), \
                 patch("app.middleware.session_timeout.is_session_blacklisted",
                       return_value=True), \
                 patch("app.middleware.session_timeout.logout_user") as mock_logout, \
                 patch("app.middleware.session_timeout.remove_session_from_blacklist") as mock_remove, \
                 patch("app.middleware.session_timeout.session",
                       {"session_id": "blacklisted-sid"}), \
                 patch("app.middleware.session_timeout.is_json_request", return_value=False):
                result = handle_session_timeout()
                mock_logout.assert_called_once()
                mock_remove.assert_called_once_with("blacklisted-sid")
                assert result is not None  # redirect
                assert result.status_code == 302

    def test_blacklisted_session_json_returns_401(self, app):
        with app.test_request_context(
            "/admin/api/refresh-csrf-token",
            headers={"X-Requested-With": "XMLHttpRequest"},
        ):
            with patch("app.middleware.session_timeout.is_static_asset_request",
                       return_value=False), \
                 patch("app.middleware.session_timeout.is_session_blacklisted",
                       return_value=True), \
                 patch("app.middleware.session_timeout.logout_user") as mock_logout, \
                 patch("app.middleware.session_timeout.remove_session_from_blacklist") as mock_remove, \
                 patch("app.middleware.session_timeout.session",
                       {"session_id": "blacklisted-sid"}), \
                 patch("app.middleware.session_timeout.is_json_request", return_value=True):
                result = handle_session_timeout()
                mock_logout.assert_called_once()
                assert result is not None
                assert result.status_code == 401

    def test_timed_out_session_redirects_to_login(self, app):
        with app.test_request_context("/dashboard"):
            with patch("app.middleware.session_timeout.is_static_asset_request",
                       return_value=False), \
                 patch("app.middleware.session_timeout.is_session_blacklisted",
                       return_value=False), \
                 patch("app.middleware.session_timeout.check_session_timeout",
                       return_value=True), \
                 patch("app.middleware.session_timeout.end_user_session") as mock_end, \
                 patch("app.middleware.session_timeout.logout_user") as mock_logout, \
                 patch("app.middleware.session_timeout.remove_session_from_blacklist") as mock_remove, \
                 patch("app.middleware.session_timeout.session",
                       {"session_id": "expired-sid"}), \
                 patch("app.middleware.session_timeout.is_json_request", return_value=False):
                result = handle_session_timeout()
                mock_end.assert_called_once_with("expired-sid", "timeout")
                mock_logout.assert_called_once()
                mock_remove.assert_called_once_with("expired-sid")
                assert result is not None
                assert result.status_code == 302

    def test_timed_out_session_json_returns_401(self, app):
        with app.test_request_context(
            "/admin/api/refresh-csrf-token",
            headers={"X-Requested-With": "XMLHttpRequest"},
        ):
            with patch("app.middleware.session_timeout.is_static_asset_request",
                       return_value=False), \
                 patch("app.middleware.session_timeout.is_session_blacklisted",
                       return_value=False), \
                 patch("app.middleware.session_timeout.check_session_timeout",
                       return_value=True), \
                 patch("app.middleware.session_timeout.end_user_session") as mock_end, \
                 patch("app.middleware.session_timeout.logout_user") as mock_logout, \
                 patch("app.middleware.session_timeout.remove_session_from_blacklist") as mock_remove, \
                 patch("app.middleware.session_timeout.session",
                       {"session_id": "expired-sid"}), \
                 patch("app.middleware.session_timeout.is_json_request", return_value=True):
                result = handle_session_timeout()
                mock_end.assert_called_once_with("expired-sid", "timeout")
                mock_logout.assert_called_once()
                assert result is not None
                assert result.status_code == 401

    def test_active_session_returns_none(self, app):
        with app.test_request_context("/dashboard"):
            with patch("app.middleware.session_timeout.is_static_asset_request",
                       return_value=False), \
                 patch("app.middleware.session_timeout.is_session_blacklisted",
                       return_value=False), \
                 patch("app.middleware.session_timeout.check_session_timeout",
                       return_value=False):
                result = handle_session_timeout()
                assert result is None

    def test_no_session_id_blacklist_check_uses_none(self, app):
        """session.get('session_id') returns None when key absent — no crash."""
        with app.test_request_context("/dashboard"):
            with patch("app.middleware.session_timeout.is_static_asset_request",
                       return_value=False), \
                 patch("app.middleware.session_timeout.is_session_blacklisted",
                       return_value=False) as mock_bl, \
                 patch("app.middleware.session_timeout.check_session_timeout",
                       return_value=False), \
                 patch("app.middleware.session_timeout.session", {}):
                result = handle_session_timeout()
                mock_bl.assert_called_once_with(None)
                assert result is None


# ────────────────────────────────────────────────────────────────────────────
# register_session_timeout_middleware
# ────────────────────────────────────────────────────────────────────────────

class TestRegisterSessionTimeoutMiddleware:
    def test_registers_before_request(self):
        mock_app = MagicMock()
        register_session_timeout_middleware(mock_app)
        mock_app.before_request.assert_called_once()
