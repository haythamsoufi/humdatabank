"""UPR visuals assignment and bulk-admin HTTP routes."""

from __future__ import annotations

from io import BytesIO

import pytest
from flask import Response, abort

from plugins.upr_visuals import routes
from plugins.upr_visuals.routes import MAX_BULK_AES_IDS, MAX_BULK_DASHBOARDS
from plugins.upr_visuals.service import UprVisualsService


@pytest.mark.unit
def test_live_assignment_pdf_route_is_registered(app):
    endpoint, values = app.url_map.bind("localhost").match("/assignment/42/pdf")
    assert endpoint == "upr_visuals.assignment_pdf"
    assert values == {"aes_id": 42}


@pytest.mark.unit
def test_dashboard_assignment_pdf_route_is_registered(app):
    endpoint, values = app.url_map.bind("localhost").match("/assignment/42/pdf/combined")
    assert endpoint == "upr_visuals.assignment_pdf_dashboard"
    assert values == {"aes_id": 42, "dashboard_id": "combined"}


@pytest.mark.unit
def test_live_assignment_pdf_requires_login(client):
    response = client.get("/assignment/42/pdf")
    assert response.status_code in (302, 401)


@pytest.mark.unit
def test_bulk_routes_require_login(client):
    assert client.get("/admin/data-exploration/upr-visuals/assignments").status_code in (302, 401)
    assert client.get("/admin/data-exploration/upr-visuals/status").status_code in (302, 401)
    assert client.post("/admin/data-exploration/upr-visuals/generate", json={}).status_code in (302, 401)
    assert client.post("/admin/data-exploration/upr-visuals/cancel", json={"job_id": "x"}).status_code in (302, 401)
    assert client.get("/admin/data-exploration/upr-visuals/download/job-x").status_code in (302, 401)


@pytest.mark.unit
def test_bulk_routes_forbid_non_system_manager(logged_in_focal_client):
    resp = logged_in_focal_client.get("/admin/data-exploration/upr-visuals/assignments")
    assert resp.status_code in (302, 403)
    resp = logged_in_focal_client.get("/admin/data-exploration/upr-visuals/status")
    assert resp.status_code in (302, 403)


@pytest.mark.unit
def test_assignment_pdf_unknown_aes_is_404(logged_in_sm_client):
    response = logged_in_sm_client.get("/assignment/999999999/pdf")
    assert response.status_code == 404


@pytest.mark.unit
def test_assignment_pdf_forbidden_when_no_assignment_access(logged_in_sm_client, monkeypatch):
    monkeypatch.setattr(routes, "_aes_or_404", lambda _aes_id: abort(403))
    response = logged_in_sm_client.get("/assignment/1/pdf")
    assert response.status_code == 403


@pytest.mark.unit
def test_generate_rejects_oversized_country_and_dashboard_lists(logged_in_sm_client):
    too_many_aes = logged_in_sm_client.post(
        "/admin/data-exploration/upr-visuals/generate",
        json={
            "assigned_form_id": 1,
            "aes_ids": list(range(MAX_BULK_AES_IDS + 1)),
            "dashboard_ids": ["combined"],
        },
    )
    assert too_many_aes.status_code == 400
    assert str(MAX_BULK_AES_IDS) in (too_many_aes.get_json() or {}).get("error", "")

    too_many_dash = logged_in_sm_client.post(
        "/admin/data-exploration/upr-visuals/generate",
        json={
            "assigned_form_id": 1,
            "aes_ids": [1],
            "dashboard_ids": [f"d{i}" for i in range(MAX_BULK_DASHBOARDS + 1)],
        },
    )
    assert too_many_dash.status_code == 400
    assert str(MAX_BULK_DASHBOARDS) in (too_many_dash.get_json() or {}).get("error", "")


@pytest.mark.unit
def test_generate_status_cancel_download_flow(logged_in_sm_client, monkeypatch):
    monkeypatch.setattr(
        UprVisualsService,
        "start_bulk",
        classmethod(lambda cls, **_kw: "job-flow"),
    )
    monkeypatch.setattr(
        UprVisualsService,
        "get_status",
        classmethod(lambda cls, job_id=None: {"job_id": job_id or "job-flow", "status": "queued"}),
    )
    monkeypatch.setattr(
        UprVisualsService,
        "cancel",
        classmethod(lambda cls, job_id: job_id == "job-flow"),
    )

    monkeypatch.setattr(
        UprVisualsService,
        "serve_zip",
        classmethod(lambda cls, job_id: Response(b"PK", mimetype="application/zip")),
    )

    created = logged_in_sm_client.post(
        "/admin/data-exploration/upr-visuals/generate",
        json={"assigned_form_id": 3, "aes_ids": [1], "dashboard_ids": ["combined"]},
    )
    assert created.status_code == 200
    body = created.get_json()
    assert body["success"] is True
    assert body["job_id"] == "job-flow"

    status = logged_in_sm_client.get("/admin/data-exploration/upr-visuals/status?job_id=job-flow")
    assert status.status_code == 200
    assert status.get_json()["status"]["job_id"] == "job-flow"

    cancelled = logged_in_sm_client.post(
        "/admin/data-exploration/upr-visuals/cancel",
        json={"job_id": "job-flow"},
    )
    assert cancelled.status_code == 200
    assert cancelled.get_json()["cancelled"] is True

    download = logged_in_sm_client.get("/admin/data-exploration/upr-visuals/download/job-flow")
    assert download.status_code == 200


@pytest.mark.unit
def test_narrative_route_rejects_missing_and_bad_format(logged_in_sm_client, monkeypatch):
    monkeypatch.setattr(routes, "_aes_or_404", lambda _aes_id: object())

    missing_fmt = logged_in_sm_client.post("/assignment/1/visuals/narrative", data={})
    assert missing_fmt.status_code == 400

    missing_file = logged_in_sm_client.post(
        "/assignment/1/visuals/narrative",
        data={"format": "pdf"},
    )
    assert missing_file.status_code == 400
    assert "Word" in (missing_file.get_json() or {}).get("error", "")

    bad_docx = logged_in_sm_client.post(
        "/assignment/1/visuals/narrative",
        data={"format": "pdf", "file": (BytesIO(b"not-a-docx"), "notes.txt")},
        content_type="multipart/form-data",
    )
    assert bad_docx.status_code == 400
