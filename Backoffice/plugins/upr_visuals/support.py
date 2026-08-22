"""Bilateral support table assembly for plan and report visuals."""

from __future__ import annotations

import logging
from typing import Any

from app.models.organization import NationalSociety
from plugins.upr_visuals.catalog import (
    PLAN_ITEM_FALLBACKS,
    PLAN_LABEL_NEEDLES,
    PNS_PLAN_TEMPLATE_ID,
    REPORT_ITEM_FALLBACKS,
    REPORT_LABEL_NEEDLES,
    SUPPORT_AREA_CODES,
    display_ns_name,
)
from plugins.upr_visuals.formatters import format_compact_chf, planning_years, to_number
from plugins.upr_visuals.matrix import (
    _funding_area_code,
    _is_support_funding_column,
    _iter_matrix_numbers,
    _matrix_cells,
    _resolve_funding_year_item,
    _resolve_item,
    _split_cell_key,
    _support_area_code,
)
from plugins.upr_visuals.pns_funding import (
    _find_country_aes_for_year,
    _load_t22_funding_by_pns,
    _load_t23_funding_by_pns,
    pns_area_funding_from_plan_cells,
    pns_funding_from_plan_cells,
)
from app.utils.api_serialization import _resolve_matrix_cell

logger = logging.getLogger(__name__)


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


def _ns_names(ns_ids: list[int]) -> dict[int, str]:
    unique = sorted({i for i in ns_ids if i})
    if not unique:
        return {}
    rows = NationalSociety.query.filter(NationalSociety.id.in_(unique)).all()
    return {int(row.id): row.name for row in rows}


