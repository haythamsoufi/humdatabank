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
from contextlib import suppress
from app.models import (
    db, FormItem, FormData, AIFormDataValidation,
    RepeatGroupInstance, SubmittedDocument, DynamicIndicatorData
)
from app.services.monitoring.debug import (
    debug_manager, performance_monitor, debug_request_info,
    log_user_action
)
from .processing_service import (
    FormItemProcessor,
    _create_dynamic_indicator_object,
)
from app.utils.api_helpers import service_error, GENERIC_ERROR_MESSAGE
from app.utils.form_localization import get_localized_indicator_name
from datetime import datetime
import json
import os
from typing import Dict, List, Tuple, Any, Optional
from app.models.enums import AssignmentEntityStatusValue
from app.utils.transactions import request_transaction_rollback
from app.services.forms.processors import (
    PluginProcessorMixin,
    IndicatorProcessorMixin,
    RepeatGroupProcessorMixin,
    DocumentProcessorMixin,
)

# Create a specific logger for this module using the debug manager
logger = debug_manager.get_logger(__name__)


from app.services.forms.processors._common import (  # noqa: F401 re-export
    get_english_field_name,
    decode_b64_matrix_json,
    get_possibly_chunked_form_value,
    read_waf_protected_form_value,
    MatrixJsonDecodeError,
)

class FormDataService(
    PluginProcessorMixin,
    IndicatorProcessorMixin,
    RepeatGroupProcessorMixin,
    DocumentProcessorMixin,
):
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

        if not is_public_submission:
            status = assignment_entity_status.status
            if hasattr(status, 'value'):
                status = status.value
            if status == AssignmentEntityStatusValue.cancelled.value:
                return {
                    'success': False,
                    'validation_errors': ['This assignment has been cancelled and can no longer be edited.'],
                    'field_changes': [],
                }

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

                    # Capture/refresh the emergency-operation identity for this dynamic section so
                    # saved data stays attributable to a specific appeal even if the source API
                    # later reorders results or filters change (Direction A binding).
                    try:
                        cls._persist_emergency_section_binding(section, assignment_entity_status)
                    except Exception as e:
                        logger.debug("Emergency section binding skipped for section %s: %s", section.id, e)

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
            if assignment_entity_status.status == AssignmentEntityStatusValue.pending:
                assignment_entity_status.status = AssignmentEntityStatusValue.in_progress

            # Persist changes (middleware will commit if we're in a managed request)
            cls._commit_or_flush()

            logger.debug(f"FormDataService: Committed changes, action: {action}")

            # Handle submission vs save
            effective_action = action
            if not is_public_submission:
                from flask_login import current_user as _cu
                from app.services.assignments.workflow_service import (
                    resolve_submit_action,
                    should_apply_sent_for_review,
                )
                effective_action = resolve_submit_action(
                    assignment_entity_status, _cu, action or 'save'
                )

            if effective_action in ('submit', 'send_for_review'):
                logger.debug("FormDataService: Processing %s action", effective_action)
                validation_result = cls._validate_for_submission(
                    all_sections, assignment_entity_status
                )
                if validation_result['is_valid']:
                    now = utcnow()
                    from flask_login import current_user as _cu
                    from app.services.assignments.workflow_service import should_apply_sent_for_review

                    if (
                        not is_public_submission
                        and should_apply_sent_for_review(
                            assignment_entity_status, effective_action
                        )
                    ):
                        from app.services.organization.authorization_service import AuthorizationService

                        if not AuthorizationService.can_send_for_review(
                            assignment_entity_status, _cu
                        ):
                            return {
                                'success': False,
                                'field_changes': field_changes_tracker,
                                'validation_errors': [
                                    'You do not have permission to send this assignment for review.'
                                ],
                                'submitted': False,
                            }

                        assignment_entity_status.status = AssignmentEntityStatusValue.sent_for_review
                        assignment_entity_status.status_timestamp = now
                        assignment_entity_status.sent_for_review_at = now
                        try:
                            if _cu and _cu.is_authenticated:
                                assignment_entity_status.sent_for_review_by_user_id = _cu.id
                        except Exception as e:
                            current_app.logger.debug(
                                "sent_for_review_by_user_id assignment failed: %s", e
                            )
                        cls._commit_or_flush()
                        return {
                            'success': True,
                            'field_changes': field_changes_tracker,
                            'validation_errors': [],
                            'submitted': False,
                            'sent_for_review': True,
                        }

                    assignment_entity_status.status = AssignmentEntityStatusValue.submitted
                    assignment_entity_status.status_timestamp = now
                    assignment_entity_status.submitted_at = now
                    try:
                        if _cu and _cu.is_authenticated:
                            assignment_entity_status.submitted_by_user_id = _cu.id
                    except Exception as e:
                        current_app.logger.debug("submitted_by_user_id assignment failed: %s", e)
                    cls._commit_or_flush()
                    result = {
                        'success': True,
                        'field_changes': field_changes_tracker,
                        'validation_errors': [],
                        'submitted': True,
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

            current_app.logger.exception(
                "Form submission failed for assignment %s (action=%s, sections=%s, user_id=%s)",
                assignment_entity_status.id,
                action,
                len(all_sections),
                current_user.id if current_user.is_authenticated else None,
            )

            # Log user action for audit
            log_user_action(
                "Form Submission Failed",
                {'error': 'Form submission failed', 'assignment_id': assignment_entity_status.id},
                logger=logger
            )

            error_result = {
                'success': False,
                'field_changes': field_changes_tracker,
                'validation_errors': [f"An error occurred while processing the form. Please try again."],
                'internal_error': True,
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
        data_entry.numeric_value = None
        data_entry.disagg_type = None
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
            data_entry.numeric_value = None
            data_entry.disagg_type = None
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
    def _store_scalar_question_value(cls, data_entry, question, processed_value):
        """Store a scalar question value and any emergency-operation metadata."""
        if isinstance(processed_value, dict) and 'mode' in processed_value and 'values' in processed_value:
            data_entry.set_disaggregated_data(processed_value['mode'], processed_value['values'])
            return

        data_entry.set_simple_value(processed_value)
        if cls._is_emergency_operations_choice(question) and processed_value:
            cls._apply_emergency_operation_disagg(
                data_entry,
                processed_value,
                cls._get_emergency_metadata_from_request(form_item_id=question.id),
            )

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

        try:
            processed_value, has_value, data_not_available, not_applicable = FormItemProcessor.process_form_item_data(
                question, request.form, assignment_entity_status.id, field_prefix=field_prefix
            )
        except MatrixJsonDecodeError as e:
            # Raised before any data_entry is touched, so a previously saved
            # answer for this question is left untouched — see
            # decode_b64_matrix_json's safe-failure contract.
            current_app.logger.error(f"Question {question.id}: {e}")
            validation_errors.append(
                f"Question '{question.label}': submitted data could not be decoded. "
                "Refresh the page and try again."
            )
            return field_changes

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
            if cls._should_preserve_existing_on_empty_save(
                form_item_id, data_entry, is_presave=is_presave, field_cleared=field_cleared
            ):
                cls._log_verbose(
                    "Question %s: save submitted empty but existing data preserved (presave=%s).",
                    form_item_id,
                    is_presave,
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
                    cls._store_scalar_question_value(data_entry, question, processed_value)

                db.session.add(data_entry)

                # Determine if there's a meaningful change
                if cls._is_emergency_operations_choice(question):
                    emergency_metadata = cls._get_emergency_metadata_from_request(form_item_id=question.id)
                    old_display = cls._normalize_emergency_operation_from_entry(data_entry)
                    new_display = cls._normalize_emergency_operation_value(processed_value, emergency_metadata)
                    value_changed = old_display != new_display
                    activity_old_value = old_display
                    activity_new_value = new_display
                else:
                    value_changed = old_value != processed_value
                    activity_old_value = old_value
                    activity_new_value = processed_value
                availability_changed = (old_data_not_available != data_not_available) or (old_not_applicable != not_applicable)

                if value_changed or availability_changed:
                    cls._clear_ai_validation_for_form_data(data_entry, reason="question_value_changed")
                    field_changes.append({
                        'type': 'updated',
                        'form_item_id': form_item_id,
                        'field_name': get_english_field_name(question),
                        'old_value': activity_old_value,
                        'new_value': activity_new_value,
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
                    cls._store_scalar_question_value(data_entry, question, processed_value)

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
            # Replace the __other__ sentinel with the user-typed free text
            if '__other__' in selected_options:
                other_text = (request.form.get(f'field_other_text[{question.id}]') or '').strip()
                selected_options = [v for v in selected_options if v != '__other__']
                if other_text:
                    selected_options.append(other_text)
            return json.dumps(selected_options) if selected_options else None

        elif question.type == 'single_choice':
            single_val = str(raw_value).strip() if raw_value and isinstance(raw_value, str) else None
            # Replace the __other__ sentinel with the user-typed free text
            if single_val == '__other__':
                single_val = (request.form.get(f'field_other_text[{question.id}]') or '').strip() or None
            return single_val

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
                        'indirect': indirect_reach_value
                    }
                }
                return disaggregation_data
            except ValueError:
                flash(f"Invalid indirect reach for question '{question.label}'.", "warning")

        return final_value

    @classmethod
    def _create_pending_dynamic_indicators(cls, section, assignment_entity_status, validation_errors: List) -> Dict[str, int]:
        """Create DB records for pending dynamic indicators and return mapping of temp IDs to real IDs.

        Handles two key formats emitted by the frontend:
          - pending_dynamic_indicator_{sectionId}          → section-level (repeat_instance_number=None)
          - pending_dynamic_indicator_{sectionId}_ri_{N}   → repeat-entry-level (repeat_instance_number=N)
        """
        temp_to_real_map = {}

        # Collect all pending indicator keys for this section (section-level and per-repeat-instance)
        import re as _re
        section_prefix = f'pending_dynamic_indicator_{section.id}'
        pending_by_instance: Dict[object, list] = {}  # key = repeat_instance_number (None or int)

        for form_key in request.form.keys():
            if form_key == section_prefix:
                pending_by_instance.setdefault(None, []).extend(request.form.getlist(form_key))
            elif form_key.startswith(f'{section_prefix}_ri_'):
                m = _re.fullmatch(rf'pending_dynamic_indicator_{section.id}_ri_(\d+)', form_key)
                if m:
                    instance_num = int(m.group(1))
                    pending_by_instance.setdefault(instance_num, []).extend(request.form.getlist(form_key))

        if not pending_by_instance:
            return temp_to_real_map

        is_public = cls._is_public_submission(assignment_entity_status)
        from app.models import IndicatorBank
        max_allowed = getattr(section, 'max_dynamic_indicators', None)
        if max_allowed is not None:
            try:
                max_allowed = int(max_allowed)
            except (TypeError, ValueError):
                max_allowed = None

        for repeat_instance_number, pending_values in pending_by_instance.items():
            # Get existing assignments for this (section, repeat_instance) combination
            if is_public:
                existing_assignments = DynamicIndicatorData.query.filter_by(
                    public_submission_id=assignment_entity_status.id,
                    section_id=section.id,
                    repeat_instance_number=repeat_instance_number
                ).all()
            else:
                existing_assignments = DynamicIndicatorData.query.filter_by(
                    assignment_entity_status_id=assignment_entity_status.id,
                    section_id=section.id,
                    repeat_instance_number=repeat_instance_number
                ).all()

            existing_indicator_ids = {a.indicator_bank_id for a in existing_assignments}
            max_order = max((a.order for a in existing_assignments), default=0)

            if max_allowed is not None and len(existing_assignments) >= max_allowed:
                validation_errors.append("Maximum indicators reached for this section.")
                continue

            for pending_value in pending_values:
                try:
                    parts = pending_value.split(':')
                    if len(parts) != 2:
                        continue

                    indicator_bank_id = int(parts[0])
                    temp_assignment_id = parts[1]

                    if indicator_bank_id in existing_indicator_ids:
                        continue

                    if max_allowed is not None and len(existing_assignments) >= max_allowed:
                        validation_errors.append("Maximum indicators reached for this section.")
                        break

                    indicator = IndicatorBank.query.get(indicator_bank_id)
                    if not indicator:
                        continue

                    max_order += 1
                    dynamic_assignment = DynamicIndicatorData(
                        section_id=section.id,
                        indicator_bank_id=indicator_bank_id,
                        custom_label=None,
                        order=max_order,
                        added_by_user_id=current_user.id,
                        repeat_instance_number=repeat_instance_number
                    )

                    if is_public:
                        dynamic_assignment.public_submission_id = assignment_entity_status.id
                    else:
                        dynamic_assignment.assignment_entity_status_id = assignment_entity_status.id

                    db.session.add(dynamic_assignment)
                    db.session.flush()

                    temp_to_real_map[temp_assignment_id] = dynamic_assignment.id
                    existing_indicator_ids.add(indicator_bank_id)
                    existing_assignments.append(dynamic_assignment)

                    cls._log_verbose(
                        f"Created pending dynamic indicator: temp_id={temp_assignment_id}, "
                        f"real_id={dynamic_assignment.id}, indicator_id={indicator_bank_id}, "
                        f"repeat_instance={repeat_instance_number}"
                    )

                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid pending indicator value: {pending_value}, error: {e}")
                    continue

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
    def _persist_emergency_section_binding(cls, section, assignment_entity_status) -> None:
        """Freeze the emergency (appeal-code) identity for an emergency dynamic section.

        Only applies to assignment submissions (not public submissions) and only when the section
        references an [EOn] slot and has at least one dynamic indicator row. The actual ordering and
        identity resolution live in .emergency_section_binding.
        """
        if cls._is_public_submission(assignment_entity_status):
            return

        from .emergency_section_binding import slot_for_section, persist_section_binding

        if not slot_for_section(section):
            return

        # Only bind sections that actually carry dynamic indicators.
        has_rows = DynamicIndicatorData.query.filter_by(
            assignment_entity_status_id=assignment_entity_status.id,
            section_id=section.id,
        ).first() is not None
        if not has_rows:
            return

        user_id = None
        try:
            from flask_login import current_user
            if current_user and getattr(current_user, 'is_authenticated', False):
                user_id = current_user.id
        except Exception:
            user_id = None

        persist_section_binding(section, assignment_entity_status, user_id=user_id)

    @classmethod
    def _delete_pending_dynamic_indicators(cls, section, assignment_entity_status) -> set:
        """Delete dynamic indicators marked for removal on form save.

        The frontend writes a hidden input ``delete_dynamic_indicator_{assignmentId}``
        for each saved indicator the user removes before saving.  We process those here
        in the same DB transaction as the rest of the form save so that the deletion is
        atomic and only takes effect when the user actually submits.

        Returns the set of deleted assignment IDs so the caller can skip them when
        iterating over dynamic assignments.
        """
        import re as _re
        deleted_ids: set = set()
        is_public = cls._is_public_submission(assignment_entity_status)

        for form_key in request.form.keys():
            m = _re.fullmatch(r'delete_dynamic_indicator_(\d+)', form_key)
            if not m:
                continue
            assignment_id = int(m.group(1))
            assignment = DynamicIndicatorData.query.get(assignment_id)
            if not assignment:
                continue

            # Ownership check — assignment must belong to this section and submission
            if assignment.section_id != section.id:
                logger.warning(
                    f"Attempted to delete dynamic indicator {assignment_id} "
                    f"that does not belong to section {section.id} — skipped"
                )
                continue
            if is_public:
                if assignment.public_submission_id != assignment_entity_status.id:
                    logger.warning(
                        f"Attempted to delete dynamic indicator {assignment_id} "
                        f"belonging to a different public submission — skipped"
                    )
                    continue
            else:
                if assignment.assignment_entity_status_id != assignment_entity_status.id:
                    logger.warning(
                        f"Attempted to delete dynamic indicator {assignment_id} "
                        f"belonging to a different assignment — skipped"
                    )
                    continue

            db.session.delete(assignment)
            deleted_ids.add(assignment_id)
            logger.info(f"Deferred-deleted dynamic indicator assignment {assignment_id}")

        return deleted_ids

    @classmethod
    def _process_dynamic_indicators(cls, section, assignment_entity_status, validation_errors: List) -> List[Dict]:
        """Process dynamic indicators using unified FormItemProcessor approach"""
        field_changes = []

        # Debug: Log all form field names to see dynamic indicator patterns
        all_form_fields = list(request.form.keys())
        dynamic_field_names = [name for name in all_form_fields if 'dynamic' in name]
        cls._log_verbose(f"All form field names: {all_form_fields}")
        cls._log_verbose(f"Dynamic field names: {dynamic_field_names}")

        # Delete indicators the user removed before saving (deferred from the UI delete button)
        deleted_ids = cls._delete_pending_dynamic_indicators(section, assignment_entity_status)

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
            if dynamic_assignment.id in deleted_ids:
                continue  # already deleted above — skip value processing
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
                        dynamic_assignment.disagg_type = None
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
                if data_not_available or not_applicable:
                    dynamic_assignment.set_data_availability(data_not_available, not_applicable)
                elif isinstance(processed_value, dict) and 'mode' in processed_value and 'values' in processed_value:
                    dynamic_assignment.set_disaggregated_data(processed_value['mode'], processed_value['values'])
                elif isinstance(processed_value, dict):
                    dynamic_assignment.value = None
                    dynamic_assignment.numeric_value = None
                    dynamic_assignment.disagg_data = processed_value
                    dynamic_assignment.disagg_type = 'matrix'
                    dynamic_assignment.data_not_available = False
                    dynamic_assignment.not_applicable = False
                else:
                    dynamic_assignment.set_simple_value(processed_value)
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

                if getattr(field, 'is_image', False):
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

                    # Exclude stringified-null sentinels (matches _has_meaningful_in_obj above) —
                    # these can arrive verbatim from JS serialization bugs and are not real data.
                    return stripped_value not in ('None', 'null', 'undefined')
                elif form_data_entry.value not in [None, '', 'None']:
                    return True
            except Exception as e:
                current_app.logger.debug("has_meaningful_value check failed: %s", e)
                return bool(form_data_entry.value and str(form_data_entry.value).strip())

        return False

    @classmethod
    def _validate_repeat_section(cls, section, assignment_entity_status, hidden_field_ids=None) -> Dict[str, Any]:
        """Validate repeat sections have at least one complete instance"""
        # RepeatGroupInstance is already imported at module level — do not re-import it
        # here, since a local import would shadow (and break) test-time patching of
        # app.services.forms.data_service.RepeatGroupInstance.

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
            # No entries, but nothing required either — an empty optional repeat section is valid.
            return {'is_valid': True, 'errors': []}

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
            # Get matrix data from form (client may base64-encode to avoid WAF
            # blocks, and may split large values across field_name/__c1/__c2).
            field_name = f'field_value[{matrix.id}]'
            matrix_data_json = read_waf_protected_form_value(request.form, field_name)

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

            if matrix_data:
                from app.utils.api_serialization import prune_stale_matrix_cell_keys
                matrix_config = (matrix.config or {}).get('matrix_config') or {}
                pruned_matrix_data = prune_stale_matrix_cell_keys(matrix_data, matrix_config)
                if len(pruned_matrix_data) != len(matrix_data):
                    dropped_keys = sorted(set(matrix_data) - set(pruned_matrix_data))
                    logger.info(
                        f"Matrix field {matrix.id}: dropped {len(dropped_keys)} stale cell key(s) "
                        f"no longer matching current columns: {dropped_keys}"
                    )
                matrix_data = pruned_matrix_data

            # Determine final value and disagg_data
            if data_not_available:
                final_value = None
                final_disagg_data = None
            elif not_applicable:
                final_value = None
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
                if data_not_available or not_applicable:
                    data_entry.set_data_availability(data_not_available, not_applicable)
                else:
                    data_entry.value = final_value
                    data_entry.numeric_value = None
                    data_entry.disagg_data = final_disagg_data
                    data_entry.disagg_type = 'matrix' if final_disagg_data is not None else None
                    data_entry.data_not_available = False
                    data_entry.not_applicable = False
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
                        from app.utils.matrix_activity import (
                            matrix_cell_activity_values_differ,
                            matrix_cell_display_value,
                        )

                        all_keys = set(old_value.keys()) | set(new_value_for_comparison.keys())
                        changed_keys = {
                            k
                            for k in all_keys
                            if matrix_cell_activity_values_differ(
                                old_value.get(k), new_value_for_comparison.get(k)
                            )
                        }
                        if changed_keys:
                            diff_old = {"_matrix_change": True}
                            diff_new = {"_matrix_change": True}
                            for k in changed_keys:
                                diff_old[k] = matrix_cell_display_value(old_value.get(k))
                                diff_new[k] = matrix_cell_display_value(
                                    new_value_for_comparison.get(k)
                                )

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
                if data_not_available or not_applicable:
                    data_entry.set_data_availability(data_not_available, not_applicable)
                else:
                    data_entry.value = final_value
                    data_entry.numeric_value = None
                    data_entry.disagg_data = final_disagg_data
                    data_entry.disagg_type = 'matrix' if final_disagg_data is not None else None
                    data_entry.data_not_available = False
                    data_entry.not_applicable = False
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

        except MatrixJsonDecodeError as e:
            # Raised before data_entry is looked up/mutated above, so the previously
            # saved matrix value is untouched. Report a real failure instead of the
            # generic message so this is distinguishable in logs from other bugs.
            logger.error(f"Matrix field {matrix.id}: {e}")
            validation_errors.append(
                f"Matrix field '{matrix.label}': submitted data could not be decoded. "
                "Refresh the page and try again."
            )
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
    def _create_data_entry(cls, obj, form_item_id, created_by_user_id=None):
        """Create a new data entry with the appropriate model."""
        DataModel = cls._get_data_model(obj)
        if cls._is_public_submission(obj):
            kwargs = {
                'public_submission_id': obj.id,
                'form_item_id': form_item_id,
            }
        else:
            kwargs = {
                'assignment_entity_status_id': obj.id,
                'form_item_id': form_item_id,
            }

        if DataModel is FormData:
            kwargs['created_at'] = utcnow()
            if created_by_user_id is None and current_user.is_authenticated:
                created_by_user_id = current_user.id
            kwargs['created_by_user_id'] = created_by_user_id

        return DataModel(**kwargs)

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

            if hasattr(assignment_entity_status, 'id') and getattr(
                assignment_entity_status, 'assigned_form_id', None
            ):
                from app.services.assignments.completion_service import AssignmentCompletionService
                AssignmentCompletionService.refresh_and_persist(assignment_entity_status.id)

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
