"""People-reached assembly for Unified Plan and Report visuals."""

from __future__ import annotations

from typing import Any

from plugins.upr_visuals.catalog import (
    AREA_LABELS,
    PLAN_ITEM_FALLBACKS,
    PLAN_LABEL_NEEDLES,
    REACH_CODES,
    REACH_DROP_LONG_TERM_NEEDLES,
    REACH_EMERGENCY_BANK_ID,
    REACH_EMERGENCY_TO_SP2_NEEDLES,
    REPORT_ITEM_FALLBACKS,
    REPORT_LABEL_NEEDLES,
)
from plugins.upr_visuals.formatters import format_count, planning_years, to_number
from plugins.upr_visuals.icons import _spef_icon_alias, spef_icon_srcs
from plugins.upr_visuals.loaders import _load_dynamic_indicator_rows
from plugins.upr_visuals.matrix import (
    _area_from_item,
    _bank_area,
    _matrix_cells,
    _resolve_item,
    _scalar_number,
    _split_cell_key,
)
from app.utils.api_serialization import _resolve_matrix_cell

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


