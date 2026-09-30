"""The MCP limiter key must never embed the presented API key."""
from unittest.mock import patch

from app.routes import mcp


def _key_for(app, presented):
    with app.test_request_context("/mcp"), patch.object(mcp, "_presented_api_key", return_value=presented):
        return mcp._rate_limit_key()


def test_key_is_stable_opaque_and_per_presented_value(app):
    first = _key_for(app, "secret-key-value-1")
    assert first == _key_for(app, "secret-key-value-1")
    assert first != _key_for(app, "secret-key-value-2")
    assert first.startswith("mcp:key:")
    assert "secret-key-value" not in first


def test_key_depends_on_the_server_secret(app):
    original = app.config["SECRET_KEY"]
    first = _key_for(app, "same-key")
    app.config["SECRET_KEY"] = original + "-rotated"
    try:
        assert _key_for(app, "same-key") != first
    finally:
        app.config["SECRET_KEY"] = original
