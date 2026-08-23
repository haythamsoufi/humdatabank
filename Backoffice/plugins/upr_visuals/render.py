"""HTML dashboards matching UPR Visuals.twb layouts (bars, icons, support matrix)."""

from __future__ import annotations

from html import escape
from typing import Any

from plugins.upr_visuals.catalog import (
    AREA_COLORS,
    AREA_LABELS,
    DASHBOARD_BY_ID,
    EF_CODES,
    KPI_ORDER,
    PLAN_DETAIL_SP_LABELS,
    PLAN_KPI_ORDER,
    SP_CODES,
    SUPPORT_AREA_CODES,
    SUPPORT_AREA_HEADER_LINES,
    SUPPORT_DOT_COLORS,
    kpi_icon_src,
)
from plugins.upr_visuals.formatters import (
    appeal_number,
    chf_label,
    document_subtitle,
    format_compact_chf,
    format_header_date,
    split_display_amount,
    with_chf,
)
from plugins.upr_visuals.i18n import (
    arabic_font_class,
    current_export_language,
    is_rtl,
    localized_country_header,
    rtl_document_attrs,
    t,
)


def _export_dir_attrs() -> str:
    attrs = rtl_document_attrs()
    return f" lang='{escape(attrs['lang'])}' dir='{escape(attrs['dir'])}'"


def _export_font_class() -> str:
    extra = arabic_font_class()
    return f" {extra}" if extra else ""

IFRC_RED = "#d22730"
IFRC_LOGO_SRC = "/static/IFRC_logo_square.svg"


def _not_reported() -> str:
    return t("Not reported")


def _ltr_row(cells: list[str]) -> str:
    """Join cells for a ``dir=ltr`` table. RTL exports reverse here.

    Finance, support, and reach tables stay LTR in the DOM (WeasyPrint
    corrupts RTL tables). Indicator ``.upr-bars`` tables are the other
    strategy: they inherit ``direction: rtl`` from CSS and are not reversed.
    """
    if is_rtl():
        cells = list(reversed(cells))
    return "".join(cells)


_PLAN_REQ_BAR_CLASS = {
    "HNS": "upr-plan-req__bar--hns",
    "PNS": "upr-plan-req__bar--pns",
    "IFRC Secretariat": "upr-plan-req__bar--ifrc",
}
_PLAN_REQ_ARROW = (
    "<span class='upr-plan-req__arrow' aria-hidden='true'>"
    "<svg viewBox='0 0 8 10' width='8' height='10' focusable='false'>"
    "<path d='M1 1 L7 5 L1 9 Z' fill='#222'/></svg>"
    "</span>"
)
_PLAN_REQ_ORDER = ("HNS", "PNS", "IFRC Secretariat")


def _amount_html(text: str | None) -> str:
    """Render an amount; Arabic units are a separate LTR flex item left of digits."""
    raw = (text or "").strip()
    if not raw:
        return ""
    if raw.lower() == "not reported" or raw == _not_reported():
        return f'<span class="upr-not-reported">{escape(raw)}</span>'
    parts = split_display_amount(raw)
    if parts:
        unit, number = parts
        return (
            f'<span class="upr-amt" dir="ltr">'
            f'<span class="upr-amt__unit">{escape(unit)}</span> '
            f'<span class="upr-amt__num">{escape(number)}</span>'
            f"</span>"
        )
    return escape(raw)


def _metric_html(text: str | None, *, fallback: str | None = None) -> str:
    raw = (text or "").strip() or (fallback if fallback is not None else _not_reported())
    if raw.lower() == "not reported" or raw == _not_reported():
        return f'<span class="upr-not-reported">{escape(raw)}</span>'
    return _amount_html(raw) or escape(raw)

# Tableau Reach uses circular SP pictograms (FDRS IFRC icons).
_SP_ICON_PATHS = {
    "EO": '<path d="M5 18h14M7 18l2-8 3 4 2-6 3 10"/>',
    "CC1": '<circle cx="9" cy="12" r="5"/><circle cx="15" cy="12" r="5"/>',
    "SP1": '<path d="M12 20v-7M8 20h8"/><path d="M12 4l6 8H6z"/><path d="M10 9h4"/>',
    "SP2": '<path d="M5 18h14l-3-7H8z"/><path d="M12 4v4M9 7h6"/>',
    "SP3": '<circle cx="12" cy="12" r="8"/><path d="M12 8v8M8 12h8"/>',
    "SP4": '<circle cx="8" cy="10" r="2"/><path d="M4 18c.5-3 2-5 4-5s3.5 2 4 5"/><path d="M14 8h6l-2 4h-4z"/>',
    "SP5": '<circle cx="12" cy="8" r="3"/><path d="M6 19c1-3 3.5-5 6-5s5 2 6 5"/>',
}


def _kpi_icon(key: str) -> str:
    src = kpi_icon_src(key)
    if src:
        return (
            f'<span class="upr-kpi__icon upr-kpi__icon--img" aria-hidden="true">'
            f'<img src="{escape(src, quote=True)}" alt="">'
            f"</span>"
        )
    return (
        f'<svg class="upr-kpi__icon" viewBox="0 0 24 24" width="52" height="52" '
        f'aria-hidden="true" fill="none" stroke="{IFRC_RED}" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<circle cx="12" cy="12" r="8"/>'
        f"</svg>"
    )


def _sp_icon(code: str, icon_src: str | None = None) -> str:
    src = (icon_src or "").strip()
    if src:
        href = escape(src, quote=True)
        # Fixed SVG box so WeasyPrint cannot stretch the ring to the
        # table-cell width (that clips the circle into a crescent).
        return (
            f'<span class="upr-reach-icon upr-reach-icon--img" aria-hidden="true">'
            f'<svg viewBox="0 0 40 40" width="56" height="56">'
            f'<circle cx="20" cy="20" r="18" fill="#fff" stroke="#011e41" stroke-width="1.4"/>'
            f'<image href="{href}" x="4" y="4" width="32" height="32" '
            f'preserveAspectRatio="xMidYMid meet"/>'
            f"</svg></span>"
        )
    color = AREA_COLORS.get(code, IFRC_RED)
    inner = _SP_ICON_PATHS.get(code, f'<text x="12" y="16" text-anchor="middle" font-size="8">{escape(code)}</text>')
    return (
        f'<span class="upr-reach-icon" aria-hidden="true">'
        f'<svg viewBox="0 0 40 40" width="56" height="56">'
        f'<circle cx="20" cy="20" r="18" fill="#fff" stroke="#011e41" stroke-width="1.4"/>'
        f'<g transform="translate(4 4) scale(1.333)" fill="none" stroke="{color}" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round">{inner}</g></svg></span>'
    )


def render_dashboard_html(payload: dict[str, Any], dashboard_id: str) -> str:
    spec = DASHBOARD_BY_ID.get(dashboard_id)
    if spec is None:
        raise ValueError(f"Unknown dashboard: {dashboard_id}")
    if dashboard_id == "combined":
        body = _combined(payload)
    elif dashboard_id == "in_support":
        body = _in_support(payload)
    elif dashboard_id == "reach":
        body = _reach(payload)
    elif dashboard_id == "financial":
        body = _financial(payload)
    elif dashboard_id == "support":
        body = _support(payload)
    elif dashboard_id == "network_funding":
        body = _network_funding(payload)
    elif dashboard_id == "strategic_priorities":
        body = _strategic_priorities(payload)
    elif dashboard_id == "enabling_functions":
        body = _enabling_functions(payload)
    elif dashboard_id.startswith("emergency_"):
        slot = int(dashboard_id.rsplit("_", 1)[-1])
        body = _emergency(payload, slot)
    else:
        body = ""
    return (
        f'<div class="upr-dashboard upr-dashboard--{escape(dashboard_id)}'
        f'{_export_font_class()}"'
        f"{_export_dir_attrs()}>{body}</div>"
    )


def render_dashboards_html(payload: dict[str, Any], dashboard_ids: list[str] | None = None) -> dict[str, str]:
    ids = dashboard_ids or [str(d.get("id") or "") for d in payload.get("dashboards") or [] if d.get("id")]
    return {did: render_dashboard_html(payload, did) for did in ids}


def render_report_html(payload: dict[str, Any], dashboard_ids: list[str] | None = None) -> str:
    ids = dashboard_ids or [d["id"] for d in payload.get("dashboards") or [] if d.get("id") != "combined"]
    if "combined" in (dashboard_ids or []):
        ids = ["combined"]
    parts = [render_dashboard_html(payload, did) for did in ids]
    meta = payload.get("meta") or {}
    ns = escape(meta.get("national_society") or meta.get("country_name") or "")
    period = escape(meta.get("period_name") or "")
    return (
        f'<article class="upr-visual-report{_export_font_class()}" '
        f'data-aes-id="{escape(str(meta.get("aes_id") or ""))}"'
        f"{_export_dir_attrs()}>"
        f'<header class="upr-visual-report__toolbar">'
        f"<div><strong>{ns}</strong> · {period} · {escape(meta.get('round_code') or '')}</div>"
        f"</header>"
        f'<div class="upr-visual-report__body">{"".join(parts)}</div>'
        f"</article>"
    )


def _is_plan(payload: dict[str, Any]) -> bool:
    return (payload.get("meta") or {}).get("kind") == "plan"


def _combined(payload: dict[str, Any]) -> str:
    pieces: list[str] = []

    def add(part: str, *, page_start: bool = False) -> None:
        if part:
            pieces.append(_combined_section_wrap(part, page_start=page_start))

    if _is_plan(payload):
        for part in (
            _in_support(payload),
            _reach(payload),
            _plan_funding(payload),
            _network_funding(payload),
            _support(payload),
        ):
            add(part)
    else:
        add(_in_support(payload))
        add(_reach(payload))
        add(_financial(payload))
        emergencies = payload.get("emergencies") or []
        if emergencies:
            heading = (
                "<h2 class='upr-block__title upr-block__title--center "
                "upr-combined-heading'>" + escape(t("ONGOING EMERGENCY INDICATORS")) + "</h2>"
            )
            for index, em in enumerate(emergencies):
                block = _emergency(payload, int(em["slot"]))
                add(heading + block if index == 0 else block)
        add(_strategic_priorities(payload) if payload.get("core_indicators") else "", page_start=bool(emergencies))
        add(_enabling_functions(payload) if payload.get("enabling_indicators") else "")
        add(_support(payload))
    body = "".join(pieces)
    header = _doc_header(payload)
    footer = _doc_footer(payload)
    if not header:
        return f"{body}{footer}"
    return f"{header}{footer}<div class='upr-combined-body'>{body}</div>"


def _combined_section_wrap(part: str, *, page_start: bool = False) -> str:
    extra = ""
    if "upr-block--finance" in part:
        extra = " upr-combined-section--finance"
    elif "upr-block--plan-fund" in part or "upr-plan-detail-row" in part:
        extra = " upr-combined-section--plan-fund"
    elif "upr-block--network-funding" in part:
        extra = " upr-combined-section--network-funding"
    elif "upr-block--bars" in part:
        extra = " upr-combined-section--indicators"
    elif "upr-block--reach" in part:
        extra = " upr-combined-section--reach"
    elif "upr-kpi-row" in part:
        extra = " upr-combined-section--before-reach"
    if page_start:
        extra += " upr-combined-section--page-start"
    return f'<div class="upr-combined-section{extra}">{part}</div>'


def _in_support(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    ns = (meta.get("national_society") or "").strip()
    prefix = (meta.get("header_prefix") or t("In support of" if _is_plan(payload) else "IN SUPPORT OF")).strip()
    heading = f"{prefix} {ns}" if _is_plan(payload) else f"{prefix} {ns.upper()}"
    kpis = payload.get("kpis") or {}
    order = PLAN_KPI_ORDER if _is_plan(payload) else KPI_ORDER
    cards = []
    for key in order:
        kpi = kpis.get(key) or {}
        cards.append(
            "<div class='upr-kpi'>"
            f"{_kpi_icon(key)}"
            f"<div class='upr-kpi__label'>{escape(kpi.get('label') or key)}</div>"
            f"<div class='upr-kpi__value'>{_metric_html(kpi.get('display'))}</div>"
            "</div>"
        )
    return (
        "<section class='upr-block upr-block--support'>"
        f"<h2 class='upr-block__title'>{escape(heading.strip())}</h2>"
        f"<div class='upr-kpi-row'>{''.join(cards)}</div>"
        "</section>"
    )


def _reach(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    raw_title = meta.get("people_title") or t("People reached")
    title = escape(raw_title if _is_plan(payload) else raw_title.upper())
    rows = payload.get("people_reached") or []
    headline = next((row for row in rows if row.get("is_total") and row.get("has_value")), None)
    visible = [row for row in rows if row.get("has_value") and not row.get("is_total")]
    split_eo = any((row.get("code") or "") == "EO" for row in visible) and any(
        (row.get("code") or "") != "EO" for row in visible
    )
    labels: list[str] = []
    icons: list[str] = []
    values: list[str] = []
    for row in visible:
        code = row.get("code") or ""
        extra = " upr-reach-cell--eo" if code == "EO" else ""
        labels.append(f"<td class='upr-reach-label{extra}'>{escape(row.get('label') or '')}</td>")
        icons.append(
            f"<td class='upr-reach-icon-wrap{extra}'>{_sp_icon(code, row.get('icon_src'))}</td>"
        )
        values.append(
            f"<td class='upr-reach-value{extra}'>{_metric_html(row.get('display'), fallback='')}</td>"
        )
        if split_eo and code == "EO":
            divider = "<td class='upr-reach-divider' aria-hidden='true'></td>"
            labels.append(divider)
            icons.append(divider)
            values.append(divider)
    if is_rtl() and labels:
        labels.reverse()
        icons.reverse()
        values.reverse()
    headline_html = ""
    if headline and _is_plan(payload):
        headline_html = (
            f"<div class='upr-reach-headline'>{_metric_html(headline.get('display'), fallback='')}</div>"
        )
    if not labels:
        body = headline_html or f"<p class='upr-empty'>{escape(t('No people-reached figures reported.'))}</p>"
    else:
        row_class = "upr-reach-row upr-reach-row--eo-split" if split_eo else "upr-reach-row"
        if len(visible) >= 6:
            row_class += " upr-reach-row--full"
        body = (
            f"{headline_html}"
            f"<table class='{row_class}' dir='ltr'>"
            f"<tr class='upr-reach-band upr-reach-band--labels'>{''.join(labels)}</tr>"
            f"<tr class='upr-reach-band upr-reach-band--icons'>{''.join(icons)}</tr>"
            f"<tr class='upr-reach-band upr-reach-band--values'>{''.join(values)}</tr>"
            "</table>"
        )
    return (
        f"<section class='upr-block upr-block--reach'><h2 class='upr-block__title'>{title}</h2>"
        f"{body}</section>"
    )


def _ltr_num_attr() -> str:
    """Isolate Latin digits. Always LTR so mixed Arabic amounts stay unit-left."""
    return " dir='ltr'"


def _plan_chf_html(display: str | None) -> str:
    text = (display or "").strip()
    if not text or text.lower() == "not reported":
        return _metric_html(text)
    if text.upper().endswith("CHF") or text.endswith(chf_label()):
        return f'<span class="upr-num"{_ltr_num_attr()}>{_amount_html(text)}</span>'
    return f'<span class="upr-num"{_ltr_num_attr()}>{_amount_html(with_chf(text))}</span>'


def _cover_country_type(name: str) -> tuple[str, str, str]:
    """Font size and tracking so short names read large and long names still fit."""
    chars = max(len((name or "").strip()), 1)
    size_rem = min(3.15, max(1.22, 44.0 / chars))
    if chars <= 14:
        tracking = 0.06
    elif chars <= 24:
        tracking = 0.035
    else:
        tracking = 0.02
    extra = " upr-doc-header__country--long" if chars > 36 else ""
    return f"{size_rem:.2f}rem", f"{tracking:.3f}em", extra


def _doc_header(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    country = localized_country_header(meta)
    if not country:
        return ""
    size, tracking, name_extra = _cover_country_type(country)
    subtitle = (meta.get("document_subtitle") or "").strip() or document_subtitle(
        meta.get("kind") or "report",
        meta.get("period_name"),
        plan_years=meta.get("plan_years"),
    )
    date_text = (meta.get("header_date") or "").strip() or format_header_date()
    ns_src = (meta.get("ns_logo_src") or "").strip()
    ns_alt = (meta.get("national_society") or t("National Society")).strip() or t("National Society")
    ns_logo_html = ""
    if ns_src:
        ns_logo_html = (
            f"<img class='upr-doc-header__ns-logo' src='{escape(ns_src, quote=True)}' "
            f"alt='{escape(ns_alt, quote=True)}'>"
        )
    return (
        "<header class='upr-doc-header'>"
        "<div class='upr-doc-header__brand'>"
        f"<img class='upr-doc-header__logo' src='{escape(IFRC_LOGO_SRC, quote=True)}' alt='IFRC'>"
        "</div>"
        "<div class='upr-doc-header__titles'>"
        f"<h1 class='upr-doc-header__country{name_extra}' style='font-size:{size};letter-spacing:{tracking}'>{escape(country)}</h1>"
        f"<p class='upr-doc-header__subtitle'>{escape(subtitle)}</p>"
        "</div>"
        "<div class='upr-doc-header__meta'>"
        f"{ns_logo_html}"
        f"<time class='upr-doc-header__date'>{escape(date_text)}</time>"
        "</div>"
        "</header>"
    )


COVER_FOOTER_NOTE = "Information on data scope and limitations is available on the back page"
COVER_FOOTER_ORG = "International Federation of Red Cross and Red Crescent Societies"


def _doc_footer(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    code = escape(appeal_number(meta.get("iso2") or meta.get("appeal_iso2")))
    appeal_html = ""
    if code:
        appeal_html = (
            "<span class='upr-doc-footer__appeal'>"
            f"{escape(t('Appeal number'))} <strong>{code}</strong>"
            "</span>"
        )
    return (
        f"<footer class='upr-doc-footer{_export_font_class()}'>"
        "<table class='upr-doc-footer__row'><tr>"
        f"<td class='upr-doc-footer__appeal-cell'>{appeal_html}</td>"
        "<td class='upr-doc-footer__note-cell'>"
        f"<span class='upr-doc-footer__note'>*{escape(t(COVER_FOOTER_NOTE))}</span>"
        "</td>"
        "</tr></table>"
        f"<p class='upr-doc-footer__org'>{escape(t(COVER_FOOTER_ORG))}</p>"
        "</footer>"
    )


def _plan_cover_banner(payload: dict[str, Any]) -> str:
    return _doc_header(payload)


def _plan_pns_list(payload: dict[str, Any]) -> str:
    rows = payload.get("participating_societies") or payload.get("support") or []
    names: list[str] = []
    any_star = False
    seen: set[str] = set()
    for rec in rows:
        name = (rec.get("name") or "").strip()
        if not name:
            continue
        key = str(rec.get("ns_id") if rec.get("ns_id") is not None else name).lower()
        if key in seen:
            continue
        seen.add(key)
        areas = rec.get("areas") or {}
        spef = any(areas.get(code) for code in SUPPORT_AREA_CODES)
        star = bool(rec.get("multilateral_only") or (areas.get("multilateral") and not spef))
        if star:
            any_star = True
            names.append(f"{escape(name)}*")
        else:
            names.append(escape(name))
    if not names:
        return ""
    meta = payload.get("meta") or {}
    note_year = int(meta.get("year") or 0) - 1
    if any_star and note_year > 0:
        note = (
            f"<p class='upr-plan-pns__note'>*{escape(t('National Societies which have contributed only multilaterally through the IFRC in {year}.').replace('{year}', str(note_year)))}</p>"
        )
    elif any_star:
        note = f"<p class='upr-plan-pns__note'>* {escape(t('Multilateral support only'))}</p>"
    else:
        note = ""
    items = "".join(f"<li>{name}</li>" for name in names)
    return (
        "<section class='upr-block upr-block--pns-list'>"
        f"<h2 class='upr-block__title'>{escape(t('Participating National Societies'))}</h2>"
        f"<ul class='upr-plan-pns__list'>{items}</ul>"
        f"{note}</section>"
    )


def _with_plan_pns(payload: dict[str, Any], detail: str) -> str:
    pns = _plan_pns_list(payload)
    if not pns:
        return detail
    return (
        "<div class='upr-plan-detail-row'>"
        "<table class='upr-plan-detail-row__grid'><tr>"
        f"<td class='upr-plan-detail-row__fund'>{detail}</td>"
        f"<td class='upr-plan-detail-row__pns'>{pns}</td>"
        "</tr></table></div>"
    )


def _plan_req_amount(display: str | None, *, tone: str = "dark") -> str:
    text = (display or "").strip()
    extra = " upr-plan-req__amt--accent" if tone == "accent" else ""
    if not text or text.lower() == "not reported":
        return f"<span class='upr-plan-req__amt{extra}'>{_metric_html(text)}</span>"
    if text.upper().endswith("CHF"):
        text = text[:-3].strip()
    label = chf_label()
    if text.endswith(label):
        text = text[: -len(label)].strip()
    if is_rtl():
        return (
            f"<span class='upr-plan-req__amt{extra}'>"
            f"<span class='upr-num upr-plan-fund__source-value'{_ltr_num_attr()}>"
            f"{_amount_html(with_chf(text))}</span></span>"
        )
    return (
        f"<span class='upr-plan-req__amt{extra}'>"
        f"<span class='upr-num upr-plan-fund__source-value'{_ltr_num_attr()}>{escape(text)}</span>"
        f"<span class='upr-plan-req__chf'> {escape(label)}</span></span>"
    )


def _plan_req_total(display: str | None) -> str:
    amount = _plan_req_amount(display, tone="accent")
    return f"<div class='upr-plan-req__total'>{escape(t('Total'))} {amount}</div>"


def _plan_funding(payload: dict[str, Any]) -> str:
    fin = payload.get("financial") or {}
    meta = payload.get("meta") or {}
    years = list(fin.get("years") or [])
    cover = list(fin.get("cover_sources") or [])
    if not cover:
        label_map = {
            "HNS": t("Through Host National Society"),
            "IFRC Secretariat": t("Through the IFRC"),
            "PNS": t("Through Participating National Societies"),
        }
        for src in fin.get("sources") or []:
            entity = src.get("entity") or ""
            if entity == "PNS" and not src.get("value"):
                continue
            cover.append(
                {
                    "entity": entity,
                    "label": label_map.get(entity, src.get("label") or entity),
                    "display": src.get("display") or "",
                    "value": src.get("value") or 0,
                }
            )
    year0 = meta.get("year") or (years[0].get("year") if years else None)
    network = fin.get("ifrc_network") or {}
    rank = {key: index for index, key in enumerate(_PLAN_REQ_ORDER)}
    cover.sort(key=lambda src: rank.get(src.get("entity") or "", 99))
    visible = [src for src in cover if float(src.get("value") or 0) > 0]
    peak = max((float(src.get("value") or 0) for src in visible), default=0.0) or 1.0
    rows = []
    for src in visible:
        value = float(src.get("value") or 0)
        pct = min(100.0, max(8.0, 100.0 * value / peak))
        hatch = _PLAN_REQ_BAR_CLASS.get(src.get("entity") or "", "upr-plan-req__bar--ifrc")
        amount = _plan_req_amount(src.get("display"))
        on_bar = pct >= 48
        if on_bar:
            plot = (
                f"<div class='upr-plan-req__plot'>"
                f"<span class='upr-plan-req__bar {hatch}' style='width:{pct:.1f}%'>{amount}</span>"
                "</div>"
            )
        else:
            plot = (
                f"<div class='upr-plan-req__plot'>"
                f"<span class='upr-plan-req__bar {hatch}' style='width:{pct:.1f}%'></span>"
                f"{_PLAN_REQ_ARROW}"
                f"{amount}</div>"
            )
        rows.append(
            "<div class='upr-plan-req__row'>"
            f"<div class='upr-plan-req__label'>{escape(src.get('label') or '')}</div>"
            f"{plot}</div>"
        )
    year0_total = network.get("funding_requirement_display") or (
        years[0].get("total_display") if years else ""
    )
    current = ""
    if year0 or rows:
        tree = f"<div class='upr-plan-req__tree'>{''.join(rows)}</div>" if rows else ""
        current = (
            "<div class='upr-plan-req__current'>"
            f"<div class='upr-plan-req__year'>{escape(str(year0 or ''))}</div>"
            f"{_plan_req_total(year0_total)}"
            f"{tree}</div>"
        )
    projected = []
    for year_row in years[1:]:
        projected.append(
            "<div class='upr-plan-req__proj'>"
            f"<div class='upr-plan-req__year'>{escape(str(year_row.get('year') or ''))}</div>"
            f"{_plan_req_total(year_row.get('total_display'))}</div>"
        )
    extra = ""
    if projected:
        extra = (
            f"<div class='upr-plan-req__projected'>{''.join(projected)}</div>"
            f"<p class='upr-plan-req__note'>*{escape(t('Projected funding requirements'))}</p>"
        )
    if not current and not extra:
        body = f"<p class='upr-empty'>{escape(t('No funding requirements reported.'))}</p>"
    else:
        body = f"<div class='upr-plan-req'>{current}{extra}</div>"
    return _with_plan_pns(
        payload,
        "<section class='upr-block upr-block--plan-fund'>"
        f"<h2 class='upr-block__title'>{escape(t('IFRC network Funding Requirements'))}</h2>"
        f"{body}</section>",
    )


def _detail_amt_cell(value: Any, *, pill: bool) -> str:
    number = float(value or 0)
    disp = format_compact_chf(number) if number else ""
    if not disp:
        return "<td class='upr-detail-fund__amt'></td>"
    text = escape(disp)
    if pill:
        text = f"<span class='upr-detail-fund__pill'>{text}</span>"
    return f"<td class='upr-detail-fund__amt'>{text}</td>"


def _detail_pair(hns: dict[str, Any], ifrc: dict[str, Any], key: str, *, pill: bool) -> str:
    return _detail_amt_cell(hns.get(key), pill=pill) + _detail_amt_cell(ifrc.get(key), pill=pill)


def _entity_funding_total(rec: dict[str, Any]) -> float:
    breakdown = sum(float(rec.get(code) or 0) for code in (*SP_CODES, "EFs"))
    emergency = float(rec.get("emergency") or 0)
    if breakdown or emergency:
        return breakdown + emergency
    return float(rec.get("total") or 0)


def _network_funding(payload: dict[str, Any]) -> str:
    """Tableau plan layout: Detailed funding requirements (year 0, HNS vs IFRC)."""
    fin = payload.get("financial") or {}
    area_years = list(fin.get("area_years") or [])
    empty = (
        "<section class='upr-block upr-block--network-funding'>"
        f"<h2 class='upr-block__title'>{escape(t('Detailed funding requirements'))}</h2>"
        f"<p class='upr-empty'>{escape(t('No funding requirements reported.'))}</p></section>"
    )
    if not area_years:
        return empty
    year_row = area_years[0]
    by_entity = year_row.get("by_entity") or {}
    hns = by_entity.get("HNS") or {}
    ifrc = by_entity.get("IFRC Secretariat") or {}

    def has_values(rec: dict[str, Any]) -> bool:
        return any(float(rec.get(key) or 0) for key in (*SP_CODES, "EFs", "emergency", "total"))

    if not has_values(hns) and not has_values(ifrc):
        return empty

    year = year_row.get("year") or (payload.get("meta") or {}).get("year") or ""
    sp_rows = []
    for code in SP_CODES:
        label = t(PLAN_DETAIL_SP_LABELS.get(code) or AREA_LABELS.get(code, code))
        sp_rows.append(
            "<tr class='upr-detail-fund__child'>"
            f"<td>{escape(label)}</td>"
            f"{_detail_pair(hns, ifrc, code, pill=False)}"
            "</tr>"
        )
    detail = (
        "<section class='upr-block upr-block--network-funding'>"
        "<div class='upr-detail-fund-wrap'>"
        f"<h2 class='upr-block__title'>{escape(t('Detailed funding requirements'))}</h2>"
        f"<div class='upr-detail-fund__year'>{escape(str(year))}</div>"
        "<table class='upr-detail-fund'>"
        "<thead><tr>"
        f"<th></th><th>{escape(t('Host National Society'))}</th><th>{escape(t('IFRC'))}</th>"
        "</tr></thead><tbody>"
        "<tr class='upr-detail-fund__section'>"
        f"<td>{escape(t('Ongoing emergencies'))}</td>"
        f"{_detail_pair(hns, ifrc, 'emergency', pill=True)}"
        "</tr>"
        f"<tr class='upr-detail-fund__group'><td>{escape(t('Longer-term needs'))}</td><td></td><td></td></tr>"
        f"{''.join(sp_rows)}"
        "<tr class='upr-detail-fund__section'>"
        f"<td>{escape(t('Enabling local actors'))}</td>"
        f"{_detail_pair(hns, ifrc, 'EFs', pill=True)}"
        "</tr></tbody><tfoot><tr>"
        f"<td>{escape(t('Total'))}</td>"
        f"{_detail_amt_cell(_entity_funding_total(hns), pill=True)}"
        f"{_detail_amt_cell(_entity_funding_total(ifrc), pill=True)}"
        "</tr></tfoot></table></div></section>"
    )
    return detail


def _financial(payload: dict[str, Any]) -> str:
    if _is_plan(payload):
        return _plan_funding(payload)
    fin = payload.get("financial") or {}
    network = fin.get("ifrc_network") or {}
    ns_block = fin.get("national_society") or {}
    sources = list(fin.get("sources") or [])
    years = fin.get("years") or []
    entities = fin.get("network_entities") or []
    ns_name = escape((payload.get("meta") or {}).get("national_society") or "")

    overview_rows = [
        {
            "label": t("Funding"),
            "display": ns_block.get("funding_display") or network.get("funding_display") or _not_reported(),
            "value": ns_block.get("funding") or network.get("funding") or 0,
            "color": AREA_COLORS["funding"],
        },
        {
            "label": t("Expenditure"),
            "display": ns_block.get("expenditure_display") or network.get("expenditure_display") or _not_reported(),
            "value": ns_block.get("expenditure") or network.get("expenditure") or 0,
            "color": AREA_COLORS["expenditure"],
        },
    ]

    source_rows = [
        {
            "label": src.get("label") or src.get("entity") or "",
            "display": src.get("display") or format_compact_chf(src.get("value")) or _not_reported(),
            "value": src.get("value") or 0,
            "color": AREA_COLORS["source"],
        }
        for src in sources
    ]

    ns_heading = f"<div class='upr-fin-ns'>{ns_name}</div>" if ns_name else ""
    top = (
        "<div class='upr-fin-hero'>"
        f"{ns_heading}"
        f"{_financial_hero_charts(overview_rows, source_rows)}"
        "</div>"
    )
    network_html = _financial_network(entities, years)
    return (
        "<section class='upr-block upr-block--finance'>"
        "<div class='upr-fin-cover'>"
        f"<h2 class='upr-block__title upr-block__title--center'>{escape(t('FINANCIAL OVERVIEW'))}</h2>"
        f"<p class='upr-fin-unit'>{escape(t('in Swiss francs (CHF)'))}</p>"
        f"{top}</div>{network_html}"
        "</section>"
    )


def _hero_bar_cells(row: dict[str, Any] | None, *, scale: float) -> str:
    if not row:
        return _ltr_row(["<td class='upr-bar-label'></td>", "<td class='upr-bar-plot'></td>"])
    label = escape(row.get("label") or "")
    return _ltr_row(
        [
            f"<td class='upr-bar-label'>{label}</td>",
            (
                f"<td class='upr-bar-plot'>"
                f"{_bar_plot(row, color=row.get('color') or IFRC_RED, scale=scale)}"
                f"</td>"
            ),
        ]
    )


def _hero_pair_table(
    title: str,
    rows: list[dict[str, Any]],
    *,
    scale: float,
    label_class: str,
    plot_class: str,
    empty: str | None = None,
) -> str:
    if rows:
        body = "".join(
            f"<tr class='upr-bar-row'>{_hero_bar_cells(row, scale=scale)}</tr>" for row in rows
        )
    else:
        body = f"<tr><td class='upr-empty' colspan='2'>{escape(empty or '')}</td></tr>"
    cols = [f"<col class='{label_class}'>", f"<col class='{plot_class}'>"]
    return (
        f"<table class='upr-fin-grid upr-fin-grid--half' dir='ltr'><colgroup>"
        f"{_ltr_row(cols)}"
        "</colgroup>"
        f"<thead><tr><th class='upr-block__subtitle' colspan='2'>{escape(title)}</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _financial_hero_charts(overview_rows: list[dict[str, Any]], source_rows: list[dict[str, Any]]) -> str:
    left_scale = max((float(row.get("value") or 0) for row in overview_rows), default=0) or 1
    right_scale = max((float(row.get("value") or 0) for row in source_rows), default=0) or 1
    overview = _hero_pair_table(
        t("Overview"),
        overview_rows,
        scale=left_scale,
        label_class="upr-fin-col-overview-label",
        plot_class="upr-fin-col-overview-plot",
    )
    if not source_rows:
        return overview
    sources = _hero_pair_table(
        t("Funding Sources"),
        source_rows,
        scale=right_scale,
        label_class="upr-fin-col-source-label",
        plot_class="upr-fin-col-source-plot",
        empty=t("No funding sources reported."),
    )
    return (
        "<div class='upr-fin-hero-split upr-fin-grid--with-sources'>"
        f"<div class='upr-fin-hero-split__col'>{overview}</div>"
        f"<div class='upr-fin-hero-split__col'>{sources}</div>"
        "</div>"
    )


def _financial_network(
    entities: list[dict[str, Any]],
    years: list[dict[str, Any]],
) -> str:
    """Tableau Financial Overview (3) — entity | bucket | metric | bar."""
    metric_colors = {
        "funding_requirement": AREA_COLORS["funding_requirement"],
        "funding": AREA_COLORS["funding"],
        "expenditure": AREA_COLORS["expenditure"],
    }
    if entities:
        peak = 1.0
        for entity in entities:
            for bucket in entity.get("buckets") or []:
                for metric in bucket.get("metrics") or []:
                    peak = max(peak, float(metric.get("value") or 0))
        table_rows: list[str] = []
        first_entity = True
        for entity in entities:
            buckets = [bucket for bucket in (entity.get("buckets") or []) if bucket.get("metrics")]
            if not buckets:
                continue
            entity_label = escape(entity.get("label") or entity.get("entity") or "")
            entity_emitted = False
            first_bucket = True
            for bucket in buckets:
                metrics = bucket.get("metrics") or []
                bucket_label = escape(bucket.get("label") or "")
                bucket_emitted = False
                for metric in metrics:
                    row = {
                        "display": metric.get("display") or "",
                        "value": metric.get("value") or 0,
                        "color": metric_colors.get(metric.get("key") or "", AREA_COLORS["funding"]),
                    }
                    classes = ["upr-fin-net__row"]
                    if not first_entity and not entity_emitted:
                        classes.append("upr-fin-net__group-start")
                    if not first_bucket and not bucket_emitted:
                        classes.append("upr-fin-net__bucket-start")
                    cells: list[str] = []
                    # Repeat empty cells instead of rowspan — WeasyPrint paints
                    # rowspan cells into neighbouring metric/plot text.
                    if not entity_emitted:
                        cells.append(f"<td class='upr-fin-net__entity'>{entity_label}</td>")
                        entity_emitted = True
                    else:
                        cells.append("<td class='upr-fin-net__entity'></td>")
                    if not bucket_emitted:
                        cells.append(
                            f"<td class='upr-fin-net__bucket'>{bucket_label or '&nbsp;'}</td>"
                        )
                        bucket_emitted = True
                    else:
                        cells.append("<td class='upr-fin-net__bucket'></td>")
                    cells.append(
                        f"<td class='upr-fin-net__metric'>{escape(metric.get('label') or '')}</td>"
                    )
                    cells.append(
                        f"<td class='upr-fin-net__plot'>{_bar_plot(row, color=row['color'], scale=peak)}</td>"
                    )
                    table_rows.append(f"<tr class='{' '.join(classes)}'>{_ltr_row(cells)}</tr>")
                first_bucket = False
            first_entity = False
        if not table_rows:
            return ""
        row_count = len(table_rows)
        if row_count <= 10:
            density = " upr-fin-net--airy"
        elif row_count <= 16:
            density = " upr-fin-net--spread"
        else:
            density = ""
        cols = [
            "<col class='upr-fin-net-col-entity'>",
            "<col class='upr-fin-net-col-bucket'>",
            "<col class='upr-fin-net-col-metric'>",
            "<col class='upr-fin-net-col-plot'>",
        ]
        return (
            "<div class='upr-fin-network'>"
            f"<h3 class='upr-block__subtitle upr-block__subtitle--center'>{escape(t('IFRC network'))}</h3>"
            f"<table class='upr-fin-net{density}' dir='ltr'><colgroup>"
            f"{_ltr_row(cols)}"
            "</colgroup><tbody>"
            f"{''.join(table_rows)}</tbody></table></div>"
        )

    network_rows = []
    if years:
        for year_row in years:
            network_rows.append(
                {
                    "label": str(year_row.get("year") or ""),
                    "display": year_row.get("total_display") or "",
                    "value": year_row.get("total") or 0,
                    "color": AREA_COLORS["funding_requirement"],
                }
            )
    if not network_rows:
        return ""
    return (
        f"<h3 class='upr-block__subtitle upr-block__subtitle--center'>{escape(t('IFRC network'))}</h3>"
        f"{_hbar_chart(network_rows)}"
    )


def _support(payload: dict[str, Any]) -> str:
    if _is_plan(payload):
        return _support_plan(payload)
    return _support_report(payload)


def _wrapped_th_label(label: str) -> str:
    text = escape(label)
    if " " not in text:
        return text
    head, tail = text.rsplit(" ", 1)
    return f"{head}<br>{tail}"


def _support_area_header_cells(*, plan: bool = False) -> list[str]:
    cls = "upr-support-th upr-support-th--plan" if plan else "upr-support-th"
    cells = []
    for code in SUPPORT_AREA_CODES:
        lines = SUPPORT_AREA_HEADER_LINES.get(code)
        if lines and current_export_language() == "en":
            inner = "<br>".join(escape(line) for line in lines)
        else:
            inner = _wrapped_th_label(t(AREA_LABELS.get(code, code)))
        cells.append(f"<th class='{cls}'><span>{inner}</span></th>")
    return cells


def _support_area_headers(*, plan: bool = False) -> str:
    return "".join(_support_area_header_cells(plan=plan))


def _support_plan_area_headers() -> str:
    return _support_area_headers(plan=True)


def _plan_support_area_cell(rec: dict[str, Any], code: str) -> str:
    areas = rec.get("areas") or {}
    amounts = rec.get("area_amounts") or {}
    number = float(amounts.get(code) or 0)
    active = bool(areas.get(code)) or bool(number)
    if not active:
        return "<td class='upr-support-fill'></td>"
    color = SUPPORT_DOT_COLORS.get(code, AREA_COLORS.get(code, IFRC_RED))
    text = escape(format_compact_chf(number) if number else "-")
    return (
        f"<td class='upr-support-fill upr-support-fill--on' style='background:{color}'>{text}</td>"
    )


def _support_plan(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    title = escape(meta.get("support_title") or t("Bilateral support"))
    rows = payload.get("support") or []
    if not rows:
        return (
            f"<section class='upr-block'><h2 class='upr-block__title'>{title}</h2>"
            f"<p class='upr-empty'>{escape(t('No participating National Societies reported.'))}</p></section>"
        )
    n_areas = len(SUPPORT_AREA_CODES)
    body: list[str] = []
    index = 0
    while index < len(rows):
        rec = rows[index]
        ns_id = rec.get("ns_id")
        span = 1
        if ns_id is not None:
            while index + span < len(rows) and rows[index + span].get("ns_id") == ns_id:
                span += 1
        for offset in range(span):
            row = rows[index + offset]
            cells: list[str] = []
            if offset == 0:
                cells.append(
                    f"<td class='upr-ns' rowspan='{span}'>{escape(row.get('name') or '')}</td>"
                )
            cells.append(f"<td class='upr-support-year'>{escape(str(row.get('year') or ''))}</td>")
            funding = _amount_html(row.get("funding_display")) or "&nbsp;"
            confirmed = _amount_html(row.get("confirmed_display")) or "&nbsp;"
            cells.append(f"<td class='upr-num'{_ltr_num_attr()}>{funding}</td>")
            cells.append(f"<td class='upr-num upr-support-confirmed'{_ltr_num_attr()}>{confirmed}</td>")
            cells.extend(_plan_support_area_cell(row, code) for code in SUPPORT_AREA_CODES)
            body.append(f"<tr>{_ltr_row(cells)}</tr>")
        index += span
    total = payload.get("support_total") or {}
    total_display = escape((total.get("display") or "").strip() or format_compact_chf(total.get("value")) or "0")
    confirmed_total = sum(float(row.get("confirmed") or 0) for row in rows)
    confirmed_total_display = escape(format_compact_chf(confirmed_total) if confirmed_total else "") or "&nbsp;"
    cols = [
        "<col class='upr-support-col-ns'>",
        "<col class='upr-support-col-year'>",
        "<col class='upr-support-col-num'>",
        "<col class='upr-support-col-num'>",
        *["<col class='upr-support-col-fill'>" for _ in range(n_areas)],
    ]
    heads = [
        f"<th class='upr-ns'>{escape(t('National Society'))}</th>",
        f"<th class='upr-support-year'>{escape(t('Year'))}</th>",
        f"<th class='upr-support-th'><span>{_wrapped_th_label(meta.get('support_funding_label') or t('Funding Requirement'))}</span></th>",
        f"<th class='upr-support-th'><span>{_wrapped_th_label(meta.get('support_confirmed_label') or t('Confirmed Funding'))}</span></th>",
        *_support_area_header_cells(plan=True),
    ]
    foot = [
        f"<td class='upr-ns'>{escape(t('Total'))}</td>",
        "<td></td>",
        f"<td class='upr-num upr-support-total'{_ltr_num_attr()}>{_amount_html(with_chf(total_display, prefix=True))}</td>",
        f"<td class='upr-num upr-support-confirmed'{_ltr_num_attr()}>{_amount_html(confirmed_total_display) or confirmed_total_display}</td>",
        f"<td colspan='{n_areas}'></td>",
    ]
    return (
        f"<section class='upr-block'><h2 class='upr-block__title'>{title}</h2>"
        "<table class='upr-support-table upr-support-table--plan' dir='ltr'>"
        f"<colgroup>{_ltr_row(cols)}</colgroup>"
        f"<thead><tr>{_ltr_row(heads)}</tr></thead><tbody>{''.join(body)}</tbody>"
        f"<tfoot><tr class='upr-support-total-row'>{_ltr_row(foot)}</tr></tfoot></table></section>"
    )


def _support_report(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    title = escape(meta.get("support_title") or t("Bilateral support"))
    rows = payload.get("support") or []
    if not rows:
        return (
            f"<section class='upr-block'><h2 class='upr-block__title'>{title}</h2>"
            f"<p class='upr-empty'>{escape(t('No participating National Societies reported.'))}</p></section>"
        )
    n_areas = len(SUPPORT_AREA_CODES)
    body = []
    for rec in rows:
        dots = []
        areas = rec.get("areas") or {}
        for code in SUPPORT_AREA_CODES:
            active = bool(areas.get(code))
            color = SUPPORT_DOT_COLORS.get(code, AREA_COLORS.get(code, IFRC_RED)) if active else "transparent"
            cls = "upr-dot upr-dot--on" if active else "upr-dot"
            dots.append(f"<td class='upr-dot-cell'><span class='{cls}' style='background:{color}'></span></td>")
        funding = _amount_html(rec.get("funding_display")) or "&nbsp;"
        body.append(
            "<tr>"
            + _ltr_row(
                [
                    f"<td class='upr-ns'>{escape(rec.get('name') or '')}</td>",
                    f"<td class='upr-num'{_ltr_num_attr()}>{funding}</td>",
                    *dots,
                ]
            )
            + "</tr>"
        )
    total = payload.get("support_total") or {}
    total_display = escape((total.get("display") or "").strip() or format_compact_chf(total.get("value")) or "0")
    cols = [
        "<col class='upr-support-col-ns'>",
        "<col class='upr-support-col-num'>",
        *["<col class='upr-support-col-dot'>" for _ in range(n_areas)],
    ]
    heads = [
        "<th class='upr-ns'></th>",
        f"<th class='upr-support-th'><span>{_wrapped_th_label(meta.get('support_funding_label') or t('Funding Reported'))}</span></th>",
        *_support_area_header_cells(),
    ]
    total_amount = (
        f"{_amount_html(with_chf(total_display, prefix=True))}"
    )
    # Report totals sit next to the number column; merge the remaining cells
    # in RTL so "Total" does not collide with the LTR amount. Plan support
    # has two amount columns plus a year gap, so it keeps the LTR colspan.
    if is_rtl():
        foot = [
            f"<td class='upr-ns'>{escape(t('Total'))}</td>",
            (
                f"<td class='upr-num upr-support-total' colspan='{n_areas + 1}'"
                f"{_ltr_num_attr()}>{total_amount}</td>"
            ),
        ]
    else:
        foot = [
            f"<td class='upr-ns'>{escape(t('Total'))}</td>",
            f"<td class='upr-num upr-support-total'{_ltr_num_attr()}>{total_amount}</td>",
            f"<td colspan='{n_areas}'></td>",
        ]
    return (
        f"<section class='upr-block'><h2 class='upr-block__title'>{title}</h2>"
        "<table class='upr-support-table' dir='ltr'>"
        f"<colgroup>{_ltr_row(cols)}</colgroup>"
        f"<thead><tr>{_ltr_row(heads)}</tr></thead><tbody>{''.join(body)}</tbody>"
        f"<tfoot><tr class='upr-support-total-row'>{_ltr_row(foot)}</tr></tfoot></table></section>"
    )


def _strategic_priorities(payload: dict[str, Any]) -> str:
    rows = payload.get("core_indicators") or []
    body = _bars_grouped(rows, SP_CODES) if rows else f"<p class='upr-empty'>{escape(t('No core indicators reported.'))}</p>"
    return (
        "<section class='upr-block upr-block--bars'>"
        f"<h2 class='upr-block__title'>{escape(t('Strategic Priorities'))}</h2>"
        f"{body}</section>"
    )


def _enabling_functions(payload: dict[str, Any]) -> str:
    rows = payload.get("enabling_indicators") or []
    body = _bars_grouped(rows, EF_CODES) if rows else f"<p class='upr-empty'>{escape(t('No enabling-function indicators reported.'))}</p>"
    return (
        "<section class='upr-block upr-block--bars'>"
        f"<h2 class='upr-block__title'>{escape(t('Enabling Functions'))}</h2>"
        f"{body}</section>"
    )


def _emergency(payload: dict[str, Any], slot: int) -> str:
    match = next((em for em in payload.get("emergencies") or [] if int(em.get("slot") or 0) == slot), None)
    if not match:
        return (
            f"<section class='upr-block'><h2 class='upr-block__title'>{escape(t(f'Emergency {slot}'))}</h2>"
            f"<p class='upr-empty'>{escape(t('No emergency appeal selected for this slot.'))}</p></section>"
        )
    name = escape(match.get("name") or t(f"Emergency {slot}"))
    code = escape(match.get("code") or "")
    indicators = match.get("indicators") or []
    visible = [
        row
        for row in indicators
        if row.get("kind") in {"yesno", "percent"} or row.get("value")
    ]
    grouped = _bars_grouped(visible, (*SP_CODES, *EF_CODES, "EO")) if visible else ""
    if visible and not grouped:
        grouped = _hbar_chart(visible, color=IFRC_RED)
    name_html = f"<span class='upr-emergency-name'>{name}</span>"
    if code:
        title = f"<span class='upr-code'>{code}</span> / {name_html}"
    else:
        title = name_html
    return (
        "<section class='upr-block upr-block--emergency'>"
        f"<h2 class='upr-block__title'>{title}</h2>"
        f"{grouped}"
        "</section>"
    )


def _bars_grouped(rows: list[dict[str, Any]], order: tuple[str, ...]) -> str:
    by_code: dict[str, list[dict[str, Any]]] = {}
    leftover: list[dict[str, Any]] = []
    for row in rows:
        code = row.get("code")
        if code in order:
            by_code.setdefault(code, []).append(row)
        else:
            leftover.append(row)
    peak = max(
        (
            float(row.get("value") or 0)
            for row in rows
            if row.get("kind") not in {"yesno", "percent"}
        ),
        default=0,
    ) or 1
    chunks = []
    for code in order:
        group = by_code.get(code) or []
        if not group:
            continue
        chunks.append(
            "<div class='upr-bar-group'>"
            f"<div class='upr-bar-group__title'>{escape(t(AREA_LABELS.get(code, code)))}</div>"
            f"{_hbar_chart(group, color=IFRC_RED, peak=peak)}"
            "</div>"
        )
    if leftover:
        chunks.append(_hbar_chart(leftover, color=IFRC_RED, peak=peak))
    return "".join(chunks)


def _is_label_only(row: dict[str, Any]) -> bool:
    if row.get("kind") in {"yesno", "percent"}:
        return True
    return not float(row.get("value") or 0)


def _bar_plot(row: dict[str, Any], *, color: str, scale: float) -> str:
    display = _metric_html(row.get("display"))
    value = float(row.get("value") or 0)
    fill = row.get("color") or color
    if row.get("kind") == "percent":
        return f"<div class='upr-bar-yes upr-num'{_ltr_num_attr()}>{display}</div>"
    if _is_label_only(row):
        return f"<div class='upr-bar-yes'>{display}</div>"
    pct = max(3.0, min(100.0, value / scale * 100)) if value else 0.0
    return (
        "<div class='upr-bar-track'>"
        f"<span class='upr-bar-fill' style='width:{pct:.1f}%;background:{fill}'></span>"
        f"<span class='upr-bar-value'{_ltr_num_attr()}>{display}</span>"
        "</div>"
    )


def _hbar_chart(
    rows: list[dict[str, Any]],
    *,
    color: str = IFRC_RED,
    peak: float | None = None,
) -> str:
    if not rows:
        return ""
    scale = float(peak) if peak else max(
        (
            float(row.get("value") or 0)
            for row in rows
            if row.get("kind") not in {"yesno", "percent"}
        ),
        default=0,
    ) or 1
    parts = []
    for row in rows:
        label = escape(row.get("label") or "")
        extra = " upr-bar-row--text" if _is_label_only(row) else ""
        parts.append(
            f"<tr class='upr-bar-row{extra}'>"
            f"<td class='upr-bar-label'>{label}</td>"
            f"<td class='upr-bar-plot'>{_bar_plot(row, color=row.get('color') or color, scale=scale)}</td>"
            "</tr>"
        )
    # CSS ``direction: rtl`` (not ``_ltr_row``) so labels sit on the right.
    return f"<table class='upr-bars'><tbody>{''.join(parts)}</tbody></table>"
