"""Tests for FDRS publication background job service."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models import AIJob
from app.services.imports.async_import_job_store import FDRS_PUBLICATION_JOB_TYPE
from plugins.fdrs.services.fdrs_publication_job import (
    create_fdrs_publication_job,
    get_active_fdrs_publication_jobs_for_user,
    request_fdrs_publication_cancel,
)

pytestmark = [pytest.mark.unit]


class TestCreateFdrsPublicationJob:
    def test_creates_job_with_single_item(self, db_session, admin_user):
        job_id = create_fdrs_publication_job(
            user_id=admin_user.id,
            assigned_form_id=44,
            assignment_entity_status_ids=[11, 12],
        )
        job = AIJob.query.get(job_id)
        assert job is not None
        assert job.job_type == FDRS_PUBLICATION_JOB_TYPE
        assert job.total_items == 1
        assert len(job.items) == 1
        item = job.items[0]
        assert item.entity_type == "assigned_form"
        assert item.entity_id == 44
        assert item.payload["assignment_entity_status_ids"] == [11, 12]
        assert job.meta["assigned_form_id"] == 44


class TestGetActiveFdrsPublicationJobs:
    def test_returns_non_terminal_jobs_for_user(self, db_session, admin_user):
        job_id = create_fdrs_publication_job(
            user_id=admin_user.id,
            assigned_form_id=44,
            assignment_entity_status_ids=None,
        )
        active = get_active_fdrs_publication_jobs_for_user(admin_user.id, assigned_form_id=44)
        assert any(row["job_id"] == job_id for row in active)

        job = AIJob.query.get(job_id)
        job.status = "completed"
        db_session.commit()
        active_after = get_active_fdrs_publication_jobs_for_user(admin_user.id, assigned_form_id=44)
        assert not any(row["job_id"] == job_id for row in active_after)


class TestRequestFdrsPublicationCancel:
    def test_cancel_running_job(self, db_session, admin_user):
        job_id = create_fdrs_publication_job(
            user_id=admin_user.id,
            assigned_form_id=44,
            assignment_entity_status_ids=None,
        )
        job = AIJob.query.get(job_id)
        job.status = "running"
        db_session.commit()

        with patch("plugins.fdrs.services.fdrs_publication_job.signal_job_cancel") as mock_signal:
            status = request_fdrs_publication_cancel(job_id)
        assert status == "cancel_requested"
        db_session.refresh(job)
        assert job.status == "cancel_requested"
        mock_signal.assert_called_once_with(job_id)

    def test_cancel_terminal_job_is_noop(self, db_session, admin_user):
        job_id = create_fdrs_publication_job(
            user_id=admin_user.id,
            assigned_form_id=44,
            assignment_entity_status_ids=None,
        )
        job = AIJob.query.get(job_id)
        job.status = "completed"
        db_session.commit()
        status = request_fdrs_publication_cancel(job_id)
        assert status == "completed"
