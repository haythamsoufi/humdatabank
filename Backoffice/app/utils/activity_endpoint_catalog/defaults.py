"""
Default description + activity category from endpoint for generated catalog rows.
"""

from __future__ import annotations

import re
from typing import Optional

from app.utils.activity_endpoint_overrides import endpoint_last_segment, strip_endpoint_verb_prefix


def _humanize_snake_tail(tail: str) -> str:
    """Turn ``entity_from_assignment`` → ``Entity From Assignment``."""
    if not tail:
        return ""
    parts = [p for p in tail.strip("_").split("_") if p]
    if not parts:
        return ""
    return " ".join(p.capitalize() for p in parts)


def _strip_outer_wrappers(segment: str) -> str:
    """
    Strip ``api_`` / ``get_`` / ``fetch_`` so ``api_delete_document`` → ``delete_document``.

    Does **not** strip ``delete_`` / ``update_`` — those carry semantic meaning for descriptions.
    """
    s = segment
    for _ in range(3):
        low = s.lower()
        if low.startswith("api_") and len(s) > 4:
            s = s[4:]
        elif low.startswith("get_") and len(s) > 4:
            s = s[4:]
        elif low.startswith("fetch_") and len(s) > 6:
            s = s[6:]
        else:
            break
    return s


# Longest prefix first — first match wins.
_POST_VERB_PREFIXES: tuple[tuple[str, str], ...] = (
    ("regenerate_", "Regenerated"),
    ("deactivate_", "Deactivated"),
    ("duplicate_", "Duplicated"),
    ("reprocess_", "Reprocessed"),
    ("redetect_", "Redetected"),
    ("process_", "Processed"),
    ("uninstall_", "Uninstalled"),
    ("configure_", "Configured"),
    ("decline_", "Declined"),
    ("approve_", "Approved"),
    ("answer_", "Answered"),
    ("discard_", "Discarded"),
    ("generate_", "Generated"),
    ("cleanup_", "Cleaned up"),
    ("activate_", "Activated"),
    ("import_", "Imported"),
    ("export_", "Exported"),
    ("preview_", "Previewed"),
    ("resolve_", "Resolved"),
    ("cancel_", "Cancelled"),
    ("install_", "Installed"),
    ("submit_", "Submitted"),
    ("send_", "Sent"),
    ("deploy_", "Deployed"),
    ("reorder_", "Reordered"),
    ("compile_", "Compiled"),
    ("extract_", "Extracted"),
    ("reload_", "Reloaded"),
    ("archive_", "Archived"),
    ("remove_", "Removed"),
    ("delete_", "Deleted"),
    ("update_", "Updated"),
    ("toggle_", "Toggled"),
    ("reject_", "Rejected"),
    ("reopen_", "Reopened"),
    ("create_", "Created"),
    ("edit_", "Edited"),
    ("sync_", "Synced"),
    ("close_", "Closed"),
    ("clear_", "Cleared"),
    ("manage_", "Managed"),
    ("add_", "Added"),
    ("new_", "Created"),
    ("run_", "Ran"),
)


def _describe_post_inner(inner: str) -> str:
    """Human description for POST from view name (after ``api_`` strip)."""
    il = inner.lower()
    # Compound prefixes (must run before generic ``delete_`` / ``extract_``).
    if il.startswith("delete_removed_"):
        return f"Deleted {_humanize_snake_tail(inner[len('delete_removed_') :])}"
    if il.startswith("extract_update_"):
        return f"Extracted {_humanize_snake_tail(inner[len('extract_update_') :])}"
    if il.startswith("kickout_"):
        return f"Kicked out {_humanize_snake_tail(inner[len('kickout_') :])}"
    # ``import_*_cancel`` / ``*_bulk_cancel`` — suffix must win over ``import_`` / ``bulk_``.
    if il.endswith("_cancel") and len(inner) > len("_cancel"):
        base = inner[: -len("_cancel")]
        return f"Cancelled {_humanize_snake_tail(base)}"
    if il.startswith("bulk_"):
        tail = inner[5:]
        tl = tail.lower()
        if tl.startswith("update_"):
            return f"Bulk updated {_humanize_snake_tail(tail[7:])}"
        if tl.startswith("remove_"):
            return f"Bulk removed {_humanize_snake_tail(tail[7:])}"
        if tl.startswith("enable_"):
            return f"Bulk enabled {_humanize_snake_tail(tail[7:])}"
        return f"Bulk {_humanize_snake_tail(tail)}"

    for prefix, label in _POST_VERB_PREFIXES:
        if il.startswith(prefix):
            rest = _humanize_snake_tail(inner[len(prefix) :])
            return f"{label} {rest}".strip() if rest else label

    seg = strip_endpoint_verb_prefix(inner)
    return f"Completed {_humanize_snake_tail(seg)}"


def describe_get_request_without_catalog(endpoint: Optional[str]) -> str:
    """
    Human-readable line for GET / page_view when no catalog row applies.

    GET traffic is reflected in session ``page_views``, not as audited actions; wording
    is neutral (no ``Viewed`` / ``Fetched`` audit phrasing).
    """
    if not endpoint:
        return "Session ·"
    last = endpoint_last_segment(endpoint)
    if last.startswith("api_"):
        rest = last[4:]
        if rest.lower().startswith("get_"):
            rest = rest[4:]
        readable = rest.replace("_", " ").strip().title()
        return f"Session · {readable}" if readable else "Session ·"
    segment = re.sub(
        r"^(api_|get_|post_|put_|delete_|fetch_)",
        "",
        last,
        flags=re.I,
    )
    readable = segment.replace("_", " ").strip().title()
    return f"Session · {readable}" if readable else "Session ·"


def blueprint_name(endpoint: str) -> str:
    if not endpoint or "." not in endpoint:
        return ""
    return endpoint.split(".", 1)[0]


def activity_category_for_endpoint(endpoint: str) -> str:
    """
    Map Flask blueprint to a finite audit badge key (see activity_types.CANONICAL_ACTIVITY_TYPES).
    """
    bp = blueprint_name(endpoint)
    if bp in (
        "ai_management",
        "ai_documents",
        "ai_v2",
        "ai",
        "ai_ws",
    ):
        return "admin_ai"
    if bp in ("content_management",):
        return "admin_content"
    if bp in ("embed_management",):
        return "admin_embed"
    if bp in ("assignment_management", "excel"):
        return "admin_assignments"
    if bp in ("organization",):
        return "admin_organization"
    if bp in ("system_admin", "template_special"):
        return "admin_system"
    if bp in ("user_management",):
        return "admin_users"
    if bp in ("form_builder", "forms", "forms_api", "forms_validation_summary"):
        return "admin_forms"
    if bp in ("analytics", "admin_analytics_api", "data_exploration", "governance_dashboard"):
        return "admin_analytics"
    if bp in ("utilities", "documentation", "help_docs"):
        return "admin_utilities"
    if bp in ("settings", "api_key_management", "api_management", "rbac_management", "security_dashboard"):
        return "admin_settings"
    if bp in ("plugin_management", "plugins"):
        return "admin_plugin"
    if bp in ("notifications", "notification"):
        return "admin_notifications"
    if bp in ("monitoring",):
        return "admin_monitoring"
    if bp in ("main", "public", "auth"):
        return "admin_portal"
    return "admin_other"


def default_generated_description(method: str, endpoint: str) -> str:
    """
    Deterministic sentence for a (method, endpoint) pair in the generated catalog.

    Uses the Flask view name (last segment), not HTTP path. Recognises common verb
    prefixes (``delete_*`` on POST, ``remove_*`` on DELETE, ``update_*`` on PUT) so
    we do not emit ``Completed Document`` or ``Updated Update …`` artefacts.
    """
    m = (method or "GET").strip().upper() or "GET"
    if m == "GET":
        raise ValueError(
            "GET is excluded from the activity catalog (session page views only); "
            "see should_exclude_from_activity_catalog"
        )

    last = endpoint_last_segment(endpoint)
    if not last:
        return "Completed action"

    inner = _strip_outer_wrappers(last)
    il = inner.lower()

    if m == "DELETE":
        if il.startswith("delete_removed_"):
            return f"Deleted {_humanize_snake_tail(inner[len('delete_removed_') :])}"
        if il.startswith("remove_"):
            return f"Removed {_humanize_snake_tail(inner[7:])}"
        if il.startswith("delete_"):
            tail = inner[7:]
            if tail.lower().startswith("removed_"):
                return f"Deleted {_humanize_snake_tail(tail[8:])}"
            return f"Deleted {_humanize_snake_tail(tail)}"
        seg = strip_endpoint_verb_prefix(last)
        return f"Deleted {_humanize_snake_tail(seg)}"

    if m in ("PUT", "PATCH"):
        if il.startswith("update_"):
            return f"Updated {_humanize_snake_tail(inner[7:])}"
        if il.startswith("edit_"):
            return f"Edited {_humanize_snake_tail(inner[5:])}"
        if il.startswith("delete_"):
            return f"Deleted {_humanize_snake_tail(inner[7:])}"
        seg = strip_endpoint_verb_prefix(last)
        sl = seg.lower()
        if sl.startswith("update_"):
            return f"Updated {_humanize_snake_tail(seg[7:])}"
        if sl.startswith("edit_"):
            return f"Edited {_humanize_snake_tail(seg[5:])}"
        return f"Updated {_humanize_snake_tail(seg)}"

    if m == "POST":
        return _describe_post_inner(inner)

    return f"Completed {_humanize_snake_tail(strip_endpoint_verb_prefix(last))}"


def catalog_display_description(method: str, endpoint: str) -> str:
    """
    Description for the admin catalog HTML/CSV viewer.

    Uses :func:`default_generated_description` plus ``MANUAL_ACTIVITY_OVERRIDES`` so the
    page reflects current ``defaults.py`` logic without relying on merged generated
    partials that were loaded at import time (stale until the server restarts).
    """
    from app.utils.activity_endpoint_catalog.manual_overrides import MANUAL_ACTIVITY_OVERRIDES

    if (method, endpoint) in MANUAL_ACTIVITY_OVERRIDES:
        return MANUAL_ACTIVITY_OVERRIDES[(method, endpoint)].description
    if ("*", endpoint) in MANUAL_ACTIVITY_OVERRIDES:
        return MANUAL_ACTIVITY_OVERRIDES[("*", endpoint)].description
    try:
        return default_generated_description(method, endpoint)
    except ValueError:
        return ""
