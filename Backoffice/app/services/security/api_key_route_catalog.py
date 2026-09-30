"""
Live catalog of routes that accept an API key and the capability each one declares.

The admin UI ("what does this permission unlock?") and the guard test both read this, so
the documentation shown to admins can never drift from what the decorators enforce.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

_KEY_AUTH_MODES = frozenset({"api_key", "api_key_or_session"})
_SKIP_METHODS = frozenset({"HEAD", "OPTIONS"})


@dataclass(frozen=True)
class KeyRoute:
    path: str
    methods: tuple
    endpoint: str
    auth: str
    capability: Optional[str]
    scope_aware: bool


def _unwrap_attr(view, name):
    seen = 0
    while view is not None and seen < 20:
        value = getattr(view, name, None)
        if value is not None:
            return value
        view = getattr(view, "__wrapped__", None)
        seen += 1
    return None


def collect_key_routes(app) -> List[KeyRoute]:
    """Every route that accepts an API key (``_ep_auth`` of api_key / api_key_or_session)."""
    routes: List[KeyRoute] = []
    for rule in app.url_map.iter_rules():
        view = app.view_functions.get(rule.endpoint)
        if view is None:
            continue
        auth = _unwrap_attr(view, "_ep_auth")
        capability = _unwrap_attr(view, "_ep_capability")
        if auth not in _KEY_AUTH_MODES and capability is None:
            continue
        routes.append(
            KeyRoute(
                path=rule.rule,
                methods=tuple(sorted(rule.methods - _SKIP_METHODS)),
                endpoint=rule.endpoint,
                auth=auth or "api_key_or_session",
                capability=capability,
                scope_aware=bool(_unwrap_attr(view, "_ep_scope_aware")),
            )
        )
    routes.sort(key=lambda r: (r.path, r.methods))
    return routes


def routes_by_capability(app) -> Dict[str, List[KeyRoute]]:
    grouped: Dict[str, List[KeyRoute]] = {}
    for route in collect_key_routes(app):
        if route.capability:
            grouped.setdefault(route.capability, []).append(route)
    return grouped


def undeclared_key_routes(app) -> List[KeyRoute]:
    """Key-accepting routes with no declared capability (they are denied at runtime)."""
    return [r for r in collect_key_routes(app) if not r.capability]
