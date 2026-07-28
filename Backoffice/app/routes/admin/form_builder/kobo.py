"""KoBo Data Import Wizard routes."""

import os
import uuid

from flask import request, render_template, session, current_app, flash, redirect, url_for
from flask_login import current_user

from . import bp
from app import db
from app.models import FormTemplate, FormSection, FormItem, FormTemplateVersion
from app.models.core import Country
from app.services.imports.kobo_data_import_service import KoboDataImportService
from app.utils.advanced_validation import validate_upload_extension_and_mime
from app.utils.file_parsing import EXCEL_EXTENSIONS
from app.services.platform.user_analytics_service import log_admin_action
from app.utils.api_responses import json_bad_request, json_ok, json_server_error
from app.utils.api_helpers import get_json_safe
from app.routes.admin.shared import admin_required, system_manager_required


@bp.route("/kobo-data-import", methods=["GET"])
@admin_required
@system_manager_required
def kobo_data_import():
    """Render the KoBo data import wizard page."""
    from app.utils.form_localization import get_localized_template_name

    countries = Country.query.filter_by(status='Active').order_by(Country.name).all()

    templates = FormTemplate.query.all()

    template_choices = []
    for t in templates:
        name = get_localized_template_name(t)
        if name:
            template_choices.append({'id': t.id, 'name': name})
    template_choices.sort(key=lambda x: x['name'].lower())

    return render_template(
        "admin/templates/kobo_data_import.html",
        title="Import KoBo Data",
        countries=countries,
        template_choices=template_choices,
    )


@bp.route("/kobo-data-import/validate", methods=["POST"])
@admin_required
@system_manager_required
def kobo_data_import_validate():
    """Validate a KoBo data export Excel file before analysis (AJAX)."""
    if 'file' not in request.files:
        return json_bad_request('No file provided')

    f = request.files['file']
    if not f or f.filename == '':
        return json_bad_request('No file selected')

    valid, error_msg, ext = validate_upload_extension_and_mime(f, EXCEL_EXTENSIONS)
    if not valid:
        current_app.logger.info(
            'kobo_validate: rejected at mime/ext check – filename=%r ext_detected=%r error=%r',
            f.filename, ext, error_msg,
        )
        return json_ok(
            valid=False,
            message=error_msg or 'Invalid file type. Please upload an Excel file (.xlsx or .xls).',
            errors=[error_msg or 'Invalid file type.'],
            preview={'sheet_name': None, 'total_rows': 0, 'total_columns': 0},
        )

    file_bytes = f.read()
    current_app.logger.info(
        'kobo_validate: filename=%r ext=%r size=%d bytes',
        f.filename, ext, len(file_bytes),
    )

    if len(file_bytes) > 50 * 1024 * 1024:
        current_app.logger.info(
            'kobo_validate: rejected – file too large (%d bytes) filename=%r',
            len(file_bytes), f.filename,
        )
        return json_ok(
            valid=False,
            message='File too large (max 50 MB)',
            errors=['File too large (max 50 MB)'],
            preview={'sheet_name': None, 'total_rows': 0, 'total_columns': 0},
        )

    try:
        result = KoboDataImportService.validate_data_export(file_bytes)
        current_app.logger.info(
            'kobo_validate: result valid=%s message=%r filename=%r',
            result.get('valid'), result.get('message'), f.filename,
        )
        return json_ok(**result)
    except Exception as e:
        current_app.logger.error(
            'kobo_validate: unhandled exception filename=%r – %s', f.filename, e, exc_info=True,
        )
        return json_server_error('Validation failed. Please try again.')


@bp.route("/kobo-data-import/analyze", methods=["POST"])
@admin_required
@system_manager_required
def kobo_data_import_analyze():
    """Analyze an uploaded KoBo data export Excel file (AJAX)."""
    if 'file' not in request.files:
        return json_bad_request('No file provided')

    f = request.files['file']
    if not f or f.filename == '':
        return json_bad_request('No file selected')

    valid, error_msg, ext = validate_upload_extension_and_mime(f, EXCEL_EXTENSIONS)
    if not valid:
        current_app.logger.info(
            'kobo_analyze: rejected at mime/ext check – filename=%r ext_detected=%r error=%r',
            f.filename, ext, error_msg,
        )
        return json_bad_request(error_msg or 'Invalid file type')

    file_bytes = f.read()
    current_app.logger.info(
        'kobo_analyze: filename=%r ext=%r size=%d bytes',
        f.filename, ext, len(file_bytes),
    )

    if len(file_bytes) > 50 * 1024 * 1024:
        current_app.logger.info(
            'kobo_analyze: rejected – file too large (%d bytes) filename=%r',
            len(file_bytes), f.filename,
        )
        return json_bad_request('File too large (max 50 MB)')

    result = KoboDataImportService.analyze(file_bytes)

    if result.get('success'):
        upload_dir = os.path.join(current_app.instance_path, 'tmp')
        os.makedirs(upload_dir, exist_ok=True)
        file_id = str(uuid.uuid4())
        tmp_path = os.path.join(upload_dir, f'{file_id}.xlsx')
        with open(tmp_path, 'wb') as tf:
            tf.write(file_bytes)
        session['kobo_data_import_file'] = tmp_path
        session['kobo_data_import_id'] = file_id
        result['file_id'] = file_id
        current_app.logger.info(
            'kobo_analyze: file saved as file_id=%s filename=%r',
            file_id, f.filename,
        )
    else:
        current_app.logger.info(
            'kobo_analyze: analysis failed – filename=%r message=%r',
            f.filename, result.get('message'),
        )

    return json_ok(**result)


@bp.route("/kobo-data-import/match-entities", methods=["POST"])
@admin_required
@system_manager_required
def kobo_data_import_match():
    """Try to match entity names to countries (AJAX).

    If entity_column_index is provided, extracts all unique values from the
    stored temp file so matching covers every entity (not just samples).
    """
    data = get_json_safe()
    if not data:
        return json_bad_request('No data provided')

    entity_names = data.get('entity_names', [])
    entity_col_idx = data.get('entity_column_index')

    if entity_col_idx is not None:
        tmp_path = session.get('kobo_data_import_file')
        if tmp_path and os.path.exists(tmp_path):
            try:
                with open(tmp_path, 'rb') as f:
                    file_bytes = f.read()
                entity_names = KoboDataImportService.extract_unique_entities(
                    file_bytes,
                    int(entity_col_idx),
                    submission_filter=data.get('submission_filter', 'all'),
                    validation_status_column_index=data.get('validation_status_column_index'),
                )
            except Exception:
                pass

    if not entity_names:
        return json_bad_request(
            'No entity names found. Your submission filter may exclude every row, or the export may be '
            'missing _validation_status. Try "All rows" or re-export with validation metadata.'
        )

    mapping = KoboDataImportService.try_match_entities(entity_names)

    countries = Country.query.filter_by(status='Active').order_by(Country.name).all()
    country_list = [{'id': c.id, 'name': c.name} for c in countries]

    return json_ok(
        entity_mapping=mapping,
        countries=country_list,
    )


@bp.route("/kobo-data-import/preview", methods=["POST"])
@admin_required
@system_manager_required
def kobo_data_import_preview():
    """Return a preview of the mapped data for the AG Grid table (AJAX)."""
    data = get_json_safe()
    if not data:
        return json_bad_request('No configuration provided')

    file_id = data.get('file_id')
    stored_id = session.get('kobo_data_import_id')
    tmp_path = session.get('kobo_data_import_file')

    if not file_id or file_id != stored_id or not tmp_path or not os.path.exists(tmp_path):
        return json_bad_request('Upload session expired. Please re-upload the file.')

    try:
        with open(tmp_path, 'rb') as f:
            file_bytes = f.read()
    except Exception as e:
        return json_server_error(f'Cannot read uploaded file: {e}')

    from app.services.imports.kobo_data_import_service import KoboDataImportService
    result = KoboDataImportService.generate_preview(
        file_bytes,
        entity_column_index=data.get('entity_column_index'),
        columns_to_import=data.get('columns_to_import', []),
        entity_mapping=data.get('entity_mapping', {}),
        duplicate_strategy=data.get('duplicate_strategy', 'latest'),
        submission_time_column_index=data.get('submission_time_column_index'),
        submission_filter=data.get('submission_filter', 'all'),
        validation_status_column_index=data.get('validation_status_column_index'),
        max_rows=data.get('max_rows', 100),
        existing_template_id=data.get('existing_template_id'),
        column_to_item_mapping=data.get('column_to_item_mapping'),
    )
    return json_ok(**result)


@bp.route("/kobo-data-import/template-structure", methods=["POST"])
@admin_required
@system_manager_required
def kobo_data_import_template_structure():
    """Return sections and items for an existing template (AJAX)."""
    from app.utils.form_localization import get_localized_template_name

    data = get_json_safe()
    if not data or not data.get('template_id'):
        return json_bad_request('template_id is required')

    template_id = int(data['template_id'])
    template = FormTemplate.query.get(template_id)
    if not template:
        from app.utils.api_responses import json_not_found
        return json_not_found('Template not found')

    version = template.published_version
    if not version:
        version = template.versions.order_by(FormTemplateVersion.version_number.desc()).first()
    if not version:
        return json_bad_request('Template has no version')

    sections = FormSection.query.filter_by(
        template_id=template.id, version_id=version.id
    ).order_by(FormSection.order).all()

    section_ids = [sec.id for sec in sections]
    items_by_section_id = {}
    if section_ids:
        for item in (
            FormItem.query.filter(
                FormItem.template_id == template.id,
                FormItem.version_id == version.id,
                FormItem.section_id.in_(section_ids),
            )
            .order_by(FormItem.section_id, FormItem.order)
            .all()
        ):
            items_by_section_id.setdefault(item.section_id, []).append(item)

    result_sections = []
    all_items = []
    for sec in sections:
        items = items_by_section_id.get(sec.id, [])
        item_list = []
        for item in items:
            opts = list(item.allowed_disaggregation_options or [])
            has_slice_opts = any(o in opts for o in ('sex', 'age', 'sex_age'))
            item_info = {
                'id': item.id,
                'label': item.label or '',
                'type': item.type or item.item_type or '',
                'section_id': sec.id,
                'section_name': sec.name or 'Unnamed',
                'is_indicator': item.is_indicator,
                'unit': item.unit,
                'supports_disaggregation': bool(item.supports_disaggregation),
                'allowed_disaggregation_options': opts,
                'effective_sex_categories': list(item.effective_sex_categories) if item.is_indicator else [],
                'effective_age_groups': list(item.effective_age_groups) if item.is_indicator else [],
                'indirect_reach': bool(item.indirect_reach) if item.is_indicator else False,
                'show_disagg_mapping': bool(
                    item.is_indicator and item.supports_disaggregation and has_slice_opts
                ),
            }
            item_list.append(item_info)
            all_items.append(item_info)
        result_sections.append({
            'id': sec.id,
            'name': sec.name or 'Unnamed',
            'order': sec.order,
            'items': item_list,
        })

    return json_ok(
        template_id=template.id,
        template_name=get_localized_template_name(template, version=version),
        version_id=version.id,
        sections=result_sections,
        items=all_items,
    )


@bp.route("/kobo-data-import/map-columns", methods=["POST"])
@admin_required
@system_manager_required
def kobo_data_import_map_columns():
    """Auto-map KoBo columns to an existing template's items (AJAX)."""
    data = get_json_safe()
    if not data:
        return json_bad_request('No data provided')

    kobo_columns = data.get('kobo_columns', [])
    template_items = data.get('template_items', [])

    if not kobo_columns or not template_items:
        return json_bad_request('kobo_columns and template_items are required')

    mappings = KoboDataImportService.map_columns_to_template(kobo_columns, template_items)
    matched = sum(1 for m in mappings if m['item_id'] is not None)

    return json_ok(
        mappings=mappings,
        matched_count=matched,
        total_columns=len(mappings),
    )


@bp.route("/kobo-data-import/execute", methods=["POST"])
@admin_required
@system_manager_required
def kobo_data_import_execute():
    """Execute the KoBo data import (AJAX)."""
    data = get_json_safe()
    if not data:
        return json_bad_request('No configuration provided')

    file_id = data.get('file_id')
    stored_id = session.get('kobo_data_import_id')
    tmp_path = session.get('kobo_data_import_file')

    if not file_id or file_id != stored_id or not tmp_path or not os.path.exists(tmp_path):
        return json_bad_request('Upload session expired. Please re-upload the file.')

    try:
        with open(tmp_path, 'rb') as f:
            file_bytes = f.read()
    except Exception as e:
        return json_server_error(f'Cannot read uploaded file: {e}')

    sub_time_idx = None
    if data.get('submission_time_column_index') is not None:
        sub_time_idx = data['submission_time_column_index']

    vs_idx = data.get('validation_status_column_index')
    if vs_idx is not None:
        try:
            vs_idx = int(vs_idx)
        except (TypeError, ValueError):
            vs_idx = None

    config = {
        'template_name': data.get('template_name', 'KoBo Data Import'),
        'period_name': data.get('period_name', 'Imported'),
        'entity_column_index': data.get('entity_column_index'),
        'columns_to_import': data.get('columns_to_import', []),
        'entity_mapping': data.get('entity_mapping', {}),
        'create_template': data.get('create_template', True),
        'import_data': data.get('import_data', True),
        'owned_by': current_user.id,
        'duplicate_strategy': data.get('duplicate_strategy', 'latest'),
        'submission_time_column_index': sub_time_idx,
        'submission_filter': data.get('submission_filter', 'all'),
        'validation_status_column_index': vs_idx,
        'existing_template_id': data.get('existing_template_id'),
        'column_to_item_mapping': data.get('column_to_item_mapping', {}),
    }

    result = KoboDataImportService.execute_import(file_bytes, config)

    # Clean up temp file
    try:
        os.remove(tmp_path)
        session.pop('kobo_data_import_file', None)
        session.pop('kobo_data_import_id', None)
    except Exception:
        pass

    if result.get('success'):
        log_admin_action('kobo_data_import', {
            'template_id': result.get('template_id'),
            'counts': result.get('counts'),
        })

    return json_ok(**result)
