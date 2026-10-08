"""Display order for matrix row headers.

Period labels sort by calendar start. Other labels sort alphabetically,
with digit runs compared as numbers so 2 comes before 10.
"""

from __future__ import annotations

import re
from typing import Any, Optional

_MONTH_NUMBERS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?"
)
_MONTH_RANGE = re.compile(
    rf"^({_MONTH})\s*[-–—]\s*({_MONTH})\s+(\d{{4}})$",
    re.IGNORECASE,
)
_MONTH_YEAR = re.compile(rf"^({_MONTH})\s+(\d{{4}})$", re.IGNORECASE)
_QUARTER = re.compile(r"^q([1-4])\s+(\d{4})$", re.IGNORECASE)
_ANNUAL = re.compile(r"^(?:annual\s+)?(\d{4})$", re.IGNORECASE)
_YEAR_SPAN = re.compile(r"^(\d{4})\s*[-/]\s*(\d{2,4})$")
_DIGITS = re.compile(r"(\d+)")


def matrix_row_period_key(label: Any) -> Optional[int]:
    """Calendar key YYYYMM, or None when the label is not a period.

    A bare year uses month 00 so ``2026`` stays before ``Jan-Jun 2026``.
    """
    text = str(label or "").strip()
    if not text:
        return None

    match = _MONTH_RANGE.match(text)
    if match:
        month = _MONTH_NUMBERS.get(match.group(1)[:3].lower())
        return (int(match.group(3)) * 100 + month) if month else None
    match = _QUARTER.match(text)
    if match:
        return int(match.group(2)) * 100 + (int(match.group(1)) - 1) * 3 + 1
    match = _MONTH_YEAR.match(text)
    if match:
        month = _MONTH_NUMBERS.get(match.group(1)[:3].lower())
        return (int(match.group(2)) * 100 + month) if month else None
    match = _ANNUAL.match(text)
    if match:
        return int(match.group(1)) * 100
    match = _YEAR_SPAN.match(text)
    if match:
        return int(match.group(1)) * 100
    return None


def _alpha_key(label: str) -> tuple:
    parts = _DIGITS.split(label.casefold())
    return tuple(int(part) if part.isdigit() else part for part in parts)


def matrix_row_sort_key(label: Any) -> tuple:
    text = str(label or "").strip()
    period = matrix_row_period_key(text)
    if period is not None:
        return (0, period, text.casefold())
    return (1, _alpha_key(text))


def sort_matrix_display_rows(rows: Any) -> list:
    """Sort PDF/export row dicts by ``row_display`` (period, then name)."""
    items = list(rows or [])

    def _label(item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("row_display") or item.get("sort_label") or "")
        return str(item or "")

    return sorted(items, key=lambda item: matrix_row_sort_key(_label(item)))
