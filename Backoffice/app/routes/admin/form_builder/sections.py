"""Section management routes."""

from flask import request, flash, redirect, url_for, current_app
from flask_login import current_user
from flask_babel import _

from . import bp
from app import db
from app.models import FormTemplate, FormSection, FormItem, FormPage, FormTemplateVersion
from app.forms.form_builder import FormSectionForm
from app.routes.admin.shared import permission_required
from app.utils.request_utils import is_json_request, get_request_data
from app.utils.user_analytics import log_admin_action
from app.utils.transactions import request_transaction_rollback
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_ok, json_server_error
from app.services.section_duplication_service import SectionDuplicationService
from config.config import Config
from .helpers import (_update_version_timestamp, _ensure_template_access_or_redirect,
    _get_descendant_section_ids, _delete_or_archive_one_section)
import json


@bp.route("/templates/<int:template_id>/sections/new", methods=["POST"])
@permission_required('admin.templates.edit')
def new_template_section(template_id):
    data = get_request_data()
    template = FormTemplate.query.get_or_404(template_id)
    version_ref = data.get('version_id') or request.args.get('version_id')
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ref)
    if access_redirect:
        return access_redirect
    form = FormSectionForm(data, prefix="section")

    target_version_id = data.get('version_id') or request.args.get('version_id')
    version = None
    if target_version_id:
        try:
            version = FormTemplateVersion.query.filter_by(id=int(target_version_id), template_id=template.id).first()
        except Exception as e:
            current_app.logger.debug("target_version_id parse failed: %s", e)
            version = None
    if not version and template.published_version_id:
        version = FormTemplateVersion.query.get(template.published_version_id)
    if not version:
        version = FormTemplateVersion.query.filter_by(template_id=template.id).order_by(FormTemplateVersion.created_at.desc()).first()

    # Initialize page choices if template is paginated (check version)
    if version and version.is_paginated:
        pages_for_version = FormPage.query.filter_by(template_id=template.id, version_id=version.id).all()
        form.page_id.choices = [(p.id, p.name) for p in pages_for_version]
    else:
        form.page_id.choices = [(None, 'No Pages')]

    if form.validate_on_submit():
        try:
            # Parent section is now explicit (no more decimal-based inference)
            parent_section_id_raw = data.get('parent_section_id')
            parent_section_id = int(parent_section_id_raw) if parent_section_id_raw else None
            parent_section = None
            if parent_section_id:
                parent_section = FormSection.query.filter_by(
                    template_id=template.id,
                    version_id=version.id,
                    id=parent_section_id
                ).first()
                if not parent_section:
                    flash("Invalid parent section selected.", "danger")
                    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version.id))
                # Prevent deeper nesting: only allow top-level sections to be parents
                if parent_section.parent_section_id is not None:
                    flash("Only top-level sections can be selected as a parent section.", "danger")
                    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version.id))

            # Whole-number ordering only (allow 0; only auto-fill when value is missing/empty)
            order_val = form.order.data
            order_missing = order_val is None or (isinstance(order_val, str) and str(order_val).strip() == '')
            if order_missing:
                if parent_section_id:
                    last_sibling = FormSection.query.filter_by(
                        template_id=template.id,
                        version_id=version.id,
                        parent_section_id=parent_section_id
                    ).order_by(FormSection.order.desc()).first()
                    order_val = (int(last_sibling.order) + 1) if last_sibling and last_sibling.order is not None else 1
                else:
                    last_top = FormSection.query.filter_by(
                        template_id=template.id,
                        version_id=version.id,
                        parent_section_id=None
                    ).order_by(FormSection.order.desc()).first()
                    order_val = (int(last_top.order) + 1) if last_top and last_top.order is not None else 1
            else:
                try:
                    order_val = int(float(order_val))
                except Exception as e:
                    current_app.logger.debug("order_val parse failed: %s", e)
                    order_val = 1

            # Get dynamic indicators fields from form object
            section_type = (form.section_type.data.lower() if form.section_type.data else 'standard')
            max_dynamic_indicators = form.max_dynamic_indicators.data
            add_indicator_note = form.add_indicator_note.data

            # Get max_entries for repeat groups
            max_entries_raw = data.get('max_entries')
            max_entries = int(max_entries_raw) if max_entries_raw else None

            current_app.logger.debug(f"Creating section with type: {section_type}, max_dynamic: {max_dynamic_indicators}, max_entries: {max_entries}")
            current_app.logger.debug(f"New section - form relevance_condition data: '{form.relevance_condition.data}'")
            current_app.logger.debug(f"New section - form data keys: {list(data.keys())}")

            # Page for paginated templates: subsections always inherit parent's page
            if parent_section_id and parent_section:
                page_id = parent_section.page_id  # subsection: always use parent's page (or None)
            elif version and version.is_paginated and form.page_id.data:
                page_id = form.page_id.data
            else:
                page_id = None

            new_section = FormSection(
                name=form.name.data,
                order=order_val,
                template_id=template_id,
                version_id=version.id,
                parent_section_id=parent_section_id,
                section_type=section_type,
                max_dynamic_indicators=max_dynamic_indicators,
                add_indicator_note=add_indicator_note,
                page_id=page_id,
                relevance_condition=form.relevance_condition.data
            )

            # Set max_entries in config for repeat groups
            if section_type == 'repeat' and max_entries is not None:
                new_section.set_max_entries(max_entries)
            elif section_type == 'repeat':
                # Initialize config as empty dict if not set
                if new_section.config is None:
                    new_section.config = {}

            # Handle name translations - ISO codes only
            if hasattr(form, 'name_translations') and form.name_translations.data:
                try:
                    name_translations = json.loads(form.name_translations.data)
                    supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
                    filtered_translations = {}
                    if isinstance(name_translations, dict):
                        for k, v in name_translations.items():
                            if not (isinstance(k, str) and isinstance(v, str) and v.strip()):
                                continue
                            code = k.strip().lower().split('_', 1)[0]
                            if code in supported_codes:
                                filtered_translations[code] = v.strip()
                    new_section.name_translations = filtered_translations if filtered_translations else None
                except (json.JSONDecodeError, TypeError) as e:
                    current_app.logger.error(f"Error parsing section name translations: {e}")

            db.session.add(new_section)
            _update_version_timestamp(version.id, current_user.id)
            db.session.flush()

            # Log admin action for audit trail
            try:
                log_admin_action(
                    action_type='form_section_create',
                    description=f"Created section '{new_section.name}' in template '{template.name}' (Type: {section_type})",
                    target_type='form_section',
                    target_id=new_section.id,
                    target_description=f"Template ID: {template_id}, Section ID: {new_section.id}, Version ID: {version.id}",
                    risk_level='low'
                )
            except Exception as log_error:
                current_app.logger.error(f"Error logging section creation: {log_error}")

            flash(f"Section '{new_section.name}' added to template.", "success")

        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")
            current_app.logger.error(f"Error adding section to template {template_id}: {e}", exc_info=True)

    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {field}: {error}", "danger")

    # Preserve version context after adding a section
    version_id = version.id if version is not None else data.get('version_id')
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version_id))

@bp.route("/sections/edit/<int:section_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def edit_template_section(section_id):
    is_ajax = is_json_request()
    data = get_request_data()
    section = FormSection.query.get_or_404(section_id)
    template_id = section.template_id
    version_ctx = data.get('version_id') or section.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        return access_redirect

    try:
        section.name = data.get("section-name", section.name)

        parent_raw = data.get("parent_section_id")
        if parent_raw is not None:
            parent_raw = str(parent_raw).strip()
            if parent_raw == '':
                section.parent_section_id = None
            else:
                try:
                    new_parent_id = int(parent_raw)
                except Exception as e:
                    current_app.logger.debug("parent_section_id parse failed: %s", e)
                    flash("Invalid parent section selected.", "warning")
                    new_parent_id = None

                if new_parent_id:
                    if new_parent_id == section.id:
                        flash("A section cannot be its own parent.", "danger")
                        new_parent_id = None
                    else:
                        parent_section = FormSection.query.filter_by(
                            template_id=section.template_id,
                            version_id=section.version_id,
                            id=new_parent_id
                        ).first()
                        if not parent_section:
                            flash("Invalid parent section selected.", "danger")
                            new_parent_id = None
                        elif parent_section.parent_section_id is not None:
                            flash("Only top-level sections can be selected as a parent section.", "danger")
                            new_parent_id = None
                        else:
                            direct_child = FormSection.query.filter_by(parent_section_id=section.id, id=new_parent_id).first()
                            if direct_child:
                                flash("Invalid parent selection (would create a cycle).", "danger")
                                new_parent_id = None

                section.parent_section_id = new_parent_id

        order_str = data.get("section-order")
        if order_str:
            try:
                section.order = int(float(order_str))
            except ValueError:
                flash(f"Invalid order value: {order_str}", "warning")

        version = section.version if section.version else (section.template.published_version if section.template.published_version else None)
        if version and version.is_paginated:
            if section.parent_section_id:
                parent = FormSection.query.get(section.parent_section_id)
                section.page_id = parent.page_id if parent else None
            else:
                page_id = data.get("section-page_id")
                section.page_id = int(page_id) if page_id and page_id != 'None' else None

        name_translations_str = data.get("name_translations")
        if name_translations_str:
            try:
                name_translations = json.loads(name_translations_str)
                supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
                filtered_translations = {}
                if isinstance(name_translations, dict):
                    for k, v in name_translations.items():
                        if not (isinstance(k, str) and isinstance(v, str) and v.strip()):
                            continue
                        code = k.strip().lower().split('_', 1)[0]
                        if code in supported_codes:
                            filtered_translations[code] = v.strip()
                section.name_translations = filtered_translations if filtered_translations else None
            except (json.JSONDecodeError, TypeError) as e:
                current_app.logger.error(f"Error parsing section name translations: {e}")

        section_type = data.get("section-section_type", "standard")
        section.section_type = section_type.lower() if section_type else 'standard'

        if section_type.lower() == 'repeat':
            max_entries = data.get('max_entries', type=int) if hasattr(data, 'get') else data.get('max_entries')
            if max_entries is not None and not isinstance(max_entries, int):
                try:
                    max_entries = int(max_entries)
                except (ValueError, TypeError):
                    max_entries = None
            section.set_max_entries(max_entries)
        else:
            if section.config:
                section.config.pop('max_entries', None)

        relevance_condition = data.get("relevance_condition")
        current_app.logger.debug(f"Edit section - form data keys: {list(data.keys())}")
        current_app.logger.debug(f"Edit section - relevance_condition value: '{relevance_condition}'")

        if relevance_condition and str(relevance_condition).strip():
            try:
                json.loads(relevance_condition)
                section.relevance_condition = relevance_condition
                current_app.logger.debug(f"Edit section - set relevance_condition to: {relevance_condition}")
            except (json.JSONDecodeError, TypeError) as e:
                current_app.logger.error(f"Error parsing section relevance condition: {e}")
                flash("Invalid relevance condition format. Skip logic not saved.", "warning")
                section.relevance_condition = None
        else:
            section.relevance_condition = None
            current_app.logger.debug("Edit section - cleared relevance_condition (empty or None)")

        _update_version_timestamp(section.version_id)
        db.session.flush()

        try:
            log_admin_action(
                action_type='form_section_update',
                description=f"Updated section '{section.name}' in template '{section.template.name}'",
                target_type='form_section',
                target_id=section_id,
                target_description=f"Template ID: {template_id}, Section ID: {section_id}, Version ID: {section.version_id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging section update: {log_error}")

        flash(f"Section '{section.name}' updated successfully.", "success")

        target_version_id = data.get('version_id') or section.version_id
        redirect_url = url_for("form_builder.edit_template", template_id=section.template_id, version_id=target_version_id)
        if is_ajax:
            return json_ok(message=f"Section '{section.name}' updated successfully.", redirect_url=redirect_url)
        return redirect(redirect_url)

    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error updating section {section_id}: {e}", exc_info=True)

    target_version_id = data.get('version_id') or section.version_id
    redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
    if is_ajax:
        return json_server_error("An error occurred. Please try again.")
    return redirect(redirect_url)


@bp.route("/sections/delete/<int:section_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def delete_template_section(section_id):
    data = get_request_data()
    from app.models.forms import FormData, RepeatGroupData, RepeatGroupInstance, DynamicIndicatorData
    from app.models.form_items import FormItem

    section = FormSection.query.get_or_404(section_id)
    template_id = section.template_id
    version_ctx = data.get('version_id') or section.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        return access_redirect

    # Check if user wants to delete data, keep data and delete section, or cancel
    delete_data_param = data.get('delete_data', 'true')
    delete_data = delete_data_param.lower() == 'true'
    keep_data_delete_section = delete_data_param.lower() == 'false-keep-data'

    # Cascade: delete or archive child sections first (user confirmed via frontend warning)
    descendant_ids = _get_descendant_section_ids(section.id)
    for desc_id in descendant_ids:
        desc_section = FormSection.query.get(desc_id)
        if desc_section:
            _delete_or_archive_one_section(desc_section, delete_data, keep_data_delete_section)

    try:
        version_id = section.version_id

        # Capture section and template names BEFORE any deletion/archival operations
        # to avoid SQLAlchemy session issues when accessing lazy-loaded relationships
        section_label = section.name
        template = FormTemplate.query.get(template_id)
        template_name = template.name if template else "Unknown Template"

        # Count existing data entries for this section
        data_count = 0
        # Count data from items in this section (include archived items for data counting)
        section_item_ids = [item.id for item in FormItem.query.filter_by(section_id=section.id).all()]
        if section_item_ids:
            data_count += FormData.query.filter(FormData.form_item_id.in_(section_item_ids)).count()
            data_count += RepeatGroupData.query.filter(RepeatGroupData.form_item_id.in_(section_item_ids)).count()
        # Count repeat group instances
        data_count += RepeatGroupInstance.query.filter_by(section_id=section.id).count()
        # Count dynamic indicator data
        data_count += DynamicIndicatorData.query.filter_by(section_id=section.id).count()

        # If user wants to keep data but not delete section (cancel), do nothing
        if data_count > 0 and not delete_data and not keep_data_delete_section:
            # This shouldn't happen as the frontend should handle cancel, but just in case
            target_version_id = data.get('version_id') or section.version_id
            return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

        # If delete_data is true and data exists, delete it first
        if delete_data and data_count > 0:
            # Delete data from items in this section
            if section_item_ids:
                FormData.query.filter(FormData.form_item_id.in_(section_item_ids)).delete(synchronize_session=False)
                RepeatGroupData.query.filter(RepeatGroupData.form_item_id.in_(section_item_ids)).delete(synchronize_session=False)
            # Delete repeat group instances (which will cascade to their data)
            RepeatGroupInstance.query.filter_by(section_id=section.id).delete(synchronize_session=False)
            # Delete dynamic indicator data
            DynamicIndicatorData.query.filter_by(section_id=section.id).delete(synchronize_session=False)
            db.session.flush()

        # If keep_data_delete_section is true, archive the section and its items instead of deleting
        # This preserves the FK relationships so data can remain
        if keep_data_delete_section:
            # Archive the section
            section.archived = True
            db.session.add(section)

            # Archive all items in this section
            section_items = FormItem.query.filter_by(section_id=section.id).all()
            for item in section_items:
                item.archived = True
                db.session.add(item)

            _update_version_timestamp(version_id)
            db.session.flush()

            # Log admin action for audit trail
            log_admin_action(
                action_type='form_section_delete',
                description=f"Archived section '{section_label}' from template '{template_name}' (data preserved)",
                target_type='form_section',
                target_id=section_id,
                target_description=f"Template ID: {template_id}, Section ID: {section_id}",
                risk_level='medium'
            )
            child_note = f" and {len(descendant_ids)} child section(s)" if descendant_ids else ""
            flash(f"Section '{section_label}'{child_note} archived (removed from template). {data_count} data entries preserved.", "success")
        else:
            # Actually delete the section (items will cascade delete due to relationship cascade)
            db.session.delete(section)
            _update_version_timestamp(version_id)

            try:
                db.session.flush()
            except Exception as fk_error:
                request_transaction_rollback()
                flash(f"Error deleting section '{section_label}'.", "danger")
                current_app.logger.error(f"Error deleting section {section_id}: {fk_error}", exc_info=True)
                target_version_id = data.get('version_id') or section.version_id
                return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

            # Log admin action for audit trail
            log_admin_action(
                action_type='form_section_delete',
                description=f"Deleted section '{section_label}' from template '{template_name}'" + (f" (and {data_count} data entries)" if delete_data and data_count > 0 else ""),
                target_type='form_section',
                target_id=section_id,
                target_description=f"Template ID: {template_id}, Section ID: {section_id}",
                risk_level='medium'
            )

            child_note = f" and {len(descendant_ids)} child section(s)" if descendant_ids else ""
            if delete_data and data_count > 0:
                flash(f"Section '{section_label}'{child_note} and {data_count} associated data entries deleted.", "success")
            else:
                flash(f"Section '{section_label}'{child_note} deleted.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error deleting section {section_id}: {e}", exc_info=True)

    # Preserve version context after deletion
    target_version_id = data.get('version_id') or section.version_id
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

@bp.route("/sections/duplicate/<int:section_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def duplicate_template_section(section_id):
    """Duplicate a form section including all its items and nested subsections."""
    data = get_request_data()
    section = FormSection.query.get_or_404(section_id)
    template_id = section.template_id
    version_id = section.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_id)
    if access_redirect:
        return access_redirect

    try:
        # Use the section duplication service
        new_section, section_id_map = SectionDuplicationService.duplicate_section(
            section_id=section_id,
            user_id=current_user.id
        )

        # Update version timestamp
        _update_version_timestamp(version_id, current_user.id)
        db.session.flush()

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='form_section_duplicate',
                description=f"Duplicated section '{section.name}' in template '{section.template.name}'",
                target_type='form_section',
                target_id=new_section.id,
                target_description=f"Source Section ID: {section_id}, New Section ID: {new_section.id}, Template ID: {template_id}, Version ID: {version_id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging section duplication: {log_error}")

        flash(f"Section '{section.name}' duplicated as '{new_section.name}'.", "success")

    except ValueError as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error duplicating section {section_id}: {e}", exc_info=True)
    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error duplicating section {section_id}: {e}", exc_info=True)

    # Preserve version context after duplication
    target_version_id = data.get('version_id') or version_id
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

@bp.route("/sections/unarchive/<int:section_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def unarchive_section(section_id):
    """Unarchive a form section so it appears in the form again"""
    data = get_request_data()
    section = FormSection.query.get_or_404(section_id)
    template_id = section.template_id
    version_id = section.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_id)
    if access_redirect:
        return access_redirect

    try:
        if not section.archived:
            flash("Section is not archived.", "warning")
            target_version_id = data.get('version_id') or version_id
            return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

        section_label = section.name
        template_name = section.template.name

        # Unarchive the section
        section.archived = False
        db.session.add(section)

        # Unarchive all items in this section
        from app.models.form_items import FormItem
        section_items = FormItem.query.filter_by(section_id=section.id).all()
        for item in section_items:
            item.archived = False
            db.session.add(item)

        _update_version_timestamp(version_id)
        db.session.flush()

        # Log admin action for audit trail
        log_admin_action(
            action_type='form_section_unarchive',
            description=f"Unarchived section '{section_label}' in template '{template_name}'",
            target_type='form_section',
            target_id=section_id,
            target_description=f"Template ID: {template_id}, Section ID: {section_id}",
            risk_level='low'
        )

        flash(f"Section '{section.name}' has been unarchived and is now visible in the form.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash_message = GENERIC_ERROR_MESSAGE
        flash(flash_message, "danger")
        current_app.logger.error(f"Error unarchiving section {section_id}: {e}", exc_info=True)

    target_version_id = data.get('version_id') or version_id
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

@bp.route("/sections/configure-dynamic/<int:section_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def configure_dynamic_section(section_id):
    """Configure settings for a dynamic indicators section."""
    data = get_request_data()
    section = FormSection.query.get_or_404(section_id)
    template_id = section.template_id
    version_ctx = data.get('version_id') or section.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        return access_redirect

    # Verify this is actually a dynamic indicators section
    if section.section_type != 'dynamic_indicators':
        flash('This section is not a dynamic indicators section.', 'warning')
        target_version_id = data.get('version_id') or section.version_id
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

    is_ajax = is_json_request()

    current_app.logger.debug(f"Configuring dynamic section {section_id} (ajax={is_ajax})")
    current_app.logger.debug(f"Form data: {data}")

    try:
        # Update max_dynamic_indicators
        max_dynamic_indicators = data.get('max_dynamic_indicators')
        if max_dynamic_indicators and max_dynamic_indicators.strip():
            try:
                section.max_dynamic_indicators = int(max_dynamic_indicators)
            except ValueError:
                section.max_dynamic_indicators = None
        else:
            section.max_dynamic_indicators = None

        # Update add_indicator_note
        add_indicator_note = data.get('add_indicator_note')
        if add_indicator_note and add_indicator_note.strip():
            section.add_indicator_note = add_indicator_note.strip()
        else:
            section.add_indicator_note = None

        # Update data availability options
        section.allow_data_not_available = data.get('allow_data_not_available') == '1'
        section.allow_not_applicable = data.get('allow_not_applicable') == '1'

        # Update allowed disaggregation options
        allowed_disagg_options = data.getlist('allowed_disaggregation_options')
        # Always save the selected options, even if empty
        section.set_allowed_disaggregation_options(allowed_disagg_options)

        # Update data entry display filters
        data_entry_display_filters = data.getlist('data_entry_display_filters')
        section.set_data_entry_display_filters(data_entry_display_filters)

        # Update indicator filters
        # Process the dynamic filter data from the form
        filters = []

        # Get all filter field names from the form
        filter_fields = data.getlist(f'filter_field_{section_id}[]')

        for i, field in enumerate(filter_fields):
            if field:  # Only process if a field is selected
                # Get the corresponding values for this filter
                values_key = f'filter_values_{section_id}_{i}[]'
                values = data.getlist(values_key)

                if values:  # Only add filter if it has values
                    filter_obj = {
                        'field': field,
                        'values': values
                    }

                    # Check for "primary_only" flag for sector/subsector fields
                    if field in ['sector', 'subsector']:
                        primary_only_key = f'filter_primary_only_{section_id}_{i}'
                        primary_only = data.get(primary_only_key) == '1'
                        if primary_only:
                            filter_obj['primary_only'] = True

                    filters.append(filter_obj)

        # Store the filters in the section using the model's setter method
        section.set_indicator_filters(filters if filters else None)

        # Keep backward compatibility - also handle allowed_sectors if provided
        allowed_sectors_list = data.getlist('allowed_sectors')
        if allowed_sectors_list:
            section.allowed_sectors = json.dumps(allowed_sectors_list)
        else:
            section.allowed_sectors = None

        _update_version_timestamp(section.version_id)
        db.session.flush()

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='form_section_configure',
                description=f"Configured dynamic section '{section.name}' in template '{section.template.name}' (Max indicators: {section.max_dynamic_indicators})",
                target_type='form_section',
                target_id=section_id,
                target_description=f"Template ID: {template_id}, Section ID: {section_id}, Version ID: {section.version_id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging dynamic section configuration: {log_error}")

        # For XHR requests, do not store a server-side flash (it would appear later unexpectedly).
        if not is_ajax:
            flash(f"Dynamic section '{section.name}' configured successfully.", "success")
        else:
            return json_ok(
                section_id=section_id,
                template_id=template_id,
                version_id=data.get('version_id') or section.version_id,
                message=f"Dynamic section '{section.name}' saved.",
            )
    except Exception as e:
        request_transaction_rollback()
        if is_ajax:
            return json_server_error("An error occurred. Please try again.", success=False)
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error configuring dynamic section {section_id}: {e}", exc_info=True)

    # Preserve version context after configuring dynamic section
    target_version_id = data.get('version_id') or section.version_id
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))


@bp.route("/sections/configure-repeat/<int:section_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def configure_repeat_section(section_id):
    """Configure settings for a repeat group section."""
    data = get_request_data()
    section = FormSection.query.get_or_404(section_id)
    template_id = section.template_id
    version_ctx = data.get('version_id') or section.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        return access_redirect

    # Verify this is actually a repeat group section
    if section.section_type != 'repeat':
        flash('This section is not a repeat group section.', 'warning')
        target_version_id = data.get('version_id') or section.version_id
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

    current_app.logger.debug(f"Configuring repeat section {section_id}")
    current_app.logger.debug(f"Form data: {data}")

    try:
        # Update max_entries in config
        max_entries = data.get('max_entries')
        if max_entries and max_entries.strip():
            try:
                section.set_max_entries(int(max_entries))
            except ValueError:
                section.set_max_entries(None)
        else:
            section.set_max_entries(None)

        _update_version_timestamp(section.version_id)
        db.session.flush()

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='form_section_configure',
                description=f"Configured repeat section '{section.name}' in template '{section.template.name}' (Max entries: {section.max_entries})",
                target_type='form_section',
                target_id=section_id,
                target_description=f"Template ID: {template_id}, Section ID: {section_id}, Version ID: {section.version_id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging repeat section configuration: {log_error}")

        # Always set server-side flash message for consistency with other routes
        flash(f"Repeat section '{section.name}' configured successfully.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error configuring repeat section {section_id}: {e}", exc_info=True)

    # Preserve version context after configuring repeat section
    target_version_id = data.get('version_id') or section.version_id
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))
