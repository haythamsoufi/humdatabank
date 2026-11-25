"""Read the chapters back from a Word file that was exported from a draft and edited.

Only the narrative chapters come back. The tables and the figures are written from the monitoring
data every time, so text Databank generated (styled ``Generated text`` and ``Generated bullet`` in
the export) and the tables are skipped. A chapter is the text under its GO heading, up to the next
heading, with paragraphs, lists, and the marks a person applied: bold, italic, underline,
strikethrough, colour, highlight, and links.

``analyze_docx`` changes nothing. It returns what each chapter would become so the person can pick
which to keep, and the page then saves the chosen ones like any other edit.
"""

from __future__ import annotations

import re
import zipfile
from io import BytesIO

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.text.run import Run as DocxRun

from plugins.emergency_operations_monitoring.constants import SECTION_LABELS
from plugins.emergency_operations_monitoring.i18n import SUPPORTED, translate
from plugins.emergency_operations_monitoring.services import narrative_format as fmt
from plugins.emergency_operations_monitoring.services.docx_export import GENERATED_BULLET_STYLE, GENERATED_TEXT_STYLE
from plugins.emergency_operations_monitoring.services.drafts import chapter_keys_for, chapters_of
from plugins.emergency_operations_monitoring.services.report_document import chapter_headings

MAX_BYTES = 5 * 1024 * 1024
_MAX_UNPACKED = 60 * 1024 * 1024
_MAX_PARTS = 2000
_IGNORED_STYLES = {GENERATED_TEXT_STYLE, GENERATED_BULLET_STYLE, "Note", "Table text"}
_MANUAL_BULLET = re.compile(r"^\s*(?:[\u2022\u25cf\u25aa\u2013*-])\s+")
_MANUAL_NUMBER = re.compile(r"^\s*\d{1,3}[.)]\s+")
_WORD_HIGHLIGHTS = {
    "yellow": "ffff00",
    "green": "00ff00",
    "cyan": "00ffff",
    "magenta": "ff00ff",
    "blue": "0000ff",
    "red": "ff0000",
    "darkBlue": "000080",
    "darkCyan": "008080",
    "darkGreen": "008000",
    "darkMagenta": "800080",
    "darkRed": "800000",
    "darkYellow": "808000",
    "darkGray": "808080",
    "lightGray": "c0c0c0",
    "black": "000000",
}


class DocxImportError(ValueError):
    """The file cannot be read as an edited draft. The message is shown to the person."""


def read_docx(raw: bytes):
    if not raw:
        raise DocxImportError("The file is empty.")
    if len(raw) > MAX_BYTES:
        raise DocxImportError("The file is larger than 5 MB.")
    if not zipfile.is_zipfile(BytesIO(raw)):
        raise DocxImportError("This is not a Word (.docx) file.")
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            parts = archive.infolist()
            if len(parts) > _MAX_PARTS or sum(part.file_size for part in parts) > _MAX_UNPACKED:
                raise DocxImportError("The file is too large to read.")
            if "word/document.xml" not in archive.namelist():
                raise DocxImportError("This is not a Word (.docx) file.")
        return Document(BytesIO(raw))
    except DocxImportError:
        raise
    except Exception as exc:
        raise DocxImportError("The Word file could not be read.") from exc


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).rstrip(":").casefold()


def heading_index(kind: str) -> dict[str, str]:
    """Each chapter heading in every display language, so a file edited in any of them still maps."""
    index: dict[str, str] = {}
    for key, english in chapter_headings(kind).items():
        for code in SUPPORTED:
            index[_norm(translate(english, lang=code))] = key
    return index


def _body_items(parent):
    """Paragraphs and tables in document order, including those inside content controls."""
    for child in parent.iterchildren():
        name = child.tag.rsplit("}", 1)[-1]
        if name == "p":
            yield "p", child
        elif name == "tbl":
            yield "tbl", child
        elif name == "sdt":
            for content in child.iterchildren(qn("w:sdtContent")):
                yield from _body_items(content)


def _style_name(paragraph) -> str:
    try:
        return str(paragraph.style.name or "")
    except Exception:
        return ""


def _is_heading(paragraph) -> bool:
    return _style_name(paragraph).startswith("Heading")


def _num_pr(paragraph):
    properties = paragraph._p.pPr
    numbering = None if properties is None else properties.numPr
    if numbering is None or numbering.numId is None or int(numbering.numId.val or 0) == 0:
        return None, 0
    ilvl = 0 if numbering.ilvl is None else int(numbering.ilvl.val or 0)
    return int(numbering.numId.val), ilvl


def _numbering_kind(document, number_id: int, level: int) -> str:
    try:
        numbering = document.part.numbering_part.element
        abstract_id = numbering.num_having_numId(number_id).abstractNumId.val
        abstract = numbering.xpath(f'w:abstractNum[@w:abstractNumId="{abstract_id}"]')[0]
        formats = abstract.xpath(f'w:lvl[@w:ilvl="{level}"]/w:numFmt')
        value = formats[0].get(qn("w:val")) if formats else "bullet"
    except Exception:
        return "ul"
    return "ul" if value in ("bullet", "none") else "ol"


def _list_info(document, paragraph) -> tuple[str, object] | None:
    """``("ul" | "ol", identity)`` for a list paragraph. Paragraphs of one list share an identity."""
    style = _style_name(paragraph)
    number_id, level = _num_pr(paragraph)
    if number_id:
        return _numbering_kind(document, number_id, level), number_id
    if style.startswith("List Bullet") or style == GENERATED_BULLET_STYLE:
        return "ul", style
    if style.startswith("List Number"):
        return "ol", style
    return None


def _marks(run: DocxRun) -> tuple[bool, bool, bool]:
    bold = bool(run.bold)
    italic = bool(run.italic)
    underline = run.underline not in (None, False, 0)
    try:
        character = str(run.style.name or "")
    except Exception:
        character = ""
    return bold or character == "Strong", italic or character == "Emphasis", bool(underline)


def _direct_color(properties, tag: str) -> str:
    node = None if properties is None else properties.find(qn(tag))
    if node is None:
        return ""
    return fmt.normalize_color("#" + str(node.get(qn("w:val")) or ""))


def _run_marks(element, paragraph) -> tuple:
    """Marks written on the run itself. A character style is not treated as something the person set,
    except Strong and Emphasis, which Word uses for bold and italic."""
    run = DocxRun(element, paragraph)
    bold, italic, underline = _marks(run)
    properties = element.find(qn("w:rPr"))
    href = ""
    parent = element.getparent()
    if parent is not None and parent.tag == qn("w:hyperlink"):
        rel_id = parent.get(qn("r:id"))
        relation = paragraph.part.rels.get(rel_id) if rel_id else None
        if relation is not None and relation.is_external:
            href = fmt.safe_href(relation.target_ref)
    color = _direct_color(properties, "w:color")
    highlight = ""
    shade = None if properties is None else properties.find(qn("w:shd"))
    if shade is not None:
        highlight = fmt.normalize_color("#" + str(shade.get(qn("w:fill")) or ""))
    if not highlight and properties is not None:
        painted = properties.find(qn("w:highlight"))
        if painted is not None:
            highlight = fmt.normalize_color("#" + _WORD_HIGHLIGHTS.get(str(painted.get(qn("w:val")) or ""), ""))
    strike_node = None if properties is None else properties.find(qn("w:strike"))
    strike = strike_node is not None and strike_node.get(qn("w:val")) not in ("0", "false", "off")
    return (bold, italic, underline, strike, href, color, highlight)


def _runs(paragraph) -> list[fmt.Run]:
    """The visible runs of a paragraph, with tracked deletions and text boxes left out."""
    found: list[fmt.Run] = []
    query = ".//w:r[not(ancestor::w:del)][not(ancestor::w:moveFrom)][not(ancestor::w:txbxContent)]"
    for element in paragraph._p.xpath(query):
        run = DocxRun(element, paragraph)
        text = run.text or ""
        if not text:
            continue
        marks = _run_marks(element, paragraph)
        pieces = text.replace("\t", " ").replace("\r", "\n").split("\n")
        for index, piece in enumerate(pieces):
            if index:
                found.append(fmt.Run("\n", *marks))
            if piece:
                found.append(fmt.Run(piece, *marks))
    return found


def _strip_marker(runs: list[fmt.Run], pattern: re.Pattern) -> list[fmt.Run]:
    for index, run in enumerate(runs):
        if run.is_break:
            continue
        stripped = pattern.sub("", run.text, count=1)
        runs = list(runs)
        runs[index] = fmt.Run(stripped, *run.marks())
        return runs
    return runs


def _nodes(document, paragraphs: list[Paragraph]) -> list[fmt.Node]:
    nodes: list[fmt.Node] = []
    items: list[tuple[fmt.Run, ...]] = []
    current: tuple[str, object] | None = None

    def flush() -> None:
        nonlocal items, current
        if current and items:
            nodes.append(fmt.Node(current[0], items=tuple(items)))
        items = []
        current = None

    for paragraph in paragraphs:
        runs = _runs(paragraph)
        if not fmt.has_text(runs):
            flush()
            continue
        info = _list_info(document, paragraph)
        if info is None:
            first = next((run.text for run in runs if not run.is_break), "")
            if _MANUAL_BULLET.match(first):
                info = ("ul", "manual-bullet")
                runs = _strip_marker(runs, _MANUAL_BULLET)
            elif _MANUAL_NUMBER.match(first):
                info = ("ol", "manual-number")
                runs = _strip_marker(runs, _MANUAL_NUMBER)
        merged = fmt.merge_runs(runs)
        if info is None:
            flush()
            nodes.append(fmt.Node("p", runs=merged))
            continue
        if current != info:
            flush()
            current = info
        items.append(merged)
    flush()
    return nodes


def _regions(document, kind: str, *, allow_plain: bool) -> tuple[dict[str, list[Paragraph]], dict[str, int], list[str]]:
    """The paragraphs under each chapter heading, the text found under other headings, and any
    chapter heading that appears twice."""
    index = heading_index(kind)
    regions: dict[str, list[Paragraph]] = {}
    ignored: dict[str, int] = {}
    repeated: list[str] = []
    current: str | None = None
    last_heading = ""
    for tag, element in _body_items(document.element.body):
        if tag != "p":
            continue
        paragraph = Paragraph(element, document)
        text = (paragraph.text or "").strip()
        heading = _is_heading(paragraph)
        key = None
        if text and (heading or (allow_plain and len(text) <= 200 and _list_info(document, paragraph) is None)):
            key = index.get(_norm(text))
        if key:
            if key in regions:
                repeated.append(text)
                current = None
            else:
                regions[key] = []
                current = key
            continue
        if heading:
            current = None
            last_heading = text
            continue
        if _style_name(paragraph) in _IGNORED_STYLES:
            continue
        if current is None:
            if text and last_heading:
                ignored[last_heading] = ignored.get(last_heading, 0) + 1
            continue
        regions[current].append(paragraph)
    return regions, ignored, repeated


_REFERENCE_PREFIXES = ("emergency-operations:", "dref-monitoring:")


def expected_reference(operation_id: int, draft_id: int) -> str:
    return f"emergency-operations:{operation_id}:{draft_id}"


def _reference_tail(value: str) -> str:
    for prefix in _REFERENCE_PREFIXES:
        if value.startswith(prefix):
            return value[len(prefix):]
    return ""


def analyze_docx(raw: bytes, draft, operation) -> dict:
    """What importing this file would do to each chapter of ``draft``. Nothing is saved."""
    document = read_docx(raw)
    kind = draft.report_kind
    regions, ignored, repeated = _regions(document, kind, allow_plain=False)
    if not regions:
        regions, ignored, repeated = _regions(document, kind, allow_plain=True)
    if not regions:
        raise DocxImportError(
            "No chapter of this report was found in the file. Export the draft to Word, edit that file, and upload it again."
        )

    stored = chapters_of(draft)
    chapters = []
    for key in chapter_keys_for(draft):
        before_html = fmt.to_html(stored.get(key))
        row = {
            "key": key,
            "label": translate(SECTION_LABELS[key], lang=getattr(draft, "language", None) or "en"),
            "current": fmt.to_plain(before_html),
            "incoming": "",
            "html": "",
            "words_before": fmt.word_count(before_html),
            "words_after": 0,
        }
        if key not in regions:
            row["status"] = "missing"
            chapters.append(row)
            continue
        after_html = fmt.nodes_to_html(_nodes(document, regions[key]))
        row.update(incoming=fmt.to_plain(after_html), words_after=fmt.word_count(after_html))
        if fmt.too_long(after_html):
            row["status"] = "too_long"
        elif after_html == before_html:
            row["status"] = "unchanged"
        else:
            row["html"] = after_html
            row["status"] = "added" if not before_html else ("cleared" if not after_html else "changed")
        chapters.append(row)

    warnings: list[str] = []
    reference = str(getattr(document.core_properties, "identifier", "") or "")
    expected = expected_reference(operation.id, draft.id)
    reference_tail = _reference_tail(reference)
    if reference_tail and reference_tail != _reference_tail(expected):
        warnings.append("This file was exported from a different report.")
    if repeated:
        warnings.append("A chapter heading appears more than once. Only the first one was read.")
    return {
        "ok": True,
        "chapters": chapters,
        "ignored": [{"heading": heading, "paragraphs": count} for heading, count in list(ignored.items())[:12]],
        "warnings": warnings,
        "summary": {
            status: sum(1 for row in chapters if row["status"] == status)
            for status in ("changed", "added", "cleared", "unchanged", "missing", "too_long")
        },
    }
