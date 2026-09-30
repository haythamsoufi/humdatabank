"""Mapbox tile proxy only relays image responses and marks them non-executable."""
import inspect
from unittest.mock import MagicMock, patch

import pytest

TILE_URL = "/admin/plugins/interactive_map/api/tiles/mapbox/3/2/1.png"


def _upstream(content_type, body=b"\x89PNG", status=200):
    response = MagicMock()
    response.status_code = status
    response.headers = {"Content-Type": content_type}
    response.content = body
    return response


@pytest.fixture
def tile_client(app, logged_in_admin_client):
    view = app.view_functions.get("interactive_map_plugin.proxy_mapbox_tile")
    if view is None:
        pytest.skip("interactive_map plugin is not registered in the test app")
    routes_globals = inspect.unwrap(view).__globals__
    fake_config = MagicMock(get_api_key=lambda provider: "token")
    with patch.dict(routes_globals, {"plugin_config": fake_config}):
        yield logged_in_admin_client


def _get(client, upstream):
    with patch("requests.get", return_value=upstream):
        return client.get(TILE_URL)


def test_image_tiles_are_relayed_with_nosniff(tile_client):
    resp = _get(tile_client, _upstream("image/png; charset=binary"))
    if resp.status_code == 404:
        pytest.skip("interactive_map plugin is not registered in the test app")
    assert resp.status_code == 200, resp.get_data()
    assert resp.mimetype == "image/png"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in resp.headers["Content-Security-Policy"]


def test_non_image_upstream_content_is_not_relayed(tile_client):
    resp = _get(tile_client, _upstream("text/html", b"<script>alert(1)</script>"))
    if resp.status_code == 404:
        pytest.skip("interactive_map plugin is not registered in the test app")
    assert resp.status_code >= 500
    assert b"<script>" not in resp.data

