"""Tests for app/routes/mcp.py — MCP reverse proxy (auth, header hygiene, upstream policy)."""

from unittest.mock import MagicMock, patch

import pytest
import requests

pytestmark = [pytest.mark.unit]

UPSTREAM = "https://mcp.example.test"
PUBLIC_IP = "93.184.216.34"


def _upstream_response(status=200, headers=None, chunks=(b"event: message\ndata: {}\n\n",)):
    upstream = MagicMock()
    upstream.status_code = status
    upstream.headers = headers or {"Content-Type": "text/event-stream"}
    upstream.iter_content.return_value = list(chunks)
    return upstream


@pytest.fixture
def mcp_config(app, monkeypatch):
    import ipaddress

    from app.routes import mcp as mcp_module

    previous = {
        k: app.config.get(k)
        for k in (
            "MCP_UPSTREAM_URL",
            "MCP_PROXY_AUTH_MODE",
            "MCP_PROXY_MAX_BODY_BYTES",
            "MCP_UPSTREAM_ALLOWED_NETWORKS",
            "MCP_UPSTREAM_AUTH_TOKEN",
        )
    }
    app.config["MCP_UPSTREAM_URL"] = UPSTREAM
    app.config["MCP_PROXY_AUTH_MODE"] = "public"
    mcp_module._upstream_verdict_cache.clear()
    monkeypatch.setattr(
        "app.utils.outbound_url.resolve_host_ips",
        lambda host, port=None: (ipaddress.ip_address(PUBLIC_IP),),
    )
    yield app
    for k, v in previous.items():
        app.config[k] = v
    mcp_module._upstream_verdict_cache.clear()


class TestMcpProxyPublicMode:
    def test_returns_404_when_upstream_not_configured(self, app, client):
        previous = app.config.get("MCP_UPSTREAM_URL")
        app.config["MCP_UPSTREAM_URL"] = ""
        try:
            resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        finally:
            app.config["MCP_UPSTREAM_URL"] = previous
        assert resp.status_code == 404

    def test_proxies_post_to_upstream(self, mcp_config, client):
        with patch("app.routes.mcp.requests.request", return_value=_upstream_response()) as mock_request:
            resp = client.post(
                "/mcp",
                data='{"jsonrpc":"2.0","id":1}',
                content_type="application/json",
                headers={"Accept": "application/json, text/event-stream"},
            )

        assert resp.status_code == 200
        assert b"event: message" in resp.data
        mock_request.assert_called_once()
        call = mock_request.call_args
        assert call.kwargs["method"] == "POST"
        assert call.kwargs["url"] == "https://mcp.example.test/mcp"
        assert call.kwargs["allow_redirects"] is False
        assert call.kwargs["stream"] is True

    def test_returns_502_when_upstream_unreachable(self, mcp_config, client):
        with patch("app.routes.mcp.requests.request", side_effect=requests.ConnectionError("boom")):
            resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1})
        assert resp.status_code == 502

    def test_inbound_credentials_are_not_forwarded(self, mcp_config, client):
        client.set_cookie("session", "secret-session")
        with patch("app.routes.mcp.requests.request", return_value=_upstream_response()) as mock_request:
            client.post(
                "/mcp?api_key=leak&keep=1",
                json={"jsonrpc": "2.0", "id": 1},
                headers={
                    "Authorization": "Bearer user-secret",
                    "X-API-Key": "user-secret",
                    "X-Forwarded-For": "10.0.0.1",
                    "Mcp-Session-Id": "abc",
                },
            )
        sent = mock_request.call_args.kwargs
        lowered = {k.lower(): v for k, v in sent["headers"].items()}
        assert "authorization" not in lowered
        assert "cookie" not in lowered
        assert "x-api-key" not in lowered
        assert "x-forwarded-for" not in lowered
        assert lowered["mcp-session-id"] == "abc"
        assert "api_key" not in sent["url"]
        assert sent["url"].endswith("/mcp?keep=1")

    def test_upstream_set_cookie_is_dropped(self, mcp_config, client):
        upstream = _upstream_response(headers={"Content-Type": "application/json", "Set-Cookie": "a=b"})
        with patch("app.routes.mcp.requests.request", return_value=upstream):
            resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1})
        assert "Set-Cookie" not in resp.headers

    def test_dot_segments_in_subpath_are_rejected(self, mcp_config, client):
        with patch("app.routes.mcp.requests.request", return_value=_upstream_response()) as mock_request:
            resp = client.get("/mcp/a/%2e%2e/%2e%2e/admin")
        assert resp.status_code in (400, 404)
        for call in mock_request.call_args_list:
            assert ".." not in call.kwargs["url"]

    def test_upstream_path_is_confined_under_mcp(self, mcp_config, client):
        with patch("app.routes.mcp.requests.request", return_value=_upstream_response()) as mock_request:
            client.get("/mcp/sse/messages")
        assert mock_request.call_args.kwargs["url"] == "https://mcp.example.test/mcp/sse/messages"

    def test_oversized_body_rejected(self, mcp_config, client):
        mcp_config.config["MCP_PROXY_MAX_BODY_BYTES"] = 2048
        with patch("app.routes.mcp.requests.request", return_value=_upstream_response()) as mock_request:
            resp = client.post("/mcp", data=b"x" * 5000, content_type="application/json")
        assert resp.status_code == 413
        mock_request.assert_not_called()

    def test_upstream_auth_token_is_injected(self, mcp_config, client):
        mcp_config.config["MCP_UPSTREAM_AUTH_TOKEN"] = "upstream-token"
        with patch("app.routes.mcp.requests.request", return_value=_upstream_response()) as mock_request:
            client.post("/mcp", json={"jsonrpc": "2.0", "id": 1}, headers={"Authorization": "Bearer user"})
        assert mock_request.call_args.kwargs["headers"]["Authorization"] == "Bearer upstream-token"


class TestMcpUpstreamPolicy:
    @pytest.mark.parametrize(
        "url",
        [
            "http://mcp.example.test",
            "https://169.254.169.254",
            "https://127.0.0.1:8000",
            "https://10.1.2.3",
            "https://user:pw@mcp.example.test",
        ],
    )
    def test_unsafe_upstream_is_rejected(self, mcp_config, client, url):
        mcp_config.config["MCP_UPSTREAM_URL"] = url
        with patch("app.routes.mcp.requests.request") as mock_request:
            resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1})
        assert resp.status_code == 503
        mock_request.assert_not_called()

    def test_hostname_resolving_to_private_ip_is_rejected(self, mcp_config, client, monkeypatch):
        import ipaddress

        monkeypatch.setattr(
            "app.utils.outbound_url.resolve_host_ips",
            lambda host, port=None: (ipaddress.ip_address("169.254.169.254"),),
        )
        with patch("app.routes.mcp.requests.request") as mock_request:
            resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1})
        assert resp.status_code == 503
        mock_request.assert_not_called()

    def test_private_upstream_allowed_only_via_explicit_network_allowlist(self, mcp_config, client, monkeypatch):
        import ipaddress

        monkeypatch.setattr(
            "app.utils.outbound_url.resolve_host_ips",
            lambda host, port=None: (ipaddress.ip_address("10.1.2.3"),),
        )
        mcp_config.config["MCP_UPSTREAM_ALLOWED_NETWORKS"] = "10.1.0.0/16"
        with patch("app.routes.mcp.requests.request", return_value=_upstream_response()):
            resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1})
        assert resp.status_code == 200


class TestMcpProxyRequiredMode:
    @pytest.fixture(autouse=True)
    def _required_mode(self, mcp_config):
        mcp_config.config["MCP_PROXY_AUTH_MODE"] = "required"

    def test_default_mode_is_required(self, mcp_config, client):
        mcp_config.config.pop("MCP_PROXY_AUTH_MODE", None)
        with patch("app.routes.mcp.requests.request") as mock_request:
            resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1})
        assert resp.status_code == 401
        mock_request.assert_not_called()

    def test_anonymous_is_rejected(self, client):
        with patch("app.routes.mcp.requests.request") as mock_request:
            resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1})
        assert resp.status_code == 401
        assert resp.headers.get("WWW-Authenticate", "").startswith("Bearer")
        mock_request.assert_not_called()

    def test_session_user_without_mcp_permission_is_forbidden(self, logged_in_client):
        with patch("app.routes.mcp.requests.request") as mock_request:
            resp = logged_in_client.post("/mcp", json={"jsonrpc": "2.0", "id": 1})
        assert resp.status_code == 403
        mock_request.assert_not_called()

    def test_session_user_with_mcp_permission_is_allowed(self, logged_in_client):
        with patch(
            "app.services.organization.authorization_service.AuthorizationService.has_rbac_permission",
            return_value=True,
        ), patch("app.routes.mcp.requests.request", return_value=_upstream_response()) as mock_request:
            resp = logged_in_client.post("/mcp", json={"jsonrpc": "2.0", "id": 1})
        assert resp.status_code == 200
        mock_request.assert_called_once()

    def test_api_key_without_mcp_capability_is_forbidden(self, client, auth_headers, api_key, db_session):
        from app.services.security.api_key_permissions import DATA_READ, build_permissions_document

        api_key[0].permissions = build_permissions_document([DATA_READ])
        db_session.commit()
        with patch("app.routes.mcp.requests.request") as mock_request:
            resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1}, headers=auth_headers)
        assert resp.status_code == 403
        mock_request.assert_not_called()

    def test_api_key_with_mcp_capability_is_allowed(self, client, auth_headers, api_key, db_session):
        from app.services.security.api_key_permissions import MCP_USE, build_permissions_document

        record = api_key[0] if isinstance(api_key, tuple) else api_key
        record.permissions = build_permissions_document([MCP_USE])
        db_session.commit()
        with patch("app.routes.mcp.requests.request", return_value=_upstream_response()) as mock_request:
            resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1}, headers=auth_headers)
        assert resp.status_code == 200
        forwarded = {k.lower() for k in mock_request.call_args.kwargs["headers"]}
        assert "authorization" not in forwarded

    def test_invalid_api_key_is_rejected(self, client):
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1},
            headers={"Authorization": "Bearer definitely-not-a-key"},
        )
        assert resp.status_code == 401
