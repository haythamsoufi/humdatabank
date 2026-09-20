"""FDRS admin HTTP routes."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from plugins.fdrs import routes as fdrs_routes


@pytest.mark.unit
def test_settings_page_route_is_registered(app):
    endpoint, values = app.url_map.bind("localhost").match("/admin/plugins/fdrs/settings")
    assert endpoint == "fdrs.settings_page"
    assert values == {}


@pytest.mark.unit
def test_settings_page_requires_login(client):
    response = client.get("/admin/plugins/fdrs/settings")
    assert response.status_code in (302, 401)


@pytest.mark.unit
def test_settings_page_renders_for_system_manager(logged_in_sm_client):
    response = logged_in_sm_client.get("/admin/plugins/fdrs/settings")
    assert response.status_code == 200
    assert b"FDRS Plugin Settings" in response.data
    assert b"#sync" in response.data
    assert b"Sync" in response.data


@pytest.mark.unit
def test_sync_verify_routes_are_registered(app):
    endpoint, values = app.url_map.bind("localhost").match(
        "/admin/templates/data-sync/21/run-sync-verify", method="POST"
    )
    assert endpoint == "fdrs.run_sync_verify"
    assert values == {"template_id": 21}

    endpoint, values = app.url_map.bind("localhost").match(
        "/admin/templates/data-sync/21/sync-verify-status/abc"
    )
    assert endpoint == "fdrs.sync_verify_status"
    assert values["job_id"] == "abc"

    endpoint, values = app.url_map.bind("localhost").match(
        "/admin/templates/data-sync/21/sync-verify-results/abc"
    )
    assert endpoint == "fdrs.sync_verify_results"
    assert values["job_id"] == "abc"

    endpoint, values = app.url_map.bind("localhost").match(
        "/admin/templates/data-sync/21/sync-verify-latest"
    )
    assert endpoint == "fdrs.sync_verify_latest"
    assert values == {"template_id": 21}

    endpoint, values = app.url_map.bind("localhost").match(
        "/admin/fdrs-tools/documents/run", method="POST"
    )
    assert endpoint == "fdrs.run_document_status"

    endpoint, values = app.url_map.bind("localhost").match(
        "/admin/fdrs-tools/documents/latest"
    )
    assert endpoint == "fdrs.document_status_latest"


class TestJobLooksActivelyRunning:
    """_job_looks_actively_running lets status polls skip stale-job reconciliation
    (thread-liveness probing, stuck-item recovery) while a sync is healthy — see
    docstring in plugins/fdrs/routes.py for why that matters."""

    def test_false_when_status_is_not_running(self):
        job = {"status": "queued", "updated_ts": time.time()}
        assert fdrs_routes._job_looks_actively_running(job) is False

        job = {"status": "completed", "updated_ts": time.time()}
        assert fdrs_routes._job_looks_actively_running(job) is False

    def test_false_when_no_heartbeat_recorded_yet(self):
        job = {"status": "running", "updated_ts": None}
        assert fdrs_routes._job_looks_actively_running(job) is False

    def test_true_when_running_with_fresh_heartbeat(self):
        job = {"status": "running", "updated_ts": time.time() - 5}
        assert fdrs_routes._job_looks_actively_running(job) is True

    def test_false_when_heartbeat_is_stale(self):
        job = {"status": "running", "updated_ts": time.time() - 120}
        assert fdrs_routes._job_looks_actively_running(job, fresh_seconds=60.0) is False

    def test_false_on_malformed_updated_ts(self):
        job = {"status": "running", "updated_ts": "not-a-number"}
        assert fdrs_routes._job_looks_actively_running(job) is False


class TestMaybeCleanupExpiredImportJobs:
    """Cleanup does a table scan; status polls hit this every few seconds during a
    sync, so it must be throttled (see _CLEANUP_MIN_INTERVAL_SECONDS)."""

    def test_skips_when_called_again_within_the_throttle_window(self, monkeypatch):
        mock_cleanup = MagicMock()
        monkeypatch.setattr(fdrs_routes, "cleanup_expired_import_jobs", mock_cleanup)
        monkeypatch.setattr(fdrs_routes, "_last_import_job_cleanup_ts", 0.0)

        fdrs_routes._maybe_cleanup_expired_import_jobs()
        fdrs_routes._maybe_cleanup_expired_import_jobs()
        fdrs_routes._maybe_cleanup_expired_import_jobs()

        assert mock_cleanup.call_count == 1

    def test_runs_again_after_the_throttle_window_elapses(self, monkeypatch):
        mock_cleanup = MagicMock()
        monkeypatch.setattr(fdrs_routes, "cleanup_expired_import_jobs", mock_cleanup)
        monkeypatch.setattr(
            fdrs_routes, "_last_import_job_cleanup_ts", time.time() - fdrs_routes._CLEANUP_MIN_INTERVAL_SECONDS - 1
        )

        fdrs_routes._maybe_cleanup_expired_import_jobs()

        assert mock_cleanup.call_count == 1
