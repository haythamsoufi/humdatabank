"""Canonical client IP resolution.

Single source of truth for "who is calling": every rate limiter, lockout check,
analytics/audit record and dev-only loopback guard must use ``get_client_ip()``.

Trust model: forwarding headers are never read here. When ``TRUST_PROXY_HEADERS``
is enabled, ``ProxyFix`` (app/__init__.py) rewrites ``request.remote_addr`` using
exactly ``PROXY_FIX_X_FOR`` trusted hops, so a client-supplied ``X-Forwarded-For``
prefix cannot change the result. When it is disabled, forwarding headers are
ignored and ``remote_addr`` is the TCP peer.
"""
from __future__ import annotations

import ipaddress
from typing import Optional

from flask import has_request_context, request

UNKNOWN_CLIENT_IP = "unknown"

_LOOPBACK_TEXT = frozenset({"localhost"})
_FORWARDING_HEADERS = ("X-Forwarded-For", "Forwarded", "X-Real-IP")


def _strip_ip_port(ip: Optional[str]) -> Optional[str]:
    """Strip a port suffix (``1.2.3.4:5678`` or ``[::1]:5678``); bare IPv6 is untouched."""
    if not ip or ip == UNKNOWN_CLIENT_IP:
        return ip
    if ip.startswith("["):
        bracket_end = ip.find("]")
        if bracket_end != -1:
            return ip[1:bracket_end]
    elif ip.count(":") == 1:
        return ip.rsplit(":", 1)[0]
    return ip


def normalize_ip(value: Optional[str]) -> str:
    """Return a canonical textual IP, or ``unknown`` when it is not a valid address."""
    candidate = _strip_ip_port((value or "").strip())
    if not candidate:
        return UNKNOWN_CLIENT_IP
    try:
        addr = ipaddress.ip_address(candidate)
    except ValueError:
        return UNKNOWN_CLIENT_IP
    mapped = getattr(addr, "ipv4_mapped", None)
    return str(mapped or addr)


def get_client_ip() -> str:
    """Client IP as seen after ProxyFix (see module docstring)."""
    if not has_request_context():
        return UNKNOWN_CLIENT_IP
    return normalize_ip(request.remote_addr)


def is_loopback_ip(value: Optional[str]) -> bool:
    candidate = (value or "").strip().lower()
    if candidate in _LOOPBACK_TEXT:
        return True
    normalized = normalize_ip(candidate)
    if normalized == UNKNOWN_CLIENT_IP:
        return False
    return ipaddress.ip_address(normalized).is_loopback


def is_loopback_request() -> bool:
    """True only for a direct loopback connection.

    Requests relayed by a same-host reverse proxy also arrive from 127.0.0.1, so any
    forwarding header disqualifies the request: dev-only shortcuts must never be
    reachable through a proxy.
    """
    if not has_request_context():
        return False
    if any(request.headers.get(name) for name in _FORWARDING_HEADERS):
        return False
    return is_loopback_ip(get_client_ip())
