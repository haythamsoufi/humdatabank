"""Tests for app/routes/admin/rbac_management.py."""

from unittest.mock import MagicMock, patch, call

import pytest

pytestmark = [pytest.mark.unit]


def _mock_render(text="ok"):
    from flask import make_response
    return make_response(text, 200)


def _auth_patches():
    """Patch all auth guards to pass."""
    return [
        patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True),
        patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True),
        patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True),
    ]


def _make_role(id=1, code="test_role", name="Test Role", description="A test role"):
    r = MagicMock()
    r.id = id
    r.code = code
    r.name = name
    r.description = description
    return r


def _make_perm(id=1, code="admin.test.view", name="Test View", description=""):
    p = MagicMock()
    p.id = id
    p.code = code
    p.name = name
    p.description = description
    return p


# ---------------------------------------------------------------------------
# manage_roles
# ---------------------------------------------------------------------------


class TestManageRoles:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/users/roles")
        assert resp.status_code in (301, 302, 308)

    def test_renders_roles_list(self, logged_in_client, db_session, app):
        role = _make_role()
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.db") as mock_db, \
             patch("app.routes.admin.rbac_management.render_template", return_value=_mock_render("roles")):
            mock_rr.query.order_by.return_value.all.return_value = [role]
            mock_db.session.query.return_value.group_by.return_value.all.return_value = [(1, 2)]
            resp = logged_in_client.get("/admin/users/roles")
        assert resp.status_code == 200

    def test_exception_redirects_to_dashboard(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.flash"):
            mock_rr.query.order_by.return_value.all.side_effect = RuntimeError("db error")
            resp = logged_in_client.get("/admin/users/roles")
        assert resp.status_code in (302, 200)

    def test_trailing_slash_url_also_works(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.db") as mock_db, \
             patch("app.routes.admin.rbac_management.render_template", return_value=_mock_render("roles")):
            mock_rr.query.order_by.return_value.all.return_value = []
            mock_db.session.query.return_value.group_by.return_value.all.return_value = []
            resp = logged_in_client.get("/admin/users/roles/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# new_role
# ---------------------------------------------------------------------------


class TestNewRole:
    def test_get_renders_form(self, logged_in_client, db_session, app):
        perm = _make_perm(code="admin.test.view")

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp, \
             patch("app.routes.admin.rbac_management.render_template", return_value=_mock_render("role-form")):
            mock_rp.query.order_by.return_value.all.return_value = [perm]
            resp = logged_in_client.get("/admin/users/roles/new")
        assert resp.status_code == 200

    def test_post_missing_code_redirects(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.flash"):
            resp = logged_in_client.post("/admin/users/roles/new", data={"name": "MyRole"})
        assert resp.status_code == 302

    def test_post_missing_name_redirects(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.flash"):
            resp = logged_in_client.post("/admin/users/roles/new", data={"code": "my_role"})
        assert resp.status_code == 302

    def test_post_duplicate_code_flashes(self, logged_in_client, db_session, app):
        existing = _make_role(code="duplicate")

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.flash") as mock_flash:
            mock_rr.query.filter_by.return_value.first.return_value = existing
            resp = logged_in_client.post("/admin/users/roles/new", data={"code": "duplicate", "name": "Dup"})
        assert resp.status_code == 302
        mock_flash.assert_called()

    def test_post_success_creates_role(self, logged_in_client, db_session, app):
        new_role = _make_role(id=99, code="new_code", name="New Role")

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.db") as mock_db, \
             patch("app.routes.admin.rbac_management.log_admin_action"), \
             patch("app.routes.admin.rbac_management.flash"):
            mock_rr.query.filter_by.return_value.first.return_value = None
            mock_rr.return_value = new_role
            mock_db.session.add.return_value = None
            mock_db.session.flush.return_value = None
            resp = logged_in_client.post(
                "/admin/users/roles/new",
                data={"code": "new_code", "name": "New Role", "description": "Desc"},
            )
        assert resp.status_code == 302

    def test_post_with_permissions(self, logged_in_client, db_session, app):
        new_role = _make_role(id=100, code="role_with_perms", name="With Perms")

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.RbacRolePermission") as mock_rrp, \
             patch("app.routes.admin.rbac_management.db") as mock_db, \
             patch("app.routes.admin.rbac_management.log_admin_action"), \
             patch("app.routes.admin.rbac_management.flash"):
            mock_rr.query.filter_by.return_value.first.return_value = None
            mock_rr.return_value = new_role
            resp = logged_in_client.post(
                "/admin/users/roles/new",
                data={"code": "role_with_perms", "name": "With Perms", "permissions": ["1", "2", "bad"]},
            )
        assert resp.status_code == 302

    def test_post_exception_flashes_error(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.request_transaction_rollback"), \
             patch("app.routes.admin.rbac_management.flash") as mock_flash:
            mock_rr.query.filter_by.return_value.first.return_value = None
            mock_rr.side_effect = RuntimeError("db down")
            resp = logged_in_client.post(
                "/admin/users/roles/new", data={"code": "x", "name": "Y"}
            )
        mock_flash.assert_called()


# ---------------------------------------------------------------------------
# edit_role
# ---------------------------------------------------------------------------


class TestEditRole:
    def test_get_renders_edit_form(self, logged_in_client, db_session, app):
        role = _make_role()
        perm = _make_perm()

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp, \
             patch("app.routes.admin.rbac_management.RbacRolePermission") as mock_rrp, \
             patch("app.routes.admin.rbac_management.render_template", return_value=_mock_render("role-edit")):
            mock_rr.query.get_or_404.return_value = role
            mock_rp.query.order_by.return_value.all.return_value = [perm]
            mock_rrp.query.filter_by.return_value.all.return_value = []
            resp = logged_in_client.get("/admin/users/roles/1/edit")
        assert resp.status_code == 200

    def test_post_missing_name_redirects(self, logged_in_client, db_session, app):
        role = _make_role()

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.flash"):
            mock_rr.query.get_or_404.return_value = role
            resp = logged_in_client.post("/admin/users/roles/1/edit", data={"name": ""})
        assert resp.status_code == 302

    def test_post_success_updates_role(self, logged_in_client, db_session, app):
        role = _make_role()

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.RbacRolePermission") as mock_rrp, \
             patch("app.routes.admin.rbac_management.db") as mock_db, \
             patch("app.routes.admin.rbac_management.log_admin_action"), \
             patch("app.routes.admin.rbac_management.flash"):
            mock_rr.query.get_or_404.return_value = role
            mock_rrp.query.filter_by.return_value.delete.return_value = None
            mock_db.session.flush.return_value = None
            resp = logged_in_client.post(
                "/admin/users/roles/1/edit",
                data={"name": "Updated Name", "description": "New desc"},
            )
        assert resp.status_code == 302

    def test_post_exception_flashes(self, logged_in_client, db_session, app):
        role = _make_role()

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.RbacRolePermission") as mock_rrp, \
             patch("app.routes.admin.rbac_management.request_transaction_rollback"), \
             patch("app.routes.admin.rbac_management.flash") as mock_flash:
            mock_rr.query.get_or_404.return_value = role
            mock_rrp.query.filter_by.return_value.delete.side_effect = RuntimeError("crash")
            resp = logged_in_client.post("/admin/users/roles/1/edit", data={"name": "Name"})
        mock_flash.assert_called()


# ---------------------------------------------------------------------------
# delete_role
# ---------------------------------------------------------------------------


class TestDeleteRole:
    def test_has_users_prevents_delete(self, logged_in_client, db_session, app):
        role = _make_role()

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.RbacUserRole") as mock_rur, \
             patch("app.routes.admin.rbac_management.flash") as mock_flash:
            mock_rr.query.get_or_404.return_value = role
            mock_rur.query.filter_by.return_value.count.return_value = 3
            resp = logged_in_client.post("/admin/users/roles/1/delete")
        assert resp.status_code == 302
        mock_flash.assert_called()

    def test_success_deletes_role(self, logged_in_client, db_session, app):
        role = _make_role()

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.RbacUserRole") as mock_rur, \
             patch("app.routes.admin.rbac_management.RbacRolePermission") as mock_rrp, \
             patch("app.routes.admin.rbac_management.db") as mock_db, \
             patch("app.routes.admin.rbac_management.log_admin_action"), \
             patch("app.routes.admin.rbac_management.flash"):
            mock_rr.query.get_or_404.return_value = role
            mock_rur.query.filter_by.return_value.count.return_value = 0
            mock_rrp.query.filter_by.return_value.delete.return_value = None
            mock_db.session.delete.return_value = None
            mock_db.session.flush.return_value = None
            resp = logged_in_client.post("/admin/users/roles/1/delete")
        assert resp.status_code == 302

    def test_exception_flashes_error(self, logged_in_client, db_session, app):
        role = _make_role()

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.RbacUserRole") as mock_rur, \
             patch("app.routes.admin.rbac_management.RbacRolePermission") as mock_rrp, \
             patch("app.routes.admin.rbac_management.request_transaction_rollback"), \
             patch("app.routes.admin.rbac_management.flash") as mock_flash:
            mock_rr.query.get_or_404.return_value = role
            mock_rur.query.filter_by.return_value.count.return_value = 0
            mock_rrp.query.filter_by.return_value.delete.side_effect = RuntimeError("crash")
            resp = logged_in_client.post("/admin/users/roles/1/delete")
        mock_flash.assert_called()


# ---------------------------------------------------------------------------
# list_permissions
# ---------------------------------------------------------------------------


class TestListPermissions:
    def test_renders_permissions_list(self, logged_in_client, db_session, app):
        perm = _make_perm()

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp, \
             patch("app.routes.admin.rbac_management.render_template", return_value=_mock_render("perms")):
            mock_rp.query.order_by.return_value.all.return_value = [perm]
            resp = logged_in_client.get("/admin/users/permissions")
        assert resp.status_code == 200

    def test_exception_redirects(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp, \
             patch("app.routes.admin.rbac_management.flash"):
            mock_rp.query.order_by.return_value.all.side_effect = RuntimeError("crash")
            resp = logged_in_client.get("/admin/users/permissions")
        assert resp.status_code in (302, 200)


# ---------------------------------------------------------------------------
# manage_grants
# ---------------------------------------------------------------------------


class TestManageGrants:
    def test_renders_grants(self, logged_in_client, db_session, app):
        grant = MagicMock()
        grant.principal_type = "user"
        grant.principal_id = 1
        grant.permission_id = 1
        grant.template_id = None
        grant.assigned_form_id = None

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacAccessGrant") as mock_ag, \
             patch("app.routes.admin.rbac_management.User") as mock_u, \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp, \
             patch("app.routes.admin.rbac_management.FormTemplate") as mock_ft, \
             patch("app.routes.admin.rbac_management.AssignedForm") as mock_af, \
             patch("app.routes.admin.rbac_management.render_template", return_value=_mock_render("grants")):
            mock_ag.query.order_by.return_value.all.return_value = [grant]
            mock_u.query.filter.return_value.all.return_value = []
            mock_rr.query.filter.return_value.all.return_value = []
            mock_rp.query.filter.return_value.all.return_value = []
            mock_ft.query.filter.return_value.all.return_value = []
            mock_af.query.filter.return_value.all.return_value = []
            resp = logged_in_client.get("/admin/users/grants")
        assert resp.status_code == 200

    def test_exception_redirects(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacAccessGrant") as mock_ag, \
             patch("app.routes.admin.rbac_management.flash"):
            mock_ag.query.order_by.return_value.all.side_effect = RuntimeError("crash")
            resp = logged_in_client.get("/admin/users/grants")
        assert resp.status_code in (302, 200)


# ---------------------------------------------------------------------------
# new_grant GET
# ---------------------------------------------------------------------------


class TestNewGrantGet:
    def test_renders_grant_form(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp, \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.User") as mock_u, \
             patch("app.routes.admin.rbac_management.render_template", return_value=_mock_render("grant-form")):
            mock_rp.query.order_by.return_value.all.return_value = []
            mock_rr.query.order_by.return_value.all.return_value = []
            mock_u.query.filter_by.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.get("/admin/users/grants/new")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# new_grant POST — validation failures
# ---------------------------------------------------------------------------


class TestNewGrantPost:
    def _post(self, logged_in_client, data):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.flash"):
            return logged_in_client.post("/admin/users/grants/new", data=data)

    def test_invalid_principal_type(self, logged_in_client, db_session, app):
        resp = self._post(logged_in_client, {
            "principal_type": "group", "principal_id": "1", "permission_id": "1", "effect": "allow", "scope_kind": "global"
        })
        assert resp.status_code == 302

    def test_missing_principal_id(self, logged_in_client, db_session, app):
        resp = self._post(logged_in_client, {
            "principal_type": "user", "permission_id": "1", "effect": "allow", "scope_kind": "global"
        })
        assert resp.status_code == 302

    def test_invalid_effect(self, logged_in_client, db_session, app):
        resp = self._post(logged_in_client, {
            "principal_type": "user", "principal_id": "1", "permission_id": "1", "effect": "neutral", "scope_kind": "global"
        })
        assert resp.status_code == 302

    def test_invalid_scope_kind(self, logged_in_client, db_session, app):
        resp = self._post(logged_in_client, {
            "principal_type": "user", "principal_id": "1", "permission_id": "1", "effect": "allow", "scope_kind": "alien"
        })
        assert resp.status_code == 302

    def test_user_principal_not_found(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.User") as mock_u, \
             patch("app.routes.admin.rbac_management.flash"):
            mock_u.query.get.return_value = None
            resp = logged_in_client.post("/admin/users/grants/new", data={
                "principal_type": "user", "principal_id": "999", "permission_id": "1", "effect": "allow", "scope_kind": "global"
            })
        assert resp.status_code == 302

    def test_role_principal_not_found(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr, \
             patch("app.routes.admin.rbac_management.flash"):
            mock_rr.query.get.return_value = None
            resp = logged_in_client.post("/admin/users/grants/new", data={
                "principal_type": "role", "principal_id": "999", "permission_id": "1", "effect": "allow", "scope_kind": "global"
            })
        assert resp.status_code == 302

    def test_permission_not_found(self, logged_in_client, db_session, app):
        mock_user = MagicMock()
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.User") as mock_u, \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp, \
             patch("app.routes.admin.rbac_management.flash"):
            mock_u.query.get.return_value = mock_user
            mock_rp.query.get.return_value = None
            resp = logged_in_client.post("/admin/users/grants/new", data={
                "principal_type": "user", "principal_id": "1", "permission_id": "999", "effect": "allow", "scope_kind": "global"
            })
        assert resp.status_code == 302

    def test_entity_scope_missing_entity_type(self, logged_in_client, db_session, app):
        mock_user = MagicMock()
        mock_perm = MagicMock()
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.User") as mock_u, \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp, \
             patch("app.routes.admin.rbac_management.flash"):
            mock_u.query.get.return_value = mock_user
            mock_rp.query.get.return_value = mock_perm
            resp = logged_in_client.post("/admin/users/grants/new", data={
                "principal_type": "user", "principal_id": "1", "permission_id": "1",
                "effect": "allow", "scope_kind": "entity"
                # missing entity_type and entity_id
            })
        assert resp.status_code == 302

    def test_entity_scope_too_long(self, logged_in_client, db_session, app):
        mock_user = MagicMock()
        mock_perm = MagicMock()
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.User") as mock_u, \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp, \
             patch("app.routes.admin.rbac_management.flash"):
            mock_u.query.get.return_value = mock_user
            mock_rp.query.get.return_value = mock_perm
            resp = logged_in_client.post("/admin/users/grants/new", data={
                "principal_type": "user", "principal_id": "1", "permission_id": "1",
                "effect": "allow", "scope_kind": "entity",
                "entity_type": "x" * 60,  # too long
                "entity_id": "5",
            })
        assert resp.status_code == 302

    def test_template_scope_missing_template_id(self, logged_in_client, db_session, app):
        mock_user = MagicMock()
        mock_perm = MagicMock()
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.User") as mock_u, \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp, \
             patch("app.routes.admin.rbac_management.flash"):
            mock_u.query.get.return_value = mock_user
            mock_rp.query.get.return_value = mock_perm
            resp = logged_in_client.post("/admin/users/grants/new", data={
                "principal_type": "user", "principal_id": "1", "permission_id": "1",
                "effect": "allow", "scope_kind": "template"
            })
        assert resp.status_code == 302

    def test_assignment_scope_missing_assigned_form_id(self, logged_in_client, db_session, app):
        mock_user = MagicMock()
        mock_perm = MagicMock()
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.User") as mock_u, \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp, \
             patch("app.routes.admin.rbac_management.flash"):
            mock_u.query.get.return_value = mock_user
            mock_rp.query.get.return_value = mock_perm
            resp = logged_in_client.post("/admin/users/grants/new", data={
                "principal_type": "user", "principal_id": "1", "permission_id": "1",
                "effect": "allow", "scope_kind": "assignment"
            })
        assert resp.status_code == 302

    def test_success_global_scope(self, logged_in_client, db_session, app):
        mock_user = MagicMock()
        mock_perm = MagicMock()
        mock_grant = MagicMock()
        mock_grant.id = 42

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.User") as mock_u, \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp, \
             patch("app.routes.admin.rbac_management.RbacAccessGrant") as mock_ag, \
             patch("app.routes.admin.rbac_management.db") as mock_db, \
             patch("app.routes.admin.rbac_management.log_admin_action"), \
             patch("app.routes.admin.rbac_management.flash"):
            mock_u.query.get.return_value = mock_user
            mock_rp.query.get.return_value = mock_perm
            mock_ag.return_value = mock_grant
            resp = logged_in_client.post("/admin/users/grants/new", data={
                "principal_type": "user", "principal_id": "1", "permission_id": "1",
                "effect": "allow", "scope_kind": "global"
            })
        assert resp.status_code == 302

    def test_integrity_error_flashes(self, logged_in_client, db_session, app):
        from sqlalchemy.exc import IntegrityError
        mock_user = MagicMock()
        mock_perm = MagicMock()

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.User") as mock_u, \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp, \
             patch("app.routes.admin.rbac_management.RbacAccessGrant") as mock_ag, \
             patch("app.routes.admin.rbac_management.db") as mock_db, \
             patch("app.routes.admin.rbac_management.request_transaction_rollback"), \
             patch("app.routes.admin.rbac_management.flash") as mock_flash:
            mock_u.query.get.return_value = mock_user
            mock_rp.query.get.return_value = mock_perm
            mock_db.session.flush.side_effect = IntegrityError("duplicate", None, None)
            resp = logged_in_client.post("/admin/users/grants/new", data={
                "principal_type": "user", "principal_id": "1", "permission_id": "1",
                "effect": "allow", "scope_kind": "global"
            })
        mock_flash.assert_called()


# ---------------------------------------------------------------------------
# delete_grant
# ---------------------------------------------------------------------------


class TestDeleteGrant:
    def test_success_deletes_and_redirects(self, logged_in_client, db_session, app):
        grant = MagicMock()
        grant.id = 1
        grant.principal_type = "user"
        grant.principal_id = 1
        grant.permission_id = 1
        grant.effect = "allow"
        grant.scope_kind = "global"

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacAccessGrant") as mock_ag, \
             patch("app.routes.admin.rbac_management.db") as mock_db, \
             patch("app.routes.admin.rbac_management.log_admin_action"), \
             patch("app.routes.admin.rbac_management.flash"):
            mock_ag.query.get_or_404.return_value = grant
            resp = logged_in_client.post("/admin/users/grants/1/delete")
        assert resp.status_code == 302

    def test_exception_flashes_error(self, logged_in_client, db_session, app):
        grant = MagicMock()
        grant.id = 1
        grant.principal_type = "user"
        grant.principal_id = 1
        grant.permission_id = 1
        grant.effect = "allow"
        grant.scope_kind = "global"

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacAccessGrant") as mock_ag, \
             patch("app.routes.admin.rbac_management.db") as mock_db, \
             patch("app.routes.admin.rbac_management.request_transaction_rollback"), \
             patch("app.routes.admin.rbac_management.flash") as mock_flash:
            mock_ag.query.get_or_404.return_value = grant
            mock_db.session.delete.side_effect = RuntimeError("crash")
            resp = logged_in_client.post("/admin/users/grants/1/delete")
        mock_flash.assert_called()


# ---------------------------------------------------------------------------
# api_list_roles
# ---------------------------------------------------------------------------


class TestApiListRoles:
    def test_returns_roles_json(self, logged_in_client, db_session, app):
        role = _make_role()

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr:
            mock_rr.query.order_by.return_value.all.return_value = [role]
            resp = logged_in_client.get("/admin/users/api/roles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "roles" in data

    def test_exception_returns_500(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr:
            mock_rr.query.order_by.return_value.all.side_effect = RuntimeError("crash")
            resp = logged_in_client.get("/admin/users/api/roles")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# api_list_permissions
# ---------------------------------------------------------------------------


class TestApiListPermissions:
    def test_returns_permissions_json(self, logged_in_client, db_session, app):
        perm = _make_perm()

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp:
            mock_rp.query.order_by.return_value.all.return_value = [perm]
            resp = logged_in_client.get("/admin/users/api/permissions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "permissions" in data

    def test_exception_returns_500(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.RbacPermission") as mock_rp:
            mock_rp.query.order_by.return_value.all.side_effect = RuntimeError("crash")
            resp = logged_in_client.get("/admin/users/api/permissions")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# api_get_user_roles
# ---------------------------------------------------------------------------


class TestApiGetUserRoles:
    def test_returns_user_roles(self, logged_in_client, db_session, app):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.email = "user@example.com"
        mock_user.name = "User"
        role = _make_role()

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.User") as mock_u, \
             patch("app.routes.admin.rbac_management.RbacUserRole") as mock_rur, \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr:
            mock_u.query.get_or_404.return_value = mock_user
            mock_ur = MagicMock()
            mock_ur.role_id = 1
            mock_rur.query.filter_by.return_value.all.return_value = [mock_ur]
            mock_rr.query.filter.return_value.all.return_value = [role]
            resp = logged_in_client.get("/admin/users/api/users/1/roles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "roles" in data

    def test_user_not_found_404(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True):
            # Real DB will 404 for non-existent user
            resp = logged_in_client.get("/admin/users/api/users/999999/roles")
        assert resp.status_code in (404, 500)

    def test_no_roles(self, logged_in_client, db_session, app):
        mock_user = MagicMock()
        mock_user.id = 2
        mock_user.email = "other@example.com"
        mock_user.name = "Other"

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.rbac_management.User") as mock_u, \
             patch("app.routes.admin.rbac_management.RbacUserRole") as mock_rur, \
             patch("app.routes.admin.rbac_management.RbacRole") as mock_rr:
            mock_u.query.get_or_404.return_value = mock_user
            mock_rur.query.filter_by.return_value.all.return_value = []
            mock_rr.query.filter.return_value.all.return_value = []
            resp = logged_in_client.get("/admin/users/api/users/2/roles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["roles"] == []
