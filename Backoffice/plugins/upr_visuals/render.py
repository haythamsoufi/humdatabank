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
    SP_CODES,
    SUPPORT_AREA_CODES,
)
from plugins.upr_visuals.formatters import format_chf, format_compact_chf

IFRC_RED = "#d22730"
_NOT_REPORTED = "Not reported"


def _metric_html(text: str | None, *, fallback: str = _NOT_REPORTED) -> str:
    raw = (text or "").strip() or fallback
    if raw.lower() == "not reported":
        return f'<span class="upr-not-reported">{escape(raw)}</span>'
    return escape(raw)

_KPI_SVG_PATHS = {
    "branches": (
        '<rect x="4" y="8" width="16" height="12" rx="1"/>'
        '<path d="M8 8V6h8v2M12 12v8"/>'
        '<path d="M8 14h2M14 14h2"/>'
    ),
    "local_units": (
        '<path d="M12 21s7-5.4 7-11a7 7 0 1 0-14 0c0 5.6 7 11 7 11z"/>'
        '<circle cx="12" cy="10" r="2.2"/>'
    ),
    "volunteers": (
        '<circle cx="9" cy="8" r="2.4"/><path d="M3.6 19v-1.4c0-2.2 2.2-3.8 5.4-3.8"/>'
        '<circle cx="16" cy="8" r="2.4"/><path d="M20.4 19v-1.4c0-2.2-2.2-3.8-5.4-3.8"/>'
    ),
    "staff": (
        '<circle cx="12" cy="8" r="2.6"/><path d="M6 20v-1.6c0-2.5 2.5-4.2 6-4.2s6 1.7 6 4.2V20"/>'
        '<path d="M12 13.2v2.4"/>'
    ),
}

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
    inner = _KPI_SVG_PATHS.get(key, '<circle cx="12" cy="12" r="8"/>')
    return (
        f'<svg class="upr-kpi__icon" viewBox="0 0 24 24" width="32" height="32" '
        f'aria-hidden="true" fill="none" stroke="{IFRC_RED}" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round">{inner}</svg>'
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
        f'<svg class="upr-reach-icon" viewBox="0 0 40 40" width="52" height="52" aria-hidden="true">'
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


def _combined(payload: dict[str, Any]) -> str:
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
    ns = escape((meta.get("national_society") or "").upper())
    kpis = payload.get("kpis") or {}
    cards = []
    for key in KPI_ORDER:
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
        f"<h2 class='upr-block__title'>IN SUPPORT OF {ns}</h2>"
        f"<div class='upr-kpi-row'>{''.join(cards)}</div>"
        "</section>"
    )


def _reach(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    title = escape((meta.get("people_title") or "People reached").upper())
    rows = payload.get("people_reached") or []
    labels: list[str] = []
    icons: list[str] = []
    values: list[str] = []
    for row in rows:
        if not row.get("has_value"):
            continue
        code = row.get("code") or ""
        labels.append(f"<div class='upr-reach-label'>{escape(row.get('label') or '')}</div>")
        icons.append(
            f"<div class='upr-reach-icon-wrap'>{_sp_icon(code, row.get('icon_src'))}</div>"
        )
        values.append(f"<div class='upr-reach-value'>{_metric_html(row.get('display'), fallback='')}</div>")
    if not labels:
        body = "<p class='upr-empty'>No people-reached figures reported.</p>"
    else:
        body = (
            "<div class='upr-reach-row'>"
            f"<div class='upr-reach-band upr-reach-band--labels'>{''.join(labels)}</div>"
            f"<div class='upr-reach-band upr-reach-band--icons'>{''.join(icons)}</div>"
            f"<div class='upr-reach-band upr-reach-band--values'>{''.join(values)}</div>"
            "</div>"
        )
    return (
        f"<section class='upr-block upr-block--reach'><h2 class='upr-block__title'>{title}</h2>"
        f"{body}</section>"
    )


def _financial(payload: dict[str, Any]) -> str:
    fin = payload.get("financial") or {}
    network = fin.get("ifrc_network") or {}
    ns_block = fin.get("national_society") or {}
    sources = list(fin.get("sources") or [])
    years = fin.get("years") or []
    entities = fin.get("network_entities") or []
    kind = (payload.get("meta") or {}).get("kind")
    ns_name = escape((payload.get("meta") or {}).get("national_society") or "")

    overview_rows = []
    if kind == "plan":
        overview_rows.append(
            {
                "label": "Funding requirement",
                "display": network.get("funding_requirement_display") or "Not reported",
                "value": network.get("funding_requirement") or 0,
                "color": AREA_COLORS["funding_requirement"],
            }
        )
    else:
        overview_rows.append(
            {
                "label": "Funding",
                "display": ns_block.get("funding_display") or network.get("funding_display") or "Not reported",
                "value": ns_block.get("funding") or network.get("funding") or 0,
                "color": AREA_COLORS["funding"],
            }
        )
        overview_rows.append(
            {
                "label": "Expenditure",
                "display": ns_block.get("expenditure_display") or network.get("expenditure_display") or "Not reported",
                "value": ns_block.get("expenditure") or network.get("expenditure") or 0,
                "color": AREA_COLORS["expenditure"],
            }
        )

    source_rows = [
        {
            "label": src.get("label") or src.get("entity") or "",
            "display": src.get("display") or format_compact_chf(src.get("value")) or "Not reported",
            "value": src.get("value") or 0,
            "color": AREA_COLORS["source"],
        }
        for src in sources
    ]

    ns_heading = f"<div class='upr-fin-ns'>{ns_name}</div>" if ns_name and kind == "report" else ""
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
        f"<tr class='upr-support-total-gap'><td colspan='{n_areas + 2}'></td></tr>"
        "<tr>"
        "<td class='upr-ns'></td>"
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
    return (
        "<section class='upr-block upr-block--emergency'>"
        f"<h2 class='upr-block__title'>{name}"
        f"{f' <span class=\"upr-code\">{code}</span>' if code else ''}</h2>"
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
