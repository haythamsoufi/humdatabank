"""
Comprehensive tests for app/plugins/manager.py
Targets 100% code coverage of PluginManager.
"""
import json
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open


# ---------------------------------------------------------------------------
# Helpers for building real plugin directories on disk
# ---------------------------------------------------------------------------

PLUGIN_PY_TEMPLATE = """\
from app.plugins.base import BasePlugin, BaseFieldType
from typing import Dict, List, Any, Optional
from flask import Blueprint


class SampleFieldType(BaseFieldType):
    @property
    def type_name(self): return "{type_name}"
    @property
    def display_name(self): return "Sample Field"
    @property
    def category(self): return "input"
    def get_form_builder_config(self): return {{"fields": []}}
    def get_entry_form_config(self): return {{"template": "field.html", "es_module_path": "/j.js", "es_module_class": "C"}}
    def validate_config(self, c): return True


class SamplePlugin(BasePlugin):
    @property
    def plugin_id(self): return "{plugin_id}"
    @property
    def display_name(self): return "{display_name}"
    @property
    def version(self): return "1.0.0"
    def get_field_types(self):
        return [SampleFieldType()]
"""


def _create_plugin_dir(base_dir: Path, plugin_id: str, display_name: str = None, type_name: str = None):
    """Write a minimal plugin directory to *base_dir/plugin_id*."""
    d = base_dir / plugin_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "__init__.py").write_text("")
    code = PLUGIN_PY_TEMPLATE.format(
        plugin_id=plugin_id,
        display_name=display_name or plugin_id.replace("_", " ").title(),
        type_name=type_name or f"{plugin_id}_type",
    )
    (d / "plugin.py").write_text(code)
    return d


def _make_flask_app(tmp_path: Path, plugin_dir: Path = None):
    """Return a real Flask app whose root_path / instance_path point at tmp_path."""
    from flask import Flask
    app = Flask(__name__, instance_path=str(tmp_path / "instance"))
    app.config["TESTING"] = True
    (tmp_path / "instance").mkdir(exist_ok=True)
    # Override root_path so PluginManager scans the right dirs
    app.root_path = str(tmp_path / "app")
    (tmp_path / "app").mkdir(exist_ok=True)
    return app


def _make_manager(tmp_path: Path, plugin_ids=None):
    """Create a PluginManager with real plugin dirs at tmp_path/plugins."""
    from app.plugins.manager import PluginManager

    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(exist_ok=True)

    app = _make_flask_app(tmp_path)

    # Inject the tmp plugins dir into plugin_directories
    with patch("app.plugins.manager.utcnow") as mock_utcnow:
        mock_utcnow.return_value.isoformat.return_value = "2026-01-01T00:00:00"
        pm = PluginManager(app)
        pm.plugin_directories = [plugins_dir]

    if plugin_ids:
        for pid in plugin_ids:
            _create_plugin_dir(plugins_dir, pid)

    return pm, plugins_dir


# ---------------------------------------------------------------------------
# __init__ and state loading
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPluginManagerInit:
    def test_creates_with_empty_state(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        assert pm.plugins == {}
        assert pm.active_plugins == set()
        assert pm.field_types == {}

    def test_loads_existing_state_file(self, tmp_path):
        """Active plugin ids are read from the state file on init."""
        (tmp_path / "instance").mkdir(exist_ok=True)
        state_file = tmp_path / "instance" / "plugin_states.json"
        state_file.write_text(json.dumps({"active_plugin_ids": ["plugin_a", "plugin_b"]}))

        app = _make_flask_app(tmp_path)
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            from app.plugins.manager import PluginManager
            pm = PluginManager(app)

        assert "plugin_a" in pm._raw_active_tokens

    def test_loads_legacy_active_plugins_key(self, tmp_path):
        (tmp_path / "instance").mkdir(exist_ok=True)
        state_file = tmp_path / "instance" / "plugin_states.json"
        state_file.write_text(json.dumps({"active_plugins": ["Legacy Plugin"]}))

        app = _make_flask_app(tmp_path)
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            from app.plugins.manager import PluginManager
            pm = PluginManager(app)

        assert "Legacy Plugin" in pm._raw_active_tokens

    def test_handles_corrupt_state_file(self, tmp_path):
        (tmp_path / "instance").mkdir(exist_ok=True)
        (tmp_path / "instance" / "plugin_states.json").write_text("{NOT JSON}")

        app = _make_flask_app(tmp_path)
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            from app.plugins.manager import PluginManager
            pm = PluginManager(app)

        # Should not crash; falls back to empty
        assert pm._raw_active_tokens is None

    def test_loads_discovery_cache(self, tmp_path):
        (tmp_path / "instance").mkdir(exist_ok=True)
        cache_data = {"cache": {"somekey": {"hash": "abc", "plugins": []}}}
        (tmp_path / "instance" / "plugin_discovery_cache.json").write_text(
            json.dumps(cache_data)
        )
        app = _make_flask_app(tmp_path)
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            from app.plugins.manager import PluginManager
            pm = PluginManager(app)
        assert pm._discovery_cache != {}

    def test_handles_corrupt_discovery_cache(self, tmp_path):
        (tmp_path / "instance").mkdir(exist_ok=True)
        (tmp_path / "instance" / "plugin_discovery_cache.json").write_text("{BAD}")
        app = _make_flask_app(tmp_path)
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            from app.plugins.manager import PluginManager
            pm = PluginManager(app)
        assert pm._discovery_cache == {}


# ---------------------------------------------------------------------------
# _save_plugin_states
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSavePluginStates:
    def test_writes_state_file(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        pm.active_plugins = {"plugin_a", "plugin_b"}

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm._save_plugin_states()

        data = json.loads((tmp_path / "instance" / "plugin_states.json").read_text())
        assert set(data["active_plugin_ids"]) == {"plugin_a", "plugin_b"}

    def test_processes_pending_state_updates(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        pm._pending_state_updates = [("plugin_a", "activated"), ("plugin_b", "deactivated")]

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm._save_plugin_states()

        # Pending updates should be cleared after processing
        assert pm._pending_state_updates == []

    def test_handles_write_error_gracefully(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        with patch("builtins.open", side_effect=OSError("no perm")):
            with patch("app.plugins.manager.utcnow") as m:
                m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
                pm._save_plugin_states()  # Should not raise


# ---------------------------------------------------------------------------
# _save_discovery_cache
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSaveDiscoveryCache:
    def test_writes_cache_file(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        pm._discovery_cache = {"key": {"hash": "h", "plugins": []}}

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm._save_discovery_cache()

        content = json.loads((tmp_path / "instance" / "plugin_discovery_cache.json").read_text())
        assert "cache" in content

    def test_handles_error_gracefully(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        with patch("builtins.open", side_effect=OSError("fail")):
            with patch("app.plugins.manager.utcnow") as m:
                m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
                pm._save_discovery_cache()  # Should not raise


# ---------------------------------------------------------------------------
# _get_directory_hash
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetDirectoryHash:
    def test_returns_empty_string_for_missing_dir(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        result = pm._get_directory_hash(tmp_path / "nonexistent")
        assert result == ""

    def test_returns_hash_for_existing_dir(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")
        result = pm._get_directory_hash(plugins_dir)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_plugin_json_in_hash(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        pd = plugins_dir / "plugin_a"
        pd.mkdir()
        (pd / "__init__.py").write_text("")
        (pd / "plugin.json").write_text('{"plugin_id": "plugin_a", "version": "1.0.0"}')
        result = pm._get_directory_hash(plugins_dir)
        assert result

    def test_returns_timestamp_string_on_error(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        with patch("pathlib.Path.iterdir", side_effect=OSError("perm")):
            result = pm._get_directory_hash(tmp_path)
        # Fallback is a timestamp string (float as string)
        float(result)  # Should not raise


# ---------------------------------------------------------------------------
# _is_plugin_directory and _contains_plugins
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPluginDirectoryChecks:
    def test_is_plugin_directory_with_plugin_py(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        d = tmp_path / "my_plugin"
        d.mkdir()
        (d / "__init__.py").write_text("")
        (d / "plugin.py").write_text("")
        assert pm._is_plugin_directory(d) is True

    def test_is_plugin_directory_with_plugin_json(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        d = tmp_path / "my_plugin"
        d.mkdir()
        (d / "__init__.py").write_text("")
        (d / "plugin.json").write_text("{}")
        assert pm._is_plugin_directory(d) is True

    def test_is_plugin_directory_false_no_init(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        d = tmp_path / "my_plugin"
        d.mkdir()
        (d / "plugin.py").write_text("")
        assert pm._is_plugin_directory(d) is False

    def test_is_plugin_directory_false_no_plugin_file(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        d = tmp_path / "my_plugin"
        d.mkdir()
        (d / "__init__.py").write_text("")
        assert pm._is_plugin_directory(d) is False

    def test_contains_plugins_true(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        parent = tmp_path / "group"
        parent.mkdir()
        sub = parent / "a_plugin"
        sub.mkdir()
        (sub / "__init__.py").write_text("")
        (sub / "plugin.py").write_text("")
        assert pm._contains_plugins(parent) is True

    def test_contains_plugins_false(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        parent = tmp_path / "empty_group"
        parent.mkdir()
        assert pm._contains_plugins(parent) is False


# ---------------------------------------------------------------------------
# discover_plugins
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDiscoverPlugins:
    def test_returns_empty_for_nonexistent_dirs(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        pm.plugin_directories = [tmp_path / "nonexistent"]
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.discover_plugins()
        assert result == []

    def test_discovers_plugins_by_scanning(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.discover_plugins()
        assert any("plugin_a" in p for p in result)

    def test_uses_cache_when_hash_matches(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")

        # Build the real hash first
        real_hash = pm._get_directory_hash(plugins_dir)
        pm._discovery_cache[str(plugins_dir)] = {
            "hash": real_hash,
            "plugins": [str(plugins_dir / "plugin_a")],
            "last_scan": "2026-01-01T00:00:00",
        }
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.discover_plugins()
        assert str(plugins_dir / "plugin_a") in result

    def test_updates_cache_when_hash_changes(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")

        pm._discovery_cache[str(plugins_dir)] = {
            "hash": "STALE_HASH",
            "plugins": [],
            "last_scan": "2020-01-01T00:00:00",
        }
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.discover_plugins()
        assert any("plugin_a" in p for p in result)

    def test_scans_subgroup_directories(self, tmp_path):
        """Directories that themselves contain plugins (nested scan)."""
        pm, plugins_dir = _make_manager(tmp_path)
        group_dir = plugins_dir / "group"
        group_dir.mkdir()
        _create_plugin_dir(group_dir, "nested_plugin")

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.discover_plugins()
        assert any("nested_plugin" in p for p in result)


# ---------------------------------------------------------------------------
# _load_plugin and helpers
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestLoadPlugin:
    def test_loads_python_plugin(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        pd = _create_plugin_dir(plugins_dir, "plugin_a")
        plugin = pm._load_plugin(str(pd))
        assert plugin is not None
        assert plugin.plugin_id == "plugin_a"

    def test_returns_none_when_no_plugin_file(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        d = tmp_path / "empty_dir"
        d.mkdir()
        result = pm._load_plugin(str(d))
        assert result is None

    def test_loads_json_plugin(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        pd = plugins_dir / "json_plugin"
        pd.mkdir()
        (pd / "__init__.py").write_text("")
        (pd / "plugin.json").write_text(json.dumps({
            "plugin_id": "json_plugin",
            "name": "JSON Plugin",
            "version": "2.0.0",
        }))
        plugin = pm._load_plugin(str(pd))
        assert plugin is not None
        assert plugin.plugin_id == "json_plugin"

    def test_handles_bad_python_plugin(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        pd = plugins_dir / "bad_plugin"
        pd.mkdir()
        (pd / "__init__.py").write_text("")
        (pd / "plugin.py").write_text("THIS IS NOT VALID PYTHON !!!!")
        result = pm._load_plugin(str(pd))
        assert result is None

    def test_handles_bad_json_plugin(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        pd = plugins_dir / "bad_json"
        pd.mkdir()
        (pd / "__init__.py").write_text("")
        (pd / "plugin.json").write_text("{NOT JSON")
        result = pm._load_plugin(str(pd))
        assert result is None

    def test_uses_cached_module_for_same_file(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        pd = _create_plugin_dir(plugins_dir, "plugin_a")
        # Load once to populate cache
        pm._load_plugin(str(pd))
        # Load again – should use cache (module_key matches)
        plugin = pm._load_plugin(str(pd))
        assert plugin is not None

    def test_extract_plugin_class_returns_none_when_no_class(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        mock_module = MagicMock()
        mock_module.__dir__ = MagicMock(return_value=["not_a_class"])
        mock_module.not_a_class = "just a string"
        result = pm._extract_plugin_class(mock_module)
        assert result is None

    def test_extract_plugin_class_handles_exception(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        mock_module = MagicMock()
        # Make dir() raise inside
        with patch("builtins.dir", side_effect=RuntimeError("boom")):
            result = pm._extract_plugin_class(mock_module)
        assert result is None


# ---------------------------------------------------------------------------
# _create_plugin_class_from_json
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCreatePluginClassFromJson:
    def test_dynamic_plugin_uses_display_name_key(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        cls = pm._create_plugin_class_from_json({
            "plugin_id": "dyn_plugin",
            "display_name": "Dynamic Plugin",
            "version": "3.0.0",
        })
        inst = cls()
        assert inst.plugin_id == "dyn_plugin"
        assert inst.display_name == "Dynamic Plugin"

    def test_dynamic_plugin_falls_back_to_id_key(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        cls = pm._create_plugin_class_from_json({"id": "fallback_id"})
        inst = cls()
        assert inst.plugin_id == "fallback_id"

    def test_dynamic_plugin_falls_back_to_slug_key(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        cls = pm._create_plugin_class_from_json({"slug": "slug_plugin"})
        inst = cls()
        assert inst.plugin_id == "slug_plugin"

    def test_dynamic_plugin_uses_unknown_when_no_id(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        cls = pm._create_plugin_class_from_json({})
        inst = cls()
        assert inst.plugin_id == "unknown_plugin"

    def test_dynamic_plugin_get_field_types_skips_none(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        cls = pm._create_plugin_class_from_json({
            "plugin_id": "x",
            "field_types": [{"type_name": "x_type"}],
        })
        inst = cls()
        # _create_field_type_from_json returns None → field_types is empty
        assert inst.get_field_types() == []


# ---------------------------------------------------------------------------
# load_plugins
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestLoadPlugins:
    def test_loads_discovered_plugins(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.load_plugins()

        assert "plugin_a" in result

    def test_skips_duplicate_plugins(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()
            # Second call with same plugins
            initial_count = len(pm.plugins)
            pm.load_plugins()

        assert len(pm.plugins) == initial_count

    def test_logs_folder_name_mismatch(self, tmp_path):
        """If plugin_id doesn't match folder name, logs error."""
        pm, plugins_dir = _make_manager(tmp_path)
        pd = _create_plugin_dir(plugins_dir, "folder_name")

        # Rewrite plugin.py so plugin_id differs from folder name
        mismatched_code = PLUGIN_PY_TEMPLATE.format(
            plugin_id="different_id",
            display_name="Mismatch Plugin",
            type_name="mismatch_type",
        )
        (pd / "plugin.py").write_text(mismatched_code)

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()

        # The plugin is still loaded despite the mismatch warning
        assert "different_id" in pm.plugins

    def test_handles_load_exception(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")

        with patch.object(pm, "_load_plugin", side_effect=RuntimeError("crash")):
            with patch("app.plugins.manager.utcnow") as m:
                m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
                # Should not raise
                pm.load_plugins()


# ---------------------------------------------------------------------------
# _resolve_active_plugins
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResolveActivePlugins:
    def test_all_active_when_no_persisted_tokens(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()

        pm._raw_active_tokens = None
        pm._resolve_active_plugins()
        assert "plugin_a" in pm.active_plugins

    def test_resolves_by_plugin_id(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()

        pm._raw_active_tokens = ["plugin_a"]
        pm._resolve_active_plugins()
        assert "plugin_a" in pm.active_plugins

    def test_resolves_legacy_display_name(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a", display_name="Legacy Display")

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()

        pm._raw_active_tokens = ["Legacy Display"]
        pm._resolve_active_plugins()
        assert "plugin_a" in pm.active_plugins

    def test_empty_tokens_means_all_inactive(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()

        pm._raw_active_tokens = []
        pm._resolve_active_plugins()
        assert "plugin_a" not in pm.active_plugins


# ---------------------------------------------------------------------------
# _is_existing_plugin
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestIsExistingPlugin:
    def test_returns_true_when_state_file_exists(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        pm.state_file_path.parent.mkdir(parents=True, exist_ok=True)
        pm.state_file_path.write_text('{"active_plugin_ids": []}')
        assert pm._is_existing_plugin("anything") is True

    def test_returns_false_when_state_file_missing(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        assert pm._is_existing_plugin("anything") is False

    def test_returns_false_on_exception(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        # Create the state file so exists() returns True, then make open() fail
        pm.state_file_path.parent.mkdir(parents=True, exist_ok=True)
        pm.state_file_path.write_text("{}")
        with patch("builtins.open", side_effect=OSError("fail")):
            result = pm._is_existing_plugin("anything")
        assert result is False


# ---------------------------------------------------------------------------
# register_template_loader
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRegisterTemplateLoader:
    def test_registers_loader_with_existing_loader(self, tmp_path):
        from jinja2 import ChoiceLoader
        pm, _ = _make_manager(tmp_path)

        fake_existing = MagicMock()
        pm.app.jinja_loader = fake_existing
        pm.app.jinja_env = MagicMock()

        with patch("app.plugins.manager.ChoiceLoader") as mock_cl:
            mock_cl.return_value = MagicMock()
            pm.register_template_loader()
        mock_cl.assert_called_once()

    def test_registers_loader_when_no_existing_loader(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        pm.app.jinja_loader = None
        pm.app.jinja_env = MagicMock()

        pm.register_template_loader()
        assert pm.app.jinja_loader is not None

    def test_updates_jinja_env_loader(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        mock_env = MagicMock()
        pm.app.jinja_env = mock_env
        pm.app.jinja_loader = MagicMock()

        pm.register_template_loader()
        assert mock_env.loader is not None

    def test_handles_exception_gracefully(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        with patch("app.plugins.manager.PluginTemplateLoader", side_effect=RuntimeError("err")):
            pm.register_template_loader()  # Should not raise


# ---------------------------------------------------------------------------
# _queue_state_update
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestQueueStateUpdate:
    def test_appends_to_pending_updates(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        pm._queue_state_update("my_plugin", "activated")
        assert ("my_plugin", "activated") in pm._pending_state_updates


# ---------------------------------------------------------------------------
# Plugin lifecycle methods
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPluginLifecycle:
    def _loaded_pm(self, tmp_path, plugin_ids=None):
        pm, plugins_dir = _make_manager(tmp_path)
        for pid in (plugin_ids or ["plugin_a"]):
            _create_plugin_dir(plugins_dir, pid)
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()
        return pm

    def test_get_plugin(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        assert pm.get_plugin("plugin_a") is not None
        assert pm.get_plugin("nonexistent") is None

    def test_get_active_plugins(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        active = pm.get_active_plugins()
        assert "plugin_a" in active

    def test_is_plugin_active(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.active_plugins.add("plugin_a")
        assert pm.is_plugin_active("plugin_a") is True
        assert pm.is_plugin_active("missing") is False

    def test_get_plugin_status(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.active_plugins.add("plugin_a")
        assert pm.get_plugin_status("plugin_a") == "active"
        pm.active_plugins.discard("plugin_a")
        assert pm.get_plugin_status("plugin_a") == "inactive"
        assert pm.get_plugin_status("not_installed") == "not_installed"

    def test_install_plugin_success(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.install_plugin("plugin_a")
        assert result is True

    def test_install_plugin_not_found(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        assert pm.install_plugin("nonexistent") is False

    def test_install_plugin_exception(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.plugins["plugin_a"].install = MagicMock(side_effect=RuntimeError("fail"))
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.install_plugin("plugin_a")
        assert result is False

    def test_install_plugin_returns_false_when_install_returns_false(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.plugins["plugin_a"].install = MagicMock(return_value=False)
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.install_plugin("plugin_a")
        assert result is False

    def test_deactivate_plugin_success(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.active_plugins.add("plugin_a")
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.deactivate_plugin("plugin_a")
        assert result is True
        assert "plugin_a" not in pm.active_plugins

    def test_deactivate_plugin_not_found(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        assert pm.deactivate_plugin("nonexistent") is False

    def test_deactivate_plugin_deactivate_returns_false(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.active_plugins.add("plugin_a")
        pm.plugins["plugin_a"].deactivate = MagicMock(return_value=False)
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.deactivate_plugin("plugin_a")
        assert result is False

    def test_deactivate_plugin_exception(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.active_plugins.add("plugin_a")
        pm.plugins["plugin_a"].deactivate = MagicMock(side_effect=RuntimeError("err"))
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.deactivate_plugin("plugin_a")
        assert result is False

    def test_activate_plugin_success(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.active_plugins.discard("plugin_a")
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.activate_plugin("plugin_a")
        assert result is True
        assert "plugin_a" in pm.active_plugins

    def test_activate_plugin_not_found(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        assert pm.activate_plugin("nonexistent") is False

    def test_activate_plugin_activate_returns_false(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.plugins["plugin_a"].activate = MagicMock(return_value=False)
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.activate_plugin("plugin_a")
        assert result is False

    def test_activate_plugin_exception(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.plugins["plugin_a"].activate = MagicMock(side_effect=RuntimeError("err"))
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.activate_plugin("plugin_a")
        assert result is False

    def test_uninstall_plugin_success(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            with patch("shutil.rmtree"):
                result = pm.uninstall_plugin("plugin_a")
        assert result is True
        assert "plugin_a" not in pm.plugins

    def test_uninstall_plugin_not_found(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        assert pm.uninstall_plugin("nonexistent") is False

    def test_uninstall_plugin_cleanup_returns_false(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.plugins["plugin_a"].cleanup = MagicMock(return_value=False)
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.uninstall_plugin("plugin_a")
        assert result is False

    def test_uninstall_plugin_exception(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.plugins["plugin_a"].cleanup = MagicMock(side_effect=RuntimeError("err"))
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.uninstall_plugin("plugin_a")
        assert result is False


# ---------------------------------------------------------------------------
# _remove_plugin_files
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRemovePluginFiles:
    def test_removes_plugin_dir_when_found(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        pd = _create_plugin_dir(plugins_dir, "plugin_a")

        with patch("shutil.rmtree") as mock_rmtree:
            pm._remove_plugin_files("plugin_a")
        mock_rmtree.assert_called_once_with(pd)

    def test_logs_warning_when_dir_not_found(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        pm._remove_plugin_files("not_on_disk")  # Should not raise

    def test_handles_rmtree_exception(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")
        with patch("shutil.rmtree", side_effect=OSError("perm")):
            pm._remove_plugin_files("plugin_a")  # Should not raise


# ---------------------------------------------------------------------------
# reload_plugin
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestReloadPlugin:
    def _loaded_pm(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()
        return pm, plugins_dir

    def test_reload_success(self, tmp_path):
        pm, plugins_dir = self._loaded_pm(tmp_path)
        pm.active_plugins.add("plugin_a")

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            result = pm.reload_plugin("plugin_a")
        assert result is True

    def test_reload_not_found(self, tmp_path):
        pm, _ = self._loaded_pm(tmp_path)
        assert pm.reload_plugin("nonexistent") is False

    def test_reload_fails_when_plugin_path_not_found(self, tmp_path):
        pm, _ = self._loaded_pm(tmp_path)
        with patch.object(pm, "_find_plugin_path", return_value=None):
            with patch("app.plugins.manager.utcnow") as m:
                m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
                result = pm.reload_plugin("plugin_a")
        assert result is False

    def test_reload_fails_on_plugin_id_mismatch(self, tmp_path):
        pm, plugins_dir = self._loaded_pm(tmp_path)
        mock_new_plugin = MagicMock()
        mock_new_plugin.plugin_id = "different_id"  # Mismatch!

        with patch.object(pm, "_find_plugin_path", return_value=str(plugins_dir / "plugin_a")):
            with patch.object(pm, "_load_plugin", return_value=mock_new_plugin):
                with patch("app.plugins.manager.utcnow") as m:
                    m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
                    result = pm.reload_plugin("plugin_a")
        assert result is False

    def test_reload_exception(self, tmp_path):
        pm, _ = self._loaded_pm(tmp_path)
        with patch.object(pm, "deactivate_plugin", side_effect=RuntimeError("err")):
            with patch("app.plugins.manager.utcnow") as m:
                m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
                result = pm.reload_plugin("plugin_a")
        assert result is False


# ---------------------------------------------------------------------------
# reload_plugins
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestReloadPlugins:
    def test_reloads_all_plugins(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()
            pm.active_plugins.add("plugin_a")
            pm.reload_plugins()

        assert "plugin_a" in pm.active_plugins

    def test_handles_reload_exception(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        with patch.object(pm, "load_plugins", side_effect=RuntimeError("fail")):
            with patch("app.plugins.manager.utcnow") as m:
                m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
                pm.reload_plugins()  # Should not raise


# ---------------------------------------------------------------------------
# register_blueprints
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRegisterBlueprints:
    def test_registers_blueprints(self, tmp_path):
        from flask import Blueprint
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()

        mock_bp = Blueprint("plugin_a_bp", __name__)
        pm.plugins["plugin_a"].get_blueprint = MagicMock(return_value=mock_bp)

        pm.register_blueprints()
        assert "plugin_a_bp" in pm.app.blueprints

    def test_skips_already_registered_blueprint(self, tmp_path):
        from flask import Blueprint
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()

        mock_bp = Blueprint("existing_bp", __name__)
        pm.app.blueprints["existing_bp"] = mock_bp
        pm.plugins["plugin_a"].get_blueprint = MagicMock(return_value=mock_bp)

        pm.register_blueprints()  # Should not raise

    def test_handles_blueprint_registration_exception(self, tmp_path):
        from flask import Blueprint
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()

        mock_bp = MagicMock()
        mock_bp.name = "new_bp"
        pm.plugins["plugin_a"].get_blueprint = MagicMock(return_value=mock_bp)
        pm.app.register_blueprint = MagicMock(side_effect=RuntimeError("fail"))
        pm.app.blueprints = {}

        pm.register_blueprints()  # Should not raise

    def test_handles_already_registered_error_message(self, tmp_path):
        from flask import Blueprint
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()

        mock_bp = MagicMock()
        mock_bp.name = "new_bp"
        pm.plugins["plugin_a"].get_blueprint = MagicMock(return_value=mock_bp)
        pm.app.register_blueprint = MagicMock(
            side_effect=Exception("has already been registered")
        )
        pm.app.blueprints = {}

        pm.register_blueprints()  # Should not raise


# ---------------------------------------------------------------------------
# get_plugin_info and related
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetPluginInfo:
    def _loaded_pm(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()
        pm.active_plugins.add("plugin_a")
        return pm

    def test_returns_none_for_unknown_plugin(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        assert pm.get_plugin_info("nonexistent") is None

    def test_returns_info_dict(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        info = pm.get_plugin_info("plugin_a")
        assert info is not None
        assert info["plugin_id"] == "plugin_a"
        assert info["is_active"] is True
        assert "field_types" in info
        assert "resource_usage" in info
        assert "cleanup_info" in info

    def test_includes_installation_tracking(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.plugin_installations["plugin_a"] = {"action": "installed"}
        info = pm.get_plugin_info("plugin_a")
        assert info["installation_info"]["action"] == "installed"

    def test_get_all_plugin_info(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        all_info = pm.get_all_plugin_info()
        assert len(all_info) >= 1

    def test_list_field_types_alias(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        assert pm.list_field_types() == pm.get_field_types()

    def test_get_field_type(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm._extract_field_types()
        ft = pm.get_field_type("plugin_a_type")
        assert ft is not None

    def test_get_field_type_config(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm._extract_field_types()
        cfg = pm.get_field_type_config("plugin_a_type")
        assert cfg is not None
        assert "type_name" in cfg
        assert "form_builder_config" in cfg
        assert "entry_form_config" in cfg

    def test_get_field_type_config_none_for_unknown(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        assert pm.get_field_type_config("unknown") is None

    def test_get_all_field_type_configs(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm._extract_field_types()
        configs = pm.get_all_field_type_configs()
        assert len(configs) >= 1

    def test_get_plugin_cleanup_info(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        info = pm.get_plugin_cleanup_info("plugin_a")
        assert info is not None

    def test_get_plugin_cleanup_info_none_for_unknown(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        assert pm.get_plugin_cleanup_info("nonexistent") is None

    def test_get_plugin_resource_usage(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        usage = pm.get_plugin_resource_usage("plugin_a")
        assert usage is not None

    def test_get_plugin_resource_usage_none_for_unknown(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        assert pm.get_plugin_resource_usage("nonexistent") is None

    def test_get_plugin_installation_history(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.plugin_installations["plugin_a"] = {"action": "installed"}
        history = pm.get_plugin_installation_history("plugin_a")
        assert history is not None

    def test_get_plugin_installation_history_none_for_unknown(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        assert pm.get_plugin_installation_history("never_installed") is None

    def test_get_all_plugin_installations(self, tmp_path):
        pm = self._loaded_pm(tmp_path)
        pm.plugin_installations["plugin_a"] = {"action": "installed"}
        all_inst = pm.get_all_plugin_installations()
        assert "plugin_a" in all_inst


# ---------------------------------------------------------------------------
# _track_plugin_installation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTrackPluginInstallation:
    def test_tracks_installation(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()
        assert "plugin_a" in pm.plugin_installations

    def test_handles_exception_gracefully(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "p"
        mock_plugin.display_name = "P"
        mock_plugin.version = "1.0"
        mock_plugin.name = "P"
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.side_effect = RuntimeError("no time")
            pm._track_plugin_installation(mock_plugin, "installed")
        # Should not raise; may or may not track

    def test_handles_inner_app_context_exception(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "p"
        mock_plugin.display_name = "P"
        mock_plugin.version = "1.0"
        mock_plugin.name = "P"
        mock_plugin.get_cleanup_info.side_effect = RuntimeError("cleanup err")

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm._track_plugin_installation(mock_plugin, "installed")

        assert "p" in pm.plugin_installations


# ---------------------------------------------------------------------------
# _find_plugin_path
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFindPluginPath:
    def test_finds_existing_path(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        pd = _create_plugin_dir(plugins_dir, "plugin_a")
        result = pm._find_plugin_path("plugin_a")
        assert result == str(pd)

    def test_returns_none_when_not_found(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        assert pm._find_plugin_path("phantom") is None


# ---------------------------------------------------------------------------
# Additional targeted tests for uncovered lines
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResolveActivePluginsNameLegacy:
    """Cover lines 334-335: legacy `name` property match."""

    def test_resolves_by_name_property(self, tmp_path):
        """Plugin matched via .name when .plugin_id and .display_name don't match token."""
        pm, plugins_dir = _make_manager(tmp_path)

        # Create a mock plugin whose .name differs from .display_name
        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "custom_id"
        mock_plugin.display_name = "Does Not Match"
        # .name returns something different from display_name
        type(mock_plugin).name = property(lambda self: "Legacy Name")

        pm.plugins["custom_id"] = mock_plugin
        pm._raw_active_tokens = ["Legacy Name"]
        pm._resolve_active_plugins()

        assert "custom_id" in pm.active_plugins


@pytest.mark.unit
class TestLoadPythonPluginNoSpec:
    """Cover lines 388-389: importlib returns no spec."""

    def test_returns_none_when_spec_is_none(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        pd = _create_plugin_dir(plugins_dir, "plugin_a")
        plugin_file = pd / "plugin.py"

        with patch("importlib.util.spec_from_file_location", return_value=None):
            result = pm._load_python_plugin(plugin_file)
        assert result is None

    def test_returns_none_when_spec_has_no_loader(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        pd = _create_plugin_dir(plugins_dir, "plugin_a")
        plugin_file = pd / "plugin.py"

        mock_spec = MagicMock()
        mock_spec.loader = None
        with patch("importlib.util.spec_from_file_location", return_value=mock_spec):
            result = pm._load_python_plugin(plugin_file)
        assert result is None


@pytest.mark.unit
class TestDynamicPluginAllProperties:
    """Cover lines 459, 463, 467, 475: access all dynamic plugin properties."""

    def test_all_dynamic_plugin_properties(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        cls = pm._create_plugin_class_from_json({
            "plugin_id": "dyn",
            "display_name": "Dynamic",
            "version": "2.0.0",
            "description": "A dynamic plugin",
            "author": "Tester",
        })
        inst = cls()
        # Cover lines 459, 463, 467
        assert inst.version == "2.0.0"
        assert inst.description == "A dynamic plugin"
        assert inst.author == "Tester"

    def test_dynamic_plugin_field_types_append_path(self, tmp_path):
        """Cover line 475: field_types.append when _create_field_type_from_json returns non-None."""
        pm, _ = _make_manager(tmp_path)
        cls = pm._create_plugin_class_from_json({"plugin_id": "x", "field_types": [{}]})

        # Patch _create_field_type_from_json to return a non-None value
        mock_ft = MagicMock()
        inst = cls()
        with patch.object(inst.__class__, "_create_field_type_from_json", return_value=mock_ft):
            field_types = inst.get_field_types()
        assert mock_ft in field_types


@pytest.mark.unit
class TestTrackPluginInstallationNoBranches:
    """Cover lines 505, 510: plugin without get_cleanup_info / get_resource_usage."""

    def test_plugin_without_cleanup_info(self, tmp_path):
        pm, _ = _make_manager(tmp_path)

        # Create a plugin that has no get_cleanup_info method
        mock_plugin = MagicMock(spec=["plugin_id", "display_name", "version", "name"])
        mock_plugin.plugin_id = "bare_plugin"
        mock_plugin.display_name = "Bare Plugin"
        mock_plugin.version = "1.0"
        mock_plugin.name = "Bare Plugin"

        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm._track_plugin_installation(mock_plugin, "installed")

        assert "bare_plugin" in pm.plugin_installations
        assert pm.plugin_installations["bare_plugin"]["cleanup_info"] == {}
        assert pm.plugin_installations["bare_plugin"]["resource_usage"] == {}


@pytest.mark.unit
class TestListActiveFieldTypesIndependent:
    """Cover line 888: list_active_field_types called directly."""

    def test_list_active_field_types_directly(self, tmp_path):
        pm, plugins_dir = _make_manager(tmp_path)
        _create_plugin_dir(plugins_dir, "plugin_a")
        with patch("app.plugins.manager.utcnow") as m:
            m.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            pm.load_plugins()
        pm.active_plugins.add("plugin_a")
        pm._extract_field_types()

        # Explicitly call list_active_field_types (not via list_field_types alias)
        result = pm.list_active_field_types()
        assert isinstance(result, list)


@pytest.mark.unit
class TestGetPluginCleanupAndResourceWithoutMethods:
    """Cover lines 935, 945: plugin without get_cleanup_info / get_resource_usage."""

    def test_get_plugin_cleanup_info_no_method(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        mock_plugin = MagicMock(spec=["plugin_id"])  # No get_cleanup_info
        pm.plugins["bare"] = mock_plugin
        result = pm.get_plugin_cleanup_info("bare")
        assert result is None

    def test_get_plugin_resource_usage_no_method(self, tmp_path):
        pm, _ = _make_manager(tmp_path)
        mock_plugin = MagicMock(spec=["plugin_id"])  # No get_resource_usage
        pm.plugins["bare"] = mock_plugin
        result = pm.get_plugin_resource_usage("bare")
        assert result is None
