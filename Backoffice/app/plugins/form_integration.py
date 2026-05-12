# Backoffice/app/plugins/form_integration.py

import logging
from typing import Dict, List, Any, Optional
from contextlib import suppress
from flask import render_template, current_app
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
                return f"<p class='text-red-500'>Unknown field type: {field_type}</p>"

            current_app.logger.info(f"Field type config found: {field_type_config.keys()}")

            # Get the form builder configuration
            if 'form_builder_config' not in field_type_config:
                current_app.logger.error(f"Form builder config not found for field type: {field_type}")
                return f"<p class='text-red-500'>No form builder configuration available for {field_type}</p>"

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
        <div class="custom-field-config" data-field-type="{field_type}">
            <h4 class="text-lg font-semibold mb-4 text-gray-700">
                <i class="{builder_config.get('icon', 'fas fa-cog')} mr-2"></i>
                {builder_config.get('title', 'Field Configuration')}
            </h4>
            {fields_html}
        </div>
        """

    def _render_config_field(self, field: Dict[str, Any], current_value: Any) -> str:
        """Render a single configuration field."""
        field_type = field.get('type', 'text')
        field_name = field['name']
        field_label = field.get('label', field_name.title())
        field_required = field.get('required', False)
        field_placeholder = field.get('placeholder', '')

        if field_type == 'text':
            return f"""
            <div class="mb-4">
                <label for="{field_name}" class="block text-sm font-medium text-gray-700 mb-2">
                    {field_label}
                    {f'<span class="text-red-500">*</span>' if field_required else ''}
                </label>
                <input type="text"
                       id="{field_name}"
                       name="{field_name}"
                       value="{current_value or ''}"
                       placeholder="{field_placeholder}"
                       class="shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full text-sm border-gray-300 rounded-md"
                       {f'required' if field_required else ''}>
            </div>
            """

        elif field_type == 'select':
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
                options_html += f'<option value="{value}" {selected}>{label}</option>'

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

        elif field_type == 'number':
            min_val = field.get('min')
            max_val = field.get('max')
            step_val = field.get('step', '1')

            min_attr = f'min="{min_val}"' if min_val is not None else ''
            max_attr = f'max="{max_val}"' if max_val is not None else ''
            step_attr = f'step="{step_val}"'

            return f"""
            <div class="mb-4">
                <label for="{field_name}" class="block text-sm font-medium text-gray-700 mb-2">
                    {field_label}
                    {f'<span class="text-red-500">*</span>' if field_required else ''}
                </label>
                <input type="number"
                       id="{field_name}"
                       name="{field_name}"
                       value="{current_value or ''}"
                       placeholder="{field_placeholder}"
                       {min_attr} {max_attr} {step_attr}
                       class="shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full text-sm border-gray-300 rounded-md"
                       {f'required' if field_required else ''}>
            </div>
            """

        elif field_type == 'checkbox':
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

        elif field_type == 'textarea':
            rows = field.get('rows', 3)
            return f"""
            <div class="mb-4">
                <label for="{field_name}" class="block text-sm font-medium text-gray-700 mb-2">
                    {field_label}
                    {f'<span class="text-red-500">*</span>' if field_required else ''}
                </label>
                <textarea id="{field_name}"
                          name="{field_name}"
                          rows="{rows}"
                          placeholder="{field_placeholder}"
                          class="shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full text-sm border-gray-300 rounded-md"
                          {f'required' if field_required else ''}>{current_value or ''}</textarea>
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
                    config_json = json.dumps(field_config or {}, ensure_ascii=False)
                except Exception as e:
                    logger.debug("render_custom_field_entry_form: config_json dumps failed: %s", e)
                    config_json = "{}"

                existing_payload = field_value if isinstance(field_value, (dict, list)) else ({'value': field_value} if field_value is not None else {})
                try:
                    existing_data_json = json.dumps(existing_payload, ensure_ascii=False)
                except Exception as e:
                    logger.debug("render_custom_field_entry_form: existing_data_json dumps failed: %s", e)
                    existing_data_json = "{}"

                field_name = str(field_id) if field_id is not None else field_config.get('field_name', f'{field_type}_field')

                return render_template(
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
                )
            except Exception as e:
                current_app.logger.warning(f"Failed to render plugin template for {field_type} ({resolved_template}): {e}", exc_info=True)

        # Fallback to generic field rendering
        return self._render_entry_form_field(field_type, entry_config, field_config, field_value)

    def _render_entry_form_field(self, field_type: str, entry_config: Dict[str, Any], field_config: Dict[str, Any], field_value: Any) -> str:
        """Render a custom field in the entry form."""
        template = entry_config.get('template')
        js_module = entry_config.get('js_module')
        css_files = entry_config.get('css_files', [])

        # Basic field rendering
        field_html = f"""
        <div class="custom-field-entry" data-field-type="{field_type}" data-field-config='{field_config}'>
            <label class="block text-sm font-medium text-gray-700 mb-2">
                {field_config.get('label', 'Custom Field')}
                {f'<span class="text-red-500">*</span>' if field_config.get('required') else ''}
            </label>
            <div class="field-container">
                <!-- Custom field content will be rendered here -->
                <p class="text-sm text-gray-500">Loading {field_type} field...</p>
            </div>
            <input type="hidden" name="{field_config.get('field_name', field_type)}" value="{field_value or ''}" />
        </div>
        """

        # Add CSS dependencies
        for css_file in css_files:
            # Handle both absolute and relative CSS paths
            if css_file.startswith('/') or css_file.startswith('http'):
                css_href = css_file
            else:
                css_href = f'/plugins/static/{css_file}'
            field_html += f'<link rel="stylesheet" href="{css_href}">'

        # Add JavaScript initialization (ES modules only)
        es_module_path = entry_config.get('es_module_path')
        es_module_class = entry_config.get('es_module_class')

        if es_module_path and es_module_class:
            # ES Module approach
            field_html += f"""
            <script type="module">
                import {{ {es_module_class} }} from '{es_module_path}';

                document.addEventListener('DOMContentLoaded', function() {{
                    // Make ES module class available globally for compatibility
                    window.{es_module_class} = {es_module_class};

                    // Initialize the field
                    const fieldContainer = document.querySelector('[data-field-type="{field_type}"]');
                    if (fieldContainer) {{
                        const fieldName = fieldContainer.dataset.fieldName || '{field_config.get('field_name', field_type)}';
                        const instance = new {es_module_class}(fieldName);
                        fieldContainer.pluginInstance = instance;

                        if (typeof instance.initialize === 'function') {{
                            instance.initialize();
                        }} else if (typeof instance.initField === 'function') {{
                            instance.initField('{field_type}', fieldName);
                        }}
                    }}
                }});
            </script>
            """


        return field_html

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
