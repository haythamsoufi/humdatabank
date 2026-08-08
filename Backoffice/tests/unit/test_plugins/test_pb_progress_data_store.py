"""Tests for PBProgressDataStore build-claim locking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models.plugin_data import PluginData
from plugins.pb_progress.plugin_data_store import (
    BUILD_HEARTBEAT_STALE_SECONDS,
    PBProgressDataStore,
)
from plugins.pb_progress.versions import DEFAULT_VERSION, VERSION_ORDER

OTHER_VERSION = next(v for v in VERSION_ORDER if v != DEFAULT_VERSION)


@pytest.fixture
def pb_progress_store(app):
    with app.app_context():
        db.create_all()
        PluginData.query.filter_by(plugin_id="pb_progress").delete()
        db.session.commit()
        PBProgressDataStore._config = None
        yield
        PluginData.query.filter_by(plugin_id="pb_progress").delete()
        db.session.commit()
        PBProgressDataStore._config = None


@pytest.mark.unit
def test_try_set_version_status_rejects_concurrent_running(app, pb_progress_store) -> None:
    with app.app_context():
        PBProgressDataStore.save_version_status(
            DEFAULT_VERSION,
            {"status": "running", "job_id": "existing-job"},
        )
        claimed = PBProgressDataStore.try_set_version_status_if_not_running(
            DEFAULT_VERSION,
            {"status": "running", "job_id": "new-job"},
        )
        assert claimed is False
        saved = PBProgressDataStore.get_version_status(DEFAULT_VERSION)
        assert saved["job_id"] == "existing-job"


@pytest.mark.unit
def test_try_set_version_status_allows_idle(app, pb_progress_store) -> None:
    with app.app_context():
        claimed = PBProgressDataStore.try_set_version_status_if_not_running(
            DEFAULT_VERSION,
            {
                "status": "running",
                "job_id": "new-job",
                "output_names": ["pb-report.html"],
            },
        )
        assert claimed is True
        saved = PBProgressDataStore.get_version_status(DEFAULT_VERSION)
        assert saved["status"] == "running"
        assert saved["job_id"] == "new-job"
        assert saved["output_names"] == ["pb-report.html"]


@pytest.mark.unit
def test_try_set_version_status_rejects_other_version_running(app, pb_progress_store) -> None:
    """Plugin-wide lock: a fresh build of ANY version blocks starting another.

    Regression guard for the cross-worker race where two different Gunicorn
    workers each only knew about their own in-process build thread, so one
    worker starting version A could not see that another worker was already
    building version B.
    """
    with app.app_context():
        now = datetime.now(timezone.utc).isoformat()
        PBProgressDataStore.save_version_status(
            OTHER_VERSION,
            {"status": "running", "job_id": "other-version-job", "heartbeat": now},
        )
        claimed = PBProgressDataStore.try_set_version_status_if_not_running(
            DEFAULT_VERSION,
            {"status": "running", "job_id": "new-job"},
        )
        assert claimed is False
        # The version we tried to claim must stay untouched.
        saved = PBProgressDataStore.get_version_status(DEFAULT_VERSION)
        assert saved.get("job_id") != "new-job"


@pytest.mark.unit
def test_try_set_version_status_allows_when_other_version_heartbeat_stale(app, pb_progress_store) -> None:
    """A 'running' status with a long-dead heartbeat is treated as abandoned.

    Otherwise a single crashed worker (killed mid-build) would permanently
    wedge every version's build slot with no way to recover.
    """
    with app.app_context():
        stale_heartbeat = (
            datetime.now(timezone.utc) - timedelta(seconds=BUILD_HEARTBEAT_STALE_SECONDS + 60)
        ).isoformat()
        PBProgressDataStore.save_version_status(
            OTHER_VERSION,
            {"status": "running", "job_id": "abandoned-job", "heartbeat": stale_heartbeat},
        )
        claimed = PBProgressDataStore.try_set_version_status_if_not_running(
            DEFAULT_VERSION,
            {"status": "running", "job_id": "new-job"},
        )
        assert claimed is True
        saved = PBProgressDataStore.get_version_status(DEFAULT_VERSION)
        assert saved["job_id"] == "new-job"
