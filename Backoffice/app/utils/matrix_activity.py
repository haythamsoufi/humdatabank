"""Helpers for matrix change summaries in recent activities."""

from __future__ import annotations

from typing import Any, Optional

# Keep in sync with app.utils.api_serialization.MATRIX_HEADER_KEY_PREFIX
# (selectable-headers.js stores the chosen column-header value under this key).
MATRIX_HEADER_KEY_PREFIX = "col_header|"

# Internal grouping key for selectable column-header changes (col_header|{column}).
# render_matrix_change() translates this to a user-facing "Column header" label.
MATRIX_HEADER_ACTIVITY_ROW = "__col_header__"

# Provenance flags stored alongside matrix data — not user-visible activity.
_ACTIVITY_HIDDEN_KEY_PREFIXES = (
    "col_header_go_unmatched|",
    "row_go_unmatched|",
)


def is_hidden_matrix_activity_key(key: Any) -> bool:
    """True for GO-unmatched flags that must not appear in recent-activity diffs."""
    if not isinstance(key, str):
        return False
    return any(key.startswith(prefix) for prefix in _ACTIVITY_HIDDEN_KEY_PREFIXES)


def split_matrix_activity_cell_key(key: Any) -> tuple[str, str]:
    """Split a matrix disagg key into (row grouping, column label) for activity display.

    Selectable header keys use ``col_header|{columnName}`` (pipe, not underscore) so
    they are not cell data. Splitting those on ``_`` produced ``col`` / ``header|EA3``.
    """
    key_str = str(key)
    if key_str.startswith(MATRIX_HEADER_KEY_PREFIX):
        column_name = key_str[len(MATRIX_HEADER_KEY_PREFIX) :].strip()
        return MATRIX_HEADER_ACTIVITY_ROW, column_name
    if "_" in key_str:
        row_code, col_label = key_str.split("_", 1)
        return row_code, col_label
    return key_str, ""


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
        return None if num == 0 else num
    except ValueError:
        return text


def _is_binary_like_matrix_value(value: Any) -> bool:
    return value in (0, 1, "0", "1", True, False)


def matrix_cell_activity_render_displays(old_v: Any, new_v: Any) -> tuple[str, str]:
    """
    Human-readable old/new strings for matrix activity rows.

    Matches render_matrix_change() coercion so diff detection and HTML output agree.
    """
    if (old_v is None or old_v == "") and _is_binary_like_matrix_value(new_v):
        old_disp = "0"
    else:
        old_disp = "" if old_v is None else str(old_v)

    if (new_v is None or new_v == "") and _is_binary_like_matrix_value(old_v):
        new_disp = "0"
    else:
        new_disp = "" if new_v is None else str(new_v)

    return old_disp, new_disp


def matrix_cell_activity_values_differ(old_entry: Any, new_entry: Any) -> bool:
    """True when the user-visible matrix cell value changed."""
    return normalize_matrix_activity_display(old_entry) != normalize_matrix_activity_display(
        new_entry
    )


def is_matrix_activity_payload(old_value: Any, new_value: Any) -> bool:
    """True when either side is a matrix-style activity payload."""
    return bool(
        (isinstance(old_value, dict) and old_value.get("_matrix_change"))
        or (isinstance(new_value, dict) and new_value.get("_matrix_change"))
    )


def collect_matrix_activity_cell_changes(
    old_value: Any, new_value: Any
) -> dict[str, list[tuple[str, Any, Any]]]:
    """
    Return changed matrix cells grouped by row code.

    Values are raw display values from matrix_cell_display_value(), aligned with
    render_matrix_change() filtering rules.
    """
    old_map = dict(old_value) if isinstance(old_value, dict) else {}
    new_map = dict(new_value) if isinstance(new_value, dict) else {}
    old_map.pop("_matrix_change", None)
    new_map.pop("_matrix_change", None)

    rows: dict[str, list[tuple[str, Any, Any]]] = {}
    for key in sorted(set(old_map.keys()) | set(new_map.keys()), key=str):
        if key is None or is_hidden_matrix_activity_key(key):
            continue
        if normalize_matrix_activity_display(old_map.get(key)) == normalize_matrix_activity_display(
            new_map.get(key)
        ):
            continue

        row_code, col_label = split_matrix_activity_cell_key(key)

        old_v = matrix_cell_display_value(old_map.get(key))
        new_v = matrix_cell_display_value(new_map.get(key))
        old_disp, new_disp = matrix_cell_activity_render_displays(old_v, new_v)
        if old_disp == new_disp:
            continue
        rows.setdefault(row_code, []).append((col_label, old_v, new_v))

    return rows


def matrix_activity_has_visible_changes(old_value: Any, new_value: Any) -> bool:
    """True when a matrix payload contains at least one displayable cell diff."""
    return bool(collect_matrix_activity_cell_changes(old_value, new_value))


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
        and not is_hidden_matrix_activity_key(key)
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
