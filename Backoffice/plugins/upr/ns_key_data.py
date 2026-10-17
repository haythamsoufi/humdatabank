"""One National Society key-figure row per country and year.

Templates 21 (FDRS), 24 (planning), and 33 (annual and mid-year reporting)
all collect volunteers, staff, branches, and local units. For each country
and year this keeps a single approved assignment: the one approved most
recently. All four figures come from that assignment. A blank on the winning
source stays blank.

A planning round is named for the year being planned. P27 is filled in 2026,
so its key figures belong to 2026.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

from app.services.data_quality.helpers import parse_period_year
from app.utils.data_quality_constants import FDRS_TEMPLATE_ID
from plugins.upr.capacity_comparison import _number_from_fields, _prefer_value, _status_name
from plugins.upr.catalog import KPI_BANK_IDS, PLAN_TEMPLATE_ID, REPORT_TEMPLATE_ID
from plugins.upr.validation_dashboard import round_for_assignment

MEASURES: tuple[str, ...] = ("volunteers", "staff", "branches", "local_units")
MEASURE_COLUMNS = {
    "volunteers": "Volunteers",
    "staff": "Staff",
    "branches": "Branches",
    "local_units": "LocalUnits",
}
BANK_TO_MEASURE = {KPI_BANK_IDS[key]: key for key in MEASURES}
TEMPLATE_IDS = (FDRS_TEMPLATE_ID, PLAN_TEMPLATE_ID, REPORT_TEMPLATE_ID)

SOURCE_FDRS = "FDRS"
SOURCE_PLANNING = "Planning"
SOURCE_ANNUAL = "Annual reporting"
SOURCE_MIDYEAR = "Mid-year reporting"

NS_KEY_COLUMNS: tuple[str, ...] = (
    "Country",
    "ISO2",
    "ISO3",
    "Year",
    "Volunteers",
    "Staff",
    "Branches",
    "LocalUnits",
    "Source",
    "ApprovedAt",
)


def classify_source(template_id: int, period_name: str | None) -> dict[str, Any] | None:
    """Map an assignment to the calendar year and the source label for that round."""
    template_id = int(template_id)
    period = str(period_name or "").strip()
    if template_id == FDRS_TEMPLATE_ID:
        year = parse_period_year(period)
        if year is None:
            return None
        return {
            "year": year,
            "source": SOURCE_FDRS,
        }
    round_code = round_for_assignment(template_id, period)
    if not round_code:
        return None
    if template_id == PLAN_TEMPLATE_ID and round_code.startswith("P") and round_code[1:].isdigit():
        # P27 is the plan for 2027, filled during 2026. The key figures are the
        # current year's numbers, so they belong to 2026.
        plan_year = 2000 + int(round_code[1:])
        return {
            "year": plan_year - 1,
            "source": SOURCE_PLANNING,
        }
    if template_id != REPORT_TEMPLATE_ID:
        return None
    if round_code.startswith("MYR") and round_code[3:].isdigit():
        return {
            "year": 2000 + int(round_code[3:]),
            "source": SOURCE_MIDYEAR,
        }
    if round_code.startswith("AR") and round_code[2:].isdigit():
        return {
            "year": 2000 + int(round_code[2:]),
            "source": SOURCE_ANNUAL,
        }
    return None


def _approved_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return None


def _approval_rank(row: Mapping[str, Any]) -> tuple:
    """Later approval wins. A missing timestamp loses to any real timestamp."""
    approved_at = _approved_at(row.get("approved_at"))
    return (
        approved_at is not None,
        approved_at or datetime.min,
        int(row.get("aes_id") or 0),
    )


def _values_by_cell(values: Iterable[Mapping[str, Any]]) -> dict[tuple[int, str], int | None]:
    by_cell: dict[tuple[int, int], Mapping[str, Any]] = {}
    for row in values:
        bank_id = row.get("bank_id")
        if bank_id not in BANK_TO_MEASURE:
            continue
        aes_id = int(row["aes_id"])
        stored = {
            "form_data_id": int(row.get("form_data_id") or 0),
            "value": _number_from_fields(row),
        }
        key = (aes_id, int(bank_id))
        by_cell[key] = _prefer_value(by_cell.get(key), stored)
    return {
        (aes_id, BANK_TO_MEASURE[bank_id]): stored.get("value")
        for (aes_id, bank_id), stored in by_cell.items()
    }


def _iso_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(sep=" ", timespec="seconds")


def build_ns_key_rows(
    assignments: Iterable[Mapping[str, Any]],
    values: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """One row per country and year, from the most recently approved source."""
    figures = _values_by_cell(values)
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for assignment in assignments:
        if _status_name(assignment.get("status")) != "approved":
            continue
        classified = classify_source(assignment.get("template_id"), assignment.get("period_name"))
        if classified is None:
            continue
        aes_id = int(assignment["aes_id"])
        numbers = {measure: figures.get((aes_id, measure)) for measure in MEASURES}
        if all(number is None for number in numbers.values()):
            continue
        candidate = {
            "aes_id": aes_id,
            "country_id": int(assignment["country_id"]),
            "country_name": str(assignment.get("country_name") or ""),
            "iso2": str(assignment.get("iso2") or "") or None,
            "iso3": str(assignment.get("iso3") or ""),
            "approved_at": _approved_at(assignment.get("approved_at")),
            "numbers": numbers,
            **classified,
        }
        grouped.setdefault((candidate["country_id"], candidate["year"]), []).append(candidate)

    rows: list[dict[str, Any]] = []
    for candidates in grouped.values():
        winner = max(candidates, key=_approval_rank)
        row = {
            "Country": winner["country_name"],
            "ISO2": winner["iso2"],
            "ISO3": winner["iso3"],
            "Year": winner["year"],
            "Source": winner["source"],
            "ApprovedAt": _iso_timestamp(winner["approved_at"]),
        }
        for measure, column in MEASURE_COLUMNS.items():
            row[column] = winner["numbers"].get(measure)
        rows.append(row)

    rows.sort(key=lambda row: (-int(row["Year"]), str(row["Country"]).lower(), str(row["ISO3"])))
    return rows


def load_ns_key_rows() -> list[dict[str, Any]]:
    """Read approved country assignments on templates 21, 24, and 33."""
    from app import db
    from app.models.assignments import AssignedForm, AssignmentEntityStatus
    from app.models.core import Country
    from app.models.enums import AssignmentEntityStatusValue
    from app.models.form_items import FormItem
    from app.models.forms import FormData

    assignment_rows = (
        db.session.query(
            AssignmentEntityStatus.id,
            AssignmentEntityStatus.entity_id,
            AssignmentEntityStatus.status,
            AssignmentEntityStatus.status_timestamp,
            AssignedForm.template_id,
            AssignedForm.period_name,
            Country.name,
            Country.iso2,
            Country.iso3,
        )
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .join(Country, Country.id == AssignmentEntityStatus.entity_id)
        .filter(
            AssignmentEntityStatus.entity_type == "country",
            AssignmentEntityStatus.status == AssignmentEntityStatusValue.approved,
            AssignedForm.template_id.in_(TEMPLATE_IDS),
        )
        .all()
    )
    assignments = [
        {
            "aes_id": aes_id,
            "country_id": country_id,
            "status": status,
            "approved_at": approved_at,
            "template_id": template_id,
            "period_name": period_name,
            "country_name": name,
            "iso2": iso2,
            "iso3": iso3,
        }
        for aes_id, country_id, status, approved_at, template_id, period_name, name, iso2, iso3 in assignment_rows
    ]
    if not assignments:
        return []

    value_rows = (
        db.session.query(
            FormData.assignment_entity_status_id,
            FormData.id,
            FormItem.indicator_bank_id,
            FormData.numeric_value,
            FormData.value,
            FormData.data_not_available,
            FormData.not_applicable,
        )
        .join(FormItem, FormItem.id == FormData.form_item_id)
        .join(
            AssignmentEntityStatus,
            AssignmentEntityStatus.id == FormData.assignment_entity_status_id,
        )
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            AssignmentEntityStatus.entity_type == "country",
            AssignmentEntityStatus.status == AssignmentEntityStatusValue.approved,
            AssignedForm.template_id.in_(TEMPLATE_IDS),
            FormItem.indicator_bank_id.in_(tuple(BANK_TO_MEASURE)),
        )
        .all()
    )
    values = [
        {
            "aes_id": aes_id,
            "form_data_id": form_data_id,
            "bank_id": bank_id,
            "numeric_value": numeric_value,
            "value": value,
            "not_available": not_available,
            "not_applicable": not_applicable,
        }
        for aes_id, form_data_id, bank_id, numeric_value, value, not_available, not_applicable in value_rows
    ]
    return build_ns_key_rows(assignments, values)
