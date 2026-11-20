"""Plan generation, bounds, rebase, drafts, and escalation against the test database."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import openpyxl
import pytest

from plugins.dref_monitoring.access import Actor
from app.extensions import db
from plugins.dref_monitoring.models import (
    DrefActivityUpdate,
    DrefChangeRequest,
    DrefDateHistory,
    DrefDraft,
    DrefMember,
    DrefOperation,
    DrefPeriod,
    DrefPlan,
    DrefReport,
)
from plugins.dref_monitoring.services.drafts import build_payload, generate_draft
from plugins.dref_monitoring.services.escalation import run_escalation
from plugins.dref_monitoring.services.overview import build_overview
from plugins.dref_monitoring.services.excel_import import import_activities, parse_workbook
from plugins.dref_monitoring.services.go_sync import apply_rows, fetch_rows
from plugins.dref_monitoring.services.plans import (
    activities_for,
    edit_activity,
    groups_for,
    latest_plan,
    save_plan_activities,
    sectors_not_on_plan,
    validate_plan,
)
from tests.factories import create_test_country, create_test_user

pytestmark = pytest.mark.db


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
    import plugins.dref_monitoring.models  # noqa: F401 — register tables before create_all

    country = create_test_country(db_session, name="Zedland", iso3="ZZZ", region="Test")
    user = create_test_user(db_session, email="dref-monitor@example.com")
    return country, user


def test_sync_builds_a_plan_links_the_country_and_blocks_dates_past_approval(seeded):
    country, user = seeded
    summary = apply_rows([_row()])
    assert summary["created"] == 1
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    assert operation.country_id == country.id
    assert operation.reporting_frequency == "monthly"
    plan = latest_plan(operation.id)
    assert plan.status == "draft"
    groups = groups_for(plan.id)
    assert [group.key for group in groups] == ["health"]
    activity = activities_for(groups[0].id)[0]
    actor = _manager(user.id)

    refused = edit_activity(
        operation,
        activity,
        {"end_date": "2026-08-01", "start_date": "2026-01-01", "budget_chf": "8000"},
        actor,
    )
    assert refused["ok"] is False

    pending = edit_activity(
        operation,
        activity,
        {
            "end_date": "2026-08-01",
            "start_date": "2026-01-01",
            "budget_chf": "8000",
            "justification": "The flood season runs longer than the approved end date.",
        },
        actor,
    )
    assert pending["pending"] is True
    db_activity = db.session.get(type(activity), activity.id)
    assert db_activity.end_date == date(2026, 6, 30)
    change = DrefChangeRequest.query.filter_by(operation_id=operation.id, field="end_date").one()
    assert change.status == "pending"

    moved = edit_activity(
        operation,
        db_activity,
        {
            "end_date": "2026-05-01",
            "start_date": "2026-01-01",
            "budget_chf": "8000",
            "justification": "Distribution finished early.",
        },
        actor,
    )
    assert moved["ok"] is True and not moved["pending"]
    assert DrefDateHistory.query.filter_by(activity_id=activity.id, field="end_date").count() == 1


def test_saving_an_unchanged_budget_above_the_sector_does_not_ask_for_sign_off(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    activity = activities_for(groups_for(latest_plan(operation.id).id)[0].id)[0]
    activity.budget_chf = Decimal("9000")
    db.session.commit()
    actor = _manager(user.id)
    kept = edit_activity(
        operation,
        activity,
        {"budget_chf": "9000", "justification": "No change to the budget."},
        actor,
    )
    assert kept["ok"] is True and not kept["pending"]
    assert DrefChangeRequest.query.filter_by(operation_id=operation.id).count() == 0

    raised = edit_activity(
        operation,
        activity,
        {"budget_chf": "9500", "justification": "The sector budget needs to cover this line."},
        actor,
    )
    assert raised["pending"] is True
    assert raised["held"][0]["field"] == "budget_chf"
    assert raised["held"][0]["title"] == activity.title
    assert Decimal(str(raised["held"][0]["value"])) == Decimal("9500")
    assert Decimal(str(raised["held"][0]["limit"])) == Decimal("8000")


class _Posted(dict):
    def getlist(self, key):
        value = self.get(key, [])
        if isinstance(value, list):
            return value
        if value in (None, ""):
            return []
        return [value]


def test_plan_table_saves_every_row_together(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    activity = activities_for(groups_for(latest_plan(operation.id).id)[0].id)[0]
    actor = _manager(user.id)
    fields = {
        "activity_id": [str(activity.id)],
        f"title-{activity.id}": "Clinics",
        f"budget_chf-{activity.id}": "8000",
        f"start_date-{activity.id}": "2026-01-01",
        f"end_date-{activity.id}": "2026-06-30",
        "justification": "",
        f"indicator_id-{activity.id}": [],
    }
    refused = save_plan_activities(operation, _Posted(fields), actor)
    assert refused["ok"] is False
    assert db.session.get(type(activity), activity.id).title != "Clinics"

    fields["justification"] = "Renamed the health activity."
    saved = save_plan_activities(operation, _Posted(fields), actor)
    assert saved["ok"] is True and not saved["pending"] and not saved["errors"]
    assert db.session.get(type(activity), activity.id).title == "Clinics"


def test_a_negative_new_sector_does_not_keep_the_other_edits(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    activity = activities_for(groups_for(latest_plan(operation.id).id)[0].id)[0]
    actor = _manager(user.id)
    refused = save_plan_activities(
        operation,
        _Posted(
            {
                "activity_id": [str(activity.id)],
                f"title-{activity.id}": "Clinics",
                f"budget_chf-{activity.id}": "8000",
                f"start_date-{activity.id}": "2026-01-01",
                f"end_date-{activity.id}": "2026-06-30",
                "justification": "Adding a sector with a bad budget.",
                "add_sector": ["livelihoods"],
                "add_title-livelihoods": "Deliver Livelihoods",
                "add_budget-livelihoods": "-5",
            }
        ),
        actor,
    )
    assert refused["ok"] is False
    assert "Amounts cannot be negative." in refused["error"]
    assert "Deliver Livelihoods" in refused["error"]
    assert db.session.get(type(activity), activity.id).title != "Clinics"
    assert all(group.label != "Livelihoods" for group in groups_for(latest_plan(operation.id).id))


def test_generated_plan_puts_the_indicator_on_the_sector(seeded):
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    group = groups_for(latest_plan(operation.id).id)[0]
    activity = activities_for(group.id)[0]
    from plugins.dref_monitoring.services.plans import indicators_for_activity

    indicator = indicators_for_activity(activity.id)[0]
    assert indicator.group_id == group.id
    assert activity.indicator_id == indicator.id
    assert group.people_targeted == 80
    assert group.budget_chf == Decimal("8000")


def test_adding_an_activity_to_a_confirmed_plan_opens_a_draft(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    actor = _manager(user.id)
    assert validate_plan(operation, actor, date(2026, 1, 10)) is None
    group = groups_for(latest_plan(operation.id).id)[0]
    activity = activities_for(group.id)[0]
    from plugins.dref_monitoring.services.plans import indicators_for_activity

    indicator = indicators_for_activity(activity.id)[0]
    saved = save_plan_activities(
        operation,
        _Posted(
            {
                "activity_id": [str(activity.id)],
                f"title-{activity.id}": activity.title,
                f"status-{activity.id}": activity.status,
                f"budget_chf-{activity.id}": "8000",
                f"start_date-{activity.id}": "2026-01-01",
                f"end_date-{activity.id}": "2026-06-30",
                f"indicator_id-{activity.id}": [str(indicator.id)],
                f"target-{indicator.id}": "80",
                "justification": "Distribution is a second activity under the same indicator.",
                "add_activity": [str(indicator.id)],
                f"add_activity_title-{indicator.id}": "Distribute kits",
                f"add_activity_status-{indicator.id}": "planned",
                f"add_activity_type-{indicator.id}": "direct_delivery",
                f"add_activity_by-{indicator.id}": "national_society",
            }
        ),
        actor,
    )
    assert saved["ok"] is True and not saved["errors"]
    operation = db.session.get(DrefOperation, operation.id)
    plan = latest_plan(operation.id)
    assert plan.version == 2
    assert plan.status == "draft"
    assert plan.source == "structure"
    assert operation.workflow_status == "plan_draft"
    titles = {row.title for row in activities_for(groups_for(plan.id)[0].id)}
    assert titles == {activity.title, "Distribute kits"}
    added = next(row for row in activities_for(groups_for(plan.id)[0].id) if row.title == "Distribute kits")
    assert added.activity_type == "direct_delivery"
    assert added.carried_out_by == "national_society"
    assert added.indicator_id is not None


def test_edit_mode_adds_several_activities_under_one_sector(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    actor = _manager(user.id)
    assert validate_plan(operation, actor, date(2026, 1, 10)) is None
    group = groups_for(latest_plan(operation.id).id)[0]
    activity = activities_for(group.id)[0]
    from plugins.dref_monitoring.services.plans import indicators_for_activity

    indicator = indicators_for_activity(activity.id)[0]
    saved = save_plan_activities(
        operation,
        _Posted(
            {
                "activity_id": [str(activity.id)],
                f"title-{activity.id}": activity.title,
                f"status-{activity.id}": activity.status,
                f"budget_chf-{activity.id}": "8000",
                f"start_date-{activity.id}": "2026-01-01",
                f"end_date-{activity.id}": "2026-06-30",
                f"indicator_id-{activity.id}": [str(indicator.id)],
                f"target-{indicator.id}": "80",
                "justification": "Two more activities under the same sector.",
                "add_activity": ["n1", "n2", "n3"],
                "add_activity_indicator-n1": str(indicator.id),
                "add_activity_indicator-n2": str(indicator.id),
                "add_activity_indicator-n3": str(indicator.id),
                "add_activity_group-n1": str(group.id),
                "add_activity_group-n2": str(group.id),
                "add_activity_group-n3": str(group.id),
                "add_activity_title-n1": "Distribute kits",
                "add_activity_title-n2": "Train volunteers",
                "add_activity_title-n3": "",
                "add_activity_status-n1": "planned",
                "add_activity_status-n2": "ongoing",
                "add_activity_status-n3": "planned",
                "add_activity_budget-n1": "100",
                "add_activity_budget-n2": "250",
                "add_activity_type-n1": "direct_delivery",
                "add_activity_by-n2": "national_society",
            }
        ),
        actor,
    )
    assert saved["ok"] is True and not saved["errors"]
    plan = latest_plan(operation.id)
    assert plan.version == 2 and plan.status == "draft"
    rows = activities_for(groups_for(plan.id)[0].id)
    titles = {row.title: row for row in rows}
    assert set(titles) == {activity.title, "Distribute kits", "Train volunteers"}
    assert titles["Distribute kits"].budget_chf == Decimal("100.00")
    assert titles["Distribute kits"].activity_type == "direct_delivery"
    assert titles["Train volunteers"].status == "ongoing"
    assert titles["Train volunteers"].carried_out_by == "national_society"
    assert titles["Train volunteers"].budget_chf == Decimal("250.00")
    added_indicators = {titles["Distribute kits"].indicator_id, titles["Train volunteers"].indicator_id}
    assert len(added_indicators) == 1
    assert None not in added_indicators


def test_plan_edit_adds_a_sector_that_was_not_on_the_plan(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    plan = latest_plan(operation.id)
    assert "livelihoods" in {key for key, _label in sectors_not_on_plan(plan.id)}
    actor = _manager(user.id)
    activity = activities_for(groups_for(plan.id)[0].id)[0]
    fields = {
        "activity_id": [str(activity.id)],
        f"title-{activity.id}": activity.title,
        f"status-{activity.id}": "ongoing",
        f"budget_chf-{activity.id}": "8000",
        f"start_date-{activity.id}": "2026-01-01",
        f"end_date-{activity.id}": "2026-06-30",
        f"indicator_id-{activity.id}": [],
        "justification": "Livelihoods support was agreed locally.",
        "add_sector": ["livelihoods"],
        "add_title-livelihoods": "Deliver Livelihoods",
        "add_status-livelihoods": "planned",
        "add_budget-livelihoods": "1500",
        "add_start-livelihoods": "2026-02-01",
        "add_end-livelihoods": "2026-06-30",
        "add_target-livelihoods": "40",
    }
    saved = save_plan_activities(operation, _Posted(fields), actor)
    assert saved["ok"] is True and not saved["errors"]
    groups = {group.key: group for group in groups_for(plan.id)}
    assert "livelihoods" in groups
    added = activities_for(groups["livelihoods"].id)[0]
    assert added.title == "Deliver Livelihoods"
    assert added.status == "planned"
    assert db.session.get(type(activity), activity.id).status == "ongoing"
    assert added.budget_chf == Decimal("1500.00")
    assert added.start_date == date(2026, 2, 1)
    assert "livelihoods" not in {key for key, _label in sectors_not_on_plan(plan.id)}


def test_sync_keeps_dref_appeals_and_drops_emergency_appeals(seeded):
    summary = apply_rows(
        [
            _row(),
            _row(id="Dref-ea", appeal_code="MDREA001", appeal_type="EA", disaster_name="Emergency appeal"),
            _row(id="Dref-imminent", appeal_code="MDRIM001", appeal_type="i-DREF", pillar="Anticipatory"),
        ]
    )
    assert summary["created"] == 2
    assert summary["appeals"] == 2
    assert DrefOperation.query.filter_by(appeal_code="MDRZZ001").count() == 1
    assert DrefOperation.query.filter_by(appeal_code="MDRIM001").count() == 1
    assert DrefOperation.query.filter_by(appeal_code="MDREA001").count() == 0

    db.session.add(DrefOperation(appeal_code="MDREA002", disaster_name="Stored appeal", appeal_type="EA"))
    db.session.commit()
    again = apply_rows([_row()])
    assert again["removed"] == 1
    assert DrefOperation.query.filter_by(appeal_code="MDREA002").count() == 0


def test_fetch_rows_reads_the_feed_without_a_status_filter():
    seen = []

    def http_get(url, params):
        seen.append((url, params))
        return []

    rows = fetch_rows(http_get, "https://example.test/dref3/")
    assert rows == []
    assert seen == [("https://example.test/dref3/", {"limit": 200, "offset": 0})]


def test_a_later_closed_stage_closes_an_operation_that_was_active(seeded):
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    assert operation.operation_status == "active"
    assert operation.workflow_status == "plan_draft"

    apply_rows(
        [
            _row(is_latest_stage=False, id="Dref-1", operation_status="active"),
            _row(
                id="DrefFinalReport-2",
                stage="Final Report",
                operation_status="closed",
                is_latest_stage=True,
                date_of_approval="2026-06-01",
            ),
        ]
    )
    operation = db.session.get(DrefOperation, operation.id)
    assert operation.operation_status == "closed"
    assert operation.workflow_status == "closure"


def test_a_blank_latest_stage_keeps_an_earlier_closed_status(seeded):
    apply_rows(
        [
            _row(id="Dref-1", operation_status="closed", is_latest_stage=False, date_of_approval="2026-01-05"),
            _row(
                id="DrefFinalReport-2",
                stage="Final Report",
                operation_status="",
                is_latest_stage=True,
                date_of_approval="2026-06-01",
            ),
        ]
    )
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    assert operation.operation_status == "closed"
    assert operation.workflow_status == "closure"


def test_an_active_latest_stage_is_not_closed_by_an_older_stage(seeded):
    apply_rows(
        [
            _row(id="Dref-1", operation_status="closed", is_latest_stage=False, date_of_approval="2026-01-05"),
            _row(
                id="DrefOperationalUpdate-2",
                stage="Operational Update 1",
                operation_status="active",
                is_latest_stage=True,
                date_of_approval="2026-04-01",
            ),
        ]
    )
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    assert operation.operation_status == "active"
    assert operation.workflow_status == "plan_draft"


def test_a_new_allocation_opens_a_fresh_draft_and_keeps_the_validated_plan(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    assert DrefPeriod.query.filter_by(operation_id=operation.id).count() >= 1

    apply_rows(
        [
            _row(is_latest_stage=False, id="Dref-1"),
            _row(
                id="DrefOperationalUpdate-9",
                stage="Operational Update 1",
                total_approved=18000,
                sector_health_budget=12000,
                end_date_of_operation="2026-09-30",
                is_latest_stage=True,
                date_of_approval="2026-04-01",
            ),
        ]
    )
    plans = DrefPlan.query.filter_by(operation_id=operation.id).order_by(DrefPlan.version).all()
    assert [plan.status for plan in plans] == ["validated", "draft"]
    assert plans[1].source == "rebased"
    operation = db.session.get(DrefOperation, operation.id)
    assert operation.workflow_status == "plan_draft"
    assert str(operation.total_approved) in {"18000", "18000.00"}


def test_draft_payload_has_figures_only_and_records_the_model_call(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    payload = build_payload(operation)
    dumped = str(payload).lower()
    assert "email" not in dumped
    assert "narrative" not in payload
    assert payload["expenditure_note"]
    assert payload["sectors"][0]["key"] == "health"
    assert "history" in payload
    assert "request" in payload
    assert "feedback" not in dumped
    seen = {}

    def complete(body, kind):
        seen["body"] = body
        seen["kind"] = kind
        return "Draft from the model"

    result = generate_draft(operation, "final_report", _manager(user.id), complete=complete, model_name="gpt-test")
    assert result["ai_used"] is True
    assert "narrative" not in seen["body"]
    draft = db.session.get(DrefDraft, result["draft_id"])
    assert draft.body == "Draft from the model"
    assert draft.input_hash
    assert draft.model == "gpt-test"
    plain = generate_draft(operation, "operational_update", _manager(user.id))
    plain_draft = db.session.get(DrefDraft, plain["draft_id"])
    assert plain["ai_used"] is False
    assert plain_draft.body == ""
    assert "Operational update for" not in plain_draft.body


def test_a_due_period_and_the_end_date_each_create_one_draft(seeded):
    import json

    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    validate_plan(operation, _manager(user.id), date(2026, 1, 10))
    today = date(2026, 6, 30)
    period = DrefPeriod.query.filter_by(operation_id=operation.id).order_by(DrefPeriod.sequence.desc()).first()
    period.due_date = today
    db.session.commit()
    seen = {}

    def complete(payload, kind):
        seen[kind] = payload["language"]
        assert "feedback" not in payload
        assert payload["history"]
        return json.dumps({"what_happened": "Water entered the clinic.", "achievements": "Forty people were reached."})

    from plugins.dref_monitoring.services.drafts import generate_scheduled_drafts

    assert generate_scheduled_drafts(today, complete=complete) == 2
    assert generate_scheduled_drafts(today, complete=complete) == 0
    drafts = DrefDraft.query.filter_by(operation_id=operation.id).all()
    assert sorted(row.report_kind for row in drafts) == ["final_report", "operational_update"]
    update = next(row for row in drafts if row.report_kind == "operational_update")
    assert update.trigger == "milestone"
    assert update.period_id == period.id
    assert update.ai_used is True
    assert "Water entered the clinic." in update.body
    assert seen["operational_update"] == "en"


def test_validation_posts_go_chapters_and_a_missing_token_does_not(seeded):
    import json

    from flask import current_app

    from plugins.dref_monitoring.services.drafts import validate_draft
    from plugins.dref_monitoring.services.go_submit import submit_draft

    _country, user = seeded
    apply_rows([_row(appeal_id=91)])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    result = generate_draft(
        operation,
        "operational_update",
        _manager(user.id),
        complete=lambda payload, kind: json.dumps({"what_happened": "The river rose.", "summary_of_changes": "The end date moved."}),
        model_name="gpt-test",
        language="fr",
    )
    draft = db.session.get(DrefDraft, result["draft_id"])
    assert draft.language == "fr"
    missing = submit_draft(operation, draft, post=lambda *args: (_ for _ in ()).throw(AssertionError("posted too early")))
    assert missing["ok"] is False
    error = validate_draft(draft, operation, _manager(user.id))
    assert error is None
    assert draft.status == "validated"
    current_app.config["GO_API_TOKEN"] = ""
    try:
        refused = submit_draft(operation, draft)
        assert refused["ok"] is False
        assert draft.go_status == "failed"
        calls = {}

        def post(url, payload, token):
            calls["url"] = url
            calls["payload"] = payload
            calls["token"] = token
            return 201, '{"id": 44}'

        current_app.config["GO_API_TOKEN"] = "secret-token"
        current_app.config["GO_API_BASE"] = "https://go.example.test/api/v2/"
        sent = submit_draft(operation, draft, post=post)
        assert sent["ok"] is True
        assert sent["reference"] == "44"
        assert draft.status == "submitted"
        assert calls["url"].endswith("/dref-op-update/")
        assert calls["payload"]["event_description"] == "The river rose."
        assert calls["payload"]["summary_of_change"] == "The end date moved."
        assert calls["payload"]["starting_language"] == "fr"
        assert calls["payload"]["dref"] == 91
        assert calls["payload"]["status"] == 1
        assert "secret-token" not in json.dumps(calls["payload"])
        again = submit_draft(operation, draft, post=lambda *args: (_ for _ in ()).throw(AssertionError("posted twice")))
        assert again["ok"] is True
    finally:
        current_app.config["GO_API_TOKEN"] = ""
        current_app.config["GO_API_BASE"] = "https://goadmin.ifrc.org/api/v2/"


def test_excel_import_replaces_a_draft_plan(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Activities"
    sheet.append(["Group", "Activity", "Indicator", "Indicator type", "Target", "Unit", "Budget CHF", "Start", "End"])
    sheet.append(["Health", "Distribute kits", "Kits delivered", "output", 10, "kits", 500, "2026-01-02", "2026-02-01"])
    buffer = BytesIO()
    book.save(buffer)
    parsed = parse_workbook(buffer.getvalue())
    assert parsed[0]["activity"] == "Distribute kits"
    result = import_activities(operation, buffer.getvalue(), _manager(user.id), date(2026, 1, 10))
    assert result["ok"] is True
    plan = latest_plan(operation.id)
    assert plan.source == "excel"
    assert groups_for(plan.id)[0].label == "Health"


def test_escalation_notifies_members_once_per_day(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    validate_plan(operation, _manager(user.id), date(2026, 1, 10))
    for period in DrefPeriod.query.filter_by(operation_id=operation.id).all():
        period.due_date = date.today() - timedelta(days=1)
    db.session.add(DrefMember(operation_id=operation.id, user_id=user.id, tier="enter"))
    db.session.commit()
    calls = []

    def notify(user_ids, op, per, level):
        calls.append((user_ids, level))

    assert run_escalation(date.today(), notify) >= 1
    assert calls[0][0] == [user.id]
    assert calls[0][1] == "reminder"
    calls.clear()
    assert run_escalation(date.today(), notify) == 0
    assert calls == []


def test_activity_add_rename_and_remove_keep_the_justification(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    actor = _manager(user.id)
    activity = activities_for(groups_for(latest_plan(operation.id).id)[0].id)[0]
    original_title = activity.title
    renamed = save_plan_activities(
        operation,
        _Posted(
            {
                "activity_id": [str(activity.id)],
                f"title-{activity.id}": "Clinics",
                f"budget_chf-{activity.id}": "8000",
                f"start_date-{activity.id}": "2026-01-01",
                f"end_date-{activity.id}": "2026-06-30",
                "justification": "Renamed the health activity.",
            }
        ),
        actor,
    )
    assert renamed["ok"] is True
    recorded = DrefChangeRequest.query.filter_by(operation_id=operation.id, field="title").one()
    assert recorded.status == "approved" and recorded.within_bounds is True
    assert recorded.old_value == original_title
    assert recorded.new_value == "Clinics"
    assert recorded.justification == "Renamed the health activity."
    assert recorded.plan_id == latest_plan(operation.id).id

    assert validate_plan(operation, actor, date(2026, 1, 10)) is None
    plan = latest_plan(operation.id)
    group = groups_for(plan.id)[0]
    kept = activities_for(group.id)[0]
    from plugins.dref_monitoring.services.plans import indicators_for_activity

    indicator = indicators_for_activity(kept.id)[0]
    added = save_plan_activities(
        operation,
        _Posted(
            {
                "activity_id": [str(kept.id)],
                f"title-{kept.id}": kept.title,
                f"budget_chf-{kept.id}": "8000",
                f"start_date-{kept.id}": "2026-01-01",
                f"end_date-{kept.id}": "2026-06-30",
                f"indicator_id-{kept.id}": [str(indicator.id)],
                "justification": "Distribution is a second activity under the same indicator.",
                "add_activity": [str(indicator.id)],
                f"add_activity_title-{indicator.id}": "Distribute kits",
            }
        ),
        actor,
    )
    assert added["ok"] is True
    created = DrefChangeRequest.query.filter_by(operation_id=operation.id, field="added").one()
    assert created.status == "approved"
    assert created.new_value == "Distribute kits"
    assert created.justification == "Distribution is a second activity under the same indicator."
    draft = latest_plan(operation.id)
    assert created.plan_id == draft.id
    current = activities_for(groups_for(draft.id)[0].id)
    extra = next(row for row in current if row.title == "Distribute kits")
    kept_now = next(row for row in current if row.id != extra.id)
    removed = save_plan_activities(
        operation,
        _Posted(
            {
                "activity_id": [str(kept_now.id)],
                f"title-{kept_now.id}": kept_now.title,
                f"budget_chf-{kept_now.id}": "8000",
                f"start_date-{kept_now.id}": "2026-01-01",
                f"end_date-{kept_now.id}": "2026-06-30",
                "justification": "Distribution was folded back into the sector activity.",
                "remove_activity": [str(extra.id)],
            }
        ),
        actor,
    )
    assert removed["ok"] is True
    gone = DrefChangeRequest.query.filter_by(operation_id=operation.id, field="removed").one()
    assert gone.old_value == "Distribute kits"
    assert gone.justification == "Distribution was folded back into the sector activity."
    assert gone.plan_id == latest_plan(operation.id).id


def test_unvalidated_plan_reminds_the_validation_tier_once_per_day(seeded):
    _country, user = seeded
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    plan = latest_plan(operation.id)
    plan.validation_due = date.today() + timedelta(days=20)
    db.session.add(DrefMember(operation_id=operation.id, user_id=user.id, tier="validate"))
    db.session.commit()
    calls = []

    def notify(user_ids, op, subject, level):
        calls.append((user_ids, op.appeal_code, level))

    assert run_escalation(date.today(), notify) == 0
    assert calls == []
    plan.validation_due = date.today()
    db.session.commit()
    assert run_escalation(date.today(), notify) == 1
    assert calls == [([user.id], "MDRZZ001", "plan")]
    calls.clear()
    assert run_escalation(date.today(), notify) == 0
    assert calls == []


def test_portfolio_totals_include_reach_and_completed_activities(seeded):
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    activity = activities_for(groups_for(latest_plan(operation.id).id)[0].id)[0]
    activity.status = "completed"
    period = DrefPeriod(
        operation_id=operation.id,
        sequence=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        due_date=date(2026, 1, 31),
    )
    db.session.add(period)
    db.session.flush()
    report = DrefReport(
        period_id=period.id,
        operation_id=operation.id,
        expenditure_total=Decimal("120"),
    )
    db.session.add(report)
    db.session.flush()
    db.session.add(
        DrefActivityUpdate(
            report_id=report.id,
            activity_id=activity.id,
            people_individuals=12,
            people_households=4,
            status="completed",
        )
    )
    db.session.commit()
    overview = build_overview(date(2026, 2, 1))
    assert overview["people_reached"] == 12
    assert overview["households_reached"] == 4
    assert overview["activities_completed"] == 1
    assert overview["operations"][0]["people_reached"] == 12
