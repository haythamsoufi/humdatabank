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
def test_pdf_response_download_uses_attachment():
    from plugins.upr_visuals.routes import _pdf_response

    response = _pdf_response(b"%PDF-1.4", "AFG_P25_combined.pdf", download=True)
    assert response.headers["Content-Disposition"] == 'attachment; filename="AFG_P25_combined.pdf"'


@pytest.mark.unit
def test_assignment_pdf_response_renders_live_bytes(monkeypatch):
    from plugins.upr_visuals import routes

    monkeypatch.setattr(routes, "_aes_or_404", lambda aes_id: object())
    monkeypatch.setattr(
        routes.UprVisualsService,
        "pdf_bytes",
        classmethod(lambda cls, aes_id, dashboard_id: (b"%PDF-1.4", f"NS_{dashboard_id}.pdf")),
    )
    response = routes._assignment_pdf_response(9, "combined", download=False)
    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-1.4"
    assert "NS_combined.pdf" in response.headers["Content-Disposition"]
    assert response.headers["Content-Disposition"].startswith("inline;")


@pytest.mark.unit
def test_pdf_viewer_sets_document_title():
    from plugins.upr_visuals.routes import _pdf_viewer_response

    response = _pdf_viewer_response(
        title="Bangladesh — Unified Plan – 2026",
        pdf_url="/assignment/9/pdf?raw=1",
    )
    html = response.get_data(as_text=True)
    assert response.mimetype.startswith("text/html")
    assert "<title>Bangladesh — Unified Plan – 2026</title>" in html
    assert "raw=1" in html


@pytest.mark.unit
def test_pdf_viewer_csp_allows_same_origin_frame():
    from plugins.upr_visuals.plugin import UprVisualsPlugin, _UPR_PDF_VIEWER_CSP

    overrides = UprVisualsPlugin().get_csp_overrides()
    assert len(overrides) == 1
    assert overrides[0].endpoint == "upr_visuals.assignment_pdf"
    assert "frame-ancestors 'self'" in overrides[0].policy
    assert overrides[0].policy == _UPR_PDF_VIEWER_CSP
