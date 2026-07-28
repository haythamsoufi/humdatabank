"""Tests for cross-worker async import job persistence."""

import uuid

import pytest

from app.models import AIJob
from app.models.forms import FormData
from app.services.imports.async_import_job_store import (
    UPR_EXCEL_IMPORT_JOB_TYPE,
    create_import_job,
    get_import_job,
    is_import_job_cancel_requested,
    request_import_job_cancel,
    update_import_job,
)

pytestmark = [pytest.mark.unit]


class TestAsyncImportJobStore:
    def test_update_import_job_leaves_main_session_pending_objects_unflushed(
        self, db_session, admin_user
    ):
        job_id = uuid.uuid4().hex
        create_import_job(
            job_id=job_id,
            job_type=UPR_EXCEL_IMPORT_JOB_TYPE,
            user_id=admin_user.id,
            initial={"kind": "upr_excel", "status": "running"},
        )

        pending = FormData(
            assignment_entity_status_id=999_999_999,
            form_item_id=999_999_999,
            value="pending-import-row",
        )
        db_session.add(pending)

        update_import_job(
            job_id,
            force=True,
            status="running",
            message="Processing 50/1000",
            percent=12.5,
        )

        # Import rows stay pending on the main session; job progress uses an isolated session.
        assert pending in db_session.new

        job = get_import_job(job_id)
        assert job is not None
        assert job["message"] == "Processing 50/1000"
        assert job["percent"] == 12.5

    def test_cancel_check_does_not_autoflush_main_session(self, db_session, admin_user):
        job_id = uuid.uuid4().hex
        create_import_job(
            job_id=job_id,
            job_type=UPR_EXCEL_IMPORT_JOB_TYPE,
            user_id=admin_user.id,
            initial={"kind": "upr_excel"},
        )
        request_import_job_cancel(job_id)

        pending = FormData(
            assignment_entity_status_id=999_999_998,
            form_item_id=999_999_998,
            value="cancel-check-pending",
        )
        db_session.add(pending)

        assert is_import_job_cancel_requested(job_id) is True
        assert pending in db_session.new

    def test_get_import_job_reads_persisted_row(self, admin_user):
        job_id = uuid.uuid4().hex
        create_import_job(
            job_id=job_id,
            job_type=UPR_EXCEL_IMPORT_JOB_TYPE,
            user_id=admin_user.id,
            initial={"kind": "upr_excel", "stage": "queued"},
        )

        job = get_import_job(job_id)
        assert job is not None
        assert job["job_id"] == job_id
        assert job["kind"] == "upr_excel"

        assert AIJob.query.get(job_id) is not None
