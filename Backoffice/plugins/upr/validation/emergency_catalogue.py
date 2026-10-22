"""Applicable emergencies for one UPR round, marked covered or not.

Each row is one appeal for one country. A round can collect the appeal on more
than one list (Emergency Appeals rows, Funding Requirements headers). The row
is covered only when every list that includes it has it saved.
"""

from __future__ import annotations

from typing import Any

from plugins.emergency_operations.appeal_group import parse_operation_label
from plugins.upr.catalog import UPR_VALIDATION_TEMPLATE_IDS
from plugins.upr.validation.emergency_coverage import (
    EmergencyRef,
    FieldEmergencyCoverage,
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
        "sections": sections,
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

    from app.models.assignments import AssignedForm, AssignmentEntityStatus
    from app.models.core import Country

    assignments = (
        AssignedForm.query.filter(
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
    payload.update({
        "available": not unavailable or bool(payload["rows"]),
        "template_id": int(template_id),
        "period": period_name,
    })
    return payload


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
