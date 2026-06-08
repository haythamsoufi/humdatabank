"""Integration tests for admin assignments list page and grid action routes."""

import pytest

from app.models import AssignedForm, db
from app.models.rbac import RbacPermission, RbacRole, RbacRolePermission

from tests.factories import (
    _grant_role_permission,
    create_test_admin,
    create_test_template,
    create_test_user,
)
from tests.helpers import login_session


def _login(client, user_id: int) -> None:
    login_session(client, user_id)


def _create_assignment(db_session, *, is_active=True, unique_token=None, is_public_active=False):
    template = create_test_template(db_session)
    period_name = f"Assignment {_create_assignment.counter}"
    assignment = AssignedForm(
        template_id=template.id,
        period_name=period_name,
        is_active=is_active,
        unique_token=unique_token,
        is_public_active=is_public_active,
    )
    _create_assignment.counter += 1
    db_session.add(assignment)
    db_session.commit()
    return {
        "id": assignment.id,
        "period_name": period_name,
    }


_create_assignment.counter = 1


def _create_admin_with_permissions(db_session, permissions):
    admin = create_test_admin(
        db_session,
        can_manage_assignments=False,
        can_manage_templates=False,
        can_manage_users=False,
        can_manage_countries=False,
        can_manage_content=False,
        can_manage_api_keys=False,
        can_manage_system=False,
    )
    for perm_code in permissions:
        _grant_role_permission(db_session, "admin_core", perm_code)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def _revoke_role_permission(db_session, role_code: str, perm_code: str) -> None:
    role = db_session.query(RbacRole).filter_by(code=role_code).first()
    perm = db_session.query(RbacPermission).filter_by(code=perm_code).first()
    if not role or not perm:
        return
    db_session.query(RbacRolePermission).filter_by(
        role_id=role.id,
        permission_id=perm.id,
    ).delete()
    db_session.commit()


@pytest.mark.integration
class TestManageAssignmentsListRoute:
    def test_list_renders_for_admin(self, logged_in_client, db_session, app):
        with app.app_context():
            assignment = _create_assignment(db_session)

            resp = logged_in_client.get("/admin/assignments")
            assert resp.status_code == 200
            body = resp.get_data(as_text=True)
            assert 'id="assignments-data"' in body
            assert assignment["period_name"] in body

    def test_list_requires_auth(self, client):
        resp = client.get("/admin/assignments", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_list_denied_for_regular_user(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="user")
            _login(client, user.id)

            resp = client.get("/admin/assignments", follow_redirects=False)
            assert resp.status_code in (301, 302, 303, 307, 308, 403)

    def test_list_returns_json_for_api_request(self, logged_in_client, db_session, app):
        with app.app_context():
            assignment = _create_assignment(db_session)

            resp = logged_in_client.get(
                "/admin/assignments",
                headers={"Accept": "application/json"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["count"] >= 1
            assert isinstance(data["assignments"], list)
            ids = {row["id"] for row in data["assignments"]}
            assert assignment["id"] in ids


@pytest.mark.integration
class TestToggleAssignmentActive:
    def test_toggle_active_deactivates(self, logged_in_client, db_session, app):
        with app.app_context():
            assignment = _create_assignment(db_session, is_active=True)
            assignment_id = assignment["id"]

            resp = logged_in_client.post(
                f"/admin/assignments/{assignment_id}/toggle_active",
                follow_redirects=False,
            )
            assert resp.status_code in (301, 302, 303, 307, 308)

            updated = db.session.get(AssignedForm, assignment_id)
            assert updated.is_active is False

    def test_toggle_inactive_activates(self, logged_in_client, db_session, app):
        with app.app_context():
            assignment = _create_assignment(db_session, is_active=False)
            assignment_id = assignment["id"]

            resp = logged_in_client.post(
                f"/admin/assignments/{assignment_id}/toggle_active",
                follow_redirects=False,
            )
            assert resp.status_code in (301, 302, 303, 307, 308)

            updated = db.session.get(AssignedForm, assignment_id)
            assert updated.is_active is True

    def test_toggle_requires_edit_permission(self, client, db_session, app):
        with app.app_context():
            admin = _create_admin_with_permissions(
                db_session,
                permissions=["admin.assignments.view"],
            )
            assignment = _create_assignment(db_session, is_active=True)
            assignment_id = assignment["id"]
            _login(client, admin.id)

            resp = client.post(
                f"/admin/assignments/{assignment_id}/toggle_active",
                follow_redirects=False,
            )
            assert resp.status_code in (301, 302, 303, 307, 308, 403)

            updated = db.session.get(AssignedForm, assignment_id)
            assert updated.is_active is True


@pytest.mark.integration
class TestDeleteAssignment:
    def test_delete_assignment_happy_path(self, logged_in_client, db_session, app):
        with app.app_context():
            assignment = _create_assignment(db_session)
            assignment_id = assignment["id"]

            resp = logged_in_client.post(
                f"/admin/assignments/delete/{assignment_id}",
                follow_redirects=False,
            )
            assert resp.status_code in (301, 302, 303, 307, 308)
            assert db.session.get(AssignedForm, assignment_id) is None

    def test_delete_assignment_requires_permission(self, client, db_session, app):
        with app.app_context():
            admin = _create_admin_with_permissions(
                db_session,
                permissions=["admin.assignments.view"],
            )
            _revoke_role_permission(db_session, "admin_core", "admin.assignments.delete")
            assignment = _create_assignment(db_session)
            assignment_id = assignment["id"]
            _login(client, admin.id)

            resp = client.post(
                f"/admin/assignments/delete/{assignment_id}",
                follow_redirects=False,
            )
            assert resp.status_code in (301, 302, 303, 307, 308, 403)
            assert db.session.get(AssignedForm, assignment_id) is not None


@pytest.mark.integration
class TestGeneratePublicUrl:
    def test_generate_public_url_creates_token(self, logged_in_client, db_session, app):
        with app.app_context():
            assignment = _create_assignment(db_session)
            assignment_id = assignment["id"]

            resp = logged_in_client.post(
                f"/admin/assignments/{assignment_id}/generate_public_url",
                follow_redirects=False,
            )
            assert resp.status_code in (301, 302, 303, 307, 308)

            updated = db.session.get(AssignedForm, assignment_id)
            assert updated.unique_token is not None
            assert updated.is_public_active is True

    def test_generate_public_url_idempotent(self, logged_in_client, db_session, app):
        with app.app_context():
            assignment = _create_assignment(db_session)
            assignment_id = assignment["id"]

            logged_in_client.post(
                f"/admin/assignments/{assignment_id}/generate_public_url",
                follow_redirects=False,
            )
            first_token = db.session.get(AssignedForm, assignment_id).unique_token

            resp = logged_in_client.post(
                f"/admin/assignments/{assignment_id}/generate_public_url",
                follow_redirects=False,
            )
            assert resp.status_code in (301, 302, 303, 307, 308)

            updated = db.session.get(AssignedForm, assignment_id)
            assert updated.unique_token == first_token

    def test_generate_requires_public_submissions_permission(self, client, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session, can_manage_assignments=True)
            _revoke_role_permission(
                db_session,
                "admin_core",
                "admin.assignments.public_submissions.manage",
            )
            assignment = _create_assignment(db_session)
            assignment_id = assignment["id"]
            _login(client, admin.id)

            resp = client.post(
                f"/admin/assignments/{assignment_id}/generate_public_url",
                follow_redirects=False,
            )
            assert resp.status_code in (301, 302, 303, 307, 308, 403)

            updated = db.session.get(AssignedForm, assignment_id)
            assert updated.unique_token is None


@pytest.mark.integration
class TestTogglePublicAccess:
    def test_toggle_public_access_deactivates(self, logged_in_client, db_session, app):
        with app.app_context():
            from uuid import uuid4

            token = str(uuid4())
            assignment = _create_assignment(
                db_session,
                unique_token=token,
                is_public_active=True,
            )
            assignment_id = assignment["id"]

            resp = logged_in_client.post(
                f"/admin/assignments/{assignment_id}/toggle_public_access",
                follow_redirects=False,
            )
            assert resp.status_code in (301, 302, 303, 307, 308)

            updated = db.session.get(AssignedForm, assignment_id)
            assert updated.is_public_active is False

    def test_toggle_public_access_no_url_gives_warning(self, logged_in_client, db_session, app):
        with app.app_context():
            assignment = _create_assignment(db_session, unique_token=None)
            assignment_id = assignment["id"]

            resp = logged_in_client.post(
                f"/admin/assignments/{assignment_id}/toggle_public_access",
                follow_redirects=False,
            )
            assert resp.status_code in (301, 302, 303, 307, 308)

            updated = db.session.get(AssignedForm, assignment_id)
            assert updated.unique_token is None
            assert updated.is_public_active is False

    def test_toggle_public_access_requires_permission(self, client, db_session, app):
        with app.app_context():
            from uuid import uuid4

            admin = create_test_admin(db_session, can_manage_assignments=True)
            _revoke_role_permission(
                db_session,
                "admin_core",
                "admin.assignments.public_submissions.manage",
            )
            token = str(uuid4())
            assignment = _create_assignment(
                db_session,
                unique_token=token,
                is_public_active=True,
            )
            assignment_id = assignment["id"]
            _login(client, admin.id)

            resp = client.post(
                f"/admin/assignments/{assignment_id}/toggle_public_access",
                follow_redirects=False,
            )
            assert resp.status_code in (301, 302, 303, 307, 308, 403)

            updated = db.session.get(AssignedForm, assignment_id)
            assert updated.is_public_active is True
