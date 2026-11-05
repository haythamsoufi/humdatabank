"""FDRS and Unified Reporting merged into one long-form extract.

``GET /api/v1/upr/overall`` has the same rows and columns as ``/api/v1/upr/data``,
except ``Source`` is renamed ``Data source`` (``FDRS`` or ``Unified Reporting``) and
``Country Value`` becomes ``FDRS Value`` and ``UPR Value``: what each source reported,
while ``Value`` is the final figure.

Template 21 (FDRS) and template 33 (Unified Reporting) collect many of the same
indicators. They are matched on the Indicator Bank id behind each form item,
for each country and calendar year. When both reported the indicator, FDRS wins.
Otherwise Unified Reporting is used: the annual report first, then mid-year.
A source is only taken whole, so disaggregations from two sources are never mixed.
Only approved country assignments are read.

Everything that FDRS does not collect (emergency appeals, bilateral support, funding
sources, comments) comes from Unified Reporting unchanged.
"""

from __future__ import annotations

from typing import Any

from app.utils.data_quality_constants import FDRS_TEMPLATE_ID
from plugins.upr.catalog import REPORT_TEMPLATE_ID
from plugins.upr.upr_data import (
    FACT_COLUMNS,
    _KPI_BANK_ID_SET,
    ItemView,
    _dynamic_facts,
    _fill_funding_ea_codes,
    _is_ns_expenditure,
    _load_form_data,
    _load_items,
    _load_national_societies,
    _load_places,
    _status_text,
    assignment_year,
    classify_item,
    comment_fact,
    facts_for_item,
    indicator_name,
    measure_facts,
)

SOURCE_FDRS = "FDRS"
SOURCE_UNIFIED_REPORTING = "Unified Reporting"

def _overall_columns() -> tuple[str, ...]:
    columns: list[str] = []
    for column in FACT_COLUMNS:
        if column == "Source":
            columns.append("Data source")
        elif column == "Country Value":
            columns.extend(("FDRS Value", "UPR Value"))
        else:
            columns.append(column)
    return tuple(columns)


OVERALL_COLUMNS: tuple[str, ...] = _overall_columns()

_CELL_FIELDS = ("Section", "SectionB", "Indicator", "Attribute", "Entity", "SP/EF", "EA Code")

# Lower wins. Annual reporting covers the full year, mid-year only January to June.
_RANK_FDRS = 0
_RANK_ANNUAL = 1
_RANK_MIDYEAR = 2

# FDRS bank ids that are scalar items, but are not measured the same way as the
# Unified Reporting funding matrix. They stay FDRS-only (no counterpart to merge with).
FDRS_FUNDING_INDICATORS: dict[int, str] = {
    733: "Funding",
    1131: "Funding (reporting currency)",
    1132: "Expenditure (reporting currency)",
}

_SCALAR_ROLES = frozenset({"ns_data", "core", "expenditure"})


def fdrs_role(item: ItemView) -> str:
    """Role of an FDRS form item. Only indicators linked to the Indicator Bank are carried."""
    if item.item_type != "indicator" or item.bank_id is None:
        return "skip"
    if item.bank_id in FDRS_FUNDING_INDICATORS:
        return "fdrs_funding"
    if _is_ns_expenditure(item):
        return "expenditure"
    if item.bank_id in _KPI_BANK_ID_SET:
        return "ns_data"
    return "core"


def _fdrs_funding_facts(place: dict[str, Any], item: ItemView, entry: Any) -> list[dict[str, Any]]:
    return measure_facts(
        place,
        table="Funding",
        indicator=FDRS_FUNDING_INDICATORS[int(item.bank_id)],
        section="Funding",
        spef=None,
        year=None,
        value=entry.value,
        disagg=None,
        data_not_available=bool(entry.data_not_available),
        not_applicable=bool(entry.not_applicable),
    )


def _place_rank(place: dict[str, Any]) -> int:
    if place["template_id"] == FDRS_TEMPLATE_ID:
        return _RANK_FDRS
    if str(place.get("period_name") or "").strip().lower().startswith("jan-jun"):
        return _RANK_MIDYEAR
    return _RANK_ANNUAL


def _approved_places(template_id: int, *, iso3: str | None, year: int | None) -> list[dict[str, Any]]:
    places = _load_places({template_id}, iso3=iso3, round_code=None)
    kept = []
    for place in places:
        if _status_text(place.get("status")).lower() != "approved":
            continue
        place_year = assignment_year(place)
        if place_year is None or (year is not None and place_year != year):
            continue
        if template_id == FDRS_TEMPLATE_ID:
            place["round"] = f"FDRS{place_year % 100:02d}"
        kept.append(place)
    return kept


def _is_numeric(row: dict[str, Any]) -> bool:
    return row.get("ValueNum") is not None


def pick_sources(candidates: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Rows of the best source. A source with a number beats one that only flags no data."""
    ranked = sorted(candidates)
    for rank in ranked:
        if any(_is_numeric(row) for row in candidates[rank]):
            return candidates[rank]
    return candidates[ranked[0]]


def _cell(fact: dict[str, Any]) -> tuple:
    return tuple(fact.get(field) for field in _CELL_FIELDS)


def _values_by_cell(rows: list[dict[str, Any]]) -> dict[tuple, Any]:
    found: dict[tuple, Any] = {}
    for row in rows:
        if _is_numeric(row):
            found.setdefault(_cell(row), row["ValueNum"])
    return found


def merge_facts(tagged: list[tuple[tuple | None, int, dict[str, Any]]]) -> list[tuple[dict[str, Any], int]]:
    """Apply FDRS-first priority. Returns ``(fact, source_rank)`` pairs.

    *tagged* holds ``(match_key, source_rank, fact)``. Facts with no match key are
    kept as they are. Facts with a key (country, year, indicator bank id) compete.
    ``FDRS Value`` and ``UPR Value`` show what each source reported for the same
    cell; ``Value`` is the winner's.
    """
    rows: list[tuple[dict[str, Any], int]] = []
    groups: dict[tuple, dict[int, list[dict[str, Any]]]] = {}
    for key, rank, fact in tagged:
        if key is None:
            number = fact.get("ValueNum")
            fact["FDRS Value"] = number if rank == _RANK_FDRS else None
            fact["UPR Value"] = number if rank != _RANK_FDRS else None
            rows.append((fact, rank))
            continue
        groups.setdefault(key, {}).setdefault(rank, []).append(fact)
    for candidates in groups.values():
        fdrs_values = _values_by_cell(candidates.get(_RANK_FDRS, []))
        upr_values: dict[tuple, Any] = {}
        for rank in sorted(candidates):
            if rank != _RANK_FDRS:
                for cell, number in _values_by_cell(candidates[rank]).items():
                    upr_values.setdefault(cell, number)
        winner = pick_sources(candidates)
        winner_rank = next(rank for rank in sorted(candidates) if candidates[rank] is winner)
        for fact in winner:
            cell = _cell(fact)
            fact["FDRS Value"] = fdrs_values.get(cell)
            fact["UPR Value"] = upr_values.get(cell)
            rows.append((fact, winner_rank))
    return rows


def _finish(fact: dict[str, Any], rank: int) -> dict[str, Any]:
    fact.pop("_bank_id", None)
    fact["Data source"] = SOURCE_FDRS if rank == _RANK_FDRS else SOURCE_UNIFIED_REPORTING
    return {column: fact.get(column) for column in OVERALL_COLUMNS}


def build_overall_data(
    *,
    iso3: str | None = None,
    year: int | None = None,
    section: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Merged FDRS and Unified Reporting facts."""
    fdrs_places = _approved_places(FDRS_TEMPLATE_ID, iso3=iso3, year=year)
    report_places = _approved_places(REPORT_TEMPLATE_ID, iso3=iso3, year=year)
    places = fdrs_places + report_places
    ns_by_id, ns_by_country, _ns_country = _load_national_societies()
    for place in places:
        if not place.get("ns") and place.get("country_id"):
            place["ns"] = ns_by_country.get(place["country_id"])

    by_submission = {place["submission_id"]: place for place in places}
    entries = _load_form_data(list(by_submission))
    items = _load_items({entry.form_item_id for entry in entries})
    emergency_index: dict[tuple[int, str], int] = {}

    tagged: list[tuple[tuple | None, int, dict[str, Any]]] = []

    def add(place: dict[str, Any], facts: list[dict[str, Any]], bank_id: int | None) -> None:
        rank = _place_rank(place)
        year_value = assignment_year(place)
        for fact in facts:
            bank = bank_id if bank_id is not None else fact.get("_bank_id")
            key = (place["country_id"], year_value, int(bank)) if bank is not None else None
            tagged.append((key, rank, fact))

    for entry in entries:
        place = by_submission.get(entry.assignment_entity_status_id)
        item = items.get(entry.form_item_id)
        if place is None or item is None:
            continue
        if place["template_id"] == FDRS_TEMPLATE_ID:
            role = fdrs_role(item)
            if role == "skip":
                continue
            if role == "fdrs_funding":
                add(place, _fdrs_funding_facts(place, item, entry), None)
                continue
        else:
            role = classify_item(item)
            if role == "comment":
                text = (entry.value or "").strip()
                if text:
                    add(place, [comment_fact(place, item, text)], None)
                continue
        facts = facts_for_item(
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
        add(place, facts, item.bank_id if role in _SCALAR_ROLES else None)

    # Emergency appeal rows and other dynamic indicators exist only in Unified Reporting.
    # Country-level "Other indicators" carry their bank id so FDRS can still take priority.
    for fact in _dynamic_facts(report_places, by_submission, tag_bank_id=True):
        add(by_submission[fact["submission_id"]], [fact], None)

    all_facts = [fact for _key, _rank, fact in tagged]
    _fill_funding_ea_codes(all_facts, emergency_index, area_key="SP/EF")

    rows = [_finish(fact, rank) for fact, rank in merge_facts(tagged)]

    if section:
        wanted = section.strip().lower()
        rows = [row for row in rows if str(row.get("Section") or "").strip().lower() == wanted]
    rows.sort(
        key=lambda row: (
            str(row.get("ISO3") or ""),
            -(row.get("Year") or 0),
            str(row.get("Section") or ""),
            str(row.get("Indicator") or ""),
            str(row.get("Attribute") or ""),
        )
    )
    return {"data": rows}
