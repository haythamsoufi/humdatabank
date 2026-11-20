"""Pick the National Society that implements a country project."""

from __future__ import annotations

from typing import Optional, Sequence


def pick_national_society(rows: Sequence) -> Optional[object]:
    """Return the society's row when the country has one clear National Society.

    Active societies win over inactive ones. More than one candidate is left
    unmatched so a free-text name is not stored in its place.
    """
    active = [row for row in rows if getattr(row, "is_active", True)]
    pool = active or list(rows)
    if len(pool) == 1:
        return pool[0]
    return None
