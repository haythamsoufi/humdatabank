"""
Per-(method, endpoint) descriptions for routes that automatic activity logging records.

**GET is omitted:** navigations only bump session ``page_views`` (see activity middleware
and session utilities), not ``UserActivityLog`` rows for ``page_view``.
Generated rows live under generated/partials/ (merged in generated/__init__.py).
Regenerate: python scripts/generate_activity_endpoint_catalog.py
Manual overrides in manual_overrides.py win for the same endpoint (wildcard '*' applies to all methods).
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from app.utils.activity_endpoint_catalog.generated import GENERATED_ACTIVITY_SPECS
from app.utils.activity_endpoint_catalog.manual_overrides import MANUAL_ACTIVITY_OVERRIDES
from app.utils.activity_endpoint_catalog.spec import (
    ActivityEndpointSpec,
    fallback_description_for_unmapped,
    lookup_activity_endpoint_spec,
    merge_activity_specs,
)


def _merge_registry() -> Dict[Tuple[str, str], ActivityEndpointSpec]:
    """Merge generated + manual; wildcard '*' replaces all method-specific rows for that endpoint."""
    base = dict(GENERATED_ACTIVITY_SPECS)
    if len(base) != len(set(base.keys())):
        raise RuntimeError("Generated activity catalog contains duplicate keys")
    for (mm, ep), spec in MANUAL_ACTIVITY_OVERRIDES.items():
        if mm == "*":
            remove = [k for k in list(base.keys()) if k[1] == ep]
            for k in remove:
                del base[k]
            base[("*", ep)] = spec
        else:
            base[(mm, ep)] = spec
    return base


ENDPOINT_ACTIVITY_SPECS: Dict[Tuple[str, str], ActivityEndpointSpec] = _merge_registry()


def resolve_activity_catalog_spec(
    method: Optional[str],
    endpoint: Optional[str],
) -> Optional[ActivityEndpointSpec]:
    """Return merged catalog spec for logging / display."""
    return lookup_activity_endpoint_spec(method, endpoint, ENDPOINT_ACTIVITY_SPECS)


__all__ = [
    "ActivityEndpointSpec",
    "ENDPOINT_ACTIVITY_SPECS",
    "resolve_activity_catalog_spec",
    "fallback_description_for_unmapped",
    "lookup_activity_endpoint_spec",
    "merge_activity_specs",
]
