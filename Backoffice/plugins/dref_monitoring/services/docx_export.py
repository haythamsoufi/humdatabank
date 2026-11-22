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


# Paragraph styles the import reads. Text Databank writes from the figures uses the first two, so an
# edited Word file gives back only what a person wrote. They look exactly like Normal and List Bullet.
GENERATED_TEXT_STYLE = "Generated text"
GENERATED_BULLET_STYLE = "Generated bullet"


def render_docx(blocks: list, header: str, language: str = "en", reference: str = "") -> bytes:
    """The report as a Word file. ``reference`` is stored in the file so an import can tell whether
    it was exported from the same draft."""
    document = Document()
    _apply_page(document)
    _apply_styles(document)
    _apply_header(document, header)
    _apply_footer(document, blocks, language)
    for block in blocks:
        _add_block(document, block)
    if language == "ar":
        _mark_rtl(document)
    _properties(document, blocks, header, reference)
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
        generated = getattr(block, "generated", False) and _has_style(document, GENERATED_BULLET_STYLE)
        style = GENERATED_BULLET_STYLE if generated else ("List Bullet" if _has_style(document, "List Bullet") else "Normal")
        for row in block.rows:
            text = row[0] if row else ""
            if style == "Normal":
                text = f"• {text}"
            document.add_paragraph(text, style=style)
    elif getattr(block, "is_grid", False):
        _add_cards(document, block.cards)
    elif getattr(block, "html", "") and getattr(block, "generated", False):
        _add_generated_rich(document, block)
    elif getattr(block, "html", ""):
        _add_rich(document, block)
    else:
        style = GENERATED_TEXT_STYLE if getattr(block, "generated", False) and block.text else "Normal"
        document.add_paragraph(block.text or "", style=style)


_HYPERLINK_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"


def _add_runs(paragraph, runs) -> None:
    for run in runs:
        if run.is_break:
            paragraph.add_run().add_break()
            continue
        item = paragraph.add_run(run.text)
        if run.bold:
            item.bold = True
        if run.italic:
            item.italic = True
        if run.underline:
            item.underline = True
        if getattr(run, "strike", False):
            item.font.strike = True
        color = getattr(run, "color", "") or ""
        if color:
            item.font.color.rgb = RGBColor.from_string(color[1:].upper())
        highlight = getattr(run, "highlight", "") or ""
        if highlight:
            _shade_text(item, highlight[1:].upper())
        href = getattr(run, "href", "") or ""
        if href:
            _attach_link(item, href)


def _shade_text(run, fill: str) -> None:
    """A highlight behind the words. Word's highlight names cannot hold an arbitrary colour."""
    properties = run._r.get_or_add_rPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), fill)


def _attach_link(run, url: str) -> None:
    from plugins.dref_monitoring.services.narrative_format import safe_href

    address = safe_href(url)
    if not address:
        return
    element = run._r
    parent = element.getparent()
    index = list(parent).index(element)
    parent.remove(element)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), run.part.relate_to(address, _HYPERLINK_REL, is_external=True))
    link.append(element)
    parent.insert(index, link)


def _plain_runs(runs) -> str:
    return "".join("\n" if getattr(run, "is_break", False) else run.text for run in runs)


def _add_generated_rich(document, block) -> None:
    """Figure text with the generated styles, so a Word import does not read it back as a chapter."""
    text_style = GENERATED_TEXT_STYLE if _has_style(document, GENERATED_TEXT_STYLE) else "Normal"
    bullet_style = GENERATED_BULLET_STYLE if _has_style(document, GENERATED_BULLET_STYLE) else "Normal"
    nodes = block.nodes
    if not nodes:
        document.add_paragraph(block.text or "", style=text_style if (block.text or "").strip() else "Normal")
        return
    for node in nodes:
        if not node.is_list:
            text = _plain_runs(node.runs)
            document.add_paragraph(text, style=text_style if text.strip() else "Normal")
            continue
        for item in node.items:
            text = _plain_runs(item)
            if bullet_style == "Normal":
                text = f"• {text}"
            document.add_paragraph(text, style=bullet_style)


def _add_rich(document, block) -> None:
    """A chapter with its paragraphs, lists, and the marks a person applied."""
    nodes = block.nodes
    if not nodes:
        document.add_paragraph("", style="Normal")
        return
    for node in nodes:
        if not node.is_list:
            _add_runs(document.add_paragraph(style="Normal"), node.runs)
            continue
        numbered = node.type == "ol" and _has_style(document, "List Number")
        bulleted = node.type == "ul" and _has_style(document, "List Bullet")
        style = "List Number" if numbered else ("List Bullet" if bulleted else "Normal")
        paragraphs = []
        for number, item in enumerate(node.items, start=1):
            paragraph = document.add_paragraph(style=style)
            if style == "Normal":
                paragraph.add_run(f"{number}. " if node.type == "ol" else "\u2022 ")
            _add_runs(paragraph, item)
            paragraphs.append(paragraph)
        if numbered:
            _restart_numbering(document, paragraphs)


def _restart_numbering(document, paragraphs) -> None:
    """Start the list at 1. Word counts every ``List Number`` paragraph in one run unless told otherwise."""
    try:
        numbering = document.part.numbering_part.numbering_definitions._numbering
        number_id = document.styles["List Number"].element.pPr.numPr.numId.val
        base = numbering.num_having_numId(number_id)
        fresh = numbering.add_num(base.abstractNumId.val)
        fresh.add_lvlOverride(ilvl=0).add_startOverride(1)
        for paragraph in paragraphs:
            properties = paragraph._p.get_or_add_pPr()
            numbering_properties = properties.get_or_add_numPr()
            numbering_properties.get_or_add_ilvl().val = 0
            numbering_properties.get_or_add_numId().val = fresh.numId
    except Exception:  # The list still reads in order. Only the restart is lost.
        return


def _add_cards(document, cards) -> None:
    """Short entries (the contact people) two to a row, with no borders. Word skips tables on import."""
    columns = 2
    table = document.add_table(rows=(len(cards) + columns - 1) // columns, cols=columns)
    table.autofit = False
    _set_widths(table, (89, 89))
    for index, runs in enumerate(cards):
        cell = table.rows[index // columns].cells[index % columns]
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(10)
        paragraph.paragraph_format.line_spacing = 1.1
        _add_runs(paragraph, runs)
    _keep_rows(table)


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
        generated_bullet = _ensure_style(document, GENERATED_BULLET_STYLE)
        generated_bullet.base_style = bullet
    number = document.styles["List Number"] if _has_style(document, "List Number") else None
    if number is not None:
        _paint_style(number, _BODY_FONT, 10.5, color="000000")
        number.paragraph_format.space_after = Pt(2)
    generated = _ensure_style(document, GENERATED_TEXT_STYLE)
    generated.base_style = normal

    _set_document_font(document, _BODY_FONT)


def _apply_page(document) -> None:
    section = document.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.left_margin = Mm(16)
    section.right_margin = Mm(16)
    section.top_margin = Mm(18)
    section.bottom_margin = Mm(22)
    section.header_distance = Mm(8)
    section.footer_distance = Mm(14)


def _apply_header(document, header: str) -> None:
    paragraph = document.sections[0].header.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.space_after = Pt(4)
    run = paragraph.add_run(header)
    _paint_run(run, _BODY_FONT, 8, color=_NAVY)
    _border_below(paragraph, _RED)


def footer_parts(blocks) -> tuple[str, str]:
    """The report type and the operation name the footer carries: ``22  DREF Operational Update • Zedland``."""
    title = next((block.text for block in blocks if block.kind == "title"), "")
    subtitle = next((block.text for block in blocks if block.kind == "subtitle"), "")
    return (title or "").strip(), (subtitle or "").strip()


def _apply_footer(document, blocks, language: str = "en") -> None:
    title, subtitle = footer_parts(blocks)
    paragraph = document.sections[0].footer.paragraphs[0]
    # In a right-to-left file Word reads "left" as the start of the line, which is the right edge.
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    _field(paragraph, " PAGE ", bold=True, size=11)
    if title:
        run = paragraph.add_run("   " + title)
        _paint_run(run, _BODY_FONT, 9, color=_NAVY)
    if subtitle:
        run = paragraph.add_run(" \u2022 " if title else "   ")
        _paint_run(run, _BODY_FONT, 9, bold=True, color=_RED)
        run = paragraph.add_run(subtitle)
        _paint_run(run, _BODY_FONT, 9, bold=True, color=_NAVY)


def _mark_rtl(document) -> None:
    for paragraph in document.paragraphs:
        _bidi(paragraph)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _bidi(paragraph)
    for section in document.sections:
        for paragraph in list(section.header.paragraphs) + list(section.footer.paragraphs):
            _bidi(paragraph)
        marker = OxmlElement("w:bidi")
        section._sectPr.append(marker)


def _bidi(paragraph) -> None:
    properties = paragraph._p.get_or_add_pPr()
    if properties.find(qn("w:bidi")) is None:
        properties.append(OxmlElement("w:bidi"))
    for run in paragraph.runs:
        r_pr = run._r.get_or_add_rPr()
        r_fonts = r_pr.find(qn("w:rFonts"))
        if r_fonts is None:
            r_fonts = OxmlElement("w:rFonts")
            r_pr.append(r_fonts)
        r_fonts.set(qn("w:cs"), "Tajawal")


def _properties(document, blocks, header: str, reference: str = "") -> None:
    title = next((block.text for block in blocks if block.kind == "title"), header)
    document.core_properties.title = title
    document.core_properties.subject = header
    document.core_properties.author = "IFRC Databank"
    document.core_properties.category = "DREF"
    if reference:
        document.core_properties.identifier = reference


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


def _field(paragraph, instruction: str, *, bold: bool = False, size: float = 8) -> None:
    run = paragraph.add_run()
    _paint_run(run, _BODY_FONT, size, bold=bold, color=_NAVY)
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
