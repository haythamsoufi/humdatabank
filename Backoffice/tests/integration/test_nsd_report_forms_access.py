"""NSD funds plugin: NSD assignments are scoped with Access Groups (``rbac_role.kind = 'group'``)."""

from collections import defaultdict

import pytest

from app.models import AssignedForm
from app.models.rbac import RbacRole, RbacUserRole
from app.services.assignments import access_service
from plugins.nsd_report_forms.importer import apply as nsd_apply
from plugins.nsd_report_forms.importer import restrictions
from plugins.nsd_report_forms.plugin import NSD_ADMIN_ROLE, NSD_GROUP_FOCAL, NSD_GROUP_PM
from tests.factories import (
    _ensure_permission,
    _grant_entity_permission,
    create_test_assignment_entity_status,
    create_test_country,
    create_test_template,
    create_test_user,
)
from app.models.rbac import RbacRolePermission

_WORK_PERMS = ("assignment.view", "assignment.enter", "assignment.submit")


def _role(db_session, code, perms=()):
    role = RbacRole.query.filter_by(code=code).first()
    if role is None:
        role = RbacRole(code=code, name=code, kind="permission")
        db_session.add(role)
        db_session.flush()
        for perm in perms:
            db_session.add(RbacRolePermission(role_id=role.id, permission_id=_ensure_permission(db_session, perm)))
        db_session.commit()
    return role


def _user(db_session, role_codes):
    user = create_test_user(db_session, role="user")
    for link in list(RbacUserRole.query.filter_by(user_id=user.id)):
        db_session.delete(link)
    for code in role_codes:
        db_session.add(RbacUserRole(user_id=user.id, role_id=RbacRole.query.filter_by(code=code).one().id))
    db_session.commit()
    return user


def _held(db_session, user):
    return {
        code
        for (code,) in db_session.query(RbacRole.code)
        .join(RbacUserRole, RbacUserRole.role_id == RbacRole.id)
        .filter(RbacUserRole.user_id == user.id)
    }


def _runner():
    """A Run without a workbook: only the access helpers are used."""
    run = object.__new__(nsd_apply.Run)
    run.roles, run.stats = {}, defaultdict(int)
    return run


@pytest.fixture
def nsd(db_session, app):
    """The NSD roles, the NSD Access Groups made by the plugin, a country and two NSD assignments on it."""
    admin_role = _role(db_session, NSD_ADMIN_ROLE)
    roles = restrictions.load_roles()
    restrictions.ensure_groups(roles)
    db_session.commit()

    country = create_test_country(db_session)
    quarter = create_test_assignment_entity_status(
        db_session, country=country, template=create_test_template(db_session), period_name="REF-1 Y1Q1")
    final = create_test_assignment_entity_status(
        db_session, country=country, template=create_test_template(db_session), period_name="REF-1 Final")
    roles = restrictions.load_roles()
    restrictions.restrict(db_session.get(AssignedForm, quarter.assigned_form_id), "CBF quarter", roles)
    restrictions.restrict(db_session.get(AssignedForm, final.assigned_form_id), "CBF final report", roles)
    db_session.commit()
    access_service.invalidate_cache()
    return {"country": country, "quarter": quarter, "final": final, "admin_role": admin_role}


def _can(user, aes):
    access_service.invalidate_cache()
    return access_service.user_can_access_assigned_form(user, aes.assigned_form_id)


class TestAccessGroups:
    def test_groups_are_created_once_as_access_groups(self, db_session, nsd):
        again = restrictions.ensure_groups(restrictions.load_roles())
        assert again == 0
        for code in (NSD_GROUP_FOCAL, NSD_GROUP_PM):
            group = RbacRole.query.filter_by(code=code).one()
            assert group.kind == "group"

    def test_assignments_list_groups_not_permission_roles(self, db_session, nsd):
        quarter = db_session.get(AssignedForm, nsd["quarter"].assigned_form_id)
        final = db_session.get(AssignedForm, nsd["final"].assigned_form_id)
        assert {r.code for r in quarter.allowed_roles} == {NSD_GROUP_FOCAL, NSD_GROUP_PM, NSD_ADMIN_ROLE}
        assert {r.code for r in final.allowed_roles} == {NSD_GROUP_PM, NSD_ADMIN_ROLE}

    def test_restricting_twice_adds_nothing(self, db_session, nsd):
        quarter = db_session.get(AssignedForm, nsd["quarter"].assigned_form_id)
        assert restrictions.restrict(quarter, "CBF quarter", restrictions.load_roles()) is False


class TestWhoReachesWhat:
    def test_focal_group_reaches_quarterly_only(self, db_session, nsd):
        user = _user(db_session, [NSD_GROUP_FOCAL])
        _grant_entity_permission(db_session, user, "country", nsd["country"].id)
        assert _can(user, nsd["quarter"])
        assert not _can(user, nsd["final"])

    def test_pm_group_reaches_quarterly_and_final(self, db_session, nsd):
        user = _user(db_session, [NSD_GROUP_PM])
        _grant_entity_permission(db_session, user, "country", nsd["country"].id)
        assert _can(user, nsd["quarter"])
        assert _can(user, nsd["final"])

    def test_ordinary_country_focal_reaches_no_nsd_report(self, db_session, nsd):
        ordinary = _role(db_session, "ordinary_focal_for_nsd_test", _WORK_PERMS)
        user = _user(db_session, [ordinary.code])
        _grant_entity_permission(db_session, user, "country", nsd["country"].id)
        assert not _can(user, nsd["quarter"])
        assert not _can(user, nsd["final"])


class TestGrantingMembership:
    def test_focal_contact_gets_role_and_group(self, db_session, nsd):
        user = create_test_user(db_session, role="user")
        _runner().ensure_role(user.id, NSD_GROUP_FOCAL)
        db_session.commit()
        assert NSD_GROUP_FOCAL in _held(db_session, user)
        assert NSD_GROUP_PM not in _held(db_session, user)

    def test_pm_contact_replaces_focal_group(self, db_session, nsd):
        user = create_test_user(db_session, role="user")
        run = _runner()
        run.ensure_role(user.id, NSD_GROUP_FOCAL)
        run.ensure_role(user.id, NSD_GROUP_PM)
        db_session.commit()
        held = _held(db_session, user)
        assert NSD_GROUP_PM in held
        assert NSD_GROUP_FOCAL not in held

    def test_focal_contact_keeps_pm_group(self, db_session, nsd):
        user = create_test_user(db_session, role="user")
        run = _runner()
        run.ensure_role(user.id, NSD_GROUP_PM)
        run.ensure_role(user.id, NSD_GROUP_FOCAL)
        db_session.commit()
        held = _held(db_session, user)
        assert NSD_GROUP_PM in held
        assert NSD_GROUP_FOCAL not in held

    def test_system_manager_gets_nothing_extra(self, db_session, nsd):
        user = create_test_user(db_session, role="system_manager")
        _runner().ensure_role(user.id, NSD_GROUP_PM)
        db_session.commit()
        assert NSD_GROUP_PM not in _held(db_session, user)
