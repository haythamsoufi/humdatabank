"""Tests for app/routes/mcp.py — MCP reverse proxy."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


class TestMcpProxy:
    def test_returns_404_when_upstream_not_configured(self, client):
        resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert resp.status_code == 404

    def test_proxies_post_to_upstream(self, app, client):
        app.config["MCP_UPSTREAM_URL"] = "https://mcp.example.test"

        upstream = MagicMock()
        upstream.status_code = 200
        upstream.headers = {"Content-Type": "text/event-stream"}
        upstream.iter_content.return_value = [b"event: message\ndata: {}\n\n"]

        with patch("app.routes.mcp.requests.request", return_value=upstream) as mock_request:
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

    def test_returns_502_when_upstream_unreachable(self, app, client):
        app.config["MCP_UPSTREAM_URL"] = "https://mcp.example.test"

        with patch(
            "app.routes.mcp.requests.request",
            side_effect=__import__("requests").ConnectionError("boom"),
        ):
            resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1})

        assert resp.status_code == 502
