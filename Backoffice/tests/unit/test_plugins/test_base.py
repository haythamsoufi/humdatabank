"""
Comprehensive tests for app/plugins/base.py
Covers BaseFieldType defaults and BasePlugin concrete methods.
"""
import pytest
from typing import Dict, List, Any, Optional
from flask import Blueprint
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Concrete implementations for testing
# ---------------------------------------------------------------------------

def _make_field_type_class(**overrides):
    """Create a minimal concrete BaseFieldType subclass."""
    from app.plugins.base import BaseFieldType

    class ConcreteFieldType(BaseFieldType):
        @property
        def type_name(self) -> str:
            return overrides.get("type_name", "test_field")

        @property
        def display_name(self) -> str:
            return overrides.get("display_name", "Test Field")

        @property
        def category(self) -> str:
            return overrides.get("category", "input")

        def get_form_builder_config(self) -> Dict[str, Any]:
            return overrides.get("form_builder_config", {"fields": []})

        def get_entry_form_config(self) -> Dict[str, Any]:
            return overrides.get("entry_form_config", {"template": "field.html"})

        def validate_config(self, config: Dict[str, Any]) -> bool:
            return overrides.get("validate_config", True)

    return ConcreteFieldType


def _make_plugin_class(**overrides):
    """Create a minimal concrete BasePlugin subclass."""
    from app.plugins.base import BasePlugin

    class ConcretePlugin(BasePlugin):
        @property
        def plugin_id(self) -> str:
            return overrides.get("plugin_id", "test_plugin")

        @property
        def display_name(self) -> str:
            return overrides.get("display_name", "Test Plugin")

        @property
        def version(self) -> str:
            return overrides.get("version", "1.0.0")

    return ConcretePlugin


# ---------------------------------------------------------------------------
# BaseFieldType tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBaseFieldTypeDefaults:
    """Tests for all default (non-abstract) methods on BaseFieldType."""

    @pytest.fixture(autouse=True)
    def ft(self):
        cls = _make_field_type_class()
        self.ft = cls()

    def test_type_name(self):
        assert self.ft.type_name == "test_field"

    def test_display_name(self):
        assert self.ft.display_name == "Test Field"

    def test_category(self):
        assert self.ft.category == "input"

    def test_description_default_empty(self):
        assert self.ft.description == ""

    def test_icon_default(self):
        assert self.ft.icon == "fas fa-puzzle-piece"

    def test_version_default(self):
        assert self.ft.version == "1.0.0"

    def test_get_js_dependencies_empty(self):
        assert self.ft.get_js_dependencies() == []

    def test_get_css_dependencies_empty(self):
        assert self.ft.get_css_dependencies() == []

    def test_get_external_dependencies_structure(self):
        ext = self.ft.get_external_dependencies()
        assert "js" in ext
        assert "css" in ext
        assert ext["js"] == []
        assert ext["css"] == []

    def test_get_validation_rules_empty(self):
        assert self.ft.get_validation_rules() == []

    def test_get_condition_types_empty(self):
        assert self.ft.get_condition_types() == []

    def test_get_relevance_measures_empty(self):
        assert self.ft.get_relevance_measures() == []

    def test_get_label_variables_empty(self):
        assert self.ft.get_label_variables() == []

    def test_get_data_storage_config_defaults(self):
        config = self.ft.get_data_storage_config()
        assert config["type"] == "text"
        assert config["fields"] == []
        assert config["max_size"] is None

    def test_get_translation_config_defaults(self):
        config = self.ft.get_translation_config()
        assert "en" in config["supported_languages"]
        assert "label" in config["translatable_fields"]

    def test_get_form_builder_config_abstract_implemented(self):
        result = self.ft.get_form_builder_config()
        assert isinstance(result, dict)

    def test_get_entry_form_config_abstract_implemented(self):
        result = self.ft.get_entry_form_config()
        assert isinstance(result, dict)

    def test_validate_config_abstract_implemented(self):
        result = self.ft.validate_config({})
        assert result is True


@pytest.mark.unit
class TestBaseFieldTypeAbstractEnforcement:
    """Abstract methods raise TypeError when not implemented."""

    def test_cannot_instantiate_without_type_name(self):
        from app.plugins.base import BaseFieldType

        class Incomplete(BaseFieldType):
            @property
            def display_name(self): return "x"
            @property
            def category(self): return "x"
            def get_form_builder_config(self): return {}
            def get_entry_form_config(self): return {}
            def validate_config(self, c): return True
            # type_name missing

        with pytest.raises(TypeError):
            Incomplete()

    def test_cannot_instantiate_without_abstract_methods(self):
        from app.plugins.base import BaseFieldType
        with pytest.raises(TypeError):
            BaseFieldType()  # type: ignore


# ---------------------------------------------------------------------------
# BasePlugin tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBasePluginDefaults:
    """Test default implementations on BasePlugin."""

    @pytest.fixture(autouse=True)
    def plugin(self):
        cls = _make_plugin_class()
        self.plugin = cls()

    def test_plugin_id(self):
        assert self.plugin.plugin_id == "test_plugin"

    def test_display_name(self):
        assert self.plugin.display_name == "Test Plugin"

    def test_name_alias_returns_display_name(self):
        """name property is a backwards-compatible alias."""
        assert self.plugin.name == self.plugin.display_name

    def test_version(self):
        assert self.plugin.version == "1.0.0"

    def test_description_default(self):
        assert self.plugin.description == ""

    def test_author_default(self):
        assert self.plugin.author == "Unknown"

    def test_homepage_default(self):
        assert self.plugin.homepage == ""

    def test_license_default(self):
        assert self.plugin.license == "MIT"

    def test_get_field_types_empty(self):
        assert self.plugin.get_field_types() == []

    def test_get_blueprint_none(self):
        assert self.plugin.get_blueprint() is None

    def test_get_admin_menu_items_empty(self):
        assert self.plugin.get_admin_menu_items() == []

    def test_get_models_empty(self):
        assert self.plugin.get_models() == []

    def test_get_lookup_lists_empty(self):
        assert self.plugin.get_lookup_lists() == []

    def test_get_migrations_empty(self):
        assert self.plugin.get_migrations() == []

    def test_install_returns_true(self):
        assert self.plugin.install() is True

    def test_uninstall_returns_true(self):
        assert self.plugin.uninstall() is True

    def test_activate_returns_true(self):
        assert self.plugin.activate() is True

    def test_deactivate_returns_true(self):
        assert self.plugin.deactivate() is True

    def test_upgrade_returns_true(self):
        assert self.plugin.upgrade("1.0.0", "2.0.0") is True

    def test_cleanup_calls_uninstall(self):
        """cleanup() delegates to uninstall()."""
        self.plugin.uninstall = MagicMock(return_value=True)
        result = self.plugin.cleanup()
        assert result is True
        self.plugin.uninstall.assert_called_once()

    def test_get_cleanup_info_structure(self):
        info = self.plugin.get_cleanup_info()
        assert "database_tables" in info
        assert "uploaded_files" in info
        assert "configuration_keys" in info
        assert "estimated_space_freed" in info
        assert "warnings" in info
        assert "backup_recommendation" in info

    def test_get_resource_usage_structure(self):
        usage = self.plugin.get_resource_usage()
        assert "disk_space" in usage
        assert "database_tables" in usage
        assert "uploaded_files" in usage
        assert "configuration_keys" in usage
        assert "last_activity" in usage
        assert "memory_usage" in usage

    def test_get_installation_info_structure(self):
        info = self.plugin.get_installation_info()
        assert info["plugin_id"] == "test_plugin"
        assert info["display_name"] == "Test Plugin"
        assert info["version"] == "1.0.0"
        assert info["description"] == ""
        assert info["author"] == "Unknown"
        assert info["license"] == "MIT"
        assert info["homepage"] == ""
        assert info["field_types_count"] == 0
        assert info["has_blueprint"] is False
        assert info["has_admin_menu"] is False
        assert info["has_models"] is False
        assert info["has_migrations"] is False

    def test_get_installation_info_with_field_types(self):
        """has_blueprint and field_types_count reflect plugin state."""
        from app.plugins.base import BaseFieldType

        FieldCls = _make_field_type_class()
        PluginCls = _make_plugin_class()

        class RichPlugin(PluginCls):
            def get_field_types(self):
                return [FieldCls()]

            def get_blueprint(self):
                return Blueprint("test_bp", __name__)

            def get_admin_menu_items(self):
                return [{"label": "Item"}]

            def get_models(self):
                return [object()]

            def get_migrations(self):
                return ["0001_initial.py"]

        plugin = RichPlugin()
        info = plugin.get_installation_info()
        assert info["field_types_count"] == 1
        assert info["has_blueprint"] is True
        assert info["has_admin_menu"] is True
        assert info["has_models"] is True
        assert info["has_migrations"] is True


@pytest.mark.unit
class TestBasePluginAbstractEnforcement:
    def test_cannot_instantiate_base_plugin_directly(self):
        from app.plugins.base import BasePlugin
        with pytest.raises(TypeError):
            BasePlugin()  # type: ignore

    def test_cannot_instantiate_without_version(self):
        from app.plugins.base import BasePlugin

        class NoVersion(BasePlugin):
            @property
            def plugin_id(self): return "x"
            @property
            def display_name(self): return "X"
            # version missing

        with pytest.raises(TypeError):
            NoVersion()


# ---------------------------------------------------------------------------
# Coverage for abstract method bodies (pass statements)
# Calling via super() or direct class method invocation exercises the body.
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAbstractMethodBodies:
    """
    Python abstract methods CAN have bodies (executed via super()).
    Calling BaseFieldType.<method>.fget(instance) or BasePlugin.<method>.fget(instance)
    covers the `pass` statement in abstract property bodies.
    Calling BaseFieldType.<method>(instance) covers abstract method bodies.
    """

    def _ft_instance(self):
        cls = _make_field_type_class()
        return cls()

    def _plugin_instance(self):
        cls = _make_plugin_class()
        return cls()

    # BaseFieldType abstract property bodies
    def test_field_type_type_name_body(self):
        from app.plugins.base import BaseFieldType
        inst = self._ft_instance()
        # Call the abstract property body directly via fget
        result = BaseFieldType.type_name.fget(inst)
        assert result is None  # `pass` returns None

    def test_field_type_display_name_body(self):
        from app.plugins.base import BaseFieldType
        inst = self._ft_instance()
        result = BaseFieldType.display_name.fget(inst)
        assert result is None

    def test_field_type_category_body(self):
        from app.plugins.base import BaseFieldType
        inst = self._ft_instance()
        result = BaseFieldType.category.fget(inst)
        assert result is None

    def test_field_type_get_form_builder_config_body(self):
        from app.plugins.base import BaseFieldType
        inst = self._ft_instance()
        result = BaseFieldType.get_form_builder_config(inst)
        assert result is None

    def test_field_type_get_entry_form_config_body(self):
        from app.plugins.base import BaseFieldType
        inst = self._ft_instance()
        result = BaseFieldType.get_entry_form_config(inst)
        assert result is None

    def test_field_type_validate_config_body(self):
        from app.plugins.base import BaseFieldType
        inst = self._ft_instance()
        result = BaseFieldType.validate_config(inst, {})
        assert result is None

    # BasePlugin abstract property bodies
    def test_plugin_plugin_id_body(self):
        from app.plugins.base import BasePlugin
        inst = self._plugin_instance()
        result = BasePlugin.plugin_id.fget(inst)
        assert result is None

    def test_plugin_display_name_body(self):
        from app.plugins.base import BasePlugin
        inst = self._plugin_instance()
        result = BasePlugin.display_name.fget(inst)
        assert result is None

    def test_plugin_version_body(self):
        from app.plugins.base import BasePlugin
        inst = self._plugin_instance()
        result = BasePlugin.version.fget(inst)
        assert result is None
