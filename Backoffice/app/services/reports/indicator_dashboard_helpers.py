"""P&B-style dashboard table row visibility from indicator type/unit."""

from __future__ import annotations

NS_TABLE_STANDARD = "standard"
NS_TABLE_IMPLEMENTING_COUNT = "implementing_count"
NS_TABLE_NS_UNIT = "ns_unit"


def is_ns_unit(unit: str | None) -> bool:
    return str(unit or "").strip().lower() in {"ns", "nss"}


def ns_table_mode(indicator_type: str | None, unit: str | None) -> str:
    type_text = str(indicator_type or "").strip()
    if type_text == "Distinct" and is_ns_unit(unit):
        return NS_TABLE_IMPLEMENTING_COUNT
    if is_ns_unit(unit):
        return NS_TABLE_NS_UNIT
    return NS_TABLE_STANDARD


def dashboard_table_rows(
    *,
    ns_table_mode: str,
    show_ns_breakdown: bool = True,
) -> tuple[bool, bool]:
    """Return (show_reporting_row, show_implementing_row)."""
    if not show_ns_breakdown:
        return False, False
    if ns_table_mode in {NS_TABLE_IMPLEMENTING_COUNT, NS_TABLE_NS_UNIT}:
        return True, False
    return True, True
