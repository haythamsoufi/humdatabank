"""The MCP limiter key must not embed the whole presented API key."""
from unittest.mock import patch

from app.routes import mcp


def _key_for(app, presented, ip="203.0.113.5"):
    with app.test_request_context("/mcp"), \
            patch.object(mcp, "_presented_api_key", return_value=presented), \
            patch.object(mcp, "_client_ip_for_limits", return_value=ip):
        return mcp._rate_limit_key()


def test_key_is_per_prefix_and_client_and_never_contains_the_full_key(app):
    full = "abcdefgh-the-rest-of-a-long-secret-token"
    key = _key_for(app, full)
    assert key == "mcp:key:abcdefgh:203.0.113.5"
    assert full not in key
    assert key != _key_for(app, full, ip="198.51.100.9")


def test_requests_without_a_key_are_limited_by_client_address(app):
    assert _key_for(app, "") == "mcp:ip:203.0.113.5"
