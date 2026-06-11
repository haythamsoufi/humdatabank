"""Tests for app/routes/admin/security_dashboard.py."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


def _mock_render(text="ok"):
    from flask import make_response
    return make_response(text, 200)


def _perm_patch():
    return patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True)


# ---------------------------------------------------------------------------
# security_dashboard
# ---------------------------------------------------------------------------


class TestSecurityDashboard:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/security/dashboard")
        assert resp.status_code in (301, 302, 308)

    def test_renders_for_permitted_user(self, logged_in_client, db_session, app):
        mock_event = MagicMock()
        mock_event.severity = "high"
        mock_action = MagicMock()
        mock_action.risk_level = "high"

        with _perm_patch(), \
             patch("app.routes.admin.security_dashboard.get_security_metrics", return_value={"total": 0}), \
             patch("app.routes.admin.security_dashboard.SecurityEvent") as mock_se, \
             patch("app.routes.admin.security_dashboard.AdminActionLog") as mock_aal, \
             patch("app.routes.admin.security_dashboard.render_template", return_value=_mock_render("sec-dash")):
            mock_se.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_event]
            mock_aal.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_action]
            resp = logged_in_client.get("/admin/security/dashboard")
        assert resp.status_code == 200

    def test_denied_without_permission(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=False):
            resp = logged_in_client.get("/admin/security/dashboard")
        assert resp.status_code in (302, 403)


# ---------------------------------------------------------------------------
# security_events
# ---------------------------------------------------------------------------


class TestSecurityEvents:
    def test_renders_all_events(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.security_dashboard.SecurityEvent") as mock_se, \
             patch("app.routes.admin.security_dashboard.render_template", return_value=_mock_render("events")):
            mock_se.query.order_by.return_value.all.return_value = []
            mock_se.query.filter.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.get("/admin/security/events")
        assert resp.status_code == 200

    def test_filter_by_severity(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.security_dashboard.SecurityEvent") as mock_se, \
             patch("app.routes.admin.security_dashboard.render_template", return_value=_mock_render("events")):
            mock_se.query.filter.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.get("/admin/security/events?severity=high")
        assert resp.status_code == 200

    def test_filter_by_event_type(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.security_dashboard.SecurityEvent") as mock_se, \
             patch("app.routes.admin.security_dashboard.render_template", return_value=_mock_render("events")):
            mock_se.query.filter.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.get("/admin/security/events?event_type=failed_login")
        assert resp.status_code == 200

    def test_filter_unresolved_only(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.security_dashboard.SecurityEvent") as mock_se, \
             patch("app.routes.admin.security_dashboard.render_template", return_value=_mock_render("events")):
            mock_se.query.filter.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.get("/admin/security/events?unresolved_only=true")
        assert resp.status_code == 200

    def test_multiple_filters(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.security_dashboard.SecurityEvent") as mock_se, \
             patch("app.routes.admin.security_dashboard.render_template", return_value=_mock_render("events")):
            mock_se.query.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = []
            mock_se.query.filter.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.get("/admin/security/events?severity=critical&event_type=failed_login")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# resolve_security_event
# ---------------------------------------------------------------------------


class TestResolveSecurityEvent:
    def test_404_on_missing_event(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.security_dashboard.SecurityEvent") as mock_se:
            mock_se.query.get_or_404.side_effect = Exception("404")
            # Use real DB — event 9999 won't exist
            resp = logged_in_client.post("/admin/security/events/9999/resolve", data={})
        assert resp.status_code in (302, 404)

    def test_already_resolved_redirects(self, logged_in_client, db_session, app):
        mock_event = MagicMock()
        mock_event.is_resolved = True

        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.security_dashboard.SecurityEvent") as mock_se, \
             patch("app.routes.admin.security_dashboard.flash"), \
             patch("app.routes.admin.security_dashboard.redirect", side_effect=lambda loc, **kw: ("redir", loc)), \
             patch("app.routes.admin.security_dashboard.url_for", return_value="/admin/security/events"):
            mock_se.query.get_or_404.return_value = mock_event
            with app.test_request_context("/admin/security/events/1/resolve", method="POST"):
                from app.routes.admin.security_dashboard import resolve_security_event
                with patch("app.routes.admin.security_dashboard.current_user") as cu:
                    cu.id = 1
                    result = resolve_security_event(1)
        assert result[0] == "redir"

    def test_resolve_sets_resolved_and_redirects(self, logged_in_client, db_session, app):
        mock_event = MagicMock()
        mock_event.is_resolved = False
        mock_event.id = 1

        with app.test_request_context(
            "/admin/security/events/1/resolve",
            method="POST",
            data={"resolution_notes": "Fixed"},
        ):
            with patch("app.routes.admin.security_dashboard.SecurityEvent") as mock_se, \
                 patch("app.routes.admin.security_dashboard.db") as mock_db, \
                 patch("app.routes.admin.security_dashboard.flash"), \
                 patch("app.routes.admin.security_dashboard.redirect", side_effect=lambda loc, **kw: ("redir", loc)), \
                 patch("app.routes.admin.security_dashboard.url_for", return_value="/admin/security/events"), \
                 patch("app.routes.admin.security_dashboard.current_user") as cu:
                mock_se.query.get_or_404.return_value = mock_event
                mock_db.session.flush.return_value = None
                cu.id = 5
                from app.routes.admin.security_dashboard import resolve_security_event
                result = resolve_security_event(1)
        assert mock_event.is_resolved is True
        assert mock_event.resolved_by_user_id == 5
        assert result[0] == "redir"


# ---------------------------------------------------------------------------
# security_event_detail
# ---------------------------------------------------------------------------


class TestSecurityEventDetail:
    def test_renders_event_detail(self, logged_in_client, db_session, app):
        mock_event = MagicMock()
        mock_event.id = 1
        mock_event.ip_address = "1.2.3.4"
        mock_event.timestamp = MagicMock()

        with _perm_patch(), \
             patch("app.routes.admin.security_dashboard.SecurityEvent") as mock_se, \
             patch("app.routes.admin.security_dashboard.render_template", return_value=_mock_render("detail")):
            mock_se.query.get_or_404.return_value = mock_event
            mock_se.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            resp = logged_in_client.get("/admin/security/events/1")
        assert resp.status_code == 200

    def test_event_not_found_raises(self, logged_in_client, db_session, app):
        with _perm_patch():
            # Hitting a non-existent event ID through the real DB
            resp = logged_in_client.get("/admin/security/events/999999")
        assert resp.status_code in (302, 404)


# ---------------------------------------------------------------------------
# security_alerts
# ---------------------------------------------------------------------------


class TestSecurityAlerts:
    def test_renders_alerts(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.security_dashboard.SecurityEvent") as mock_se, \
             patch("app.routes.admin.security_dashboard.render_template", return_value=_mock_render("alerts")):
            mock_se.query.filter.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.get("/admin/security/alerts")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# security_settings
# ---------------------------------------------------------------------------


class TestSecuritySettings:
    def test_renders_settings(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.security_dashboard.render_template", return_value=_mock_render("settings")):
            resp = logged_in_client.get("/admin/security/settings")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# test_security_alert
# ---------------------------------------------------------------------------


class TestTestSecurityAlert:
    def test_success_redirects(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.security_dashboard.log_security_event"), \
             patch("app.routes.admin.security_dashboard.flash"), \
             patch("app.routes.admin.security_dashboard.redirect", side_effect=lambda loc, **kw: ("redir", loc)), \
             patch("app.routes.admin.security_dashboard.url_for", return_value="/admin/security/dashboard"), \
             patch("app.routes.admin.security_dashboard.current_user") as cu:
            cu.id = 1
            cu.email = "admin@example.com"
            with app.test_request_context("/admin/security/test-alert", method="POST"):
                from app.routes.admin.security_dashboard import test_security_alert
                result = test_security_alert()
        assert result[0] == "redir"

    def test_exception_flashes_error(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.security_dashboard.log_security_event", side_effect=RuntimeError("failed")), \
             patch("app.routes.admin.security_dashboard.flash") as mock_flash, \
             patch("app.routes.admin.security_dashboard.redirect", side_effect=lambda loc, **kw: ("redir", loc)), \
             patch("app.routes.admin.security_dashboard.url_for", return_value="/admin/security/dashboard"), \
             patch("app.routes.admin.security_dashboard.current_user") as cu:
            cu.id = 1
            cu.email = "admin@example.com"
            with app.test_request_context("/admin/security/test-alert", method="POST"):
                from app.routes.admin.security_dashboard import test_security_alert
                result = test_security_alert()
        mock_flash.assert_called()
        assert result[0] == "redir"


# ---------------------------------------------------------------------------
# api_security_metrics
# ---------------------------------------------------------------------------


class TestApiSecurityMetrics:
    def test_returns_dict_metrics(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.security_dashboard.get_security_metrics", return_value={"total": 5, "critical": 0}):
            resp = logged_in_client.get("/admin/api/security/metrics")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total" in data

    def test_returns_non_dict_wrapped(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.security_dashboard.get_security_metrics", return_value=[1, 2, 3]):
            resp = logged_in_client.get("/admin/api/security/metrics")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data

    def test_custom_days_param(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.security_dashboard.get_security_metrics", return_value={"days": 30}) as mock_gm:
            resp = logged_in_client.get("/admin/api/security/metrics?days=30")
        assert resp.status_code == 200
        mock_gm.assert_called_once_with(days=30)

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/api/security/metrics")
        assert resp.status_code in (301, 302, 308)
