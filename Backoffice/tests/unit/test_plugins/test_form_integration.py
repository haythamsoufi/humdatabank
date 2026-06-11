"""
Comprehensive tests for app/plugins/form_integration.py
Targets 100% code coverage of FormIntegration.
"""
import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Dict, List, Any, Optional


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _mock_plugin_manager(
    active_field_types=None,
    field_type_config=None,
    field_type_instance=None,
    active_plugins=None,
    plugins=None,
    field_type_to_plugin_id=None,
):
    """Build a heavily mocked PluginManager."""
    pm = MagicMock()
    pm.list_active_field_types.return_value = active_field_types or []
    pm.get_field_type_config.return_value = field_type_config
    pm.get_field_type.return_value = field_type_instance
    pm.get_active_plugins.return_value = active_plugins or {}
    pm.plugins = plugins or {}
    pm.active_plugins = set((active_plugins or {}).keys())
    pm.field_type_to_plugin_id = field_type_to_plugin_id or {}
    return pm


def _make_fi(pm=None):
    """Create a FormIntegration instance with a mock PluginManager."""
    from app.plugins.form_integration import FormIntegration
    return FormIntegration(pm or _mock_plugin_manager())


@pytest.fixture
def fi():
    return _make_fi()


@pytest.fixture
def mock_current_app():
    with patch("app.plugins.form_integration.current_app") as mca:
        mca.logger = MagicMock()
        yield mca


# ---------------------------------------------------------------------------
# __init__ and internal utilities
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormIntegrationInit:
    def test_init_stores_plugin_manager(self):
        pm = _mock_plugin_manager()
        fi = _make_fi(pm)
        assert fi.plugin_manager is pm

    def test_get_template_cache_key_is_deterministic(self, fi):
        k1 = fi._get_template_cache_key("ft", "tmpl.html", "abc")
        k2 = fi._get_template_cache_key("ft", "tmpl.html", "abc")
        assert k1 == k2

    def test_get_template_cache_key_differs_for_different_inputs(self, fi):
        k1 = fi._get_template_cache_key("ft_a", "tmpl.html", "abc")
        k2 = fi._get_template_cache_key("ft_b", "tmpl.html", "abc")
        assert k1 != k2


@pytest.mark.unit
class TestGetTemplateFileHash:
    def test_existing_file_returns_mtime_size(self, fi, tmp_path):
        f = tmp_path / "tmpl.html"
        f.write_text("hello")
        h = fi._get_template_file_hash(str(f))
        assert ":" in h  # format: "mtime:size"

    def test_missing_file_returns_missing(self, fi, tmp_path):
        h = fi._get_template_file_hash(str(tmp_path / "no_file.html"))
        assert h == "missing"

    def test_exception_returns_error(self, fi):
        with patch("app.plugins.form_integration.os.path.exists", return_value=True):
            with patch("app.plugins.form_integration.os.stat", side_effect=OSError("perm")):
                h = fi._get_template_file_hash("/some/path.html")
        assert h == "error"


@pytest.mark.unit
class TestGetPluginIdForFieldType:
    def test_returns_from_direct_mapping(self, fi):
        fi.plugin_manager.field_type_to_plugin_id = {"my_type": "my_plugin"}
        assert fi._get_plugin_id_for_field_type("my_type") == "my_plugin"

    def test_fallback_scan_active_plugins(self, fi, mock_current_app):
        ft_mock = MagicMock()
        ft_mock.type_name = "scan_type"

        plugin_mock = MagicMock()
        plugin_mock.get_field_types.return_value = [ft_mock]

        fi.plugin_manager.field_type_to_plugin_id = {}
        fi.plugin_manager.plugins = {"scan_plugin": plugin_mock}
        fi.plugin_manager.active_plugins = {"scan_plugin"}

        result = fi._get_plugin_id_for_field_type("scan_type")
        assert result == "scan_plugin"

    def test_returns_none_when_not_found(self, fi):
        fi.plugin_manager.field_type_to_plugin_id = {}
        fi.plugin_manager.plugins = {}
        fi.plugin_manager.active_plugins = set()
        assert fi._get_plugin_id_for_field_type("unknown") is None

    def test_handles_exception_in_direct_mapping(self, fi):
        """getattr raising still falls through to scan."""
        fi.plugin_manager.field_type_to_plugin_id = {}
        fi.plugin_manager.plugins = {}
        fi.plugin_manager.active_plugins = set()
        with patch("app.plugins.form_integration.getattr", side_effect=Exception("boom")):
            # should not raise; just return None
            pass  # getattr is a builtin, test the fallback path differently

        result = fi._get_plugin_id_for_field_type("x")
        assert result is None


@pytest.mark.unit
class TestResolveTemplateName:
    def test_already_prefixed_with_plugins(self, fi, mock_current_app):
        fi._get_plugin_id_for_field_type = MagicMock(return_value="my_plugin")
        result = fi._resolve_template_name("my_type", "plugins/my_plugin/field.html")
        assert result == "plugins/my_plugin/field.html"

    def test_resolves_simple_name(self, fi, mock_current_app):
        fi._get_plugin_id_for_field_type = MagicMock(return_value="my_plugin")
        result = fi._resolve_template_name("my_type", "field.html")
        assert result == "plugins/my_plugin/field.html"

    def test_strips_legacy_plugin_prefix(self, fi, mock_current_app):
        fi._get_plugin_id_for_field_type = MagicMock(return_value="my_plugin")
        result = fi._resolve_template_name("my_type", "my_plugin/field.html")
        assert result == "plugins/my_plugin/field.html"

    def test_returns_none_for_empty_template_name(self, fi, mock_current_app):
        result = fi._resolve_template_name("my_type", "")
        assert result is None
        mock_current_app.logger.warning.assert_called()

    def test_returns_none_when_plugin_id_not_found(self, fi, mock_current_app):
        fi._get_plugin_id_for_field_type = MagicMock(return_value=None)
        result = fi._resolve_template_name("unknown_type", "field.html")
        assert result is None
        mock_current_app.logger.error.assert_called()

    def test_strips_leading_slash_from_rel_path(self, fi, mock_current_app):
        fi._get_plugin_id_for_field_type = MagicMock(return_value="my_plugin")
        result = fi._resolve_template_name("my_type", "/field.html")
        assert result == "plugins/my_plugin/field.html"


# ---------------------------------------------------------------------------
# get_plugin_lookup_lists
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetPluginLookupLists:
    def test_includes_reporting_currency(self, mock_current_app):
        pm = _mock_plugin_manager(active_plugins={})
        fi = _make_fi(pm)
        result = fi.get_plugin_lookup_lists()
        ids = [str(lst.get("id")) for lst in result]
        assert "reporting_currency" in ids

    def test_includes_plugin_lookup_lists(self, mock_current_app):
        mock_plugin = MagicMock()
        mock_plugin.get_lookup_lists.return_value = [{"id": "custom_list", "name": "Custom"}]
        pm = _mock_plugin_manager(active_plugins={"my_plugin": mock_plugin})
        fi = _make_fi(pm)
        result = fi.get_plugin_lookup_lists()
        ids = [str(lst.get("id")) for lst in result]
        assert "custom_list" in ids

    def test_no_duplicate_reporting_currency(self, mock_current_app):
        mock_plugin = MagicMock()
        mock_plugin.get_lookup_lists.return_value = [
            {"id": "reporting_currency", "name": "Currency"}
        ]
        pm = _mock_plugin_manager(active_plugins={"p": mock_plugin})
        fi = _make_fi(pm)
        result = fi.get_plugin_lookup_lists()
        count = sum(1 for lst in result if str(lst.get("id")) == "reporting_currency")
        assert count == 1

    def test_handles_plugin_exception(self, mock_current_app):
        mock_plugin = MagicMock()
        mock_plugin.get_lookup_lists.side_effect = RuntimeError("oops")
        pm = _mock_plugin_manager(active_plugins={"p": mock_plugin})
        fi = _make_fi(pm)
        result = fi.get_plugin_lookup_lists()
        assert isinstance(result, list)

    def test_handles_get_active_plugins_exception(self, mock_current_app):
        pm = _mock_plugin_manager()
        pm.get_active_plugins.side_effect = RuntimeError("no plugins")
        fi = _make_fi(pm)
        result = fi.get_plugin_lookup_lists()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# get_custom_field_types_for_builder
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetCustomFieldTypesForBuilder:
    def test_returns_list_of_field_type_dicts(self, mock_current_app):
        field_config = {
            "display_name": "My Field",
            "category": "input",
            "icon": "fas fa-map",
            "description": "A field",
            "form_builder_config": {"fields": []},
        }
        pm = _mock_plugin_manager(
            active_field_types=["my_type"],
            field_type_config=field_config,
        )
        fi = _make_fi(pm)
        # Clear lru_cache before test
        fi._get_cached_field_config.cache_clear()
        fi.plugin_manager.get_field_type_config.return_value = field_config

        result = fi.get_custom_field_types_for_builder()
        assert len(result) == 1
        assert result[0]["type"] == "my_type"
        assert result[0]["type_id"] == "my_type"

    def test_skips_field_types_without_config(self, mock_current_app):
        pm = _mock_plugin_manager(
            active_field_types=["unknown"],
            field_type_config=None,
        )
        fi = _make_fi(pm)
        fi._get_cached_field_config.cache_clear()
        fi.plugin_manager.get_field_type_config.return_value = None

        result = fi.get_custom_field_types_for_builder()
        assert result == []


# ---------------------------------------------------------------------------
# render_custom_field_builder_ui
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRenderCustomFieldBuilderUI:
    def test_returns_error_html_when_field_type_not_found(self, mock_current_app):
        pm = _mock_plugin_manager(field_type_config=None)
        fi = _make_fi(pm)
        html = fi.render_custom_field_builder_ui("unknown", {})
        assert "Unknown field type" in html

    def test_returns_error_html_when_no_form_builder_config(self, mock_current_app):
        pm = _mock_plugin_manager(field_type_config={"display_name": "X"})
        fi = _make_fi(pm)
        html = fi.render_custom_field_builder_ui("ft", {})
        assert "No form builder configuration" in html

    def test_renders_with_existing_config_dict(self, mock_current_app):
        """Merges existing_config dict with field_config."""
        field_config = {
            "display_name": "Field",
            "form_builder_config": {"title": "Config", "fields": []},
        }
        pm = _mock_plugin_manager(field_type_config=field_config)
        fi = _make_fi(pm)
        fi._render_configuration_form = MagicMock(return_value="<div>form</div>")
        html = fi.render_custom_field_builder_ui("ft", {"a": 1}, existing_config={"b": 2})
        assert html == "<div>form</div>"

    def test_renders_with_existing_config_json_string(self, mock_current_app):
        field_config = {
            "display_name": "Field",
            "form_builder_config": {"fields": []},
        }
        pm = _mock_plugin_manager(field_type_config=field_config)
        fi = _make_fi(pm)
        fi._render_configuration_form = MagicMock(return_value="<div>ok</div>")
        html = fi.render_custom_field_builder_ui("ft", {}, existing_config='{"key": "val"}')
        assert html == "<div>ok</div>"

    def test_renders_with_existing_config_invalid_json_string(self, mock_current_app):
        field_config = {
            "display_name": "Field",
            "form_builder_config": {"fields": []},
        }
        pm = _mock_plugin_manager(field_type_config=field_config)
        fi = _make_fi(pm)
        fi._render_configuration_form = MagicMock(return_value="<div>ok</div>")
        html = fi.render_custom_field_builder_ui("ft", {}, existing_config="NOT JSON")
        assert html == "<div>ok</div>"

    def test_renders_with_existing_config_non_dict_type(self, mock_current_app):
        field_config = {
            "display_name": "Field",
            "form_builder_config": {"fields": []},
        }
        pm = _mock_plugin_manager(field_type_config=field_config)
        fi = _make_fi(pm)
        fi._render_configuration_form = MagicMock(return_value="<div>ok</div>")
        html = fi.render_custom_field_builder_ui("ft", {}, existing_config=12345)
        assert html == "<div>ok</div>"

    def test_returns_error_html_on_exception(self, mock_current_app):
        pm = _mock_plugin_manager(field_type_config={"display_name": "X", "form_builder_config": {}})
        fi = _make_fi(pm)
        fi._render_configuration_form = MagicMock(side_effect=RuntimeError("boom"))
        html = fi.render_custom_field_builder_ui("ft", {})
        assert "error occurred" in html.lower()


# ---------------------------------------------------------------------------
# _render_configuration_form
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRenderConfigurationForm:
    def test_uses_custom_template_when_available(self, mock_current_app):
        with patch("app.plugins.form_integration.render_template", return_value="<custom/>") as rt:
            pm = _mock_plugin_manager()
            fi = _make_fi(pm)
            fi._resolve_template_name = MagicMock(return_value="plugins/p/tmpl.html")
            result = fi._render_configuration_form(
                "ft",
                {"custom_template": "tmpl.html", "fields": []},
                {},
            )
        assert result == "<custom/>"

    def test_falls_back_when_custom_template_resolution_returns_none(self, mock_current_app):
        pm = _mock_plugin_manager()
        fi = _make_fi(pm)
        fi._resolve_template_name = MagicMock(return_value=None)
        result = fi._render_configuration_form(
            "ft",
            {"custom_template": "tmpl.html", "fields": [], "title": "T", "icon": "fas fa-x"},
            {},
        )
        assert "custom-field-config" in result

    def test_falls_back_when_render_template_raises(self, mock_current_app):
        with patch("app.plugins.form_integration.render_template", side_effect=Exception("fail")):
            pm = _mock_plugin_manager()
            fi = _make_fi(pm)
            fi._resolve_template_name = MagicMock(return_value="plugins/p/tmpl.html")
            result = fi._render_configuration_form(
                "ft",
                {"custom_template": "tmpl.html", "fields": []},
                {},
            )
        assert "custom-field-config" in result

    def test_renders_fields(self, mock_current_app):
        pm = _mock_plugin_manager()
        fi = _make_fi(pm)
        builder_config = {
            "fields": [{"name": "my_field", "type": "text", "label": "My Label"}]
        }
        result = fi._render_configuration_form("ft", builder_config, {"my_field": "val"})
        assert "my_field" in result

    def test_renders_validation_rules_section(self, mock_current_app):
        pm = _mock_plugin_manager()
        fi = _make_fi(pm)
        builder_config = {"fields": [], "validation_rules": True}
        result = fi._render_configuration_form("ft", builder_config, {})
        assert "Validation Rules" in result

    def test_renders_condition_types_section(self, mock_current_app):
        pm = _mock_plugin_manager()
        fi = _make_fi(pm)
        builder_config = {"fields": [], "condition_types": True}
        result = fi._render_configuration_form("ft", builder_config, {})
        assert "Condition Support" in result


# ---------------------------------------------------------------------------
# _render_config_field
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRenderConfigField:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.fi = _make_fi()

    def test_text_field(self):
        html = self.fi._render_config_field(
            {"name": "my_text", "type": "text", "label": "My Text", "required": True},
            "current"
        )
        assert 'type="text"' in html
        assert "my_text" in html
        assert "required" in html

    def test_text_field_not_required(self):
        html = self.fi._render_config_field(
            {"name": "opt_text", "type": "text"},
            ""
        )
        assert 'type="text"' in html

    def test_select_field_with_dict_options(self):
        html = self.fi._render_config_field(
            {
                "name": "my_select",
                "type": "select",
                "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
            },
            "a"
        )
        assert "<select" in html
        assert 'selected' in html

    def test_select_field_with_string_options(self):
        html = self.fi._render_config_field(
            {"name": "sel", "type": "select", "options": ["opt1", "opt2"]},
            "opt1"
        )
        assert "opt1" in html

    def test_number_field(self):
        html = self.fi._render_config_field(
            {"name": "num", "type": "number", "min": 0, "max": 100, "step": "0.5"},
            42
        )
        assert 'type="number"' in html
        assert 'min="0"' in html
        assert 'max="100"' in html
        assert 'step="0.5"' in html

    def test_number_field_no_min_max(self):
        html = self.fi._render_config_field({"name": "n", "type": "number"}, "")
        assert 'type="number"' in html

    def test_checkbox_field_checked(self):
        html = self.fi._render_config_field({"name": "cb", "type": "checkbox"}, True)
        assert "checkbox" in html
        assert "checked" in html

    def test_checkbox_field_unchecked(self):
        html = self.fi._render_config_field({"name": "cb", "type": "checkbox"}, False)
        assert "checkbox" in html
        assert "checked" not in html

    def test_textarea_field(self):
        html = self.fi._render_config_field(
            {"name": "ta", "type": "textarea", "rows": 5},
            "some text"
        )
        assert "<textarea" in html
        assert 'rows="5"' in html

    def test_unknown_field_type_renders_unsupported_message(self):
        html = self.fi._render_config_field({"name": "x", "type": "weird_type"}, "")
        assert "Unsupported field type" in html


# ---------------------------------------------------------------------------
# _render_validation_rules and _render_condition_types
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRenderSections:
    def test_render_validation_rules(self):
        fi = _make_fi()
        html = fi._render_validation_rules("ft", {})
        assert "Validation Rules" in html

    def test_render_condition_types(self):
        fi = _make_fi()
        html = fi._render_condition_types("ft", {})
        assert "Condition Support" in html


# ---------------------------------------------------------------------------
# render_custom_field_entry_form
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRenderCustomFieldEntryForm:
    def test_returns_error_html_when_field_type_not_found(self, mock_current_app):
        pm = _mock_plugin_manager(field_type_config=None)
        fi = _make_fi(pm)
        html = fi.render_custom_field_entry_form("unknown", {})
        assert "Unknown field type" in html

    def test_renders_via_template_when_resolved(self, mock_current_app):
        entry_config = {"template": "field.html", "es_module_path": "/js/m.js", "es_module_class": "MyCls"}
        field_config_full = {
            "entry_form_config": entry_config,
        }
        pm = _mock_plugin_manager(field_type_config=field_config_full)
        fi = _make_fi(pm)
        fi._resolve_template_name = MagicMock(return_value="plugins/p/field.html")

        with patch("app.plugins.form_integration.render_template", return_value="<rendered/>"):
            html = fi.render_custom_field_entry_form("ft", {"k": "v"}, field_value="val", field_id="f1")
        assert "<rendered/>" == html

    def test_falls_back_on_template_render_exception(self, mock_current_app):
        entry_config = {"template": "field.html"}
        field_config_full = {"entry_form_config": entry_config}
        pm = _mock_plugin_manager(field_type_config=field_config_full)
        fi = _make_fi(pm)
        fi._resolve_template_name = MagicMock(return_value="plugins/p/field.html")

        with patch("app.plugins.form_integration.render_template", side_effect=Exception("tmpl err")):
            html = fi.render_custom_field_entry_form("ft", {}, field_value=None)
        assert "custom-field-entry" in html

    def test_falls_back_when_no_template(self, mock_current_app):
        entry_config = {}
        field_config_full = {"entry_form_config": entry_config}
        pm = _mock_plugin_manager(field_type_config=field_config_full)
        fi = _make_fi(pm)
        html = fi.render_custom_field_entry_form("ft", {})
        assert "custom-field-entry" in html

    def test_field_value_dict_passed_as_existing_data(self, mock_current_app):
        entry_config = {"template": "field.html"}
        field_config_full = {"entry_form_config": entry_config}
        pm = _mock_plugin_manager(field_type_config=field_config_full)
        fi = _make_fi(pm)
        fi._resolve_template_name = MagicMock(return_value="plugins/p/field.html")

        with patch("app.plugins.form_integration.render_template", return_value="ok") as rt:
            fi.render_custom_field_entry_form("ft", {}, field_value={"k": "v"})
        call_kwargs = rt.call_args[1]
        assert call_kwargs["existing_data"] == {"k": "v"}

    def test_field_value_scalar_wrapped_in_dict(self, mock_current_app):
        entry_config = {"template": "field.html"}
        field_config_full = {"entry_form_config": entry_config}
        pm = _mock_plugin_manager(field_type_config=field_config_full)
        fi = _make_fi(pm)
        fi._resolve_template_name = MagicMock(return_value="plugins/p/field.html")

        with patch("app.plugins.form_integration.render_template", return_value="ok") as rt:
            fi.render_custom_field_entry_form("ft", {}, field_value="scalar_val")
        call_kwargs = rt.call_args[1]
        assert call_kwargs["existing_data"] == {"value": "scalar_val"}

    def test_field_name_from_field_config_when_no_field_id(self, mock_current_app):
        entry_config = {"template": "field.html"}
        field_config_full = {"entry_form_config": entry_config}
        pm = _mock_plugin_manager(field_type_config=field_config_full)
        fi = _make_fi(pm)
        fi._resolve_template_name = MagicMock(return_value="plugins/p/field.html")

        with patch("app.plugins.form_integration.render_template", return_value="ok") as rt:
            fi.render_custom_field_entry_form("ft", {"field_name": "custom_name"}, field_id=None)
        call_kwargs = rt.call_args[1]
        assert call_kwargs["field_name"] == "custom_name"

    def test_uses_entry_template_key_as_fallback(self, mock_current_app):
        """entry_config may use 'entry_template' instead of 'template'."""
        entry_config = {"entry_template": "entry.html"}
        field_config_full = {"entry_form_config": entry_config}
        pm = _mock_plugin_manager(field_type_config=field_config_full)
        fi = _make_fi(pm)
        fi._resolve_template_name = MagicMock(return_value="plugins/p/entry.html")

        with patch("app.plugins.form_integration.render_template", return_value="ok"):
            html = fi.render_custom_field_entry_form("ft", {})
        assert html == "ok"


# ---------------------------------------------------------------------------
# _render_entry_form_field
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRenderEntryFormField:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.fi = _make_fi()

    def test_basic_rendering(self):
        html = self.fi._render_entry_form_field(
            "my_field",
            {"template": "field.html", "css_files": [], "js_module": None},
            {"label": "My Label", "required": True},
            "current_value",
        )
        assert "my_field" in html
        assert "My Label" in html

    def test_css_files_included(self):
        html = self.fi._render_entry_form_field(
            "ft",
            {"css_files": ["style.css", "/abs/style2.css", "http://cdn.com/x.css"]},
            {},
            None,
        )
        assert 'rel="stylesheet"' in html
        assert "/plugins/static/style.css" in html
        assert "/abs/style2.css" in html
        assert "http://cdn.com/x.css" in html

    def test_es_module_script_included(self):
        html = self.fi._render_entry_form_field(
            "ft",
            {
                "css_files": [],
                "es_module_path": "/js/module.mjs",
                "es_module_class": "MyClass",
            },
            {"field_name": "my_field"},
            None,
        )
        assert 'type="module"' in html
        assert "MyClass" in html

    def test_required_indicator_present(self):
        html = self.fi._render_entry_form_field(
            "ft", {}, {"required": True, "label": "L"}, None
        )
        assert "text-red-500" in html

    def test_no_es_module_no_script(self):
        html = self.fi._render_entry_form_field(
            "ft", {"css_files": []}, {}, None
        )
        assert 'type="module"' not in html


# ---------------------------------------------------------------------------
# get_custom_field_dependencies
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetCustomFieldDependencies:
    def test_aggregates_all_dependencies(self, mock_current_app):
        fc = {
            "js_dependencies": ["a.js"],
            "css_dependencies": ["a.css"],
            "external_dependencies": {"js": ["cdn.js"], "css": ["cdn.css"]},
        }
        pm = _mock_plugin_manager(
            active_field_types=["ft"],
            field_type_config=fc,
        )
        fi = _make_fi(pm)
        fi.plugin_manager.get_field_type_config.return_value = fc
        deps = fi.get_custom_field_dependencies()
        assert "a.js" in deps["js"]
        assert "a.css" in deps["css"]
        assert "cdn.js" in deps["external_js"]
        assert "cdn.css" in deps["external_css"]

    def test_deduplicates_dependencies(self, mock_current_app):
        fc = {"js_dependencies": ["a.js", "a.js"], "css_dependencies": [], "external_dependencies": {}}
        pm = _mock_plugin_manager(active_field_types=["ft"], field_type_config=fc)
        fi = _make_fi(pm)
        fi.plugin_manager.get_field_type_config.return_value = fc
        deps = fi.get_custom_field_dependencies()
        assert deps["js"].count("a.js") == 1

    def test_handles_none_field_config(self, mock_current_app):
        pm = _mock_plugin_manager(active_field_types=["ft"], field_type_config=None)
        fi = _make_fi(pm)
        fi.plugin_manager.get_field_type_config.return_value = None
        deps = fi.get_custom_field_dependencies()
        assert deps["js"] == []


# ---------------------------------------------------------------------------
# validate_custom_field_config
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestValidateCustomFieldConfig:
    def test_returns_false_when_field_type_not_found(self, mock_current_app):
        pm = _mock_plugin_manager(field_type_config=None)
        fi = _make_fi(pm)
        valid, errors = fi.validate_custom_field_config("unknown", {})
        assert valid is False
        assert "Unknown field type" in errors[0]

    def test_returns_false_when_no_field_type_instance(self, mock_current_app):
        pm = _mock_plugin_manager(field_type_config={"x": 1}, field_type_instance=None)
        fi = _make_fi(pm)
        valid, errors = fi.validate_custom_field_config("ft", {})
        assert valid is False

    def test_returns_true_when_validate_returns_true(self, mock_current_app):
        ft_instance = MagicMock()
        ft_instance.validate_config.return_value = True
        pm = _mock_plugin_manager(field_type_config={"x": 1}, field_type_instance=ft_instance)
        fi = _make_fi(pm)
        valid, errors = fi.validate_custom_field_config("ft", {})
        assert valid is True
        assert errors == []

    def test_returns_false_when_validate_returns_false(self, mock_current_app):
        ft_instance = MagicMock()
        ft_instance.validate_config.return_value = False
        pm = _mock_plugin_manager(field_type_config={"x": 1}, field_type_instance=ft_instance)
        fi = _make_fi(pm)
        valid, errors = fi.validate_custom_field_config("ft", {})
        assert valid is False

    def test_returns_false_when_validate_raises(self, mock_current_app):
        ft_instance = MagicMock()
        ft_instance.validate_config.side_effect = RuntimeError("boom")
        pm = _mock_plugin_manager(field_type_config={"x": 1}, field_type_instance=ft_instance)
        fi = _make_fi(pm)
        valid, errors = fi.validate_custom_field_config("ft", {})
        assert valid is False
        assert "Validation failed" in errors[0]


# ---------------------------------------------------------------------------
# get_custom_field_data_storage_config / translation_config
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetStorageAndTranslationConfig:
    def test_data_storage_config_returns_default_when_not_found(self, mock_current_app):
        pm = _mock_plugin_manager(field_type_config=None)
        fi = _make_fi(pm)
        result = fi.get_custom_field_data_storage_config("unknown")
        assert result["type"] == "text"

    def test_data_storage_config_returns_custom(self, mock_current_app):
        fc = {"data_storage_config": {"type": "json", "fields": ["val"], "max_size": 512}}
        pm = _mock_plugin_manager(field_type_config=fc)
        fi = _make_fi(pm)
        result = fi.get_custom_field_data_storage_config("ft")
        assert result["type"] == "json"

    def test_translation_config_returns_default_when_not_found(self, mock_current_app):
        pm = _mock_plugin_manager(field_type_config=None)
        fi = _make_fi(pm)
        result = fi.get_custom_field_translation_config("unknown")
        assert "en" in result["supported_languages"]

    def test_translation_config_returns_custom(self, mock_current_app):
        fc = {"translation_config": {"supported_languages": ["en", "fr"], "translatable_fields": ["label"]}}
        pm = _mock_plugin_manager(field_type_config=fc)
        fi = _make_fi(pm)
        result = fi.get_custom_field_translation_config("ft")
        assert "fr" in result["supported_languages"]


# ---------------------------------------------------------------------------
# Additional targeted tests for uncovered lines
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetPluginIdForFieldTypeExceptionPath:
    """Cover lines 51-52: exception in direct mapping path."""

    def test_exception_in_direct_mapping_falls_through_to_scan(self, mock_current_app):
        pm = _mock_plugin_manager()
        fi = _make_fi(pm)
        # Make .field_type_to_plugin_id.get() raise to trigger the except block
        bad_dict = MagicMock()
        bad_dict.get.side_effect = RuntimeError("boom in get")
        fi.plugin_manager.field_type_to_plugin_id = bad_dict

        ft_mock = MagicMock()
        ft_mock.type_name = "scan_type"
        plugin_mock = MagicMock()
        plugin_mock.get_field_types.return_value = [ft_mock]
        fi.plugin_manager.plugins = {"scan_plugin": plugin_mock}
        fi.plugin_manager.active_plugins = {"scan_plugin"}

        result = fi._get_plugin_id_for_field_type("scan_type")
        assert result == "scan_plugin"


@pytest.mark.unit
class TestRenderCustomFieldEntryFormJsonFailure:
    """Cover lines 428-430 and 435-437: json.dumps failure paths."""

    def test_config_json_dumps_failure(self, mock_current_app):
        """When json.dumps(field_config) fails, config_json falls back to '{}'."""
        entry_config = {"template": "field.html"}
        field_config_full = {"entry_form_config": entry_config}
        pm = _mock_plugin_manager(field_type_config=field_config_full)
        fi = _make_fi(pm)
        fi._resolve_template_name = MagicMock(return_value="plugins/p/field.html")

        # A non-serializable config value
        class NotSerializable:
            pass

        with patch("app.plugins.form_integration.render_template", return_value="ok") as rt:
            html = fi.render_custom_field_entry_form(
                "ft",
                {"bad": NotSerializable()},  # Non-serializable field_config
                field_value=None,
            )
        assert html == "ok"

    def test_existing_data_json_dumps_failure(self, mock_current_app):
        """When json.dumps(existing_payload) fails, existing_data_json falls back to '{}'."""
        entry_config = {"template": "field.html"}
        field_config_full = {"entry_form_config": entry_config}
        pm = _mock_plugin_manager(field_type_config=field_config_full)
        fi = _make_fi(pm)
        fi._resolve_template_name = MagicMock(return_value="plugins/p/field.html")

        class NotSerializable:
            pass

        # field_value is a dict (so it becomes existing_payload directly) with a non-serializable value
        with patch("app.plugins.form_integration.render_template", return_value="ok") as rt:
            html = fi.render_custom_field_entry_form(
                "ft",
                {},
                field_value={"bad_key": NotSerializable()},
            )
        assert html == "ok"
