"""Form data plugin processing mixin."""

import json
from typing import Dict, List, Optional

from flask import current_app, request
from app.models import db, FormItem
from app.utils.plugin_data_processor import plugin_data_processor
from app.services.forms.processors._common import get_english_field_name
from app.services.monitoring.debug import debug_manager

logger = debug_manager.get_logger(__name__)


class PluginProcessorMixin:
    """Mixin providing plugin processing for FormDataService."""

    @classmethod
    def _process_plugin_fields(cls, section, assignment_entity_status, validation_errors: List, plugin_fields: Optional[List[FormItem]] = None) -> List[Dict]:
        """Process plugin fields in a section"""
        field_changes = []

        if plugin_fields is None:
            plugin_fields = FormItem.query.filter(
                FormItem.section_id == section.id,
                FormItem.item_type.like('plugin_%')
            ).all()

        for plugin_field in plugin_fields:
            try:
                # Initialize plugin data processor if needed
                if not plugin_data_processor.plugin_manager and hasattr(current_app, 'plugin_manager'):
                    plugin_data_processor.initialize(current_app.plugin_manager)

                # Get the field value from request
                field_name = f'field_value[{plugin_field.id}]'
                field_value = request.form.get(field_name, '')

                cls._log_verbose(f"Processing plugin field {field_name}: {field_value}")

                # Process the plugin field data
                is_valid, processed_value, error_message = plugin_data_processor.process_plugin_field_data(
                    field_name, field_value, plugin_field.id
                )

                if is_valid:
                    # Save the processed data
                    changes = cls._save_plugin_field_data(
                        plugin_field, processed_value, assignment_entity_status, validation_errors
                    )
                    field_changes.extend(changes)
                else:
                    validation_errors.append(f"Plugin field '{plugin_field.label}': {error_message}")
                    logger.error(f"Plugin field validation failed: {error_message}")

            except Exception as e:
                logger.error(f"Error processing plugin field {plugin_field.id}: {e}", exc_info=True)
                validation_errors.append(f"Plugin field '{plugin_field.label}': Processing error")

        return field_changes

    @classmethod
    def _save_plugin_field_data(cls, plugin_field: FormItem, processed_value: str, assignment_entity_status, validation_errors: List) -> List[Dict]:
        """Save processed plugin field data"""
        field_changes = []

        # If processed_value is None, this plugin field doesn't save data
        if processed_value is None:
            return field_changes

        try:
            # Get or create form data entry using helper methods
            DataModel = cls._get_data_model(assignment_entity_status)
            query_filter = cls._get_data_query_filter(assignment_entity_status, plugin_field.id)

            data_entry = DataModel.query.filter_by(**query_filter).first()

            if data_entry:
                # Track old value for change detection
                old_value = data_entry.disagg_data if getattr(data_entry, "disagg_data", None) else data_entry.get_effective_value()
                new_effective_value = None

                # Parse the processed value to determine if it's JSON data
                try:
                    json_data = json.loads(processed_value) if processed_value else {}
                    # For plugin data, store JSON in disagg_data and leave value as None
                    data_entry.value = None
                    data_entry.numeric_value = None
                    data_entry.disagg_data = json_data
                    data_entry.disagg_type = 'plugin'
                    new_effective_value = json_data
                except (json.JSONDecodeError, TypeError):
                    # If it's not JSON, store as simple value
                    data_entry.set_simple_value(processed_value)
                    new_effective_value = processed_value

                db.session.add(data_entry)

                # Record the change if value actually changed
                values_changed = False
                if isinstance(old_value, dict) and isinstance(new_effective_value, dict):
                    values_changed = json.dumps(old_value, sort_keys=True) != json.dumps(new_effective_value, sort_keys=True)
                else:
                    values_changed = old_value != new_effective_value

                if values_changed:
                    cls._clear_ai_validation_for_form_data(data_entry, reason="plugin_value_changed")

                if values_changed:
                    # Delegate plugin-specific activity changes to the field type implementation
                    if getattr(plugin_field, 'item_type', '').startswith('plugin_') and plugin_data_processor.plugin_manager:
                        plugin_type = plugin_field.item_type.replace('plugin_', '')
                        field_type = plugin_data_processor.plugin_manager.get_field_type(plugin_type)
                        if field_type and hasattr(field_type, 'compute_field_changes'):
                            try:
                                plugin_changes = field_type.compute_field_changes(
                                    old_value, processed_value, get_english_field_name(plugin_field), plugin_field.id
                                )
                                if isinstance(plugin_changes, list):
                                    field_changes.extend(plugin_changes)
                                else:
                                    field_changes.append({
                                        'type': 'updated',
                                        'form_item_id': plugin_field.id,
                                        'field_name': get_english_field_name(plugin_field),
                                        'old_value': old_value,
                                        'new_value': processed_value
                                    })
                            except Exception as e:
                                current_app.logger.debug("plugin field change diff failed: %s", e)
                                field_changes.append({
                                    'type': 'updated',
                                    'form_item_id': plugin_field.id,
                                    'field_name': get_english_field_name(plugin_field),
                                    'old_value': old_value,
                                    'new_value': processed_value
                                })
                        else:
                            field_changes.append({
                                'type': 'updated',
                                'form_item_id': plugin_field.id,
                                'field_name': get_english_field_name(plugin_field),
                                'old_value': old_value,
                                'new_value': processed_value
                            })
                    else:
                        field_changes.append({
                            'type': 'updated',
                            'form_item_id': plugin_field.id,
                            'field_name': get_english_field_name(plugin_field),
                            'old_value': old_value,
                            'new_value': processed_value
                        })
            else:
                # Create new entry using helper method
                data_entry = cls._create_data_entry(assignment_entity_status, plugin_field.id)

                # Parse the processed value to determine if it's JSON data
                try:
                    json_data = json.loads(processed_value) if processed_value else {}
                    # For plugin data, store JSON in disagg_data and leave value as None
                    data_entry.value = None
                    data_entry.numeric_value = None
                    data_entry.disagg_data = json_data
                    data_entry.disagg_type = 'plugin'
                except (json.JSONDecodeError, TypeError):
                    # If it's not JSON, store as simple value
                    data_entry.set_simple_value(processed_value)

                db.session.add(data_entry)

                # Delegate plugin-specific activity changes for new values
                if getattr(plugin_field, 'item_type', '').startswith('plugin_') and plugin_data_processor.plugin_manager:
                    plugin_type = plugin_field.item_type.replace('plugin_', '')
                    field_type = plugin_data_processor.plugin_manager.get_field_type(plugin_type)
                    if field_type and hasattr(field_type, 'compute_field_changes'):
                        try:
                            plugin_changes = field_type.compute_field_changes(
                                None, processed_value, get_english_field_name(plugin_field), plugin_field.id
                            )
                            if isinstance(plugin_changes, list) and plugin_changes:
                                field_changes.extend(plugin_changes)
                            else:
                                field_changes.append({
                                    'type': 'added',
                                    'form_item_id': plugin_field.id,
                                    'field_name': get_english_field_name(plugin_field),
                                    'old_value': None,
                                    'new_value': processed_value
                                })
                        except Exception as e:
                            current_app.logger.debug("plugin field added diff failed: %s", e)
                            field_changes.append({
                                'type': 'added',
                                'form_item_id': plugin_field.id,
                                'field_name': get_english_field_name(plugin_field),
                                'old_value': None,
                                'new_value': processed_value
                            })
                    else:
                        field_changes.append({
                            'type': 'added',
                            'form_item_id': plugin_field.id,
                            'field_name': get_english_field_name(plugin_field),
                            'old_value': None,
                            'new_value': processed_value
                        })
                else:
                    field_changes.append({
                        'type': 'added',
                        'form_item_id': plugin_field.id,
                        'field_name': get_english_field_name(plugin_field),
                        'old_value': None,
                        'new_value': processed_value
                    })

            cls._log_verbose(f"Successfully saved plugin field {plugin_field.id}")

        except Exception as e:
            logger.error(f"Error saving plugin field data: {e}", exc_info=True)
            validation_errors.append(f"Failed to save plugin field '{plugin_field.label}'")

        return field_changes
