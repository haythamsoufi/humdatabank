"""Tests for DbPluginConfig and PluginData model."""

from __future__ import annotations

import copy

import pytest

from app.extensions import db
from app.models.plugin_data import PluginData
from app.plugins.db_config import DbPluginConfig


@pytest.fixture
def plugin_config(app):
    with app.app_context():
        db.create_all()
        PluginData.query.filter_by(plugin_id="test_plugin").delete()
        db.session.commit()
        yield DbPluginConfig(
            "test_plugin",
            {"section_a": {"key": "default"}, "counter": 1},
        )
        PluginData.query.filter_by(plugin_id="test_plugin").delete()
        db.session.commit()


@pytest.mark.unit
def test_get_all_config_without_app_context(tmp_path):
    legacy = tmp_path / "plugin_config.json"
    legacy.write_text('{"counter": 9}', encoding="utf-8")
    cfg = DbPluginConfig("offline_plugin", {"counter": 1, "section_a": {"key": "default"}}, plugin_root=tmp_path)
    data = cfg.get_all_config()
    assert data["counter"] == 9
    assert data["section_a"]["key"] == "default"


@pytest.mark.unit
def test_get_all_config_returns_copy(plugin_config):
    with db.session.begin():
        plugin_config._save_config({"section_a": {"key": "value"}, "counter": 2})
    data = plugin_config.get_all_config()
    data["counter"] = 99
    assert plugin_config.get_all_config()["counter"] == 2


@pytest.mark.unit
def test_get_section_missing_returns_empty_dict(plugin_config):
    assert plugin_config.get_section("missing") == {}


@pytest.mark.unit
def test_update_section_merges(plugin_config):
    assert plugin_config.update_section("section_a", {"extra": True}) is True
    section = plugin_config.get_section("section_a")
    assert section["key"] == "default"
    assert section["extra"] is True


@pytest.mark.unit
def test_set_and_get_setting(plugin_config):
    assert plugin_config.set_setting("prefs", "theme", "dark") is True
    assert plugin_config.get_setting("prefs", "theme") == "dark"
    assert plugin_config.get_setting("prefs", "missing", default="x") == "x"


@pytest.mark.unit
def test_reset_to_defaults(plugin_config):
    plugin_config.update_config({"counter": 42})
    assert plugin_config.reset_to_defaults() is True
    assert plugin_config.get_all_config()["counter"] == 1


@pytest.mark.unit
def test_nested_get_set(plugin_config):
    assert plugin_config.set_nested({"status": "idle"}, "versions", "2027-2028") is True
    bucket = plugin_config.get_nested("versions", "2027-2028")
    assert bucket == {"status": "idle"}


@pytest.mark.unit
def test_legacy_file_import_on_first_access(app, tmp_path):
    legacy = tmp_path / "plugin_config.json"
    legacy.write_text('{"api": {"base_url": "https://example.test"}}', encoding="utf-8")
    with app.app_context():
        db.create_all()
        PluginData.query.filter_by(plugin_id="legacy_plugin").delete()
        db.session.commit()
        cfg = DbPluginConfig("legacy_plugin", {"api": {"timeout": 30}}, plugin_root=tmp_path)
        loaded = cfg.get_all_config()
        assert loaded["api"]["base_url"] == "https://example.test"
        assert loaded["api"]["timeout"] == 30
        row = PluginData.query.filter_by(plugin_id="legacy_plugin").one()
        assert row.data["api"]["base_url"] == "https://example.test"
        PluginData.query.filter_by(plugin_id="legacy_plugin").delete()
        db.session.commit()
