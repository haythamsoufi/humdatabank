"""Tests for FDRS document-status background job."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models import AIJob
from app.services.imports.async_import_job_store import FDRS_DOCUMENT_STATUS_JOB_TYPE
from plugins.fdrs.services.fdrs_document_status_job import (
    create_fdrs_document_status_job,
    get_active_fdrs_document_status_jobs_for_user,
    request_fdrs_document_status_cancel,
)

pytestmark = [pytest.mark.unit]


class TestCreateFdrsDocumentStatusJob:
    def test_creates_job_with_single_item(self, db_session, admin_user):
        job_id = create_fdrs_document_status_job(
            user_id=admin_user.id,
            output_path="/tmp/docs.xlsx",
            limit=50,
        )
        job = AIJob.query.get(job_id)
        assert job is not None
        assert job.job_type == FDRS_DOCUMENT_STATUS_JOB_TYPE
        assert job.total_items == 1
        assert len(job.items) == 1
        assert job.items[0].payload["limit"] == 50
        assert job.items[0].payload["year"] is None

    def test_stores_scan_year_on_job(self, db_session, admin_user):
        job_id = create_fdrs_document_status_job(
            user_id=admin_user.id,
            output_path="/tmp/docs.xlsx",
            year=2024,
        )
        job = AIJob.query.get(job_id)
        assert job.meta["year"] == 2024
        assert job.items[0].payload["year"] == 2024
        assert job.items[0].payload["retry_failed"] is False

    def test_stores_retry_failed_flag(self, db_session, admin_user):
        job_id = create_fdrs_document_status_job(
            user_id=admin_user.id,
            output_path="/tmp/docs.xlsx",
            retry_failed=True,
        )
        job = AIJob.query.get(job_id)
        assert job.meta["retry_failed"] is True
        assert job.items[0].payload["retry_failed"] is True


class TestGetActiveDocumentStatusJobs:
    def test_returns_non_terminal_jobs_for_user(self, db_session, admin_user):
        job_id = create_fdrs_document_status_job(
            user_id=admin_user.id,
            output_path="/tmp/docs.xlsx",
        )
        active = get_active_fdrs_document_status_jobs_for_user(admin_user.id)
        assert any(row["job_id"] == job_id for row in active)

        job = AIJob.query.get(job_id)
        job.status = "completed"
        db_session.commit()
        active_after = get_active_fdrs_document_status_jobs_for_user(admin_user.id)
        assert not any(row["job_id"] == job_id for row in active_after)


class TestRequestDocumentStatusCancel:
    def test_cancel_running_job(self, db_session, admin_user):
        job_id = create_fdrs_document_status_job(
            user_id=admin_user.id,
            output_path="/tmp/docs.xlsx",
        )
        job = AIJob.query.get(job_id)
        job.status = "running"
        db_session.commit()

        with patch("plugins.fdrs.services.fdrs_document_status_job.signal_job_cancel") as mock_signal:
            status = request_fdrs_document_status_cancel(job_id)
        assert status == "cancel_requested"
        db_session.refresh(job)
        assert job.status == "cancel_requested"
        mock_signal.assert_called_once_with(job_id)
