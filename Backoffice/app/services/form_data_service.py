# ========== Form Data Processing Service ==========
from app.utils.datetime_helpers import utcnow
"""
Centralized service for processing form data submissions.
Extracted from the massive handle_assignment_form function to improve maintainability.

This service handles:
- Indicator data processing (including disaggregation)
- Question data processing
- Document uploads
- Dynamic indicator processing
- Repeat group processing
- Data validation and saving

CRITICAL: Maintains exact JavaScript compatibility with field naming patterns and data structures.
"""

from flask import request, flash, current_app, g, has_request_context
from flask_login import current_user
import logging
from app.models import (
    db, FormItem, FormItemType, FormData, AIFormDataValidation,
    RepeatGroupInstance, RepeatGroupData, SubmittedDocument, DynamicIndicatorData
)
from contextlib import suppress
from app.services.monitoring.debug import (
    debug_manager, performance_monitor, debug_request_info,
    debug_database_query, log_user_action, format_error_context
)
from app.services.form_processing_service import (
    FormItemProcessor,
    IndirectReachProcessor,
    get_form_items_for_section,
    should_create_data_availability_entry as unified_should_create,
    _create_dynamic_indicator_object,
)
from app.utils.plugin_data_processor import plugin_data_processor
from app.utils.api_helpers import service_error, GENERIC_ERROR_MESSAGE
from app.utils.form_localization import get_localized_indicator_name
from app.services.notification.core import notify_document_uploaded
from app.utils.file_paths import save_submission_document
from app.utils.submitted_document_policy import user_may_delete_or_replace_submitted_document_file
from app.utils.file_scanning import scan_file_for_viruses, FileScanError
from werkzeug.utils import secure_filename
from datetime import datetime
import json
import os
from typing import Dict, List, Tuple, Any, Optional
from app.models import QuestionType
from app.utils.transactions import request_transaction_rollback, register_post_commit

# Create a specific logger for this module using the debug manager
logger = debug_manager.get_logger(__name__)


def get_english_field_name(form_item):
    """Get the English field name for fallback storage in activity logging."""
    # Always return the default English label for fallback storage
    return form_item.label


class FormDataService:
    """
    Service for processing form data submissions with JavaScript compatibility.

    Maintains exact field naming patterns and data structures expected by:
    - field-management.js
    - disaggregation-calculator.js
    - data-availability.js
    - repeat-sections.js
    """
    @staticmethod
    def _is_verbose_logging_enabled() -> bool:
        """
        Check if verbose form data logging is enabled via configuration.
        Enables full POST dumps (see debug_utils), per-section trace lines in
        FormDataService, and per-section template prep logs. Set env
        VERBOSE_FORM_DATA_LOGGING=true (see config).
        """
        if not has_request_context():
            return False
        return current_app.config.get('VERBOSE_FORM_DATA_LOGGING', False)

    @classmethod
    def _log_verbose(cls, message: str, *args, **kwargs):
        """
        Log verbose information only if verbose logging is enabled.
        Use this for detailed per-item logging that can be excessive in production.
        """
        if cls._is_verbose_logging_enabled():
            logger.info(message, *args, **kwargs)

    @staticmethod
    def _is_auto_managed_request() -> bool:
        """
        Determine if the current execution is inside an auto-managed Flask request.
        """
        if not has_request_context():
            return False
        return bool(getattr(g, "_auto_txn_managed", False))

    @classmethod
    def _commit_or_flush(cls) -> None:
        """
        Flush changes during managed requests, otherwise commit immediately.
        """
        if cls._is_auto_managed_request():
            db.session.flush()
        else:
            db.session.commit()

    @staticmethod
    def _rollback_transaction(reason: str) -> None:
        """
        Roll back the current transaction and notify the middleware when applicable.
        """
        request_transaction_rollback(reason=reason)

    @classmethod
    def _clear_ai_validation_for_form_data(cls, data_entry: FormData, *, reason: str | None = None) -> None:
        """
        Clear any stored AI validation opinion for a FormData row.

        Rationale: AI opinions are "latest-only" and can become stale when the
        underlying FormData value/disaggregation/availability flags change.
        """
        if not data_entry or not getattr(data_entry, "id", None):
            return

        try:
            deleted = (
                AIFormDataValidation.query.filter_by(form_data_id=int(data_entry.id))
                .delete(synchronize_session=False)
            )
            if deleted:
                cls._log_verbose(
                    "Cleared AI validation for FormData %s (reason=%s)",
                    data_entry.id,
                    reason or "value_changed",
                )

            # Avoid stale relationship usage within the same session if it was already loaded.
            if hasattr(data_entry, "__dict__") and "ai_validation" in data_entry.__dict__:
                data_entry.ai_validation = None
        except Exception as e:
            logger.error(
                "Failed to clear AI validation for FormData %s: %s",
                getattr(data_entry, "id", None),
                e,
                exc_info=True,
            )

    @classmethod
    @performance_monitor("Form Submission Processing")
    def process_form_submission(cls, assignment_entity_status, all_sections: List, csrf_form=None) -> Dict[str, Any]:
        """
        Main entry point for processing form submissions.

        Args:
        assignment_entity_status: Either an AssignmentEntityStatus or PublicSubmission object
        all_sections: List of form sections to process
        csrf_form: CSRF form for validation (optional for public submissions)

        Returns:
            Dict with submission results: {
                'success': bool,
                'field_changes': List,
                'validation_errors': List,
                'redirect_url': str (optional)
            }
        """
        # Enhanced debugging (form body: summary only unless VERBOSE_FORM_DATA_LOGGING)
        debug_request_info(logger)
        action = request.form.get('action')

        logger.debug("Processing form submission: action=%s, sections=%s", action, len(all_sections))

        # CSRF validation is optional (not needed for public submissions)
        if csrf_form and not csrf_form.validate_on_submit():
            logger.debug("CSRF validation failed in FormDataService")
            return {
                'success': False,
                'validation_errors': ['Form submission failed due to security validation.'],
                'field_changes': []
            }

        # Determine if this is a public submission using the helper method
        is_public_submission = cls._is_public_submission(assignment_entity_status)

        action = request.form.get('action')
        # When action is 'save', do not block on required fields (including required matrix)
        skip_required_validation = (action == 'save')
        field_changes_tracker = []
        validation_errors = []

        try:
            # Process hidden fields first - clear their database records
            hidden_fields_changes = cls._process_hidden_fields_clearing(assignment_entity_status)
            field_changes_tracker.extend(hidden_fields_changes)

            verbose_section_trace = cls._is_verbose_logging_enabled()

            # Process each section type
            for section in all_sections:
                if verbose_section_trace:
                    logger.debug("Processing section %s of type %s", section.id, section.section_type)

                # Process standard form items (indicators, questions, documents)
                section_changes = cls._process_section_data(
                    section, assignment_entity_status, validation_errors,
                    skip_required_validation=skip_required_validation
                )
                field_changes_tracker.extend(section_changes)

                # Process dynamic indicators for dynamic sections
                if section.section_type == 'dynamic_indicators':
                    if verbose_section_trace:
                        logger.debug("Processing dynamic indicators for section %s", section.id)
                    dynamic_changes = cls._process_dynamic_indicators(
                        section, assignment_entity_status, validation_errors
                    )
                    field_changes_tracker.extend(dynamic_changes)

                # Process repeat groups for repeat sections
                if section.section_type == 'repeat':
                    if verbose_section_trace:
                        logger.debug("Processing repeat groups for section %s", section.id)
                    repeat_changes = cls._process_repeat_groups(
                        section, assignment_entity_status, validation_errors
                    )
                    field_changes_tracker.extend(repeat_changes)
                    if verbose_section_trace:
                        logger.debug(
                            "Repeat processing completed for section %s with %s changes",
                            section.id,
                            len(repeat_changes),
                        )

            # Availability flags are handled during field processing; skip redundant pass

            # Update assignment status if needed
            if assignment_entity_status.status == "Pending":
                assignment_entity_status.status = "In Progress"

            # Persist changes (middleware will commit if we're in a managed request)
            cls._commit_or_flush()

            logger.debug(f"FormDataService: Committed changes, action: {action}")

            # Handle submission vs save
            if action == 'submit':
                logger.debug("FormDataService: Processing submit action")
                validation_result = cls._validate_for_submission(
                    all_sections, assignment_entity_status
                )
                if validation_result['is_valid']:
                    assignment_entity_status.status = "Submitted"
                    now = utcnow()
                    assignment_entity_status.status_timestamp = now
                    assignment_entity_status.submitted_at = now
                    # Record who submitted (governance accountability)
                    try:
                        from flask_login import current_user as _cu
                        if _cu and _cu.is_authenticated:
                            assignment_entity_status.submitted_by_user_id = _cu.id
                    except Exception as e:
                        current_app.logger.debug("submitted_by_user_id assignment failed: %s", e)
                    cls._commit_or_flush()
                    result = {
                        'success': True,
                        'field_changes': field_changes_tracker,
                        'validation_errors': [],
                        'submitted': True
                    }
                    logger.debug(f"FormDataService: Returning submit result: {result}")
                    return result
                else:
                    validation_errors.extend(validation_result['errors'])
                    logger.debug(f"FormDataService: Submit validation failed: {validation_errors}")

            success = len(validation_errors) == 0
            result = {
                'success': success,
                'field_changes': field_changes_tracker,
                'validation_errors': validation_errors,
                'submitted': False
            }
            if success:
                logger.debug(f"FormDataService: Returning save result: {result}")
            else:
                logger.debug(f"FormDataService: Returning validation failure: {result}")
            return result

        except Exception as e:
            cls._rollback_transaction("form_submission_error")

            # Enhanced error logging with context
            error_context = {
                'action': action,
                'sections_count': len(all_sections),
                'assignment_id': assignment_entity_status.id,
                'user_id': current_user.id if current_user.is_authenticated else None
            }

            error_msg = format_error_context(e, error_context)
            logger.error(f"Form submission error: {error_msg}")

            # Log user action for audit
            log_user_action(
                "Form Submission Failed",
                {'error': 'Form submission failed', 'assignment_id': assignment_entity_status.id},
                logger=logger
            )

            error_result = {
                'success': False,
                'field_changes': field_changes_tracker,
                'validation_errors': [f"An error occurred while processing the form. Please try again."]
            }
            return error_result

    @classmethod
    @performance_monitor("Section Data Processing", quiet=True)
    def _process_section_data(cls, section, assignment_entity_status, validation_errors: List, *, skip_required_validation: bool = False) -> List[Dict]:
        """Process standard form items in a section (indicators, questions, documents)"""
        field_changes = []

        # Skip repeat sections - they're processed separately
        if section.section_type == 'repeat':
            return field_changes

        section_items = FormItem.query.filter_by(section_id=section.id).all()
        if not section_items:
            return field_changes
        section_items.sort(key=lambda item: getattr(item, 'order', getattr(item, 'id', 0)))

        plugin_fields = [item for item in section_items if item.item_type and item.item_type.startswith('plugin_')]
        indicators = [item for item in section_items if item.item_type == 'indicator']
        questions = [item for item in section_items if item.item_type == 'question']
        documents = [item for item in section_items if item.item_type == 'document_field']
        matrices = [item for item in section_items if item.item_type == 'matrix']

        if plugin_fields:
            plugin_changes = cls._process_plugin_fields(
                section,
                assignment_entity_status,
                validation_errors,
                plugin_fields=plugin_fields,
            )
            field_changes.extend(plugin_changes)

        for indicator in indicators:
            changes = cls._process_indicator_data(indicator, assignment_entity_status, validation_errors)
            field_changes.extend(changes)

        for question in questions:
            changes = cls._process_question_data(question, assignment_entity_status, validation_errors)
            field_changes.extend(changes)

        for document in documents:
            changes = cls._process_document_upload(document, assignment_entity_status, validation_errors)
            field_changes.extend(changes)

        for matrix in matrices:
            changes = cls._process_matrix_data(matrix, assignment_entity_status, validation_errors, skip_required_validation=skip_required_validation)
            field_changes.extend(changes)

        return field_changes

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
                    data_entry.disagg_data = json_data
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
                    data_entry.disagg_data = json_data
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

    # Removed plugin-specific diffing; delegated to plugin via plugin_manager

    @classmethod
    def _process_hidden_fields_clearing(cls, assignment_entity_status) -> List[Dict]:
        """
        Process hidden fields by clearing their database records.
        Hidden fields are identified by the 'hidden_fields_to_clear' form parameter.
        """
        field_changes = []

        # Get the list of hidden field IDs from the form
        hidden_fields_param = request.form.get('hidden_fields_to_clear', '').strip()
        if not hidden_fields_param:
            if cls._is_verbose_logging_enabled():
                logger.debug("No hidden fields to clear")
            return field_changes

        try:
            hidden_field_ids = [int(fid.strip()) for fid in hidden_fields_param.split(',') if fid.strip().isdigit()]
            cls._log_verbose(f"Processing {len(hidden_field_ids)} hidden fields for clearing: {hidden_field_ids}")

            for field_id in hidden_field_ids:
                try:
                    # Get the form item to determine its type
                    form_item = FormItem.query.filter_by(id=field_id).first()
                    if not form_item:
                        continue

                    # Clear the field data
                    field_change = cls._clear_hidden_field_data(form_item, assignment_entity_status)
                    if field_change:
                        field_changes.append(field_change)

                except Exception as e:
                    logger.error(f"Error clearing hidden field {field_id}: {e}", exc_info=True)
                    continue

        except Exception as e:
            logger.error(f"Error processing hidden fields parameter '{hidden_fields_param}': {e}", exc_info=True)

            cls._log_verbose(f"Cleared {len(field_changes)} hidden fields from database")
        return field_changes

    @classmethod
    def _clear_hidden_field_data(cls, form_item: FormItem, assignment_entity_status) -> Dict:
        """
        Clear database records for a hidden field.
        """
        cls._log_verbose(f"Clearing database records for hidden field {form_item.id} ({form_item.item_type})")

        # Get existing form data entry using helper methods
        DataModel = cls._get_data_model(assignment_entity_status)
        query_filter = cls._get_data_query_filter(assignment_entity_status, form_item.id)

        data_entry = DataModel.query.filter_by(**query_filter).first()

        if not data_entry:
            if cls._is_verbose_logging_enabled():
                logger.debug(f"No existing data to clear for hidden field {form_item.id}")
            return None

        # Track old value for change detection
        old_value = data_entry.get_effective_value()
        old_data_not_available = data_entry.data_not_available
        old_not_applicable = data_entry.not_applicable

        # Clear the field completely
        data_entry.value = None
        data_entry.data_not_available = False
        data_entry.not_applicable = False

        # Clear disaggregation data if it exists
        if hasattr(data_entry, 'disagg_data') and data_entry.disagg_data:
            data_entry.disagg_data = db.null()

        # Clear any AI opinion since the underlying value is being cleared/removed.
        cls._clear_ai_validation_for_form_data(data_entry, reason="hidden_field_cleared")

        # Mark for deletion or update
        if cls._has_meaningful_data(data_entry):
            # Update the record with cleared values
            db.session.add(data_entry)
            change_type = 'cleared'
        else:
            # Delete the record entirely if it has no meaningful data
            db.session.delete(data_entry)
            change_type = 'deleted'

        # Record the change
        field_change = {
            'type': change_type,
            'form_item_id': form_item.id,
            'field_name': get_english_field_name(form_item),
            'old_value': old_value,
            'new_value': None,
            'old_data_not_available': old_data_not_available,
            'new_data_not_available': False,
            'old_not_applicable': old_not_applicable,
            'new_not_applicable': False,
            'reason': 'field_hidden_by_relevance_condition'
        }

        cls._log_verbose(f"Hidden field {form_item.id} {change_type}: {old_value} -> None")
        return field_change

    @classmethod
    def _check_for_field_clearing_signals(cls, item_id: int) -> bool:
        """
        Check if JavaScript has sent a signal to clear this field.
        JavaScript sends field_name + '_clear_field' = 'CLEAR_FIELD_VALUE' when all checkboxes are unchecked.
        """
        # Check all possible checkbox field name patterns
        clear_signal_patterns = [
            f'indicator_{item_id}_standard_value_clear_field',
            f'field_value[{item_id}]_clear_field'
        ]

        # Also check for dynamic field patterns
        for key in request.form.keys():
            if key.endswith('_clear_field') and f'_{item_id}_' in key:
                clear_signal_patterns.append(key)

        for pattern in clear_signal_patterns:
            if pattern in request.form and request.form.get(pattern) == 'CLEAR_FIELD_VALUE':
                cls._log_verbose(f"Field clearing signal detected for item {item_id}: {pattern}")
                return True

        return False

    @classmethod
    def _handle_field_clearing(cls, form_item: FormItem, assignment_entity_status, field_changes: List) -> List[Dict]:
        """
        Handle explicit field clearing by setting the field value to None and clearing data availability flags.
        """
        cls._log_verbose(f"Clearing field {form_item.id} due to JavaScript signal")

        # Get existing form data entry using helper methods
        DataModel = cls._get_data_model(assignment_entity_status)
        query_filter = cls._get_data_query_filter(assignment_entity_status, form_item.id)

        data_entry = DataModel.query.filter_by(**query_filter).first()

        if data_entry:
            # Track old value for change detection
            old_value = data_entry.get_effective_value()
            old_data_not_available = data_entry.data_not_available
            old_not_applicable = data_entry.not_applicable

            # Clear the field completely
            data_entry.value = None
            data_entry.data_not_available = False
            data_entry.not_applicable = False

            # Clear disaggregation data if it exists
            if hasattr(data_entry, 'disagg_data') and data_entry.disagg_data:
                data_entry.disagg_data = db.null()

            db.session.add(data_entry)

            # Clear any AI opinion since the underlying value is being cleared explicitly.
            cls._clear_ai_validation_for_form_data(data_entry, reason="explicit_field_cleared")

            # Record the change
            field_changes.append({
                'type': 'cleared',
                'form_item_id': form_item.id,
                'field_name': get_english_field_name(form_item),
                'old_value': old_value,
                'new_value': None,
                'old_data_not_available': old_data_not_available,
                'new_data_not_available': False,
                'old_not_applicable': old_not_applicable,
                'new_not_applicable': False
            })

            cls._log_verbose(f"Field {form_item.id} cleared: {old_value} -> None")
        else:
            cls._log_verbose(f"No existing data to clear for field {form_item.id}")

        return field_changes

    @classmethod
    def _process_indicator_data(cls, indicator: FormItem, assignment_entity_status, validation_errors: List) -> List[Dict]:
        """
        Process indicator data with JavaScript-compatible field patterns.

        Maintains exact naming patterns:
        - indicator_{item_id}_total_value
        - indicator_{item_id}_reporting_mode
        - indicator_{item_id}_data_not_available
        """
        field_changes = []
        field_prefix = f'indicator_{indicator.id}'

        # Check for explicit field clearing signals from JavaScript
        field_cleared = cls._check_for_field_clearing_signals(indicator.id)
        if field_cleared:
            # Handle field clearing
            return cls._handle_field_clearing(indicator, assignment_entity_status, field_changes)

        # Use FormItemProcessor for unified processing
        processed_value, has_value, data_not_available, not_applicable = \
            FormItemProcessor.process_form_item_data(
                indicator, request.form, assignment_entity_status.id, field_prefix
            )

        # Check if the indicator field was submitted (even if empty) - this allows us to clear existing values
        # Indicators can have total_value or standard_value fields
        total_value_field = f'{field_prefix}_total_value'
        standard_value_field = f'{field_prefix}_standard_value'
        # Check if field exists in form (even if empty string) - empty number inputs still submit as empty strings
        total_value_raw = request.form.get(total_value_field)
        standard_value_raw = request.form.get(standard_value_field)
        # Field was submitted if it's in the form (even if value is empty string)
        field_was_submitted = (total_value_field in request.form) or (standard_value_field in request.form)

        # Get or create form data entry using helper methods
        form_item_id = indicator.id
        DataModel = cls._get_data_model(assignment_entity_status)
        query_filter = cls._get_data_query_filter(assignment_entity_status, form_item_id)

        data_entry = DataModel.query.filter_by(**query_filter).first()

        is_presave = request.form.get('ifrc_presave') == '1'

        # Handle the case where field was submitted but has no value (clearing existing value)
        # This happens when user clears a field - it's submitted as empty string but has_value is False
        if field_was_submitted and not has_value and not data_not_available and not not_applicable:
            # IMPORTANT: For presave (save-before-submit) requests we must NOT clear existing values
            # just because empty strings were submitted for untouched fields.
            if is_presave:
                logger.info(
                    "Indicator %s: presave request submitted empty (total_value=%r, standard_value=%r); "
                    "skipping clear to avoid overwriting existing values.",
                    form_item_id,
                    total_value_raw,
                    standard_value_raw,
                )
                return field_changes

            cls._log_verbose(f"Indicator {form_item_id}: Field was submitted empty (total_value='{total_value_raw}', standard_value='{standard_value_raw}'), "
                       f"has_value={has_value}, clearing existing value. data_entry exists={data_entry is not None}")
            if data_entry:
                # Track old value and data availability flags for change detection
                old_value = data_entry.get_effective_value()
                if data_entry.disagg_data:
                    old_value = data_entry.disagg_data
                old_data_not_available = data_entry.data_not_available
                old_not_applicable = data_entry.not_applicable

                # Clear the existing value
                cls._update_indicator_entry(data_entry, indicator, None, False, False)
                db.session.add(data_entry)

                # Record the change
                if old_value is not None or old_data_not_available or old_not_applicable:
                    cls._clear_ai_validation_for_form_data(data_entry, reason="indicator_value_cleared")
                    field_changes.append({
                        'type': 'updated',
                        'form_item_id': form_item_id,
                        'field_name': get_english_field_name(indicator),
                        'old_value': old_value,
                        'new_value': None,
                        'old_data_not_available': old_data_not_available,
                        'new_data_not_available': False,
                        'old_not_applicable': old_not_applicable,
                        'new_not_applicable': False
                    })
            # If no existing entry and field was submitted empty, nothing to do
            return field_changes

        if has_value or data_not_available or not_applicable:
            if data_entry:
                # Track old value and data availability flags for change detection
                old_value = data_entry.get_effective_value()
                if data_entry.disagg_data:
                    old_value = data_entry.disagg_data

                # Check if data availability flags have changed
                old_data_not_available = data_entry.data_not_available
                old_not_applicable = data_entry.not_applicable

                # Update with new data
                cls._update_indicator_entry(data_entry, indicator, processed_value, data_not_available, not_applicable)

                # Determine if there's a meaningful change
                value_changed = old_value != processed_value
                availability_changed = (old_data_not_available != data_not_available) or (old_not_applicable != not_applicable)

                if value_changed or availability_changed:
                    cls._clear_ai_validation_for_form_data(data_entry, reason="indicator_value_changed")
                    field_changes.append({
                        'type': 'updated',
                        'form_item_id': form_item_id,
                        'field_name': get_english_field_name(indicator),
                        'old_value': old_value,
                        'new_value': processed_value,
                        'old_data_not_available': old_data_not_available,
                        'new_data_not_available': data_not_available,
                        'old_not_applicable': old_not_applicable,
                        'new_not_applicable': not_applicable
                    })
            else:
                # Create new entry using helper method
                data_entry = cls._create_data_entry(assignment_entity_status, form_item_id)
                cls._update_indicator_entry(data_entry, indicator, processed_value, data_not_available, not_applicable)
                db.session.add(data_entry)

                field_changes.append({
                    'type': 'added',
                    'form_item_id': form_item_id,
                    'field_name': get_english_field_name(indicator),
                    'old_value': None,
                    'new_value': processed_value
                })

        return field_changes

    @classmethod
    def _update_indicator_entry(cls, data_entry: FormData, indicator: FormItem,
                               processed_value, data_not_available: bool, not_applicable: bool):
        """Update FormData entry with indicator data maintaining JS compatibility"""

        # Set data availability flags first
        data_entry.set_data_availability(data_not_available, not_applicable)

        # Only update the value if we don't have data availability flags set
        if not data_not_available and not not_applicable:
            if processed_value is not None:
                # Check if processed_value is a disaggregated data structure
                if isinstance(processed_value, dict) and 'mode' in processed_value and 'values' in processed_value:
                    # It's disaggregated data, extract mode and values
                    mode = processed_value['mode']
                    values = processed_value['values']
                    data_entry.set_disaggregated_data(mode, values)
                else:
                    # It's simple data
                    data_entry.set_simple_value(processed_value)
            else:
                data_entry.set_simple_value(None)

    @classmethod
    def _calculate_direct_total(cls, direct_values) -> float:
        """Calculate total from direct values structure"""
        if isinstance(direct_values, dict):
            return sum(value for value in direct_values.values() if isinstance(value, (int, float)))
        elif isinstance(direct_values, (int, float)):
            return direct_values
        return 0

    @classmethod
    def _calculate_total_from_values(cls, values: Dict) -> float:
        """Calculate total from disaggregated values"""
        total = 0
        for value in values.values():
            if isinstance(value, (int, float)):
                total += value
        return total

    @classmethod
    def _process_question_data(cls, question: FormItem, assignment_entity_status, validation_errors: List) -> List[Dict]:
        """
        Process question data via unified FormItemProcessor to centralize logic.
        """
        field_changes = []
        field_prefix = f"question_{question.id}"

        # Check for explicit field clearing signals from JavaScript
        field_cleared = cls._check_for_field_clearing_signals(question.id)
        if field_cleared:
            # Handle field clearing
            return cls._handle_field_clearing(question, assignment_entity_status, field_changes)

        processed_value, has_value, data_not_available, not_applicable = FormItemProcessor.process_form_item_data(
            question, request.form, assignment_entity_status.id, field_prefix=field_prefix
        )

        # Check if the field was submitted (even if empty) - this allows us to clear existing values
        field_name = f'field_value[{question.id}]'
        field_was_submitted = field_name in request.form

        # Get or create form data entry using helper methods
        form_item_id = question.id
        DataModel = cls._get_data_model(assignment_entity_status)
        query_filter = cls._get_data_query_filter(assignment_entity_status, form_item_id)

        data_entry = DataModel.query.filter_by(**query_filter).first()

        is_presave = request.form.get('ifrc_presave') == '1'

        # Handle the case where field was submitted but has no value (clearing existing value)
        if field_was_submitted and not has_value and not data_not_available and not not_applicable:
            if is_presave:
                cls._log_verbose(
                    "Question %s: presave request submitted empty; skipping clear to avoid overwriting existing values.",
                    form_item_id,
                )
                return field_changes

            if data_entry:
                # Track old value and data availability flags for change detection
                old_value = data_entry.get_effective_value()
                old_data_not_available = data_entry.data_not_available
                old_not_applicable = data_entry.not_applicable

                # Clear the existing value
                data_entry.set_simple_value(None)
                data_entry.set_data_availability(False, False)
                db.session.add(data_entry)

                # Record the change
                if old_value is not None or old_data_not_available or old_not_applicable:
                    cls._clear_ai_validation_for_form_data(data_entry, reason="question_value_cleared")
                    field_changes.append({
                        'type': 'updated',
                        'form_item_id': form_item_id,
                        'field_name': get_english_field_name(question),
                        'old_value': old_value,
                        'new_value': None,
                        'old_data_not_available': old_data_not_available,
                        'new_data_not_available': False,
                        'old_not_applicable': old_not_applicable,
                        'new_not_applicable': False
                    })
            # If no existing entry and field was submitted empty, nothing to do
            return field_changes

        if has_value or data_not_available or not_applicable:
            if data_entry:
                # Track old value and data availability flags for change detection
                old_value = data_entry.get_effective_value()
                old_data_not_available = data_entry.data_not_available
                old_not_applicable = data_entry.not_applicable

                # Set data availability flags first
                data_entry.set_data_availability(data_not_available, not_applicable)
                # Only set value if we have a value AND no data availability flags
                if processed_value is not None and not data_not_available and not not_applicable:
                    data_entry.set_simple_value(processed_value)

                db.session.add(data_entry)

                # Determine if there's a meaningful change
                value_changed = old_value != processed_value
                availability_changed = (old_data_not_available != data_not_available) or (old_not_applicable != not_applicable)

                if value_changed or availability_changed:
                    cls._clear_ai_validation_for_form_data(data_entry, reason="question_value_changed")
                    field_changes.append({
                        'type': 'updated',
                        'form_item_id': form_item_id,
                        'field_name': get_english_field_name(question),
                        'old_value': old_value,
                        'new_value': processed_value,
                        'old_data_not_available': old_data_not_available,
                        'new_data_not_available': data_not_available,
                        'old_not_applicable': old_not_applicable,
                        'new_not_applicable': not_applicable
                    })
            else:
                # Create new entry using helper method
                data_entry = cls._create_data_entry(assignment_entity_status, form_item_id)
                # Set data availability flags first
                data_entry.set_data_availability(data_not_available, not_applicable)
                # Only set value if we have a value AND no data availability flags
                if processed_value is not None and not data_not_available and not not_applicable:
                    data_entry.set_simple_value(processed_value)

                db.session.add(data_entry)

                field_changes.append({
                    'type': 'added',
                    'form_item_id': form_item_id,
                    'field_name': get_english_field_name(question),
                    'old_value': None,
                    'new_value': processed_value
                })

        return field_changes

    @classmethod
    def _process_question_value(cls, question: FormItem, raw_value, field_name: str):
        """Process question value based on type"""
        if raw_value is None:
            return None

        if question.type == 'number':
            try:
                return str(int(raw_value)) if raw_value and str(raw_value).strip() else None
            except ValueError:
                flash(f"Invalid number for question '{question.label}'.", "warning")
                return None

        elif question.type == 'percentage':
            try:
                return str(float(raw_value)) if raw_value and str(raw_value).strip() else None
            except ValueError:
                flash(f"Invalid percentage for question '{question.label}'.", "warning")
                return None

        elif question.type == 'multiple_choice':
            selected_options = request.form.getlist(field_name)
            return json.dumps(selected_options) if selected_options else None

        elif question.type == 'CHECKBOX':
            return 'true' if raw_value else 'false'

        else:
            return str(raw_value).strip() if raw_value and isinstance(raw_value, str) and str(raw_value).strip() else None

    @classmethod
    def _add_indirect_reach_to_question(cls, question: FormItem, final_value):
        """Add indirect reach processing to questions"""
        indirect_reach_str = request.form.get(f'question_{question.id}_indirect_reach', '')
        if indirect_reach_str and indirect_reach_str.strip() and final_value is not None:
            try:
                if question.type == 'number':
                    indirect_reach_value = int(indirect_reach_str)
                elif question.type == 'percentage':
                    indirect_reach_value = float(indirect_reach_str)
                else:
                    indirect_reach_value = int(indirect_reach_str)

                # Create disaggregation structure for questions with indirect reach
                disaggregation_data = {
                    'mode': 'total',
                    'values': {
                        'total': final_value,
                        'indirect_reach': indirect_reach_value
                    }
                }
                return json.dumps(disaggregation_data)
            except ValueError:
                flash(f"Invalid indirect reach for question '{question.label}'.", "warning")

        return final_value

    @classmethod
    def _process_document_upload(cls, document: FormItem, assignment_entity_status, validation_errors: List) -> List[Dict]:
        """Process document uploads maintaining JavaScript compatibility"""
        field_changes = []

        # Handle new document uploads - support multiple files with the same field name
        file_key = f'field_value[{document.id}]'
        language_key = f'field_language[{document.id}]'
        type_key = f'field_document_type[{document.id}]'
        year_key = f'field_year[{document.id}]'
        public_key = f'field_is_public[{document.id}]'

        # Get all files for this field (supports multiple uploads)
        files_list = request.files.getlist(file_key)
        languages_list = request.form.getlist(language_key)
        types_list = request.form.getlist(type_key)
        years_list = request.form.getlist(year_key)
        publics_list = request.form.getlist(public_key)

        # Filter out empty file uploads and pair with metadata
        valid_files = []
        for i, f in enumerate(files_list):
            if f and f.filename:
                valid_files.append({
                    'file': f,
                    'language': languages_list[i] if i < len(languages_list) else 'en',
                    'document_type': types_list[i] if i < len(types_list) else None,
                    'year': years_list[i] if i < len(years_list) else None,
                    'is_public': publics_list[i] if i < len(publics_list) else None
                })

        # Check max documents limit if configured
        max_documents = document.config.get('max_documents') if document.config else None
        if max_documents:
            # Count existing documents
            if cls._is_public_submission(assignment_entity_status):
                existing_count = SubmittedDocument.query.filter_by(
                    public_submission_id=assignment_entity_status.id,
                    form_item_id=document.id
                ).count()
            else:
                existing_count = SubmittedDocument.query.filter_by(
                    assignment_entity_status_id=assignment_entity_status.id,
                    form_item_id=document.id
                ).count()

            total_count = existing_count + len(valid_files)
            if total_count > max_documents:
                validation_errors.append(f"Maximum of {max_documents} document(s) allowed for '{document.label}'. You have {existing_count} existing and tried to add {len(valid_files)}.")
                logger.warning(f"Document limit exceeded for field {document.id}: {total_count} > {max_documents}")
                return field_changes

        # Process each file
        for file_data in valid_files:
            file = file_data['file']
            selected_language = file_data['language']
            document_type = file_data.get('document_type')
            year_value = file_data.get('year')
            is_public = file_data.get('is_public')

            original_filename = file.filename or ""

            # SECURITY: Detect path traversal attempts before sanitization
            if '..' in original_filename or '/' in original_filename or '\\' in original_filename:
                logger.warning(
                    "Path traversal attempt detected in filename before sanitization: %s",
                    original_filename
                )
                validation_errors.append(
                    f"Invalid filename for '{document.label}': {original_filename}"
                )
                continue

            # SECURITY: Enhanced filename sanitization with path traversal prevention
            # Multiple layers of protection:
            # 1. AdvancedValidator.sanitize_filename() - removes path components, null bytes, dangerous chars
            # 2. secure_filename() - Werkzeug's additional sanitization
            # 3. Path construction uses os.path.join() with validated components
            from app.utils.advanced_validation import AdvancedValidator, validate_upload_extension_and_mime
            original_filename = file.filename or ''
            if '\x00' in original_filename:
                logger.warning(f"Null byte detected in filename: {original_filename!r}")
                validation_errors.append(f"Invalid filename for '{document.label}': {original_filename}")
                continue
            secured_filename = AdvancedValidator.sanitize_filename(original_filename)

            # Additional check: ensure secure_filename doesn't introduce issues
            secured_filename = secure_filename(secured_filename)

            # Final validation: ensure no path traversal remains after sanitization.
            normalized_original = original_filename.replace('\\', '/')
            if (
                '..' in normalized_original
                or '/' in normalized_original
                or '..' in secured_filename
                or '/' in secured_filename
                or '\\' in secured_filename
            ):
                logger.warning(
                    f"Path traversal attempt detected in filename: {original_filename} -> {secured_filename}"
                )
                validation_errors.append(f"Invalid filename for '{document.label}': {original_filename}")
                continue

            # Server-side file validation
            max_bytes = int(current_app.config.get('MAX_UPLOAD_SIZE_BYTES', 25 * 1024 * 1024))  # 25MB default
            allowed_exts = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}
            valid, error_msg, ext = validate_upload_extension_and_mime(file, allowed_exts)
            if not valid:
                validation_errors.append(
                    f"File validation failed for '{document.label}': {secured_filename}. "
                    f"{error_msg or 'Unsupported file type.'}"
                )
                logger.warning(
                    f"Rejected upload '{secured_filename}' - {error_msg} (ext: {ext}) for field {document.id}"
                )
                continue

            # Size validation (fail fast, before virus scanning)
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(0)
            if size > max_bytes:
                validation_errors.append(
                    f"File '{secured_filename}' too large for '{document.label}'. Maximum is {max_bytes // (1024*1024)}MB."
                )
                logger.warning(f"Rejected upload too large ({size} bytes) for field {document.id}")
                continue

            # Virus/Malware scanning
            try:
                scan_result = scan_file_for_viruses(file)
            except FileScanError as scan_error:
                validation_errors.append(
                    f"Virus scan failed for '{secured_filename}' in '{document.label}': {scan_error}"
                )
                logger.warning(
                    f"Virus scan failure for file '{secured_filename}' (field {document.id}): {scan_error}"
                )
                continue

            if scan_result.get('fail_open'):
                error_detail = scan_result.get('error') or 'Virus scanner unavailable'
                logger.warning(
                    f"File scan fail-open for '{secured_filename}' (field {document.id}): {error_detail}"
                )
                # When fail_open is True, we allow the upload to proceed despite scan failure
                # This is the expected behavior when virus scanning is disabled or unavailable
            else:
                if scan_result.get('infected'):
                    threats = ', '.join(scan_result.get('threats') or ['Unknown threat'])
                    validation_errors.append(
                        f"Virus detected in '{secured_filename}' for '{document.label}': {threats}"
                    )
                    logger.warning(
                        f"Virus detected in file '{secured_filename}' (field {document.id}): {threats}"
                    )
                    continue

                if not scan_result.get('clean'):
                    validation_errors.append(
                        f"Unable to verify that '{secured_filename}' for '{document.label}' is safe to upload."
                    )
                    logger.warning(
                        f"File scan produced indeterminate result for '{secured_filename}' (field {document.id}): "
                        f"{scan_result}"
                    )
                    continue

            # Ensure stream reset before saving downstream
            try:
                file.seek(0)
            except Exception as e:
                logger.debug("Could not rewind upload stream before saving (continuing): %s", e, exc_info=True)

            # Save document using standardized path function
            try:
                is_public_sub = cls._is_public_submission(assignment_entity_status)
                form_id = assignment_entity_status.assigned_form_id if is_public_sub else None
                submission_id = assignment_entity_status.id if is_public_sub else None

                if is_public_sub:
                    st_ent_type, st_ent_id = "country", assignment_entity_status.country_id
                else:
                    st_ent_type = assignment_entity_status.entity_type
                    st_ent_id = assignment_entity_status.entity_id

                # Save file and get relative path from submissions root
                storage_rel_path = save_submission_document(
                    file_storage=file,
                    assignment_id=assignment_entity_status.id,
                    filename=secured_filename,
                    is_public=is_public_sub,
                    form_id=form_id,
                    submission_id=submission_id,
                    entity_type=st_ent_type,
                    entity_id=st_ent_id,
                )

                # Parse period value (keep as string - can be "2024", "2024-2025", "Jan-Dec 2024", etc.)
                parsed_period = year_value if year_value else None

                # Parse is_public value
                is_public_bool = is_public in ['1', 'true', 'True'] if is_public else False

                # Create new document (allow multiple documents per field)
                if is_public_sub:
                    new_doc = SubmittedDocument(
                        public_submission_id=assignment_entity_status.id,
                        form_item_id=document.id,
                        filename=secured_filename,
                        storage_path=storage_rel_path,  # Store relative path
                        uploaded_by_user_id=(current_user.id if current_user.is_authenticated else None),
                        language=selected_language,
                        document_type=document_type or None,  # Use document_type field, not document_label property
                        period=parsed_period,
                        is_public=is_public_bool
                    )
                else:
                    # Non-public submissions require an authenticated user.
                    if not getattr(current_user, "is_authenticated", False):
                        validation_errors.append(
                            f"Authentication required to upload document '{secured_filename}' for '{document.label}'."
                        )
                        continue
                    new_doc = SubmittedDocument(
                        assignment_entity_status_id=assignment_entity_status.id,
                        form_item_id=document.id,
                        filename=secured_filename,
                        storage_path=storage_rel_path,  # Store relative path
                        uploaded_by_user_id=current_user.id,
                        language=selected_language,
                        document_type=document_type or None,  # Use document_type field, not document_label property
                        period=parsed_period,
                        is_public=is_public_bool
                    )
                db.session.add(new_doc)
                logger.info(f"Added document to session: {secured_filename} for form_item_id={document.id}, assignment_entity_status_id={assignment_entity_status.id}")
                flash(f"Uploaded document '{secured_filename}' for '{document.label}' in {selected_language.upper()}.", "success")

                # Trigger notification
                try:
                    db.session.flush()
                    cls._log_verbose(f"Flushed document to database: {secured_filename}, doc_id={new_doc.id}")
                    # create_notification uses commit/rollback on the global session; doing that here
                    # can roll back the SubmittedDocument row while the file remains on disk. Defer until
                    # after the request transaction commits (see transaction_middleware + register_post_commit).
                    register_post_commit(notify_document_uploaded, assignment_entity_status, secured_filename)
                    logger.info(
                        "Queued post-commit focal-point notification for document upload "
                        "(aes_id=%s, form_item_id=%s, submitted_document_id=%s, filename=%s)",
                        assignment_entity_status.id,
                        document.id,
                        getattr(new_doc, "id", None),
                        secured_filename,
                    )
                except Exception as e:
                    logger.error(
                        "Error flushing document or scheduling upload notification: %s", str(e), exc_info=True
                    )

                ch_entry = {
                    'type': 'added',
                    'form_item_id': document.id,
                    'field_name': get_english_field_name(document),
                    'old_value': None,
                    'new_value': secured_filename,
                }
                if getattr(new_doc, 'id', None):
                    ch_entry['submitted_document_id'] = new_doc.id
                field_changes.append(ch_entry)

            except Exception as e:
                validation_errors.append(f"Error uploading document for '{document.label}'.")
                logger.error(f"Document upload error: {e}")

        # Handle document deletions (marked via delete_document hidden inputs)
        # Process all delete_document inputs in the form
        for form_key in request.form.keys():
            if form_key.startswith('delete_document_') and request.form[form_key] == 'true':
                try:
                    doc_id_str = form_key.replace('delete_document_', '')
                    doc_id = int(doc_id_str)

                    # Find the document
                    doc_to_delete = SubmittedDocument.query.get(doc_id)
                    if not doc_to_delete:
                        logger.warning(f"Document {doc_id} not found for deletion")
                        continue

                    # Verify document belongs to this submission
                    if cls._is_public_submission(assignment_entity_status):
                        if doc_to_delete.public_submission_id != assignment_entity_status.id:
                            logger.warning(f"Document {doc_id} does not belong to this public submission")
                            continue
                    else:
                        if doc_to_delete.assignment_entity_status_id != assignment_entity_status.id:
                            logger.warning(f"Document {doc_id} does not belong to this assignment")
                            continue

                    # Verify document belongs to this form item
                    if doc_to_delete.form_item_id != document.id:
                        logger.warning(f"Document {doc_id} does not belong to form item {document.id}")
                        continue

                    if not user_may_delete_or_replace_submitted_document_file(current_user, doc_to_delete):
                        validation_errors.append(
                            "This document is approved and can only be removed by an administrator."
                        )
                        continue

                    # Delete the document
                    deleted_filename = doc_to_delete.filename
                    try:
                        from app.services import storage_service as _ss
                        try:
                            _ss.delete(
                                _ss.submitted_document_rel_storage_category(doc_to_delete.storage_path),
                                doc_to_delete.storage_path,
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to delete document file (will still delete DB row): "
                                f"doc_id={doc_id} storage_path={doc_to_delete.storage_path} error={e}",
                                exc_info=True
                            )

                        # Delete from database
                        db.session.delete(doc_to_delete)
                        cls._log_verbose(f"Deleted document {doc_id} ({deleted_filename}) for form item {document.id}")

                        field_changes.append({
                            'type': 'deleted',
                            'form_item_id': document.id,
                            'field_name': get_english_field_name(document),
                            'old_value': deleted_filename,
                            'new_value': None
                        })
                    except Exception as e:
                        validation_errors.append("Error deleting document.")
                        logger.error(f"Error deleting document {doc_id}: {e}", exc_info=True)

                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid document ID in delete_document input '{form_key}': {e}")
                    continue

        # Handle document edits
        edit_doc_id_key = f'edit_document_id[{document.id}]'
        edit_language_key = f'edit_document_language[{document.id}]'
        edit_file_key = f'edit_document_file[{document.id}]'

        if edit_doc_id_key in request.form and request.form[edit_doc_id_key]:
            doc_id = request.form[edit_doc_id_key]
            new_language = request.form.get(edit_language_key, 'en')

            try:
                # Find the document to edit
                doc_to_edit = SubmittedDocument.query.get(doc_id)
                if not doc_to_edit:
                    validation_errors.append(f"Document not found or not accessible.")
                    return field_changes

                # Check if document belongs to this submission
                if cls._is_public_submission(assignment_entity_status):
                    if doc_to_edit.public_submission_id != assignment_entity_status.id:
                        validation_errors.append(f"Document not found or not accessible.")
                        return field_changes
                else:
                    if doc_to_edit.assignment_entity_status_id != assignment_entity_status.id:
                        validation_errors.append(f"Document not found or not accessible.")
                        return field_changes

                if not user_may_delete_or_replace_submitted_document_file(current_user, doc_to_edit):
                    validation_errors.append(
                        "This document is approved and can only be changed by an administrator."
                    )
                    return field_changes

                # Update language
                doc_to_edit.language = new_language
                doc_to_edit.uploaded_at = utcnow()
                doc_to_edit.uploaded_by_user_id = current_user.id

                # Update additional metadata fields if provided
                edit_type_key = f'edit_document_type[{document.id}]'
                edit_year_key = f'edit_document_year[{document.id}]'
                edit_public_key = f'edit_document_is_public[{document.id}]'

                if edit_type_key in request.form:
                    doc_to_edit.document_type = request.form[edit_type_key] or None  # Use document_type field, not document_label property

                if edit_year_key in request.form:
                    period_value = request.form[edit_year_key]
                    # Store period as string (can be "2024", "2024-2025", "Jan-Dec 2024", etc.)
                    doc_to_edit.period = period_value if period_value else None

                if edit_public_key in request.form:
                    doc_to_edit.is_public = request.form[edit_public_key] in ['1', 'true', 'True']
                    try:
                        from app.services.ai_submitted_document_ingest import (
                            sync_ai_document_is_public_from_submitted,
                        )

                        sync_ai_document_is_public_from_submitted(doc_to_edit)
                    except Exception as e:
                        logger.debug("sync_ai_document_is_public_from_submitted: %s", e, exc_info=True)

                # Handle file replacement if provided
                if edit_file_key in request.files and request.files[edit_file_key].filename:
                    file = request.files[edit_file_key]
                    secured_filename = secure_filename(file.filename)

                    from app.services import storage_service as _ss
                    try:
                        _ss.delete(
                            _ss.submitted_document_rel_storage_category(doc_to_edit.storage_path),
                            doc_to_edit.storage_path,
                        )
                    except Exception as e:
                        current_app.logger.warning(f"Error removing old file: {e}", exc_info=True)

                    # Save new file using standardized function
                    is_public_sub = cls._is_public_submission(assignment_entity_status)
                    form_id = assignment_entity_status.assigned_form_id if is_public_sub else None
                    submission_id = assignment_entity_status.id if is_public_sub else None

                    if is_public_sub:
                        st_ent_type, st_ent_id = "country", assignment_entity_status.country_id
                    else:
                        st_ent_type = assignment_entity_status.entity_type
                        st_ent_id = assignment_entity_status.entity_id

                    storage_rel_path = save_submission_document(
                        file_storage=file,
                        assignment_id=assignment_entity_status.id,
                        filename=secured_filename,
                        is_public=is_public_sub,
                        form_id=form_id,
                        submission_id=submission_id,
                        entity_type=st_ent_type,
                        entity_id=st_ent_id,
                    )

                    doc_to_edit.filename = secured_filename
                    doc_to_edit.storage_path = storage_rel_path  # Store relative path

                db.session.add(doc_to_edit)
                flash(f"Updated document for '{document.label}' in {new_language}.", "success")

                field_changes.append({
                    'type': 'updated',
                    'form_item_id': document.id,
                    'field_name': get_english_field_name(document),
                    'old_value': doc_to_edit.filename,
                    'new_value': doc_to_edit.filename
                })

            except Exception as e:
                validation_errors.append(f"Error updating document for '{document.label}'.")
                logger.error(f"Document update error: {e}")

        return field_changes

    @classmethod
    def _create_pending_dynamic_indicators(cls, section, assignment_entity_status, validation_errors: List) -> Dict[str, int]:
        """Create DB records for pending dynamic indicators and return mapping of temp IDs to real IDs."""
        temp_to_real_map = {}

        # Find all pending indicators for this section
        pending_key = f'pending_dynamic_indicator_{section.id}'
        pending_values = request.form.getlist(pending_key)

        if not pending_values:
            return temp_to_real_map

        is_public = cls._is_public_submission(assignment_entity_status)

        # Get existing assignments to check for duplicates and get max order
        if is_public:
            existing_assignments = DynamicIndicatorData.query.filter_by(
                public_submission_id=assignment_entity_status.id,
                section_id=section.id
            ).all()
        else:
            existing_assignments = DynamicIndicatorData.query.filter_by(
                assignment_entity_status_id=assignment_entity_status.id,
                section_id=section.id
            ).all()

        existing_indicator_ids = {a.indicator_bank_id for a in existing_assignments}
        max_order = max((a.order for a in existing_assignments), default=0)

        # Respect max indicator limits if configured
        max_allowed = getattr(section, 'max_dynamic_indicators', None)
        if max_allowed is not None:
            try:
                max_allowed = int(max_allowed)
                if len(existing_assignments) >= max_allowed:
                    validation_errors.append("Maximum indicators reached for this section.")
                    return temp_to_real_map
            except (TypeError, ValueError):
                pass

        # Process each pending indicator
        for pending_value in pending_values:
            try:
                parts = pending_value.split(':')
                if len(parts) != 2:
                    continue

                indicator_bank_id = int(parts[0])
                temp_assignment_id = parts[1]

                # Skip if already exists
                if indicator_bank_id in existing_indicator_ids:
                    continue

                # Check max limit
                if max_allowed is not None and len(existing_assignments) >= max_allowed:
                    validation_errors.append("Maximum indicators reached for this section.")
                    break

                # Import IndicatorBank here to avoid circular imports
                from app.models import IndicatorBank
                indicator = IndicatorBank.query.get(indicator_bank_id)
                if not indicator:
                    continue

                # Create the real assignment
                max_order += 1
                dynamic_assignment = DynamicIndicatorData(
                    section_id=section.id,
                    indicator_bank_id=indicator_bank_id,
                    custom_label=None,
                    order=max_order,
                    added_by_user_id=current_user.id
                )

                if is_public:
                    dynamic_assignment.public_submission_id = assignment_entity_status.id
                else:
                    dynamic_assignment.assignment_entity_status_id = assignment_entity_status.id

                db.session.add(dynamic_assignment)
                db.session.flush()  # Get the real ID

                # Map temp ID to real ID
                temp_to_real_map[temp_assignment_id] = dynamic_assignment.id
                existing_indicator_ids.add(indicator_bank_id)
                existing_assignments.append(dynamic_assignment)

                cls._log_verbose(f"Created pending dynamic indicator: temp_id={temp_assignment_id}, real_id={dynamic_assignment.id}, indicator_id={indicator_bank_id}")

            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid pending indicator value: {pending_value}, error: {e}")
                continue

        # Ensure all created assignments are available for queries
        if temp_to_real_map:
            db.session.flush()

        return temp_to_real_map

    @classmethod
    def _remap_pending_indicator_form_data(cls, temp_to_real_map: Dict[str, int]) -> None:
        """Remap form data keys from temporary assignment IDs to real IDs."""
        if not temp_to_real_map:
            return

        # Store mapping for use during processing
        # We'll check this mapping when processing form fields
        request._pending_indicator_id_map = temp_to_real_map

    @classmethod
    def _process_dynamic_indicators(cls, section, assignment_entity_status, validation_errors: List) -> List[Dict]:
        """Process dynamic indicators using unified FormItemProcessor approach"""
        field_changes = []

        # Debug: Log all form field names to see dynamic indicator patterns
        all_form_fields = list(request.form.keys())
        dynamic_field_names = [name for name in all_form_fields if 'dynamic' in name]
        cls._log_verbose(f"All form field names: {all_form_fields}")
        cls._log_verbose(f"Dynamic field names: {dynamic_field_names}")

        # Create DB records for pending indicators before processing
        temp_to_real_id_map = cls._create_pending_dynamic_indicators(section, assignment_entity_status, validation_errors)

        # Remap form data from temporary IDs to real IDs
        if temp_to_real_id_map:
            cls._remap_pending_indicator_form_data(temp_to_real_id_map)

        # Get all dynamic indicator assignments for this section
        if cls._is_public_submission(assignment_entity_status):
            dynamic_assignments = DynamicIndicatorData.query.filter_by(
                public_submission_id=assignment_entity_status.id,
                section_id=section.id
            ).all()
        else:
            dynamic_assignments = DynamicIndicatorData.query.filter_by(
                assignment_entity_status_id=assignment_entity_status.id,
                section_id=section.id
            ).all()

        logger.info(f"Found {len(dynamic_assignments)} dynamic assignments for section {section.id}")

        for dynamic_assignment in dynamic_assignments:
            logger.info(f"Processing dynamic assignment {dynamic_assignment.id}")

            # Create a pseudo-form item for the dynamic indicator
            dynamic_field = cls._create_dynamic_form_item(dynamic_assignment)

            # Use the correct field prefix for dynamic indicators
            field_prefix = f"dynamic_{dynamic_assignment.id}"

            # Collect form data for this dynamic indicator
            # Also check for pending (temp) IDs that map to this real ID
            temp_prefixes = []
            if hasattr(request, '_pending_indicator_id_map'):
                for temp_id, real_id in request._pending_indicator_id_map.items():
                    if real_id == dynamic_assignment.id:
                        temp_prefixes.append(f"dynamic_{temp_id}")

            form_data = {}
            for key, value in request.form.items():
                if key.startswith(field_prefix):
                    form_data[key] = value
                else:
                    # Check if this is a temp ID field that maps to this assignment
                    for temp_prefix in temp_prefixes:
                        if key.startswith(temp_prefix):
                            # Remap to use real ID
                            remapped_key = key.replace(temp_prefix, field_prefix)
                            form_data[remapped_key] = value
                            break

            cls._log_verbose(f"Collected form data for dynamic assignment {dynamic_assignment.id}: {form_data}")
            cls._log_verbose(f"Dynamic field type: {dynamic_field.type}, unit: {dynamic_field.unit}")
            cls._log_verbose(f"Dynamic field allowed_disaggregation_options: {dynamic_field.allowed_disaggregation_options}")

            # Use the unified FormItemProcessor to process the field data
            processed_value, has_value, data_not_available, not_applicable = FormItemProcessor.process_form_item_data(
                dynamic_field, form_data, assignment_entity_status.id, field_prefix=field_prefix
            )

            cls._log_verbose(f"Dynamic assignment {dynamic_assignment.id} processing result: value={processed_value}, has_value={has_value}")

            if not (has_value or data_not_available or not_applicable):
                # If the form submitted this dynamic indicator but all inputs are empty,
                # clear any previously stored value/flags.
                if form_data:
                    had_existing_data = bool(
                        dynamic_assignment.disagg_data or
                        dynamic_assignment.value or
                        dynamic_assignment.data_not_available or
                        dynamic_assignment.not_applicable
                    )
                    if had_existing_data:
                        old_data_not_available = dynamic_assignment.data_not_available or False
                        old_not_applicable = dynamic_assignment.not_applicable or False
                        if dynamic_assignment.disagg_data:
                            old_value = dynamic_assignment.disagg_data
                        else:
                            old_value = dynamic_assignment.get_effective_value()

                        dynamic_assignment.value = None
                        dynamic_assignment.disagg_data = db.null()
                        dynamic_assignment.data_not_available = False
                        dynamic_assignment.not_applicable = False
                        db.session.add(dynamic_assignment)

                        # IMPORTANT: For dynamic indicator sections, the "field id" used in the UI
                        # and activity anchors is the IndicatorBank id (not a FormItem id).
                        # Prefer a user-provided custom label when available.
                        field_name = (
                            (dynamic_assignment.custom_label.strip() if dynamic_assignment.custom_label and str(dynamic_assignment.custom_label).strip() else None)
                            or (get_localized_indicator_name(dynamic_assignment.indicator_bank) if dynamic_assignment.indicator_bank else None)
                            or "Dynamic Indicator"
                        )

                        field_changes.append({
                            'type': 'removed',
                            'form_item_id': dynamic_assignment.indicator_bank_id if dynamic_assignment.indicator_bank_id else None,
                            'field_id_kind': 'indicator_bank',
                            'field_name': field_name,
                            'old_value': old_value,
                            'new_value': None,
                            'old_data_not_available': old_data_not_available,
                            'new_data_not_available': False,
                            'old_not_applicable': old_not_applicable,
                            'new_not_applicable': False
                        })
                continue

            if has_value or data_not_available or not_applicable:
                # Track old value before updating - handle both simple values and disaggregated data
                old_data_not_available = dynamic_assignment.data_not_available or False
                old_not_applicable = dynamic_assignment.not_applicable or False

                # Get old value - prefer disagg_data if present, otherwise use value
                if dynamic_assignment.disagg_data:
                    old_value = dynamic_assignment.disagg_data
                else:
                    old_value = dynamic_assignment.get_effective_value()

                # Update the dynamic indicator assignment directly with data
                if isinstance(processed_value, dict):
                    # For JSON data, store in disagg_data and leave value as None
                    dynamic_assignment.value = None
                    dynamic_assignment.disagg_data = processed_value
                else:
                    dynamic_assignment.value = str(processed_value) if processed_value is not None else None
                    dynamic_assignment.disagg_data = db.null()
                dynamic_assignment.data_not_available = data_not_available
                dynamic_assignment.not_applicable = not_applicable
                db.session.add(dynamic_assignment)

                # IMPORTANT: For dynamic indicator sections, the "field id" used in the UI
                # and activity anchors is the IndicatorBank id (not a FormItem id).
                # Prefer a user-provided custom label when available.
                field_name = (
                    (dynamic_assignment.custom_label.strip() if dynamic_assignment.custom_label and str(dynamic_assignment.custom_label).strip() else None)
                    or (get_localized_indicator_name(dynamic_assignment.indicator_bank) if dynamic_assignment.indicator_bank else None)
                    or "Dynamic Indicator"
                )

                # Determine change type
                if old_value is None and processed_value is not None:
                    change_type = 'added'
                elif old_value is not None and processed_value is None:
                    change_type = 'removed'
                else:
                    change_type = 'updated'

                # Record the change if value actually changed
                # Compare values properly - handle dict comparison for disaggregated data
                values_changed = False
                if isinstance(old_value, dict) and isinstance(processed_value, dict):
                    # Compare dictionaries
                    values_changed = json.dumps(old_value, sort_keys=True) != json.dumps(processed_value, sort_keys=True)
                else:
                    values_changed = old_value != processed_value

                if (values_changed or
                    old_data_not_available != data_not_available or
                    old_not_applicable != not_applicable):
                    field_changes.append({
                        'type': change_type,
                        'form_item_id': dynamic_assignment.indicator_bank_id if dynamic_assignment.indicator_bank_id else None,
                        'field_id_kind': 'indicator_bank',
                        'field_name': field_name,
                        'old_value': old_value,
                        'new_value': processed_value,
                        'old_data_not_available': old_data_not_available,
                        'new_data_not_available': data_not_available or False,
                        'old_not_applicable': old_not_applicable,
                        'new_not_applicable': not_applicable or False
                    })

        return field_changes

    @classmethod
    def _create_dynamic_form_item(cls, dynamic_assignment):
        """Deprecated: use centralized dynamic indicator builder."""
        return _create_dynamic_indicator_object(dynamic_assignment, section_obj=None)

    @classmethod
    @performance_monitor("Repeat Groups Processing", quiet=True)
    def _process_repeat_groups(cls, section, assignment_entity_status, validation_errors: List) -> List[Dict]:
        """Process repeat groups with JavaScript compatibility"""
        field_changes = []

        # Get all form items for this section using the unified approach
        all_fields = get_form_items_for_section(section, assignment_entity_status)

        # Parse repeat data from form - use comprehensive approach from original
        repeat_data = {}
        processed_fields = set()

        for field_name in request.form.keys():
            if field_name.startswith(f'repeat_{section.id}_') and field_name not in processed_fields:
                parts = field_name.split('_')
                if len(parts) >= 4 and parts[3] == 'field':
                    section_id = int(parts[1])
                    instance_number = int(parts[2])

                    if instance_number not in repeat_data:
                        repeat_data[instance_number] = {}

                    if len(parts) >= 5:
                        field_index = int(parts[4])

                        # Get all values for this field name (handles both single and multi-choice)
                        field_values = request.form.getlist(field_name)

                        if len(parts) >= 6:
                            input_index = '_'.join(parts[5:])
                            field_key = f'field_{field_index}_{input_index}'
                        else:
                            field_key = f'field_{field_index}'

                        # Check if this is a multi-choice field
                        base_field = '_'.join(parts[:5])
                        is_multi_choice = len(field_values) > 1

                        if is_multi_choice:
                            repeat_data[instance_number][field_key] = field_values
                        else:
                            repeat_data[instance_number][field_key] = field_values[0] if field_values else ''

                        processed_fields.add(field_name)

        cls._log_verbose(f"Parsed repeat data: {repeat_data}")

        # Process each repeat instance
        for instance_number, instance_data in repeat_data.items():
            cls._log_verbose(f"Processing repeat instance {instance_number} with data: {instance_data}")

            # Create or get repeat group instance using helper methods
            if cls._is_public_submission(assignment_entity_status):
                repeat_instance = RepeatGroupInstance.query.filter_by(
                    public_submission_id=assignment_entity_status.id,
                    section_id=section.id,
                    instance_number=instance_number
                ).first()

                if not repeat_instance:
                    repeat_instance = RepeatGroupInstance(
                        public_submission_id=assignment_entity_status.id,
                        section_id=section.id,
                        instance_number=instance_number,
                        created_by_user_id=1,  # Public submissions use user_id=1
                        is_hidden=False
                    )
                    db.session.add(repeat_instance)
                    db.session.flush()  # Get the ID
                    logger.info(f"Created new repeat instance {repeat_instance.id}")
                else:
                    logger.info(f"Found existing repeat instance {repeat_instance.id}")
            else:
                repeat_instance = RepeatGroupInstance.query.filter_by(
                    assignment_entity_status_id=assignment_entity_status.id,
                    section_id=section.id,
                    instance_number=instance_number
                ).first()

                if not repeat_instance:
                    repeat_instance = RepeatGroupInstance(
                        assignment_entity_status_id=assignment_entity_status.id,
                        section_id=section.id,
                        instance_number=instance_number,
                        created_by_user_id=current_user.id,
                        is_hidden=False
                    )
                    db.session.add(repeat_instance)
                    db.session.flush()  # Get the ID
                    cls._log_verbose(f"Created new repeat instance {repeat_instance.id}")
                else:
                    cls._log_verbose(f"Found existing repeat instance {repeat_instance.id}")

            # Process each field in this instance using comprehensive field processing
            for field_index, field in enumerate(all_fields):
                cls._log_verbose(f"Checking field {field_index} ({field.label})")

                # Look for any field keys that start with this field index
                # Also handle variations like field_0_ and field_0 (without underscore)
                matching_keys = []

                # Pattern 1: field_{index}_ (with underscore)
                pattern_with_underscore = f'field_{field_index}_'
                matching_keys.extend([key for key in instance_data.keys() if key.startswith(pattern_with_underscore)])

                # Pattern 2: field_{index} (exact match, for base field key)
                base_field_key = f'field_{field_index}'
                if base_field_key in instance_data:
                    if base_field_key not in matching_keys:
                        matching_keys.append(base_field_key)

                # Pattern 3: Check if this is a field without underscore but with data (edge case)
                for key in instance_data.keys():
                    if key == f'field_{field_index}' or (key.startswith(f'field_{field_index}') and not key.startswith(f'field_{field_index}_')):
                        if key not in matching_keys:
                            matching_keys.append(key)

                cls._log_verbose(f"Found matching keys for field {field_index}: {matching_keys}")
                cls._log_verbose(f"Available keys in instance_data: {list(instance_data.keys())}")

                if matching_keys:
                    # Use comprehensive field processing like the original
                    field_values = {}
                    for key in matching_keys:
                        field_values[key] = instance_data[key]

                    # Also add the base field key if it exists
                    base_field_key = f'field_{field_index}'
                    if base_field_key in instance_data:
                        field_values[base_field_key] = instance_data[base_field_key]

                    cls._log_verbose(f"Processing field {field_index} ({field.label}) with field_values: {field_values}")

                    # Process the field data using comprehensive processing
                    processed_value, data_not_available, not_applicable, has_meaningful_data = cls._process_repeat_field_data_comprehensive(
                        field, field_values, field_index, instance_number
                    )

                    cls._log_verbose(f"Processed value: {processed_value}, has_meaningful_data: {has_meaningful_data}")

                    if has_meaningful_data:
                        # Create or update repeat group data entry
                        existing_entry = RepeatGroupData.query.filter_by(
                            repeat_instance_id=repeat_instance.id,
                            form_item_id=field.id
                        ).first()

                        # Track old value before updating
                        old_value = None
                        old_data_not_available = False
                        old_not_applicable = False
                        change_type = 'added'

                        if existing_entry:
                            # Track old values before updating - handle both simple values and disaggregated data
                            # Get old value - prefer disagg_data if present, otherwise use value
                            if existing_entry.disagg_data:
                                old_value = existing_entry.disagg_data
                            else:
                                old_value = existing_entry.get_effective_value()
                            old_data_not_available = existing_entry.data_not_available or False
                            old_not_applicable = existing_entry.not_applicable or False
                            change_type = 'updated'

                            # Update existing entry
                            cls._store_repeat_data_entry(existing_entry, processed_value, data_not_available, not_applicable, field)
                            cls._log_verbose(f"Updated existing repeat data entry for field {field.id}: value={existing_entry.value}, disagg_data={existing_entry.disagg_data}")
                        else:
                            # Create new entry
                            new_entry = RepeatGroupData(
                                repeat_instance_id=repeat_instance.id,
                                form_item_id=field.id
                            )
                            cls._store_repeat_data_entry(new_entry, processed_value, data_not_available, not_applicable, field)
                            db.session.add(new_entry)
                            cls._log_verbose(f"Created new repeat data entry for field {field.id}: value={new_entry.value}, disagg_data={new_entry.disagg_data}")

                        # Record the change if value actually changed
                        # Compare values properly - handle dict comparison for disaggregated data
                        values_changed = False
                        if isinstance(old_value, dict) and isinstance(processed_value, dict):
                            # Compare dictionaries
                            values_changed = json.dumps(old_value, sort_keys=True) != json.dumps(processed_value, sort_keys=True)
                        else:
                            values_changed = old_value != processed_value

                        if (values_changed or
                            old_data_not_available != data_not_available or
                            old_not_applicable != not_applicable):
                            # Include instance number in field name for repeat groups
                            base_field_name = get_english_field_name(field)
                            field_name_with_instance = f"{base_field_name} (Entry {instance_number})"

                            field_changes.append({
                                'type': change_type,
                                'form_item_id': field.id,
                                'field_name': field_name_with_instance,
                                'old_value': old_value,
                                'new_value': processed_value,
                                'old_data_not_available': old_data_not_available,
                                'new_data_not_available': data_not_available or False,
                                'old_not_applicable': old_not_applicable,
                                'new_not_applicable': not_applicable or False,
                                'repeat_instance_number': instance_number  # Store separately for potential future use
                            })
                else:
                    cls._log_verbose(f"No matching keys found for field {field_index}")

        cls._log_verbose(f"Repeat group processing completed with {len(field_changes)} field changes")
        return field_changes

    # Helper methods for field processing optimization
    @classmethod
    def _field_supports_disaggregation(cls, field):
        """Check if field truly supports disaggregation (beyond just 'total')"""
        options = getattr(field, 'allowed_disaggregation_options', None) or []
        has_true_disagg = any(opt in ('sex', 'age', 'sex_age') for opt in options)
        return has_true_disagg or bool(getattr(field, 'indirect_reach', False))

    @classmethod
    def _is_numeric_field(cls, field):
        """Check if field is numeric-like"""
        try:
            field_type_for_js = getattr(field, 'field_type_for_js', '').lower()
        except (AttributeError, TypeError):
            field_type_for_js = ''

        return (field_type_for_js in ['number', 'percentage', 'currency'] or
                getattr(field, 'type', '') in ['Number', 'Percentage', 'Currency'])

    @classmethod
    def _find_field_value(cls, field_values, field_index, suffixes):
        """Find field value using multiple naming patterns"""
        # Build possible keys from suffixes
        possible_keys = [f'field_{field_index}_{suffix}' for suffix in suffixes]
        possible_keys.append(f'field_{field_index}')  # Add base pattern

        # Also check for any key that starts with field_{field_index} and might contain a value
        additional_keys = [key for key in field_values.keys()
                         if key.startswith(f'field_{field_index}')
                         and key not in possible_keys
                         and not key.endswith('_data_not_available')
                         and not key.endswith('_not_applicable')
                         and not key.endswith('_reporting_mode')]
        possible_keys.extend(additional_keys)

        for key in possible_keys:
            if key in field_values:
                val_str = field_values[key]
                if val_str and str(val_str).strip():
                    return val_str

        return None

    @classmethod
    def _process_numeric_value(cls, val_str, field):
        """Process numeric value based on field type"""
        try:
            field_type_for_js = getattr(field, 'field_type_for_js', '').lower()
            # Currency and number can have decimals; store as normalized string
            if field.type == 'Percentage' or field_type_for_js == 'percentage':
                return str(float(val_str))
            elif field_type_for_js in ['currency', 'number'] or getattr(field, 'type', '') in ['Currency', 'Number']:
                # Allow decimals for currency/number
                return str(float(val_str))
            else:
                return str(int(val_str))
        except ValueError:
            logger.warning(f"Invalid numeric value for {field.label}: {val_str}")
            return str(val_str) if val_str else None

    @classmethod
    def _process_repeat_field_data_comprehensive(cls, field, field_values, field_index, instance_number):
        """Process repeat field data with comprehensive handling like the original"""
        data_not_available = False
        not_applicable = False
        has_meaningful_data = False
        final_value_to_store = None

        # Check for data availability flags first
        data_not_available = field_values.get(f'field_{field_index}_data_not_available') == '1'
        not_applicable = field_values.get(f'field_{field_index}_not_applicable') == '1'

        # Handle different field types
        if field.is_indicator:
            final_value_to_store = cls._process_repeat_indicator_data_comprehensive(field, field_values, field_index)
        elif field.is_question:
            final_value_to_store = cls._process_repeat_question_data_comprehensive(field, field_values, field_index)
        elif field.is_document_field:
            final_value_to_store = cls._process_repeat_document_data_comprehensive(field, field_values, field_index)
        elif field.item_type == 'matrix':
            final_value_to_store = cls._process_repeat_matrix_data_comprehensive(field, field_values, field_index)
        else:
            # Unknown field type - try to find any value
            final_value_to_store = None

        # Determine if we have meaningful data
        has_meaningful_data = unified_should_create(final_value_to_store, data_not_available, not_applicable)

        cls._log_verbose(f"Comprehensive processing result - value: {final_value_to_store}, has_meaningful_data: {has_meaningful_data}")

        return final_value_to_store, data_not_available, not_applicable, has_meaningful_data

    @classmethod
    def _process_repeat_indicator_data_comprehensive(cls, field, field_values, field_index):
        """Process repeat indicator data with comprehensive handling"""
        logger.info(f"Processing repeat indicator {field.id} with field_values: {field_values}")

        # Check if this indicator truly supports disaggregation (beyond just 'total')
        supports_disaggregation = cls._field_supports_disaggregation(field)
        is_numeric_like = cls._is_numeric_field(field)

        if supports_disaggregation and is_numeric_like:
            return cls._process_repeat_disaggregation_indicator(field, field_values, field_index)

        # Handle numeric indicators WITHOUT disaggregation
        if is_numeric_like and not supports_disaggregation:
            val_str = cls._find_field_value(field_values, field_index, ['total_value', '0', 'standard_value'])
            if val_str:
                cls._log_verbose(f"Found numeric value '{val_str}' for non-disaggregated indicator {field.id}")
                return cls._process_numeric_value(val_str, field)

            cls._log_verbose(f"No numeric value found for non-disaggregated indicator {field.id}")
            return None

        # Handle text/other types - look for any non-empty value
        val_str = None

        # Special debugging for yes/no indicators
        if (hasattr(field, 'type') and
            field.type == 'yesno'):
            cls._log_verbose(f"PROCESSING YES/NO INDICATOR: field {field.id}, field_values keys: {list(field_values.keys())}")
            # Look specifically for standard_value key
            standard_value_key = f'field_{field_index}_standard_value'
            if standard_value_key in field_values:
                val_str = field_values[standard_value_key]
                cls._log_verbose(f"Found yes/no indicator value: '{val_str}' for field {field.id}")

        # Check for any key that might contain the actual value (prioritize standard_value for yes/no)
        if val_str is None:
            # First, check for standard_value (yes/no fields)
            standard_value_key = f'field_{field_index}_standard_value'
            if standard_value_key in field_values and field_values[standard_value_key]:
                val_str = field_values[standard_value_key]
                logger.info(f"Found standard value '{val_str}' for field {field.id}")
            else:
                # Then check other keys
                for key, value in field_values.items():
                    if key.startswith(f'field_{field_index}_') and value and str(value).strip():
                        # Skip reporting mode and other non-value fields
                        if not key.endswith('_reporting_mode') and not key.endswith('_data_not_available') and not key.endswith('_not_applicable'):
                            val_str = value
                            logger.info(f"Found text value '{val_str}' in key '{key}' for field {field.id}")
                            break

        if val_str and val_str.strip():
            return val_str

        return None

    @classmethod
    def _process_repeat_question_data_comprehensive(cls, field, field_values, field_index):
        """Process repeat question data with comprehensive handling"""
        cls._log_verbose(f"Processing repeat question {field.id} ({field.question_type}) with field_values: {field_values}")

        # Use optimized field value lookup
        question_type = field.question_type.value if field.question_type else None

        if question_type == 'yesno':
            # For yes/no questions, prioritize standard_value
            raw_value = cls._find_field_value(field_values, field_index, ['standard_value', '0'])
        else:
            # For other questions, try various patterns
            raw_value = cls._find_field_value(field_values, field_index, ['0', 'standard_value'])

        if raw_value is not None:
            return cls._process_question_value_by_type(raw_value, question_type, field, field_values, field_index)

        return None

    @classmethod
    def _process_question_value_by_type(cls, raw_value, question_type, field, field_values, field_index):
        """Process question value based on its type"""
        if isinstance(raw_value, str) and raw_value.strip() == '':
            return None

        if question_type == 'number':
            return cls._process_numeric_value(raw_value, field)
        elif question_type == 'percentage':
            return cls._process_numeric_value(raw_value, field)
        elif question_type == 'multiple_choice':
            return cls._process_multiple_choice_value(raw_value, field_values, field_index)
        elif question_type == 'yesno':
            return 'true' if raw_value else 'false'
        else:
            return str(raw_value).strip() if isinstance(raw_value, str) and str(raw_value).strip() else str(raw_value) if raw_value else None

    @classmethod
    def _process_multiple_choice_value(cls, raw_value, field_values, field_index):
        """Process multiple choice question values"""
        selected_options = []

        # Check if we already have an array of values from multi-choice field processing
        if f'field_{field_index}' in field_values:
            value = field_values[f'field_{field_index}']
            if isinstance(value, list):
                selected_options = value
                cls._log_verbose(f"Using pre-collected multi-choice values: {selected_options}")
            else:
                selected_options = [value] if value else []
                cls._log_verbose(f"Converting single value to multi-choice: {selected_options}")
        else:
            # Fallback: collect all values for this field
            for key, value in field_values.items():
                if key.startswith(f'field_{field_index}') and not key.endswith('_data_not_available') and not key.endswith('_not_applicable'):
                    selected_options.append(value)
            cls._log_verbose(f"Fallback multi-choice collection: {selected_options}")

        return json.dumps(selected_options) if selected_options else None

    @classmethod
    def _store_repeat_data_entry(cls, entry, processed_value, data_not_available, not_applicable, field=None):
        """Store data in a repeat group data entry using appropriate method"""
        # Get field - use provided field or try to load from entry
        if not field:
            if entry.form_item:
                field = entry.form_item
            else:
                # Try to load it if not already loaded
                from app.models.forms import FormItem
                field = db.session.get(FormItem, entry.form_item_id)

        # Check if this is a matrix field - matrix data is stored in disagg_data
        is_matrix_field = field and str(field.item_type).lower() == 'matrix'

        cls._log_verbose(f"Storing repeat data entry for field {entry.form_item_id}: is_matrix={is_matrix_field}, item_type={field.item_type if field else 'None'}, processed_value_type={type(processed_value)}, is_dict={isinstance(processed_value, dict)}, has_mode={isinstance(processed_value, dict) and 'mode' in processed_value if isinstance(processed_value, dict) else False}, processed_value_keys={list(processed_value.keys()) if isinstance(processed_value, dict) else 'N/A'}")

        # Check for disaggregated data first (has 'mode' and 'values' keys)
        if isinstance(processed_value, dict) and 'mode' in processed_value and 'values' in processed_value:
            # This is disaggregated data
            mode = processed_value['mode']
            values = processed_value['values']
            entry.set_disaggregated_data(mode, values)
            cls._log_verbose(f"Stored disaggregated data: mode={mode}")
        elif is_matrix_field and isinstance(processed_value, dict):
            # Matrix data - store in disagg_data, leave value as None
            # IMPORTANT: Do NOT call set_simple_value for matrix data as it clears disagg_data
            entry.value = None
            entry.disagg_data = processed_value
            # Explicitly ensure data_not_available and not_applicable are set AFTER setting disagg_data
            # (they will be set at the end, but being explicit here)
            cls._log_verbose(f"Stored matrix data in disagg_data for field {entry.form_item_id}: keys={list(processed_value.keys())}, sample_data={dict(list(processed_value.items())[:3])}")
        elif isinstance(processed_value, dict) and not is_matrix_field:
            # Non-matrix dict data - might be JSON string that was parsed
            # Convert to string for storage
            import json
            entry.value = json.dumps(processed_value) if processed_value else None
            entry.disagg_data = db.null()
            cls._log_verbose(f"Stored non-matrix dict as JSON string: {entry.value}")
        else:
            # Simple value - but check if it's a matrix field first to avoid overwriting
            if is_matrix_field:
                # Matrix field but value is not a dict - might be empty/None
                entry.value = None
                entry.disagg_data = db.null()
                cls._log_verbose(f"Matrix field with non-dict value (empty matrix): {processed_value}")
            else:
                # Simple value
                entry.set_simple_value(processed_value)
                cls._log_verbose(f"Stored simple value: {processed_value}")

        # Set data availability flags for all field types
        entry.data_not_available = data_not_available
        entry.not_applicable = not_applicable

    @classmethod
    def _process_repeat_document_data_comprehensive(cls, field, field_values, field_index):
        """Process repeat document data with comprehensive handling"""
        cls._log_verbose(f"Processing repeat document {field.id} with field_values: {field_values}")

        # For documents, we typically just need to check if a file was uploaded
        # This would be handled by the file upload processing, not the repeat group processing
        return None

    @classmethod
    def _process_repeat_matrix_data_comprehensive(cls, field, field_values, field_index):
        """Process repeat matrix data with comprehensive handling"""
        import json

        cls._log_verbose(f"Processing repeat matrix {field.id} with field_values: {field_values}")

        # Matrix data is stored in the hidden field: field_{field_index}_1
        # The first input (index 0) is the search input, the second (index 1) is the hidden field
        matrix_data_key = f'field_{field_index}_1'
        matrix_data_json = field_values.get(matrix_data_key, '')

        cls._log_verbose(f"Matrix data key: {matrix_data_key}, value: {matrix_data_json}")

        # Parse matrix data
        matrix_data = {}
        if matrix_data_json:
            try:
                matrix_data = json.loads(matrix_data_json)
                cls._log_verbose(f"Parsed matrix data for field {field.id}: {matrix_data}")
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Invalid matrix data for field {field.id}: {matrix_data_json} - {e}")
                matrix_data = {}

        # Return the matrix data dict (will be stored in disagg_data)
        # Return None if empty to indicate no data
        return matrix_data if matrix_data else None

    @classmethod
    def _process_repeat_disaggregation_indicator(cls, field, field_values, field_index):
        """Process repeat disaggregation indicator data"""
        cls._log_verbose(f"Processing repeat disaggregation indicator {field.id}")
        base = f'field_{field_index}'
        reporting_mode = field_values.get(f'{base}_reporting_mode', 'total')

        collected_values = {}
        has_any_value = False

        def parse_int(val_str, is_percentage=False):
            try:
                return float(val_str) if is_percentage else int(val_str)
            except (ValueError, TypeError):
                return None

        is_percentage = (getattr(field, 'type', '') == 'Percentage' or getattr(field, 'field_type_for_js', '').lower() == 'percentage')

        # total mode
        if reporting_mode == 'total':
            total_str = field_values.get(f'{base}_total_value', '')
            if total_str and str(total_str).strip():
                parsed = parse_int(total_str, is_percentage)
                if parsed is not None:
                    key = 'direct' if getattr(field, 'indirect_reach', False) else 'total'
                    collected_values[key] = parsed
                    has_any_value = True

        # sex mode
        elif reporting_mode == 'sex':
            sex_values = {}
            for sex_cat in getattr(field, 'effective_sex_categories', []):
                sex_slug = sex_cat.lower().replace(' ', '_').replace('-', '_')
                key = f'{base}_sex_{sex_slug}'
                val_str = field_values.get(key, '')
                if val_str and str(val_str).strip():
                    parsed = parse_int(val_str, is_percentage)
                    if parsed is not None:
                        sex_values[sex_slug] = parsed
            if sex_values:
                if getattr(field, 'indirect_reach', False):
                    collected_values['direct'] = sex_values
                else:
                    collected_values = sex_values
                has_any_value = True

        # age mode
        elif reporting_mode == 'age':
            age_values = {}
            for age_group in getattr(field, 'effective_age_groups', []):
                age_slug = FormItemProcessor.slugify_age_group(age_group)
                key = f'{base}_age_{age_slug}'
                val_str = field_values.get(key, '')
                if val_str and str(val_str).strip():
                    parsed = parse_int(val_str, is_percentage)
                    if parsed is not None:
                        age_values[age_slug] = parsed
            if age_values:
                if getattr(field, 'indirect_reach', False):
                    collected_values['direct'] = age_values
                else:
                    collected_values = age_values
                has_any_value = True

        # sex_age mode
        elif reporting_mode == 'sex_age':
            sex_age_values = {}
            for sex_cat in getattr(field, 'effective_sex_categories', []):
                sex_slug = sex_cat.lower().replace(' ', '_').replace('-', '_')
                for age_group in getattr(field, 'effective_age_groups', []):
                    age_slug = FormItemProcessor.slugify_age_group(age_group)
                    key = f'{base}_sexage_{sex_slug}_{age_slug}'
                    val_str = field_values.get(key, '')
                    if val_str and str(val_str).strip():
                        parsed = parse_int(val_str, is_percentage)
                        if parsed is not None:
                            sex_age_values[f'{sex_slug}_{age_slug}'] = parsed
            if sex_age_values:
                if getattr(field, 'indirect_reach', False):
                    collected_values['direct'] = sex_age_values
                else:
                    collected_values = sex_age_values
                has_any_value = True

        # optional indirect reach in repeat context
        if getattr(field, 'indirect_reach', False):
            ir_str = field_values.get(f'{base}_indirect_reach', '')
            if ir_str and str(ir_str).strip():
                with suppress((ValueError, TypeError)):
                    ir_val = int(ir_str)
                    if ir_val >= 0:
                        collected_values['indirect'] = ir_val
                        has_any_value = True

        if has_any_value:
            return { 'mode': reporting_mode, 'values': collected_values }

        return None

    @classmethod
    def _process_data_availability_flags(cls, all_sections: List, assignment_entity_status) -> List[Dict]:
        """Deprecated: availability flags are saved during field processing."""
        return []

    @classmethod
    def _validate_for_submission(cls, all_sections: List, assignment_entity_status) -> Dict[str, Any]:
        """Validate form data for submission"""
        validation_errors = []
        is_valid = True

        # Frontend relevance conditions hide fields and submit their IDs in `hidden_fields_to_clear`.
        # Those hidden fields should NOT block submission as "missing required" on the backend.
        #
        # We intentionally use this request-provided list instead of re-evaluating relevance
        # server-side because relevance may depend on plugin variables / complex client state.
        hidden_field_ids = set()
        try:
            hidden_fields_param = request.form.get('hidden_fields_to_clear', '').strip()
            if hidden_fields_param:
                hidden_field_ids = {
                    int(fid.strip())
                    for fid in hidden_fields_param.split(',')
                    if fid and fid.strip().isdigit()
                }
        except (ValueError, TypeError):
            # Never allow parsing issues to break submission validation
            hidden_field_ids = set()

        for section in all_sections:
            if hasattr(section, 'fields_ordered'):
                section_validation = cls._validate_section(section, assignment_entity_status, hidden_field_ids)
                if not section_validation['is_valid']:
                    is_valid = False
                    validation_errors.extend(section_validation['errors'])

        return {
            'is_valid': is_valid,
            'errors': validation_errors
        }

    @classmethod
    def _validate_section(cls, section, assignment_entity_status, hidden_field_ids=None) -> Dict[str, Any]:
        """Validate a single section"""
        errors = []
        is_valid = True

        if hasattr(section, 'section_type') and section.section_type == 'repeat':
            # Validate repeat sections
            validation_result = cls._validate_repeat_section(section, assignment_entity_status, hidden_field_ids)
            return validation_result

        # Validate regular sections
        if hasattr(section, 'fields_ordered'):
            for field in section.fields_ordered:
                field_id = getattr(field, 'id', None)
                if hidden_field_ids and field_id in hidden_field_ids:
                    # Field was hidden by relevance on the client; do not enforce required on submit.
                    continue

                if field.is_required_for_js:
                    field_validation = cls._validate_required_field(field, assignment_entity_status)
                    if not field_validation['is_valid']:
                        is_valid = False
                        errors.append(field_validation['error'])

        return {
            'is_valid': is_valid,
            'errors': errors
        }

    @classmethod
    def _validate_required_field(cls, field, assignment_entity_status) -> Dict[str, Any]:
        """Validate a required field has meaningful data"""
        if field.is_document_field:
            # Check for submitted document
            if cls._is_public_submission(assignment_entity_status):
                submitted_doc = SubmittedDocument.query.filter_by(
                    public_submission_id=assignment_entity_status.id,
                    form_item_id=field.id
                ).first()
            else:
                submitted_doc = SubmittedDocument.query.filter_by(
                    assignment_entity_status_id=assignment_entity_status.id,
                    form_item_id=field.id
                ).first()
            if not submitted_doc:
                return {
                    'is_valid': False,
                    'error': f"Required document '{field.label}' in section '{field.form_section.name}' is missing."
                }
        else:
            # Check form data using helper methods
            DataModel = cls._get_data_model(assignment_entity_status)
            query_filter = cls._get_data_query_filter(assignment_entity_status, field.id)

            form_data_entry = DataModel.query.filter_by(**query_filter).first()

            has_meaningful_data = cls._has_meaningful_data(form_data_entry)
            if not has_meaningful_data:
                # Extra diagnostics: required-field validation failures are costly UX-wise;
                # log what we found in DB to troubleshoot mode/structure mismatches.
                try:
                    logger.warning(
                        "[SUBMIT VALIDATION] Required field missing/empty. "
                        "aes_or_submission_id=%s form_item_id=%s label=%r "
                        "entry_exists=%s value=%r disagg_data=%r data_not_available=%r not_applicable=%r "
                        "prefilled_value=%r prefilled_disagg_data=%r imputed_value=%r imputed_disagg_data=%r",
                        getattr(assignment_entity_status, "id", None),
                        getattr(field, "id", None),
                        getattr(field, "label", None),
                        bool(form_data_entry),
                        getattr(form_data_entry, "value", None),
                        getattr(form_data_entry, "disagg_data", None),
                        getattr(form_data_entry, "data_not_available", None),
                        getattr(form_data_entry, "not_applicable", None),
                        getattr(form_data_entry, "prefilled_value", None),
                        getattr(form_data_entry, "prefilled_disagg_data", None),
                        getattr(form_data_entry, "imputed_value", None),
                        getattr(form_data_entry, "imputed_disagg_data", None),
                    )
                except Exception as e:
                    current_app.logger.debug("diagnostics logging failed (non-blocking): %s", e)

                return {
                    'is_valid': False,
                    'error': f"Required field '{field.label}' in section '{field.form_section.name}' is missing or empty."
                }

        return {'is_valid': True}

    @classmethod
    def _has_meaningful_data(cls, form_data_entry) -> bool:
        """Check if form data entry has meaningful data"""
        if not form_data_entry:
            return False

        # Data availability flags count as meaningful data
        if form_data_entry.data_not_available or form_data_entry.not_applicable:
            return True

        def _has_meaningful_in_obj(obj) -> bool:
            """
            Determine if a stored JSON-like object contains meaningful values.
            Treat 0 as meaningful (required fields may legitimately be 0).
            """
            if obj is None:
                return False
            if isinstance(obj, (int, float)):
                return True  # includes 0
            if isinstance(obj, str):
                s = obj.strip()
                return s not in ('', 'None', 'null', 'undefined')
            if isinstance(obj, list):
                return any(_has_meaningful_in_obj(v) for v in obj)
            if isinstance(obj, dict):
                # Common structure: {'mode': 'total', 'values': {...}} or {'values': {'direct': {...}, 'indirect': 0}}
                if 'values' in obj:
                    return _has_meaningful_in_obj(obj.get('values'))
                return any(_has_meaningful_in_obj(v) for v in obj.values())
            return bool(obj)

        # Disaggregation/matrix/plugin data can be stored in disagg_data (not in value)
        if getattr(form_data_entry, 'disagg_data', None) is not None:
            if _has_meaningful_in_obj(form_data_entry.disagg_data):
                return True

        # Prefilled/imputed values should count as meaningful for required validation
        if getattr(form_data_entry, 'prefilled_value', None) is not None:
            if _has_meaningful_in_obj(form_data_entry.prefilled_value):
                return True
        if getattr(form_data_entry, 'prefilled_disagg_data', None) is not None:
            if _has_meaningful_in_obj(form_data_entry.prefilled_disagg_data):
                return True
        if getattr(form_data_entry, 'imputed_value', None) is not None:
            if _has_meaningful_in_obj(form_data_entry.imputed_value):
                return True
        if getattr(form_data_entry, 'imputed_disagg_data', None) is not None:
            if _has_meaningful_in_obj(form_data_entry.imputed_disagg_data):
                return True

        if form_data_entry.value:
            try:
                # Try to parse as JSON for disaggregated data
                if isinstance(form_data_entry.value, str) and form_data_entry.value.strip():
                    stripped_value = form_data_entry.value.strip()
                    if stripped_value.startswith('{') or stripped_value.startswith('['):
                        with suppress(json.JSONDecodeError):
                            parsed_data = json.loads(form_data_entry.value)
                            if isinstance(parsed_data, dict) and 'values' in parsed_data:
                                values = parsed_data['values']
                                return any(v is not None and str(v).strip() for v in values.values())
                            elif isinstance(parsed_data, list):
                                return len(parsed_data) > 0

                    return bool(stripped_value)
                elif form_data_entry.value not in [None, '', 'None']:
                    return True
            except Exception as e:
                current_app.logger.debug("has_meaningful_value check failed: %s", e)
                return bool(form_data_entry.value and str(form_data_entry.value).strip())

        return False

    @classmethod
    def _validate_repeat_section(cls, section, assignment_entity_status, hidden_field_ids=None) -> Dict[str, Any]:
        """Validate repeat sections have at least one complete instance"""
        from app.models import RepeatGroupInstance

        if cls._is_public_submission(assignment_entity_status):
            repeat_instances = RepeatGroupInstance.query.filter_by(
                public_submission_id=assignment_entity_status.id,
                section_id=section.id
            ).all()
        else:
            repeat_instances = RepeatGroupInstance.query.filter_by(
                assignment_entity_status_id=assignment_entity_status.id,
                section_id=section.id
            ).all()

        if not repeat_instances:
            # Only enforce the "must have at least one entry" rule if there exists at least one
            # required field that is not hidden by relevance at submit-time.
            has_required_fields = any(
                field.is_required_for_js and not (hidden_field_ids and getattr(field, 'id', None) in hidden_field_ids)
                for field in section.fields_ordered
            )
            if has_required_fields:
                return {
                    'is_valid': False,
                    'errors': [f"Required section '{section.name}' has no entries. Please add at least one entry."]
                }

        # Check if at least one instance has all required fields filled
        for instance in repeat_instances:
            if cls._is_repeat_instance_complete(instance, section):
                return {'is_valid': True, 'errors': []}

        return {
            'is_valid': False,
            'errors': [f"Required fields in repeat section '{section.name}' are not completed in any instance."]
        }

    @classmethod
    def _is_repeat_instance_complete(cls, instance, section) -> bool:
        """Check if a repeat instance is complete"""
        # This would need to be implemented based on the original logic
        return True

    @staticmethod
    def should_create_data_availability_entry(field_value: Any, data_not_available: bool, not_applicable: bool) -> bool:
        """Determine if we should create a data availability entry"""
        return field_value is not None or data_not_available or not_applicable

    @staticmethod
    def create_data_availability_value(value, data_not_available=False, not_applicable=False):
        """Create a unified value with data availability flags"""
        if data_not_available:
            return "data_not_available"
        elif not_applicable:
            return "not_applicable"
        else:
            return value

    @staticmethod
    def parse_stored_value(stored_value):
        """Parse stored value from database"""
        if stored_value is None:
            return None
        elif stored_value == "data_not_available":
            return {"data_not_available": True}
        elif stored_value == "not_applicable":
            return {"not_applicable": True}
        else:
            return stored_value

    @classmethod
    def _process_matrix_data(cls, matrix: FormItem, assignment_entity_status, validation_errors: List, *, skip_required_validation: bool = False) -> List[Dict]:
        """Process matrix data from form submission"""
        field_changes = []

        try:
            # Get matrix data from form
            field_name = f'field_value[{matrix.id}]'
            matrix_data_json = request.form.get(field_name, '')

            # Get data availability flags
            data_not_available = request.form.get(f'matrix_{matrix.id}_data_not_available') == '1'
            not_applicable = request.form.get(f'matrix_{matrix.id}_not_applicable') == '1'

            cls._log_verbose(f"Processing matrix field {field_name}: {matrix_data_json}")
            cls._log_verbose(f"Matrix data_not_available: {data_not_available}, not_applicable: {not_applicable}")

            # Parse matrix data
            matrix_data = {}
            if matrix_data_json:
                try:
                    matrix_data = json.loads(matrix_data_json)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Invalid matrix data for field {matrix.id}: {matrix_data_json} - {e}")
                    matrix_data = {}

            # Determine final value and disagg_data
            if data_not_available:
                final_value = "data_not_available"
                final_disagg_data = None
            elif not_applicable:
                final_value = "not_applicable"
                final_disagg_data = None
            elif matrix_data:
                # For matrix data, store JSON in disagg_data and leave value as None
                final_value = None
                final_disagg_data = matrix_data
            else:
                final_value = None
                final_disagg_data = None

            # Get or create form data entry using helper methods
            DataModel = cls._get_data_model(assignment_entity_status)
            query_filter = cls._get_data_query_filter(assignment_entity_status, matrix.id)

            data_entry = DataModel.query.filter_by(**query_filter).first()

            if data_entry:
                # Track old value for change detection - handle matrix data stored in disagg_data
                old_data_not_available = data_entry.data_not_available or False
                old_not_applicable = data_entry.not_applicable or False

                # Get old value - prefer disagg_data if present (for matrix data), otherwise use value
                if data_entry.disagg_data:
                    old_value = data_entry.disagg_data
                else:
                    old_value = data_entry.get_effective_value()

                # Update with new value and disagg_data
                data_entry.value = final_value
                data_entry.disagg_data = final_disagg_data
                data_entry.data_not_available = data_not_available
                data_entry.not_applicable = not_applicable
                db.session.add(data_entry)

                # Determine new value for comparison - use disagg_data if present, otherwise use final_value
                new_value_for_comparison = final_disagg_data if final_disagg_data is not None else final_value

                # Record the change if value actually changed
                # Compare values properly - handle dict comparison for matrix data
                values_changed = False
                if isinstance(old_value, dict) and isinstance(new_value_for_comparison, dict):
                    # Compare dictionaries
                    values_changed = json.dumps(old_value, sort_keys=True) != json.dumps(new_value_for_comparison, sort_keys=True)
                else:
                    values_changed = old_value != new_value_for_comparison

                if (values_changed or
                    old_data_not_available != data_not_available or
                    old_not_applicable != not_applicable):

                    diff_old = old_value
                    diff_new = new_value_for_comparison
                    if isinstance(old_value, dict) and isinstance(new_value_for_comparison, dict):
                        all_keys = set(old_value.keys()) | set(new_value_for_comparison.keys())
                        changed_keys = {
                            k for k in all_keys
                            if old_value.get(k) != new_value_for_comparison.get(k)
                        }
                        if changed_keys:
                            diff_old = {'_matrix_change': True}
                            diff_old.update({k: old_value[k] for k in changed_keys if k in old_value})
                            diff_new = {'_matrix_change': True}
                            diff_new.update({k: new_value_for_comparison[k] for k in changed_keys if k in new_value_for_comparison})

                    field_changes.append({
                        'type': 'updated',
                        'form_item_id': matrix.id,
                        'field_name': get_english_field_name(matrix),
                        'old_value': diff_old,
                        'new_value': diff_new,
                        'old_data_not_available': old_data_not_available,
                        'new_data_not_available': data_not_available or False,
                        'old_not_applicable': old_not_applicable,
                        'new_not_applicable': not_applicable or False
                    })

            elif final_value is not None or final_disagg_data is not None or data_not_available or not_applicable:
                # Create new entry using helper method
                data_entry = cls._create_data_entry(assignment_entity_status, matrix.id)
                data_entry.value = final_value
                data_entry.disagg_data = final_disagg_data
                data_entry.data_not_available = data_not_available
                data_entry.not_applicable = not_applicable
                db.session.add(data_entry)

                # Determine new value for change tracking - use disagg_data if present, otherwise use final_value
                new_value_for_tracking = final_disagg_data if final_disagg_data is not None else final_value

                # Record the change
                field_changes.append({
                    'type': 'added',
                    'form_item_id': matrix.id,
                    'field_name': get_english_field_name(matrix),
                    'old_value': None,
                    'new_value': new_value_for_tracking,
                    'old_data_not_available': False,
                    'new_data_not_available': data_not_available or False,
                    'old_not_applicable': False,
                    'new_not_applicable': not_applicable or False
                })

            elif matrix.is_required and not skip_required_validation:
                validation_errors.append(f"Required matrix field '{matrix.label}' has no value.")
                logger.warning(f"Required matrix field {matrix.id} ({matrix.label}) has no value")

        except Exception as e:
            logger.error(f"Error processing matrix field {matrix.id}: {e}", exc_info=True)
            validation_errors.append(f"Matrix field '{matrix.label}': Processing error")

        return field_changes

    @classmethod
    def _is_public_submission(cls, obj):
        """Check if the object is a public submission"""
        # Check the class name to distinguish between AssignmentEntityStatus and PublicSubmission
        return obj.__class__.__name__ == 'PublicSubmission'

    @classmethod
    def _get_submission_id(cls, obj):
        """Get the submission ID (either assignment_entity_status_id or public_submission_id)"""
        if cls._is_public_submission(obj):
            return obj.id  # PublicSubmission.id
        else:
            return obj.id  # AssignmentEntityStatus.id

    @classmethod
    def _get_data_model(cls, obj):
        """Get the appropriate data model class"""
        # Both regular assignments and public submissions use the same FormData model
        # The difference is in the foreign key fields used
        from app.models import FormData
        return FormData

    @classmethod
    def _get_data_query_filter(cls, obj, form_item_id):
        """Get the appropriate query filter for data entries"""
        if cls._is_public_submission(obj):
            return {
                'public_submission_id': obj.id,
                'form_item_id': form_item_id
            }
        else:
            return {
                'assignment_entity_status_id': obj.id,
                'form_item_id': form_item_id
            }

    @classmethod
    def _create_data_entry(cls, obj, form_item_id):
        """Create a new data entry with the appropriate model"""
        DataModel = cls._get_data_model(obj)
        if cls._is_public_submission(obj):
            return DataModel(
                public_submission_id=obj.id,
                form_item_id=form_item_id
            )
        else:
            return DataModel(
                assignment_entity_status_id=obj.id,
                form_item_id=form_item_id
            )

    @classmethod
    def save_simple_field(cls, assignment_entity_status, form_item_id: int, value: str) -> Dict[str, Any]:
        """
        Save a simple field value with validation.

        Args:
            assignment_entity_status: AssignmentEntityStatus or PublicSubmission object
            form_item_id: The form item ID to save
            value: The value to save (string or None)

        Returns:
            Dict with success status and any error messages
        """
        try:
            # Get or create form data entry
            DataModel = cls._get_data_model(assignment_entity_status)
            query_filter = cls._get_data_query_filter(assignment_entity_status, form_item_id)

            data_entry = DataModel.query.filter_by(**query_filter).first()

            if data_entry:
                # Update existing entry
                if data_entry.value != value:
                    data_entry.set_simple_value(value)
                    db.session.add(data_entry)
                    cls._clear_ai_validation_for_form_data(data_entry, reason="save_simple_field_value_changed")
            elif value is not None:
                # Create new entry
                data_entry = cls._create_data_entry(assignment_entity_status, form_item_id)
                data_entry.set_simple_value(value)
                db.session.add(data_entry)

            return {'success': True, 'updated': True}

        except Exception as e:
            logger.error(f"Error saving simple field {form_item_id}: {e}", exc_info=True)
            return service_error(GENERIC_ERROR_MESSAGE)

    @classmethod
    def bulk_save_fields(cls, assignment_entity_status, field_data: Dict[int, str]) -> Dict[str, Any]:
        """
        Save multiple fields at once (for Excel import).

        Args:
            assignment_entity_status: AssignmentEntityStatus or PublicSubmission object
            field_data: Dict mapping form_item_id to value

        Returns:
            Dict with success status, count of updates, and any errors
        """
        updated_count = 0
        errors = []

        try:
            for form_item_id, value in field_data.items():
                result = cls.save_simple_field(assignment_entity_status, form_item_id, value)
                if result['success']:
                    if result.get('updated'):
                        updated_count += 1
                else:
                    errors.append(f"Field {form_item_id}: {result.get('error', 'Unknown error')}")

            # Persist all changes; middleware will commit when appropriate
            cls._commit_or_flush()

            return {
                'success': True,
                'updated_count': updated_count,
                'errors': errors
            }

        except Exception as e:
            cls._rollback_transaction("bulk_save_fields_error")
            logger.error(f"Error in bulk save: {e}", exc_info=True)
            return {
                'success': False,
                'updated_count': 0,
                'errors': ['An error occurred while saving.']
            }
