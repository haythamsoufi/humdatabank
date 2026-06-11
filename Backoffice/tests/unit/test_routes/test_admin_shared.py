"""Tests for app/routes/admin/shared.py — decorators and utility functions."""

from unittest.mock import MagicMock, patch

import pytest
from flask import make_response
from flask_login import login_user

pytestmark = [pytest.mark.unit]


def _mock_view():
    return make_response("ok", 200)


# ---------------------------------------------------------------------------
# admin_required
# ---------------------------------------------------------------------------


class TestAdminRequired:
    def test_unauthenticated_redirects_to_login(self, app, db_session):
        from app.routes.admin.shared import admin_required

        @admin_required
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/", method="GET"):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.redirect", side_effect=lambda loc, **kw: ("redirect", loc)) as mock_redirect, \
                 patch("app.routes.admin.shared.url_for", return_value="/login"), \
                 patch("app.routes.admin.shared.get_current_relative_url", return_value="/admin/"), \
                 patch("app.routes.admin.shared.flash"):
                mock_user.is_authenticated = False
                app.config["DEBUG_SKIP_LOGIN"] = False
                result = dummy_view()
        assert result == ("redirect", "/login")

    def test_non_admin_user_redirects_to_dashboard(self, app, db_session):
        from app.routes.admin.shared import admin_required

        @admin_required
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/", method="GET"):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=False), \
                 patch("app.routes.admin.shared.redirect", side_effect=lambda loc, **kw: ("redirect", loc)), \
                 patch("app.routes.admin.shared.url_for", return_value="/dashboard"), \
                 patch("app.routes.admin.shared.flash"):
                mock_user.is_authenticated = True
                app.config["DEBUG_SKIP_LOGIN"] = False
                result = dummy_view()
        assert "redirect" in result

    def test_admin_user_proceeds(self, app, db_session):
        from app.routes.admin.shared import admin_required

        @admin_required
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/", method="GET"):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True):
                mock_user.is_authenticated = True
                app.config["DEBUG_SKIP_LOGIN"] = False
                resp = dummy_view()
        assert resp.status_code == 200

    def test_sets_rbac_admin_required_metadata(self, app):
        from app.routes.admin.shared import admin_required

        @admin_required
        def my_view():
            return _mock_view()

        assert getattr(my_view, "_rbac_admin_required", False) is True


# ---------------------------------------------------------------------------
# permission_required
# ---------------------------------------------------------------------------


class TestPermissionRequired:
    def test_unauthenticated_html_redirects(self, app, db_session):
        from app.routes.admin.shared import permission_required

        @permission_required("admin.some.perm")
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/x", method="GET"):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.redirect", side_effect=lambda loc, **kw: ("redirect", loc)), \
                 patch("app.routes.admin.shared.url_for", return_value="/login"), \
                 patch("app.routes.admin.shared.get_current_relative_url", return_value="/admin/x"), \
                 patch("app.routes.admin.shared.flash"), \
                 patch("app.routes.admin.shared._is_json_request", return_value=False):
                mock_user.is_authenticated = False
                app.config["DEBUG_SKIP_LOGIN"] = False
                result = dummy_view()
        assert result[0] == "redirect"

    def test_unauthenticated_json_returns_401(self, app, db_session):
        from app.routes.admin.shared import permission_required

        @permission_required("admin.some.perm")
        def dummy_view():
            return _mock_view()

        with app.test_request_context(
            "/admin/x",
            method="GET",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        ):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared._is_json_request", return_value=True):
                mock_user.is_authenticated = False
                app.config["DEBUG_SKIP_LOGIN"] = False
                resp, status = dummy_view()
        assert status == 401

    def test_no_permission_html_redirects(self, app, db_session):
        from app.routes.admin.shared import permission_required

        @permission_required("admin.restricted")
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/x", method="GET"):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=False), \
                 patch("app.routes.admin.shared.redirect", side_effect=lambda loc, **kw: ("redirect", loc)), \
                 patch("app.routes.admin.shared.url_for", return_value="/dashboard"), \
                 patch("app.routes.admin.shared.flash"), \
                 patch("app.routes.admin.shared._is_json_request", return_value=False):
                mock_user.is_authenticated = True
                app.config["DEBUG_SKIP_LOGIN"] = False
                result = dummy_view()
        assert result[0] == "redirect"

    def test_no_permission_json_returns_403(self, app, db_session):
        from app.routes.admin.shared import permission_required

        @permission_required("admin.restricted")
        def dummy_view():
            return _mock_view()

        with app.test_request_context(
            "/admin/x",
            method="GET",
            headers={"Accept": "application/json"},
        ):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=False), \
                 patch("app.routes.admin.shared._is_json_request", return_value=True):
                mock_user.is_authenticated = True
                app.config["DEBUG_SKIP_LOGIN"] = False
                resp, status = dummy_view()
        assert status == 403

    def test_permitted_user_proceeds(self, app, db_session):
        from app.routes.admin.shared import permission_required

        @permission_required("admin.some.perm")
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/x", method="GET"):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
                 patch("app.routes.admin.shared._is_json_request", return_value=False):
                mock_user.is_authenticated = True
                app.config["DEBUG_SKIP_LOGIN"] = False
                resp = dummy_view()
        assert resp.status_code == 200

    def test_metadata_accumulated(self, app):
        from app.routes.admin.shared import permission_required

        @permission_required("admin.users.view")
        def my_view():
            return _mock_view()

        assert "admin.users.view" in getattr(my_view, "_rbac_permissions_required", [])


# ---------------------------------------------------------------------------
# system_manager_required
# ---------------------------------------------------------------------------


class TestSystemManagerRequired:
    def test_unauthenticated_html_redirects(self, app, db_session):
        from app.routes.admin.shared import system_manager_required

        @system_manager_required
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/sm", method="GET"):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.redirect", side_effect=lambda loc, **kw: ("redirect", loc)), \
                 patch("app.routes.admin.shared.url_for", return_value="/login"), \
                 patch("app.routes.admin.shared.get_current_relative_url", return_value="/admin/sm"), \
                 patch("app.routes.admin.shared.flash"), \
                 patch("app.routes.admin.shared._is_json_request", return_value=False):
                mock_user.is_authenticated = False
                result = dummy_view()
        assert result[0] == "redirect"

    def test_non_system_manager_html_redirects(self, app, db_session):
        from app.routes.admin.shared import system_manager_required

        @system_manager_required
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/sm"):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=False), \
                 patch("app.routes.admin.shared.redirect", side_effect=lambda loc, **kw: ("redirect", loc)), \
                 patch("app.routes.admin.shared.url_for", return_value="/admin/"), \
                 patch("app.routes.admin.shared.flash"), \
                 patch("app.routes.admin.shared._is_json_request", return_value=False):
                mock_user.is_authenticated = True
                result = dummy_view()
        assert result[0] == "redirect"

    def test_non_system_manager_json_returns_403(self, app, db_session):
        from app.routes.admin.shared import system_manager_required

        @system_manager_required
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/sm", headers={"Accept": "application/json"}):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=False), \
                 patch("app.routes.admin.shared._is_json_request", return_value=True):
                mock_user.is_authenticated = True
                resp, status = dummy_view()
        assert status == 403

    def test_system_manager_proceeds(self, app, db_session):
        from app.routes.admin.shared import system_manager_required

        @system_manager_required
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/sm"):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
                 patch("app.routes.admin.shared._is_json_request", return_value=False):
                mock_user.is_authenticated = True
                resp = dummy_view()
        assert resp.status_code == 200

    def test_sets_system_manager_metadata(self, app):
        from app.routes.admin.shared import system_manager_required

        @system_manager_required
        def my_view():
            return _mock_view()

        assert getattr(my_view, "_rbac_system_manager_required", False) is True


# ---------------------------------------------------------------------------
# permission_required_any
# ---------------------------------------------------------------------------


class TestPermissionRequiredAny:
    def test_unauthenticated_redirects(self, app, db_session):
        from app.routes.admin.shared import permission_required_any

        @permission_required_any("admin.a.view", "admin.b.view")
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/x"):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.redirect", side_effect=lambda loc, **kw: ("redirect", loc)), \
                 patch("app.routes.admin.shared.url_for", return_value="/login"), \
                 patch("app.routes.admin.shared.get_current_relative_url", return_value="/admin/x"), \
                 patch("app.routes.admin.shared.flash"), \
                 patch("app.routes.admin.shared._is_json_request", return_value=False):
                mock_user.is_authenticated = False
                app.config["DEBUG_SKIP_LOGIN"] = False
                result = dummy_view()
        assert result[0] == "redirect"

    def test_no_matching_permission_redirects(self, app, db_session):
        from app.routes.admin.shared import permission_required_any

        @permission_required_any("admin.a.view", "admin.b.view")
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/x"):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=False), \
                 patch("app.routes.admin.shared.redirect", side_effect=lambda loc, **kw: ("redirect", loc)), \
                 patch("app.routes.admin.shared.url_for", return_value="/dashboard"), \
                 patch("app.routes.admin.shared.flash"), \
                 patch("app.routes.admin.shared._is_json_request", return_value=False):
                mock_user.is_authenticated = True
                app.config["DEBUG_SKIP_LOGIN"] = False
                result = dummy_view()
        assert result[0] == "redirect"

    def test_one_matching_permission_proceeds(self, app, db_session):
        from app.routes.admin.shared import permission_required_any

        @permission_required_any("admin.a.view", "admin.b.view")
        def dummy_view():
            return _mock_view()

        call_count = [0]

        def has_perm(user, perm):
            call_count[0] += 1
            return perm == "admin.a.view"

        with app.test_request_context("/admin/x"):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", side_effect=has_perm), \
                 patch("app.routes.admin.shared._is_json_request", return_value=False):
                mock_user.is_authenticated = True
                app.config["DEBUG_SKIP_LOGIN"] = False
                resp = dummy_view()
        assert resp.status_code == 200

    def test_single_iterable_argument(self, app):
        from app.routes.admin.shared import permission_required_any

        @permission_required_any(["admin.a.view", "admin.b.view"])
        def dummy_view():
            return _mock_view()

        perms = getattr(dummy_view, "_rbac_permissions_any_required", [])
        assert "admin.a.view" in perms
        assert "admin.b.view" in perms

    def test_invalid_perms_filtered_out(self, app):
        from app.routes.admin.shared import permission_required_any

        @permission_required_any("admin.valid.perm", "no-dot-here", "", "  ")
        def dummy_view():
            return _mock_view()

        perms = getattr(dummy_view, "_rbac_permissions_any_required", [])
        assert "admin.valid.perm" in perms
        assert "no-dot-here" not in perms

    def test_unauthenticated_json_returns_401(self, app, db_session):
        from app.routes.admin.shared import permission_required_any

        @permission_required_any("admin.a.view")
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/x", headers={"Accept": "application/json"}):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared._is_json_request", return_value=True):
                mock_user.is_authenticated = False
                app.config["DEBUG_SKIP_LOGIN"] = False
                resp, status = dummy_view()
        assert status == 401

    def test_no_permission_json_returns_403(self, app, db_session):
        from app.routes.admin.shared import permission_required_any

        @permission_required_any("admin.a.view")
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/x", headers={"Accept": "application/json"}):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=False), \
                 patch("app.routes.admin.shared._is_json_request", return_value=True):
                mock_user.is_authenticated = True
                app.config["DEBUG_SKIP_LOGIN"] = False
                resp, status = dummy_view()
        assert status == 403


# ---------------------------------------------------------------------------
# rbac_guard_audit_exempt
# ---------------------------------------------------------------------------


class TestRbacGuardAuditExempt:
    def test_exempt_decorator_passes_through(self, app, db_session):
        from app.routes.admin.shared import rbac_guard_audit_exempt

        @rbac_guard_audit_exempt("public endpoint")
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/"):
            resp = dummy_view()
        assert resp.status_code == 200

    def test_exempt_sets_metadata(self, app):
        from app.routes.admin.shared import rbac_guard_audit_exempt

        @rbac_guard_audit_exempt("intentionally public")
        def my_view():
            return _mock_view()

        assert getattr(my_view, "_rbac_guard_audit_exempt", False) is True
        assert "intentionally public" in getattr(my_view, "_rbac_guard_audit_exempt_reason", "")


# ---------------------------------------------------------------------------
# admin_permission_required
# ---------------------------------------------------------------------------


class TestAdminPermissionRequired:
    def test_stacks_both_checks(self, app, db_session):
        from app.routes.admin.shared import admin_permission_required

        @admin_permission_required("admin.users.view")
        def dummy_view():
            return _mock_view()

        with app.test_request_context("/admin/users"):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
                 patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
                 patch("app.routes.admin.shared._is_json_request", return_value=False):
                mock_user.is_authenticated = True
                app.config["DEBUG_SKIP_LOGIN"] = False
                resp = dummy_view()
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# user_has_permission
# ---------------------------------------------------------------------------


class TestUserHasPermission:
    def test_unauthenticated_returns_false(self, app, db_session):
        from app.routes.admin.shared import user_has_permission

        with app.test_request_context("/"):
            with patch("app.routes.admin.shared.current_user") as mock_user:
                mock_user.is_authenticated = False
                result = user_has_permission("admin.users.view")
        assert result is False

    def test_invalid_permission_name_returns_false(self, app, db_session):
        from app.routes.admin.shared import user_has_permission

        with app.test_request_context("/"):
            with patch("app.routes.admin.shared.current_user") as mock_user:
                mock_user.is_authenticated = True
                result = user_has_permission("no-dot-here")
        assert result is False

    def test_empty_string_returns_false(self, app, db_session):
        from app.routes.admin.shared import user_has_permission

        with app.test_request_context("/"):
            with patch("app.routes.admin.shared.current_user") as mock_user:
                mock_user.is_authenticated = True
                result = user_has_permission("")
        assert result is False

    def test_non_string_returns_false(self, app, db_session):
        from app.routes.admin.shared import user_has_permission

        with app.test_request_context("/"):
            with patch("app.routes.admin.shared.current_user") as mock_user:
                mock_user.is_authenticated = True
                result = user_has_permission(None)  # type: ignore
        assert result is False

    def test_valid_permission_returns_service_result(self, app, db_session):
        from app.routes.admin.shared import user_has_permission

        with app.test_request_context("/"):
            with patch("app.routes.admin.shared.current_user") as mock_user, \
                 patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True):
                mock_user.is_authenticated = True
                result = user_has_permission("admin.users.view")
        assert result is True


# ---------------------------------------------------------------------------
# check_template_access
# ---------------------------------------------------------------------------


class TestCheckTemplateAccess:
    def test_delegates_to_authorization_service(self, app, db_session):
        from app.routes.admin.shared import check_template_access

        with app.test_request_context("/"):
            with patch("app.routes.admin.shared.AuthorizationService.check_template_access", return_value=True):
                result = check_template_access(1, 2)
        assert result is True

    def test_returns_false_when_no_access(self, app, db_session):
        from app.routes.admin.shared import check_template_access

        with app.test_request_context("/"):
            with patch("app.routes.admin.shared.AuthorizationService.check_template_access", return_value=False):
                result = check_template_access(1, 2)
        assert result is False


# ---------------------------------------------------------------------------
# _is_json_request alias
# ---------------------------------------------------------------------------


class TestIsJsonRequestAlias:
    def test_alias_calls_is_json_request(self, app, db_session):
        from app.routes.admin.shared import _is_json_request

        with app.test_request_context("/", headers={"Accept": "application/json"}):
            with patch("app.routes.admin.shared.is_json_request", return_value=True):
                result = _is_json_request()
        assert result is True
