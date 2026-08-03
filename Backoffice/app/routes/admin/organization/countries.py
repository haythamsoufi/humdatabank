"""Organization dashboard and country CRUD routes."""
import io
import json
import os
from datetime import datetime

import pandas as pd
from flask import render_template, redirect, url_for, request, flash, current_app, send_file
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

# ==================== Main Organization Dashboard ====================

@bp.route('/', methods=['GET'])
@admin_permission_required_any('admin.organization.manage', 'admin.countries.view', 'admin.countries.edit')
def index():
    """Main organization dashboard with tabbed interface."""
    enabled_entity_groups = get_enabled_entity_groups()
    countries_enabled = 'countries' in enabled_entity_groups
    ns_structure_enabled = 'ns_structure' in enabled_entity_groups
    secretariat_enabled = 'secretariat' in enabled_entity_groups

    tab_sequence = []
    if countries_enabled:
        tab_sequence.append('countries')
        tab_sequence.append('nss')
    if ns_structure_enabled:
        tab_sequence.append('ns-structure')
    if secretariat_enabled:
        tab_sequence.append('secretariat')
    if not tab_sequence:
        tab_sequence.append('countries')
    # Get counts for each entity type
    countries_count = Country.query.count() if countries_enabled else 0
    nss_count = NationalSociety.query.count() if countries_enabled else 0
    branches_count = NSBranch.query.count() if ns_structure_enabled else 0
    subbranches_count = NSSubBranch.query.count() if ns_structure_enabled else 0
    localunits_count = NSLocalUnit.query.count() if ns_structure_enabled else 0
    divisions_count = SecretariatDivision.query.count() if secretariat_enabled else 0
    departments_count = SecretariatDepartment.query.count() if secretariat_enabled else 0
    regions_count = SecretariatRegionalOffice.query.count() if secretariat_enabled else 0
    clusters_count = SecretariatClusterOffice.query.count() if secretariat_enabled else 0

    # Get active tab from query parameter
    requested_tab = request.args.get('tab', tab_sequence[0])
    active_tab = requested_tab if requested_tab in tab_sequence else tab_sequence[0]
    # Get desired sub-tab for Secretariat panel
    secretariat_tab = request.args.get('secretariat_tab', 'divisions')
    if secretariat_tab not in ('divisions', 'departments', 'regions', 'clusters'):
        secretariat_tab = 'divisions'

    # Get filter parameters
    selected_country_id = request.args.get('country_id', type=int) if ns_structure_enabled else None
    selected_division_id = request.args.get('division_id', type=int) if secretariat_enabled else None
    active_only = request.args.get('active', 'true') == 'true'

    # Load all data for tabs
    # Countries data
    countries = countries_with_fds_member_query().order_by(Country.name).all() if countries_enabled else []
    # National Societies data
    nss = (
        NationalSociety.query
        .join(Country)
        .order_by(Country.name, NationalSociety.display_order, NationalSociety.name)
        .all()
    ) if countries_enabled else []

    # NS Branches data
    branch_id = None
    if ns_structure_enabled:
        branches_query = NSBranch.query.join(Country)
        if selected_country_id:
            branches_query = branches_query.filter(NSBranch.country_id == selected_country_id)
        if active_only:
            branches_query = branches_query.filter(NSBranch.is_active == True)
        branches = branches_query.order_by(Country.name, NSBranch.name).all()
        all_countries = Country.query.order_by(Country.name).all()

        subbranches_query = NSSubBranch.query.join(NSBranch)
        branch_id = request.args.get('branch_id', type=int)
        if branch_id:
            subbranches_query = subbranches_query.filter(NSSubBranch.branch_id == branch_id)
        if active_only:
            subbranches_query = subbranches_query.filter(NSSubBranch.is_active == True)
        subbranches = subbranches_query.order_by(NSBranch.name, NSSubBranch.name).all()

        localunits_query = NSLocalUnit.query.join(NSBranch)
        if selected_country_id:
            localunits_query = localunits_query.filter(NSBranch.country_id == selected_country_id)
        if active_only:
            localunits_query = localunits_query.filter(NSLocalUnit.is_active == True)
        localunits = localunits_query.order_by(NSBranch.name, NSLocalUnit.name).all()
    else:
        branches = []
        subbranches = []
        localunits = []
        all_countries = []
        branch_id = None

    if secretariat_enabled:
        divisions = SecretariatDivision.query.order_by(SecretariatDivision.display_order, SecretariatDivision.name).all()

        departments_query = SecretariatDepartment.query.join(SecretariatDivision)
        if selected_division_id:
            departments_query = departments_query.filter(SecretariatDepartment.division_id == selected_division_id)
        if active_only:
            departments_query = departments_query.filter(SecretariatDepartment.is_active == True)
        departments = departments_query.order_by(SecretariatDivision.display_order, SecretariatDepartment.display_order, SecretariatDepartment.name).all()

        regions = SecretariatRegionalOffice.query.order_by(SecretariatRegionalOffice.display_order, SecretariatRegionalOffice.name).all()

        clusters_query = SecretariatClusterOffice.query.join(SecretariatRegionalOffice)
        if active_only:
            clusters_query = clusters_query.filter(SecretariatClusterOffice.is_active == True)
        clusters = clusters_query.order_by(SecretariatRegionalOffice.display_order, SecretariatClusterOffice.display_order, SecretariatClusterOffice.name).all()
    else:
        divisions = []
        departments = []
        regions = []
        clusters = []

    # Return JSON for API requests (mobile app)
    if is_json_request():
        # Build JSON response based on active tab
        response_data = {
            'success': True,
            'active_tab': active_tab,
            'enabled_entity_types': enabled_entity_groups,
            'counts': {
                'countries': countries_count,
                'national_societies': nss_count,
                'branches': branches_count,
                'subbranches': subbranches_count,
                'local_units': localunits_count,
                'divisions': divisions_count,
                'departments': departments_count,
                'regions': regions_count,
                'clusters': clusters_count,
            }
        }

        # Always include national_societies data (needed for program filtering)
        # Serialize part_of properly - JSONB fields need special handling
        response_data['national_societies'] = []
        for ns in nss:
            ns_data = {
                'id': ns.id,
                'name': ns.name,
                'country_id': ns.country_id,
                'country_name': ns.country.name if ns.country else None,
            }
            # Handle part_of JSONB field - ensure it's always an array
            if ns.part_of:
                if isinstance(ns.part_of, list):
                    ns_data['part_of'] = ns.part_of
                elif isinstance(ns.part_of, str):
                    try:
                        parsed = json.loads(ns.part_of)
                        ns_data['part_of'] = parsed if isinstance(parsed, list) else []
                    except (json.JSONDecodeError, TypeError):
                        ns_data['part_of'] = []
                else:
                    ns_data['part_of'] = []
            else:
                ns_data['part_of'] = []
            response_data['national_societies'].append(ns_data)

        # Add data based on active tab
        if active_tab == 'countries':
            response_data['countries'] = [{
                'id': c.id,
                'name': c.name,
                'code': c.code if hasattr(c, 'code') else None,
            } for c in countries]
        elif active_tab == 'ns-structure':
            response_data['branches'] = [{
                'id': b.id,
                'name': b.name,
                'country_id': b.country_id,
                'country_name': b.country.name if b.country else None,
                'is_active': b.is_active if hasattr(b, 'is_active') else True,
            } for b in branches]
            response_data['subbranches'] = [{
                'id': sb.id,
                'name': sb.name,
                'branch_id': sb.branch_id,
                'branch_name': sb.branch.name if sb.branch else None,
                'is_active': sb.is_active if hasattr(sb, 'is_active') else True,
            } for sb in subbranches]
            response_data['local_units'] = [{
                'id': lu.id,
                'name': lu.name,
                'branch_id': lu.branch_id,
                'branch_name': lu.branch.name if lu.branch else None,
                'is_active': lu.is_active if hasattr(lu, 'is_active') else True,
            } for lu in localunits]
        elif active_tab == 'secretariat':
            response_data['divisions'] = [{
                'id': d.id,
                'name': d.name,
                'display_order': d.display_order if hasattr(d, 'display_order') else None,
            } for d in divisions]
            response_data['departments'] = [{
                'id': dept.id,
                'name': dept.name,
                'division_id': dept.division_id,
                'division_name': dept.division.name if dept.division else None,
                'display_order': dept.display_order if hasattr(dept, 'display_order') else None,
                'is_active': dept.is_active if hasattr(dept, 'is_active') else True,
            } for dept in departments]
            response_data['regions'] = [{
                'id': r.id,
                'name': r.name,
                'short_name': r.short_name,
                'display_order': r.display_order if hasattr(r, 'display_order') else None,
            } for r in regions]
            response_data['clusters'] = [{
                'id': c.id,
                'name': c.name,
                'regional_office_id': c.regional_office_id,
                'regional_office_name': c.regional_office.name if c.regional_office else None,
                'display_order': c.display_order if hasattr(c, 'display_order') else None,
            } for c in clusters]

        response_data['all_countries'] = [{
            'id': c.id,
            'name': c.name,
            'code': c.code if hasattr(c, 'code') else None,
        } for c in all_countries] if 'all_countries' in locals() else []

        return json_ok(**response_data)

    # Derive part_of categories from already-loaded NSs so the page does not
    # need a separate GET /api/part-of-programs round-trip on load.
    part_of_programs = sorted({
        item.strip()
        for ns in nss
        if ns.part_of and isinstance(ns.part_of, list)
        for item in ns.part_of
        if item and isinstance(item, str) and item.strip()
    })

    return render_template('admin/organization/index.html',
                         countries_count=countries_count,
                         nss_count=nss_count,
                         branches_count=branches_count,
                         subbranches_count=subbranches_count,
                         localunits_count=localunits_count,
                         divisions_count=divisions_count,
                         departments_count=departments_count,
                         regions_count=regions_count,
                         clusters_count=clusters_count,
                         active_tab=active_tab,
                         secretariat_tab=secretariat_tab,
                         # Data for tabs
                         countries=countries,
                         nss=nss,
                         branches=branches,
                         subbranches=subbranches,
                         localunits=localunits,
                         divisions=divisions,
                         departments=departments,
                         regions=regions,
                         clusters=clusters,
                         all_countries=all_countries,
                         part_of_programs=part_of_programs,
                         # Filter parameters
                         selected_country_id=selected_country_id,
                         selected_division_id=selected_division_id,
                         selected_branch_id=branch_id,
                         active_only=active_only,
                         enabled_entity_types=enabled_entity_groups)


# ==================== Countries ====================

@bp.route('/countries/new', methods=['GET', 'POST'])
@admin_permission_required_any('admin.countries.edit', 'admin.organization.manage')
def new_country():
    """Create a new country."""
    form = CountryForm()

    if form.validate_on_submit():
        country = Country(
            name=form.name.data,
            iso3=form.iso3.data.upper(),
            iso2=form.iso2.data.upper() if form.iso2.data else None,
            secretariat_regional_office_id=form.secretariat_regional_office_id.data,
            status=form.status.data or 'Active',
            preferred_language=form.preferred_language.data,
            currency_code=form.currency_code.data
        )
        assign_country_secretariat_regional_office(country, None)
        country.name_translations = collect_translations(form, 'name')
        db.session.add(country)
        db.session.flush()
        flash(f'Country "{country.name}" created successfully.', 'success')
        return redirect(url_for('organization.index', tab='countries'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=False,
                         entity=None,
                         entity_label='Country',
                         icon='fas fa-flag',
                         cancel_url=url_for('organization.index', tab='countries'))


@bp.route('/countries/<int:country_id>/edit', methods=['GET', 'POST'])
@admin_permission_required_any('admin.countries.edit', 'admin.organization.manage')
def edit_country(country_id):
    """Edit an existing country."""
    country = Country.query.get_or_404(country_id)
    form = CountryForm()

    if request.method == 'GET':
        # Populate non-translation fields from the country object
        form.name.data = country.name
        form.iso3.data = country.iso3
        form.iso2.data = country.iso2
        form.secretariat_regional_office_id.data = country.secretariat_regional_office_id
        form.status.data = country.status
        form.preferred_language.data = country.preferred_language
        form.currency_code.data = country.currency_code

        # Clear translation fields first to ensure they start empty
        clear_translation_fields(form, 'name')
        # Now populate from actual translations in name_translations (only if they exist)
        populate_translation_fields(form, country, 'name_translations', 'name')

    if form.validate_on_submit():
        country.name = form.name.data
        country.iso3 = form.iso3.data.upper()
        country.iso2 = form.iso2.data.upper() if form.iso2.data else None
        country.secretariat_regional_office_id = form.secretariat_regional_office_id.data
        assign_country_secretariat_regional_office(country, None)
        country.status = form.status.data
        country.preferred_language = form.preferred_language.data
        country.currency_code = form.currency_code.data
        try:
            assign_country_fds_member_user(
                country,
                parse_fds_member_user_id(request.form.get('fds_member_user_id')),
            )
        except ValueError as exc:
            flash(str(exc), 'danger')
            return render_template('admin/organization/edit_entity.html',
                                 form=form,
                                 is_edit=True,
                                 entity=country,
                                 entity_label='Country',
                                 icon='fas fa-flag',
                                 cancel_url=url_for('organization.index', tab='countries'))
        country.name_translations = collect_translations(form, 'name')

        db.session.flush()
        flash(f'Country "{country.name}" updated successfully.', 'success')
        return redirect(url_for('organization.index', tab='countries'))

    return render_template('admin/organization/edit_entity.html',
                         form=form,
                         is_edit=True,
                         entity=country,
                         entity_label='Country',
                         icon='fas fa-flag',
                         cancel_url=url_for('organization.index', tab='countries'))


@bp.route('/countries/<int:country_id>/delete', methods=['POST'])
@admin_permission_required_any('admin.countries.edit', 'admin.organization.manage')
def delete_country(country_id):
    """Delete a country."""
    country = Country.query.get_or_404(country_id)
    csrf_form = FlaskForm()

    if csrf_form.validate_on_submit():
        try:
            name = country.name
            db.session.delete(country)
            db.session.flush()
            flash(f'Country "{name}" deleted successfully.', 'success')
        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")

    return redirect(url_for('organization.index', tab='countries'))
