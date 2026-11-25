"""DREF reporting assignments are limited to the Emergency Operations access group."""

from __future__ import annotations

from datetime import date

import pytest

from app.extensions import db
from app.models.assignments import AssignedForm
from app.models.rbac import ROLE_KIND_GROUP, RbacRole, RbacUserRole
from app.services.assignments.access_service import invalidate_cache, user_can_access_assigned_form
from plugins.emergency_operations_monitoring.models import DrefOperation, DrefPeriod
from plugins.emergency_operations_monitoring.plugin import EmergencyOperationsMonitoringPlugin
from plugins.emergency_operations_monitoring.services.access_group import (
    GROUP_CODE,
    GROUP_NAME,
    attach_dref_audience,
    ensure_dref_access_group,
    restrict_dref_assignments,
)
from plugins.emergency_operations_monitoring.services.go_sync import apply_rows
from plugins.emergency_operations_monitoring.services.plans import validate_plan
from plugins.emergency_operations_monitoring.tests.test_projects import _manager, _row
from tests.factories import create_test_country, create_test_user

pytestmark = pytest.mark.db


@pytest.fixture
def seeded(db_session):
    import plugins.emergency_operations_monitoring.models  # noqa: F401

    create_test_country(db_session, name="Zedland", iso3="ZZZ", region="Test")
    user = create_test_user(db_session, email="dref-group@example.com")
    return user


def test_the_group_is_created_once_and_an_existing_name_is_kept(seeded):
    del seeded
    named = RbacRole(code="custom_dref_group", name="Emergency Operations", description="Already there", kind=ROLE_KIND_GROUP)
    db.session.add(named)
    db.session.commit()
    found = ensure_dref_access_group()
    assert found.id == named.id
    assert RbacRole.query.filter(db.func.lower(RbacRole.name) == "emergency operations", RbacRole.kind == ROLE_KIND_GROUP).count() == 1

    db.session.delete(named)
    db.session.commit()
    created = ensure_dref_access_group()
    again = ensure_dref_access_group()
    assert created.id == again.id
    assert created.code == GROUP_CODE
    assert created.name == GROUP_NAME
    assert created.kind == ROLE_KIND_GROUP


def test_reporting_assignments_require_the_dref_group(seeded):
    user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    cycles = AssignedForm.query.filter_by(project_id=operation.project_id, scope="project_cycle").all()
    assert cycles
    group = RbacRole.query.filter_by(code=GROUP_CODE).one()
    assert all(group in cycle.allowed_roles for cycle in cycles)

    outsider = create_test_user(db.session, email="outsider-dref@example.com")
    insider = create_test_user(db.session, email="insider-dref@example.com")
    manager = create_test_user(db.session, email="manager-dref@example.com", role="system_manager")
    db.session.add(RbacUserRole(user_id=insider.id, role_id=group.id))
    db.session.commit()
    invalidate_cache()

    assignment_id = cycles[0].id
    assert user_can_access_assigned_form(outsider, assignment_id) is False
    assert user_can_access_assigned_form(insider, assignment_id) is True
    assert user_can_access_assigned_form(manager, assignment_id) is True


def test_an_assignment_opened_earlier_gains_the_group(seeded):
    user = seeded
    apply_rows([_row(appeal_code="MDRZZ008", id="Dref-8")])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ008").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    period = DrefPeriod.query.filter_by(operation_id=operation.id).first()
    assignment = db.session.get(AssignedForm, period.assigned_form_id)
    assignment.allowed_roles = []
    db.session.commit()
    assert restrict_dref_assignments() == 1
    db.session.refresh(assignment)
    assert any(role.name == GROUP_NAME for role in assignment.allowed_roles)
    assert attach_dref_audience(assignment) is False


def test_only_dref_projects_require_the_group(seeded):
    del seeded
    plugin = EmergencyOperationsMonitoringPlugin()

    class Project:
        portfolio = "NSD"

    assert plugin.project_report_audience(Project(), "Y1Q1") == []
    Project.portfolio = "Emergency Operations"
    role_ids = plugin.project_report_audience(Project(), "2026-01")
    group = RbacRole.query.filter_by(code=GROUP_CODE).one()
    assert role_ids == [group.id]
