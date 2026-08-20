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
    PLAN_KPI_ORDER,
    SP_CODES,
    SUPPORT_AREA_CODES,
    kpi_icon_src,
)
from plugins.upr_visuals.formatters import format_compact_chf

IFRC_RED = "#d22730"
_NOT_REPORTED = "Not reported"


def _metric_html(text: str | None, *, fallback: str = _NOT_REPORTED) -> str:
    raw = (text or "").strip() or fallback
    if raw.lower() == "not reported":
        return f'<span class="upr-not-reported">{escape(raw)}</span>'
    return escape(raw)

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
        return (
            f'<span class="upr-reach-icon upr-reach-icon--img" aria-hidden="true">'
            f'<img src="{escape(src, quote=True)}" alt="">'
            f"</span>"
        )
    color = AREA_COLORS.get(code, IFRC_RED)
    inner = _SP_ICON_PATHS.get(code, f'<text x="12" y="16" text-anchor="middle" font-size="8">{escape(code)}</text>')
    return (
        f'<svg class="upr-reach-icon" viewBox="0 0 40 40" width="64" height="64" aria-hidden="true">'
        f'<circle cx="20" cy="20" r="18" fill="#fff" stroke="#011e41" stroke-width="1.4"/>'
        f'<g transform="translate(8 8)" fill="none" stroke="{color}" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round">{inner}</g></svg>'
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
    return f'<div class="upr-dashboard upr-dashboard--{escape(dashboard_id)}">{body}</div>'


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
        f'<article class="upr-visual-report" data-aes-id="{escape(str(meta.get("aes_id") or ""))}">'
        f'<header class="upr-visual-report__toolbar">'
        f"<div><strong>{ns}</strong> · {period} · {escape(meta.get('round_code') or '')}</div>"
        f"</header>"
        f'<div class="upr-visual-report__body">{"".join(parts)}</div>'
        f"</article>"
    )


def _is_plan(payload: dict[str, Any]) -> bool:
    return (payload.get("meta") or {}).get("kind") == "plan"


def _network_area_label(code: str) -> str:
    if code == "EFs":
        return "Enabling local actors"
    return AREA_LABELS.get(code, code)


def _combined(payload: dict[str, Any]) -> str:
    if _is_plan(payload):
        parts = [
            _plan_cover_banner(payload),
            _in_support(payload),
            _reach(payload),
            _plan_funding(payload),
            _plan_pns_list(payload),
            _support(payload),
            _network_funding(payload),
        ]
        return "".join(f'<div class="upr-combined-section">{part}</div>' for part in parts if part)
    parts = [_in_support(payload), _reach(payload), _financial(payload), _support(payload)]
    if payload.get("core_indicators"):
        parts.append(_strategic_priorities(payload))
    if payload.get("enabling_indicators"):
        parts.append(_enabling_functions(payload))
    for em in payload.get("emergencies") or []:
        parts.append(_emergency(payload, int(em["slot"])))
    return "".join(f'<div class="upr-combined-section">{part}</div>' for part in parts)


def _in_support(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    ns = (meta.get("national_society") or "").strip()
    prefix = (meta.get("header_prefix") or ("In support of" if _is_plan(payload) else "IN SUPPORT OF")).strip()
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
    raw_title = meta.get("people_title") or "People reached"
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
        labels.append(f"<div class='upr-reach-label{extra}'>{escape(row.get('label') or '')}</div>")
        icons.append(
            f"<div class='upr-reach-icon-wrap{extra}'>{_sp_icon(code, row.get('icon_src'))}</div>"
        )
        values.append(
            f"<div class='upr-reach-value{extra}'>{_metric_html(row.get('display'), fallback='')}</div>"
        )
        if split_eo and code == "EO":
            divider = "<div class='upr-reach-divider' aria-hidden='true'></div>"
            labels.append(divider)
            icons.append(divider)
            values.append(divider)
    headline_html = ""
    if headline and _is_plan(payload):
        headline_html = (
            f"<div class='upr-reach-headline'>{_metric_html(headline.get('display'), fallback='')}</div>"
        )
    if not labels:
        body = headline_html or "<p class='upr-empty'>No people-reached figures reported.</p>"
    else:
        row_class = "upr-reach-row upr-reach-row--eo-split" if split_eo else "upr-reach-row"
        body = (
            f"{headline_html}"
            f"<div class='{row_class}'>"
            f"<div class='upr-reach-band upr-reach-band--labels'>{''.join(labels)}</div>"
            f"<div class='upr-reach-band upr-reach-band--icons'>{''.join(icons)}</div>"
            f"<div class='upr-reach-band upr-reach-band--values'>{''.join(values)}</div>"
            "</div>"
        )
    return (
        f"<section class='upr-block upr-block--reach'><h2 class='upr-block__title'>{title}</h2>"
        f"{body}</section>"
    )


def _plan_chf_html(display: str | None) -> str:
    text = (display or "").strip()
    if not text or text.lower() == "not reported":
        return _metric_html(text)
    if text.upper().endswith("CHF"):
        return f'<span class="upr-num">{escape(text)}</span>'
    return f'<span class="upr-num">{escape(text)} CHF</span>'


def _plan_cover_banner(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    country = escape((meta.get("country_name") or "").upper())
    years = [str(year) for year in (meta.get("plan_years") or []) if year]
    if len(years) >= 2:
        span = f"{years[0]}-{years[-1]} IFRC network country plan"
    elif years:
        span = f"{years[0]} IFRC network country plan"
    else:
        year = meta.get("year") or meta.get("period_name") or ""
        span = f"{year} IFRC network country plan" if year else "IFRC network country plan"
    if not country:
        return ""
    return (
        "<header class='upr-plan-cover'>"
        f"<h1 class='upr-plan-cover__country'>{country}</h1>"
        f"<p class='upr-plan-cover__span'>{escape(span)}</p>"
        "</header>"
    )


def _plan_pns_list(payload: dict[str, Any]) -> str:
    rows = payload.get("participating_societies") or payload.get("support") or []
    names: list[str] = []
    any_star = False
    for rec in rows:
        name = (rec.get("name") or "").strip()
        if not name:
            continue
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
            f"<p class='upr-plan-pns__note'>*National Societies which have contributed only "
            f"multilaterally through the IFRC in {note_year}.</p>"
        )
    elif any_star:
        note = "<p class='upr-plan-pns__note'>* Multilateral support only</p>"
    else:
        note = ""
    return (
        "<section class='upr-block upr-block--pns-list'>"
        "<h2 class='upr-block__title'>Participating National Societies</h2>"
        f"<p class='upr-plan-pns__names'>{', '.join(names)}</p>"
        f"{note}</section>"
    )


def _plan_funding(payload: dict[str, Any]) -> str:
    fin = payload.get("financial") or {}
    meta = payload.get("meta") or {}
    years = list(fin.get("years") or [])
    cover = list(fin.get("cover_sources") or [])
    if not cover:
        label_map = {
            "HNS": "Through Host National Society",
            "IFRC Secretariat": "Through the IFRC",
            "PNS": "Through Participating National Societies",
        }
        for src in fin.get("sources") or []:
            entity = src.get("entity") or ""
            if entity == "PNS" and not src.get("value"):
                continue
            cover.append(
                {
                    "label": label_map.get(entity, src.get("label") or entity),
                    "display": src.get("display") or "",
                    "value": src.get("value") or 0,
                }
            )
    year0 = meta.get("year") or (years[0].get("year") if years else None)
    network = fin.get("ifrc_network") or {}
    sources = []
    for src in cover:
        sources.append(
            "<div class='upr-plan-fund__source'>"
            f"<div class='upr-plan-fund__source-value'>{_plan_chf_html(src.get('display'))}</div>"
            f"<div class='upr-plan-fund__source-label'>{escape(src.get('label') or '')}</div>"
            "</div>"
        )
    total_display = network.get("funding_requirement_display") or (years[0].get("total_display") if years else "")
    body = (
        f"<div class='upr-plan-fund__year'>{escape(str(year0 or ''))}</div>" if year0 else ""
    )
    if sources:
        body += f"<div class='upr-plan-fund__sources'>{''.join(sources)}</div>"
        body += (
            "<div class='upr-plan-fund__total'>Total "
            f"{_plan_chf_html(total_display)}</div>"
        )
    else:
        body += "<p class='upr-empty'>No funding requirements reported.</p>"
    projected = []
    for year_row in years[1:]:
        projected.append(
            "<div class='upr-plan-fund__projected-year'>"
            f"<div class='upr-plan-fund__year'>{escape(str(year_row.get('year') or ''))}</div>"
            "<div class='upr-plan-fund__projected-label'>Total</div>"
            f"<div class='upr-plan-fund__projected-value'>{_plan_chf_html(year_row.get('total_display'))}</div>"
            "</div>"
        )
    if projected:
        body += (
            "<h3 class='upr-block__subtitle'>Projected funding requirements</h3>"
            f"<div class='upr-plan-fund__projected'>{''.join(projected)}</div>"
        )
    return (
        "<section class='upr-block upr-block--plan-fund'>"
        "<h2 class='upr-block__title'>IFRC network Funding Requirements</h2>"
        "<p class='upr-fin-unit'>in Swiss francs (CHF)</p>"
        f"{body}</section>"
    )


def _network_funding(payload: dict[str, Any]) -> str:
    fin = payload.get("financial") or {}
    area_years = list(fin.get("area_years") or [])
    empty = (
        "<section class='upr-block upr-block--network-funding'>"
        "<h2 class='upr-block__title'>IFRC Network-Supported Activities</h2>"
        "<p class='upr-empty'>No funding requirements reported.</p></section>"
    )
    if not area_years:
        return empty
    entity_specs = (
        ("HNS", "Host National Society"),
        ("IFRC Secretariat", "IFRC"),
    )
    headers = "".join(
        f"<th class='upr-support-th'><span>{escape(_network_area_label(code))}</span></th>"
        for code in SUPPORT_AREA_CODES
    )
    body: list[str] = []
    n_years = len(area_years)
    for entity, label in entity_specs:
        has_any = any(
            any(
                float((year_row.get("by_entity") or {}).get(entity, {}).get(key) or 0)
                for key in (*SUPPORT_AREA_CODES, "total")
            )
            for year_row in area_years
        )
        if not has_any:
            continue
        first = True
        for year_row in area_years:
            rec = (year_row.get("by_entity") or {}).get(entity) or {}
            cells = []
            if first:
                cells.append(f"<td class='upr-ns' rowspan='{n_years}'>{escape(label)}</td>")
                first = False
            cells.append(f"<td class='upr-netfund-year'>{escape(str(year_row.get('year') or ''))}</td>")
            for code in SUPPORT_AREA_CODES:
                val = rec.get(code) or 0
                disp = format_compact_chf(val) if val else ""
                cells.append(f"<td class='upr-num'>{escape(disp) or '&nbsp;'}</td>")
            total = rec.get("total") or 0
            cells.append(f"<td class='upr-num'>{escape(format_compact_chf(total) if total else '') or '&nbsp;'}</td>")
            body.append(f"<tr>{''.join(cells)}</tr>")
    if not body:
        return empty
    n_cols = len(SUPPORT_AREA_CODES)
    return (
        "<section class='upr-block upr-block--network-funding'>"
        "<h2 class='upr-block__title'>IFRC Network-Supported Activities</h2>"
        "<p class='upr-fin-unit'>Longer-term needs in Swiss francs (CHF)</p>"
        "<table class='upr-support-table upr-netfund-table'>"
        "<colgroup>"
        "<col class='upr-support-col-ns'>"
        "<col class='upr-netfund-col-year'>"
        f"<col class='upr-support-col-num' span='{n_cols + 1}'>"
        "</colgroup>"
        "<thead><tr>"
        "<th class='upr-ns'></th><th>Year</th>"
        f"{headers}<th class='upr-support-th'><span>Total</span></th>"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table></section>"
    )


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
            "label": "Funding",
            "display": ns_block.get("funding_display") or network.get("funding_display") or "Not reported",
            "value": ns_block.get("funding") or network.get("funding") or 0,
            "color": AREA_COLORS["funding"],
        },
        {
            "label": "Expenditure",
            "display": ns_block.get("expenditure_display") or network.get("expenditure_display") or "Not reported",
            "value": ns_block.get("expenditure") or network.get("expenditure") or 0,
            "color": AREA_COLORS["expenditure"],
        },
    ]

    source_rows = [
        {
            "label": src.get("label") or src.get("entity") or "",
            "display": src.get("display") or format_compact_chf(src.get("value")) or "Not reported",
            "value": src.get("value") or 0,
            "color": AREA_COLORS["source"],
        }
        for src in sources
    ]

    ns_heading = f"<div class='upr-fin-ns'>{ns_name}</div>" if ns_name else ""
    sources_html = (
        _hbar_chart(source_rows)
        if source_rows
        else '<p class="upr-empty">No funding sources reported.</p>'
    )
    top = (
        "<div class='upr-fin-hero'>"
        f"{ns_heading}"
        "<table class='upr-fin-grid'><tr>"
        "<td class='upr-fin-grid__cell'><h3 class='upr-block__subtitle'>Overview</h3>"
        f"{_hbar_chart(overview_rows)}</td>"
        "<td class='upr-fin-grid__cell'><h3 class='upr-block__subtitle'>Funding Sources</h3>"
        f"{sources_html}</td>"
        "</tr></table></div>"
    )
    network_html = _financial_network(entities, years)
    return (
        "<section class='upr-block upr-block--finance'>"
        "<h2 class='upr-block__title upr-block__title--center'>FINANCIAL OVERVIEW</h2>"
        "<p class='upr-fin-unit'>in Swiss francs (CHF)</p>"
        f"{top}{network_html}"
        "</section>"
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
            entity_rows = sum(len(bucket.get("metrics") or []) for bucket in buckets)
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
                    if not entity_emitted:
                        cells.append(
                            f"<td class='upr-fin-net__entity' rowspan='{entity_rows}'>{entity_label}</td>"
                        )
                        entity_emitted = True
                    if not bucket_emitted:
                        cells.append(
                            f"<td class='upr-fin-net__bucket' rowspan='{len(metrics)}'>{bucket_label}</td>"
                        )
                        bucket_emitted = True
                    cells.append(
                        f"<td class='upr-fin-net__metric'>{escape(metric.get('label') or '')}</td>"
                    )
                    cells.append(
                        f"<td class='upr-fin-net__plot'>{_bar_plot(row, color=row['color'], scale=peak)}</td>"
                    )
                    table_rows.append(f"<tr class='{' '.join(classes)}'>{''.join(cells)}</tr>")
                first_bucket = False
            first_entity = False
        if not table_rows:
            return ""
        return (
            "<div class='upr-fin-network'>"
            "<h3 class='upr-block__subtitle upr-block__subtitle--center'>IFRC network</h3>"
            "<table class='upr-fin-net'><tbody>"
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
        "<h3 class='upr-block__subtitle upr-block__subtitle--center'>IFRC network</h3>"
        f"{_hbar_chart(network_rows)}"
    )


def _support(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    title = escape(meta.get("support_title") or "Bilateral support")
    rows = payload.get("support") or []
    if not rows:
        return (
            f"<section class='upr-block'><h2 class='upr-block__title'>{title}</h2>"
            "<p class='upr-empty'>No participating National Societies reported.</p></section>"
        )
    headers = "".join(
        f"<th class='upr-support-th'><span>{escape(AREA_LABELS.get(code, code))}</span></th>"
        for code in SUPPORT_AREA_CODES
    )
    funding_label = escape(
        meta.get("support_funding_label")
        or ("Funding Requirement" if meta.get("kind") == "plan" else "Funding Reported")
    )
    n_areas = len(SUPPORT_AREA_CODES)
    body = []
    for rec in rows:
        dots = []
        areas = rec.get("areas") or {}
        for code in SUPPORT_AREA_CODES:
            active = bool(areas.get(code))
            color = AREA_COLORS.get(code, IFRC_RED) if active else "transparent"
            cls = "upr-dot upr-dot--on" if active else "upr-dot"
            dots.append(f"<td class='upr-dot-cell'><span class='{cls}' style='background:{color}'></span></td>")
        funding = escape(rec.get("funding_display") or "") or "&nbsp;"
        body.append(
            "<tr>"
            f"<td class='upr-ns'>{escape(rec.get('name') or '')}</td>"
            f"<td class='upr-num'>{funding}</td>"
            f"{''.join(dots)}"
            "</tr>"
        )
    total = payload.get("support_total") or {}
    total_display = escape((total.get("display") or "").strip() or format_compact_chf(total.get("value")) or "0")
    return (
        f"<section class='upr-block'><h2 class='upr-block__title'>{title}</h2>"
        "<table class='upr-support-table'>"
        "<colgroup>"
        "<col class='upr-support-col-ns'>"
        "<col class='upr-support-col-num'>"
        f"<col class='upr-support-col-dot' span='{n_areas}'>"
        "</colgroup>"
        "<thead><tr>"
        "<th class='upr-ns'></th>"
        f"<th class='upr-support-th'><span>{funding_label}</span></th>"
        f"{headers}</tr></thead><tbody>{''.join(body)}</tbody>"
        "<tfoot>"
        "<tr class='upr-support-total-row'>"
        "<td class='upr-ns'>Total</td>"
        f"<td class='upr-num upr-support-total'>CHF {total_display}</td>"
        f"<td colspan='{n_areas}'></td>"
        "</tr></tfoot></table></section>"
    )


def _strategic_priorities(payload: dict[str, Any]) -> str:
    rows = payload.get("core_indicators") or []
    body = _bars_grouped(rows, SP_CODES) if rows else "<p class='upr-empty'>No core indicators reported.</p>"
    return (
        "<section class='upr-block upr-block--bars'>"
        "<h2 class='upr-block__title'>Strategic Priorities</h2>"
        f"{body}</section>"
    )


def _enabling_functions(payload: dict[str, Any]) -> str:
    rows = payload.get("enabling_indicators") or []
    body = _bars_grouped(rows, EF_CODES) if rows else "<p class='upr-empty'>No enabling-function indicators reported.</p>"
    return (
        "<section class='upr-block upr-block--bars'>"
        "<h2 class='upr-block__title'>Enabling Functions</h2>"
        f"{body}</section>"
    )


def _emergency(payload: dict[str, Any], slot: int) -> str:
    match = next((em for em in payload.get("emergencies") or [] if int(em.get("slot") or 0) == slot), None)
    if not match:
        return (
            f"<section class='upr-block'><h2 class='upr-block__title'>Emergency {slot}</h2>"
            "<p class='upr-empty'>No emergency appeal selected for this slot.</p></section>"
        )
    name = escape(match.get("name") or f"Emergency {slot}")
    code = escape(match.get("code") or "")
    indicators = match.get("indicators") or []
    numeric = [row for row in indicators if row.get("kind") != "yesno" and row.get("value")]
    yesno = [row for row in indicators if row.get("kind") == "yesno"]
    grouped = _bars_grouped(numeric, (*SP_CODES, *EF_CODES, "EO")) if numeric else ""
    if numeric and not grouped:
        grouped = _hbar_chart(numeric, color=IFRC_RED)
    yes_html = ""
    if yesno:
        yes_html = _hbar_chart(yesno)
    code_html = f" <span class='upr-code'>{code}</span>" if code else ""
    return (
        "<section class='upr-block upr-block--emergency'>"
        f"<h2 class='upr-block__title'>{name}{code_html}</h2>"
        f"{grouped}{yes_html}"
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
    chunks = []
    for code in order:
        group = by_code.get(code) or []
        if not group:
            continue
        chunks.append(
            "<div class='upr-bar-group'>"
            f"<div class='upr-bar-group__title'>{escape(AREA_LABELS.get(code, code))}</div>"
            f"{_hbar_chart(group, color=IFRC_RED)}"
            "</div>"
        )
    if leftover:
        chunks.append(_hbar_chart(leftover, color=IFRC_RED))
    return "".join(chunks)


def _bar_plot(row: dict[str, Any], *, color: str, scale: float) -> str:
    display = _metric_html(row.get("display"))
    value = float(row.get("value") or 0)
    fill = row.get("color") or color
    if row.get("kind") == "yesno" or not value:
        return f"<div class='upr-bar-yes'>{display}</div>"
    pct = max(3.0, min(100.0, value / scale * 100)) if value else 0.0
    return (
        "<div class='upr-bar-track'>"
        f"<span class='upr-bar-fill' style='width:{pct:.1f}%;background:{fill}'></span>"
        f"<span class='upr-bar-value'>{display}</span>"
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
    scale = float(peak) if peak else max((float(row.get("value") or 0) for row in rows), default=0) or 1
    parts = []
    for row in rows:
        label = escape(row.get("label") or "")
        value = float(row.get("value") or 0)
        extra = " upr-bar-row--text" if row.get("kind") == "yesno" or not value else ""
        parts.append(
            f"<tr class='upr-bar-row{extra}'>"
            f"<td class='upr-bar-label'>{label}</td>"
            f"<td class='upr-bar-plot'>{_bar_plot(row, color=row.get('color') or color, scale=scale)}</td>"
            "</tr>"
        )
    return f"<table class='upr-bars'><tbody>{''.join(parts)}</tbody></table>"
