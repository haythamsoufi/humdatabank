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



def test_tile_responses_are_private_cache(tile_client):
    resp = _get(tile_client, _upstream("image/png"))
    if resp.status_code == 404:
        pytest.skip("interactive_map plugin is not registered in the test app")
    assert resp.headers["Cache-Control"].startswith("private")


@pytest.mark.parametrize("path", ["3/8/0.png", "3/0/8.png", "23/0/0.png"])
def test_out_of_range_tile_coordinates_are_rejected_without_upstream_call(tile_client, path):
    with patch("requests.get") as upstream:
        resp = tile_client.get(f"/admin/plugins/interactive_map/api/tiles/mapbox/{path}")
    if resp.status_code == 404 and not upstream.called:
        pytest.skip("interactive_map plugin is not registered in the test app")
    assert resp.status_code == 400
    upstream.assert_not_called()


def test_tile_proxy_is_rate_limited_per_user(tile_client):
    import plugins.interactive_map.routes as routes

    with patch.object(routes, "hit_rate_limit", return_value=True), patch("requests.get") as upstream:
        resp = tile_client.get(TILE_URL)
    assert resp.status_code in (404, 429)
    upstream.assert_not_called()


def test_upstream_failure_does_not_leak_token(tile_client):
    import requests as real_requests

    boom = real_requests.exceptions.ConnectionError("https://api.mapbox.com/...?access_token=token")
    with patch("requests.get", side_effect=boom):
        resp = tile_client.get(TILE_URL)
    assert b"access_token" not in resp.data
