from app.plugins.base import BasePlugin, BaseFieldType
from typing import List, Dict, Any
from flask import current_app


def _relevance_measures() -> List[Dict[str, Any]]:
    """Measures this plugin exposes for relevance conditions (used only by this plugin)."""
    return [
        {
            'id': 'operations_count',
            'name': 'Operations Count',
            'description': 'Number of operations after applying filters',
            'data_attribute': 'data-operations-count',
            'value_type': 'number'
        },
    ]


def _label_variables() -> List[Dict[str, Any]]:
    """Variables for section/item labels (suggested when typing "["). Keys EO1, EO2, EO3 = "Name (CODE)"."""
    return [
        {'key': 'EO1', 'label': 'First Emergency Operation (name and code)'},
        {'key': 'EO2', 'label': 'Second Emergency Operation (name and code)'},
        {'key': 'EO3', 'label': 'Third Emergency Operation (name and code)'},
    ]


class EmergencyOperationsFieldType(BaseFieldType):
    @property
    def type_name(self) -> str:
        return "emergency_operations"

    @property
    def display_name(self) -> str:
        return "Emergency Operations (GO)"

    @property
    def category(self) -> str:
        return "data"

    @property
    def description(self) -> str:
        return "Lists current active IFRC operations for the country"

    @property
    def icon(self) -> str:
        return "fas fa-flag"

    def get_form_builder_config(self) -> Dict[str, Any]:
        # Minimal config; relies on unified modal for standard properties
        # Note: custom_template takes precedence over fields array
        # The fields array below is kept as fallback documentation but won't be used
        # since custom_template is specified
        return {
            'title': 'Emergency Operations Field',
            'icon': self.icon,
            'custom_template': 'builder.html',  # Just the template name - plugin_id will be prepended automatically
            # Fields array kept for reference/fallback, but not used when custom_template exists
            # All field definitions are in templates/builder.html
        }

    def get_relevance_measures(self) -> List[Dict[str, Any]]:
        return _relevance_measures()

    def get_label_variables(self) -> List[Dict[str, Any]]:
        return _label_variables()

    def get_entry_form_config(self) -> Dict[str, Any]:
        return {
            'template': 'field.html',
            'es_module_path': '/plugins/static/emergency_operations/js/emergency_operations_field.js',
            'es_module_class': 'EmergencyOperationsField',
            'css_files': ['/plugins/static/emergency_operations/css/emergency_operations_field.css'],
            'schema_version': '1.0.0',
            'data_attributes': [
                'data-field-id', 'data-can-edit', 'data-existing-data', 'data-country-iso', 'data-plugin-config',
                'data-operations-count', 'data-eo1', 'data-eo2', 'data-eo3'
            ]
        }

    def validate_config(self, config: Dict[str, Any]) -> bool:
        try:
            max_items = config.get('max_items', 10)
            if not isinstance(max_items, int) or max_items < 1 or max_items > 100:
                return False

            # Validate operation_types if present
            operation_types = config.get('operation_types', ['All'])
            if not isinstance(operation_types, list):
                return False

            valid_types = ['All', 'Emergency Appeal', 'DREF']
            for op_type in operation_types:
                if op_type not in valid_types:
                    return False

            return True
        except Exception as e:
            current_app.logger.error(f"EmergencyOperations config validation failed: {e}")
            return False


class EmergencyOperationsPlugin(BasePlugin):
    @property
    def plugin_id(self) -> str:
        return "emergency_operations"

    @property
    def display_name(self) -> str:
        return "Emergency Operations Plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Provides a field type that lists active IFRC operations for a country using GO API"

    @property
    def author(self) -> str:
        return "IFRC Development Team"

    @property
    def license(self) -> str:
        return "MIT"

    def get_field_types(self) -> List[BaseFieldType]:
        return [EmergencyOperationsFieldType()]

    def get_blueprint(self):
        """Return blueprint for plugin-specific routes with unique import path."""
        try:
            import importlib
            module = importlib.import_module('plugins.emergency_operations.routes')
            return module.create_blueprint()
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("Plugin routes import failed, using local fallback: %s", e)
            # Fallback: local import using plugin directory on sys.path
            import sys
            import os
            plugin_dir = os.path.dirname(__file__)
            if plugin_dir not in sys.path:
                sys.path.insert(0, plugin_dir)
            from routes import create_blueprint
            return create_blueprint()

    def activate(self) -> bool:
        return True

    def deactivate(self) -> bool:
        return True

    def get_lookup_lists(self) -> List[Dict[str, Any]]:
        """
        Get lookup lists provided by this plugin for form builder integration.

        Returns:
            List of lookup list configurations
        """
        try:
            # Try relative import first
            from .routes import get_emergency_operations_lookup_list
            return [get_emergency_operations_lookup_list()]
        except ImportError:
            # Fallback to absolute import
            from plugins.emergency_operations.routes import get_emergency_operations_lookup_list
            return [get_emergency_operations_lookup_list()]
