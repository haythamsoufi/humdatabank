"""Analysis of Unified Plans and Reports — live aggregates for the Data Explorer.

This powers the "Analysis" tab. It reduces the same live extracts the Power BI
endpoints use (:func:`plugins.upr.upr_data.build_upr_master` and
``build_upr_submissions``) into a small set of per-round series that showcase
how the Unified Planning and Reporting process is growing:

* **Coverage** — how many National Societies complete a plan / report each round.
* **Funding** — the same mix as the Financial Overview network block: the
  country-plan funding requirement, PNS self-reported funding and expenditure,
  country-reported other sources, and IFRC Secretariat actuals from the
  shipped snapshot. Host National Society strategic-priority totals are not
  added on top of that mix.
* **Reach** — people to be reached through the plans.
* **Partners** — participating National Societies providing bilateral support,
  split by planning (funding requirement) and reporting (funding reported),
  and by country records, PNS self-reports, or both.
* **Capacity** — National Society volunteers, staff, branches and local units.

The figures are *indicative network totals* summed from submitted Unified Plans
and Reports in the database. Because the source is the live database, the trend
only spans the rounds that currently have assignments; it is not a historical
back-fill. De-duplication rules are applied per metric (see ``_reduce_*``) so a
value and its breakdown are never counted twice.
"""

from __future__ import annotations

from typing import Any, Iterable

from plugins.upr.analysis_common import (
    APPROVED_STATUSES,
    MATURE_ROUND_RATIO,
    SUBMITTED_STATUSES,
    delta_record,
    iso3s_in_region,
    load_countries,
    norm,
    num,
    ordered_rounds,
    round_calendar_year,
    round_kind,
    round_prefix,
    round_sort_key,
)
from plugins.upr.api_cache import get_or_build_upr_payload
from plugins.upr.upr_data import build_upr_master, build_upr_submissions

__all__ = ["aggregate_impact", "build_upr_impact", "round_sort_key"]

# NS Data capacity indicators, matched by substring on the indicator name.
_CAPACITY_MATCHERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("volunteers", ("volunteer",)),
    ("staff", ("paid staff", "staff")),
    ("branches", ("branch",)),
    ("local_units", ("local unit",)),
)
_CAPACITY_KEYS = tuple(key for key, _ in _CAPACITY_MATCHERS)


def _plan_year_map(plan_rounds: list[str]) -> dict[int, str]:
    """{year: plan round}. One plan per year."""
    return {round_calendar_year(c): c for c in plan_rounds if round_calendar_year(c) is not None}


def _report_year_map(report_rounds: list[str]) -> dict[int, str]:
    """{year: reporting round}, one figure per year.

    The annual report is the canonical year-end figure; the mid-year report is
    only used as a fall-back while the annual is not yet available. Iterating in
    chronological order (``MYR`` before ``AR``) lets the annual overwrite the
    mid-year for the same year.
    """
    out: dict[int, str] = {}
    for code in sorted(report_rounds, key=round_sort_key):
        year = round_calendar_year(code)
        if year is not None:
            out[year] = code
    return out


def _by_round_index(points: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {p.get("round"): p for p in points}


def _collapse_to_years(
    by_round: list[dict[str, Any]],
    year_to_round: dict[int, str],
    value_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Project a per-round series onto a year axis using ``year_to_round``.

    Only years that actually map to a round are emitted, so plan-only and
    report-only series stay sparse and the frontend renders gaps as null.
    """
    index = _by_round_index(by_round)
    out: list[dict[str, Any]] = []
    for year in sorted(year_to_round):
        src = index.get(year_to_round[year], {})
        record: dict[str, Any] = {"year": year, "round": year_to_round[year]}
        for key in value_keys:
            record[key] = src.get(key, 0)
        record["countries"] = list(src.get("countries") or [])
        out.append(record)
    return out


def _country_rows(amounts: dict[str, dict[str, Any]], names: dict[str, str]) -> list[dict[str, Any]]:
    """One row per country, alphabetical. Empty amounts are left out."""
    rows: list[dict[str, Any]] = []
    for iso, fields in amounts.items():
        if not iso:
            continue
        if not any(value for value in fields.values()):
            continue
        row: dict[str, Any] = {"iso3": iso, "country": names.get(iso) or iso}
        row.update(fields)
        rows.append(row)
    rows.sort(key=lambda row: (str(row["country"]).lower(), row["iso3"]))
    return rows


def _remember_country(names: dict[str, str], iso: str, row: dict[str, Any]) -> None:
    if iso in names:
        return
    name = str(row.get("Country") or "").strip()
    if name:
        names[iso] = name


def _capacity_key(indicator: str) -> str | None:
    low = norm(indicator)
    if not low:
        return None
    for key, needles in _CAPACITY_MATCHERS:
        if any(needle in low for needle in needles):
            return key
    return None


def _reduce_single_value(rows: list[dict[str, Any]], attribute_priority: tuple[str, ...]) -> float:
    """Collapse rows for one (round, country, indicator) to a single amount.

    Rows are grouped by Entity. Within an entity the first attribute present in
    ``attribute_priority`` wins, so a stored "Total" is never summed together
    with the breakdown that produced it. Entity subtotals are then summed to a
    network figure for the country.
    """
    by_entity: dict[str, dict[str, float]] = {}
    for row in rows:
        entity = str(row.get("Entity") or "")
        attr = str(row.get("Attribute") or "")
        value = num(row.get("ValueNum"))
        if value is None:
            continue
        by_entity.setdefault(entity, {})
        by_entity[entity][attr] = by_entity[entity].get(attr, 0.0) + value
    total = 0.0
    for attrs in by_entity.values():
        chosen = None
        for attr in attribute_priority:
            if attr in attrs:
                chosen = attrs[attr]
                break
        if chosen is None:
            # No preferred attribute — sum the leaf breakdown that is present.
            chosen = sum(attrs.values())
        total += chosen
    return total


def _group(rows: Iterable[dict[str, Any]], *keys: str) -> dict[tuple, list[dict[str, Any]]]:
    out: dict[tuple, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(tuple(row.get(k) for k in keys), []).append(row)
    return out


def aggregate_impact(
    master_rows: list[dict[str, Any]],
    submissions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Pure reducer: master + submission rows -> per-year impact series.

    Planning and reporting rounds are never mixed on one axis. Every series is
    projected onto a **calendar-year** axis: planning metrics use that year's
    plan (``P``), and reporting metrics use a single figure per year — the
    annual report (``AR``) when available, otherwise the mid-year report
    (``MYR``). Kept free of database access so it can be unit tested with
    synthetic rows.
    """
    rounds_all = ordered_rounds(
        [r.get("Round") for r in master_rows] + [s.get("Round") for s in submissions]
    )
    plan_rounds = [c for c in rounds_all if round_kind(c) == "plan"]
    report_rounds = [c for c in rounds_all if round_kind(c) == "report"]

    plan_by_year = _plan_year_map(plan_rounds)
    report_by_year = _report_year_map(report_rounds)
    years = sorted(set(plan_by_year) | set(report_by_year))

    coverage_rounds = _coverage_series(submissions, rounds_all)
    funding_rounds = _funding_series(master_rows, plan_rounds, report_rounds)
    reach_rounds = _reach_series(master_rows, plan_rounds)
    plan_partner_rounds = _partner_series(master_rows, plan_rounds, requirement=True)
    report_partner_rounds = _partner_series(master_rows, report_rounds, requirement=False)
    capacity_rounds = _capacity_series(master_rows, report_rounds)

    in_progress = _in_progress_rounds(coverage_rounds)
    in_progress_years = sorted(
        y
        for y in years
        if plan_by_year.get(y) in in_progress or report_by_year.get(y) in in_progress
    )
    midyear_fallback_years = sorted(
        y for y, code in report_by_year.items() if round_prefix(code) == "MYR"
    )

    coverage = _coverage_byround_calendar_year(coverage_rounds, plan_by_year, report_by_year, years)
    funding = {
        "plan_requirement": _collapse_to_years(
            funding_rounds["plan_requirement"], plan_by_year, ("value",)
        ),
        "report_funding": _collapse_to_years(
            funding_rounds["report_funding"], report_by_year, ("value",)
        ),
        "report_expenditure": _collapse_to_years(
            funding_rounds["report_expenditure"], report_by_year, ("value",)
        ),
    }
    reach = {"by_year": _collapse_to_years(reach_rounds["by_round"], plan_by_year, ("value",))}
    partners_by_source = {
        source: _partners_by_year(
            plan_partner_rounds[source],
            report_partner_rounds[source],
            plan_by_year,
            report_by_year,
            years,
        )
        for source in ("all", "pns", "country")
    }
    # Headline KPIs stay on every source combined. The visual toggles the rest.
    partners = {"by_year": partners_by_source["all"], "by_source": partners_by_source}
    capacity = {
        key: _collapse_to_years(capacity_rounds[key], report_by_year, ("value",))
        for key in _CAPACITY_KEYS
    }

    return {
        "rounds": rounds_all,
        "plan_rounds": plan_rounds,
        "report_rounds": report_rounds,
        "years": years,
        "in_progress": sorted(in_progress, key=round_sort_key),
        "in_progress_years": in_progress_years,
        "midyear_fallback_years": midyear_fallback_years,
        "coverage": coverage,
        "funding": funding,
        "reach": reach,
        "partners": partners,
        "capacity": capacity,
        "headline": _headline(coverage, funding, reach, partners, in_progress_years),
    }


def _coverage_byround_calendar_year(
    coverage_rounds: dict[str, Any],
    plan_by_year: dict[int, str],
    report_by_year: dict[int, str],
    years: list[int],
) -> dict[str, Any]:
    """Split participation into planning vs reporting, one figure per year."""
    index = _by_round_index(coverage_rounds.get("by_round", []))
    by_year = []
    for year in years:
        plan = index.get(plan_by_year.get(year), {})
        report = index.get(report_by_year.get(year), {})
        by_year.append(
            {
                "year": year,
                "plan_submitted": plan.get("submitted", 0),
                "plan_countries": plan.get("countries", 0),
                "report_submitted": report.get("submitted", 0),
                "report_countries": report.get("countries", 0),
                "report_validated": report.get("validated", 0),
                "countries": _coverage_countries(
                    plan.get("detail") or [], report.get("detail") or []
                ),
            }
        )
    return {"by_year": by_year}


def _coverage_countries(
    plan_detail: list[dict[str, Any]], report_detail: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Countries that submitted a plan and/or a report in the year."""
    merged: dict[str, dict[str, Any]] = {}
    for source, flag in ((plan_detail, "plan_submitted"), (report_detail, "report_submitted")):
        for row in source:
            if not row.get("submitted"):
                continue
            iso = str(row.get("iso3") or "")
            if not iso:
                continue
            rec = merged.setdefault(
                iso,
                {
                    "iso3": iso,
                    "country": row.get("country") or iso,
                    "plan_submitted": 0,
                    "report_submitted": 0,
                },
            )
            rec[flag] = 1
            if row.get("country"):
                rec["country"] = row["country"]
    return sorted(merged.values(), key=lambda row: (str(row["country"]).lower(), row["iso3"]))


def _coverage_series(submissions: list[dict[str, Any]], rounds: list[str]) -> dict[str, Any]:
    countries: dict[str, set[str]] = {c: set() for c in rounds}
    submitted: dict[str, set[str]] = {c: set() for c in rounds}
    validated: dict[str, set[str]] = {c: set() for c in rounds}
    names: dict[str, dict[str, str]] = {c: {} for c in rounds}
    for row in submissions:
        code = row.get("Round")
        if code not in countries:
            continue
        iso = str(row.get("ISO3") or "").strip().upper()
        if not iso:
            iso = str(row.get("Country") or "").strip().upper()
        if not iso:
            continue
        countries[code].add(iso)
        _remember_country(names[code], iso, row)
        status = norm(row.get("status"))
        if status in SUBMITTED_STATUSES:
            submitted[code].add(iso)
        if status in APPROVED_STATUSES or norm(row.get("fds_validated")) == "validated":
            validated[code].add(iso)
    return {
        "by_round": [
            {
                "round": code,
                "countries": len(countries[code]),
                "submitted": len(submitted[code]),
                "validated": len(validated[code]),
                "detail": [
                    {
                        "iso3": iso,
                        "country": names[code].get(iso) or iso,
                        "submitted": 1 if iso in submitted[code] else 0,
                        "validated": 1 if iso in validated[code] else 0,
                    }
                    for iso in sorted(countries[code], key=lambda i: (names[code].get(i, i).lower(), i))
                ],
            }
            for code in rounds
        ]
    }


def _sum_by_round(
    rows: list[dict[str, Any]],
    rounds: list[str],
    *,
    attribute_priority: tuple[str, ...],
) -> list[dict[str, Any]]:
    by_round = {code: 0.0 for code in rounds}
    by_country: dict[str, dict[str, dict[str, Any]]] = {code: {} for code in rounds}
    names: dict[str, dict[str, str]] = {code: {} for code in rounds}
    grouped = _group(rows, "Round", "ISO3", "Indicator")
    for (code, iso, _ind), group_rows in grouped.items():
        if code not in by_round:
            continue
        amount = _reduce_single_value(group_rows, attribute_priority)
        by_round[code] += amount
        iso_key = str(iso or "").strip().upper()
        if not iso_key:
            continue
        bucket = by_country[code].setdefault(iso_key, {"value": 0.0})
        bucket["value"] += amount
        for row in group_rows:
            _remember_country(names[code], iso_key, row)
    return [
        {
            "round": code,
            "value": by_round[code],
            "countries": _country_rows(by_country[code], names[code]),
        }
        for code in rounds
    ]


def _funding_series(
    master_rows: list[dict[str, Any]],
    plan_rounds: list[str],
    report_rounds: list[str],
) -> dict[str, Any]:
    """Financial Overview network mix, before IFRC Secretariat snapshots.

    * Planned requirement is the country unified plan (``Source = Country Data``):
      host National Society + IFRC Secretariat + the PNS amount recorded on that
      plan. Those three streams are the Country funding-requirement bar.
    * Reported funding is PNS self-reported funding (``Source = PNS Data``) plus
      other sources on the country report. The host's strategic-priority funding
      total is the separate National Society figure and is not added again.
    * Reported expenditure is PNS self-reported expenditure only. Transfers are
      not expenditure. IFRC Secretariat actuals are added later from the snapshot
      the Financial Overview visual uses.
    """
    funding_rows = [r for r in master_rows if norm(r.get("Section")) == "funding"]

    requirement_rows = [
        r
        for r in funding_rows
        if norm(r.get("Indicator")) == "funding requirement"
        and norm(r.get("Source")) == "country data"
    ]
    report_funding_rows = [r for r in funding_rows if _is_network_reported_funding(r)]
    report_expenditure_rows = [r for r in funding_rows if _is_network_reported_expenditure(r)]

    return {
        "plan_requirement": _sum_by_round(
            requirement_rows, plan_rounds, attribute_priority=("Total",)
        ),
        "report_funding": _sum_by_round(
            report_funding_rows, report_rounds, attribute_priority=("Total", "Funding Source")
        ),
        "report_expenditure": _sum_by_round(
            report_expenditure_rows, report_rounds, attribute_priority=("Total", "Funding Source")
        ),
    }


def _is_network_reported_funding(row: dict[str, Any]) -> bool:
    if norm(row.get("Indicator")) != "funding":
        return False
    source = norm(row.get("Source"))
    if source == "pns data":
        return True
    return source == "country data" and norm(row.get("Entity")) == "other sources"


def _is_network_reported_expenditure(row: dict[str, Any]) -> bool:
    return norm(row.get("Indicator")) == "expenditure" and norm(row.get("Source")) == "pns data"


def _add_ifrc_network_actuals(funding: dict[str, Any], iso3s: set[str] | None) -> None:
    """Add the Financial Overview IFRC Secretariat snapshot onto delivery totals."""
    from plugins.upr.financial import ifrc_secretariat_actuals_by_country

    for point in funding.get("report_funding") or []:
        rows = ifrc_secretariat_actuals_by_country(str(point.get("round") or ""), iso3s=iso3s)
        point["value"] = (point.get("value") or 0) + sum(row["funding"] for row in rows)
        _merge_ifrc_countries(point, rows, "funding")
    for point in funding.get("report_expenditure") or []:
        rows = ifrc_secretariat_actuals_by_country(str(point.get("round") or ""), iso3s=iso3s)
        point["value"] = (point.get("value") or 0) + sum(row["expenditure"] for row in rows)
        _merge_ifrc_countries(point, rows, "expenditure")


def _merge_ifrc_countries(point: dict[str, Any], rows: list[dict[str, Any]], metric: str) -> None:
    """Add one snapshot metric onto the country rows of a delivery series."""
    countries = list(point.get("countries") or [])
    by_iso = {row.get("iso3"): row for row in countries}
    for rec in rows:
        amount = rec.get(metric) or 0
        if not amount:
            continue
        iso = rec.get("iso3") or ""
        existing = by_iso.get(iso)
        if existing is None:
            existing = {"iso3": iso, "country": rec.get("country") or iso, "value": 0}
            countries.append(existing)
            by_iso[iso] = existing
        existing["value"] = (existing.get("value") or 0) + amount
        if rec.get("country"):
            existing["country"] = rec["country"]
    countries.sort(key=lambda row: (str(row.get("country") or "").lower(), str(row.get("iso3") or "")))
    point["countries"] = countries


def _reach_series(master_rows: list[dict[str, Any]], plan_rounds: list[str]) -> dict[str, Any]:
    reach_rows = [
        r
        for r in master_rows
        if norm(r.get("Section")) == "reach"
        and "people to be reached" in norm(r.get("Indicator"))
    ]
    # Reach has no stored grand total — Area rows are leaves, so sum them all.
    by_round = {code: 0.0 for code in plan_rounds}
    by_country: dict[str, dict[str, dict[str, Any]]] = {code: {} for code in plan_rounds}
    names: dict[str, dict[str, str]] = {code: {} for code in plan_rounds}
    for row in reach_rows:
        code = row.get("Round")
        if code not in by_round:
            continue
        value = num(row.get("ValueNum"))
        if value is None:
            continue
        by_round[code] += value
        iso = str(row.get("ISO3") or "").strip().upper()
        if not iso:
            continue
        bucket = by_country[code].setdefault(iso, {"value": 0.0})
        bucket["value"] += value
        _remember_country(names[code], iso, row)
    return {
        "by_round": [
            {
                "round": code,
                "value": by_round[code],
                "countries": _country_rows(by_country[code], names[code]),
            }
            for code in plan_rounds
        ]
    }


_TOTAL_AREAS = {"", "total", "row total", "row_total"}


def _source_keys(row: dict[str, Any]) -> tuple[str, ...]:
    """Which partner-source toggles a row belongs to.

    ``all`` is the union of country records and Participating Society
    self-reports. Other sources (for example IFRC Secretariat actuals) stay out.
    """
    source = norm(row.get("Source"))
    if source == "pns data":
        return ("pns",)
    if source in {"", "country data"}:
        return ("country",)
    return ()


def _partner_name(row: dict[str, Any]) -> str:
    name = str(row.get("NS") or "").strip()
    if not name or norm(name) == "country":
        return ""
    return name


def _partner_series(
    master_rows: list[dict[str, Any]],
    rounds: list[str],
    *,
    requirement: bool,
) -> dict[str, dict[str, Any]]:
    """Partner counts and funding, split by country records and PNS self-reports.

    ``requirement`` selects the planning figure (that year's PNS funding
    requirement). Otherwise the figure is funding reported. A stored total wins
    over its area breakdown. ``all`` counts each society once and adds the two
    funding sources.
    """
    tracked = ("country", "pns")
    partners: dict[str, dict[str, set[str]]] = {key: {code: set() for code in rounds} for key in tracked}
    host_partners: dict[str, dict[str, dict[str, set[str]]]] = {
        key: {code: {} for code in rounds} for key in tracked
    }
    funding_rows: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {
        key: {code: {} for code in rounds} for key in tracked
    }
    loose_rows: dict[str, dict[str, list[dict[str, Any]]]] = {
        key: {code: [] for code in rounds} for key in tracked
    }
    names: dict[str, dict[str, dict[str, str]]] = {key: {code: {} for code in rounds} for key in tracked}

    for row in master_rows:
        keys = _source_keys(row)
        if not keys:
            continue
        code = str(row.get("Round") or "")
        if code not in partners["country"]:
            continue
        section = norm(row.get("Section"))
        entity = norm(row.get("Entity"))
        indicator = norm(row.get("Indicator"))
        is_support = section in {"support", "activities"} and entity == "pns"
        is_requirement = (
            section == "funding"
            and indicator == "funding requirement"
            and entity == "pns"
            and _requirement_on_round_year(row, code)
        )
        is_reported = section == "funding" and indicator == "funding" and entity == "pns"
        is_money = is_requirement if requirement else is_reported
        if not is_support and not is_money:
            continue
        iso = str(row.get("ISO3") or "").strip().upper()
        ns = _partner_name(row)
        for key in keys:
            # A country funding row names the host, not the supporting society.
            names_a_partner = is_support or (is_money and key == "pns")
            if names_a_partner and ns:
                partners[key][code].add(ns)
                if iso:
                    host_partners[key][code].setdefault(iso, set()).add(ns)
                    _remember_country(names[key][code], iso, row)
            if not is_money:
                continue
            if iso:
                funding_rows[key][code].setdefault(iso, []).append(row)
                _remember_country(names[key][code], iso, row)
            else:
                loose_rows[key][code].append(row)

    built = {
        key: _partner_rounds(key, rounds, partners, host_partners, funding_rows, loose_rows, names)
        for key in tracked
    }
    built["all"] = _all_partner_rounds(rounds, partners, host_partners, funding_rows, loose_rows, names)
    return built


def _partner_rounds(
    key: str,
    rounds: list[str],
    partners: dict[str, dict[str, set[str]]],
    host_partners: dict[str, dict[str, dict[str, set[str]]]],
    funding_rows: dict[str, dict[str, dict[str, list[dict[str, Any]]]]],
    loose_rows: dict[str, dict[str, list[dict[str, Any]]]],
    names: dict[str, dict[str, dict[str, str]]],
) -> dict[str, Any]:
    by_round = []
    for code in rounds:
        host_funding = {
            iso: _prefer_total_area(rows) for iso, rows in funding_rows[key][code].items()
        }
        amounts: dict[str, dict[str, Any]] = {}
        for iso in set(host_partners[key][code]) | set(host_funding):
            amounts[iso] = {
                "partners": len(host_partners[key][code].get(iso) or ()),
                "funding": host_funding.get(iso, 0.0),
            }
        by_round.append(
            {
                "round": code,
                "partners": len(partners[key][code]),
                "funding": sum(host_funding.values()) + _prefer_total_area(loose_rows[key][code]),
                "countries": _country_rows(amounts, names[key][code]),
            }
        )
    return {"by_round": by_round}


def _all_partner_rounds(
    rounds: list[str],
    partners: dict[str, dict[str, set[str]]],
    host_partners: dict[str, dict[str, dict[str, set[str]]]],
    funding_rows: dict[str, dict[str, dict[str, list[dict[str, Any]]]]],
    loose_rows: dict[str, dict[str, list[dict[str, Any]]]],
    names: dict[str, dict[str, dict[str, str]]],
) -> dict[str, Any]:
    """Each society once, and the sum of country-recorded and self-reported funding."""
    by_round = []
    for code in rounds:
        host_funding: dict[str, float] = {}
        host_names: dict[str, set[str]] = {}
        labels: dict[str, str] = {}
        loose = 0.0
        for key in ("country", "pns"):
            for iso, rows in funding_rows[key][code].items():
                host_funding[iso] = host_funding.get(iso, 0.0) + _prefer_total_area(rows)
            for iso, society_names in host_partners[key][code].items():
                host_names.setdefault(iso, set()).update(society_names)
            for iso, label in names[key][code].items():
                labels.setdefault(iso, label)
            loose += _prefer_total_area(loose_rows[key][code])
        amounts = {
            iso: {
                "partners": len(host_names.get(iso) or ()),
                "funding": host_funding.get(iso, 0.0),
            }
            for iso in set(host_names) | set(host_funding)
        }
        by_round.append(
            {
                "round": code,
                "partners": len(partners["country"][code] | partners["pns"][code]),
                "funding": sum(host_funding.values()) + loose,
                "countries": _country_rows(amounts, labels),
            }
        )
    return {"by_round": by_round}


def _requirement_on_round_year(row: dict[str, Any], code: str) -> bool:
    """True when a plan row is the requirement for that round's own calendar year.

    A plan also stores the next two years. Those stay off this year so the
    planning figure lines up with the report for the same year.
    """
    raw = row.get("Year")
    if raw in (None, ""):
        return True
    year = num(raw)
    if year is None:
        return True
    round_year = round_calendar_year(code)
    return round_year is None or int(year) == round_year


def _prefer_total_area(rows: list[dict[str, Any]]) -> float:
    """Sum a stored total when one is present, otherwise the area breakdown."""
    totals: list[float] = []
    parts: list[float] = []
    for row in rows:
        value = num(row.get("ValueNum"))
        if value is None:
            continue
        if norm(row.get("Area")) in _TOTAL_AREAS:
            totals.append(value)
        else:
            parts.append(value)
    chosen = totals if totals else parts
    return sum(chosen)


def _partners_by_year(
    plan_rounds: dict[str, Any],
    report_rounds: dict[str, Any],
    plan_by_year: dict[int, str],
    report_by_year: dict[int, str],
    years: list[int],
) -> list[dict[str, Any]]:
    """One row per calendar year: planning requirement beside reported funding.

    A side with no round for that year is left blank (``None``) so the chart
    draws a gap rather than a zero. ``partners`` and ``funding`` keep the
    reporting figures for the headline KPIs.
    """
    plan_index = _by_round_index(plan_rounds.get("by_round", []))
    report_index = _by_round_index(report_rounds.get("by_round", []))
    by_year = []
    for year in years:
        plan = plan_index.get(plan_by_year.get(year), {})
        report = report_index.get(report_by_year.get(year), {})
        by_year.append(
            {
                "year": year,
                "plan_round": plan_by_year.get(year),
                "report_round": report_by_year.get(year),
                "plan_partners": plan.get("partners", 0) if plan else None,
                "plan_funding": plan.get("funding", 0.0) if plan else None,
                "report_partners": report.get("partners", 0) if report else None,
                "report_funding": report.get("funding", 0.0) if report else None,
                "partners": report.get("partners", 0) if report else 0,
                "funding": report.get("funding", 0.0) if report else 0.0,
                "countries": _merge_partner_countries(
                    plan.get("countries") or [], report.get("countries") or []
                ),
            }
        )
    return by_year


def _merge_partner_countries(
    plan_rows: list[dict[str, Any]], report_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """One country row carrying the planning and reporting partner figures."""
    merged: dict[str, dict[str, Any]] = {}
    for rows, partners_key, funding_key in (
        (plan_rows, "plan_partners", "plan_funding"),
        (report_rows, "report_partners", "report_funding"),
    ):
        for row in rows:
            iso = str(row.get("iso3") or "")
            if not iso:
                continue
            rec = merged.setdefault(
                iso,
                {
                    "iso3": iso,
                    "country": row.get("country") or iso,
                    "plan_partners": 0,
                    "report_partners": 0,
                    "plan_funding": 0.0,
                    "report_funding": 0.0,
                },
            )
            if row.get("country"):
                rec["country"] = row["country"]
            rec[partners_key] = row.get("partners") or 0
            rec[funding_key] = row.get("funding") or 0.0
    rows = [
        rec
        for rec in merged.values()
        if any(rec[key] for key in ("plan_partners", "report_partners", "plan_funding", "report_funding"))
    ]
    rows.sort(key=lambda row: (str(row["country"]).lower(), row["iso3"]))
    return rows


def _capacity_series(master_rows: list[dict[str, Any]], report_rounds: list[str]) -> dict[str, Any]:
    ns_rows = [r for r in master_rows if norm(r.get("Section")) == "ns data"]
    series: dict[str, dict[str, float]] = {key: {c: 0.0 for c in report_rounds} for key in _CAPACITY_KEYS}
    by_country: dict[str, dict[str, dict[str, dict[str, Any]]]] = {
        key: {c: {} for c in report_rounds} for key in _CAPACITY_KEYS
    }
    names: dict[str, dict[str, str]] = {c: {} for c in report_rounds}
    for row in ns_rows:
        code = row.get("Round")
        key = _capacity_key(str(row.get("Indicator") or ""))
        if key is None or code not in series[key]:
            continue
        value = num(row.get("ValueNum"))
        if value is None:
            continue
        series[key][code] += value
        iso = str(row.get("ISO3") or "").strip().upper()
        if not iso:
            continue
        bucket = by_country[key][code].setdefault(iso, {"value": 0.0})
        bucket["value"] += value
        _remember_country(names[code], iso, row)
    return {
        key: [
            {
                "round": code,
                "value": series[key][code],
                "countries": _country_rows(by_country[key][code], names[code]),
            }
            for code in report_rounds
        ]
        for key in _CAPACITY_KEYS
    }


def _in_progress_rounds(coverage: dict[str, Any]) -> set[str]:
    open_rounds: set[str] = set()
    for row in coverage.get("by_round", []):
        countries = num(row.get("countries")) or 0
        submitted = num(row.get("submitted")) or 0
        if countries <= 0:
            open_rounds.add(row["round"])
            continue
        if submitted / countries < MATURE_ROUND_RATIO:
            open_rounds.add(row["round"])
    return open_rounds


def _settled_delta(
    points: list[dict[str, Any]],
    value_key: str,
    in_progress_years: list[int] | set[int] | None = None,
) -> dict[str, Any]:
    """Year-over-year change for a year-keyed series.

    In-progress years are dropped first, so the headline always compares the two
    most recent *settled* years of the same track (planning or reporting). Since
    every series carries one figure per year, the previous year is an inherently
    like-for-like comparison.
    """
    skip = set(in_progress_years or ())
    usable = [p for p in points if p.get("year") not in skip and num(p.get(value_key))]
    latest = usable[-1] if usable else None
    previous = usable[-2] if len(usable) >= 2 else None
    return delta_record(latest, previous, value_key)


def _headline(
    coverage: dict[str, Any],
    funding: dict[str, Any],
    reach: dict[str, Any],
    partners: dict[str, Any],
    in_progress_years: list[int],
) -> dict[str, Any]:
    return {
        "coverage": _settled_delta(coverage["by_year"], "report_submitted", in_progress_years),
        "plan_requirement": _settled_delta(funding["plan_requirement"], "value", in_progress_years),
        "report_funding": _settled_delta(funding["report_funding"], "value", in_progress_years),
        "reach": _settled_delta(reach["by_year"], "value", in_progress_years),
        "partners": _settled_delta(partners["by_year"], "partners", in_progress_years),
        "partner_funding": _settled_delta(partners["by_year"], "funding", in_progress_years),
    }


def _region_options(submissions: list[dict[str, Any]]) -> list[str]:
    return sorted({str(s.get("Region")).strip() for s in submissions if s.get("Region")})


def _filter_iso3(rows: list[dict[str, Any]], iso3s: set[str] | None) -> list[dict[str, Any]]:
    """Keep rows of the given countries (``None`` keeps everything)."""
    if iso3s is None:
        return rows
    return [r for r in rows if str(r.get("ISO3") or "").strip().upper() in iso3s]


def build_upr_impact(*, region: str | None = None) -> dict[str, Any]:
    """Analysis series for the whole network, or one region.

    Cached per database revision, like the other UPR extracts.
    """

    def _loader() -> dict[str, Any]:
        master = build_upr_master()["data"]
        submissions = build_upr_submissions()["data"]
        iso3s = iso3s_in_region(load_countries(), region)
        payload = aggregate_impact(_filter_iso3(master, iso3s), _filter_iso3(submissions, iso3s))
        _add_ifrc_network_actuals(payload["funding"], iso3s)
        payload["regions"] = _region_options(submissions)
        payload["region"] = region or None
        return payload

    # ``series`` is part of the cache key so a change in the mix or scoping
    # rules cannot reuse a payload built with an earlier rule.
    payload, _cache_hit = get_or_build_upr_payload(
        "impact", {"region": region or None, "series": "network-mix-v5"}, _loader
    )
    return payload
