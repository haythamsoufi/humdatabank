"""Reverse proxy for the external Humanitarian Databank MCP server.

Claude and other MCP clients POST JSON-RPC (often SSE) to /mcp. A 302/307 redirect
breaks that flow, so Backoffice forwards the request body to MCP_UPSTREAM_URL instead.

Set MCP_UPSTREAM_URL (no trailing slash), e.g.:
  https://ifrc-databank-mcp-staging.azurewebsites.net
"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from flask import Blueprint, Response, abort, current_app, request

bp = Blueprint("mcp", __name__)

_HOP_BY_HOP_REQUEST = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
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
    }
)

_PROXY_TIMEOUT = (10, 300)


def _upstream_base() -> str:
    return (current_app.config.get("MCP_UPSTREAM_URL") or "").strip().rstrip("/")


def _validate_upstream(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        current_app.logger.error("Invalid MCP_UPSTREAM_URL configured: %r", url)
        abort(503)


def _forward_headers(incoming: dict[str, str], upstream_host: str) -> dict[str, str]:
    headers = {
        key: value
        for key, value in incoming.items()
        if key.lower() not in _HOP_BY_HOP_REQUEST
    }
    headers["Host"] = upstream_host
    return headers


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


@bp.route("/mcp", methods=["GET", "POST", "DELETE", "OPTIONS"], strict_slashes=False)
@bp.route("/mcp/", methods=["GET", "POST", "DELETE", "OPTIONS"])
@bp.route("/mcp/<path:subpath>", methods=["GET", "POST", "DELETE", "OPTIONS"])
def mcp_proxy(subpath: str = "") -> Response:
    """Forward MCP streamable-http traffic to the configured upstream MCP host."""
    upstream_base = _upstream_base()
    if not upstream_base:
        abort(404)

    _validate_upstream(upstream_base)

    upstream_path = "/mcp/" + subpath if subpath else "/mcp"
    target = urljoin(upstream_base + "/", upstream_path.lstrip("/"))
    if request.query_string:
        target = f"{target}?{request.query_string.decode()}"

    parsed = urlparse(upstream_base)
    headers = _forward_headers(dict(request.headers), parsed.netloc)

    try:
        upstream_resp = requests.request(
            method=request.method,
            url=target,
            headers=headers,
            data=request.get_data(),
            stream=True,
            timeout=_PROXY_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        current_app.logger.warning("MCP upstream request failed: %s", exc)
        abort(502)

    return _proxy_response(upstream_resp)
