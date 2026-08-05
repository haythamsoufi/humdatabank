"""MCP connector icon metadata and route."""

from pathlib import Path

from starlette.testclient import TestClient

import server


def test_icon_asset_exists():
    assert server._ICON_PATH.is_file()


def test_default_icon_url():
    assert server._ICON_URL == "https://databank.ifrc.org/mcp/icon.svg"


def test_icon_route_serves_svg():
    client = TestClient(server.app)
    response = client.get(server._ICON_ROUTE)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.content == Path(server._ICON_PATH).read_bytes()
