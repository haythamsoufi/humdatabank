"""Form item management routes."""

from contextlib import suppress
from flask import request, flash, redirect, url_for, current_app
from flask_login import current_user
from flask_babel import _

from . import bp
from app import db
from app.models import (FormTemplate, FormSection, FormItem, IndicatorBank,
    FormTemplateVersion)
from app.forms.form_builder import IndicatorForm, QuestionForm, DocumentFieldForm
from app.routes.admin.shared import permission_required
from app.utils.request_utils import is_json_request, get_request_data
from app.utils.user_analytics import log_admin_action
from app.utils.transactions import request_transaction_rollback
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import (json_forbidden, json_bad_request, json_ok,
    json_server_error, json_form_errors)
from app.services.item_duplication_service import ItemDuplicationService
from .helpers import (_create_form_item, _update_indicator_fields, _update_question_fields,
    _update_document_field_fields, _update_matrix_fields, _update_plugin_fields,
    _update_item_config, _update_version_timestamp, _ensure_template_access_or_redirect,
    is_conditions_meaningful)
import json


@bp.route("/templates/<int:template_id>/sections/<int:section_id>/items/new", methods=["POST"])
@permission_required('admin.templates.edit')
def new_section_item(template_id, section_id):
    """Unified route for creating new form items (indicators, questions, document fields, plugin items)"""
    is_ajax = is_json_request()
    data = get_request_data()
    template = FormTemplate.query.get_or_404(template_id)
    version_ctx = data.get('version_id')
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        if is_ajax:
            try:
                loc = getattr(access_redirect, 'location', None) or None
            except Exception as e:
                current_app.logger.debug("getattr access_redirect.location failed: %s", e)
                loc = None
            return json_forbidden('Access denied', success=False, redirect_url=loc)
        return access_redirect
    section = FormSection.query.get_or_404(section_id)
    if section.template_id != template.id:
        flash("Section does not belong to the specified template.", "danger")
        target_version_id = version_ctx or section.version_id
        redirect_url = url_for("form_builder.edit_template", template_id=template.id, version_id=target_version_id)
        if is_ajax:
            return json_bad_request("Section does not belong to the specified template.", success=False, errors={'section_id': ["Invalid section for template"]}, redirect_url=redirect_url)
        return redirect(redirect_url)

    item_type = data.get('item_type')
    if not item_type:
        flash("Item type is required", "danger")
        target_version_id = data.get('version_id') or section.version_id
        redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
        if is_ajax:
            return json_bad_request("Item type is required", success=False, errors={'item_type': ["Item type is required"]}, redirect_url=redirect_url)
        return redirect(redirect_url)

    try:
        form_item = _create_form_item(template, section, data, item_type)
        if form_item:
            _update_version_timestamp(form_item.version_id, current_user.id)
            db.session.flush()
            log_admin_action(
                action_type='form_item_create',
                description=f"Created new {item_type} in template '{template.name}'",
                target_type='form_item',
                target_id=form_item.id,
                target_description=f"Template ID: {template_id}, Item ID: {form_item.id}",
                risk_level='low'
            )

            flash_message = f"{item_type.title()} added successfully."
            flash(flash_message, "success")
            target_version_id = data.get('version_id') or section.version_id
            redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
            if is_ajax:
                return json_ok(message=flash_message, redirect_url=redirect_url)
        else:
            flash_message = f'Failed to create {item_type}. Please check your input.'
            flash(flash_message, "danger")
            target_version_id = data.get('version_id') or section.version_id
            redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
            if is_ajax:
                return json_bad_request(flash_message, success=False, errors={'__all__': [flash_message]}, redirect_url=redirect_url)

    except Exception as e:
        request_transaction_rollback()
        flash_message = GENERIC_ERROR_MESSAGE
        flash(flash_message, "danger")
        current_app.logger.error(f"Error adding {item_type} to section {section_id}: {e}", exc_info=True)
        target_version_id = data.get('version_id') or section.version_id
        redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
        if is_ajax:
            return json_server_error(flash_message, success=False, errors={'database': [flash_message]}, redirect_url=redirect_url)

    target_version_id = data.get('version_id') or section.version_id
    redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
    if is_ajax:
        return json_bad_request('Failed to create item', success=False, errors={'__all__': ['Failed to create item']}, redirect_url=redirect_url)
    return redirect(redirect_url)


@bp.route("/items/edit/<int:item_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def edit_item(item_id):
    """Unified route for editing form items (indicators, questions, document fields)"""
    is_ajax = is_json_request()
    data = get_request_data()
    form_item = FormItem.query.get_or_404(item_id)
    template_id = form_item.template_id
    version_ctx = data.get('version_id') or form_item.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        if is_ajax:
            try:
                loc = getattr(access_redirect, 'location', None) or None
            except Exception as e:
                current_app.logger.debug("getattr access_redirect.location failed: %s", e)
                loc = None
            return json_forbidden('Access denied', success=False, redirect_url=loc)
        return access_redirect

    if form_item.archived:
        msg = "Cannot edit archived items. Please unarchive the item first."
        if is_ajax:
            redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=version_ctx)
            return json_bad_request(msg, success=False, errors={'__all__': [msg]}, redirect_url=redirect_url)
        flash(msg, "warning")
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version_ctx))

    try:
        current_app.logger.debug(
            "edit_item called: item_id=%s item_type=%s keys=%s",
            item_id,
            getattr(form_item, 'item_type', None),
            list(data.keys())
        )
    except Exception as e:
        current_app.logger.debug("edit_item: debug log failed: %s", e)

    submitted_item_type = (data.get('item_type') or '').strip() or form_item.item_type
    if submitted_item_type not in ('indicator', 'question', 'document_field', 'matrix') and not (submitted_item_type and submitted_item_type.startswith('plugin_')):
        submitted_item_type = form_item.item_type

    if submitted_item_type == 'indicator':
        from app.forms.form_builder import IndicatorForm
        form_class = IndicatorForm
        all_ib_objects = IndicatorBank.query.order_by(IndicatorBank.name).all()
        indicator_bank_choices_with_unit = []
        for ib in all_ib_objects:
            if ib and hasattr(ib, 'id') and hasattr(ib, 'name') and hasattr(ib, 'type'):
                indicator_bank_choices_with_unit.append({
                    'value': ib.id,
                    'label': f"{ib.name} (Type: {ib.type}, Unit: {ib.unit or 'N/A'})",
                    'unit': ib.unit if ib.unit else ''
                })
        form_kwargs = {'indicator_bank_choices_with_unit': indicator_bank_choices_with_unit}
    elif submitted_item_type == 'question':
        from app.forms.form_builder import QuestionForm
        form_class = QuestionForm
        form_kwargs = {}
    elif submitted_item_type == 'document_field':
        from app.forms.form_builder import DocumentFieldForm
        form_class = DocumentFieldForm
        form_kwargs = {}
    elif submitted_item_type == 'matrix':
        from app.forms.form_builder import MatrixForm
        form_class = MatrixForm
        form_kwargs = {}
    elif submitted_item_type and submitted_item_type.startswith('plugin_'):
        from app.forms.form_builder import PluginItemForm
        form_class = PluginItemForm
        form_kwargs = {}
    else:
        flash(f"Unknown item type: {submitted_item_type or form_item.item_type}", "danger")
        target_version_id = data.get('version_id') or form_item.version_id
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

    form = form_class(obj=form_item, **form_kwargs)

    template_sections = FormSection.query.filter_by(template_id=template_id, version_id=form_item.version_id).order_by(FormSection.order).all()
    form.section_id.choices = [(s.id, s.name) for s in template_sections]

    if 'section_id' in data and data['section_id']:
        try:
            form.section_id.data = int(data['section_id'])
        except (ValueError, TypeError):
            form.section_id.data = form_item.section_id
    else:
        form.section_id.data = form_item.section_id
    if 'order' in data:
        form.order.data = float(data['order']) if data['order'] else None
    # Checkboxes: when unchecked, browsers omit the key entirely.
    # JSON payloads always include all keys, so the same "key in data" check works.
    if hasattr(form, 'is_required'):
        form.is_required.data = ('is_required' in data) and (data.get('is_required') in ['true', 'on', '1', True])
        if 'is_required' in data:
            current_app.logger.debug(f"FLASH_DEBUG: Processing is_required: {data['is_required']} -> {form.is_required.data}")
    if 'layout_column_width' in data:
        form.layout_column_width.data = str(data['layout_column_width']) if data['layout_column_width'] else '12'
    if hasattr(form, 'layout_break_after'):
        form.layout_break_after.data = ('layout_break_after' in data) and (data.get('layout_break_after') in ['true', 'on', '1', True])
        if 'layout_break_after' in data:
            current_app.logger.debug(f"FLASH_DEBUG: Processing layout_break_after: {data['layout_break_after']} -> {form.layout_break_after.data}")
    if hasattr(form, 'allow_data_not_available'):
        form.allow_data_not_available.data = ('allow_data_not_available' in data) and (data.get('allow_data_not_available') in ['true', 'on', '1', True])
    if hasattr(form, 'allow_not_applicable'):
        form.allow_not_applicable.data = ('allow_not_applicable' in data) and (data.get('allow_not_applicable') in ['true', 'on', '1', True])
    if hasattr(form, 'indirect_reach'):
        form.indirect_reach.data = ('indirect_reach' in data) and (data.get('indirect_reach') in ['true', 'on', '1', True])

    if 'relevance_condition' in data and hasattr(form, 'relevance_condition'):
        form.relevance_condition.data = data['relevance_condition'] if data['relevance_condition'] != 'null' else None
    if 'validation_condition' in data and hasattr(form, 'validation_condition'):
        form.validation_condition.data = data['validation_condition'] if data['validation_condition'] != 'null' else None
    if 'validation_message' in data and hasattr(form, 'validation_message'):
        form.validation_message.data = data['validation_message'] if data['validation_message'] else None

    if submitted_item_type == 'indicator':
        if 'label' in data and hasattr(form, 'label'):
            form.label.data = data['label']
        if 'definition' in data and hasattr(form, 'definition'):
            form.definition.data = data['definition'] or None
        if 'indicator_bank_id' in data:
            form.indicator_bank_id.data = int(data['indicator_bank_id']) if data['indicator_bank_id'] else None
        if 'allowed_disaggregation_options' in data:
            disagg_options = data.getlist('allowed_disaggregation_options')
            form.allowed_disaggregation_options.data = disagg_options if disagg_options else ["total"]
        if 'age_groups_config' in data:
            form.age_groups_config.data = data['age_groups_config'] if data['age_groups_config'] else None
    elif submitted_item_type == 'question':
        if 'question_type' in data and data['question_type']:
            form.question_type.data = data['question_type']
    elif submitted_item_type == 'matrix':
        if 'label' in data:
            form.label.data = data['label']
        if 'description' in data:
            try:
                descriptions = data.getlist('description')
                last_non_empty_desc = next((v for v in reversed(descriptions) if str(v).strip()), '') if descriptions else ''
                form.description.data = last_non_empty_desc
            except Exception as e:
                current_app.logger.debug("description getlist fallback failed: %s", e)
                form.description.data = data.get('description', '')
        if 'config' in data:
            form.matrix_config.data = data['config']
        elif 'matrix_config' in data:
            form.matrix_config.data = data['matrix_config']

    if form.validate_on_submit():
        current_app.logger.info(f"Edit {form_item.item_type.title()} Form validated. Processed form data: {form.data}")

        try:
            form_item.section_id = form.section_id.data
            form_item.order = form.order.data if form.order.data is not None else form_item.order

            if submitted_item_type != form_item.item_type:
                form_item.item_type = submitted_item_type
                if submitted_item_type == 'indicator':
                    form_item.definition = None
                    form_item.options_json = None
                    form_item.options_translations = None
                    form_item.lookup_list_id = None
                    form_item.list_display_column = None
                    form_item.list_filters_json = None
                elif submitted_item_type == 'question':
                    form_item.indicator_bank_id = None
                    form_item.type = None
                    form_item.unit = None
                    form_item.label_translations = None
                    form_item.definition_translations = None

            if submitted_item_type == 'indicator':
                _update_indicator_fields(form_item, form, data)
            elif submitted_item_type == 'question':
                _update_question_fields(form_item, form, data)
            elif submitted_item_type == 'document_field':
                _update_document_field_fields(form_item, form, data)
            elif submitted_item_type == 'matrix':
                _update_matrix_fields(form_item, form, data)
            elif submitted_item_type and submitted_item_type.startswith('plugin_'):
                _update_plugin_fields(form_item, form, data)

            _update_item_config(form_item, form, data)

            rel_json = data.get('relevance_condition')
            val_json = data.get('validation_condition')
            val_msg = data.get('validation_message')

            form_item.relevance_condition = rel_json if is_conditions_meaningful(rel_json) else None
            form_item.validation_condition = val_json if is_conditions_meaningful(val_json) else None
            form_item.validation_message = val_msg if val_msg else None

            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(form_item, 'config')

            _update_version_timestamp(form_item.version_id, current_user.id)
            db.session.flush()

            item_label = form_item.label or f"{form_item.item_type.title()} {item_id}"

            log_admin_action(
                action_type='form_item_update',
                description=f"Updated form item '{item_label}' in template '{form_item.template.name}'",
                target_type='form_item',
                target_id=item_id,
                target_description=f"Template ID: {template_id}, Item ID: {item_id}",
                risk_level='low'
            )

            flash_message = f"{form_item.item_type.title()} '{item_label}' updated successfully."
            target_version_id = data.get('version_id') or form_item.version_id
            redirect_url = url_for("form_builder.edit_template", template_id=form_item.template_id, version_id=target_version_id)
            if is_ajax:
                return json_ok(message=flash_message, redirect_url=redirect_url)
            flash(flash_message, "success")
            return redirect(redirect_url)

        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error(f"Error during DB commit for editing {form_item.item_type} {item_id}: {e}", exc_info=True)
            if is_ajax:
                return json_server_error(GENERIC_ERROR_MESSAGE, success=False, errors={'database': [GENERIC_ERROR_MESSAGE]})
            flash(GENERIC_ERROR_MESSAGE, "danger")
            target_version_id = data.get('version_id') or form_item.version_id
            return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))
    else:
        current_app.logger.error(f"Form validation failed for Edit {form_item.item_type.title()} (ID: {item_id}). Errors: {form.errors}")
        if is_ajax:
            return json_form_errors(form, 'Validation failed')
        flash(_("Validation failed. Please check the form."), "danger")
        target_version_id = data.get('version_id') or form_item.version_id
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))


@bp.route("/items/delete/<int:item_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def delete_item(item_id):
    """Unified route for deleting form items (indicators, questions, document fields)"""
    is_ajax = is_json_request()
    data = get_request_data()
    from app.models.forms import FormData, RepeatGroupData
    from app.models import SubmittedDocument

    form_item = FormItem.query.get_or_404(item_id)
    template_id = form_item.template_id
    version_ctx = data.get('version_id') or form_item.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        if is_ajax:
            try:
                loc = getattr(access_redirect, 'location', None) or None
            except Exception as e:
                current_app.logger.debug("getattr access_redirect.location failed: %s", e)
                loc = None
            return json_forbidden('Access denied', success=False, redirect_url=loc)
        return access_redirect

    # Check if user wants to delete data, keep data and delete item, or cancel
    delete_data_param = data.get('delete_data', 'true')
    delete_data = delete_data_param.lower() == 'true'
    keep_data_delete_item = delete_data_param.lower() == 'false-keep-data'

    try:
        item_type = form_item.item_type.title()
        item_label = form_item.label or f"{item_type} {item_id}"
        template_name = form_item.template.name
        version_id = form_item.version_id

        # Count existing data entries
        data_count = 0
        data_count += FormData.query.filter_by(form_item_id=form_item.id).count()
        data_count += RepeatGroupData.query.filter_by(form_item_id=form_item.id).count()
        if form_item.item_type == 'document_field':
            data_count += SubmittedDocument.query.filter_by(form_item_id=form_item.id).count()

        # If user wants to keep data but not delete item (cancel), do nothing
        if data_count > 0 and not delete_data and not keep_data_delete_item:
            # This shouldn't happen as the frontend should handle cancel, but just in case
            target_version_id = data.get('version_id') or form_item.version_id
            redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
            if is_ajax:
                return json_ok(message='Cancelled', redirect_url=redirect_url)
            return redirect(redirect_url)

        # If delete_data is true and data exists, delete it first
        if delete_data and data_count > 0:
            FormData.query.filter_by(form_item_id=form_item.id).delete(synchronize_session=False)
            RepeatGroupData.query.filter_by(form_item_id=form_item.id).delete(synchronize_session=False)
            if form_item.item_type == 'document_field':
                SubmittedDocument.query.filter_by(form_item_id=form_item.id).delete(synchronize_session=False)
            db.session.flush()
        # If keep_data_delete_item is true, archive the item instead of deleting it
        # This preserves the FK relationship so data can remain
        if keep_data_delete_item:
            form_item.archived = True
            db.session.add(form_item)
            _update_version_timestamp(version_id)
            db.session.flush()
        else:
            # Actually delete the item
            db.session.delete(form_item)
            _update_version_timestamp(version_id)
            db.session.flush()

        # Log admin action for audit trail
        if keep_data_delete_item:
            action_desc = f"Archived {item_type.lower()} '{item_label}' from template '{template_name}' (data preserved)"
        else:
            action_desc = f"Deleted {item_type.lower()} '{item_label}' from template '{template_name}'" + (f" (and {data_count} data entries)" if delete_data and data_count > 0 else "")

        log_admin_action(
            action_type='form_item_delete',
            description=action_desc,
            target_type='form_item',
            target_id=item_id,
            target_description=f"Template ID: {template_id}, Item ID: {item_id}",
            risk_level='medium'
        )

        if delete_data and data_count > 0:
            flash_message = f"{item_type} '{item_label}' and {data_count} associated data entries deleted successfully."
        elif keep_data_delete_item and data_count > 0:
            flash_message = f"{item_type} '{item_label}' archived (removed from template). {data_count} data entries preserved."
        else:
            flash_message = f"{item_type} '{item_label}' deleted successfully."
        flash(flash_message, "success")
    except Exception as e:
        request_transaction_rollback()
        flash_message = f"Error deleting {form_item.item_type}."
        flash(flash_message, "danger")
        current_app.logger.error(f"Error deleting {form_item.item_type} {item_id}: {e}", exc_info=True)
        target_version_id = data.get('version_id') or form_item.version_id
        redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
        if is_ajax:
            return json_server_error(flash_message, success=False, errors={'database': [flash_message]}, redirect_url=redirect_url)

    # Preserve version context after deleting an item
    target_version_id = data.get('version_id') or form_item.version_id
    redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
    if is_ajax:
        return json_ok(message=flash_message, redirect_url=redirect_url)
    return redirect(redirect_url)


@bp.route("/items/duplicate/<int:item_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def duplicate_item(item_id):
    """Duplicate a form item including all its properties."""
    is_ajax = is_json_request()
    data = get_request_data()
    form_item = FormItem.query.get_or_404(item_id)
    template_id = form_item.template_id
    version_id = form_item.version_id
    version_ctx = data.get('version_id') or version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        if is_ajax:
            try:
                loc = getattr(access_redirect, 'location', None) or None
            except Exception as e:
                current_app.logger.debug("getattr access_redirect.location failed: %s", e)
                loc = None
            return json_forbidden('Access denied', success=False, redirect_url=loc)
        return access_redirect

    try:
        # Use the item duplication service
        new_item = ItemDuplicationService.duplicate_item(
            item_id=item_id,
            user_id=current_user.id
        )

        # Update version timestamp
        _update_version_timestamp(version_id, current_user.id)
        db.session.flush()

        # Log admin action for audit trail
        try:
            item_type = form_item.item_type.title()
            item_label = form_item.label or f"{item_type} {item_id}"
            log_admin_action(
                action_type='form_item_duplicate',
                description=f"Duplicated {item_type.lower()} '{item_label}' in template '{form_item.template.name}'",
                target_type='form_item',
                target_id=new_item.id,
                target_description=f"Source Item ID: {item_id}, New Item ID: {new_item.id}, Template ID: {template_id}, Version ID: {version_id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging item duplication: {log_error}")

        item_type = form_item.item_type.title()
        item_label = form_item.label or f"{item_type} {item_id}"
        flash(f"{item_type} '{item_label}' duplicated as '{new_item.label}'.", "success")
        flash_message = f"{item_type} '{item_label}' duplicated as '{new_item.label}'."

    except ValueError as e:
        request_transaction_rollback()
        flash_message = "An error occurred. Please try again."
        flash(flash_message, "danger")
        current_app.logger.error(f"Error duplicating item {item_id}: {e}", exc_info=True)
        if is_ajax:
            target_version_id = data.get('version_id') or version_id
            redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
            return json_bad_request(flash_message, success=False, errors={'__all__': [flash_message]}, redirect_url=redirect_url)
    except Exception as e:
        request_transaction_rollback()
        flash_message = "An error occurred. Please try again."
        flash(flash_message, "danger")
        current_app.logger.error(f"Error duplicating item {item_id}: {e}", exc_info=True)
        if is_ajax:
            target_version_id = data.get('version_id') or version_id
            redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
            return json_server_error(flash_message, success=False, errors={'database': [flash_message]}, redirect_url=redirect_url)

    # Preserve version context after duplication
    target_version_id = data.get('version_id') or version_id
    redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
    if is_ajax:
        return json_ok(message=flash_message or 'Item duplicated', redirect_url=redirect_url)
    return redirect(redirect_url)


@bp.route("/items/unarchive/<int:item_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def unarchive_item(item_id):
    """Unarchive a form item so it appears in the form again. Also unarchives parent section if needed."""
    data = get_request_data()
    form_item = FormItem.query.get_or_404(item_id)
    template_id = form_item.template_id
    version_id = form_item.version_id
    version_ctx = data.get('version_id') or version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        return access_redirect

    try:
        if not form_item.archived:
            flash("Item is not archived.", "warning")
            target_version_id = data.get('version_id') or version_id
            return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

        item_type = form_item.item_type.title()
        item_label = form_item.label or f"{item_type} {item_id}"
        template_name = form_item.template.name

        # Unarchive the item
        form_item.archived = False
        db.session.add(form_item)

        # Check if the item's section is archived and unarchive it if so
        section = FormSection.query.get(form_item.section_id)
        section_unarchived = False
        if section and section.archived:
            section.archived = False
            db.session.add(section)
            section_unarchived = True

            # Log section unarchive action
            log_admin_action(
                action_type='form_section_unarchive',
                description=f"Auto-unarchived section '{section.name}' in template '{template_name}' (item unarchived)",
                target_type='form_section',
                target_id=section.id,
                target_description=f"Template ID: {template_id}, Section ID: {section.id}",
                risk_level='low'
            )

            # Also check if there's a parent section and unarchive it if needed
            if section.parent_section_id:
                parent_section = FormSection.query.get(section.parent_section_id)
                if parent_section and parent_section.archived:
                    parent_section.archived = False
                    db.session.add(parent_section)

                    # Log parent section unarchive action
                    log_admin_action(
                        action_type='form_section_unarchive',
                        description=f"Auto-unarchived parent section '{parent_section.name}' in template '{template_name}' (child section unarchived)",
                        target_type='form_section',
                        target_id=parent_section.id,
                        target_description=f"Template ID: {template_id}, Section ID: {parent_section.id}",
                        risk_level='low'
                    )

        _update_version_timestamp(version_id)
        db.session.flush()

        # Log admin action for audit trail
        log_admin_action(
            action_type='form_item_unarchive',
            description=f"Unarchived {item_type.lower()} '{item_label}' in template '{template_name}'",
            target_type='form_item',
            target_id=item_id,
            target_description=f"Template ID: {template_id}, Item ID: {item_id}",
            risk_level='low'
        )

        # Prepare flash message
        flash_msg = f"{item_type} '{item_label}' has been unarchived and is now visible in the form."
        if section_unarchived:
            flash_msg += f" The section '{section.name}' has also been unarchived."
        flash(flash_msg, "success")
    except Exception as e:
        request_transaction_rollback()
        flash_message = GENERIC_ERROR_MESSAGE
        flash(flash_message, "danger")
        current_app.logger.error(f"Error unarchiving {form_item.item_type} {item_id}: {e}", exc_info=True)

    target_version_id = data.get('version_id') or version_id
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))
