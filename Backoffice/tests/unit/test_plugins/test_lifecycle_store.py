"""Tests for DB-backed plugin lifecycle store and legacy config import."""

from __future__ import annotations

import json

import pytest

from app.extensions import db
from app.models.plugin_data import PluginData
from app.plugins.legacy_config_import import import_missing_plugin_configs
from app.plugins.lifecycle_store import (
    LIFECYCLE_PLUGIN_ID,
    get_updated_at,
    load_active_plugin_ids,
    migrate_from_legacy_state_file,
    save_active_plugin_ids,
)


@pytest.fixture
def plugin_data_db(app):
    with app.app_context():
        db.create_all()
        PluginData.query.filter(PluginData.plugin_id.in_([LIFECYCLE_PLUGIN_ID, "map_plugin", "eo"])).delete(
            synchronize_session=False
        )
        db.session.commit()
        yield
        PluginData.query.filter(PluginData.plugin_id.in_([LIFECYCLE_PLUGIN_ID, "map_plugin", "eo"])).delete(
            synchronize_session=False
        )
        db.session.commit()


@pytest.mark.unit
def test_save_and_load_active_plugin_ids(app, plugin_data_db):
    with app.app_context():
        assert load_active_plugin_ids() == []
        assert save_active_plugin_ids(["upr", "fdrs"]) is True
        assert set(load_active_plugin_ids()) == {"fdrs", "upr"}
        assert get_updated_at() is not None


@pytest.mark.unit
def test_migrate_from_legacy_state_file(app, plugin_data_db, tmp_path):
    state = tmp_path / "plugin_states.json"
    state.write_text(json.dumps({"active_plugin_ids": ["interactive_map"]}), encoding="utf-8")
    with app.app_context():
        migrated = migrate_from_legacy_state_file(state)
        assert migrated == ["interactive_map"]
        assert load_active_plugin_ids() == ["interactive_map"]
        # Second call is a no-op once the row exists
        assert migrate_from_legacy_state_file(state) is None


@pytest.mark.unit
def test_migrate_legacy_active_plugins_key(app, plugin_data_db, tmp_path):
    state = tmp_path / "plugin_states.json"
    state.write_text(json.dumps({"active_plugins": ["Legacy Name"]}), encoding="utf-8")
    with app.app_context():
        migrated = migrate_from_legacy_state_file(state)
        assert migrated == ["Legacy Name"]


@pytest.mark.unit
def test_migrate_skips_corrupt_json(app, plugin_data_db, tmp_path):
    state = tmp_path / "plugin_states.json"
    state.write_text("{NOT JSON}", encoding="utf-8")
    with app.app_context():
        assert migrate_from_legacy_state_file(state) is None
        assert PluginData.query.filter_by(plugin_id=LIFECYCLE_PLUGIN_ID).first() is None


@pytest.mark.unit
def test_import_missing_plugin_configs_inserts_and_skips(app, plugin_data_db, tmp_path):
    map_dir = tmp_path / "interactive_map"
    map_dir.mkdir()
    (map_dir / "plugin_config.json").write_text(
        json.dumps({"api": {"key": "secret"}}),
        encoding="utf-8",
    )
    eo_dir = tmp_path / "emergency_operations"
    eo_dir.mkdir()
    (eo_dir / "plugin_config.json").write_text("{bad", encoding="utf-8")

    with app.app_context():
        db.session.add(PluginData(plugin_id="map_plugin", data={"already": True}))
        db.session.commit()

        imported = import_missing_plugin_configs(
            [map_dir, eo_dir],
            plugin_id_by_dir={map_dir: "map_plugin", eo_dir: "eo"},
        )
        assert imported == []  # map_plugin row exists; eo corrupt
        assert PluginData.query.filter_by(plugin_id="map_plugin").one().data == {"already": True}

        PluginData.query.filter_by(plugin_id="map_plugin").delete()
        db.session.commit()
        (eo_dir / "plugin_config.json").write_text(json.dumps({"feed": 1}), encoding="utf-8")

        imported = import_missing_plugin_configs(
            [map_dir, eo_dir],
            plugin_id_by_dir={map_dir: "map_plugin", eo_dir: "eo"},
        )
        assert set(imported) == {"map_plugin", "eo"}
        assert PluginData.query.filter_by(plugin_id="map_plugin").one().data["api"]["key"] == "secret"
        assert PluginData.query.filter_by(plugin_id="eo").one().data["feed"] == 1


@pytest.mark.unit
def test_store_without_app_context(monkeypatch):
    monkeypatch.setattr("app.plugins.lifecycle_store.has_app_context", lambda: False)
    assert load_active_plugin_ids() == []
    assert get_updated_at() is None
    assert save_active_plugin_ids(["x"]) is False
