"""A validated plan becomes one project and one cycle per reporting period."""

from __future__ import annotations

from datetime import date

import pytest

from app.extensions import db
from app.models.assignments import AssignedForm, AssignmentEntityStatus
from app.models.enums import AssignmentEntityStatusValue
from app.models.projects import Project
from plugins.emergency_operations_monitoring.access import Actor
from plugins.emergency_operations_monitoring.fields import DrefOperationalReportField
from plugins.emergency_operations_monitoring.models import (
    DrefActivityUpdate,
    DrefIndicatorValue,
    DrefOperation,
    DrefPeriod,
    DrefReport,
)
from plugins.emergency_operations_monitoring.services.assignment_sync import assignment_url, register_assignment_sync
from plugins.emergency_operations_monitoring.services.go_sync import apply_rows
from plugins.emergency_operations_monitoring.services.plans import activities_for, groups_for, indicators_for_activity, latest_plan, validate_plan
from plugins.emergency_operations_monitoring.services.project_link import backfill_projects, open_cycles
from plugins.emergency_operations_monitoring.services.reporting import apply_cycle_payload
from tests.factories import create_test_country, create_test_user

pytestmark = pytest.mark.db

register_assignment_sync()


def _row(**overrides):
    base = {
        "id": "Dref-1",
        "appeal_code": "MDRZZ001",
        "appeal_type": "DREF",
        "pillar": "Response",
        "country": "Zedland",
        "country_iso3": "ZZZ",
        "disaster_definition": "Flood",
        "disaster_name": "Zedland Flood",
        "total_approved": 10000,
        "amount_approved": 10000,
        "people_targeted": 100,
        "start_date_of_operation": "2026-01-01",
        "end_date_of_operation": "2026-06-30",
        "operation_timeframe": 6,
        "operation_status": "active",
        "is_latest_stage": True,
        "sector_health": True,
        "sector_health_budget": 8000,
        "sector_health_people_targeted": 80,
        "date_of_approval": "2026-01-05",
    }
    base.update(overrides)
    return base


def _manager(user_id):
    return Actor(user_id, True, frozenset(), frozenset(), {})


@pytest.fixture
def seeded(db_session):
    import plugins.emergency_operations_monitoring.models  # noqa: F401

    country = create_test_country(db_session, name="Zedland", iso3="ZZZ", region="Test")
    user = create_test_user(db_session, email="dref-project@example.com")
    return country, user


def _cycles(project_id: int) -> list[AssignedForm]:
    return AssignedForm.query.filter_by(project_id=project_id, scope="project_cycle").all()


def test_sync_creates_a_project_and_validation_opens_one_cycle_per_period(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    project = db.session.get(Project, operation.project_id)
    assert project.reference == "MDRZZ001"
    assert project.portfolio == "Emergency Operations"
    assert project.fund == "DREF"
    assert project.title == "Zedland Flood"
    assert project.status == "Open"
    assert project.country_id == operation.country_id
    assert project.plan_data["dref_operation_id"] == operation.id
    assert int(project.amount_granted) == 10000
    assert DrefPeriod.query.filter_by(operation_id=operation.id).count() == 0

    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    operation = db.session.get(DrefOperation, operation.id)
    periods = DrefPeriod.query.filter_by(operation_id=operation.id).order_by(DrefPeriod.sequence).all()
    assert len(periods) == 6
    cycles = _cycles(operation.project_id)
    assert len(cycles) == 6
    assert {period.assigned_form_id for period in periods} == {cycle.id for cycle in cycles}
    assert any(cycle.period_name == "MDRZZ001 · 2026-01" for cycle in cycles)
    assert all(cycle.period_start and cycle.period_end and cycle.project_id == operation.project_id for cycle in cycles)

    assert open_cycles(operation) == 0
    assert len(_cycles(operation.project_id)) == 6
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 11)) == "The plan is already validated."
    assert len(_cycles(operation.project_id)) == 6


def test_the_same_month_gets_a_distinct_cycle_label(seeded):
    _country, user = seeded
    apply_rows(
        [
            _row(
                id="Dref-im",
                appeal_code="MDRIM009",
                appeal_type="i-DREF",
                pillar="Anticipatory",
                start_date_of_operation="2026-01-01",
                end_date_of_operation="2026-02-10",
                operation_timeframe=1,
            )
        ]
    )
    operation = DrefOperation.query.filter_by(appeal_code="MDRIM009").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    project = db.session.get(Project, operation.project_id)
    assert project.fund == "i-DREF"
    names = [row.period_name for row in _cycles(project.id)]
    assert len(names) == len(set(names)) == 3
    assert "MDRIM009 · 2026-01" in names
    assert any(name.startswith("MDRIM009 · 2026-01-") for name in names)


def test_an_operation_without_a_country_stays_off_the_project_list(seeded):
    _country, user = seeded
    apply_rows([_row(id="Dref-qq", appeal_code="MDRQQ001", country_iso3="QQQ")])
    operation = DrefOperation.query.filter_by(appeal_code="MDRQQ001").one()
    assert operation.country_id is None
    assert operation.project_id is None
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    operation = db.session.get(DrefOperation, operation.id)
    assert operation.project_id is None
    periods = DrefPeriod.query.filter_by(operation_id=operation.id).all()
    assert periods
    assert all(period.assigned_form_id is None for period in periods)
    assert Project.query.filter_by(reference="MDRQQ001").count() == 0


def test_closing_the_operation_closes_the_project_cycles(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    apply_rows(
        [
            _row(is_latest_stage=False, id="Dref-1"),
            _row(
                id="DrefFinalReport-2",
                stage="Final Report",
                operation_status="closed",
                is_latest_stage=True,
                date_of_approval="2026-06-01",
            ),
        ]
    )
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    project = db.session.get(Project, operation.project_id)
    assert project.status == "Closed"
    assert project.is_open is False
    assert _cycles(project.id)
    assert all(cycle.is_closed for cycle in _cycles(project.id))


def test_saving_a_cycle_stores_the_report_and_submit_moves_its_status(seeded, app):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    period = DrefPeriod.query.filter_by(operation_id=operation.id).order_by(DrefPeriod.sequence).first()
    group = groups_for(latest_plan(operation.id).id)[0]
    activity = activities_for(group.id)[0]
    indicator = indicators_for_activity(activity.id)[0]
    payload = {
        "narrative": "Kits moved",
        "activities": {
            str(activity.id): {
                "status": "ongoing",
                "percent": 40,
                "households": 3,
                "individuals": 10,
                "women": 4,
                "men": 3,
                "girls": 2,
                "boys": 1,
                "expenditure": "25.50",
            }
        },
        "indicators": {str(indicator.id): {"actual": "9"}},
    }
    aes = AssignmentEntityStatus.query.filter_by(assigned_form_id=period.assigned_form_id).one()
    with app.test_request_context(f"/assignment/{aes.id}"):
        from flask import request

        request.view_args = {"aes_id": aes.id}
        assert DrefOperationalReportField().normalize_value(payload, {}) is None
    db.session.commit()
    report = DrefReport.query.filter_by(period_id=period.id).one()
    assert report.status == "draft"
    assert report.narrative == "Kits moved"
    assert int(report.expenditure_total) == 25
    update = DrefActivityUpdate.query.filter_by(report_id=report.id, activity_id=activity.id).one()
    assert update.status == "ongoing"
    assert update.percent == 40
    assert update.people_households == 3
    assert update.disaggregation["women"] == 4
    assert DrefIndicatorValue.query.filter_by(report_id=report.id, indicator_id=indicator.id).one().actual == 9
    assert assignment_url(operation.id, period) == f"/assignment/{aes.id}"

    refused = apply_cycle_payload(
        operation,
        period,
        {"activities": {str(activity.id): {"expenditure": "-1"}}},
        user.id,
    )
    assert "Expenditure cannot be negative." in refused
    assert activity.title in refused

    aes.status = AssignmentEntityStatusValue.submitted
    aes.status_changed_by_user_id = user.id
    db.session.commit()
    report = db.session.get(DrefReport, report.id)
    assert report.status == "submitted"
    assert report.submitted_by_user_id == user.id
    assert period.status == "submitted" or db.session.get(DrefPeriod, period.id).status == "submitted"

    aes.status = AssignmentEntityStatusValue.approved
    aes.status_changed_by_user_id = user.id
    db.session.commit()
    report = db.session.get(DrefReport, report.id)
    assert report.status == "validated"
    assert report.validated_by_user_id == user.id
    assert report.reviewed_at is None

    aes.status = AssignmentEntityStatusValue.requires_revision
    db.session.commit()
    report = db.session.get(DrefReport, report.id)
    assert report.status == "draft"


def test_a_percentage_split_is_stored_as_counts(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    period = DrefPeriod.query.filter_by(operation_id=operation.id).order_by(DrefPeriod.sequence).first()
    activity = activities_for(groups_for(latest_plan(operation.id).id)[0].id)[0]
    saved = apply_cycle_payload(
        operation,
        period,
        {
            "activities": {
                str(activity.id): {
                    "status": "ongoing",
                    "reached": 10,
                    "pct_women": 40,
                    "pct_men": 30,
                    "pct_girls": 20,
                    "pct_boys": 10,
                    "expenditure": "5",
                }
            }
        },
        user.id,
    )
    assert saved is None
    update = DrefActivityUpdate.query.filter_by(activity_id=activity.id).one()
    assert update.people_individuals == 10
    assert update.disaggregation["women"] == 4
    assert update.disaggregation["men"] == 3
    assert update.disaggregation["girls"] == 2
    assert update.disaggregation["boys"] == 1
    assert update.disaggregation_na is False

    refused = apply_cycle_payload(
        operation,
        period,
        {
            "activities": {
                str(activity.id): {
                    "reached": 10,
                    "pct_women": 50,
                    "pct_men": 10,
                    "pct_girls": 10,
                    "pct_boys": 10,
                }
            }
        },
        user.id,
    )
    assert "The percentage split must add up to 100." in refused
    assert activity.title in refused
    assert db.session.get(DrefActivityUpdate, update.id).disaggregation["women"] == 4


def test_skipping_disaggregation_requires_a_reason_and_drops_the_split(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    period = DrefPeriod.query.filter_by(operation_id=operation.id).order_by(DrefPeriod.sequence).first()
    activity = activities_for(groups_for(latest_plan(operation.id).id)[0].id)[0]
    refused = apply_cycle_payload(
        operation,
        period,
        {"activities": {str(activity.id): {"reached": 10, "disaggregation_na": "1", "disaggregation_reason": "  "}}},
        user.id,
    )
    assert "Explain why this data is not available." in refused
    assert activity.title in refused

    saved = apply_cycle_payload(
        operation,
        period,
        {
            "activities": {
                str(activity.id): {
                    "reached": 10,
                    "pct_women": 100,
                    "pct_men": 0,
                    "pct_girls": 0,
                    "pct_boys": 0,
                    "disaggregation_na": "1",
                    "disaggregation_reason": "The register has no age split.",
                }
            }
        },
        user.id,
    )
    assert saved is None
    update = DrefActivityUpdate.query.filter_by(activity_id=activity.id).one()
    assert update.disaggregation_na is True
    assert update.disaggregation["women"] is None
    assert update.disaggregation["reason"] == "The register has no age split."


def test_backfill_replaces_a_missing_project_and_does_not_duplicate_cycles(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    project_id = operation.project_id
    form_ids = [row.id for row in AssignedForm.query.filter_by(project_id=project_id).all()]
    for period in DrefPeriod.query.filter_by(operation_id=operation.id).all():
        period.assigned_form_id = None
    if form_ids:
        AssignmentEntityStatus.query.filter(
            AssignmentEntityStatus.assigned_form_id.in_(form_ids)
        ).delete(synchronize_session=False)
        AssignedForm.query.filter(AssignedForm.id.in_(form_ids)).delete(synchronize_session=False)
    operation.project_id = None
    db.session.flush()
    db.session.delete(db.session.get(Project, project_id))
    db.session.commit()

    summary = backfill_projects()
    assert summary["projects"] >= 1
    assert summary["cycles"] == 6
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    assert operation.project_id
    assert len(_cycles(operation.project_id)) == 6
    again = backfill_projects()
    assert again["cycles"] == 0
    assert len(_cycles(operation.project_id)) == 6
