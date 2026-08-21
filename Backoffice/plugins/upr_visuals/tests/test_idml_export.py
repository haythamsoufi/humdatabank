"""IDML package helpers and Word-narrative styling."""

from __future__ import annotations

import io
import zipfile

import pytest

from plugins.upr_visuals.data import UprVisualsError
from plugins.upr_visuals.idml import (
    folio_label,
    load_word_paragraphs,
    read_docx_upload,
    style_narrative_blocks,
    validate_docx_bytes,
)
from plugins.upr_visuals.idml.builder import zip_indesign_package
from plugins.upr_visuals.service import visual_export_filename


def _docx_bytes(*body_xml: str) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<w:body>{''.join(body_xml)}</w:body></w:document>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
        'Target="https://example.test/appeal" TargetMode="External"/>'
        "</Relationships>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("word/document.xml", document)
        zf.writestr("word/_rels/document.xml.rels", rels)
    return out.getvalue()


def _p(text: str = "", *, href: bool = False) -> str:
    if not text:
        return "<w:p/>"
    run = f"<w:r><w:t>{text}</w:t></w:r>"
    if href:
        run = f'<w:hyperlink r:id="rId1">{run}</w:hyperlink>'
    return f"<w:p>{run}</w:p>"


def _table() -> str:
    return (
        "<w:tbl><w:tr>"
        f"<w:tc>{_p('Emergency Appeal name')}</w:tc>"
        f"<w:tc>{_p('Bangladesh – Population Movement', href=True)}</w:tc>"
        "</w:tr></w:tbl>"
    )


@pytest.mark.unit
def test_validate_docx_rejects_non_word():
    with pytest.raises(UprVisualsError):
        validate_docx_bytes(b"")
    with pytest.raises(UprVisualsError):
        validate_docx_bytes(b"%PDF-1.4")
    with pytest.raises(UprVisualsError):
        validate_docx_bytes(b"PK\x03\x04not-a-zip")


@pytest.mark.unit
def test_read_docx_upload_requires_docx_suffix():
    data = _docx_bytes(_p("Hello"))
    storage = io.BytesIO(data)
    storage.filename = "notes.pdf"
    with pytest.raises(UprVisualsError):
        read_docx_upload(storage, filename="notes.pdf")
    storage.seek(0)
    storage.filename = "report.docx"
    assert read_docx_upload(storage, filename="report.docx") == data


@pytest.mark.unit
def test_style_keeps_one_blank_after_table():
    blocks = load_word_paragraphs(_docx_bytes(_table(), _p(), _p(), _p("In 2016, a crisis unfolded.")))
    styled = style_narrative_blocks(blocks, country_name="Bangladesh")
    assert styled[0]["kind"] == "table"
    assert styled[1]["style"] == "Blank"
    assert styled[2]["style"] == "Body"
    assert "In 2016" in styled[2]["text"]
    assert [row.get("style") for row in styled].count("Blank") == 1


@pytest.mark.unit
def test_style_skips_country_cover_line():
    blocks = load_word_paragraphs(
        _docx_bytes(_p("Bangladesh"), _p("IFRC network annual report 2025, Jan-Dec"), _p("Context"))
    )
    styled = style_narrative_blocks(blocks, country_name="Bangladesh")
    assert [row["text"] for row in styled] == ["Context"]
    assert styled[0]["style"] == "SectionHead"


@pytest.mark.unit
def test_style_skips_word_cover_title_when_country_differs():
    blocks = load_word_paragraphs(
        _docx_bytes(_p("Bangladesh"), _p("IFRC network annual report 2025, Jan-Dec"), _p("Context"))
    )
    styled = style_narrative_blocks(blocks, country_name="Afghanistan")
    assert [row["text"] for row in styled] == ["Context"]


@pytest.mark.unit
def test_folio_label_uses_year_and_kind():
    assert folio_label({"year": 2026, "kind": "report"}) == "2026 IFRC network annual report"
    assert folio_label({"year": 2026, "kind": "plan"}) == "2026 IFRC network unified plan"
    assert folio_label({}) == "IFRC network annual report"


@pytest.mark.unit
def test_zip_indesign_package_includes_links(tmp_path):
    links = tmp_path / "Links"
    links.mkdir()
    (links / "in_support.svg").write_text("<svg/>", encoding="utf-8")
    (links / "notes.txt").write_text("skip", encoding="utf-8")
    packed = zip_indesign_package(b"idml", "Report.idml", links)
    with zipfile.ZipFile(io.BytesIO(packed)) as zf:
        names = set(zf.namelist())
    assert names == {"Report.idml", "Links/in_support.svg"}


@pytest.mark.unit
def test_idml_download_name_keeps_document_title():
    name = visual_export_filename(
        {"document_title": "Bangladesh — Midyear Reporting 2026 - Unified Country Report"},
        "combined",
        "zip",
    )
    assert name == "Bangladesh - Midyear Reporting 2026 - Unified Country Report.zip"
