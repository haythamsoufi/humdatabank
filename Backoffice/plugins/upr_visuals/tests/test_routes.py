"""HTTP helpers for live assignment PDF export."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_pdf_response_is_inline_by_default():
    from plugins.upr_visuals.routes import _pdf_response

    response = _pdf_response(b"%PDF-1.4", "AFG_P25_combined.pdf", download=False)
    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-1.4"
    assert response.headers["Content-Disposition"] == 'inline; filename="AFG_P25_combined.pdf"'
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.unit
def test_pdf_response_encodes_unicode_filename():
    from plugins.upr_visuals.routes import _pdf_response

    response = _pdf_response(
        b"%PDF-1.4",
        "Bangladesh — Unified Plan – 2026.pdf",
        download=True,
    )
    header = response.headers["Content-Disposition"]
    header.encode("latin-1")
    assert 'filename="Bangladesh - Unified Plan - 2026.pdf"' in header
    assert "filename*=UTF-8''" in header
    assert "%E2%80%94" in header


@pytest.mark.unit
def test_pdf_response_arabic_filename_keeps_utf8_country():
    from plugins.upr_visuals.routes import _pdf_response

    response = _pdf_response(
        b"%PDF-1.4",
        "أفغانستان - Unified Country Report.pdf",
        download=True,
    )
    header = response.headers["Content-Disposition"]
    header.encode("latin-1")
    assert "filename*=UTF-8''" in header
    assert "%D8%A3" in header
    assert "Unified Country Report.pdf" in header


@pytest.mark.unit
def test_pdf_response_download_uses_attachment():
    from plugins.upr_visuals.routes import _pdf_response

    response = _pdf_response(b"%PDF-1.4", "AFG_P25_combined.pdf", download=True)
    assert response.headers["Content-Disposition"] == 'attachment; filename="AFG_P25_combined.pdf"'


@pytest.mark.unit
def test_assignment_pdf_response_queues_background_job(monkeypatch):
    from flask import Response

    from plugins.upr_visuals import routes

    queued = []
    monkeypatch.setattr(routes, "_aes_or_404", lambda aes_id: object())
    monkeypatch.setattr(
        routes,
        "_queue_visual_export",
        lambda aes_id, fmt, dashboard_id="combined": queued.append((aes_id, fmt, dashboard_id)) or "job-pdf",
    )
    monkeypatch.setattr(
        routes,
        "_export_wait_response",
        lambda aes_id, job_id, download=True: Response(
            f"wait:{job_id}:{download}", mimetype="text/html"
        ),
    )
    response = routes._assignment_pdf_response(9, "combined", download=False)
    assert response.get_data(as_text=True) == "wait:job-pdf:False"
    assert queued == [(9, "pdf", "combined")]


@pytest.mark.unit
def test_queue_visual_export_reuses_matching_job(monkeypatch):
    from flask import Flask

    from plugins.upr_visuals import routes

    started = []
    monkeypatch.setattr(routes, "_requested_language", lambda *, strict=False: "ar")
    monkeypatch.setattr(
        routes,
        "find_reusable_assignment_export_job",
        lambda **_k: "job-reuse",
    )
    monkeypatch.setattr(
        routes,
        "ensure_assignment_export_job_running",
        lambda _app, job_id: started.append(job_id),
    )
    monkeypatch.setattr(
        routes,
        "create_assignment_export_job",
        lambda **_k: (_ for _ in ()).throw(AssertionError("should reuse")),
    )
    app = Flask(__name__)
    with app.app_context():
        assert routes._queue_visual_export(1641, "pdf") == "job-reuse"
    assert started == ["job-reuse"]


@pytest.mark.unit
def test_export_wait_copy_matches_format():
    from plugins.upr_visuals.routes import _export_wait_copy

    assert _export_wait_copy("pdf")[0] == "Preparing your PDF"
    assert _export_wait_copy("png")[0] == "Preparing your image"
    assert _export_wait_copy("idml")[0] == "Preparing InDesign files"


@pytest.mark.unit
def test_wants_json_export_for_xhr():
    from flask import Flask

    from plugins.upr_visuals.routes import _wants_json_export

    app = Flask(__name__)
    with app.test_request_context("/", headers={"X-Requested-With": "XMLHttpRequest"}):
        assert _wants_json_export() is True
    with app.test_request_context("/", headers={"Accept": "application/json"}):
        assert _wants_json_export() is True
    with app.test_request_context("/", headers={"Accept": "text/html"}):
        assert _wants_json_export() is False


@pytest.mark.unit
def test_assignment_png_returns_json_job(monkeypatch):
    from flask import Flask

    from plugins.upr_visuals import routes

    monkeypatch.setattr(routes, "_aes_or_404", lambda aes_id: object())
    monkeypatch.setattr(routes, "_queue_visual_export", lambda *_a, **_k: "job-png")
    monkeypatch.setattr(
        routes,
        "build_assignment_export_status",
        lambda job_id: {"job_id": job_id, "status": "queued", "export_format": "png"},
    )
    app = Flask(__name__)
    with app.test_request_context(
        "/assignment/9/png/combined",
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    ):
        response = routes._assignment_png_response(9, "combined")
    assert response.status_code == 202
    data = response.get_json()
    assert data["job_id"] == "job-png"
    assert data["status"]["status"] == "queued"


@pytest.mark.unit
def test_export_wait_page_has_live_status(monkeypatch):
    from flask import Flask

    from plugins.upr_visuals import routes

    monkeypatch.setattr(
        routes, "build_assignment_export_status", lambda _job_id: {"status": "running"}
    )
    monkeypatch.setattr(
        routes,
        "url_for",
        lambda endpoint, **_k: (
            "/static/js/upr-visuals-export-wait.js"
            if endpoint == "upr_visuals.static_file"
            else "/status"
        ),
    )
    app = Flask(__name__)
    with app.test_request_context("/"):
        response = routes._export_wait_response(
            9, "job-1", download=False, file_url="/assignment/9/pdf?raw=1&job_id=job-1"
        )
    html = response.get_data(as_text=True)
    assert response.mimetype.startswith("text/html")
    assert "<title>Preparing your PDF</title>" in html
    assert "id='upr-export-wait-status'" in html
    assert "upr-export-wait__sweep" in html
    assert "Usually ready in about 15 seconds." not in html
    assert "upr-visuals-export-wait.js" in html


@pytest.mark.unit
def test_export_wait_serves_completed_file(monkeypatch):
    from flask import Flask, Response

    from plugins.upr_visuals import routes

    served = []
    monkeypatch.setattr(
        routes, "build_assignment_export_status", lambda _job_id: {"status": "completed"}
    )
    monkeypatch.setattr(
        routes,
        "serve_assignment_export",
        lambda job_id, aes_id, as_attachment=True: served.append((job_id, aes_id, as_attachment))
        or Response(b"%PDF-1.4", mimetype="application/pdf"),
    )
    app = Flask(__name__)
    with app.test_request_context("/"):
        response = routes._export_wait_response(9, "job-ready", download=False)
    assert response.mimetype == "application/pdf"
    assert served == [("job-ready", 9, False)]


@pytest.mark.unit
def test_pdf_viewer_sets_document_title():
    from plugins.upr_visuals.routes import _pdf_viewer_response

    response = _pdf_viewer_response(
        title="Bangladesh — Unified Plan – 2026",
        pdf_url="/assignment/9/pdf?raw=1",
        download_url="/assignment/9/pdf?download=1",
        script_url="/upr-visuals/static/js/upr-visuals-pdf-viewer.js",
        lang="ar",
    )
    html = response.get_data(as_text=True)
    assert response.mimetype.startswith("text/html")
    assert "<title>Bangladesh — Unified Plan – 2026</title>" in html
    assert "raw=1" in html
    assert "download=1" in html
    assert "name='viewport'" in html
    assert "upr-pdf-fallback" in html
    assert "upr-visuals-pdf-viewer.js" in html
    assert "lang='ar'" in html
    assert "dir='rtl'" in html


@pytest.mark.unit
def test_prefers_native_pdf_viewer_for_phones():
    from flask import Flask

    from plugins.upr_visuals.routes import _prefers_native_pdf_viewer

    app = Flask(__name__)
    iphone = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    )
    android = (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
    )
    desktop = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    with app.test_request_context("/", headers={"User-Agent": iphone}):
        assert _prefers_native_pdf_viewer() is True
    with app.test_request_context("/", headers={"User-Agent": android}):
        assert _prefers_native_pdf_viewer() is True
    with app.test_request_context("/", headers={"Sec-CH-UA-Mobile": "?1"}):
        assert _prefers_native_pdf_viewer() is True
    with app.test_request_context("/", headers={"User-Agent": desktop}):
        assert _prefers_native_pdf_viewer() is False


@pytest.mark.unit
def test_file_response_zip_is_attachment():
    from plugins.upr_visuals.routes import _file_response

    response = _file_response(b"PK", "NS - InDesign.zip", mimetype="application/zip", download=True)
    assert response.mimetype == "application/zip"
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert "NS - InDesign.zip" in response.headers["Content-Disposition"]


@pytest.mark.unit
def test_fonts_css_is_shared_typography():
    from flask import Flask

    from plugins.upr_visuals.routes import fonts_css
    from plugins.upr_visuals.typography import ARABIC_FAMILY, export_style_token

    app = Flask(__name__)
    with app.test_request_context("/upr-visuals/fonts.css"):
        response = fonts_css.__wrapped__()
    body = response.get_data(as_text=True)
    assert response.mimetype.startswith("text/css")
    assert ARABIC_FAMILY in body
    assert ".upr-arabic-font *" in body
    assert response.headers["ETag"].strip('"') == export_style_token()


@pytest.mark.unit
def test_pdf_viewer_csp_allows_same_origin_frame():
    from plugins.upr_visuals.plugin import UprVisualsPlugin, _UPR_PDF_VIEWER_CSP

    overrides = UprVisualsPlugin().get_csp_overrides()
    endpoints = {item.endpoint for item in overrides}
    assert endpoints == {"upr_visuals.assignment_pdf", "upr_visuals.assignment_narrative_file"}
    assert all(item.policy == _UPR_PDF_VIEWER_CSP for item in overrides)
    assert "frame-ancestors 'self'" in _UPR_PDF_VIEWER_CSP
