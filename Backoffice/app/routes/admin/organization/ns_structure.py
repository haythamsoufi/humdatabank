"""National Society and NS structure routes and APIs."""
import io
import json
import os
from datetime import datetime

import pandas as pd
from flask import render_template, redirect, url_for, request, flash, current_app
from app.extensions import limiter
from app.routes.admin.shared import rbac_guard_audit_exempt
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
    NS_STATUS_ACTIVE,
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
    json_form_errors,
    json_ok,
    json_select_options,
    json_server_error,
    require_json_data,
    require_json_keys,
)
from app.utils.sector_logo_urls import ns_logo_url
from app.utils.error_handling import handle_json_view_exception
from config.config import Config
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
    commit_translation_entity,
)
from app.routes.admin.system_admin.helpers import (
    _delete_logo_file,
    _safe_logo_mimetype,
    _save_logo_file,
)
from app.services.platform import storage_service as storage
from . import bp

NS_LOGO_SUBDIR = "ns"


def _ns_logo_stem(ns: NationalSociety) -> str:
    country = getattr(ns, "country", None)
    if country is None and ns.country_id:
        country = Country.query.get(ns.country_id)
    iso3 = (getattr(country, "iso3", None) or "").strip().upper()
    if len(iso3) == 3 and iso3.isalpha():
        return iso3
    code = (ns.code or "").strip()
    return code or f"ns-{ns.id}"


def _apply_ns_logo_upload(ns: NationalSociety, form: NationalSocietyForm) -> None:
    file_storage = form.logo_file.data
    if not file_storage or not getattr(file_storage, "filename", None):
        return
    if ns.logo_filename:
        _delete_logo_file(ns.logo_filename, subdir=NS_LOGO_SUBDIR)
    saved = _save_logo_file(file_storage, _ns_logo_stem(ns), subdir=NS_LOGO_SUBDIR)
    if saved:
        ns.logo_filename = saved

# ==================== National Societies ====================

@bp.route('/national-societies/new', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def new_national_society():
    """Create a new National Society."""
    form = NationalSocietyForm()
    form.country_id.choices = choices_from_query(Country.query.order_by(Country.name))

    if form.validate_on_submit():
        ns = NationalSociety(
            name=form.name.data,
            code=form.code.data,
            description=form.description.data,
            country_id=form.country_id.data,
            status=form.status.data or NS_STATUS_ACTIVE,
            display_order=form.display_order.data or 0,
        )
        ns.name_translations = collect_translations(form, 'name')
        db.session.add(ns)
        db.session.flush()
        _apply_ns_logo_upload(ns, form)
        flash(f'National Society "{ns.name}" created successfully.', 'success')
        return redirect(url_for('organization.index', tab='nss'))

    return render_template('admin/organization/edit_entity.html',
                           form=form,
                           is_edit=False,
                           entity=None,
                           entity_label='National Society',
                           icon='fas fa-hands-helping',
                           cancel_url=url_for('organization.index', tab='nss'))


@bp.route('/national-societies/<int:ns_id>/data', methods=['GET'])
@admin_permission_required('admin.organization.manage')
def get_national_society_data(ns_id):
    """JSON payload for the Edit National Society modal."""
    ns = NationalSociety.query.get_or_404(ns_id)
    return json_ok(
        id=ns.id,
        name=ns.name or '',
        code=ns.code or '',
        description=ns.description or '',
        country_id=ns.country_id,
        country_name=ns.country.name if ns.country else '',
        status=ns.status_label,
        is_active=bool(ns.is_active),
        display_order=ns.display_order or 0,
        logo_url=ns_logo_url(ns) or '',
        name_translations=ns.name_translations or {},
    )


@bp.route('/national-societies/<int:ns_id>/edit', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def edit_national_society(ns_id):
    """Edit an existing National Society."""
    ns = NationalSociety.query.get_or_404(ns_id)
    form = NationalSocietyForm()
    form.country_id.choices = choices_from_query(Country.query.order_by(Country.name))

    if request.method == 'GET':
        # Populate non-translation fields from the NS object
        form.name.data = ns.name
        form.code.data = ns.code
        form.description.data = ns.description
        form.country_id.data = ns.country_id
        form.status.data = ns.status_label
        form.display_order.data = ns.display_order

        # Clear translation fields first to ensure they start empty
        clear_translation_fields(form, 'name')
        # Now populate from actual translations in name_translations (only if they exist)
        populate_translation_fields(form, ns, 'name_translations', 'name')

    if form.validate_on_submit():
        ns.name = form.name.data
        ns.code = form.code.data
        ns.description = form.description.data
        ns.country_id = form.country_id.data
        ns.status = form.status.data or NS_STATUS_ACTIVE
        ns.display_order = form.display_order.data or 0
        ns.name_translations = collect_translations(form, 'name')
        _apply_ns_logo_upload(ns, form)

        db.session.flush()
        if is_json_request():
            return json_ok(message=f'National Society "{ns.name}" updated successfully.')
        flash(f'National Society "{ns.name}" updated successfully.', 'success')
        return redirect(url_for('organization.index', tab='nss'))

    if is_json_request() and request.method == 'POST':
        return json_form_errors(form)

    return render_template('admin/organization/edit_entity.html',
                           form=form,
                           is_edit=True,
                           entity=ns,
                           entity_label='National Society',
                           icon='fas fa-hands-helping',
                           cancel_url=url_for('organization.index', tab='nss'))


@bp.route('/national-societies/<int:ns_id>/delete', methods=['POST'])
@admin_permission_required('admin.organization.manage')
def delete_national_society(ns_id):
    """Delete a National Society."""
    ns = NationalSociety.query.get_or_404(ns_id)
    csrf_form = FlaskForm()

    if csrf_form.validate_on_submit():
        try:
            name = ns.name
            db.session.delete(ns)
            db.session.flush()
            flash(f'National Society "{name}" deleted successfully.', 'success')
        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")

    return redirect(url_for('organization.index', tab='nss'))


@bp.route('/national-societies/<int:ns_id>/logo', methods=['GET'])
@limiter.exempt
@rbac_guard_audit_exempt("Intentionally public to allow NS logo rendering without admin session.")
def national_society_logo(ns_id):
    ns = NationalSociety.query.get_or_404(ns_id)
    if not ns.logo_filename:
        return ("", 404)
    rel_path = f"{NS_LOGO_SUBDIR}/{ns.logo_filename}"
    if not storage.exists(storage.SYSTEM, rel_path):
        return ("", 404)
    return storage.stream_response(
        storage.SYSTEM, rel_path,
        filename=ns.logo_filename, as_attachment=False,
        mimetype=_safe_logo_mimetype(ns.logo_filename),
    )


# ==================== NS Branches ====================

@bp.route('/ns-branches', methods=['GET'])
@admin_permission_required('admin.organization.manage')
def list_ns_branches():
    """List all NS branches."""
    # Get filter parameters
    country_id = request.args.get('country_id', type=int)
    active_only = request.args.get('active', 'true') == 'true'

    query = NSBranch.query

    if country_id:
        query = query.filter_by(country_id=country_id)
    if active_only:
        query = query.filter_by(is_active=True)

    branches = query.order_by(NSBranch.country_id, NSBranch.display_order, NSBranch.name).all()
    countries = Country.query.order_by(Country.name).all()

    return render_template('admin/organization/ns_branches.html',
                         branches=branches,
                         countries=countries,
                         selected_country_id=country_id,
                         active_only=active_only)


@bp.route('/ns-branches/new', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def new_ns_branch():
    """Create a new NS branch."""
    form = NSBranchForm()
    form.country_id.choices = choices_from_query(Country.query.order_by(Country.name))

    if form.validate_on_submit():
        branch = NSBranch(
            name=form.name.data,
            code=form.code.data,
            description=form.description.data,
            country_id=form.country_id.data,
            address=form.address.data,
            city=form.city.data,
            postal_code=form.postal_code.data,
            coordinates=form.coordinates.data,
            phone=form.phone.data,
            email=form.email.data,
            website=form.website.data,
            is_active=form.is_active.data,
            established_date=form.established_date.data,
            display_order=form.display_order.data or 0
        )
        branch.name_translations = collect_translations(form, 'name')
        db.session.add(branch)
        db.session.flush()
        flash(f'NS Branch "{branch.name}" created successfully.', 'success')
        return redirect(url_for('organization.list_ns_branches'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=False,
                         entity=None,
                         entity_label='NS Branch',
                         icon='fas fa-code-branch',
                         cancel_url=url_for('organization.list_ns_branches'))


@bp.route('/ns-branches/<int:branch_id>/edit', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def edit_ns_branch(branch_id):
    """Edit an existing NS branch."""
    branch = NSBranch.query.get_or_404(branch_id)
    form = NSBranchForm(obj=branch)
    form.country_id.choices = choices_from_query(Country.query.order_by(Country.name))

    if request.method == 'GET':
        clear_translation_fields(form, 'name')
        populate_translation_fields(form, branch, 'name_translations', 'name')

    if form.validate_on_submit():
        branch.name = form.name.data
        branch.code = form.code.data
        branch.description = form.description.data
        branch.country_id = form.country_id.data
        branch.address = form.address.data
        branch.city = form.city.data
        branch.postal_code = form.postal_code.data
        branch.coordinates = form.coordinates.data
        branch.phone = form.phone.data
        branch.email = form.email.data
        branch.website = form.website.data
        branch.is_active = form.is_active.data
        branch.established_date = form.established_date.data
        branch.display_order = form.display_order.data
        branch.name_translations = collect_translations(form, 'name')

        db.session.flush()
        flash(f'NS Branch "{branch.name}" updated successfully.', 'success')
        return redirect(url_for('organization.list_ns_branches'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=True,
                         entity=branch,
                         entity_label='NS Branch',
                         icon='fas fa-code-branch',
                         cancel_url=url_for('organization.list_ns_branches'))


@bp.route('/ns-branches/<int:branch_id>/delete', methods=['POST'])
@admin_permission_required('admin.organization.manage')
def delete_ns_branch(branch_id):
    """Delete an NS branch."""
    branch = NSBranch.query.get_or_404(branch_id)
    csrf_form = FlaskForm()

    if csrf_form.validate_on_submit():
        try:
            name = branch.name
            db.session.delete(branch)
            db.session.flush()
            flash(f'NS Branch "{name}" deleted successfully.', 'success')
        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")

    return redirect(url_for('organization.list_ns_branches'))


# ==================== NS Sub-branches ====================

@bp.route('/ns-subbranches', methods=['GET'])
@admin_permission_required('admin.organization.manage')
def list_ns_subbranches():
    """List all NS sub-branches."""
    # Get filter parameters
    branch_id = request.args.get('branch_id', type=int)
    active_only = request.args.get('active', 'true') == 'true'

    query = NSSubBranch.query.join(NSBranch)

    if branch_id:
        query = query.filter(NSSubBranch.branch_id == branch_id)
    if active_only:
        query = query.filter(NSSubBranch.is_active == True)

    subbranches = query.order_by(NSBranch.country_id, NSSubBranch.branch_id, NSSubBranch.display_order, NSSubBranch.name).all()
    branches = NSBranch.query.order_by(NSBranch.name).all()

    return render_template('admin/organization/ns_subbranches.html',
                         subbranches=subbranches,
                         branches=branches,
                         selected_branch_id=branch_id,
                         active_only=active_only)


@bp.route('/ns-subbranches/new', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def new_ns_subbranch():
    """Create a new NS sub-branch."""
    form = NSSubBranchForm()
    form.branch_id.choices = choices_from_query(
            NSBranch.query.join(Country).order_by(Country.name, NSBranch.name),
            label_func=lambda b: f"{b.country.name} - {b.name}"
        )

    if form.validate_on_submit():
        subbranch = NSSubBranch(
            name=form.name.data,
            code=form.code.data,
            description=form.description.data,
            branch_id=form.branch_id.data,
            address=form.address.data,
            city=form.city.data,
            postal_code=form.postal_code.data,
            coordinates=form.coordinates.data,
            phone=form.phone.data,
            email=form.email.data,
            is_active=form.is_active.data,
            established_date=form.established_date.data,
            display_order=form.display_order.data or 0
        )
        subbranch.name_translations = collect_translations(form, 'name')
        db.session.add(subbranch)
        db.session.flush()
        flash(f'NS Sub-branch "{subbranch.name}" created successfully.', 'success')
        return redirect(url_for('organization.list_ns_subbranches'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=False,
                         entity=None,
                         entity_label='NS Sub-branch',
                         icon='fas fa-network-wired',
                         cancel_url=url_for('organization.list_ns_subbranches'))


@bp.route('/ns-subbranches/<int:subbranch_id>/edit', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def edit_ns_subbranch(subbranch_id):
    """Edit an existing NS sub-branch."""
    subbranch = NSSubBranch.query.get_or_404(subbranch_id)
    form = NSSubBranchForm(obj=subbranch)
    form.branch_id.choices = choices_from_query(
            NSBranch.query.join(Country).order_by(Country.name, NSBranch.name),
            label_func=lambda b: f"{b.country.name} - {b.name}"
        )

    if request.method == 'GET':
        clear_translation_fields(form, 'name')
        populate_translation_fields(form, subbranch, 'name_translations', 'name')

    if form.validate_on_submit():
        subbranch.name = form.name.data
        subbranch.code = form.code.data
        subbranch.description = form.description.data
        subbranch.branch_id = form.branch_id.data
        subbranch.address = form.address.data
        subbranch.city = form.city.data
        subbranch.postal_code = form.postal_code.data
        subbranch.coordinates = form.coordinates.data
        subbranch.phone = form.phone.data
        subbranch.email = form.email.data
        subbranch.is_active = form.is_active.data
        subbranch.established_date = form.established_date.data
        subbranch.display_order = form.display_order.data
        subbranch.name_translations = collect_translations(form, 'name')

        db.session.flush()
        flash(f'NS Sub-branch "{subbranch.name}" updated successfully.', 'success')
        return redirect(url_for('organization.list_ns_subbranches'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=True,
                         entity=subbranch,
                         entity_label='NS Sub-branch',
                         icon='fas fa-network-wired',
                         cancel_url=url_for('organization.list_ns_subbranches'))


@bp.route('/ns-subbranches/<int:subbranch_id>/delete', methods=['POST'])
@admin_permission_required('admin.organization.manage')
def delete_ns_subbranch(subbranch_id):
    """Delete an NS sub-branch."""
    subbranch = NSSubBranch.query.get_or_404(subbranch_id)
    csrf_form = FlaskForm()

    if csrf_form.validate_on_submit():
        try:
            name = subbranch.name
            db.session.delete(subbranch)
            db.session.flush()
            flash(f'NS Sub-branch "{name}" deleted successfully.', 'success')
        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")

    return redirect(url_for('organization.list_ns_subbranches'))


# ==================== NS Local Units ====================

@bp.route('/ns-localunits', methods=['GET'])
@admin_permission_required('admin.organization.manage')
def list_ns_localunits():
    """List all NS local units."""
    # Get filter parameters
    branch_id = request.args.get('branch_id', type=int)
    subbranch_id = request.args.get('subbranch_id', type=int)
    active_only = request.args.get('active', 'true') == 'true'

    query = NSLocalUnit.query.join(NSBranch)

    if branch_id:
        query = query.filter(NSLocalUnit.branch_id == branch_id)
    if subbranch_id:
        query = query.filter(NSLocalUnit.subbranch_id == subbranch_id)
    if active_only:
        query = query.filter(NSLocalUnit.is_active == True)

    localunits = query.order_by(NSBranch.country_id, NSLocalUnit.branch_id, NSLocalUnit.display_order, NSLocalUnit.name).all()
    branches = NSBranch.query.order_by(NSBranch.name).all()

    return render_template('admin/organization/ns_localunits.html',
                         localunits=localunits,
                         branches=branches,
                         selected_branch_id=branch_id,
                         active_only=active_only)


@bp.route('/ns-localunits/new', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def new_ns_localunit():
    """Create a new NS local unit."""
    form = NSLocalUnitForm()
    form.branch_id.choices = choices_from_query(
            NSBranch.query.join(Country).order_by(Country.name, NSBranch.name),
            label_func=lambda b: f"{b.country.name} - {b.name}"
        )
    form.subbranch_id.choices = choices_from_query(
            NSSubBranch.query.order_by(NSSubBranch.name),
            empty_option=('', 'None (Direct to Branch)')
        )

    if form.validate_on_submit():
        localunit = NSLocalUnit(
            name=form.name.data,
            code=form.code.data,
            description=form.description.data,
            branch_id=form.branch_id.data,
            subbranch_id=form.subbranch_id.data if form.subbranch_id.data else None,
            address=form.address.data,
            city=form.city.data,
            postal_code=form.postal_code.data,
            coordinates=form.coordinates.data,
            phone=form.phone.data,
            email=form.email.data,
            is_active=form.is_active.data,
            established_date=form.established_date.data,
            display_order=form.display_order.data or 0
        )
        localunit.name_translations = collect_translations(form, 'name')
        db.session.add(localunit)
        db.session.flush()
        flash(f'NS Local Unit "{localunit.name}" created successfully.', 'success')
        return redirect(url_for('organization.list_ns_localunits'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=False,
                         entity=None,
                         entity_label='NS Local Unit',
                         icon='fas fa-map-marker-alt',
                         cancel_url=url_for('organization.list_ns_localunits'))


@bp.route('/ns-localunits/<int:localunit_id>/edit', methods=['GET', 'POST'])
@admin_permission_required('admin.organization.manage')
def edit_ns_localunit(localunit_id):
    """Edit an existing NS local unit."""
    localunit = NSLocalUnit.query.get_or_404(localunit_id)
    form = NSLocalUnitForm(obj=localunit)
    form.branch_id.choices = choices_from_query(
            NSBranch.query.join(Country).order_by(Country.name, NSBranch.name),
            label_func=lambda b: f"{b.country.name} - {b.name}"
        )
    form.subbranch_id.choices = choices_from_query(
            NSSubBranch.query.order_by(NSSubBranch.name),
            empty_option=('', 'None (Direct to Branch)')
        )

    if request.method == 'GET':
        clear_translation_fields(form, 'name')
        populate_translation_fields(form, localunit, 'name_translations', 'name')

    if form.validate_on_submit():
        localunit.name = form.name.data
        localunit.code = form.code.data
        localunit.description = form.description.data
        localunit.branch_id = form.branch_id.data
        localunit.subbranch_id = form.subbranch_id.data if form.subbranch_id.data else None
        localunit.address = form.address.data
        localunit.city = form.city.data
        localunit.postal_code = form.postal_code.data
        localunit.coordinates = form.coordinates.data
        localunit.phone = form.phone.data
        localunit.email = form.email.data
        localunit.is_active = form.is_active.data
        localunit.established_date = form.established_date.data
        localunit.display_order = form.display_order.data
        localunit.name_translations = collect_translations(form, 'name')

        db.session.flush()
        flash(f'NS Local Unit "{localunit.name}" updated successfully.', 'success')
        return redirect(url_for('organization.list_ns_localunits'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=True,
                         entity=localunit,
                         entity_label='NS Local Unit',
                         icon='fas fa-map-marker-alt',
                         cancel_url=url_for('organization.list_ns_localunits'))


@bp.route('/ns-localunits/<int:localunit_id>/delete', methods=['POST'])
@admin_permission_required('admin.organization.manage')
def delete_ns_localunit(localunit_id):
    """Delete an NS local unit."""
    localunit = NSLocalUnit.query.get_or_404(localunit_id)
    csrf_form = FlaskForm()

    if csrf_form.validate_on_submit():
        try:
            name = localunit.name
            db.session.delete(localunit)
            db.session.flush()
            flash(f'NS Local Unit "{name}" deleted successfully.', 'success')
        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")

    return redirect(url_for('organization.list_ns_localunits'))
@bp.route('/api/branches/<int:country_id>', methods=['GET'])
@permission_required('admin.organization.manage')
def api_get_branches_by_country(country_id):
    """API endpoint to get branches for a specific country."""
    branches = NSBranch.query.filter_by(country_id=country_id, is_active=True).order_by(NSBranch.name).all()
    return json_select_options(branches)


@bp.route('/api/subbranches/<int:branch_id>', methods=['GET'])
@permission_required('admin.organization.manage')
def api_get_subbranches_by_branch(branch_id):
    """API endpoint to get sub-branches for a specific branch."""
    subbranches = NSSubBranch.query.filter_by(branch_id=branch_id, is_active=True).order_by(NSSubBranch.name).all()
    return json_select_options(subbranches)


# Public API endpoints (no authentication required) for NS structure
@bp.route('/api/public/branches/<int:country_id>', methods=['GET'])
@limiter.exempt
@rbac_guard_audit_exempt("Public endpoint for branch selectors (no authentication).")
def api_get_branches_by_country_public(country_id):
    """Public API endpoint to get branches for a specific country (no auth required)."""
    try:
        branches = NSBranch.query.filter_by(country_id=country_id, is_active=True).order_by(NSBranch.name).all()
        return json_select_options(branches, ('id', 'name', 'code'))
    except Exception as e:
        return handle_json_view_exception(e, 'Failed to fetch branches', status_code=500)


@bp.route('/api/public/subbranches/<int:branch_id>', methods=['GET'])
@limiter.exempt
@rbac_guard_audit_exempt("Public endpoint for sub-branch selectors (no authentication).")
def api_get_subbranches_by_branch_public(branch_id):
    """Public API endpoint to get sub-branches for a specific branch (no auth required)."""
    try:
        subbranches = NSSubBranch.query.filter_by(branch_id=branch_id, is_active=True).order_by(NSSubBranch.name).all()
        return json_select_options(subbranches, ('id', 'name', 'code'))
    except Exception as e:
        return handle_json_view_exception(e, 'Failed to fetch sub-branches', status_code=500)


@bp.route('/api/public/subbranches/by-country/<int:country_id>', methods=['GET'])
@limiter.exempt
@rbac_guard_audit_exempt("Public endpoint for sub-branch selectors by country (no authentication).")
def api_get_subbranches_by_country_public(country_id):
    """Public API endpoint to get all sub-branches for a specific country (no auth required)."""
    try:
        subbranches = (
            NSSubBranch.query
            .join(NSBranch)
            .filter(NSBranch.country_id == country_id)
            .filter(NSSubBranch.is_active == True)
            .order_by(NSSubBranch.name)
            .all()
        )
        return json_select_options(subbranches, ('id', 'name', 'code', 'branch_id'))
    except Exception as e:
        return handle_json_view_exception(e, 'Failed to fetch sub-branches', status_code=500)
# ==================== API Endpoint for NS part_of field ====================

@bp.route('/api/national-societies/<int:ns_id>/part-of', methods=['POST', 'PUT'])
@admin_permission_required('admin.organization.manage')
def api_update_ns_part_of(ns_id):
    """API endpoint to update the part_of field for a National Society."""
    try:
        ns = NationalSociety.query.get_or_404(ns_id)
        data = get_json_safe()
        err = require_json_data(data)
        if err:
            return err

        has_part_of = 'part_of' in data
        has_text = 'category_text_name' in data
        if not has_part_of and not has_text:
            return json_bad_request('part_of or category_text_name is required')

        from sqlalchemy.orm.attributes import flag_modified

        if has_part_of:
            part_of = data.get('part_of')
            if part_of is not None and not isinstance(part_of, list):
                return json_bad_request('part_of must be a list or null')
            ns.part_of = part_of if part_of else None
            flag_modified(ns, 'part_of')

        if has_text:
            category_name = (data.get('category_text_name') or '').strip()
            if not category_name:
                return json_bad_request('category_text_name is required')
            raw_value = data.get('category_text_value')
            if raw_value is not None and not isinstance(raw_value, str):
                return json_bad_request('category_text_value must be a string')
            value = (raw_value or '').strip()
            if len(value) > 500:
                return json_bad_request('category_text_value must be 500 characters or fewer')
            current = dict(ns.category_text) if isinstance(ns.category_text, dict) else {}
            if value:
                current[category_name] = value
            else:
                current.pop(category_name, None)
            ns.category_text = current or None
            flag_modified(ns, 'category_text')

        db.session.add(ns)
        db.session.flush()

        return json_ok(
            success=True,
            message='National Society category updated successfully',
            part_of=ns.part_of if isinstance(ns.part_of, list) else [],
            category_text=ns.category_text if isinstance(ns.category_text, dict) else {}
        )

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error updating NS part_of field: {e}")
        return json_server_error(GENERIC_ERROR_MESSAGE)


def _part_of_category_payload():
    from app.utils.country_utils import collect_part_of_category_definitions

    nss = NationalSociety.query.filter(NationalSociety.part_of.isnot(None)).all()
    definitions = collect_part_of_category_definitions(nss)
    checkbox_names = [item["name"] for item in definitions if item["type"] == "checkbox"]
    return definitions, checkbox_names


@bp.route('/api/part-of-programs', methods=['GET'])
@admin_permission_required_any('admin.organization.manage', 'admin.countries.view', 'admin.countries.edit')
def api_get_part_of_programs():
    """API endpoint to get the list of available categories for part_of columns."""
    try:
        definitions, categories_list = _part_of_category_payload()
        return json_ok(
            success=True,
            categories=categories_list,
            programs=categories_list,
            category_definitions=definitions
        )

    except Exception as e:
        current_app.logger.error(f"Error getting part_of categories: {e}")
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route('/api/part-of-programs', methods=['POST'])
@admin_permission_required('admin.organization.manage')
def api_add_part_of_program():
    """API endpoint to add a new category to the available list."""
    try:
        from app.utils.country_utils import PART_OF_CATEGORY_TYPES, remember_part_of_category

        data = get_json_safe()
        category_name = (data.get('category_name') or data.get('program_name') or '').strip()
        if not category_name:
            return json_bad_request('category_name is required')
        category_type = (data.get('category_type') or 'checkbox').strip().lower()
        if category_type not in PART_OF_CATEGORY_TYPES:
            return json_bad_request('category_type must be checkbox or text')

        remember_part_of_category(category_name, category_type)
        definitions, categories_list = _part_of_category_payload()

        return json_ok(
            success=True,
            message=f'Category "{category_name}" added successfully',
            categories=categories_list,
            programs=categories_list,
            category_definitions=definitions
        )

    except Exception as e:
        current_app.logger.error(f"Error adding part_of category: {e}")
        return json_server_error(GENERIC_ERROR_MESSAGE)


def _migrate_part_of_category_values(category_name, new_type):
    """Move saved values when a category switches between tick boxes and text.

    A tick becomes the text Yes. Non-empty text becomes a tick.
    """
    from sqlalchemy.orm.attributes import flag_modified

    changed = []
    if new_type == 'text':
        nss = NationalSociety.query.filter(NationalSociety.part_of.isnot(None)).all()
        for ns in nss:
            if not isinstance(ns.part_of, list) or category_name not in ns.part_of:
                continue
            ns.part_of = [item for item in ns.part_of if item != category_name] or None
            flag_modified(ns, 'part_of')
            texts = dict(ns.category_text) if isinstance(ns.category_text, dict) else {}
            if not str(texts.get(category_name) or '').strip():
                texts[category_name] = 'Yes'
            ns.category_text = texts
            flag_modified(ns, 'category_text')
            db.session.add(ns)
            changed.append(ns)
    else:
        text_rows = NationalSociety.query.filter(NationalSociety.category_text.isnot(None)).all()
        for ns in text_rows:
            if not isinstance(ns.category_text, dict):
                continue
            if not str(ns.category_text.get(category_name) or '').strip():
                continue
            part_of = list(ns.part_of) if isinstance(ns.part_of, list) else []
            if category_name not in part_of:
                part_of.append(category_name)
            ns.part_of = part_of
            flag_modified(ns, 'part_of')
            remaining = {key: value for key, value in ns.category_text.items() if key != category_name}
            ns.category_text = remaining or None
            flag_modified(ns, 'category_text')
            db.session.add(ns)
            changed.append(ns)
    if changed:
        db.session.flush()
    return changed


@bp.route('/api/part-of-programs/<program_name>', methods=['PUT'])
@admin_permission_required('admin.organization.manage')
def api_update_part_of_program_type(program_name):
    """Change a category between tick boxes and text."""
    try:
        from urllib.parse import unquote
        from app.utils.country_utils import (
            PART_OF_CATEGORY_TYPES,
            load_part_of_category_catalog,
            update_part_of_category_type,
        )

        category_name = unquote(program_name).strip()
        if not category_name:
            return json_bad_request('category_name is required')
        data = get_json_safe()
        category_type = (data.get('category_type') or '').strip().lower()
        if category_type not in PART_OF_CATEGORY_TYPES:
            return json_bad_request('category_type must be checkbox or text')

        previous = load_part_of_category_catalog().get(category_name, 'checkbox')
        changed = []
        if previous != category_type:
            changed = _migrate_part_of_category_values(category_name, category_type)
            update_part_of_category_type(category_name, category_type)

        definitions, categories_list = _part_of_category_payload()
        return json_ok(
            success=True,
            message=f'Category "{category_name}" is now {category_type}',
            categories=categories_list,
            programs=categories_list,
            category_definitions=definitions,
            updated_societies=[
                {
                    'id': ns.id,
                    'part_of': ns.part_of if isinstance(ns.part_of, list) else [],
                    'category_text': ns.category_text if isinstance(ns.category_text, dict) else {},
                }
                for ns in changed
            ],
        )
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error updating part_of category type: {e}")
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route('/api/part-of-programs/<program_name>', methods=['DELETE'])
@admin_permission_required('admin.organization.manage')
def api_remove_part_of_program(program_name):
    """API endpoint to remove a category from all NSs and the available list."""
    try:
        from urllib.parse import unquote
        from app.utils.country_utils import forget_part_of_category

        category_name = unquote(program_name).strip()

        # Remove this category from all NSs' part_of fields
        nss = NationalSociety.query.filter(NationalSociety.part_of.isnot(None)).all()
        updated_ids = set()
        from sqlalchemy.orm.attributes import flag_modified
        for ns in nss:
            if ns.part_of and isinstance(ns.part_of, list):
                original_length = len(ns.part_of)
                ns.part_of = [p for p in ns.part_of if p != category_name]
                if len(ns.part_of) != original_length:
                    flag_modified(ns, 'part_of')
                    db.session.add(ns)
                    updated_ids.add(ns.id)

        text_rows = NationalSociety.query.filter(NationalSociety.category_text.isnot(None)).all()
        for ns in text_rows:
            if isinstance(ns.category_text, dict) and category_name in ns.category_text:
                remaining = {key: value for key, value in ns.category_text.items() if key != category_name}
                ns.category_text = remaining or None
                flag_modified(ns, 'category_text')
                db.session.add(ns)
                updated_ids.add(ns.id)

        updated_count = len(updated_ids)
        if updated_count > 0:
            db.session.flush()

        forget_part_of_category(category_name)

        return json_ok(
            success=True,
            message=f'Category "{category_name}" removed from {updated_count} National Societies',
            updated_count=updated_count
        )

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error removing part_of category: {e}")
        return json_server_error(GENERIC_ERROR_MESSAGE)
