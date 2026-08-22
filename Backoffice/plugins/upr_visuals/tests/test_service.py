"""Unit tests for UprVisualsService job guard and bulk resilience."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask

from plugins.upr_visuals import service as svc
from plugins.upr_visuals.service import UprVisualsService


@pytest.fixture
def isolated_jobs():
    with svc._lock:
        svc._jobs.clear()
        svc._threads.clear()
    yield
    with svc._lock:
        svc._jobs.clear()
        svc._threads.clear()


@pytest.fixture
def flask_app(tmp_path):
    app = Flask("upr-visuals-service-test")
    app.instance_path = str(tmp_path)
    return app


@pytest.mark.unit
def test_start_bulk_rejects_in_flight_job(isolated_jobs, flask_app, monkeypatch):
    monkeypatch.setattr(
        "plugins.upr_visuals.data.get_assigned_form_for_bulk",
        lambda _id: SimpleNamespace(id=7, template_id=24, period_name="Annual 2026"),
    )
    svc._jobs["running-job"] = {
        "job_id": "running-job",
        "status": "running",
        "created_at": "2026-01-01T00:00:00",
    }
    with flask_app.app_context():
        with pytest.raises(RuntimeError, match="already running"):
            UprVisualsService.start_bulk(assigned_form_id=7, dashboard_ids=["combined"])


@pytest.mark.unit
def test_bulk_render_failure_still_completes_zip(isolated_jobs, flask_app, monkeypatch):
    job_id = "job-partial"
    svc._jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "assigned_form_id": 1,
        "template_id": 24,
        "period_name": "Annual 2026",
        "dashboard_ids": ["combined"],
        "aes_ids": [11, 22],
        "progress": 0,
        "total": 0,
        "message": "Queued",
        "zip_key": None,
        "error": None,
        "created_at": "2026-01-01T00:00:00",
        "finished_at": None,
    }
    monkeypatch.setattr(
        "plugins.upr_visuals.data.list_countries_for_bulk",
        lambda _id: [{"aes_id": 11}, {"aes_id": 22}],
    )
    monkeypatch.setattr(
        svc,
        "build_payload",
        lambda aes_id, **_kw: {
            "meta": {"iso3": "AFG" if aes_id == 11 else "BGD", "round_code": "P26"},
            "dashboards": [{"id": "combined"}],
        },
    )
    monkeypatch.setattr(svc, "render_dashboard_html", lambda *_a, **_k: "<html/>")

    calls = {"n": 0}

    def fake_png(_html, tmp, dashboard_id="combined"):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("render boom")
        tmp.write_bytes(b"png-bytes")

    monkeypatch.setattr(svc, "render_png", fake_png)
    monkeypatch.setattr(UprVisualsService, "_render_with_timeout", classmethod(lambda cls, fn, timeout=120: fn()))

    uploaded: dict = {}

    def fake_upload(_category, key, data):
        uploaded["key"] = key
        uploaded["data"] = data

    monkeypatch.setattr(svc.storage_service, "upload", fake_upload)

    UprVisualsService._run_bulk(flask_app, job_id)

    job = svc._jobs[job_id]
    assert job["status"] == "completed"
    assert uploaded.get("key")
    assert uploaded.get("data")
    assert "render boom" in (job.get("error") or "")
    assert job.get("zip_key") == uploaded["key"]
