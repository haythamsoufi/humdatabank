"""Assemble a Tableau-shaped UPR visual payload from live assignment FormData."""

from __future__ import annotations

from typing import Any

from app.models.assignments import AssignmentEntityStatus
from app.models.form_items import FormItem
from app.models.forms import FormData
from app.utils.api_serialization import _country_for_aes
from plugins.upr_visuals.bulk import (
    get_assigned_form_for_bulk,
    list_assigned_forms_for_bulk,
    list_countries_for_bulk,
)
from plugins.upr_visuals.catalog import (
    EF_CODES,
    KPI_BANK_IDS,
    KPI_LABELS,
    KPI_ORDER,
    PLAN_KPI_LABELS,
    PLAN_KPI_ORDER,
    SP_CODES,
    dashboards_for_kind,
    display_ns_name,
    kind_for_template,
)
from plugins.upr_visuals.errors import UprVisualsError, assignment_supports_visuals
from plugins.upr_visuals.financial import (
    _plan_financial,
    _report_financial,
    _usable_ifrc_actual,
    build_report_network_entities,
    ifrc_secretariat_actuals_for_report,
)
from plugins.upr_visuals.formatters import (
    document_subtitle,
    format_count,
    format_header_date,
    period_to_round,
    planning_years,
)
from plugins.upr_visuals.icons import (
    _load_spef_catalog_rows,
    _ns_logo_src,
    _set_spef_icon_mode,
    _spef_catalog_icon_url,
    _spef_icon_alias,
    spef_icon_srcs,
)
from plugins.upr_visuals.indicators import (
    _report_emergencies,
    _report_indicator_rows,
    _section_is_other_indicators,
    _section_is_overall_action,
    _split_appeal_label,
)
from plugins.upr_visuals.loaders import (
    _load_aes,
    _load_dynamic_indicator_rows,
    _load_entries,
    _load_items,
)
from plugins.upr_visuals.matrix import (
    _funding_column_bucket,
    _funding_entity,
    _matrix_cells,
    _scalar_number,
    _split_cell_key,
    _sum_funding_by_area,
    _sum_funding_by_bucket,
    _sum_funding_rows,
)
from plugins.upr_visuals.people_reached import (
    _plan_people_reached,
    _reach_rows,
    _report_people_reached,
    max_people_by_area,
    override_people_reached_area,
)
from plugins.upr_visuals.pns_funding import (
    pns_area_funding_from_plan_cells,
    pns_funding_from_plan_cells,
    sum_t23_host_cells,
    t22_host_funding_by_pns,
    t23_host_funding_by_pns,
)
from plugins.upr_visuals.support import (
    _apply_support_funding,
    _expand_plan_support_years,
    _extend_support_with_funding,
    _ns_names,
    _plan_support,
    _report_support,
    _support_from_cells,
    support_total_from_rows,
)

__all__ = [
    "UprVisualsError",
    "assignment_supports_visuals",
    "build_payload",
    "filename_from_visual_title",
    "get_assigned_form_for_bulk",
    "list_assigned_forms_for_bulk",
    "list_countries_for_bulk",
    "visuals_browser_title",
    "visuals_document_title",
]


def visuals_document_title(*, country_name: str | None, assignment_title: str | None) -> str:
    """Same string as the live PDF tab title (country — assignment)."""
    parts = [
        part
        for part in ((country_name or "").strip(), str(assignment_title or "").strip())
        if part
    ]
    return " — ".join(parts) or "UPR visuals"


def visuals_browser_title(aes: AssignmentEntityStatus) -> str:
    """Tab title for the live assignment PDF viewer."""
    country = _country_for_aes(aes)
    assigned = aes.assigned_form
    return visuals_document_title(
        country_name=getattr(country, "name", None),
        assignment_title=assigned.display_name if assigned else "",
    )


def filename_from_visual_title(title: str, ext: str = "pdf") -> str:
    """ASCII download name matching the PDF page title (HTTP headers are latin-1)."""
    raw = (title or "").strip() or "UPR visuals"
    raw = raw.replace("\u2014", " - ").replace("\u2013", "-")
    for char in '<>:"/\\|?*':
        raw = raw.replace(char, " ")
    raw = raw.encode("ascii", "ignore").decode("ascii")
    raw = " ".join(raw.split()) or "UPR visuals"
    suffix = ext.lstrip(".").lower() or "pdf"
    return f"{raw}.{suffix}"


def build_payload(aes_id: int, *, inline_icons: bool = False) -> dict[str, Any]:
    _set_spef_icon_mode(inline=inline_icons)
    aes = _load_aes(aes_id)
    assigned = aes.assigned_form
    template_id = int(assigned.template_id)
    kind = kind_for_template(template_id)
    country = _country_for_aes(aes)
    ns = getattr(country, "primary_national_society", None) if country else None
    period_name = assigned.period_name or ""
    items = _load_items(assigned.template)
    entries = _load_entries(aes.id)
    by_item = {row.form_item_id: row for row in entries}

    payload: dict[str, Any] = {
        "meta": {
            "aes_id": aes.id,
            "template_id": template_id,
            "kind": kind,
            "period_name": period_name,
            "round_code": period_to_round(period_name, kind),
            "country_name": country.name if country else "",
            "iso3": country.iso3 if country else "",
            "iso2": country.iso2 if country else "",
            "document_title": visuals_document_title(
                country_name=country.name if country else "",
                assignment_title=assigned.display_name,
            ),
            "national_society": display_ns_name(ns.name if ns else country.name if country else ""),
            "year": (planning_years(period_name) or [None])[0],
            "header_date": format_header_date(),
            "document_subtitle": document_subtitle(kind, period_name),
            "ns_logo_src": _ns_logo_src(
                ns,
                country.iso3 if country else "",
                inline=inline_icons,
            ),
        },
        "kpis": _build_kpis(items, by_item, kind=kind),
        "people_reached": [],
        "financial": {"ifrc_network": {}, "sources": [], "years": []},
        "support": [],
        "core_indicators": [],
        "enabling_indicators": [],
        "emergencies": [],
        "dashboards": [],
    }

    if kind == "plan":
        payload["people_reached"] = _plan_people_reached(items, by_item, period_name)
        payload["financial"] = _plan_financial(items, by_item, period_name)
        payload["support"] = _plan_support(
            items,
            by_item,
            period_name=period_name,
            country_id=country.id if country else None,
        )
        payload["meta"]["people_title"] = (
            f"People to be reached in {payload['meta']['year']}"
            if payload["meta"].get("year")
            else "People to be reached"
        )
        payload["meta"]["support_title"] = "Participating National Societies bilateral support"
        payload["meta"]["support_funding_label"] = "Funding Requirement"
        payload["meta"]["support_confirmed_label"] = "Confirmed Funding"
        payload["meta"]["header_prefix"] = "In support of"
        payload["meta"]["plan_years"] = planning_years(period_name)
    else:
        payload["people_reached"] = _report_people_reached(items, by_item, aes.id)
        payload["financial"] = _report_financial(
            items,
            by_item,
            country_id=country.id if country else None,
            host_ns_id=ns.id if ns else None,
            period_name=period_name,
            iso2=country.iso2 if country else None,
            iso3=country.iso3 if country else None,
        )
        payload["support"] = _report_support(
            items,
            by_item,
            host_ns_id=ns.id if ns else None,
            host_country_id=country.id if country else None,
            period_name=period_name,
            year=payload["meta"].get("year"),
        )
        payload["emergencies"] = _report_emergencies(aes.id, items)
        payload["core_indicators"] = _report_indicator_rows(
            items, by_item, SP_CODES, bars_only=True, aes_id=aes.id
        )
        payload["enabling_indicators"] = _report_indicator_rows(
            items, by_item, EF_CODES, bars_only=False, aes_id=aes.id
        )
        payload["meta"]["people_title"] = "People reached"
        payload["meta"]["support_title"] = "IFRC Network-Supported Activities"
        payload["meta"]["support_funding_label"] = "Funding Reported"
        payload["meta"]["header_prefix"] = "IN SUPPORT OF"

    payload["support_total"] = support_total_from_rows(payload.get("support") or [])
    emergency_slots = {int(em.get("slot") or 0) for em in payload.get("emergencies") or []}
    payload["dashboards"] = [
        {
            "id": spec.id,
            "title": _dashboard_title(spec, kind),
            "description": spec.description,
            "width": spec.width,
            "height": spec.height,
        }
        for spec in dashboards_for_kind(kind, emergency_slots=emergency_slots)
    ]

    return payload


def _dashboard_title(spec, kind: str) -> str:
    if kind == "plan" and getattr(spec, "plan_title", None):
        return spec.plan_title
    return spec.title


def _build_kpis(items: list[FormItem], by_item: dict[int, FormData], *, kind: str = "report") -> dict[str, Any]:
    bank_to_item: dict[int, FormItem] = {}
    for item in items:
        bank_id = getattr(item, "indicator_bank_id", None)
        if bank_id in KPI_BANK_IDS.values() and bank_id not in bank_to_item:
            bank_to_item[int(bank_id)] = item

    labels = PLAN_KPI_LABELS if kind == "plan" else KPI_LABELS
    order = PLAN_KPI_ORDER if kind == "plan" else KPI_ORDER
    kpis = {}
    for key in order:
        bank_id = KPI_BANK_IDS[key]
        item = bank_to_item.get(bank_id)
        entry = by_item.get(item.id) if item else None
        number = _scalar_number(entry)
        kpis[key] = {
            "key": key,
            "label": labels[key],
            "value": number,
            "display": format_count(number) if number is not None else "Not reported",
            "icon": key,
        }
    return kpis
