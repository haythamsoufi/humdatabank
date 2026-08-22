"""PyMuPDF-based SVG/PNG extraction from the combined WeasyPrint PDF."""

from __future__ import annotations

import re
from pathlib import Path

from plugins.upr_visuals.idml.constants import (
    A4_H,
    FOLLOW_MARGIN,
    FOOTER_TOP,
    HEADING_PREFIXES,
    MIN_CROP,
    PNG_DPI,
)


def _lines(page) -> list[dict]:
    rows: list[dict] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            size = line["spans"][0].get("size") if line.get("spans") else 11
            rows.append({"text": text, "x": x0, "y": y0, "x1": x1, "y1": y1, "size": float(size or 11)})
    rows.sort(key=lambda r: (r["y"], r["x"]))
    return rows


def _is_heading(text: str) -> bool:
    upper = text.upper()
    return any(upper.startswith(prefix) for prefix in HEADING_PREFIXES)


def _is_native_extra(text: str) -> bool:
    low = text.lower()
    if low.startswith("in swiss francs"):
        return True
    if text.startswith("MDR") and " / " in text:
        return True
    return False


def _save_clip(page, rect, path: Path) -> tuple[float, float]:
    import fitz

    matrix = fitz.Matrix(PNG_DPI / 72.0, PNG_DPI / 72.0)
    pix = page.get_pixmap(matrix=matrix, clip=rect, alpha=False)
    pix.save(str(path))
    return float(pix.width), float(pix.height)


def _rgba_png_bytes(doc, xref: int, smask: int) -> bytes | None:
    import fitz

    pix = fitz.Pixmap(doc, xref)
    mask = fitz.Pixmap(doc, smask)
    try:
        pix = fitz.Pixmap(pix, mask)
    except Exception:
        return None
    if pix.colorspace and pix.colorspace.n == 4:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    return pix.tobytes("png")


def _masked_icon_pngs(doc) -> dict[int, bytes]:
    icons: dict[int, bytes] = {}
    for page in doc:
        for img in page.get_images(full=True):
            xref, smask = img[0], img[1]
            if not smask or xref in icons:
                continue
            png = _rgba_png_bytes(doc, xref, smask)
            if png:
                icons[xref] = png
    return icons


def _png_wh(png: bytes) -> tuple[int, int]:
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


def _fix_svg_icon_alpha(svg: str, icons: dict[int, bytes]) -> str:
    """MuPDF writes icon SMasks as black squares. Swap those images for RGBA PNGs."""
    import base64
    from collections import defaultdict, deque

    by_size: dict[tuple[int, int], deque[bytes]] = defaultdict(deque)
    for png in icons.values():
        by_size[_png_wh(png)].append(png)

    def repl(match: re.Match[str]) -> str:
        prefix, href = match.group(1), match.group(2)
        try:
            raw = base64.b64decode(href.split(",", 1)[-1])
        except Exception:
            return match.group(0)
        if len(raw) < 26 or raw[25] == 6:
            return match.group(0)
        width, height = _png_wh(raw)
        queue = by_size.get((width, height))
        if not queue:
            return match.group(0)
        png = queue[0]
        queue.rotate(-1)
        return prefix + "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    return re.sub(
        r'(<image\b[^>]*?(?:xlink:)?href=")(data:image/png;base64,[^"]+)',
        repl,
        svg,
        flags=re.DOTALL,
    )


def _ensure_payload(payload: dict) -> dict:
    return payload


def _visual_dashboard_ids(payload: dict) -> list[str]:
    kind = (payload.get("meta") or {}).get("kind") or "report"
    if kind == "plan":
        return ["in_support", "reach", "financial", "network_funding", "support"]
    ids = ["in_support", "reach", "financial"]
    for emergency in payload.get("emergencies") or []:
        ids.append(f"emergency_{int(emergency['slot'])}")
    if payload.get("core_indicators"):
        ids.append("strategic_priorities")
    if payload.get("enabling_indicators"):
        ids.append("enabling_functions")
    ids.append("support")
    return ids


def _usable_icon_src(src: str) -> bool:
    raw = (src or "").strip()
    return raw.startswith(("data:", "file:")) or (raw.startswith("/") and Path(raw).is_file())


def _hydrate_reach_icons(payload: dict, pdf_doc) -> None:
    """Combined PDF has the catalog SPEF icons; isolated HTML often lost them."""
    import base64
    import fitz

    rows = payload.get("people_reached") or []
    if not rows or all(_usable_icon_src(str(row.get("icon_src") or "")) for row in rows):
        return
    for page in pdf_doc:
        heading = next(
            (
                row
                for row in _lines(page)
                if row["text"].upper().startswith("PEOPLE REACHED")
                or row["text"].upper().startswith("PEOPLE TO BE REACHED")
            ),
            None,
        )
        if heading is None:
            continue
        bottom = FOOTER_TOP
        for row in _lines(page):
            if row["y"] > heading["y1"] + 8 and _is_heading(row["text"]):
                bottom = row["y"]
                break
        stolen: list[tuple[float, bytes]] = []
        for img in page.get_images(full=True):
            xref, smask = img[0], img[1]
            for rect in page.get_image_rects(xref):
                if rect.y0 < heading["y"] - 4 or rect.y1 > bottom + 4:
                    continue
                if rect.width < 12 or rect.width > 90 or rect.height < 12 or rect.height > 90:
                    continue
                png = _rgba_png_bytes(pdf_doc, xref, smask) if smask else fitz.Pixmap(pdf_doc, xref).tobytes("png")
                if png:
                    stolen.append((float(rect.x0), png))
        stolen.sort(key=lambda item: item[0])
        for row, (_x, png) in zip(rows, stolen):
            row["icon_src"] = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        return


def _section_htmls(payload: dict) -> list[tuple[str, str]]:
    from plugins.upr_visuals import render as R

    wrap = R._combined_section_wrap
    kind = (payload.get("meta") or {}).get("kind") or "report"
    sections = [
        ("in_support", wrap(R._in_support(payload))),
        ("reach", wrap(R._reach(payload))),
    ]
    if kind == "plan":
        sections += [
            ("financial", wrap(R._plan_funding(payload))),
            ("network_funding", wrap(R._network_funding(payload))),
            ("support", wrap(R._support(payload))),
        ]
        return sections
    sections.append(("financial", wrap(R._financial(payload))))
    heading = (
        "<h2 class='upr-block__title upr-block__title--center "
        "upr-combined-heading'>ONGOING EMERGENCY INDICATORS</h2>"
    )
    for index, emergency in enumerate(payload.get("emergencies") or []):
        block = R._emergency(payload, int(emergency["slot"]))
        name = f"emergency_{int(emergency['slot'])}"
        sections.append((name, wrap(heading + block if index == 0 else block)))
    if payload.get("core_indicators"):
        sections.append(("strategic_priorities", wrap(R._strategic_priorities(payload))))
    if payload.get("enabling_indicators"):
        sections.append(("enabling_functions", wrap(R._enabling_functions(payload))))
    sections.append(("support", wrap(R._support(payload))))
    return sections


def _tight_clip(page, *, full_width: bool = False):
    """Trim to ink (text/icons). Ignore tall empty section boxes WeasyPrint leaves behind."""
    import fitz
    from plugins.upr_visuals.raster import _is_page_backdrop

    clip = fitz.Rect()
    for block in page.get_text("blocks"):
        clip |= fitz.Rect(block[:4])
    for info in page.get_image_info():
        clip |= fitz.Rect(info["bbox"])
    if clip.is_empty:
        return page.rect
    limit = clip.y1 + 10.0
    try:
        drawings = page.get_drawings()
    except Exception:
        drawings = []
    for drawing in drawings:
        rect = drawing.get("rect")
        if not rect or _is_page_backdrop(drawing, page.rect):
            continue
        box = fitz.Rect(rect)
        if box.y0 > limit or box.y1 < clip.y0 - 4.0:
            continue
        box.y1 = min(box.y1, limit)
        clip |= box
    if full_width:
        clip.x0 = page.rect.x0
        clip.x1 = page.rect.x1
    else:
        clip.x0 = max(page.rect.x0, clip.x0 - 3.0)
        clip.x1 = min(page.rect.x1, clip.x1 + 3.0)
    clip.y0 = max(page.rect.y0, clip.y0 - 3.0)
    clip.y1 = min(page.rect.y1, clip.y1 + 3.0)
    return clip


def _write_isolated_svg(pdf_bytes: bytes, dest: Path, *, full_width: bool = False) -> list[tuple[str, float, float]]:
    """One complete visual → SVG. Keep A4 width; trim empty paper above/below only."""
    import fitz

    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    icons = _masked_icon_pngs(src)
    exported: list[tuple[str, float, float]] = []
    try:
        for index, page in enumerate(src):
            clip = _tight_clip(page, full_width=full_width)
            tmp = fitz.open()
            try:
                new_page = tmp.new_page(width=float(clip.width), height=float(clip.height))
                new_page.show_pdf_page(new_page.rect, src, index, clip=clip)
                svg = _fix_svg_icon_alpha(new_page.get_svg_image(), icons)
            finally:
                tmp.close()
            path = dest if src.page_count == 1 else dest.with_name(f"{dest.stem}-{index + 1}{dest.suffix}")
            path.write_text(svg, encoding="utf-8")
            exported.append((path.name, float(clip.width), float(clip.height)))
    finally:
        src.close()
    return exported


def _svg_wh(path: Path) -> tuple[float, float]:
    head = path.read_text(encoding="utf-8", errors="replace")[:1500]
    match = re.search(r'width="([\d.]+)"[^>]*height="([\d.]+)"', head)
    if not match:
        return 0.0, 0.0
    return float(match.group(1)), float(match.group(2))


_FLOW_IDS = {"strategic_priorities", "enabling_functions", "support"}


def export_visual_svgs(payload: dict, links: Path) -> list[tuple[str, str, float, float]]:
    from plugins.upr_visuals.raster import render_pdf_bytes

    for stale in links.glob("*.svg"):
        stale.unlink()
    exported: list[tuple[str, str, float, float]] = []
    standalone: list[tuple[str, str]] = []
    flow_html: list[str] = []
    for dashboard_id, section_html in _section_htmls(payload):
        if dashboard_id in _FLOW_IDS:
            flow_html.append(section_html)
        else:
            standalone.append((dashboard_id, section_html))

    for dashboard_id, section_html in standalone:
        dest = links / f"{dashboard_id}.svg"
        extra = ""
        if dashboard_id == "reach":
            extra = (
                "<style>"
                ".upr-block--reach,.upr-combined-section > .upr-block--reach{"
                "margin-left:0;margin-right:0;width:100%;max-width:none;"
                "padding:1.15rem 10mm 1.35rem;}"
                "</style>"
            )
        html = extra + f'<div class="upr-dashboard upr-dashboard--combined">{section_html}</div>'
        pdf_bytes = render_pdf_bytes(html, dashboard_id="combined")
        for name, width, height in _write_isolated_svg(pdf_bytes, dest, full_width=dashboard_id == "reach"):
            exported.append((dashboard_id, name, width, height))

    if flow_html:
        html = f'<div class="upr-dashboard upr-dashboard--combined">{"".join(flow_html)}</div>'
        pdf_bytes = render_pdf_bytes(html, dashboard_id="combined")
        for name, width, height in _write_isolated_svg(pdf_bytes, links / "indicators.svg"):
            exported.append(("indicators", name, width, height))
    return exported


def _heading_key(text: str) -> str:
    upper = text.upper()
    if upper.startswith("IN SUPPORT"):
        return "in_support"
    if upper.startswith("PEOPLE REACHED") or upper.startswith("PEOPLE TO BE"):
        return "reach"
    if upper.startswith("FINANCIAL"):
        return "financial"
    if upper.startswith("ONGOING EMERGENCY"):
        return "emergency_1"
    if upper.startswith("STRATEGIC"):
        return "strategic_priorities"
    if upper.startswith("ENABLING"):
        return "enabling_functions"
    if upper.startswith("IFRC NETWORK"):
        return "support"
    if upper.startswith("NETWORK FUNDING") or upper.startswith("FUNDING FROM"):
        return "network_funding"
    return ""


def _section_bands(pdf_doc) -> dict[str, tuple[int, float, float]]:
    """Page + [y0, y1) for each visual, from the combined WeasyPrint PDF."""
    heads: list[tuple[int, float, str]] = []
    for index, page in enumerate(pdf_doc):
        for row in _lines(page):
            if not _is_heading(row["text"]):
                continue
            key = _heading_key(row["text"])
            if key and key not in {item[2] for item in heads}:
                heads.append((index, float(row["y"]), key))
    bands: dict[str, tuple[int, float, float]] = {}
    for i, (page_i, y0, key) in enumerate(heads):
        if i + 1 < len(heads) and heads[i + 1][0] == page_i:
            y1 = heads[i + 1][1]
        elif page_i == 0:
            y1 = FOOTER_TOP - 4.0
        else:
            y1 = A4_H - FOLLOW_MARGIN
        if y1 > y0 + MIN_CROP:
            bands[key] = (page_i, y0, y1)
    return bands
