"""AI drafting runs as a background job that reports progress and can be stopped."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.extensions import db
from app.models import AIJob
from plugins.dref_monitoring.access import Actor
from plugins.dref_monitoring.models import DrefDraft, DrefOperation
from plugins.dref_monitoring.services import draft_job
from plugins.dref_monitoring.services.draft_job import queue_draft_job, request_draft_cancel, status_payload
from plugins.dref_monitoring.services.drafts import DraftCancelled, generate_draft, include_narrative
from plugins.dref_monitoring.services.go_sync import apply_rows
from plugins.dref_monitoring.services.llm import _stream_reply
from plugins.dref_monitoring.services.prompts import chapter_keys
from tests.factories import create_test_country, create_test_user

pytestmark = pytest.mark.db


def _row():
    return {
        "id": "Dref-job-1",
        "appeal_code": "MDRJOB01",
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


@pytest.fixture
def operation(db_session):
    import plugins.dref_monitoring.models  # noqa: F401

    create_test_country(db_session, name="Zedland", iso3="ZZZ", region="Test")
    apply_rows([_row()])
    return DrefOperation.query.filter_by(appeal_code="MDRJOB01").one()


def _manager(user_id):
    return Actor(user_id, True, frozenset(), frozenset(), {})


def _chunk(text="", finish=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text), finish_reason=finish)])


def test_a_draft_reports_each_stage_in_order(operation, system_manager_user):
    seen = []

    def complete(payload, kind, progress=None):
        progress({"stage": "writing", "message": "Writing chapter 1.", "percent": 50})
        return '{"what_happened": "Rain flooded the town."}'

    def loader(op, actor, progress=None):
        progress({"stage": "documents", "message": "Searching Databank documents.", "percent": 32})
        return {}

    result = generate_draft(
        operation,
        "operational_update",
        _manager(system_manager_user.id),
        complete=complete,
        model_name="test-model",
        narrative="ai",
        context_loader=loader,
        progress=seen.append,
    )
    assert result["ok"] is True and result["ai_used"] is True
    stages = [event["stage"] for event in seen]
    assert stages == ["collecting", "documents", "writing", "writing", "saving"]
    percents = [event["percent"] for event in seen]
    assert percents == sorted(percents)


def test_callers_without_a_listener_keep_the_old_call_shape(operation, system_manager_user):
    calls = []

    def complete(payload, kind):
        calls.append(kind)
        return '{"what_happened": "Rain flooded the town."}'

    def loader(op, actor):
        return {}

    result = generate_draft(
        operation,
        "operational_update",
        _manager(system_manager_user.id),
        complete=complete,
        narrative="ai",
        context_loader=loader,
    )
    assert result["ai_used"] is True
    assert calls == ["operational_update"]


def test_cancelling_during_the_model_call_stores_nothing(operation, system_manager_user):
    def complete(payload, kind, progress=None):
        raise DraftCancelled()

    before = DrefDraft.query.count()
    with pytest.raises(DraftCancelled):
        generate_draft(
            operation,
            "operational_update",
            _manager(system_manager_user.id),
            complete=complete,
            narrative="ai",
            progress=lambda event: None,
        )
    assert DrefDraft.query.count() == before


def test_a_failing_listener_never_stops_the_draft(operation, system_manager_user):
    def listener(event):
        raise RuntimeError("the progress store is down")

    result = generate_draft(
        operation, "operational_update", _manager(system_manager_user.id), narrative="none", progress=listener
    )
    assert result["ok"] is True


def test_cancelling_while_adding_chapters_keeps_the_draft_unchanged(operation, system_manager_user):
    actor = _manager(system_manager_user.id)
    created = generate_draft(operation, "operational_update", actor, narrative="none")
    draft = db.session.get(DrefDraft, created["draft_id"])

    def complete(payload, kind, progress=None):
        raise DraftCancelled()

    with pytest.raises(DraftCancelled):
        include_narrative(draft, operation, actor, "ai", complete=complete, progress=lambda event: None)
    db.session.refresh(draft)
    assert draft.body == "" and draft.ai_used is False


def test_streaming_names_the_chapter_being_written():
    keys = chapter_keys("operational_update")
    pieces = []
    for key in keys:
        pieces.append(_chunk('{' if not pieces else ', '))
        pieces.append(_chunk(f'"{key}": "Some text for it."'))
    pieces.append(_chunk("}", finish="stop"))

    class Provider:
        def create(self, messages, model=None, **kwargs):
            assert kwargs["stream"] is True
            return iter(pieces)

    events = []
    text, reason = _stream_reply(Provider(), [], "m", {}, "operational_update", events.append)
    assert reason == "stop"
    assert text.startswith("{") and text.endswith("}")
    current = [event["current"] for event in events]
    assert current == sorted(current)
    assert current[0] == 1 and current[-1] == len(keys)
    assert all(event["total"] == len(keys) for event in events)
    assert events[-1]["percent"] <= 94


def test_cancelling_stops_the_stream_and_closes_it():
    closed = []

    class Stream:
        def __iter__(self):
            yield _chunk('{"what_happened": "x"')
            yield _chunk("never read")

        def close(self):
            closed.append(True)

    class Provider:
        def create(self, messages, model=None, **kwargs):
            return Stream()

    def listener(event):
        raise DraftCancelled()

    with pytest.raises(DraftCancelled):
        _stream_reply(Provider(), [], "m", {}, "operational_update", listener)
    assert closed == [True]


def _run_job(app, job_id):
    job = db.session.get(AIJob, job_id)
    item = job.items[0]
    draft_job._process_item(app, job_id=job_id, item_id=item.id)
    db.session.expire_all()
    return db.session.get(AIJob, job_id)


def _patch_ai(monkeypatch, complete):
    monkeypatch.setattr("app.services.ai.ai_job_runner.start_ai_job_thread", lambda *args, **kwargs: None)
    monkeypatch.setattr("plugins.dref_monitoring.config_store.ai_enabled", lambda: True)
    monkeypatch.setattr("plugins.dref_monitoring.services.llm.complete_with_engine", complete)
    monkeypatch.setattr("plugins.dref_monitoring.services.context.load_context", lambda *a, **k: {})


def test_the_job_creates_the_draft_and_reports_it(app, operation, system_manager_user, monkeypatch):
    def complete(payload, kind, progress=None):
        progress({"stage": "writing", "message": "Writing chapter 1 of 2.", "percent": 60})
        return '{"what_happened": "Rain flooded the town."}'

    _patch_ai(monkeypatch, complete)
    job_id, created = queue_draft_job(
        system_manager_user.id,
        {"action": "generate", "operation_id": operation.id, "kind": "operational_update", "narrative": "ai"},
        app,
    )
    assert created is True
    job = _run_job(app, job_id)
    payload = status_payload(job)
    assert payload["status"] == "completed"
    assert payload["percent"] == 100
    assert payload["summary"]["ai_used"] is True
    draft = db.session.get(DrefDraft, payload["summary"]["draft_id"])
    assert draft is not None and draft.ai_used is True and draft.operation_id == operation.id


def test_the_job_adds_chapters_to_an_existing_figures_only_draft(app, operation, system_manager_user, monkeypatch):
    _patch_ai(monkeypatch, lambda payload, kind, progress=None: '{"what_happened": "Rain flooded the town."}')
    created = generate_draft(operation, "operational_update", _manager(system_manager_user.id), narrative="none")
    job_id, _ = queue_draft_job(
        system_manager_user.id,
        {
            "action": "include",
            "operation_id": operation.id,
            "kind": "operational_update",
            "draft_id": created["draft_id"],
            "narrative": "ai",
        },
        app,
    )
    payload = status_payload(_run_job(app, job_id))
    assert payload["status"] == "completed"
    assert payload["summary"]["draft_id"] == created["draft_id"]
    assert db.session.get(DrefDraft, created["draft_id"]).ai_used is True


def test_a_refused_draft_ends_the_job_with_the_reason(app, operation, system_manager_user, monkeypatch):
    _patch_ai(monkeypatch, lambda payload, kind, progress=None: None)
    job_id, _ = queue_draft_job(
        system_manager_user.id,
        {"action": "generate", "operation_id": operation.id, "kind": "not_a_kind", "narrative": "ai"},
        app,
    )
    payload = status_payload(_run_job(app, job_id))
    assert payload["status"] == "failed"
    assert payload["error"] == "Unknown report type."


def test_a_crash_ends_the_job_without_leaking_the_error(app, operation, system_manager_user, monkeypatch):
    def broken(payload, kind, progress=None):
        raise RuntimeError("secret internal detail")

    _patch_ai(monkeypatch, broken)
    monkeypatch.setattr(
        draft_job, "generate_draft", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret internal detail"))
    )
    job_id, _ = queue_draft_job(
        system_manager_user.id,
        {"action": "generate", "operation_id": operation.id, "kind": "operational_update", "narrative": "ai"},
        app,
    )
    payload = status_payload(_run_job(app, job_id))
    assert payload["status"] == "failed"
    assert "secret" not in payload["error"]


def test_a_cancel_before_the_job_starts_stops_it(app, operation, system_manager_user, monkeypatch):
    calls = []
    _patch_ai(monkeypatch, lambda payload, kind, progress=None: calls.append(kind))
    job_id, _ = queue_draft_job(
        system_manager_user.id,
        {"action": "generate", "operation_id": operation.id, "kind": "operational_update", "narrative": "ai"},
        app,
    )
    assert request_draft_cancel(job_id) == "cancel_requested"
    payload = status_payload(_run_job(app, job_id))
    assert payload["status"] == "cancelled"
    assert calls == []
    assert DrefDraft.query.filter_by(operation_id=operation.id).count() == 0


def test_the_same_request_reuses_the_running_job(app, operation, system_manager_user, monkeypatch):
    _patch_ai(monkeypatch, lambda payload, kind, progress=None: None)
    params = {"action": "generate", "operation_id": operation.id, "kind": "operational_update", "narrative": "ai"}
    first, created = queue_draft_job(system_manager_user.id, params, app)
    again, created_again = queue_draft_job(system_manager_user.id, params, app)
    assert created is True and created_again is False and again == first
    other, created_other = queue_draft_job(system_manager_user.id, {**params, "kind": "final_report"}, app)
    assert created_other is True and other != first


def _activate_plugin(app):
    from app.plugins.lifecycle_store import save_active_plugin_ids

    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"dref_monitoring"}))
    app.plugin_manager.sync_activation_state()
    return previous


def test_the_page_starts_polls_and_cancels_a_job(app, operation, logged_in_sm_client, monkeypatch):
    monkeypatch.setattr("app.services.ai.ai_job_runner.start_ai_job_thread", lambda *args, **kwargs: None)
    monkeypatch.setattr("plugins.dref_monitoring.routes.ai_enabled", lambda: True)
    previous = _activate_plugin(app)
    try:
        url = f"/dref-monitoring/operations/{operation.id}/drafts"
        form = {"kind": "operational_update", "narrative": "ai", "language": "en"}
        started = logged_in_sm_client.post(url, data=form, headers={"Accept": "application/json"})
        assert started.status_code == 202
        body = started.get_json()
        assert body["created"] is True and body["status"] == "queued"
        job_id = body["job_id"]

        again = logged_in_sm_client.post(url, data=form, headers={"Accept": "application/json"})
        assert again.get_json()["job_id"] == job_id and again.get_json()["created"] is False

        status = logged_in_sm_client.get(f"{url}/jobs/{job_id}")
        assert status.status_code == 200
        assert status.get_json()["job_id"] == job_id
        assert "redirect_url" not in status.get_json()

        cancelled = logged_in_sm_client.post(f"{url}/jobs/{job_id}/cancel")
        assert cancelled.status_code == 202
        assert cancelled.get_json()["status"] == "cancel_requested"
    finally:
        app.plugin_manager.active_plugins = previous


def test_a_draft_without_a_model_comes_back_at_once(app, operation, logged_in_sm_client):
    previous = _activate_plugin(app)
    try:
        url = f"/dref-monitoring/operations/{operation.id}/drafts"
        response = logged_in_sm_client.post(
            url,
            data={"kind": "operational_update", "narrative": "manual", "language": "en"},
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body["status"] == "completed"
        assert body["redirect_url"].startswith(f"{url}/")
        plain = logged_in_sm_client.post(
            url, data={"kind": "operational_update", "narrative": "manual", "language": "en"}
        )
        assert plain.status_code == 302
    finally:
        app.plugin_manager.active_plugins = previous


def test_a_job_belongs_to_the_person_who_started_it(app, db_session, operation, logged_in_sm_client, monkeypatch):
    monkeypatch.setattr("app.services.ai.ai_job_runner.start_ai_job_thread", lambda *args, **kwargs: None)
    other = create_test_user(db_session, email="dref-job-other@example.com")
    job_id, _ = queue_draft_job(
        other.id,
        {"action": "generate", "operation_id": operation.id, "kind": "operational_update", "narrative": "ai"},
        app,
    )
    previous = _activate_plugin(app)
    try:
        url = f"/dref-monitoring/operations/{operation.id}/drafts/jobs/{job_id}"
        assert logged_in_sm_client.get(url).status_code == 404
        assert logged_in_sm_client.post(f"{url}/cancel").status_code == 404
    finally:
        app.plugin_manager.active_plugins = previous
