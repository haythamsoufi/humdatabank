"""IDML package helpers and Word-narrative styling."""

from __future__ import annotations

import io
import zipfile

import pytest

from plugins.upr.data import UprError
from plugins.upr.idml import (
    DOCX_MAX_BYTES,
    DOCX_MAX_UNCOMPRESSED_BYTES,
    PDF_MAX_BYTES,
    folio_label,
    folio_text,
    load_word_paragraphs,
    merge_report_pdfs,
    read_docx_upload,
    read_narrative_upload,
    style_narrative_blocks,
    validate_docx_bytes,
    validate_pdf_bytes,
)
from plugins.upr.idml.pages import add_narrative_pages
from plugins.upr.idml.builder import zip_indesign_package
from plugins.upr.idml.xml_idml import Idml, _xml_text
from plugins.upr.service import visual_export_filename


def _docx_bytes(*body_xml: str, extra_rels: str = "", extra_files: dict[str, bytes] | None = None) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f"<w:body>{''.join(body_xml)}</w:body></w:document>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
        'Target="https://example.test/appeal" TargetMode="External"/>'
        f"{extra_rels}"
        "</Relationships>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("word/document.xml", document)
        zf.writestr("word/_rels/document.xml.rels", rels)
        for name, data in (extra_files or {}).items():
            zf.writestr(name, data)
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
def test_safe_export_href_allowlist():
    from plugins.upr.idml.word_reader import safe_export_href

    assert safe_export_href("https://example.test/appeal") == "https://example.test/appeal"
    assert safe_export_href("mailto:ns@example.test") == "mailto:ns@example.test"
    assert safe_export_href("javascript:alert(1)") == ""
    assert safe_export_href("file:///etc/passwd") == ""
    assert safe_export_href("data:text/html,hi") == ""


@pytest.mark.unit
def test_validate_docx_rejects_non_word():
    with pytest.raises(UprError):
        validate_docx_bytes(b"")
    with pytest.raises(UprError):
        validate_docx_bytes(b"%PDF-1.4")
    with pytest.raises(UprError):
        validate_docx_bytes(b"PK\x03\x04not-a-zip")
    with pytest.raises(UprError):
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
    with pytest.raises(UprError, match="too large"):
        validate_docx_bytes(out.getvalue())


@pytest.mark.unit
def test_load_word_paragraphs_rejects_corrupt_xml():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("word/document.xml", b"<not-xml")
    with pytest.raises(UprError):
        load_word_paragraphs(out.getvalue())


@pytest.mark.unit
def test_read_docx_upload_requires_docx_suffix():
    data = _docx_bytes(_p("Hello"))
    storage = io.BytesIO(data)
    storage.filename = "notes.pdf"
    with pytest.raises(UprError):
        read_docx_upload(storage, filename="notes.pdf")
    storage.seek(0)
    storage.filename = "report.docx"
    assert read_docx_upload(storage, filename="report.docx") == data


@pytest.mark.unit
def test_validate_pdf_rejects_non_pdf():
    with pytest.raises(UprError):
        validate_pdf_bytes(b"")
    with pytest.raises(UprError):
        validate_pdf_bytes(b"PK\x03\x04")
    with pytest.raises(UprError):
        validate_pdf_bytes(b"%PDF" + (b"x" * PDF_MAX_BYTES))


@pytest.mark.unit
def test_read_narrative_upload_accepts_pdf_and_docx():
    pdf = _blank_pdf(1)
    storage = io.BytesIO(pdf)
    storage.filename = "notes.pdf"
    assert read_narrative_upload(storage, filename="notes.pdf") == pdf
    data = _docx_bytes(_p("Hello"))
    storage = io.BytesIO(data)
    storage.filename = "report.docx"
    assert read_narrative_upload(storage, filename="report.docx") == data
    with pytest.raises(UprError, match="Word document"):
        read_narrative_upload(io.BytesIO(b"hello"), filename="notes.txt")


def _text_pdf(*, heading: str, body: str, bold_contact: str = "") -> bytes:
    import fitz

    doc = fitz.open()
    try:
        page = doc.new_page(width=595.28, height=841.89)
        page.insert_text((72, 80), heading, fontsize=16, fontname="helv")
        page.insert_text((72, 120), body, fontsize=10, fontname="helv")
        if bold_contact:
            page.insert_text((72, 160), bold_contact, fontsize=10, fontname="hebo")
        return doc.tobytes()
    finally:
        doc.close()


@pytest.mark.unit
def test_load_pdf_paragraphs_styles_like_word():
    from plugins.upr.idml.pdf_reader import load_pdf_paragraphs

    blocks = load_pdf_paragraphs(
        _text_pdf(heading="Context", body="In 2016, a crisis unfolded.")
    )
    texts = [row["text"] for row in blocks if row.get("text")]
    assert "Context" in texts
    assert any("crisis" in text for text in texts)
    styled = style_narrative_blocks(blocks, country_name="Bangladesh")
    assert styled[0]["style"] == "SectionHead"
    assert styled[0]["text"] == "Context"
    assert any(row.get("style") == "Body" and "crisis" in row["text"] for row in styled)


@pytest.mark.unit
def test_load_pdf_paragraphs_rejects_empty_text():
    from plugins.upr.idml.pdf_reader import load_pdf_paragraphs

    with pytest.raises(UprError, match="extractable text"):
        load_pdf_paragraphs(_blank_pdf(1))


@pytest.mark.unit
def test_load_pdf_paragraphs_keeps_bold_runs():
    from plugins.upr.idml.pdf_reader import load_pdf_paragraphs

    blocks = load_pdf_paragraphs(
        _text_pdf(heading="Context", body="In 2016, a crisis unfolded.", bold_contact="Jane Doe")
    )
    jane = next(row for row in blocks if "Jane" in (row.get("text") or ""))
    assert any(run.get("bold") for run in jane.get("runs") or [])


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


_PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _drawing_p() -> str:
    return (
        "<w:p><w:r><w:drawing><wp:inline>"
        '<wp:extent cx="2667000" cy="1600200"/>'
        "<a:graphic><a:graphicData>"
        '<a:blip r:embed="rIdImg"/>'
        "</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
    )


def _italic_caption_p(text: str = "Photo: IFRC") -> str:
    return (
        "<w:p><w:pPr><w:jc w:val=\"left\"/><w:rPr><w:i/><w:sz w:val=\"18\"/></w:rPr></w:pPr>"
        f'<w:r><w:rPr><w:i/><w:sz w:val="18"/></w:rPr><w:t>{text}</w:t></w:r></w:p>'
    )


def _docx_with_photo() -> bytes:
    extra_rels = (
        '<Relationship Id="rIdImg" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        'Target="media/image1.png"/>'
    )
    return _docx_bytes(
        _p("Context"),
        _drawing_p(),
        _p(),
        _italic_caption_p(),
        _p("In 2016, a crisis unfolded."),
        extra_rels=extra_rels,
        extra_files={"word/media/image1.png": _PNG_1PX},
    )


@pytest.mark.unit
def test_load_word_keeps_embedded_image_and_italic_caption():
    blocks = load_word_paragraphs(_docx_with_photo())
    photo = next(row for row in blocks if row.get("kind") == "image")
    assert photo["src"].startswith("data:image/png;base64,")
    assert photo.get("width_pt") == pytest.approx(210.0, rel=0.01)
    caption = next(row for row in blocks if "Photo:" in (row.get("text") or ""))
    assert caption.get("align") == "left"
    assert caption.get("size_pt") == 9.0
    assert all(run.get("italic") for run in caption["runs"])
    styled = style_narrative_blocks(blocks, country_name="Bangladesh")
    assert styled[0]["style"] == "SectionHead"
    assert styled[1]["kind"] == "image"
    assert styled[2]["style"] == "Caption"
    assert styled[2]["text"] == "Photo: IFRC"
    assert styled[2]["align"] == "left"


@pytest.mark.unit
def test_style_skips_word_cover_logos():
    extra_rels = (
        '<Relationship Id="rIdImg" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        'Target="media/image1.png"/>'
    )
    blocks = load_word_paragraphs(
        _docx_bytes(
            _drawing_p(),
            _p("Bangladesh"),
            _p("IFRC network annual report 2025, Jan-Dec"),
            _p("Context"),
            _drawing_p(),
            _italic_caption_p(),
            extra_rels=extra_rels,
            extra_files={"word/media/image1.png": _PNG_1PX},
        )
    )
    styled = style_narrative_blocks(blocks, country_name="Bangladesh")
    assert styled[0]["style"] == "SectionHead"
    assert styled[1]["kind"] == "image"
    assert styled[2]["style"] == "Caption"


@pytest.mark.unit
def test_narrative_pdf_embeds_image_and_italic_caption(monkeypatch):
    captured = {}
    _patch_weasyprint(monkeypatch, captured)
    from plugins.upr.idml.narrative_pdf import render_narrative_pdf_bytes

    blocks = load_word_paragraphs(_docx_with_photo())
    styled = style_narrative_blocks(blocks, country_name="Bangladesh")
    render_narrative_pdf_bytes(styled)
    html = captured.get("html") or ""
    css = captured.get("css") or ""
    assert 'class="upr-nar-img"' in html
    assert "data:image/png;base64," in html
    assert "upr-nar-p--Caption" in html
    assert "is-italic" in html
    assert "text-align:left" in html
    assert "font-size:9.0pt" in html
    assert "font-style: italic" in css


@pytest.mark.unit
def test_idml_story_skips_narrative_images():
    doc = Idml()
    add_narrative_pages(
        doc,
        [
            {"kind": "image", "src": "data:image/png;base64,xxxx", "width_pt": 200, "height_pt": 100},
            {
                "style": "Caption",
                "text": "Photo: IFRC",
                "runs": [{"text": "Photo: IFRC", "href": "", "bold": False, "italic": True}],
            },
        ],
        folio="2025 IFRC network annual report",
    )
    stories = "".join(doc.stories.values())
    assert "data:image" not in stories
    assert "Photo: IFRC" in stories
    assert 'FontStyle="Italic"' in stories
    assert "ParagraphStyle/Caption" in stories


@pytest.mark.unit
def test_style_keeps_word_heading_sizes_for_same_style_cluster():
    def _sized(text: str, half_points: int) -> str:
        return (
            "<w:p><w:pPr><w:rPr>"
            f'<w:sz w:val="{half_points}"/></w:rPr></w:pPr>'
            f'<w:r><w:rPr><w:b/><w:sz w:val="{half_points}"/></w:rPr><w:t>{text}</w:t></w:r></w:p>'
        )

    blocks = load_word_paragraphs(
        _docx_bytes(
            _sized("ENABLING LOCAL ACTORS", 36),
            _sized("Strategic and operational coordination", 28),
            _sized("Progress by National Society against objectives", 20),
            _sized("IFRC membership coordination", 22),
            _p("IFRC membership coordination involves working with National Societies to assess needs."),
        )
    )
    styled = style_narrative_blocks(blocks, country_name="Bangladesh")
    by_text = {row["text"]: row for row in styled if row.get("text")}
    assert by_text["ENABLING LOCAL ACTORS"]["style"] == "BandHead"
    assert by_text["ENABLING LOCAL ACTORS"]["size_pt"] == 18.0
    assert by_text["Strategic and operational coordination"]["style"] == "TopicHead"
    assert by_text["Strategic and operational coordination"]["size_pt"] == 14.0
    assert by_text["Progress by National Society against objectives"]["style"] == "Subhead"
    assert by_text["IFRC membership coordination"]["style"] == "Subhead"
    assert by_text["IFRC membership coordination"]["size_pt"] == 11.0


@pytest.mark.unit
def test_narrative_pdf_uses_word_heading_sizes(monkeypatch):
    captured = {}
    _patch_weasyprint(monkeypatch, captured)
    from plugins.upr.idml.narrative_pdf import render_narrative_pdf_bytes

    render_narrative_pdf_bytes(
        [
            {"style": "BandHead", "text": "ENABLING LOCAL ACTORS", "size_pt": 18.0,
             "runs": [{"text": "ENABLING LOCAL ACTORS", "href": "", "bold": True}]},
            {"style": "TopicHead", "text": "Strategic and operational coordination", "size_pt": 14.0,
             "runs": [{"text": "Strategic and operational coordination", "href": "", "bold": True}]},
            {"style": "Subhead", "text": "Progress by National Society against objectives", "size_pt": 10.0,
             "runs": [{"text": "Progress by National Society against objectives", "href": "", "bold": True}]},
            {"style": "Subhead", "text": "IFRC membership coordination", "size_pt": 11.0,
             "runs": [{"text": "IFRC membership coordination", "href": "", "bold": True}]},
        ]
    )
    html = captured.get("html") or ""
    assert "font-size:18.0pt" in html
    assert "font-size:14.0pt" in html
    assert "font-size:10.0pt" in html
    assert "font-size:11.0pt" in html


@pytest.mark.unit
def test_folio_label_uses_year_and_kind():
    assert folio_label({"year": 2026, "kind": "report"}) == "2026 IFRC network annual report"
    assert folio_label({"year": 2026, "kind": "plan"}) == "2026 IFRC network unified plan"
    assert folio_label({}) == "IFRC network annual report"
    assert folio_text("2026 IFRC network annual report", 2) == "2026 IFRC network annual report    /    2"
    from plugins.upr.idml.narrative_style import folio_html, folio_runs

    html = folio_html("2026 IFRC network annual report", 2)
    assert "upr-folio-slash" in html
    assert "<strong>2</strong>" in html
    assert "/" in html
    runs = folio_runs("2026 IFRC network annual report", 2)
    assert runs[1]["text"] == "/"
    assert runs[1]["color"] == "Color/IFRCRed"
    assert runs[1]["style"] == "Bold"
    assert runs[2]["style"] == "Bold"
    assert runs[2]["text"].strip() == "2"


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
    for page_no, text in enumerate(texts[1:], start=2):
        assert " ".join(text.split()) == f"{label} / {page_no}"
    spans = []
    doc = fitz.open(stream=merged, filetype="pdf")
    try:
        for block in doc[1].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans.extend(line.get("spans") or [])
    finally:
        doc.close()
    slash = next((s for s in spans if (s.get("text") or "").strip() == "/"), None)
    page_no = next((s for s in spans if (s.get("text") or "").strip() == "2"), None)
    assert slash is not None
    assert page_no is not None
    slash_color = slash.get("color")
    if isinstance(slash_color, int):
        assert slash_color == 0xF5333F
    else:
        assert slash_color in {(245, 51, 63), (0.9607843137254902, 0.2, 0.24705882352941178)}
    assert slash.get("flags", 0) & 16 or "Bold" in (slash.get("font") or "")
    assert page_no.get("flags", 0) & 16 or "Bold" in (page_no.get("font") or "")


@pytest.mark.unit
def test_arabic_folio_stamps_readable_glyphs():
    import fitz

    from plugins.upr.idml.narrative_pdf import _folio_font_path, _folio_has_rtl

    assert _folio_has_rtl("تقرير الشبكة السنوي 2026")
    assert not _folio_has_rtl("2026 IFRC network annual report")
    assert _folio_font_path(rtl=True) is not None

    label = "تقرير الشبكة السنوي للاتحاد الدولي 2026"
    merged = merge_report_pdfs(_blank_pdf(2), _blank_pdf(1), folio=label)
    doc = fitz.open(stream=merged, filetype="pdf")
    try:
        text = doc[1].get_text()
    finally:
        doc.close()
    assert any("\u0600" <= char <= "\u06ff" for char in text)
    assert "2026" in text
    assert "2" in text


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
    assert "2026 IFRC network annual report    " in stories
    assert 'FillColor="Color/IFRCRed"' in stories
    assert 'FontStyle="Bold"' in stories
    assert "<Content>/</Content>" in stories
    assert "    4</Content>" in stories
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


def _patch_weasyprint(monkeypatch, captured: dict):
    class FakeCSS:
        def __init__(self, string="", **kwargs):
            captured["css"] = string
            captured["css_kwargs"] = kwargs

    class FakeHTML:
        def __init__(self, **kwargs):
            captured["html"] = kwargs.get("string") or ""
            captured["html_kwargs"] = kwargs

        def write_pdf(self, buf, **kwargs):
            captured.update(kwargs)
            buf.write(b"%PDF-1.4")

    class FakeFontConfiguration:
        pass

    monkeypatch.setattr("weasyprint.CSS", FakeCSS)
    monkeypatch.setattr("weasyprint.HTML", FakeHTML)
    monkeypatch.setattr("weasyprint.text.fonts.FontConfiguration", FakeFontConfiguration)


@pytest.mark.unit
def test_narrative_pdf_subsets_fonts_by_default(monkeypatch):
    captured = {}
    _patch_weasyprint(monkeypatch, captured)
    from plugins.upr.idml.narrative_pdf import render_narrative_pdf_bytes

    render_narrative_pdf_bytes([{"style": "Body", "text": "Hello", "runs": [{"text": "Hello"}]}])
    assert captured.get("full_fonts") is False
    assert captured.get("font_config") is not None
    assert captured.get("css_kwargs", {}).get("font_config") is captured.get("font_config")


@pytest.mark.unit
def test_arabic_narrative_pdf_registers_tajawal(monkeypatch):
    captured = {}
    _patch_weasyprint(monkeypatch, captured)
    monkeypatch.setattr("plugins.upr.i18n.current_export_language", lambda: "ar")
    from plugins.upr.idml.narrative_pdf import render_narrative_pdf_bytes

    render_narrative_pdf_bytes(
        [{"style": "Body", "text": "مرحبا", "runs": [{"text": "مرحبا", "href": "", "bold": False}]}]
    )
    html = captured.get("html") or ""
    css = captured.get("css") or ""
    assert "class='upr-arabic-font'" in html
    assert "Tajawal" in html
    assert "@font-face" in html
    assert "Tajawal" in css
    assert captured.get("full_fonts") is True
    assert captured.get("font_config") is not None
    assert captured.get("css_kwargs", {}).get("font_config") is captured.get("font_config")


@pytest.mark.unit
def test_arabic_narrative_pdf_embeds_tajawal(monkeypatch):
    """Live WeasyPrint: Arabic narrative must embed Tajawal, not a system fallback."""
    fitz = pytest.importorskip("fitz")
    pytest.importorskip("weasyprint")
    monkeypatch.setattr("plugins.upr.i18n.current_export_language", lambda: "ar")
    from plugins.upr.idml.narrative_pdf import render_narrative_pdf_bytes

    pdf = render_narrative_pdf_bytes(
        [
            {
                "style": "Body",
                "text": "مرحبا بالعالم",
                "runs": [{"text": "مرحبا بالعالم", "href": "", "bold": False}],
            }
        ]
    )
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        names = " ".join(
            str(font[3] or "") + " " + str(font[4] or "")
            for page in doc
            for font in page.get_fonts()
        )
    finally:
        doc.close()
    assert "Tajawal" in names
