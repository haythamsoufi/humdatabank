"""In-process LRU for Mapbox tiles shared by UPR and Interactive Map proxies."""
from unittest.mock import MagicMock, patch

from plugins.upr.flow import clear_mapbox_tile_cache, mapbox_tile


def _upstream(body=b"\x89PNG", content_type="image/png", status=200):
    response = MagicMock()
    response.status_code = status
    response.headers = {"Content-Type": content_type}
    response.content = body
    return response


def test_mapbox_tile_second_call_skips_upstream(app):
    clear_mapbox_tile_cache()
    fake_config = MagicMock(get_api_key=lambda provider: "test-token")
    with app.app_context():
        with patch("plugins.interactive_map.config.plugin_config", fake_config):
            with patch("requests.get", return_value=_upstream(b"\x89PNG-a")) as get:
                body1, mime1, err1 = mapbox_tile(3, 2, 1)
                body2, mime2, err2 = mapbox_tile(3, 2, 1)
    assert err1 is None and err2 is None
    assert mime1 == mime2 == "image/png"
    assert body1 == body2 == b"\x89PNG-a"
    assert get.call_count == 1
    clear_mapbox_tile_cache()


def test_mapbox_tile_errors_are_not_cached(app):
    clear_mapbox_tile_cache()
    fake_config = MagicMock(get_api_key=lambda provider: "test-token")
    boom = _upstream(b"nope", content_type="text/html", status=200)
    ok = _upstream(b"\x89PNG-ok")
    with app.app_context():
        with patch("plugins.interactive_map.config.plugin_config", fake_config):
            with patch("requests.get", side_effect=[boom, ok]) as get:
                body1, mime1, err1 = mapbox_tile(4, 1, 1)
                body2, mime2, err2 = mapbox_tile(4, 1, 1)
    assert err1 == "upstream" and body1 is None
    assert err2 is None and body2 == b"\x89PNG-ok"
    assert get.call_count == 2
    clear_mapbox_tile_cache()
