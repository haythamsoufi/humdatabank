"""Shared helpers for user profile-summary API payloads (hover cards)."""

from __future__ import annotations

import uuid
from contextlib import suppress
from typing import Any


def collect_arg_strings(args: Any, key: str) -> list[str]:
    """Merge request getlist(key) and optional comma-separated key= single value."""
    raw = args.getlist(key)
    if raw:
        return [str(x).strip() for x in raw if str(x).strip()]
    csv = (args.get(key) or "").strip()
    if csv:
        return [p.strip() for p in csv.split(",") if p.strip()]
    return []


def parse_uuid_list(values: list[str]) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for v in values:
        try:
            u = uuid.UUID(str(v).strip())
        except ValueError:
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def parse_int_user_ids(values: list[str]) -> list[int]:
    out: list[int] = []
    for v in values:
        with suppress(ValueError, TypeError):
            out.append(int(str(v).strip()))
    # dedupe preserving order
    seen: set[int] = set()
    unique: list[int] = []
    for i in out:
        if i not in seen:
            seen.add(i)
            unique.append(i)
    return unique


def role_badge_key_from_rbac_codes(codes: list[str | None]) -> str:
    """
    Coarse role bucket for hover UI (matches user-hover-profile.js themes).

    Order: system_manager > admin (any admin_* or substring admin) >
    focal_point / assignment > default user.
    """
    normalized: list[str] = []
    for raw in codes:
        t = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")
        if t:
            normalized.append(t)
    for token in normalized:
        if "system_manager" in token:
            return "system_manager"
    for token in normalized:
        if "admin" in token:
            return "admin"
    for token in normalized:
        if "focal_point" in token or "assignment_" in token:
            return "focal_point"
    return "user"


def focal_scope_display_lines(
    country_ids: set[int],
    entity_counts: dict[str, int],
    *,
    country_id_to_name_region: dict[int, tuple[str, str]],
    region_to_all_country_ids: dict[str, set[int]],
) -> list[str]:
    """
    Human-readable scope lines for focal-point hover cards.

    - Full DB country coverage -> "Global".
    - Full coverage of a region (all countries in that region) -> region label.
    - If total display units (regions + loose countries + non-country permission rows) <= 5,
      list loose country names and non-country counts by type.
    - Otherwise summarize remainder as a single count after region lines.
    """
    ui = {cid for cid in country_ids if cid in country_id_to_name_region}
    total_in_db = len(country_id_to_name_region)
    other_rows = sum(int(v) for v in entity_counts.values() if int(v) > 0)

    lines: list[str] = []

    if total_in_db > 0 and len(ui) == total_in_db:
        lines.append("Global")
        if other_rows == 0:
            return lines
        if 1 + other_rows <= 5:
            for key, value in sorted(entity_counts.items()):
                v = int(value)
                if v > 0:
                    lines.append(f"{key.replace('_', ' ')}: {v}")
            return lines
        lines.append(f"{other_rows} other assignments")
        return lines

    covered_by_regions: set[int] = set()
    full_region_labels: list[str] = []
    for region in sorted(region_to_all_country_ids.keys()):
        ids = region_to_all_country_ids[region]
        if not ids:
            continue
        if ids <= ui:
            display_region = region.strip() if region.strip() else "Other"
            full_region_labels.append(display_region)
            covered_by_regions |= ids

    loose_ids = ui - covered_by_regions
    loose_names = sorted(country_id_to_name_region[cid][0] for cid in loose_ids)

    units = len(full_region_labels) + len(loose_ids) + other_rows
    for label in full_region_labels:
        lines.append(label)

    if units <= 5:
        if loose_names:
            lines.append(", ".join(loose_names))
        for key, value in sorted(entity_counts.items()):
            v = int(value)
            if v > 0:
                lines.append(f"{key.replace('_', ' ')}: {v}")
        return lines

    if len(loose_ids) + other_rows == 0:
        return lines
    if len(loose_ids) and other_rows:
        lines.append(f"{len(loose_ids)} countries, {other_rows} other assignments")
    elif len(loose_ids):
        lines.append(f"{len(loose_ids)} countries")
    else:
        lines.append(f"{other_rows} assignments")
    return lines


def profile_summary_scope_fields(
    role_badge_key: str,
    country_ids: set[int],
    entity_counts: dict[str, int],
    *,
    country_id_to_name_region: dict[int, tuple[str, str]],
    region_to_all_country_ids: dict[str, set[int]],
) -> dict[str, object]:
    """
    Build scope-related keys for GET profile-summary JSON.

    Focal points: scope_display_lines + legacy counts for older clients.
    Admin / system_manager / default user: omit scope and counts (hover hides them).
    """
    if role_badge_key != "focal_point":
        return {}
    lines = focal_scope_display_lines(
        country_ids,
        entity_counts,
        country_id_to_name_region=country_id_to_name_region,
        region_to_all_country_ids=region_to_all_country_ids,
    )
    out: dict[str, object] = {
        "scope_display_lines": lines,
        "countries_count": len({cid for cid in country_ids if cid in country_id_to_name_region}),
        "entity_counts": dict(entity_counts),
    }
    parts: list[str] = []
    for key, value in sorted(entity_counts.items()):
        v = int(value)
        if v > 0:
            parts.append(f"{key.replace('_', ' ')}: {v}")
    out["entity_summary"] = ", ".join(parts)
    return out
