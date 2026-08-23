"""Tests for UPR visuals bulk export jobs on AIJob / ai_job_runner."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models import AIJob, AIJobItem
from plugins.upr_visuals.bulk_job import (
    BULK_EXPORT_JOB_TYPE,
    _process_bulk_export_item_sync,
    build_bulk_export_status_payload,
    create_bulk_export_job,
    get_active_bulk_export_job,
    request_bulk_export_cancel,
)

pytestmark = [pytest.mark.unit]


def _create_job(admin_user, **overrides):
    kwargs = {
        "user_id": admin_user.id,
        "assigned_form_id": 7,
        "dashboard_ids": ["combined"],
        "aes_ids": [11],
        "export_format": "png",
        "include_narrative": False,
        "narrative_files": None,
        "lang": "en",
    }
    kwargs.update(overrides)
    return create_bulk_export_job(**kwargs)


@pytest.fixture
def assigned_form(monkeypatch):
    monkeypatch.setattr(
        "plugins.upr_visuals.data.get_assigned_form_for_bulk",
        lambda _id: SimpleNamespace(id=7, template_id=24, period_name="Annual 2026"),
    )
    monkeypatch.setattr(
        "plugins.upr_visuals.bulk_job.dashboards_for_kind",
        lambda _kind: [SimpleNamespace(id="combined"), SimpleNamespace(id="in_support")],
    )


class TestCreateBulkExportJob:
    def test_creates_job_with_single_item(self, db_session, admin_user, assigned_form, app):
        with app.app_context():
            job_id = _create_job(admin_user, lang="fr")
        job = AIJob.query.get(job_id)
        assert job is not None
        assert job.job_type == BULK_EXPORT_JOB_TYPE
        assert job.total_items == 1
        assert job.status == "queued"
        assert len(job.items) == 1
        item = job.items[0]
        assert item.entity_type == "assigned_form"
        assert item.entity_id == 7
        assert item.status == "queued"
        assert item.payload["lang"] == "fr"
        assert item.payload["dashboard_ids"] == ["combined"]
        payload = build_bulk_export_status_payload(job_id)
        assert payload["job_id"] == job_id
        assert payload["status"] == "queued"
        assert payload["progress"] == 0
        assert payload["lang"] == "fr"

    def test_idml_locks_combined(self, db_session, admin_user, assigned_form, app):
        with app.app_context():
            job_id = _create_job(
                admin_user,
                dashboard_ids=["in_support", "combined"],
                export_format="idml",
                include_narrative=True,
                narrative_files={"afg": b"PK\x03\x04fake"},
            )
        item = AIJobItem.query.filter_by(job_id=job_id).one()
        assert item.payload["export_format"] == "idml"
        assert item.payload["include_narrative"] is True
        assert item.payload["dashboard_ids"] == ["combined"]
        assert item.payload["narrative_paths"]["afg"]

    def test_rejects_in_flight_when_thread_alive(self, db_session, admin_user, assigned_form, app):
        with app.app_context():
            _create_job(admin_user)
            with patch("plugins.upr_visuals.bulk_job.is_job_thread_alive", return_value=True):
                with pytest.raises(RuntimeError, match="already running"):
                    _create_job(admin_user)

    def test_orphaned_job_is_failed_so_new_export_can_start(self, db_session, admin_user, assigned_form, app):
        with app.app_context():
            first = _create_job(admin_user)
            with patch("plugins.upr_visuals.bulk_job.is_job_thread_alive", return_value=False):
                second = _create_job(admin_user)
        first_job = AIJob.query.get(first)
        assert first_job.status == "failed"
        assert "stopped" in (first_job.error or "").lower()
        second_job = AIJob.query.get(second)
        assert second_job is not None
        assert second_job.status == "queued"
        assert second != first


class TestCancelAndActive:
    def test_cancel_running_job(self, db_session, admin_user, assigned_form, app):
        with app.app_context():
            job_id = _create_job(admin_user)
        job = AIJob.query.get(job_id)
        job.status = "running"
        db_session.commit()
        with patch("plugins.upr_visuals.bulk_job.signal_job_cancel") as mock_signal:
            status = request_bulk_export_cancel(job_id)
        assert status == "cancel_requested"
        db_session.refresh(job)
        assert job.status == "cancel_requested"
        mock_signal.assert_called_once_with(job_id)

    def test_cancel_terminal_job_is_noop(self, db_session, admin_user, assigned_form, app):
        with app.app_context():
            job_id = _create_job(admin_user)
        job = AIJob.query.get(job_id)
        job.status = "completed"
        db_session.commit()
        assert request_bulk_export_cancel(job_id) == "completed"

    def test_get_active_returns_running_then_completed_zip(self, db_session, admin_user, assigned_form, app):
        with app.app_context():
            job_id = _create_job(admin_user)
        active = get_active_bulk_export_job()
        assert active and active["job_id"] == job_id
        job = AIJob.query.get(job_id)
        job.status = "completed"
        job.meta = dict(job.meta or {}, zip_key="exports/x/upr-visuals.zip")
        db_session.commit()
        active = get_active_bulk_export_job()
        assert active and active["zip_key"] == "exports/x/upr-visuals.zip"


class TestRenderLoop:
    def test_render_failure_still_completes_zip(self, db_session, admin_user, assigned_form, app, monkeypatch):
        with app.app_context():
            job_id = _create_job(admin_user, aes_ids=[11, 22])
        item = AIJobItem.query.filter_by(job_id=job_id).one()
        monkeypatch.setattr(
            "plugins.upr_visuals.data.list_countries_for_bulk",
            lambda _id: [{"aes_id": 11}, {"aes_id": 22}],
        )
        monkeypatch.setattr(
            "plugins.upr_visuals.bulk_job.build_payload",
            lambda aes_id, **_kw: {
                "meta": {"iso3": "AFG" if aes_id == 11 else "BGD", "round_code": "P26"},
                "dashboards": [{"id": "combined"}],
            },
        )
        monkeypatch.setattr("plugins.upr_visuals.bulk_job.render_dashboard_html", lambda *_a, **_k: "<html/>")
        calls = {"n": 0}

        def fake_png(_html, tmp, dashboard_id="combined", **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("render boom")
            Path(tmp).write_bytes(b"png-bytes")

        monkeypatch.setattr("plugins.upr_visuals.service.render_png_isolated", fake_png)
        uploaded: dict = {}
        monkeypatch.setattr(
            "plugins.upr_visuals.bulk_job.storage_service.upload",
            lambda _c, key, data: uploaded.update(key=key, data=data),
        )
        _process_bulk_export_item_sync(app, job_id=job_id, item_id=item.id)
        db_session.refresh(item)
        assert item.status == "completed"
        assert uploaded.get("key")
        payload = build_bulk_export_status_payload(job_id)
        assert payload["zip_key"] == uploaded["key"]
        assert "render boom" in (payload.get("error") or "")

    def test_bulk_pdf_writes_zip(self, db_session, admin_user, assigned_form, app, monkeypatch):
        with app.app_context():
            job_id = _create_job(admin_user, export_format="pdf")
        item = AIJobItem.query.filter_by(job_id=job_id).one()
        monkeypatch.setattr(
            "plugins.upr_visuals.data.list_countries_for_bulk",
            lambda _id: [{"aes_id": 11, "iso3": "AFG", "country_name": "Afghanistan"}],
        )
        monkeypatch.setattr(
            "plugins.upr_visuals.bulk_job.build_payload",
            lambda aes_id, **_kw: {
                "meta": {"iso3": "AFG", "round_code": "P26", "document_title": "Afghanistan INP AR 2026"},
                "dashboards": [{"id": "combined"}],
            },
        )
        monkeypatch.setattr("plugins.upr_visuals.bulk_job.render_dashboard_html", lambda *_a, **_k: "<html/>")

        def fake_isolated(job, timeout=120):
            Path(job["output_path"]).write_bytes(b"%PDF-1.4")
            return Path(job["output_path"])

        monkeypatch.setattr("plugins.upr_visuals.service.run_isolated", fake_isolated)
        uploaded: dict = {}
        monkeypatch.setattr(
            "plugins.upr_visuals.bulk_job.storage_service.upload",
            lambda _c, key, data: uploaded.update(key=key, data=data),
        )
        _process_bulk_export_item_sync(app, job_id=job_id, item_id=item.id)
        db_session.refresh(item)
        assert item.status == "completed"
        with zipfile.ZipFile(io.BytesIO(uploaded["data"])) as zf:
            assert any(name.endswith(".pdf") for name in zf.namelist())
