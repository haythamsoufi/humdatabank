"""Version-selection helpers for UPR import (no Flask dependency)."""

from __future__ import annotations

from typing import Dict, Optional

# First MYR/AR reporting cycle on template version 2 (MYR26 / AR26 → calendar 2026).
REPORTING_COUNTRY_VERSION_2_MIN_YEAR = 2026


def reporting_round_calendar_year(round_code: str) -> Optional[int]:
    """Return calendar year from an AR/MYR round code, or None."""
    rnd = (round_code or "").strip().upper()
    if rnd.startswith("MYR") and len(rnd) >= 5 and rnd[3:].isdigit():
        return 2000 + int(rnd[3:])
    if rnd.startswith("AR") and len(rnd) >= 4 and rnd[2:].isdigit():
        return 2000 + int(rnd[2:])
    return None


def period_calendar_year(period: str) -> Optional[int]:
    """Return calendar year from assignment period_name."""
    pn = (period or "").strip()
    if pn.startswith("Jan-Jun ") and pn[8:].isdigit():
        return int(pn[8:])
    if pn.isdigit():
        return int(pn)
    return None


def resolve_version_bracket(
    brackets: Dict[str, int],
    *,
    period: str = "",
    round_code: Optional[str] = None,
    min_year_v2: int = REPORTING_COUNTRY_VERSION_2_MIN_YEAR,
) -> int:
    """Pick legacy vs current version id from a {legacy, current} bracket map."""
    current = brackets.get("current")
    legacy = brackets.get("legacy")
    if not legacy or not current:
        return int(current or legacy or 0)

    year: Optional[int] = None
    if round_code:
        year = reporting_round_calendar_year(round_code)
    if year is None and period:
        year = period_calendar_year(period)
    if year is not None and year >= min_year_v2:
        return int(current)
    if year is not None:
        return int(legacy)
    return int(current)


def find_item_by_label(labels: Dict[str, int], *needles: str) -> Optional[int]:
    """Resolve form item id by exact or substring label match (case-insensitive)."""
    for needle in needles:
        key = (needle or "").strip().lower()
        if not key:
            continue
        if key in labels:
            return labels[key]
    for needle in needles:
        key = (needle or "").strip().lower()
        if not key:
            continue
        for label, item_id in labels.items():
            if key in label:
                return item_id
    return None
