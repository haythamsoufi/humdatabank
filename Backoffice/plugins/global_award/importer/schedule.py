"""Award window and quarterly cycles. No database access."""

from __future__ import annotations

import calendar
import datetime as dt
import json
import re
from dataclasses import dataclass
from typing import Optional, Sequence

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_YEAR = re.compile(r"(20\d{2})")
_BASELINE_SHEET = "Baseline - Targets"


@dataclass(frozen=True)
class AwardWindow:
    start: dt.date
    end: dt.date

    @property
    def label(self) -> str:
        return f"{self.start.strftime('%b %Y')} – {self.end.strftime('%b %Y')}"


@dataclass(frozen=True)
class QuarterCycle:
    slot: str
    start: dt.date
    end: dt.date


@dataclass(frozen=True)
class ReportCycle:
    """One official MARC reporting window and its review deadlines."""

    slot: str
    start: dt.date
    end: dt.date
    country_due: dt.date
    region_due: dt.date
    geneva_due: dt.date
    dhr_due: dt.date
    kind: str = "quarter"


# DHR reporting calendar. 17–30 Sep 2026 was waived and is covered by Y1Q1 and Final.
AWARD_START = dt.date(2026, 9, 17)
AWARD_END = dt.date(2027, 9, 16)
WAIVED_PERIOD_NOTE = (
    "17–30 Sep 2026 was waived by DHR and is included in the first quarterly report and the final report."
)
OFFICIAL_CYCLES: tuple[ReportCycle, ...] = (
    ReportCycle("Y1Q1", dt.date(2026, 9, 17), dt.date(2026, 12, 20), dt.date(2027, 1, 8), dt.date(2027, 1, 15), dt.date(2027, 1, 22), dt.date(2027, 1, 30)),
    ReportCycle("Y1Q2", dt.date(2026, 12, 21), dt.date(2027, 3, 20), dt.date(2027, 4, 8), dt.date(2027, 4, 15), dt.date(2027, 4, 22), dt.date(2027, 4, 30)),
    ReportCycle("Y1Q3", dt.date(2027, 3, 21), dt.date(2027, 6, 20), dt.date(2027, 7, 8), dt.date(2027, 7, 15), dt.date(2027, 7, 22), dt.date(2027, 7, 30)),
    ReportCycle("Final", AWARD_START, AWARD_END, dt.date(2027, 10, 15), dt.date(2027, 11, 5), dt.date(2027, 12, 1), dt.date(2028, 1, 14), kind="final"),
)


def official_cycles() -> list[ReportCycle]:
    return list(OFFICIAL_CYCLES)


def cycle_by_slot(slot: str) -> Optional[ReportCycle]:
    wanted = (slot or "").strip()
    for cycle in OFFICIAL_CYCLES:
        if cycle.slot == wanted:
            return cycle
    return None


def add_months(day: dt.date, months: int) -> dt.date:
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    return dt.date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def quarterly_cycles(start: dt.date, end: dt.date) -> list[QuarterCycle]:
    """Three-month periods from ``start`` through ``end``. The last period stops on ``end``."""
    if end < start:
        return []
    cycles: list[QuarterCycle] = []
    cursor = start
    year = 1
    quarter = 1
    while cursor <= end and len(cycles) < 40:
        period_end = min(end, add_months(cursor, 3) - dt.timedelta(days=1))
        if period_end < cursor:
            break
        cycles.append(QuarterCycle(f"Y{year}Q{quarter}", cursor, period_end))
        cursor = period_end + dt.timedelta(days=1)
        quarter += 1
        if quarter > 4:
            quarter = 1
            year += 1
    return cycles


def relevance_for_countries(iso3_codes: Sequence[str]) -> str:
    """Show the question only for these ISO3 codes.

    An empty list stays in the template and stays hidden on a country report
    until the logframe gives that line a target.
    """
    codes: list[str] = []
    for code in iso3_codes:
        token = (code or "").strip().upper()
        if token and token not in codes:
            codes.append(token)
    if not codes:
        conditions = [{"item_id": "country_iso", "condition_type": "equal_to", "value": ""}]
        logic = "AND"
    else:
        conditions = [{"item_id": "country_iso", "condition_type": "in", "value": codes}]
        logic = "OR"
    return json.dumps({"logic": logic, "conditions": conditions})


def parse_award_window(workbook) -> Optional[AwardWindow]:
    """Read the baseline month columns (Sep 2026 … Sep 2027 in the annex)."""
    if _BASELINE_SHEET not in getattr(workbook, "sheetnames", []):
        return None
    rows = [tuple(row) for row in workbook[_BASELINE_SHEET].iter_rows(max_row=8, values_only=True)]
    header_at = _month_header(rows)
    if header_at is None:
        return None
    months = _dated_months(rows[header_at - 1] if header_at else (), rows[header_at])
    if not months:
        return None
    first_year, first_month = months[0]
    last_year, last_month = months[-1]
    start = dt.date(first_year, first_month, 1)
    end = dt.date(last_year, last_month, calendar.monthrange(last_year, last_month)[1])
    if end < start:
        return None
    return AwardWindow(start, end)


def _month_header(rows: list[tuple]) -> Optional[int]:
    for index, row in enumerate(rows):
        months = [number for number in (_month_number(cell) for cell in row) if number]
        if len(months) >= 3:
            return index
    return None


def _month_number(value) -> Optional[int]:
    text = re.sub(r"[^a-z]", "", str(value or "").casefold())
    if len(text) < 3:
        return None
    return _MONTHS.get(text[:3])


def _dated_months(year_row: tuple, month_row: tuple) -> list[tuple[int, int]]:
    width = max(len(year_row), len(month_row))
    year = None
    previous = None
    found: list[tuple[int, int]] = []
    for index in range(width):
        raw_year = year_row[index] if index < len(year_row) else None
        match = _YEAR.search(str(raw_year or ""))
        if match:
            year = int(match.group(1))
        month = _month_number(month_row[index] if index < len(month_row) else None)
        if month is None:
            continue
        if year is None:
            continue
        if previous is not None and month <= previous and not match:
            year += 1
        found.append((year, month))
        previous = month
    return found
