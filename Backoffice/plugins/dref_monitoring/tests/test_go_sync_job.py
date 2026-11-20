"""GO sync runs as a background job and reports status to the settings page."""

from __future__ import annotations

import pytest

from app.extensions import db
from app.models import AIJob
from plugins.dref_monitoring.models import DrefOperation, DrefSyncLog
from plugins.dref_monitoring.services.go_sync import GoSyncBusy, GoSyncCancelled, sync_from_go
from plugins.dref_monitoring.services.go_sync_job import queue_go_sync, status_payload, _write_progress

pytestmark = pytest.mark.db


def _feed(url, params):
    if params is None or "/emergency/" in str(url):
        return {"dref": {}}
    return {
        "results": [
            {
                "id": "Dref-sync-1",
                "appeal_code": "MDRSYNC1",
                "appeal_type": "DREF",
                "country": "Zedland",
                "country_iso3": "ZZZ",
                "disaster_name": "Sync flood",
                "total_approved": 1000,
                "amount_approved": 1000,
                "people_targeted": 10,
                "start_date_of_operation": "2026-01-01",
                "end_date_of_operation": "2026-03-01",
                "operation_status": "active",
                "is_latest_stage": True,
                "date_of_approval": "2026-01-02",
                "link_to_emergency_page": "https://go.ifrc.org/emergencies/9/details",
            }
        ]
    }


def test_sync_reports_each_stage_and_records_the_log(db_session):
    seen = []
    summary = sync_from_go(_feed, progress=seen.append)
    stages = [item["stage"] for item in seen]
    assert "fetching" in stages
    assert "applications" in stages
    assert "applying" in stages
    assert stages[-1] == "completed"
    assert seen[-1]["percent"] == 100.0
    assert summary["created"] == 1
    log = DrefSyncLog.query.filter_by(status="ok").one()
    assert log.created_count == 1
    assert log.finished_at is not None


def test_cancel_before_save_keeps_no_operation(db_session):
    with pytest.raises(GoSyncCancelled):
        sync_from_go(_feed, should_stop=lambda: True)
    assert DrefOperation.query.filter_by(appeal_code="MDRSYNC1").count() == 0
    log = DrefSyncLog.query.one()
    assert log.status == "cancelled"
    assert log.finished_at is not None


def test_a_second_sync_is_refused_while_one_holds_the_lock():
    from plugins.dref_monitoring.services import go_sync as mod

    assert mod._THREAD_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(GoSyncBusy):
            mod.sync_from_go(_feed)
    finally:
        mod._THREAD_LOCK.release()


def test_queued_progress_is_what_the_status_poll_returns(app, db_session, system_manager_user, monkeypatch):
    monkeypatch.setattr("app.services.ai.ai_job_runner.start_ai_job_thread", lambda *args, **kwargs: None)
    job_id, created = queue_go_sync(system_manager_user.id, app)
    assert created is True
    _write_progress(
        job_id,
        {
            "stage": "fetching",
            "message": "Reading the GO feed, page %(current)s.",
            "message_vars": {"current": 2},
            "current": 2,
            "percent": 8,
        },
        force=True,
    )
    db.session.expire_all()
    payload = status_payload(db.session.get(AIJob, job_id))
    assert payload["stage"] == "fetching"
    assert payload["percent"] == 8
    assert payload["current"] == 2
    assert "2" in payload["message"]
    assert payload["status"] == "queued"


def test_sync_start_returns_immediately_and_cancel_is_visible(app, db_session, logged_in_sm_client, monkeypatch):
    from app.plugins.lifecycle_store import save_active_plugin_ids

    monkeypatch.setattr("app.services.ai.ai_job_runner.start_ai_job_thread", lambda *args, **kwargs: None)
    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"dref_monitoring"}))
    app.plugin_manager.sync_activation_state()
    try:
        started = logged_in_sm_client.post(
            "/admin/plugins/dref_monitoring/sync",
            headers={"Accept": "application/json"},
        )
        assert started.status_code == 202
        body = started.get_json()
        assert body["created"] is True
        assert body["status"] == "queued"
        assert body["percent"] == 0
        job_id = body["job_id"]

        again = logged_in_sm_client.post(
            "/admin/plugins/dref_monitoring/sync",
            headers={"Accept": "application/json"},
        )
        assert again.status_code == 202
        assert again.get_json()["job_id"] == job_id
        assert again.get_json()["created"] is False

        status = logged_in_sm_client.get(f"/admin/plugins/dref_monitoring/sync/jobs/{job_id}")
        assert status.status_code == 200
        assert status.get_json()["job_id"] == job_id
        assert "message" in status.get_json()

        cancelled = logged_in_sm_client.post(f"/admin/plugins/dref_monitoring/sync/jobs/{job_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.get_json()["status"] == "cancel_requested"

        final = logged_in_sm_client.get(f"/admin/plugins/dref_monitoring/sync/jobs/{job_id}")
        assert final.status_code == 200
        assert final.get_json()["status"] == "cancelled"
    finally:
        app.plugin_manager.active_plugins = previous


def test_sync_start_is_denied_to_anonymous_users(client):
    response = client.post("/admin/plugins/dref_monitoring/sync")
    assert response.status_code in (302, 401, 403, 404)


def _feed_with_plan(disaster_name="Sync flood"):
    def http_get(url, params):
        if params is None or "/emergency/" in str(url):
            return {
                "dref": {
                    "planned_interventions": [
                        {
                            "title": "health",
                            "budget": 10,
                            "person_targeted": 2,
                            "description": "Open the clinic",
                            "indicators": [{"title": "People reached", "target": 2}],
                        }
                    ]
                }
            }
        return {
            "results": [
                {
                    "id": "Dref-sync-1",
                    "appeal_code": "MDRSYNC1",
                    "appeal_type": "DREF",
                    "country": "Zedland",
                    "country_iso3": "ZZZ",
                    "disaster_name": disaster_name,
                    "total_approved": 1000,
                    "amount_approved": 1000,
                    "people_targeted": 10,
                    "start_date_of_operation": "2026-01-01",
                    "end_date_of_operation": "2026-03-01",
                    "operation_status": "active",
                    "is_latest_stage": True,
                    "date_of_approval": "2026-01-02",
                    "link_to_emergency_page": "https://go.ifrc.org/emergencies/9/details",
                }
            ]
        }

    return http_get


def test_a_repeat_sync_reuses_the_stored_application_and_skips_the_appeal(db_session):
    calls = []

    def http_get(url, params):
        calls.append(str(url))
        return _feed_with_plan()(url, params)

    first = sync_from_go(http_get)
    assert first["created"] == 1
    assert any("/emergency/" in url for url in calls)

    calls.clear()
    second = sync_from_go(http_get)
    assert second["unchanged"] == 1
    assert second["created"] == 0
    assert second["updated"] == 0
    assert not any("/emergency/" in url for url in calls)

    calls.clear()

    def revised(url, params):
        calls.append(str(url))
        return _feed_with_plan("Sync flood, revised")(url, params)

    third = sync_from_go(revised)
    assert third["updated"] == 1
    assert third["unchanged"] == 0
    assert DrefOperation.query.filter_by(appeal_code="MDRSYNC1").one().disaster_name == "Sync flood, revised"
    assert not any("/emergency/" in url for url in calls)
