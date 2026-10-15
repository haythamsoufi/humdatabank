"""Assignment access control: per-user scope and per-assignment role restriction."""

import uuid

import pytest

from app import db
from app.models import AssignedForm, User
from app.models.assignments import assigned_form_allowed_role, user_assignment_access
from app.models.rbac import RbacRole, RbacRolePermission, RbacUserRole
from app.services.assignments import access_service
from app.services.organization.authorization_service import AuthorizationService
from tests.factories import (
    _ensure_permission,
    _grant_entity_permission,
    create_test_assignment_entity_status,
    create_test_country,
    create_test_template,
    create_test_user,
)
from tests.helpers import login_session

_FOCAL_PERMS = ("assignment.view", "assignment.edit", "assignment.submit", "assignment.enter")
_ADMIN_PERMS = (
    "admin.assignments.view",
    "admin.assignments.edit",
    "admin.assignments.access.manage",
    "admin.users.view",
    "admin.users.edit",
    "admin.users.grants.manage",
)


def _make_role(db_session, perms=(), name=None):
    role = RbacRole(code=f"r_{uuid.uuid4().hex[:10]}", name=name or f"Role {uuid.uuid4().hex[:6]}")
    db_session.add(role)
    db_session.flush()
    for code in perms:
        pid = _ensure_permission(db_session, code)
        db_session.add(RbacRolePermission(role_id=role.id, permission_id=pid))
    db_session.commit()
    return role


def _user_with_roles(db_session, roles):
    user = create_test_user(db_session, role="user")
    for link in list(RbacUserRole.query.filter_by(user_id=user.id)):
        db_session.delete(link)
    for role in roles:
        db_session.add(RbacUserRole(user_id=user.id, role_id=role.id))
    db_session.commit()
    return user


def _restrict_to_roles(db_session, assignment_id, roles):
    assignment = db_session.get(AssignedForm, assignment_id)
    access_service.set_assignment_allowed_roles(assignment, [r.id for r in roles])
    db_session.commit()
    access_service.invalidate_cache()


def _select_for_user(db_session, user, assignment_ids):
    user = db_session.get(User, user.id)
    access_service.set_user_assignment_access(user, "selected", assignment_ids)
    db_session.commit()
    access_service.invalidate_cache()


@pytest.fixture
def scenario(db_session, app):
    """Two assignments on one country, a focal role, and a finance role."""
    country = create_test_country(db_session)
    aes_1 = create_test_assignment_entity_status(
        db_session, country=country, template=create_test_template(db_session), period_name="2024"
    )
    aes_2 = create_test_assignment_entity_status(
        db_session, country=country, template=create_test_template(db_session), period_name="2025"
    )
    focal_role = _make_role(db_session, _FOCAL_PERMS, name="Focal")
    finance_role = _make_role(db_session, (), name="Finance")
    focal = _user_with_roles(db_session, [focal_role])
    finance_focal = _user_with_roles(db_session, [focal_role, finance_role])
    for user in (focal, finance_focal):
        _grant_entity_permission(db_session, user, aes_1.entity_type, aes_1.entity_id)
    db_session.commit()
    access_service.invalidate_cache()
    return {
        "aes_1": aes_1,
        "aes_2": aes_2,
        "focal": focal,
        "finance_focal": finance_focal,
        "finance_role": finance_role,
        "focal_role": focal_role,
        "system_manager": create_test_user(db_session, role="system_manager"),
    }


class TestDefaults:
    def test_everything_open_by_default(self, scenario):
        for key in ("aes_1", "aes_2"):
            aes = scenario[key]
            assert access_service.user_can_access_assigned_form(scenario["focal"], aes.assigned_form_id)
        assert access_service.assignment_access_clause(scenario["focal"], AssignedForm.id) is not None
        assert access_service.get_access_scope(scenario["system_manager"]).unrestricted

    def test_default_mode_is_all(self, scenario):
        assert scenario["focal"].assignment_access_mode == "all"
        assert list(scenario["focal"].selected_assignments) == []


class TestUserScope:
    def test_selected_mode_limits_to_chosen_assignments(self, db_session, scenario):
        a1, a2 = scenario["aes_1"].assigned_form_id, scenario["aes_2"].assigned_form_id
        _select_for_user(db_session, scenario["focal"], [a1])
        user = scenario["focal"]
        assert access_service.user_can_access_assigned_form(user, a1)
        assert not access_service.user_can_access_assigned_form(user, a2)
        assert access_service.filter_accessible_assigned_form_ids(user, [a1, a2]) == {a1}

    def test_selected_with_nothing_ticked_blocks_all(self, db_session, scenario):
        _select_for_user(db_session, scenario["focal"], [])
        for key in ("aes_1", "aes_2"):
            assert not access_service.user_can_access_assigned_form(
                scenario["focal"], scenario[key].assigned_form_id
            )
        rows = access_service.apply_assignment_access(
            AssignedForm.query, scenario["focal"], AssignedForm.id
        ).all()
        assert rows == []

    def test_switching_back_to_all_restores_access_and_keeps_picks(self, db_session, scenario):
        a1, a2 = scenario["aes_1"].assigned_form_id, scenario["aes_2"].assigned_form_id
        _select_for_user(db_session, scenario["focal"], [a1])
        user = db_session.get(User, scenario["focal"].id)
        access_service.set_user_assignment_access(user, "all", [a1])
        db_session.commit()
        access_service.invalidate_cache()
        assert access_service.user_can_access_assigned_form(user, a2)
        assert {a.id for a in user.selected_assignments} == {a1}

    def test_invalid_mode_falls_back_to_all(self):
        assert access_service.normalize_access_mode("bogus") == "all"
        assert access_service.normalize_access_mode(None) == "all"

    def test_system_manager_ignores_selected_mode(self, db_session, scenario):
        _select_for_user(db_session, scenario["system_manager"], [])
        assert access_service.user_can_access_assigned_form(
            scenario["system_manager"], scenario["aes_1"].assigned_form_id
        )


class TestRoleRestriction:
    def test_only_holders_of_the_role_pass(self, db_session, scenario):
        a1 = scenario["aes_1"].assigned_form_id
        _restrict_to_roles(db_session, a1, [scenario["finance_role"]])
        assert not access_service.user_can_access_assigned_form(scenario["focal"], a1)
        assert access_service.user_can_access_assigned_form(scenario["finance_focal"], a1)
        assert access_service.user_can_access_assigned_form(scenario["system_manager"], a1)

    def test_any_listed_role_is_enough(self, db_session, scenario):
        a1 = scenario["aes_1"].assigned_form_id
        _restrict_to_roles(db_session, a1, [scenario["finance_role"], scenario["focal_role"]])
        assert access_service.user_can_access_assigned_form(scenario["focal"], a1)

    def test_clearing_roles_reopens_assignment(self, db_session, scenario):
        a1 = scenario["aes_1"].assigned_form_id
        _restrict_to_roles(db_session, a1, [scenario["finance_role"]])
        _restrict_to_roles(db_session, a1, [])
        assert access_service.user_can_access_assigned_form(scenario["focal"], a1)

    def test_both_restrictions_must_allow(self, db_session, scenario):
        a1, a2 = scenario["aes_1"].assigned_form_id, scenario["aes_2"].assigned_form_id
        _restrict_to_roles(db_session, a1, [scenario["finance_role"]])
        _select_for_user(db_session, scenario["finance_focal"], [a2])
        assert not access_service.user_can_access_assigned_form(scenario["finance_focal"], a1)
        assert access_service.user_can_access_assigned_form(scenario["finance_focal"], a2)

    def test_clause_matches_single_check(self, db_session, scenario):
        a1, a2 = scenario["aes_1"].assigned_form_id, scenario["aes_2"].assigned_form_id
        _restrict_to_roles(db_session, a1, [scenario["finance_role"]])
        _select_for_user(db_session, scenario["focal"], [a1, a2])
        for user in (scenario["focal"], scenario["finance_focal"], scenario["system_manager"]):
            via_clause = {
                row.id
                for row in access_service.apply_assignment_access(
                    AssignedForm.query, user, AssignedForm.id
                ).all()
                if row.id in (a1, a2)
            }
            via_check = {
                aid for aid in (a1, a2) if access_service.user_can_access_assigned_form(user, aid)
            }
            assert via_clause == via_check


class TestAuthorizationService:
    def test_can_access_assignment_honors_role_restriction(self, db_session, scenario):
        aes = scenario["aes_1"]
        assert AuthorizationService.can_access_assignment(aes, scenario["focal"])
        _restrict_to_roles(db_session, aes.assigned_form_id, [scenario["finance_role"]])
        assert not AuthorizationService.can_access_assignment(aes, scenario["focal"])
        assert not AuthorizationService.can_edit_assignment(aes, scenario["focal"])
        assert AuthorizationService.can_access_assignment(aes, scenario["finance_focal"])

    def test_can_access_assignment_honors_user_scope(self, db_session, scenario):
        aes = scenario["aes_1"]
        _select_for_user(db_session, scenario["focal"], [])
        assert not AuthorizationService.can_access_assignment(aes, scenario["focal"])


class TestAdminAssignmentRoutes:
    @pytest.fixture
    def admin(self, db_session, scenario):
        role = _make_role(db_session, _ADMIN_PERMS, name="Assignments admin")
        user = _user_with_roles(db_session, [role])
        return user

    def test_list_hides_restricted_assignments(self, client, db_session, scenario, admin):
        a1, a2 = scenario["aes_1"].assigned_form_id, scenario["aes_2"].assigned_form_id
        _restrict_to_roles(db_session, a1, [scenario["finance_role"]])
        login_session(client, admin.id)
        resp = client.get("/admin/assignments", headers={"Accept": "application/json"})
        assert resp.status_code == 200
        ids = {row["id"] for row in resp.get_json()["assignments"]}
        assert a2 in ids
        assert a1 not in ids

    def test_hidden_assignment_detail_is_404(self, client, db_session, scenario, admin):
        a1 = scenario["aes_1"].assigned_form_id
        _restrict_to_roles(db_session, a1, [scenario["finance_role"]])
        login_session(client, admin.id)
        assert client.get(f"/admin/assignments/edit/{a1}").status_code == 404
        assert client.get(f"/admin/assignments/{a1}/entities").status_code == 404

    def test_visible_assignment_detail_still_works(self, client, db_session, scenario, admin):
        a2 = scenario["aes_2"].assigned_form_id
        login_session(client, admin.id)
        assert client.get(f"/admin/assignments/edit/{a2}").status_code == 200

    def test_system_manager_sees_restricted_assignment(self, client, db_session, scenario):
        a1 = scenario["aes_1"].assigned_form_id
        _restrict_to_roles(db_session, a1, [scenario["finance_role"]])
        login_session(client, scenario["system_manager"].id)
        assert client.get(f"/admin/assignments/edit/{a1}").status_code == 200

    def test_admin_can_restrict_assignment_to_role(self, client, db_session, scenario, admin):
        a2 = scenario["aes_2"].assigned_form_id
        # The admin holds the Finance role so they keep access after restricting.
        db_session.add(RbacUserRole(user_id=admin.id, role_id=scenario["finance_role"].id))
        db_session.commit()
        login_session(client, admin.id)
        resp = client.get(f"/admin/assignments/edit/{a2}")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'name="allowed_role_ids"' in body
        assert "Finance" in body

    def test_role_deletion_blocked_while_it_restricts_assignments(
        self, client, db_session, scenario
    ):
        a1 = scenario["aes_1"].assigned_form_id
        role = _make_role(db_session, (), name="Temporary")
        _restrict_to_roles(db_session, a1, [role])
        login_session(client, scenario["system_manager"].id)
        resp = client.post(f"/admin/users/roles/{role.id}/delete", follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert db_session.get(RbacRole, role.id) is not None
        remaining = db_session.execute(
            assigned_form_allowed_role.select().where(assigned_form_allowed_role.c.role_id == role.id)
        ).all()
        assert len(remaining) == 1


class TestUserFormAssignmentAccess:
    def test_form_renders_picker_for_system_manager(self, client, db_session, scenario):
        login_session(client, scenario["system_manager"].id)
        resp = client.get(f"/admin/users/edit_user/{scenario['focal'].id}")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'id="assignment-access-section"' in body
        assert 'name="assignment_access_mode"' in body
        assert f'value="{scenario["aes_1"].assigned_form_id}"' in body

    def test_saving_selected_mode_persists(self, client, db_session, scenario):
        login_session(client, scenario["system_manager"].id)
        focal = scenario["focal"]
        a1 = scenario["aes_1"].assigned_form_id
        resp = client.post(
            f"/admin/users/edit_user/{focal.id}",
            data={
                "email": focal.email,
                "name": focal.name,
                "profile_color": "#3B82F6",
                "assignment_access_submitted": "1",
                "assignment_access_mode": "selected",
                "selected_assignment_ids": [str(a1)],
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303), resp.data.decode()[:500]
        db_session.expire_all()
        user = db_session.get(User, focal.id)
        assert user.assignment_access_mode == "selected"
        assert {a.id for a in user.selected_assignments} == {a1}
        rows = db_session.execute(
            user_assignment_access.select().where(user_assignment_access.c.user_id == focal.id)
        ).all()
        assert len(rows) == 1

    def test_post_without_marker_leaves_scope_untouched(self, client, db_session, scenario):
        a1 = scenario["aes_1"].assigned_form_id
        _select_for_user(db_session, scenario["focal"], [a1])
        login_session(client, scenario["system_manager"].id)
        focal = scenario["focal"]
        resp = client.post(
            f"/admin/users/edit_user/{focal.id}",
            data={"email": focal.email, "name": focal.name, "profile_color": "#3B82F6"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        db_session.expire_all()
        assert db_session.get(User, focal.id).assignment_access_mode == "selected"


class TestEditAssignmentSavesRoles:
    @pytest.fixture
    def admin(self, db_session, scenario):
        role = _make_role(db_session, _ADMIN_PERMS, name="Assignments admin")
        return _user_with_roles(db_session, [role, scenario["finance_role"]])

    def _post(self, client, assignment, **extra):
        data = {
            "template_id": assignment.template_id,
            "period_name": assignment.period_name,
            "allowed_roles_submitted": "1",
        }
        data.update(extra)
        return client.post(
            f"/admin/assignments/edit/{assignment.id}", data=data, follow_redirects=False
        )

    def test_saves_allowed_roles(self, client, db_session, scenario, admin):
        assignment = db_session.get(AssignedForm, scenario["aes_2"].assigned_form_id)
        login_session(client, admin.id)
        resp = self._post(client, assignment, allowed_role_ids=[str(scenario["finance_role"].id)])
        assert resp.status_code in (302, 303), resp.data.decode()[:500]
        db_session.expire_all()
        refreshed = db_session.get(AssignedForm, assignment.id)
        assert [r.id for r in refreshed.allowed_roles] == [scenario["finance_role"].id]

    def test_clearing_roles_reopens_assignment(self, client, db_session, scenario, admin):
        assignment = db_session.get(AssignedForm, scenario["aes_2"].assigned_form_id)
        _restrict_to_roles(db_session, assignment.id, [scenario["finance_role"]])
        login_session(client, admin.id)
        resp = self._post(client, assignment)
        assert resp.status_code in (302, 303)
        db_session.expire_all()
        assert list(db_session.get(AssignedForm, assignment.id).allowed_roles) == []

    def test_without_permission_roles_are_not_changed(self, client, db_session, scenario):
        role = _make_role(
            db_session,
            tuple(p for p in _ADMIN_PERMS if p != "admin.assignments.access.manage"),
            name="No access admin",
        )
        admin = _user_with_roles(db_session, [role])
        assignment = db_session.get(AssignedForm, scenario["aes_2"].assigned_form_id)
        login_session(client, admin.id)
        resp = self._post(client, assignment, allowed_role_ids=[str(scenario["finance_role"].id)])
        assert resp.status_code in (302, 303)
        db_session.expire_all()
        assert list(db_session.get(AssignedForm, assignment.id).allowed_roles) == []
