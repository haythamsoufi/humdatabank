"""Tests for FDRS data sync background job service."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models import AIJob, AIJobItem
from app.services.imports.async_import_job_store import FDRS_DATA_SYNC_JOB_TYPE
from plugins.fdrs.services.fdrs_data_sync_job import (
    create_fdrs_data_sync_job,
    get_active_fdrs_data_sync_jobs_for_user,
    request_fdrs_data_sync_cancel,
)

pytestmark = [pytest.mark.unit]


class TestCreateFdrsDataSyncJob:
    def test_creates_job_with_single_item(self, db_session, admin_user):
        job_id = create_fdrs_data_sync_job(
            user_id=admin_user.id,
            template_id=1,
            dry_run=False,
            batch_size=1000,
            fdrs_years=[2024],
            test_limit=None,
            imputed_use_cache=True,
            sync_documents=True,
            fdrs_reported_import_states=[100, 200],
            preview_path=None,
            sync_user_id=admin_user.id,
        )
        job = AIJob.query.get(job_id)
        assert job is not None
        assert job.job_type == FDRS_DATA_SYNC_JOB_TYPE
        assert job.total_items == 1
        assert len(job.items) == 1
        item = job.items[0]
        assert item.item_index == 0
        assert item.entity_type == "form_template"
        assert item.entity_id == 1
        assert item.status == "queued"
        assert item.payload["batch_size"] == 1000


class TestGetActiveFdrsDataSyncJobs:
    def test_returns_non_terminal_jobs_for_user(self, db_session, admin_user):
        job_id = create_fdrs_data_sync_job(
            user_id=admin_user.id,
            template_id=5,
            dry_run=False,
            batch_size=1000,
            fdrs_years=None,
            test_limit=None,
            imputed_use_cache=True,
            sync_documents=True,
            fdrs_reported_import_states=None,
            preview_path=None,
            sync_user_id=admin_user.id,
        )
        active = get_active_fdrs_data_sync_jobs_for_user(admin_user.id, template_id=5)
        assert any(row["job_id"] == job_id for row in active)

        job = AIJob.query.get(job_id)
        job.status = "completed"
        db_session.commit()
        active_after = get_active_fdrs_data_sync_jobs_for_user(admin_user.id, template_id=5)
        assert not any(row["job_id"] == job_id for row in active_after)


class TestRequestFdrsDataSyncCancel:
    def test_cancel_running_job(self, db_session, admin_user):
        job_id = create_fdrs_data_sync_job(
            user_id=admin_user.id,
            template_id=1,
            dry_run=False,
            batch_size=1000,
            fdrs_years=None,
            test_limit=None,
            imputed_use_cache=True,
            sync_documents=True,
            fdrs_reported_import_states=None,
            preview_path=None,
            sync_user_id=admin_user.id,
        )
        job = AIJob.query.get(job_id)
        job.status = "running"
        db_session.commit()

        with patch("plugins.fdrs.services.fdrs_data_sync_job.signal_job_cancel") as mock_signal:
            status = request_fdrs_data_sync_cancel(job_id)
        assert status == "cancel_requested"
        db_session.refresh(job)
        assert job.status == "cancel_requested"
        mock_signal.assert_called_once_with(job_id)

    def test_cancel_terminal_job_is_noop(self, db_session, admin_user):
        job_id = create_fdrs_data_sync_job(
            user_id=admin_user.id,
            template_id=1,
            dry_run=False,
            batch_size=1000,
            fdrs_years=None,
            test_limit=None,
            imputed_use_cache=True,
            sync_documents=True,
            fdrs_reported_import_states=None,
            preview_path=None,
            sync_user_id=admin_user.id,
        )
        job = AIJob.query.get(job_id)
        job.status = "completed"
        db_session.commit()
        status = request_fdrs_data_sync_cancel(job_id)
        assert status == "completed"


class TestImportReusesRunningApp:
    def test_flask_app_for_import_does_not_create_second_app(self, app):
        import os
        import sys

        imports_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "plugins", "fdrs", "scripts")
        )
        if imports_dir not in sys.path:
            sys.path.insert(0, imports_dir)
        from import_fdrs_form_data import _flask_app_for_import

        with app.app_context():
            with patch("app.create_app") as create_app:
                resolved = _flask_app_for_import()
                assert resolved is app
                create_app.assert_not_called()

