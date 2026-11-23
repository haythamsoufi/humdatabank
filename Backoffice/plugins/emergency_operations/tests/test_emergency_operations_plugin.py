"""Plugin class, manifest and settings page access for Emergency Operations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugins.emergency_operations.plugin import EmergencyOperationsPlugin, EmergencyOperationsFieldType

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def test_plugin_class_loads():
    plugin = EmergencyOperationsPlugin()
    assert plugin.plugin_id == "emergency_operations"
    assert plugin.get_blueprint() is not None
    assert [ft.type_name for ft in plugin.get_field_types()] == ["emergency_operations"]


def test_manifest_matches_the_plugin_class():
    manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    plugin = EmergencyOperationsPlugin()
    assert manifest["plugin_id"] == plugin.plugin_id
    assert manifest["version"] == plugin.version
    assert manifest["display_name"] == plugin.display_name


def test_field_is_display_only():
    field_type = EmergencyOperationsFieldType()
    assert field_type.normalize_value({"anything": 1}, {}) is None


@pytest.mark.parametrize(
    "config, expected",
    [
        ({}, True),
        ({"max_items": 10, "operation_types": ["All"]}, True),
        ({"max_items": 0}, False),
        ({"max_items": 101}, False),
        ({"max_items": "ten"}, False),
        ({"operation_types": "All"}, False),
        ({"operation_types": ["Not a type"]}, False),
    ],
)
def test_validate_config(config, expected, app):
    with app.app_context():
        assert EmergencyOperationsFieldType().validate_config(config) is expected


@pytest.mark.db
def test_settings_page_is_registered(app):
    endpoint, values = app.url_map.bind("localhost").match("/admin/plugins/emergency_operations/settings")
    assert endpoint.startswith("emergency_operations_plugin.")
    assert values == {}


@pytest.mark.db
def test_settings_page_is_denied_to_anonymous_users(client):
    response = client.get("/admin/plugins/emergency_operations/settings")
    assert response.status_code in (302, 401, 403, 404)
