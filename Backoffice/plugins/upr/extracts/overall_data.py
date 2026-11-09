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
FDRS assignments are approved-only. Unified Reporting, Unified Planning, and PNS
forms include every workflow status (same coverage as ``/api/v1/upr/data``).

Everything that FDRS does not collect (emergency appeals, bilateral support, funding
sources, comments) comes from Unified Reporting unchanged.
"""

from __future__ import annotations

from typing import Any

from app.utils.data_quality_constants import FDRS_TEMPLATE_ID
from plugins.upr.dashboards.catalog import REPORT_ITEM_FALLBACKS, REPORT_TEMPLATE_ID
from plugins.upr.dashboards.formatters import to_number
from plugins.upr.dashboards.matrix import _funding_entity
from plugins.upr.extracts.upr_data import (
    FACT_COLLAPSE_KEY_FIELDS,
    _KPI_BANK_ID_SET,
    ItemView,
    _dynamic_facts,
    _fill_funding_ea_codes,
    _is_ns_expenditure,
    _load_form_data,
    _load_items,
    _load_national_societies,
    _load_places,
    _matrix_cells_from_disagg,
    _status_text,
    _with_value,
    build_upr_data,
    assignment_year,
    blank_fact,
    classify_item,
    collapse_breakdowns,
    comment_fact,
    data_status_label,
    facts_for_item,
    fill_entity,
    fill_section_b,
)

SOURCE_FDRS = "FDRS"
SOURCE_UNIFIED_REPORTING = "Unified Reporting"
SOURCE_UNIFIED_PLANNING = "Unified Planning"
SOURCE_PNS_REPORTING = "PNS Reporting"
SOURCE_PNS_PLANNING = "PNS Planning"

OVERALL_COLUMNS: tuple[str, ...] = (
    "submission_id",
    "ISO3",
    "Year",
    "Round",
    "Data source",
    "Data status",
    "Region",
    "Country",
    "NS",
    "Section",
    "SectionB",
    "Entity",
    "Attribute",
    "Breakdown",
    "SP/EF",
    "EA Code",
    "Applicable/Data not available",
    "Indicator",
    "Indicator ID",
    "Value",
    "ValueNum",
    "FDRS Value",
    "UPR Value",
    "PNS Value",
    "PNS reported",
)

_CELL_FIELDS = ("Section", "SectionB", "Indicator", "Attribute", "Entity", "SP/EF", "EA Code")

# Same grouping as /data, with ``Data source`` instead of ``Source``.
_COLLAPSE_KEY_FIELDS = tuple(
    "Data source" if field == "Source" else field for field in FACT_COLLAPSE_KEY_FIELDS
)

# Lower wins. Annual reporting covers the full year, mid-year only January to June.
_RANK_FDRS = 0
_RANK_ANNUAL = 1
_RANK_MIDYEAR = 2

# National Society funding. FDRS item 1530 (bank 733, total income in CHF) is the total of the
# Unified Reporting funding matrix (item 1403, sum of its rows). FDRS item 943 (income sources)
# lists each source; its "IFRC" row is the matrix row "IFRC Secretariat". Expenditure is the same
# indicator (bank 734) in both: FDRS item 1531 and Unified Reporting item 1404.
FUNDING_INDICATOR = "Funding (CHF)"
FUNDING_INDICATOR_ID = 733
# Entity of the NS totals (total funding, expenditure), as opposed to a funding source.
NATIONAL_SOCIETY_ENTITY = "National Society"
FDRS_FUNDING_TOTAL_BANK_ID = 733
FDRS_INCOME_SOURCES_ITEM_ID = 943
# Reporting-currency twins of funding and expenditure. The CHF items are used instead.
_FDRS_SKIPPED_BANK_IDS = frozenset({1131, 1132})
# FDRS item 943 row label -> output Entity. Unified Reporting item 1403 uses the same names.
_FDRS_SOURCE_ENTITY = {
    "IFRC": "IFRC Secretariat",
    "Other National Society": "Other National Society",
}
# Unified Reporting item 1403 row -> output Entity.
# PNSs ↔ FDRS "Other National Society". HNS other sources = every FDRS source except those two.
_UR_SOURCE_ENTITY = {
    "IFRC Secretariat": "IFRC Secretariat",
    "IFRC": "IFRC Secretariat",
    "PNSs": "Other National Society",
    "PNS": "Other National Society",
    "HNS other sources": "HNS other sources",
    "Other sources": "HNS other sources",
}
_UR_FUNDING_COLUMN = "_ns_fun"
# Entities that are a single FDRS income-source row (not rolled into HNS other sources).
_FDRS_DIRECT_SOURCE_ENTITIES = frozenset({"IFRC Secretariat", "Other National Society"})

TOKEN_FUNDING_TOTAL = ("funding_total",)
# All Funding Source rows for a country and year share this token so FDRS and Unified
# Reporting never mix: one source set wins, the other is dropped.
TOKEN_FUNDING_SOURCES = ("funding_sources",)


def fdrs_role(item: ItemView) -> str:
    """Role of an FDRS form item. Only indicators linked to the Indicator Bank are carried."""
    if item.item_type == "matrix" and (
        item.id == FDRS_INCOME_SOURCES_ITEM_ID or (item.label or "").strip().lower() == "income sources"
    ):
        return "fdrs_income_sources"
    if item.item_type != "indicator" or item.bank_id is None:
        return "skip"
    if item.bank_id in _FDRS_SKIPPED_BANK_IDS:
        return "skip"
    if item.bank_id == FDRS_FUNDING_TOTAL_BANK_ID:
        return "fdrs_funding"
    if _is_ns_expenditure(item):
        return "expenditure"
    if item.bank_id in _KPI_BANK_ID_SET:
        return "ns_data"
    return "core"


def ur_role(item: ItemView) -> str:
    """Role of a Unified Reporting item. Adds the NS funding matrix, and reads item 1404 as a scalar."""
    role = classify_item(item)
    if role == "funding":
        if item.item_type == "indicator" and _is_ns_expenditure(item):
            return "expenditure"
        if item.item_type == "matrix" and item.id == REPORT_ITEM_FALLBACKS["funding_sources"]:
            return "ur_funding_sources"
    return role


def _funding_fact(
    place: dict[str, Any],
    number: float,
    *,
    attribute: str,
    entity: str | None,
) -> dict[str, Any]:
    fact = blank_fact(place)
    fact.update(
        {
            "Section": "Funding",
            "SectionB": "Funding",
            "Entity": entity,
            "Attribute": attribute,
            "Indicator": FUNDING_INDICATOR,
            "Indicator ID": FUNDING_INDICATOR_ID,
        }
    )
    return _with_value(fact, number)


def _fdrs_funding_total_facts(place: dict[str, Any], entry: Any) -> list[dict[str, Any]]:
    number = to_number(entry.value)
    if number is None:
        return []
    return [_funding_fact(place, number, attribute="Total", entity=None)]


def _fdrs_income_source_facts(place: dict[str, Any], entry: Any) -> list[tuple[tuple, dict[str, Any]]]:
    """One row per income source. Keys look like ``IFRC_Funding``.

    Every source row shares ``TOKEN_FUNDING_SOURCES`` so the whole FDRS set wins or loses
    against Unified Reporting together.
    """
    found = []
    for key, raw in _matrix_cells_from_disagg(entry.disagg_data).items():
        number = to_number(raw)
        if not number or "_" not in key:
            continue
        source = key.rsplit("_", 1)[0].strip()
        entity = _FDRS_SOURCE_ENTITY.get(source, source)
        found.append((TOKEN_FUNDING_SOURCES, _funding_fact(place, number, attribute="Funding Source", entity=entity)))
    return found


def _ur_source_entity(row: str) -> str:
    name = row.strip()
    return _UR_SOURCE_ENTITY.get(name) or _UR_SOURCE_ENTITY.get(_funding_entity(name) or "") or name


def _ur_funding_facts(place: dict[str, Any], entry: Any) -> list[tuple[tuple | None, dict[str, Any]]]:
    """Rows of the NS funding matrix, plus their sum as the Total.

    Keys look like ``IFRC Secretariat_ns_fun`` (the column name has an underscore itself).
    Source rows share ``TOKEN_FUNDING_SOURCES`` with FDRS item 943.
    """
    found: list[tuple[tuple | None, dict[str, Any]]] = []
    total = 0.0
    for key, raw in _matrix_cells_from_disagg(entry.disagg_data).items():
        number = to_number(raw)
        if not number:
            continue
        row = key[: -len(_UR_FUNDING_COLUMN)] if key.endswith(_UR_FUNDING_COLUMN) else key.rsplit("_", 1)[0]
        entity = _ur_source_entity(row)
        total += number
        found.append(
            (TOKEN_FUNDING_SOURCES, _funding_fact(place, number, attribute="Funding Source", entity=entity))
        )
    if found:
        found.append((TOKEN_FUNDING_TOTAL, _funding_fact(place, total, attribute="Total", entity=None)))
    return found


def _hns_other_from_fdrs(rows: list[dict[str, Any]]) -> float | None:
    """Sum of FDRS income sources that roll into Unified Reporting ``HNS other sources``."""
    total = 0.0
    found = False
    for row in rows:
        if row.get("Attribute") != "Funding Source":
            continue
        if row.get("Entity") in _FDRS_DIRECT_SOURCE_ENTITIES:
            continue
        if not _is_numeric(row):
            continue
        total += float(row["ValueNum"])
        found = True
    return total if found else None


def _place_rank(place: dict[str, Any]) -> int:
    if place["template_id"] == FDRS_TEMPLATE_ID:
        return _RANK_FDRS
    if str(place.get("period_name") or "").strip().lower().startswith("jan-jun"):
        return _RANK_MIDYEAR
    return _RANK_ANNUAL


def _places(
    template_id: int,
    *,
    iso3: str | None,
    year: int | None,
    approved_only: bool = False,
) -> list[dict[str, Any]]:
    places = _load_places({template_id}, iso3=iso3, round_code=None)
    kept = []
    for place in places:
        if approved_only and _status_text(place.get("status")).lower() != "approved":
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
        hns_other = _hns_other_from_fdrs(candidates.get(_RANK_FDRS, []))
        for fact in winner:
            cell = _cell(fact)
            fact["FDRS Value"] = fdrs_values.get(cell)
            fact["UPR Value"] = upr_values.get(cell)
            # UR's single "HNS other sources" row is the sum of every FDRS source except
            # IFRC Secretariat and Other National Society.
            if (
                fact.get("Entity") == "HNS other sources"
                and fact.get("Attribute") == "Funding Source"
                and fact["FDRS Value"] is None
                and hns_other is not None
            ):
                fact["FDRS Value"] = int(hns_other) if hns_other == int(hns_other) else hns_other
            rows.append((fact, winner_rank))
    return rows


def _planning_data_source(fact: dict[str, Any]) -> str:
    round_code = str(fact.get("Round") or "").upper()
    planning = len(round_code) > 1 and round_code[0] == "P" and round_code[1:].isdigit()
    if fact.get("Source") == "PNS Data":
        return SOURCE_PNS_PLANNING if planning else SOURCE_PNS_REPORTING
    return SOURCE_UNIFIED_PLANNING


def _planning_and_pns_facts(*, iso3: str | None, year: int | None) -> list[dict[str, Any]]:
    """Plan and PNS facts labelled by where they came from.

    Same status coverage as ``/api/v1/upr/data`` (not approved-only): a PNS can have entered
    host-country figures while its assignment is still pending. PNS forms (templates 22/23)
    are assigned to the PNS country, but each matrix row is remapped to the host; filter by
    host ``ISO3`` after build.

    Prefer the ``template=plan`` extract for PNS Planning rows: that path merges T22 into the
    host plan and keeps ``Country Value`` (host figure) beside ``PNS Value``. A bare
    ``template=pns`` rebuild has no host matrix, so ``Country Value`` / ``UPR Value`` would
    be blank. Skip duplicate PNS Planning rows from the pns pass; keep PNS Reporting.
    """
    from plugins.upr.dashboards.catalog import PLAN_TEMPLATE_ID, PNS_PLAN_TEMPLATE_ID, PNS_REPORT_TEMPLATE_ID

    status_by_submission = {
        place["submission_id"]: place.get("status")
        for place in _load_places(
            {PLAN_TEMPLATE_ID, PNS_PLAN_TEMPLATE_ID, PNS_REPORT_TEMPLATE_ID},
            iso3=None,
            round_code=None,
        )
    }
    facts: list[dict[str, Any]] = []
    wanted = (iso3 or "").strip().upper() or None
    for template in ("plan", "pns"):
        # Host-country filter applies after remap for PNS; for Unified Plan it can filter places.
        place_iso3 = None if template == "pns" else iso3
        built = build_upr_data(template=template, iso3=place_iso3)
        for fact in built["data"]:
            source_label = _planning_data_source(fact)
            # Plan extract already carries merged T22 (+ Country Value). Avoid the pns-only copy.
            if template == "pns" and source_label == SOURCE_PNS_PLANNING:
                continue
            if wanted and str(fact.get("ISO3") or "").upper() != wanted:
                continue
            if year is not None and fact.get("Year") != year:
                continue
            fact["_data_source"] = source_label
            if fact.get("Data status") is None:
                fact["Data status"] = data_status_label(status_by_submission.get(fact.get("submission_id")))
            facts.append(fact)
    return facts


def _finish(fact: dict[str, Any], rank: int) -> dict[str, Any]:
    fact.pop("_bank_id", None)
    override = fact.pop("_data_source", None)
    data_source = override or (SOURCE_FDRS if rank == _RANK_FDRS else SOURCE_UNIFIED_REPORTING)
    fact["Data source"] = data_source
    if data_source in (SOURCE_PNS_REPORTING, SOURCE_PNS_PLANNING):
        fact["Source"] = "PNS Data"
    if data_source in (SOURCE_UNIFIED_PLANNING, SOURCE_PNS_PLANNING, SOURCE_PNS_REPORTING):
        # Parallel to FDRS vs UR: UPR Value is the host / Unified Plan figure (Country Value),
        # not the winning Value when a reported PNS overwrote it.
        if fact.get("Country Value") is not None:
            fact["UPR Value"] = fact.get("Country Value")
        elif fact.get("Source") == "PNS Data":
            fact["UPR Value"] = None
        else:
            fact["UPR Value"] = fact.get("ValueNum")
    if fact.get("Indicator ID") is None and fact.get("indicatorId") is not None:
        fact["Indicator ID"] = fact.get("indicatorId")
    fill_section_b(fact)
    fill_entity(fact)
    fact.setdefault("Breakdown", None)
    return {column: fact.get(column) for column in OVERALL_COLUMNS}


def build_overall_data(
    *,
    iso3: str | None = None,
    year: int | None = None,
    section: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Merged FDRS and Unified Reporting facts."""
    fdrs_places = _places(FDRS_TEMPLATE_ID, iso3=iso3, year=year, approved_only=True)
    report_places = _places(REPORT_TEMPLATE_ID, iso3=iso3, year=year)
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

    def add(
        place: dict[str, Any],
        facts: list[dict[str, Any]],
        *,
        bank_id: int | None = None,
        token: tuple | None = None,
    ) -> None:
        """*token* says what a fact competes on; a scalar item competes on its bank id."""
        rank = _place_rank(place)
        year_value = assignment_year(place)
        for fact in facts:
            fact["Data status"] = data_status_label(place.get("status"))
            if bank_id is not None and fact.get("Indicator ID") is None:
                fact["Indicator ID"] = int(bank_id)
            match = token
            if match is None:
                bank = (
                    fact.get("Indicator ID")
                    if fact.get("Indicator ID") is not None
                    else (bank_id if bank_id is not None else fact.get("_bank_id"))
                )
                match = ("bank", int(bank)) if bank is not None else None
            key = (place["country_id"], year_value, match) if match is not None else None
            if (
                fact.get("Section") == "Funding"
                and fact.get("Attribute") == "Total"
                and fact.get("Entity") is None
                and fact.get("Indicator") in (FUNDING_INDICATOR, "Expenditure")
            ):
                fact["Entity"] = NATIONAL_SOCIETY_ENTITY
            if "_indicator_id" in fact:
                tagged_id = fact.pop("_indicator_id")
                if fact.get("Indicator ID") is None:
                    fact["Indicator ID"] = tagged_id
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
                add(place, _fdrs_funding_total_facts(place, entry), token=TOKEN_FUNDING_TOTAL)
                continue
            if role == "fdrs_income_sources":
                for token, fact in _fdrs_income_source_facts(place, entry):
                    add(place, [fact], token=token)
                continue
        else:
            role = ur_role(item)
            if role == "comment":
                text = (entry.value or "").strip()
                if text:
                    add(place, [comment_fact(place, item, text)])
                continue
            if role == "ur_funding_sources":
                for token, fact in _ur_funding_facts(place, entry):
                    add(place, [fact], token=token)
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
        add(place, facts, bank_id=item.bank_id)

    # Emergency appeal rows and other dynamic indicators exist only in Unified Reporting.
    # Country-level "Other indicators" carry their bank id so FDRS can still take priority.
    for fact in _dynamic_facts(report_places, by_submission, tag_bank_id=True):
        add(by_submission[fact["submission_id"]], [fact])

    # Planning (template 24) and PNS reporting/planning (templates 23, 22) have no FDRS
    # counterpart, so they are carried exactly as /api/v1/upr/data builds them.
    for fact in _planning_and_pns_facts(iso3=iso3, year=year):
        tagged.append((None, _RANK_ANNUAL, fact))

    all_facts = [fact for _key, _rank, fact in tagged]
    _fill_funding_ea_codes(all_facts, emergency_index, area_key="SP/EF")

    rows = collapse_breakdowns(
        [_finish(fact, rank) for fact, rank in merge_facts(tagged)],
        columns=OVERALL_COLUMNS,
        key_fields=_COLLAPSE_KEY_FIELDS,
        blank_value_fields=("Value", "ValueNum", "FDRS Value", "UPR Value"),
    )

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
