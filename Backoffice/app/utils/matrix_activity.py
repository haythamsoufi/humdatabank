"""Helpers for matrix change summaries in recent activities."""

from __future__ import annotations

from typing import Any, Optional


def matrix_cell_display_value(raw: Any) -> Any:
    """User-visible matrix cell value (aligned with matrix-handler.js display rules)."""
    if raw is None:
        return None
    if isinstance(raw, dict) and (
        "original" in raw or "modified" in raw or "isModified" in raw
    ):
        is_modified = bool(raw.get("isModified"))
        modified = raw.get("modified")
        original = raw.get("original")
        if is_modified:
            if modified is not None and modified != "":
                return modified
            return ""  # PNS/user explicitly cleared the lookup value
        if modified is not None and modified != "":
            return modified
        if original is not None and original != "":
            return original
        return ""
    return raw


def normalize_matrix_activity_display(value: Any) -> Any:
    """Normalize display values so absent/blank/zero compare equal in activity diffs."""
    display = matrix_cell_display_value(value)
    if display is None or display == "":
        return None
    if isinstance(display, bool):
        return 1 if display else 0
    if isinstance(display, (int, float)):
        return None if display == 0 else display
    text = str(display).strip()
    if not text:
        return None
    try:
        num = float(text.replace(",", ""))
        return 0 if num == 0 else num
    except ValueError:
        return text


def matrix_cell_activity_values_differ(old_entry: Any, new_entry: Any) -> bool:
    """True when the user-visible matrix cell value changed."""
    return normalize_matrix_activity_display(old_entry) != normalize_matrix_activity_display(
        new_entry
    )


def trim_matrix_activity_maps(
    old_map: Optional[dict], new_map: Optional[dict]
) -> tuple[Optional[dict], Optional[dict]]:
    """Return trimmed old/new maps containing only cells whose display value changed."""
    if not isinstance(old_map, dict) or not isinstance(new_map, dict):
        return None, None

    keys = {
        key
        for key in set(old_map.keys()) | set(new_map.keys())
        if not (isinstance(key, str) and key.startswith("_"))
    }
    trimmed_old: dict = {"_matrix_change": True}
    trimmed_new: dict = {"_matrix_change": True}

    for key in keys:
        old_entry = old_map.get(key)
        new_entry = new_map.get(key)
        if not matrix_cell_activity_values_differ(old_entry, new_entry):
            continue
        trimmed_old[key] = matrix_cell_display_value(old_entry)
        trimmed_new[key] = matrix_cell_display_value(new_entry)

    if len(trimmed_old) <= 1 and len(trimmed_new) <= 1:
        return None, None
    return trimmed_old, trimmed_new
