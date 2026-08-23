"""OOXML → paragraph/table dicts for UPR narrative uploads."""

from __future__ import annotations

import zipfile
from io import BytesIO
from urllib.parse import urlparse

from plugins.upr_visuals.errors import UprVisualsError

MAX_NARRATIVE_BLOCKS = 2000
_ALLOWED_HREF_SCHEMES = frozenset({"http", "https", "mailto"})


def safe_export_href(href: str | None) -> str:
    """Keep only http(s) and mailto links from Word. Drop javascript:/file:/data:."""
    raw = (href or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme == "mailto":
        return raw if parsed.path else ""
    if scheme in {"http", "https"} and parsed.netloc:
        return raw
    return ""


def _parse_word_para(p_el, hrefs: dict[str, str], w_ns: str, r_ns: str) -> dict | None:
    ppr = p_el.find(f"{w_ns}pPr")
    bullet = ppr is not None and ppr.find(f"{w_ns}numPr") is not None
    runs: list[dict] = []
    for child in list(p_el):
        if child.tag == f"{w_ns}hyperlink":
            href = hrefs.get(child.get(f"{r_ns}id") or "", "")
            for r_el in child.iter(f"{w_ns}r"):
                text = "".join((t.text or "") for t in r_el.iter(f"{w_ns}t"))
                if not text:
                    continue
                rpr = r_el.find(f"{w_ns}rPr")
                bold = rpr is not None and rpr.find(f"{w_ns}b") is not None
                runs.append({"text": text, "href": href, "bold": bold})
        elif child.tag == f"{w_ns}r":
            text = "".join((t.text or "") for t in child.iter(f"{w_ns}t"))
            if not text:
                continue
            rpr = child.find(f"{w_ns}rPr")
            bold = rpr is not None and rpr.find(f"{w_ns}b") is not None
            runs.append({"text": text, "href": "", "bold": bold})
    text = "".join(run["text"] for run in runs).strip()
    if not text:
        return {"text": "", "runs": [], "bullet": False, "role": "empty"}
    return {"text": text, "runs": runs, "bullet": bullet, "role": ""}


def _parse_word_table(tbl, hrefs: dict[str, str], w_ns: str, r_ns: str) -> dict | None:
    rows: list[list[list[dict]]] = []
    for tr in tbl.findall(f"{w_ns}tr"):
        row: list[list[dict]] = []
        for tc in tr.findall(f"{w_ns}tc"):
            cell: list[dict] = []
            for p_el in tc.findall(f"{w_ns}p"):
                parsed = _parse_word_para(p_el, hrefs, w_ns, r_ns)
                if parsed and parsed.get("role") != "empty":
                    cell.append(parsed)
            row.append(cell)
        if any(row):
            rows.append(row)
    if not rows:
        return None
    return {"kind": "table", "rows": rows, "text": "", "runs": [], "bullet": False, "role": ""}


def _walk_word_blocks(el, hrefs: dict[str, str], w_ns: str, r_ns: str, out: list[dict]) -> None:
    if el.tag == f"{w_ns}tbl":
        table = _parse_word_table(el, hrefs, w_ns, r_ns)
        if table:
            out.append(table)
        return
    if el.tag == f"{w_ns}p":
        para = _parse_word_para(el, hrefs, w_ns, r_ns)
        if para:
            out.append(para)
        return
    for child in list(el):
        _walk_word_blocks(child, hrefs, w_ns, r_ns, out)


def load_word_paragraphs(docx_bytes: bytes) -> list[dict]:
    try:
        from defusedxml.ElementTree import fromstring as xml_fromstring
    except ImportError:  # pragma: no cover - production pins defusedxml
        from xml.etree.ElementTree import fromstring as xml_fromstring
    from xml.etree.ElementTree import ParseError

    from plugins.upr_visuals.idml import read_docx_xml_member

    w_ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    r_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    blocks: list[dict] = []
    try:
        with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
            try:
                rels_root = xml_fromstring(read_docx_xml_member(zf, "word/_rels/document.xml.rels"))
            except KeyError:
                hrefs = {}
            else:
                hrefs = {
                    rel.get("Id"): safe_export_href(rel.get("Target") or "")
                    for rel in rels_root
                    if "hyperlink" in (rel.get("Type") or "").lower()
                }
            root = xml_fromstring(read_docx_xml_member(zf, "word/document.xml"))
            body = root.find(f"{w_ns}body")
            if body is not None:
                for child in list(body):
                    _walk_word_blocks(child, hrefs, w_ns, r_ns, blocks)
                    if len(blocks) > MAX_NARRATIVE_BLOCKS:
                        raise UprVisualsError("The Word document has too many paragraphs.")
    except UprVisualsError:
        raise
    except (ParseError, zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise UprVisualsError("Upload a Word document (.docx).") from exc
    return blocks
