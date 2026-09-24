"""Long-form UPR extract for Power BI.

Replaces the Fabric dataflow "UPR Monster" (templates 33, 24, and 23).
Each form item is classified once, then emitted as fact rows. Round comes
from the assignment period (``period_to_round``), not from due dates.
IFRC Secretariat actuals come from the plugin snapshots already used by
the report visuals. SharePoint and the separate planned-funding dataflow
are not queried.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterator

from sqlalchemy import and_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.assignments import AssignedForm, AssignmentEntityStatus
from app.models.core import Country
from app.models.enums import AssignmentEntityStatusValue
from app.models.form_items import FormItem
from app.models.forms import DynamicIndicatorData, DynamicSectionContext, FormData, FormSection
from app.models.indicator_bank import IndicatorBank
from app.models.organization import NationalSociety
from plugins.upr.catalog import (
    AREA_LABELS,
    KPI_BANK_IDS,
    PLAN_ITEM_FALLBACKS,
    PLAN_LABEL_NEEDLES,
    PLAN_TEMPLATE_ID,
    PNS_REPORT_LABEL_NEEDLES,
    PNS_REPORT_TEMPLATE_ID,
    REPORT_ITEM_FALLBACKS,
    REPORT_LABEL_NEEDLES,
    REPORT_TEMPLATE_ID,
    section_to_area,
)
from plugins.upr.financial import _IFRC_ACTUALS_SNAPSHOTS, _usable_ifrc_actual
from plugins.upr.formatters import _year_token, period_to_round, planning_years, strip_trailing_period, to_number
from plugins.upr.matrix import (
    _area_code,
    _funding_column_bucket,
    _funding_entity,
    _iter_matrix_numbers,
)

TEMPLATE_KIND = {
    REPORT_TEMPLATE_ID: "report",
    PLAN_TEMPLATE_ID: "plan",
    PNS_REPORT_TEMPLATE_ID: "pns",
}
TEMPLATE_IDS = frozenset(TEMPLATE_KIND)

_NS_LABELS = frozenset({"branches", "local units", "staff", "volunteers"})
_KPI_BANK_ID_SET = frozenset(KPI_BANK_IDS.values())
_PLAN_YEAR_OFFSET = {
    PLAN_ITEM_FALLBACKS["funding_y0"]: 0,
    PLAN_ITEM_FALLBACKS["funding_y1"]: 1,
    PLAN_ITEM_FALLBACKS["funding_y2"]: 2,
}
_PLAN_FUNDING_IDS = frozenset(_PLAN_YEAR_OFFSET)
_REPORT_FUNDING_IDS = frozenset(
    REPORT_ITEM_FALLBACKS[key] for key in ("funding_sources", "expenditure", "sp_breakdown")
)
_MATRIX_ROLES = frozenset(
    {"support", "funding", "activity", "reach", "emergency", "plan_funding", "pns_funding"}
)
_EA_CODE_RE = re.compile(r"\(([^)]+)\)")
_ID_CHUNK = 2000

_DISAGG_LABELS = {
    "total": "Total",
    "total_direct": "Direct",
    "total_indirect": "Indirect",
    "male": "Total male",
    "female": "Total female",
    "female__5": "Female <5",
    "male__5": "Male <5",
    "male_5_17": "Male 5-17",
    "male_18_49": "Male 18-49",
    "male_50_": "Male 50+",
    "female_5_17": "Female 5-17",
    "female_18_49": "Female 18-49",
    "female_50_": "Female 50+",
    "female_unknown": "Female Unknown age",
    "male_unknown": "Male Unknown age",
    "5_17": "Ages 5-17",
    "18_49": "Ages 18-49",
    "non_binary": "Non-binary",
    "non_binary_18_49": "Non-binary 18-49",
    "unknown": "Other/Unknown",
}

# Workbook indicatorId values on the UPR Data sheet (not always an IndicatorBank id).
_SHEET_INDICATOR_IDS = {
    "Funding Requirement": 2,
    "Bilateral Support": 3,
    "Transferred": 5,
    "Funding": 733,
    "Expenditure": 734,
}

MASTER_COLUMNS = (
    "ISO3",
    "Country",
    "Round",
    "Year",
    "Section",
    "SectionB",
    "Entity",
    "NS",
    "Source",
    "Area",
    "Attribute",
    "Indicator",
    "indicatorId",
    "ValueNum",
    "Country Value",
    "PNS Value",
    "Value",
    "UPR Value",
    "EA Code",
    "Applicable/Data not available",
    "PNS reported",
)

FACT_COLUMNS = (
    "Round",
    "ISO3",
    "Country",
    "NS",
    "Region",
    "Table",
    "SectionB",
    "Source",
    "Entity",
    "Attribute",
    "SP/EF",
    "Applicable/Data not available",
    "Indicator",
    "Value",
    "ValueNum",
    "Year",
    "EA Code",
    "assigned_form_id",
    "submission_id",
    "template",
)

SUBMISSION_COLUMNS = (
    "Round",
    "Country",
    "Region",
    "NS",
    "ISO3",
    "status",
    "fds_validated",
    "submitted_at",
    "due_date",
    "assigned_form_id",
    "submission_id",
    "template",
)


@dataclass
class _Entry:
    assignment_entity_status_id: int
    form_item_id: int
    value: Any
    disagg_data: Any
    data_not_available: bool
    not_applicable: bool


@dataclass(frozen=True)
class ItemView:
    id: int
    template_id: int
    item_type: str
    label: str
    section_name: str
    bank_id: int | None
    bank_name: str | None
    bank_area: str | None


def classify_item(item: ItemView) -> str:
    """One role per form item. Matrix roles are emitted as cells; the rest as measures."""
    label = (item.label or "").strip().lower()
    section = (item.section_name or "").strip().lower()
    if item.item_type == "question" or "comment" in section:
        return "comment"
    if item.template_id == REPORT_TEMPLATE_ID:
        return _classify_report(item, label)
    if item.template_id == PLAN_TEMPLATE_ID:
        return _classify_plan(item, label)
    if item.template_id == PNS_REPORT_TEMPLATE_ID:
        return _classify_pns(item, label)
    return "skip"


def _classify_report(item: ItemView, label: str) -> str:
    if _matches(label, REPORT_LABEL_NEEDLES["support"]) or item.id == REPORT_ITEM_FALLBACKS["support"]:
        return "support"
    if item.id in _REPORT_FUNDING_IDS or any(
        _matches(label, REPORT_LABEL_NEEDLES[key]) for key in ("funding_sources", "expenditure", "sp_breakdown")
    ):
        return "funding"
    if _is_ns_expenditure(item):
        return "expenditure"
    if item.bank_id in _KPI_BANK_ID_SET or label in _NS_LABELS:
        return "ns_data"
    if item.item_type == "indicator" and "bilateral" not in (item.section_name or "").lower():
        return "core"
    return "skip"


def _classify_plan(item: ItemView, label: str) -> str:
    if _matches(label, PLAN_LABEL_NEEDLES["support"]) or item.id == PLAN_ITEM_FALLBACKS["support"]:
        return "activity"
    if _matches(label, PLAN_LABEL_NEEDLES["reach_emergency"]) or item.id == PLAN_ITEM_FALLBACKS["reach_emergency"]:
        return "emergency"
    if _matches(label, PLAN_LABEL_NEEDLES["reach_longer_term"]) or item.id == PLAN_ITEM_FALLBACKS["reach_longer_term"]:
        return "reach"
    if item.id in _PLAN_FUNDING_IDS or _matches(label, PLAN_LABEL_NEEDLES["funding_y0"]):
        return "plan_funding"
    if item.bank_id in _KPI_BANK_ID_SET or label in _NS_LABELS:
        return "ns_data"
    return "skip"


def _classify_pns(item: ItemView, label: str) -> str:
    if "staff" in label or "delegate" in label:
        return "skip"
    if item.item_type == "matrix" or _matches(label, PNS_REPORT_LABEL_NEEDLES["funding"]):
        return "pns_funding"
    if "fund" in label or "expend" in label:
        return "pns_funding"
    return "skip"


def _matches(label: str, needles: tuple[str, ...]) -> bool:
    return any(needle in label for needle in needles)


def _is_ns_expenditure(item: ItemView) -> bool:
    for raw in (item.bank_name, item.label):
        text = (raw or "").strip().lower()
        if "total expenditure" in text and "national society" in text:
            return True
    return False


def availability_label(*, data_not_available: bool, not_applicable: bool) -> str:
    if not_applicable:
        return "Not Applicable"
    if data_not_available:
        return "Applicable- data not available"
    return "Applicable"


def attribute_label(key: str) -> str:
    if key in _DISAGG_LABELS:
        return _DISAGG_LABELS[key]
    text = key.replace("__", " <").replace("_", " ").strip()
    if not text:
        return key
    return text[0].upper() + text[1:]


def spef_label(code: str | None) -> str | None:
    mapped = _area_code(code) or section_to_area(code)
    if not mapped:
        token = (code or "").strip()
        if not token:
            return None
        mapped = token
    if mapped == "CC1":
        return AREA_LABELS["CC1"]
    return mapped


def indicator_name(item: ItemView) -> str:
    return strip_trailing_period(item.bank_name or item.label or "")


def horizon_year(period_name: str | None, label: str | None, item_id: int | None = None) -> int | None:
    years = planning_years(period_name)
    if not years:
        return None
    lower = (label or "").lower()
    if any(token in lower for token in ("+2", "year 3", "y2")):
        return years[min(2, len(years) - 1)]
    if any(token in lower for token in ("+1", "year 2", "y1")):
        return years[min(1, len(years) - 1)]
    for year in years:
        if str(year) in lower:
            return year
    offset = _PLAN_YEAR_OFFSET.get(item_id) if item_id is not None else None
    if offset is not None:
        return years[min(offset, len(years) - 1)]
    return years[0]


def ea_code_from_text(text: str | None) -> str | None:
    match = _EA_CODE_RE.search(text or "")
    if not match:
        return None
    code = match.group(1).strip()
    return code or None


def iter_measure_points(
    value: Any,
    disagg: Any,
    *,
    yes_no: bool = False,
) -> Iterator[tuple[str, float]]:
    """Scalar value is attribute Total. Disagg keys are additional attributes.

    A stored total is skipped when the scalar already supplied Total, so the
    same amount is not emitted twice.
    """
    scalar = _yes_no_number(value) if yes_no else to_number(value)
    if yes_no and _is_yes_no(value):
        if scalar is None:
            scalar_emitted = False
        else:
            yield "Total", scalar
            scalar_emitted = True
    elif scalar is not None:
        yield "Total", scalar
        scalar_emitted = True
    else:
        scalar_emitted = False

    values = _disagg_values(disagg)
    for key, raw in values.items():
        if key == "total" and scalar_emitted:
            continue
        number = _yes_no_number(raw) if yes_no else to_number(raw)
        if number is None:
            continue
        yield attribute_label(str(key)), number


def _is_yes_no(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in {"yes", "no"}


def _yes_no_number(value: Any) -> float | None:
    if _is_yes_no(value):
        return 1.0 if value.strip().lower() == "yes" else None
    return to_number(value)


def _disagg_values(disagg: Any) -> dict[str, Any]:
    if not isinstance(disagg, dict):
        return {}
    values = disagg.get("values") if "values" in disagg else disagg
    if not isinstance(values, dict):
        return {}
    return {
        str(key): raw
        for key, raw in values.items()
        if isinstance(key, str) and not key.startswith("_") and key not in {"mode", "values"}
    }


def _json_number(number: float) -> int | float:
    if number == int(number):
        return int(number)
    return float(number)


def assignment_year(place: dict[str, Any]) -> int | None:
    """Return an integer year for every supported UPR round."""
    period_year = _year_token(str(place.get("period_name") or ""))
    if period_year is not None:
        return period_year
    match = re.fullmatch(r"(?:P|AR|MYR)(\d{2})", str(place.get("round") or "").strip().upper())
    if not match:
        return None
    return 2000 + int(match.group(1))


def blank_fact(place: dict[str, Any]) -> dict[str, Any]:
    return {
        "Round": place.get("round") or None,
        "ISO3": place.get("iso3"),
        "Country": place.get("country"),
        "NS": place.get("ns"),
        "Region": place.get("region"),
        "Table": None,
        "SectionB": None,
        "Source": place.get("source") or "Country Data",
        "Entity": None,
        "Attribute": None,
        "SP/EF": None,
        "Applicable/Data not available": "Applicable",
        "Indicator": None,
        "Value": None,
        "ValueNum": None,
        "Year": assignment_year(place),
        "EA Code": None,
        "assigned_form_id": place.get("assigned_form_id"),
        "submission_id": place.get("submission_id"),
        "template": place.get("template"),
    }


def _with_value(row: dict[str, Any], number: float) -> dict[str, Any]:
    rendered = _json_number(number)
    row["Value"] = rendered
    row["ValueNum"] = rendered
    return row


def measure_facts(
    place: dict[str, Any],
    *,
    table: str,
    indicator: str | None,
    section: str | None,
    spef: str | None,
    year: int | None,
    value: Any,
    disagg: Any,
    data_not_available: bool,
    not_applicable: bool,
    yes_no: bool = False,
    ea_code: str | None = None,
) -> list[dict[str, Any]]:
    points = list(iter_measure_points(value, disagg, yes_no=yes_no))
    status = availability_label(data_not_available=data_not_available, not_applicable=not_applicable)
    if not points:
        if status == "Applicable":
            return []
        row = blank_fact(place)
        row.update(
            {
                "Table": table,
                "SectionB": section,
                "Indicator": indicator,
                "Attribute": "Total",
                "SP/EF": spef,
                "Year": year if year is not None else assignment_year(place),
                "EA Code": ea_code,
                "Applicable/Data not available": status,
            }
        )
        return [row]
    rows = []
    for attribute, number in points:
        row = blank_fact(place)
        row.update(
            {
                "Table": table,
                "SectionB": section,
                "Indicator": indicator,
                "Attribute": attribute,
                "SP/EF": spef,
                "Year": year if year is not None else assignment_year(place),
                "EA Code": ea_code,
                "Applicable/Data not available": status,
            }
        )
        rows.append(_with_value(row, number))
    return rows


def facts_for_item(
    item: ItemView,
    role: str,
    place: dict[str, Any],
    *,
    value: Any,
    disagg: Any,
    data_not_available: bool = False,
    not_applicable: bool = False,
    ns_by_id: dict[int, str] | None = None,
    emergency_index: dict[tuple[int, str], int] | None = None,
) -> list[dict[str, Any]]:
    if role == "comment" or role == "skip":
        return []
    ns_by_id = ns_by_id or {}
    if emergency_index is None:
        emergency_index = {}
    if role in _MATRIX_ROLES:
        return _matrix_facts(
            item,
            role,
            place,
            disagg,
            ns_by_id=ns_by_id,
            emergency_index=emergency_index,
        )
    table, section, indicator = _scalar_labels(item, role)
    spef = spef_label(item.bank_area) or spef_label(item.section_name)
    if place.get("template") == "plan":
        section = None
    return measure_facts(
        place,
        table=table,
        indicator=indicator,
        section=section,
        spef=spef,
        year=None,
        value=value,
        disagg=None if _disagg_mode(disagg) == "matrix" else disagg,
        data_not_available=data_not_available,
        not_applicable=not_applicable,
    )


def _scalar_labels(item: ItemView, role: str) -> tuple[str, str | None, str]:
    if role == "expenditure":
        return "Funding", "Funding", "Expenditure"
    if role == "ns_data":
        return "NS Data", "NS Data", indicator_name(item)
    return "Core indicators", "Core indicators", indicator_name(item)


def _disagg_mode(disagg: Any) -> str | None:
    if isinstance(disagg, dict):
        mode = disagg.get("mode")
        return str(mode) if mode else None
    return None


def _matrix_facts(
    item: ItemView,
    role: str,
    place: dict[str, Any],
    disagg: Any,
    *,
    ns_by_id: dict[int, str],
    emergency_index: dict[tuple[int, str], int],
) -> list[dict[str, Any]]:
    cells = _matrix_cells_from_disagg(disagg)
    if role == "support":
        return _support_facts(place, cells, ns_by_id, table="Support")
    if role == "activity":
        return _support_facts(place, cells, ns_by_id, table="Activities", only_one=True)
    if role == "funding":
        return _report_funding_facts(place, cells)
    if role == "plan_funding":
        return _plan_funding_facts(item, place, cells, ns_by_id)
    if role == "pns_funding":
        return _pns_funding_facts(place, cells, ns_by_id)
    if role == "reach":
        return _reach_facts(item, place, cells, ns_by_id, emergencies=False, emergency_index=emergency_index)
    if role == "emergency":
        return _reach_facts(item, place, cells, ns_by_id, emergencies=True, emergency_index=emergency_index)
    return []


def _matrix_cells_from_disagg(disagg: Any) -> dict[str, Any]:
    if not isinstance(disagg, dict):
        return {}
    values = disagg.get("values") if "values" in disagg else disagg
    if not isinstance(values, dict):
        return {}
    return {
        str(key): raw
        for key, raw in values.items()
        if isinstance(key, str) and not key.startswith("_") and key not in {"mode", "values"}
    }


def _named_row(row: str, ns_by_id: dict[int, str]) -> tuple[str | None, str | None]:
    """Return ``(entity, ns_name)`` for a matrix row."""
    if not row:
        return None, None
    named = _funding_entity(row)
    if named:
        return named, None
    if row.isdigit():
        return "PNS", ns_by_id.get(int(row))
    return None, None


def _support_facts(
    place: dict[str, Any],
    cells: dict[str, Any],
    ns_by_id: dict[int, str],
    *,
    table: str,
    only_one: bool = False,
) -> list[dict[str, Any]]:
    section = table if place.get("template") != "plan" else None
    rows = []
    for row_key, col, number in _iter_matrix_numbers(cells):
        if not row_key or (col or "").strip().lower() == "total":
            continue
        if only_one and number != 1:
            continue
        spef, _, attribute = (col or "").partition(" ")
        _, ns_name = _named_row(row_key, ns_by_id)
        if ns_name is None and not row_key.isdigit():
            ns_name = row_key
        fact = blank_fact(place)
        fact.update(
            {
                "Table": table,
                "SectionB": section,
                "Entity": "PNS",
                "NS": ns_name or place.get("ns"),
                "Attribute": attribute or None,
                "SP/EF": spef_label(spef),
                "Indicator": "Planned Bilateral Support" if table == "Activities" else None,
            }
        )
        rows.append(_with_value(fact, number))
    return rows


def _report_funding_indicator(col: str) -> str | None:
    lower = (col or "").strip().lower()
    if not lower:
        return None
    if "expenditure" in lower:
        return "Expenditure"
    if "funding" in lower or lower in {"ns_fun", "ns fun", "total", "row_total"}:
        return "Funding"
    return None


def _report_funding_facts(place: dict[str, Any], cells: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row_key, col, number in _iter_matrix_numbers(cells):
        indicator = _report_funding_indicator(col)
        if indicator is None:
            continue
        lower_col = (col or "").strip().lower()
        entity, _ns = _named_row(row_key, {})
        if not (row_key or "").strip():
            if "expenditure" in lower_col or "funding" in lower_col:
                continue
            attribute = "Total"
            spef = None
            entity_name = None
        elif entity:
            attribute = "Funding Source"
            spef = None
            entity_name = entity
        else:
            attribute = "SP Breakdown"
            spef = spef_label(row_key)
            entity_name = None
        fact = blank_fact(place)
        fact.update(
            {
                "Table": "Funding",
                "SectionB": "Funding",
                "Source": "Country Data",
                "Entity": entity_name,
                "Attribute": attribute,
                "SP/EF": spef,
                "Indicator": indicator,
            }
        )
        rows.append(_with_value(fact, number))
    return rows


def _plan_funding_facts(
    item: ItemView,
    place: dict[str, Any],
    cells: dict[str, Any],
    ns_by_id: dict[int, str],
) -> list[dict[str, Any]]:
    year = horizon_year(place.get("period_name"), item.label, item.id)
    rows = []
    for row_key, col, number in _iter_matrix_numbers(cells):
        if (col or "").strip().lower() in {"total", "row_total"}:
            attribute = "Total"
            spef = None
        else:
            bucket = _funding_column_bucket(col)
            spef = spef_label(col)
            if bucket == "emergency":
                attribute = "Emergency Operations"
            elif bucket == "longer_term":
                attribute = "Longer-term"
            else:
                attribute = col or None
        entity, _ns_name = _named_row(row_key, ns_by_id)
        fact = blank_fact(place)
        fact.update(
            {
                "Table": "FR_Country",
                "SectionB": None,
                "Entity": entity or (row_key or None),
                "NS": place.get("ns"),
                "Attribute": attribute,
                "SP/EF": spef,
                "Indicator": "Funding",
                "Year": year,
            }
        )
        rows.append(_with_value(fact, number))
    return rows


def _pns_column_indicator(col: str) -> str | None:
    lower = (col or "").strip().lower()
    if not lower or lower in {"total", "row_total"}:
        return None
    if any(token in lower for token in ("staff", "delegate", "funding requirement")):
        return None
    if "expend" in lower:
        return "Expenditure"
    if "transfer" in lower:
        return "Transferred"
    if "fund" in lower:
        return "Funding"
    return None


def _pns_funding_facts(
    place: dict[str, Any],
    cells: dict[str, Any],
    ns_by_id: dict[int, str],
) -> list[dict[str, Any]]:
    rows = []
    for row_key, col, number in _iter_matrix_numbers(cells):
        indicator = _pns_column_indicator(col)
        if indicator is None:
            continue
        host = ns_by_id.get(int(row_key)) if row_key.isdigit() else (row_key or None)
        fact = blank_fact(place)
        fact.update(
            {
                "Table": "Funding",
                "SectionB": "Funding",
                "Source": "PNS Data",
                "Entity": host,
                "Attribute": "Funding Source",
                "SP/EF": spef_label((col or "").split(" ", 1)[0]),
                "Indicator": indicator,
            }
        )
        rows.append(_with_value(fact, number))
    return rows


def _reach_facts(
    item: ItemView,
    place: dict[str, Any],
    cells: dict[str, Any],
    ns_by_id: dict[int, str],
    *,
    emergencies: bool,
    emergency_index: dict[tuple[int, str], int],
) -> list[dict[str, Any]]:
    year = horizon_year(place.get("period_name"), item.label, item.id)
    submission_id = place.get("submission_id")
    rows = []
    for row_key, col, number in _iter_matrix_numbers(cells):
        entity, ns_name = _named_row(row_key, ns_by_id)
        label = row_key if not row_key.isdigit() else (ns_name or row_key)
        fact = blank_fact(place)
        fact.update(
            {
                "Table": "Emergencies" if emergencies else "Reach",
                "SectionB": None,
                "Entity": entity,
                "NS": place.get("ns"),
                "Attribute": _emergency_attribute(emergency_index, submission_id, label) if emergencies else (col or None),
                "SP/EF": spef_label(col),
                "Indicator": "People to be reached",
                "Year": year,
                "EA Code": ea_code_from_text(label) if emergencies else None,
            }
        )
        rows.append(_with_value(fact, number))
    return rows


def _emergency_attribute(index: dict[tuple[int, str], int], submission_id: Any, label: str) -> str:
    key = (int(submission_id or 0), label)
    if key not in index:
        used = sum(1 for sub, _label in index if sub == key[0])
        index[key] = used + 1
    return f"E{index[key]}"


def dynamic_facts(
    place: dict[str, Any],
    *,
    indicator: str,
    area: str | None,
    value: Any,
    disagg: Any,
    data_not_available: bool,
    not_applicable: bool,
    section_name: str | None,
    appeal_code: str | None,
    slot: int | None,
) -> list[dict[str, Any]]:
    if appeal_code or slot:
        table = f"Emergency {slot}" if slot else "Emergencies"
        section = appeal_code or section_name
        ea_code = appeal_code
    else:
        table = "Other indicators"
        section = "Other indicators"
        ea_code = None
    return measure_facts(
        place,
        table=table,
        indicator=strip_trailing_period(indicator),
        section=section,
        spef=spef_label(area),
        year=None,
        value=value,
        disagg=disagg,
        data_not_available=data_not_available,
        not_applicable=not_applicable,
        yes_no=True,
        ea_code=ea_code,
    )


def system_facts_from_snapshot(
    payload: dict[str, Any],
    *,
    regions_by_iso3: dict[str, str] | None = None,
    rounds: list[str] | None = None,
) -> list[dict[str, Any]]:
    """One row per country, bucket, metric, and round listed on the snapshot."""
    regions = regions_by_iso3 or {}
    wanted = {code.upper() for code in rounds} if rounds else None
    snapshot_rounds = [str(code) for code in (payload.get("rounds") or []) if code]
    if wanted is not None:
        snapshot_rounds = [code for code in snapshot_rounds if code.upper() in wanted]
    by_iso2 = payload.get("by_iso2") if isinstance(payload.get("by_iso2"), dict) else {}
    year = None
    for period in payload.get("period_names") or []:
        year = _year_token(str(period))
        if year:
            break
    rows: list[dict[str, Any]] = []
    buckets = (("longer_term", "Longer-term"), ("emergency", "Emergency Operations"))
    for code in snapshot_rounds:
        for rec in by_iso2.values():
            if not isinstance(rec, dict):
                continue
            iso3 = str(rec.get("iso3") or "").strip().upper() or None
            country = rec.get("country")
            if _is_testland(country, iso3):
                continue
            for bucket_key, attribute in buckets:
                metrics = rec.get(bucket_key)
                if not isinstance(metrics, dict):
                    continue
                for metric_key, indicator in (("funding", "Funding"), ("expenditure", "Expenditure")):
                    number = _usable_ifrc_actual(metrics.get(metric_key))
                    if number is None:
                        continue
                    fact = blank_fact(
                        {
                            "round": code,
                            "iso3": iso3,
                            "country": country,
                            "ns": "IFRC Secretariat",
                            "region": regions.get(iso3 or ""),
                            "source": "IFRC System",
                            "template": "report",
                        }
                    )
                    fact.update(
                        {
                            "Table": "Funding",
                            "SectionB": "Funding",
                            "Entity": "IFRC Secretariat",
                            "Attribute": attribute,
                            "Indicator": indicator,
                            "Year": year,
                        }
                    )
                    rows.append(_with_value(fact, number))
    return rows


def blank_master(place: dict[str, Any]) -> dict[str, Any]:
    reported = None
    if place.get("template") == "pns" and _status_text(place.get("status")).lower() in {"submitted", "approved"}:
        reported = "Yes"
    return {
        "ISO3": place.get("iso3"),
        "Country": place.get("country"),
        "Round": place.get("round") or None,
        "Year": assignment_year(place),
        "Section": None,
        "SectionB": None,
        "Entity": "HNS",
        "NS": place.get("ns"),
        "Source": place.get("source") or "Country Data",
        "Area": "Total",
        "Attribute": "Total",
        "Indicator": None,
        "indicatorId": None,
        "ValueNum": None,
        "Country Value": None,
        "PNS Value": None,
        "Value": None,
        "UPR Value": None,
        "EA Code": None,
        "Applicable/Data not available": "Applicable",
        "PNS reported": reported,
    }


def _sheet_indicator_id(item: ItemView, indicator: str | None) -> int | None:
    if item.bank_id:
        return int(item.bank_id)
    return _SHEET_INDICATOR_IDS.get(indicator or "")


def _master_total(value: Any, disagg: Any, *, yes_no: bool = False) -> float | None:
    """One flat amount. Sex/age parts stay out of this sheet."""
    for attribute, number in iter_measure_points(value, disagg, yes_no=yes_no):
        if attribute == "Total":
            return number
    return None


def _put_master_amount(row: dict[str, Any], number: float, *, funding: bool) -> dict[str, Any]:
    rendered = _json_number(number)
    row["ValueNum"] = rendered
    if funding and row.get("Source") == "PNS Data":
        row["PNS Value"] = rendered
    elif funding:
        row["Country Value"] = rendered
    return row


def master_rows_for_item(
    item: ItemView,
    role: str,
    place: dict[str, Any],
    *,
    value: Any,
    disagg: Any,
    data_not_available: bool = False,
    not_applicable: bool = False,
    ns_by_id: dict[int, str] | None = None,
    ns_country_by_id: dict[int, dict[str, Any]] | None = None,
    emergency_index: dict[tuple[int, str], int] | None = None,
) -> list[dict[str, Any]]:
    """One UPR Data-sheet row per area, not per disaggregation."""
    if role in {"comment", "skip"}:
        return []
    ns_by_id = ns_by_id or {}
    ns_country_by_id = ns_country_by_id or {}
    if emergency_index is None:
        emergency_index = {}
    if role in _MATRIX_ROLES:
        return _master_matrix_rows(
            item,
            role,
            place,
            disagg,
            ns_by_id=ns_by_id,
            ns_country_by_id=ns_country_by_id,
            emergency_index=emergency_index,
        )
    total = _master_total(value, None if _disagg_mode(disagg) == "matrix" else disagg)
    status = availability_label(data_not_available=data_not_available, not_applicable=not_applicable)
    if total is None and status == "Applicable":
        return []
    section, area = _master_scalar_section(item, role)
    row = blank_master(place)
    row.update(
        {
            "Section": section,
            "Area": area,
            "Attribute": "Total",
            "Indicator": "Expenditure" if role == "expenditure" else indicator_name(item),
            "indicatorId": _sheet_indicator_id(item, "Expenditure" if role == "expenditure" else indicator_name(item)),
            "Applicable/Data not available": status,
            "Year": (
                horizon_year(place.get("period_name"), item.label, item.id)
                if place.get("template") == "plan"
                else assignment_year(place)
            ),
        }
    )
    if total is None:
        return [row]
    return [_put_master_amount(row, total, funding=role == "expenditure")]


def _master_scalar_section(item: ItemView, role: str) -> tuple[str, str]:
    if role == "expenditure":
        return "Funding", "Total"
    if role == "ns_data":
        return "NS Data", "Total"
    return "Core indicators", spef_label(item.bank_area) or spef_label(item.section_name) or "Total"


def _master_matrix_rows(
    item: ItemView,
    role: str,
    place: dict[str, Any],
    disagg: Any,
    *,
    ns_by_id: dict[int, str],
    ns_country_by_id: dict[int, dict[str, Any]],
    emergency_index: dict[tuple[int, str], int],
) -> list[dict[str, Any]]:
    cells = _matrix_cells_from_disagg(disagg)
    if role in {"support", "activity"}:
        return _master_support_rows(item, place, cells, ns_by_id, planned=role == "activity")
    if role == "funding":
        return _master_report_funding_rows(place, cells)
    if role == "plan_funding":
        return _master_plan_funding_rows(item, place, cells)
    if role == "pns_funding":
        return _master_pns_funding_rows(place, cells, ns_country_by_id)
    if role in {"reach", "emergency"}:
        return _master_reach_rows(item, place, cells, emergencies=role == "emergency", emergency_index=emergency_index)
    return []


def _master_support_rows(
    item: ItemView,
    place: dict[str, Any],
    cells: dict[str, Any],
    ns_by_id: dict[int, str],
    *,
    planned: bool,
) -> list[dict[str, Any]]:
    indicator = "Bilateral Support" if planned else "Received support"
    rows = []
    for row_key, col, number in _iter_matrix_numbers(cells):
        if not row_key or (col or "").strip().lower() == "total":
            continue
        if planned and number != 1:
            continue
        area, _, attribute = (col or "").partition(" ")
        _, ns_name = _named_row(row_key, ns_by_id)
        if ns_name is None and not row_key.isdigit():
            ns_name = row_key
        row = blank_master(place)
        row.update(
            {
                "Section": "Support",
                "Entity": "PNS",
                "NS": ns_name or place.get("ns"),
                "Area": spef_label(area) or "Total",
                "Attribute": attribute or "Total",
                "Indicator": indicator,
                "indicatorId": _sheet_indicator_id(item, indicator),
            }
        )
        rows.append(_put_master_amount(row, number, funding=False))
    return rows


def _master_report_funding_rows(place: dict[str, Any], cells: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row_key, col, number in _iter_matrix_numbers(cells):
        indicator = _report_funding_indicator(col)
        if indicator is None:
            continue
        lower_col = (col or "").strip().lower()
        entity, _ns = _named_row(row_key, {})
        if not (row_key or "").strip():
            if "expenditure" in lower_col or "funding" in lower_col:
                continue
            attribute = "Total"
            area = "Total"
            entity_name = "HNS"
        elif entity:
            attribute = "Funding Source"
            area = "Total"
            entity_name = entity
        else:
            attribute = "SP Breakdown"
            area = spef_label(row_key) or "Total"
            entity_name = "HNS"
        row = blank_master(place)
        row.update(
            {
                "Section": "Funding",
                "Entity": entity_name,
                "Area": area,
                "Attribute": attribute,
                "Indicator": indicator,
                "indicatorId": _SHEET_INDICATOR_IDS.get(indicator),
            }
        )
        rows.append(_put_master_amount(row, number, funding=True))
    return rows


def _master_plan_funding_rows(item: ItemView, place: dict[str, Any], cells: dict[str, Any]) -> list[dict[str, Any]]:
    year = horizon_year(place.get("period_name"), item.label, item.id)
    rows = []
    for row_key, col, number in _iter_matrix_numbers(cells):
        entity, _ns_name = _named_row(row_key, {})
        lower_col = (col or "").strip().lower()
        area = "Total" if lower_col in {"total", "row_total"} else (spef_label(col) or col or "Total")
        row = blank_master(place)
        row.update(
            {
                "Section": "Funding",
                "Entity": entity or "HNS",
                "Area": area,
                "Attribute": "Total",
                "Indicator": "Funding Requirement",
                "indicatorId": _SHEET_INDICATOR_IDS["Funding Requirement"],
                "Year": year,
            }
        )
        rows.append(_put_master_amount(row, number, funding=True))
    return rows


def _master_pns_funding_rows(
    place: dict[str, Any],
    cells: dict[str, Any],
    ns_country_by_id: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for row_key, col, number in _iter_matrix_numbers(cells):
        indicator = _pns_column_indicator(col)
        if indicator is None:
            continue
        host = ns_country_by_id.get(int(row_key)) if row_key.isdigit() else None
        row = blank_master(place)
        row.update(
            {
                "ISO3": (host or {}).get("iso3") or place.get("iso3"),
                "Country": (host or {}).get("country") or place.get("country"),
                "Section": "Funding",
                "Entity": "PNS",
                "NS": place.get("ns"),
                "Source": "PNS Data",
                "Area": spef_label((col or "").split(" ", 1)[0]) or "Total",
                "Attribute": "Total",
                "Indicator": indicator,
                "indicatorId": _SHEET_INDICATOR_IDS.get(indicator),
            }
        )
        rows.append(_put_master_amount(row, number, funding=True))
    return rows


def _master_reach_rows(
    item: ItemView,
    place: dict[str, Any],
    cells: dict[str, Any],
    *,
    emergencies: bool,
    emergency_index: dict[tuple[int, str], int],
) -> list[dict[str, Any]]:
    year = horizon_year(place.get("period_name"), item.label, item.id)
    rows = []
    for row_key, col, number in _iter_matrix_numbers(cells):
        _entity, ns_name = _named_row(row_key, {})
        label = row_key if not str(row_key).isdigit() else (ns_name or row_key)
        if emergencies:
            slot = _emergency_attribute(emergency_index, place.get("submission_id"), label)
            area = "EA" + slot[1:]
            ea_code = ea_code_from_text(label)
        else:
            area = spef_label(col) or (col or "Total")
            ea_code = None
        row = blank_master(place)
        row.update(
            {
                "Section": "Reach",
                "Area": area,
                "Attribute": "Total",
                "Indicator": "People to be reached",
                "indicatorId": _sheet_indicator_id(item, "People to be reached"),
                "Year": year,
                "EA Code": ea_code,
            }
        )
        rows.append(_put_master_amount(row, number, funding=False))
    return rows


def master_dynamic_rows(
    place: dict[str, Any],
    *,
    indicator: str,
    indicator_id: int | None,
    area: str | None,
    value: Any,
    disagg: Any,
    data_not_available: bool,
    not_applicable: bool,
    appeal_code: str | None,
    slot: int | None,
) -> list[dict[str, Any]]:
    total = _master_total(value, disagg, yes_no=True)
    status = availability_label(data_not_available=data_not_available, not_applicable=not_applicable)
    if total is None and status == "Applicable":
        return []
    if appeal_code or slot:
        section = f"Emergency {slot}" if slot else "Emergencies"
        section_b = appeal_code
        ea_code = appeal_code
    else:
        section = "Other indicators"
        section_b = None
        ea_code = None
    row = blank_master(place)
    row.update(
        {
            "Section": section,
            "SectionB": section_b,
            "Area": spef_label(area) or "Total",
            "Attribute": "Total",
            "Indicator": strip_trailing_period(indicator),
            "indicatorId": indicator_id,
            "EA Code": ea_code,
            "Applicable/Data not available": status,
        }
    )
    if total is None:
        return [row]
    return [_put_master_amount(row, total, funding=False)]


def master_comment_row(place: dict[str, Any], item: ItemView, text: str) -> dict[str, Any]:
    row = blank_master(place)
    row.update(
        {
            "Section": "Comments",
            "Area": "Total",
            "Attribute": "Total",
            "Indicator": indicator_name(item) or None,
            "indicatorId": item.bank_id,
            "Value": text,
            "UPR Value": text,
        }
    )
    return row


def submission_row(place: dict[str, Any], *, status: str, submitted_at: Any, due_date: Any) -> dict[str, Any]:
    validated = "Validated" if (status or "").lower() == AssignmentEntityStatusValue.approved.value else None
    return {
        "Round": place.get("round") or None,
        "Country": place.get("country"),
        "Region": place.get("region"),
        "NS": place.get("ns"),
        "ISO3": place.get("iso3"),
        "status": status or None,
        "fds_validated": validated,
        "submitted_at": _iso(submitted_at),
        "due_date": _iso(due_date),
        "assigned_form_id": place.get("assigned_form_id"),
        "submission_id": place.get("submission_id"),
        "template": place.get("template"),
    }


def comment_row(place: dict[str, Any], text: str) -> dict[str, Any]:
    return {
        "Round": place.get("round") or None,
        "Country": place.get("country"),
        "ISO3": place.get("iso3"),
        "NS": place.get("ns"),
        "Value": text,
        "template": place.get("template"),
        "assigned_form_id": place.get("assigned_form_id"),
        "submission_id": place.get("submission_id"),
    }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    return iso() if callable(iso) else str(value)


def _is_testland(country: Any, iso3: Any) -> bool:
    if str(iso3 or "").strip().upper() == "TST":
        return True
    return str(country or "").strip().lower() == "testland"


def build_upr_data(
    *,
    template: str | None = None,
    round_code: str | None = None,
    iso3: str | None = None,
    table: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Load UPR assignments and return facts, submissions, and comments."""
    template_ids = _template_ids(template)
    places = _load_places(template_ids, iso3=iso3, round_code=round_code)
    ns_by_id, ns_by_country, _ns_country = _load_national_societies()
    for place in places:
        if not place.get("ns") and place.get("country_id"):
            place["ns"] = ns_by_country.get(place["country_id"])

    aes_ids = [place["submission_id"] for place in places]
    entries = _load_form_data(aes_ids)
    items = _load_items({entry.form_item_id for entry in entries})
    emergency_index: dict[tuple[int, str], int] = {}
    facts: list[dict[str, Any]] = []
    comments: list[dict[str, Any]] = []
    by_submission = {place["submission_id"]: place for place in places}

    for entry in entries:
        place = by_submission.get(entry.assignment_entity_status_id)
        item = items.get(entry.form_item_id)
        if place is None or item is None:
            continue
        role = classify_item(item)
        if role == "comment":
            text = (entry.value or "").strip()
            if text:
                comments.append(comment_row(place, text))
            continue
        facts.extend(
            facts_for_item(
                item,
                role,
                place,
                value=entry.value,
                disagg=entry.disagg_data,
                data_not_available=bool(entry.data_not_available),
                not_applicable=bool(entry.not_applicable),
                ns_by_id=ns_by_id,
                emergency_index=emergency_index,
            )
        )

    facts.extend(_dynamic_facts(places, by_submission))
    if template in (None, "report"):
        facts.extend(_system_facts(round_code=round_code, iso3=iso3))

    if table:
        wanted = table.strip().lower()
        facts = [row for row in facts if str(row.get("Table") or "").strip().lower() == wanted]
    if iso3:
        code = iso3.strip().upper()
        facts = [row for row in facts if str(row.get("ISO3") or "").upper() == code]
        comments = [row for row in comments if str(row.get("ISO3") or "").upper() == code]

    submissions = [
        submission_row(
            place,
            status=_status_text(place.get("status")),
            submitted_at=place.get("submitted_at"),
            due_date=place.get("due_date"),
        )
        for place in places
    ]
    return {"data": facts, "submissions": submissions, "comments": comments}


def build_upr_submissions(
    *,
    template: str | None = None,
    round_code: str | None = None,
    iso3: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return country assignment statuses across all matching UPR rounds."""
    places = _load_places(_template_ids(template), iso3=iso3, round_code=round_code)
    _ns_by_id, ns_by_country, _ns_country = _load_national_societies()
    for place in places:
        if not place.get("ns") and place.get("country_id"):
            place["ns"] = ns_by_country.get(place["country_id"])

    rows = [
        submission_row(
            place,
            status=_status_text(place.get("status")),
            submitted_at=place.get("submitted_at"),
            due_date=place.get("due_date"),
        )
        for place in places
    ]
    rows.sort(
        key=lambda row: (
            str(row.get("Round") or ""),
            str(row.get("ISO3") or ""),
            str(row.get("template") or ""),
            int(row.get("assigned_form_id") or 0),
            int(row.get("submission_id") or 0),
        )
    )
    return {"data": rows}


def build_upr_master(
    *,
    template: str | None = None,
    round_code: str | None = None,
    iso3: str | None = None,
    section: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Rows shaped like the UPR Master workbook sheet ``UPR Data``.

    One row per country, round, section, and area. Sex/age breakdowns are
    collapsed to the total. IFRC system snapshots are not part of that sheet.
    """
    template_ids = _template_ids(template)
    places = _load_places(template_ids, iso3=iso3, round_code=round_code)
    ns_by_id, ns_by_country, ns_country_by_id = _load_national_societies()
    for place in places:
        if not place.get("ns") and place.get("country_id"):
            place["ns"] = ns_by_country.get(place["country_id"])

    aes_ids = [place["submission_id"] for place in places]
    entries = _load_form_data(aes_ids)
    items = _load_items({entry.form_item_id for entry in entries})
    emergency_index: dict[tuple[int, str], int] = {}
    rows: list[dict[str, Any]] = []
    by_submission = {place["submission_id"]: place for place in places}

    for entry in entries:
        place = by_submission.get(entry.assignment_entity_status_id)
        item = items.get(entry.form_item_id)
        if place is None or item is None:
            continue
        role = classify_item(item)
        if role == "comment":
            text = (entry.value or "").strip()
            if text:
                rows.append(master_comment_row(place, item, text))
            continue
        rows.extend(
            master_rows_for_item(
                item,
                role,
                place,
                value=entry.value,
                disagg=entry.disagg_data,
                data_not_available=bool(entry.data_not_available),
                not_applicable=bool(entry.not_applicable),
                ns_by_id=ns_by_id,
                ns_country_by_id=ns_country_by_id,
                emergency_index=emergency_index,
            )
        )

    rows.extend(_dynamic_facts(places, by_submission, master=True))
    if section:
        wanted = section.strip().lower()
        rows = [row for row in rows if str(row.get("Section") or "").strip().lower() == wanted]
    if iso3:
        code = iso3.strip().upper()
        rows = [row for row in rows if str(row.get("ISO3") or "").upper() == code]
    return {"data": rows}


def _template_ids(template: str | None) -> set[int]:
    if not template:
        return set(TEMPLATE_IDS)
    kind = template.strip().lower()
    return {template_id for template_id, name in TEMPLATE_KIND.items() if name == kind}


def _status_text(status: Any) -> str:
    value = getattr(status, "value", status)
    return "" if value is None else str(value)


def _load_places(template_ids: set[int], *, iso3: str | None, round_code: str | None) -> list[dict[str, Any]]:
    if not template_ids:
        return []
    rows = (
        db.session.query(
            AssignmentEntityStatus.id,
            AssignmentEntityStatus.assigned_form_id,
            AssignmentEntityStatus.entity_type,
            AssignmentEntityStatus.entity_id,
            AssignmentEntityStatus.status,
            AssignmentEntityStatus.submitted_at,
            AssignmentEntityStatus.due_date,
            AssignedForm.template_id,
            AssignedForm.period_name,
            Country.id,
            Country.name,
            Country.iso3,
            Country.iso2,
            Country.region,
        )
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .outerjoin(
            Country,
            and_(
                AssignmentEntityStatus.entity_type == "country",
                Country.id == AssignmentEntityStatus.entity_id,
            ),
        )
        .filter(AssignedForm.template_id.in_(template_ids))
        .filter(AssignmentEntityStatus.entity_type == "country")
        .all()
    )
    wanted_round = (round_code or "").strip().upper()
    wanted_iso = (iso3 or "").strip().upper()
    places = []
    for row in rows:
        country_name = row[10]
        country_iso3 = row[11]
        if _is_testland(country_name, country_iso3):
            continue
        if wanted_iso and str(country_iso3 or "").upper() != wanted_iso:
            continue
        template_id = int(row[7])
        kind = "plan" if template_id == PLAN_TEMPLATE_ID else "report"
        code = period_to_round(row[8], kind)
        if wanted_round and code.upper() != wanted_round:
            continue
        feed = TEMPLATE_KIND.get(template_id, "report")
        places.append(
            {
                "submission_id": row[0],
                "assigned_form_id": row[1],
                "status": row[4],
                "submitted_at": row[5],
                "due_date": row[6],
                "period_name": row[8],
                "country_id": row[9],
                "country": country_name,
                "iso3": country_iso3,
                "iso2": row[12],
                "region": row[13],
                "round": code,
                "template": feed,
                "source": "PNS Data" if feed == "pns" else "Country Data",
                "ns": None,
            }
        )
    return places


def _load_national_societies() -> tuple[dict[int, str], dict[int, str], dict[int, dict[str, Any]]]:
    rows = (
        db.session.query(
            NationalSociety.id,
            NationalSociety.country_id,
            NationalSociety.name,
            Country.iso3,
            Country.name,
        )
        .outerjoin(Country, NationalSociety.country_id == Country.id)
        .filter(NationalSociety.is_active.is_(True))
        .order_by(NationalSociety.display_order.asc().nullslast(), NationalSociety.id.asc())
        .all()
    )
    by_id: dict[int, str] = {}
    by_country: dict[int, str] = {}
    country_by_ns: dict[int, dict[str, Any]] = {}
    for ns_id, country_id, name, iso3, country_name in rows:
        by_id[int(ns_id)] = name
        if country_id is not None:
            by_country.setdefault(int(country_id), name)
        country_by_ns[int(ns_id)] = {"iso3": iso3, "country": country_name, "ns": name}
    return by_id, by_country, country_by_ns


def _chunks(ids: list[int] | set[int]) -> Iterator[list[int]]:
    ordered = list(ids)
    for start in range(0, len(ordered), _ID_CHUNK):
        yield ordered[start : start + _ID_CHUNK]


def _load_form_data(aes_ids: list[int]) -> list[_Entry]:
    if not aes_ids:
        return []
    found: list[_Entry] = []
    columns = (
        FormData.assignment_entity_status_id,
        FormData.form_item_id,
        FormData.value,
        FormData.disagg_data,
        FormData.data_not_available,
        FormData.not_applicable,
    )
    for chunk in _chunks(aes_ids):
        for row in db.session.query(*columns).filter(FormData.assignment_entity_status_id.in_(chunk)).all():
            found.append(_Entry(*row))
    return found


def _load_items(item_ids: set[int]) -> dict[int, ItemView]:
    if not item_ids:
        return {}
    views: dict[int, ItemView] = {}
    for chunk in _chunks(item_ids):
        items = (
            FormItem.query.options(joinedload(FormItem.form_section), joinedload(FormItem.indicator_bank))
            .filter(FormItem.id.in_(chunk))
            .all()
        )
        for item in items:
            bank = item.indicator_bank
            section = item.form_section
            views[item.id] = ItemView(
                id=item.id,
                template_id=int(item.template_id or 0),
                item_type=item.item_type or "",
                label=item.label or "",
                section_name=(section.name if section else "") or "",
                bank_id=item.indicator_bank_id,
                bank_name=(bank.name if bank else None),
                bank_area=(bank.area if bank else None),
            )
    return views


def _dynamic_facts(
    places: list[dict[str, Any]],
    by_submission: dict[int, dict[str, Any]],
    *,
    master: bool = False,
) -> list[dict[str, Any]]:
    report_ids = [place["submission_id"] for place in places if place.get("template") == "report"]
    if not report_ids:
        return []
    contexts = _load_contexts(report_ids)
    section_ids: set[int] = set()
    raw_rows = []
    for chunk in _chunks(report_ids):
        raw_rows.extend(
            db.session.query(
                DynamicIndicatorData.assignment_entity_status_id,
                DynamicIndicatorData.section_id,
                DynamicIndicatorData.repeat_instance_number,
                DynamicIndicatorData.value,
                DynamicIndicatorData.disagg_data,
                DynamicIndicatorData.data_not_available,
                DynamicIndicatorData.not_applicable,
                IndicatorBank.name,
                IndicatorBank.area,
                DynamicIndicatorData.indicator_bank_id,
            )
            .join(IndicatorBank, DynamicIndicatorData.indicator_bank_id == IndicatorBank.id)
            .filter(DynamicIndicatorData.assignment_entity_status_id.in_(chunk))
            .all()
        )
        for row in raw_rows:
            section_ids.add(int(row[1]))
    section_names = _section_names(section_ids)
    facts = []
    for row in raw_rows:
        place = by_submission.get(row[0])
        if place is None:
            continue
        ctx = contexts.get((row[0], int(row[1])))
        appeal = ctx.get("code") if ctx else None
        slot = ctx.get("slot") if ctx else None
        if appeal is None and row[2] is not None:
            slot = int(row[2])
        if master:
            facts.extend(
                master_dynamic_rows(
                    place,
                    indicator=row[7] or "",
                    indicator_id=int(row[9]) if row[9] is not None else None,
                    area=row[8],
                    value=row[3],
                    disagg=row[4],
                    data_not_available=bool(row[5]),
                    not_applicable=bool(row[6]),
                    appeal_code=appeal,
                    slot=slot,
                )
            )
            continue
        facts.extend(
            dynamic_facts(
                place,
                indicator=row[7] or "",
                area=row[8],
                value=row[3],
                disagg=row[4],
                data_not_available=bool(row[5]),
                not_applicable=bool(row[6]),
                section_name=section_names.get(int(row[1])),
                appeal_code=appeal,
                slot=slot,
            )
        )
    return facts


def _load_contexts(aes_ids: list[int]) -> dict[tuple[int, int], dict[str, Any]]:
    found: dict[tuple[int, int], dict[str, Any]] = {}
    for chunk in _chunks(aes_ids):
        rows = (
            db.session.query(
                DynamicSectionContext.assignment_entity_status_id,
                DynamicSectionContext.section_id,
                DynamicSectionContext.slot,
                DynamicSectionContext.context_key,
                DynamicSectionContext.provider_id,
            )
            .filter(DynamicSectionContext.assignment_entity_status_id.in_(chunk))
            .filter(DynamicSectionContext.status == "active")
            .all()
        )
        for aes_id, section_id, slot, context_key, provider_id in rows:
            key = (int(aes_id), int(section_id))
            current = found.get(key)
            if current and current.get("provider") == "emergency_operations" and provider_id != "emergency_operations":
                continue
            found[key] = {"slot": slot, "code": context_key, "provider": provider_id}
    return found


def _section_names(section_ids: set[int]) -> dict[int, str]:
    if not section_ids:
        return {}
    names: dict[int, str] = {}
    for chunk in _chunks(section_ids):
        for section_id, name in db.session.query(FormSection.id, FormSection.name).filter(FormSection.id.in_(chunk)):
            names[int(section_id)] = name or ""
    return names


def _system_facts(*, round_code: str | None, iso3: str | None) -> list[dict[str, Any]]:
    wanted = [round_code] if round_code else None
    seen_paths: set[str] = set()
    facts: list[dict[str, Any]] = []
    iso3s: set[str] = set()
    payloads = []
    for _round, (_slug, path) in _IFRC_ACTUALS_SNAPSHOTS.items():
        key = str(path)
        if key in seen_paths or not path.is_file():
            continue
        seen_paths.add(key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
            by_iso2 = payload.get("by_iso2") if isinstance(payload.get("by_iso2"), dict) else {}
            for rec in by_iso2.values():
                if isinstance(rec, dict) and rec.get("iso3"):
                    iso3s.add(str(rec["iso3"]).strip().upper())
    regions = _regions_for_iso3(iso3s)
    for payload in payloads:
        facts.extend(system_facts_from_snapshot(payload, regions_by_iso3=regions, rounds=wanted))
    if iso3:
        code = iso3.strip().upper()
        facts = [row for row in facts if str(row.get("ISO3") or "").upper() == code]
    return facts


def _regions_for_iso3(iso3s: set[str]) -> dict[str, str]:
    if not iso3s:
        return {}
    rows = db.session.query(Country.iso3, Country.region).filter(Country.iso3.in_(list(iso3s))).all()
    return {str(code).upper(): region for code, region in rows if code}
