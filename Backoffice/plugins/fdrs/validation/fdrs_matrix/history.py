"""Historical comparison helpers for FDRS validation matrix."""

from __future__ import annotations

CHECK_TYPE_PAST_YEAR = "Threshold over the past year"
CHECK_TYPE_3YEAR_AVG = "Threshold over the average of the last 3 years"

DEATH_KPI_CODES = frozenset({"KPI_noVolDeathsDuty_Tot", "KPI_PStaffDeathsDuty_Tot"})


def baseline_value(history: dict[int, float], year: int, check_type: str) -> float | None:
    """history: year -> value for prior years only (year-1, year-2, year-3)."""
    y1 = history.get(year - 1)
    y2 = history.get(year - 2)
    y3 = history.get(year - 3)

    if check_type == CHECK_TYPE_3YEAR_AVG:
        vals = [v for v in (y1, y2, y3) if v is not None]
        if not vals:
            return None
        return sum(vals) / len(vals)

    for v in (y1, y2, y3):
        if v is not None:
            return v
    return None


def ytd_pct(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or baseline == 0:
        return None
    return (current - baseline) / baseline


def threshold_exceeded(ytd: float | None, threshold: float | None) -> bool:
    if ytd is None or threshold is None:
        return False
    return abs(ytd) > threshold
