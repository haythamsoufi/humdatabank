"""Parse human period labels into typed bounds.

``parse_structured_period_label`` accepts the labels the assignment period
picker produces (single year, year range, month range). Admin save uses it to
create the catalog row, then copies those bounds onto the assignment.

``parse_period_label`` is the looser parser used by maintenance scripts. It
also treats other text that contains a year as an annual or custom span.
"""

from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Optional, Tuple

PeriodBounds = Tuple[str, date, date]

_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2}|21\d{2})\b")
_QUARTER_RE = re.compile(r"\bQ([1-4])\b", re.IGNORECASE)
_MONTH_TOKEN = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_MONTH_YEAR_PAIR_RANGE_RE = re.compile(
    rf"(?P<sm>{_MONTH_TOKEN})\s+(?P<sy>\d{{4}})\s*[-–—]\s*"
    rf"(?P<em>{_MONTH_TOKEN})\s+(?P<ey>\d{{4}})",
    re.IGNORECASE,
)
_MONTH_RANGE_SAME_YEAR_RE = re.compile(
    rf"(?P<sm>{_MONTH_TOKEN})\s*[-–]\s*(?P<em>{_MONTH_TOKEN})\s+(?P<y>\d{{4}})",
    re.IGNORECASE,
)
_SINGLE_MONTH_RE = re.compile(
    rf"(?P<m>{_MONTH_TOKEN})\s+(?P<y>\d{{4}})",
    re.IGNORECASE,
)
_SINGLE_YEAR_RE = re.compile(r"\d{4}")
_YEAR_RANGE_RE = re.compile(r"\d{4}-\d{4}")
_MONTH_ALIASES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _extract_years(period_name: str) -> list[int]:
    return [int(y) for y in _YEAR_RE.findall(str(period_name or "").strip())]


def _month_token_to_number(token: str) -> Optional[int]:
    return _MONTH_ALIASES.get(str(token or "").strip().lower())


def _month_range_bounds(
    start_month: int,
    start_year: int,
    end_month: int,
    end_year: int,
) -> PeriodBounds:
    period_start = date(start_year, start_month, 1)
    period_end = date(end_year, end_month, _last_day_of_month(end_year, end_month))
    if (
        start_year == end_year
        and start_month == 1
        and end_month == 12
        and period_end.day == 31
    ):
        return "annual", period_start, period_end
    return "monthly", period_start, period_end


def _try_parse_month_range(raw: str) -> Optional[PeriodBounds]:
    pair_match = _MONTH_YEAR_PAIR_RANGE_RE.search(raw)
    if pair_match:
        start_month = _month_token_to_number(pair_match.group("sm"))
        end_month = _month_token_to_number(pair_match.group("em"))
        if start_month and end_month:
            return _month_range_bounds(
                start_month,
                int(pair_match.group("sy")),
                end_month,
                int(pair_match.group("ey")),
            )

    same_year_match = _MONTH_RANGE_SAME_YEAR_RE.search(raw)
    if same_year_match:
        start_month = _month_token_to_number(same_year_match.group("sm"))
        end_month = _month_token_to_number(same_year_match.group("em"))
        year = int(same_year_match.group("y"))
        if start_month and end_month:
            return _month_range_bounds(start_month, year, end_month, year)

    return None


def _try_parse_single_month(raw: str) -> Optional[PeriodBounds]:
    match = _SINGLE_MONTH_RE.fullmatch(raw.strip())
    if not match:
        return None
    month = _month_token_to_number(match.group("m"))
    if not month:
        return None
    year = int(match.group("y"))
    return _month_range_bounds(month, year, month, year)


def parse_structured_period_label(period_name: str) -> Optional[PeriodBounds]:
    """Parse a period-picker label into (period_type, period_start, period_end).

    Accepts only the exact labels the admin form generates:
    ``2027``, ``2024-2025``, ``Jan 2024``, ``Jan-Jun 2024``, ``Jan 2024-Mar 2025``.
    Other text, including a label that merely contains a year, returns None.
    """
    raw = (period_name or "").strip()
    if not raw:
        return None
    if _SINGLE_YEAR_RE.fullmatch(raw) or _YEAR_RANGE_RE.fullmatch(raw):
        return parse_period_label(raw)
    if (
        _MONTH_YEAR_PAIR_RANGE_RE.fullmatch(raw)
        or _MONTH_RANGE_SAME_YEAR_RE.fullmatch(raw)
    ):
        return _try_parse_month_range(raw)
    return _try_parse_single_month(raw)


def parse_period_label(period_name: str) -> Optional[PeriodBounds]:
    """Parse a human period label into (period_type, period_start, period_end)."""
    raw = (period_name or "").strip()
    if not raw:
        return None

    years = _extract_years(raw)
    if not years:
        return None

    month_range = _try_parse_month_range(raw)
    if month_range is not None:
        return month_range

    single_month = _try_parse_single_month(raw)
    if single_month is not None:
        return single_month

    if len(years) == 1:
        year = years[0]
        quarter_match = _QUARTER_RE.search(raw)
        if quarter_match:
            quarter = int(quarter_match.group(1))
            start_month = (quarter - 1) * 3 + 1
            end_month = quarter * 3
            return (
                "quarterly",
                date(year, start_month, 1),
                date(year, end_month, _last_day_of_month(year, end_month)),
            )
        return "annual", date(year, 1, 1), date(year, 12, 31)

    start_year = min(years)
    end_year = max(years)
    return "custom", date(start_year, 1, 1), date(end_year, 12, 31)
