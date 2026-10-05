"""World Bank snapshot for Everyone Counts.

Population (SP.POP.TOTL) and the current income classification are what the
report uses for volunteer density. GNI per capita (NY.GNP.PCAP.CD), latest
year per country, is stored in the same snapshot for later wage comparisons.
The World Bank API needs no key.

The saved file is the series the analysis reads. Refreshing replaces it.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from plugins.fdrs.services.external_snapshots import load_snapshot, save_snapshot

logger = logging.getLogger(__name__)

SNAPSHOT_NAME = "world_bank"
POPULATION_START_YEAR = 2010
API_ROOT = "https://api.worldbank.org/v2"
POPULATION_INDICATOR = "SP.POP.TOTL"
GNI_INDICATOR = "NY.GNP.PCAP.CD"
INCOME_CODES = {
    "LIC": "L",
    "LMC": "LM",
    "UMC": "UM",
    "HIC": "H",
}
USER_AGENT = "IFRC-Databank-EveryoneCounts/1.0"
PAGE_SIZE = 1000

GetJson = Callable[[str], Any]


def _default_get_json(url: str) -> Any:
    last_error: Exception | None = None
    for _attempt in range(2):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _iter_pages(get_json: GetJson, path: str, params: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    page = 1
    while True:
        query = dict(params)
        query["format"] = "json"
        query["per_page"] = PAGE_SIZE
        query["page"] = page
        url = f"{API_ROOT}/{path}?{urllib.parse.urlencode(query)}"
        payload = get_json(url)
        if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
            break
        meta = payload[0] if isinstance(payload[0], dict) else {}
        yield from (row for row in payload[1] if isinstance(row, dict))
        pages = int(meta.get("pages") or 1)
        if page >= pages:
            break
        page += 1


def _iso3(value: Any) -> str:
    text = str(value or "").strip().upper()
    if len(text) == 3 and text.isalpha():
        return text
    return ""


def _year(value: Any) -> int | None:
    try:
        year = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if year < 1960 or year > 2100:
        return None
    return year


def _positive_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def parse_population_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    parsed = []
    for row in rows:
        iso3 = _iso3(row.get("countryiso3code"))
        year = _year(row.get("date"))
        population = _positive_number(row.get("value"))
        if not iso3 or year is None or population is None:
            continue
        parsed.append({"iso3": iso3, "year": year, "population": int(round(population))})
    parsed.sort(key=lambda item: (item["iso3"], item["year"]))
    return parsed


def parse_income_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    parsed = []
    seen: set[str] = set()
    for row in rows:
        iso3 = _iso3(row.get("id"))
        region = row.get("region") if isinstance(row.get("region"), dict) else {}
        if not iso3 or str(region.get("id") or "") in {"", "NA"}:
            continue
        level = row.get("incomeLevel") if isinstance(row.get("incomeLevel"), dict) else {}
        group = INCOME_CODES.get(str(level.get("id") or ""))
        if group is None or iso3 in seen:
            continue
        seen.add(iso3)
        parsed.append(
            {
                "iso3": iso3,
                "income_group": group,
                "income_name": str(level.get("value") or ""),
            }
        )
    parsed.sort(key=lambda item: item["iso3"])
    return parsed


def parse_latest_gni(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        iso3 = _iso3(row.get("countryiso3code"))
        year = _year(row.get("date"))
        value = _positive_number(row.get("value"))
        if not iso3 or year is None or value is None:
            continue
        current = latest.get(iso3)
        if current is None or year > current["year"]:
            latest[iso3] = {"iso3": iso3, "year": year, "gni_per_capita_usd": value}
    return [latest[iso3] for iso3 in sorted(latest)]


def fetch_world_bank_snapshot(
    *,
    get_json: GetJson | None = None,
    start_year: int = POPULATION_START_YEAR,
    end_year: int | None = None,
) -> dict[str, Any]:
    """Download population, income groups, and latest GNI per capita."""
    reader = get_json or _default_get_json
    if end_year is None:
        end_year = datetime.now(timezone.utc).year
    # One year per request. A single call for the whole span is large enough
    # that the World Bank API often times out before the first byte.
    population_raw: list[dict[str, Any]] = []
    gni_raw: list[dict[str, Any]] = []
    for year in range(start_year, end_year + 1):
        population_raw.extend(
            _iter_pages(reader, f"country/all/indicator/{POPULATION_INDICATOR}", {"date": str(year)})
        )
    for year in range(2000, end_year + 1):
        gni_raw.extend(
            _iter_pages(reader, f"country/all/indicator/{GNI_INDICATOR}", {"date": str(year)})
        )
    population = parse_population_rows(population_raw)
    gni = parse_latest_gni(gni_raw)
    income = parse_income_rows(_iter_pages(reader, "country", {}))
    if not population:
        raise RuntimeError("World Bank population response was empty")
    return {
        "source": "world_bank",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "indicators": {
            POPULATION_INDICATOR: "Population, total",
            GNI_INDICATOR: "GNI per capita, Atlas method (current US$)",
            "income_level": "Current World Bank income classification",
        },
        "population": population,
        "income_groups": income,
        "gni_per_capita": gni,
    }


def ensure_world_bank_snapshot(
    *,
    refresh: bool = False,
    directory: Path | None = None,
    get_json: GetJson | None = None,
) -> dict[str, Any] | None:
    """Return the saved snapshot, downloading it when it is missing or a refresh was asked for."""
    existing = load_snapshot(SNAPSHOT_NAME, directory)
    if existing is not None and not refresh:
        return existing
    try:
        payload = fetch_world_bank_snapshot(get_json=get_json)
    except Exception as exc:
        logger.warning("World Bank snapshot was not refreshed: %s", exc)
        if existing is not None:
            existing = dict(existing)
            existing["refresh_error"] = "The World Bank snapshot could not be refreshed. The saved snapshot is still in use."
            return existing
        return {"source": "world_bank", "available": False, "refresh_error": "The World Bank snapshot could not be downloaded."}
    save_snapshot(SNAPSHOT_NAME, payload, directory)
    return payload
