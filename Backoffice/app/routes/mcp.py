"""Reverse proxy for the external Humanitarian Databank MCP server.

Claude and other MCP clients POST JSON-RPC (often SSE) to /mcp. A 302/307 redirect
breaks that flow, so Backoffice forwards the request body to MCP_UPSTREAM_URL instead.

Set MCP_UPSTREAM_URL (no trailing slash), e.g.:
  https://ifrc-databank-mcp-staging.azurewebsites.net

Access control (deny by default):
  ``MCP_PROXY_AUTH_MODE=required`` (default) — caller must present a Backoffice session or an
  API key whose ``permissions`` JSON contains ``{"mcp": true}``.
  ``MCP_PROXY_AUTH_MODE=public`` — explicit opt-in for the anonymous public connector; the same
  header allow-list, body cap, upstream URL policy and (IP based) rate limit still apply.

Only an allow-list of MCP protocol headers is forwarded upstream; inbound cookies, Authorization
and API-key material never leave this process. The upstream host is validated with
``app.utils.outbound_url`` (https, no private / link-local / metadata addresses unless listed in
``MCP_UPSTREAM_ALLOWED_NETWORKS``) and redirects are never followed.
"""

from __future__ import annotations

import hmac
import time
from typing import Optional
from urllib.parse import parse_qsl, quote, urlencode, urlparse

import requests
from flask import Blueprint, Response, abort, current_app, jsonify, request
from flask_login import current_user

from app.extensions import limiter
from app.utils.outbound_url import (
    is_local_dev_environment,
    parse_network_allowlist,
    validate_outbound_url,
)

bp = Blueprint("mcp", __name__)

MCP_API_KEY_PERMISSION = "mcp"
_DEFAULT_MAX_BODY_BYTES = 1024 * 1024
_DEFAULT_RATE_LIMIT = "120 per minute"
_UPSTREAM_VERDICT_TTL_SECONDS = 60

_FORWARDED_REQUEST_HEADERS = frozenset(
    {
        "accept",
        "accept-language",
        "content-type",
        "last-event-id",
        "mcp-protocol-version",
        "mcp-session-id",
        "user-agent",
    }
)

_HOP_BY_HOP_RESPONSE = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-encoding",
        "content-length",
        "set-cookie",
    }
)

_STRIPPED_QUERY_KEYS = frozenset({"api_key", "apikey", "access_token", "token", "key"})

_PROXY_TIMEOUT = (10, 300)
_upstream_verdict_cache: dict[str, tuple[float, bool]] = {}


def _upstream_base() -> str:
    return (current_app.config.get("MCP_UPSTREAM_URL") or "").strip().rstrip("/")


def _validate_upstream(url: str) -> None:
    """Abort 503 unless ``url`` passes the shared outbound URL policy (cached briefly)."""
    now = time.time()
    cached = _upstream_verdict_cache.get(url)
    if cached is not None and now - cached[0] < _UPSTREAM_VERDICT_TTL_SECONDS:
        if cached[1]:
            return
        abort(503)

    dev = is_local_dev_environment()
    result = validate_outbound_url(
        url,
        allow_http=dev,
        allow_private_networks=dev,
        allowed_networks=parse_network_allowlist(current_app.config.get("MCP_UPSTREAM_ALLOWED_NETWORKS")),
    )
    _upstream_verdict_cache[url] = (now, result.ok)
    if not result.ok:
        current_app.logger.error("MCP_UPSTREAM_URL rejected by outbound policy: %s (%r)", result.reason, url)
        abort(503)


def _forward_headers(incoming, upstream_host: str) -> dict[str, str]:
    headers = {
        key: value
        for key, value in incoming.items()
        if key.lower() in _FORWARDED_REQUEST_HEADERS
    }
    headers["Host"] = upstream_host
    token = (current_app.config.get("MCP_UPSTREAM_AUTH_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _safe_query_string() -> str:
    pairs = [
        (k, v)
        for k, v in parse_qsl(request.query_string.decode("utf-8", "replace"), keep_blank_values=True)
        if k.lower() not in _STRIPPED_QUERY_KEYS
    ]
    return urlencode(pairs)


def _proxy_response(upstream_resp: requests.Response) -> Response:
    def generate():
        try:
            for chunk in upstream_resp.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        finally:
            upstream_resp.close()

    response_headers = [
        (key, value)
        for key, value in upstream_resp.headers.items()
        if key.lower() not in _HOP_BY_HOP_RESPONSE
    ]
    return Response(
        generate(),
        status=upstream_resp.status_code,
        headers=response_headers,
    )


def _auth_mode() -> str:
    mode = str(current_app.config.get("MCP_PROXY_AUTH_MODE") or "required").strip().lower()
    return "public" if mode == "public" else "required"


def _presented_api_key() -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return (request.headers.get("X-API-Key") or "").strip()


def _api_key_has_mcp_capability(api_key) -> bool:
    from app.services.security.api_key_permissions import MCP_USE, parse_key_permissions

    return parse_key_permissions(getattr(api_key, "permissions", None)).has(MCP_USE)


def _unauthorized() -> Response:
    resp = jsonify({"success": False, "error": "Authentication required"})
    resp.status_code = 401
    resp.headers["WWW-Authenticate"] = 'Bearer realm="mcp"'
    return resp


def _forbidden() -> Response:
    resp = jsonify({"success": False, "error": "Not authorized for MCP access"})
    resp.status_code = 403
    return resp


def authorize_mcp_request() -> Optional[Response]:
    """Return an error response when the caller may not use the proxy, else ``None``."""
    if _auth_mode() == "public":
        return None

    if getattr(current_user, "is_authenticated", False) and getattr(current_user, "active", True):
        return None

    if not _presented_api_key():
        return _unauthorized()

    from app.models.api_key_management import APIKey
    from app.services.security.api_authentication import authenticate_db_api_key_only
    from app.services.security.api_key_permissions import MCP_USE

    result = authenticate_db_api_key_only(capability=MCP_USE)
    if isinstance(result, APIKey):
        return None if _api_key_has_mcp_capability(result) else _forbidden()
    if result is True:
        return _forbidden()
    return result


def _rate_limit_key() -> str:
    if getattr(current_user, "is_authenticated", False):
        return f"mcp:user:{current_user.get_id()}"
    presented = _presented_api_key()
    if presented:
        secret = str(current_app.config.get("SECRET_KEY") or "").encode("utf-8")
        digest = hmac.digest(secret, presented.encode("utf-8"), "sha256").hex()[:24]
        return "mcp:key:" + digest
    try:
        from app.services.platform.user_analytics_service import get_client_ip

        return f"mcp:ip:{get_client_ip()}"
    except Exception:
        return f"mcp:ip:{request.remote_addr}"


def _rate_limit() -> str:
    return str(current_app.config.get("MCP_PROXY_RATE_LIMIT") or _DEFAULT_RATE_LIMIT)


def _max_body_bytes() -> int:
    try:
        return max(1024, int(current_app.config.get("MCP_PROXY_MAX_BODY_BYTES") or _DEFAULT_MAX_BODY_BYTES))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_BODY_BYTES


def _read_bounded_body() -> bytes:
    limit = _max_body_bytes()
    declared = request.content_length
    if declared is not None and declared > limit:
        abort(413)
    request.max_content_length = limit
    return request.get_data()


def _safe_upstream_path(subpath: str) -> str:
    if not subpath:
        return "/mcp"
    segments = subpath.split("/")
    if any(seg in (".", "..") or "\\" in seg or any(ord(c) < 32 for c in seg) for seg in segments):
        abort(400)
    return "/mcp/" + quote(subpath, safe="/")


@bp.route("/mcp", methods=["GET", "POST", "DELETE", "OPTIONS"], strict_slashes=False)
@bp.route("/mcp/", methods=["GET", "POST", "DELETE", "OPTIONS"])
@bp.route("/mcp/<path:subpath>", methods=["GET", "POST", "DELETE", "OPTIONS"])
@limiter.limit(_rate_limit, key_func=_rate_limit_key)
def mcp_proxy(subpath: str = "") -> Response:
    """Forward MCP streamable-http traffic to the configured upstream MCP host."""
    upstream_base = _upstream_base()
    if not upstream_base:
        abort(404)

    denied = authorize_mcp_request()
    if denied is not None:
        return denied

    _validate_upstream(upstream_base)

    target = upstream_base + _safe_upstream_path(subpath)
    query = _safe_query_string()
    if query:
        target = f"{target}?{query}"

    parsed = urlparse(upstream_base)
    headers = _forward_headers(request.headers, parsed.netloc)
    body = _read_bounded_body() if request.method in ("POST", "PUT", "PATCH") else b""

    try:
        upstream_resp = requests.request(
            method=request.method,
            url=target,
            headers=headers,
            data=body,
            stream=True,
            timeout=_PROXY_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        current_app.logger.warning("MCP upstream request failed: %s", exc)
        abort(502)

    return _proxy_response(upstream_resp)
