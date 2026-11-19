"""Checks against the latest approved GO baseline.

Expenditure entered here is indicative. It is not the figure delegation finance
validates in ERP, so it is not part of the bounds.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable


def _money(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(value)


def exceeds_group_budget(
    group_budget,
    activity_budgets: Iterable[tuple[int, object]],
    activity_id: int,
    new_budget,
) -> bool:
    """True when the group's activities would cost more than the approved sector budget."""
    if group_budget is None or new_budget is None:
        return False
    total = Decimal("0")
    for existing_id, amount in activity_budgets:
        total += _money(new_budget if existing_id == activity_id else amount)
    return total > _money(group_budget)


def dates_outside_operation(
    operation_start: date | None,
    operation_end: date | None,
    start: date | None,
    end: date | None,
) -> bool:
    if start and operation_start and start < operation_start:
        return True
    if end and operation_end and end > operation_end:
        return True
    return False


def people_over_cap(cap: int | None, target) -> bool:
    if cap is None or target is None:
        return False
    return Decimal(target) > Decimal(cap)


def dates_need_justification(old_start, old_end, new_start, new_end) -> bool:
    return old_start != new_start or old_end != new_end
