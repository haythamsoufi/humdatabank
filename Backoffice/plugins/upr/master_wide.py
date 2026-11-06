"""Excel-ready layouts for ``/api/v1/upr/master`` (planning).

Builds the same measure names as the Power BI "Monster Planning Sheet", then either:

- ``layout=long`` (default): identity columns + Attribute + Value (one row per figure)
- ``layout=wide``: one row per country and round with those measures as columns

Attribute names already combine entity, year and area (e.g. ``HNS 2027 SP1``) so Excel
can filter by Round and pivot Attribute into columns.
"""

from __future__ import annotations

import re
from typing import Any

IDENTITY_COLUMNS = ("Round", "ISO3", "Region", "Country", "Part of Bundle", "Data status")
LONG_COLUMNS = (*IDENTITY_COLUMNS, "Attribute order", "Attribute", "Value")

SECONDARY_ATTR_ORDER = (
    "Latest data available",
    "Volunteers",
    "Staff",
    "Branches",
    "Local Units",
    "Total Population",
    "Income Group",
    "INFORM Risk Class",
    "INFORM Severity Category",
    "INFORM Climate change Risk",
    "Poverty",
    "HDI Score",
    "HDI Rank",
    "HDI Tier",
)

_AREA_RE = re.compile(r"^([A-Za-z]+)(\d+)?")
# Within a year: EAs first, then EF/CC/SP, then Total last (e.g. Reach 2027 EA1 before SP1;
# HNS 2027 EAs before HNS 2027 SP1; HNS 2027 Total last in the HNS group).
_AREA_GROUP_ORDER = {"EA": 0, "EAS": 0, "EF": 1, "CC": 2, "SP": 3, "TOTAL": 9}


def _area_sort_key(area: str) -> tuple:
    text = str(area or "").strip()
    match = _AREA_RE.match(text)
    prefix = (match.group(1) if match else text or "").upper()
    number = int(match.group(2)) if match and match.group(2) else 0
    # "EAs" / "EA" share the emergency-appeal bucket.
    if prefix.startswith("EA"):
        group = 0
    else:
        group = _AREA_GROUP_ORDER.get(prefix, 5)
    return (group, prefix, number, text)


def _entity_key(entity: Any) -> str:
    text = str(entity or "HNS").strip()
    if text.upper().startswith("IFRC"):
        return "IFRC"
    if text.upper() == "PNS":
        return "PNS"
    return "HNS"


def _funding_area(row: dict[str, Any]) -> str:
    area = str(row.get("Area") or "Total").strip() or "Total"
    if row.get("EA Code") or area.upper().startswith("EA"):
        return "EAs"
    return area


def _reach_area(row: dict[str, Any]) -> str:
    """Collapse EA1/EA2/… into a single ``EAs`` bucket (same as funding)."""
    area = str(row.get("Area") or "Total").strip() or "Total"
    if row.get("EA Code") or area.upper().startswith("EA"):
        return "EAs"
    return area


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _add(cells: dict[str, float], column: str, value: float | None) -> None:
    if value is not None:
        cells[column] = cells.get(column, 0) + value


def _clean(value: float | int | str) -> int | float | str:
    if isinstance(value, str):
        return value
    number = float(value)
    return int(number) if number.is_integer() else number


def _round_sort_key(code: Any) -> tuple[int, str]:
    digits = "".join(ch for ch in str(code or "") if ch.isdigit())
    return (int(digits) if digits else 0, str(code or ""))


def _plan_year(round_code: str) -> int | None:
    digits = "".join(ch for ch in str(round_code or "") if ch.isdigit())
    return 2000 + int(digits) if digits else None


def _nskey_year(round_code: str) -> int | None:
    plan = _plan_year(round_code)
    return plan - 1 if plan else None


def _funding_attr(entity: str, year: int, area: str) -> str:
    return f"{entity} {year} {area}"


def _reach_attr(year: int, area: str) -> str:
    return f"Reach {year} {area}"


def _pns_attr(name: str, year: int) -> str:
    return f"{name} {year}"


def _eas_sprm_attr(year: int) -> str:
    return f"IFRC {year} EAs SPRM/OPS"


def _ifrc_new_total_attr(year: int) -> str:
    return f"IFRC {year} New Total"


def _new_total_attr(year: int) -> str:
    return f"{year} New Total"


def compute_new_totals(
    *,
    hns_total: float | None,
    ifrc_total: float | None,
    ifrc_subtotal: float | None,
    pns_total: float | None,
    eas_sprm: float | None,
) -> tuple[float | None, float | None]:
    """Return ``(IFRC New Total, Year New Total)`` matching the Power BI sheet."""
    subtotal = ifrc_subtotal if ifrc_subtotal is not None else ifrc_total
    if eas_sprm is None:
        ifrc_new = ifrc_total
    else:
        base = subtotal or 0
        ifrc_new = base + eas_sprm
    parts = [v for v in (ifrc_new, pns_total, hns_total) if v is not None]
    year_new = sum(parts) if parts else None
    return ifrc_new, year_new


def build_master_context(rounds: set[str] | list[str] | None = None) -> dict[str, Any]:
    """Load secondary + nskeydata maps once for a master build."""
    from plugins.upr.ns_key_data import load_ns_key_rows
    from plugins.upr.secondary.loaders import (
        load_eas_sprm_ops,
        load_hdi,
        load_income_groups,
        load_inform_climate,
        load_inform_risk,
        load_inform_severity,
        load_multilateral,
        load_population,
        load_poverty,
    )
    from plugins.upr.secondary.planning_bundle import planning_bundle_by_iso3

    ns_key_by_iso_year: dict[tuple[str, int], dict[str, Any]] = {}
    try:
        for row in load_ns_key_rows():
            iso3 = str(row.get("ISO3") or "").strip().upper()
            year = row.get("Year")
            if iso3 and year is not None:
                ns_key_by_iso_year[(iso3, int(year))] = row
    except Exception:
        ns_key_by_iso_year = {}

    poverty_raw = load_poverty()
    poverty: dict[str, Any] = {}
    for iso3, value in poverty_raw.items():
        poverty[iso3] = value.get("value") if isinstance(value, dict) else value

    rounds = {str(code).strip().upper() for code in (rounds or []) if code}
    multilateral: dict[str, dict[str, list[str]]] = {}
    eas_sprm: dict[str, dict[str, float]] = {}
    for code in rounds:
        try:
            multilateral[code] = load_multilateral(code)
        except Exception:
            multilateral[code] = {}
        try:
            eas_sprm[code] = load_eas_sprm_ops(code)
        except Exception:
            eas_sprm[code] = {}

    return {
        "ns_key_by_iso_year": ns_key_by_iso_year,
        "planning_bundle": planning_bundle_by_iso3(),
        "population": load_population(),
        "income_groups": load_income_groups(),
        "inform_risk": load_inform_risk(),
        "inform_severity": load_inform_severity(),
        "inform_climate": load_inform_climate(),
        "poverty": poverty,
        "hdi": load_hdi(),
        "multilateral": multilateral,
        "eas_sprm": eas_sprm,
    }


def pivot_master_wide(
    rows: list[dict[str, Any]],
    *,
    region_by_iso: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Return ``(columns, wide_rows)`` for master rows of every planning round."""
    region_by_iso = region_by_iso or {}
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        iso3 = row.get("ISO3")
        if iso3:
            by_key.setdefault((str(row.get("Round") or ""), str(iso3)), []).append(row)

    if context is None:
        context = build_master_context({round_code for round_code, _iso in by_key})

    reach_cols: set[tuple[int, str]] = set()
    activity_areas: set[str] = set()
    fund_hns_ifrc: set[tuple[int, str, str]] = set()
    pns_names: set[tuple[int, str]] = set()
    fund_years: set[int] = set()
    eas_years: set[int] = set()
    secondary_seen: set[str] = set()
    country_rows: list[dict[str, Any]] = []

    def _group_sort(key: tuple[str, str]) -> tuple:
        round_code, iso3 = key
        country = str(by_key[key][0].get("Country") or iso3)
        return (_round_sort_key(round_code), country)

    for round_code, iso3 in sorted(by_key, key=_group_sort):
        group = by_key[(round_code, iso3)]
        head = next((r for r in group if r.get("Source") == "Country Data"), group[0])
        out: dict[str, Any] = {
            "Round": round_code or head.get("Round"),
            "ISO3": iso3,
            "Region": region_by_iso.get(iso3),
            "Country": head.get("Country"),
            "Part of Bundle": (context.get("planning_bundle") or {}).get(iso3),
            "Data status": head.get("Data status"),
        }
        cells: dict[str, Any] = {}
        activities: dict[str, set[str]] = {}
        funding: dict[tuple[int, str, str], float] = {}
        pns_parts: dict[tuple[int, str], dict[str, float]] = {}

        # NS key data from nskeydata (FDRS > annual > mid-year > planning).
        nskey_year = _nskey_year(round_code)
        ns_key = (context.get("ns_key_by_iso_year") or {}).get((iso3, nskey_year)) if nskey_year else None
        if ns_key:
            for attr, column in (
                ("Volunteers", "Volunteers"),
                ("Staff", "Staff"),
                ("Branches", "Branches"),
                ("LocalUnits", "Local Units"),
            ):
                value = ns_key.get(attr)
                if value is not None:
                    cells[column] = _clean(value)
                    secondary_seen.add(column)
            if ns_key.get("Source"):
                cells["Latest data available"] = ns_key["Source"]
                secondary_seen.add("Latest data available")

        # Secondary country attributes.
        for attr, mapping in (
            ("Total Population", "population"),
            ("Income Group", "income_groups"),
            ("INFORM Risk Class", "inform_risk"),
            ("INFORM Severity Category", "inform_severity"),
            ("INFORM Climate change Risk", "inform_climate"),
            ("Poverty", "poverty"),
        ):
            value = (context.get(mapping) or {}).get(iso3)
            if value is not None and value != "":
                cells[attr] = _clean(value) if isinstance(value, (int, float)) else value
                secondary_seen.add(attr)
        hdi = (context.get("hdi") or {}).get(iso3) or {}
        for key, attr in (("score", "HDI Score"), ("rank", "HDI Rank"), ("tier", "HDI Tier")):
            if hdi.get(key) is not None and hdi.get(key) != "":
                cells[attr] = _clean(hdi[key]) if isinstance(hdi[key], (int, float)) else hdi[key]
                secondary_seen.add(attr)

        for row in group:
            section = row.get("Section")
            amount = _num(row.get("ValueNum"))
            year = row.get("Year")
            # Plan NS Data is ignored when nskeydata supplied the figures.
            if section == "NS Data":
                continue
            if section == "Reach" and amount is not None and year:
                area = _reach_area(row)
                reach_cols.add((int(year), area))
                _add(cells, _reach_attr(int(year), area), amount)
            elif section == "Support" and row.get("Indicator") == "Bilateral Support":
                area = str(row.get("Area") or "")
                if area and area != "Total" and row.get("NS"):
                    activity_areas.add(area)
                    activities.setdefault(area, set()).add(str(row["NS"]))
            elif section == "Funding" and row.get("Indicator") == "Funding Requirement" and amount is not None and year:
                year = int(year)
                fund_years.add(year)
                entity = _entity_key(row.get("Entity"))
                area = _funding_area(row)
                if entity == "PNS":
                    name = str(row.get("NS") or "PNS")
                    pns_names.add((year, name))
                    bucket = pns_parts.setdefault((year, name), {})
                    bucket[area] = bucket.get(area, 0) + amount
                else:
                    fund_hns_ifrc.add((year, entity, area))
                    key = (year, entity, area)
                    funding[key] = funding.get(key, 0) + amount

        multi_names = set((context.get("multilateral") or {}).get(round_code, {}).get(iso3) or [])
        bilateral_names = set().union(*activities.values()) if activities else set()
        for area, names in activities.items():
            out[f"Activities {area}"] = ", ".join(sorted(names))
        combined = sorted(bilateral_names | multi_names)
        if combined:
            labeled = [f"{name}*" if name in multi_names and name not in bilateral_names else name for name in combined]
            out["Activities Combined"] = ", ".join(labeled)
            # Multilateral-only societies without a bilateral SP still appear in Combined.
            if multi_names - bilateral_names and "Combined" not in activity_areas:
                activity_areas.add("Combined")

        pns_total: dict[tuple[int, str], float] = {}
        for key, parts in pns_parts.items():
            pns_total[key] = parts["Total"] if "Total" in parts else sum(parts.values())

        plan_year = _plan_year(round_code)
        eas_value = None
        if plan_year is not None:
            eas_value = (context.get("eas_sprm") or {}).get(round_code, {}).get(iso3)
            if eas_value:
                fund_years.add(plan_year)
                eas_years.add(plan_year)

        for year in sorted(fund_years | eas_years):
            totals: dict[str, float | None] = {}
            for entity in ("HNS", "IFRC"):
                parts = {a: v for (y, e, a), v in funding.items() if y == year and e == entity}
                if not parts:
                    totals[entity] = None
                    continue
                total = parts.get("Total")
                if total is None:
                    total = sum(parts.values())
                    funding[(year, entity, "Total")] = total
                    fund_hns_ifrc.add((year, entity, "Total"))
                totals[entity] = total
            pns_sum = sum(v for (y, _n), v in pns_total.items() if y == year) if any(
                y == year for (y, _n) in pns_total
            ) else None
            known = [v for v in (totals["HNS"], totals["IFRC"], pns_sum) if v is not None]
            if known:
                cells[f"Total FR {year}"] = sum(known)
            if pns_sum is not None:
                cells[f"Total PNSs {year}"] = pns_sum

            sprm = eas_value if plan_year == year else None
            if sprm:
                cells[_eas_sprm_attr(year)] = _clean(sprm)
            ifrc_new, year_new = compute_new_totals(
                hns_total=totals.get("HNS"),
                ifrc_total=totals.get("IFRC"),
                ifrc_subtotal=funding.get((year, "IFRC", "Total")),
                pns_total=pns_sum,
                eas_sprm=sprm,
            )
            if ifrc_new is not None:
                cells[_ifrc_new_total_attr(year)] = _clean(ifrc_new)
            if year_new is not None:
                cells[_new_total_attr(year)] = _clean(year_new)

        for (year, entity, area), value in funding.items():
            cells[_funding_attr(entity, year, area)] = _clean(value)
        for (year, name), value in pns_total.items():
            cells[_pns_attr(name, year)] = _clean(value)

        # Numeric cells already cleaned; copy string cells as-is.
        out.update(cells)
        country_rows.append(out)

    years = sorted(fund_years | eas_years)
    columns: list[str] = list(IDENTITY_COLUMNS)
    for attr in SECONDARY_ATTR_ORDER:
        if attr in secondary_seen or any(row.get(attr) is not None for row in country_rows):
            columns.append(attr)
    columns.extend(_reach_attr(y, a) for y, a in sorted(reach_cols, key=lambda c: (c[0], _area_sort_key(c[1]))))
    columns.extend(f"Activities {a}" for a in sorted(activity_areas, key=_area_sort_key) if a != "Combined")
    columns.append("Activities Combined")
    for entity in ("HNS", "IFRC"):
        for year in years:
            areas = sorted({a for (y, e, a) in fund_hns_ifrc if y == year and e == entity}, key=_area_sort_key)
            columns.extend(_funding_attr(entity, year, a) for a in areas)
    for year in years:
        columns.append(_eas_sprm_attr(year))
        columns.append(_ifrc_new_total_attr(year))
    for year in years:
        columns.extend(_pns_attr(name, year) for name in sorted({n for (y, n) in pns_names if y == year}))
    columns.extend(f"Total PNSs {year}" for year in years)
    columns.extend(f"Total FR {year}" for year in years)
    columns.extend(_new_total_attr(year) for year in years)

    # Drop measure columns that never appear, keep identity.
    used = set(IDENTITY_COLUMNS)
    for row in country_rows:
        used.update(key for key, value in row.items() if value is not None and value != "")
    columns = [column for column in columns if column in used]

    wide = [{column: row.get(column) for column in columns} for row in country_rows]
    return columns, wide


def melt_master_long(
    rows: list[dict[str, Any]],
    *,
    region_by_iso: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Wide measures melted to ``Attribute`` / ``Value`` for Excel pivot tables."""
    columns, wide = pivot_master_wide(rows, region_by_iso=region_by_iso, context=context)
    measure_columns = [column for column in columns if column not in IDENTITY_COLUMNS]
    order_by_attr = {attribute: index + 1 for index, attribute in enumerate(measure_columns)}
    long_rows: list[dict[str, Any]] = []
    for row in wide:
        identity = {column: row.get(column) for column in IDENTITY_COLUMNS}
        for attribute in measure_columns:
            value = row.get(attribute)
            if value is None or value == "":
                continue
            long_rows.append(
                {
                    **identity,
                    "Attribute order": order_by_attr[attribute],
                    "Attribute": attribute,
                    "Value": value,
                }
            )
    long_rows.sort(
        key=lambda row: (
            _round_sort_key(row.get("Round")),
            int(row.get("Attribute order") or 0),
            str(row.get("Country") or ""),
        )
    )
    return list(LONG_COLUMNS), long_rows
