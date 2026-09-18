"""PDF → paragraph/table dicts in the same shape as the Word narrative reader."""

from __future__ import annotations

import re
from collections import Counter

from plugins.upr.errors import UprError
from plugins.upr.idml.word_reader import MAX_NARRATIVE_BLOCKS, safe_export_href

_TEXT_FONT_BOLD = 16
_BULLET_RE = re.compile(r"^[\u2022\u2023\u25e6\u2043\u2219\u25aa\u25cf\-\u2013\u2014\*]\s+")
_FOLIO_RE = re.compile(r"(?:^|\s)/\s*\d+\s*$")
_PAGE_NUM_RE = re.compile(r"^\d{1,4}$")
_HEADER_BAND = 48.0
_FOOTER_BAND = 52.0


def _span_bold(span: dict) -> bool:
    flags = int(span.get("flags") or 0)
    font = str(span.get("font") or "").lower()
    return bool(flags & _TEXT_FONT_BOLD) or "bold" in font


def _join_line_text(parts: list[str]) -> str:
    out = ""
    for part in parts:
        part = (part or "").strip()
        if not part:
            continue
        if out.endswith("-") and part[:1].islower():
            out = out[:-1] + part
        elif out:
            out += " " + part
        else:
            out = part
    return out


def _merge_runs(runs: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for run in runs:
        text = str(run.get("text") or "")
        if not text:
            continue
        href = str(run.get("href") or "")
        bold = bool(run.get("bold"))
        if merged and merged[-1]["href"] == href and merged[-1]["bold"] == bold:
            prev = merged[-1]["text"]
            if prev.endswith("-") and text[:1].islower():
                merged[-1]["text"] = prev[:-1] + text
            elif prev.endswith((" ", "\n")) or text.startswith(" "):
                merged[-1]["text"] = prev + text
            else:
                merged[-1]["text"] = prev + " " + text
        else:
            merged.append({"text": text, "href": href, "bold": bold})
    return merged


def _href_for_bbox(bbox, links: list[tuple]) -> str:
    import fitz

    rect = fitz.Rect(bbox)
    for link_rect, href in links:
        if rect.intersects(link_rect):
            return href
    return ""


def _page_links(page) -> list[tuple]:
    import fitz

    found: list[tuple] = []
    for link in page.get_links() or []:
        href = safe_export_href(link.get("uri") or "")
        if not href or "from" not in link:
            continue
        found.append((fitz.Rect(link["from"]), href))
    return found


def _is_running_chrome(text: str, *, y0: float, y1: float, page_h: float, repeating: set[str]) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    in_band = y0 < _HEADER_BAND or y1 > page_h - _FOOTER_BAND
    if not in_band:
        return False
    low = raw.lower()
    if _PAGE_NUM_RE.match(raw) or _FOLIO_RE.search(raw):
        return True
    if raw in repeating or low in repeating:
        return True
    if low.startswith("ifrc network") and len(raw) < 80:
        return True
    return False


def _heading_role(size: float, body_size: float) -> str:
    if size >= max(body_size * 1.45, body_size + 3.5):
        return "h1"
    if size >= max(body_size * 1.18, body_size + 1.2):
        return "h2"
    return ""


def _block_from_dict(block: dict, links: list[tuple], body_size: float) -> dict | None:
    lines = []
    runs: list[dict] = []
    sizes: list[float] = []
    y0 = float(block.get("bbox", [0, 0, 0, 0])[1])
    y1 = float(block.get("bbox", [0, 0, 0, 0])[3])
    for line in block.get("lines") or []:
        line_bits: list[str] = []
        for span in line.get("spans") or []:
            text = str(span.get("text") or "")
            if not text.strip():
                continue
            size = float(span.get("size") or 0)
            sizes.append(size)
            runs.append(
                {
                    "text": text,
                    "href": _href_for_bbox(span.get("bbox") or line.get("bbox"), links),
                    "bold": _span_bold(span),
                }
            )
            line_bits.append(text)
        if line_bits:
            lines.append("".join(line_bits))
    text = _join_line_text(lines)
    if not text:
        return {"text": "", "runs": [], "bullet": False, "role": "empty", "y0": y0, "y1": y1}
    bullet = bool(_BULLET_RE.match(text))
    if bullet:
        text = _BULLET_RE.sub("", text).strip()
        runs = _merge_runs(runs)
        if runs:
            runs[0]["text"] = _BULLET_RE.sub("", str(runs[0]["text"])).lstrip()
            runs = [run for run in runs if str(run.get("text") or "").strip()]
    else:
        runs = _merge_runs(runs)
    size = max(sizes) if sizes else body_size
    return {
        "text": text,
        "runs": runs or [{"text": text, "href": "", "bold": False}],
        "bullet": bullet,
        "role": _heading_role(size, body_size),
        "y0": y0,
        "y1": y1,
    }


def _table_block(rows_text: list[list]) -> dict | None:
    rows: list[list[list[dict]]] = []
    for raw_row in rows_text or []:
        cells: list[list[dict]] = []
        for cell in raw_row:
            text = " ".join(str(cell or "").split())
            if not text:
                cells.append([])
                continue
            cells.append(
                [
                    {
                        "text": text,
                        "runs": [{"text": text, "href": "", "bold": False}],
                        "bullet": False,
                        "role": "",
                    }
                ]
            )
        if any(cells):
            rows.append(cells)
    if not rows:
        return None
    return {"kind": "table", "rows": rows, "text": "", "runs": [], "bullet": False, "role": ""}


def _page_tables(page) -> list[dict]:
    try:
        finder = page.find_tables()
    except Exception:
        return []
    found: list[dict] = []
    for table in getattr(finder, "tables", None) or []:
        try:
            rows = table.extract()
            bbox = tuple(table.bbox)
        except Exception:
            continue
        if not rows:
            continue
        found.append({"bbox": bbox, "rows": rows, "y0": float(bbox[1])})
    return found


def _inside_table(y0: float, y1: float, x0: float, tables: list[dict]) -> bool:
    mid_y = (y0 + y1) / 2.0
    for table in tables:
        x_min, top, x_max, bottom = table["bbox"]
        if top - 2.0 <= mid_y <= bottom + 2.0 and x_min - 2.0 <= x0 <= x_max + 2.0:
            return True
    return False


def _collect_sizes(doc) -> float:
    weights: Counter[float] = Counter()
    for page in doc:
        for block in page.get_text("dict").get("blocks") or []:
            if block.get("type") != 0:
                continue
            for line in block.get("lines") or []:
                for span in line.get("spans") or []:
                    text = str(span.get("text") or "").strip()
                    size = float(span.get("size") or 0)
                    if text and size > 0:
                        weights[round(size, 1)] += max(len(text), 1)
    if not weights:
        return 10.0
    best = max(weights.values())
    return min(size for size, count in weights.items() if count == best)


def _repeating_chrome(doc) -> set[str]:
    counts: Counter[str] = Counter()
    for page in doc:
        page_h = float(page.rect.height)
        lines: list[tuple[float, str]] = []
        for block in page.get_text("dict").get("blocks") or []:
            if block.get("type") != 0:
                continue
            for line in block.get("lines") or []:
                text = "".join(str(span.get("text") or "") for span in line.get("spans") or []).strip()
                if not text:
                    continue
                y0 = float(line["bbox"][1])
                y1 = float(line["bbox"][3])
                if y0 < _HEADER_BAND or y1 > page_h - _FOOTER_BAND:
                    lines.append((y0, text))
        if not lines:
            continue
        lines.sort(key=lambda item: item[0])
        counts[lines[0][1]] += 1
        if len(lines) > 1:
            counts[lines[-1][1]] += 1
    return {text for text, count in counts.items() if count >= 2}


def load_pdf_paragraphs(pdf_bytes: bytes) -> list[dict]:
    import fitz

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise UprError("Upload a valid PDF.") from exc
    try:
        if doc.needs_pass:
            raise UprError("This PDF is password-protected.")
        body_size = _collect_sizes(doc)
        repeating = _repeating_chrome(doc)
        blocks: list[dict] = []
        for page in doc:
            page_h = float(page.rect.height)
            links = _page_links(page)
            tables = _page_tables(page)
            items: list[tuple[float, dict]] = []
            for table in tables:
                table_block = _table_block(table["rows"])
                if table_block:
                    items.append((table["y0"], table_block))
            for block in page.get_text("dict").get("blocks") or []:
                if block.get("type") != 0:
                    continue
                bbox = block.get("bbox") or (0, 0, 0, 0)
                if _inside_table(float(bbox[1]), float(bbox[3]), float(bbox[0]), tables):
                    continue
                parsed = _block_from_dict(block, links, body_size)
                if parsed is None:
                    continue
                text = str(parsed.get("text") or "").strip()
                if parsed.get("role") != "empty" and _is_running_chrome(
                    text, y0=parsed["y0"], y1=parsed["y1"], page_h=page_h, repeating=repeating
                ):
                    continue
                items.append((parsed["y0"], parsed))
            items.sort(key=lambda item: item[0])
            for _y, parsed in items:
                parsed.pop("y0", None)
                parsed.pop("y1", None)
                blocks.append(parsed)
                if parsed.get("kind") == "table":
                    blocks.append({"text": "", "runs": [], "bullet": False, "role": "empty"})
                if len(blocks) > MAX_NARRATIVE_BLOCKS:
                    raise UprError("The narrative document has too many paragraphs.")
        if not any((row.get("text") or "").strip() or row.get("kind") == "table" for row in blocks):
            raise UprError(
                "This PDF has no extractable text. Upload a Word document (.docx) or a text-based PDF."
            )
        return blocks
    finally:
        doc.close()
