"""Tests for PBProgressDataStore build-claim locking."""

from __future__ import annotations

import pytest

from app.extensions import db
from app.models.plugin_data import PluginData
from plugins.pb_progress.plugin_data_store import PBProgressDataStore
from plugins.pb_progress.versions import DEFAULT_VERSION


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
