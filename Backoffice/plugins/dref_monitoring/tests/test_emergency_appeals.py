"""Emergency Appeals: the appeal API feed, the loan stages that share its code, and what stays DREF-only."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from plugins.dref_monitoring.models import DrefBaseline, DrefDraft, DrefOperation
from plugins.dref_monitoring.services import go_sync
from plugins.dref_monitoring.services.go_appeals import appeal_queries, appeal_row, enrich_from_emergency
from plugins.dref_monitoring.services.go_application import appeal_application_from_emergency
from plugins.dref_monitoring.services.go_parse import (
    appeal_type_label,
    is_emergency_appeal,
    is_monitored_appeal,
    parse_stage,
)
from plugins.dref_monitoring.services.go_submit import NOT_POSTED, posts_to_go, submit_draft
from plugins.dref_monitoring.services.plans import activities_for, go_source_notices, groups_for, latest_baseline, latest_plan
from plugins.dref_monitoring.services.prompts import system_prompt
from tests.factories import create_test_country


def _appeal(**overrides):
    base = {
        "id": "7831",
        "aid": "43649055110994104",
        "name": "Zedland - Population Movement",
        "atype": 1,
        "atype_display": "Emergency Appeal",
        "status": 0,
        "status_display": "Active",
        "code": "MDRZZ018",
        "num_beneficiaries": 500000,
        "amount_requested": 15000000.0,
        "amount_funded": 1492175.83,
        "start_date": "2026-09-11T00:00:00Z",
        "end_date": "2027-10-31T00:00:00Z",
        "event": 8083,
        "country": {"iso3": "ZZZ", "name": "Zedland"},
        "region": {"region_name": "Middle East & North Africa"},
        "dtype": {"id": 5, "name": "Population Movement"},
        "event_details": {"id": 8083, "name": "Zedland Population Movement -2026", "ifrc_severity_level_display": "Orange"},
    }
    base.update(overrides)
    return base


def _loan(**overrides):
    """A dref3 row GO tags ``EA``: the DREF allocated as a loan against the appeal."""
    base = {
        "id": "Dref-loan-1",
        "appeal_id": 7831,
        "appeal_code": "MDRZZ018",
        "stage": "Application",
        "allocation": "First",
        "appeal_type": "EA",
        "pillar": "Response",
        "allocation_type": "Loan",
        "country": "Zedland",
        "country_iso3": "ZZZ",
        "disaster_definition": "Population Movement",
        "disaster_name": "Zedland loan DREF",
        "total_approved": 1000000,
        "amount_approved": 1000000,
        "people_targeted": 5000,
        "start_date_of_operation": "2026-09-01",
        "end_date_of_operation": "2026-12-31",
        "operation_status": "active",
        "is_latest_stage": True,
        "date_of_approval": "2026-09-05",
        "sector_health": True,
        "sector_health_budget": 800000,
        "sector_health_people_targeted": 4000,
    }
    base.update(overrides)
    return base


# --- converters, no database -------------------------------------------------------------------


@pytest.mark.unit
def test_an_appeal_becomes_a_dref3_shaped_row_with_the_amount_requested_as_its_budget():
    row = appeal_row(_appeal())
    assert row["id"] == "Appeal-7831"
    assert row["appeal_code"] == "MDRZZ018"
    assert row["appeal_type"] == "EA"
    assert row["stage"] == "Emergency Appeal"
    assert row["appeal_feed"] is True
    assert row["operation_status"] == "active"
    assert row["link_to_emergency_page"] == "https://go.ifrc.org/emergencies/8083"

    parsed = parse_stage(row)
    assert parsed["total_approved"] == Decimal("15000000.00")
    assert parsed["people_targeted"] == 500000
    assert parsed["start_date"] == date(2026, 9, 11)
    assert parsed["end_date"] == date(2027, 10, 31)
    assert parsed["operation_timeframe_months"] == 14
    assert parsed["country_iso3"] == "ZZZ"
    assert parsed["hazard"] == "Population Movement"
    assert parsed["crisis_category"] == "Orange"
    assert parsed["sectors"] == []
    assert parsed["from_appeal_feed"] is True


@pytest.mark.unit
@pytest.mark.parametrize("status", [1, 2, 3])
def test_only_an_active_appeal_is_still_operating(status):
    assert appeal_row(_appeal(status=status))["operation_status"] == "closed"


@pytest.mark.unit
def test_a_record_that_is_not_an_emergency_appeal_is_skipped():
    assert appeal_row(_appeal(atype=0)) is None
    assert appeal_row(_appeal(code="")) is None
    assert appeal_row(_appeal(id=None)) is None
    # A dref3 row has no ``atype``. A test double that answers every URL with dref3 rows must not create appeals.
    assert appeal_row(_loan()) is None
    assert appeal_row("not a record") is None


@pytest.mark.unit
def test_the_event_page_fills_only_what_the_appeal_list_lacks():
    row = appeal_row(_appeal())
    enrich_from_emergency(
        row,
        {
            "districts": [{"name": "Ibb"}, {"name": "Taiz"}],
            "disaster_start_date": "2026-09-03T00:00:00Z",
            "num_affected": 12000,
        },
    )
    parsed = parse_stage(row)
    assert parsed["districts"] == "Ibb, Taiz"
    assert parsed["date_of_disaster"] == date(2026, 9, 3)
    assert parsed["people_affected"] == 12000

    enrich_from_emergency(row, None)
    enrich_from_emergency(row, {"districts": [{"name": "Other"}], "num_affected": 1})
    assert row["districts"] == "Ibb, Taiz"
    assert row["people_affected"] == 12000


@pytest.mark.unit
def test_the_appeal_reads_are_active_appeals_and_recent_ones_of_any_status():
    queries = appeal_queries(2025)
    assert {"atype": 1, "status": 0} in queries
    assert {"atype": 1, "start_date__gte": "2025-01-01"} in queries


@pytest.mark.unit
def test_appeal_types_are_told_apart():
    assert is_emergency_appeal("EA") and is_emergency_appeal("Emergency Appeal") and is_emergency_appeal("emergency_appeal")
    assert not is_emergency_appeal("DREF")
    assert is_monitored_appeal("DREF") and is_monitored_appeal("i-DREF") and is_monitored_appeal("EA")
    assert not is_monitored_appeal("International Appeal") and not is_monitored_appeal("")
    assert [appeal_type_label(item) for item in ("DREF", "i-DREF", "EA")] == [
        "DREF",
        "Imminent DREF",
        "Emergency Appeal",
    ]


@pytest.mark.unit
def test_an_appeal_application_never_takes_the_interventions_of_the_dref_on_the_same_event():
    payload = {
        "summary": "<p>Fighting displaced <strong>many</strong> families.</p>",
        "timeline_field_reports": [{"id": 5, "report_date": "2026-09-09T00:00:00Z"}],
        "countries": [{"name": "Zedland", "society_name": "Zedland Red Crescent"}],
        "dref": {"planned_interventions": [{"title": "health", "budget": 10, "description": "Open a clinic"}]},
    }
    application = appeal_application_from_emergency(payload, 8083)
    assert application["interventions"] == []
    assert application["source"] == "emergency_appeal"
    assert "Fighting displaced" in application["narrative"]["event_description"]
    assert application["context"]["field_report_ids"] == [5]
    assert appeal_application_from_emergency(None, 8083) is None


@pytest.mark.unit
def test_the_prompt_names_an_emergency_appeal_and_leaves_a_dref_prompt_alone():
    dref = system_prompt("operational_update", "en")
    appeal = system_prompt("operational_update", "en", appeal_type="EA")
    assert "chapters of a DREF operational update" in dref
    assert "Emergency Appeal, not a DREF" not in dref
    assert "chapters of an Emergency Appeal operational update" in appeal
    assert "Emergency Appeal, not a DREF" in appeal
    assert "its Emergency Plan of Action" in appeal


@pytest.mark.unit
def test_an_emergency_appeal_report_is_not_posted_to_go():
    class Op:
        id = 1
        appeal_type = "EA"

    class Dref:
        id = 2
        appeal_type = "DREF"

    assert posts_to_go(Dref()) is True
    assert posts_to_go(Op()) is False
    result = submit_draft(Op(), type("Draft", (), {"operation_id": 1})())
    assert result["ok"] is False and result["error"] == NOT_POSTED


# --- sync, with a database ---------------------------------------------------------------------


@pytest.fixture
def seeded(db_session):
    import plugins.dref_monitoring.models  # noqa: F401

    return create_test_country(db_session, name="Zedland", iso3="ZZZ", region="Test")


def _feed(appeals, loans=(), emergency=None, seen=None):
    """A GO double that answers the appeal API, the dref3 feed, and emergency pages by URL."""

    def http_get(url, params):
        if seen is not None:
            seen.append((str(url), dict(params or {})))
        if "/emergency/" in str(url) or params is None:
            return emergency if emergency is not None else {}
        if "/appeal/" in str(url):
            if isinstance(appeals, Exception):
                raise appeals
            return {"results": list(appeals)}
        return {"results": list(loans)}

    return http_get


@pytest.mark.db
def test_a_sync_creates_the_appeal_as_one_group_with_the_appeal_budget(seeded):
    summary = go_sync.sync_from_go(_feed([_appeal()]))
    assert summary["created"] == 1
    assert summary["emergency_appeals"] == 1

    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    assert operation.appeal_type == "EA"
    assert operation.operation_status == "active"
    assert operation.country_id == seeded.id
    assert operation.total_approved == Decimal("15000000.00")
    assert operation.people_targeted == 500000
    assert operation.reporting_frequency == "monthly"

    baseline = latest_baseline(operation.id)
    assert baseline.stage == "Emergency Appeal"
    assert baseline.go_stage_id == "Appeal-7831"

    plan = latest_plan(operation.id)
    groups = groups_for(plan.id)
    assert [group.key for group in groups] == ["operation"]
    assert groups[0].budget_chf == Decimal("15000000.00")
    assert groups[0].people_targeted == 500000
    assert [item.title for item in activities_for(groups[0].id)] == ["Operation"]
    assert "not its sectors" in go_source_notices(baseline)[0]


@pytest.mark.db
def test_the_project_is_tagged_as_an_emergency_appeal(seeded):
    from app.models.projects import Project

    go_sync.sync_from_go(_feed([_appeal()]))
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    project = db.session.get(Project, operation.project_id)
    assert project.fund == "EA"
    assert project.portfolio == "DREF"
    assert int(project.amount_granted) == 15000000


@pytest.mark.db
def test_the_appeal_outranks_the_loan_dref_that_shares_its_code(seeded):
    go_sync.sync_from_go(_feed([_appeal()], loans=[_loan()]))
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    assert operation.total_approved == Decimal("15000000.00")

    stages = {row.go_stage_id: row for row in DrefBaseline.query.filter_by(operation_id=operation.id)}
    assert set(stages) == {"Appeal-7831", "Dref-loan-1"}
    assert stages["Appeal-7831"].is_latest is True
    assert stages["Dref-loan-1"].is_latest is False
    # The loan stage keeps its own sector budgets for reference, but the plan does not follow them.
    assert [item["key"] for item in stages["Dref-loan-1"].sectors] == ["health"]
    assert [group.key for group in groups_for(latest_plan(operation.id).id)] == ["operation"]


@pytest.mark.db
def test_a_loan_without_an_appeal_is_monitored_from_its_sectors(seeded):
    go_sync.sync_from_go(_feed([], loans=[_loan()]))
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    assert operation.appeal_type == "EA"
    assert operation.total_approved == Decimal("1000000.00")
    assert [group.key for group in groups_for(latest_plan(operation.id).id)] == ["health"]


@pytest.mark.db
def test_a_repeat_sync_finds_the_appeal_unchanged(seeded):
    emergency = {
        "summary": "<p>Situation overview.</p>",
        "districts": [{"name": "Ibb"}],
        "disaster_start_date": "2026-09-03T00:00:00Z",
        "num_affected": 900,
    }
    first = go_sync.sync_from_go(_feed([_appeal()], emergency=emergency))
    assert first["created"] == 1
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    assert operation.districts == "Ibb"
    assert operation.date_of_disaster == date(2026, 9, 3)
    assert operation.people_affected == 900

    second = go_sync.sync_from_go(_feed([_appeal()], emergency=emergency))
    assert second["unchanged"] == 1
    assert second["updated"] == 0


@pytest.mark.db
def test_an_unreadable_emergency_page_does_not_blank_the_stored_event_details(seeded):
    emergency = {"districts": [{"name": "Ibb"}], "disaster_start_date": "2026-09-03T00:00:00Z", "num_affected": 900}
    go_sync.sync_from_go(_feed([_appeal()], emergency=emergency))
    again = go_sync.sync_from_go(_feed([_appeal()], emergency={}))
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    assert operation.districts == "Ibb"
    assert operation.people_affected == 900
    assert again["unchanged"] == 1


@pytest.mark.db
def test_a_larger_appeal_budget_sends_a_validated_plan_back_to_draft(seeded):
    from plugins.dref_monitoring.access import Actor
    from plugins.dref_monitoring.services.plans import validate_plan
    from tests.factories import create_test_user

    user = create_test_user(db.session, email="ea-validator@example.com")
    go_sync.sync_from_go(_feed([_appeal()]))
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    assert validate_plan(operation, Actor(user.id, True, frozenset(), frozenset(), {}), date(2026, 9, 12)) is None

    go_sync.sync_from_go(_feed([_appeal(amount_requested=20000000.0)]))
    operation = db.session.get(DrefOperation, operation.id)
    assert operation.total_approved == Decimal("20000000.00")
    assert operation.workflow_status == "plan_draft"
    assert latest_plan(operation.id).version == 2


@pytest.mark.db
def test_a_closed_appeal_closes_the_operation(seeded):
    go_sync.sync_from_go(_feed([_appeal()]))
    go_sync.sync_from_go(_feed([_appeal(status=1, status_display="Closed")]))
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    assert operation.operation_status == "closed"
    assert operation.workflow_status == "closure"


@pytest.mark.db
def test_a_failed_appeal_read_keeps_the_stored_appeal_and_ignores_its_loan_stage(seeded):
    go_sync.sync_from_go(_feed([_appeal()], loans=[_loan()]))
    summary = go_sync.sync_from_go(_feed(RuntimeError("GO is down"), loans=[_loan()]))
    assert summary["appeals_unavailable"] is True
    assert summary["loans_held"] == 1
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    assert operation.total_approved == Decimal("15000000.00")
    assert latest_baseline(operation.id).go_stage_id == "Appeal-7831"
    assert "could not be read" in db.session.execute(
        db.text("select message from dref_mon_sync_log order by id desc limit 1")
    ).scalar()


@pytest.mark.db
def test_a_dref_sync_still_runs_when_the_appeal_api_is_down(seeded):
    dref = {
        "id": "Dref-9",
        "appeal_code": "MDRZZ001",
        "appeal_type": "DREF",
        "country_iso3": "ZZZ",
        "country": "Zedland",
        "total_approved": 5000,
        "start_date_of_operation": "2026-01-01",
        "end_date_of_operation": "2026-04-01",
        "operation_status": "active",
        "is_latest_stage": True,
        "date_of_approval": "2026-01-02",
    }
    summary = go_sync.sync_from_go(_feed(RuntimeError("GO is down"), loans=[dref]))
    assert summary["created"] == 1
    assert summary["appeals_unavailable"] is True
    assert DrefOperation.query.filter_by(appeal_code="MDRZZ001").count() == 1


@pytest.mark.db
def test_switching_emergency_appeals_off_neither_reads_nor_changes_them(seeded, monkeypatch):
    go_sync.sync_from_go(_feed([_appeal()], loans=[_loan()]))
    monkeypatch.setattr(go_sync, "emergency_appeal_settings", lambda: {"enabled": False, "closed_since_year": 2025})
    seen = []
    summary = go_sync.sync_from_go(
        _feed([_appeal(amount_requested=99.0)], loans=[_loan(total_approved=7)], seen=seen)
    )
    assert not any("/appeal/" in url for url, _params in seen)
    assert summary["appeals"] == 0
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    assert operation.total_approved == Decimal("15000000.00")


@pytest.mark.db
def test_the_appeal_reads_use_the_configured_year(seeded, monkeypatch):
    monkeypatch.setattr(go_sync, "emergency_appeal_settings", lambda: {"enabled": True, "closed_since_year": 2023})
    seen = []
    go_sync.sync_from_go(_feed([], seen=seen))
    reads = [params for url, params in seen if "/appeal/" in url]
    assert {"atype": 1, "start_date__gte": "2023-01-01", "limit": 200, "offset": 0} in reads
    assert {"atype": 1, "status": 0, "limit": 200, "offset": 0} in reads


@pytest.mark.db
def test_a_validated_appeal_report_stays_in_the_databank(seeded):
    from plugins.dref_monitoring.access import Actor
    from plugins.dref_monitoring.services.drafts import generate_draft, validate_draft
    from tests.factories import create_test_user

    user = create_test_user(db.session, email="ea-draft@example.com")
    go_sync.sync_from_go(_feed([_appeal()]))
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    actor = Actor(user.id, True, frozenset(), frozenset(), {})
    draft = db.session.get(DrefDraft, generate_draft(operation, "operational_update", actor)["draft_id"])
    assert validate_draft(draft, operation, actor) is None

    called = []
    result = submit_draft(operation, draft, post=lambda *args: called.append(args) or (201, "{}"))
    assert result["ok"] is False and result.get("not_posted") is True
    assert called == []
    db.session.refresh(draft)
    assert draft.status == "validated"
    assert (draft.go_status or "") == ""


@pytest.mark.db
def test_the_appeal_report_document_is_titled_as_an_emergency_appeal(seeded):
    from plugins.dref_monitoring.services.report_document import build_report
    from plugins.dref_monitoring.tests.test_report_export import _source

    blocks = build_report({**_source(), "appeal_type": "EA"})
    assert next(block.text for block in blocks if block.kind == "title") == "Emergency Appeal Operational Update"
    labels = [label for block in blocks if block.kind == "kv" for label, _value in block.rows]
    assert "Total appeal budget (CHF)" in labels
    assert "Total DREF allocation (CHF)" not in labels

    dref_blocks = build_report(_source())
    assert next(block.text for block in dref_blocks if block.kind == "title") == "DREF Operational Update"
