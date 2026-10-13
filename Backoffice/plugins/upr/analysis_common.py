"""Helpers shared by every part of the UPR Analysis feature.

The aggregators (:mod:`plugins.upr.impact`, :mod:`plugins.upr.narrative`), the
view builders (:mod:`plugins.upr.impact_views`, :mod:`plugins.upr.narrative_views`)
and any future export (PDF, presentation) need the same definition of a round,
of a "submitted" status, of a settled round and of a year-over-year change.
Keeping those rules in one place stops the numbers on the tab, in a report and
on a slide from drifting apart.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

# Round code -> (year, within-year order). Plans open the year, mid-year reports
# sit in the middle, annual reports close it.
ROUND_RE = re.compile(r"^(P|MYR|AR)(\d{2})$")
KIND_ORDER = {"P": 0, "MYR": 1, "AR": 2}
PLAN_PREFIX = "P"
REPORT_PREFIXES = ("MYR", "AR")
TRACKS = ("P", "MYR", "AR")

APPROVED_STATUSES = frozenset({"approved", "validated"})
SUBMITTED_STATUSES = frozenset({"submitted", "approved", "validated"})

# A round is "in progress" when far fewer countries took part than expected.
# Settled rounds historically clear ~0.8; open rounds sit near ~0.4.
MATURE_ROUND_RATIO = 0.6


def norm(value: Any) -> str:
    return str(value or "").strip().lower()


def num(value: Any) -> float | None:
    """A real number, or ``None`` (booleans and strings are not numbers)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def pct(part: int, whole: int) -> float | None:
    return round(part / whole * 100.0, 1) if whole else None


def _match_round(code: str | None) -> re.Match[str] | None:
    return ROUND_RE.match((code or "").strip().upper())


def round_sort_key(code: str | None) -> tuple[int, int, str]:
    """Chronological key for a round code (``P27`` < ``MYR27`` < ``AR27``)."""
    match = _match_round(code)
    if not match:
        return (9999, 9, str(code or ""))
    return (2000 + int(match.group(2)), KIND_ORDER.get(match.group(1), 5), code or "")


def round_kind(code: str | None) -> str | None:
    """``"plan"`` / ``"report"``, or ``None`` for an unknown code."""
    match = _match_round(code)
    if not match:
        return None
    return "plan" if match.group(1) == PLAN_PREFIX else "report"


def round_prefix(code: str | None) -> str:
    """Exact round family (``P`` / ``MYR`` / ``AR``) for like-for-like comparison."""
    match = _match_round(code)
    return match.group(1) if match else ""


def round_calendar_year(code: str | None) -> int | None:
    """Calendar year a round belongs to (``AR25`` -> ``2025``)."""
    match = _match_round(code)
    return 2000 + int(match.group(2)) if match else None


def ordered_rounds(codes: Iterable[str | None]) -> list[str]:
    return sorted({c for c in codes if c}, key=round_sort_key)


def delta_record(
    latest: Mapping[str, Any] | None,
    previous: Mapping[str, Any] | None,
    key: str,
) -> dict[str, Any]:
    """Change between two year / round records for one value key.

    ``change_pct`` is only set when both records exist and the previous value is
    non-zero, so a first figure never reports an infinite or misleading rise.
    """
    out: dict[str, Any] = {
        "latest": latest.get(key) if latest else None,
        "latest_year": latest.get("year") if latest else None,
        "latest_round": latest.get("round") if latest else None,
        "previous": previous.get(key) if previous else None,
        "previous_year": previous.get("year") if previous else None,
        "change_pct": None,
    }
    if latest and previous:
        prev_val = num(previous.get(key)) or 0.0
        latest_val = num(latest.get(key)) or 0.0
        if prev_val:
            out["change_pct"] = round((latest_val - prev_val) / prev_val * 100.0, 1)
    return out


def load_countries() -> dict[str, dict[str, Any]]:
    """``{ISO3: {iso2, name, region}}`` for every country in the databank."""
    from app.models import Country

    rows = Country.query.with_entities(Country.iso2, Country.iso3, Country.name, Country.region).all()
    return {
        str(iso3).upper(): {"iso2": (iso2 or "").upper() or None, "name": name, "region": region}
        for iso2, iso3, name, region in rows
        if iso3
    }


def iso3s_in_region(countries: Mapping[str, Mapping[str, Any]], region: str | None) -> set[str] | None:
    """ISO3 codes of one region, or ``None`` when no region is selected.

    The single region rule for the whole Analysis feature, so the data and
    narrative sections never disagree about which countries a region holds.
    """
    if not region:
        return None
    wanted = norm(region)
    return {iso3 for iso3, info in countries.items() if norm(info.get("region")) == wanted}
