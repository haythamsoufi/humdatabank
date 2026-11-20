"""Report buttons on a cycle's entry form, and the narrative options behind them."""

from __future__ import annotations

from datetime import date

import pytest

from app.extensions import db
from app.models.assignments import AssignmentEntityStatus
from plugins.dref_monitoring.access import Actor
from plugins.dref_monitoring.models import DrefDraft, DrefOperation, DrefPeriod
from plugins.dref_monitoring.services.drafts import generate_draft, include_narrative, narrative_mode_of, save_sections
from plugins.dref_monitoring.services.entry_report_actions import report_actions_context, report_kinds_for
from plugins.dref_monitoring.services.go_sync import apply_rows
from plugins.dref_monitoring.services.plans import validate_plan
from plugins.dref_monitoring.services.report_document import Block, _without_empty_headings, build_report
from plugins.dref_monitoring.tests.test_report_export import _source
from tests.factories import create_test_country, create_test_user


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
def validated(db_session):
    import plugins.dref_monitoring.models  # noqa: F401

    create_test_country(db_session, name="Zedland", iso3="ZZZ", region="Test")
    user = create_test_user(db_session, email="dref-report-actions@example.com")
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ001").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    operation = db.session.get(DrefOperation, operation.id)
    periods = DrefPeriod.query.filter_by(operation_id=operation.id).order_by(DrefPeriod.sequence).all()
    return operation, periods, user


def _aes(period):
    return AssignmentEntityStatus.query.filter_by(assigned_form_id=period.assigned_form_id).one()


@pytest.mark.db
def test_only_the_last_cycle_offers_the_final_report(validated):
    operation, periods, _user = validated
    assert len(periods) > 1
    assert report_kinds_for(operation, periods[0]) == ["operational_update"]
    assert report_kinds_for(operation, periods[-2]) == ["operational_update"]
    assert report_kinds_for(operation, periods[-1]) == ["operational_update", "final_report"]


@pytest.mark.db
def test_the_header_context_follows_the_cycle_and_the_actor(validated):
    operation, periods, user = validated
    last = report_actions_context(_aes(periods[-1]), actor=_manager(user.id))
    assert last["kinds"] == ["operational_update", "final_report"]
    assert last["operation"].id == operation.id
    first = report_actions_context(_aes(periods[0]), actor=_manager(user.id))
    assert first["kinds"] == ["operational_update"]
    nobody = Actor(user.id, False, frozenset(), frozenset(), {})
    assert report_actions_context(_aes(periods[0]), actor=nobody) is None


@pytest.mark.db
def test_the_header_html_has_both_buttons_and_the_three_narrative_choices(app, validated, monkeypatch):
    from app.plugins.lifecycle_store import save_active_plugin_ids
    from plugins.dref_monitoring.plugin import DrefMonitoringPlugin

    operation, periods, user = validated
    monkeypatch.setattr(
        "plugins.dref_monitoring.services.entry_report_actions.current_actor", lambda: _manager(user.id)
    )
    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"dref_monitoring"}))
    app.plugin_manager.sync_activation_state()
    try:
        with app.test_request_context("/"):
            plugin = DrefMonitoringPlugin()
            last = plugin.get_entry_form_header_html(_aes(periods[-1]))
            first = plugin.get_entry_form_header_html(_aes(periods[0]))
    finally:
        app.plugin_manager.active_plugins = previous
    assert 'data-dref-report-open="dref-report-modal-operational_update"' in last
    assert 'data-dref-report-open="dref-report-modal-final_report"' in last
    assert 'data-dref-report-open="dref-report-modal-final_report"' not in first
    for value in ("ai", "manual", "none"):
        assert f'name="narrative" value="{value}"' in last
    assert f"/dref-monitoring/operations/{operation.id}/drafts" in last
    assert f'name="return_to" value="/assignment/{_aes(periods[-1]).id}"' in last


@pytest.mark.db
def test_the_header_html_is_empty_for_a_form_that_is_not_a_dref_cycle(app, db_session):
    from plugins.dref_monitoring.plugin import DrefMonitoringPlugin

    class _NotACycle:
        assigned_form = None
        id = 1

    with app.test_request_context("/"):
        assert DrefMonitoringPlugin().get_entry_form_header_html(_NotACycle()) == ""


@pytest.mark.db
def test_a_figures_only_draft_never_calls_the_model_and_cannot_be_edited(validated):
    operation, _periods, user = validated
    calls = []

    def complete(payload, kind):
        calls.append(kind)
        return "text"

    result = generate_draft(
        operation, "operational_update", _manager(user.id), complete=complete, narrative="none"
    )
    assert result["ok"] is True and result["ai_used"] is False
    assert calls == []
    draft = db.session.get(DrefDraft, result["draft_id"])
    assert draft.body == "" and draft.ai_used is False
    assert narrative_mode_of(draft) == "none"
    assert "narrative_mode" in draft.sections
    refused = save_sections(draft, operation, {"section_what_happened": "x"}, _manager(user.id))
    assert refused == "This report is figures only and has no narrative to edit."
    assert draft.edited_body is None


@pytest.mark.db
def test_a_figures_only_draft_can_gain_chapters_without_a_new_draft(validated):
    operation, _periods, user = validated
    actor = _manager(user.id)
    result = generate_draft(operation, "operational_update", actor, narrative="none")
    draft = db.session.get(DrefDraft, result["draft_id"])
    added = include_narrative(draft, operation, actor, "manual")
    assert added == {"ok": True, "ai_used": False}
    assert draft.id == result["draft_id"]
    assert narrative_mode_of(draft) == "manual"
    assert save_sections(draft, operation, {"section_what_happened": "The river rose."}, actor) is None

    second = generate_draft(operation, "operational_update", actor, narrative="none")
    other = db.session.get(DrefDraft, second["draft_id"])
    calls = []
    drafted = include_narrative(
        other,
        operation,
        actor,
        "ai",
        complete=lambda payload, kind: calls.append(kind) or '{"what_happened": "Rain flooded the town."}',
        model_name="test-model",
    )
    assert drafted["ok"] is True and drafted["ai_used"] is True
    assert calls == ["operational_update"]
    assert narrative_mode_of(other) == "ai"
    assert other.model == "test-model"
    assert include_narrative(other, operation, actor, "manual") == {
        "ok": False,
        "error": "This draft already has narrative chapters.",
    }
    blocked = generate_draft(operation, "final_report", actor, narrative="none")
    plain = db.session.get(DrefDraft, blocked["draft_id"])
    assert include_narrative(plain, operation, actor, "ai") == {
        "ok": False,
        "error": "AI drafting is not enabled.",
    }
    assert narrative_mode_of(plain) == "none"


@pytest.mark.db
def test_a_manual_draft_starts_empty_and_stays_editable(validated):
    operation, _periods, user = validated
    calls = []
    result = generate_draft(
        operation,
        "final_report",
        _manager(user.id),
        complete=lambda payload, kind: calls.append(kind) or "text",
        narrative="manual",
    )
    assert result["ok"] is True and result["ai_used"] is False
    assert calls == []
    draft = db.session.get(DrefDraft, result["draft_id"])
    assert narrative_mode_of(draft) == "manual"
    assert save_sections(draft, operation, {"section_what_happened": "The river rose."}, _manager(user.id)) is None


@pytest.mark.db
def test_an_ai_draft_needs_the_model_and_records_the_mode(validated):
    operation, _periods, user = validated
    refused = generate_draft(operation, "operational_update", _manager(user.id), narrative="ai")
    assert refused == {"ok": False, "error": "AI drafting is not enabled."}
    assert DrefDraft.query.filter_by(operation_id=operation.id).count() == 0
    result = generate_draft(
        operation,
        "operational_update",
        _manager(user.id),
        complete=lambda payload, kind: "Drafted by the model",
        narrative="ai",
    )
    assert result["ai_used"] is True
    assert narrative_mode_of(db.session.get(DrefDraft, result["draft_id"])) == "ai"
    unknown = generate_draft(operation, "operational_update", _manager(user.id), narrative="poem")
    assert unknown == {"ok": False, "error": "Unknown narrative option."}


@pytest.mark.db
def test_an_older_draft_reads_as_manual_or_ai(validated):
    operation, _periods, _user = validated
    older = DrefDraft(operation_id=operation.id, report_kind="operational_update", input_hash="a", sections={}, body="")
    assert narrative_mode_of(older) == "manual"
    older.ai_used = True
    assert narrative_mode_of(older) == "ai"


@pytest.mark.unit
def test_a_figures_only_document_drops_headings_with_nothing_under_them():
    full = build_report(_source())
    plain = build_report({**_source(), "narrative_mode": "none"})
    full_headings = [block.text for block in full if block.kind == "heading"]
    plain_headings = [block.text for block in plain if block.kind == "heading"]
    assert "What happened, where and when?" in full_headings
    assert "What happened, where and when?" not in plain_headings
    assert "Contact information" not in plain_headings
    assert "Budget overview" in plain_headings
    assert not any(block.kind == "paragraph" and not (block.text or "").strip() for block in plain)
    cover = next(block.text for block in plain if block.kind == "note")
    assert "no narrative chapters" in cover


@pytest.mark.unit
def test_a_manual_document_keeps_the_empty_chapters_to_fill_in():
    manual = build_report({**_source(), "narrative_mode": "manual"})
    headings = [block.text for block in manual if block.kind == "heading"]
    assert "What happened, where and when?" in headings


@pytest.mark.unit
def test_heading_pruning_keeps_a_parent_whose_child_has_content():
    blocks = [
        Block("heading", "Parent", 1),
        Block("heading", "Child with content", 2),
        Block("paragraph", "Text"),
        Block("heading", "Child without content", 2),
        Block("paragraph", ""),
        Block("heading", "Empty parent", 1),
        Block("heading", "Empty child", 2),
    ]
    kept = [block.text for block in _without_empty_headings(blocks)]
    assert kept == ["Parent", "Child with content", "Text"]
