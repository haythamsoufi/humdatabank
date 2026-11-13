# Backoffice/app/utils/forms/plugin_data_processor.py

import json
import logging
from typing import Dict, Any, Optional, Tuple
from flask import current_app

from app.plugins.base import _CLIENT_METADATA_KEYS
from app.utils.forms.schema_validation import (
    validate_plugin_data,
    sanitize_plugin_data,
    SchemaValidationError
)

logger = logging.getLogger(__name__)

# Hard ceiling for any plugin field value, checked before it is parsed. Field types
# declare tighter limits through get_data_storage_config()['max_size'].
MAX_RAW_PLUGIN_VALUE_BYTES = 4 * 1024 * 1024

class PluginDataProcessor:
    """Handles processing and validation of plugin field data during form submissions."""

    def __init__(self):
        self.plugin_manager = None
        self.processed_cache = {}

    def initialize(self, plugin_manager):
        """Initialize with plugin manager instance."""
        self.plugin_manager = plugin_manager

    def process_plugin_field_data(self, field_name: str, field_value: str, form_item_id: int) -> Tuple[bool, str, Optional[str]]:
        """
        Process and validate plugin field data.

        Args:
            field_name: Name of the form field (e.g., 'field_value[123]')
            field_value: Raw field value as string
            form_item_id: ID of the form item

        Returns:
            Tuple of (is_valid, processed_value, error_message)
        """
        try:
            # Check if this is a plugin field
            plugin_type = self._get_plugin_type_for_field(form_item_id)
            if not plugin_type:
                # Not a plugin field, return unchanged
                return True, field_value, None

            logger.info(f"Processing plugin field {field_name} of type {plugin_type}")

            if isinstance(field_value, str) and len(field_value.encode('utf-8')) > MAX_RAW_PLUGIN_VALUE_BYTES:
                return False, field_value, "Plugin data exceeds size limit."

            # Parse the field value
            try:
                data = json.loads(field_value) if field_value else {}
            except json.JSONDecodeError:
                # Not JSON data, return as-is for text fields
                return True, field_value, None

            field_type = self._resolve_field_type(plugin_type)

            # Display-only field types (normalize_value -> None) never store anything.
            if not data and field_type is not None and field_type.normalize_value({}, {}) is None:
                return True, None, None

            # Get plugin configuration for validation
            plugin_config = self._get_plugin_config(plugin_type, form_item_id)
            if not plugin_config:
                logger.warning(f"No plugin config found for {plugin_type}")
                return True, field_value, None

            # Generic plugin data processing for all plugins
            return self._process_generic_plugin_data(data, plugin_type, plugin_config, field_type)

        except Exception as e:
            logger.error(f"Error processing plugin field {field_name}: {e}", exc_info=True)
            return False, field_value, "Plugin data processing failed."

    def _get_plugin_type_for_field(self, form_item_id: int) -> Optional[str]:
        """Get the plugin type for a form item."""
        try:
            # Import locally to avoid circular imports
            from app.models import FormItem
            form_item = FormItem.query.get(form_item_id)

            if not form_item:
                return None

            # Check if this is a plugin field based on item type
            if hasattr(form_item, 'item_type') and form_item.item_type and form_item.item_type.startswith('plugin_'):
                return form_item.item_type.replace('plugin_', '')

            return None

        except Exception as e:
            logger.warning(f"Could not determine plugin type for form item {form_item_id}: {e}")
            return None

    def _get_plugin_config(self, plugin_type: str, form_item_id: int) -> Optional[Dict[str, Any]]:
        """Get the plugin configuration for validation."""
        try:
            # Import locally to avoid circular imports
            from app.models import FormItem
            form_item = FormItem.query.get(form_item_id)

            if not form_item or not hasattr(form_item, 'plugin_config'):
                return {}

            # Get the stored plugin configuration
            return form_item.plugin_config or {}

        except Exception as e:
            logger.warning(f"Could not get plugin config for {plugin_type}: {e}")
            return {}


    def _resolve_field_type(self, plugin_type: str):
        """Field type instance for ``plugin_type``, including field types of inactive plugins."""
        manager = self.plugin_manager
        if manager is None:
            return None
        try:
            return manager.get_field_type_any(plugin_type)
        except Exception as exc:
            logger.warning(f"Could not resolve field type {plugin_type}: {exc}")
            return None

    def _process_generic_plugin_data(
        self,
        data: Dict[str, Any],
        plugin_type: str,
        config: Dict[str, Any],
        field_type=None,
    ) -> Tuple[bool, str, Optional[str]]:
        """Normalize, validate and size-check plugin field data before storage."""
        try:
            essential_data = self._extract_essential_plugin_data(data, field_type, config)

            # If essential_data is None, this field type does not store data
            if essential_data is None:
                return True, None, None

            if isinstance(essential_data, dict) and field_type is not None:
                error = field_type.validate_value(essential_data, config)
                if error:
                    return False, json.dumps(essential_data), error

            # Get data storage configuration from plugin
            if self.plugin_manager:
                field_type_config = self.plugin_manager.get_field_type_config(plugin_type)
                if field_type_config:
                    storage_config = field_type_config.get('data_storage_config', {})

                    # Check if plugin has a custom data schema
                    if 'schema' in storage_config:
                        try:
                            validate_plugin_data(essential_data, storage_config['schema'])
                        except SchemaValidationError as e:
                            logger.warning(f"Plugin {plugin_type} data validation failed: {e}")
                            # Try to sanitize
                            essential_data = sanitize_plugin_data(essential_data, storage_config['schema'])

                    # Check size limits (be tolerant of None/invalid types)
                    raw_max_size = storage_config.get('max_size', 10000)  # May be None/str
                    try:
                        max_size = int(raw_max_size) if raw_max_size is not None else 10000
                    except (ValueError, TypeError):
                        max_size = 10000
                    if max_size <= 0:
                        max_size = 10000

                    data_size = len(json.dumps(essential_data).encode('utf-8'))
                    if data_size > max_size:
                        return False, json.dumps(essential_data), f"Plugin data exceeds size limit ({data_size} > {max_size} bytes)"

            processed_value = json.dumps(essential_data)
            return True, processed_value, None

        except Exception as e:
            logger.error(f"Error processing {plugin_type} plugin data: {e}", exc_info=True)
            return False, json.dumps(data), "Plugin data processing failed."

    def _extract_essential_plugin_data(self, data: Any, field_type, config: Dict[str, Any]) -> Any:
        """Ask the field type what to store; fall back to dropping client metadata keys."""
        if not isinstance(data, dict):
            return data
        if field_type is not None:
            return field_type.normalize_value(data, config)
        cleaned = dict(data)
        for key in _CLIENT_METADATA_KEYS:
            cleaned.pop(key, None)
        return cleaned

# Global processor instance
plugin_data_processor = PluginDataProcessor()

def process_form_plugin_data(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process all plugin fields in form data.

    Args:
        form_data: Dictionary of form field names to values

    Returns:
        Processed form data with plugin fields validated and normalized
    """
    processed_data = form_data.copy()
    errors = []

    for field_name, field_value in form_data.items():
        # Check if this is a plugin field (field_value[123] format)
        if field_name.startswith('field_value[') and field_name.endswith(']'):
            try:
                # Extract form item ID
                import re
                match = re.search(r'field_value\[(\d+)\]', field_name)
                if match:
                    form_item_id = int(match.group(1))

                    # Process the plugin field data
                    is_valid, processed_value, error_message = plugin_data_processor.process_plugin_field_data(
                        field_name, field_value, form_item_id
                    )

                    if is_valid:
                        # Only save the field if it has a value (not None)
                        if processed_value is not None:
                            processed_data[field_name] = processed_value
                        # If processed_value is None, skip saving this field entirely
                    else:
                        errors.append(f"Field {field_name}: {error_message}")
                        logger.error(f"Plugin field processing error for {field_name}: {error_message}")

            except Exception as e:
                logger.error(f"Error processing field {field_name}: {e}")
                errors.append(f"Field {field_name}: Processing error")

    # Add errors to processed data if any
    if errors:
        processed_data['_plugin_errors'] = errors

    return processed_data
