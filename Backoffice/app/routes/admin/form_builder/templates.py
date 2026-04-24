"""Template CRUD and management routes."""

from contextlib import suppress
from flask import render_template, request, flash, redirect, url_for, current_app, session, send_file
from flask_login import current_user
from flask_babel import _
from flask_wtf import FlaskForm
from werkzeug.utils import secure_filename
from sqlalchemy import func, select, literal

from . import bp
from app import db
from app.models import (FormTemplate, FormSection, FormItem, FormPage, IndicatorBank,
    QuestionType, TemplateShare, User, FormTemplateVersion, AssignedForm)
from app.models.core import Country
from app.forms.form_builder import (FormTemplateForm, FormSectionForm, IndicatorForm, QuestionForm, DocumentFieldForm)
from app.routes.admin.shared import (admin_required, admin_permission_required, permission_required,
    system_manager_required, check_template_access)
from app.utils.request_utils import is_json_request, get_request_data
from app.services.security.api_authentication import get_user_allowed_template_ids
from app.services.user_analytics_service import log_admin_action
from app.services.template_excel_service import TemplateExcelService
from app.services.kobo_xls_import_service import KoboXlsImportService
from app.utils.error_handling import handle_view_exception, handle_json_view_exception
from app.utils.transactions import request_transaction_rollback
from app.utils.datetime_helpers import utcnow
from app.utils.advanced_validation import validate_upload_extension_and_mime
from app.utils.file_parsing import EXCEL_EXTENSIONS
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import json_forbidden, json_bad_request, json_not_found, json_ok, json_server_error
from config.config import Config
from .helpers import (_handle_template_sharing, _handle_template_pages, _populate_template_sharing,
    _build_template_data_for_js, _clone_template_structure_between_templates,
    _get_or_create_draft_version, _update_version_timestamp, _ensure_template_access_or_redirect)
from . import (_handle_version_translations, _handle_version_description_translations,
    _populate_version_translations, _populate_version_description_translations)
import json


@bp.route("/templates", methods=["GET"])
@permission_required('admin.templates.view')
def manage_templates():
    from app.utils.form_localization import get_localized_template_name, get_localized_indicator_type, get_localized_indicator_unit
    from flask_babel import gettext as _gettext, ngettext as _ngettext

    # System managers can see all templates regardless of ownership and sharing
    from app.services.authorization_service import AuthorizationService
    if AuthorizationService.is_system_manager(current_user):
        templates_query = FormTemplate.query.options(
            db.joinedload(FormTemplate.owned_by_user),
            db.joinedload(FormTemplate.shared_with).joinedload(TemplateShare.shared_with_user),
            db.joinedload(FormTemplate.published_version)
        )
    else:
        # Filter templates based on ownership and sharing permissions
        # Users can see templates they own or templates shared with them
        # Use efficient UNION query instead of loading all templates
        allowed_template_ids = get_user_allowed_template_ids(current_user.id)

        if not allowed_template_ids:
            # User has no access to any templates
            templates_query = FormTemplate.query.filter(literal(False))
        else:
            templates_query = FormTemplate.query.options(
                db.joinedload(FormTemplate.owned_by_user),
                db.joinedload(FormTemplate.shared_with).joinedload(TemplateShare.shared_with_user),
                db.joinedload(FormTemplate.published_version)
            ).filter(FormTemplate.id.in_(allowed_template_ids))

    templates = templates_query.all()
    # Sort by name (from published version) in Python since it's a property
    templates.sort(key=lambda t: t.name if t.name else "")

    # Compute counts of saved data referencing each template's item IDs to warn on delete
    from app.models.form_items import FormItem
    from app.models.forms import FormData, RepeatGroupData, DynamicIndicatorData, FormSection
    from sqlalchemy import func

    # FormData counts per template via join on FormItem
    formdata_counts_rows = (
        db.session.query(FormItem.template_id, func.count(FormData.id))
        .join(FormData, FormData.form_item_id == FormItem.id)
        .group_by(FormItem.template_id)
        .all()
    )
    formdata_counts = {tpl_id: count for tpl_id, count in formdata_counts_rows}

    # RepeatGroupData counts per template via join on FormItem
    repeat_counts_rows = (
        db.session.query(FormItem.template_id, func.count(RepeatGroupData.id))
        .join(RepeatGroupData, RepeatGroupData.form_item_id == FormItem.id)
        .group_by(FormItem.template_id)
        .all()
    )
    repeat_counts = {tpl_id: count for tpl_id, count in repeat_counts_rows}

    # DynamicIndicatorData counts per template via section -> template
    dynamic_counts_rows = (
        db.session.query(FormSection.template_id, func.count(DynamicIndicatorData.id))
        .join(DynamicIndicatorData, DynamicIndicatorData.section_id == FormSection.id)
        .group_by(FormSection.template_id)
        .all()
    )
    dynamic_counts = {tpl_id: count for tpl_id, count in dynamic_counts_rows}

    # Combine into total counts per template id
    template_data_counts = {}
    for t in templates:
        template_id = t.id
        template_data_counts[template_id] = (
            int(formdata_counts.get(template_id, 0))
            + int(repeat_counts.get(template_id, 0))
            + int(dynamic_counts.get(template_id, 0))
        )

    # Compute version counts per template to avoid N+1 queries
    from app.models.forms import FormTemplateVersion
    version_counts_rows = (
        db.session.query(FormTemplateVersion.template_id, func.count(FormTemplateVersion.id))
        .group_by(FormTemplateVersion.template_id)
        .all()
    )
    template_version_counts = {tpl_id: count for tpl_id, count in version_counts_rows}

    # Detect duplicate template names (using localized names)
    template_name_counts = {}
    for template in templates:
        template_name = get_localized_template_name(template) if template else None
        name_key = template_name if template_name else (template.name if template.name else 'Unnamed Template')
        template_name_counts[name_key] = template_name_counts.get(name_key, 0) + 1

    # Create a list of names that appear multiple times (convert to list for JSON serialization)
    duplicate_template_names = [name for name, count in template_name_counts.items() if count > 1]

    # Return JSON for API requests (mobile app)
    if is_json_request():
        templates_data = []
        for template in templates:
            template_name = get_localized_template_name(template) if template else None
            add_to_self_report = False
            if template.published_version:
                add_to_self_report = template.published_version.get_effective_add_to_self_report() or False
            else:
                # Fallback to first version if no published version
                first_version = template.versions.order_by('created_at').first()
                if first_version:
                    add_to_self_report = first_version.get_effective_add_to_self_report() or False

            templates_data.append({
                'id': template.id,
                'name': template.name or 'Unnamed Template',
                'localized_name': template_name if template_name != template.name else None,
                'add_to_self_report': add_to_self_report,
                'created_at': template.created_at.isoformat() if hasattr(template, 'created_at') and template.created_at else None,
                'data_count': template_data_counts.get(template.id, 0),
                'has_published_version': template.published_version is not None,
            })
        return json_ok(templates=templates_data, count=len(templates_data))

    return render_template(
        "admin/templates/templates.html",
        templates=templates,
        title="Manage Form Templates",
        get_localized_template_name=get_localized_template_name,
        template_data_counts=template_data_counts,
        template_version_counts=template_version_counts,
        duplicate_template_names=duplicate_template_names,
    )


@bp.route("/templates/import_kobo_xls", methods=["POST"])
@permission_required('admin.templates.create')
def import_kobo_xls():
    """Create a new template by importing a Kobo Toolbox XLSForm (.xlsx or .xls) file."""
    import os
    handle_sharing = _handle_template_sharing  # capture before any _ assignment

    if 'kobo_file' not in request.files and 'excel_file' not in request.files:
        flash(_("No file provided for Kobo import."), "danger")
        return redirect(url_for("form_builder.new_template"))

    kobo_file = request.files.get('kobo_file') or request.files.get('excel_file')
    if not kobo_file or kobo_file.filename == '':
        flash(_("No file selected for Kobo import."), "danger")
        return redirect(url_for("form_builder.new_template"))

    valid, error_msg, ext = validate_upload_extension_and_mime(kobo_file, EXCEL_EXTENSIONS)
    if not valid:
        flash(_(error_msg or "Invalid file type. Please upload an Excel file (.xlsx or .xls) in Kobo XLSForm format."), "danger")
        return redirect(url_for("form_builder.new_template"))

    template_name = request.form.get('name', '').strip() or None
    owned_by = request.form.get('owned_by', type=int) or current_user.id
    shared_admin_ids = request.form.getlist('shared_with_admins')
    shared_admin_ids = [int(x) for x in shared_admin_ids if x]

    try:
        result = KoboXlsImportService.import_kobo_xls(
            kobo_file,
            template_name=template_name,
            owned_by=owned_by,
        )
    except Exception as e:
        current_app.logger.error(f"Kobo import failed: {e}", exc_info=True)
        flash(_("Kobo import failed."), "danger")
        return redirect(url_for("form_builder.new_template"))

    if not result['success']:
        flash(_("Kobo import failed: %(message)s", message=result.get('message', 'Unknown error')), "danger")
        if result.get('errors'):
            for err in result['errors'][:3]:
                flash(err, "warning")
        return redirect(url_for("form_builder.new_template"))

    template_id = result['template_id']
    if shared_admin_ids:
        template = FormTemplate.query.get(template_id)
        if template:
            handle_sharing(template, shared_admin_ids, current_user.id)

    counts = result.get('created_counts', {})
    name = result.get('message', '').split("'")[1] if "'" in result.get('message', '') else 'Template'
    flash(
        _("Template '%(name)s' created with %(sections)d sections and %(items)d items. You can edit it in the form builder.", name=name, sections=counts.get('sections', 0), items=counts.get('items', 0)),
        "success",
    )
    if result.get('warnings'):
        for w in result['warnings'][:3]:
            flash(w, "info")

    return redirect(url_for("form_builder.edit_template", template_id=result['template_id']))


@bp.route("/templates/new", methods=["GET", "POST"])
@permission_required('admin.templates.create')
def new_template():
    from app.utils.form_localization import get_localized_template_name

    form = FormTemplateForm()

    # Get available templates for cloning (same logic as manage_templates)
    # System managers can clone from any template
    from app.services.authorization_service import AuthorizationService
    if AuthorizationService.is_system_manager(current_user):
        templates_query = FormTemplate.query.options(
            db.joinedload(FormTemplate.owned_by_user),
            db.joinedload(FormTemplate.shared_with).joinedload(TemplateShare.shared_with_user)
        )
    else:
        # Use efficient UNION query instead of loading all templates
        allowed_template_ids = get_user_allowed_template_ids(current_user.id)

        if not allowed_template_ids:
            # User has no access to any templates
            templates_query = FormTemplate.query.filter(literal(False))
        else:
            templates_query = FormTemplate.query.options(
                db.joinedload(FormTemplate.owned_by_user),
                db.joinedload(FormTemplate.shared_with).joinedload(TemplateShare.shared_with_user)
            ).filter(FormTemplate.id.in_(allowed_template_ids))
    # Note: Can't order by FormTemplate.name in SQL since it's a property
    # Will sort in Python after loading

    available_templates = templates_query.all()

    # Preselect current user as template owner for new templates
    if request.method == 'GET':
        form.owned_by.data = current_user.id

        # Handle cloning from existing template
        clone_from_id = request.args.get('clone_from')
        if clone_from_id:
            with suppress((ValueError, TypeError)):  # Invalid clone_from_id, ignore
                clone_from_id = int(clone_from_id)
                source_template = FormTemplate.query.get(clone_from_id)
                if source_template and check_template_access(clone_from_id, current_user.id):
                    # Pre-populate form with source template data (use published version)
                    source_version = source_template.published_version if source_template.published_version else source_template.versions.order_by('created_at').first()
                    if source_version:
                        form.name.data = f"{source_version.name} (Copy)" if source_version.name else "New Template (Copy)"
                        form.description.data = source_version.description or ""
                        form.add_to_self_report.data = source_version.add_to_self_report
                        form.display_order_visible.data = source_version.display_order_visible
                        form.is_paginated.data = source_version.is_paginated
                        form.enable_export_pdf.data = source_version.enable_export_pdf
                        form.enable_export_excel.data = source_version.enable_export_excel
                        form.enable_import_excel.data = source_version.enable_import_excel
                        form.enable_ai_validation.data = source_version.enable_ai_validation
                    else:
                        # Fallback if no version exists (shouldn't happen normally, use defaults)
                        form.name.data = "New Template (Copy)"
                        form.description.data = ""
                        form.add_to_self_report.data = False
                        form.display_order_visible.data = False
                        form.is_paginated.data = False
                        form.enable_export_pdf.data = False
                        form.enable_export_excel.data = False
                        form.enable_import_excel.data = False
                        form.enable_ai_validation.data = False
                    form.owned_by.data = current_user.id  # New template owned by current user

                    # Handle name translations from version
                    if source_version and source_version.name_translations:
                        # Populate the hidden field for translations
                        pass  # Will be handled by JavaScript

    # Check if this is an Excel import request (bypasses normal form validation but still needs required fields)
    import_from_excel = request.form.get('import_from_excel')

    if import_from_excel:
        # For Excel import, name can come from Excel file
        # Use form values if provided, otherwise Excel will populate them
        new_name = request.form.get('name', '').strip()

        # If name is provided, check for uniqueness (Excel import will override if it has a name)
        if new_name:
            existing_version = FormTemplateVersion.query.filter_by(
                name=new_name,
                status='published'
            ).join(FormTemplate, FormTemplateVersion.template_id == FormTemplate.id).filter(
                FormTemplate.id.isnot(None)
            ).first()
            if existing_version:
                flash(f"Error: A form template with the name '{new_name}' already exists.", "danger")
                return render_template(
                    "admin/templates/new_template.html",
                    form=form,
                    title="Create New Form Template",
                    available_templates=available_templates,
                    get_localized_template_name=get_localized_template_name
                )

        # Create template with data from form (using request.form for Excel import)
        # Use placeholder values if not provided - Excel import will update them
        add_to_self_report = request.form.get('add_to_self_report') == 'y'
        display_order_visible = request.form.get('display_order_visible') == 'y'
        is_paginated = request.form.get('is_paginated') == 'y'
        enable_export_pdf = request.form.get('enable_export_pdf') == 'y'
        enable_export_excel = request.form.get('enable_export_excel') == 'y'
        enable_import_excel = request.form.get('enable_import_excel') == 'y'
        enable_ai_validation = request.form.get('enable_ai_validation') == 'y'
        description = request.form.get('description', '')
        owned_by = request.form.get('owned_by', type=int) or current_user.id

        # Create template record (no config fields here; all are stored per-version)
        template = FormTemplate(
            created_by=current_user.id,
            owned_by=owned_by
        )

        db.session.add(template)
        db.session.flush()

        # Create initial version
        # Use placeholder name if not provided - Excel import will update it
        placeholder_name = new_name if new_name else "Imported Template"
        now = utcnow()
        initial_version = FormTemplateVersion(
            template_id=template.id,
            version_number=1,
            status='draft',
            name=placeholder_name,
            description=description,
            add_to_self_report=add_to_self_report,
            display_order_visible=display_order_visible,
            is_paginated=is_paginated,
            enable_export_pdf=enable_export_pdf,
            enable_export_excel=enable_export_excel,
            enable_import_excel=enable_import_excel,
            enable_ai_validation=enable_ai_validation,
            created_by=current_user.id,
            updated_by=current_user.id,
            created_at=now,
            updated_at=now
        )

        # Handle name translations from hidden fields
        name_translations_json = request.form.get('name_translations', '{}')
        with suppress((json.JSONDecodeError, TypeError)):
            name_translations = json.loads(name_translations_json) if name_translations_json else {}
            if name_translations:
                initial_version.name_translations = name_translations

        # Handle individual translation fields
        translations = {}
        for code in current_app.config.get('SUPPORTED_LANGUAGES', []):
            if code != 'en':
                trans_value = request.form.get(f'name_{code}', '').strip()
                if trans_value:
                    translations[code] = trans_value
        if translations:
            if initial_version.name_translations:
                initial_version.name_translations.update(translations)
            else:
                initial_version.name_translations = translations

        db.session.add(initial_version)
        db.session.flush()

        # Store version ID and template ID in variables before any commit operations
        # This prevents "not persistent" errors if operations commit the session
        version_id = initial_version.id
        template_id = template.id
        version_name_before_import = initial_version.name or "Imported Template"

        # Handle template sharing
        shared_admin_ids = request.form.getlist('shared_with_admins')
        if shared_admin_ids:
            shared_admin_ids = [int(id) for id in shared_admin_ids if id]
            # Pass version name to avoid accessing template.name which might trigger relationship queries
            _handle_template_sharing(template, shared_admin_ids, current_user.id, template_name=version_name_before_import)

        try:
            db.session.flush()

            # Handle Excel import
            if 'excel_file' not in request.files:
                flash(_("No Excel file provided for import."), "danger")
                return redirect(url_for("form_builder.edit_template", template_id=template_id))

            excel_file = request.files['excel_file']

            if excel_file.filename == '':
                flash(_("No Excel file selected for import."), "danger")
                return redirect(url_for("form_builder.edit_template", template_id=template_id))

            # SECURITY: Validate file extension and MIME type
            valid, error_msg, ext = validate_upload_extension_and_mime(excel_file, EXCEL_EXTENSIONS)
            if not valid:
                flash(_(error_msg or "Invalid file type. Please upload an Excel file (.xlsx or .xls)."), "danger")
                if ext:
                    current_app.logger.warning(f"Rejected Excel import - MIME type mismatch (ext: {ext})")
                return redirect(url_for("form_builder.edit_template", template_id=template_id))

            # IMPORTANT:
            # Commit the newly created template + initial version BEFORE we start the import.
            # The import service rolls back on errors; without this commit, a failed import
            # would rollback the template itself and cause a 404 on redirect to edit.
            try:
                db.session.commit()
            except Exception as commit_error:
                handle_view_exception(
                    commit_error,
                    "Error creating template.",
                    log_message=f"Error committing template before Excel import: {commit_error}",
                )
                return render_template(
                    "admin/templates/new_template.html",
                    form=form,
                    title="Create New Form Template",
                    available_templates=available_templates,
                    get_localized_template_name=get_localized_template_name
                )

            # Import template structure from Excel
            result = TemplateExcelService.import_template(template_id, excel_file, version_id)

            if result['success']:
                # Import succeeded - re-query version to get updated name from Excel import
                # Use a fresh query in case the import service committed
                try:
                    initial_version = FormTemplateVersion.query.get(version_id)
                    template_name = initial_version.name if initial_version and initial_version.name else version_name_before_import
                except Exception as query_error:
                    # If query fails (e.g., session was rolled back), use fallback name
                    current_app.logger.warning(f"Could not re-query version after import: {query_error}")
                    template_name = version_name_before_import

                created_counts = result.get('created_counts', {})
                pages_count = created_counts.get('pages', 0)
                sections_count = created_counts.get('sections', 0)
                items_count = created_counts.get('items', 0)

                # Log admin action for Excel import
                try:
                    log_admin_action(
                        action_type='template_import_excel',
                        description=f"Created template '{template_name}' and imported structure from Excel "
                                  f"(Pages: {pages_count}, Sections: {sections_count}, Items: {items_count})",
                        target_type='form_template',
                        target_id=template_id,
                        target_description=f"Template ID: {template_id}, Imported from Excel",
                        risk_level='medium'
                    )
                except Exception as log_error:
                    current_app.logger.error(f"Error logging Excel import: {log_error}")

                if result.get('errors'):
                    error_msg = _("Template created and Excel import completed with %(pages)d pages, %(sections)d sections, and %(items)d items. Some errors occurred: %(errors)s", pages=pages_count, sections=sections_count, items=items_count, errors=', '.join(result['errors'][:3]))
                    flash(error_msg, "warning")
                else:
                    flash(_("Template '%(name)s' created and Excel import completed: %(pages)d pages, %(sections)d sections, and %(items)d items imported.", name=template_name, pages=pages_count, sections=sections_count, items=items_count), "success")
            else:
                # Import failed - the import service may have rolled back the session
                # Rollback our session to ensure clean state
                try:
                    db.session.rollback()
                except Exception as e:
                    current_app.logger.debug("Rollback after Excel import failure: %s", e)

                error_msg = result.get('message', _('Unknown error during Excel import'))
                flash(_("Template created but Excel import failed: %(error)s", error=error_msg), "warning")
                if result.get('errors'):
                    current_app.logger.error(f"Excel import errors: {result['errors']}")

                # Even if import failed, template was created, so redirect to edit page
                # The template exists but may be incomplete

            return redirect(url_for("form_builder.edit_template", template_id=template_id))

        except Exception as e:
            handle_view_exception(
                e,
                "Error creating template.",
                log_message=f"Error creating template with Excel import: {e}"
            )
            return render_template(
                "admin/templates/new_template.html",
                form=form,
                title="Create New Form Template",
                available_templates=available_templates,
                get_localized_template_name=get_localized_template_name
            )

    if form.validate_on_submit():
        add_to_self_report = form.add_to_self_report.data

        # Check for name uniqueness across all published versions
        new_name = form.name.data.strip()
        if new_name:
            # Check if any published version has this name
            # Explicitly specify the join condition to avoid ambiguous foreign key error
            existing_version = FormTemplateVersion.query.filter_by(
                name=new_name,
                status='published'
            ).join(FormTemplate, FormTemplateVersion.template_id == FormTemplate.id).filter(
                FormTemplate.id.isnot(None)  # This will be None for new template
            ).first()
            if existing_version:
                flash(f"Error: A form template with the name '{new_name}' already exists.", "danger")
                return render_template(
                    "admin/templates/new_template.html",
                    form=form,
                    title="Create New Form Template",
                    available_templates=available_templates,
                    get_localized_template_name=get_localized_template_name
                )

        # Create template (no properties - all are now in versions)
        template = FormTemplate(
            created_by=current_user.id,
            owned_by=form.owned_by.data if form.owned_by.data else current_user.id
        )

        db.session.add(template)
        db.session.flush()  # Flush to get template ID

        # Create initial version with name and translations
        now = utcnow()
        initial_version = FormTemplateVersion(
            template_id=template.id,
            version_number=1,
            status='draft',
            name=new_name,
            description=form.description.data,
            add_to_self_report=add_to_self_report,
            display_order_visible=form.display_order_visible.data,
            is_paginated=form.is_paginated.data,
            enable_export_pdf=form.enable_export_pdf.data,
            enable_export_excel=form.enable_export_excel.data,
            enable_import_excel=form.enable_import_excel.data,
            enable_ai_validation=form.enable_ai_validation.data,
            created_by=current_user.id,
            updated_by=current_user.id,
            created_at=now,
            updated_at=now
        )

        # Handle version name and description translations
        _handle_version_translations(initial_version, form)
        _handle_version_description_translations(initial_version, form)

        db.session.add(initial_version)
        db.session.flush()

        # Store version name and ID in variables before any commit operations
        # This prevents "not persistent" errors if log_admin_action commits the session
        version_name = initial_version.name
        version_id = initial_version.id
        template_id = template.id

        # Handle template sharing - get values from form data since we're using checkboxes
        # Pass template name directly to avoid accessing template.name property which queries versions
        shared_admin_ids = request.form.getlist(form.shared_with_admins.name)
        current_app.logger.debug(f"Template creation - shared_admin_ids from form: {shared_admin_ids}")
        if shared_admin_ids:
            # Convert string IDs to integers
            shared_admin_ids = [int(id) for id in shared_admin_ids if id]
            current_app.logger.debug(f"Template creation - processed shared_admin_ids: {shared_admin_ids}")
            # Pass version name to avoid accessing template.name which might trigger relationship queries
            _handle_template_sharing(template, shared_admin_ids, current_user.id, template_name=version_name)

        try:
            db.session.flush()

            # Log admin action for template creation
            # Use stored variables to avoid accessing initial_version after potential commit
            try:
                log_admin_action(
                    action_type='template_create',
                    description=f"Created new template '{version_name}'",
                    target_type='form_template',
                    target_id=template_id,
                    target_description=f"Template ID: {template_id}",
                    risk_level='medium'
                )
            except Exception as log_error:
                current_app.logger.error(f"Error logging template creation: {log_error}")

            flash(f"Form Template '{version_name}' created. You can now add sections and items.", "success")
            return redirect(url_for("form_builder.edit_template", template_id=template_id))
        except Exception as e:
            handle_view_exception(
                e,
                GENERIC_ERROR_MESSAGE,
                log_message=f"Error creating new template: {e}"
            )

    return render_template(
        "admin/templates/new_template.html",
        form=form,
        title="Create New Form Template",
        available_templates=available_templates,
        get_localized_template_name=get_localized_template_name
    )

@bp.route("/templates/<int:template_id>/owned-by", methods=["GET"])
@permission_required('admin.templates.view')
def get_template_owned_by(template_id):
    """Return the owned_by user info for a template (used to pre-fill data owner on assignments)."""
    template = FormTemplate.query.get_or_404(template_id)
    if template.owned_by_user:
        return json_ok(
            owned_by_user_id=template.owned_by,
            owned_by_user_name=template.owned_by_user.name,
            owned_by_user_email=template.owned_by_user.email,
        )
    return json_ok(owned_by_user_id=None)


@bp.route("/templates/<int:template_id>/clone-data", methods=["GET"])
@permission_required('admin.templates.view')
def get_template_clone_data(template_id):
    """Get template data for cloning purposes."""
    template = FormTemplate.query.get_or_404(template_id)

    # Check if user has access to this template
    if not check_template_access(template_id, current_user.id):
        return json_forbidden('Access denied')

    # Return template data as JSON
    # Get name from published version or first version
    version = template.published_version if template.published_version else template.versions.order_by('created_at').first()
    version_name = version.name if version and version.name else "Unnamed Template"
    version_translations = version.name_translations if version and version.name_translations else {}

    return json_ok(
        id=template.id,
        name=version_name,
        description=version.description if version else '',
        add_to_self_report=version.add_to_self_report if version else False,
        display_order_visible=version.display_order_visible if version else False,
        is_paginated=version.is_paginated if version else False,
        enable_export_pdf=version.enable_export_pdf if version else False,
        enable_export_excel=version.enable_export_excel if version else False,
        enable_import_excel=version.enable_import_excel if version else False,
        enable_ai_validation=version.enable_ai_validation if version else False,
        name_translations=version_translations,
    )

@bp.route("/templates/edit/<int:template_id>", methods=["GET", "POST"])
@permission_required('admin.templates.edit')
def edit_template(template_id):
    template = FormTemplate.query.get_or_404(template_id)

    # Check if user has access to this template (owner or shared with)
    if not check_template_access(template_id, current_user.id):
        flash("Access denied. You don't have permission to edit this template.", "warning")
        return redirect(url_for("form_builder.manage_templates"))
    # Don't use obj=template since template.name is now a property - populate manually
    # IMPORTANT: do not pre-populate from DB on POST, otherwise submitted values (e.g. description)
    # get overwritten before validation/save.
    form = FormTemplateForm()

    # Unified request data: returns _JsonFormProxy for JSON requests, request.form for form-encoded.
    data = get_request_data()

    # Determine which version to display: explicit version_id (GET or POST) > published by default
    requested_version_id = None
    try:
        version_param = request.args.get('version_id') or (data.get('version_id') if request.method == 'POST' else None)
        requested_version_id = int(version_param) if version_param else None
    except Exception as e:
        current_app.logger.debug("version_id parse failed: %s", e)
        requested_version_id = None

    selected_version = None
    if requested_version_id:
        selected_version = FormTemplateVersion.query.filter_by(id=requested_version_id, template_id=template.id).first()
    if not selected_version and template.published_version_id:
        selected_version = FormTemplateVersion.query.get(template.published_version_id)
    # Fallback: latest version
    if not selected_version:
        selected_version = FormTemplateVersion.query.filter_by(template_id=template.id).order_by(FormTemplateVersion.created_at.desc()).first()

    # Safety net: if the template has no versions at all, create a draft version on the fly
    if not selected_version:
        selected_version = _get_or_create_draft_version(template, current_user.id)

    # Ensure we have fresh data from the database (in case of recent updates)
    if selected_version:
        db.session.refresh(selected_version)

    # Check if form was submitted (either via submit button or hidden field)
    # The submit field name is 'submit' and value is 'Save Template'
    is_template_details_submit = (
        request.method == 'POST' and
        data.get('submit') == 'Save Template'
    )

    # Populate fields from version (all properties are now version-specific) only for initial render.
    # On POST, Flask-WTF already binds request.form; repopulating here would clobber submitted data.
    if request.method == 'GET' and selected_version:
        form.name.data = selected_version.name if selected_version.name else ""
        form.description.data = selected_version.description or ""
        form.add_to_self_report.data = selected_version.add_to_self_report
        form.display_order_visible.data = selected_version.display_order_visible
        form.is_paginated.data = selected_version.is_paginated
        form.enable_export_pdf.data = selected_version.enable_export_pdf
        form.enable_export_excel.data = selected_version.enable_export_excel
        form.enable_import_excel.data = selected_version.enable_import_excel
        form.enable_ai_validation.data = selected_version.enable_ai_validation

        # Populate translation fields with existing values from version
        _populate_version_translations(form, selected_version)
        _populate_version_description_translations(form, selected_version)

        # Populate sharing fields with existing values
        _populate_template_sharing(form, template)
    section_form = FormSectionForm(prefix="section")

    # Forms for editing modals
    add_indicator_modal_form = IndicatorForm(prefix="add_ind_modal")
    document_field_form = DocumentFieldForm(prefix="doc_field")
    add_question_modal_form = QuestionForm(prefix="add_q_modal")

    # Populate page choices dynamically for the SELECTED version
    page_choices = []
    try:
        pages_for_choices = FormPage.query.filter_by(template_id=template.id, version_id=selected_version.id).all()
        page_choices = [(p.id, p.name) for p in pages_for_choices]
    except Exception as e:
        current_app.logger.warning("Failed to load page choices: %s", e, exc_info=True)
        page_choices = []
    section_form.page_id.choices = page_choices

    # Populate section choices for modal forms (scoped to draft version)
    # Include archived sections in form builder (they will be filtered/hidden in the template)
    all_sections = FormSection.query.filter_by(template_id=template.id, version_id=selected_version.id).order_by(FormSection.order).all()
    section_choices = [(s.id, s.name) for s in all_sections]
    add_indicator_modal_form.section_id.choices = section_choices
    add_question_modal_form.section_id.choices = section_choices
    document_field_form.section_id.choices = section_choices

    if is_template_details_submit:
        # Log form submission details only when VERBOSE_FORM_DEBUG is enabled (never log full form data)
        _template_debug = current_app.config.get('VERBOSE_FORM_DEBUG', False)
        if _template_debug:
            current_app.logger.debug(
                "TEMPLATE_UPDATE: form submission template_id=%s version_id=%s method=%s keys=%s",
                template.id, selected_version.id, request.method, list(data.keys())
            )

        # Validate form
        if not form.validate():
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error in {field}: {error}", "danger")
            return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=selected_version.id))

        # Form validation passed, proceed with update
        # Handle version name updates - use raw request form data as primary source
        new_name = data.get('name', form.name.data)
        if new_name:
            new_name = new_name.strip()

        # Ensure we have a valid name
        if not new_name or not new_name.strip():
            flash("Template name cannot be empty.", "danger")
            return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=selected_version.id))

        # Check for name uniqueness if this is a published version or if name changed
        is_published_version = (template.published_version_id == selected_version.id)
        if is_published_version or (selected_version.name != new_name):
            # Check if any other published version has this name
            # Explicitly specify the join condition to avoid ambiguous foreign key error
            existing_version = FormTemplateVersion.query.filter_by(
                name=new_name,
                status='published'
            ).join(FormTemplate, FormTemplateVersion.template_id == FormTemplate.id).filter(
                FormTemplate.id != template.id
            ).first()
            if existing_version:
                error_msg = f"Error: Another form template with the name '{new_name}' already exists."
                flash(error_msg, "danger")
                form.name.data = selected_version.name if selected_version.name else ""
                return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=selected_version.id))

        # Update version-specific name and properties
        selected_version.name = new_name if new_name else None
        selected_version.description = form.description.data

        # Boolean fields: handle both HTML checkbox values ('y') and JSON booleans (true/false).
        if 'is_paginated' in data:
            raw_value = data.get('is_paginated')
            if isinstance(raw_value, bool):
                is_paginated_value = raw_value
            else:
                is_paginated_value = str(raw_value).lower() in ('y', 'yes', 'true', 't', 'on', '1', '1.0')
        else:
            is_paginated_value = False

        def get_boolean_from_form(field_name, default_when_missing=False):
            if field_name in data:
                raw_value = data.get(field_name)
                if isinstance(raw_value, bool):
                    return raw_value
                return str(raw_value).lower() in ('y', 'yes', 'true', 't', 'on', '1', '1.0')
            else:
                return default_when_missing
        selected_version.add_to_self_report = get_boolean_from_form('add_to_self_report', default_when_missing=False)
        selected_version.display_order_visible = get_boolean_from_form('display_order_visible', default_when_missing=False)
        selected_version.is_paginated = is_paginated_value
        selected_version.enable_export_pdf = get_boolean_from_form('enable_export_pdf', default_when_missing=False)
        selected_version.enable_export_excel = get_boolean_from_form('enable_export_excel', default_when_missing=False)
        selected_version.enable_import_excel = get_boolean_from_form('enable_import_excel', default_when_missing=False)
        selected_version.enable_ai_validation = get_boolean_from_form('enable_ai_validation', default_when_missing=False)



        # Update template ownership if changed
        if form.owned_by.data and form.owned_by.data != template.owned_by:
            template.owned_by = form.owned_by.data

        # Handle version name and description translations
        _handle_version_translations(selected_version, form)
        _handle_version_description_translations(selected_version, form)

        shared_admin_ids = data.getlist(form.shared_with_admins.name)
        current_app.logger.debug(f"Template edit - shared_admin_ids from form: {shared_admin_ids}")
        if shared_admin_ids:
            # Convert string IDs to integers
            shared_admin_ids = [int(id) for id in shared_admin_ids if id]
        else:
            shared_admin_ids = []
        current_app.logger.debug(f"Template edit - processed shared_admin_ids: {shared_admin_ids}")
        _handle_template_sharing(template, shared_admin_ids, current_user.id)

        try:
            # Handle pages data
            if selected_version.is_paginated:
                before_pages = FormPage.query.filter_by(template_id=template.id, version_id=selected_version.id).count()
                current_app.logger.debug(
                    f"VERSIONING_DEBUG: edit_template - updating pages for version {selected_version.id}; "
                    f"pages before={before_pages}"
                )
                # Update pages for the active version (draft or published)
                _handle_template_pages(template, data, version_id=selected_version.id)
                _update_version_timestamp(selected_version.id, current_user.id)
                after_pages = FormPage.query.filter_by(template_id=template.id, version_id=selected_version.id).count()
                current_app.logger.debug(
                    f"VERSIONING_DEBUG: edit_template - updated pages for version {selected_version.id}; "
                    f"pages after={after_pages}"
                )
            db.session.flush()

            # Refresh the version object to ensure we have the latest data
            db.session.refresh(selected_version)

            # Double-check by querying from database
            db.session.expire(selected_version)
            db.session.refresh(selected_version)

            # Verify persisted value when verbose debug is enabled
            if _template_debug:
                db_version = FormTemplateVersion.query.get(selected_version.id)
                if db_version and db_version.is_paginated != selected_version.is_paginated:
                    current_app.logger.warning(
                        "TEMPLATE_UPDATE: is_paginated mismatch object=%s db=%s",
                        selected_version.is_paginated, db_version.is_paginated
                    )

            # Log admin action for audit trail
            try:
                log_admin_action(
                    action_type='template_update',
                    description=f"Updated template '{selected_version.name}'",
                    target_type='form_template',
                    target_id=template.id,
                    target_description=f"Template ID: {template.id}, Version ID: {selected_version.id}",
                    risk_level='medium'
                )
            except Exception as log_error:
                current_app.logger.error(f"Error logging template update: {log_error}")

            success_msg = f"Form Template '{selected_version.name}' updated successfully."

            flash(success_msg, "success")
            redirect_url = url_for("form_builder.edit_template", template_id=template.id, version_id=selected_version.id)
            if is_json_request():
                return json_ok(message=success_msg, redirect_url=redirect_url)
            return redirect(redirect_url)
        except Exception as e:
            request_transaction_rollback()
            error_msg = "Error updating form template."
            current_app.logger.error(f"Error updating template {template_id}: {e}", exc_info=True)
            db.session.refresh(template)
            form = FormTemplateForm(obj=template)

    # Build template data for JavaScript scoped to the selected version
    template_data = _build_template_data_for_js(template, version_id=selected_version.id)

    # Sanitize template_data to avoid collisions with helper function names
    # If any plugin or upstream builder inadvertently adds these keys, ensure
    # our callable helpers are not overridden in the Jinja context.
    try:
        reserved_helper_keys = {
            'get_localized_template_name',
            'get_localized_indicator_type',
            'get_localized_indicator_unit',
            # Prevent collisions with Flask-Babel translation functions
            '_', 'gettext', 'ngettext',
        }
        for _key in list(template_data.keys()):
            if _key in reserved_helper_keys:
                current_app.logger.warning(
                    f"Removing conflicting key from template_data: {_key}"
                )
                template_data.pop(_key, None)
    except Exception as _e:
        current_app.logger.error(
            f"Error sanitizing template_data for helper collisions: {_e}",
            exc_info=True,
        )

    # Get custom field types from plugins for the form builder
    custom_field_types = []
    if current_app.form_integration:
        custom_field_types = current_app.form_integration.get_custom_field_types_for_builder()

    from app.utils.form_localization import get_localized_template_name, get_localized_indicator_type, get_localized_indicator_unit
    from flask_babel import gettext as _gettext, ngettext as _ngettext
    # Important: Pass template_data first so that callable helpers below cannot be overridden
    # by any accidentally conflicting keys inside template_data.
    # Pages list for server-side rendering (use selected version)
    draft_pages = FormPage.query.filter_by(template_id=template.id, version_id=selected_version.id).order_by(FormPage.order).all()

    # Compute data counts for warning prompts in the builder UI
    from sqlalchemy import func
    from app.models.forms import FormData, RepeatGroupData, RepeatGroupInstance, DynamicIndicatorData

    # Item-level counts (FormData + RepeatGroupData) for items in this template
    item_counts_fd_rows = (
        db.session.query(FormItem.id, func.count(FormData.id))
        .join(FormData, FormData.form_item_id == FormItem.id)
        .filter(FormItem.template_id == template.id)
        .group_by(FormItem.id)
        .all()
    )
    item_counts_rd_rows = (
        db.session.query(FormItem.id, func.count(RepeatGroupData.id))
        .join(RepeatGroupData, RepeatGroupData.form_item_id == FormItem.id)
        .filter(FormItem.template_id == template.id)
        .group_by(FormItem.id)
        .all()
    )
    item_data_counts = {}
    for item_id, count in item_counts_fd_rows:
        item_data_counts[item_id] = item_data_counts.get(item_id, 0) + int(count)
    for item_id, count in item_counts_rd_rows:
        item_data_counts[item_id] = item_data_counts.get(item_id, 0) + int(count)

    # Section-level counts: aggregate counts for items in each section (+ dynamic indicator data + repeat instances per section)
    sec_counts_fd_rows = (
        db.session.query(FormItem.section_id, func.count(FormData.id))
        .join(FormData, FormData.form_item_id == FormItem.id)
        .filter(FormItem.template_id == template.id)
        .group_by(FormItem.section_id)
        .all()
    )
    sec_counts_rd_rows = (
        db.session.query(FormItem.section_id, func.count(RepeatGroupData.id))
        .join(RepeatGroupData, RepeatGroupData.form_item_id == FormItem.id)
        .filter(FormItem.template_id == template.id)
        .group_by(FormItem.section_id)
        .all()
    )
    # Dynamic indicator data is tied directly to section_id
    section_ids_subq = select(FormSection.id).filter_by(template_id=template.id).scalar_subquery()
    dyn_counts_rows = (
        db.session.query(DynamicIndicatorData.section_id, func.count(DynamicIndicatorData.id))
        .filter(DynamicIndicatorData.section_id.in_(section_ids_subq))
        .group_by(DynamicIndicatorData.section_id)
        .all()
    )
    # Repeat group instances are tied directly to section_id
    repeat_instance_counts_rows = (
        db.session.query(RepeatGroupInstance.section_id, func.count(RepeatGroupInstance.id))
        .filter(RepeatGroupInstance.section_id.in_(section_ids_subq))
        .group_by(RepeatGroupInstance.section_id)
        .all()
    )
    section_data_counts = {}
    for sec_id, count in sec_counts_fd_rows:
        section_data_counts[sec_id] = section_data_counts.get(sec_id, 0) + int(count)
    for sec_id, count in sec_counts_rd_rows:
        section_data_counts[sec_id] = section_data_counts.get(sec_id, 0) + int(count)
    for sec_id, count in dyn_counts_rows:
        section_data_counts[sec_id] = section_data_counts.get(sec_id, 0) + int(count)
    for sec_id, count in repeat_instance_counts_rows:
        section_data_counts[sec_id] = section_data_counts.get(sec_id, 0) + int(count)

    # Versions list for UI
    # PERFORMANCE: Pre-fetch all users to avoid N+1 queries
    versions = FormTemplateVersion.query.filter_by(template_id=template.id).order_by(FormTemplateVersion.created_at.desc()).all()

    # Collect all unique user IDs
    user_ids = set()
    for v in versions:
        if hasattr(v, 'updated_by') and v.updated_by:
            user_ids.add(v.updated_by)

    # Fetch all users in a single query
    users_by_id = {}
    if user_ids:
        users = User.query.filter(User.id.in_(user_ids)).all()
        users_by_id = {user.id: user for user in users}

    versions_for_ui = []
    for v in versions:
        # Get updated_by user info from pre-fetched dict
        updated_by_user = None
        if hasattr(v, 'updated_by') and v.updated_by:
            updated_by_user = users_by_id.get(v.updated_by)

        versions_for_ui.append({
            'id': v.id,
            'version_number': v.version_number if hasattr(v, 'version_number') else None,
            'status': v.status,
            'comment': v.comment or '',
            'created_at': v.created_at,
            'updated_at': v.updated_at if hasattr(v, 'updated_at') else v.created_at,
            'updated_by': updated_by_user,
            'updated_by_name': updated_by_user.name if updated_by_user and updated_by_user.name else (updated_by_user.email if updated_by_user else None),
            'is_published': (template.published_version_id == v.id)
        })
    has_draft = FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').first() is not None

    # Get active version number for display
    active_version_number = None
    if selected_version:
        active_version_number = selected_version.version_number if hasattr(selected_version, 'version_number') else None

    # Check if template has any archived items or sections
    has_archived_items = FormItem.query.filter_by(template_id=template.id, archived=True).first() is not None
    has_archived_sections = FormSection.query.filter_by(template_id=template.id, archived=True).first() is not None
    has_archived_items = has_archived_items or has_archived_sections

    # Integrity guardrails: block deploy if any indicator items are missing a valid indicator bank reference
    invalid_indicator_items_count = (
        FormItem.query
        .filter_by(template_id=template.id, version_id=selected_version.id, item_type='indicator')
        .filter(FormItem.indicator_bank_id.is_(None))
        .count()
    )

    _all_lang_disp = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", None) or {}
    _primary_lang_disp = getattr(Config, "LANGUAGE_DISPLAY_NAMES", None) or {}
    merged_language_display_names = {**_all_lang_disp, **_primary_lang_disp}

    return render_template("forms/form_builder/form_builder.html",
                           **template_data,
                           title=f"Edit Form Template: {template.name}",
                           active_version_number=active_version_number,
                           template=template,
                           form=form,
                           section_form=section_form,
                           add_indicator_modal_form=add_indicator_modal_form,
                           document_field_form=document_field_form,
                           add_question_modal_form=add_question_modal_form,
                           active_version_id=selected_version.id,
                           has_draft=has_draft,
                           published_version_id=template.published_version_id,
                           draft_pages=draft_pages,
                           versions_for_ui=versions_for_ui,
                           selected_version=selected_version,
                           selected_version_comment=selected_version.comment or '',
                           selected_version_is_draft=(selected_version.status == 'draft'),
                           selected_version_status=selected_version.status,

                           # Re-inject gettext helpers explicitly to avoid any shadowing
                           _=_gettext,
                           gettext=_gettext,
                           ngettext=_ngettext,
                           get_localized_template_name=get_localized_template_name,
                           get_localized_indicator_type=get_localized_indicator_type,
                           get_localized_indicator_unit=get_localized_indicator_unit,
                           custom_field_types=custom_field_types,
                           item_data_counts=item_data_counts,
                           section_data_counts=section_data_counts,
                           has_archived_items=has_archived_items,
                           invalid_indicator_items_count=invalid_indicator_items_count,
                           merged_language_display_names=merged_language_display_names)

@bp.route("/templates/<int:template_id>/delete-info", methods=["GET"])
@admin_permission_required('admin.templates.delete')
def get_template_delete_info(template_id):
    """Get detailed information about what will be deleted when deleting a template."""
    from app.services.authorization_service import AuthorizationService

    template = FormTemplate.query.get_or_404(template_id)

    # Template owner or system manager can view delete info
    if template.owned_by != current_user.id and not AuthorizationService.is_system_manager(current_user):
        return json_forbidden('Access denied. Only the template owner can view this information.')

    # Get assignments
    assigned_forms = template.assigned_forms.all()
    assignments_list = []
    for af in assigned_forms:
        public_submissions_count = af.public_submissions.count() if hasattr(af, 'public_submissions') else 0
        assignments_list.append({
            'id': af.id,
            'period_name': af.period_name,
            'public_submissions_count': public_submissions_count
        })

    # Get data counts (reuse logic from manage_templates)
    from app.models.form_items import FormItem
    from app.models.forms import FormData, RepeatGroupData, DynamicIndicatorData, FormSection, RepeatGroupInstance
    from sqlalchemy import func

    item_ids_subq = select(FormItem.id).filter_by(template_id=template.id).scalar_subquery()
    section_ids_subq = select(FormSection.id).filter_by(template_id=template.id).scalar_subquery()

    formdata_count = db.session.query(func.count(FormData.id)).filter(FormData.form_item_id.in_(item_ids_subq)).scalar() or 0
    repeat_data_count = db.session.query(func.count(RepeatGroupData.id)).filter(RepeatGroupData.form_item_id.in_(item_ids_subq)).scalar() or 0
    repeat_instances_count = db.session.query(func.count(RepeatGroupInstance.id)).filter(RepeatGroupInstance.section_id.in_(section_ids_subq)).scalar() or 0
    dynamic_data_count = db.session.query(func.count(DynamicIndicatorData.id)).filter(DynamicIndicatorData.section_id.in_(section_ids_subq)).scalar() or 0

    total_data_count = formdata_count + repeat_data_count + repeat_instances_count + dynamic_data_count

    # Get template structure counts
    versions_count = FormTemplateVersion.query.filter_by(template_id=template.id).count()
    pages_count = FormPage.query.filter_by(template_id=template.id).count()
    sections_count = FormSection.query.filter_by(template_id=template.id).count()
    items_count = FormItem.query.filter_by(template_id=template.id).count()

    # Get version details
    versions = FormTemplateVersion.query.filter_by(template_id=template.id).order_by(FormTemplateVersion.created_at.desc()).all()
    versions_list = []
    for v in versions:
        versions_list.append({
            'id': v.id,
            'version_number': v.version_number if hasattr(v, 'version_number') else None,
            'status': v.status,
            'created_at': v.created_at.isoformat() if v.created_at else None
        })

    return json_ok(
        template_id=template.id,
        template_name=template.name,
        assignments=assignments_list,
        assignments_count=len(assignments_list),
        data_counts={
            'form_data': formdata_count,
            'repeat_data': repeat_data_count,
            'repeat_instances': repeat_instances_count,
            'dynamic_data': dynamic_data_count,
            'total': total_data_count,
        },
        structure_counts={
            'versions': versions_count,
            'pages': pages_count,
            'sections': sections_count,
            'items': items_count,
        },
        versions=versions_list,
    )

@bp.route("/templates/delete/<int:template_id>", methods=["POST"])
@admin_permission_required('admin.templates.delete')
def delete_template(template_id):
    from app.services.authorization_service import AuthorizationService

    template = FormTemplate.query.get_or_404(template_id)

    # Template owner or system manager can delete the template
    if template.owned_by != current_user.id and not AuthorizationService.is_system_manager(current_user):
        flash("Access denied. Only the template owner can delete this template.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    # Check if deletion is confirmed (from the modal)
    confirmed = request.form.get('confirmed', 'false').lower() == 'true'

    if not confirmed:
        # Return JSON error for AJAX requests, or redirect for form submissions
        if is_json_request():
            return json_bad_request('Deletion not confirmed. Please use the confirmation modal.')
        flash("Deletion not confirmed. Please use the confirmation modal.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    try:
        # Debug counts prior to delete
        total_versions = template.versions.count() if hasattr(template, 'versions') else 0
        total_pages = template.pages.count() if hasattr(template, 'pages') else 0
        total_sections = template.sections.count() if hasattr(template, 'sections') else 0
        current_app.logger.debug(
            f"VERSIONING_DEBUG: delete_template - template_id={template_id} pre-delete: "
            f"versions={total_versions}, pages={total_pages}, sections={total_sections}"
        )
        # ``FormTemplate.name`` is derived from the published (or first) version; capture it
        # before unpublishing and bulk-deleting versions below.
        template_name = template.name
        # Delete template sharing records first
        TemplateShare.query.filter_by(template_id=template.id).delete(synchronize_session=False)

        # Delete assignments (which will cascade to public submissions and entity statuses)
        from app.models.assignments import AssignedForm
        assignments_deleted = AssignedForm.query.filter_by(template_id=template.id).delete(synchronize_session=False)
        current_app.logger.debug(f"VERSIONING_DEBUG: delete_template - deleted {assignments_deleted} assignments")

        # Unpublish to avoid FK constraints
        template.published_version_id = None
        db.session.flush()

        # Manually delete children and dependent data in safe order (works even without DB ON DELETE)
        from app.models.form_items import FormItem
        from app.models.forms import (
            FormPage,
            FormSection,
            FormTemplateVersion,
            FormData,
            RepeatGroupInstance,
            RepeatGroupData,
            DynamicIndicatorData,
        )

        # Subqueries for dependent deletes
        item_ids_subq = select(FormItem.id).filter_by(template_id=template.id).scalar_subquery()
        section_ids_subq = select(FormSection.id).filter_by(template_id=template.id).scalar_subquery()

        # Delete data rows that reference this template's items/sections first to avoid FK violations
        formdata_deleted = FormData.query.filter(FormData.form_item_id.in_(item_ids_subq)).delete(synchronize_session=False)
        repeat_data_deleted = RepeatGroupData.query.filter(RepeatGroupData.form_item_id.in_(item_ids_subq)).delete(synchronize_session=False)
        repeat_instances_deleted = RepeatGroupInstance.query.filter(RepeatGroupInstance.section_id.in_(section_ids_subq)).delete(synchronize_session=False)
        dynamic_data_deleted = DynamicIndicatorData.query.filter(DynamicIndicatorData.section_id.in_(section_ids_subq)).delete(synchronize_session=False)

        # Now remove the structural records
        items_deleted = FormItem.query.filter_by(template_id=template.id).delete(synchronize_session=False)
        sections_deleted = FormSection.query.filter_by(template_id=template.id).delete(synchronize_session=False)
        pages_deleted = FormPage.query.filter_by(template_id=template.id).delete(synchronize_session=False)
        versions_deleted = FormTemplateVersion.query.filter_by(template_id=template.id).delete(synchronize_session=False)

        current_app.logger.debug(
            f"VERSIONING_DEBUG: delete_template - manual cascade deletes -> "
            f"formdata={formdata_deleted}, repeat_data={repeat_data_deleted}, "
            f"repeat_instances={repeat_instances_deleted}, dynamic_data={dynamic_data_deleted}, "
            f"items={items_deleted}, sections={sections_deleted}, pages={pages_deleted}, versions={versions_deleted}"
        )

        db.session.delete(template)
        db.session.flush()
        current_app.logger.info(
            f"VERSIONING_DEBUG: delete_template - deleted template_id={template_id} "
            f"(assignments={assignments_deleted}, items={items_deleted}, sections={sections_deleted}, pages={pages_deleted}, versions={versions_deleted})"
        )

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='template_delete',
                description=f"Deleted template '{template_name}' and all structure (assignments={assignments_deleted}, items={items_deleted}, sections={sections_deleted}, data entries={formdata_deleted + repeat_data_deleted + dynamic_data_deleted})",
                target_type='form_template',
                target_id=template_id,
                target_description=f"Template ID: {template_id}",
                risk_level='medium'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging template deletion: {log_error}")

        flash(f"Form Template '{template_name}' and its structure deleted.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error deleting template {template_id}: {e}", exc_info=True)
    return redirect(url_for("form_builder.manage_templates"))

@bp.route("/templates/duplicate/<int:template_id>", methods=["POST"])
@permission_required('admin.templates.duplicate')
def duplicate_template(template_id):
    """Duplicate a form template including its published structure into a new template owned by the current user.

    - Generates a unique name by appending "(Copy)" (and a counter if needed)
    - Copies template flags and translations
    - Creates a published version in the new template and clones pages/sections/items from the source published version
    """
    # Validate access to source
    source_template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(source_template.id, current_user.id):
        flash("Access denied. You don't have permission to duplicate this template.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    # Get source version name for copying
    source_version = source_template.published_version if source_template.published_version else source_template.versions.order_by('created_at').first()
    source_name = source_version.name if source_version and source_version.name else "Unnamed Template"

    # Determine base name and ensure uniqueness (check published versions)
    base_copy_name = f"{source_name} (Copy)"
    new_name = base_copy_name
    suffix = 2
    while FormTemplateVersion.query.filter_by(name=new_name, status='published').first() is not None:
        new_name = f"{base_copy_name} {suffix}"
        suffix += 1

    # Create the new template record (no properties - all are now in versions)
    new_template = FormTemplate(
        created_by=current_user.id,
        owned_by=current_user.id
    )

    try:
        db.session.add(new_template)
        db.session.flush()  # obtain ID

        # Source version already retrieved above, but ensure we have it
        if not source_version:
            if source_template.published_version_id:
                source_version = FormTemplateVersion.query.get(source_template.published_version_id)
            if not source_version:
                source_version = FormTemplateVersion.query.filter_by(template_id=source_template.id).order_by(FormTemplateVersion.created_at.desc()).first()

        # Always create a published version on the new template
        # Use the new template name for the version (not the source version name)
        # This ensures consistency: new template name = new version name
        new_published = FormTemplateVersion(
            template_id=new_template.id,
            version_number=1,
            status='published',
            based_on_version_id=None,
            created_by=current_user.id,
            updated_by=current_user.id,
            comment=f"Cloned from template {source_template.id}",
            name=new_name,  # Use the unique name we generated
            name_translations=source_version.name_translations.copy() if source_version and source_version.name_translations else None,  # Copy from source version
            description=source_version.description if source_version else None,
            description_translations=source_version.description_translations.copy() if source_version and source_version.description_translations else None,  # Copy description translations
            add_to_self_report=source_version.add_to_self_report if source_version else None,
            display_order_visible=source_version.display_order_visible if source_version else None,
            is_paginated=source_version.is_paginated if source_version else None,
            enable_export_pdf=source_version.enable_export_pdf if source_version else None,
            enable_export_excel=source_version.enable_export_excel if source_version else None,
            enable_import_excel=source_version.enable_import_excel if source_version else None,
            enable_ai_validation=source_version.enable_ai_validation if source_version else False
        )
        db.session.add(new_published)
        db.session.flush()

        if source_version:
            _clone_template_structure_between_templates(
                source_template_id=source_template.id,
                source_version_id=source_version.id,
                target_template_id=new_template.id,
                target_version_id=new_published.id
            )

        # Point new template to its published version
        new_template.published_version_id = new_published.id

        db.session.flush()

        # Audit log
        with suppress(Exception):
            log_admin_action(
                action_type='template_duplicate',
                description=f"Duplicated template '{source_name}' to '{new_name}'",
                target_type='form_template',
                target_id=new_template.id,
                target_description=f"Source ID: {source_template.id}, New ID: {new_template.id}",
                risk_level='low'
            )

        flash(f"Form Template '{source_name}' duplicated as '{new_name}'.", "success")
        return redirect(url_for("form_builder.edit_template", template_id=new_template.id))

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error duplicating template {template_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("form_builder.manage_templates"))

@bp.route("/templates/<int:template_id>/export_excel", methods=["GET"])
@permission_required('admin.templates.export_excel')
def export_template_excel(template_id):
    """Export template structure to Excel file."""
    template = FormTemplate.query.get_or_404(template_id)

    # Check template access
    if not check_template_access(template_id, current_user.id):
        flash("Access denied. You don't have permission to export this template.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    # Get version_id from query parameter (defaults to published or latest)
    version_id = request.args.get('version_id', type=int)

    try:
        # Export template to Excel
        excel_file = TemplateExcelService.export_template(template_id, version_id)

        # Generate filename
        template_name_safe = secure_filename(template.name)
        filename = f"template_{template_name_safe}_{utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

        # Log admin action
        try:
            log_admin_action(
                action_type='template_export',
                description=f"Exported template '{template.name}' to Excel",
                target_type='form_template',
                target_id=template_id,
                target_description=f"Template ID: {template_id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging template export: {log_error}")

        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        current_app.logger.error(f"Error exporting template {template_id} to Excel: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("form_builder.edit_template", template_id=template_id))

@bp.route("/templates/<int:template_id>/import_excel", methods=["POST"])
@permission_required('admin.templates.import_excel')
def import_template_excel(template_id):
    """Import template structure from Excel file."""
    template = FormTemplate.query.get_or_404(template_id)

    # Check template access
    if not check_template_access(template_id, current_user.id):
        flash("Access denied. You don't have permission to import into this template.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    # Get version_id from query parameter or form (defaults to active version)
    # Get this early so we can use it in error redirects too
    version_id = request.args.get('version_id', type=int) or request.form.get('version_id', type=int)

    # Validate CSRF token
    csrf_form = FlaskForm()
    if not csrf_form.validate_on_submit():
        flash("Security validation failed. Please try again.", "danger")
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version_id))

    # Check if file was uploaded
    if 'excel_file' not in request.files:
        flash("No Excel file provided.", "danger")
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version_id))

    excel_file = request.files['excel_file']

    if excel_file.filename == '':
        flash("No Excel file selected.", "danger")
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version_id))

    # Validate file extension
    if not excel_file.filename.lower().endswith(('.xlsx', '.xls')):
        flash("Invalid file type. Please upload an Excel file (.xlsx or .xls).", "danger")
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version_id))

    try:
        # Import template from Excel
        result = TemplateExcelService.import_template(template_id, excel_file, version_id)

        # Use the version_id from result (may be new draft if published was selected)
        final_version_id = result.get('version_id', version_id)

        if result['success']:
            # Log admin action
            try:
                log_admin_action(
                    action_type='template_import',
                    description=f"Imported template structure from Excel into '{template.name}' "
                           f"(Pages: {result['created_count']['pages']}, "
                           f"Sections: {result['created_count']['sections']}, "
                           f"Items: {result['created_count']['items']})",
                    target_type='form_template',
                    target_id=template_id,
                    target_description=f"Template ID: {template_id}",
                    risk_level='medium'
                )
            except Exception as log_error:
                current_app.logger.error(f"Error logging template import: {log_error}")

            flash(result['message'], "success")
        else:
            # Show errors
            error_msg = result['message']
            if result.get('errors'):
                error_msg += f" Errors: {', '.join(result['errors'][:5])}"
                if len(result['errors']) > 5:
                    error_msg += f" (and {len(result['errors']) - 5} more)"
            flash(error_msg, "danger")

        # Preserve version_id in redirect (use final_version_id which may be new draft)
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=final_version_id))

    except Exception as e:
        current_app.logger.error(f"Error importing template {template_id} from Excel: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version_id))

# === Template Variables Management Routes ===
@bp.route("/templates/<int:template_id>/variables", methods=["GET", "POST"])
@permission_required('admin.templates.edit')
def manage_template_variables(template_id):
    """Get or save template variables."""
    try:
        template = FormTemplate.query.get_or_404(template_id)
    except Exception as e:
        current_app.logger.error(f"Template not found: {template_id}: {e}", exc_info=True)
        return json_not_found('Template not found.')

    # Check template access - return JSON error instead of redirect
    if not check_template_access(template_id, current_user.id):
        return json_forbidden('Access denied. You don\'t have permission to manage variables for this template.')

    # Get version_id from query parameter (for both GET and POST)
    version_id = request.args.get('version_id', type=int)
    if not version_id and request.method == 'POST':
        # Try to get from JSON body
        with suppress(Exception):
            json_data = get_json_safe()
            if json_data and 'version_id' in json_data:
                version_id = json_data.get('version_id', type=int)

    # Determine which version to use
    version = None
    if version_id:
        version = FormTemplateVersion.query.filter_by(id=version_id, template_id=template.id).first()
    if not version and template.published_version_id:
        version = FormTemplateVersion.query.get(template.published_version_id)
    if not version:
        version = FormTemplateVersion.query.filter_by(template_id=template.id).order_by(FormTemplateVersion.created_at.desc()).first()

    if not version:
        return json_not_found('No version found for this template.')

    if request.method == 'GET':
        # Return variables as JSON
        variables = version.variables if version.variables else {}
        return json_ok(variables=variables)

    elif request.method == 'POST':
        # Save variables
        try:
            # Get JSON data - handle both Content-Type: application/json and form data
            variables_data = None
            if is_json_request():
                variables_data = get_json_safe()
            else:
                # Try to parse from form data
                variables_str = request.form.get('variables')
                if variables_str:
                    try:
                        variables_data = json.loads(variables_str)
                    except json.JSONDecodeError:
                        return json_bad_request('Invalid JSON in variables field.')

            if not variables_data:
                return json_bad_request('No data provided. Expected JSON with "variables" key.')

            if 'variables' not in variables_data:
                return json_bad_request('Invalid data format. Expected "variables" key.')

            # Validate variables structure
            variables_dict = variables_data['variables']
            if not isinstance(variables_dict, dict):
                return json_bad_request('Variables must be a dictionary/object.')

            # Save variables
            version.variables = variables_dict
            _update_version_timestamp(version.id, current_user.id)
            db.session.commit()

            # Log admin action
            try:
                log_admin_action(
                    action_type='template_variables_update',
                    description=f"Updated variables for template '{template.name}'",
                    target_type='form_template',
                    target_id=template_id,
                    target_description=f"Template ID: {template_id}, Version ID: {version.id}",
                    risk_level='low'
                )
            except Exception as log_error:
                current_app.logger.error(f"Error logging variables update: {log_error}")

            return json_ok(message='Variables saved successfully.')
        except json.JSONDecodeError as e:
            request_transaction_rollback()
            current_app.logger.error(f"JSON decode error saving variables for template {template_id}: {e}")
            return json_bad_request('Invalid JSON format.')
        except Exception as e:
            return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/templates/<int:template_id>/variables/options", methods=["GET"])
@permission_required('admin.templates.edit')
def get_variable_options(template_id):
    """Get dropdown options for variable configuration (templates, assignments, form items)."""
    template = FormTemplate.query.get_or_404(template_id)

    # Check template access
    if not check_template_access(template_id, current_user.id):
        return json_forbidden('Access denied.')

    try:
        # Get all templates (for source template dropdown)
        # Load templates with published version for sorting
        all_templates = FormTemplate.query.options(
            db.joinedload(FormTemplate.published_version)
        ).all()
        # Sort by name (from published version) in Python since it's a property
        all_templates.sort(key=lambda t: t.name if t.name else "")
        templates_list = [{'id': t.id, 'name': t.name} for t in all_templates]

        # Get all assignments grouped by template
        assignments_by_template = {}
        all_assignments = AssignedForm.query.order_by(AssignedForm.period_name.desc()).all()
        for assignment in all_assignments:
            if assignment.template_id not in assignments_by_template:
                assignments_by_template[assignment.template_id] = []
            assignments_by_template[assignment.template_id].append({
                'id': assignment.id,
                'period_name': assignment.period_name,
                'template_id': assignment.template_id
            })

        # Get source template ID from query parameter (if filtering)
        source_template_id = request.args.get('source_template_id', type=int)

        # Get form items for a specific template (if source_template_id provided)
        form_items_list = []
        if source_template_id:
            # Get published version of source template
            source_template = FormTemplate.query.get(source_template_id)
            if source_template and source_template.published_version_id:
                source_version_id = source_template.published_version_id
                form_items = FormItem.query.filter_by(
                    template_id=source_template_id,
                    version_id=source_version_id,
                    archived=False
                ).order_by(FormItem.order).all()
                form_items_list = [
                    {
                        'id': item.id,
                        'label': item.label,
                        'item_type': item.item_type,
                        'section_id': item.section_id
                    }
                    for item in form_items
                ]

        return json_ok(
            templates=templates_list,
            assignments_by_template=assignments_by_template,
            form_items=form_items_list,
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)
