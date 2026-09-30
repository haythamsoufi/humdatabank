# Backoffice/app/plugins/form_integration.py

import logging
import re
from typing import Dict, List, Any, Optional
from contextlib import suppress
from flask import render_template, current_app
from jinja2.utils import htmlsafe_json_dumps
from markupsafe import Markup, escape
from .manager import PluginManager
import threading
from functools import lru_cache
import hashlib
import os
import time
import json


logger = logging.getLogger(__name__)


class FormIntegration:
    """Handles integration of custom field types with the form system."""

    def __init__(self, plugin_manager: PluginManager):
        self.plugin_manager = plugin_manager
        self._template_cache = {}
        self._template_cache_lock = threading.Lock()
        self._config_cache = {}
        self._config_cache_lock = threading.Lock()

    def _get_template_cache_key(self, field_type: str, template_path: str, config_hash: str) -> str:
        """Generate cache key for templates."""
        return hashlib.md5(f"{field_type}:{template_path}:{config_hash}".encode()).hexdigest()

    def _get_template_file_hash(self, template_path: str) -> str:
        """Generate hash for template file based on modification time."""
        try:
            if os.path.exists(template_path):
                stat = os.stat(template_path)
                return f"{stat.st_mtime}:{stat.st_size}"
            return "missing"
        except Exception as e:
            logger.debug("_get_template_file_hash failed for %s: %s", template_path, e)
            return "error"

    def _get_plugin_id_for_field_type(self, field_type: str) -> Optional[str]:
        """Return plugin_id that owns a given field_type."""
        # Preferred: direct mapping maintained by PluginManager
        try:
            pid = getattr(self.plugin_manager, "field_type_to_plugin_id", {}).get(field_type)
            if pid:
                return pid
        except Exception as e:
            logger.debug("_get_plugin_id_for_field_type direct mapping failed: %s", e)

        # Fallback: scan active plugins
        for plugin_id, plugin in getattr(self.plugin_manager, "plugins", {}).items():
            if plugin_id in getattr(self.plugin_manager, "active_plugins", set()):
                for ft in plugin.get_field_types():
                    if ft.type_name == field_type:
                        return plugin_id
        return None

    def _resolve_template_name(self, field_type: str, template_name: str) -> Optional[str]:
        """
        Resolve a plugin template to a deterministic Jinja template name.
        Result will be: plugins/<plugin_id>/<template_name>
        """
        if not template_name:
            current_app.logger.warning(f"[FormIntegration] _resolve_template_name: template_name is empty")
            return None

        # If already deterministic, keep it
        if template_name.startswith("plugins/"):
            return template_name

        plugin_id = self._get_plugin_id_for_field_type(field_type)

        if not plugin_id:
            current_app.logger.error(f"[FormIntegration] _resolve_template_name: Could not find plugin_id for field_type: {field_type}")
            return None

        # Support legacy "<plugin_id>/field.html" values by stripping prefix
        if "/" in template_name:
            parts = template_name.split("/", 1)
            if parts[0] == plugin_id:
                template_name = parts[1]

        resolved = f"plugins/{plugin_id}/{template_name.lstrip('/')}"
        return resolved

    @lru_cache(maxsize=128)
    def _get_cached_field_config(self, field_type_name: str) -> Optional[Dict[str, Any]]:
        """Get cached field configuration."""
        return self.plugin_manager.get_field_type_config(field_type_name)

    def get_plugin_lookup_lists(self) -> List[Dict[str, Any]]:
        """Get lookup lists from all active plugins for form builder integration."""
        lookup_lists = []

        try:
            # Get all active plugins
            active_plugins = self.plugin_manager.get_active_plugins()

            for plugin_name, plugin_instance in active_plugins.items():
                try:
                    # Get lookup lists from this plugin
                    plugin_lookup_lists = plugin_instance.get_lookup_lists()
                    if plugin_lookup_lists:
                        lookup_lists.extend(plugin_lookup_lists)
                except Exception as e:
                    current_app.logger.warning(f"Error getting lookup lists from plugin {plugin_name}: {e}")
                    continue

        except Exception as e:
            current_app.logger.error(f"Error getting plugin lookup lists: {e}")

        # Append core system lists that behave like plugin lists (always available)
        with suppress(Exception):
            # Reporting Currency: dynamic local currency + common CHF/EUR/USD
            reporting_currency_list = {
                'id': 'reporting_currency',
                'name': 'Reporting Currency',
                'columns_config': [
                    { 'name': 'code', 'type': 'string' }
                ]
            }
            # Avoid duplicates if a plugin accidentally provides same id
            if all(str(lst.get('id')) != 'reporting_currency' for lst in lookup_lists):
                lookup_lists.append(reporting_currency_list)

        return lookup_lists

    def get_custom_field_types_for_builder(self) -> List[Dict[str, Any]]:
        """Get custom field types formatted for the form builder with caching."""
        custom_fields = []

        # Use cached configurations when possible
        active_field_types = self.plugin_manager.list_active_field_types()

        for field_type_name in active_field_types:
            field_config = self._get_cached_field_config(field_type_name)
            if field_config:
                custom_fields.append({
                    'type': field_type_name,
                    'type_id': field_type_name,  # Add type_id field for template compatibility
                    'display_name': field_config['display_name'],
                    'category': field_config['category'],
                    'icon': field_config['icon'],
                    'description': field_config['description'],
                    'config': field_config['form_builder_config']
                })

        return custom_fields

    def render_custom_field_builder_ui(self, field_type: str, field_config: Dict[str, Any], existing_config: Dict[str, Any] = None) -> str:
        """Render the UI for configuring a custom field type in the form builder."""
        try:
            current_app.logger.info(f"Starting to render builder UI for field type: {field_type}")

            field_type_config = self.plugin_manager.get_field_type_config(field_type)
            if not field_type_config:
                current_app.logger.error(f"Field type config not found for: {field_type}")
                return f"<p class='text-red-500'>Unknown field type: {escape(field_type)}</p>"

            current_app.logger.info(f"Field type config found: {field_type_config.keys()}")

            # Get the form builder configuration
            if 'form_builder_config' not in field_type_config:
                current_app.logger.error(f"Form builder config not found for field type: {field_type}")
                return f"<p class='text-red-500'>No form builder configuration available for {escape(field_type)}</p>"

            builder_config = field_type_config['form_builder_config']
            current_app.logger.info(f"Builder config: {builder_config}")

            # Merge existing configuration with current config for edit mode
            if existing_config:
                # Ensure existing_config is a dictionary
                if isinstance(existing_config, str):
                    try:
                        import json
                        existing_config = json.loads(existing_config) if existing_config else {}
                    except (json.JSONDecodeError, ValueError):
                        existing_config = {}
                elif not isinstance(existing_config, dict):
                    existing_config = {}

                merged_config = {**field_config, **existing_config}
            else:
                merged_config = field_config

            # Render the configuration form
            html = self._render_configuration_form(field_type, builder_config, merged_config)
            current_app.logger.info(f"Generated HTML length: {len(html) if html else 0}")

            return html

        except Exception as e:
            current_app.logger.error(f"Error in render_custom_field_builder_ui for {field_type}: {e}", exc_info=True)
            return "<p class='text-red-500'>An error occurred while rendering configuration.</p>"

    def _render_configuration_form(self, field_type: str, builder_config: Dict[str, Any], current_config: Dict[str, Any]) -> str:
        """Render the configuration form for a custom field type."""

        # Check if there's a custom builder template
        custom_template = builder_config.get('custom_template')
        current_app.logger.info(f"[FormIntegration] _render_configuration_form for {field_type}, custom_template: {custom_template}")

        if custom_template:
            try:
                # Generate a unique field ID for this instance
                import uuid
                field_id = str(uuid.uuid4())[:8]

                current_app.logger.info(f"[FormIntegration] Resolving template: {custom_template} for field_type: {field_type}")
                resolved = self._resolve_template_name(field_type, custom_template)
                current_app.logger.info(f"[FormIntegration] Resolved template: {resolved}")

                if resolved:
                    current_app.logger.info(f"[FormIntegration] Rendering template: {resolved} with field_id: {field_id}")
                    rendered = render_template(
                        resolved,
                        field_id=field_id,
                        config=current_config,
                    )
                    current_app.logger.info(f"[FormIntegration] Template rendered successfully, length: {len(rendered)}")
                    return rendered
                else:
                    current_app.logger.warning(f"[FormIntegration] Template resolution returned None for {custom_template}")
            except Exception as e:
                current_app.logger.error(f"[FormIntegration] Error rendering custom template {custom_template}: {e}", exc_info=True)

        current_app.logger.info(f"[FormIntegration] Falling back to default field rendering for {field_type}")

        # Fallback to default rendering
        fields_html = ""

        # Render each configuration field
        for field in builder_config.get('fields', []):
            field_html = self._render_config_field(field, current_config.get(field['name'], field.get('default', '')))
            fields_html += field_html

        # Add validation rules if supported
        if builder_config.get('validation_rules'):
            fields_html += self._render_validation_rules(field_type, current_config)

        # Add condition types if supported
        if builder_config.get('condition_types'):
            fields_html += self._render_condition_types(field_type, current_config)

        return f"""
        <div class="custom-field-config" data-field-type="{escape(field_type)}">
            <h4 class="text-lg font-semibold mb-4 text-gray-700">
                <i class="{escape(builder_config.get('icon', 'fas fa-cog'))} mr-2"></i>
                {escape(builder_config.get('title', 'Field Configuration'))}
            </h4>
            {fields_html}
        </div>
        """

    def _render_config_field(self, field: Dict[str, Any], current_value: Any) -> str:
        """Render a single configuration field."""
        field_type = escape(field.get('type', 'text'))
        raw_type = field.get('type', 'text')
        field_name = escape(field['name'])
        field_label = escape(field.get('label', str(field['name']).title()))
        field_required = field.get('required', False)
        field_placeholder = escape(field.get('placeholder', ''))
        cv = escape(current_value or '')

        if raw_type == 'text':
            return f"""
            <div class="mb-4">
                <label for="{field_name}" class="block text-sm font-medium text-gray-700 mb-2">
                    {field_label}
                    {f'<span class="text-red-500">*</span>' if field_required else ''}
                </label>
                <input type="text"
                       id="{field_name}"
                       name="{field_name}"
                       value="{cv}"
                       placeholder="{field_placeholder}"
                       class="shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full text-sm border-gray-300 rounded-md"
                       {f'required' if field_required else ''}>
            </div>
            """

        elif raw_type == 'select':
            options = field.get('options', [])
            options_html = ""
            for option in options:
                if isinstance(option, dict):
                    value = option.get('value', '')
                    label = option.get('label', value)
                else:
                    value = str(option)
                    label = str(option)

                selected = 'selected' if str(current_value) == str(value) else ''
                options_html += f'<option value="{escape(value)}" {selected}>{escape(label)}</option>'

            return f"""
            <div class="mb-4">
                <label for="{field_name}" class="block text-sm font-medium text-gray-700 mb-2">
                    {field_label}
                    {f'<span class="text-red-500">*</span>' if field_required else ''}
                </label>
                <select id="{field_name}"
                        name="{field_name}"
                        class="shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full text-sm border-gray-300 rounded-md"
                        {f'required' if field_required else ''}>
                    {options_html}
                </select>
            </div>
            """

        elif raw_type == 'number':
            min_val = field.get('min')
            max_val = field.get('max')
            step_val = field.get('step', '1')

            min_attr = f'min="{escape(min_val)}"' if min_val is not None else ''
            max_attr = f'max="{escape(max_val)}"' if max_val is not None else ''
            step_attr = f'step="{escape(step_val)}"'

            return f"""
            <div class="mb-4">
                <label for="{field_name}" class="block text-sm font-medium text-gray-700 mb-2">
                    {field_label}
                    {f'<span class="text-red-500">*</span>' if field_required else ''}
                </label>
                <input type="number"
                       id="{field_name}"
                       name="{field_name}"
                       value="{cv}"
                       placeholder="{field_placeholder}"
                       {min_attr} {max_attr} {step_attr}
                       class="shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full text-sm border-gray-300 rounded-md"
                       {f'required' if field_required else ''}>
            </div>
            """

        elif raw_type == 'checkbox':
            checked = 'checked' if current_value else ''
            return f"""
            <div class="mb-4">
                <label class="flex items-center text-gray-700 text-sm">
                    <input type="checkbox"
                           id="{field_name}"
                           name="{field_name}"
                           value="1"
                           {checked}
                           class="form-checkbox h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500">
                    <span class="ml-2">{field_label}</span>
                </label>
            </div>
            """

        elif raw_type == 'textarea':
            rows = field.get('rows', 3)
            return f"""
            <div class="mb-4">
                <label for="{field_name}" class="block text-sm font-medium text-gray-700 mb-2">
                    {field_label}
                    {f'<span class="text-red-500">*</span>' if field_required else ''}
                </label>
                <textarea id="{field_name}"
                          name="{field_name}"
                          rows="{escape(rows)}"
                          placeholder="{field_placeholder}"
                          class="shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full text-sm border-gray-300 rounded-md"
                          {f'required' if field_required else ''}>{cv}</textarea>
            </div>
            """

        else:
            return f"""
            <div class="mb-4">
                <label for="{field_name}" class="block text-sm font-medium text-gray-700 mb-2">
                    {field_label}
                </label>
                <p class="text-sm text-gray-500">Unsupported field type: {field_type}</p>
            </div>
            """

    def _render_validation_rules(self, field_type: str, current_config: Dict[str, Any]) -> str:
        """Render validation rules section."""
        return f"""
        <div class="mb-4 border-t pt-4">
            <h5 class="text-md font-medium text-gray-700 mb-3">Validation Rules</h5>
            <div class="space-y-2">
                <p class="text-sm text-gray-500">Plugin-specific validation rules can be added here.</p>
                <!-- Note: The "Required field" option is handled by the main Properties section -->
                <!-- Add more validation rules as needed -->
            </div>
        </div>
        """

    def _render_condition_types(self, field_type: str, current_config: Dict[str, Any]) -> str:
        """Render condition types section."""
        return f"""
        <div class="mb-4 border-t pt-4">
            <h5 class="text-md font-medium text-gray-700 mb-3">Condition Support</h5>
            <p class="text-sm text-gray-500">This field type supports relevance and validation conditions.</p>
        </div>
        """

    def render_custom_field_entry_form(
        self,
        field_type: str,
        field_config: Dict[str, Any],
        field_value: Any = None,
        field_id: Optional[str] = None,
        can_edit: bool = True,
        country_iso: Optional[str] = None,
    ) -> str:
        """Render a custom field type in the entry form."""
        field_type_config = self.plugin_manager.get_field_type_config(field_type)
        if not field_type_config:
            return f"<p class='text-red-500'>Unknown field type: {field_type}</p>"

        # Get the entry form configuration
        entry_config = field_type_config['entry_form_config']

        # Render deterministically via registered plugin template loader
        template_name = entry_config.get('template') or entry_config.get('entry_template')
        resolved_template = self._resolve_template_name(field_type, template_name) if template_name else None
        if resolved_template:
            try:
                try:
                    config_json = htmlsafe_json_dumps(field_config or {})
                except Exception as e:
                    logger.debug("render_custom_field_entry_form: config_json dumps failed: %s", e)
                    config_json = Markup("{}")

                existing_payload = field_value if isinstance(field_value, (dict, list)) else ({'value': field_value} if field_value is not None else {})
                try:
                    existing_data_json = json.dumps(existing_payload, ensure_ascii=False)
                except Exception as e:
                    logger.debug("render_custom_field_entry_form: existing_data_json dumps failed: %s", e)
                    existing_data_json = "{}"

                field_name = str(field_id) if field_id is not None else field_config.get('field_name', f'{field_type}_field')

                return Markup(render_template(
                    resolved_template,
                    field_id=field_name,
                    field_name=field_name,
                    field_type=field_type,
                    config=field_config,
                    config_json=config_json,
                    existing_data=existing_payload,
                    existing_data_json=existing_data_json,
                    field_value=field_value,
                    can_edit=bool(can_edit),
                    country_iso=country_iso,
                ))
            except Exception as e:
                current_app.logger.warning(f"Failed to render plugin template for {field_type} ({resolved_template}): {e}", exc_info=True)

        # Fallback to generic field rendering
        return self._render_entry_form_field(field_type, entry_config, field_config, field_value)

    def _render_entry_form_field(self, field_type: str, entry_config: Dict[str, Any], field_config: Dict[str, Any], field_value: Any) -> Markup:
        """Render a custom field in the entry form (fallback when no plugin template renders).

        Every interpolated value is escaped for its context (HTML text/attribute or JS string
        literal); the return value is ``Markup`` because the result is trusted only after that.
        """
        css_files = entry_config.get('css_files', [])
        field_config = field_config if isinstance(field_config, dict) else {}

        type_html = escape(field_type)
        field_name_raw = str(field_config.get('field_name', field_type))
        try:
            config_attr = escape(json.dumps(field_config, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            config_attr = escape("{}")
        value_html = escape('' if field_value is None or field_value is False else field_value)
        required_html = '<span class="text-red-500">*</span>' if field_config.get('required') else ''

        field_html = f"""
        <div class="custom-field-entry" data-field-type="{type_html}" data-field-config="{config_attr}">
            <label class="block text-sm font-medium text-gray-700 mb-2">
                {escape(field_config.get('label', 'Custom Field'))}
                {required_html}
            </label>
            <div class="field-container">
                <!-- Custom field content will be rendered here -->
                <p class="text-sm text-gray-500">Loading {type_html} field...</p>
            </div>
            <input type="hidden" name="{escape(field_name_raw)}" value="{value_html}" />
        </div>
        """

        for css_file in css_files:
            css_file = str(css_file)
            if css_file.startswith('/') or css_file.startswith('http'):
                css_href = css_file
            else:
                css_href = f'/plugins/static/{css_file}'
            field_html += f'<link rel="stylesheet" href="{escape(css_href)}">'

        es_module_path = entry_config.get('es_module_path')
        es_module_class = entry_config.get('es_module_class')

        if es_module_path and es_module_class:
            if not re.fullmatch(r"[A-Za-z_$][\w$]*", str(es_module_class)):
                raise ValueError("Invalid es_module_class in plugin entry_form_config")
            module_path_js = htmlsafe_json_dumps(str(es_module_path))
            field_type_js = htmlsafe_json_dumps(str(field_type))
            field_name_js = htmlsafe_json_dumps(field_name_raw)
            field_html += f"""
            <script type="module">
                import {{ {es_module_class} }} from {module_path_js};

                document.addEventListener('DOMContentLoaded', function() {{
                    window.{es_module_class} = {es_module_class};

                    const fieldContainer = Array.from(document.querySelectorAll('[data-field-type]'))
                        .find(function (el) {{ return el.getAttribute('data-field-type') === {field_type_js}; }});
                    if (fieldContainer) {{
                        const fieldName = fieldContainer.dataset.fieldName || {field_name_js};
                        const instance = new {es_module_class}(fieldName);
                        fieldContainer.pluginInstance = instance;

                        if (typeof instance.initialize === 'function') {{
                            instance.initialize();
                        }} else if (typeof instance.initField === 'function') {{
                            instance.initField({field_type_js}, fieldName);
                        }}
                    }}
                }});
            </script>
            """

        return Markup(field_html)

    # NOTE: `_render_plugin_template` and `_get_template_content` were removed in favor of
    # deterministic Jinja template loading via PluginManager.register_template_loader().

    def get_custom_field_dependencies(self) -> Dict[str, List[str]]:
        """Get all custom field dependencies for inclusion in templates."""
        all_dependencies = {
            'js': [],
            'css': [],
            'external_js': [],
            'external_css': []
        }

        for field_type_name in self.plugin_manager.list_active_field_types():
            field_config = self.plugin_manager.get_field_type_config(field_type_name)
            if field_config:
                # Internal dependencies
                for js_file in field_config.get('js_dependencies', []):
                    if js_file not in all_dependencies['js']:
                        all_dependencies['js'].append(js_file)

                for css_file in field_config.get('css_dependencies', []):
                    if css_file not in all_dependencies['css']:
                        all_dependencies['css'].append(css_file)

                # External dependencies
                external_deps = field_config.get('external_dependencies', {})
                for js_file in external_deps.get('js', []):
                    if js_file not in all_dependencies['external_js']:
                        all_dependencies['external_js'].append(js_file)

                for css_file in external_deps.get('css', []):
                    if css_file not in all_dependencies['external_css']:
                        all_dependencies['external_css'].append(css_file)

        return all_dependencies

    def validate_custom_field_config(self, field_type: str, config: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate configuration for a custom field type."""
        field_type_config = self.plugin_manager.get_field_type_config(field_type)
        if not field_type_config:
            return False, [f"Unknown field type: {field_type}"]

        field_type_instance = self.plugin_manager.get_field_type(field_type)
        if not field_type_instance:
            return False, [f"Could not instantiate field type: {field_type}"]

        try:
            is_valid = field_type_instance.validate_config(config)
            if is_valid:
                return True, []
            else:
                return False, ["Field type validation failed"]
        except Exception as e:
            current_app.logger.debug("Plugin field validation failed: %s", e, exc_info=True)
            return False, ["Validation failed."]

    def get_custom_field_data_storage_config(self, field_type: str) -> Dict[str, Any]:
        """Get data storage configuration for a custom field type."""
        field_type_config = self.plugin_manager.get_field_type_config(field_type)
        if not field_type_config:
            return {'type': 'text', 'fields': [], 'max_size': None}

        return field_type_config.get('data_storage_config', {'type': 'text', 'fields': [], 'max_size': None})

    def get_custom_field_translation_config(self, field_type: str) -> Dict[str, Any]:
        """Get translation configuration for a custom field type."""
        field_type_config = self.plugin_manager.get_field_type_config(field_type)
        if not field_type_config:
            return {'supported_languages': ['en'], 'translatable_fields': []}

        return field_type_config.get('translation_config', {'supported_languages': ['en'], 'translatable_fields': []})
