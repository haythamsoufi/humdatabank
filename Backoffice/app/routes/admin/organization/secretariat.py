"""Secretariat structure routes and translation APIs."""
import io
import json
import os
from datetime import datetime

import pandas as pd
from flask import render_template, redirect, url_for, request, flash, current_app, send_file, Response, stream_with_context
from flask_wtf import FlaskForm

from app.models import db
from app.models.core import Country
from app.models.organization import (
    NationalSociety,
    NSBranch,
    NSSubBranch,
    NSLocalUnit,
    SecretariatDivision,
    SecretariatDepartment,
    SecretariatRegionalOffice,
    SecretariatClusterOffice,
)
from app.services.organization.country_service import (
    assign_country_fds_member_user,
    countries_with_fds_member_query,
    fds_member_user_display_name,
    parse_fds_member_user_id,
    resolve_fds_member_user_id_from_import,
)
from app.services.organization.secretariat_regional_office_service import (
    assign_country_secretariat_regional_office,
)
from app.routes.admin.shared import (
    admin_permission_required,
    admin_permission_required_any,
    permission_required,
    permission_required_any,
)
from app.utils.request_utils import is_json_request
from app.utils.entity_groups import get_enabled_entity_groups
from app.utils.transactions import no_auto_transaction, request_transaction_rollback
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_formatting import choices_from_query
from app.utils.api_responses import (
    json_bad_request,
    json_error,
    json_ok,
    json_select_options,
    json_server_error,
    require_json_data,
    require_json_keys,
)
from app.utils.error_handling import handle_json_view_exception
from app.forms.organization import (
    CountryForm,
    NationalSocietyForm,
    NSBranchForm,
    NSSubBranchForm,
    NSLocalUnitForm,
    SecretariatDivisionForm,
    SecretariatDepartmentForm,
    SecretariatRegionalOfficeForm,
    SecretariatClusterOfficeForm,
    collect_translations,
    clear_translation_fields,
    populate_translation_fields,
    count_missing_name_translations,
    count_missing_translations_for_fields,
    secretariat_translation_fields,
    secretariat_translation_jobs,
    regional_office_translation_fields,
    stream_entity_translation_events,
    get_translation_codes,
    unique_iso_language_codes,
    iso_language_code,
)
from . import bp

# ==================== Secretariat Divisions ====================

@bp.route('/secretariat-divisions', methods=['GET'])
@admin_permission_required('admin.organization.manage')
def list_secretariat_divisions():
    """Redirect to unified Organization index with Secretariat tab."""
    return redirect(url_for('organization.index', tab='secretariat', secretariat_tab='divisions'))


@bp.route('/secretariat-divisions/new', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def new_secretariat_division():
    """Create a new Secretariat division."""
    form = SecretariatDivisionForm()

    if form.validate_on_submit():
        division = SecretariatDivision(
            name=form.name.data,
            code=form.code.data,
            description=form.description.data,
            is_active=form.is_active.data,
            display_order=form.display_order.data or 0
        )
        division.name_translations = collect_translations(form, 'name')
        db.session.add(division)
        db.session.flush()
        flash(f'Secretariat Division "{division.name}" created successfully.', 'success')
        return redirect(url_for('organization.list_secretariat_divisions'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=False,
                         entity=None,
                         entity_label='Secretariat Division',
                         icon='fas fa-building',
                         cancel_url=url_for('organization.index', tab='secretariat'))


@bp.route('/secretariat-divisions/<int:division_id>/edit', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def edit_secretariat_division(division_id):
    """Edit an existing Secretariat division."""
    division = SecretariatDivision.query.get_or_404(division_id)
    form = SecretariatDivisionForm(obj=division)

    if request.method == 'GET':
        clear_translation_fields(form, 'name')
        populate_translation_fields(form, division, 'name_translations', 'name')

    if form.validate_on_submit():
        division.name = form.name.data
        division.code = form.code.data
        division.description = form.description.data
        division.is_active = form.is_active.data
        division.display_order = form.display_order.data
        division.name_translations = collect_translations(form, 'name')

        db.session.flush()
        flash(f'Secretariat Division "{division.name}" updated successfully.', 'success')
        return redirect(url_for('organization.list_secretariat_divisions'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=True,
                         entity=division,
                         entity_label='Secretariat Division',
                         icon='fas fa-building',
                         cancel_url=url_for('organization.index', tab='secretariat'))


@bp.route('/secretariat-divisions/<int:division_id>/delete', methods=['POST'])
@admin_permission_required('admin.organization.manage')
def delete_secretariat_division(division_id):
    """Delete a Secretariat division."""
    division = SecretariatDivision.query.get_or_404(division_id)
    csrf_form = FlaskForm()

    if csrf_form.validate_on_submit():
        try:
            name = division.name
            db.session.delete(division)
            db.session.flush()
            flash(f'Secretariat Division "{name}" deleted successfully.', 'success')
        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")

    return redirect(url_for('organization.list_secretariat_divisions'))


# ==================== Secretariat Departments ====================

@bp.route('/secretariat-departments', methods=['GET'])
@admin_permission_required('admin.organization.manage')
def list_secretariat_departments():
    """Redirect to unified Organization index with Secretariat tab, preserving filters."""
    redirect_params = {'tab': 'secretariat', 'secretariat_tab': 'departments'}
    # Preserve known filters so index view applies them
    if 'division_id' in request.args:
        redirect_params['division_id'] = request.args.get('division_id')
    if 'active' in request.args:
        redirect_params['active'] = request.args.get('active')
    return redirect(url_for('organization.index', **redirect_params))


@bp.route('/secretariat-departments/new', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def new_secretariat_department():
    """Create a new Secretariat department."""
    form = SecretariatDepartmentForm()
    form.division_id.choices = choices_from_query(SecretariatDivision.query.order_by(SecretariatDivision.name))

    if form.validate_on_submit():
        department = SecretariatDepartment(
            name=form.name.data,
            code=form.code.data,
            description=form.description.data,
            division_id=form.division_id.data,
            is_active=form.is_active.data,
            display_order=form.display_order.data or 0
        )
        department.name_translations = collect_translations(form, 'name')
        db.session.add(department)
        db.session.flush()
        flash(f'Secretariat Department "{department.name}" created successfully.', 'success')
        return redirect(url_for('organization.list_secretariat_departments'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=False,
                         entity=None,
                         entity_label='Secretariat Department',
                         icon='fas fa-briefcase',
                         cancel_url=url_for('organization.index', tab='secretariat', secretariat_tab='departments'))


@bp.route('/secretariat-departments/<int:department_id>/edit', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def edit_secretariat_department(department_id):
    """Edit an existing Secretariat department."""
    department = SecretariatDepartment.query.get_or_404(department_id)
    form = SecretariatDepartmentForm(obj=department)
    form.division_id.choices = choices_from_query(SecretariatDivision.query.order_by(SecretariatDivision.name))

    if request.method == 'GET':
        clear_translation_fields(form, 'name')
        populate_translation_fields(form, department, 'name_translations', 'name')

    if form.validate_on_submit():
        department.name = form.name.data
        department.code = form.code.data
        department.description = form.description.data
        department.division_id = form.division_id.data
        department.is_active = form.is_active.data
        department.display_order = form.display_order.data
        department.name_translations = collect_translations(form, 'name')

        db.session.flush()
        flash(f'Secretariat Department "{department.name}" updated successfully.', 'success')
        return redirect(url_for('organization.list_secretariat_departments'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=True,
                         entity=department,
                         entity_label='Secretariat Department',
                         icon='fas fa-briefcase',
                         cancel_url=url_for('organization.index', tab='secretariat', secretariat_tab='departments'))


@bp.route('/secretariat-departments/<int:department_id>/delete', methods=['POST'])
@admin_permission_required('admin.organization.manage')
def delete_secretariat_department(department_id):
    """Delete a Secretariat department."""
    department = SecretariatDepartment.query.get_or_404(department_id)
    csrf_form = FlaskForm()

    if csrf_form.validate_on_submit():
        try:
            name = department.name
            db.session.delete(department)
            db.session.flush()
            flash(f'Secretariat Department "{name}" deleted successfully.', 'success')
        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")

    return redirect(url_for('organization.list_secretariat_departments'))


# ==================== Secretariat Regional Offices ====================

@bp.route('/secretariat-regional-offices', methods=['GET'])
@admin_permission_required('admin.organization.manage')
def list_secretariat_regional_offices():
    """Redirect to unified Organization index with Secretariat tab to Regions sub-tab."""
    return redirect(url_for('organization.index', tab='secretariat', secretariat_tab='regions'))


@bp.route('/secretariat-regional-offices/new', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def new_secretariat_regional_office():
    """Create a new Secretariat regional office."""
    form = SecretariatRegionalOfficeForm()

    if form.validate_on_submit():
        region = SecretariatRegionalOffice(
            name=form.name.data,
            short_name=(form.short_name.data or None),
            code=form.code.data,
            description=form.description.data,
            is_active=form.is_active.data,
            display_order=form.display_order.data or 0
        )
        region.name_translations = collect_translations(form, 'name')
        region.short_name_translations = collect_translations(form, 'short_name')
        db.session.add(region)
        db.session.flush()
        flash(f'Secretariat Regional Office "{region.name}" created successfully.', 'success')
        return redirect(url_for('organization.list_secretariat_regional_offices'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=False,
                         entity=None,
                         entity_label='Secretariat Regional Office',
                         icon='fas fa-globe-europe',
                         cancel_url=url_for('organization.index', tab='secretariat', secretariat_tab='regions'))


@bp.route('/secretariat-regional-offices/<int:region_id>/edit', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def edit_secretariat_regional_office(region_id):
    """Edit an existing Secretariat regional office."""
    region = SecretariatRegionalOffice.query.get_or_404(region_id)
    form = SecretariatRegionalOfficeForm(obj=region)

    if request.method == 'GET':
        clear_translation_fields(form, 'name')
        clear_translation_fields(form, 'short_name')
        populate_translation_fields(form, region, 'name_translations', 'name')
        populate_translation_fields(form, region, 'short_name_translations', 'short_name')

    if form.validate_on_submit():
        region.name = form.name.data
        region.short_name = form.short_name.data or None
        region.code = form.code.data
        region.description = form.description.data
        region.is_active = form.is_active.data
        region.display_order = form.display_order.data
        region.name_translations = collect_translations(form, 'name')
        region.short_name_translations = collect_translations(form, 'short_name')

        db.session.flush()
        flash(f'Secretariat Regional Office "{region.name}" updated successfully.', 'success')
        return redirect(url_for('organization.list_secretariat_regional_offices'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=True,
                         entity=region,
                         entity_label='Secretariat Regional Office',
                         icon='fas fa-globe-europe',
                         cancel_url=url_for('organization.index', tab='secretariat', secretariat_tab='regions'))


@bp.route('/secretariat-regional-offices/<int:region_id>/delete', methods=['POST'])
@admin_permission_required('admin.organization.manage')
def delete_secretariat_regional_office(region_id):
    """Delete a Secretariat regional office."""
    region = SecretariatRegionalOffice.query.get_or_404(region_id)
    csrf_form = FlaskForm()

    if csrf_form.validate_on_submit():
        try:
            name = region.name
            db.session.delete(region)
            db.session.flush()
            flash(f'Secretariat Regional Office "{name}" deleted successfully.', 'success')
        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")

    return redirect(url_for('organization.list_secretariat_regional_offices'))


# ==================== Secretariat Cluster Offices ====================

@bp.route('/secretariat-cluster-offices', methods=['GET'])
@admin_permission_required('admin.organization.manage')
def list_secretariat_cluster_offices():
    """Redirect to unified Organization index with Secretariat tab to Clusters sub-tab."""
    return redirect(url_for('organization.index', tab='secretariat', secretariat_tab='clusters'))


@bp.route('/secretariat-cluster-offices/new', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def new_secretariat_cluster_office():
    """Create a new Secretariat cluster office."""
    form = SecretariatClusterOfficeForm()
    form.regional_office_id.choices = choices_from_query(SecretariatRegionalOffice.query.order_by(SecretariatRegionalOffice.name))

    if form.validate_on_submit():
        cluster = SecretariatClusterOffice(
            name=form.name.data,
            code=form.code.data,
            description=form.description.data,
            regional_office_id=form.regional_office_id.data,
            is_active=form.is_active.data,
            display_order=form.display_order.data or 0
        )
        cluster.name_translations = collect_translations(form, 'name')
        db.session.add(cluster)
        db.session.flush()
        flash(f'Secretariat Cluster Office "{cluster.name}" created successfully.', 'success')
        return redirect(url_for('organization.list_secretariat_cluster_offices'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=False,
                         entity=None,
                         entity_label='Secretariat Cluster Office',
                         icon='fas fa-project-diagram',
                         cancel_url=url_for('organization.index', tab='secretariat', secretariat_tab='clusters'))


@bp.route('/secretariat-cluster-offices/<int:cluster_id>/edit', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def edit_secretariat_cluster_office(cluster_id):
    """Edit an existing Secretariat cluster office."""
    cluster = SecretariatClusterOffice.query.get_or_404(cluster_id)
    form = SecretariatClusterOfficeForm(obj=cluster)
    form.regional_office_id.choices = choices_from_query(SecretariatRegionalOffice.query.order_by(SecretariatRegionalOffice.name))

    if request.method == 'GET':
        clear_translation_fields(form, 'name')
        populate_translation_fields(form, cluster, 'name_translations', 'name')

    if form.validate_on_submit():
        cluster.name = form.name.data
        cluster.code = form.code.data
        cluster.description = form.description.data
        cluster.regional_office_id = form.regional_office_id.data
        cluster.is_active = form.is_active.data
        cluster.display_order = form.display_order.data
        cluster.name_translations = collect_translations(form, 'name')

        db.session.flush()
        flash(f'Secretariat Cluster Office "{cluster.name}" updated successfully.', 'success')
        return redirect(url_for('organization.list_secretariat_cluster_offices'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=True,
                         entity=cluster,
                         entity_label='Secretariat Cluster Office',
                         icon='fas fa-project-diagram',
                         cancel_url=url_for('organization.index', tab='secretariat', secretariat_tab='clusters'))


@bp.route('/secretariat-cluster-offices/<int:cluster_id>/delete', methods=['POST'])
@admin_permission_required('admin.organization.manage')
def delete_secretariat_cluster_office(cluster_id):
    """Delete a Secretariat cluster office."""
    cluster = SecretariatClusterOffice.query.get_or_404(cluster_id)
    csrf_form = FlaskForm()

    if csrf_form.validate_on_submit():
        try:
            name = cluster.name
            db.session.delete(cluster)
            db.session.flush()
            flash(f'Secretariat Cluster Office "{name}" deleted successfully.', 'success')
        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")

    return redirect(url_for('organization.list_secretariat_cluster_offices'))
# ==================== API Endpoint for Cluster by Region ====================

@bp.route('/api/cluster-offices/<int:regional_office_id>', methods=['GET'])
@permission_required('admin.organization.manage')
def api_get_clusters_by_region(regional_office_id):
    """API endpoint to get clusters for a specific regional office."""
    clusters = SecretariatClusterOffice.query.filter_by(regional_office_id=regional_office_id, is_active=True).order_by(SecretariatClusterOffice.name).all()
    return json_select_options(clusters)
@bp.route('/api/departments/<int:division_id>', methods=['GET'])
@permission_required('admin.organization.manage')
def api_get_departments_by_division(division_id):
    """API endpoint to get departments for a specific division."""
    departments = SecretariatDepartment.query.filter_by(division_id=division_id, is_active=True).order_by(SecretariatDepartment.name).all()
    return json_select_options(departments)


# ==================== Auto-Translate API Endpoints ====================

@bp.route('/api/translation-counts', methods=['GET'])
@permission_required('admin.organization.manage')
def api_get_translation_counts():
    """API endpoint to get translation counts for organization entities."""
    try:
        entity_type = request.args.get('entity_type')
        if not entity_type:
            return json_bad_request('Entity type is required')

        # Initialize counts for all languages the UI actually shows
        counts = {lang_code: 0 for lang_code in get_translation_codes()}

        def _merge_counts(extra_counts: dict[str, int]):
            for lang_key, value in extra_counts.items():
                code = iso_language_code(lang_key)
                if not code or code == "en":
                    continue
                counts[code] = counts.get(code, 0) + value

        if entity_type == 'countries':
            _merge_counts(count_missing_name_translations(Country.query.all()))

        elif entity_type == 'national_societies':
            _merge_counts(count_missing_name_translations(NationalSociety.query.all()))

        elif entity_type == 'ns_structure':
            entities = (
                NSBranch.query.all()
                + NSSubBranch.query.all()
                + NSLocalUnit.query.all()
            )
            _merge_counts(count_missing_name_translations(entities))

        elif entity_type == 'secretariat':
            for entities, fields, _, fields_resolver in secretariat_translation_jobs():
                _merge_counts(count_missing_translations_for_fields(entities, fields, fields_resolver))

        elif entity_type in (
            'secretariat_divisions',
            'secretariat_departments',
            'secretariat_regions',
            'secretariat_clusters',
        ):
            entities, fields, entity_label = secretariat_translation_fields(entity_type)
            if entities is None:
                return json_bad_request('Invalid entity type')
            fields_resolver = (
                regional_office_translation_fields
                if entity_type == 'secretariat_regions'
                else None
            )
            _merge_counts(count_missing_translations_for_fields(entities, fields, fields_resolver))

        else:
            return json_bad_request('Invalid entity type')

        return json_ok(counts=counts)

    except Exception as e:
        current_app.logger.error(f"Error getting translation counts: {e}")
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route('/api/auto-translate-organizations', methods=['POST'])
@permission_required('admin.organization.manage')
@no_auto_transaction
def api_auto_translate_organizations():
    """API endpoint to auto-translate organization entities with real-time progress streaming."""
    try:
        from app.services.translation.auto_translator import get_auto_translator
        import json

        data = get_json_safe()
        err = require_json_keys(data, ['entity_type', 'target_languages'])
        if err:
            return err

        entity_type = data.get('entity_type')
        target_languages = data.get('target_languages', [])
        translation_service = data.get('translation_service', 'ifrc')

        if not entity_type or not str(entity_type).strip():
            return json_bad_request('Entity type is required')

        if not target_languages:
            return json_bad_request('Target languages are required')

        # Honor the languages the user selected (ISO base codes, e.g. ru_RU -> ru).
        # Do not require them to appear in stale Config.TRANSLATABLE_LANGUAGES.
        normalized_languages = unique_iso_language_codes(target_languages, exclude_en=True)

        if not normalized_languages:
            return json_bad_request('Invalid target languages')

        def generate():
            """Generator function that yields HTTP streaming events as translations complete."""
            try:
                auto_translator = get_auto_translator()

                # Process translations and stream results (combining count and process in one pass)
                if entity_type == 'countries':
                    for event in stream_entity_translation_events(
                        Country.query.all(),
                        'country',
                        [('name', 'name_translations')],
                        normalized_languages,
                        auto_translator,
                        translation_service,
                    ):
                        yield event
                    return

                elif entity_type == 'national_societies':
                    for event in stream_entity_translation_events(
                        NationalSociety.query.all(),
                        'national_society',
                        [('name', 'name_translations')],
                        normalized_languages,
                        auto_translator,
                        translation_service,
                    ):
                        yield event
                    return

                elif entity_type == 'ns_structure':
                    yield f"data: {json.dumps({'type': 'error', 'message': 'NS Structure entities do not currently support translations. Translation fields need to be added to the models first.'})}\n\n"
                    return

                elif entity_type == 'secretariat':
                    total_processed = 0
                    total_items = 0
                    total_success = 0
                    total_errors = 0
                    started = False
                    for entities, fields, entity_label, fields_resolver in secretariat_translation_jobs():
                        for event in stream_entity_translation_events(
                            entities,
                            entity_label,
                            fields,
                            normalized_languages,
                            auto_translator,
                            translation_service,
                            fields_for_entity=fields_resolver,
                            emit_complete=False,
                        ):
                            payload = json.loads(event.replace('data: ', '').strip())
                            if payload.get('type') == 'start':
                                if not started:
                                    started = True
                                    total_items += payload.get('total', 0)
                                    yield f"data: {json.dumps({'type': 'start', 'total': total_items})}\n\n"
                                else:
                                    total_items += payload.get('total', 0)
                            elif payload.get('type') == 'progress':
                                total_processed = payload.get('processed', total_processed)
                                total_success = payload.get('success', total_success)
                                total_errors = payload.get('error', total_errors)
                                payload['total'] = total_items
                                yield f"data: {json.dumps(payload)}\n\n"
                    yield f"data: {json.dumps({'type': 'complete', 'processed': total_processed, 'total': total_items, 'success': total_success, 'error': total_errors})}\n\n"
                    return

                elif entity_type in (
                    'secretariat_divisions',
                    'secretariat_departments',
                    'secretariat_regions',
                    'secretariat_clusters',
                ):
                    entities, fields, entity_label = secretariat_translation_fields(entity_type)
                    if entities is None:
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Invalid entity type'})}\n\n"
                        return
                    fields_resolver = (
                        regional_office_translation_fields
                        if entity_type == 'secretariat_regions'
                        else None
                    )
                    for event in stream_entity_translation_events(
                        entities,
                        entity_label,
                        fields,
                        normalized_languages,
                        auto_translator,
                        translation_service,
                        fields_for_entity=fields_resolver,
                    ):
                        yield event
                    return

                else:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Invalid entity type'})}\n\n"
                    return

            except Exception as e:
                current_app.logger.error(f"Error in translation stream: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': GENERIC_ERROR_MESSAGE})}\n\n"

        # Return HTTP streaming response
        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',  # Disable buffering in nginx
                'Connection': 'keep-alive'
            }
        )

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error auto-translating organizations: {e}")
        return json_server_error(GENERIC_ERROR_MESSAGE)
