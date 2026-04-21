"""Entry form rendering and display routes.

Contains the unified form viewing/editing endpoint, assignment form handler,
and template preview route.
"""
from __future__ import annotations

from contextlib import suppress
import json
import re

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_babel import _
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy.orm import joinedload

from app import get_locale
from app.models import (
    db, AssignedForm, AssignmentEntityStatus, Country, DynamicIndicatorData,
    FormData, FormItem, FormPage, FormSection, PublicSubmission,
    QuestionType, RepeatGroupData, RepeatGroupInstance, SubmittedDocument,
)
from app.models.enums import EntityType
from app.services.entity_service import EntityService
from app.services.form_data_service import FormDataService
from app.services.form_processing_service import get_form_items_for_section, slugify_age_group
from app.services.monitoring.debug import debug_manager, performance_monitor
from app.services.notification.core import log_entity_activity, notify_assignment_submitted
from app.services.template_preparation_service import TemplatePreparationService
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_bad_request, json_ok, json_server_error
from app.utils.assignment_document_carryover import merge_carryover_into_submitted_documents_dict
from app.utils.form_authorization import admin_required
from app.utils.form_localization import (
    get_localized_country_name,
    get_localized_indicator_definition,
    get_localized_indicator_type,
    get_localized_indicator_unit,
    get_localized_page_name,
    get_localized_section_name,
    get_localized_template_name,
    get_translation_key,
)
from app.utils.request_utils import is_json_request
from app.utils.route_helpers import get_unified_form_url, get_unified_form_item_id
from app.utils.transactions import request_transaction_rollback
from config import Config

from .helpers import (
    _load_existing_data_for_assignment,
    calculate_section_completion_status,
    process_existing_data_for_template,
)

# Late import to avoid circular reference at module level
def _get_bp():
    from . import bp
    return bp


def register_entry_routes(bp):
    """Register all entry/rendering routes onto the forms blueprint."""

    @bp.route("/<form_type>/<int:form_id>", methods=["GET", "POST"])
    @login_required
    def view_edit_form(form_type, form_id):
        """Unified form viewing/editing endpoint for all form types."""
        if form_type == "assignment":
            return handle_assignment_form(form_id)
        elif form_type == "public-submission":
            return redirect(url_for("forms.view_public_submission", submission_id=form_id))
        else:
            flash(_("Invalid form type."), "danger")
            return redirect(url_for("main.dashboard"))

    @bp.route("/assignment_status/<int:aes_id>", methods=["GET", "POST"])
    @login_required
    def enter_data(aes_id):
        """Legacy route for backward compatibility - redirects to unified route."""
        return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))

    @bp.route("/templates/preview/<int:template_id>", methods=["GET"])
    @admin_required
    def preview_template(template_id):
        """Preview a form template using existing form processing logic."""
        return _preview_template_impl(template_id)


@performance_monitor("Assignment Form Handling")
def handle_assignment_form(aes_id):
    """Handle assignment form viewing/editing for focal points - CLEANED VERSION."""
    forms_logger = debug_manager.get_logger('app.routes.forms')

    from app.services import AssignmentService
    assignment_entity_status = AssignmentService.get_assignment_entity_status_by_id(aes_id)
    if not assignment_entity_status:
        current_app.logger.error(f"AssignmentEntityStatus not found for ID: {aes_id}")
        current_app.logger.error(f"Request method: {request.method}")
        current_app.logger.error(f"Request URL: {request.url}")
        current_app.logger.error(f"User: {current_user.email}")

        available_assignments = AssignmentEntityStatus.query\
            .filter(AssignmentEntityStatus.entity_type == EntityType.country.value)\
            .filter(AssignmentEntityStatus.entity_id.in_([c.id for c in current_user.countries.all()]))\
            .all()
        current_app.logger.error(f"Available AssignmentEntityStatus IDs for current user: {[aes.id for aes in available_assignments]}")

        flash(_("Assignment status for this country not found (ID: %(id)d). Please check the URL or contact support.", id=aes_id), "danger")
        return redirect(url_for("main.dashboard"))

    assignment = assignment_entity_status.assigned_form

    if assignment is not None and getattr(assignment, "is_active", True) is False:
        flash(_("This assignment is currently inactive."), "warning")
        return redirect(url_for("main.dashboard"))

    from app.services.authorization_service import AuthorizationService

    if not AuthorizationService.can_access_assignment(assignment_entity_status, current_user):
        entity_type = assignment_entity_status.entity_type
        entity_id = assignment_entity_status.entity_id
        entity_name = EntityService.get_entity_display_name(entity_type, entity_id)
        current_app.logger.warning(
            f"Access denied for user {current_user.email} to AssignmentEntityStatus {aes_id} "
            f"(Entity: {entity_type} {entity_id} - {entity_name}) - user does not have entity access."
        )
        flash(_("You are not authorized to access this assignment for %(entity)s.", entity=entity_name), "warning")
        return redirect(url_for("main.dashboard"))

    can_edit = AuthorizationService.can_edit_assignment(assignment_entity_status, current_user)
    form_template = assignment.template

    template, all_sections, available_indicators_by_section = TemplatePreparationService.prepare_template_for_rendering(
        form_template, assignment_entity_status, is_preview_mode=False
    )

    from app.services.variable_resolution_service import VariableResolutionService
    from app.models import FormTemplateVersion

    template_version = None
    resolved_variables = {}
    variable_configs = {}
    if form_template.published_version_id:
        template_version = FormTemplateVersion.query.get(form_template.published_version_id)

        if template_version:
            variable_configs = template_version.variables or {}
            try:
                placeholder_pattern = re.compile(r'\[(\w+)\]')

                def _extract_placeholders_from_sections(sections):
                    names = set()
                    for section in (sections or []):
                        sn = getattr(section, 'display_name', None)
                        if sn and '[' in sn:
                            names.update(placeholder_pattern.findall(sn))

                        for field in getattr(section, 'fields_ordered', []) or []:
                            if not field:
                                continue

                            for attr in ('label', 'display_label', 'definition', 'description'):
                                t = getattr(field, attr, None)
                                if t and '[' in t:
                                    names.update(placeholder_pattern.findall(t))

                            for attr in ('label_translations', 'definition_translations', 'description_translations'):
                                d = getattr(field, attr, None)
                                if isinstance(d, dict) and d:
                                    for v in d.values():
                                        if v and '[' in v:
                                            names.update(placeholder_pattern.findall(v))

                            if getattr(field, 'item_type', None) == 'matrix' and getattr(field, 'config', None):
                                try:
                                    matrix_config = field.config.get('matrix_config') if isinstance(field.config, dict) and 'matrix_config' in field.config else field.config
                                    if isinstance(matrix_config, dict):
                                        row_mode = matrix_config.get('row_mode', 'manual')
                                        if row_mode == 'manual' or not row_mode:
                                            rows = matrix_config.get('rows', [])
                                            if isinstance(rows, list):
                                                for row in rows:
                                                    if isinstance(row, dict):
                                                        for v in row.values():
                                                            if v and '[' in str(v):
                                                                names.update(placeholder_pattern.findall(str(v)))
                                                    elif isinstance(row, str) and '[' in row:
                                                        names.update(placeholder_pattern.findall(row))
                                except Exception as e:
                                    current_app.logger.debug("Placeholder extraction from row failed: %s", e)
                    return names

                placeholders = _extract_placeholders_from_sections(all_sections)
                resolvable_token_names = set(variable_configs.keys()) | set(getattr(VariableResolutionService, "_BUILTIN_METADATA_TYPES", {}).keys())
                should_resolve_variables = bool(placeholders & resolvable_token_names)
            except Exception as e:
                current_app.logger.debug("Placeholder extraction failed: %s", e)
                should_resolve_variables = True

            try:
                if should_resolve_variables:
                    resolved_variables = VariableResolutionService.resolve_variables(
                        template_version,
                        assignment_entity_status
                    )
                    current_app.logger.debug(
                        f"Variable resolution: Resolved {len(resolved_variables)} variables: {list(resolved_variables.keys())}"
                    )
                else:
                    resolved_variables = {}
            except Exception as e:
                current_app.logger.warning(f"Variable resolution failed: {e}", exc_info=True)
                resolved_variables = {}

            _match_by_bank_cache = {}
            placeholder_pattern = re.compile(r'\[(\w+)\]')

            def _resolved_vars_for_field(field_obj, text_value: str):
                merged = resolved_variables or {}
                if not (template_version and variable_configs and isinstance(variable_configs, dict)):
                    return merged
                if not text_value or '[' not in str(text_value):
                    return merged

                names = set(placeholder_pattern.findall(str(text_value)))
                if not names:
                    return merged

                out = None
                for var_name in names:
                    cfg = variable_configs.get(var_name) if isinstance(variable_configs, dict) else None
                    if not (cfg and isinstance(cfg, dict) and cfg.get('match_by_indicator_bank')):
                        continue
                    val = VariableResolutionService.resolve_variable_by_indicator_bank(
                        cfg,
                        assignment_entity_status,
                        field_obj,
                        cache=_match_by_bank_cache
                    )
                    if out is None:
                        out = dict(merged)
                    out[var_name] = val

                return out if out is not None else merged

            for section in all_sections:
                if hasattr(section, 'display_name') and section.display_name and resolved_variables and '[' in section.display_name:
                    try:
                        section._display_name_resolved = VariableResolutionService.replace_variables_in_text(
                            section.display_name,
                            _resolved_vars_for_field(section, section.display_name),
                            variable_configs
                        )
                    except Exception as e:
                        current_app.logger.warning(
                            f"Error resolving variables in section name for section {getattr(section, 'id', 'unknown')}: {e}",
                            exc_info=True
                        )

                for field in getattr(section, 'fields_ordered', []):
                    if not field or not hasattr(field, 'id'):
                        continue

                    if hasattr(field, 'label') and field.label and resolved_variables and '[' in field.label:
                        original_label = field.label
                        resolved_label = VariableResolutionService.replace_variables_in_text(
                            field.label,
                            _resolved_vars_for_field(field, field.label),
                            variable_configs
                        )
                        field._display_label = resolved_label

                    if hasattr(field, 'display_label') and field.display_label and resolved_variables and '[' in field.display_label:
                        original_display_label = field.display_label
                        resolved_display_label = VariableResolutionService.replace_variables_in_text(
                            field.display_label,
                            _resolved_vars_for_field(field, field.display_label),
                            variable_configs
                        )
                        field._display_label_resolved = resolved_display_label

                    if hasattr(field, 'label_translations') and field.label_translations and resolved_variables:
                        resolved_label_translations = {}
                        for lang_code, translated_label in field.label_translations.items():
                            if translated_label and '[' in translated_label:
                                original_translated = translated_label
                                resolved_translated = VariableResolutionService.replace_variables_in_text(
                                    translated_label,
                                    _resolved_vars_for_field(field, translated_label),
                                    variable_configs
                                )
                                resolved_label_translations[lang_code] = resolved_translated
                            elif translated_label:
                                resolved_label_translations[lang_code] = translated_label
                        field._display_label_translations = resolved_label_translations

                    if hasattr(field, 'definition') and field.definition and resolved_variables and '[' in field.definition:
                        original_definition = field.definition
                        resolved_definition = VariableResolutionService.replace_variables_in_text(
                            field.definition,
                            _resolved_vars_for_field(field, field.definition),
                            variable_configs
                        )
                        field._display_definition = resolved_definition

                    if hasattr(field, 'description') and field.description and resolved_variables and '[' in field.description:
                        original_description = field.description
                        resolved_description = VariableResolutionService.replace_variables_in_text(
                            field.description,
                            _resolved_vars_for_field(field, field.description),
                            variable_configs
                        )
                        field._display_description = resolved_description

                    if hasattr(field, 'definition_translations') and field.definition_translations:
                        resolved_definition_translations = {}
                        for lang_code, translated_def in field.definition_translations.items():
                            if translated_def and resolved_variables and '[' in translated_def:
                                original_translated = translated_def
                                resolved_translated = VariableResolutionService.replace_variables_in_text(
                                    translated_def,
                                    _resolved_vars_for_field(field, translated_def),
                                    variable_configs
                                )
                                resolved_definition_translations[lang_code] = resolved_translated
                            elif translated_def:
                                resolved_definition_translations[lang_code] = translated_def
                        field._display_definition_translations = resolved_definition_translations

                    if hasattr(field, 'description_translations') and field.description_translations:
                        resolved_description_translations = {}
                        for lang_code, translated_desc in field.description_translations.items():
                            if translated_desc and resolved_variables and '[' in translated_desc:
                                original_translated = translated_desc
                                resolved_translated = VariableResolutionService.replace_variables_in_text(
                                    translated_desc,
                                    _resolved_vars_for_field(field, translated_desc),
                                    variable_configs
                                )
                                resolved_description_translations[lang_code] = resolved_translated
                            elif translated_desc:
                                resolved_description_translations[lang_code] = translated_desc
                        field._display_description_translations = resolved_description_translations

                    if hasattr(field, 'item_type') and field.item_type == 'matrix' and hasattr(field, 'config') and field.config:
                        try:
                            matrix_config = field.config.get('matrix_config') if isinstance(field.config, dict) and 'matrix_config' in field.config else field.config
                            if isinstance(matrix_config, dict):
                                row_mode = matrix_config.get('row_mode', 'manual')
                                if row_mode == 'manual' or not row_mode:
                                    rows = matrix_config.get('rows', [])
                                    if rows and isinstance(rows, list):
                                        resolved_rows = []
                                        for row in rows:
                                            if isinstance(row, str) and resolved_variables and '[' in row:
                                                resolved_row = VariableResolutionService.replace_variables_in_text(
                                                    row,
                                                    _resolved_vars_for_field(field, row),
                                                    variable_configs
                                                )
                                                resolved_rows.append(resolved_row)
                                            else:
                                                resolved_rows.append(row)
                                        field._display_matrix_rows = resolved_rows
                        except Exception as e:
                            current_app.logger.warning(f"Error resolving variables in matrix row labels for field {field.id}: {e}", exc_info=True)

    db_sections = [s for s in all_sections if s.parent_section_id is None]

    published_pages = (
        FormPage.query
        .filter_by(template_id=form_template.id, version_id=form_template.published_version_id)
        .order_by(FormPage.order)
        .all()
    )

    csrf_form = FlaskForm()
    SEX_CATEGORIES = Config.DEFAULT_SEX_CATEGORIES

    existing_data_processed = _load_existing_data_for_assignment(
        assignment_entity_status, form_template
    )

    for section in all_sections:
        for field in getattr(section, 'fields_ordered', []):
            if not field or not hasattr(field, 'id'):
                continue

            field_key = f'field_value[{field.id}]'

            if field_key in existing_data_processed:
                continue

            def _is_numeric_type(t):
                try:
                    return str(t or '').strip().lower() in ('number', 'integer', 'float', 'currency', 'percentage')
                except Exception as e:
                    current_app.logger.debug("_is_numeric_type failed: %s", e)
                    return False

            is_number_field = False
            if hasattr(field, 'is_indicator') and field.is_indicator:
                is_number_field = _is_numeric_type(getattr(field, 'type', None))
            elif hasattr(field, 'is_question') and field.is_question:
                is_number_field = _is_numeric_type(getattr(field, 'type', None))

            if is_number_field:
                if getattr(field, 'is_indicator', False):
                    try:
                        cfg = getattr(field, 'config', None)
                        dv_raw = None
                        if isinstance(cfg, dict):
                            dv_raw = cfg.get('default_value')
                        dv_raw = str(dv_raw).strip() if dv_raw is not None else ''

                        if dv_raw:
                            if ('[' in dv_raw) and (not resolved_variables) and template_version:
                                try:
                                    resolved_variables = VariableResolutionService.resolve_variables(
                                        template_version,
                                        assignment_entity_status
                                    )
                                except Exception as e:
                                    current_app.logger.debug("resolve_variables for default_value failed: %s", e)
                                    resolved_variables = resolved_variables or {}

                            dv_resolved = dv_raw
                            if '[' in dv_raw:
                                dv_resolved = VariableResolutionService.replace_variables_in_text(
                                    dv_raw,
                                    _resolved_vars_for_field(field, dv_raw),
                                    variable_configs
                                )
                            dv_resolved_str = str(dv_resolved).strip()
                            dv_resolved_str = dv_resolved_str.replace(',', '')

                            num_value = float(dv_resolved_str)
                            if num_value.is_integer():
                                num_value = int(num_value)

                            allowed_opts = []
                            try:
                                allowed_opts = list(getattr(field, 'allowed_disaggregation_options', []) or [])
                            except Exception as e:
                                current_app.logger.debug("allowed_disaggregation_options failed: %s", e)
                                allowed_opts = []

                            if allowed_opts and len(allowed_opts) > 1:
                                if 'total' not in allowed_opts:
                                    continue
                                if getattr(field, 'indirect_reach', False):
                                    existing_data_processed[field_key] = {'mode': 'total', 'values': {'direct': num_value}}
                                else:
                                    existing_data_processed[field_key] = {'mode': 'total', 'values': {'total': num_value}}
                            else:
                                existing_data_processed[field_key] = num_value

                            existing_data_processed[f'{field_key}_is_prefilled'] = True
                            continue
                    except Exception as e:
                        current_app.logger.debug("Default value parsing failed: %s", e)

                if resolved_variables:
                    label_text = getattr(field, 'label', '') or ''
                    desc_text = getattr(field, 'definition', '') or getattr(field, 'description', '') or ''
                    combined_text = f"{label_text} {desc_text}"

                    variable_pattern = r'\[(\w+)\]'
                    matches = re.findall(variable_pattern, combined_text)

                    if matches:
                        for var_name in matches:
                            if var_name in resolved_variables:
                                var_value = resolved_variables[var_name]
                                if var_value is not None:
                                    try:
                                        num_value = float(var_value)
                                        existing_data_processed[field_key] = num_value

                                        existing_data_processed[f'{field_key}_is_prefilled'] = True
                                        if template_version and template_version.variables:
                                            var_config = template_version.variables.get(var_name, {})
                                            if var_config.get('is_readonly', False):
                                                existing_data_processed[f'{field_key}_is_readonly'] = True

                                        break
                                    except (ValueError, TypeError):
                                        continue

    repeat_data_entries = RepeatGroupData.query.join(
        RepeatGroupInstance,
        RepeatGroupData.repeat_instance_id == RepeatGroupInstance.id
    ).filter(
        RepeatGroupInstance.assignment_entity_status_id == assignment_entity_status.id
    ).all()

    repeat_instances = RepeatGroupInstance.query.filter_by(
        assignment_entity_status_id=assignment_entity_status.id,
        is_hidden=False
    ).all()

    repeat_instance_ids = [instance.id for instance in repeat_instances]
    all_repeat_data_entries = {}
    if repeat_instance_ids:
        repeat_entries = RepeatGroupData.query.filter(
            RepeatGroupData.repeat_instance_id.in_(repeat_instance_ids)
        ).all()
        for entry in repeat_entries:
            if entry.repeat_instance_id not in all_repeat_data_entries:
                all_repeat_data_entries[entry.repeat_instance_id] = []
            all_repeat_data_entries[entry.repeat_instance_id].append(entry)

    repeat_groups_data = {}
    for repeat_instance in repeat_instances:
        section_id = repeat_instance.section_id
        instance_number = repeat_instance.instance_number

        if section_id not in repeat_groups_data:
            repeat_groups_data[section_id] = {}

        if instance_number not in repeat_groups_data[section_id]:
            repeat_groups_data[section_id][instance_number] = {
                'id': repeat_instance.id,
                'label': repeat_instance.instance_label or '',
                'hidden': repeat_instance.is_hidden,
                'data': {}
            }

        repeat_data_entries = all_repeat_data_entries.get(repeat_instance.id, [])

        for repeat_data_entry in repeat_data_entries:
            if repeat_data_entry.form_item_id:
                field_key = str(repeat_data_entry.form_item_id)
            else:
                continue

            if repeat_data_entry.disagg_data:
                actual_value = repeat_data_entry.disagg_data
                data_not_available = repeat_data_entry.data_not_available
                not_applicable = repeat_data_entry.not_applicable
                display_value = actual_value
            else:
                actual_value = repeat_data_entry.value
                data_not_available = repeat_data_entry.data_not_available
                not_applicable = repeat_data_entry.not_applicable
                display_value = actual_value

            field_data = {
                'value': display_value,
                'data_not_available': data_not_available,
                'not_applicable': not_applicable
            }

            repeat_groups_data[section_id][instance_number]['data'][field_key] = field_data

    for section in all_sections:
        if section.section_type == 'repeat':
            section_id = section.id

            has_instance_1 = section_id in repeat_groups_data and 1 in repeat_groups_data[section_id]

            if not has_instance_1:
                instance_1_data = {}
                for field in section.fields_ordered:
                    if hasattr(field, 'indicator_bank_id'):
                        field_key = str(field.id)
                        original_key = f"field_value[{field.id}]"
                        if original_key in existing_data_processed:
                            original_value = existing_data_processed[original_key]
                            if isinstance(original_value, dict) and 'mode' in original_value and 'values' in original_value:
                                instance_1_data[field_key] = json.dumps(original_value)
                            else:
                                instance_1_data[field_key] = original_value
                    elif hasattr(field, 'question_type'):
                        field_key = str(field.id)
                        original_key = f"field_value[{field.id}]"
                        if original_key in existing_data_processed:
                            original_value = existing_data_processed[original_key]
                            instance_1_data[field_key] = original_value

                if instance_1_data:
                    if section_id not in repeat_groups_data:
                        repeat_groups_data[section_id] = {}

                    repeat_groups_data[section_id][1] = {
                        'id': None,
                        'label': '',
                        'hidden': False,
                        'data': instance_1_data
                    }

    existing_data_processed['repeat_groups_data'] = repeat_groups_data

    submitted_docs = (
        SubmittedDocument.query.filter_by(assignment_entity_status_id=assignment_entity_status.id)
        .order_by(SubmittedDocument.uploaded_at.desc())
        .all()
    )

    existing_submitted_documents_dict = {}
    for doc in submitted_docs:
        if not doc.form_item_id:
            continue
        key = f'field_value[{doc.form_item_id}]'
        if key not in existing_submitted_documents_dict:
            existing_submitted_documents_dict[key] = doc
        else:
            current = existing_submitted_documents_dict[key]
            if isinstance(current, list):
                current.append(doc)
            else:
                existing_submitted_documents_dict[key] = [current, doc]

    entity_repo_document_ids = merge_carryover_into_submitted_documents_dict(
        existing_submitted_documents_dict, assignment_entity_status, all_sections
    )

    section_statuses = calculate_section_completion_status(
        all_sections, existing_data_processed, existing_submitted_documents_dict
    )

    if request.method == "POST":
        is_ajax = is_json_request()

        if not can_edit:
             entity_name = EntityService.get_entity_display_name(assignment_entity_status.entity_type, assignment_entity_status.entity_id)
             flash(_("This assignment for %(entity)s is in '%(status)s' status and cannot be edited by you at this time.", entity=entity_name, status=assignment_entity_status.status), "warning")
             return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=assignment_entity_status.id))

        if csrf_form.validate_on_submit():
            action = request.form.get('action')

            try:
                submission_result = FormDataService.process_form_submission(
                    assignment_entity_status, all_sections, csrf_form
                )
                if not submission_result['success']:
                    for error in submission_result['validation_errors']:
                        flash(error, "danger")
                    if is_ajax:
                        msg = '; '.join(submission_result['validation_errors'])
                        return json_bad_request(msg, success=False)
                    else:
                        redirect_url = url_for("forms.view_edit_form", form_type="assignment", form_id=assignment_entity_status.id)
                        return redirect(redirect_url)

                field_changes_tracker = submission_result['field_changes']

                def parse_field_value(value, data_not_available=None, not_applicable=None):
                    """Parse field value to extract meaningful information for display."""
                    if data_not_available:
                        return "Data not available"
                    if not_applicable:
                        return "Not applicable"

                    if value is None:
                        return "N/A"

                    if isinstance(value, dict):
                        if 'mode' in value and 'values' in value:
                            mode = value.get('mode', '')
                            values = value.get('values', {})
                            if mode == 'total' and 'total' in values:
                                return f"Total: {values['total']}"
                            elif mode == 'disaggregated' and values:
                                items = list(values.items())[:3]
                                result = ", ".join([f"{k}: {v}" for k, v in items])
                                if len(values) > 3:
                                    result += f" (+{len(values) - 3} more)"
                                return result
                            else:
                                return str(values)
                        elif 'values' in value:
                            return str(value['values'])
                        else:
                            if 'direct' in value and len(value) == 1:
                                direct_value = value['direct']
                                if isinstance(direct_value, dict):
                                    parts = []
                                    for age_group, count in direct_value.items():
                                        if count and count != 0:
                                            parts.append(f"{age_group}: {count}")
                                    return ", ".join(parts) if parts else "0"
                                else:
                                    return str(direct_value)
                            elif 'total' in value and len(value) == 1:
                                total_value = value['total']
                                if isinstance(total_value, dict):
                                    parts = []
                                    for age_group, count in total_value.items():
                                        if count and count != 0:
                                            parts.append(f"{age_group}: {count}")
                                    return ", ".join(parts) if parts else "0"
                                else:
                                    return str(total_value)
                            elif value.get('_matrix_change') or any(
                                    isinstance(k, str) and '_' in k and not k.startswith('_')
                                    for k in value.keys()):
                                if not value.get('_matrix_change'):
                                    value = dict(value)
                                    value['_matrix_change'] = True
                                return value
                            else:
                                return str(value)
                    elif isinstance(value, str):
                        return value[:100] + "..." if len(value) > 100 else value
                    else:
                        return str(value)

                meaningful_changes = []

                for change in field_changes_tracker:
                    old_data_not_available = change.get('old_data_not_available', False)
                    new_data_not_available = change.get('new_data_not_available', False)
                    old_not_applicable = change.get('old_not_applicable', False)
                    new_not_applicable = change.get('new_not_applicable', False)

                    old_value_parsed = parse_field_value(change.get('old_value'), old_data_not_available, old_not_applicable)
                    new_value_parsed = parse_field_value(change.get('new_value'), new_data_not_available, new_not_applicable)

                    if old_value_parsed == new_value_parsed:
                        continue

                    if old_value_parsed == 'N/A':
                        change_type = 'added'
                        display_old_value = None
                        display_new_value = new_value_parsed
                    elif new_value_parsed == 'N/A':
                        change_type = 'removed'
                        display_old_value = old_value_parsed
                        display_new_value = None
                    else:
                        change_type = 'updated'
                        display_old_value = old_value_parsed
                        display_new_value = new_value_parsed

                    formatted_change = {
                        'type': change_type,
                        'form_item_id': change.get('form_item_id'),
                        'field_id_kind': change.get('field_id_kind'),
                        'field_name': change.get('field_name', f"Field {change.get('form_item_id', 'Unknown')}"),
                        'old_value': display_old_value,
                        'new_value': display_new_value
                    }
                    meaningful_changes.append(formatted_change)

                if meaningful_changes:
                    try:
                        if len(meaningful_changes) == 1:
                            ch = meaningful_changes[0]
                            summary_key = 'activity.form_data_updated.single'
                            summary_params = {
                                'field': ch['field_name'],
                                'field_id': ch.get('form_item_id'),
                                'field_id_kind': ch.get('field_id_kind'),
                                'old': ch.get('old_value') or '',
                                'new': ch.get('new_value') or '',
                                'change_type': ch.get('type') or 'updated',
                                'template': assignment_entity_status.assigned_form.template.name
                                            if assignment_entity_status
                                            and assignment_entity_status.assigned_form
                                            and assignment_entity_status.assigned_form.template
                                            else None,
                            }
                            activity_description = "Field updated"
                        else:
                            changes_list = []
                            change_type_counts = {'added': 0, 'updated': 0, 'removed': 0}
                            for ch in meaningful_changes:
                                ct = (ch.get('type') or 'updated')
                                change_type_counts[ct] = change_type_counts.get(ct, 0) + 1
                                changes_list.append({
                                    'field': ch.get('field_name', 'Field'),
                                    'field_id': ch.get('form_item_id'),
                                    'field_id_kind': ch.get('field_id_kind'),
                                    'old': ch.get('old_value') or '',
                                    'new': ch.get('new_value') or '',
                                    'change_type': ct
                                })

                            total_changes = len(meaningful_changes)
                            if change_type_counts['added'] == total_changes:
                                activity_description = "Fields added"
                                dominant_type = 'added'
                            elif change_type_counts['removed'] == total_changes:
                                activity_description = "Fields removed"
                                dominant_type = 'removed'
                            elif change_type_counts['updated'] == total_changes:
                                activity_description = "Fields updated"
                                dominant_type = 'updated'
                            else:
                                activity_description = "Fields modified"
                                dominant_type = 'updated'

                            summary_key = 'activity.form_data_updated.multiple'
                            summary_params = {
                                'count': total_changes,
                                'template': assignment_entity_status.assigned_form.template.name,
                                'change_type': dominant_type,
                                'changes': changes_list
                            }

                        log_entity_activity(
                            assignment_entity_status.entity_type,
                            assignment_entity_status.entity_id,
                            'data_update',
                            activity_description,
                            summary_key=summary_key,
                            summary_params=summary_params,
                            related_object_type='form_data',
                            related_object_id=assignment_entity_status.id,
                            assignment_id=assignment_entity_status.id,
                            user_id=current_user.id
                        )
                    except Exception as e:
                        current_app.logger.error(f"Error logging grouped activity: {e}", exc_info=True)

                if submission_result.get('submitted'):
                    notify_assignment_submitted(assignment_entity_status)
                    flash("Assignment submitted successfully!", "success")

                    is_ajax = is_json_request()
                    if is_ajax:
                        return json_ok(
                            message="Assignment submitted successfully!",
                            redirect_url=url_for("main.dashboard")
                        )
                    else:
                        return redirect(url_for("main.dashboard"))
                else:
                    is_ajax = is_json_request()
                    if is_ajax:
                        uploaded_documents = [
                            {
                                'form_item_id': ch['form_item_id'],
                                'submitted_document_id': ch['submitted_document_id'],
                                'filename': ch.get('new_value'),
                            }
                            for ch in (submission_result.get('field_changes') or [])
                            if ch.get('submitted_document_id')
                        ]
                        return json_ok(
                            message="Progress saved successfully.",
                            uploaded_documents=uploaded_documents,
                        )
                    else:
                        flash("Progress saved successfully.", "success")
                        redirect_url = url_for("forms.view_edit_form", form_type="assignment", form_id=assignment_entity_status.id)
                        return redirect(redirect_url)

            except Exception as e:
                request_transaction_rollback()
                error_message = GENERIC_ERROR_MESSAGE
                current_app.logger.exception("Error during data save/submit for AssignmentEntityStatus %s: %s", aes_id, e)

                if is_ajax:
                    return json_server_error(error_message, success=False)
                else:
                    flash(error_message, "danger")
                    return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=assignment_entity_status.id))
        else:
            current_app.logger.error("CSRF validation failed")
            current_app.logger.error(f"CSRF form errors: {csrf_form.errors}")
            error_message = "Form submission failed due to a security issue or validation errors. Please try again."
            current_app.logger.error(f"CSRF or other form validation failed for ACS {aes_id}. Errors: {csrf_form.errors}")

            if is_ajax:
                return json_bad_request(error_message, success=False)
            else:
                flash(error_message, "danger")
                return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=assignment_entity_status.id))

    template_structure = form_template

    section_statuses = calculate_section_completion_status(all_sections, existing_data_processed, existing_submitted_documents_dict)

    for section in all_sections:
        if section.section_type == 'dynamic_indicators':
            section.data_entry_display_filters_config = getattr(section, 'data_entry_display_filters_list', [])

    current_locale = (get_locale() or 'en')
    current_locale_short = current_locale.split('_', 1)[0] if isinstance(current_locale, str) else 'en'

    try:
        for page in (published_pages or []):
            page.display_name = get_localized_page_name(page)
    except Exception as e:
        current_app.logger.debug("Page localization failed; continuing without localized page names: %s", e, exc_info=True)

    page_ids_processed = set()
    for section in (all_sections or []):
        if getattr(section, 'page', None) and getattr(section.page, 'id', None) not in page_ids_processed:
            try:
                section.page.display_name = get_localized_page_name(section.page)
            except Exception as e:
                current_app.logger.debug(
                    "Page localization failed for page_id=%s; continuing: %s",
                    getattr(section.page, "id", None),
                    e,
                    exc_info=True,
                )
            page_ids_processed.add(section.page.id)

    for section in (all_sections or []):
        translated_name = None
        nt = getattr(section, 'name_translations', None)
        if isinstance(nt, dict) and nt:
            for k in (current_locale_short, 'en'):
                val = nt.get(k)
                if val and str(val).strip():
                    translated_name = str(val).strip()
                    break
        section.display_name = translated_name if translated_name else getattr(section, 'name', '')

    from app.services.authorization_service import AuthorizationService
    documents_library_url = None
    if getattr(current_user, "is_authenticated", False):
        if AuthorizationService.is_system_manager(current_user) or AuthorizationService.has_rbac_permission(
            current_user, "admin.documents.manage"
        ):
            documents_library_url = url_for("content_management.manage_documents")
        elif AuthorizationService.has_rbac_permission(current_user, "assignment.documents.upload"):
            documents_library_url = url_for("main.documents_submit")

    return render_template(
        "forms/entry_form/entry_form.html",
        template_structure=template_structure,
        sections=db_sections,
        all_sections=all_sections,
        published_pages=published_pages,
        assignment_status=assignment_entity_status,
        assignment=assignment,
        existing_data=existing_data_processed,
        existing_submitted_documents=existing_submitted_documents_dict,
        entity_repo_document_ids=entity_repo_document_ids,
        documents_library_url=documents_library_url,
        can_edit=can_edit,
        csrf_form=csrf_form,
        sex_categories=SEX_CATEGORIES,
        form_type="assignment",
        section_statuses=section_statuses,
        available_indicators_by_section=available_indicators_by_section,
        slugify_age_group=slugify_age_group,
        config=Config,
        QuestionType=QuestionType,
        isinstance=isinstance,
        json=json,
        hasattr=hasattr,
        get_localized_country_name=get_localized_country_name,
        form_action=url_for("forms.view_edit_form", form_type="assignment", form_id=assignment_entity_status.id),
        translation_key=get_translation_key(),
        get_localized_indicator_definition=get_localized_indicator_definition,
        get_localized_indicator_type=get_localized_indicator_type,
        get_localized_indicator_unit=get_localized_indicator_unit,
        get_localized_template_name=get_localized_template_name,
        plugin_manager=current_app.plugin_manager if hasattr(current_app, 'plugin_manager') else None,
        form_integration=current_app.form_integration if hasattr(current_app, 'form_integration') else None,
        template_id=form_template.id,
        assignment_entity_status_id=assignment_entity_status.id,
        template_variables=variable_configs if 'variable_configs' in locals() else {}
    )


def _preview_template_impl(template_id):
    """Preview a form template using existing form processing logic."""
    from app.services.authorization_service import AuthorizationService
    from app.routes.admin.shared import check_template_access
    if not AuthorizationService.has_rbac_permission(current_user, "admin.templates.view"):
        flash(_("Access denied."), "warning")
        return redirect(url_for("main.dashboard"))
    if not check_template_access(template_id, current_user.id):
        flash(_("Access denied."), "warning")
        return redirect(url_for("main.dashboard"))

    from app.models import FormTemplate
    from app.models.forms import FormTemplateVersion, FormPage

    template = FormTemplate.query.get_or_404(template_id)

    requested_version_id = request.args.get('version_id', type=int)
    selected_version = None
    if requested_version_id:
        selected_version = FormTemplateVersion.query.filter_by(id=requested_version_id, template_id=template.id).first()
    if not selected_version and template.published_version_id:
        selected_version = FormTemplateVersion.query.get(template.published_version_id)
    if not selected_version:
        selected_version = FormTemplateVersion.query.filter_by(template_id=template.id).order_by(FormTemplateVersion.created_at.desc()).first()

    selected_version_id = selected_version.id if selected_version else None

    from app.models.assignments import AssignedForm, AssignmentEntityStatus
    from app.models.enums import EntityType
    from app import db

    requested_period_name = (request.args.get("period_name") or "").strip()
    selected_period_name = requested_period_name

    requested_view_as = (request.args.get("view_as") or "").strip()
    selected_entity_type = None
    selected_entity_id = None
    if requested_view_as and ":" in requested_view_as:
        try:
            et, eid_str = requested_view_as.split(":", 1)
            eid = int(eid_str)
            allowed_types = {e.value for e in EntityType}
            if et in allowed_types and eid > 0:
                selected_entity_type = et
                selected_entity_id = eid
        except Exception as e:
            current_app.logger.debug("view_as parse failed: %s", e)
            selected_entity_type = None
            selected_entity_id = None

    preview_view_as_options = [{"value": "", "label": _("Preview placeholders")}]
    try:
        option_rows = []

        if AuthorizationService.is_admin(current_user) or AuthorizationService.is_system_manager(current_user):
            for et, model_cls in EntityService.ENTITY_MODEL_MAP.items():
                try:
                    entities = EntityService.get_all_entities_by_type(et, filter_active=True)
                    for ent in entities:
                        if not ent or not getattr(ent, "id", None):
                            continue
                        option_rows.append((et, int(ent.id)))
                except Exception as e:
                    current_app.logger.debug("EntityService.get_all_entities failed: %s", e)
                    continue
        else:
            from app.models.core import UserEntityPermission
            perms = UserEntityPermission.query.filter_by(user_id=current_user.id).all()
            for p in perms:
                if not p:
                    continue
                et = getattr(p, "entity_type", None)
                eid = getattr(p, "entity_id", None)
                if et and eid:
                    option_rows.append((et, int(eid)))

        seen = set()
        enriched = []
        for et, eid in option_rows:
            key = (et, eid)
            if key in seen:
                continue
            seen.add(key)
            try:
                name = EntityService.get_localized_entity_name(et, eid, include_hierarchy=True)
                label = f"{EntityService.get_entity_type_label(et)}: {name}"
            except Exception as e:
                current_app.logger.debug("get_localized_entity_name failed: %s", e)
                label = f"{et}:{eid}"
            enriched.append((label, et, eid))

        for label, et, eid in sorted(enriched, key=lambda x: (x[0] or "").lower()):
            preview_view_as_options.append({"value": f"{et}:{eid}", "label": label})
    except Exception as e:
        current_app.logger.debug("preview_view_as_options failed: %s", e)

    preview_period_name_options = []
    try:
        period_rows = (
            db.session.query(AssignedForm.period_name)
            .filter(AssignedForm.template_id == template.id)
            .distinct()
            .order_by(AssignedForm.period_name.desc())
            .all()
        )
        preview_period_name_options = [r[0] for r in period_rows if r and r[0]]
    except Exception as e:
        current_app.logger.debug("preview_period_name_options failed: %s", e)
        preview_period_name_options = []

    all_sections = FormSection.query.filter_by(template_id=template.id, version_id=selected_version_id).order_by(FormSection.order).all()

    class MockACS:
        def __init__(self, template, period_name, entity_type=None, entity_id=None):
            self.id = 0
            self.status = 'Preview Mode'
            self.due_date = None
            self.entity_type = entity_type
            self.entity_id = entity_id

            mock_assignment = type('MockAssignment', (), {})()
            mock_assignment.template = template
            mock_assignment.period_name = period_name or 'Preview Period'
            self.assigned_form = mock_assignment

            mock_country = type('MockCountry', (), {})()
            mock_country.name = 'Preview Country'
            mock_country.iso3 = 'PRE'
            mock_country.name_translations = {
                'fr': 'Pays de Prévisualisation',
                'es': 'País de Vista Previa',
                'ar': 'بلد المعاينة',
                'ru': 'Страна Предварительного Просмотра',
                'zh': '预览国家',
                'hi': 'पूर्वावलोकन देश'
            }
            self._placeholder_country = mock_country

        @property
        def entity(self):
            """Entity object for non-country entity previews."""
            if not self.entity_type or not self.entity_id:
                return None
            try:
                return EntityService.get_entity(self.entity_type, int(self.entity_id))
            except Exception as e:
                current_app.logger.debug("MockACS.entity get_entity failed: %s", e)
                return None

        @property
        def country(self):
            """Country for the preview context (used heavily by templates and JS)."""
            if not self.entity_type or not self.entity_id:
                return self._placeholder_country
            try:
                c = EntityService.get_country_for_entity(self.entity_type, int(self.entity_id))
                return c or self._placeholder_country
            except Exception as e:
                current_app.logger.debug("MockACS.country failed: %s", e)
                return self._placeholder_country

        @property
        def country_id(self):
            """Compatibility helper for legacy code that expects country_id."""
            try:
                if self.entity_type == EntityType.country.value and self.entity_id:
                    return int(self.entity_id)
                c = self.country
                return int(c.id) if c and hasattr(c, "id") else None
            except Exception as e:
                current_app.logger.debug("MockACS.country_id failed: %s", e)
                return None

    mock_acs = MockACS(
        template,
        selected_period_name,
        entity_type=selected_entity_type,
        entity_id=selected_entity_id,
    )

    for section in all_sections:
        section.fields_ordered = get_form_items_for_section(section, mock_acs)

    published_pages = FormPage.query.filter_by(template_id=template.id, version_id=selected_version_id).order_by(FormPage.order).all()
    for page in published_pages:
        page.display_name = get_localized_page_name(page)

    page_ids_processed = set()
    for section in all_sections:
        if section.page and section.page.id not in page_ids_processed:
            section.page.display_name = get_localized_page_name(section.page)
            page_ids_processed.add(section.page.id)

    for section in all_sections:
        if section.name_translations:
            current_locale = get_locale()
            translated_name = section.name_translations.get(current_locale)

            if translated_name and translated_name.strip():
                section.display_name = translated_name
            else:
                section.display_name = section.name
        else:
            section.display_name = section.name

    for section in all_sections:
        if section.section_type == 'dynamic_indicators':
            section.data_entry_display_filters_config = getattr(section, 'data_entry_display_filters_list', [])

    available_indicators_by_section = TemplatePreparationService._prepare_available_indicators(all_sections)

    csrf_form = FlaskForm()

    variable_configs = {}
    try:
        from app.services.variable_resolution_service import VariableResolutionService
        if selected_version:
            variable_configs = getattr(selected_version, "variables", None) or {}
            resolved_variables = VariableResolutionService.resolve_variables(
                selected_version,
                mock_acs
            )

            for section in all_sections:
                if hasattr(section, 'display_name') and section.display_name and resolved_variables:
                    try:
                        section._display_name_resolved = VariableResolutionService.replace_variables_in_text(
                            section.display_name,
                            resolved_variables,
                            variable_configs
                        )
                    except Exception as e:
                        current_app.logger.debug("section display_name replace failed: %s", e)

                for field in getattr(section, 'fields_ordered', []) or []:
                    if not field or not hasattr(field, 'id'):
                        continue

                    if hasattr(field, 'label') and field.label and resolved_variables:
                        try:
                            field._display_label = VariableResolutionService.replace_variables_in_text(
                                field.label,
                                resolved_variables,
                                variable_configs
                            )
                        except Exception as e:
                            current_app.logger.debug("field label replace failed: %s", e)

                    if hasattr(field, 'display_label') and field.display_label and resolved_variables:
                        try:
                            field._display_label_resolved = VariableResolutionService.replace_variables_in_text(
                                field.display_label,
                                resolved_variables,
                                variable_configs
                            )
                        except Exception as e:
                            current_app.logger.debug("field display_label replace failed: %s", e)

                    if hasattr(field, 'definition') and field.definition and resolved_variables:
                        try:
                            field._display_definition = VariableResolutionService.replace_variables_in_text(
                                field.definition,
                                resolved_variables,
                                variable_configs
                            )
                        except Exception as e:
                            current_app.logger.debug("field definition replace failed: %s", e)

                    if hasattr(field, 'description') and field.description and resolved_variables:
                        try:
                            field._display_description = VariableResolutionService.replace_variables_in_text(
                                field.description,
                                resolved_variables,
                                variable_configs
                            )
                        except Exception as e:
                            current_app.logger.debug("field description replace failed: %s", e)

                    if hasattr(field, 'item_type') and field.item_type == 'matrix' and hasattr(field, 'config') and field.config:
                        try:
                            matrix_config = field.config.get('matrix_config') if isinstance(field.config, dict) and 'matrix_config' in field.config else field.config
                            if isinstance(matrix_config, dict):
                                row_mode = matrix_config.get('row_mode', 'manual')
                                if row_mode == 'manual' or not row_mode:
                                    rows = matrix_config.get('rows', [])
                                    if rows and isinstance(rows, list):
                                        field._display_matrix_rows = [
                                            VariableResolutionService.replace_variables_in_text(r, resolved_variables, variable_configs)
                                            if isinstance(r, str) else r
                                            for r in rows
                                        ]
                        except Exception as e:
                            current_app.logger.debug("matrix row variable replace failed: %s", e)
    except Exception as e:
        current_app.logger.debug("Preview variable resolution failed: %s", e)
        variable_configs = {}

    section_statuses = {section.name: 'Not Started' for section in all_sections}

    return render_template("forms/entry_form/entry_form.html",
                         title=_("Preview: %(name)s", name=get_localized_template_name(template)),
                         assignment=mock_acs.assigned_form,
                         assignment_status=mock_acs,
                         template_structure=template,
                         all_sections=all_sections,
                         form=csrf_form,
                         published_pages=published_pages,
                         existing_data={},
                         existing_submitted_documents={},
                         entity_repo_document_ids=frozenset(),
                         section_statuses=section_statuses,
                         slugify_age_group=slugify_age_group,
                         config=Config,
                         can_edit=True,
                         QuestionType=QuestionType,
                         isinstance=isinstance,
                         json=json,
                         hasattr=hasattr,
                         available_indicators_by_section=available_indicators_by_section,
                         get_localized_country_name=get_localized_country_name,
                         get_localized_indicator_definition=get_localized_indicator_definition,
                         get_localized_indicator_type=get_localized_indicator_type,
                         get_localized_indicator_unit=get_localized_indicator_unit,
                         get_localized_template_name=get_localized_template_name,
                         is_preview_mode=True,
                         template_id=template.id,
                         template_variables=variable_configs,
                         preview_version_id=selected_version_id,
                         preview_selected_view_as=(f"{selected_entity_type}:{selected_entity_id}" if selected_entity_type and selected_entity_id else ""),
                         preview_selected_period_name=selected_period_name,
                         preview_view_as_options=preview_view_as_options,
                         preview_period_name_options=preview_period_name_options,
                         plugin_manager=current_app.plugin_manager if hasattr(current_app, 'plugin_manager') else None,
                         form_integration=current_app.form_integration if hasattr(current_app, 'form_integration') else None)
