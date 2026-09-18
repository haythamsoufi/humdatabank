"""FDRS admin HTTP routes."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_settings_page_route_is_registered(app):
    endpoint, values = app.url_map.bind("localhost").match("/admin/plugins/fdrs/settings")
    assert endpoint == "fdrs.settings_page"
    assert values == {}


@pytest.mark.unit
def test_settings_page_requires_login(client):
    response = client.get("/admin/plugins/fdrs/settings")
    assert response.status_code in (302, 401)


@pytest.mark.unit
def test_settings_page_renders_for_system_manager(logged_in_sm_client):
    response = logged_in_sm_client.get("/admin/plugins/fdrs/settings")
    assert response.status_code == 200
    assert b"FDRS Plugin Settings" in response.data
    assert b"Data Sync" in response.data
