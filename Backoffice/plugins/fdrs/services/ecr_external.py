"""Saved external series for Everyone Counts figures.

Each snapshot is a JSON file under the FDRS snapshot directory. The page
reads those files. Fetching happens in the snapshot build, not on the
page request. Motiro survey rows and the named deaths register are not
stored; the deaths snapshot keeps counts only.
"""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import median
from typing import Any, Mapping

from plugins.fdrs.services.external_snapshots import load_snapshot

GO_NAME = "go_appeals"
WGI_NAME = "world_giving_index"
MEDIAN_AGE_NAME = "wb_median_age"
AWSD_NAME = "awsd_killed"
DEATHS_NAME = "rcrc_deaths_aggregate"
OCAC_NAME = "ocac_volunteer_management"
WAGES_NAME = "ilo_wages"
HOURS_NAME = "americas_volunteer_hours"

HAZARD_GROUPS = (
    "Climate and weather",
    "Epidemic",
    "Conflict and displacement",
    "Geophysical",
    "Food insecurity",
    "Other",
)
_CLIMATE = {
    "Flood",
    "Pluvial/Flash Flood",
    "Cyclone",
    "Drought",
    "Heat Wave",
    "Cold Wave",
    "Storm Surge",
    "Landslide",
    "Storm",
}
_CONFLICT = {"Population Movement", "Civil Unrest", "Complex Emergency"}
_GEO = {"Earthquake", "Volcanic Eruption", "Tsunami"}
VIOLENCE_MECHANISMS = (
    "Small arms fire",
    "Indirect fire / blast",
    "Drone strike",
    "Aerial bombardment / airstrike",
    "Bladed weapon / assault",
)
VOLUNTEER_AGE_BANDS = (
    ("6_12", 6, 7),
    ("13_17", 13, 5),
    ("18_29", 18, 12),
    ("30_39", 30, 10),
    ("40_49", 40, 10),
    ("50_59", 50, 10),
    ("60_69", 60, 10),
    ("70_79", 70, 10),
    ("80", 80, 10),
)
ANNUAL_PAID_HOURS = 2000
WAGE_BASES = (
    ("min_usd", "Minimum wage, US dollars"),
    ("mean_usd", "Average wage, US dollars"),
    ("min_ppp", "Minimum wage, PPP dollars"),
    ("mean_ppp", "Average wage, PPP dollars"),
)


def load_sources() -> dict[str, dict[str, Any] | None]:
    return {
        "go": load_snapshot(GO_NAME),
        "wgi": load_snapshot(WGI_NAME),
        "median_age": load_snapshot(MEDIAN_AGE_NAME),
        "awsd": load_snapshot(AWSD_NAME),
        "deaths": load_snapshot(DEATHS_NAME),
        "ocac": load_snapshot(OCAC_NAME),
        "wages": load_snapshot(WAGES_NAME),
        "hours": load_snapshot(HOURS_NAME),
    }


def hazard_group(disaster_type: str | None) -> str:
    name = (disaster_type or "").strip()
    if name in _CLIMATE:
        return "Climate and weather"
    if name == "Epidemic":
        return "Epidemic"
    if name in _CONFLICT:
        return "Conflict and displacement"
    if name in _GEO:
        return "Geophysical"
    if name == "Food Insecurity":
        return "Food insecurity"
    return "Other"


def mechanism_group(text: str | None) -> str:
    raw = " ".join(str(text or "").lower().split())
    if raw in {"", "1"}:
        return "Unknown"
    if "saf" in raw or "small arm" in raw:
        return "Small arms fire"
    if "indirect" in raw or "blast" in raw:
        return "Indirect fire / blast"
    if "drone" in raw:
        return "Drone strike"
    if "aerial" in raw or "airstrike" in raw:
        return "Aerial bombardment / airstrike"
    if "bladed" in raw or "assault" in raw:
        return "Bladed weapon / assault"
    if "rta" in raw or "road" in raw:
        return "Road traffic"
    if "drown" in raw:
        return "Drowning"
    if "unknown" in raw:
        return "Unknown"
    return "Other accident"


def mechanism_cause(mechanism: str) -> str:
    if mechanism in VIOLENCE_MECHANISMS:
        return "Violence"
    if mechanism == "Unknown":
        return "Unknown"
    return "Accident"


def operation_mix(appeals: list[Mapping[str, Any]], *, year_min: int = 2016, year_max: int = 2025) -> list[dict[str, Any]]:
    """Operations launched, by year and hazard group. DREF and Emergency Appeal only."""
    counts: dict[int, dict[str, int]] = defaultdict(lambda: {name: 0 for name in HAZARD_GROUPS})
    for row in appeals:
        if row.get("atype") not in {"DREF", "Emergency Appeal"}:
            continue
        year = row.get("year")
        if not isinstance(year, int) or year < year_min or year > year_max:
            continue
        counts[year][hazard_group(row.get("dtype"))] += 1
    series = []
    for year in range(year_min, year_max + 1):
        if year not in counts:
            continue
        series.append({"year": year, "counts": dict(counts[year]), "n": sum(counts[year].values())})
    return series


def stressed_by_income(
    appeals: list[Mapping[str, Any]],
    income: Mapping[str, str],
    societies: set[str],
    *,
    year_min: int = 2016,
    year_max: int = 2025,
    window: int = 5,
    threshold: int = 4,
) -> list[dict[str, Any]]:
    """Share of each income group's Societies with at least four disaster types in five years."""
    by_society_year: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in appeals:
        if row.get("atype") not in {"DREF", "Emergency Appeal"}:
            continue
        iso3 = row.get("iso3")
        year = row.get("year")
        dtype = (row.get("dtype") or "").strip()
        if not iso3 or not isinstance(year, int) or not dtype or iso3 not in societies:
            continue
        by_society_year[(iso3, year)].add(dtype)
    denominator = {group: 0 for group in ("L", "LM", "UM", "H")}
    for iso3 in societies:
        group = income.get(iso3)
        if group in denominator:
            denominator[group] += 1
    points: dict[str, list[dict[str, Any]]] = {group: [] for group in denominator}
    for year in range(year_min, year_max + 1):
        stressed = {group: 0 for group in denominator}
        for iso3 in societies:
            group = income.get(iso3)
            if group not in stressed:
                continue
            kinds: set[str] = set()
            for past in range(year - window + 1, year + 1):
                kinds.update(by_society_year.get((iso3, past), ()))
            if len(kinds) >= threshold:
                stressed[group] += 1
        for group in denominator:
            base = denominator[group]
            if not base:
                continue
            points[group].append({"year": year, "value": stressed[group] / base, "provisional": year == year_max})
    return [{"group": group, "points": points[group], "societies": denominator[group]} for group in denominator if points[group]]


def widest_crises(
    appeals: list[Mapping[str, Any]],
    income: Mapping[str, str],
    names: Mapping[str, str],
    *,
    end_year: int = 2025,
    window: int = 5,
    limit: int = 10,
) -> list[dict[str, Any]]:
    kinds: dict[str, set[str]] = defaultdict(set)
    labels: dict[str, str] = {}
    for row in appeals:
        if row.get("atype") not in {"DREF", "Emergency Appeal"}:
            continue
        iso3 = row.get("iso3")
        year = row.get("year")
        dtype = (row.get("dtype") or "").strip()
        if not iso3 or not isinstance(year, int) or not dtype:
            continue
        if year < end_year - window + 1 or year > end_year:
            continue
        kinds[iso3].add(dtype)
        if row.get("country_name"):
            labels[iso3] = str(row["country_name"])
    ranked = sorted(kinds.items(), key=lambda item: (-len(item[1]), item[0]))[:limit]
    rows = []
    for iso3, disasters in ranked:
        rows.append(
            {
                "society": names.get(iso3) or labels.get(iso3) or iso3,
                "income": income.get(iso3) or "",
                "types": len(disasters),
            }
        )
    return rows


def interpolate_median_age(bands: Mapping[str, float], spec: tuple[tuple[str, int, int], ...]) -> float | None:
    """Age at which the cumulative share of a band distribution crosses one half."""
    present = []
    for key, lower, width in spec:
        value = bands.get(key)
        if isinstance(value, (int, float)) and value > 0:
            present.append((lower, width, float(value)))
    if len(present) < 3:
        return None
    total = sum(value for _lower, _width, value in present)
    if total <= 0:
        return None
    crossed = 0.0
    for lower, width, value in present:
        share = value / total
        if crossed + share >= 0.5:
            if share <= 0:
                return None
            return lower + (0.5 - crossed) / share * width
        crossed += share
    return None


def geometric_mean(values: list[float]) -> float | None:
    positive = [value for value in values if value > 0]
    if not positive:
        return None
    return math.exp(sum(math.log(value) for value in positive) / len(positive))


def centred_smooth(values: list[float]) -> list[float]:
    smoothed = []
    for index, _value in enumerate(values):
        window = values[max(0, index - 1): index + 2]
        smoothed.append(sum(window) / len(window))
    return smoothed


def index_to_base(values: list[float], base: float | None) -> list[float | None]:
    if not base:
        return [None for _value in values]
    return [value / base * 100 for value in values]


def hourly_wage(monthly: float | None) -> float | None:
    if monthly is None or monthly <= 0:
        return None
    return monthly * 12 / ANNUAL_PAID_HOURS


def fill_log_gaps(rows: list[dict[str, Any]], value_key: str, predictor_key: str) -> None:
    """Fill missing wages with a log-log fit on GNI. Marks filled rows."""
    paired = [
        row for row in rows
        if isinstance(row.get(value_key), (int, float)) and row[value_key] > 0
        and isinstance(row.get(predictor_key), (int, float)) and row[predictor_key] > 0
    ]
    if len(paired) < 3:
        return
    mean_x = sum(math.log10(row[predictor_key]) for row in paired) / len(paired)
    mean_y = sum(math.log10(row[value_key]) for row in paired) / len(paired)
    var_x = sum((math.log10(row[predictor_key]) - mean_x) ** 2 for row in paired)
    if var_x <= 0:
        return
    slope = sum(
        (math.log10(row[predictor_key]) - mean_x) * (math.log10(row[value_key]) - mean_y)
        for row in paired
    ) / var_x
    intercept = mean_y - slope * mean_x
    flag = f"{value_key}_imputed"
    for row in rows:
        if isinstance(row.get(value_key), (int, float)) and row[value_key] > 0:
            row[flag] = False
            continue
        predictor = row.get(predictor_key)
        if not isinstance(predictor, (int, float)) or predictor <= 0:
            row[flag] = False
            continue
        row[value_key] = round(10 ** (intercept + slope * math.log10(predictor)), 2)
        row[flag] = True


def median_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return float(median(values))
