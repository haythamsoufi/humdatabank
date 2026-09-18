"""Internal vs public UPR narrative classification."""

from __future__ import annotations

import io
import zipfile

import pytest

from plugins.upr.audience import (
    detect_narrative_audience,
    parse_narrative_audience,
    resolve_narrative_audience,
)


def _docx_bytes(text: str) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("word/document.xml", document)
    return out.getvalue()


def _pdf_with_text(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    try:
        page = doc.new_page(width=595.28, height=841.89)
        page.insert_text((72, 36), text)
        return doc.tobytes()
    finally:
        doc.close()


@pytest.mark.unit
def test_parse_narrative_audience():
    assert parse_narrative_audience("auto") is None
    assert parse_narrative_audience("") is None
    assert parse_narrative_audience("internal") == "internal"
    assert parse_narrative_audience("external") == "public"
    assert parse_narrative_audience("Public facing") == "public"


@pytest.mark.unit
def test_detect_internal_from_running_header_pdf():
    data = _pdf_with_text("Internal")
    assert detect_narrative_audience(filename="Bangladesh UPL MYR 2026.pdf", data=data) == "internal"


@pytest.mark.unit
def test_detect_public_from_design_filename():
    assert (
        detect_narrative_audience(filename="Bangladesh_INP_AR_2025_Design.docx", data=_docx_bytes("Bangladesh"))
        == "public"
    )


@pytest.mark.unit
def test_detect_public_from_ifrc_network_template():
    data = _docx_bytes("IFRC network annual report 2025, Jan-Dec Appeal code: MAABD001")
    assert detect_narrative_audience(filename="Bangladesh.docx", data=data) == "public"


@pytest.mark.unit
def test_internal_header_beats_design_filename():
    data = _pdf_with_text("Internal")
    assert detect_narrative_audience(filename="Bangladesh_Design.pdf", data=data) == "internal"


@pytest.mark.unit
def test_unclear_file_defaults_to_internal():
    assert detect_narrative_audience(filename="notes.docx", data=_docx_bytes("Hello")) == "internal"


@pytest.mark.unit
def test_manual_override_wins():
    assert (
        resolve_narrative_audience(
            "public",
            filename="Bangladesh UPL MYR 2026.pdf",
            data=_pdf_with_text("Internal"),
        )
        == "public"
    )
    assert resolve_narrative_audience("internal", filename="Bangladesh_INP_AR_2025_Design.docx") == "internal"
