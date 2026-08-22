"""IDML package helpers and Word-narrative styling."""

from __future__ import annotations

import io
import zipfile

import pytest

from plugins.upr_visuals.data import UprVisualsError
from plugins.upr_visuals.idml import (
    DOCX_MAX_BYTES,
    DOCX_MAX_UNCOMPRESSED_BYTES,
    folio_label,
    folio_text,
    load_word_paragraphs,
    merge_report_pdfs,
    read_docx_upload,
    style_narrative_blocks,
    validate_docx_bytes,
)
from plugins.upr_visuals.idml.pages import add_narrative_pages
from plugins.upr_visuals.idml.builder import zip_indesign_package
from plugins.upr_visuals.idml.xml_idml import Idml, _xml_text
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
    with pytest.raises(UprVisualsError):
        validate_docx_bytes(b"x" * (DOCX_MAX_BYTES + 1))


@pytest.mark.unit
def test_validate_docx_rejects_oversized_uncompressed_xml():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo("word/document.xml")
        payload = b"<w:document/>"
        info.file_size = DOCX_MAX_UNCOMPRESSED_BYTES + 1
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, payload)
        # Force the declared uncompressed size after write.
        zf.filelist[-1].file_size = DOCX_MAX_UNCOMPRESSED_BYTES + 1
    with pytest.raises(UprVisualsError, match="too large"):
        validate_docx_bytes(out.getvalue())


@pytest.mark.unit
def test_load_word_paragraphs_rejects_corrupt_xml():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("word/document.xml", b"<not-xml")
    with pytest.raises(UprVisualsError):
        load_word_paragraphs(out.getvalue())


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
    assert folio_text("2026 IFRC network annual report", 2) == "2026 IFRC network annual report    /    2"


def _blank_pdf(pages: int) -> bytes:
    import fitz

    doc = fitz.open()
    try:
        for _ in range(pages):
            doc.new_page(width=595.28, height=841.89)
        return doc.tobytes()
    finally:
        doc.close()


@pytest.mark.unit
def test_merge_report_pdfs_folios_from_page_two():
    import fitz

    label = "2026 IFRC network annual report"
    merged = merge_report_pdfs(_blank_pdf(3), _blank_pdf(2), folio=label)
    out = fitz.open(stream=merged, filetype="pdf")
    try:
        assert out.page_count == 5
        texts = [page.get_text() for page in out]
    finally:
        out.close()
    assert label not in texts[0]
    assert folio_text(label, 2) in texts[1]
    assert folio_text(label, 3) in texts[2]
    assert folio_text(label, 4) in texts[3]
    assert folio_text(label, 5) in texts[4]


@pytest.mark.unit
def test_idml_narrative_folio_continues_after_visual_pages():
    doc = Idml()
    doc.add_page([])
    doc.add_page([])
    doc.add_page([])
    add_narrative_pages(
        doc,
        [{"style": "Body", "text": "Context", "runs": [{"text": "Context", "href": "", "bold": False}]}],
        folio="2026 IFRC network annual report",
    )
    assert doc.page_count == 4
    stories = "".join(doc.stories.values())
    assert folio_text("2026 IFRC network annual report", 4) in stories
    assert folio_text("2026 IFRC network annual report", 1) not in stories


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
def test_xml_text_strips_control_characters():
    assert _xml_text("Côte\x00 d'Ivoire") == "Côte d'Ivoire"
    assert "\x1f" not in _xml_text("ok\x1f")


@pytest.mark.unit
def test_idml_story_escapes_unicode_and_xml_metacharacters():
    from xml.etree.ElementTree import fromstring

    text = 'Côte d\'Ivoire & Türkiye <tag> "quoted" 😀'
    doc = Idml()
    sid = doc.story([{"text": text, "font": "Open Sans", "size": "11", "color": "Color/Black"}])
    xml = doc.stories[sid]
    fromstring(xml)
    assert "&amp;" in xml
    assert "&lt;tag&gt;" in xml
    assert "Côte d'Ivoire" in xml
    assert "Türkiye" in xml
    assert "😀" in xml
    assert "<tag>" not in xml


@pytest.mark.unit
def test_idml_styled_story_escapes_hyperlink_and_narrative():
    from xml.etree.ElementTree import fromstring

    doc = Idml()
    sid = doc.styled_story(
        [
            {
                "style": "Body",
                "text": 'Support for Côte d\'Ivoire & Türkiye <x>',
                "runs": [
                    {
                        "text": 'Support for Côte d\'Ivoire & Türkiye <x>',
                        "href": 'https://example.test/?q=a&b="c"',
                        "bold": False,
                    }
                ],
            }
        ]
    )
    xml = doc.stories[sid]
    fromstring(xml)
    assert "&amp;" in xml
    assert "&lt;x&gt;" in xml
    assert "&quot;" in xml
    packed = doc.package_bytes()
    assert packed.startswith(b"PK")


@pytest.mark.unit
def test_idml_download_name_keeps_document_title():
    name = visual_export_filename(
        {"document_title": "Bangladesh — Midyear Reporting 2026 - Unified Country Report"},
        "combined",
        "zip",
    )
    assert name == "Bangladesh - Midyear Reporting 2026 - Unified Country Report.zip"
