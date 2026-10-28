"""Applicable emergencies for one UPR round, marked covered or not.

Each row is one appeal for one country. A round can collect the appeal on more
than one list (Emergency Appeals rows, Funding Requirements headers). The row
is covered only when every list that includes it has it saved.
"""

from __future__ import annotations

import re
from typing import Any

from plugins.emergency_operations.appeal_group import parse_operation_label
from plugins.upr.catalog import PLAN_TEMPLATE_ID, UPR_VALIDATION_TEMPLATE_IDS
from plugins.upr.formatters import to_number
from plugins.upr.validation.emergency_coverage import (
    EmergencyRef,
    FieldEmergencyCoverage,
    coverage_source_title,
    load_field_coverages,
    tracker_coverage_scope,
)

_COVERED = "covered"
_MISSING = "missing"
_NOT_APPLICABLE = "not_applicable"
_NO_LONGER = "no_longer"


def assemble_catalogue(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Turn per-country coverage into rows a validator can scan."""
    sections: list[str] = []
    rows: list[dict[str, Any]] = []
    ordered = sorted(entries, key=lambda entry: (str(entry.get("country_name") or ""), entry.get("country_id") or 0))
    for entry in ordered:
        fields = entry.get("fields") or []
        if not isinstance(fields, list):
            continue
        country_rows, country_sections = _country_rows(entry, fields)
        for section in country_sections:
            if section not in sections:
                sections.append(section)
        rows.extend(country_rows)
    applicable = [row for row in rows if row["status"] in (_COVERED, _MISSING)]
    return {
        "sections": _ordered_sections(sections),
        "rows": rows,
        "summary": {
            "applicable": len(applicable),
            "covered": sum(1 for row in applicable if row["status"] == _COVERED),
            "missing": sum(1 for row in applicable if row["status"] == _MISSING),
            "countries": len({row["country_id"] for row in applicable}),
        },
    }


def load_round_emergencies(template_id: int, period_name: str) -> dict[str, Any]:
    """Applicable emergencies for every country assigned to this round."""
    empty = assemble_catalogue([])
    if int(template_id) not in UPR_VALIDATION_TEMPLATE_IDS:
        return {"available": False, "template_id": template_id, "period": period_name, **empty}

    from sqlalchemy.orm import joinedload

    from app.models.assignments import AssignedForm, AssignmentEntityStatus
    from app.models.core import Country

    assignments = (
        AssignedForm.query.options(joinedload(AssignedForm.template))
        .filter(
            AssignedForm.template_id == int(template_id),
            AssignedForm.period_name == period_name,
        )
        .order_by(AssignedForm.id.desc())
        .all()
    )
    if not isinstance(assignments, list) or not assignments:
        return {"available": True, "template_id": template_id, "period": period_name, **empty}

    rank = {item.id: item.id or 0 for item in assignments}
    aes_rows = (
        AssignmentEntityStatus.query.filter(
            AssignmentEntityStatus.assigned_form_id.in_([item.id for item in assignments]),
            AssignmentEntityStatus.entity_type == "country",
        ).all()
    )
    aes_by_country: dict[int, Any] = {}
    for aes in aes_rows:
        current = aes_by_country.get(aes.entity_id)
        if current is None or rank.get(aes.assigned_form_id, 0) >= rank.get(current.assigned_form_id, 0):
            aes_by_country[aes.entity_id] = aes
    if not aes_by_country:
        return {"available": True, "template_id": template_id, "period": period_name, **empty}

    countries = {
        country.id: country
        for country in Country.query.filter(Country.id.in_(list(aes_by_country))).all()
    }
    entries: list[dict[str, Any]] = []
    unavailable = False
    aes_list = list(aes_by_country.values())
    with tracker_coverage_scope(aes_list):
        for country_id, aes in aes_by_country.items():
            country = countries.get(country_id)
            fields = load_field_coverages(aes)
            if fields is None:
                unavailable = True
                continue
            entries.append({
                "country_id": country_id,
                "country_name": getattr(country, "name", None) or "",
                "iso3": getattr(country, "iso3", None) or "",
                "fields": fields,
            })
    payload = assemble_catalogue(entries)
    attach_group_names(payload["rows"], _group_titles_from_catalogue())
    if int(template_id) == PLAN_TEMPLATE_ID:
        _attach_annualised_funding(
            payload,
            period_name=period_name,
            version_id=_published_version_id(assignments),
            aes_by_country=aes_by_country,
        )
    payload.update({
        "available": not unavailable or bool(payload["rows"]),
        "template_id": int(template_id),
        "period": period_name,
    })
    return payload


def _ordered_sections(sections: list[str]) -> list[str]:
    """People to be reached, then funding requirements, then any other list."""
    def rank(name: str) -> int:
        text = name.lower()
        if "people to be reached" in text or "emergency appeal" in text:
            return 0
        if "funding requirement" in text:
            return 1
        return 2

    return sorted(sections, key=rank)


def _country_rows(entry: dict[str, Any], fields: list[FieldEmergencyCoverage]) -> tuple[list[dict[str, Any]], list[str]]:
    sections: list[str] = []
    by_code: dict[str, dict[str, Any]] = {}
    for field in fields:
        section = field.section_name or "Emergency appeals"
        if section not in sections:
            sections.append(section)
        coverage = field.coverage
        missing = {op.code for op in coverage.missing if op.code}
        for op in coverage.applicable:
            if not op.code:
                continue
            row = _row_for(by_code, op)
            row["marks"][section] = _MISSING if op.code in missing else _COVERED
        for op in coverage.no_longer_applicable:
            if not op.code or op.code in {item.code for item in coverage.applicable}:
                continue
            row = _row_for(by_code, op)
            row["marks"].setdefault(section, _NO_LONGER)
        for op in coverage.not_applicable:
            key = op.code or ("label:" + op.label)
            if not key or key in {item.code for item in coverage.applicable}:
                continue
            row = _row_for(by_code, op, key=key)
            row["marks"].setdefault(section, _NOT_APPLICABLE)

    rows = []
    for row in by_code.values():
        row["status"] = _overall(row["marks"])
        row["country_id"] = entry.get("country_id")
        row["country_name"] = entry.get("country_name") or ""
        row["iso3"] = entry.get("iso3") or ""
        rows.append(row)
    rows.sort(key=lambda row: (row["name"].lower(), row["code"]))
    return rows, sections


def _row_for(by_code: dict[str, dict[str, Any]], op: EmergencyRef, key: str | None = None) -> dict[str, Any]:
    code = key or op.code
    row = by_code.get(code)
    if row is None:
        name, part_of = _display_name(op)
        row = {
            "code": op.code or "",
            "name": name,
            "part_of": part_of,
            "marks": {},
        }
        by_code[code] = row
    elif not row["name"]:
        row["name"], row["part_of"] = _display_name(op)
    return row


def attach_group_names(rows: list[dict[str, Any]], titles: dict[str, str] | None = None) -> None:
    """Name each grouped appeal from the catalogue. Standalone appeals stay single."""
    known = {str(code or "").strip().upper(): name for code, name in (titles or {}).items() if code and name}
    parents = {str(row.get("part_of") or "").strip().upper() for row in rows}
    parents.discard("")
    for row in rows:
        parent = str(row.get("part_of") or "").strip().upper()
        code = str(row.get("code") or "").strip().upper()
        if parent:
            row["group_code"] = parent
            row["group_name"] = known.get(parent) or parent
            row["appeal_kind"] = "child"
        elif code in parents:
            row["group_code"] = code
            row["group_name"] = known.get(code) or row.get("name") or code
            row["appeal_kind"] = "group"
        else:
            row["group_code"] = ""
            row["group_name"] = ""
            row["appeal_kind"] = "single"


def _group_titles_from_catalogue() -> dict[str, str]:
    """Parent appeal code to the grouped appeal's name."""
    try:
        from plugins.emergency_operations.data_store import get_data_store

        cached = get_data_store().load_cached() or {}
    except Exception:
        return {}
    results = cached.get("results") if isinstance(cached, dict) else None
    if not isinstance(results, list):
        return {}
    titles: dict[str, str] = {}
    for op in results:
        if not isinstance(op, dict):
            continue
        code = str(op.get("code") or "").strip().upper()
        parent = str(op.get("part_of") or "").strip().upper()
        group_name = str(op.get("group_appeal_name") or "").strip()
        name = str(op.get("name") or "").strip()
        if parent and group_name:
            titles.setdefault(parent, group_name)
        elif code and name and not parent:
            titles.setdefault(code, name)
    return titles


_FUNDING_CHECK_NOT_ANNUALISED = "not_annualised"
_FUNDING_CHECK_NOT_ENTERED = "not_entered"
_FUNDING_CHECK_ENTERED = "entered"
# One planning year holds this share of the appeal total, or more.
_FULL_YEAR_SHARE = 0.9


_PEOPLE_COLUMN = "Total People to be reached"


def people_reached_amounts(cells: dict[str, Any], column: str = _PEOPLE_COLUMN) -> dict[str, float]:
    """People-to-be-reached total saved on each emergency row."""
    from app.utils.api_serialization import _resolve_matrix_cell

    suffix = f"_{column}"
    totals: dict[str, float] = {}
    for key, raw in cells.items():
        key_s = str(key)
        if key_s.startswith("col_header") or key_s.startswith("_") or not key_s.endswith(suffix):
            continue
        row_id = key_s[: -len(suffix)]
        if not row_id or row_id.lower() in {"total", "row_total"}:
            continue
        code = str(parse_operation_label(row_id).get("code") or "").strip().upper()
        if not code:
            continue
        number = to_number(_resolve_matrix_cell(raw))
        if number is None or number <= 0:
            continue
        totals[code] = totals.get(code, 0.0) + number
    return totals


def annualised_amounts(cells: dict[str, Any], columns: list[str]) -> dict[str, float]:
    """Sum focal-point funding for each emergency selected as an EA column header."""
    headers = _ea_header_codes(cells, columns)
    totals: dict[str, float] = {}
    seen: dict[str, bool] = {}
    for column, code in headers.items():
        amount = _sum_column(cells, column)
        if amount is None:
            continue
        totals[code] = totals.get(code, 0.0) + amount
        seen[code] = True
    return {code: totals[code] for code in seen}


def appeal_duration_years(start: str | None, end: str | None) -> int | None:
    """Calendar years an appeal covers, from its start year through its end year."""
    start_year = _year_of(start)
    end_year = _year_of(end)
    if start_year is None or end_year is None or end_year < start_year:
        return None
    return end_year - start_year + 1


def positive_requested(value: float | None) -> float | None:
    """Appeal total from ERP. Zero means the child has no request of its own."""
    if value is None or value <= 0:
        return None
    return float(value)


def funding_check_status(
    requested: float | None,
    annualised: dict[str, float | None],
    duration_years: int | None = None,
) -> str:
    """Flag a multi-year appeal whose whole request was entered in one planning year.

    A total that is split across years, or that does not add up to the appeal
    request, is not a flag. A one-year appeal may hold its whole request in
    that year.
    """
    entered = [value for value in annualised.values() if value is not None and value > 0]
    if not entered:
        return _FUNDING_CHECK_NOT_ENTERED
    if requested is None or not duration_years or duration_years <= 1:
        return _FUNDING_CHECK_ENTERED
    whole = float(requested) * _FULL_YEAR_SHARE
    if any(value >= whole for value in entered):
        return _FUNDING_CHECK_NOT_ANNUALISED
    return _FUNDING_CHECK_ENTERED


def _published_version_id(assignments) -> int | None:
    for assignment in assignments:
        template = getattr(assignment, "template", None)
        version_id = getattr(template, "published_version_id", None)
        if isinstance(version_id, int):
            return version_id
    return None


def _planning_years(period_name: str) -> list[int]:
    """The round year only. Later funding matrices do not collect emergency appeals."""
    match = re.search(r"\b(20\d{2})\b", str(period_name or ""))
    if not match:
        return []
    return [int(match.group(1))]


def _funding_year_offset(section_name: str) -> int | None:
    text = (section_name or "").lower()
    if "+2" in text or "year 3" in text:
        return 2
    if "+1" in text or "year 2" in text:
        return 1
    if "funding requirement" in text:
        return 0
    return None


def _ea_columns(item) -> list[str]:
    matrix = _matrix_config(item)
    names = []
    for column in matrix.get("columns") or []:
        if not isinstance(column, dict):
            continue
        name = str(column.get("name") or "").strip()
        if name.upper().startswith("EA"):
            names.append(name)
    return names


def _published_matrices(template_id: int, version_id: int | None) -> list[Any]:
    from sqlalchemy.orm import joinedload

    from app.models.form_items import FormItem

    if not version_id:
        return []
    items = (
        FormItem.query.options(joinedload(FormItem.form_section))
        .filter(
            FormItem.template_id == template_id,
            FormItem.version_id == version_id,
            FormItem.item_type == "matrix",
            FormItem.archived == False,  # noqa: E712
        )
        .all()
    )
    return items if isinstance(items, list) else []


def _matrix_config(item) -> dict[str, Any]:
    config = item.config if isinstance(getattr(item, "config", None), dict) else {}
    matrix = config.get("matrix_config") if isinstance(config.get("matrix_config"), dict) else {}
    return matrix


def _funding_matrices(items: list[Any]) -> dict[int, Any]:
    found: dict[int, Any] = {}
    for item in items:
        section = item.form_section.name if item.form_section else ""
        offset = _funding_year_offset(section)
        if offset is None or offset in found:
            continue
        found[offset] = item
    return found


def _people_matrix(items: list[Any]):
    for item in items:
        matrix = _matrix_config(item)
        row_mode = str(matrix.get("row_mode") or "").strip().lower()
        row_lookup = str(matrix.get("lookup_list_id") or getattr(item, "lookup_list_id", "") or "").strip()
        if row_mode not in {"list_library", "hybrid"} or row_lookup != "emergency_operations":
            continue
        if _people_column(item):
            return item
    return None


def _people_column(item) -> str:
    for column in _matrix_config(item).get("columns") or []:
        if not isinstance(column, dict):
            continue
        name = str(column.get("name") or "").strip()
        if name.lower() == _PEOPLE_COLUMN.lower():
            return name
    return ""


def _section_title(item, period_name: str) -> str:
    section = item.form_section.name if getattr(item, "form_section", None) else ""
    return coverage_source_title(getattr(item, "label", "") or "", section, period_name)


def _figure_section(marks: dict[str, str], title: str, needle: str) -> str:
    if not title:
        return ""
    if title in marks:
        return title
    folded = needle.lower()
    for key in marks:
        if folded in str(key).lower():
            return key
    return title


def _attach_annualised_funding(payload, *, period_name: str, version_id: int | None, aes_by_country: dict) -> None:
    years = _planning_years(period_name)
    payload["funding_years"] = []
    payload["plan_columns"] = bool(years)
    if not years:
        return
    items = _published_matrices(PLAN_TEMPLATE_ID, version_id)
    funding_item = _funding_matrices(items).get(0)
    people_item = _people_matrix(items)
    appeals = _appeal_budgets()
    funding_by_country = _annualised_by_country(
        aes_by_country,
        {0: funding_item} if funding_item is not None else {},
        years,
    )
    people_by_country = _people_by_country(aes_by_country, people_item)
    funding_title = _section_title(funding_item, period_name) if funding_item is not None else ""
    people_title = _section_title(people_item, period_name) if people_item is not None else ""
    for row in payload["rows"]:
        code = str(row.get("code") or "").upper()
        parent = str(row.get("group_code") or "").upper()
        appeal = appeals.get(code) or {}
        parent_appeal = appeals.get(parent) or {} if parent and parent != code else {}
        amounts = funding_by_country.get(row.get("country_id"), {}).get(code, {})
        annualised = {str(year): amounts.get(year) for year in years}
        duration = appeal_duration_years(appeal.get("start"), appeal.get("end"))
        if duration is None:
            duration = appeal_duration_years(parent_appeal.get("start"), parent_appeal.get("end"))
            if row.get("duration_from") is None:
                row["duration_from"] = _year_of(parent_appeal.get("start"))
                row["duration_to"] = _year_of(parent_appeal.get("end"))
        else:
            row["duration_from"] = _year_of(appeal.get("start"))
            row["duration_to"] = _year_of(appeal.get("end"))
        requested = positive_requested(appeal.get("requested"))
        row["requested"] = requested
        row["group_requested"] = positive_requested(parent_appeal.get("requested"))
        row["annualised"] = annualised
        row["duration_years"] = duration
        row["funding_check"] = funding_check_status(requested, annualised, duration)
        row["figures"] = _section_figures(
            row.get("marks") or {},
            people_title,
            people_by_country.get(row.get("country_id"), {}).get(code),
            funding_title,
            amounts.get(years[0]),
        )
    applicable = [row for row in payload["rows"] if row.get("status") in (_COVERED, _MISSING)]
    payload["summary"]["funding_not_entered"] = sum(
        1 for row in applicable if row.get("funding_check") == _FUNDING_CHECK_NOT_ENTERED
    )
    payload["summary"]["funding_not_annualised"] = sum(
        1 for row in applicable if row.get("funding_check") == _FUNDING_CHECK_NOT_ANNUALISED
    )


def _section_figures(
    marks: dict[str, str],
    people_title: str,
    people_amount: float | None,
    funding_title: str,
    funding_amount: float | None,
) -> dict[str, float | None]:
    """Amount entered on each list. None means the appeal belongs there and nothing was reported."""
    figures: dict[str, float | None] = {}
    people_key = _figure_section(marks, people_title, "people to be reached")
    funding_key = _figure_section(marks, funding_title, "funding requirement")
    if people_key and marks.get(people_key) in (_COVERED, _MISSING):
        figures[people_key] = people_amount if people_amount else None
    if funding_key and marks.get(funding_key) in (_COVERED, _MISSING):
        figures[funding_key] = funding_amount if funding_amount else None
    return figures


def _people_by_country(aes_by_country: dict, item) -> dict[int, dict[str, float]]:
    from app.models.forms import FormData

    column = _people_column(item) if item is not None else ""
    item_id = getattr(item, "id", None)
    if not column or not isinstance(item_id, int) or not aes_by_country:
        return {}
    country_by_aes = {aes.id: country_id for country_id, aes in aes_by_country.items()}
    stored = FormData.query.filter(
        FormData.assignment_entity_status_id.in_(list(country_by_aes)),
        FormData.form_item_id == item_id,
    ).all()
    found: dict[int, dict[str, float]] = {}
    for entry in stored:
        country_id = country_by_aes.get(entry.assignment_entity_status_id)
        if country_id is None:
            continue
        for code, amount in people_reached_amounts(_matrix_cells(entry), column).items():
            found.setdefault(country_id, {})[code] = amount
    return found


def _annualised_by_country(aes_by_country: dict, matrices: dict[int, Any], years: list[int]) -> dict:
    from app.models.forms import FormData

    item_offsets = {item.id: offset for offset, item in matrices.items() if getattr(item, "id", None)}
    columns = {offset: _ea_columns(item) for offset, item in matrices.items()}
    if not item_offsets or not aes_by_country:
        return {}
    country_by_aes = {aes.id: country_id for country_id, aes in aes_by_country.items()}
    stored = FormData.query.filter(
        FormData.assignment_entity_status_id.in_(list(country_by_aes)),
        FormData.form_item_id.in_(list(item_offsets)),
    ).all()
    found: dict[int, dict[str, dict[int, float]]] = {}
    for entry in stored:
        offset = item_offsets.get(entry.form_item_id)
        country_id = country_by_aes.get(entry.assignment_entity_status_id)
        if offset is None or country_id is None or offset >= len(years):
            continue
        cells = _matrix_cells(entry)
        for code, amount in annualised_amounts(cells, columns.get(offset) or []).items():
            found.setdefault(country_id, {}).setdefault(code, {})[years[offset]] = amount
    return found


def _matrix_cells(entry) -> dict[str, Any]:
    getter = getattr(entry, "get_display_disagg_data", None)
    data = getter() if callable(getter) else getattr(entry, "disagg_data", None)
    if not isinstance(data, dict):
        return {}
    values = data.get("values") if "values" in data else data
    return values if isinstance(values, dict) else {}


def _ea_header_codes(cells: dict[str, Any], columns: list[str]) -> dict[str, str]:
    headers = {}
    for column in columns:
        parsed = parse_operation_label(str(cells.get(f"col_header|{column}") or ""))
        code = str(parsed.get("code") or "").strip().upper()
        if code:
            headers[column] = code
    return headers


def _sum_column(cells: dict[str, Any], column: str) -> float | None:
    from app.utils.api_serialization import _resolve_matrix_cell

    suffix = f"_{column}"
    total = 0.0
    found = False
    for key, raw in cells.items():
        key_s = str(key)
        if key_s.startswith("col_header") or key_s.startswith("_") or not key_s.endswith(suffix):
            continue
        row = key_s[: -len(suffix)]
        if row.lower() in {"total", "row_total"}:
            continue
        number = to_number(_resolve_matrix_cell(raw))
        if number is None:
            continue
        total += number
        found = True
    return total if found else None


def _year_of(value: str | None) -> int | None:
    match = re.search(r"\b(20\d{2})\b", str(value or ""))
    return int(match.group(1)) if match else None


def _appeal_budgets() -> dict[str, dict[str, Any]]:
    """Amount requested and start/end dates from the appeal catalogue."""
    try:
        from plugins.emergency_operations.data_store import get_data_store

        cached = get_data_store().load_cached() or {}
    except Exception:
        return {}
    results = cached.get("results") if isinstance(cached, dict) else None
    if not isinstance(results, list):
        return {}
    budgets: dict[str, dict[str, Any]] = {}
    for op in results:
        if not isinstance(op, dict):
            continue
        code = str(op.get("code") or "").strip().upper()
        if not code:
            continue
        budgets[code] = {
            "requested": to_number(op.get("amount_requested")),
            "start": op.get("start_date"),
            "end": op.get("end_date"),
        }
    return budgets


def _display_name(op: EmergencyRef) -> tuple[str, str]:
    parsed = parse_operation_label(op.label or op.code)
    name = (parsed.get("name") or "").strip() or (op.label or op.code)
    return name, (parsed.get("part_of") or "").strip()


def _overall(marks: dict[str, str]) -> str:
    values = set(marks.values())
    if _MISSING in values:
        return _MISSING
    if _COVERED in values:
        return _COVERED
    if _NO_LONGER in values:
        return _NO_LONGER
    return _NOT_APPLICABLE
