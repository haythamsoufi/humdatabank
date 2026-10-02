"""Historical comparison helpers for the FDRS validation matrix.

The comparison functions live in the core app. This module keeps the FDRS
death-indicator codes and re-exports the shared helpers for existing imports.
"""

from __future__ import annotations

from app.services.validation.history import (
    CHECK_TYPE_3YEAR_AVG,
    CHECK_TYPE_PAST_YEAR,
    baseline_value,
    threshold_exceeded,
    ytd_pct,
)

DEATH_KPI_CODES = frozenset({"KPI_noVolDeathsDuty_Tot", "KPI_PStaffDeathsDuty_Tot"})

__all__ = [
    "CHECK_TYPE_3YEAR_AVG",
    "CHECK_TYPE_PAST_YEAR",
    "DEATH_KPI_CODES",
    "baseline_value",
    "threshold_exceeded",
    "ytd_pct",
]
