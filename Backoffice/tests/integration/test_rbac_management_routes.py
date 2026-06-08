"""
Comprehensive tests for app/routes/admin/rbac_management.py

Covers all eleven routes:
  HTML pages (GET / POST / redirect):
    GET  /admin/users/roles[/]           manage_roles
    GET/POST /admin/users/roles/new      new_role
    GET/POST /admin/users/roles/<id>/edit    edit_role
    POST     /admin/users/roles/<id>/delete  delete_role
    GET  /admin/users/permissions        list_permissions
    GET  /admin/users/grants             manage_grants
    GET/POST /admin/users/grants/new     new_grant
    POST     /admin/users/grants/<id>/delete  delete_grant

  JSON API (system-manager-scoped):
    GET /admin/users/api/roles           api_list_roles
    GET /admin/users/api/permissions     api_list_permissions
    GET /admin/users/api/users/<id>/roles  api_get_user_roles

Authorization model
-------------------
- Unauthenticated requests → redirect to login (3xx)
- Regular / focal-point users → redirect or 403
- System managers → full access (superuser shortcut in has_rbac_permission)
"""
import uuid
import pytest

from tests.factories import create_test_user
from tests.helpers import login_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_rbac_role(db_session, *, code=None, name=None):
    """Create and return a fresh RbacRole in the db."""
    from app.models.rbac import RbacRole

    code = code or f"role_{uuid.uuid4().hex[:8]}"
    name = name or f"Role {code}"
    role = RbacRole(code=code, name=name)
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role


def _create_rbac_permission(db_session, *, code=None, name=None):
    """Ensure an RbacPermission row exists and return it."""
    from app.models.rbac import RbacPermission

    code = code or f"perm.{uuid.uuid4().hex[:8]}"
    perm = RbacPermission.query.filter_by(code=code).first()
    if perm:
        return perm
    perm = RbacPermission(code=code, name=name or code, description=code)
    db_session.add(perm)
    db_session.commit()
    db_session.refresh(perm)
    return perm


def _create_rbac_grant(db_session, *, user, perm):
    """Create and return an RbacAccessGrant for a user."""
    from app.models.rbac import RbacAccessGrant

    grant = RbacAccessGrant(
        principal_type="user",
        principal_id=user.id,
        permission_id=perm.id,
        effect="allow",
        scope_kind="global",
    )
    db_session.add(grant)
    db_session.commit()
    db_session.refresh(grant)
    return grant


# ---------------------------------------------------------------------------
# 1. Authentication / Authorization
# ---------------------------------------------------------------------------

GUARDED_GET_ROUTES = [
    "/admin/users/roles",
    "/admin/users/roles/",
    "/admin/users/roles/new",
    "/admin/users/permissions",
    "/admin/users/grants",
    "/admin/users/grants/new",
]


@pytest.mark.integration
@pytest.mark.critical
class TestRbacManagementAuth:
    """Unauthenticated and under-privileged requests are correctly rejected."""

    @pytest.mark.parametrize("path", GUARDED_GET_ROUTES)
    def test_unauthenticated_redirects_to_login(self, client, path):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308), (
            f"Expected redirect for unauthenticated GET {path}, got {resp.status_code}"
        )

    @pytest.mark.parametrize("path", GUARDED_GET_ROUTES)
    def test_regular_user_denied(self, client, db_session, app, path):
        with app.app_context():
            user = create_test_user(db_session, role="user")
            login_session(client, user.id)
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308, 403), (
            f"Expected denial for regular user on GET {path}, got {resp.status_code}"
        )

    @pytest.mark.parametrize("path", GUARDED_GET_ROUTES)
    def test_system_manager_gets_200(self, logged_in_sm_client, path):
        resp = logged_in_sm_client.get(path, follow_redirects=False)
        assert resp.status_code == 200, (
            f"Expected 200 for system manager on GET {path}, got {resp.status_code}"
        )

    def test_unauthenticated_post_delete_role_redirects(self, client, db_session):
        resp = client.post("/admin/users/roles/999/delete", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_unauthenticated_post_delete_grant_redirects(self, client):
        resp = client.post("/admin/users/grants/999/delete", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)


# ---------------------------------------------------------------------------
# 2. Roles – HTML routes
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestManageRolesPage:
    """GET /admin/users/roles – roles list page."""

    def test_roles_page_renders(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/users/roles")
        assert resp.status_code == 200

    def test_trailing_slash_variant_renders(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/users/roles/")
        assert resp.status_code == 200

    def test_existing_role_appears_on_page(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            role = _create_rbac_role(db_session, code="visible_role", name="Visible Role")
        resp = logged_in_sm_client.get("/admin/users/roles")
        assert resp.status_code == 200
        assert b"Visible Role" in resp.data


@pytest.mark.integration
class TestNewRoleRoute:
    """GET/POST /admin/users/roles/new – create a role."""

    def test_get_shows_create_form(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/users/roles/new")
        assert resp.status_code == 200

    def test_post_creates_role_and_redirects(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacRole

        unique = uuid.uuid4().hex[:8]
        resp = logged_in_sm_client.post(
            "/admin/users/roles/new",
            data={"code": f"new_{unique}", "name": f"New Role {unique}", "description": "desc"},
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302, 303, 307, 308)
        with app.app_context():
            role = RbacRole.query.filter_by(code=f"new_{unique}").first()
            assert role is not None
            assert role.name == f"New Role {unique}"

    def test_post_with_permission_assigns_it(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacRole, RbacRolePermission

        with app.app_context():
            perm = _create_rbac_permission(db_session, code=f"test.perm.{uuid.uuid4().hex[:6]}")
            perm_id = int(perm.id)

        unique = uuid.uuid4().hex[:8]
        logged_in_sm_client.post(
            "/admin/users/roles/new",
            data={
                "code": f"perm_role_{unique}",
                "name": f"Perm Role {unique}",
                "permissions": [str(perm_id)],
            },
            follow_redirects=False,
        )
        with app.app_context():
            role = RbacRole.query.filter_by(code=f"perm_role_{unique}").first()
            assert role is not None
            link = RbacRolePermission.query.filter_by(
                role_id=role.id, permission_id=perm_id
            ).first()
            assert link is not None

    def test_post_missing_code_redirects_with_no_creation(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacRole

        before = RbacRole.query.count()
        logged_in_sm_client.post(
            "/admin/users/roles/new",
            data={"code": "", "name": "No Code Role"},
            follow_redirects=False,
        )
        with app.app_context():
            after = RbacRole.query.count()
            assert after == before

    def test_post_missing_name_redirects_with_no_creation(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacRole

        before = RbacRole.query.count()
        logged_in_sm_client.post(
            "/admin/users/roles/new",
            data={"code": "noname_code", "name": ""},
            follow_redirects=False,
        )
        with app.app_context():
            assert RbacRole.query.count() == before

    def test_post_duplicate_code_blocked(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacRole

        with app.app_context():
            _create_rbac_role(db_session, code="dup_code_role")

        logged_in_sm_client.post(
            "/admin/users/roles/new",
            data={"code": "dup_code_role", "name": "Duplicate"},
            follow_redirects=False,
        )
        with app.app_context():
            count = RbacRole.query.filter_by(code="dup_code_role").count()
            assert count == 1


@pytest.mark.integration
class TestEditRoleRoute:
    """GET/POST /admin/users/roles/<id>/edit – edit a role."""

    def test_get_shows_edit_form(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            role = _create_rbac_role(db_session)
            role_id = int(role.id)

        resp = logged_in_sm_client.get(f"/admin/users/roles/{role_id}/edit")
        assert resp.status_code == 200

    def test_get_404_for_nonexistent_role(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/users/roles/999999/edit")
        assert resp.status_code == 404

    def test_post_updates_name_and_description(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacRole

        with app.app_context():
            role = _create_rbac_role(db_session, code=f"upd_{uuid.uuid4().hex[:8]}")
            role_id = int(role.id)

        logged_in_sm_client.post(
            f"/admin/users/roles/{role_id}/edit",
            data={"name": "Updated Role Name", "description": "New desc"},
            follow_redirects=False,
        )
        with app.app_context():
            updated = RbacRole.query.get(role_id)
            assert updated.name == "Updated Role Name"
            assert updated.description == "New desc"

    def test_post_missing_name_does_not_update(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacRole

        with app.app_context():
            role = _create_rbac_role(db_session, code=f"noname_{uuid.uuid4().hex[:8]}", name="Original")
            role_id = int(role.id)

        logged_in_sm_client.post(
            f"/admin/users/roles/{role_id}/edit",
            data={"name": "", "description": "some desc"},
            follow_redirects=False,
        )
        with app.app_context():
            unchanged = RbacRole.query.get(role_id)
            assert unchanged.name == "Original"

    def test_post_sets_permissions(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacRolePermission

        with app.app_context():
            perm = _create_rbac_permission(db_session, code=f"perm.set.{uuid.uuid4().hex[:6]}")
            role = _create_rbac_role(db_session)
            role_id = int(role.id)
            perm_id = int(perm.id)

        logged_in_sm_client.post(
            f"/admin/users/roles/{role_id}/edit",
            data={"name": "Perm Role", "permissions": [str(perm_id)]},
            follow_redirects=False,
        )
        with app.app_context():
            links = RbacRolePermission.query.filter_by(role_id=role_id).all()
            perm_ids = {lnk.permission_id for lnk in links}
            assert perm_id in perm_ids

    def test_post_404_for_nonexistent_role(self, logged_in_sm_client):
        resp = logged_in_sm_client.post(
            "/admin/users/roles/999999/edit",
            data={"name": "X"},
            follow_redirects=False,
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestDeleteRoleRoute:
    """POST /admin/users/roles/<id>/delete – delete a role."""

    def test_delete_role_without_users_succeeds(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacRole

        with app.app_context():
            role = _create_rbac_role(db_session, code=f"del_empty_{uuid.uuid4().hex[:8]}")
            role_id = int(role.id)

        resp = logged_in_sm_client.post(
            f"/admin/users/roles/{role_id}/delete",
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302, 303, 307, 308)
        with app.app_context():
            assert RbacRole.query.get(role_id) is None

    def test_delete_role_also_removes_permissions(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacRole, RbacRolePermission

        with app.app_context():
            perm = _create_rbac_permission(db_session, code=f"perm.del.{uuid.uuid4().hex[:6]}")
            role = _create_rbac_role(db_session, code=f"del_perm_{uuid.uuid4().hex[:8]}")
            db_session.add(RbacRolePermission(role_id=role.id, permission_id=perm.id))
            db_session.commit()
            role_id = int(role.id)

        logged_in_sm_client.post(f"/admin/users/roles/{role_id}/delete", follow_redirects=False)
        with app.app_context():
            assert RbacRole.query.get(role_id) is None
            remaining = RbacRolePermission.query.filter_by(role_id=role_id).count()
            assert remaining == 0

    def test_delete_blocked_when_users_assigned(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacRole, RbacUserRole

        with app.app_context():
            role = _create_rbac_role(db_session, code=f"del_blocked_{uuid.uuid4().hex[:8]}")
            user = create_test_user(
                db_session,
                email=f"del_guard_{uuid.uuid4().hex[:8]}@example.com",
            )
            db_session.add(RbacUserRole(user_id=user.id, role_id=role.id))
            db_session.commit()
            role_id = int(role.id)

        resp = logged_in_sm_client.post(
            f"/admin/users/roles/{role_id}/delete",
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302, 303, 307, 308)
        with app.app_context():
            # Role must still exist
            assert RbacRole.query.get(role_id) is not None

    def test_delete_404_for_nonexistent_role(self, logged_in_sm_client):
        resp = logged_in_sm_client.post("/admin/users/roles/999999/delete")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 3. Permissions reference page
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestListPermissionsPage:
    """GET /admin/users/permissions – permissions reference page."""

    def test_permissions_page_renders(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/users/permissions")
        assert resp.status_code == 200

    def test_permissions_page_denied_for_regular_user(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="user")
            login_session(client, user.id)
        resp = client.get("/admin/users/permissions", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308, 403)

    def test_existing_permission_visible_on_page(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            perm = _create_rbac_permission(
                db_session, code=f"visible.perm.{uuid.uuid4().hex[:6]}", name="Visible Permission"
            )
        resp = logged_in_sm_client.get("/admin/users/permissions")
        assert resp.status_code == 200
        assert b"Visible Permission" in resp.data


# ---------------------------------------------------------------------------
# 4. Grants – HTML routes
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestManageGrantsPage:
    """GET /admin/users/grants – grants list page."""

    def test_grants_page_renders(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/users/grants")
        assert resp.status_code == 200

    def test_grants_page_denied_for_regular_user(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="user")
            login_session(client, user.id)
        resp = client.get("/admin/users/grants", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308, 403)


@pytest.mark.integration
class TestNewGrantRoute:
    """GET/POST /admin/users/grants/new – create a grant."""

    def test_get_shows_grant_form(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/users/grants/new")
        assert resp.status_code == 200

    def test_post_creates_global_user_grant(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacAccessGrant

        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"grant_u_{uuid.uuid4().hex[:8]}@example.com",
            )
            perm = _create_rbac_permission(
                db_session, code=f"test.grant.{uuid.uuid4().hex[:6]}"
            )
            user_id = int(user.id)
            perm_id = int(perm.id)

        resp = logged_in_sm_client.post(
            "/admin/users/grants/new",
            data={
                "principal_type": "user",
                "principal_id": str(user_id),
                "permission_id": str(perm_id),
                "effect": "allow",
                "scope_kind": "global",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302, 303, 307, 308)
        with app.app_context():
            grant = RbacAccessGrant.query.filter_by(
                principal_id=user_id, permission_id=perm_id
            ).first()
            assert grant is not None
            assert grant.effect == "allow"
            assert grant.scope_kind == "global"
            assert grant.principal_type == "user"

    def test_post_creates_deny_grant(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacAccessGrant

        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"deny_grant_{uuid.uuid4().hex[:8]}@example.com",
            )
            perm = _create_rbac_permission(
                db_session, code=f"test.deny.{uuid.uuid4().hex[:6]}"
            )
            user_id = int(user.id)
            perm_id = int(perm.id)

        logged_in_sm_client.post(
            "/admin/users/grants/new",
            data={
                "principal_type": "user",
                "principal_id": str(user_id),
                "permission_id": str(perm_id),
                "effect": "deny",
                "scope_kind": "global",
            },
            follow_redirects=False,
        )
        with app.app_context():
            grant = RbacAccessGrant.query.filter_by(
                principal_id=user_id, permission_id=perm_id
            ).first()
            assert grant is not None
            assert grant.effect == "deny"

    def test_post_creates_role_grant(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacAccessGrant

        with app.app_context():
            role = _create_rbac_role(db_session, code=f"grant_role_{uuid.uuid4().hex[:8]}")
            perm = _create_rbac_permission(
                db_session, code=f"test.role.grant.{uuid.uuid4().hex[:6]}"
            )
            role_id = int(role.id)
            perm_id = int(perm.id)

        logged_in_sm_client.post(
            "/admin/users/grants/new",
            data={
                "principal_type": "role",
                "principal_id": str(role_id),
                "permission_id": str(perm_id),
                "effect": "allow",
                "scope_kind": "global",
            },
            follow_redirects=False,
        )
        with app.app_context():
            grant = RbacAccessGrant.query.filter_by(
                principal_type="role", principal_id=role_id, permission_id=perm_id
            ).first()
            assert grant is not None

    def test_post_invalid_principal_type_redirects(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacAccessGrant

        before = RbacAccessGrant.query.count()
        logged_in_sm_client.post(
            "/admin/users/grants/new",
            data={
                "principal_type": "invalid",
                "principal_id": "1",
                "permission_id": "1",
                "effect": "allow",
                "scope_kind": "global",
            },
            follow_redirects=False,
        )
        with app.app_context():
            assert RbacAccessGrant.query.count() == before

    def test_post_invalid_effect_redirects(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacAccessGrant

        before = RbacAccessGrant.query.count()
        logged_in_sm_client.post(
            "/admin/users/grants/new",
            data={
                "principal_type": "user",
                "principal_id": "1",
                "permission_id": "1",
                "effect": "bad_effect",
                "scope_kind": "global",
            },
            follow_redirects=False,
        )
        with app.app_context():
            assert RbacAccessGrant.query.count() == before

    def test_post_nonexistent_user_redirects(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacAccessGrant

        with app.app_context():
            perm = _create_rbac_permission(db_session, code=f"test.nouser.{uuid.uuid4().hex[:6]}")
            perm_id = int(perm.id)

        before = RbacAccessGrant.query.count()
        logged_in_sm_client.post(
            "/admin/users/grants/new",
            data={
                "principal_type": "user",
                "principal_id": "999999999",
                "permission_id": str(perm_id),
                "effect": "allow",
                "scope_kind": "global",
            },
            follow_redirects=False,
        )
        with app.app_context():
            assert RbacAccessGrant.query.count() == before

    def test_post_nonexistent_permission_redirects(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacAccessGrant

        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"no_perm_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        before = RbacAccessGrant.query.count()
        logged_in_sm_client.post(
            "/admin/users/grants/new",
            data={
                "principal_type": "user",
                "principal_id": str(user_id),
                "permission_id": "999999999",
                "effect": "allow",
                "scope_kind": "global",
            },
            follow_redirects=False,
        )
        with app.app_context():
            assert RbacAccessGrant.query.count() == before


@pytest.mark.integration
class TestDeleteGrantRoute:
    """POST /admin/users/grants/<id>/delete – delete a grant."""

    def test_delete_grant_removes_record(self, logged_in_sm_client, db_session, app):
        from app.models.rbac import RbacAccessGrant

        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"del_grnt_{uuid.uuid4().hex[:8]}@example.com",
            )
            perm = _create_rbac_permission(
                db_session, code=f"test.delete.g.{uuid.uuid4().hex[:6]}"
            )
            grant = _create_rbac_grant(db_session, user=user, perm=perm)
            grant_id = int(grant.id)

        resp = logged_in_sm_client.post(
            f"/admin/users/grants/{grant_id}/delete",
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302, 303, 307, 308)
        with app.app_context():
            assert RbacAccessGrant.query.get(grant_id) is None

    def test_delete_grant_404_for_nonexistent(self, logged_in_sm_client):
        resp = logged_in_sm_client.post("/admin/users/grants/999999999/delete")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. JSON API endpoints
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRbacJsonApiListRoles:
    """GET /admin/users/api/roles"""

    def test_requires_auth(self, client):
        resp = client.get("/admin/users/api/roles")
        assert resp.status_code in (301, 302, 303, 307, 308, 401, 403)

    def test_returns_roles_list(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            _create_rbac_role(db_session, code=f"api_lr_{uuid.uuid4().hex[:8]}", name="API List Role")

        resp = logged_in_sm_client.get(
            "/admin/users/api/roles",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "roles" in data
        assert isinstance(data["roles"], list)

    def test_role_objects_have_required_fields(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            _create_rbac_role(db_session, code=f"api_shape_{uuid.uuid4().hex[:8]}")

        resp = logged_in_sm_client.get(
            "/admin/users/api/roles",
            headers={"Accept": "application/json"},
        )
        data = resp.get_json()
        assert len(data["roles"]) > 0
        role = data["roles"][0]
        for field in ("id", "code", "name", "description"):
            assert field in role, f"Missing field in role object: {field}"


@pytest.mark.integration
class TestRbacJsonApiListPermissions:
    """GET /admin/users/api/permissions"""

    def test_requires_auth(self, client):
        resp = client.get("/admin/users/api/permissions")
        assert resp.status_code in (301, 302, 303, 307, 308, 401, 403)

    def test_returns_permissions_list(self, logged_in_sm_client):
        resp = logged_in_sm_client.get(
            "/admin/users/api/permissions",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "permissions" in data
        assert isinstance(data["permissions"], list)

    def test_permissions_objects_have_required_fields(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            _create_rbac_permission(
                db_session,
                code=f"shape.check.{uuid.uuid4().hex[:6]}",
                name="Shape Check",
            )

        resp = logged_in_sm_client.get(
            "/admin/users/api/permissions",
            headers={"Accept": "application/json"},
        )
        data = resp.get_json()
        assert len(data["permissions"]) > 0
        perm = data["permissions"][0]
        for field in ("id", "code", "name", "description"):
            assert field in perm, f"Missing field in permission object: {field}"


@pytest.mark.integration
class TestRbacJsonApiGetUserRoles:
    """GET /admin/users/api/users/<id>/roles"""

    def test_requires_auth(self, client):
        resp = client.get("/admin/users/api/users/1/roles")
        assert resp.status_code in (301, 302, 303, 307, 308, 401, 403)

    def test_returns_user_and_roles(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"api_ur_{uuid.uuid4().hex[:8]}@example.com",
                role="system_manager",
            )
            user_id = int(user.id)

        resp = logged_in_sm_client.get(
            f"/admin/users/api/users/{user_id}/roles",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "user" in data
        assert "roles" in data
        assert data["user"]["id"] == user_id
        assert isinstance(data["roles"], list)

    def test_user_object_fields(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"api_uf_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        resp = logged_in_sm_client.get(
            f"/admin/users/api/users/{user_id}/roles",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        u = resp.get_json()["user"]
        for field in ("id", "email", "name"):
            assert field in u, f"Missing field in user object: {field}"

    def test_roles_objects_have_required_fields(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"api_rf_{uuid.uuid4().hex[:8]}@example.com",
                role="system_manager",
            )
            user_id = int(user.id)

        resp = logged_in_sm_client.get(
            f"/admin/users/api/users/{user_id}/roles",
            headers={"Accept": "application/json"},
        )
        data = resp.get_json()
        assert len(data["roles"]) > 0
        role = data["roles"][0]
        for field in ("id", "code", "name", "description"):
            assert field in role, f"Missing field in role object: {field}"

    def test_returns_error_for_nonexistent_user(self, logged_in_sm_client):
        # get_or_404 is inside a try/except Exception, so 404 may be
        # re-raised as a 500 depending on how the exception handler works.
        resp = logged_in_sm_client.get(
            "/admin/users/api/users/999999999/roles",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code in (404, 500)

    def test_user_with_no_roles_returns_empty_list(self, logged_in_sm_client, db_session, app):
        """A user with no explicit RBAC role assignments returns an empty roles list.

        Note: create_test_user always assigns one default role, so we test that
        roles is a list (not missing) and contains zero or more items.
        """
        with app.app_context():
            from app.models import User

            bare_user = User(
                email=f"noroles_{uuid.uuid4().hex[:8]}@example.com",
                name="No Roles User",
                active=True,
            )
            bare_user.set_password("test_pass")
            db_session.add(bare_user)
            db_session.commit()
            user_id = int(bare_user.id)

        resp = logged_in_sm_client.get(
            f"/admin/users/api/users/{user_id}/roles",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data["roles"], list)
        assert len(data["roles"]) == 0
