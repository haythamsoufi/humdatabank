"""Global Plan analysis — live UPR plan figures shaped like the Power BI dashboard.

Aggregates funding requirement and people-to-be-reached from ``/api/v1/upr/data``
plan facts (PNS Value wins over Country Value when the PNS reported), joins
INFORM + eas_sprm_ops secondary data, NS ODA/NSIF categories, and the manual
overlay (SPF, appeals, large emergencies, division rows).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from plugins.upr.analysis.analysis_common import (
    SUBMITTED_STATUSES,
    iso3s_in_region,
    load_countries,
    norm,
    num,
    ordered_rounds,
    round_calendar_year,
    round_kind,
)
from plugins.upr.extracts.api_cache import get_or_build_upr_payload
from plugins.upr.dashboards.catalog import AREA_LABELS, SP_CODES
from plugins.upr.analysis.flow import inform_class_label
from plugins.upr.analysis.global_plan_categories import has_flag, load_ns_category_flags
from plugins.upr.analysis.global_plan_overlay import load_overlay, year_overlay
from plugins.upr.secondary.loaders import load_eas_sprm_ops, load_inform_risk
from plugins.upr.extracts.upr_data import build_upr_data, build_upr_submissions

__all__ = [
    "SECTION_IDS",
    "THEME_CODES",
    "aggregate_global_plan",
    "build_upr_global_plan",
    "prioritisation_group_label",
]

# Thematic breakdown codes plus ``Total`` for amounts that are not disaggregated.
THEME_BREAKDOWN = (*SP_CODES, "EFs", "EAs")
UNDISAGG_THEME = "Total"
THEME_CODES = (*THEME_BREAKDOWN, UNDISAGG_THEME)
ENTITY_ORDER = ("HNS", "PNS", "IFRC Secretariat")
SECTION_IDS = (
    "overview",
    "secretariat",
    "pns",
    "yearly",
    "regional",
    "divisional",
    "geo",
    "people_reached",
    "emergencies",
    "countries",
    "prioritisation",
)

_SIGNAL_GROUPS = (
    (0, "0 - No signals"),
    (1, "1 - One signal"),
    (2, "2 - Two signals"),
    (3, "3 - Three signals"),
    (4, "4 - Four signals"),
    (5, "5 - Five signals"),
)


def prioritisation_group_label(score: int) -> str:
    for value, label in _SIGNAL_GROUPS:
        if score == value:
            return label
    return _SIGNAL_GROUPS[-1][1] if score > 5 else _SIGNAL_GROUPS[0][1]


def _entity_key(entity: Any) -> str | None:
    text = str(entity or "").strip()
    upper = text.upper()
    if upper.startswith("IFRC"):
        return "IFRC Secretariat"
    if upper in {"PNS", "PNSS"}:
        return "PNS"
    if upper == "HNS":
        return "HNS"
    return None


def _area_key(row: Mapping[str, Any]) -> str:
    """Theme code from ``/data`` (``SP/EF``) or master-style ``Area``."""
    spef = str(row.get("SP/EF") or "").strip()
    area = spef or str(row.get("Area") or "").strip() or "Total"
    attr = str(row.get("Attribute") or "").strip()
    if row.get("EA Code") or area.upper().startswith("EA") or attr == "Emergency Operations":
        return "EAs"
    if area.upper().startswith("EF") and area.upper() != "EFS":
        return "EFs"
    if area == "EFs":
        return "EFs"
    return area


def _filter_iso3(rows: list[dict[str, Any]], iso3s: set[str] | None) -> list[dict[str, Any]]:
    if iso3s is None:
        return rows
    return [r for r in rows if str(r.get("ISO3") or "").strip().upper() in iso3s]


def _plan_funding_rows(fact_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Funding requirement rows; ``ValueNum`` already prefers PNS when reported."""
    out: list[dict[str, Any]] = []
    for row in fact_rows:
        if norm(row.get("Section")) != "funding":
            continue
        indicator = norm(row.get("Indicator"))
        if indicator not in {"funding", "funding requirement", "funding requirements"}:
            continue
        if num(row.get("ValueNum")) is None:
            continue
        out.append(dict(row))
    return out


def _reach_rows(fact_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in fact_rows:
        if norm(row.get("Section")) != "reach":
            continue
        if "people" not in norm(row.get("Indicator")):
            continue
        if num(row.get("ValueNum")) is None:
            continue
        out.append(dict(row))
    return out


def _add_amount(bucket: dict[Any, float], key: Any, amount: float) -> None:
    bucket[key] = bucket.get(key, 0.0) + amount


def _plan_year_round_map(plan_rounds: list[str]) -> dict[int, str]:
    """Calendar year → owning plan round (``P27`` owns 2027). One year, one round."""
    return {y: code for code in plan_rounds if (y := round_calendar_year(code)) is not None}


def _owning_round_for_year(
    year: int | None,
    plan_by_year: Mapping[int, str],
    latest_round: str | None,
) -> str | None:
    """Round that owns ``year``; horizon years beyond the latest immediate year stay on that round."""
    if year is None:
        return latest_round
    if year in plan_by_year:
        return plan_by_year[year]
    if plan_by_year and latest_round and year > max(plan_by_year):
        return latest_round
    return plan_by_year.get(year) if year in plan_by_year else latest_round


def _filter_one_round_per_year(
    rows: list[dict[str, Any]],
    plan_by_year: Mapping[int, str],
    latest_round: str | None,
) -> list[dict[str, Any]]:
    """Drop rows whose Round is not the owner of their calendar Year."""
    out: list[dict[str, Any]] = []
    for row in rows:
        year = row.get("_year")
        owning = _owning_round_for_year(year, plan_by_year, latest_round)
        if owning is None:
            continue
        if str(row.get("Round") or "") != owning:
            continue
        out.append(row)
    return out


def _leaf_key(row: Mapping[str, Any], group_keys: tuple[str, ...]) -> tuple:
    return tuple(
        [
            *(row.get(k) for k in group_keys),
            row.get("_iso3") or "",
            str(row.get("NS") or ""),
        ]
    )


def _leaf_amounts(members: Iterable[Mapping[str, Any]]) -> tuple[float, dict[str, float], float]:
    """Return ``(area_total, themes, other)`` for one country×NS leaf.

    ``/data`` uses ``Attribute=Longer-term`` + ``SP/EF`` for themes and
    ``Attribute=Total`` (no ``SP/EF``) for the roll-up. Master detail uses ``Area``.
    Prefer an explicit Total roll-up when present; otherwise sum thematic lines.
    """
    area_total = 0.0
    themes: dict[str, float] = {}
    other = 0.0
    for row in members:
        amount = num(row.get("ValueNum"))
        if amount is None:
            continue
        spef = str(row.get("SP/EF") or "").strip()
        attr = str(row.get("Attribute") or "").strip()
        raw_area = str(row.get("Area") or "").strip()
        if attr == "Total" and not spef and (not raw_area or raw_area == "Total"):
            area_total += amount
            continue
        area = _area_key(row)
        if area in THEME_BREAKDOWN:
            themes[area] = themes.get(area, 0.0) + amount
        elif raw_area == "Total" or area == "Total":
            area_total += amount
        else:
            other += amount
    return area_total, themes, other


def _sum_prefer_total(
    rows: Iterable[Mapping[str, Any]],
    *,
    group_keys: tuple[str, ...],
) -> dict[tuple, float]:
    """Prefer Area=Total roll-up at each leaf; else sum thematic (and other) lines."""
    leaves: dict[tuple, list[Mapping[str, Any]]] = {}
    for row in rows:
        leaves.setdefault(_leaf_key(row, group_keys), []).append(row)
    out: dict[tuple, float] = {}
    n_group = len(group_keys)
    for leaf, members in leaves.items():
        area_total, themes, other = _leaf_amounts(members)
        amount = area_total if area_total else (sum(themes.values()) + other)
        key = leaf[:n_group]
        out[key] = out.get(key, 0.0) + amount
    return out


def _thematic_sums(
    rows: Iterable[Mapping[str, Any]],
    *,
    group_keys: tuple[str, ...],
) -> dict[tuple, float]:
    """Disaggregate by SP/EF/EA; put Area=Total-only amounts in the ``Total`` category."""
    leaves: dict[tuple, list[Mapping[str, Any]]] = {}
    for row in rows:
        leaves.setdefault(_leaf_key(row, group_keys), []).append(row)

    out: dict[tuple, float] = {}
    n_group = len(group_keys)
    for leaf, members in leaves.items():
        base = leaf[:n_group]
        area_total, themes, _other = _leaf_amounts(members)
        theme_sum = sum(themes.values())
        if theme_sum > 0:
            for area, amount in themes.items():
                _add_amount(out, (*base, area), amount)
            # Roll-up exceeds themes → remainder is not disaggregated.
            if area_total > theme_sum + 0.5:
                _add_amount(out, (*base, UNDISAGG_THEME), area_total - theme_sum)
        elif area_total:
            _add_amount(out, (*base, UNDISAGG_THEME), area_total)
    return out


def _apply_manual_ifrc_ea(
    *,
    entity_totals: dict[tuple, float],
    thematic_entity: dict[tuple, float],
    thematic_year: dict[tuple, float],
    thematic_region: dict[tuple, float],
    year: int,
    manual_ea: float,
) -> None:
    """Replace IFRC Secretariat country-plan EAs with the manual rolling estimate for ``year``."""
    key_ent = (year, "IFRC Secretariat")
    old_ea = thematic_entity.get((*key_ent, "EAs"), 0.0)
    delta = manual_ea - old_ea
    thematic_entity[(*key_ent, "EAs")] = manual_ea
    thematic_year[(year, "EAs")] = thematic_year.get((year, "EAs"), 0.0) - old_ea + manual_ea
    entity_totals[key_ent] = entity_totals.get(key_ent, 0.0) + delta
    # Regional EA rows for IFRC cannot be remapped cleanly; leave region matrix on country data.
    _ = thematic_region


def _region_options(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return sorted({str(r.get("Region")).strip() for r in rows if r.get("Region")})


def _submitted_plan_iso3s(submissions: Iterable[Mapping[str, Any]], plan_rounds: set[str]) -> set[str]:
    out: set[str] = set()
    for row in submissions:
        if str(row.get("Round") or "") not in plan_rounds:
            continue
        if norm(row.get("status")) not in SUBMITTED_STATUSES:
            continue
        iso = str(row.get("ISO3") or "").strip().upper()
        if len(iso) == 3:
            out.add(iso)
    return out


def _eas_sprm_for_rounds(plan_rounds: list[str]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for code in plan_rounds:
        try:
            out[code] = load_eas_sprm_ops(code)
        except Exception:
            out[code] = {}
    return out


def _inform_high(label: Any) -> bool:
    text = inform_class_label(label) or str(label or "")
    low = text.strip().lower().replace("_", " ")
    return low in {"high", "very high"}


def aggregate_global_plan(
    fact_rows: list[dict[str, Any]],
    submissions: list[dict[str, Any]],
    *,
    countries: Mapping[str, Mapping[str, Any]] | None = None,
    ns_flags: Mapping[str, Mapping[str, Any]] | None = None,
    inform: Mapping[str, Any] | None = None,
    overlay: Mapping[str, Any] | None = None,
    eas_sprm: Mapping[str, Mapping[str, float]] | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """Pure aggregation used by the API and unit tests."""
    countries = countries or {}
    ns_flags = ns_flags or {}
    inform = inform or {}
    overlay = overlay or {}
    eas_sprm = eas_sprm or {}

    funding_rows = _plan_funding_rows(fact_rows)
    reach_rows = _reach_rows(fact_rows)

    plan_rounds = ordered_rounds(
        c for c in {r.get("Round") for r in funding_rows + reach_rows + list(submissions)} if round_kind(c) == "plan"
    )
    plan_by_year = _plan_year_round_map(plan_rounds)
    latest_round = plan_rounds[-1] if plan_rounds else None
    immediate_year = round_calendar_year(latest_round) if latest_round else None

    # Enrich rows with normalized fields for grouping.
    for row in funding_rows:
        row["_entity"] = _entity_key(row.get("Entity"))
        row["_area"] = _area_key(row)
        row["_year"] = int(row["Year"]) if row.get("Year") else round_calendar_year(row.get("Round"))
        row["_iso3"] = str(row.get("ISO3") or "").strip().upper()
        row["_region"] = str(row.get("Region") or (countries.get(row["_iso3"]) or {}).get("region") or "").strip()
    for row in reach_rows:
        row["_area"] = _area_key(row)
        row["_year"] = int(row["Year"]) if row.get("Year") else round_calendar_year(row.get("Round"))
        row["_iso3"] = str(row.get("ISO3") or "").strip().upper()
        row["_region"] = str(row.get("Region") or (countries.get(row["_iso3"]) or {}).get("region") or "").strip()

    # One calendar year ↔ one plan round (P25/P26/P27 horizons must not stack).
    funding_rows = _filter_one_round_per_year(funding_rows, plan_by_year, latest_round)
    reach_rows = _filter_one_round_per_year(reach_rows, plan_by_year, latest_round)

    years = sorted(
        {
            y
            for y in (
                list(plan_by_year)
                + [r["_year"] for r in funding_rows if r.get("_year")]
                + [r["_year"] for r in reach_rows if r.get("_year")]
            )
            if y
        }
    )
    # Unified Plans optionally cover y0 + two future years (e.g. 2027/28/29).
    # Global Plan defaults to the immediate year of the latest plan round (P27 → 2027),
    # not the farthest horizon year in the extract.
    if year is not None and year in years:
        selected_year = year
    elif immediate_year in years:
        selected_year = immediate_year
    elif years:
        selected_year = years[0]
    else:
        selected_year = None

    entity_totals = _sum_prefer_total(
        [r for r in funding_rows if r.get("_entity") and r.get("_year")],
        group_keys=("_year", "_entity"),
    )
    thematic_entity = _thematic_sums(
        [r for r in funding_rows if r.get("_entity") and r.get("_year")],
        group_keys=("_year", "_entity"),
    )
    thematic_year = _thematic_sums(
        [r for r in funding_rows if r.get("_year")],
        group_keys=("_year",),
    )
    thematic_region = _thematic_sums(
        [r for r in funding_rows if r.get("_year") and r.get("_region")],
        group_keys=("_year", "_region"),
    )
    country_entity = _sum_prefer_total(
        [r for r in funding_rows if r.get("_entity") and r.get("_year") and r.get("_iso3")],
        group_keys=("_year", "_iso3", "_entity"),
    )
    pns_provider = _sum_prefer_total(
        [r for r in funding_rows if r.get("_entity") == "PNS" and r.get("_year") and r.get("NS")],
        group_keys=("_year", "NS"),
    )
    pns_recipient = _sum_prefer_total(
        [r for r in funding_rows if r.get("_entity") == "PNS" and r.get("_year") and r.get("_iso3")],
        group_keys=("_year", "_iso3"),
    )
    reach_thematic = _thematic_sums(
        [r for r in reach_rows if r.get("_year")],
        group_keys=("_year",),
    )
    reach_region = _thematic_sums(
        [r for r in reach_rows if r.get("_year") and r.get("_region")],
        group_keys=("_year", "_region"),
    )
    ea_country = _sum_prefer_total(
        [r for r in funding_rows if r.get("_area") == "EAs" and r.get("_year") and r.get("_iso3")],
        group_keys=("_year", "_iso3"),
    )

    year_block = year_overlay(dict(overlay), selected_year)
    ea_source = "country"
    country_ea_ifrc = (
        thematic_entity.get((selected_year, "IFRC Secretariat", "EAs"), 0.0) if selected_year else None
    )
    if (
        selected_year is not None
        and year_block.get("use_manual_ea_rollover")
        and year_block.get("emergency_appeals_rollover") is not None
    ):
        _apply_manual_ifrc_ea(
            entity_totals=entity_totals,
            thematic_entity=thematic_entity,
            thematic_year=thematic_year,
            thematic_region=thematic_region,
            year=selected_year,
            manual_ea=float(year_block["emergency_appeals_rollover"]),
        )
        ea_source = "manual_rollover"

    submitted = _submitted_plan_iso3s(submissions, set(plan_rounds))
    # Countries with any plan FR for selected year.
    fr_countries: set[str] = set()
    for (y, iso, _ent), _amount in country_entity.items():
        if selected_year is None or y == selected_year:
            fr_countries.add(str(iso))

    large_overlay = {str(c).upper() for c in (overlay.get("large_emergency_iso3") or [])}

    # Prioritisation for selected year (or all FR countries if no year).
    prioritisation: list[dict[str, Any]] = []
    flag_counts = {"inform": 0, "oda": 0, "nsif": 0, "large_emergency": 0, "pns": 0}
    group_counts = {label: 0 for _score, label in _SIGNAL_GROUPS}

    eligible = set(fr_countries) | set(submitted) | large_overlay
    for iso in sorted(eligible):
        country_name = (
            (ns_flags.get(iso) or {}).get("country")
            or (countries.get(iso) or {}).get("name")
            or iso
        )
        region = (countries.get(iso) or {}).get("region") or ""
        inform_label = inform_class_label(inform.get(iso)) or inform.get(iso)
        flag_inform = _inform_high(inform_label)
        flag_oda = has_flag(dict(ns_flags), iso, "oda")
        flag_nsif = has_flag(dict(ns_flags), iso, "nsif")
        pns_amt = 0.0
        for (y, iso_key), amount in pns_recipient.items():
            if iso_key == iso and (selected_year is None or y == selected_year):
                pns_amt += amount
        flag_pns = pns_amt > 0
        ea_amt = 0.0
        for (y, iso_key), amount in ea_country.items():
            if iso_key == iso and (selected_year is None or y == selected_year):
                ea_amt += amount
        sprm = 0.0
        for code, mapping in eas_sprm.items():
            if selected_year is not None and round_calendar_year(code) != selected_year:
                continue
            sprm += float(mapping.get(iso) or 0)
        flag_large = iso in large_overlay or ea_amt > 0 or sprm > 0
        score = int(flag_inform) + int(flag_oda) + int(flag_nsif) + int(flag_large) + int(flag_pns)
        group = prioritisation_group_label(score)
        if flag_inform:
            flag_counts["inform"] += 1
        if flag_oda:
            flag_counts["oda"] += 1
        if flag_nsif:
            flag_counts["nsif"] += 1
        if flag_large:
            flag_counts["large_emergency"] += 1
        if flag_pns:
            flag_counts["pns"] += 1
        group_counts[group] = group_counts.get(group, 0) + 1
        prioritisation.append(
            {
                "iso3": iso,
                "country": country_name,
                "region": region,
                "inform": inform_label,
                "oda": flag_oda,
                "nsif": flag_nsif,
                "large_emergency": flag_large,
                "pns": flag_pns,
                "pns_amount": pns_amt,
                "participation_up": iso in submitted,
                "prioritisation_score": score,
                "prioritisation_group": group,
                "flags": {
                    "inform": int(flag_inform),
                    "oda": int(flag_oda),
                    "nsif": int(flag_nsif),
                    "large_emergency": int(flag_large),
                    "pns": int(flag_pns),
                },
            }
        )
    prioritisation.sort(key=lambda r: (-r["prioritisation_score"], str(r["country"]).lower()))

    participants = [r for r in prioritisation if r["participation_up"]]
    pns_among = [r for r in participants if r["pns"]]

    # Serialize nested sums for JSON.
    def _entity_year_series() -> list[dict[str, Any]]:
        points = []
        for y in years:
            point = {"year": y}
            for ent in ENTITY_ORDER:
                point[ent] = entity_totals.get((y, ent), 0.0)
            point["total"] = sum(point[ent] for ent in ENTITY_ORDER)
            points.append(point)
        return points

    def _theme_matrix(source: dict[tuple, float], extra_keys: int = 0) -> list[dict[str, Any]]:
        # Keys are (year, ...extras, area) when from _thematic_sums
        rows_out: list[dict[str, Any]] = []
        # Rebuild as year -> area -> value for the simple thematic_year case
        if extra_keys == 0:
            for y in years:
                row = {"year": y}
                for area in THEME_CODES:
                    row[area] = source.get((y, area), 0.0)
                rows_out.append(row)
            return rows_out
        # year + one dimension (region or entity)
        dims: set[Any] = set()
        for key in source:
            if len(key) >= 2 + extra_keys:
                dims.add(key[1])
        for y in years:
            for dim in sorted(dims, key=lambda v: str(v).lower()):
                row = {"year": y, "key": dim}
                for area in THEME_CODES:
                    row[area] = source.get((y, dim, area), 0.0)
                if any(row[a] for a in THEME_CODES):
                    rows_out.append(row)
        return rows_out

    # Country list for selected year
    country_rows: list[dict[str, Any]] = []
    all_iso = set(fr_countries) | set(submitted) | set(ns_flags) | set(countries)
    for iso in sorted(all_iso):
        meta = countries.get(iso) or {}
        flags = ns_flags.get(iso) or {}
        totals = {ent: 0.0 for ent in ENTITY_ORDER}
        for ent in ENTITY_ORDER:
            for (y, iso_key, entity), amount in country_entity.items():
                if iso_key == iso and entity == ent and (selected_year is None or y == selected_year):
                    totals[ent] += amount
        if not any(totals.values()) and iso not in submitted and iso not in ns_flags:
            continue
        country_rows.append(
            {
                "iso3": iso,
                "country": flags.get("country") or meta.get("name") or iso,
                "region": meta.get("region") or "",
                "nsif": bool(flags.get("nsif")),
                "oda": bool(flags.get("oda")),
                "inform": inform_class_label(inform.get(iso)) or inform.get(iso),
                "plan_submitted": iso in submitted,
                "hns": totals["HNS"],
                "pns": totals["PNS"],
                "ifrc": totals["IFRC Secretariat"],
                "total": sum(totals.values()),
            }
        )
    country_rows.sort(key=lambda r: (str(r["region"]).lower(), str(r["country"]).lower()))

    # Top lists for selected year
    def _top_named(mapping: dict[tuple, float], limit: int | None = 15) -> list[dict[str, Any]]:
        items = []
        for key, amount in mapping.items():
            y, name = key[0], key[1]
            if selected_year is not None and y != selected_year:
                continue
            items.append({"name": name, "value": amount})
        items.sort(key=lambda r: (-r["value"], str(r["name"]).lower()))
        return items if limit is None else items[:limit]

    def _top_iso(mapping: dict[tuple, float], limit: int = 15) -> list[dict[str, Any]]:
        items = []
        for key, amount in mapping.items():
            y, iso = key[0], key[1]
            if selected_year is not None and y != selected_year:
                continue
            items.append(
                {
                    "iso3": iso,
                    "country": (countries.get(iso) or {}).get("name")
                    or (ns_flags.get(iso) or {}).get("country")
                    or iso,
                    "value": amount,
                    "nsif": has_flag(dict(ns_flags), iso, "nsif"),
                }
            )
        items.sort(key=lambda r: (-r["value"], str(r["country"]).lower()))
        return items[:limit]

    divisions = [
        d
        for d in (overlay.get("divisions") or [])
        if selected_year is None or d.get("year") in (None, selected_year)
    ]
    appeals = [
        a
        for a in (overlay.get("appeals") or [])
        if selected_year is None or a.get("year") in (None, selected_year)
    ]

    selected_entity = {ent: entity_totals.get((selected_year, ent), 0.0) for ent in ENTITY_ORDER} if selected_year else {}
    selected_theme = {area: thematic_year.get((selected_year, area), 0.0) for area in THEME_CODES} if selected_year else {}
    selected_reach = {area: reach_thematic.get((selected_year, area), 0.0) for area in THEME_CODES} if selected_year else {}

    return {
        "years": years,
        "year": selected_year,
        "immediate_year": immediate_year,
        "plan_rounds": plan_rounds,
        "plan_by_year": {str(y): code for y, code in plan_by_year.items()},
        "regions": _region_options(list(submissions) + funding_rows),
        "area_labels": {**dict(AREA_LABELS), UNDISAGG_THEME: "Not disaggregated (Total)"},
        "entity_order": list(ENTITY_ORDER),
        "theme_codes": list(THEME_CODES),
        "ea_source": ea_source,
        "funding": {
            "by_entity_year": _entity_year_series(),
            "by_theme_year": _theme_matrix(thematic_year, 0),
            "by_theme_entity": _theme_matrix(thematic_entity, 1),
            "by_theme_region": _theme_matrix(thematic_region, 1),
            "selected_entity": selected_entity,
            "selected_theme": selected_theme,
            "selected_total": sum(selected_entity.values()),
        },
        "reach": {
            "by_theme_year": _theme_matrix(reach_thematic, 0),
            "by_theme_region": _theme_matrix(reach_region, 1),
            "selected_theme": selected_reach,
            "selected_total": sum(selected_reach.values()),
        },
        "pns": {
            "providers": _top_named(pns_provider, limit=None),
            "top_providers": _top_named(pns_provider),
            "top_recipients": _top_iso(pns_recipient),
            "provider_count": len(
                {name for (y, name) in pns_provider if selected_year is None or y == selected_year}
            ),
            "recipient_count": len(
                {iso for (y, iso) in pns_recipient if selected_year is None or y == selected_year}
            ),
        },
        "secretariat": {
            "by_theme": {
                area: thematic_entity.get((selected_year, "IFRC Secretariat", area), 0.0)
                for area in THEME_CODES
            }
            if selected_year
            else {},
            "top_recipients": _top_iso(
                {
                    (y, iso): amount
                    for (y, iso, ent), amount in country_entity.items()
                    if ent == "IFRC Secretariat"
                }
            ),
            "total": selected_entity.get("IFRC Secretariat", 0.0),
            "nsif_share": _nsif_share(
                {
                    (y, iso): amount
                    for (y, iso, ent), amount in country_entity.items()
                    if ent == "IFRC Secretariat"
                },
                ns_flags,
                selected_year,
            ),
        },
        "countries": country_rows,
        "countries_submitting": len(submitted),
        "countries_with_fr": len(fr_countries),
        "prioritisation": {
            "rows": prioritisation,
            "flag_counts": flag_counts,
            "group_counts": [
                {"group": label, "count": group_counts.get(label, 0)} for _s, label in _SIGNAL_GROUPS
            ],
            "eligible": len(prioritisation),
            "participation_up": len(participants),
            "pns_among_participants": len(pns_among),
            "pns_among_participants_pct": round(len(pns_among) / len(participants) * 100.0, 1)
            if participants
            else None,
        },
        "overlay": {
            "year": {
                **year_block,
                "ea_source": ea_source,
                "country_ea_ifrc": country_ea_ifrc,
            },
            "appeals": appeals,
            "divisions": divisions,
            "large_emergency_iso3": sorted(large_overlay),
            "updated_at": overlay.get("updated_at"),
        },
        "eas_sprm_total": sum(
            float(v or 0)
            for code, mapping in eas_sprm.items()
            if selected_year is None or round_calendar_year(code) == selected_year
            for v in mapping.values()
        ),
        "has_data": bool(years) and (bool(funding_rows) or bool(reach_rows) or bool(appeals) or bool(divisions)),
    }


def _nsif_share(
    mapping: dict[tuple, float],
    ns_flags: Mapping[str, Mapping[str, Any]],
    year: int | None,
) -> dict[str, float]:
    nsif = 0.0
    other = 0.0
    for (y, iso), amount in mapping.items():
        if year is not None and y != year:
            continue
        if has_flag(dict(ns_flags), iso, "nsif"):
            nsif += amount
        else:
            other += amount
    return {"nsif": nsif, "other": other, "total": nsif + other}


def build_upr_global_plan(*, region: str | None = None, year: int | None = None) -> dict[str, Any]:
    """Cached Global Plan payload for one region (or the whole network)."""

    def _loader() -> dict[str, Any]:
        # Same extract as /api/v1/upr/data (plan): PNS Value wins when PNS reported.
        facts = build_upr_data(template="plan")["data"]
        submissions = build_upr_submissions()["data"]
        countries = load_countries()
        iso3s = iso3s_in_region(countries, region)
        facts = _filter_iso3(facts, iso3s)
        submissions = _filter_iso3(submissions, iso3s)
        plan_rounds = ordered_rounds(
            c
            for c in {r.get("Round") for r in facts + submissions}
            if round_kind(c) == "plan"
        )
        payload = aggregate_global_plan(
            facts,
            submissions,
            countries=countries,
            ns_flags=load_ns_category_flags(),
            inform=load_inform_risk(),
            overlay=load_overlay(),
            eas_sprm=_eas_sprm_for_rounds(plan_rounds),
            year=year,
        )
        payload["region"] = region or None
        payload["regions"] = _region_options(submissions) or payload.get("regions") or []
        return payload

    payload, _hit = get_or_build_upr_payload(
        "global-plan",
        {"region": region or None, "year": year, "series": "global-plan-v5"},
        _loader,
    )
    return payload
