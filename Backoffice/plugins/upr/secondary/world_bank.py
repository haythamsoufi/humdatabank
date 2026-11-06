"""World Bank indicator fetch helpers."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

WB_BASE = "https://api.worldbank.org/v2/country/all/indicator"


def fetch_indicator(indicator: str, *, date: str | None = None, per_page: int = 20000) -> list[dict[str, Any]]:
    params = {"format": "json", "per_page": str(per_page)}
    if date:
        params["date"] = date
    url = f"{WB_BASE}/{indicator}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "HumanitarianDatabank-UPR/1.0"})
    with urlopen(request, timeout=120) as response:  # noqa: S310 — fixed World Bank host
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list) or len(payload) < 2:
        return []
    rows = payload[1] or []
    return [row for row in rows if isinstance(row, dict)]


def population_latest_by_iso3(*, date: str = "2000:2026") -> tuple[dict[str, float], int | None]:
    """Latest available SP.POP.TOTL per ISO3. Returns (values, max_year_seen)."""
    rows = fetch_indicator("SP.POP.TOTL", date=date)
    best: dict[str, tuple[int, float]] = {}
    for row in rows:
        iso3 = str((row.get("countryiso3code") or "")).strip().upper()
        value = row.get("value")
        year = row.get("date")
        if not iso3 or value is None or year is None:
            continue
        try:
            year_i = int(str(year)[:4])
            value_f = float(value)
        except (TypeError, ValueError):
            continue
        current = best.get(iso3)
        if current is None or year_i > current[0]:
            best[iso3] = (year_i, value_f)
    values = {iso3: value for iso3, (_year, value) in best.items()}
    max_year = max((year for year, _value in best.values()), default=None)
    return values, max_year


def population_by_iso3(*, year: int | None = None) -> dict[str, float]:
    """Back-compat: specific year, or latest when year is omitted."""
    if year is None:
        values, _max_year = population_latest_by_iso3()
        return values
    rows = fetch_indicator("SP.POP.TOTL", date=str(year))
    out: dict[str, float] = {}
    for row in rows:
        iso3 = str((row.get("countryiso3code") or "")).strip().upper()
        value = row.get("value")
        if not iso3 or value is None:
            continue
        try:
            out[iso3] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def poverty_latest_by_iso3(*, date: str = "2000:2026") -> dict[str, dict[str, Any]]:
    rows = fetch_indicator("SI.POV.NAHC", date=date)
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        iso3 = str((row.get("countryiso3code") or "")).strip().upper()
        value = row.get("value")
        year = row.get("date")
        if not iso3 or value is None or year is None:
            continue
        try:
            year_i = int(str(year)[:4])
            value_f = float(value)
        except (TypeError, ValueError):
            continue
        current = best.get(iso3)
        if current is None or year_i > int(current["year"]):
            best[iso3] = {"year": year_i, "value": round(value_f / 100.0, 4)}
    return best


def income_groups_by_iso3(*, per_page: int = 400) -> dict[str, str]:
    """Current World Bank income group per ISO3 from /v2/country."""
    url = f"https://api.worldbank.org/v2/country?{urlencode({'format': 'json', 'per_page': str(per_page)})}"
    request = Request(url, headers={"User-Agent": "HumanitarianDatabank-UPR/1.0"})
    with urlopen(request, timeout=120) as response:  # noqa: S310 — fixed World Bank host
        payload = json.loads(response.read().decode("utf-8"))
    rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
    out: dict[str, str] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        iso3 = str(row.get("id") or "").strip().upper()
        if len(iso3) != 3 or not iso3.isalpha():
            continue
        income = row.get("incomeLevel") if isinstance(row.get("incomeLevel"), dict) else {}
        label = str((income or {}).get("value") or "").strip()
        # Skip aggregates / unclassified.
        if not label or label.lower() in {"aggregates", "not classified"}:
            continue
        out[iso3] = label
    return out
