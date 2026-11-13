"""Outbound URL policy (SSRF guard) shared by every server-side fetch of an operator/user-influenced URL.

One place answers "may the server connect to this URL?":

- scheme must be ``https`` (``http`` only when the caller opts in or in explicit local dev);
- no embedded credentials;
- optional host allowlist (exact or ``.suffix`` match);
- IP-literal hosts and every DNS answer are rejected when they are loopback, link-local
  (incl. the ``169.254.169.254`` cloud metadata endpoint), RFC1918 / unique-local, CGNAT,
  multicast, reserved or unspecified, unless the host/CIDR is on an explicit allow-list
  (``allowed_networks``) supplied by configuration;
- redirects are never followed implicitly: :func:`request_with_validated_redirects` re-validates
  each hop (and re-resolves DNS) before connecting.

DNS is resolved at validation time and again by the HTTP client at connect time, so a
hostile resolver can still rebind between the two. Keep upstream hosts under operator control
and prefer the allow-list for anything user-supplied.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Sequence
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

_REDIRECT_STATUSES = (301, 302, 303, 307, 308)
_METADATA_HOSTS = frozenset({"metadata.google.internal", "metadata", "instance-data"})
_CGNAT = ipaddress.ip_network("100.64.0.0/10")

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


@dataclass(frozen=True)
class OutboundUrlResult:
    ok: bool
    reason: str = ""
    url: str = ""
    host: str = ""
    resolved_ips: tuple = ()

    def __bool__(self) -> bool:
        return self.ok


def is_local_dev_environment() -> bool:
    """True only for an explicit local dev process (FLASK_CONFIG development/default and DEBUG)."""
    if (os.environ.get("FLASK_CONFIG") or "").strip().lower() not in {"development", "default"}:
        return False
    try:
        from flask import current_app, has_app_context

        return bool(has_app_context() and current_app.config.get("DEBUG", False))
    except Exception:
        return False


def parse_network_allowlist(raw: Any) -> tuple[IPNetwork, ...]:
    """Parse ``"10.0.0.0/8, 127.0.0.1"`` (or an iterable) into networks. Invalid entries are dropped."""
    if raw is None:
        return ()
    items: Iterable[Any]
    if isinstance(raw, str):
        items = raw.split(",")
    else:
        items = raw
    out: list[IPNetwork] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        try:
            out.append(ipaddress.ip_network(text, strict=False))
        except ValueError:
            logger.warning("Ignoring invalid outbound network allow-list entry: %r", text)
    return tuple(out)


def _unwrap(ip: IPAddress) -> IPAddress:
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped
        if mapped is not None:
            return mapped
        sixtofour = ip.sixtofour
        if sixtofour is not None:
            return sixtofour
    return ip


def is_blocked_ip(ip: IPAddress, allowed_networks: Sequence[IPNetwork] = ()) -> bool:
    """True when connecting to ``ip`` must be refused under the default deny policy."""
    ip = _unwrap(ip)
    for net in allowed_networks:
        if ip.version == net.version and ip in net:
            return False
    return bool(
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (ip.version == 4 and ip in _CGNAT)
        or (ip.version == 4 and str(ip) == "169.254.169.254")
    )


def resolve_host_ips(host: str, port: Optional[int] = None) -> tuple[IPAddress, ...]:
    infos = socket.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
    seen: list[IPAddress] = []
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        except ValueError:
            continue
        if ip not in seen:
            seen.append(ip)
    return tuple(seen)


def _host_allowed(host: str, allowed_hosts: Sequence[str]) -> bool:
    return any(host == ah or host.endswith("." + ah) for ah in allowed_hosts)


def validate_outbound_url(
    url: str,
    *,
    allowed_hosts: Optional[Sequence[str]] = None,
    allow_http: bool = False,
    allow_ip_literal: bool = False,
    allowed_ports: Optional[Sequence[int]] = None,
    allowed_networks: Sequence[IPNetwork] = (),
    allow_private_networks: bool = False,
    resolve_dns: bool = True,
    resolver: Optional[Callable[[str, Optional[int]], Sequence[IPAddress]]] = None,
) -> OutboundUrlResult:
    """Validate ``url`` against the outbound policy. Never raises.

    ``allowed_hosts``: when given (even empty), the host must match one entry exactly or as a
    subdomain; an empty list therefore denies everything.
    ``allow_private_networks``: disables the private/loopback block entirely; only pass this from
    :func:`is_local_dev_environment`. Prefer ``allowed_networks`` for production exceptions.
    """
    raw = (url or "").strip()
    if not raw:
        return OutboundUrlResult(False, "URL is required")
    try:
        parsed = urlparse(raw)
        port = parsed.port
    except ValueError:
        return OutboundUrlResult(False, "Invalid URL")

    scheme = (parsed.scheme or "").lower()
    if scheme == "http":
        if not allow_http:
            return OutboundUrlResult(False, "Only https URLs are allowed")
    elif scheme != "https":
        return OutboundUrlResult(False, "Only https URLs are allowed")
    if not parsed.netloc:
        return OutboundUrlResult(False, "Invalid URL")
    if parsed.username or parsed.password:
        return OutboundUrlResult(False, "URL must not include credentials")

    host = (parsed.hostname or "").strip().lower().strip(".")
    if not host:
        return OutboundUrlResult(False, "Invalid URL host")

    if allowed_ports is not None:
        effective = port if port is not None else (443 if scheme == "https" else 80)
        if effective not in allowed_ports:
            return OutboundUrlResult(False, "Port is not allowed")

    literal: Optional[IPAddress] = None
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None and not allow_private_networks:
        if is_blocked_ip(literal, allowed_networks):
            return OutboundUrlResult(False, "URL host is not allowed")
        if not allow_ip_literal:
            return OutboundUrlResult(False, "IP address URLs are not allowed")

    if literal is None and host in _METADATA_HOSTS and not allow_private_networks:
        return OutboundUrlResult(False, "URL host is not allowed")

    if allowed_hosts is not None:
        normalized = [str(h).strip().lower().strip(".") for h in allowed_hosts if str(h).strip()]
        if not normalized:
            return OutboundUrlResult(False, "Outbound host allow-list is not configured")
        if not _host_allowed(host, normalized):
            return OutboundUrlResult(False, "URL host is not allowed")

    resolved: tuple = ()
    if literal is not None:
        resolved = (literal,)
    elif resolve_dns and not allow_private_networks:
        try:
            resolved = tuple((resolver or resolve_host_ips)(host, port))
        except (OSError, UnicodeError) as exc:
            logger.debug("Outbound URL DNS resolution failed for %s: %s", host, exc)
            return OutboundUrlResult(False, "URL host could not be resolved")
        if not resolved:
            return OutboundUrlResult(False, "URL host could not be resolved")
        for ip in resolved:
            if is_blocked_ip(ip, allowed_networks):
                return OutboundUrlResult(False, "URL host resolves to a non-public address")

    return OutboundUrlResult(True, "", raw, host, resolved)


def request_with_validated_redirects(
    method: str,
    url: str,
    *,
    validate: Callable[[str], OutboundUrlResult | tuple[bool, str]],
    max_redirects: int = 3,
    session: Any = None,
    **request_kwargs: Any,
):
    """``requests.request`` that never auto-follows redirects and re-validates every hop.

    Credentials in ``headers``/``auth`` are dropped when a redirect changes the host.
    Raises ``ValueError`` when a hop is rejected or the redirect limit is exceeded.
    """
    import requests

    requester = session.request if session is not None else requests.request
    request_kwargs.pop("allow_redirects", None)
    current = (url or "").strip()
    origin_host = (urlparse(current).hostname or "").lower()

    for _ in range(max_redirects + 1):
        verdict = validate(current)
        ok, reason = (verdict.ok, verdict.reason) if isinstance(verdict, OutboundUrlResult) else verdict
        if not ok:
            raise ValueError(f"Blocked URL: {reason}")

        resp = requester(method, current, allow_redirects=False, **request_kwargs)
        if resp.status_code not in _REDIRECT_STATUSES:
            return resp

        location = (resp.headers.get("Location") or "").strip()
        resp.close()
        if not location:
            raise ValueError("Redirect response missing Location header")
        current = urljoin(current, location)
        if (urlparse(current).hostname or "").lower() != origin_host:
            request_kwargs.pop("auth", None)
            hdrs = {
                k: v
                for k, v in (request_kwargs.get("headers") or {}).items()
                if k.lower() not in {"authorization", "cookie", "proxy-authorization", "x-api-key"}
            }
            request_kwargs["headers"] = hdrs
        if method.upper() in {"POST", "PUT", "PATCH"} and resp.status_code in (301, 302, 303):
            method = "GET"
            request_kwargs.pop("data", None)
            request_kwargs.pop("json", None)

    raise ValueError("Too many redirects")
