"""Word export with the standard heading styles Word uses for an outline.

The file is a real .docx: Title, Subtitle, Heading 1–3, Normal, Note, and
List Bullet. Heading styles keep their outline levels, so the navigation pane
follows the GO chapter order.
"""

from __future__ import annotations

from io import BytesIO

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

_NAVY = "011E41"
_RED = "EF3340"
_GREY = "58595B"
_HEADING_FONT = "Montserrat"
_BODY_FONT = "Open Sans"


def render_docx(blocks: list, header: str) -> bytes:
    document = Document()
    _apply_page(document)
    _apply_styles(document)
    _apply_header(document, header)
    _apply_footer(document)
    for block in blocks:
        _add_block(document, block)
    _properties(document, blocks, header)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _add_block(document, block) -> None:
    kind = block.kind
    if kind == "title":
        document.add_paragraph(block.text, style="Title")
    elif kind == "subtitle":
        document.add_paragraph(block.text, style="Subtitle")
    elif kind == "heading":
        document.add_paragraph(block.text, style=f"Heading {block.level}")
    elif kind == "note":
        document.add_paragraph(block.text, style="Note")
    elif kind == "kv":
        _add_kv(document, block.rows)
    elif kind == "table":
        _add_table(document, block.headers, block.rows)
    elif kind == "bullets":
        style = "List Bullet" if _has_style(document, "List Bullet") else "Normal"
        for row in block.rows:
            text = row[0] if row else ""
            if style == "Normal":
                text = f"• {text}"
            document.add_paragraph(text, style=style)
    else:
        document.add_paragraph(block.text or "", style="Normal")


def _add_kv(document, rows) -> None:
    if not rows:
        return
    table = document.add_table(rows=len(rows), cols=2)
    table.style = "Table Grid"
    table.autofit = True
    _set_widths(table, (70, 108))
    for index, (label, value) in enumerate(rows):
        _write_cell(document, table.rows[index].cells[0], label, bold=True, color=_GREY)
        _write_cell(document, table.rows[index].cells[1], value)
        _shade(table.rows[index].cells[0], "F4F5F7")
    _keep_rows(table)


def _add_table(document, headers, rows) -> None:
    if not headers:
        return
    table = document.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    table.autofit = True
    for index, header in enumerate(headers):
        _write_cell(document, table.rows[0].cells[index], header, bold=True, color="FFFFFF")
        _shade(table.rows[0].cells[index], _NAVY)
    _mark_header(table.rows[0])
    for row_index, row in enumerate(rows, start=1):
        for col_index in range(len(headers)):
            value = row[col_index] if col_index < len(row) else ""
            _write_cell(document, table.rows[row_index].cells[col_index], value)
            if row_index % 2 == 0:
                _shade(table.rows[row_index].cells[col_index], "F7F8FA")
    _keep_rows(table)


def _write_cell(document, cell, text: str, *, bold: bool = False, color: str = "000000") -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    if _has_style(document, "Table text"):
        paragraph.style = "Table text"
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(text or "")
    _paint_run(run, _BODY_FONT, 9, bold=bold, color=color)


def _apply_styles(document) -> None:
    normal = document.styles["Normal"]
    _paint_style(normal, _BODY_FONT, 10.5, color="000000")
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.line_spacing = 1.15

    title = document.styles["Title"]
    _paint_style(title, _HEADING_FONT, 22, bold=True, color=_RED)
    title.paragraph_format.space_before = Pt(0)
    title.paragraph_format.space_after = Pt(2)

    subtitle = document.styles["Subtitle"]
    _paint_style(subtitle, _HEADING_FONT, 14, bold=False, color=_NAVY)
    subtitle.paragraph_format.space_before = Pt(0)
    subtitle.paragraph_format.space_after = Pt(10)

    for level, size, before, color in (
        (1, 16, 16, _NAVY),
        (2, 13, 12, "1B365D"),
        (3, 11, 8, "000000"),
    ):
        style = document.styles[f"Heading {level}"]
        _paint_style(style, _HEADING_FONT if level < 3 else _BODY_FONT, size, bold=True, color=color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.page_break_before = False
        _outline(style, level - 1)

    note = _ensure_style(document, "Note")
    _paint_style(note, _BODY_FONT, 9, italic=True, color=_GREY)
    note.paragraph_format.space_before = Pt(2)
    note.paragraph_format.space_after = Pt(8)

    table_text = _ensure_style(document, "Table text")
    _paint_style(table_text, _BODY_FONT, 9, color="000000")
    table_text.paragraph_format.space_before = Pt(0)
    table_text.paragraph_format.space_after = Pt(0)

    bullet = document.styles["List Bullet"] if _has_style(document, "List Bullet") else None
    if bullet is not None:
        _paint_style(bullet, _BODY_FONT, 10.5, color="000000")
        bullet.paragraph_format.space_after = Pt(2)

    _set_document_font(document, _BODY_FONT)


def _apply_page(document) -> None:
    section = document.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.left_margin = Mm(16)
    section.right_margin = Mm(16)
    section.top_margin = Mm(18)
    section.bottom_margin = Mm(16)
    section.header_distance = Mm(8)
    section.footer_distance = Mm(8)


def _apply_header(document, header: str) -> None:
    paragraph = document.sections[0].header.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.space_after = Pt(4)
    run = paragraph.add_run(header)
    _paint_run(run, _BODY_FONT, 8, color=_NAVY)
    _border_below(paragraph, _RED)


def _apply_footer(document) -> None:
    paragraph = document.sections[0].footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("Page ")
    _paint_run(run, _BODY_FONT, 8, color=_NAVY)
    _field(paragraph, " PAGE ")
    run = paragraph.add_run(" / ")
    _paint_run(run, _BODY_FONT, 8, color=_NAVY)
    _field(paragraph, " NUMPAGES ")


def _properties(document, blocks, header: str) -> None:
    title = next((block.text for block in blocks if block.kind == "title"), header)
    document.core_properties.title = title
    document.core_properties.subject = header
    document.core_properties.author = "IFRC Databank"
    document.core_properties.category = "DREF"


def _paint_style(style, name: str, size: float, *, bold: bool = False, italic: bool = False, color: str) -> None:
    font = style.font
    font.name = name
    font.size = Pt(size)
    font.bold = bold
    font.italic = italic
    font.color.rgb = RGBColor.from_string(color)
    r_pr = style.element.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)
    for key in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        r_fonts.set(qn(key), name)
    node = r_pr.find(qn("w:color"))
    if node is not None:
        for attr in ("w:themeColor", "w:themeTint", "w:themeShade"):
            node.attrib.pop(qn(attr), None)
        node.set(qn("w:val"), color)


def _paint_run(run, name: str, size: float, *, bold: bool = False, color: str) -> None:
    run.bold = bold
    run.font.name = name
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    r_pr = run._r.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)
    for key in ("w:ascii", "w:hAnsi", "w:cs"):
        r_fonts.set(qn(key), name)


def _outline(style, level: int) -> None:
    p_pr = style.element.get_or_add_pPr()
    outline = p_pr.find(qn("w:outlineLvl"))
    if outline is None:
        outline = OxmlElement("w:outlineLvl")
        p_pr.append(outline)
    outline.set(qn("w:val"), str(level))


def _ensure_style(document, name: str):
    if _has_style(document, name):
        return document.styles[name]
    style = document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    style.base_style = document.styles["Normal"]
    return style


def _has_style(document, name: str) -> bool:
    try:
        document.styles[name]
    except KeyError:
        return False
    return True


def _set_document_font(document, name: str) -> None:
    styles = document.styles.element
    defaults = styles.find(qn("w:docDefaults"))
    if defaults is None:
        return
    r_pr = defaults.find(qn("w:rPrDefault"))
    if r_pr is None:
        return
    r_pr = r_pr.find(qn("w:rPr"))
    if r_pr is None:
        return
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)
    for key in ("w:ascii", "w:hAnsi", "w:cs"):
        r_fonts.set(qn(key), name)


def _shade(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    existing = tc_pr.find(qn("w:shd"))
    if existing is not None:
        tc_pr.remove(existing)
    shade = OxmlElement("w:shd")
    shade.set(qn("w:val"), "clear")
    shade.set(qn("w:color"), "auto")
    shade.set(qn("w:fill"), fill)
    tc_pr.append(shade)


def _set_widths(table, widths_mm: tuple[int, ...]) -> None:
    for row in table.rows:
        for index, width in enumerate(widths_mm):
            row.cells[index].width = Mm(width)


def _mark_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    marker = OxmlElement("w:tblHeader")
    tr_pr.append(marker)


def _keep_rows(table) -> None:
    for row in table.rows:
        tr_pr = row._tr.get_or_add_trPr()
        if tr_pr.find(qn("w:cantSplit")) is None:
            tr_pr.append(OxmlElement("w:cantSplit"))


def _border_below(paragraph, color: str) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "12")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)
    p_pr.append(borders)


def _field(paragraph, instruction: str) -> None:
    run = paragraph.add_run()
    _paint_run(run, _BODY_FONT, 8, color=_NAVY)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)
