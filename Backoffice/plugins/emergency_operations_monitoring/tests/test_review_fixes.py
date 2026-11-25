"""Guards found in the plugin review: import bounds, settings round trip, scope, and send locking."""

from __future__ import annotations

import zipfile
from datetime import date, timedelta
from io import BytesIO

import openpyxl
import pytest

from app.extensions import db
from plugins.emergency_operations_monitoring.access import Actor
from plugins.emergency_operations_monitoring.models import (
    DrefChangeRequest,
    DrefDelay,
    DrefDraft,
    DrefOperation,
)
from plugins.emergency_operations_monitoring.services.excel_import import (
    WorkbookRejected,
    import_activities,
    parse_workbook,
)
from plugins.emergency_operations_monitoring.services.go_sync import FeedRows, apply_rows, fetch_rows
from plugins.emergency_operations_monitoring.services.periods import escalation_level
from plugins.emergency_operations_monitoring.services.plans import activities_for, groups_for, latest_plan
from plugins.emergency_operations_monitoring.tests.test_workflow import _manager, _row, seeded  # noqa: F401

HEADER = ["Group", "Activity", "Indicator", "Indicator type", "Target", "Unit", "Budget CHF", "Start", "End"]


def _book(*rows) -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Activities"
    sheet.append(HEADER)
    for row in rows:
        sheet.append(list(row))
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _operation() -> DrefOperation:
    apply_rows([_row()])
    return DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()


# --- Excel import ---------------------------------------------------------------------------


@pytest.mark.db
def test_import_takes_the_sector_ceilings_from_go_not_from_the_sheet(seeded):
    _country, user = seeded
    operation = _operation()
    raw = _book(["Health", "Distribute kits", "Kits delivered", "output", 10, "kits", 500, "2026-01-02", "2026-02-01"])
    result = import_activities(operation, raw, _manager(user.id), date(2026, 1, 10))
    assert result["ok"] is True
    group = groups_for(latest_plan(operation.id).id)[0]
    assert group.key == "health"
    assert group.budget_chf == 8000
    assert group.people_targeted == 80


@pytest.mark.db
def test_import_refuses_a_sector_budget_above_the_approved_one_and_keeps_the_plan(seeded):
    _country, user = seeded
    operation = _operation()
    plan_before = latest_plan(operation.id)
    groups_before = [group.id for group in groups_for(plan_before.id)]
    raw = _book(["Health", "Too much", "", "", "", "", 9000, "2026-01-02", "2026-02-01"])
    result = import_activities(operation, raw, _manager(user.id), date(2026, 1, 10))
    assert result["ok"] is False
    assert "8,000.00" in result["error"]
    plan_after = latest_plan(operation.id)
    assert plan_after.id == plan_before.id
    assert [group.id for group in groups_for(plan_after.id)] == groups_before


@pytest.mark.db
def test_import_refuses_an_unknown_sector_and_negative_amounts(seeded):
    _country, user = seeded
    operation = _operation()
    unknown = import_activities(
        operation, _book(["Space program", "Launch", "", "", "", "", 10, "", ""]), _manager(user.id), date(2026, 1, 10)
    )
    assert unknown["ok"] is False and "Space program" in unknown["error"]
    negative = import_activities(
        operation, _book(["Health", "Refund", "", "", "", "", -5, "", ""]), _manager(user.id), date(2026, 1, 10)
    )
    assert negative["ok"] is False and "Refund" in negative["error"]
    backwards = import_activities(
        operation, _book(["Health", "Backwards", "", "", "", "", 5, "2026-03-01", "2026-02-01"]), _manager(user.id), date(2026, 1, 10)
    )
    assert backwards["ok"] is False


@pytest.mark.db
def test_import_drops_change_requests_that_pointed_at_the_replaced_draft(seeded):
    _country, user = seeded
    operation = _operation()
    plan = latest_plan(operation.id)
    activity = activities_for(groups_for(plan.id)[0].id)[0]
    db.session.add(
        DrefChangeRequest(
            operation_id=operation.id,
            plan_id=plan.id,
            target_type="activity",
            target_id=activity.id,
            field="end_date",
            old_value="2026-06-30",
            new_value="2026-08-01",
            status="pending",
            justification="Longer season",
        )
    )
    db.session.commit()
    raw = _book(["Health", "Distribute kits", "", "", "", "", 500, "2026-01-02", "2026-02-01"])
    assert import_activities(operation, raw, _manager(user.id), date(2026, 1, 10))["ok"] is True
    assert DrefChangeRequest.query.filter_by(operation_id=operation.id, field="end_date").count() == 0


def test_a_workbook_that_expands_past_the_limit_is_rejected_before_it_is_read(monkeypatch):
    import plugins.emergency_operations_monitoring.services.excel_import as module

    monkeypatch.setattr(module, "MAX_UNCOMPRESSED_BYTES", 1000)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/big.xml", "a" * 50_000)
    with pytest.raises(WorkbookRejected):
        parse_workbook(buffer.getvalue())
    with pytest.raises(WorkbookRejected):
        parse_workbook(b"not a zip at all")


def test_a_workbook_with_too_many_rows_is_rejected(monkeypatch):
    import plugins.emergency_operations_monitoring.services.excel_import as module

    monkeypatch.setattr(module, "MAX_ROWS", 3)
    raw = _book(*[["Health", f"Activity {n}", "", "", "", "", 1, "", ""] for n in range(6)])
    with pytest.raises(WorkbookRejected):
        parse_workbook(raw)


# --- Settings -------------------------------------------------------------------------------


@pytest.mark.db
def test_a_settings_api_round_trip_keeps_ai_and_the_schedule(app, db_session):
    from plugins.emergency_operations_monitoring.config_store import ai_enabled, save_posted_settings, schedule_settings
    from plugins.emergency_operations_monitoring.routes import settings_status

    save_posted_settings(
        {
            "plan_validation_days": "10",
            "reminder_days_before": "2",
            "escalation_validate_days": "4",
            "escalation_review_days": "8",
            "escalation_portfolio_days": "15",
            "ai_enabled": "1",
            "ai_language": "fr",
        }
    )
    assert ai_enabled() is True
    payload = settings_status()
    save_posted_settings(payload, partial=True)
    assert ai_enabled() is True
    assert schedule_settings()["plan_validation_days"] == 10
    assert schedule_settings()["escalation_portfolio_days"] == 15
    assert payload["ai_language"] == "fr"


@pytest.mark.db
def test_a_partial_settings_update_touches_only_the_keys_given(app, db_session):
    from plugins.emergency_operations_monitoring.config_store import ai_enabled, save_posted_settings, schedule_settings

    save_posted_settings({"plan_validation_days": "10", "ai_enabled": "1", "ai_language": "es"})
    save_posted_settings({"reminder_days_before": "5"}, partial=True)
    assert schedule_settings()["reminder_days_before"] == 5
    assert schedule_settings()["plan_validation_days"] == 10
    assert ai_enabled() is True
    save_posted_settings({"ai_enabled": False}, partial=True)
    assert ai_enabled() is False
    # The HTML form leaves an unchecked box out, which is an off switch.
    save_posted_settings({"ai_enabled": "1"})
    save_posted_settings({"plan_validation_days": "10"})
    assert ai_enabled() is False


@pytest.mark.db
def test_zero_days_is_kept_and_not_replaced_by_the_default(app, db_session):
    from plugins.emergency_operations_monitoring.config_store import save_posted_settings, schedule_settings

    save_posted_settings({"escalation_validate_days": "0", "reminder_days_before": "0"})
    assert schedule_settings()["escalation_validate_days"] == 0
    assert schedule_settings()["reminder_days_before"] == 0


def test_escalation_level_honours_zero_days():
    settings = {
        "reminder_days_before": 0,
        "escalation_validate_days": 0,
        "escalation_review_days": 7,
        "escalation_portfolio_days": 14,
    }
    due = date(2026, 3, 1)
    assert escalation_level(due - timedelta(days=1), due, False, settings) is None
    assert escalation_level(due, due, False, settings) == "reminder"
    assert escalation_level(due + timedelta(days=1), due, False, settings) == "validate"
    assert escalation_level(due + timedelta(days=8), due, False, settings) == "review"
    assert escalation_level(due + timedelta(days=1), due, True, settings) is None


# --- Scope ----------------------------------------------------------------------------------


class _Op:
    def __init__(self, op_id, country_id):
        self.id = op_id
        self.country_id = country_id


def _actor(permissions=(), countries=(), memberships=None, manager=False):
    return Actor(1, manager, frozenset(permissions), frozenset(countries), dict(memberships or {}))


def test_a_role_without_country_or_membership_sees_nothing():
    actor = _actor(["admin.emergency_operations_monitoring.enter"])
    assert actor.rank_on(_Op(1, 5)) == 0
    assert actor.allows(_Op(1, 5), "view") is False


def test_country_access_gives_the_role_rank_and_only_in_that_country():
    actor = _actor(["admin.emergency_operations_monitoring.validate"], countries=[5])
    assert actor.rank_on(_Op(1, 5)) == 2
    assert actor.allows(_Op(1, 5), "validate") is True
    assert actor.allows(_Op(1, 5), "review") is False
    assert actor.rank_on(_Op(2, 6)) == 0


def test_a_membership_narrows_a_higher_role_and_never_raises_it():
    review = "admin.emergency_operations_monitoring.review"
    narrowed = _actor([review], countries=[5], memberships={1: "enter"})
    assert narrowed.rank_on(_Op(1, 5)) == 3  # country access keeps the full role
    outside = _actor([review], memberships={1: "enter"})
    assert outside.rank_on(_Op(1, 9)) == 1  # membership alone is capped at its tier
    low_role = _actor(["admin.emergency_operations_monitoring.enter"], memberships={1: "portfolio"})
    assert low_role.rank_on(_Op(1, 9)) == 1  # a tier cannot raise the role
    nobody = _actor([], memberships={1: "portfolio"})
    assert nobody.rank_on(_Op(1, 9)) == 0  # no role, no access


def test_portfolio_and_managers_see_every_operation():
    assert _actor(["admin.emergency_operations_monitoring.portfolio"]).rank_on(_Op(1, 9)) == 4
    assert _actor(manager=True).rank_on(_Op(1, 9)) == 4


@pytest.mark.db
def test_only_people_with_a_dref_role_can_be_added_as_members(seeded):
    from app.models.rbac import RbacPermission, RbacRole, RbacRolePermission, RbacUserRole
    from plugins.emergency_operations_monitoring.access import capable_users_query
    from plugins.emergency_operations_monitoring.services.plans import set_member
    from tests.factories import create_test_user

    _country, user = seeded
    operation = _operation()
    reviewer = _manager(user.id)
    plain = create_test_user(db.session, email="plain-dref@example.com")
    assert "no Emergency Operations role" in set_member(operation, plain.id, "enter", reviewer)

    permission = RbacPermission.query.filter_by(code="admin.emergency_operations_monitoring.enter").first()
    if permission is None:
        permission = RbacPermission(code="admin.emergency_operations_monitoring.enter", name="DREF enter")
        db.session.add(permission)
        db.session.flush()
    role = RbacRole(code="dref_test_role", name="DREF test role")
    db.session.add(role)
    db.session.flush()
    db.session.add(RbacRolePermission(role_id=role.id, permission_id=permission.id))
    db.session.add(RbacUserRole(user_id=plain.id, role_id=role.id))
    db.session.commit()
    assert plain.id in {row.id for row in capable_users_query().all()}
    assert set_member(operation, plain.id, "enter", reviewer) is None


# --- Delays ---------------------------------------------------------------------------------


@pytest.mark.db
def test_a_delay_cannot_point_at_another_operations_activity_or_report(seeded):
    from plugins.emergency_operations_monitoring.services.reporting import add_delay

    _country, user = seeded
    apply_rows([_row(), _row(id="Dref-2", appeal_code="MDRZZ002", disaster_name="Other flood")])
    mine = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    other = DrefOperation.query.filter_by(appeal_code="MDRZZ002").one()
    actor = _manager(user.id)
    other_activity = activities_for(groups_for(latest_plan(other.id).id)[0].id)[0]
    own_activity = activities_for(groups_for(latest_plan(mine.id).id)[0].id)[0]
    assert add_delay(mine, {"reason": "Rain", "activity_id": str(other_activity.id)}, actor) == "Activity not found."
    assert add_delay(mine, {"reason": "Rain", "activity_id": "999999"}, actor) == "Activity not found."
    assert add_delay(mine, {"reason": "Rain", "report_id": "999999"}, actor) == "Report not found."
    assert DrefDelay.query.filter_by(operation_id=mine.id).count() == 0
    assert add_delay(mine, {"reason": "Rain", "activity_id": str(own_activity.id)}, actor) is None
    assert DrefDelay.query.filter_by(operation_id=mine.id).count() == 1


# --- Sending to GO --------------------------------------------------------------------------


@pytest.mark.db
def test_a_report_that_is_being_sent_is_not_posted_a_second_time(seeded):
    from flask import current_app

    from plugins.emergency_operations_monitoring.services.go_submit import submit_draft
    from app.utils.common.datetime_helpers import utcnow

    _country, user = seeded
    operation = _operation()
    draft = DrefDraft(
        operation_id=operation.id,
        report_kind="operational_update",
        input_hash="x",
        sections={},
        status="validated",
        go_status="sending",
        go_submitted_at=utcnow(),
    )
    db.session.add(draft)
    db.session.commit()
    current_app.config["GO_API_TOKEN"] = "secret-token"
    try:
        busy = submit_draft(
            operation, draft, post=lambda *args: (_ for _ in ()).throw(AssertionError("posted while sending"))
        )
        assert busy["ok"] is False
        assert "already being sent" in busy["error"]

        draft.go_submitted_at = utcnow() - timedelta(minutes=30)
        db.session.commit()
        sent = submit_draft(operation, draft, post=lambda *args: (201, '{"id": 7}'))
        assert sent["ok"] is True and sent["reference"] == "7"
        assert draft.go_status == "sent"
    finally:
        current_app.config["GO_API_TOKEN"] = ""


# --- GO sync --------------------------------------------------------------------------------


def test_the_feed_reports_when_the_page_cap_stopped_the_read(monkeypatch):
    import plugins.emergency_operations_monitoring.services.go_sync as module

    monkeypatch.setattr(module, "_MAX_PAGES", 2)
    monkeypatch.setattr(module, "_PAGE_LIMIT", 1)

    def http_get(url, params):
        return [{"id": str(params["offset"])}]

    rows = fetch_rows(http_get, "https://example.test/dref3/")
    assert isinstance(rows, FeedRows)
    assert len(rows) == 2 and rows.truncated is True
    assert fetch_rows(lambda url, params: [], "https://example.test/dref3/").truncated is False


@pytest.mark.db
def test_one_appeal_that_fails_to_save_does_not_stop_the_others(seeded, monkeypatch):
    import plugins.emergency_operations_monitoring.services.go_sync as module

    real = module.sync_plan

    def flaky(operation, baseline, previous, today):
        if operation.appeal_code == "MDRBAD01":
            raise RuntimeError("bad appeal")
        return real(operation, baseline, previous, today)

    monkeypatch.setattr(module, "sync_plan", flaky)
    summary = apply_rows(
        [
            _row(id="Dref-bad", appeal_code="MDRBAD01", disaster_name="Bad"),
            _row(id="Dref-good", appeal_code="MDRGOOD1", disaster_name="Good"),
        ]
    )
    assert summary["failed"] == 1
    assert summary["failed_codes"] == ["MDRBAD01"]
    assert summary["created"] == 1
    assert DrefOperation.query.filter_by(appeal_code="MDRGOOD1").count() == 1
    assert DrefOperation.query.filter_by(appeal_code="MDRBAD01").count() == 0


# --- Draft model name -----------------------------------------------------------------------


def test_the_recorded_model_is_the_one_the_call_uses(app):
    from flask import current_app

    from plugins.emergency_operations_monitoring.services.llm import DEFAULT_MODEL, configured_model

    previous = current_app.config.get("OPENAI_MODEL")
    try:
        current_app.config["OPENAI_MODEL"] = ""
        assert configured_model() == DEFAULT_MODEL
        current_app.config["OPENAI_MODEL"] = "gpt-test"
        assert configured_model() == "gpt-test"
    finally:
        current_app.config["OPENAI_MODEL"] = previous


# --- Cycle form targets ---------------------------------------------------------------------


def test_a_target_is_written_only_to_the_section_it_was_posted_for():
    from plugins.emergency_operations_monitoring.services.entry_activities import _rows_in_section

    class _Group:
        def __init__(self, key):
            self.key = key

    rows = [("a", _Group("health")), ("b", _Group("education")), ("c", _Group("early_response:health"))]
    assert [item for item, _group in _rows_in_section(rows, "health")] == ["a", "c"]
    assert [item for item, _group in _rows_in_section(rows, "education")] == ["b"]
