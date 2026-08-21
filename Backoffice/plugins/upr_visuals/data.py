"""Assemble a Tableau-shaped UPR visual payload from live assignment FormData."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.assignments import AssignedForm, AssignmentEntityStatus
from app.models.form_items import FormItem
from app.models.forms import DynamicIndicatorData, FormData, FormSection, RepeatGroupInstance
from app.models.organization import NationalSociety
from app.utils.api_serialization import _country_for_aes, _resolve_matrix_cell
from plugins.upr_visuals.catalog import (
    AREA_LABELS,
    FUNDING_ENTITY_LABELS,
    KPI_BANK_IDS,
    KPI_LABELS,
    KPI_ORDER,
    OTHER_INDICATORS_SECTION_NAME,
    OVERALL_ACTION_SECTION_NEEDLE,
    PLAN_ITEM_FALLBACKS,
    PLAN_KPI_LABELS,
    PLAN_LABEL_NEEDLES,
    PLAN_TEMPLATE_ID,
    PLANNING_EA_FUNDING_AREAS,
    PNS_PLAN_ITEM_FALLBACKS,
    PNS_PLAN_LABEL_NEEDLES,
    PNS_PLAN_TEMPLATE_ID,
    PNS_REPORT_LABEL_NEEDLES,
    PNS_REPORT_TEMPLATE_ID,
    REACH_CODES,
    REACH_DROP_LONG_TERM_NEEDLES,
    REACH_EMERGENCY_BANK_ID,
    REACH_EMERGENCY_TO_SP2_NEEDLES,
    REPORT_ITEM_FALLBACKS,
    REPORT_LABEL_NEEDLES,
    REPORTING_SP_BREAKDOWN_AREA_TO_ROW,
    SP_CODES,
    EF_CODES,
    SUPPORT_AREA_CODES,
    UPR_VISUAL_TEMPLATE_IDS,
    dashboards_for_kind,
    display_ns_name,
    kind_for_template,
    section_to_area,
)
from plugins.upr_visuals.formatters import (
    format_chf,
    format_compact_chf,
    format_count,
    format_header_date,
    period_to_round,
    planning_years,
    to_number,
    _year_token,
    document_subtitle,
)

logger = logging.getLogger(__name__)

_PLUGIN_DIR = Path(__file__).resolve().parent
_MYR26_IFRC_ACTUALS_PATH = _PLUGIN_DIR / "snapshots" / "myr26_ifrc_secretariat_actuals.json"
# Snapshot overlay: drop noise, rounding crumbs, and negative IFRC actuals.
_IFRC_ACTUALS_MIN_CHF = 1000.0
# EO is not an SP/EF catalog code; use the plugin asset instead of the indicator bank.
_PLUGIN_REACH_ICONS = {
    "EO": "icons/eo-emergency.png",
    "CC1": "icons/cc1-cross-cutting.png",
    "SP1": "icons/sp1-climate.png",
    "SP2": "icons/sp2-disasters.png",
    "SP3": "icons/sp3-health.png",
    "SP4": "icons/sp4-migration.png",
    "SP5": "icons/sp5-inclusion.png",
}


class UprVisualsError(ValueError):
    """Raised when an assignment cannot produce UPR visuals."""


def assignment_supports_visuals(aes: AssignmentEntityStatus | None) -> bool:
    if not aes or not aes.assigned_form:
        return False
    return int(aes.assigned_form.template_id or 0) in UPR_VISUAL_TEMPLATE_IDS


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
    if kind != "plan":
        return spec.title
    if spec.id == "financial":
        return "Funding requirements"
    if spec.id == "reach":
        return "People to be reached"
    if spec.id == "support":
        return "Bilateral support"
    if spec.id == "network_funding":
        return "Network-supported activities"
    return spec.title


def _load_aes(aes_id: int) -> AssignmentEntityStatus:
    aes = (
        AssignmentEntityStatus.query.options(
            joinedload(AssignmentEntityStatus.assigned_form).joinedload(AssignedForm.template),
        )
        .filter_by(id=int(aes_id))
        .first()
    )
    if not aes:
        raise UprVisualsError("Assignment not found.")
    if not assignment_supports_visuals(aes):
        raise UprVisualsError("UPR visuals are only available for Unified Plan and Report assignments.")
    return aes


def _indicator_bank_options(root):
    from app.models.indicator_bank import IndicatorBank

    return joinedload(root).joinedload(IndicatorBank.spef_area)


def _load_dynamic_indicator_rows(aes_id: int) -> list[DynamicIndicatorData]:
    query = DynamicIndicatorData.query.options(
        _indicator_bank_options(DynamicIndicatorData.indicator_bank),
        joinedload(DynamicIndicatorData.section),
    ).filter(DynamicIndicatorData.assignment_entity_status_id == aes_id)
    try:
        return query.all()
    except Exception:
        db.session.rollback()
        logger.debug("UPR visuals: falling back to dynamic rows without SPEF catalog join", exc_info=True)
        return (
            DynamicIndicatorData.query.options(
                joinedload(DynamicIndicatorData.indicator_bank),
                joinedload(DynamicIndicatorData.section),
            )
            .filter(DynamicIndicatorData.assignment_entity_status_id == aes_id)
            .all()
        )


def _section_load_options():
    return joinedload(FormItem.form_section).joinedload(FormSection.parent_section)


def _load_items(template) -> list[FormItem]:
    version_id = getattr(template, "published_version_id", None) if template else None
    if not version_id:
        return []
    query = FormItem.query.options(
        _section_load_options(),
        _indicator_bank_options(FormItem.indicator_bank),
    ).filter(FormItem.version_id == version_id, FormItem.archived.is_(False))
    try:
        return query.all()
    except Exception:
        db.session.rollback()
        logger.debug("UPR visuals: falling back to items without SPEF catalog join", exc_info=True)
        return (
            FormItem.query.options(
                _section_load_options(),
                joinedload(FormItem.indicator_bank),
            )
            .filter(FormItem.version_id == version_id, FormItem.archived.is_(False))
            .all()
        )


def _load_entries(aes_id: int) -> list[FormData]:
    return FormData.query.filter_by(assignment_entity_status_id=aes_id).all()


def _build_kpis(items: list[FormItem], by_item: dict[int, FormData], *, kind: str = "report") -> dict[str, Any]:
    bank_to_item: dict[int, FormItem] = {}
    for item in items:
        bank_id = getattr(item, "indicator_bank_id", None)
        if bank_id in KPI_BANK_IDS.values() and bank_id not in bank_to_item:
            bank_to_item[int(bank_id)] = item

    labels = PLAN_KPI_LABELS if kind == "plan" else KPI_LABELS
    kpis = {}
    for key in KPI_ORDER:
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


def _plan_people_reached(items, by_item, period_name: str) -> list[dict[str, Any]]:
    years = planning_years(period_name)
    year0 = str(years[0]) if years else ""
    longer = _resolve_item(items, PLAN_LABEL_NEEDLES["reach_longer_term"], PLAN_ITEM_FALLBACKS["reach_longer_term"])
    emergency = _resolve_item(items, PLAN_LABEL_NEEDLES["reach_emergency"], PLAN_ITEM_FALLBACKS["reach_emergency"])
    cells = _matrix_cells(by_item.get(longer.id) if longer else None)
    by_code: dict[str, float] = {}
    headline = 0.0
    for key, raw in cells.items():
        number = to_number(_resolve_matrix_cell(raw))
        if number is None:
            continue
        row, col = _split_cell_key(key)
        if year0 and row != year0 and col != year0 and not key.startswith(f"{year0}_"):
            continue
        row_l = (row or "").strip().lower()
        col_l = (col or "").strip().lower()
        if col_l in {"total", "row_total"} or row_l in {"total", "row_total"}:
            if col_l in {"total", "row_total"} and row_l in {"total", "row_total"}:
                continue
            headline = max(headline, number)
            continue
        code = _area_code(col) or _area_code(row) or section_to_area(col) or section_to_area(row)
        if code in SP_CODES:
            by_code[code] = by_code.get(code, 0) + number

    eo_total = 0.0
    eo_cells = _matrix_cells(by_item.get(emergency.id) if emergency else None)
    for raw in eo_cells.values():
        number = to_number(_resolve_matrix_cell(raw))
        if number:
            eo_total += number
    if eo_total:
        by_code["EO"] = eo_total

    rows = _reach_rows(by_code)
    if headline:
        rows.insert(
            0,
            {
                "code": "TOTAL",
                "label": "People to be reached",
                "value": headline,
                "display": format_count(headline),
                "has_value": True,
                "icon_src": "",
                "is_total": True,
            },
        )
    return rows


def _report_people_reached(items, by_item, aes_id: int | None = None) -> list[dict[str, Any]]:
    """Highest people-count indicator per Strategic Priority and EO.

    Matches Tableau People Reached ``MAX`` of unit=People / type=Number values.
    Temporary: Cross-cutting is hidden; emergency-response reach counts under
    Disasters and crises (SP2); long-term services reach is dropped.
    """
    candidates: list[tuple[str, float]] = []
    for item in items:
        bank = getattr(item, "indicator_bank", None)
        if not _is_people_count(bank):
            continue
        area = override_people_reached_area(
            _area_from_item(item),
            bank=bank,
            label=getattr(item, "label", None),
        )
        if area not in REACH_CODES:
            continue
        number = _scalar_number(by_item.get(item.id))
        if number is None:
            continue
        candidates.append((area, number))
    if aes_id:
        dyn_rows = _load_dynamic_indicator_rows(aes_id)
        for dyn in dyn_rows:
            bank = getattr(dyn, "indicator_bank", None)
            if not _is_people_count(bank):
                continue
            area = override_people_reached_area(
                "EO" if dyn.repeat_instance_number else _bank_area(bank),
                bank=bank,
                label=getattr(dyn, "custom_label", None),
            )
            if area not in REACH_CODES:
                continue
            number = _scalar_number(dyn)
            if number is None:
                continue
            candidates.append((area, number))
    return _reach_rows(max_people_by_area(candidates))


def override_people_reached_area(area: str | None, *, bank=None, label: str | None = None) -> str | None:
    """Temporary People reached remapping for Cross-cutting indicators."""
    text = " ".join(part for part in (label, getattr(bank, "name", None)) if part).strip().lower()
    bank_id = getattr(bank, "id", None)
    if any(needle in text for needle in REACH_DROP_LONG_TERM_NEEDLES):
        return None
    if bank_id == REACH_EMERGENCY_BANK_ID or any(needle in text for needle in REACH_EMERGENCY_TO_SP2_NEEDLES):
        return "SP2"
    return area


def max_people_by_area(candidates: list[tuple[str, float]]) -> dict[str, float]:
    """Keep the highest people-count value per reach area."""
    best: dict[str, float] = {}
    for area, number in candidates:
        if area not in REACH_CODES or number is None:
            continue
        if area not in best or number > best[area]:
            best[area] = number
    return best


def _is_people_count(bank) -> bool:
    if bank is None:
        return False
    unit = (getattr(bank, "unit", None) or "").strip().lower()
    meas = (getattr(bank, "type", None) or "").strip().lower()
    if meas in {"yesno", "yes/no", "boolean", "percentage", "percent"}:
        return False
    if "people" not in unit and unit not in {"person", "persons"}:
        return False
    return meas in {"number", "count", ""}


def _section_is_overall_action(section) -> bool:
    """True when section (or an ancestor) is the T33 Overall Action Indicators block."""
    current = section
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = (getattr(current, "name", None) or "").strip().lower()
        if OVERALL_ACTION_SECTION_NEEDLE in name:
            return True
        current = getattr(current, "parent_section", None)
    return False


def _section_is_other_indicators(section) -> bool:
    name = (getattr(section, "name", None) or "").strip().lower()
    stype = (getattr(section, "section_type", None) or "").strip().lower()
    return name == OTHER_INDICATORS_SECTION_NAME and stype == "dynamic_indicators"


def _indicator_visual_row(area: str, label: str, meas: str, entry, *, bars_only: bool) -> dict[str, Any] | None:
    if meas in {"yesno", "yes/no", "boolean"}:
        if bars_only:
            return None
        flag = _yes_no(entry)
        if flag is None:
            return None
        return {
            "code": area,
            "label": label,
            "value": 1.0 if flag else 0.0,
            "display": "Yes" if flag else "No",
            "kind": "yesno",
        }
    if meas in {"percentage", "percent"}:
        return None
    number = _scalar_number(entry)
    if not number:
        return None
    return {
        "code": area,
        "label": label,
        "value": number,
        "display": format_count(number),
        "kind": "number",
    }


def _report_indicator_rows(
    items: list[FormItem],
    by_item: dict[int, FormData],
    areas: tuple[str, ...],
    *,
    bars_only: bool,
    aes_id: int | None = None,
) -> list[dict[str, Any]]:
    """Overall Action core indicators plus Other Indicators dynamics (not Key Data / Funding / EA)."""
    rows: list[dict[str, Any]] = []
    for item in items:
        if not _section_is_overall_action(getattr(item, "form_section", None)):
            continue
        bank = getattr(item, "indicator_bank", None)
        if not bank:
            continue
        area = _area_from_item(item)
        if area not in areas:
            continue
        meas = (getattr(bank, "type", None) or "").strip().lower()
        label = (getattr(bank, "name", None) or item.label or "").strip()
        row = _indicator_visual_row(area, label, meas, by_item.get(item.id), bars_only=bars_only)
        if row:
            rows.append(row)
    if aes_id:
        for dyn in _load_dynamic_indicator_rows(aes_id):
            if dyn.repeat_instance_number:
                continue
            if not _section_is_other_indicators(getattr(dyn, "section", None)):
                continue
            bank = getattr(dyn, "indicator_bank", None)
            if not bank:
                continue
            area = _bank_area(bank)
            if area not in areas:
                continue
            meas = (getattr(bank, "type", None) or "").strip().lower()
            label = (dyn.custom_label or getattr(bank, "name", None) or "").strip()
            row = _indicator_visual_row(area, label, meas, dyn, bars_only=bars_only)
            if row:
                rows.append(row)
    rows.sort(key=lambda row: (areas.index(row["code"]) if row["code"] in areas else 99, -(row.get("value") or 0)))
    return rows


def _yes_no(entry) -> bool | None:
    if entry is None:
        return None
    if getattr(entry, "data_not_available", False) or getattr(entry, "not_applicable", False):
        return None
    getter = getattr(entry, "get_display_value", None)
    raw = getter() if callable(getter) else getattr(entry, "value", None)
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text in {"yes", "true", "1", "y"}:
        return True
    if text in {"no", "false", "0", "n"}:
        return False
    number = to_number(raw)
    if number is None:
        return None
    return bool(number)


def _reach_rows(by_code: dict[str, float]) -> list[dict[str, Any]]:
    icons = spef_icon_srcs()
    rows = []
    for code in REACH_CODES:
        number = by_code.get(code)
        rows.append(
            {
                "code": code,
                "label": AREA_LABELS[code],
                "value": number,
                "display": format_count(number) if number is not None else "",
                "has_value": number is not None,
                "icon_src": icons.get(code) or icons.get(_spef_icon_alias(code)),
            }
        )
    return rows


def _spef_icon_alias(code: str) -> str:
    upper = (code or "").strip().upper()
    if upper == "CC1":
        return "CC"
    if upper == "EFS":
        return "EF1"
    return upper


def _set_spef_icon_mode(*, inline: bool) -> None:
    try:
        from flask import g, has_app_context

        if has_app_context():
            g._upr_inline_spef_icons = bool(inline)
            for attr in ("_upr_spef_icon_srcs", "_upr_spef_icon_srcs_inline"):
                if hasattr(g, attr):
                    delattr(g, attr)
    except Exception:
        pass


def _inline_spef_icons() -> bool:
    try:
        from flask import g, has_app_context

        if has_app_context():
            return bool(getattr(g, "_upr_inline_spef_icons", False))
    except Exception:
        pass
    return False


def _load_spef_catalog_rows():
    """Active SPEF catalog rows — same source as the indicator-bank wizard."""
    from app.models.indicator_bank import IndicatorBankSpef

    return (
        IndicatorBankSpef.query.filter(IndicatorBankSpef.is_active.is_(True))
        .order_by(IndicatorBankSpef.sort_order, IndicatorBankSpef.code)
        .all()
    )


def _spef_catalog_icon_url(row) -> str:
    """Browser URL used by the indicator bank and assignment Visuals."""
    from app.utils.sector_logo_urls import spef_icon_url

    try:
        return spef_icon_url(row, via_api=True) or spef_icon_url(row) or ""
    except Exception:
        try:
            return spef_icon_url(row) or ""
        except Exception:
            return ""


def _inline_local_icon(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        import base64
        import mimetypes

        data = path.read_bytes()
        if not data:
            return ""
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    except Exception:
        return ""


def _plugin_reach_icon_src(code: str, *, inline: bool) -> str:
    rel = _PLUGIN_REACH_ICONS.get((code or "").strip().upper())
    if not rel:
        return ""
    path = _PLUGIN_DIR / "static" / rel
    if inline:
        return _inline_local_icon(path)
    if not path.is_file():
        return ""
    try:
        from flask import url_for

        return url_for("upr_visuals.static_file", filename=rel)
    except Exception:
        return f"/upr-visuals/static/{rel}"


def _inline_spef_icon(row) -> str:
    filename = (getattr(row, "icon_filename", None) or "").strip()
    if not filename:
        return ""
    try:
        import base64
        import mimetypes

        from app.services.platform import storage_service as storage

        data = storage.download(storage.SYSTEM, f"spef/{filename}")
        if not data:
            return ""
        mime = mimetypes.guess_type(filename)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    except Exception:
        return ""


def _inline_ns_logo(filename: str) -> str:
    name = (filename or "").strip()
    if not name:
        return ""
    try:
        import base64
        import mimetypes

        from app.services.platform import storage_service as storage

        data = storage.download(storage.SYSTEM, f"ns/{name}")
        if not data:
            return ""
        mime = mimetypes.guess_type(name)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    except Exception:
        return ""


def _ns_logo_src(ns, iso3: str, *, inline: bool = False) -> str:
    """Stored NS logo, else the public FDRS GitHub file for this ISO3."""
    filename = (getattr(ns, "logo_filename", None) or "").strip() if ns else ""
    if inline and filename:
        data_uri = _inline_ns_logo(filename)
        if data_uri:
            return data_uri
    if ns:
        try:
            from app.utils.sector_logo_urls import ns_logo_url

            url = ns_logo_url(ns, via_api=True) or ns_logo_url(ns)
            if url:
                return url
        except Exception:
            try:
                from app.utils.sector_logo_urls import ns_logo_url

                url = ns_logo_url(ns) or ""
                if url:
                    return url
            except Exception:
                pass
    try:
        from app.utils.sector_logo_urls import github_ns_logo_url

        return github_ns_logo_url(iso3) or ""
    except Exception:
        return ""


def _remember_spef_icon(out: dict[str, str], code: str, src: str) -> None:
    out[code] = src
    alias = _spef_icon_alias(code)
    if alias != code:
        out.setdefault(alias, src)
    if code == "CC":
        out.setdefault("CC1", src)


def spef_icon_srcs(*, inline: bool | None = None) -> dict[str, str]:
    """Map SPEF catalog codes to icon src from the indicator bank.

    Browser preview and assignment Visuals use ``spef_icon_url`` (same helper as
    the indicator-bank SPEF catalog). PNG/PDF export can request data URIs.
    """
    use_inline = _inline_spef_icons() if inline is None else bool(inline)
    cache_attr = "_upr_spef_icon_srcs_inline" if use_inline else "_upr_spef_icon_srcs"
    try:
        from flask import g, has_app_context

        cached = getattr(g, cache_attr, None) if has_app_context() else None
        if isinstance(cached, dict):
            return cached
    except Exception:
        pass

    out: dict[str, str] = {}
    try:
        rows = _load_spef_catalog_rows()
    except Exception:
        logger.debug("UPR visuals: could not load SPEF catalog icons", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        rows = []

    for row in rows:
        code = (getattr(row, "code", None) or "").strip().upper()
        if not code:
            continue
        src = ""
        if use_inline:
            # WeasyPrint cannot load Flask /indicator-bank URLs; only embed files.
            src = _inline_spef_icon(row)
        else:
            src = _spef_catalog_icon_url(row)
        if src:
            _remember_spef_icon(out, code, src)

    for code in _PLUGIN_REACH_ICONS:
        src = _plugin_reach_icon_src(code, inline=use_inline)
        if not src:
            continue
        if code == "EO" or not out.get(code):
            _remember_spef_icon(out, code, src)

    try:
        from flask import g, has_app_context

        if has_app_context():
            setattr(g, cache_attr, out)
    except Exception:
        pass
    return out


def _plan_financial(items, by_item, period_name: str) -> dict[str, Any]:
    years = planning_years(period_name)
    year_rows = []
    area_years = []
    source_totals = {"HNS": 0.0, "IFRC Secretariat": 0.0, "PNS": 0.0}
    for offset, year in enumerate(years):
        fallback_key = f"funding_y{offset}"
        item = _resolve_funding_year_item(items, offset, PLAN_ITEM_FALLBACKS[fallback_key])
        cells = _matrix_cells(by_item.get(item.id) if item else None)
        grouped = _sum_funding_rows(cells)
        by_area = _sum_funding_by_area(cells)
        buckets = _sum_funding_by_bucket(cells)
        for entity, rec in by_area.items():
            rec["emergency"] = float((buckets.get(entity) or {}).get("emergency") or 0)
        hns = grouped.get("HNS", 0.0)
        ifrc = grouped.get("IFRC Secretariat", 0.0)
        pns = grouped.get("PNS", 0.0)
        total = hns + ifrc + pns
        year_rows.append(
            {
                "year": year,
                "hns": hns,
                "ifrc": ifrc,
                "pns": pns,
                "total": total,
                "hns_display": format_compact_chf(hns) if hns else "",
                "ifrc_display": format_compact_chf(ifrc) if ifrc else "",
                "pns_display": format_compact_chf(pns) if pns else "",
                "total_display": format_compact_chf(total) if total else "",
            }
        )
        area_years.append({"year": year, "by_entity": by_area})
        if offset == 0:
            source_totals["HNS"] = hns
            source_totals["IFRC Secretariat"] = ifrc
            source_totals["PNS"] = pns

    cover_sources = []
    for key, label in (
        ("HNS", "Through Host National Society"),
        ("IFRC Secretariat", "Through the IFRC"),
        ("PNS", "Through Participating National Societies"),
    ):
        val = source_totals[key]
        if key == "PNS" and not val:
            continue
        cover_sources.append(
            {
                "entity": key,
                "label": label,
                "value": val,
                "display": format_compact_chf(val) if val else "Not reported",
            }
        )
    network_req = sum(source_totals.values())
    sources = [
        {
            "entity": key,
            "label": FUNDING_ENTITY_LABELS[key],
            "value": val,
            "display": format_chf(val) if val else "Not reported",
        }
        for key, val in source_totals.items()
    ]
    return {
        "ifrc_network": {
            "funding_requirement": network_req,
            "funding_requirement_display": format_compact_chf(network_req) if network_req else "Not reported",
            "funding": None,
            "expenditure": None,
        },
        "cover_sources": cover_sources,
        "sources": sources,
        "years": year_rows,
        "area_years": area_years,
    }


def _report_financial(
    items,
    by_item,
    *,
    country_id: int | None = None,
    host_ns_id: int | None = None,
    period_name: str = "",
    iso2: str | None = None,
    iso3: str | None = None,
) -> dict[str, Any]:
    """Host NS figures from this T33 assignment, plus the Tableau main network block.

    Main IFRC-network visual (cross-submission):
    - Funding requirement → Unified Country Plan (template 24) for the same calendar year
    - PNS funding / expenditure → published T23 funding matrix, keyed by this host NS
    - IFRC Secretariat Funding/Expenditure → MYR26 snapshot (System Financial Figures
      table Final); other rounds stay unreported until a live IFRC actuals source exists

    National Society visual (same assignment): HNS funding sources, expenditure, SP breakdown.
    """
    funding_item = _resolve_item(
        items, REPORT_LABEL_NEEDLES["funding_sources"], REPORT_ITEM_FALLBACKS["funding_sources"]
    )
    exp_item = _resolve_item(items, REPORT_LABEL_NEEDLES["expenditure"], REPORT_ITEM_FALLBACKS["expenditure"])
    breakdown_item = _resolve_item(
        items, REPORT_LABEL_NEEDLES["sp_breakdown"], REPORT_ITEM_FALLBACKS["sp_breakdown"]
    )
    cells = _matrix_cells(by_item.get(funding_item.id) if funding_item else None)
    by_entity: dict[str, float] = {}
    for key, raw in cells.items():
        number = to_number(_resolve_matrix_cell(raw))
        if not number:
            continue
        row, _col = _split_cell_key(key)
        entity = _funding_entity(row)
        if entity:
            by_entity[entity] = by_entity.get(entity, 0.0) + number

    expenditure = _scalar_number(by_item.get(exp_item.id) if exp_item else None)
    funding_total = sum(by_entity.values())
    sources = []
    for key in ("IFRC Secretariat", "PNS", "Other sources"):
        val = by_entity.get(key, 0.0)
        sources.append(
            {
                "entity": key,
                "label": FUNDING_ENTITY_LABELS[key],
                "value": val or None,
                "display": format_compact_chf(val) if val else "Not reported",
            }
        )

    breakdown = []
    bd_cells = _matrix_cells(by_item.get(breakdown_item.id) if breakdown_item else None)
    row_to_area = {label.lower(): code for code, label in REPORTING_SP_BREAKDOWN_AREA_TO_ROW.items()}
    grouped_bd: dict[str, dict[str, float]] = {}
    for key, raw in bd_cells.items():
        number = to_number(_resolve_matrix_cell(raw))
        if number is None:
            continue
        row, col = _split_cell_key(key)
        area = row_to_area.get((row or "").lower())
        if not area:
            continue
        metric = "funding" if "fund" in (col or "").lower() else "expenditure"
        grouped_bd.setdefault(area, {})[metric] = grouped_bd.get(area, {}).get(metric, 0.0) + number
    for code in (*SP_CODES, "EFs"):
        metrics = grouped_bd.get(code) or {}
        if metrics:
            breakdown.append(
                {
                    "code": code,
                    "label": AREA_LABELS[code],
                    "funding": metrics.get("funding"),
                    "expenditure": metrics.get("expenditure"),
                }
            )

    year = _year_token(period_name)
    plan_buckets: dict[str, dict[str, float]] = {}
    plan_meta: dict[str, Any] = {}
    pns_reported = {"funding": 0.0, "expenditure": 0.0, "transferred": 0.0, "assignments": 0}
    if country_id and year:
        try:
            plan_buckets, plan_meta = _load_plan_funding_buckets(country_id, year)
        except Exception:
            logger.exception("UPR visuals: failed to load T24 funding requirements for country %s year %s", country_id, year)
    if host_ns_id and period_name:
        try:
            pns_reported = _load_t23_pns_totals(host_ns_id, period_name, year)
        except Exception:
            logger.exception("UPR visuals: failed to load T23 PNS funding for host NS %s", host_ns_id)

    ifrc_actuals = ifrc_secretariat_actuals_for_report(
        period_name=period_name, iso2=iso2, iso3=iso3
    )
    network_entities = build_report_network_entities(
        plan_buckets,
        pns_funding=pns_reported.get("funding") or 0.0,
        pns_expenditure=pns_reported.get("expenditure") or 0.0,
        other_funding=by_entity.get("Other sources") or 0.0,
        ifrc_actuals=ifrc_actuals,
    )

    return {
        "ifrc_network": {
            "funding_requirement": None,
            "funding": funding_total or None,
            "funding_display": format_compact_chf(funding_total) if funding_total else "Not reported",
            "expenditure": expenditure,
            "expenditure_display": format_compact_chf(expenditure) if expenditure else "Not reported",
        },
        "national_society": {
            "funding": funding_total or None,
            "funding_display": format_compact_chf(funding_total) if funding_total else "Not reported",
            "expenditure": expenditure,
            "expenditure_display": format_compact_chf(expenditure) if expenditure else "Not reported",
        },
        "sources": sources,
        "years": [],
        "breakdown": breakdown,
        "network_entities": network_entities,
        "cross_submission": {
            "plan_aes_id": plan_meta.get("aes_id"),
            "plan_period": plan_meta.get("period_name"),
            "pns_assignments": pns_reported.get("assignments") or 0,
            "ifrc_actuals_source": "myr26_ifrc_secretariat_actuals" if ifrc_actuals else None,
        },
    }


def build_report_network_entities(
    plan_buckets: dict[str, dict[str, float]],
    *,
    pns_funding: float = 0.0,
    pns_expenditure: float = 0.0,
    other_funding: float = 0.0,
    ifrc_actuals: dict[str, dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    """Tableau Financial Overview (3) row groups.

    Country = full T24 requirement. IFRC Secretariat splits Longer-term / Emergency
    Operations from the plan matrix. MYR26 Funding/Expenditure come from the
    System Financial Figures snapshot; other rounds leave actuals unreported.
    PNS actuals come from template 23. HNS other uses T24 HNS requirement + T33
    other sources.
    """
    empty = {"overall": 0.0, "longer_term": 0.0, "emergency": 0.0}
    hns = plan_buckets.get("HNS") or empty
    ifrc = plan_buckets.get("IFRC Secretariat") or empty
    pns = plan_buckets.get("PNS") or empty
    country_req = (hns.get("overall") or 0) + (ifrc.get("overall") or 0) + (pns.get("overall") or 0)

    return [
        {
            "entity": "Country",
            "label": "Country",
            "buckets": [
                _network_bucket("overall", "", funding_requirement=country_req or None),
            ],
        },
        {
            "entity": "IFRC Secretariat",
            "label": FUNDING_ENTITY_LABELS["IFRC Secretariat"],
            "buckets": _ifrc_network_buckets(ifrc, actuals=ifrc_actuals),
        },
        {
            "entity": "PNS",
            "label": FUNDING_ENTITY_LABELS["PNS"],
            "buckets": [
                _network_bucket(
                    "overall",
                    "",
                    funding_requirement=pns.get("overall") or None,
                    funding=pns_funding or None,
                    expenditure=pns_expenditure or None,
                    include_actuals=True,
                )
            ],
        },
        {
            "entity": "Other sources",
            "label": FUNDING_ENTITY_LABELS["Other sources"],
            "buckets": [
                _network_bucket(
                    "overall",
                    "",
                    funding_requirement=hns.get("overall") or None,
                    funding=other_funding or None,
                    include_actuals=True,
                    include_expenditure=False,
                )
            ],
        },
    ]


def _ifrc_network_buckets(
    ifrc: dict[str, float],
    *,
    actuals: dict[str, dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    """Always emit Tableau's Longer-term / Emergency Operations split for IFRC Secretariat."""
    longer_val = ifrc.get("longer_term") or 0
    emergency_val = ifrc.get("emergency") or 0
    if not longer_val and not emergency_val:
        longer_val = ifrc.get("overall") or 0
    longer_act = (actuals or {}).get("longer_term") or {}
    emergency_act = (actuals or {}).get("emergency") or {}
    return [
        _network_bucket(
            "longer_term",
            "Longer-term",
            funding_requirement=longer_val or None,
            funding=longer_act.get("funding"),
            expenditure=longer_act.get("expenditure"),
            include_actuals=True,
        ),
        _network_bucket(
            "emergency",
            "Emergency Operations",
            funding_requirement=emergency_val or None,
            funding=emergency_act.get("funding"),
            expenditure=emergency_act.get("expenditure"),
            include_actuals=True,
        ),
    ]


def ifrc_secretariat_actuals_for_report(
    *,
    period_name: str,
    iso2: str | None = None,
    iso3: str | None = None,
) -> dict[str, dict[str, float]] | None:
    """MYR26-only IFRC Secretariat Funding/Expenditure from the shipped snapshot."""
    if period_to_round(period_name, "report") != "MYR26":
        return None
    rec = _myr26_ifrc_actuals_record(iso2=iso2, iso3=iso3)
    if not rec:
        return None
    out: dict[str, dict[str, float]] = {}
    for bucket in ("longer_term", "emergency"):
        metrics = rec.get(bucket)
        if not isinstance(metrics, dict) or not metrics:
            continue
        cleaned = {
            key: number
            for key in ("funding", "expenditure")
            if (number := _usable_ifrc_actual(metrics.get(key))) is not None
        }
        if cleaned:
            out[bucket] = cleaned
    return out or None


def _usable_ifrc_actual(value: Any) -> float | None:
    """Keep IFRC snapshot amounts of at least 1,000 CHF; drop smaller and negatives."""
    number = to_number(value)
    if number is None or number < _IFRC_ACTUALS_MIN_CHF:
        return None
    return number


@lru_cache(maxsize=1)
def _myr26_ifrc_actuals_by_iso2() -> dict[str, dict[str, Any]]:
    if not _MYR26_IFRC_ACTUALS_PATH.is_file():
        return {}
    try:
        payload = json.loads(_MYR26_IFRC_ACTUALS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("UPR visuals: failed to load MYR26 IFRC Secretariat actuals snapshot")
        return {}
    by_iso2 = payload.get("by_iso2") if isinstance(payload, dict) else None
    if not isinstance(by_iso2, dict):
        return {}
    return {str(key).strip().upper(): rec for key, rec in by_iso2.items() if rec}


def _myr26_ifrc_actuals_record(*, iso2: str | None, iso3: str | None) -> dict[str, Any] | None:
    catalog = _myr26_ifrc_actuals_by_iso2()
    if not catalog:
        return None
    code2 = (iso2 or "").strip().upper()
    if code2 and code2 in catalog:
        rec = catalog[code2]
        return rec if isinstance(rec, dict) else None
    code3 = (iso3 or "").strip().upper()
    if not code3:
        return None
    for rec in catalog.values():
        if isinstance(rec, dict) and str(rec.get("iso3") or "").strip().upper() == code3:
            return rec
    return None


def _network_bucket(
    key: str,
    label: str,
    *,
    funding_requirement: float | None = None,
    funding: float | None = None,
    expenditure: float | None = None,
    include_actuals: bool = False,
    include_expenditure: bool = True,
) -> dict[str, Any]:
    specs = [("funding_requirement", funding_requirement, "Funding requirement")]
    if include_actuals:
        specs.append(("funding", funding, "Funding"))
        if include_expenditure:
            specs.append(("expenditure", expenditure, "Expenditure"))
    metrics = [_metric_row(metric_key, metric_label, value) for metric_key, value, metric_label in specs]
    return {"key": key, "label": label, "metrics": metrics}


def _metric_row(key: str, label: str, value: float | None) -> dict[str, Any]:
    number = value if value else None
    return {
        "key": key,
        "label": label,
        "value": number or 0,
        "display": format_compact_chf(number) if number else "Not reported",
        "reported": bool(number),
    }


def _load_plan_funding_buckets(country_id: int, year: int) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    aes = _find_country_aes_for_year(PLAN_TEMPLATE_ID, country_id, year, annual_only=True)
    if not aes or not aes.assigned_form:
        return {}, {}
    assigned = aes.assigned_form
    items = _load_items(assigned.template)
    by_item = {row.form_item_id: row for row in _load_entries(aes.id)}
    item = _resolve_funding_year_item(items, 0, PLAN_ITEM_FALLBACKS["funding_y0"])
    cells = _matrix_cells(by_item.get(item.id) if item else None)
    return _sum_funding_by_bucket(cells), {
        "aes_id": aes.id,
        "period_name": assigned.period_name,
    }


def _load_t23_pns_totals(host_ns_id: int, period_name: str, year: int | None) -> dict[str, Any]:
    item_id = _pns_report_funding_item_id()
    if not item_id:
        return {"funding": 0.0, "expenditure": 0.0, "transferred": 0.0, "assignments": 0}
    period_names = [period_name]
    if year and str(year) not in period_names:
        period_names.append(str(year))
    entries = (
        db.session.query(FormData)
        .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .filter(AssignedForm.template_id == PNS_REPORT_TEMPLATE_ID)
        .filter(AssignedForm.period_name.in_(period_names))
        .filter(FormData.form_item_id == item_id)
        .all()
    )
    return sum_t23_host_cells(entries, host_ns_id)


def _load_t23_funding_by_pns(host_ns_id: int, period_name: str, year: int | None) -> dict[int, float]:
    item_id = _pns_report_funding_item_id()
    if not item_id:
        return {}
    rows = _pns_country_matrix_rows(PNS_REPORT_TEMPLATE_ID, item_id, _period_names(period_name, year))
    if not rows:
        return {}
    pns_ns_by_aes = _pns_ns_id_by_aes([aes for _entry, aes in rows])
    return t23_host_funding_by_pns([entry for entry, _aes in rows], host_ns_id, pns_ns_by_aes)


def _load_t22_funding_by_pns(host_country_id: int, period_name: str, year: int | None) -> dict[int, float]:
    item_id = _pns_plan_funding_item_id()
    if not item_id:
        return {}
    rows = _pns_country_matrix_rows(PNS_PLAN_TEMPLATE_ID, item_id, _period_names(period_name, year))
    if not rows:
        return {}
    pns_ns_by_aes = _pns_ns_id_by_aes([aes for _entry, aes in rows])
    return t22_host_funding_by_pns([entry for entry, _aes in rows], host_country_id, pns_ns_by_aes)


def _period_names(period_name: str, year: int | None) -> list[str]:
    names: list[str] = []
    if period_name:
        names.append(period_name)
    if year and str(year) not in names:
        names.append(str(year))
    return names


def _pns_country_matrix_rows(template_id: int, item_id: int, period_names: list[str]):
    if not item_id or not period_names:
        return []
    return (
        db.session.query(FormData, AssignmentEntityStatus)
        .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .filter(AssignedForm.template_id == int(template_id))
        .filter(AssignedForm.period_name.in_(period_names))
        .filter(FormData.form_item_id == int(item_id))
        .filter(AssignmentEntityStatus.entity_type == "country")
        .all()
    )


def _pns_ns_id_by_aes(assignments: list[AssignmentEntityStatus]) -> dict[int, int]:
    country_ids = sorted({int(aes.entity_id) for aes in assignments if aes.entity_id})
    if not country_ids:
        return {}
    ns_rows = (
        NationalSociety.query.filter(NationalSociety.country_id.in_(country_ids))
        .filter(NationalSociety.is_active.is_(True))
        .order_by(NationalSociety.display_order.asc().nullslast(), NationalSociety.id.asc())
        .all()
    )
    country_to_ns: dict[int, int] = {}
    for ns in ns_rows:
        country_to_ns.setdefault(int(ns.country_id), int(ns.id))
    return {
        int(aes.id): country_to_ns[int(aes.entity_id)]
        for aes in assignments
        if aes.entity_id and int(aes.entity_id) in country_to_ns
    }


def sum_t23_host_cells(entries: list, host_ns_id: int) -> dict[str, Any]:
    """Sum published T23 funding-matrix cells whose row is this host National Society."""
    funding = expenditure = transferred = 0.0
    assignments = 0
    prefix = f"{int(host_ns_id)}_"
    for entry in entries:
        cells = _matrix_cells(entry)
        hit = False
        for key, raw in cells.items():
            if not str(key).startswith(prefix):
                continue
            row, col = _split_cell_key(str(key))
            if str(row) != str(host_ns_id):
                continue
            number = to_number(_resolve_matrix_cell(raw))
            if not number:
                continue
            hit = True
            lower = (col or "").lower()
            if "expend" in lower:
                expenditure += number
            elif "transfer" in lower:
                transferred += number
            elif "fund" in lower:
                funding += number
        if hit:
            assignments += 1
    return {
        "funding": funding,
        "expenditure": expenditure,
        "transferred": transferred,
        "assignments": assignments,
    }


def _pns_report_funding_item_id() -> int | None:
    """Published T23 funding matrix — label may be blank (currently item 1433)."""
    from app.models.forms import FormTemplate

    template = FormTemplate.query.get(PNS_REPORT_TEMPLATE_ID)
    items = _plain_template_items(template)
    labeled = _resolve_item(items, PNS_REPORT_LABEL_NEEDLES["funding"], 0)
    if labeled:
        return labeled.id
    for item in items:
        label = (item.label or "").lower()
        if "staff" in label or "comment" in label:
            continue
        cfg = item.config if isinstance(getattr(item, "config", None), dict) else {}
        blob = str(cfg).lower()
        if "total funding" in blob and "total expenditure" in blob:
            return item.id
    scanned = _scan_template_matrix_item(PNS_REPORT_TEMPLATE_ID, "total funding")
    if scanned:
        return scanned
    return None


def _pns_plan_funding_item_id() -> int | None:
    from app.models.forms import FormTemplate

    template = FormTemplate.query.get(PNS_PLAN_TEMPLATE_ID)
    items = _plain_template_items(template)
    item = _resolve_item(items, PNS_PLAN_LABEL_NEEDLES["funding"], PNS_PLAN_ITEM_FALLBACKS["funding"])
    return item.id if item else PNS_PLAN_ITEM_FALLBACKS["funding"]


def _plain_template_items(template) -> list:
    version_id = getattr(template, "published_version_id", None) if template else None
    if not version_id:
        return []
    return FormItem.query.filter(FormItem.version_id == version_id, FormItem.archived.is_(False)).all()


def _scan_template_matrix_item(template_id: int, needle: str) -> int | None:
    entries = (
        db.session.query(FormData)
        .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .filter(AssignedForm.template_id == int(template_id))
        .limit(80)
        .all()
    )
    needle = needle.lower()
    for entry in entries:
        if any(needle in str(key).lower() for key in _matrix_cells(entry)):
            return entry.form_item_id
    return None


def _find_country_aes_for_year(
    template_id: int,
    country_id: int,
    year: int,
    *,
    annual_only: bool = False,
) -> AssignmentEntityStatus | None:
    rows = (
        AssignmentEntityStatus.query.options(
            joinedload(AssignmentEntityStatus.assigned_form).joinedload(AssignedForm.template),
        )
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .filter(AssignmentEntityStatus.entity_type == "country")
        .filter(AssignmentEntityStatus.entity_id == int(country_id))
        .filter(AssignedForm.template_id == int(template_id))
        .all()
    )
    exact = None
    yearly = None
    for aes in rows:
        pname = (aes.assigned_form.period_name if aes.assigned_form else "") or ""
        if pname == str(year):
            exact = aes
            break
        if _year_token(pname) != year:
            continue
        if annual_only and pname.lower().startswith("jan-jun"):
            continue
        yearly = yearly or aes
    return exact or yearly


def _plan_support(
    items,
    by_item,
    *,
    period_name: str = "",
    country_id: int | None = None,
) -> list[dict[str, Any]]:
    item = _resolve_item(items, PLAN_LABEL_NEEDLES["support"], PLAN_ITEM_FALLBACKS["support"])
    tick_rows = _support_from_cells(_matrix_cells(by_item.get(item.id) if item else None), planned=True)
    years = planning_years(period_name) or []
    year_totals: dict[int, dict[int, float]] = {}
    year_areas: dict[int, dict[int, dict[str, float]]] = {}
    for offset, year in enumerate(years):
        fallback_key = f"funding_y{offset}"
        fallback_id = PLAN_ITEM_FALLBACKS.get(fallback_key)
        fund_item = _resolve_funding_year_item(items, offset, fallback_id) if fallback_id else None
        cells = _matrix_cells(by_item.get(fund_item.id) if fund_item else None)
        year_totals[year] = pns_funding_from_plan_cells(cells)
        year_areas[year] = pns_area_funding_from_plan_cells(cells)
    confirmed: dict[int, float] = {}
    if country_id and years:
        try:
            confirmed = _load_t22_funding_by_pns(int(country_id), period_name, years[0])
        except Exception:
            logger.exception(
                "UPR visuals: failed to load T22 confirmed PNS funding for host country %s",
                country_id,
            )
    return _expand_plan_support_years(tick_rows, year_totals, year_areas, confirmed, years)


def _report_support(
    items,
    by_item,
    *,
    host_ns_id: int | None = None,
    host_country_id: int | None = None,
    period_name: str = "",
    year: int | None = None,
) -> list[dict[str, Any]]:
    item = _resolve_item(items, REPORT_LABEL_NEEDLES["support"], REPORT_ITEM_FALLBACKS["support"])
    rows = _support_from_cells(_matrix_cells(by_item.get(item.id) if item else None), planned=False)
    amounts: dict[int, float] = {}
    if host_ns_id:
        try:
            amounts.update(_load_t23_funding_by_pns(int(host_ns_id), period_name, year))
        except Exception:
            logger.exception("UPR visuals: failed to load T23 PNS funding rows for host NS %s", host_ns_id)
    if host_country_id:
        try:
            for ns_id, value in _load_t22_funding_by_pns(int(host_country_id), period_name, year).items():
                amounts.setdefault(int(ns_id), value)
        except Exception:
            logger.exception("UPR visuals: failed to load T22 PNS funding rows for host country %s", host_country_id)
    rows = _apply_support_funding(rows, amounts)
    return _extend_support_with_funding(rows, amounts)


def _support_from_cells(cells: dict[str, Any], *, planned: bool) -> list[dict[str, Any]]:
    by_ns: dict[str, dict[str, Any]] = {}
    ns_ids: list[int] = []
    for key, raw in cells.items():
        number = to_number(_resolve_matrix_cell(raw))
        if not number:
            continue
        row, col = _split_cell_key(key)
        if not row:
            continue
        rec = by_ns.setdefault(row, {"ns_key": row, "areas": {}, "funding": 0.0})
        code = _support_area_code(col, planned=planned)
        if code:
            rec["areas"][code] = True
        elif _is_support_funding_column(col):
            rec["funding"] += number
        try:
            ns_ids.append(int(row))
        except (TypeError, ValueError):
            pass

    names = _ns_names(ns_ids)
    rows = []
    for rec in by_ns.values():
        ns_key = rec["ns_key"]
        try:
            ns_id = int(ns_key)
        except (TypeError, ValueError):
            ns_id = None
        name = display_ns_name(names.get(ns_id) or ns_key)
        areas = {code: bool(rec["areas"].get(code)) for code in SUPPORT_AREA_CODES}
        areas["multilateral"] = bool(rec["areas"].get("multilateral"))
        funding = rec["funding"] or None
        rows.append(
            {
                "ns_id": ns_id,
                "name": name,
                "funding": funding,
                "funding_display": format_compact_chf(funding) if funding else "",
                "areas": areas,
            }
        )
    rows.sort(key=lambda row: (row["name"] or "").lower())
    return rows


def _is_support_funding_column(col: str | None) -> bool:
    text = (col or "").strip().lower()
    if not text or "expend" in text or "transfer" in text:
        return False
    return text in {"total", "row_total"} or "funding" in text


def pns_area_funding_from_plan_cells(cells: dict[str, Any]) -> dict[int, dict[str, float]]:
    """Per-PNS Strategic Priority / Enabling Functions amounts from a T24 funding matrix."""
    grouped: dict[int, dict[str, float]] = {}
    for key, raw in cells.items():
        number = to_number(_resolve_matrix_cell(raw))
        if not number:
            continue
        row, col = _split_cell_key(key)
        try:
            ns_id = int(row)
        except (TypeError, ValueError):
            continue
        code = _funding_area_code(col)
        if not code:
            continue
        rec = grouped.setdefault(ns_id, {area: 0.0 for area in SUPPORT_AREA_CODES})
        rec[code] = rec.get(code, 0.0) + number
    return grouped


def _expand_plan_support_years(
    tick_rows: list[dict[str, Any]],
    year_totals: dict[int, dict[int, float]],
    year_areas: dict[int, dict[int, dict[str, float]]],
    confirmed: dict[int, float],
    years: list[int],
) -> list[dict[str, Any]]:
    """One row per National Society × plan year that has ticks or funding."""
    by_ns = {int(row["ns_id"]): row for row in tick_rows if row.get("ns_id") is not None}
    all_ids: set[int] = set(by_ns)
    for totals in year_totals.values():
        all_ids.update(int(ns_id) for ns_id in totals)
    for areas in year_areas.values():
        all_ids.update(int(ns_id) for ns_id in areas)
    all_ids.update(int(ns_id) for ns_id in confirmed)
    names = {int(row["ns_id"]): row["name"] for row in tick_rows if row.get("ns_id") is not None}
    missing = [ns_id for ns_id in all_ids if ns_id not in names]
    names.update({int(ns_id): display_ns_name(label) for ns_id, label in _ns_names(missing).items()})
    empty_areas = {code: False for code in SUPPORT_AREA_CODES}
    year_list = list(years) or [None]
    first_year = year_list[0]
    rows: list[dict[str, Any]] = []
    for ns_id in all_ids:
        tick = by_ns.get(ns_id) or {}
        areas = tick.get("areas") or dict(empty_areas)
        name = display_ns_name(names.get(ns_id) or str(ns_id))
        active_years = []
        for year in year_list:
            total = float((year_totals.get(year) or {}).get(ns_id) or 0)
            area_amt = (year_areas.get(year) or {}).get(ns_id) or {}
            if total or any(area_amt.values()):
                active_years.append(year)
        if not active_years:
            if any(areas.get(code) for code in SUPPORT_AREA_CODES) or confirmed.get(ns_id) or tick.get("funding"):
                active_years = [first_year]
        for year in active_years:
            total = float((year_totals.get(year) or {}).get(ns_id) or 0)
            if not total and year == first_year:
                total = float(tick.get("funding") or 0)
            area_amt = (year_areas.get(year) or {}).get(ns_id) or {}
            conf = float(confirmed.get(ns_id) or 0) if year == first_year else 0.0
            rows.append(
                {
                    "ns_id": int(ns_id),
                    "name": name,
                    "year": year,
                    "funding": total or None,
                    "funding_display": format_compact_chf(total) if total else "",
                    "confirmed": conf or None,
                    "confirmed_display": format_compact_chf(conf) if conf else "",
                    "areas": {code: bool(areas.get(code)) for code in SUPPORT_AREA_CODES}
                    | {"multilateral": bool(areas.get("multilateral"))},
                    "area_amounts": {
                        code: (float(area_amt[code]) if area_amt.get(code) else None)
                        for code in SUPPORT_AREA_CODES
                    },
                    "multilateral_only": bool(
                        tick.get("multilateral_only")
                        or (areas.get("multilateral") and not any(areas.get(code) for code in SUPPORT_AREA_CODES))
                    ),
                }
            )
    for rec in tick_rows:
        if rec.get("ns_id") is not None:
            continue
        rows.append(
            {
                **rec,
                "year": first_year,
                "confirmed": None,
                "confirmed_display": "",
                "area_amounts": {code: None for code in SUPPORT_AREA_CODES},
            }
        )
    rows.sort(key=lambda row: ((row.get("name") or "").lower(), int(row.get("year") or 0)))
    return rows


def pns_funding_from_plan_cells(cells: dict[str, Any]) -> dict[int, float]:
    """Per-PNS funding requirement from T24 hybrid matrix rows keyed by NationalSociety.id."""
    by_ns: dict[int, float] = {}
    totals: dict[int, float] = {}
    for key, raw in cells.items():
        number = to_number(_resolve_matrix_cell(raw))
        if not number:
            continue
        row, col = _split_cell_key(key)
        try:
            ns_id = int(row)
        except (TypeError, ValueError):
            continue
        bucket = _funding_column_bucket(col)
        if bucket == "row_total":
            totals[ns_id] = totals.get(ns_id, 0.0) + number
            continue
        if bucket in {"longer_term", "emergency"}:
            by_ns[ns_id] = by_ns.get(ns_id, 0.0) + number
    for ns_id, total in totals.items():
        if not by_ns.get(ns_id):
            by_ns[ns_id] = total
    return by_ns


def _apply_support_funding(rows: list[dict[str, Any]], amounts: dict[int, float]) -> list[dict[str, Any]]:
    for rec in rows:
        if rec.get("funding"):
            continue
        ns_id = rec.get("ns_id")
        value = amounts.get(int(ns_id)) if ns_id is not None else None
        if not value:
            continue
        rec["funding"] = value
        rec["funding_display"] = format_compact_chf(value)
    return rows


def _extend_support_with_funding(rows: list[dict[str, Any]], amounts: dict[int, float]) -> list[dict[str, Any]]:
    """Keep Tableau's funding-only PNS rows (amount but no SP ticks)."""
    present = {int(row["ns_id"]) for row in rows if row.get("ns_id") is not None}
    missing = [ns_id for ns_id, value in amounts.items() if value and int(ns_id) not in present]
    names = _ns_names(missing)
    empty_areas = {code: False for code in SUPPORT_AREA_CODES}
    for ns_id in missing:
        value = amounts[ns_id]
        rows.append(
            {
                "ns_id": int(ns_id),
                "name": display_ns_name(names.get(int(ns_id)) or str(ns_id)),
                "funding": value,
                "funding_display": format_compact_chf(value),
                "areas": dict(empty_areas),
            }
        )
    rows.sort(key=lambda row: (row["name"] or "").lower())
    return rows


def support_total_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(float(row.get("funding") or 0) for row in rows)
    return {
        "value": total or 0,
        "display": format_compact_chf(total) if total else "",
    }


def t23_host_funding_by_pns(
    entries: list,
    host_ns_id: int,
    pns_ns_by_aes: dict[int, int],
) -> dict[int, float]:
    """Per-PNS Total Funding from the published T23 funding matrix for this host NS."""
    by_pns: dict[int, float] = {}
    prefix = f"{int(host_ns_id)}_"
    for entry in entries:
        pns_ns_id = pns_ns_by_aes.get(int(getattr(entry, "assignment_entity_status_id", 0) or 0))
        if not pns_ns_id:
            continue
        cells = _matrix_cells(entry)
        for key, raw in cells.items():
            if not str(key).startswith(prefix):
                continue
            row, col = _split_cell_key(str(key))
            if str(row) != str(host_ns_id) or not _is_support_funding_column(col):
                continue
            number = to_number(_resolve_matrix_cell(raw))
            if number:
                by_pns[int(pns_ns_id)] = by_pns.get(int(pns_ns_id), 0.0) + number
    return by_pns


def t22_host_funding_by_pns(
    entries: list,
    host_country_id: int,
    pns_ns_by_aes: dict[int, int],
) -> dict[int, float]:
    """Per-PNS host-country totals from T22 item 1303 (`{country_id}_Total` or SP sum)."""
    by_pns: dict[int, float] = {}
    prefix = f"{int(host_country_id)}_"
    for entry in entries:
        pns_ns_id = pns_ns_by_aes.get(int(getattr(entry, "assignment_entity_status_id", 0) or 0))
        if not pns_ns_id:
            continue
        cells = _matrix_cells(entry)
        total = 0.0
        areas = 0.0
        for key, raw in cells.items():
            if not str(key).startswith(prefix):
                continue
            row, col = _split_cell_key(str(key))
            if str(row) != str(host_country_id):
                continue
            number = to_number(_resolve_matrix_cell(raw))
            if not number:
                continue
            bucket = _funding_column_bucket(col)
            if bucket == "row_total" or (col or "").strip().lower() == "total":
                total += number
            elif bucket in {"longer_term", "emergency"}:
                areas += number
        value = total or areas
        if value:
            by_pns[int(pns_ns_id)] = by_pns.get(int(pns_ns_id), 0.0) + value
    return by_pns


def _report_emergencies(aes_id: int, items: list[FormItem]) -> list[dict[str, Any]]:
    repeat_sections = [
        item.form_section
        for item in items
        if item.form_section and item.form_section.section_type == "repeat"
        and "emergency" in (item.form_section.name or "").lower()
    ]
    if not repeat_sections:
        return []
    section_ids = {sec.id for sec in repeat_sections if sec}
    parent_ids = {sec.id for sec in repeat_sections if sec and not sec.parent_section_id}
    target_ids = parent_ids or section_ids
    instances = (
        RepeatGroupInstance.query.filter(
            RepeatGroupInstance.assignment_entity_status_id == aes_id,
            RepeatGroupInstance.section_id.in_(target_ids),
            RepeatGroupInstance.is_hidden.is_(False),
        )
        .order_by(RepeatGroupInstance.instance_number)
        .all()
    )
    dyn_rows = _load_dynamic_indicator_rows(aes_id)
    by_slot: dict[int, list[DynamicIndicatorData]] = {}
    for row in dyn_rows:
        if row.repeat_instance_number:
            by_slot.setdefault(int(row.repeat_instance_number), []).append(row)

    emergencies = []
    for inst in instances:
        slot = int(inst.instance_number)
        label = inst.instance_label or ""
        name, code = _split_appeal_label(label)
        people = None
        indicators = []
        for dyn in by_slot.get(slot, []):
            number = _scalar_number(dyn)
            bank = dyn.indicator_bank
            unit = (getattr(bank, "unit", None) or "").strip().lower() if bank else ""
            label_text = dyn.custom_label or (bank.name if bank else "")
            meas = (getattr(bank, "type", None) or "").strip().lower() if bank else ""
            area = _bank_area(bank)
            if meas in {"yesno", "yes/no", "boolean"}:
                flag = str(getattr(dyn, "value", "") or "").strip().lower() in {"yes", "true", "1"}
                if number is not None:
                    flag = bool(number)
                indicators.append(
                    {
                        "label": label_text,
                        "value": 1.0 if flag else 0.0,
                        "display": "Yes" if flag else "No",
                        "kind": "yesno",
                        "code": area,
                    }
                )
                continue
            if meas in {"percentage", "percent"} or not number:
                continue
            indicators.append(
                {
                    "label": label_text,
                    "value": number,
                    "display": format_count(number) if number is not None else "",
                    "kind": "number",
                    "code": area,
                }
            )
            if people is None and "people" in unit and number is not None:
                people = number
            elif people is None and "people reached" in (label_text or "").lower() and number is not None:
                people = number
        if not name and not code and people is None and not indicators:
            continue
        emergencies.append(
            {
                "slot": slot,
                "name": name or label or f"Emergency {slot}",
                "code": code,
                "people_reached": people,
                "people_display": format_count(people) if people is not None else "",
                "indicators": indicators[:40],
            }
        )
    return emergencies


def _resolve_item(items: list[FormItem], needles: tuple[str, ...], fallback_id: int) -> FormItem | None:
    lowered = [(item, (item.label or "").strip().lower()) for item in items]
    for item, label in lowered:
        if any(needle in label for needle in needles):
            return item
    for item in items:
        if item.id == fallback_id:
            return item
    return None


def _resolve_funding_year_item(items: list[FormItem], offset: int, fallback_id: int) -> FormItem | None:
    """Resolve T24 hybrid funding matrices 967 / 968 / 974 (year offsets 0/1/2)."""
    fallback = next((item for item in items if item.id == fallback_id), None)
    if fallback:
        return fallback
    year_needles = {
        0: ("year 1", "y0", "current year"),
        1: ("year 2", "y1", "+1"),
        2: ("year 3", "y2", "+2"),
    }
    candidates = [
        item
        for item in items
        if "funding" in (item.label or "").lower() and "requirement" in (item.label or "").lower()
    ]
    candidates.sort(key=lambda item: (item.order or 0, item.id or 0))
    hinted = [
        item
        for item in candidates
        if any(n in (item.label or "").lower() for n in year_needles.get(offset, ()))
    ]
    if hinted:
        return hinted[0]
    if offset < len(candidates):
        return candidates[offset]
    return _resolve_item(items, PLAN_LABEL_NEEDLES["funding_y0"], fallback_id) if offset == 0 else None


def _matrix_cells(entry: FormData | None) -> dict[str, Any]:
    if not entry:
        return {}
    getter = getattr(entry, "get_display_disagg_data", None)
    disagg = getter() if callable(getter) else entry.disagg_data
    if not isinstance(disagg, dict):
        return {}
    values = disagg.get("values") if "values" in disagg else disagg
    if not isinstance(values, dict):
        return {}
    return {
        str(key): val
        for key, val in values.items()
        if isinstance(key, str) and not key.startswith("_") and key not in {"mode", "values"}
    }


def _scalar_number(entry) -> float | None:
    if entry is None:
        return None
    if getattr(entry, "data_not_available", False) or getattr(entry, "not_applicable", False):
        return None
    getter = getattr(entry, "get_display_value", None)
    raw = getter() if callable(getter) else getattr(entry, "value", None)
    number = to_number(raw)
    if number is not None:
        return number
    numeric = getattr(entry, "numeric_value", None)
    return float(numeric) if numeric is not None else None


def _split_cell_key(key: str) -> tuple[str, str]:
    """Split ``{row}_{column}`` matrix keys.

    Numeric rows (National Society id or calendar year) keep the remainder as
    the column, so T33 keys like ``7_SP1 Supported`` stay intact. Named rows
    (``HNS``, ``IFRC Secretariat``, SP breakdown labels) split on the last
    underscore.
    """
    if "_" not in key:
        return key, ""
    row, sep, col = key.partition("_")
    if sep and row.isdigit():
        return row, col
    row, col = key.rsplit("_", 1)
    return row, col


def _area_code(text: str | None) -> str | None:
    raw = (text or "").strip()
    upper = raw.upper().replace(" ", "-")
    if upper in SP_CODES or upper in {"EO", "EFS", "EF1", "EF2", "EF3", "EF4", "CC1"}:
        return "EFs" if upper == "EFS" else upper
    if upper in {"CC", "CROSS-CUTTING", "CROSSCUTTING"}:
        return "CC1"
    return None


def _support_area_code(col: str | None, *, planned: bool = True) -> str | None:
    text = (col or "").strip()
    upper = text.upper()
    if "MULTILATERAL" in upper:
        return "multilateral"
    if planned is False and "PLANNED" in upper and "SUPPORTED" not in upper:
        return None
    upper = upper.replace(" SUPPORTED", "").replace(" PLANNED", "")
    return _area_code(upper)


def _area_from_item(item: FormItem) -> str | None:
    bank = getattr(item, "indicator_bank", None)
    mapped = _bank_area(bank)
    if mapped:
        return mapped
    section = getattr(item, "form_section", None)
    return section_to_area(section.name if section else None)


def _bank_area(bank) -> str | None:
    if bank is None:
        return None
    spef = getattr(bank, "spef_area", None)
    if spef is not None:
        mapped = _area_code(getattr(spef, "code", None))
        if mapped:
            return mapped
    return _area_code(getattr(bank, "area", None))


def _funding_entity(row: str | None) -> str | None:
    raw = (row or "").strip()
    if not raw:
        return None
    if raw in FUNDING_ENTITY_LABELS:
        if raw in {"PNSs", "PNS"}:
            return "PNS"
        if raw in {"Other sources", "HNS other sources"}:
            return "Other sources"
        if raw in {"IFRC", "IFRC Secretariat"}:
            return "IFRC Secretariat"
        return raw
    lower = raw.lower()
    if "ifrc" in lower:
        return "IFRC Secretariat"
    if "pns" in lower:
        return "PNS"
    if "other" in lower:
        return "Other sources"
    if raw.upper() == "HNS":
        return "HNS"
    return None


def _sum_funding_rows(cells: dict[str, Any]) -> dict[str, float]:
    grouped = {"HNS": 0.0, "IFRC Secretariat": 0.0, "PNS": 0.0}
    totals = {"HNS": 0.0, "IFRC Secretariat": 0.0, "PNS": 0.0}
    for key, raw in cells.items():
        number = to_number(_resolve_matrix_cell(raw))
        if not number:
            continue
        row, col = _split_cell_key(key)
        entity = _funding_entity(row)
        if entity not in grouped:
            if entity is None:
                try:
                    int(row)
                    entity = "PNS"
                except (TypeError, ValueError):
                    continue
            else:
                continue
        if col.lower() in {"total", "row_total"}:
            totals[entity] += number
        else:
            grouped[entity] += number
    for key in grouped:
        if not grouped[key] and totals[key]:
            grouped[key] = totals[key]
    return grouped


def _funding_area_code(col: str | None) -> str | None:
    code = _area_code(col)
    if code in SP_CODES or code == "EFs":
        return code
    if code in EF_CODES:
        return "EFs"
    mapped = section_to_area(col)
    if mapped in SP_CODES or mapped == "EFs":
        return mapped
    if mapped in EF_CODES:
        return "EFs"
    text = (col or "").strip().lower()
    if "enabling" in text:
        return "EFs"
    return None


def _sum_funding_by_area(cells: dict[str, Any]) -> dict[str, dict[str, float]]:
    """T24 funding cells grouped by entity and Strategic Priority / Enabling Functions."""
    entities = ("HNS", "IFRC Secretariat", "PNS")
    grouped = {key: {code: 0.0 for code in SUPPORT_AREA_CODES} | {"total": 0.0} for key in entities}
    totals = {key: 0.0 for key in entities}
    for key, raw in cells.items():
        number = to_number(_resolve_matrix_cell(raw))
        if not number:
            continue
        row, col = _split_cell_key(key)
        entity = _funding_entity(row)
        if entity not in grouped:
            if entity is None:
                try:
                    int(row)
                    entity = "PNS"
                except (TypeError, ValueError):
                    continue
            else:
                continue
        if (col or "").strip().lower() in {"total", "row_total"}:
            totals[entity] += number
            continue
        code = _funding_area_code(col)
        if not code:
            continue
        grouped[entity][code] += number
        grouped[entity]["total"] += number
    for key, rec in grouped.items():
        if not rec["total"] and totals[key]:
            rec["total"] = totals[key]
    return grouped


def _funding_column_bucket(col: str | None) -> str | None:
    """Classify a T24 hybrid-matrix column as longer-term, emergency, or row total."""
    text = (col or "").strip()
    if not text:
        return None
    lower = text.lower()
    upper = text.upper().replace(" ", "")
    if lower in {"total", "row_total"} or upper in {"TOTAL", "ROW_TOTAL"}:
        return "row_total"
    if upper in PLANNING_EA_FUNDING_AREAS or upper.startswith("EA"):
        return "emergency"
    code = _area_code(text)
    if code in SP_CODES or code == "EFs":
        return "longer_term"
    return None


def _sum_funding_by_bucket(cells: dict[str, Any]) -> dict[str, dict[str, float]]:
    """T24 funding cells grouped by entity and Longer-term vs Emergency Operations."""
    grouped = {
        key: {"overall": 0.0, "longer_term": 0.0, "emergency": 0.0}
        for key in ("HNS", "IFRC Secretariat", "PNS")
    }
    totals = {key: 0.0 for key in grouped}
    for key, raw in cells.items():
        number = to_number(_resolve_matrix_cell(raw))
        if not number:
            continue
        row, col = _split_cell_key(key)
        entity = _funding_entity(row)
        if entity not in grouped:
            if entity is None:
                try:
                    int(row)
                    entity = "PNS"
                except (TypeError, ValueError):
                    continue
            else:
                continue
        bucket = _funding_column_bucket(col)
        if bucket == "row_total":
            totals[entity] += number
            continue
        if bucket in {"longer_term", "emergency"}:
            grouped[entity][bucket] += number
        grouped[entity]["overall"] += number
    for key, rec in grouped.items():
        if not rec["overall"] and totals[key]:
            rec["overall"] = totals[key]
    return grouped


def _ns_names(ns_ids: list[int]) -> dict[int, str]:
    unique = sorted({i for i in ns_ids if i})
    if not unique:
        return {}
    rows = NationalSociety.query.filter(NationalSociety.id.in_(unique)).all()
    return {int(row.id): row.name for row in rows}


def _split_appeal_label(label: str) -> tuple[str, str]:
    text = (label or "").strip()
    if text.endswith(")") and "(" in text:
        name, _, rest = text.rpartition("(")
        return name.strip(), rest.rstrip(")").strip()
    return text, ""


def list_assigned_forms_for_bulk() -> list[dict[str, Any]]:
    """Unified Plan and Report assignments available for bulk PNG generation."""
    rows = (
        AssignedForm.query.options(joinedload(AssignedForm.template))
        .filter(AssignedForm.template_id.in_(UPR_VISUAL_TEMPLATE_IDS))
        .order_by(
            AssignedForm.assigned_at.desc().nullslast(),
            AssignedForm.id.desc(),
        )
        .all()
    )
    return [
        {
            "id": assigned.id,
            "display_name": assigned.display_name,
            "template_id": assigned.template_id,
            "template_name": assigned.template.name if assigned.template else "",
            "period_name": assigned.period_name,
            "kind": kind_for_template(int(assigned.template_id or 0)),
        }
        for assigned in rows
    ]


def list_countries_for_bulk(assigned_form_id: int) -> list[dict[str, Any]]:
    """Country rows on one assignment, for bulk PNG generation."""
    from app.models.core import Country

    rows = (
        db.session.query(AssignmentEntityStatus, Country)
        .outerjoin(
            Country,
            db.and_(
                AssignmentEntityStatus.entity_type == "country",
                AssignmentEntityStatus.entity_id == Country.id,
            ),
        )
        .filter(AssignmentEntityStatus.assigned_form_id == int(assigned_form_id))
        .filter(AssignmentEntityStatus.entity_type == "country")
        .order_by(Country.name.asc().nullslast())
        .all()
    )
    return [
        {
            "aes_id": aes.id,
            "country_name": country.name if country else "",
            "iso3": country.iso3 if country else "",
        }
        for aes, country in rows
    ]


def get_assigned_form_for_bulk(assigned_form_id: int) -> AssignedForm:
    assigned = AssignedForm.query.get(int(assigned_form_id))
    if assigned is None or int(assigned.template_id or 0) not in UPR_VISUAL_TEMPLATE_IDS:
        raise UprVisualsError("Select a Unified Plan or Report assignment.")
    return assigned
