"""Plan/report financial assembly and IFRC network entity rows."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from plugins.upr_visuals.catalog import (
    AREA_LABELS,
    FUNDING_ENTITY_LABELS,
    PLAN_ITEM_FALLBACKS,
    PLAN_LABEL_NEEDLES,
    PLAN_TEMPLATE_ID,
    REPORT_ITEM_FALLBACKS,
    REPORT_LABEL_NEEDLES,
    REPORTING_SP_BREAKDOWN_AREA_TO_ROW,
    SP_CODES,
)
from plugins.upr_visuals.formatters import (
    format_chf,
    format_compact_chf,
    period_to_round,
    planning_years,
    to_number,
    _year_token,
)
from plugins.upr_visuals.loaders import _load_entries, _load_items
from plugins.upr_visuals.matrix import (
    _classify_funding_row,
    _funding_entity,
    _iter_matrix_numbers,
    _matrix_cells,
    _resolve_funding_year_item,
    _resolve_item,
    _scalar_number,
    _split_cell_key,
    _sum_funding_by_area,
    _sum_funding_by_bucket,
    _sum_funding_rows,
)
from plugins.upr_visuals.pns_funding import _find_country_aes_for_year, _load_t23_pns_totals
from app.utils.api_serialization import _resolve_matrix_cell

logger = logging.getLogger(__name__)

_PLUGIN_DIR = Path(__file__).resolve().parent
_MYR26_IFRC_ACTUALS_PATH = _PLUGIN_DIR / "snapshots" / "myr26_ifrc_secretariat_actuals.json"
_IFRC_ACTUALS_MIN_CHF = 1000.0
_MYR26_ROUND_CODE = "MYR26"

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
    if period_to_round(period_name, "report") != _MYR26_ROUND_CODE:
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


