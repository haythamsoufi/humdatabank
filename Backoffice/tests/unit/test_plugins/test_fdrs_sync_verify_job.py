"""Tests for FDRS sync verification background job service."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models import AIJob
from app.services.imports.async_import_job_store import FDRS_SYNC_VERIFY_JOB_TYPE
from plugins.fdrs.services.fdrs_sync_verify_job import (
    create_fdrs_sync_verify_job,
    get_active_fdrs_sync_verify_jobs_for_user,
    request_fdrs_sync_verify_cancel,
)

pytestmark = [pytest.mark.unit]


class TestCreateFdrsSyncVerifyJob:
    def test_creates_job_with_single_item(self, db_session, admin_user):
        job_id = create_fdrs_sync_verify_job(
            user_id=admin_user.id,
            template_id=21,
            fdrs_years=[2024],
            skip_imputed=True,
            fresh_imputed=False,
            problems_only=True,
            fdrs_reported_import_states=None,
            output_path="/tmp/verify.xlsx",
        )
        job = AIJob.query.get(job_id)
        assert job is not None
        assert job.job_type == FDRS_SYNC_VERIFY_JOB_TYPE
        assert job.total_items == 1
        assert len(job.items) == 1
        item = job.items[0]
        assert item.payload["skip_imputed"] is True
        assert item.payload["problems_only"] is True
        assert item.payload["fdrs_years"] == [2024]


class TestGetActiveFdrsSyncVerifyJobs:
    def test_returns_non_terminal_jobs_for_user(self, db_session, admin_user):
        job_id = create_fdrs_sync_verify_job(
            user_id=admin_user.id,
            template_id=21,
            fdrs_years=[2024],
            skip_imputed=False,
            fresh_imputed=False,
            problems_only=False,
            fdrs_reported_import_states=None,
            output_path="/tmp/verify.xlsx",
        )
        active = get_active_fdrs_sync_verify_jobs_for_user(admin_user.id, template_id=21)
        assert any(row["job_id"] == job_id for row in active)

        job = AIJob.query.get(job_id)
        job.status = "completed"
        db_session.commit()
        active_after = get_active_fdrs_sync_verify_jobs_for_user(admin_user.id, template_id=21)
        assert not any(row["job_id"] == job_id for row in active_after)


class TestRequestFdrsSyncVerifyCancel:
    def test_cancel_running_job(self, db_session, admin_user):
        job_id = create_fdrs_sync_verify_job(
            user_id=admin_user.id,
            template_id=21,
            fdrs_years=[2024],
            skip_imputed=False,
            fresh_imputed=False,
            problems_only=False,
            fdrs_reported_import_states=None,
            output_path="/tmp/verify.xlsx",
        )
        job = AIJob.query.get(job_id)
        job.status = "running"
        db_session.commit()

        with patch("plugins.fdrs.services.fdrs_sync_verify_job.signal_job_cancel") as mock_signal:
            status = request_fdrs_sync_verify_cancel(job_id)
        assert status == "cancel_requested"
        db_session.refresh(job)
        assert job.status == "cancel_requested"
        mock_signal.assert_called_once_with(job_id)


def test_execute_verification_reuses_app_context(app, tmp_path):
    from plugins.fdrs.scripts_path import ensure_fdrs_scripts_in_path

    ensure_fdrs_scripts_in_path()
    import verify_fdrs_sync as verify_mod

    snapshot = [
        {
            "ISO3": "KEN",
            "DonCode": "DKEN001",
            "year": "2024",
            "KPI_code": "KPI_PeopleVol_Tot",
            "BaseKPI": "KPI_PeopleVol",
            "Value": "1500",
            "ReportedValue": "1500",
            "ImputedValue": "",
            "ValueStatus": "Published Reported",
            "State": 500,
            "in_fdrs_data_stage": "yes",
            "fdrs_data_filter_reason": "",
        }
    ]
    out = tmp_path / "fdrs_sync_verification.xlsx"
    with app.app_context():
        with patch("app.create_app") as create_app, \
             patch.object(verify_mod, "_resolve_api_key", return_value="test-key"), \
             patch.object(
                 verify_mod,
                 "build_fdrs_table",
                 return_value=([], {}, {}, snapshot, {}),
             ), \
             patch.object(
                 verify_mod,
                 "_load_databank_lookups",
                 return_value=({}, {}, set(), {}, {}, {}),
             ):
            result = verify_mod.execute_verification(
                years=[2024],
                output_path=str(out),
                skip_imputed=True,
            )
            create_app.assert_not_called()
    assert out.is_file()
    assert result["total"] >= 1
    assert "matched" in result
