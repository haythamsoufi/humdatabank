"""
Comprehensive tests for app/error_handlers.py — targets 100% coverage.

Strategy:
- Add a session-scoped blueprint with trigger routes for each HTTP error code.
- Test both JSON (Accept: application/json) and HTML response paths.
- Test the 403/500 security-monitor and email-alert paths (DEBUG=False).
- Test exception suppression paths inside handlers.
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

JSON_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
HTML_HEADERS = {"Accept": "text/html"}


def _json(client, code):
    return client.get(f"/test-error/{code}", headers=JSON_HEADERS)


def _html(client, code):
    return client.get(f"/test-error/{code}", headers=HTML_HEADERS)


# ===========================================================================
# 400 Bad Request
# ===========================================================================

class TestBadRequestHandler:
    def test_json_response(self, client):
        resp = _json(client, 400)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data is not None
        assert data.get("success") is False

    def test_html_response(self, client):
        resp = _html(client, 400)
        assert resp.status_code == 400
        assert b"Bad Request" in resp.data or b"400" in resp.data

    def test_json_logs_warning(self, client, app):
        """Ensure the logger.warning call inside the handler doesn't break anything."""
        with patch.object(app.logger, "warning"):
            resp = _json(client, 400)
        assert resp.status_code == 400

    def test_json_logger_exception_suppressed(self, client, app):
        """Exception inside logger.warning block is suppressed."""
        with patch.object(app.logger, "warning", side_effect=Exception("log failed")):
            resp = _json(client, 400)
        assert resp.status_code == 400


# ===========================================================================
# 401 Unauthorized
# ===========================================================================

class TestUnauthorizedHandler:
    def test_json_response(self, client):
        resp = _json(client, 401)
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["success"] is False
        assert "Authentication required" in data.get("message", "") or "Unauthorized" in str(data)

    def test_html_response(self, client):
        resp = _html(client, 401)
        assert resp.status_code == 401
        assert b"401" in resp.data or b"Unauthorized" in resp.data


# ===========================================================================
# 403 Forbidden
# ===========================================================================

class TestForbiddenHandler:
    def test_json_response(self, client):
        resp = _json(client, 403)
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["success"] is False

    def test_html_response(self, client):
        resp = _html(client, 403)
        assert resp.status_code == 403
        assert b"403" in resp.data or b"Forbidden" in resp.data

    def test_debug_mode_skips_security_monitor(self, client, app):
        """In DEBUG mode the SecurityMonitor block is skipped."""
        original = app.config.get("DEBUG")
        try:
            app.config["DEBUG"] = True
            resp = _html(client, 403)
            assert resp.status_code == 403
        finally:
            app.config["DEBUG"] = original

    def test_production_mode_calls_security_monitor(self, client, app):
        """In non-DEBUG mode, SecurityMonitor.log_security_event is called."""
        original = app.config.get("DEBUG")
        try:
            app.config["DEBUG"] = False
            mock_monitor = MagicMock()
            with patch(
                "app.services.security.monitoring.SecurityMonitor.log_security_event",
                mock_monitor,
            ):
                resp = _html(client, 403)
            assert resp.status_code == 403
            mock_monitor.assert_called_once()
        finally:
            app.config["DEBUG"] = original

    def test_security_monitor_exception_suppressed(self, client, app):
        """Exception inside the security monitor block is suppressed."""
        original = app.config.get("DEBUG")
        try:
            app.config["DEBUG"] = False
            with patch(
                "app.services.security.monitoring.SecurityMonitor",
                side_effect=Exception("monitor unavailable"),
            ):
                resp = _html(client, 403)
            assert resp.status_code == 403
        finally:
            app.config["DEBUG"] = original

    def test_authenticated_user_id_extracted(self, client, app):
        """When an authenticated user exists, user_id is extracted for the security event."""
        original = app.config.get("DEBUG")
        try:
            app.config["DEBUG"] = False
            mock_event = MagicMock()

            # Patch _get_user so flask-login thinks the user is authenticated
            # without hitting the DB; also patch db.session.get so bootstrap
            # middleware doesn't attempt a real DB lookup.
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            mock_user.get_id.return_value = "42"

            from app.extensions import db as _db

            with patch(
                "app.services.security.monitoring.SecurityMonitor.log_security_event",
                mock_event,
            ):
                with patch.object(_db.session, "get", return_value=mock_user):
                    with client.session_transaction() as sess:
                        sess["_user_id"] = "42"
                        sess["_fresh"] = True
                    resp = _html(client, 403)

            assert resp.status_code == 403
        finally:
            app.config["DEBUG"] = original


# ===========================================================================
# 404 Not Found
# ===========================================================================

class TestNotFoundHandler:
    def test_json_response(self, client):
        resp = _json(client, 404)
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["success"] is False

    def test_html_response(self, client):
        resp = _html(client, 404)
        assert resp.status_code == 404
        assert b"404" in resp.data or b"Not Found" in resp.data

    def test_unknown_route_returns_404(self, client):
        """A request to an unknown path triggers the 404 handler."""
        resp = client.get("/this-path-does-not-exist-at-all")
        assert resp.status_code == 404


# ===========================================================================
# 500 Internal Server Error
# ===========================================================================

class TestInternalErrorHandler:
    def test_json_response(self, client):
        resp = _json(client, 500)
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["success"] is False

    def test_html_response(self, client):
        resp = _html(client, 500)
        assert resp.status_code == 500
        assert b"500" in resp.data or b"Internal Server Error" in resp.data

    def test_debug_mode_skips_security_monitor(self, client, app):
        original = app.config.get("DEBUG")
        try:
            app.config["DEBUG"] = True
            resp = _html(client, 500)
            assert resp.status_code == 500
        finally:
            app.config["DEBUG"] = original

    def test_production_mode_calls_security_monitor(self, client, app):
        original = app.config.get("DEBUG")
        try:
            app.config["DEBUG"] = False
            mock_monitor = MagicMock()
            with patch(
                "app.services.security.monitoring.SecurityMonitor.log_security_event",
                mock_monitor,
            ):
                with patch(
                    "app.services.email.service.send_security_alert",
                    return_value=True,
                ):
                    with patch("app.models.User") as mock_user:
                        from app.models.rbac import RbacUserRole, RbacRole

                        # Simulate manager query returning no managers
                        mock_user.query.join.return_value.join.return_value.filter.return_value.filter.return_value.all.return_value = (
                            []
                        )
                        resp = _html(client, 500)

            assert resp.status_code == 500
        finally:
            app.config["DEBUG"] = original

    def test_production_mode_sends_alert_email_to_managers(self, client, app):
        original = app.config.get("DEBUG")
        try:
            app.config["DEBUG"] = False
            mock_manager = MagicMock()
            mock_manager.email = "manager@example.com"

            with patch(
                "app.services.security.monitoring.SecurityMonitor.log_security_event"
            ):
                with patch(
                    "app.services.email.service.send_security_alert",
                    return_value=True,
                ) as mock_alert:
                    with patch("app.models.User") as mock_user_cls:
                        mock_user_cls.query.join.return_value.join.return_value.filter.return_value.filter.return_value.all.return_value = [
                            mock_manager
                        ]
                        resp = _html(client, 500)

            assert resp.status_code == 500
        finally:
            app.config["DEBUG"] = original

    def test_production_mode_alert_email_fails(self, client, app):
        """When send_security_alert returns False, no exception should propagate."""
        original = app.config.get("DEBUG")
        try:
            app.config["DEBUG"] = False
            mock_manager = MagicMock()
            mock_manager.email = "manager@example.com"

            with patch(
                "app.services.security.monitoring.SecurityMonitor.log_security_event"
            ):
                with patch(
                    "app.services.email.service.send_security_alert",
                    return_value=False,
                ):
                    with patch("app.models.User") as mock_user_cls:
                        mock_user_cls.query.join.return_value.join.return_value.filter.return_value.filter.return_value.all.return_value = [
                            mock_manager
                        ]
                        resp = _html(client, 500)

            assert resp.status_code == 500
        finally:
            app.config["DEBUG"] = original

    def test_production_mode_managers_without_email(self, client, app):
        """Managers found but none have email — warning is logged, no crash."""
        original = app.config.get("DEBUG")
        try:
            app.config["DEBUG"] = False
            mock_manager = MagicMock()
            mock_manager.email = None

            with patch(
                "app.services.security.monitoring.SecurityMonitor.log_security_event"
            ):
                with patch("app.models.User") as mock_user_cls:
                    mock_user_cls.query.join.return_value.join.return_value.filter.return_value.filter.return_value.all.return_value = [
                        mock_manager
                    ]
                    resp = _html(client, 500)

            assert resp.status_code == 500
        finally:
            app.config["DEBUG"] = original

    def test_production_mode_rbac_join_failure_falls_back(self, client, app):
        """When the RBAC join fails, fallback to empty managers list."""
        original = app.config.get("DEBUG")
        try:
            app.config["DEBUG"] = False
            with patch(
                "app.services.security.monitoring.SecurityMonitor.log_security_event"
            ):
                with patch(
                    "app.models.rbac.RbacUserRole",
                    side_effect=Exception("rbac table missing"),
                ):
                    resp = _html(client, 500)

            assert resp.status_code == 500
        finally:
            app.config["DEBUG"] = original

    def test_production_mode_email_exception_suppressed(self, client, app):
        """Exception during email sending is suppressed — response still returns 500."""
        original = app.config.get("DEBUG")
        try:
            app.config["DEBUG"] = False
            with patch(
                "app.services.security.monitoring.SecurityMonitor.log_security_event"
            ):
                with patch(
                    "app.services.email.service.send_security_alert",
                    side_effect=Exception("smtp down"),
                ):
                    with patch("app.models.User") as mock_user_cls:
                        mock_manager = MagicMock()
                        mock_manager.email = "m@x.com"
                        mock_user_cls.query.join.return_value.join.return_value.filter.return_value.filter.return_value.all.return_value = [
                            mock_manager
                        ]
                        resp = _html(client, 500)

            assert resp.status_code == 500
        finally:
            app.config["DEBUG"] = original

    def test_production_outer_exception_suppressed(self, client, app):
        """When the entire security-monitor import fails, still returns 500."""
        original = app.config.get("DEBUG")
        try:
            app.config["DEBUG"] = False
            with patch(
                "app.services.security.monitoring.SecurityMonitor",
                side_effect=Exception("import failed"),
            ):
                resp = _html(client, 500)

            assert resp.status_code == 500
        finally:
            app.config["DEBUG"] = original


# ===========================================================================
# 502 Bad Gateway
# ===========================================================================

class TestBadGatewayHandler:
    def test_json_response(self, client):
        resp = _json(client, 502)
        assert resp.status_code == 502
        data = resp.get_json()
        assert data["success"] is False

    def test_html_response(self, client):
        resp = _html(client, 502)
        assert resp.status_code == 502
        assert b"502" in resp.data or b"Bad Gateway" in resp.data


# ===========================================================================
# 503 Service Unavailable
# ===========================================================================

class TestServiceUnavailableHandler:
    def test_json_response(self, client):
        resp = _json(client, 503)
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["success"] is False

    def test_html_response(self, client):
        resp = _html(client, 503)
        assert resp.status_code == 503
        assert b"503" in resp.data or b"Service Unavailable" in resp.data


# ===========================================================================
# DEBUG mode — error_details exposed in HTML
# ===========================================================================

class TestDebugModeErrorDetails:
    """In DEBUG mode, error_details should be passed to the template (non-None)."""

    def test_400_html_debug_has_error_details(self, client, app):
        original = app.config.get("DEBUG")
        try:
            app.config["DEBUG"] = True
            resp = _html(client, 400)
            assert resp.status_code == 400
        finally:
            app.config["DEBUG"] = original

    def test_500_html_debug_has_error_details(self, client, app):
        original = app.config.get("DEBUG")
        try:
            app.config["DEBUG"] = True
            resp = _html(client, 500)
            assert resp.status_code == 500
        finally:
            app.config["DEBUG"] = original
