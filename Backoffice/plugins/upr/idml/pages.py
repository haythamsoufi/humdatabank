"""Cover chrome and native visual-page composition."""

from __future__ import annotations

from pathlib import Path

from plugins.upr.idml.constants import (
    A4_W,
    FOLLOW_MARGIN,
    FOLIO_Y,
    FOOTER_TOP,
    HEADER_H,
    LOGO,
    LOGO_PAD,
    LOGO_Y,
    NS_LOGO_INSET,
    NARRATIVE_H,
    NARRATIVE_W,
    NARRATIVE_X,
    NARRATIVE_Y,
    _COVER_LAYOUT,
)
from plugins.upr.idml.narrative_style import _narrative_page_count, folio_label, folio_runs
from plugins.upr.idml.pdf_extract import (
    _ensure_payload,
    _hydrate_reach_icons,
    _lines,
    _save_clip,
    export_visual_svgs,
)
from plugins.upr.idml.xml_idml import Idml


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


def _mirror_x(x: float, w: float) -> float:
    return A4_W - x - w


def build_cover_chrome(
    doc: Idml,
    meta: dict,
    logos: dict[str, tuple[str, float, float]],
    footer: dict[str, dict] | None = None,
) -> list[str]:
    from plugins.upr.audience import INTERNAL_COVER_BANNER, INTERNAL_COVER_BANNER_H, is_internal_narrative
    from plugins.upr.formatters import appeal_number
    from plugins.upr.i18n import localized_country_header, t
    from plugins.upr.render import COVER_FOOTER_NOTE, COVER_FOOTER_ORG

    country = localized_country_header(meta)
    subtitle = (meta.get("document_subtitle") or "").strip()
    prefix = (meta.get("header_prefix") or t("IN SUPPORT OF")).strip()
    ns = (meta.get("national_society") or "").strip()
    appeal = appeal_number(meta.get("iso2") or meta.get("appeal_iso2"))
    footer = footer or {}
    L = _COVER_LAYOUT
    rtl = bool(getattr(doc, "rtl", False))
    start_align = "RightAlign" if rtl else "LeftAlign"
    title_x = _mirror_x(L["title_x"], L["title_w"]) if rtl else L["title_x"]
    rule_x = _mirror_x(L["rule_x"], L["rule_w"]) if rtl else L["rule_x"]
    banner_h = INTERNAL_COVER_BANNER_H if is_internal_narrative(meta) else 0.0
    logo_y = LOGO_Y + banner_h

    items = [
        doc.rect(0, 0, A4_W, HEADER_H + banner_h, "Color/IFRCNavy"),
    ]
    if banner_h:
        items += [
            doc.rect(0, 0, A4_W, banner_h, "Color/InternalGold"),
            _label(
                doc,
                t(INTERNAL_COVER_BANNER),
                x=0.0,
                y=2.0,
                w=A4_W,
                h=banner_h - 3.0,
                size="9",
                color="Color/IFRCNavy",
                align="CenterAlign",
                valign="CenterAlign",
            ),
        ]
    items += [
        doc.rect(rule_x, L["rule_y"] + banner_h, L["rule_w"], L["rule_h"], "Color/IFRCRed"),
        _label(
            doc,
            country,
            x=title_x,
            y=L["title_y"] + banner_h,
            w=L["title_w"],
            h=L["title_h"],
            size="38",
            color="Color/Paper",
            align=start_align,
        ),
        _label(
            doc,
            subtitle,
            x=title_x,
            y=L["subtitle_y"] + banner_h,
            w=L["title_w"],
            h=L["subtitle_h"],
            size="12",
            color="Color/Paper",
            style="Regular",
            align=start_align,
        ),
    ]
    ifrc = logos.get("ifrc")
    ifrc_x = A4_W - LOGO_PAD - LOGO if rtl else LOGO_PAD
    if ifrc:
        items.append(doc.image_frame(ifrc_x, logo_y, LOGO, LOGO, ifrc[0], ifrc[1], ifrc[2]))
    ns_logo = logos.get("ns")
    ns_x = LOGO_PAD if rtl else A4_W - LOGO_PAD - LOGO
    if ns_logo:
        items.append(doc.rect(ns_x, logo_y, LOGO, LOGO, "Color/Paper"))
        inset = NS_LOGO_INSET
        items.append(
            doc.image_frame(
                ns_x + inset,
                logo_y + inset,
                LOGO - 2 * inset,
                LOGO - 2 * inset,
                ns_logo[0],
                ns_logo[1],
                ns_logo[2],
            )
        )

    pad_x = L["pad_x"]
    box_y = L["box_y"]
    if appeal:
        appeal_text = f"{t('Appeal number')}  {appeal}"
        appeal_x = A4_W - pad_x - L["appeal_w"] if rtl else pad_x
        items.append(
            _label(
                doc,
                appeal_text,
                x=appeal_x,
                y=box_y,
                w=L["appeal_w"],
                h=L["appeal_h"],
                size="8",
                color="Color/AppealPink",
                style="Regular",
                align=start_align,
                valign="CenterAlign",
                inset=(0.0, 7.0, 0.0, 7.0),
                stroke="Color/IFRCRed",
                weight="0.75",
            )
        )
    note_text = f"*{t(COVER_FOOTER_NOTE)}"
    note_w, note_h = L["note_w"], L["note_h"]
    note_x = pad_x if rtl else A4_W - pad_x - note_w
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
            t(COVER_FOOTER_ORG),
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
            folio_runs(folio, page_number),
            align="CenterAlign",
        ),
    )


def build_native_pages(doc: Idml, pdf_doc, payload: dict, links: Path, pdf_name: str = "") -> int:
    import fitz

    payload = _ensure_payload(payload)
    _hydrate_reach_icons(payload, pdf_doc)
    meta = payload.get("meta") or {}
    svgs = export_visual_svgs(payload, links)
    from plugins.upr.audience import INTERNAL_COVER_BANNER_H, is_internal_narrative

    banner_h = INTERNAL_COVER_BANNER_H if is_internal_narrative(meta) else 0.0
    logo_y = LOGO_Y + banner_h

    logos: dict[str, tuple[str, float, float]] = {}
    first = pdf_doc[0]
    rtl = bool(getattr(doc, "rtl", False))
    ifrc_box = (
        fitz.Rect(A4_W - LOGO_PAD - LOGO, logo_y, A4_W - LOGO_PAD, logo_y + LOGO)
        if rtl
        else fitz.Rect(LOGO_PAD, logo_y, LOGO_PAD + LOGO, logo_y + LOGO)
    )
    ns_box = (
        fitz.Rect(LOGO_PAD, logo_y, LOGO_PAD + LOGO, logo_y + LOGO)
        if rtl
        else fitz.Rect(A4_W - LOGO_PAD - LOGO, logo_y, A4_W - LOGO_PAD, logo_y + LOGO)
    )
    for key, box in (
        ("ifrc", ifrc_box),
        ("ns", ns_box),
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

    last_page, last_bottom = 0, HEADER_H + banner_h + 6.0
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
