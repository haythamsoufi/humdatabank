"""
Per-endpoint audit catalog: dataclass and lookup helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from app.utils.activity_endpoint_overrides import endpoint_last_segment, strip_endpoint_verb_prefix


@dataclass(frozen=True)
class ActivityEndpointSpec:
    """Curated description and optional activity-type override for audit rows."""

    description: str
    # When set, overrides auto-derived activity_type for logging and consolidated badge.
    activity_type: Optional[str] = None


def merge_activity_specs(
    *dicts: Dict[Tuple[str, str], ActivityEndpointSpec],
    allow_override: bool = True,
) -> Dict[Tuple[str, str], ActivityEndpointSpec]:
    """
    Merge catalog dicts. When allow_override is False, duplicate keys raise ValueError
    (fail-fast when assembling generated partials).
    """
    out: Dict[Tuple[str, str], ActivityEndpointSpec] = {}
    for d in dicts:
        for k, v in d.items():
            if not allow_override and k in out:
                raise ValueError(f"Duplicate activity catalog key: {k!r}")
            out[k] = v
    return out


def lookup_activity_endpoint_spec(
    method: Optional[str],
    endpoint: Optional[str],
    registry: Dict[Tuple[str, str], ActivityEndpointSpec],
) -> Optional[ActivityEndpointSpec]:
    """
    Resolve catalog entry for (HTTP method, Flask endpoint).

    Tries: (METHOD, endpoint), ("*", endpoint).
    METHOD is normalized to upper case.
    """
    if not endpoint:
        return None
    m = (method or "GET").strip().upper() or "GET"
    if (m, endpoint) in registry:
        return registry[(m, endpoint)]
    if ("*", endpoint) in registry:
        return registry[("*", endpoint)]
    return None


def fallback_description_for_unmapped(method: Optional[str], endpoint: Optional[str]) -> str:
    """Last-resort line when no catalog entry exists (dev visibility)."""
    if not endpoint:
        return "Completed action"
    seg = strip_endpoint_verb_prefix(endpoint_last_segment(endpoint))
    readable = seg.replace("_", " ").strip().title() or "action"
    m = (method or "GET").strip().upper() or "GET"
    if m == "GET":
        return f"Session · {readable}"
    if m == "DELETE":
        return f"Deleted {readable}"
    if m in ("PUT", "PATCH"):
        return f"Updated {readable}"
    return f"Completed {readable}"
