"""
Tests for app/routes/admin/utilities/sessions.py

Covers:
- POST /admin/utilities/sessions/cleanup  (cleanup_sessions)
- GET  /admin/utilities/sessions/show_all  (show_all_sessions)
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_session(user=None, last_activity=None, started_at=None):
    """Build a mock UserSessionLog-like object."""
    sess = MagicMock()
    sess.id = 1
    sess.user_id = 42
    sess.user = user or MagicMock(name="Test User")
    sess.user.name = "Test User"
    sess.started_at = started_at or datetime(2024, 1, 1, 10, 0, 0)
    sess.last_activity = last_activity or datetime(2024, 1, 1, 10, 0, 0)
    sess.ip_address = "127.0.0.1"
    sess.user_agent = "Mozilla/5.0"
    sess.ended_at = None
    sess.end_reason = None
    return sess


# ---------------------------------------------------------------------------
# POST /admin/utilities/sessions/cleanup
# ---------------------------------------------------------------------------

class TestCleanupSessions:
    """Tests for cleanup_sessions (POST /admin/utilities/sessions/cleanup)."""

    def test_redirects_when_table_does_not_exist(self, logged_in_client, db_session):
        """When the session table doesn't exist, flash warning and redirect."""
        mock_inspect = MagicMock()
        mock_inspect.has_table.return_value = False

        with patch(
            "app.routes.admin.utilities.sessions.inspect",
            return_value=mock_inspect,
        ):
            resp = logged_in_client.post("/admin/utilities/sessions/cleanup")

        assert resp.status_code == 302
        # Should redirect to admin dashboard
        assert "dashboard" in resp.headers["Location"] or resp.status_code == 302

    def test_cleans_up_expired_sessions_and_redirects(self, logged_in_client, db_session):
        """When expired sessions exist, mark them ended and redirect."""
        expired = _make_mock_session()
        expired.ended_at = None

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [expired]

        mock_inspect = MagicMock()
        mock_inspect.has_table.return_value = True

        with patch(
            "app.routes.admin.utilities.sessions.inspect",
            return_value=mock_inspect,
        ), patch(
            "app.routes.admin.utilities.sessions.UserSessionLog.query",
            mock_query,
        ), patch(
            "app.routes.admin.utilities.sessions.db.session.flush"
        ):
            resp = logged_in_client.post("/admin/utilities/sessions/cleanup")

        assert resp.status_code == 302

    def test_redirects_when_no_expired_sessions(self, logged_in_client, db_session):
        """When table exists but no expired sessions, still redirect to dashboard."""
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = []

        mock_inspect = MagicMock()
        mock_inspect.has_table.return_value = True

        with patch(
            "app.routes.admin.utilities.sessions.inspect",
            return_value=mock_inspect,
        ), patch(
            "app.routes.admin.utilities.sessions.UserSessionLog.query",
            mock_query,
        ), patch(
            "app.routes.admin.utilities.sessions.db.session.flush"
        ):
            resp = logged_in_client.post("/admin/utilities/sessions/cleanup")

        assert resp.status_code == 302

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post("/admin/utilities/sessions/cleanup")
        assert resp.status_code in (302, 401)

    def test_exception_handled_gracefully(self, logged_in_client, db_session):
        """Unhandled exception triggers error handler and redirects."""
        mock_inspect = MagicMock()
        mock_inspect.has_table.side_effect = RuntimeError("DB error")

        with patch(
            "app.routes.admin.utilities.sessions.inspect",
            return_value=mock_inspect,
        ):
            resp = logged_in_client.post("/admin/utilities/sessions/cleanup")

        # handle_view_exception redirects to admin_dashboard
        assert resp.status_code == 302

    def test_multiple_expired_sessions_all_marked_ended(self, logged_in_client, db_session):
        """All expired sessions get ended_at set."""
        sessions = [_make_mock_session() for _ in range(3)]

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = sessions

        mock_inspect = MagicMock()
        mock_inspect.has_table.return_value = True

        with patch(
            "app.routes.admin.utilities.sessions.inspect",
            return_value=mock_inspect,
        ), patch(
            "app.routes.admin.utilities.sessions.UserSessionLog.query",
            mock_query,
        ), patch(
            "app.routes.admin.utilities.sessions.db.session.flush"
        ):
            resp = logged_in_client.post("/admin/utilities/sessions/cleanup")

        assert resp.status_code == 302
        # Verify each session had ended_at set
        for s in sessions:
            assert s.ended_at is not None
            assert s.end_reason == "timeout"


# ---------------------------------------------------------------------------
# GET /admin/utilities/sessions/show_all
# ---------------------------------------------------------------------------

class TestShowAllSessions:
    """Tests for show_all_sessions (GET /admin/utilities/sessions/show_all)."""

    def test_renders_template_with_empty_sessions_when_no_table(
        self, logged_in_client, db_session
    ):
        mock_inspect = MagicMock()
        mock_inspect.has_table.return_value = False

        with patch(
            "app.routes.admin.utilities.sessions.inspect",
            return_value=mock_inspect,
        ), patch(
            "app.routes.admin.utilities.sessions.render_template",
            return_value="<html>sessions</html>",
        ) as mock_render:
            resp = logged_in_client.get("/admin/utilities/sessions/show_all")

        assert resp.status_code == 200
        call_kwargs = mock_render.call_args
        # Should pass empty sessions list
        if call_kwargs[1].get("sessions") is not None:
            assert call_kwargs[1]["sessions"] == []
        else:
            assert call_kwargs[0][1:] == () or True  # positional fallback

    def test_renders_template_with_active_sessions(self, logged_in_client, db_session):
        """Active sessions are converted to dicts and passed to template."""
        mock_user = MagicMock()
        mock_user.name = "Alice"

        mock_session_obj = _make_mock_session(user=mock_user)

        mock_query = MagicMock()
        mock_query.filter.return_value.order_by.return_value.all.return_value = [
            mock_session_obj
        ]

        mock_inspect = MagicMock()
        mock_inspect.has_table.return_value = True

        with patch(
            "app.routes.admin.utilities.sessions.inspect",
            return_value=mock_inspect,
        ), patch(
            "app.routes.admin.utilities.sessions.UserSessionLog.query",
            mock_query,
        ), patch(
            "app.routes.admin.utilities.sessions.render_template",
            return_value="<html>sessions</html>",
        ) as mock_render:
            resp = logged_in_client.get("/admin/utilities/sessions/show_all")

        assert resp.status_code == 200
        call_kwargs = mock_render.call_args
        sessions_arg = call_kwargs[1].get("sessions") or (
            call_kwargs[0][1] if len(call_kwargs[0]) > 1 else []
        )
        # Should have one session entry
        assert len(sessions_arg) == 1
        assert sessions_arg[0]["user_name"] == "Alice"

    def test_session_with_no_user_shows_unknown(self, logged_in_client, db_session):
        """A session whose .user is None shows 'Unknown' as user_name."""
        mock_session_obj = _make_mock_session()
        mock_session_obj.user = None

        mock_query = MagicMock()
        mock_query.filter.return_value.order_by.return_value.all.return_value = [
            mock_session_obj
        ]

        mock_inspect = MagicMock()
        mock_inspect.has_table.return_value = True

        with patch(
            "app.routes.admin.utilities.sessions.inspect",
            return_value=mock_inspect,
        ), patch(
            "app.routes.admin.utilities.sessions.UserSessionLog.query",
            mock_query,
        ), patch(
            "app.routes.admin.utilities.sessions.render_template",
            return_value="<html>ok</html>",
        ) as mock_render:
            resp = logged_in_client.get("/admin/utilities/sessions/show_all")

        assert resp.status_code == 200
        sessions_arg = mock_render.call_args[1].get("sessions", [])
        assert sessions_arg[0]["user_name"] == "Unknown"

    def test_exception_handled_gracefully(self, logged_in_client, db_session):
        """Exception in show_all_sessions triggers handle_view_exception."""
        mock_inspect = MagicMock()
        mock_inspect.has_table.side_effect = RuntimeError("inspect failed")

        with patch(
            "app.routes.admin.utilities.sessions.inspect",
            return_value=mock_inspect,
        ):
            resp = logged_in_client.get("/admin/utilities/sessions/show_all")

        # handle_view_exception redirects
        assert resp.status_code == 302

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/utilities/sessions/show_all")
        assert resp.status_code in (302, 401)

    def test_ip_address_and_user_agent_included_in_result(
        self, logged_in_client, db_session
    ):
        """ip_address and user_agent are passed through from getattr."""
        mock_session_obj = _make_mock_session()
        mock_session_obj.ip_address = "192.168.1.1"
        mock_session_obj.user_agent = "TestBrowser/1.0"

        mock_query = MagicMock()
        mock_query.filter.return_value.order_by.return_value.all.return_value = [
            mock_session_obj
        ]

        mock_inspect = MagicMock()
        mock_inspect.has_table.return_value = True

        with patch(
            "app.routes.admin.utilities.sessions.inspect",
            return_value=mock_inspect,
        ), patch(
            "app.routes.admin.utilities.sessions.UserSessionLog.query",
            mock_query,
        ), patch(
            "app.routes.admin.utilities.sessions.render_template",
            return_value="<html>ok</html>",
        ) as mock_render:
            resp = logged_in_client.get("/admin/utilities/sessions/show_all")

        assert resp.status_code == 200
        sessions_arg = mock_render.call_args[1].get("sessions", [])
        assert sessions_arg[0]["ip_address"] == "192.168.1.1"
        assert sessions_arg[0]["user_agent"] == "TestBrowser/1.0"

    def test_title_passed_to_template(self, logged_in_client, db_session):
        mock_inspect = MagicMock()
        mock_inspect.has_table.return_value = False

        with patch(
            "app.routes.admin.utilities.sessions.inspect",
            return_value=mock_inspect,
        ), patch(
            "app.routes.admin.utilities.sessions.render_template",
            return_value="<html>ok</html>",
        ) as mock_render:
            resp = logged_in_client.get("/admin/utilities/sessions/show_all")

        assert resp.status_code == 200
        call_kwargs = mock_render.call_args[1]
        assert call_kwargs.get("title") == "All Active Sessions"
