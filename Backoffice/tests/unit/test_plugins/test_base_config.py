"""
Comprehensive tests for app/plugins/base_config.py
Targets 100% code coverage of BasePluginConfig.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_plugin_root(tmp_path):
    """Return a temporary directory that acts as the plugin root."""
    plugin_root = tmp_path / "my_plugin"
    plugin_root.mkdir()
    return plugin_root


def _make_config(tmp_path, plugin_id="test_plugin", default_config=None, plugin_root=None):
    """Factory that builds a BasePluginConfig without hitting the filesystem by default."""
    from app.plugins.base_config import BasePluginConfig
    return BasePluginConfig(
        plugin_id=plugin_id,
        default_config=default_config or {},
        plugin_root=plugin_root,
    )


# ---------------------------------------------------------------------------
# __init__ and _get_config_file_path
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBasePluginConfigInit:
    def test_init_with_explicit_plugin_root(self, tmp_plugin_root):
        """plugin_root is passed explicitly – config file is placed inside it."""
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("my_plugin", {}, plugin_root=tmp_plugin_root)
        assert cfg.plugin_root == tmp_plugin_root
        assert cfg.config_file == tmp_plugin_root / "plugin_config.json"

    def test_init_without_plugin_root_uses_fallback(self, tmp_path):
        """Without plugin_root the code scans possible_paths and falls back."""
        from app.plugins.base_config import BasePluginConfig
        # No plugin directory on disk → should fall back to module-sibling path
        cfg = BasePluginConfig("nonexistent_plugin_xyz", {})
        assert cfg.config_file is not None
        assert cfg.plugin_root is None

    def test_init_uses_string_plugin_root(self, tmp_plugin_root):
        """plugin_root can be given as a str – it is coerced to Path."""
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("my_plugin", {}, plugin_root=str(tmp_plugin_root))
        assert isinstance(cfg.plugin_root, Path)

    def test_default_config_defaults_to_empty_dict(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("my_plugin", plugin_root=tmp_plugin_root)
        assert cfg.default_config == {}

    def test_possible_paths_existing_dir_wins(self, tmp_path, monkeypatch):
        """When a possible_path directory exists the config file is placed there."""
        from app.plugins import base_config as bc_module

        # Create the sibling "plugins/<plugin_id>" directory next to the module
        # We patch __file__ of the module so we control the directory layout.
        fake_plugins_dir = tmp_path / "plugins" / "my_plugin"
        fake_plugins_dir.mkdir(parents=True)

        # Patch Path(__file__).parent.parent.parent.parent to point at tmp_path
        original_file = bc_module.__file__

        # The code uses:  Path(__file__).parent.parent.parent.parent / "plugins" / plugin_id
        # depth = 4 parents up from base_config.py  →  we monkeypatch the module
        with patch.object(bc_module, "__file__", str(tmp_path / "app" / "plugins" / "base_config.py")):
            # Build the expected possible path manually
            module_path = Path(bc_module.__file__)
            expected_dir = module_path.parent.parent.parent.parent / "plugins" / "my_plugin"
            expected_dir.mkdir(parents=True, exist_ok=True)

            cfg = bc_module.BasePluginConfig("my_plugin", {})
            assert cfg.config_file == expected_dir / "plugin_config.json"


# ---------------------------------------------------------------------------
# _load_config
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestLoadConfig:
    def test_load_config_creates_default_when_no_file(self, tmp_plugin_root):
        """Config file absent → default is saved and returned."""
        from app.plugins.base_config import BasePluginConfig
        defaults = {"key": "value", "nested": {"a": 1}}
        cfg = BasePluginConfig("my_plugin", defaults, plugin_root=tmp_plugin_root)

        assert cfg.config == defaults
        # File should have been created
        assert cfg.config_file.exists()
        with open(cfg.config_file) as f:
            saved = json.load(f)
        assert saved == defaults

    def test_load_config_reads_existing_file(self, tmp_plugin_root):
        """Existing config file is read and merged with defaults."""
        from app.plugins.base_config import BasePluginConfig
        existing = {"key": "from_file", "extra": True}
        config_file = tmp_plugin_root / "plugin_config.json"
        config_file.write_text(json.dumps(existing))

        defaults = {"key": "default_val", "default_only": 99}
        cfg = BasePluginConfig("my_plugin", defaults, plugin_root=tmp_plugin_root)

        # Existing value overrides default
        assert cfg.config["key"] == "from_file"
        # Default-only key is preserved
        assert cfg.config["default_only"] == 99
        # Extra key from file is included
        assert cfg.config["extra"] is True

    def test_load_config_handles_exception_with_app_logger(self, tmp_plugin_root):
        """IO exceptions during load are caught and default returned."""
        from app.plugins.base_config import BasePluginConfig

        # Write garbage to the config file to trigger json.JSONDecodeError
        config_file = tmp_plugin_root / "plugin_config.json"
        config_file.write_text("NOT_VALID_JSON{{{")

        mock_logger = MagicMock()
        with patch("app.plugins.base_config.current_app") as mock_app:
            mock_app.logger = mock_logger
            cfg = BasePluginConfig("my_plugin", {"fallback": True}, plugin_root=tmp_plugin_root)

        assert cfg.config == {"fallback": True}
        mock_logger.error.assert_called_once()

    def test_load_config_exception_without_current_app(self, tmp_plugin_root):
        """IO exceptions when current_app has no .logger attribute are silently handled."""
        from app.plugins.base_config import BasePluginConfig

        config_file = tmp_plugin_root / "plugin_config.json"
        config_file.write_text("{bad json")

        # current_app without a logger attribute
        with patch("app.plugins.base_config.current_app", spec=[]):
            cfg = BasePluginConfig("my_plugin", {"x": 1}, plugin_root=tmp_plugin_root)

        assert cfg.config == {"x": 1}


# ---------------------------------------------------------------------------
# _merge_with_defaults
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMergeWithDefaults:
    def test_simple_merge(self, tmp_plugin_root):
        """Flat keys from loaded config override defaults."""
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {"a": 1, "b": 2}, plugin_root=tmp_plugin_root)
        merged = cfg._merge_with_defaults({"b": 99, "c": 3})
        assert merged == {"a": 1, "b": 99, "c": 3}

    def test_deep_merge_nested_dicts(self, tmp_plugin_root):
        """Nested dicts are recursively merged."""
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {"section": {"x": 1, "y": 2}}, plugin_root=tmp_plugin_root)
        merged = cfg._merge_with_defaults({"section": {"y": 99, "z": 3}})
        assert merged["section"] == {"x": 1, "y": 99, "z": 3}

    def test_non_dict_source_value_replaces_dict_default(self, tmp_plugin_root):
        """Source non-dict value replaces a default dict."""
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {"section": {"x": 1}}, plugin_root=tmp_plugin_root)
        merged = cfg._merge_with_defaults({"section": "flat_string"})
        assert merged["section"] == "flat_string"


# ---------------------------------------------------------------------------
# _save_config
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSaveConfig:
    def test_save_config_writes_json_file(self, tmp_plugin_root):
        """_save_config persists config as JSON and updates self.config."""
        from app.plugins.base_config import BasePluginConfig

        with patch("app.plugins.base_config.current_app") as mock_app:
            mock_app.logger = MagicMock()
            cfg = BasePluginConfig("p", {}, plugin_root=tmp_plugin_root)
            result = cfg._save_config({"written": True})

        assert result is True
        with open(cfg.config_file) as f:
            assert json.load(f) == {"written": True}
        assert cfg.config == {"written": True}

    def test_save_config_logs_success_when_logger_present(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        mock_logger = MagicMock()
        with patch("app.plugins.base_config.current_app") as mock_app:
            mock_app.logger = mock_logger
            cfg = BasePluginConfig("p", {}, plugin_root=tmp_plugin_root)
            cfg._save_config({"a": 1})
        mock_logger.info.assert_called()

    def test_save_config_returns_false_on_error(self, tmp_plugin_root):
        """When writing fails, _save_config returns False."""
        from app.plugins.base_config import BasePluginConfig
        mock_logger = MagicMock()
        with patch("app.plugins.base_config.current_app") as mock_app:
            mock_app.logger = mock_logger
            cfg = BasePluginConfig("p", {}, plugin_root=tmp_plugin_root)

        # Make open() raise to simulate a write error
        with patch("builtins.open", side_effect=OSError("no perm")):
            result = cfg._save_config({"x": 1})

        assert result is False

    def test_save_config_error_without_logger(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        with patch("app.plugins.base_config.current_app", spec=[]):
            cfg = BasePluginConfig("p", {}, plugin_root=tmp_plugin_root)
            with patch("builtins.open", side_effect=OSError("fail")):
                result = cfg._save_config({"x": 1})
        assert result is False


# ---------------------------------------------------------------------------
# Public API methods
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPublicAPI:
    def test_get_all_config(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {"a": 1, "b": 2}, plugin_root=tmp_plugin_root)
        result = cfg.get_all_config()
        assert result == {"a": 1, "b": 2}
        # Must be a copy, not the same object
        result["new_key"] = "x"
        assert "new_key" not in cfg.config

    def test_get_section_returns_section(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {"sec": {"k": "v"}}, plugin_root=tmp_plugin_root)
        assert cfg.get_section("sec") == {"k": "v"}

    def test_get_section_returns_empty_dict_for_missing(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {}, plugin_root=tmp_plugin_root)
        assert cfg.get_section("missing") == {}

    def test_update_config(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {"a": 1}, plugin_root=tmp_plugin_root)
        result = cfg.update_config({"a": 99, "b": 2})
        assert result is True
        assert cfg.config["a"] == 99

    def test_update_section_new_section(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {}, plugin_root=tmp_plugin_root)
        result = cfg.update_section("new_sec", {"k": "v"})
        assert result is True
        assert cfg.config["new_sec"]["k"] == "v"

    def test_update_section_existing_section(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {"sec": {"a": 1}}, plugin_root=tmp_plugin_root)
        cfg.update_section("sec", {"b": 2})
        assert cfg.config["sec"] == {"a": 1, "b": 2}

    def test_update_section_exception_logged(self, tmp_plugin_root):
        """Exception during update_section is caught and False returned."""
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {}, plugin_root=tmp_plugin_root)

        mock_logger = MagicMock()
        with patch("app.plugins.base_config.current_app") as mock_app:
            mock_app.logger = mock_logger
            # Make config.update raise
            original_update = cfg.config.update

            def raise_on_update(*a, **kw):
                raise RuntimeError("boom")

            with patch.dict(cfg.config, {}):
                # patch the update method of the config dict
                with patch.object(cfg, "_save_config", side_effect=RuntimeError("save fail")):
                    # Trigger exception path via _save_config
                    result = cfg.update_section("sec", {"k": 1})
        assert result is False

    def test_update_section_exception_without_logger(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {}, plugin_root=tmp_plugin_root)
        with patch("app.plugins.base_config.current_app", spec=[]):
            with patch.object(cfg, "_save_config", side_effect=RuntimeError("fail")):
                result = cfg.update_section("sec", {"k": 1})
        assert result is False

    def test_get_setting(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {"sec": {"key": "val"}}, plugin_root=tmp_plugin_root)
        assert cfg.get_setting("sec", "key") == "val"

    def test_get_setting_default(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {}, plugin_root=tmp_plugin_root)
        assert cfg.get_setting("missing", "key", default="fallback") == "fallback"

    def test_set_setting_new_section(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {}, plugin_root=tmp_plugin_root)
        result = cfg.set_setting("new_sec", "key", "value")
        assert result is True
        assert cfg.config["new_sec"]["key"] == "value"

    def test_set_setting_existing_section(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        cfg = BasePluginConfig("p", {"sec": {"a": 1}}, plugin_root=tmp_plugin_root)
        cfg.set_setting("sec", "b", 2)
        assert cfg.config["sec"]["b"] == 2

    def test_reset_to_defaults(self, tmp_plugin_root):
        from app.plugins.base_config import BasePluginConfig
        defaults = {"a": 1, "b": 2}
        cfg = BasePluginConfig("p", defaults, plugin_root=tmp_plugin_root)
        cfg.config["a"] = 999
        result = cfg.reset_to_defaults()
        assert result is True
        assert cfg.config == defaults
