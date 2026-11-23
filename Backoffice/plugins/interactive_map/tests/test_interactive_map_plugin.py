"""Plugin class, manifest, marker normalisation and settings page access for Interactive Map."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from plugins.interactive_map.data_utils import normalize_marker_data
from plugins.interactive_map.plugin import InteractiveMapPlugin

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def test_plugin_class_loads():
    plugin = InteractiveMapPlugin()
    assert plugin.plugin_id == "interactive_map"
    assert plugin.get_blueprint() is not None
    assert [ft.type_name for ft in plugin.get_field_types()] == ["interactive_map"]


def test_manifest_matches_the_plugin_class():
    manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    plugin = InteractiveMapPlugin()
    assert manifest["plugin_id"] == plugin.plugin_id
    assert manifest["version"] == plugin.version
    assert manifest["display_name"] == plugin.display_name


def test_marker_timestamps_are_timezone_aware_utc():
    marker = normalize_marker_data({"lat": 1.5, "lng": 2.5}, {})
    for key in ("created_at", "updated_at"):
        parsed = datetime.fromisoformat(marker[key])
        assert parsed.utcoffset() is not None
        assert parsed.utcoffset().total_seconds() == 0


def test_marker_keeps_an_existing_created_at():
    marker = normalize_marker_data({"lat": 1, "lng": 2, "created_at": "2020-01-01T00:00:00+00:00"}, {})
    assert marker["created_at"] == "2020-01-01T00:00:00+00:00"
    assert marker["updated_at"] != marker["created_at"]


def test_marker_string_property_accepts_a_non_string_value():
    config = {"marker_properties_schema": {"properties": {"label": {"type": "string", "maxLength": 3}}}}
    marker = normalize_marker_data({"lat": 0, "lng": 0, "label": 123456}, config)
    assert marker["label"] == "123"


def test_marker_rejects_out_of_range_coordinates():
    with pytest.raises(ValueError):
        normalize_marker_data({"lat": 91, "lng": 0}, {})
    with pytest.raises(ValueError):
        normalize_marker_data({"lat": 0}, {})


@pytest.mark.db
def test_settings_page_is_registered(app):
    endpoint, values = app.url_map.bind("localhost").match("/admin/plugins/interactive_map/settings")
    assert endpoint
    assert values == {}


@pytest.mark.db
def test_settings_page_is_denied_to_anonymous_users(client):
    response = client.get("/admin/plugins/interactive_map/settings")
    assert response.status_code in (302, 401, 403, 404)
