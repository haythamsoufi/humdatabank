"""Indicator-row classification and emergency-appeal assembly."""

from __future__ import annotations

from typing import Any

from app.models.form_items import FormItem
from app.models.forms import DynamicIndicatorData, RepeatGroupInstance
from plugins.upr_visuals.catalog import OTHER_INDICATORS_SECTION_NAME, OVERALL_ACTION_SECTION_NEEDLE
from plugins.upr_visuals.formatters import format_count, to_number
from plugins.upr_visuals.loaders import _load_dynamic_indicator_rows
from plugins.upr_visuals.matrix import _area_from_item, _bank_area, _scalar_number
from plugins.upr_visuals.people_reached import _is_people_count

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


def _split_appeal_label(label: str) -> tuple[str, str]:
    text = (label or "").strip()
    if text.endswith(")") and "(" in text:
        name, _, rest = text.rpartition("(")
        return name.strip(), rest.rstrip(")").strip()
    return text, ""


