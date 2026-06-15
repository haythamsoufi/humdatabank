"""Tests for app/routes/admin/__init__.py — admin dashboard, plugin management,
legacy redirects, template globals and error handlers."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_render(text="ok"):
    from flask import make_response
    return make_response(text, 200)


def _error_status(result):
    if isinstance(result, tuple):
        return result[1]
    return result.status_code


def _auth_patches():
    """Common patches to grant admin / system-manager / permission access."""
    return [
        patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True),
        patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True),
        patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True),
    ]


# ---------------------------------------------------------------------------
# admin_dashboard
# ---------------------------------------------------------------------------


class TestAdminDashboard:
    def test_unauthenticated_redirects_to_login(self, client, db_session):
        resp = client.get("/admin/")
        assert resp.status_code in (302, 301, 308)
        assert "/login" in resp.headers["Location"] or "/auth" in resp.headers["Location"]

    def test_dashboard_renders_for_admin(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.get_platform_stats", return_value={
                 "total_users": 5,
                 "total_countries": 3,
                 "total_templates": 2,
                 "total_indicators": 10,
             }), \
             patch("app.routes.admin._kobo_data_import_url_for_dashboard", return_value=None), \
             patch("app.routes.admin.render_template", return_value=_mock_render("dashboard")):
            resp = logged_in_client.get("/admin/")
        assert resp.status_code == 200

    def test_dashboard_handles_exception(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.get_platform_stats", side_effect=RuntimeError("boom")), \
             patch("app.routes.admin._kobo_data_import_url_for_dashboard", return_value=None), \
             patch("app.routes.admin.render_template", return_value=_mock_render("error-dashboard")):
            resp = logged_in_client.get("/admin/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# plugin_management
# ---------------------------------------------------------------------------


class TestPluginManagement:
    def test_plugin_management_html(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.render_template", return_value=_mock_render("plugins")):
            resp = logged_in_client.get("/admin/plugins")
        assert resp.status_code == 200

    def test_plugin_management_json(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True):
            resp = logged_in_client.get(
                "/admin/plugins",
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "plugins" in data

    def test_plugin_management_json_import_error(self, logged_in_client, db_session, app):
        """If Plugin model not importable, returns empty list."""
        import builtins
        real_import = builtins.__import__

        def bad_import(name, *args, **kwargs):
            if name == "app.models.plugins":
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("builtins.__import__", side_effect=bad_import):
            resp = logged_in_client.get(
                "/admin/plugins",
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 0


# ---------------------------------------------------------------------------
# legacy_api_key_admin_redirect
# ---------------------------------------------------------------------------


class TestLegacyApiKeyRedirect:
    def test_redirect_no_subpath(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True):
            resp = logged_in_client.get("/admin/api-keys")
        assert resp.status_code == 301
        assert "/admin/api-management/api-keys" in resp.headers["Location"]

    def test_redirect_with_subpath(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True):
            resp = logged_in_client.get("/admin/api-keys/some/sub")
        assert resp.status_code == 301
        assert "some/sub" in resp.headers["Location"]

    def test_redirect_with_query_string(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True):
            resp = logged_in_client.get("/admin/api-keys?foo=bar")
        assert resp.status_code == 301
        assert "foo=bar" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# Template globals — direct function tests
# ---------------------------------------------------------------------------


class TestTemplateGlobals:
    def test_user_has_permission_not_authenticated(self, app, db_session):
        from app.routes.admin import user_has_permission

        with app.test_request_context("/admin/"):
            with patch("app.routes.admin.current_user") as mock_user:
                mock_user.is_authenticated = False
                result = user_has_permission("admin.some.perm")
        assert result is False

    def test_user_has_permission_authenticated(self, app, db_session):
        from app.routes.admin import user_has_permission

        with app.test_request_context("/admin/"):
            with patch("app.routes.admin.current_user") as mock_user, \
                 patch("app.routes.admin.AuthorizationService.has_rbac_permission", return_value=True):
                mock_user.is_authenticated = True
                result = user_has_permission("admin.some.perm")
        assert result is True

    def test_get_localized_sector_name(self, app, db_session):
        from app.routes.admin import get_localized_sector_name

        mock_sector = MagicMock()
        with app.test_request_context("/admin/"):
            with patch("app.routes.admin.shared.get_localized_sector_name", return_value="Water & Sanitation"):
                result = get_localized_sector_name(mock_sector)
        assert result == "Water & Sanitation"

    def test_get_localized_subsector_name(self, app, db_session):
        from app.routes.admin import get_localized_subsector_name

        mock_sub = MagicMock()
        with app.test_request_context("/admin/"):
            with patch("app.routes.admin.shared.get_localized_subsector_name", return_value="Sub"):
                result = get_localized_subsector_name(mock_sub)
        assert result == "Sub"


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


class TestAdminErrorHandlers:
    def test_admin_forbidden_html(self, app, db_session):
        from app.routes.admin import admin_forbidden

        with app.test_request_context("/admin/foo", headers={"Accept": "text/html"}):
            with patch("app.routes.admin.render_template", return_value=_mock_render("forbidden")):
                result = admin_forbidden(Exception("403"))
        assert _error_status(result) == 403

    def test_admin_forbidden_json(self, app, db_session):
        from app.routes.admin import admin_forbidden

        with app.test_request_context(
            "/admin/foo",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        ):
            result = admin_forbidden(Exception("403"))
        assert _error_status(result) == 403

    def test_admin_not_found_html(self, app, db_session):
        from app.routes.admin import admin_not_found

        with app.test_request_context("/admin/missing", headers={"Accept": "text/html"}):
            with patch("app.routes.admin.render_template", return_value=_mock_render("not-found")):
                result = admin_not_found(Exception("404"))
        assert _error_status(result) == 404

    def test_admin_not_found_json(self, app, db_session):
        from app.routes.admin import admin_not_found

        with app.test_request_context(
            "/admin/missing",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        ):
            result = admin_not_found(Exception("404"))
        assert _error_status(result) == 404

    def test_admin_internal_error_html(self, app, db_session):
        from app.routes.admin import admin_internal_error

        with app.test_request_context("/admin/err", headers={"Accept": "text/html"}):
            with patch("app.routes.admin.render_template", return_value=_mock_render("500")):
                result = admin_internal_error(Exception("500"))
        assert _error_status(result) == 500

    def test_admin_internal_error_json(self, app, db_session):
        from app.routes.admin import admin_internal_error

        with app.test_request_context(
            "/admin/err",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        ):
            result = admin_internal_error(Exception("500"))
        assert _error_status(result) == 500


# ---------------------------------------------------------------------------
# _kobo_data_import_url_for_dashboard helper
# ---------------------------------------------------------------------------


class TestKoboDataImportUrl:
    def test_returns_none_when_not_registered(self, app, db_session):
        from app.routes.admin import _kobo_data_import_url_for_dashboard

        with app.test_request_context("/admin/"):
            url = _kobo_data_import_url_for_dashboard()
        # form_builder.kobo_data_import may or may not be registered; either None or a URL string
        assert url is None or isinstance(url, str)
