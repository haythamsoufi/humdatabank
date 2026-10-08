"""Everyone Counts 2026 outputs for the data-explorer tab.

Each printed figure and table has one entry. Series that can be calculated
from the FDRS panel and the saved World Bank snapshot are filled in. The
others stay in the catalogue with the source they still need.

Figures 3.8 and 3.9 are the unadjusted comparison. The printed charts, and
Figure 3.10 and Table A.1, are multilevel models and are not re-estimated.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any, Mapping

from plugins.fdrs.services.ecr_external import (
    HAZARD_GROUPS,
    VOLUNTEER_AGE_BANDS,
    WAGE_BASES,
    centred_smooth,
    geometric_mean,
    hazard_group,
    hourly_wage,
    index_to_base,
    interpolate_median_age,
    mechanism_cause,
    operation_mix,
    stressed_by_income,
    widest_crises,
)
from plugins.fdrs.services.ecr_analysis import (
    INCOME_LABELS,
    STAFF_CODE,
    VOLUNTEER_CODE,
    _age_summary,
    _female_share,
    _is_provisional,
    _median_positive,
    _population_series,
    _positive,
    _region_summary,
    _sum_positive,
    _year_rows,
    population_for_year,
    volunteer_density_by_income,
)

BIG5 = frozenset({"IND", "CHN", "IRN", "PHL", "NGA"})
SWVR_ALL_VOLUNTEERS = 2_100_000_000
SWVR_ORGANISATION_VOLUNTEERS = 714_000_000

RESPONSE = ("KPI_ReachDRR", "KPI_ReachDRER", "KPI_ReachCTP", "KPI_ReachL", "KPI_ReachS")
RESILIENCE_TREND = (
    "KPI_Climate",
    "KPI_ClimateHeat",
    "KPI_ReachH",
    "KPI_ReachWASH",
    "KPI_ReachHPM",
    "KPI_ReachHI",
    "KPI_TrainFA",
    "KPI_ReachM",
)
RESPECT = ("KPI_ReachSI", "KPI_ReachRCRCEd")
CROSS = ("KPI_ReachLTSPD", "KPI_ReachDRER")
RESILIENCE_GROUP = (
    "KPI_ReachLTSPD",
    "KPI_ReachH",
    "KPI_ReachHI",
    "KPI_ReachWASH",
    "KPI_ReachM",
    "KPI_ReachHPM",
    "KPI_ClimateHeat",
    "KPI_Climate",
    "KPI_DonBlood",
    "KPI_TrainFA",
)
REACH_FOR_SPLIT = tuple(dict.fromkeys(RESPONSE + RESILIENCE_TREND + RESPECT + CROSS + RESILIENCE_GROUP))

INCOME_COLORS = {"L": "#1e3a5f", "LM": "#0369a1", "UM": "#c2410c", "H": "#e11b22"}
BAND_COLORS = {"All National Societies": "#6b7280", "Higher income": "#1e3a5f", "Lower income": "#e11b22"}
SERIES_COLORS = (
    "#1e3a5f",
    "#e11b22",
    "#0369a1",
    "#c2410c",
    "#0f766e",
    "#7c3aed",
    "#b45309",
    "#be123c",
    "#334155",
    "#059669",
)
DENSITY_BANDS = (
    ("2% or more", "#e11b22", 20_000),
    ("1 to 2%", "#c2410c", 10_000),
    ("0.5 to 1%", "#0369a1", 5_000),
    ("0.1 to 0.5%", "#1e3a5f", 1_000),
    ("Under 0.1%", "#9ca3af", 0),
)
INSURANCE_SEGMENTS = (
    ("Insured", "#1e3a5f"),
    ("Reported none", "#c2410c"),
    ("Did not report", "#d1d5db"),
)


def build_chapters(
    rows: list[Mapping[str, Any]],
    *,
    world_bank: Mapping[str, Any] | None = None,
    leaders: list[Mapping[str, Any]] | None = None,
    sources: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """One chapter per part of the report, plus the databank data checks."""
    ctx = _context(rows, world_bank=world_bank, leaders=leaders)
    ctx["sources"] = dict(sources or {})
    return [
        _chapter("volunteers", "Volunteers", _volunteer_outputs(ctx)),
        _chapter("reach", "Reach", _reach_outputs(ctx)),
        _chapter("operations", "Operations", _operations_outputs(ctx)),
        _chapter("capacity", "Capacity", _capacity_outputs(ctx)),
        _chapter("value", "Value of time", _value_outputs(ctx)),
        _chapter("protection", "Protection", _protection_outputs(ctx)),
        _chapter("giving", "Giving", _giving_outputs(ctx)),
        _chapter("checks", "Data checks", _check_outputs(ctx)),
    ]


def _context(rows, *, world_bank, leaders) -> dict[str, Any]:
    volunteers = _year_rows(rows, VOLUNTEER_CODE)
    provisional = {year for year, group in volunteers.items() if _is_provisional(group)}
    years = sorted(volunteers)
    settled = [year for year in years if year not in provisional and _positive(volunteers[year])]
    labels = {}
    names = {}
    for row in rows:
        labels[row["kpi_code"]] = row.get("label") or row["kpi_code"]
        names[row["iso3"]] = row.get("country_name") or row["iso3"]
    return {
        "rows": rows,
        "income": _income_map(world_bank),
        "populations": _populations(world_bank),
        "has_population": bool(world_bank and world_bank.get("population")),
        "labels": labels,
        "names": names,
        "provisional": provisional,
        "leaders": list(leaders or []),
        "world_bank": world_bank,
        "settled_year": settled[-1] if settled else None,
        "open_year": years[-1] if years and years[-1] in provisional else None,
        "volunteers": volunteers,
    }


def _chapter(chapter_id: str, label: str, outputs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": chapter_id, "label": label, "outputs": outputs}


def _output(number: str, output_id: str, title: str, caption: str, **body: Any) -> dict[str, Any]:
    item = {
        "number": number,
        "id": output_id,
        "title": title,
        "caption": caption,
        "available": body.get("kind") != "missing",
    }
    item.update(body)
    return item


def _missing(
    number: str,
    output_id: str,
    title: str,
    source: str,
    detail: str,
    *,
    blocker: str = "source",
) -> dict[str, Any]:
    return _output(
        number,
        output_id,
        title,
        detail,
        kind="missing",
        available=False,
        source=source,
        detail=detail,
        blocker=blocker,
    )


def _income_map(world_bank: Mapping[str, Any] | None) -> dict[str, str]:
    mapping = {}
    for item in (world_bank or {}).get("income_groups") or []:
        iso3 = str(item.get("iso3") or "").strip().upper()
        group = item.get("income_group")
        if iso3 and group in INCOME_LABELS:
            mapping[iso3] = str(group)
    return mapping


def _populations(world_bank: Mapping[str, Any] | None) -> dict[str, dict[int, float]]:
    if not world_bank or not world_bank.get("population"):
        return {}
    return _population_series(list(world_bank.get("population") or []))


def _pop(ctx: dict[str, Any], iso3: str, year: int) -> float | None:
    found = population_for_year(ctx["populations"], iso3, year)
    if found is None:
        return None
    return found[0]


def _hl(group: str | None) -> str | None:
    if group in ("H", "UM"):
        return "Higher income"
    if group in ("LM", "L"):
        return "Lower income"
    return None


def _band_name(vpm: float) -> str:
    for name, _color, floor in DENSITY_BANDS:
        if vpm >= floor:
            return name
    return "Under 0.1%"


def _label(ctx: dict[str, Any], code: str) -> str:
    return ctx["labels"].get(code) or code


def _point(year: int, value: float, provisional: bool = False, dashed: bool = False) -> dict[str, Any]:
    item = {"year": int(year), "value": float(value), "provisional": bool(provisional)}
    if dashed:
        item["dashed"] = True
    return item


def _line(name: str, color: str, points: list[dict[str, Any]]) -> dict[str, Any]:
    return {"name": name, "color": color, "points": points}


def _rows_for(ctx: dict[str, Any], code: str, year: int) -> list[Mapping[str, Any]]:
    return [row for row in ctx["rows"] if row["kpi_code"] == code and row["year"] == year]


def _share_of_row(row: Mapping[str, Any]) -> float | None:
    female = row.get("female")
    male = row.get("male")
    if female is None or male is None:
        return None
    total = female + male
    if total <= 0:
        return None
    return female / total


def _sex_lines(ctx: dict[str, Any], code: str, year_min: int) -> list[dict[str, Any]]:
    buckets: dict[tuple[int, str], list[float]] = defaultdict(list)
    for row in ctx["rows"]:
        if row["kpi_code"] != code or row["year"] < year_min:
            continue
        share = _share_of_row(row)
        if share is None:
            continue
        buckets[(row["year"], "All National Societies")].append(share)
        band = _hl(ctx["income"].get(row["iso3"]))
        if band:
            buckets[(row["year"], band)].append(share)
    series = []
    for name in ("All National Societies", "Higher income", "Lower income"):
        years = sorted({year for year, band in buckets if band == name})
        points = [
            _point(year, float(median(buckets[(year, name)])), year in ctx["provisional"])
            for year in years
        ]
        if points:
            series.append(_line(name, BAND_COLORS[name], points))
    return series


def _indicator_lines(ctx: dict[str, Any], codes: tuple[str, ...], year_min: int) -> list[dict[str, Any]]:
    series = []
    for index, code in enumerate(codes):
        points = []
        grouped = _year_rows(ctx["rows"], code)
        for year in sorted(year for year in grouped if year >= year_min):
            societies = len(_positive(grouped[year]))
            if societies:
                points.append(_point(year, societies, year in ctx["provisional"]))
        if points:
            series.append(_line(_label(ctx, code), SERIES_COLORS[index % len(SERIES_COLORS)], points))
    return series


def _reach_cross_section(ctx: dict[str, Any], codes: tuple[str, ...], year: int) -> list[dict[str, Any]]:
    table = []
    for code in codes:
        positive = _positive(_rows_for(ctx, code, year))
        if not positive:
            continue
        per_head = []
        by_income: dict[str, list[float]] = defaultdict(list)
        for row in positive:
            by_income[ctx["income"].get(row["iso3"]) or ""].append(row["value"])
            population = _pop(ctx, row["iso3"], year)
            if population:
                per_head.append(row["value"] / population * 1_000_000)
        table.append(
            {
                "indicator": _label(ctx, code),
                "societies": len(positive),
                "median": _median_positive([row["value"] for row in positive]),
                "total": _sum_positive(positive),
                "per_million": _median_positive(per_head),
                "L": _median_positive(by_income.get("L", [])),
                "LM": _median_positive(by_income.get("LM", [])),
                "UM": _median_positive(by_income.get("UM", [])),
                "H": _median_positive(by_income.get("H", [])),
            }
        )
    return table


def _reach_people_rows(ctx: dict[str, Any], codes: tuple[str, ...], year: int) -> list[dict[str, Any]]:
    people = []
    for code in codes:
        for row in _positive(_rows_for(ctx, code, year)):
            group = ctx["income"].get(row["iso3"])
            people.append(
                {
                    "society": row.get("country_name") or row["iso3"],
                    "income": INCOME_LABELS.get(group, ""),
                    "indicator": _label(ctx, code),
                    "people": row["value"],
                }
            )
    people.sort(key=lambda item: (item["indicator"], -(item["people"] or 0), item["society"]))
    return people


def _latest_positive_year(ctx: dict[str, Any], codes: tuple[str, ...]) -> int | None:
    years = [
        row["year"]
        for row in ctx["rows"]
        if row["kpi_code"] in codes and row["value"] is not None and row["value"] > 0
    ]
    return max(years) if years else None


def _income_columns() -> list[dict[str, str]]:
    return [
        {"key": "indicator", "label": "Indicator", "format": "text"},
        {"key": "societies", "label": "Societies", "format": "number"},
        {"key": "median", "label": "Median", "format": "count"},
        {"key": "total", "label": "Total", "format": "count"},
        {"key": "per_million", "label": "Median per million", "format": "count"},
        {"key": "L", "label": "Low", "format": "count"},
        {"key": "LM", "label": "Lower-middle", "format": "count"},
        {"key": "UM", "label": "Upper-middle", "format": "count"},
        {"key": "H", "label": "High", "format": "count"},
    ]


def _volunteer_outputs(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _global_share(ctx),
        _reporting_bars(ctx),
        _rolling_line(ctx),
        _excluding_big5(ctx),
        _density_lines(ctx),
        _giving_comparison(ctx),
        _density_bands(ctx),
        _top10(ctx),
        _staff_ratio_lines(ctx),
        _volunteer_sex(ctx),
        _staff_sex(ctx),
        _leader_sex(ctx),
        _age_bars(ctx),
        _age_gap(ctx),
    ]


def _global_share(ctx: dict[str, Any]) -> dict[str, Any]:
    year = ctx["settled_year"] if ctx["settled_year"] is not None else ctx["open_year"]
    rolling = None
    societies = 0
    if year is not None:
        values = [
            row["value_roll3"]
            for row in ctx["volunteers"].get(year, [])
            if row.get("value_roll3") is not None and row["value_roll3"] > 0
        ]
        if values:
            rolling = float(sum(values))
            societies = len(values)
    network_share = None
    if rolling:
        network_share = rolling / SWVR_ORGANISATION_VOLUNTEERS
    year_label = str(year) if year is not None else "the latest year"
    return _output(
        "Figure 2.1",
        "c3-volglobshare",
        "IFRC volunteers among organisation-based volunteers",
        "The worldwide totals are the State of the World’s Volunteerism Report 2026 figures used in Everyone Counts (2.1 billion volunteers, of whom 714 million volunteer through an organisation). They are not a live feed. The IFRC line is the sum of National Societies’ three-year means in "
        + year_label
        + ".",
        kind="table",
        columns=[
            {"key": "group", "label": "Group", "format": "text"},
            {"key": "people", "label": "People", "format": "count"},
            {"key": "share", "label": "Share of organisation-based", "format": "percent"},
        ],
        rows=[
            {"group": "All volunteers worldwide (SWVR 2026)", "people": SWVR_ALL_VOLUNTEERS, "share": None},
            {
                "group": "Organisation-based volunteers (SWVR 2026)",
                "people": SWVR_ORGANISATION_VOLUNTEERS,
                "share": 1,
            },
            {
                "group": f"IFRC network, three-year mean, {year_label}"
                + (f" ({societies} National Societies)" if societies else ""),
                "people": rolling,
                "share": network_share,
            },
        ],
    )


def _reporting_bars(ctx: dict[str, Any]) -> dict[str, Any]:
    points = []
    for year in sorted(ctx["volunteers"]):
        if year < 2016:
            continue
        reported = [row for row in _positive(ctx["volunteers"][year]) if not row.get("imputed")]
        points.append(
            {
                "year": year,
                "value": len(reported),
                "provisional": year in ctx["provisional"],
            }
        )
    return _output(
        "Figure 2.2",
        "c3-volsn",
        "National Societies reporting volunteers",
        "Societies with a positive reported count. Imputed values are not counted. An amber bar is a provisional year.",
        kind="bars",
        unit="number",
        points=points,
    )


def _rolling_line(ctx: dict[str, Any]) -> dict[str, Any]:
    points = []
    for year in sorted(ctx["volunteers"]):
        if year < 2012:
            continue
        values = [
            row["value_roll3"]
            for row in ctx["volunteers"][year]
            if row.get("value_roll3") is not None and row["value_roll3"] > 0
        ]
        if not values:
            continue
        points.append(_point(year, float(sum(values)), year in ctx["provisional"]))
    return _output(
        "Figure 2.3",
        "c3-volsroll-total-n",
        "Volunteers, three-year mean",
        "Sum across National Societies of each Society’s trailing three-year mean. A Society is included only when that year and the two before it are all positive. A hollow point is a provisional year.",
        kind="lines",
        unit="count",
        series=[_line("Volunteers", "#1e3a5f", points)] if points else [],
    )


def _excluding_big5(ctx: dict[str, Any]) -> dict[str, Any]:
    all_points = []
    trimmed = []
    for year in sorted(ctx["volunteers"]):
        if year in ctx["provisional"]:
            continue
        positive = _positive(ctx["volunteers"][year])
        if not positive:
            continue
        total = float(sum(row["value"] for row in positive))
        without = float(sum(row["value"] for row in positive if row["iso3"] not in BIG5))
        all_points.append(_point(year, total))
        trimmed.append(_point(year, without))
    series = []
    if all_points:
        series.append(_line("All reporting Societies", "#9ca3af", all_points))
        series.append(_line("Without India, China, Iran, the Philippines and Nigeria", "#e11b22", trimmed))
    return _output(
        "Figure 2.4",
        "c3-volsglob-excl",
        "Volunteers without the five largest Societies",
        "Annual reported totals for closed years. The five Societies are India, China, Iran, the Philippines and Nigeria. Provisional years are left out.",
        kind="lines",
        unit="count",
        series=series,
        note=""
        if series
        else "No closed year has a published volunteer total yet. A year is left out when most Societies still have no published value, so this figure stays empty even when the open year has reported counts.",
    )


def _density_lines(ctx: dict[str, Any]) -> dict[str, Any]:
    if not ctx["has_population"]:
        return _missing(
            "Figure 2.5",
            "c3-volsperpop",
            "Volunteers per million people, by income group",
            "World Bank population",
            "No World Bank population snapshot is saved, so volunteer density is not calculated.",
        )
    series = []
    points = volunteer_density_by_income(ctx["rows"], ctx["world_bank"])
    for group in ("L", "LM", "UM", "H"):
        group_points = [
            _point(
                item["year"],
                item["median_per_million"],
                dashed=bool(item.get("population_carried_forward")),
            )
            for item in points
            if item["income_group"] == group
        ]
        if group_points:
            series.append(_line(INCOME_LABELS[group], INCOME_COLORS[group], group_points))
    return _output(
        "Figure 2.5",
        "c3-volsperpop",
        "Volunteers per million people, by income group",
        "Median of each Society’s three-year volunteer mean divided by World Bank population, within the Bank’s current income group. A hollow point means that country’s population was carried forward from its last published year. Years before 2014 are left out.",
        kind="lines",
        unit="per_million",
        series=series,
    )


def _density_bands(ctx: dict[str, Any]) -> dict[str, Any]:
    if not ctx["has_population"]:
        return _missing(
            "Figure 2.7",
            "c3-voltarget-area",
            "National Societies by volunteer density, 2020–2024",
            "World Bank population",
            "No World Bank population snapshot is saved, so the density bands are not calculated.",
        )
    window = [year for year in range(2020, 2025) if year not in ctx["provisional"]]
    by_society: dict[str, list[float]] = defaultdict(list)
    for row in ctx["rows"]:
        if row["kpi_code"] != VOLUNTEER_CODE or row["year"] not in window:
            continue
        rolling = row.get("value_roll3")
        group = ctx["income"].get(row["iso3"])
        if group is None or not isinstance(rolling, (int, float)) or rolling <= 0:
            continue
        population = _pop(ctx, row["iso3"], row["year"])
        if not population:
            continue
        by_society[row["iso3"]].append(float(rolling) / population * 1_000_000)
    counts: dict[str, dict[str, int]] = {group: {name: 0 for name, _color, _floor in DENSITY_BANDS} for group in INCOME_LABELS}
    totals = {group: 0 for group in INCOME_LABELS}
    for iso3, values in by_society.items():
        group = ctx["income"][iso3]
        counts[group][_band_name(float(sum(values) / len(values)))] += 1
        totals[group] += 1
    rows = []
    for group in ("L", "LM", "UM", "H"):
        if not totals[group]:
            continue
        rows.append(
            {
                "category": INCOME_LABELS[group],
                "n": totals[group],
                "counts": counts[group],
            }
        )
    years_label = _year_span(window) or "2020–2024"
    return _output(
        "Figure 2.7",
        "c3-voltarget-area",
        "Share of National Societies in each volunteer-density band",
        f"Each Society’s band is the mean of its volunteers per million over {years_label}, using closed years only. The share is within that income group. 20,000 per million is 2% of the population.",
        kind="stacked",
        unit="share",
        segments=[{"name": name, "color": color} for name, color, _floor in DENSITY_BANDS],
        rows=rows,
        note="" if rows else "No Society in this window has both a three-year volunteer mean and a population figure.",
    )


def _top10(ctx: dict[str, Any]) -> dict[str, Any]:
    year = ctx["settled_year"] if ctx["settled_year"] is not None else ctx["open_year"]
    if not ctx["has_population"]:
        return _missing(
            "Figure 2.8",
            "c3-volpop-top10",
            "National Societies with the highest volunteer share of the population",
            "World Bank population",
            "No World Bank population snapshot is saved, so this ranking is not calculated.",
        )
    if year is None:
        return _output(
            "Figure 2.8",
            "c3-volpop-top10",
            "National Societies with the highest volunteer share of the population",
            "Three-year volunteer mean divided by World Bank population.",
            kind="ranked",
            unit="share",
            rows=[],
            note="No volunteer year is on the panel yet.",
        )
    ranked = []
    for row in ctx["volunteers"].get(year, []):
        rolling = row.get("value_roll3")
        if not isinstance(rolling, (int, float)) or rolling <= 0:
            continue
        population = _pop(ctx, row["iso3"], year)
        if not population:
            continue
        group = ctx["income"].get(row["iso3"])
        share = rolling / population
        detail = INCOME_LABELS.get(group, "Income group not classified")
        ranked.append(
            {
                "name": row.get("country_name") or row["iso3"],
                "value": share,
                "detail": detail,
            }
        )
    ranked.sort(key=lambda item: item["value"], reverse=True)
    top = []
    for index, item in enumerate(ranked[:10], start=1):
        top.append({"rank": index, **item})
    return _output(
        "Figure 2.8",
        "c3-volpop-top10",
        "Ten National Societies with the highest volunteer share of the population",
        f"Three-year volunteer mean in {year} divided by World Bank population. {len(ranked)} Societies had both figures.",
        kind="ranked",
        unit="percent",
        rows=top,
    )


def _staff_ratio_lines(ctx: dict[str, Any]) -> dict[str, Any]:
    staff = _year_rows(ctx["rows"], STAFF_CODE)
    buckets: dict[tuple[int, str], list[float]] = defaultdict(list)
    for year, volunteer_rows in ctx["volunteers"].items():
        staff_by_iso = {
            row["iso3"]: row["value"]
            for row in staff.get(year, [])
            if row["value"] is not None and row["value"] > 0
        }
        for row in _positive(volunteer_rows):
            paid = staff_by_iso.get(row["iso3"])
            group = ctx["income"].get(row["iso3"])
            if not paid or not group:
                continue
            buckets[(year, group)].append(row["value"] / paid)
    series = []
    for group in ("L", "LM", "UM", "H"):
        years = sorted({year for year, item_group in buckets if item_group == group})
        points = [
            _point(year, float(median(buckets[(year, group)])), year in ctx["provisional"])
            for year in years
        ]
        if points:
            series.append(_line(INCOME_LABELS[group], INCOME_COLORS[group], points))
    note = ""
    if not ctx["income"]:
        note = "Income groups need the World Bank snapshot, so this chart is empty until that snapshot is saved."
    elif not series:
        note = "No Society reported both volunteers and paid staff."
    return _output(
        "Figure 2.9",
        "c3-vsratio-4inc",
        "Volunteers per paid staff member, by income group",
        "Each point is the median, within an income group, of volunteers divided by paid staff. Both figures have to be positive. A hollow point is a provisional year.",
        kind="lines",
        unit="ratio",
        series=series,
        note=note,
    )


def _volunteer_sex(ctx: dict[str, Any]) -> dict[str, Any]:
    series = _sex_lines(ctx, VOLUNTEER_CODE, 2016)
    return _output(
        "Figure 2.10",
        "c3-pyramidyear-ns",
        "Women’s share of volunteers",
        "Median, across Societies, of women divided by women plus men. Societies that did not report both are left out. Higher income is high and upper-middle; lower income is low and lower-middle.",
        kind="lines",
        unit="share",
        series=series,
        note="" if series else "No Society reported a sex breakdown for volunteers.",
    )


def _staff_sex(ctx: dict[str, Any]) -> dict[str, Any]:
    series = _sex_lines(ctx, STAFF_CODE, 2016)
    return _output(
        "Figure 2.11",
        "c3-pyramidyear-staff-ns",
        "Women’s share of paid staff",
        "Same measure as the volunteer chart, using the sex breakdown reported for paid staff.",
        kind="lines",
        unit="share",
        series=series,
        note="" if series else "No Society reported a sex breakdown for paid staff.",
    )


def _leader_sex(ctx: dict[str, Any]) -> dict[str, Any]:
    buckets: dict[tuple[int, str], list[int]] = defaultdict(list)
    for leader in ctx["leaders"]:
        year = leader.get("year")
        sex = leader.get("sex")
        if not isinstance(year, int) or year < 2017:
            continue
        if sex not in {"Female", "Male"}:
            continue
        flag = 1 if sex == "Female" else 0
        buckets[(year, "All National Societies")].append(flag)
        band = _hl(ctx["income"].get(leader.get("iso3")))
        if band:
            buckets[(year, band)].append(flag)
    series = []
    for name in ("All National Societies", "Higher income", "Lower income"):
        years = sorted({year for year, band in buckets if band == name})
        points = [
            _point(year, sum(buckets[(year, name)]) / len(buckets[(year, name)]), year in ctx["provisional"])
            for year in years
        ]
        if points:
            series.append(_line(name, BAND_COLORS[name], points))
    return _output(
        "Figure 2.12",
        "c3-leaderssex",
        "Women among Presidents and Secretaries General",
        "Share of President and Secretary General answers recorded as female, among answers recorded as female or male. Closed years from 2017. These are FDRS questions, not indicator-bank totals.",
        kind="lines",
        unit="share",
        series=series,
        note="" if series else "No President or Secretary General sex answers were found on the FDRS assignments.",
    )


def _age_bars(ctx: dict[str, Any]) -> dict[str, Any]:
    year = ctx["settled_year"] if ctx["settled_year"] is not None else ctx["open_year"]
    bands = _age_summary(ctx["volunteers"].get(year, [])) if year is not None else []
    points = [{"label": item["band"], "value": item["mean_share"]} for item in bands]
    societies = bands[0]["societies"] if bands else 0
    return _output(
        "Figure 2.13",
        "c3-agedist-ns",
        "Volunteer age",
        "Each Society that reported ages is weighted equally, then the shares are averaged. At least five Societies are required."
        + (f" {year}, {societies} Societies." if bands else ""),
        kind="bars",
        unit="share",
        points=points,
        note="" if points else "Fewer than five Societies reported an age breakdown for the latest closed year.",
    )


def _reach_outputs(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _trend_figure(
            ctx,
            "Figure 3.1",
            "c3-3rresp-combined",
            "Response: Societies reporting, and people reached",
            RESPONSE,
        ),
        _trend_figure(
            ctx,
            "Figure 3.2",
            "c3-3rresil-combined",
            "Resilience: Societies reporting, and people reached",
            RESILIENCE_TREND,
        ),
        _trend_figure(
            ctx,
            "Figure 3.3",
            "c3-3rrespect-combined",
            "Respect: Societies reporting, and people reached",
            RESPECT,
        ),
        _beeswarm_figure(ctx, "Figure 3.4", "c3-reach2025-cross", "Cross-cutting reach", CROSS),
        _beeswarm_figure(ctx, "Figure 3.5", "c3-reach2025-response", "Response reach", RESPONSE),
        _beeswarm_figure(ctx, "Figure 3.6", "c3-reach2025-resilience", "Resilience reach", RESILIENCE_GROUP),
        _beeswarm_figure(ctx, "Figure 3.7", "c3-reach2025-respect", "Respect reach", RESPECT),
        _split_figure(
            ctx,
            "Figure 3.8",
            "c3-volreach-dumbbell",
            "People reached where volunteer density is higher or lower",
            "reach",
        ),
        _split_figure(
            ctx,
            "Figure 3.9",
            "c3-branchreach-dumbbell",
            "Branches where volunteer density is higher or lower",
            "branches",
        ),
        _missing(
            "Figure 3.10",
            "c3-branchreach-adj-dumbbell",
            "Branches and volunteer density, holding other factors level",
            "Multilevel model",
            "The printed figure holds volunteers, population and human development level in a multilevel model. That model is not re-estimated here. Figure 3.9 is the unadjusted comparison.",
            blocker="method",
        ),
        _treemap(ctx, "Figure 3.11", "c3-treemig", "Migration", "KPI_ReachM"),
        _treemap(ctx, "Figure 3.12", "c3-treemig-health", "Health", "KPI_ReachH"),
        _treemap(ctx, "Figure 3.13", "c3-treemig-wash", "Water, sanitation and hygiene", "KPI_ReachWASH"),
        _missing(
            "Table A.1",
            "c3-tab-reach-slopes",
            "Modelled change in people reached",
            "Multilevel model",
            "The printed table is the multilevel model’s slopes. It is not re-estimated here.",
            blocker="method",
        ),
    ]


def _trend_figure(ctx, number, output_id, title, codes) -> dict[str, Any]:
    year = _latest_positive_year(ctx, codes)
    sections = [
        {
            "kind": "lines",
            "unit": "number",
            "series": _indicator_lines(ctx, codes, 2015),
            "note": "Societies reporting a positive value, from 2015.",
        }
    ]
    if year is not None:
        sections.append(
            {
                "kind": "table",
                "columns": _income_columns(),
                "rows": _reach_cross_section(ctx, codes, year),
                "note": f"Medians and totals in {year}"
                + (" (provisional)." if year in ctx["provisional"] else "."),
            }
        )
    return _output(
        number,
        output_id,
        title,
        "The lines count Societies reporting each activity. The table is the latest year: median and total people reached, median per million people, and the median inside each income group. People-reached indicators are not added together.",
        kind="sections",
        sections=sections,
    )


def _beeswarm_figure(ctx, number, output_id, title, codes) -> dict[str, Any]:
    year = _latest_positive_year(ctx, codes)
    if year is None:
        return _output(
            number,
            output_id,
            title,
            "No Society reported a positive value for these activities.",
            kind="table",
            columns=[],
            rows=[],
            note="No Society reported a positive value for these activities.",
        )
    summary = []
    for code in codes:
        positive = _positive(_rows_for(ctx, code, year))
        if not positive:
            continue
        values = [row["value"] for row in positive]
        summary.append(
            {
                "indicator": _label(ctx, code),
                "societies": len(positive),
                "median": _median_positive(values),
                "lower": _quantile(values, 0.25),
                "upper": _quantile(values, 0.75),
                "total": float(sum(values)),
            }
        )
    people = _reach_people_rows(ctx, codes, year)
    provisional = " This year is provisional." if year in ctx["provisional"] else ""
    return _output(
        number,
        output_id,
        title,
        f"Latest year with reports: {year}.{provisional} The first table is the spread across Societies. The second lists every Society with a positive value. Long-term services and disaster response are counted in more than one group, as in the report.",
        kind="sections",
        sections=[
            {
                "kind": "table",
                "columns": [
                    {"key": "indicator", "label": "Indicator", "format": "text"},
                    {"key": "societies", "label": "Societies", "format": "number"},
                    {"key": "lower", "label": "Lower quartile", "format": "count"},
                    {"key": "median", "label": "Median", "format": "count"},
                    {"key": "upper", "label": "Upper quartile", "format": "count"},
                    {"key": "total", "label": "Total", "format": "count"},
                ],
                "rows": summary,
            },
            {
                "kind": "table",
                "columns": [
                    {"key": "society", "label": "National Society", "format": "text"},
                    {"key": "income", "label": "Income", "format": "text"},
                    {"key": "indicator", "label": "Indicator", "format": "text"},
                    {"key": "people", "label": "People reached", "format": "count"},
                ],
                "rows": people,
                "scroll": True,
            },
        ],
    )


def _split_figure(ctx, number, output_id, title, outcome: str) -> dict[str, Any]:
    year = ctx["settled_year"]
    if not ctx["has_population"]:
        return _missing(
            number,
            output_id,
            title,
            "World Bank population",
            "No World Bank population snapshot is saved, so this comparison is not calculated. The printed figure is a multilevel model; this page shows the unadjusted split only.",
        )
    if year is None:
        return _output(
            number,
            output_id,
            title,
            "Unadjusted split of Societies with higher and lower volunteer density. The printed figure is a multilevel model; this page does not re-estimate it.",
            kind="table",
            columns=[],
            rows=[],
            note="No closed volunteer year is on the panel yet.",
        )
    societies = []
    volunteer_by_iso = {row["iso3"]: row for row in ctx["volunteers"].get(year, [])}
    if outcome == "branches":
        branch_rows = {
            row["iso3"]: row["value"]
            for row in _positive(_rows_for(ctx, "KPI_noBranches", year))
        }
    else:
        branch_rows = {}
    reach_by_iso: dict[str, list[float]] = defaultdict(list)
    if outcome == "reach":
        for row in ctx["rows"]:
            if row["year"] != year or row["kpi_code"] not in REACH_FOR_SPLIT:
                continue
            if row["value"] is None or row["value"] <= 0:
                continue
            population = _pop(ctx, row["iso3"], year)
            if population:
                reach_by_iso[row["iso3"]].append(row["value"] / population * 1_000_000)
    for iso3, volunteer in volunteer_by_iso.items():
        rolling = volunteer.get("value_roll3")
        group = ctx["income"].get(iso3)
        population = _pop(ctx, iso3, year)
        if group is None or not population or not isinstance(rolling, (int, float)) or rolling <= 0:
            continue
        density = float(rolling) / population * 1_000_000
        if outcome == "reach":
            values = reach_by_iso.get(iso3) or []
            if not values:
                continue
            measure = float(median(values))
        else:
            branches = branch_rows.get(iso3)
            if not branches:
                continue
            measure = branches / population * 1_000_000
        societies.append({"group": group, "density": density, "measure": measure})
    table = []
    for group in ("L", "LM", "UM", "H"):
        members = [item for item in societies if item["group"] == group]
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda item: item["density"])
        cut = len(ordered) // 2
        lower = [item["measure"] for item in ordered[:cut]]
        higher = [item["measure"] for item in ordered[cut:]]
        table.append(
            {
                "income": INCOME_LABELS[group],
                "lower": float(median(lower)),
                "lower_n": len(lower),
                "higher": float(median(higher)),
                "higher_n": len(higher),
            }
        )
    measure_label = (
        "Median people reached per million"
        if outcome == "reach"
        else "Branches per million people"
    )
    return _output(
        number,
        output_id,
        title,
        f"Unadjusted split in {year}. Within each income group, Societies are divided in half by volunteer density. The printed figure is a multilevel model; this table does not hold population or human development level constant.",
        kind="table",
        columns=[
            {"key": "income", "label": "Income", "format": "text"},
            {"key": "lower", "label": f"{measure_label}, lower density", "format": "count"},
            {"key": "lower_n", "label": "Societies, lower", "format": "number"},
            {"key": "higher", "label": f"{measure_label}, higher density", "format": "count"},
            {"key": "higher_n", "label": "Societies, higher", "format": "number"},
        ],
        rows=table,
        note="" if table else "Not enough Societies in any income group reported the figures this split needs.",
    )


def _treemap(ctx, number, output_id, title, code) -> dict[str, Any]:
    year = _latest_positive_year(ctx, (code,))
    if year is None:
        return _output(
            number,
            output_id,
            title,
            "No Society reported a positive value.",
            kind="ranked",
            unit="count",
            rows=[],
            note="No Society reported a positive value.",
        )
    positive = _positive(_rows_for(ctx, code, year))
    used = [row for row in positive if row["iso3"] in ctx["income"]] if ctx["income"] else positive
    total = float(sum(row["value"] for row in used)) or 1.0
    ranked = []
    for row in sorted(used, key=lambda item: item["value"], reverse=True):
        group = ctx["income"].get(row["iso3"])
        ranked.append(
            {
                "name": row.get("country_name") or row["iso3"],
                "value": row["value"],
                "detail": INCOME_LABELS.get(group, ""),
                "share": row["value"] / total,
            }
        )
    provisional = " Provisional year." if year in ctx["provisional"] else ""
    return _output(
        number,
        output_id,
        f"{title}: share of people reached",
        f"Every Society with a positive {title.lower()} figure in {year}, largest first.{provisional} Societies without an income classification are left out when the snapshot has income groups.",
        kind="ranked",
        unit="count",
        rows=[{"rank": index, **item} for index, item in enumerate(ranked, start=1)],
    )


def _source(ctx: dict[str, Any], name: str) -> dict[str, Any] | None:
    payload = (ctx.get("sources") or {}).get(name)
    return payload if isinstance(payload, dict) else None


def _stamp(payload: Mapping[str, Any] | None) -> str:
    fetched = str((payload or {}).get("fetched_at") or "")[:10]
    return f" Snapshot {fetched}." if fetched else ""


def _operations_outputs(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    go = _source(ctx, "go")
    appeals = list((go or {}).get("appeals") or [])
    if not appeals:
        detail = (
            "These charts use the public IFRC GO register of Emergency Appeals and DREF operations "
            "(https://goadmin.ifrc.org/api/v2/appeal/). A snapshot has not been saved."
        )
        return [
            _missing("Figure 3.14", "c4-polycrisis-mix", "Operations by kind of hazard", "IFRC GO", detail),
            _missing("Figure 3.15", "c4-polycrisis-share", "Share of each income group facing four or more kinds of crisis", "IFRC GO", detail),
            _missing("Table 3.1", "c4-tab-polycrisis-who", "National Societies facing the widest range of crises", "IFRC GO", detail),
        ]
    mix = operation_mix(appeals)
    societies = {row["iso3"] for row in ctx["rows"]}
    stressed = stressed_by_income(appeals, ctx["income"], societies)
    who = widest_crises(appeals, ctx["income"], ctx["names"])
    return [
        _output(
            "Figure 3.14",
            "c4-polycrisis-mix",
            "Operations by kind of hazard",
            "Each bar is the Emergency Appeals and DREF operations launched that year. 2026 is left out because the year is still partial."
            + _stamp(go),
            kind="stacked",
            unit="share",
            segments=[
                {"name": name, "color": color}
                for name, color in zip(
                    HAZARD_GROUPS,
                    ("#1e3a5f", "#e11b22", "#c2410c", "#7c3aed", "#0f766e", "#9ca3af"),
                )
            ],
            rows=[{"category": str(item["year"]), "n": item["n"], "counts": item["counts"]} for item in mix if item["n"]],
        ),
        _output(
            "Figure 3.15",
            "c4-polycrisis-share",
            "Share of each income group facing four or more kinds of crisis",
            "A Society counts in a year when its Emergency Appeals and DREF operations over the previous five years cover at least four disaster types. The share uses the National Societies in that income group in this FDRS panel."
            + _stamp(go),
            kind="lines",
            unit="share",
            series=[
                _line(INCOME_LABELS[item["group"]], INCOME_COLORS[item["group"]], item["points"])
                for item in stressed
                if item["group"] in INCOME_LABELS
            ],
            note="" if stressed else "No National Society on the volunteer panel falls in an income group, so the share is not calculated.",
        ),
        _output(
            "Table 3.1",
            "c4-tab-polycrisis-who",
            "National Societies facing the widest range of crises",
            "Distinct Emergency Appeal and DREF disaster types over the five years to 2025, ten highest."
            + _stamp(go),
            kind="table",
            columns=[
                {"key": "society", "label": "National Society", "format": "text"},
                {"key": "income", "label": "Income", "format": "text"},
                {"key": "types", "label": "Different crisis types", "format": "number"},
            ],
            rows=[{**row, "income": INCOME_LABELS.get(row["income"], row["income"] or "")} for row in who],
        ),
    ]


def _capacity_outputs(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _ocac_bands(ctx),
        _missing(
            "Figure 4.2",
            "c6-eng-model",
            "What keeps volunteers engaged",
            "Motiro survey",
            "This figure is a model of a volunteer survey. Individual responses are not stored in the databank, so the model is not re-estimated.",
            blocker="withheld",
        ),
    ]


def _value_outputs(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    calculated = _volunteer_value(ctx)
    if calculated is not None:
        return calculated
    wages = _source(ctx, "wages")
    hours = _source(ctx, "hours")
    if (wages or {}).get("rows") and (hours or {}).get("rows"):
        note = (
            "ILO wages and the Americas hours study are saved. "
            "No Society has a three-year volunteer mean for 2020–2024, so the value is not calculated."
        )
        return [
            _output(
                "Figure 5.1",
                "c5-volvalglobalbasis",
                "Value of volunteer time",
                note + _stamp(wages),
                kind="bars",
                unit="ratio",
                points=[],
                note=note,
            ),
            _output(
                "Table 5.1",
                "c5-tab-volvalamericas",
                "Value of volunteer time in three Americas Societies",
                note,
                kind="table",
                columns=[],
                rows=[],
                note=note,
            ),
            _output(
                "Table 5.2",
                "c5-tab-volvalamericastot",
                "Americas total",
                note,
                kind="table",
                columns=[],
                rows=[],
                note=note,
            ),
            _output(
                "Table 5.3",
                "c5-tab-volvalglobaltot",
                "Global total",
                note,
                kind="table",
                columns=[],
                rows=[],
                note=note,
            ),
        ]
    detail = (
        "Valuing volunteer time uses ILOSTAT wages (https://rplumber.ilo.org) and the Americas volunteer-hours study. "
        "Those snapshots have not been saved."
    )
    return [
        _missing("Figure 5.1", "c5-volvalglobalbasis", "Value of volunteer time", "ILO wages", detail),
        _missing("Table 5.1", "c5-tab-volvalamericas", "Value of volunteer time in the Americas", "ILO wages", detail),
        _missing("Table 5.2", "c5-tab-volvalamericastot", "Americas total", "ILO wages", detail),
        _missing("Table 5.3", "c5-tab-volvalglobaltot", "Global total", "ILO wages", detail),
    ]


def _protection_outputs(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _awsd_trend(ctx),
        *_death_register_outputs(ctx),
        _insurance_status(ctx),
        _insurance_coverage(ctx),
        _deaths_on_duty(ctx),
    ]


def _insurance_pairs(ctx: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    insured = {
        (row["iso3"], row["year"]): row
        for row in ctx["rows"]
        if row["kpi_code"] == "KPI_noVolCoveredAI"
    }
    pairs = {}
    for row in ctx["rows"]:
        if row["kpi_code"] != VOLUNTEER_CODE or row["value"] is None or row["value"] <= 0:
            continue
        cover = insured.get((row["iso3"], row["year"]))
        if cover is None or cover.get("value") is None:
            status = "Did not report"
            coverage = None
        elif cover["value"] > 0:
            status = "Insured"
            coverage = min(cover["value"] / row["value"], 1.0)
        else:
            status = "Reported none"
            coverage = 0.0
        pairs[(row["iso3"], row["year"])] = {
            "year": row["year"],
            "iso3": row["iso3"],
            "status": status,
            "coverage": coverage,
            "imp_fill": bool(row.get("imp_fill")),
        }
    return pairs


def _insurance_status(ctx: dict[str, Any]) -> dict[str, Any]:
    counts: dict[int, dict[str, int]] = defaultdict(lambda: {name: 0 for name, _color in INSURANCE_SEGMENTS})
    for item in _insurance_pairs(ctx).values():
        counts[item["year"]][item["status"]] += 1
    rows = []
    for year in sorted(counts):
        total = sum(counts[year].values())
        if not total:
            continue
        rows.append({"category": str(year), "n": total, "counts": dict(counts[year])})
    return _output(
        "Figure 6.5",
        "c6-insurance",
        "Accident insurance among Societies with volunteers",
        "A Society is insured when it reports any volunteers covered by accident insurance, and as reporting none when that figure is zero. Otherwise it did not report. Only Societies with volunteers above zero are included.",
        kind="stacked",
        unit="share",
        segments=[{"name": name, "color": color} for name, color in INSURANCE_SEGMENTS],
        rows=rows,
        note="" if rows else "No Society reported volunteers.",
    )


def _insurance_coverage(ctx: dict[str, Any]) -> dict[str, Any]:
    buckets: dict[tuple[int, str], list[float]] = defaultdict(list)
    for item in _insurance_pairs(ctx).values():
        if item["imp_fill"] or item["coverage"] is None:
            continue
        group = ctx["income"].get(item["iso3"])
        if not group:
            continue
        buckets[(item["year"], group)].append(item["coverage"])
    series = []
    for group in ("L", "LM", "UM", "H"):
        years = sorted({year for year, item_group in buckets if item_group == group})
        points = [
            _point(year, float(sum(buckets[(year, group)]) / len(buckets[(year, group)])))
            for year in years
        ]
        if points:
            series.append(_line(INCOME_LABELS[group], INCOME_COLORS[group], points))
    note = ""
    if not ctx["income"]:
        note = "Income groups need the World Bank snapshot."
    elif not series:
        note = "No Society reported both volunteers and insurance cover, outside imputed fills."
    return _output(
        "Figure 6.6",
        "c6-insurancetrend",
        "Share of volunteers covered by accident insurance",
        "Mean, within each income group, of insured volunteers divided by volunteers, capped at 100%. Imputed volunteer fills are left out. Societies that did not report insurance are left out.",
        kind="lines",
        unit="share",
        series=series,
        note=note,
    )


def _deaths_on_duty(ctx: dict[str, Any]) -> dict[str, Any]:
    series = []
    for index, (code, name) in enumerate(
        (("KPI_noVolDeathsDuty", "Volunteers"), ("KPI_PStaffDeathsDuty", "Paid staff"))
    ):
        grouped = _year_rows(ctx["rows"], code)
        points = []
        for year in sorted(grouped):
            reported = [row for row in grouped[year] if row["value"] is not None]
            if not reported:
                continue
            points.append(_point(year, float(sum(row["value"] for row in reported)), year in ctx["provisional"]))
        if points:
            series.append(_line(name, SERIES_COLORS[index], points))
    return _output(
        "FDRS",
        "fdrs-deaths-duty",
        "Deaths on duty reported to FDRS",
        "Sum of the deaths-on-duty indicators on FDRS assignments. This is not Figures 6.2 to 6.4, which use the security-unit register.",
        kind="lines",
        unit="count",
        series=series,
        note="" if series else "No Society reported deaths on duty.",
    )


def _giving_outputs(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    wgi = _source(ctx, "wgi")
    if not wgi or not wgi.get("rows"):
        return [
            _missing(
                "Figure 1.1",
                "c2-wgi-income",
                "World Giving Index by income group",
                "World Giving Index",
                "The Charities Aid Foundation World Giving Index country files have not been saved.",
            )
        ]
    sections = []
    for metric, title in (
        ("helping", "Helping a stranger"),
        ("donating", "Donating money"),
        ("volunteering", "Volunteering time"),
    ):
        buckets: dict[tuple[int, str], list[float]] = defaultdict(list)
        for row in wgi.get("rows") or []:
            value = row.get(metric)
            year = row.get("year")
            group = ctx["income"].get(row.get("iso3"))
            if isinstance(value, (int, float)) and isinstance(year, int) and group:
                buckets[(year, group)].append(float(value))
        series = []
        for group in ("L", "LM", "UM", "H"):
            years = sorted(year for year, item_group in buckets if item_group == group)
            points = [
                _point(year, sum(buckets[(year, group)]) / len(buckets[(year, group)]) / 100)
                for year in years
            ]
            if points:
                series.append(_line(INCOME_LABELS[group], INCOME_COLORS[group], points))
        sections.append({"kind": "lines", "unit": "share", "series": series, "note": title})
    return [
        _output(
            "Figure 1.1",
            "c2-wgi-income",
            "World Giving Index by income group",
            "Each line is the unweighted mean of country scores in that income group. The score is the share of adults who said they did that thing in the past month. It covers all volunteering and giving, not only Red Cross and Red Crescent activity. Survey years run from 2010 to 2018 and 2021 to 2022."
            + _stamp(wgi),
            kind="sections",
            sections=sections,
        )
    ]


def _giving_comparison(ctx: dict[str, Any]) -> dict[str, Any]:
    wgi = _source(ctx, "wgi")
    rows = list((wgi or {}).get("rows") or [])
    if not rows or not ctx["has_population"]:
        return _missing(
            "Figure 2.6",
            "c3-volsperpop-wgi",
            "Volunteer density and the World Giving Index",
            "World Giving Index",
            "The World Giving Index volunteering-time series has not been saved, or population is missing, so this comparison is not calculated.",
        )
    density: dict[tuple[str, int], float] = {}
    for row in ctx["rows"]:
        if row.get("kpi_code") != VOLUNTEER_CODE:
            continue
        rolling = row.get("value_roll3")
        year = row.get("year")
        if not isinstance(year, int) or not isinstance(rolling, (int, float)) or rolling <= 0:
            continue
        population = _pop(ctx, row["iso3"], year)
        if population:
            density[(row["iso3"], year)] = float(rolling) / population * 1_000_000
    giving = {
        (item.get("iso3"), item.get("year")): item.get("volunteering")
        for item in rows
        if isinstance(item.get("volunteering"), (int, float))
    }
    matched = {iso3 for iso3, _year in density} & {iso3 for iso3, _year in giving if iso3}
    sections = []
    for group in ("L", "LM", "UM", "H"):
        fdrs_points = []
        wgi_points = []
        for year in range(2010, 2025):
            fdrs_values = [
                density[(iso3, year)]
                for iso3 in matched
                if ctx["income"].get(iso3) == group and (iso3, year) in density
            ]
            wgi_values = [
                float(giving[(iso3, year)])
                for iso3 in matched
                if ctx["income"].get(iso3) == group and isinstance(giving.get((iso3, year)), (int, float))
            ]
            if fdrs_values:
                fdrs_points.append((year, float(median(fdrs_values)), len(fdrs_values)))
            if wgi_values:
                wgi_points.append((year, float(median(wgi_values)), len(wgi_values)))
        series = []
        for name, color, points, smooth in (
            ("IFRC network volunteers", "#e11b22", fdrs_points, False),
            ("General public, World Giving Index", "#1e3a5f", wgi_points, True),
        ):
            if not points:
                continue
            raw = [value for _year, value, _count in points]
            smoothed = centred_smooth(raw) if smooth else raw
            base = next((value for (year, _raw, _count), value in zip(points, smoothed) if year == 2016), None)
            if not base:
                base = smoothed[0]
            indexed = index_to_base(smoothed, base)
            drawn = []
            ends = {points[0][0], points[-1][0]}
            for (year, _raw, count), value in zip(points, indexed):
                if value is None or year < 2016 or year > 2024:
                    continue
                drawn.append(_point(year, value, dashed=count < 10 or (smooth and year in ends)))
            if drawn:
                series.append(_line(name, color, drawn))
        if series:
            sections.append({"kind": "lines", "unit": "number", "series": series, "note": INCOME_LABELS[group] + ". 2016 = 100."})
    return _output(
        "Figure 2.6",
        "c3-volsperpop-wgi",
        "IFRC volunteering and the World Giving Index, indexed to 2016",
        "Each line is the median for one income group, set to 100 in 2016. Red is IFRC volunteers per million people. Blue is the share of adults who say they gave time, smoothed over three survey years. A hollow point marks fewer than 10 matched countries, or a partial smooth at either end of the Giving Index."
        + _stamp(wgi)
        + f" {len(matched)} countries are in both sources.",
        kind="sections",
        sections=sections,
        note="" if sections else "No country is in both the volunteer panel and the Giving Index.",
    )


def _age_gap(ctx: dict[str, Any]) -> dict[str, Any]:
    ages = _source(ctx, "median_age")
    population_rows = list((ages or {}).get("rows") or [])
    if not population_rows:
        return _missing(
            "Figure 2.14",
            "c3-volage-bar-pop-4inc",
            "Volunteer age against the population’s median age",
            "World Bank population by age",
            "Median age, from World Bank population by age band, has not been saved.",
        )
    population = {
        (row.get("iso3"), row.get("year")): row.get("median_age")
        for row in population_rows
        if isinstance(row.get("median_age"), (int, float))
    }
    volunteer_values: dict[str, list[float]] = defaultdict(list)
    for row in ctx["rows"]:
        if row.get("kpi_code") != VOLUNTEER_CODE or not isinstance(row.get("year"), int):
            continue
        if row["year"] < 2020 or row["year"] > 2024:
            continue
        age = interpolate_median_age(row.get("age_bands") or {}, VOLUNTEER_AGE_BANDS)
        if age is not None:
            volunteer_values[row["iso3"]].append(age)
    table = []
    for group in ("L", "LM", "UM", "H"):
        volunteer_means = []
        population_means = []
        for iso3, values in volunteer_values.items():
            if ctx["income"].get(iso3) != group:
                continue
            volunteer_means.append(sum(values) / len(values))
            pop_values = [
                population[(iso3, year)]
                for year in range(2020, 2025)
                if isinstance(population.get((iso3, year)), (int, float))
            ]
            if pop_values:
                population_means.append(sum(pop_values) / len(pop_values))
        if not volunteer_means:
            continue
        table.append(
            {
                "income": INCOME_LABELS[group],
                "volunteer_mean": sum(volunteer_means) / len(volunteer_means),
                "volunteer_median": float(median(volunteer_means)),
                "population_mean": (sum(population_means) / len(population_means)) if population_means else None,
                "societies": len(volunteer_means),
            }
        )
    return _output(
        "Figure 2.14",
        "c3-volage-bar-pop-4inc",
        "Volunteer age and the population’s median age, 2020–2024",
        "Volunteer age is interpolated inside the FDRS age groups 5–17, 18–49 and 50+, averaged over 2020–2024 for each Society, then summarised within the income group. Population age uses the same countries and the World Bank age-band median."
        + _stamp(ages),
        kind="table",
        columns=[
            {"key": "income", "label": "Income", "format": "text"},
            {"key": "volunteer_mean", "label": "Volunteers, mean age", "format": "ratio"},
            {"key": "volunteer_median", "label": "Volunteers, median age", "format": "ratio"},
            {"key": "population_mean", "label": "Population, mean of median age", "format": "ratio"},
            {"key": "societies", "label": "Societies", "format": "number"},
        ],
        rows=table,
        note=""
        if table
        else "Fewer than three of the age groups 5–17, 18–49 and 50+ were reported, so a volunteer median age could not be interpolated.",
    )


def _ocac_bands(ctx: dict[str, Any]) -> dict[str, Any]:
    ocac = _source(ctx, "ocac")
    scores = {row.get("iso3"): row.get("volmgmt") for row in (ocac or {}).get("rows") or []}
    if not scores or not ctx["has_population"]:
        return _missing(
            "Figure 4.1",
            "c4-vpm-ocac-bands",
            "Volunteer density and OCAC assessment bands",
            "OCAC",
            "The OCAC baseline volunteer-management scores have not been saved. Individual attribute ratings are not shown.",
        )
    densities: dict[str, list[float]] = defaultdict(list)
    for row in ctx["rows"]:
        if row.get("kpi_code") != VOLUNTEER_CODE:
            continue
        rolling = row.get("value_roll3")
        if not isinstance(rolling, (int, float)) or rolling <= 0 or not isinstance(row.get("year"), int):
            continue
        population = _pop(ctx, row["iso3"], row["year"])
        if population:
            densities[row["iso3"]].append(float(rolling) / population * 1_000_000)
    bands = {"Below C": [], "C or above": []}
    for iso3, values in densities.items():
        score = scores.get(iso3)
        if not isinstance(score, (int, float)):
            continue
        summary = geometric_mean(values)
        if summary is None:
            continue
        band = "C or above" if round(float(score)) >= 3 else "Below C"
        bands[band].append(summary)
    rows = []
    for name in ("Below C", "C or above"):
        if bands[name]:
            rows.append({"label": name, "value": sum(bands[name]) / len(bands[name]), "n": len(bands[name])})
    return _output(
        "Figure 4.1",
        "c4-vpm-ocac-bands",
        "Volunteer density by OCAC volunteer-management band",
        "Each bar is the average volunteer density of Societies in that band. The score is the mean of the baseline ratings for volunteer recruitment and retention and for volunteering strategy and policy. C or above is a rounded score of 3 or more on the A-to-E scale. Individual Society ratings are not listed."
        + _stamp(ocac),
        kind="bars",
        unit="per_million",
        points=[{"label": f"{item['label']} (N={item['n']})", "value": item["value"]} for item in rows],
        note="" if rows else "No Society has both an OCAC baseline score and a volunteer density.",
    )


def _latest_roll(ctx: dict[str, Any]) -> dict[str, dict[str, Any]]:
    chosen: dict[str, dict[str, Any]] = {}
    for row in ctx["rows"]:
        if row.get("kpi_code") != VOLUNTEER_CODE or not isinstance(row.get("year"), int):
            continue
        if row["year"] < 2020 or row["year"] > 2024:
            continue
        rolling = row.get("value_roll3")
        if not isinstance(rolling, (int, float)) or rolling <= 0:
            continue
        current = chosen.get(row["iso3"])
        if current is None or row["year"] > current["year"]:
            chosen[row["iso3"]] = {
                "iso3": row["iso3"],
                "year": row["year"],
                "volunteers": float(rolling),
                "country": row.get("country_name") or row["iso3"],
                "income": ctx["income"].get(row["iso3"]),
            }
    return chosen


def _volunteer_value(ctx: dict[str, Any]) -> list[dict[str, Any]] | None:
    wages = _source(ctx, "wages")
    hours = _source(ctx, "hours")
    wage_rows = list((wages or {}).get("rows") or [])
    hour_rows = list((hours or {}).get("rows") or [])
    if not wage_rows or not hour_rows:
        return None
    wage_by_iso = {row.get("iso3"): row for row in wage_rows}
    volunteers = _latest_roll(ctx)
    americas = []
    for row in hour_rows:
        iso3 = row.get("iso3")
        volunteer = volunteers.get(iso3)
        wage = wage_by_iso.get(iso3)
        hours_mid = row.get("hours_mid")
        if not volunteer or not wage or not isinstance(hours_mid, (int, float)):
            continue
        americas.append(
            {
                "iso3": iso3,
                "country": row.get("country") or volunteer["country"],
                "volunteers": volunteer["volunteers"],
                "year": volunteer["year"],
                "hours_bin": row.get("hours_bin") or "",
                "hours_year": float(hours_mid) * 12,
                "wage": wage,
            }
        )
    if not americas:
        return None
    hours_central = sum(item["hours_year"] for item in americas) / len(americas)
    bases = []
    for key, label in WAGE_BASES:
        total = 0.0
        societies = 0
        for volunteer in volunteers.values():
            wage = wage_by_iso.get(volunteer["iso3"])
            rate = hourly_wage((wage or {}).get(key))
            if rate is None:
                continue
            total += volunteer["volunteers"] * hours_central * rate
            societies += 1
        if societies:
            bases.append({"basis": label, "value_bn": total / 1e9, "societies": societies})
    americas_totals = []
    for key, label in WAGE_BASES:
        total = 0.0
        for item in americas:
            rate = hourly_wage(item["wage"].get(key))
            if rate is None:
                continue
            total += item["volunteers"] * item["hours_year"] * rate
        americas_totals.append({"basis": label, "value_m": total / 1e6})
    examples = []
    for iso3 in ("USA", "GTM", "SUR"):
        item = next((row for row in americas if row["iso3"] == iso3), None)
        if item is None:
            continue
        example = {
            "country": item["country"],
            "year": item["year"],
            "volunteers": item["volunteers"],
            "hours": item["hours_bin"],
        }
        for key, label in WAGE_BASES:
            rate = hourly_wage(item["wage"].get(key))
            example[key] = None if rate is None else item["volunteers"] * item["hours_year"] * rate / 1e6
        examples.append(example)
    stamp = _stamp(wages)
    return [
        _output(
            "Figure 5.1",
            "c5-volvalglobalbasis",
            "Value of volunteer time",
            "Each bar is the network total. A Society’s volunteers (three-year mean, latest window in 2020–2024) are multiplied by the average annual hours reported in the Americas study, then by that country’s hourly wage. Monthly wages are turned into hourly rates with 2,000 paid hours a year. Gaps in ILOSTAT are filled from GNI and marked in the snapshot."
            + stamp,
            kind="bars",
            unit="ratio",
            points=[{"label": item["basis"], "value": item["value_bn"]} for item in bases],
            note="Values are billions of dollars a year.",
        ),
        _output(
            "Table 5.1",
            "c5-tab-volvalamericas",
            "Value of volunteer time in three Americas Societies",
            "United States, Guatemala and Suriname, where the hours study and a wage are both available. Values are millions of dollars a year, using each Society’s own reported hours."
            + stamp,
            kind="table",
            columns=[
                {"key": "country", "label": "National Society", "format": "text"},
                {"key": "year", "label": "Window", "format": "number"},
                {"key": "volunteers", "label": "Volunteers", "format": "count"},
                {"key": "hours", "label": "Hours a month", "format": "text"},
                {"key": "min_usd", "label": "Min. wage, USD m", "format": "ratio"},
                {"key": "mean_usd", "label": "Average wage, USD m", "format": "ratio"},
                {"key": "min_ppp", "label": "Min. wage, PPP m", "format": "ratio"},
                {"key": "mean_ppp", "label": "Average wage, PPP m", "format": "ratio"},
            ],
            rows=examples,
        ),
        _output(
            "Table 5.2",
            "c5-tab-volvalamericastot",
            "Americas total",
            f"Aggregate across the {len(americas)} Americas Societies with both an hours band and a wage. Values are millions of dollars a year.",
            kind="table",
            columns=[
                {"key": "basis", "label": "Wage basis", "format": "text"},
                {"key": "value_m", "label": "Value, USD million a year", "format": "count"},
            ],
            rows=americas_totals,
        ),
        _output(
            "Table 5.3",
            "c5-tab-volvalglobaltot",
            "Global total",
            "The same four wage bases, for every Society with a three-year volunteer mean and a wage. Values are billions of dollars a year. Hours are the Americas average, applied to every Society.",
            kind="table",
            columns=[
                {"key": "basis", "label": "Wage basis", "format": "text"},
                {"key": "value_bn", "label": "Value, USD billion a year", "format": "ratio"},
                {"key": "societies", "label": "Societies", "format": "number"},
            ],
            rows=bases,
        ),
    ]


def _awsd_trend(ctx: dict[str, Any]) -> dict[str, Any]:
    awsd = _source(ctx, "awsd")
    rows = [row for row in (awsd or {}).get("rows") or [] if isinstance(row.get("year"), int) and 2016 <= row["year"] <= 2025]
    if not rows:
        return _missing(
            "Figure 6.1",
            "c6-awsdtrend",
            "Aid workers killed",
            "Aid Worker Security Database",
            "The Humanitarian Outcomes Aid Worker Security Database extract has not been saved. Only yearly totals are stored, not incident narratives.",
        )
    counts: dict[int, dict[str, int]] = defaultdict(lambda: {"Movement": 0, "Other aid workers": 0})
    for row in rows:
        group = "Movement" if row.get("group") == "movement" else "Other aid workers"
        counts[row["year"]][group] += int(row.get("killed") or 0)
    return _output(
        "Figure 6.1",
        "c6-awsdtrend",
        "Aid workers killed",
        "Each bar splits aid workers killed in recorded security incidents. Movement is ICRC plus National Society and IFRC personnel. This is not comparable with the all-cause deaths Societies report to FDRS. 2026 is left out."
        + _stamp(awsd),
        kind="stacked",
        unit="share",
        segments=[
            {"name": "Movement", "color": "#e11b22"},
            {"name": "Other aid workers", "color": "#1e3a5f"},
        ],
        rows=[
            {"category": str(year), "n": sum(counts[year].values()), "counts": dict(counts[year])}
            for year in sorted(counts)
        ],
    )


def _death_register_outputs(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    deaths = _source(ctx, "deaths")
    rows = [row for row in (deaths or {}).get("rows") or [] if isinstance(row.get("year"), int)]
    if not rows:
        detail = (
            "These charts use counts from the IFRC security-unit register. "
            "Names are not copied into the databank. The aggregate snapshot has not been saved."
        )
        return [
            _missing("Figure 6.2", "c6-deathsmech", "How people were killed", "Security-unit register", detail),
            _missing("Figure 6.3", "c6-deathsources", "Who recorded the deaths", "Security-unit register", detail),
            _missing("Figure 6.4", "c6-deathsmechera", "Deaths by mechanism and period", "Security-unit register", detail),
        ]
    mechanisms: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        if row["year"] < 2016 or row["year"] > 2025:
            continue
        mechanisms[(row.get("mechanism") or "Unknown", row.get("cause") or "Unknown")] += int(row.get("killed") or 0)
    ranked = sorted(mechanisms.items(), key=lambda item: item[1], reverse=True)
    by_source: dict[tuple[int, str, str], int] = defaultdict(int)
    for row in rows:
        if row["year"] < 2016 or row["year"] > 2025:
            continue
        role = row.get("role") if row.get("role") in {"Staff", "Volunteer"} else "Mixed / unknown"
        by_source[(row["year"], role, "register")] += int(row.get("killed") or 0)
    for row in ctx["rows"]:
        if row.get("kpi_code") not in {"KPI_noVolDeathsDuty", "KPI_PStaffDeathsDuty"}:
            continue
        if not isinstance(row.get("year"), int) or row["year"] < 2016 or row["value"] is None:
            continue
        role = "Volunteer" if row["kpi_code"] == "KPI_noVolDeathsDuty" else "Staff"
        by_source[(row["year"], role, "fdrs")] += int(row["value"])
    comparison = []
    for year in range(2016, 2026):
        comparison.append(
            {
                "year": year,
                "register": sum(value for (item_year, _role, source), value in by_source.items() if item_year == year and source == "register"),
                "fdrs": sum(value for (item_year, _role, source), value in by_source.items() if item_year == year and source == "fdrs"),
            }
        )
    eras = []
    for role in ("Volunteer", "Staff"):
        for label, start, end in (("2016 to 2019", 2016, 2019), ("2020 to 2025", 2020, 2025)):
            counts = {"Violence": 0, "Accident": 0, "Unknown": 0}
            for row in rows:
                if row.get("role") != role or not start <= row["year"] <= end:
                    continue
                cause = row.get("cause") if row.get("cause") in counts else "Unknown"
                counts[cause] += int(row.get("killed") or 0)
            eras.append({"category": f"{role}, {label}", "n": sum(counts.values()), "counts": counts})
    stamp = _stamp(deaths)
    return [
        _output(
            "Figure 6.2",
            "c6-deathsmech",
            "How people were killed",
            "Counts from the security-unit register, 2016 to 2025. The free-text mechanism is grouped. Names are not stored."
            + stamp,
            kind="ranked",
            unit="count",
            rows=[
                {"rank": index, "name": name, "value": killed, "detail": cause}
                for index, ((name, cause), killed) in enumerate(ranked, start=1)
                if killed
            ],
        ),
        _output(
            "Figure 6.3",
            "c6-deathsources",
            "Deaths recorded by FDRS and by the security unit",
            "FDRS is the all-cause deaths-on-duty total reported by National Societies. The register is the security-unit count of people killed. The two are not the same measurement."
            + stamp,
            kind="table",
            columns=[
                {"key": "year", "label": "Year", "format": "number"},
                {"key": "register", "label": "Security-unit register", "format": "number"},
                {"key": "fdrs", "label": "FDRS deaths on duty", "format": "number"},
            ],
            rows=comparison,
        ),
        _output(
            "Figure 6.4",
            "c6-deathsmechera",
            "Violence and accidents, by role and period",
            "Share of people killed in the register, for staff and volunteers separately. Mixed or unknown roles are left out of this split."
            + stamp,
            kind="stacked",
            unit="share",
            segments=[
                {"name": "Violence", "color": "#e11b22"},
                {"name": "Accident", "color": "#1e3a5f"},
                {"name": "Unknown", "color": "#9ca3af"},
            ],
            rows=[item for item in eras if item["n"]],
        ),
    ]


def _check_outputs(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    year_rows = []
    for year in sorted(ctx["volunteers"]):
        volunteer_rows = ctx["volunteers"][year]
        positive = _positive(volunteer_rows)
        if not positive and not any(row.get("value_roll3") for row in volunteer_rows):
            continue
        reported = [row for row in positive if not row.get("imputed")]
        rolling = [
            row["value_roll3"]
            for row in volunteer_rows
            if row.get("value_roll3") is not None and row["value_roll3"] > 0
        ]
        staff = _rows_for(ctx, STAFF_CODE, year)
        female, female_n = _female_share(volunteer_rows)
        year_rows.append(
            {
                "year": f"{year} provisional" if year in ctx["provisional"] else str(year),
                "rolling": float(sum(rolling)) if rolling else None,
                "societies_rolling": len(rolling),
                "societies_reporting": len(reported),
                "staff": _sum_positive(staff),
                "women": female,
                "women_n": female_n,
            }
        )
    snapshot_year = ctx["settled_year"] if ctx["settled_year"] is not None else ctx["open_year"]
    regions = _region_summary(ctx["volunteers"].get(snapshot_year, [])) if snapshot_year is not None else []
    extreme = [
        {
            "society": row.get("country_name") or row["iso3"],
            "year": row["year"],
            "indicator": row.get("label") or row["kpi_code"],
            "people": row["value"],
            "share": row.get("extreme_share"),
        }
        for row in ctx["rows"]
        if row.get("flag_extreme_share")
    ]
    extreme.sort(key=lambda item: item["share"] or 0, reverse=True)
    duplicate = sum(1 for row in ctx["rows"] if row.get("flag_duplicate_within_ns"))
    covid = sum(1 for row in ctx["rows"] if row.get("flag_covid_year"))
    return [
        _output(
            "Data checks",
            "ecr-year-table",
            "Year by year",
            "Volunteer totals use the three-year mean. Societies reporting excludes imputed values.",
            kind="table",
            columns=[
                {"key": "year", "label": "Year", "format": "text"},
                {"key": "rolling", "label": "Volunteers, 3-year mean", "format": "count"},
                {"key": "societies_rolling", "label": "Societies in that total", "format": "number"},
                {"key": "societies_reporting", "label": "Societies reporting", "format": "number"},
                {"key": "women", "label": "Median share women", "format": "share"},
                {"key": "staff", "label": "Paid staff", "format": "count"},
            ],
            rows=year_rows,
            scroll=True,
        ),
        _output(
            "Data checks",
            "ecr-regions",
            "Volunteers by region",
            f"Three-year means in {snapshot_year}." if snapshot_year else "No volunteer year is available.",
            kind="table",
            columns=[
                {"key": "region", "label": "Region", "format": "text"},
                {"key": "volunteers_rolling", "label": "Volunteers, 3-year mean", "format": "count"},
                {"key": "societies", "label": "Societies", "format": "number"},
            ],
            rows=regions,
        ),
        _output(
            "Data checks",
            "ecr-flags",
            "Sanity flags",
            "A duplicate is the same rounded value on three or more indicators in one Society-year. An extreme share is at least 40% of an indicator’s total in a year when two or more Societies reported it. COVID flags are 2020 values for disaster response, health, and mental health and psychosocial support.",
            kind="table",
            columns=[
                {"key": "check", "label": "Check", "format": "text"},
                {"key": "cells", "label": "Cells", "format": "number"},
            ],
            rows=[
                {"check": "Same number on three or more indicators", "cells": duplicate},
                {"check": "At least 40% of that indicator’s total", "cells": len(extreme)},
                {"check": "2020 people-reached cells flagged for COVID-19 tabulation", "cells": covid},
            ],
        ),
        _output(
            "Data checks",
            "ecr-extreme",
            "Cells that dominate a total",
            "Listed only when at least two Societies reported that indicator in that year.",
            kind="table",
            columns=[
                {"key": "society", "label": "National Society", "format": "text"},
                {"key": "year", "label": "Year", "format": "number"},
                {"key": "indicator", "label": "Indicator", "format": "text"},
                {"key": "people", "label": "Value", "format": "count"},
                {"key": "share", "label": "Share of the total", "format": "share"},
            ],
            rows=extreme,
            scroll=True,
            note="" if extreme else "No cell is 40% or more of a total that several Societies reported.",
        ),
    ]


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * probability
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return float(ordered[low] * (1 - weight) + ordered[high] * weight)


def _year_span(years: list[int]) -> str:
    if not years:
        return ""
    if len(years) == 1:
        return str(years[0])
    return f"{years[0]}–{years[-1]}"
