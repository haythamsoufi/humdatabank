"""OOXML → paragraph/table dicts for UPR narrative uploads."""

from __future__ import annotations

import base64
import mimetypes
import posixpath
import zipfile
from io import BytesIO
from urllib.parse import urlparse, unquote
from xml.etree.ElementTree import Element

from plugins.upr.errors import UprError

MAX_NARRATIVE_BLOCKS = 2000
MAX_NARRATIVE_IMAGES = 40
MAX_NARRATIVE_IMAGE_BYTES = 8 * 1024 * 1024
_ALLOWED_HREF_SCHEMES = frozenset({"http", "https", "mailto"})
_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".bmp"})
_EMU_PER_PT = 12700.0
_MAX_IMAGE_WIDTH_PT = 529.9

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_WP_NS = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
_V_NS = "{urn:schemas-microsoft-com:vml}"


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


def _toggle(rpr: Element | None, tag: str) -> bool:
    if rpr is None:
        return False
    node = rpr.find(tag)
    if node is None:
        return False
    val = (node.get(f"{_W_NS}val") or "true").strip().lower()
    return val not in {"0", "false", "off"}


def _toggle_or_none(rpr: Element | None, tag: str) -> bool | None:
    if rpr is None or rpr.find(tag) is None:
        return None
    return _toggle(rpr, tag)


def _first_defined(*values: bool | None) -> bool | None:
    for value in values:
        if value is not None:
            return value
    return None


def _p_style(ppr: Element | None) -> str:
    if ppr is None:
        return ""
    el = ppr.find(f"{_W_NS}pStyle")
    return (el.get(f"{_W_NS}val") or "").strip() if el is not None else ""


def _r_style(rpr: Element | None) -> str:
    if rpr is None:
        return ""
    el = rpr.find(f"{_W_NS}rStyle")
    return (el.get(f"{_W_NS}val") or "").strip() if el is not None else ""


def _p_align(ppr: Element | None) -> str:
    if ppr is None:
        return ""
    jc = ppr.find(f"{_W_NS}jc")
    val = ((jc.get(f"{_W_NS}val") if jc is not None else "") or "").strip().lower()
    return {
        "center": "center",
        "right": "right",
        "end": "right",
        "both": "justify",
        "distribute": "justify",
        "left": "left",
        "start": "left",
    }.get(val, "")


def _sz_pt(rpr: Element | None) -> float | None:
    if rpr is None:
        return None
    node = rpr.find(f"{_W_NS}sz")
    if node is None:
        node = rpr.find(f"{_W_NS}szCs")
    if node is None:
        return None
    try:
        half = float(node.get(f"{_W_NS}val") or 0)
    except ValueError:
        return None
    if half <= 0:
        return None
    return half / 2.0


def _style_mark_maps(styles_root: Element | None) -> tuple[dict[str, bool], dict[str, bool]]:
    italic: dict[str, bool | None] = {}
    bold: dict[str, bool | None] = {}
    based_on: dict[str, str] = {}
    if styles_root is None:
        return {}, {}
    for style in styles_root.iter(f"{_W_NS}style"):
        sid = (style.get(f"{_W_NS}styleId") or "").strip()
        if not sid:
            continue
        based = style.find(f"{_W_NS}basedOn")
        based_on[sid] = (based.get(f"{_W_NS}val") or "").strip() if based is not None else ""
        rpr = style.find(f"{_W_NS}rPr")
        italic[sid] = _first_defined(
            _toggle_or_none(rpr, f"{_W_NS}i"),
            _toggle_or_none(rpr, f"{_W_NS}iCs"),
        )
        bold[sid] = _first_defined(
            _toggle_or_none(rpr, f"{_W_NS}b"),
            _toggle_or_none(rpr, f"{_W_NS}bCs"),
        )
        if sid.lower() == "caption" and italic[sid] is None:
            italic[sid] = True

    def _resolve(table: dict[str, bool | None], sid: str, seen: set[str] | None = None) -> bool:
        if not sid:
            return False
        chain = seen or set()
        if sid in chain:
            return False
        chain.add(sid)
        direct = table.get(sid)
        if direct is not None:
            return bool(direct)
        return _resolve(table, based_on.get(sid, ""), chain)

    return (
        {sid: _resolve(italic, sid) for sid in italic},
        {sid: _resolve(bold, sid) for sid in bold},
    )


def _run_marks(
    r_el: Element,
    *,
    para_bold: bool = False,
    para_italic: bool = False,
    char_italic: dict[str, bool] | None = None,
    char_bold: dict[str, bool] | None = None,
) -> tuple[bool, bool]:
    rpr = r_el.find(f"{_W_NS}rPr")
    rstyle = _r_style(rpr)
    style_italic = bool((char_italic or {}).get(rstyle))
    style_bold = bool((char_bold or {}).get(rstyle))
    bold = _first_defined(
        _toggle_or_none(rpr, f"{_W_NS}b"),
        _toggle_or_none(rpr, f"{_W_NS}bCs"),
        style_bold if rstyle else None,
        para_bold,
    )
    italic = _first_defined(
        _toggle_or_none(rpr, f"{_W_NS}i"),
        _toggle_or_none(rpr, f"{_W_NS}iCs"),
        style_italic if rstyle else None,
        para_italic,
    )
    return bool(bold), bool(italic)


def _media_member(target: str) -> str:
    raw = unquote((target or "").replace("\\", "/")).strip()
    if not raw or raw.startswith(("/", "\\")) or ":" in raw:
        return ""
    path = posixpath.normpath(posixpath.join("word", raw))
    if path.startswith("word/") and ".." not in path.split("/"):
        return path
    return ""


def _mime_for(name: str) -> str:
    ext = posixpath.splitext(name)[1].lower()
    if ext not in _IMAGE_EXTS:
        return ""
    return mimetypes.guess_type(name)[0] or "image/png"


def _extent_pt(drawing: Element) -> tuple[float | None, float | None]:
    extent = drawing.find(f".//{_WP_NS}extent")
    if extent is None:
        return None, None
    try:
        cx = float(extent.get("cx") or 0)
        cy = float(extent.get("cy") or 0)
    except ValueError:
        return None, None
    if cx <= 0 or cy <= 0:
        return None, None
    return cx / _EMU_PER_PT, cy / _EMU_PER_PT


def _fit_image_size(width_pt: float | None, height_pt: float | None) -> tuple[float | None, float | None]:
    if not width_pt or not height_pt:
        return width_pt, height_pt
    if width_pt <= _MAX_IMAGE_WIDTH_PT:
        return width_pt, height_pt
    scale = _MAX_IMAGE_WIDTH_PT / width_pt
    return _MAX_IMAGE_WIDTH_PT, height_pt * scale


def _image_block(
    zf: zipfile.ZipFile,
    rel_id: str,
    image_rels: dict[str, str],
    drawing: Element | None = None,
) -> dict | None:
    member = image_rels.get(rel_id or "")
    if not member:
        return None
    mime = _mime_for(member)
    if not mime:
        return None
    try:
        info = zf.getinfo(member)
    except KeyError:
        return None
    if info.file_size > MAX_NARRATIVE_IMAGE_BYTES:
        return None
    data = zf.read(member)
    if not data or len(data) > MAX_NARRATIVE_IMAGE_BYTES:
        return None
    width_pt, height_pt = _extent_pt(drawing) if drawing is not None else (None, None)
    width_pt, height_pt = _fit_image_size(width_pt, height_pt)
    src = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    return {
        "kind": "image",
        "src": src,
        "mime": mime,
        "width_pt": width_pt,
        "height_pt": height_pt,
        "text": "",
        "runs": [],
        "bullet": False,
        "role": "",
    }


def _blip_rel_id(blip: Element) -> str:
    for key, val in blip.attrib.items():
        if key == "embed" or key.endswith("}embed"):
            return (val or "").strip()
    return ""


def _images_in(
    p_el: Element,
    zf: zipfile.ZipFile | None,
    image_rels: dict[str, str],
) -> list[dict]:
    if zf is None or not image_rels:
        return []
    seen: set[str] = set()
    images: list[dict] = []
    drawings = list(p_el.iter(f"{_W_NS}drawing"))
    for drawing in drawings:
        for blip in drawing.iter():
            tag = blip.tag or ""
            if not (tag.endswith("}blip") or tag == "blip"):
                continue
            rel_id = _blip_rel_id(blip)
            if not rel_id or rel_id in seen:
                continue
            block = _image_block(zf, rel_id, image_rels, drawing)
            if block:
                seen.add(rel_id)
                images.append(block)
                if len(images) >= MAX_NARRATIVE_IMAGES:
                    return images
    for el in p_el.iter():
        tag = el.tag or ""
        if not (tag.endswith("}blip") or tag == "blip"):
            continue
        rel_id = _blip_rel_id(el)
        if not rel_id or rel_id in seen:
            continue
        block = _image_block(zf, rel_id, image_rels)
        if block:
            seen.add(rel_id)
            images.append(block)
            if len(images) >= MAX_NARRATIVE_IMAGES:
                return images
    for imagedata in p_el.iter(f"{_V_NS}imagedata"):
        rel_id = imagedata.get(f"{_R_NS}id") or imagedata.get("id") or ""
        if not rel_id or rel_id in seen:
            continue
        block = _image_block(zf, rel_id, image_rels)
        if block:
            seen.add(rel_id)
            images.append(block)
            if len(images) >= MAX_NARRATIVE_IMAGES:
                return images
    return images


def _parse_word_para(
    p_el,
    hrefs: dict[str, str],
    w_ns: str,
    r_ns: str,
    *,
    zf: zipfile.ZipFile | None = None,
    image_rels: dict[str, str] | None = None,
    para_italic_styles: dict[str, bool] | None = None,
    para_bold_styles: dict[str, bool] | None = None,
    char_italic: dict[str, bool] | None = None,
    char_bold: dict[str, bool] | None = None,
) -> list[dict]:
    ppr = p_el.find(f"{w_ns}pPr")
    bullet = ppr is not None and ppr.find(f"{w_ns}numPr") is not None
    word_style = _p_style(ppr)
    p_rpr = ppr.find(f"{w_ns}rPr") if ppr is not None else None
    para_italic = bool(
        _first_defined(
            _toggle_or_none(p_rpr, f"{w_ns}i"),
            _toggle_or_none(p_rpr, f"{w_ns}iCs"),
            (para_italic_styles or {}).get(word_style),
        )
    )
    para_bold = bool(
        _first_defined(
            _toggle_or_none(p_rpr, f"{w_ns}b"),
            _toggle_or_none(p_rpr, f"{w_ns}bCs"),
            (para_bold_styles or {}).get(word_style),
        )
    )
    align = _p_align(ppr)
    size_pt = _sz_pt(p_rpr)
    blocks = _images_in(p_el, zf, image_rels or {})
    runs: list[dict] = []
    for child in list(p_el):
        if child.tag == f"{w_ns}hyperlink":
            href = hrefs.get(child.get(f"{r_ns}id") or "", "")
            for r_el in child.iter(f"{w_ns}r"):
                text = "".join((t.text or "") for t in r_el.iter(f"{w_ns}t"))
                if not text:
                    continue
                bold, italic = _run_marks(
                    r_el,
                    para_bold=para_bold,
                    para_italic=para_italic,
                    char_italic=char_italic,
                    char_bold=char_bold,
                )
                if size_pt is None:
                    size_pt = _sz_pt(r_el.find(f"{w_ns}rPr"))
                runs.append({"text": text, "href": href, "bold": bold, "italic": italic})
        elif child.tag == f"{w_ns}r":
            text = "".join((t.text or "") for t in child.iter(f"{w_ns}t"))
            if not text:
                continue
            bold, italic = _run_marks(
                child,
                para_bold=para_bold,
                para_italic=para_italic,
                char_italic=char_italic,
                char_bold=char_bold,
            )
            if size_pt is None:
                size_pt = _sz_pt(child.find(f"{w_ns}rPr"))
            runs.append({"text": text, "href": "", "bold": bold, "italic": italic})
    text = "".join(run["text"] for run in runs).strip()
    if text:
        role = "caption" if word_style.lower().startswith("caption") else ""
        para = {
            "text": text,
            "runs": runs,
            "bullet": bullet,
            "role": role,
            "word_style": word_style,
        }
        if align:
            para["align"] = align
        if size_pt:
            para["size_pt"] = size_pt
        blocks.append(para)
    elif not blocks:
        blocks.append({"text": "", "runs": [], "bullet": False, "role": "empty"})
    return blocks


def _parse_word_table(
    tbl,
    hrefs: dict[str, str],
    w_ns: str,
    r_ns: str,
    *,
    zf: zipfile.ZipFile | None = None,
    image_rels: dict[str, str] | None = None,
    italic_styles: dict[str, bool] | None = None,
    bold_styles: dict[str, bool] | None = None,
) -> dict | None:
    rows: list[list[list[dict]]] = []
    for tr in tbl.findall(f"{w_ns}tr"):
        row: list[list[dict]] = []
        for tc in tr.findall(f"{w_ns}tc"):
            cell: list[dict] = []
            for p_el in tc.findall(f"{w_ns}p"):
                for parsed in _parse_word_para(
                    p_el,
                    hrefs,
                    w_ns,
                    r_ns,
                    zf=zf,
                    image_rels=image_rels,
                    para_italic_styles=italic_styles,
                    para_bold_styles=bold_styles,
                    char_italic=italic_styles,
                    char_bold=bold_styles,
                ):
                    if parsed.get("kind") == "image":
                        continue
                    if parsed.get("role") != "empty":
                        cell.append(parsed)
            row.append(cell)
        if any(row):
            rows.append(row)
    if not rows:
        return None
    return {"kind": "table", "rows": rows, "text": "", "runs": [], "bullet": False, "role": ""}


def _walk_word_blocks(
    el,
    hrefs: dict[str, str],
    w_ns: str,
    r_ns: str,
    out: list[dict],
    *,
    zf: zipfile.ZipFile | None = None,
    image_rels: dict[str, str] | None = None,
    italic_styles: dict[str, bool] | None = None,
    bold_styles: dict[str, bool] | None = None,
) -> None:
    if el.tag == f"{w_ns}tbl":
        table = _parse_word_table(
            tbl=el,
            hrefs=hrefs,
            w_ns=w_ns,
            r_ns=r_ns,
            zf=zf,
            image_rels=image_rels,
            italic_styles=italic_styles,
            bold_styles=bold_styles,
        )
        if table:
            out.append(table)
        return
    if el.tag == f"{w_ns}p":
        out.extend(
            _parse_word_para(
                el,
                hrefs,
                w_ns,
                r_ns,
                zf=zf,
                image_rels=image_rels,
                para_italic_styles=italic_styles,
                para_bold_styles=bold_styles,
                char_italic=italic_styles,
                char_bold=bold_styles,
            )
        )
        return
    for child in list(el):
        _walk_word_blocks(
            child,
            hrefs,
            w_ns,
            r_ns,
            out,
            zf=zf,
            image_rels=image_rels,
            italic_styles=italic_styles,
            bold_styles=bold_styles,
        )


def _parse_rels(rels_root) -> tuple[dict[str, str], dict[str, str]]:
    hrefs: dict[str, str] = {}
    image_rels: dict[str, str] = {}
    for rel in rels_root:
        rel_id = rel.get("Id") or ""
        rel_type = (rel.get("Type") or "").lower()
        target = rel.get("Target") or ""
        mode = (rel.get("TargetMode") or "").lower()
        if not rel_id:
            continue
        if "hyperlink" in rel_type:
            hrefs[rel_id] = safe_export_href(target)
        elif "image" in rel_type and mode != "external":
            member = _media_member(target)
            if member:
                image_rels[rel_id] = member
    return hrefs, image_rels


def load_word_paragraphs(docx_bytes: bytes) -> list[dict]:
    try:
        from defusedxml.ElementTree import fromstring as xml_fromstring
    except ImportError:  # pragma: no cover - production pins defusedxml
        from xml.etree.ElementTree import fromstring as xml_fromstring
    from xml.etree.ElementTree import ParseError

    from plugins.upr.idml import read_docx_xml_member

    w_ns = _W_NS
    r_ns = _R_NS
    blocks: list[dict] = []
    try:
        with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
            try:
                rels_root = xml_fromstring(read_docx_xml_member(zf, "word/_rels/document.xml.rels"))
            except KeyError:
                hrefs, image_rels = {}, {}
            else:
                hrefs, image_rels = _parse_rels(rels_root)
            try:
                styles_root = xml_fromstring(read_docx_xml_member(zf, "word/styles.xml"))
            except KeyError:
                styles_root = None
            italic_styles, bold_styles = _style_mark_maps(styles_root)
            root = xml_fromstring(read_docx_xml_member(zf, "word/document.xml"))
            body = root.find(f"{w_ns}body")
            if body is not None:
                for child in list(body):
                    _walk_word_blocks(
                        child,
                        hrefs,
                        w_ns,
                        r_ns,
                        blocks,
                        zf=zf,
                        image_rels=image_rels,
                        italic_styles=italic_styles,
                        bold_styles=bold_styles,
                    )
                    if len(blocks) > MAX_NARRATIVE_BLOCKS:
                        raise UprError("The Word document has too many paragraphs.")
                    if sum(1 for row in blocks if row.get("kind") == "image") > MAX_NARRATIVE_IMAGES:
                        raise UprError("The Word document has too many images.")
    except UprError:
        raise
    except (ParseError, zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise UprError("Upload a Word document (.docx).") from exc
    return blocks


def load_narrative_paragraphs(data: bytes) -> list[dict]:
    """Read a Word or PDF narrative into the same paragraph/table dicts."""
    if data.startswith(b"%PDF"):
        from plugins.upr.idml.pdf_reader import load_pdf_paragraphs

        return load_pdf_paragraphs(data)
    return load_word_paragraphs(data)
