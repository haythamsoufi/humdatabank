"""Matrix-cell parsing and funding-classification primitives."""

from __future__ import annotations

from typing import Any, Iterator

from app.models.form_items import FormItem
from app.models.forms import FormData
from app.utils.api_serialization import _resolve_matrix_cell
from plugins.upr_visuals.catalog import (
    EF_CODES,
    FUNDING_ENTITY_LABELS,
    PLAN_LABEL_NEEDLES,
    PLANNING_EA_FUNDING_AREAS,
    SP_CODES,
    SUPPORT_AREA_CODES,
    section_to_area,
)
from plugins.upr_visuals.formatters import to_number

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


def _iter_matrix_numbers(cells: dict[str, Any]) -> Iterator[tuple[str, str, float]]:
    """Yield ``(row, col, number)`` for numeric matrix cells (zero skipped)."""
    for key, raw in cells.items():
        number = to_number(_resolve_matrix_cell(raw))
        if not number:
            continue
        row, col = _split_cell_key(key)
        yield row, col, number


def _classify_funding_row(row: str, grouped: dict[str, Any]) -> str | None:
    """Resolve a matrix row to HNS / IFRC Secretariat / PNS, or skip it."""
    entity = _funding_entity(row)
    if entity in grouped:
        return entity
    if entity is None:
        try:
            int(row)
            return "PNS"
        except (TypeError, ValueError):
            return None
    return None


def _sum_funding_rows(cells: dict[str, Any]) -> dict[str, float]:
    grouped = {"HNS": 0.0, "IFRC Secretariat": 0.0, "PNS": 0.0}
    totals = {"HNS": 0.0, "IFRC Secretariat": 0.0, "PNS": 0.0}
    for row, col, number in _iter_matrix_numbers(cells):
        entity = _classify_funding_row(row, grouped)
        if entity is None:
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
    for row, col, number in _iter_matrix_numbers(cells):
        entity = _classify_funding_row(row, grouped)
        if entity is None:
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


def _is_support_funding_column(col: str | None) -> bool:
    text = (col or "").strip().lower()
    if not text or "expend" in text or "transfer" in text:
        return False
    return text in {"total", "row_total"} or "funding" in text


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
    for row, col, number in _iter_matrix_numbers(cells):
        entity = _classify_funding_row(row, grouped)
        if entity is None:
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
