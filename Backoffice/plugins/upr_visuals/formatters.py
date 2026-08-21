"""Tableau-faithful number formatting used by UPR Visuals.twb."""

from __future__ import annotations

from datetime import date
from typing import Any


def to_number(value: Any) -> float | None:
    """Coerce stored form values to float. Empty / non-numeric → None."""
    if value is None or value is False:
        return None
    if isinstance(value, bool):
        return 1.0 if value else None
    if isinstance(value, (int, float)):
        if value != value:  # NaN
            return None
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"none", "null", "n/a", "not reported", "undefined"}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def format_count(value: Any) -> str:
    """Integer with thousands separators, Tableau ``n#,##0``."""
    number = to_number(value)
    if number is None:
        return "Not reported"
    return f"{int(round(number)):,}"


def format_compact_chf(value: Any) -> str:
    """Compact CHF-style labels from Tableau ``Value units`` / PNS funding calc.

    < 1,000 → raw integer
    < 1,000,000 → thousands as ``N,000``
    ≥ 1,000,000 → ``N.nM`` (drop trailing ``.0``)
    """
    number = to_number(value)
    if number is None or number == 0:
        return ""
    if abs(number) < 1000:
        return str(int(round(number)))
    if abs(number) < 1_000_000:
        thousands = int(round(number / 1000.0))
        return f"{thousands:,}000" if thousands >= 1000 else f"{thousands},000"
    millions = number / 1_000_000.0
    rounded = round(millions, 1)
    if rounded == int(rounded):
        return f"{int(rounded)}M"
    text = f"{rounded:.1f}".rstrip("0").rstrip(".")
    return f"{text}M"


def format_chf(value: Any) -> str:
    """Full CHF amount with thousands separators, or ``Not reported``."""
    number = to_number(value)
    if number is None:
        return "Not reported"
    return f"{int(round(number)):,}"


def period_to_round(period_name: str | None, kind: str) -> str:
    """Map assignment period_name back to the Tableau RoundParam codes."""
    raw = (period_name or "").strip()
    if not raw:
        return ""
    lower = raw.lower()
    if lower.startswith("jan-jun"):
        year = _year_token(raw)
        return f"MYR{year % 100:02d}" if year else raw
    year = _year_token(raw)
    if year is None:
        return raw
    if kind == "plan":
        return f"P{year % 100:02d}"
    return f"AR{year % 100:02d}"


def _year_token(period_name: str) -> int | None:
    digits = []
    for token in period_name.replace("-", " ").split():
        if token.isdigit() and len(token) == 4:
            digits.append(int(token))
    return digits[-1] if digits else None


def planning_years(period_name: str | None) -> list[int]:
    """Three-year planning horizon for Unified Country Plan visuals."""
    year = _year_token(period_name or "")
    if year is None:
        return []
    return [year, year + 1, year + 2]


def format_header_date(value: date | None = None) -> str:
    """INP/annual-report cover date, e.g. ``2 July 2026``."""
    day = value or date.today()
    return f"{day.day} {day.strftime('%B %Y')}"


def document_subtitle(
    kind: str,
    period_name: str | None,
    *,
    plan_years: list[int] | None = None,
) -> str:
    """Cover line under the country name on All visuals."""
    years = [int(year) for year in (plan_years or []) if year]
    if kind == "plan":
        if len(years) >= 2:
            return f"{years[0]}-{years[-1]} IFRC network country plan"
        if years:
            return f"{years[0]} IFRC network country plan"
        horizon = planning_years(period_name)
        if len(horizon) >= 2:
            return f"{horizon[0]}-{horizon[-1]} IFRC network country plan"
        if horizon:
            return f"{horizon[0]} IFRC network country plan"
        return "IFRC network country plan"
    year = years[0] if years else _year_token(period_name or "")
    raw = (period_name or "").strip().lower()
    if raw.startswith("jan-jun"):
        return (
            f"{year} IFRC network mid-year report, Jan-Jun"
            if year
            else "IFRC network mid-year report, Jan-Jun"
        )
    return (
        f"{year} IFRC network annual report, Jan-Dec"
        if year
        else "IFRC network annual report, Jan-Dec"
    )


def appeal_number(iso2: str | None) -> str:
    """Country appeal code ``MAA`` + ISO2 + ``001`` (e.g. Uganda → ``MAAUG001``)."""
    code = (iso2 or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return f"MAA{code}001"
