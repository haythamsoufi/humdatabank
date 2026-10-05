"""Everyone Counts indicators from live FDRS assignments.

The figures in Everyone Counts 2026 are drawn from a National Society–year
panel of FDRS indicators (see the private analysis repository
``stevepowell99/ECR2026-data-and-code``, ``scripts/02_ns_year_panel.R`` and
``chapters/annex a methodology/fdrs-methods.md``). This module builds that
panel from template 21 assignments instead of a frozen extract.

Closed years use the published snapshot. A late submission — a reported value
that differs from a snapshot still marked imputed — replaces that placeholder.
An unpublished cell uses the reported value, or, for indicators FDRS imputes,
the imputed value, and is marked provisional. Volunteer headlines use a
three-year trailing mean of positive counts. Zeros are kept on the panel and
left out of totals and medians.

World Bank population and income groups come from a saved snapshot, not from
assignments. Figures that need another source are still listed, with that
source named. Motiro survey rows and the named deaths register are not imported.
"""

from __future__ import annotations

import math
import re
from statistics import median
from typing import Any, Mapping

YEAR_MIN = 2010
VOLUNTEER_CODE = "KPI_PeopleVol"
STAFF_CODE = "KPI_PStaff"
ROLLAVG_CODE = "KPI_PeopleVol_RollAvg"
EXTREME_SHARE = 0.40
DUPLICATE_MIN_KPIS = 3
COVID_YEAR = 2020
COVID_CODES = frozenset({"KPI_ReachDRER", "KPI_ReachH", "KPI_ReachHPM"})
AGE_MIN_SOCIETIES = 5
DENSITY_YEAR_MIN = 2014
INCOME_LABELS = {
    "L": "Low income",
    "LM": "Lower-middle income",
    "UM": "Upper-middle income",
    "H": "High income",
}

# indicator_bank.fdrs_kpi_code, label, group, whether FDRS imputes it.
# Bank codes are the FDRS base KPI. The report's extract suffixes totals with
# ``_Tot`` and people-reached with ``_CPD``; the assignment stores that total
# on the indicator itself.
_INDICATORS: tuple[tuple[str, str, str, bool], ...] = (
    (VOLUNTEER_CODE, "Volunteers", "core", True),
    (STAFF_CODE, "Paid staff", "core", True),
    ("KPI_GB", "Governing Board members", "core", True),
    ("KPI_noLocalUnits", "Local units", "core", True),
    ("KPI_noBranches", "Branches", "core", True),
    ("KPI_IncomeLC_CHF", "Total income (CHF)", "core", True),
    ("KPI_expenditureLC_CHF", "Total expenditure (CHF)", "core", True),
    ("KPI_noVolCoveredAI", "Volunteers covered by accident insurance", "protection", False),
    ("KPI_PStaffCoveredAI", "Paid staff covered by accident insurance", "protection", False),
    ("KPI_noVolDeathsDuty", "Volunteer deaths on duty", "protection", False),
    ("KPI_PStaffDeathsDuty", "Paid staff deaths on duty", "protection", False),
    ("KPI_ReachH", "Health", "reach", True),
    ("KPI_ReachLTSPD", "Long-term services and development programmes", "reach", True),
    ("KPI_ReachHI", "Immunisation services", "reach", True),
    ("KPI_ReachDRR", "Disaster risk reduction", "reach", True),
    ("KPI_ReachWASH", "Water, sanitation and hygiene", "reach", True),
    ("KPI_ReachDRER", "Disaster response and early recovery", "reach", True),
    ("KPI_ReachL", "Livelihoods", "reach", True),
    ("KPI_ReachRCRCEd", "National Society education programmes", "reach", True),
    ("KPI_ReachM", "Migration", "reach", True),
    ("KPI_ReachSI", "Protection, gender and inclusion programmes", "reach", True),
    ("KPI_ReachHPM", "Mental health and psychosocial support", "reach", True),
    ("KPI_ClimateHeat", "Heatwave risk reduction, preparedness or response", "reach", True),
    ("KPI_Climate", "Activities to address rising climate risks", "reach", True),
    ("KPI_ReachCTP", "Cash transfer programming", "reach", True),
    ("KPI_ReachS", "Shelter", "reach", True),
    ("KPI_DonBlood", "People donating blood", "reach", True),
    ("KPI_TrainFA", "People trained in first aid", "reach", True),
)

_BY_CODE: dict[str, tuple[str, str, bool]] = {
    code: (label, group, imputable) for code, label, group, imputable in _INDICATORS
}
PANEL_CODES = frozenset(_BY_CODE)
QUERY_CODES = PANEL_CODES | {ROLLAVG_CODE}
_SEX_CODES = frozenset({VOLUNTEER_CODE, STAFF_CODE, "KPI_GB"})
# FDRS questions, not indicator-bank codes. Same ids as FDRS_QUESTION_KPI_TO_ITEM.
_LEADER_SEX_ITEMS = {924: "President", 934: "Secretary General"}

# FDRS volunteer age bands, plus the platform default bands, in display order.
_AGE_BANDS: tuple[tuple[str, str], ...] = (
    ("6_12", "6–12"),
    ("13_17", "13–17"),
    ("18_29", "18–29"),
    ("30_39", "30–39"),
    ("40_49", "40–49"),
    ("50_59", "50–59"),
    ("60_69", "60–69"),
    ("70_79", "70–79"),
    ("80", "80+"),
    ("5", "Under 5"),
    ("5_17", "5–17"),
    ("18_49", "18–49"),
    ("50", "50+"),
)
_AGE_LABEL = {key: label for key, label in _AGE_BANDS}
_AGE_ORDER = {key: index for index, (key, _label) in enumerate(_AGE_BANDS)}
_AGE_ALIASES = {
    "80_plus": "80",
    "age_80": "80",
    "50_plus": "50",
    "under_5": "5",
    "lt_5": "5",
}

_SEX_PREFIXES = ("female", "non_binary", "unknown", "other", "male")
_SKIP_KEYS = frozenset({"mode", "values", "direct", "indirect", "disability"})

NOTES = (
    "Closed years use the value FDRS published. Where a National Society reported after that snapshot and the published value is still an imputed placeholder, the reported value is used.",
    "The open year uses the reported value when the Society has submitted one, and FDRS’s imputed value otherwise. That year is marked provisional because coverage is still incomplete.",
    "The volunteer headline is a three-year trailing mean. A Society is included only when it has a positive count in that year and the two years before it.",
    "Totals and medians leave out zeros and blanks. People-reached indicators are shown separately and are not added together.",
    "Volunteer density uses a saved World Bank population snapshot. The income group is the Bank’s current classification, held fixed for every year. Population after the snapshot’s last year is carried forward.",
    "World Giving Index, IFRC GO, OCAC, ILO wages, World Bank median age, the Aid Worker Security Database, and the security-unit death counts are read from saved snapshots. Each chart states the snapshot date. Refresh those files with the snapshot build; the page does not download them.",
    "The printed reach models (Figures 3.8 to 3.10 and Table A.1) are multilevel models. This view shows the unadjusted comparison for Figures 3.8 and 3.9 and does not re-estimate the model.",
    "President and Secretary General sex come from the FDRS questions, not from the indicator bank. Motiro survey rows and the named deaths register are not imported.",
)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    text = str(value).strip().replace(",", "").replace(" ", "")
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _amount(text: Any, numeric: Any) -> float | None:
    if text is not None and str(text).strip() != "":
        if numeric is not None:
            parsed = _number(numeric)
            if parsed is not None:
                return parsed
        return _number(text)
    return _number(numeric)


def _differs(left: float, right: float) -> bool:
    scale = max(abs(left), abs(right), 1.0)
    return abs(left - right) > scale * 1e-6


def _payload(disagg: Any) -> Mapping[str, Any] | None:
    if isinstance(disagg, str):
        import json

        try:
            disagg = json.loads(disagg)
        except json.JSONDecodeError:
            return None
    if not isinstance(disagg, dict):
        return None
    values = disagg.get("values") if "values" in disagg else disagg
    if not isinstance(values, dict):
        return None
    direct = values.get("direct")
    if isinstance(direct, dict):
        return direct
    return values


def _leaves(disagg: Any):
    payload = _payload(disagg)
    if not payload:
        return
    for key, raw in payload.items():
        name = str(key).strip()
        if name.lower() in _SKIP_KEYS:
            continue
        if isinstance(raw, dict):
            for sub_key, sub_raw in raw.items():
                number = _number(sub_raw)
                if number is not None:
                    yield f"{name}_{sub_key}", number
            continue
        number = _number(raw)
        if number is not None:
            yield name, number


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def _split_sex_age(key: str) -> tuple[str | None, str]:
    slug = _slug(key)
    for sex in _SEX_PREFIXES:
        if slug == sex:
            return sex, ""
        prefix = sex + "_"
        if slug.startswith(prefix):
            return sex, slug[len(prefix):]
    return None, slug


def _age_key(rest: str) -> str | None:
    if not rest or rest in {"female", "male", "non_binary", "unknown", "other"}:
        return None
    canonical = _AGE_ALIASES.get(rest, rest)
    if canonical in _AGE_LABEL:
        return canonical
    if any(character.isdigit() for character in rest):
        return rest
    return None


def _breakdown(disagg: Any) -> tuple[dict[str, float], dict[str, bool], dict[str, float]]:
    """Sex sums, which of female/male were present, and age-band sums."""
    sex = {"female": 0.0, "male": 0.0}
    seen = {"female": False, "male": False}
    ages: dict[str, float] = {}
    for key, number in _leaves(disagg):
        sex_name, rest = _split_sex_age(key)
        if sex_name == "female":
            sex["female"] += number
            seen["female"] = True
        elif sex_name == "male":
            sex["male"] += number
            seen["male"] = True
        age_source = rest if sex_name else rest
        if sex_name and not rest:
            continue
        age_id = _age_key(age_source)
        if age_id is not None:
            ages[age_id] = ages.get(age_id, 0.0) + number
    return sex, seen, ages


def _disagg_for_cell(obs: Mapping[str, Any], *, late: bool, provisional: bool, imp_fill: bool) -> Any:
    if imp_fill:
        return None
    if late or provisional:
        return obs.get("disagg_data")
    published = obs.get("published_disagg_data")
    if published:
        return published
    return obs.get("disagg_data")


def select_cell(obs: Mapping[str, Any]) -> dict[str, Any] | None:
    """Choose the panel value for one assignment cell.

    Returns None when the cell has no usable number. ``imputed`` means the
    chosen number is FDRS's imputation. ``provisional`` means it is not a
    published snapshot. ``imp_fill`` means an open-year gap was filled from
    the imputed value. ``late`` means a reported value replaced a stale
    imputed publication.
    """
    blocked = bool(obs.get("data_not_available") or obs.get("not_applicable"))
    reported = None if blocked else _amount(obs.get("value"), obs.get("numeric_value"))
    published = _amount(obs.get("published_value"), obs.get("published_numeric_value"))
    imputed = _amount(obs.get("imputed_value"), obs.get("imputed_numeric_value"))
    source = (obs.get("published_source") or "").strip().lower()

    if published is not None:
        late = (
            reported is not None
            and source == "imputed"
            and _differs(reported, published)
        )
        if late:
            return {
                "value": reported,
                "imputed": False,
                "provisional": False,
                "imp_fill": False,
                "late": True,
            }
        return {
            "value": published,
            "imputed": source == "imputed",
            "provisional": False,
            "imp_fill": False,
            "late": False,
        }

    if reported is not None:
        return {
            "value": reported,
            "imputed": False,
            "provisional": True,
            "imp_fill": False,
            "late": False,
        }
    meta = _BY_CODE.get(str(obs.get("kpi_code") or ""))
    if imputed is not None and meta is not None and meta[2]:
        return {
            "value": imputed,
            "imputed": True,
            "provisional": True,
            "imp_fill": True,
            "late": False,
        }
    return None


def _prefer(candidate: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    candidate_rank = (candidate["provisional"], candidate["imp_fill"], candidate["imputed"])
    current_rank = (current["provisional"], current["imp_fill"], current["imputed"])
    if candidate_rank != current_rank:
        return candidate_rank < current_rank
    return abs(candidate["value"]) > abs(current["value"])


def _attach_roll3(rows: list[dict[str, Any]], rollavg: dict[tuple[str, int], float]) -> None:
    by_society: dict[str, dict[int, float]] = {}
    for row in rows:
        if row["kpi_code"] != VOLUNTEER_CODE or row["value"] is None or row["value"] <= 0:
            continue
        by_society.setdefault(row["iso3"], {})[row["year"]] = row["value"]

    rolling: dict[tuple[str, int], float] = {}
    for iso3, years in by_society.items():
        for year, value in years.items():
            previous = years.get(year - 1)
            earlier = years.get(year - 2)
            if previous is None or earlier is None:
                continue
            rolling[(iso3, year)] = (value + previous + earlier) / 3.0

    latest_year = max((row["year"] for row in rows if row["kpi_code"] == VOLUNTEER_CODE), default=None)
    for row in rows:
        if row["kpi_code"] != VOLUNTEER_CODE:
            row["value_roll3"] = None
            continue
        row["value_roll3"] = rolling.get((row["iso3"], row["year"]))
        if latest_year is not None and row["year"] == latest_year:
            official = rollavg.get((row["iso3"], latest_year))
            if official is not None and official > 0:
                row["value_roll3"] = official


def _apply_flags(rows: list[dict[str, Any]]) -> None:
    duplicate_keys: set[tuple[str, int, float]] = set()
    grouped: dict[tuple[str, int, float], set[str]] = {}
    for row in rows:
        if row["value"] is None or row["value"] <= 0:
            continue
        key = (row["iso3"], row["year"], round(float(row["value"]), 4))
        grouped.setdefault(key, set()).add(row["kpi_code"])
    for key, codes in grouped.items():
        if len(codes) >= DUPLICATE_MIN_KPIS:
            duplicate_keys.add(key)

    totals: dict[tuple[str, int], float] = {}
    reporters: dict[tuple[str, int], int] = {}
    for row in rows:
        if row["value"] is None or row["value"] <= 0:
            continue
        slot = (row["kpi_code"], row["year"])
        totals[slot] = totals.get(slot, 0.0) + row["value"]
        reporters[slot] = reporters.get(slot, 0) + 1

    for row in rows:
        value = row["value"]
        duplicate = False
        extreme = False
        share = None
        if value is not None and value > 0:
            duplicate = (row["iso3"], row["year"], round(float(value), 4)) in duplicate_keys
            total = totals.get((row["kpi_code"], row["year"])) or 0.0
            # One Society reporting an indicator is the whole total by definition.
            # The report's rule is meant to catch one Society dominating a total
            # that several Societies contributed to.
            if total > 0 and reporters.get((row["kpi_code"], row["year"]), 0) >= 2:
                share = value / total
                extreme = share >= EXTREME_SHARE
        row["flag_duplicate_within_ns"] = duplicate
        row["flag_extreme_share"] = extreme
        row["extreme_share"] = share if extreme else None
        row["flag_covid_year"] = row["year"] == COVID_YEAR and row["kpi_code"] in COVID_CODES


def build_panel(observations: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Collapse assignment cells into one row per Society, year and indicator."""
    chosen: dict[tuple[str, int, str], dict[str, Any]] = {}
    rollavg: dict[tuple[str, int], float] = {}

    for obs in observations:
        iso3 = (obs.get("iso3") or "").strip().upper()
        code = (obs.get("kpi_code") or "").strip()
        year = obs.get("year")
        if not iso3 or not isinstance(year, int) or year < YEAR_MIN or not code:
            continue
        cell = select_cell(obs)
        if cell is None:
            continue
        if code == ROLLAVG_CODE:
            if cell["value"] is not None and cell["value"] > 0:
                current = rollavg.get((iso3, year))
                if current is None or cell["value"] > current:
                    rollavg[(iso3, year)] = cell["value"]
            continue
        meta = _BY_CODE.get(code)
        if meta is None:
            continue
        label, group, _imputable = meta
        row = {
            "iso3": iso3,
            "country_name": obs.get("country_name") or iso3,
            "region": (obs.get("region") or "").strip(),
            "year": year,
            "kpi_code": code,
            "label": label,
            "group": group,
            **cell,
        }
        disagg = _disagg_for_cell(
            obs,
            late=cell["late"],
            provisional=cell["provisional"],
            imp_fill=cell["imp_fill"],
        )
        if code in _SEX_CODES and disagg:
            sex, seen, ages = _breakdown(disagg)
            row["female"] = sex["female"] if seen["female"] else None
            row["male"] = sex["male"] if seen["male"] else None
            row["age_bands"] = ages if code == VOLUNTEER_CODE else {}
        else:
            row["female"] = None
            row["male"] = None
            row["age_bands"] = {}
        key = (iso3, year, code)
        current = chosen.get(key)
        if current is None or _prefer(row, current):
            chosen[key] = row

    rows = list(chosen.values())
    _attach_roll3(rows, rollavg)
    _apply_flags(rows)
    rows.sort(key=lambda row: (row["kpi_code"], row["year"], row["iso3"]))
    return rows


def _year_rows(rows: list[dict[str, Any]], code: str) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        if row["kpi_code"] == code:
            grouped.setdefault(row["year"], []).append(row)
    return grouped


def _positive(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row["value"] is not None and row["value"] > 0]


def _sum_positive(rows: list[dict[str, Any]]) -> float | None:
    values = [row["value"] for row in _positive(rows)]
    if not values:
        return None
    return float(sum(values))


def _median_positive(values: list[float]) -> float | None:
    if not values:
        return None
    return float(median(values))


def _is_provisional(volunteer_rows: list[dict[str, Any]]) -> bool:
    """A year is provisional when most Societies still lack a published snapshot.

    One unpublished Society does not make a closed year provisional. The open
    collection year, and years with no published series at all, do.
    """
    positive = _positive(volunteer_rows)
    if not positive:
        return False
    unpublished = sum(1 for row in positive if row["provisional"])
    return unpublished * 2 >= len(positive)


def _age_summary(volunteer_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reporters: list[dict[str, float]] = []
    for row in volunteer_rows:
        bands = {
            key: value
            for key, value in (row.get("age_bands") or {}).items()
            if value is not None and value > 0
        }
        if bands:
            reporters.append(bands)
    if len(reporters) < AGE_MIN_SOCIETIES:
        return []
    union = set().union(*(bands.keys() for bands in reporters))
    ordered = sorted(union, key=lambda key: (_AGE_ORDER.get(key, 100), key))
    summary = []
    for key in ordered:
        shares = []
        for bands in reporters:
            total = sum(bands.values())
            shares.append((bands.get(key) or 0.0) / total)
        label = _AGE_LABEL.get(key) or key.replace("_", "–")
        summary.append(
            {
                "band": label,
                "mean_share": float(sum(shares) / len(shares)),
                "societies": len(reporters),
            }
        )
    return summary


def _region_summary(volunteer_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, float]] = {}
    for row in volunteer_rows:
        rolling = row.get("value_roll3")
        if rolling is None or rolling <= 0:
            continue
        region = row.get("region") or "Unassigned"
        slot = buckets.setdefault(region, {"volunteers_rolling": 0.0, "societies": 0})
        slot["volunteers_rolling"] += rolling
        slot["societies"] += 1
    regions = [
        {"region": name, "volunteers_rolling": slot["volunteers_rolling"], "societies": int(slot["societies"])}
        for name, slot in buckets.items()
    ]
    regions.sort(key=lambda item: item["volunteers_rolling"], reverse=True)
    return regions


def _female_share(rows: list[dict[str, Any]]) -> tuple[float | None, int]:
    shares = []
    for row in rows:
        female = row.get("female")
        male = row.get("male")
        if female is None or male is None:
            continue
        total = female + male
        if total <= 0:
            continue
        shares.append(female / total)
    if not shares:
        return None, 0
    return float(median(shares)), len(shares)


def _staff_ratio(volunteer_rows: list[dict[str, Any]], staff_rows: list[dict[str, Any]]) -> tuple[float | None, int]:
    staff_by_iso = {
        row["iso3"]: row["value"]
        for row in staff_rows
        if row["value"] is not None and row["value"] > 0
    }
    ratios = []
    for row in _positive(volunteer_rows):
        staff = staff_by_iso.get(row["iso3"])
        if staff:
            ratios.append(row["value"] / staff)
    if not ratios:
        return None, 0
    return float(median(ratios)), len(ratios)


def _population_series(population_rows: list[Mapping[str, Any]]) -> dict[str, dict[int, float]]:
    by_iso: dict[str, dict[int, float]] = {}
    for row in population_rows:
        iso3 = str(row.get("iso3") or "").strip().upper()
        year = row.get("year")
        population = row.get("population")
        if len(iso3) != 3 or not isinstance(year, int):
            continue
        try:
            value = float(population)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        by_iso.setdefault(iso3, {})[year] = value
    return by_iso


def population_for_year(
    series_by_iso: Mapping[str, Mapping[int, float]],
    iso3: str,
    year: int,
) -> tuple[float, bool] | None:
    """Population for a country-year.

    A missing year is filled only when it is after that country's last
    observed year. A gap between two observed years stays empty.
    """
    series = series_by_iso.get(iso3)
    if not series:
        return None
    if year in series:
        return series[year], False
    if year <= max(series):
        return None
    return series[max(series)], True


def volunteer_density_by_income(
    rows: list[Mapping[str, Any]],
    world_bank: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Median volunteers per million people, by current World Bank income group."""
    if not world_bank or not world_bank.get("population"):
        return []
    populations = _population_series(list(world_bank.get("population") or []))
    income: dict[str, str] = {}
    for item in world_bank.get("income_groups") or []:
        iso3 = str(item.get("iso3") or "").strip().upper()
        group = item.get("income_group")
        if iso3 and group in INCOME_LABELS:
            income[iso3] = str(group)
    buckets: dict[tuple[int, str], list[float]] = {}
    carried: set[tuple[int, str]] = set()
    for row in rows:
        if row.get("kpi_code") != VOLUNTEER_CODE:
            continue
        rolling = row.get("value_roll3")
        year = row.get("year")
        iso3 = row.get("iso3")
        if not isinstance(year, int) or year < DENSITY_YEAR_MIN or not isinstance(rolling, (int, float)) or rolling <= 0:
            continue
        group = income.get(iso3)
        if not group:
            continue
        found = population_for_year(populations, iso3, year)
        if found is None:
            continue
        population, was_carried = found
        key = (year, group)
        buckets.setdefault(key, []).append(float(rolling) / population * 1_000_000)
        if was_carried:
            carried.add(key)
    series = []
    for year, group in sorted(buckets):
        values = buckets[(year, group)]
        series.append(
            {
                "year": year,
                "income_group": group,
                "label": INCOME_LABELS[group],
                "median_per_million": float(median(values)),
                "societies": len(values),
                "population_carried_forward": (year, group) in carried,
            }
        )
    return series


def _world_bank_status(world_bank: Mapping[str, Any] | None, series: list[dict[str, Any]]) -> dict[str, Any]:
    if not world_bank or not world_bank.get("population"):
        return {
            "available": False,
            "fetched_at": world_bank.get("fetched_at") if world_bank else None,
            "population_rows": 0,
            "income_groups": 0,
            "gni_countries": 0,
            "density_points": 0,
            "refresh_error": (world_bank or {}).get("refresh_error"),
        }
    return {
        "available": True,
        "fetched_at": world_bank.get("fetched_at"),
        "population_rows": len(world_bank.get("population") or []),
        "income_groups": len(world_bank.get("income_groups") or []),
        "gni_countries": len(world_bank.get("gni_per_capita") or []),
        "density_points": len(series),
        "refresh_error": world_bank.get("refresh_error"),
    }


def summarize_panel(
    rows: list[dict[str, Any]],
    *,
    template_id: int | None = None,
    world_bank: Mapping[str, Any] | None = None,
    leaders: list[Mapping[str, Any]] | None = None,
    sources: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Headline series used by the Everyone Counts data-explorer tab."""
    volunteers = _year_rows(rows, VOLUNTEER_CODE)
    staff = _year_rows(rows, STAFF_CODE)
    local_units = _year_rows(rows, "KPI_noLocalUnits")
    income = _year_rows(rows, "KPI_IncomeLC_CHF")
    expenditure = _year_rows(rows, "KPI_expenditureLC_CHF")
    years_present = sorted(set(volunteers) | {row["year"] for row in rows})

    year_payload = []
    provisional_years = set()
    for year in years_present:
        volunteer_rows = volunteers.get(year, [])
        provisional = _is_provisional(volunteer_rows)
        if provisional:
            provisional_years.add(year)
        positive = _positive(volunteer_rows)
        reported = [row for row in positive if not row["imputed"]]
        rolling_values = [
            row["value_roll3"]
            for row in volunteer_rows
            if row.get("value_roll3") is not None and row["value_roll3"] > 0
        ]
        ratio, ratio_n = _staff_ratio(volunteer_rows, staff.get(year, []))
        female, female_n = _female_share(volunteer_rows)
        year_payload.append(
            {
                "year": year,
                "provisional": provisional,
                "annual_volunteers": _sum_positive(volunteer_rows),
                "societies_annual": len(positive),
                "reported_volunteers": float(sum(row["value"] for row in reported)) if reported else None,
                "societies_reporting": len(reported),
                "rolling_volunteers": float(sum(rolling_values)) if rolling_values else None,
                "societies_rolling": len(rolling_values),
                "median_volunteers": _median_positive([row["value"] for row in positive]),
                "median_rolling": _median_positive(rolling_values),
                "median_volunteers_per_staff": ratio,
                "societies_in_ratio": ratio_n,
                "median_female_share": female,
                "societies_with_sex": female_n,
                "staff": _sum_positive(staff.get(year, [])),
                "societies_staff": len(_positive(staff.get(year, []))),
                "local_units": _sum_positive(local_units.get(year, [])),
                "income": _sum_positive(income.get(year, [])),
                "expenditure": _sum_positive(expenditure.get(year, [])),
            }
        )

    settled_year = None
    for item in reversed(year_payload):
        if not item["provisional"] and item["societies_annual"]:
            settled_year = item["year"]
            break
    open_year = None
    if year_payload and year_payload[-1]["provisional"]:
        open_year = year_payload[-1]["year"]

    snapshot_year = settled_year if settled_year is not None else open_year
    snapshot = None
    regions: list[dict[str, Any]] = []
    age_bands: list[dict[str, Any]] = []
    reach: list[dict[str, Any]] = []
    if snapshot_year is not None:
        volunteer_rows = volunteers.get(snapshot_year, [])
        matched = next(item for item in year_payload if item["year"] == snapshot_year)
        snapshot = {
            "year": snapshot_year,
            "provisional": snapshot_year in provisional_years,
            "rolling_volunteers": matched["rolling_volunteers"],
            "societies_rolling": matched["societies_rolling"],
            "societies_reporting": matched["societies_reporting"],
            "annual_volunteers": matched["annual_volunteers"],
            "median_volunteers_per_staff": matched["median_volunteers_per_staff"],
            "societies_in_ratio": matched["societies_in_ratio"],
            "median_female_share": matched["median_female_share"],
            "societies_with_sex": matched["societies_with_sex"],
            "staff": matched["staff"],
            "local_units": matched["local_units"],
            "income": matched["income"],
        }
        regions = _region_summary(volunteer_rows)
        age_bands = _age_summary(volunteer_rows)
        for code, label, group, _imputable in _INDICATORS:
            if group != "reach":
                continue
            positive = _positive([row for row in rows if row["kpi_code"] == code and row["year"] == snapshot_year])
            reach.append(
                {
                    "code": code,
                    "label": label,
                    "year": snapshot_year,
                    "societies": len(positive),
                    "median": _median_positive([row["value"] for row in positive]),
                }
            )

    extreme = [
        {
            "iso3": row["iso3"],
            "country_name": row["country_name"],
            "year": row["year"],
            "label": row["label"],
            "share": row["extreme_share"],
            "value": row["value"],
        }
        for row in rows
        if row.get("flag_extreme_share")
    ]
    extreme.sort(key=lambda item: item["share"] or 0, reverse=True)

    societies = {row["iso3"] for row in rows}
    warning = None
    if not rows:
        warning = "No FDRS indicator values were found for this analysis."
    density = volunteer_density_by_income(rows, world_bank)
    from plugins.fdrs.services.ecr_report import build_chapters

    chapters = build_chapters(rows, world_bank=world_bank, leaders=leaders, sources=sources)
    return {
        "scope": {
            "template_id": template_id,
            "year_from": years_present[0] if years_present else None,
            "year_to": years_present[-1] if years_present else None,
            "national_societies": len(societies),
            "settled_year": settled_year,
            "open_year": open_year,
        },
        "snapshot": snapshot,
        "years": year_payload,
        "regions": regions,
        "reach": reach,
        "age_bands": age_bands,
        "volunteer_density": density,
        "external": {"world_bank": _world_bank_status(world_bank, density)},
        "flags": {
            "duplicate_rows": sum(1 for row in rows if row["flag_duplicate_within_ns"]),
            "extreme_share_rows": sum(1 for row in rows if row["flag_extreme_share"]),
            "covid_year_rows": sum(1 for row in rows if row["flag_covid_year"]),
            "extreme_examples": extreme[:8],
        },
        "notes": list(NOTES),
        "warning": warning,
        "chapters": chapters,
    }


def build_everyone_counts(
    observations: list[Mapping[str, Any]],
    *,
    template_id: int | None = None,
    world_bank: Mapping[str, Any] | None = None,
    leaders: list[Mapping[str, Any]] | None = None,
    sources: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return summarize_panel(
        build_panel(observations),
        template_id=template_id,
        world_bank=world_bank,
        leaders=leaders,
        sources=sources,
    )


def load_everyone_counts(
    template_id: int | None = None,
    *,
    refresh_external: bool = False,
) -> dict[str, Any]:
    """Read FDRS assignment cells and return the Everyone Counts summary."""
    from app.models import AssignedForm, AssignmentEntityStatus, Country, FormData, FormItem, IndicatorBank
    from app.services.data_quality.helpers import parse_period_year
    from app.utils.country_utils import exclude_sandbox_countries
    from app.utils.data_quality_constants import FDRS_TEMPLATE_ID

    if template_id is None:
        template_id = FDRS_TEMPLATE_ID

    query = (
        FormData.query.join(
            AssignmentEntityStatus,
            FormData.assignment_entity_status_id == AssignmentEntityStatus.id,
        )
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .join(Country, Country.id == AssignmentEntityStatus.entity_id)
        .join(FormItem, FormData.form_item_id == FormItem.id)
        .join(IndicatorBank, FormItem.indicator_bank_id == IndicatorBank.id)
        .filter(
            AssignedForm.template_id == template_id,
            AssignmentEntityStatus.entity_type == "country",
            FormItem.archived.is_(False),
            IndicatorBank.fdrs_kpi_code.in_(QUERY_CODES),
        )
    )
    fetched = exclude_sandbox_countries(query).with_entities(
        Country.iso3,
        Country.name,
        Country.region,
        AssignedForm.period_name,
        IndicatorBank.fdrs_kpi_code,
        FormData.value,
        FormData.numeric_value,
        FormData.imputed_value,
        FormData.imputed_numeric_value,
        FormData.published_value,
        FormData.published_numeric_value,
        FormData.published_source,
        FormData.published_disagg_data,
        FormData.disagg_data,
        FormData.data_not_available,
        FormData.not_applicable,
    ).all()

    observations = []
    for row in fetched:
        year = parse_period_year(row.period_name)
        if year is None:
            continue
        observations.append(
            {
                "iso3": row.iso3,
                "country_name": row.name,
                "region": row.region,
                "year": year,
                "kpi_code": row.fdrs_kpi_code,
                "value": row.value,
                "numeric_value": row.numeric_value,
                "imputed_value": row.imputed_value,
                "imputed_numeric_value": row.imputed_numeric_value,
                "published_value": row.published_value,
                "published_numeric_value": row.published_numeric_value,
                "published_source": row.published_source,
                "published_disagg_data": row.published_disagg_data,
                "disagg_data": row.disagg_data,
                "data_not_available": row.data_not_available,
                "not_applicable": row.not_applicable,
            }
        )
    from plugins.fdrs.services.ecr_external import load_sources
    from plugins.fdrs.services.world_bank_snapshot import ensure_world_bank_snapshot

    world_bank = ensure_world_bank_snapshot(refresh=refresh_external)
    leaders = load_leader_sex(template_id)
    return build_everyone_counts(
        observations,
        template_id=template_id,
        world_bank=world_bank,
        leaders=leaders,
        sources=load_sources(),
    )


def _normalise_sex(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"female", "f", "woman", "women"}:
        return "Female"
    if text in {"male", "m", "man", "men"}:
        return "Male"
    return None


def load_leader_sex(template_id: int) -> list[dict[str, Any]]:
    """President and Secretary General sex from the FDRS questions.

    These are form questions, not indicator-bank codes, so the panel query
    does not see them. Known published item ids are tried first; a label
    match covers a template whose ids differ.
    """
    from app.models import AssignedForm, AssignmentEntityStatus, Country, FormData, FormItem
    from app.services.data_quality.helpers import parse_period_year
    from app.utils.country_utils import exclude_sandbox_countries

    role_by_id = dict(_LEADER_SEX_ITEMS)
    items = FormItem.query.filter(
        FormItem.template_id == template_id,
        FormItem.archived.is_(False),
        FormItem.id.in_(list(role_by_id)),
    ).all()
    if not items:
        candidates = FormItem.query.filter(
            FormItem.template_id == template_id,
            FormItem.archived.is_(False),
        ).all()
        role_by_id = {}
        for item in candidates:
            label = (item.label or "").lower()
            if "sex" not in label and "gender" not in label:
                continue
            if "president" in label:
                role_by_id[item.id] = "President"
            elif "secretary" in label:
                role_by_id[item.id] = "Secretary General"
        items = [item for item in candidates if item.id in role_by_id]
    if not items:
        return []

    query = (
        FormData.query.join(
            AssignmentEntityStatus,
            FormData.assignment_entity_status_id == AssignmentEntityStatus.id,
        )
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .join(Country, Country.id == AssignmentEntityStatus.entity_id)
        .filter(
            AssignedForm.template_id == template_id,
            AssignmentEntityStatus.entity_type == "country",
            FormData.form_item_id.in_(list(role_by_id)),
        )
    )
    fetched = exclude_sandbox_countries(query).with_entities(
        Country.iso3,
        AssignedForm.period_name,
        FormData.form_item_id,
        FormData.value,
        FormData.published_value,
        FormData.published_source,
        FormData.data_not_available,
        FormData.not_applicable,
    ).all()

    leaders = []
    for row in fetched:
        if row.data_not_available or row.not_applicable:
            continue
        year = parse_period_year(row.period_name)
        iso3 = (row.iso3 or "").strip().upper()
        if year is None or len(iso3) != 3:
            continue
        published = _normalise_sex(row.published_value)
        reported = _normalise_sex(row.value)
        source = str(row.published_source or "").strip().lower()
        if published and source != "imputed":
            sex = published
        else:
            sex = reported or published
        if sex is None:
            continue
        leaders.append(
            {
                "iso3": iso3,
                "year": year,
                "role": role_by_id.get(row.form_item_id) or "Leader",
                "sex": sex,
            }
        )
    return leaders
