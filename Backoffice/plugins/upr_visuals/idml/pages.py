"""Cover chrome and native visual-page composition."""

from __future__ import annotations

from pathlib import Path

from plugins.upr_visuals.idml.constants import (
    A4_W,
    FOLLOW_MARGIN,
    FOLIO_Y,
    FOOTER_TOP,
    HEADER_H,
    LOGO,
    LOGO_PAD,
    LOGO_Y,
    NARRATIVE_H,
    NARRATIVE_W,
    NARRATIVE_X,
    NARRATIVE_Y,
    _COVER_LAYOUT,
)
from plugins.upr_visuals.idml.narrative_style import _narrative_page_count, folio_label, folio_text
from plugins.upr_visuals.idml.pdf_extract import (
    _ensure_payload,
    _hydrate_reach_icons,
    _lines,
    _save_clip,
    export_visual_svgs,
)
from plugins.upr_visuals.idml.xml_idml import Idml


def _measure_footer(page) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for row in _lines(page):
        low = row["text"].lower()
        if low.startswith("appeal number"):
            found["appeal"] = row
        elif "information on data scope" in low:
            found["note"] = row
        elif low.startswith("international federation of red"):
            found["org"] = row
    return found


def _label(
    doc: Idml,
    text: str,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    size: str,
    color: str,
    style: str = "Bold",
    align: str = "CenterAlign",
    valign: str = "TopAlign",
    inset: float | tuple[float, float, float, float] = 0.0,
    fill: str = "Swatch/None",
    stroke: str = "Swatch/None",
    weight: str = "0",
    radius: float = 0,
) -> str:
    return doc.text_frame(
        x,
        y,
        w,
        h,
        doc.story([{"text": text, "style": style, "size": size, "color": color}], align=align),
        valign=valign,
        inset=inset,
        fill=fill,
        stroke=stroke,
        weight=weight,
        radius=radius,
    )


def build_cover_chrome(
    doc: Idml,
    meta: dict,
    logos: dict[str, tuple[str, float, float]],
    footer: dict[str, dict] | None = None,
) -> list[str]:
    from plugins.upr_visuals.formatters import appeal_number
    from plugins.upr_visuals.render import COVER_FOOTER_NOTE, COVER_FOOTER_ORG

    country = (meta.get("country_name") or "").strip().upper()
    subtitle = (meta.get("document_subtitle") or "").strip()
    date_text = (meta.get("header_date") or "").strip()
    prefix = (meta.get("header_prefix") or "IN SUPPORT OF").strip()
    ns = (meta.get("national_society") or "").strip()
    appeal = appeal_number(meta.get("iso2") or meta.get("appeal_iso2"))
    footer = footer or {}
    L = _COVER_LAYOUT

    items = [
        doc.rect(0, 0, A4_W, HEADER_H, "Color/IFRCNavy"),
        doc.rect(L["rule_x"], L["rule_y"], L["rule_w"], L["rule_h"], "Color/IFRCRed"),
        _label(
            doc,
            country,
            x=L["title_x"],
            y=L["title_y"],
            w=L["title_w"],
            h=L["title_h"],
            size="38",
            color="Color/Paper",
            align="LeftAlign",
        ),
        _label(
            doc,
            subtitle,
            x=L["title_x"],
            y=L["subtitle_y"],
            w=L["title_w"],
            h=L["subtitle_h"],
            size="12",
            color="Color/Paper",
            style="Regular",
            align="LeftAlign",
        ),
    ]
    ifrc = logos.get("ifrc")
    if ifrc:
        items.append(doc.image_frame(LOGO_PAD, LOGO_Y, LOGO, LOGO, ifrc[0], ifrc[1], ifrc[2]))
    ns_logo = logos.get("ns")
    ns_x = A4_W - LOGO_PAD - LOGO
    if ns_logo:
        items.append(doc.image_frame(ns_x, LOGO_Y, LOGO, LOGO, ns_logo[0], ns_logo[1], ns_logo[2]))
    if date_text:
        date_w = L["date_w"]
        date_x = A4_W - LOGO_PAD - date_w
        date_y = LOGO_Y + LOGO + 10.0 if ns_logo else L["date_y_no_logo"]
        items.append(
            _label(
                doc,
                date_text,
                x=date_x,
                y=date_y,
                w=date_w,
                h=L["date_h"],
                size="9",
                color="Color/Paper",
                style="Italic",
                align="RightAlign",
            )
        )

    pad_x = L["pad_x"]
    box_y = L["box_y"]
    if appeal:
        appeal_text = f"Appeal number  {appeal}"
        items.append(
            _label(
                doc,
                appeal_text,
                x=pad_x,
                y=box_y,
                w=L["appeal_w"],
                h=L["appeal_h"],
                size="8",
                color="Color/AppealPink",
                style="Regular",
                align="LeftAlign",
                valign="CenterAlign",
                inset=(0.0, 7.0, 0.0, 7.0),
                stroke="Color/IFRCRed",
                weight="0.75",
            )
        )
    note_text = f"*{COVER_FOOTER_NOTE}"
    note_w, note_h = L["note_w"], L["note_h"]
    note_x = A4_W - pad_x - note_w
    items += [
        _label(
            doc,
            note_text,
            x=note_x,
            y=box_y,
            w=note_w,
            h=note_h,
            size="7",
            color="Color/Paper",
            style="Regular",
            align="CenterAlign",
            valign="CenterAlign",
            inset=(0.0, 10.0, 0.0, 10.0),
            fill="Color/IFRCRed",
            radius=note_h / 2.0,
        ),
        _label(
            doc,
            COVER_FOOTER_ORG,
            x=pad_x,
            y=L["org_y"],
            w=A4_W - pad_x * 2,
            h=L["org_h"],
            size="7",
            color="Color/IFRCMuted",
            style="Regular",
            valign="CenterAlign",
        ),
    ]
    _ = (prefix, ns, footer)
    return items


def _folio_frame(doc: Idml, folio: str, page_number: int) -> str:
    return doc.text_frame(
        NARRATIVE_X,
        FOLIO_Y,
        NARRATIVE_W,
        14.0,
        doc.story(
            [
                {
                    "text": folio_text(folio, page_number),
                    "font": "Montserrat",
                    "style": "Regular",
                    "size": "8",
                    "color": "Color/Black",
                }
            ],
            align="CenterAlign",
        ),
    )


def build_native_pages(doc: Idml, pdf_doc, payload: dict, links: Path, pdf_name: str = "") -> int:
    import fitz

    payload = _ensure_payload(payload)
    _hydrate_reach_icons(payload, pdf_doc)
    meta = payload.get("meta") or {}
    svgs = export_visual_svgs(payload, links)

    logos: dict[str, tuple[str, float, float]] = {}
    first = pdf_doc[0]
    for key, box in (
        ("ifrc", fitz.Rect(LOGO_PAD, LOGO_Y, LOGO_PAD + LOGO, LOGO_Y + LOGO)),
        ("ns", fitz.Rect(A4_W - LOGO_PAD - LOGO, LOGO_Y, A4_W - LOGO_PAD, LOGO_Y + LOGO)),
    ):
        path = links / f"logo-{key}.png"
        w, h = _save_clip(first, box, path)
        logos[key] = (f"file:Links/{path.name}", w, h)

    margin = FOLLOW_MARGIN
    content_w = A4_W - margin * 2

    def page_bottom(page_i: int) -> float:
        if page_i == 0:
            return FOOTER_TOP - 8.0
        return FOLIO_Y - 8.0

    items_by_page: dict[int, list[str]] = {}
    items_by_page[0] = build_cover_chrome(doc, meta, logos, _measure_footer(first))

    last_page, last_bottom = 0, HEADER_H + 6.0
    cover_ids = {"in_support", "reach", "financial"}
    for dashboard_id, name, svg_w, svg_h in svgs:
        if svg_w <= 0 or svg_h <= 0:
            continue
        bleed = dashboard_id == "reach"
        frame_w = A4_W if bleed else content_w
        frame_h = svg_h * (frame_w / svg_w)
        cover = dashboard_id in cover_ids
        if cover and last_page == 0:
            page_i, y = 0, last_bottom
        else:
            page_i, y = last_page, last_bottom
            if page_i == 0:
                page_i, y = 1, margin
        bottom = page_bottom(page_i)
        if y + frame_h > bottom + 1:
            if cover and page_i == 0 and not bleed:
                scale = max(0.35, (bottom - y) / frame_h)
                frame_w, frame_h = frame_w * scale, frame_h * scale
            elif not cover or page_i != 0:
                page_i += 1
                y = margin
                bottom = page_bottom(page_i)
                if y + frame_h > bottom + 1:
                    scale = (bottom - y) / frame_h
                    frame_w, frame_h = frame_w * scale, frame_h * scale
        frame_x = 0.0 if bleed else margin + (content_w - frame_w) / 2.0
        items_by_page.setdefault(page_i, [])
        if bleed:
            items_by_page[page_i].append(doc.rect(0, y, A4_W, frame_h, "Color/ReachGrey"))
        items_by_page[page_i].append(
            doc.svg_frame(frame_x, y, frame_w, frame_h, f"file:Links/{name}", svg_w, svg_h)
        )
        last_page, last_bottom = page_i, y + frame_h + 8.0

    folio = folio_label(meta)
    for page_i in sorted(items_by_page):
        items = items_by_page[page_i]
        if page_i >= 1 and folio:
            items.append(_folio_frame(doc, folio, page_i + 1))
        if items:
            doc.add_page(items)
    _ = pdf_name
    return len(svgs)


def add_narrative_pages(doc: Idml, styled: list[dict], *, folio: str) -> int:
    if not styled:
        return 0

    story_id = doc.styled_story(styled)
    fids = [doc.uid() for _ in range(_narrative_page_count(styled))]
    for i, fid in enumerate(fids):
        prev = fids[i - 1] if i else "n"
        nxt = fids[i + 1] if i + 1 < len(fids) else "n"
        items = [
            doc.threaded_frame(NARRATIVE_X, NARRATIVE_Y, NARRATIVE_W, NARRATIVE_H, story_id, fid, previous=prev, nxt=nxt),
            _folio_frame(doc, folio, doc.page_count + 1),
        ]
        doc.add_page(items)
    return len(styled)
