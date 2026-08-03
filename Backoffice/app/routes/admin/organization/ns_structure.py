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
from . import bp

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
            is_active=form.is_active.data,
            display_order=form.display_order.data or 0,
        )
        ns.name_translations = collect_translations(form, 'name')
        db.session.add(ns)
        db.session.flush()
        flash(f'National Society "{ns.name}" created successfully.', 'success')
        return redirect(url_for('organization.index', tab='nss'))

    return render_template('admin/organization/edit_entity.html',
                           form=form,
                           is_edit=False,
                           entity=None,
                           entity_label='National Society',
                           icon='fas fa-hands-helping',
                           cancel_url=url_for('organization.index', tab='nss'))


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
        form.is_active.data = ns.is_active
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
        ns.is_active = form.is_active.data
        ns.display_order = form.display_order.data or 0
        ns.name_translations = collect_translations(form, 'name')

        db.session.flush()
        flash(f'National Society "{ns.name}" updated successfully.', 'success')
        return redirect(url_for('organization.index', tab='nss'))

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

        part_of = data.get('part_of')

        # Validate that part_of is either None or a list/array
        if part_of is not None and not isinstance(part_of, list):
            return json_bad_request('part_of must be a list or null')

        # Update the field
        ns.part_of = part_of if part_of else None

        # Mark the JSONB field as modified
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(ns, 'part_of')

        db.session.add(ns)
        db.session.flush()

        return json_ok(
            success=True,
            message='National Society part_of field updated successfully',
            part_of=ns.part_of
        )

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error updating NS part_of field: {e}")
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route('/api/part-of-programs', methods=['GET'])
@admin_permission_required_any('admin.organization.manage', 'admin.countries.view', 'admin.countries.edit')
def api_get_part_of_programs():
    """API endpoint to get the list of available categories for part_of columns."""
    try:
        # Get all distinct categories from all NSs' part_of fields
        all_categories = set()
        nss = NationalSociety.query.filter(NationalSociety.part_of.isnot(None)).all()
        for ns in nss:
            if ns.part_of and isinstance(ns.part_of, list):
                for item in ns.part_of:
                    if item and isinstance(item, str):
                        all_categories.add(item.strip())

        categories_list = sorted(list(all_categories))
        return json_ok(
            success=True,
            categories=categories_list,
            programs=categories_list
        )

    except Exception as e:
        current_app.logger.error(f"Error getting part_of categories: {e}")
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route('/api/part-of-programs', methods=['POST'])
@admin_permission_required('admin.organization.manage')
def api_add_part_of_program():
    """API endpoint to add a new category to the available list."""
    try:
        data = get_json_safe()
        category_name = (data.get('category_name') or data.get('program_name') or '').strip()
        if not category_name:
            return json_bad_request('category_name is required')

        # Get current list of categories
        all_categories = set()
        nss = NationalSociety.query.filter(NationalSociety.part_of.isnot(None)).all()
        for ns in nss:
            if ns.part_of and isinstance(ns.part_of, list):
                for item in ns.part_of:
                    if item and isinstance(item, str):
                        all_categories.add(item.strip())

        # Add the new category
        all_categories.add(category_name)
        categories_list = sorted(list(all_categories))

        return json_ok(
            success=True,
            message=f'Category "{category_name}" added successfully',
            categories=categories_list,
            programs=categories_list
        )

    except Exception as e:
        current_app.logger.error(f"Error adding part_of category: {e}")
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route('/api/part-of-programs/<program_name>', methods=['DELETE'])
@admin_permission_required('admin.organization.manage')
def api_remove_part_of_program(program_name):
    """API endpoint to remove a category from all NSs and the available list."""
    try:
        from urllib.parse import unquote
        category_name = unquote(program_name).strip()

        # Remove this category from all NSs' part_of fields
        nss = NationalSociety.query.filter(NationalSociety.part_of.isnot(None)).all()
        updated_count = 0
        for ns in nss:
            if ns.part_of and isinstance(ns.part_of, list):
                original_length = len(ns.part_of)
                ns.part_of = [p for p in ns.part_of if p != category_name]
                if len(ns.part_of) != original_length:
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(ns, 'part_of')
                    db.session.add(ns)
                    updated_count += 1

        if updated_count > 0:
            db.session.flush()

        return json_ok(
            success=True,
            message=f'Category "{category_name}" removed from {updated_count} National Societies',
            updated_count=updated_count
        )

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error removing part_of category: {e}")
        return json_server_error(GENERIC_ERROR_MESSAGE)
