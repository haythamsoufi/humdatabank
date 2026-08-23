"""UPR visuals assignment and bulk-admin HTTP routes."""

from __future__ import annotations

from io import BytesIO

import pytest
from flask import Response, abort

from plugins.upr_visuals import routes
from plugins.upr_visuals.routes import MAX_BULK_AES_IDS, MAX_BULK_DASHBOARDS


@pytest.mark.unit
def test_visuals_progress_route_is_registered(app):
    endpoint, values = app.url_map.bind("localhost").match("/assignment/42/visuals/progress")
    assert endpoint == "upr_visuals.assignment_visuals_progress"
    assert values == {"aes_id": 42}


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


def _stub_live_pdf(monkeypatch):
    monkeypatch.setattr(routes, "_aes_or_404", lambda _aes_id: object())
    monkeypatch.setattr(routes, "_requested_language", lambda *, strict=False: "en")
    monkeypatch.setattr(routes, "visuals_browser_title", lambda _aes: "NS — Unified Plan")
    monkeypatch.setattr(
        routes.UprVisualsService,
        "pdf_bytes",
        classmethod(lambda cls, aes_id, dashboard_id, lang="en": (b"%PDF-1.4", "NS.pdf")),
    )


@pytest.mark.unit
def test_assignment_pdf_mobile_gets_inline_file(logged_in_sm_client, monkeypatch):
    _stub_live_pdf(monkeypatch)
    iphone = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    )
    response = logged_in_sm_client.get("/assignment/1/pdf", headers={"User-Agent": iphone})
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-1.4"
    assert response.headers["Content-Disposition"].startswith("inline;")


@pytest.mark.unit
def test_assignment_pdf_desktop_gets_titled_viewer(logged_in_sm_client, monkeypatch):
    _stub_live_pdf(monkeypatch)
    desktop = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    response = logged_in_sm_client.get("/assignment/1/pdf", headers={"User-Agent": desktop})
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.mimetype.startswith("text/html")
    assert "<title>NS — Unified Plan</title>" in html
    assert "name='viewport'" in html
    assert "raw=1" in html
    assert "upr-pdf-fallback" in html


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

    bad_format = logged_in_sm_client.post(
        "/admin/data-exploration/upr-visuals/generate",
        json={"assigned_form_id": 1, "aes_ids": [1], "dashboard_ids": ["combined"], "export_format": "docx"},
    )
    assert bad_format.status_code == 400


@pytest.mark.unit
def test_generate_status_cancel_download_flow(logged_in_sm_client, monkeypatch):
    monkeypatch.setattr(routes, "create_bulk_export_job", lambda **_kw: "job-flow")
    monkeypatch.setattr(routes, "start_bulk_export_job", lambda *_a, **_k: None)
    monkeypatch.setattr(
        routes,
        "build_bulk_export_status_payload",
        lambda job_id=None: {"job_id": job_id or "job-flow", "status": "queued"},
    )
    monkeypatch.setattr(routes, "ensure_bulk_export_job_running", lambda *_a, **_k: None)
    monkeypatch.setattr(routes, "request_bulk_export_cancel", lambda job_id: "cancel_requested")
    monkeypatch.setattr(
        routes,
        "serve_bulk_export_zip",
        lambda job_id: Response(b"PK", mimetype="application/zip"),
    )

    created = logged_in_sm_client.post(
        "/admin/data-exploration/upr-visuals/generate",
        json={
            "assigned_form_id": 3,
            "aes_ids": [1],
            "dashboard_ids": ["combined"],
            "export_format": "pdf",
            "include_narrative": True,
        },
    )
    assert created.status_code == 202
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


@pytest.mark.unit
def test_narrative_route_starts_background_job(logged_in_sm_client, monkeypatch):
    started = []
    monkeypatch.setattr(routes, "_aes_or_404", lambda _aes_id: object())
    monkeypatch.setattr(routes, "read_docx_upload", lambda upload, filename="": b"PK")
    monkeypatch.setattr(routes, "create_assignment_export_job", lambda **_kw: "job-nar")
    monkeypatch.setattr(routes, "start_assignment_export_job", lambda *args, **_k: started.append(args[1]))
    monkeypatch.setattr(
        routes,
        "build_assignment_export_status",
        lambda job_id: {"job_id": job_id, "status": "queued", "aes_id": 1, "message": "Queued"},
    )

    created = logged_in_sm_client.post(
        "/assignment/1/visuals/narrative",
        data={"format": "pdf", "lang": "ar", "file": (BytesIO(b"PK"), "Uganda.docx")},
        content_type="multipart/form-data",
    )
    assert created.status_code == 202
    body = created.get_json()
    assert body["success"] is True
    assert body["job_id"] == "job-nar"
    assert started == ["job-nar"]

    monkeypatch.setattr(routes, "ensure_assignment_export_job_running", lambda *_a, **_k: None)
    monkeypatch.setattr(
        routes,
        "build_assignment_export_status",
        lambda job_id: {"job_id": job_id, "status": "running", "aes_id": 1, "message": "Generating PDF…"},
    )
    status = logged_in_sm_client.get("/assignment/1/visuals/narrative/status?job_id=job-nar")
    assert status.status_code == 200
    assert status.get_json()["status"]["job_id"] == "job-nar"

    monkeypatch.setattr(
        routes,
        "serve_assignment_export",
        lambda job_id, aes_id: Response(b"%PDF", mimetype="application/pdf"),
    )
    download = logged_in_sm_client.get("/assignment/1/visuals/narrative/file/job-nar")
    assert download.status_code == 200
