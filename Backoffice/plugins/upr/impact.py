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
  and the funding they report.
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
    partner_rounds = _partner_series(master_rows, report_rounds)
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
    partners = {
        "by_year": _collapse_to_years(
            partner_rounds["by_round"], report_by_year, ("partners", "funding")
        )
    }
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


def _partner_series(master_rows: list[dict[str, Any]], report_rounds: list[str]) -> dict[str, Any]:
    support_rows = [
        r
        for r in master_rows
        if norm(r.get("Section")) in {"support", "activities"}
        and norm(r.get("Entity")) == "pns"
    ]
    pns_funding_rows = [
        r
        for r in master_rows
        if norm(r.get("Source")) == "pns data" and norm(r.get("Indicator")) == "funding"
    ]

    partners: dict[str, set[str]] = {code: set() for code in report_rounds}
    host_partners: dict[str, dict[str, set[str]]] = {code: {} for code in report_rounds}
    host_funding: dict[str, dict[str, float]] = {code: {} for code in report_rounds}
    names: dict[str, dict[str, str]] = {code: {} for code in report_rounds}
    for row in support_rows:
        code = row.get("Round")
        if code not in partners:
            continue
        ns = str(row.get("NS") or "").strip()
        if ns:
            partners[code].add(ns)
        iso = str(row.get("ISO3") or "").strip().upper()
        if iso and ns:
            host_partners[code].setdefault(iso, set()).add(ns)
            _remember_country(names[code], iso, row)

    funding: dict[str, float] = {code: 0.0 for code in report_rounds}
    for row in pns_funding_rows:
        code = row.get("Round")
        if code not in funding:
            continue
        value = num(row.get("ValueNum"))
        if value is None:
            continue
        funding[code] += value
        iso = str(row.get("ISO3") or "").strip().upper()
        if not iso:
            continue
        host_funding[code][iso] = host_funding[code].get(iso, 0.0) + value
        _remember_country(names[code], iso, row)

    by_round = []
    for code in report_rounds:
        amounts: dict[str, dict[str, Any]] = {}
        for iso in set(host_partners[code]) | set(host_funding[code]):
            amounts[iso] = {
                "partners": len(host_partners[code].get(iso) or ()),
                "funding": host_funding[code].get(iso, 0.0),
            }
        by_round.append(
            {
                "round": code,
                "partners": len(partners[code]),
                "funding": funding[code],
                "countries": _country_rows(amounts, names[code]),
            }
        )
    return {"by_round": by_round}


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
        "impact", {"region": region or None, "series": "network-mix-v3"}, _loader
    )
    return payload
