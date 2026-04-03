"""
Organization Management Routes - Unified management for all organizational entities.

This blueprint provides CRUD operations for:
- Countries
- NS Branches, Sub-branches, and Local Units
- Secretariat Divisions and Departments
"""
import io
import json
import os
from contextlib import suppress
from datetime import datetime
from typing import Any, Dict

import pandas as pd
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, Response, stream_with_context, has_app_context, send_file
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from app.extensions import limiter
from wtforms import StringField, TextAreaField, BooleanField, IntegerField, SelectField, DateField
from wtforms.validators import DataRequired, Optional, Length
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
from app.models.enums import EntityType
from app.services.entity_service import EntityService
from app.routes.admin.shared import admin_required, admin_permission_required, admin_permission_required_any, permission_required, permission_required_any, rbac_guard_audit_exempt
from app.utils.request_utils import is_json_request
from app.utils.entity_groups import get_enabled_entity_groups
from app.utils.transactions import no_auto_transaction, request_transaction_rollback
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_formatting import choices_from_query
from app.utils.api_responses import json_bad_request, json_error, json_ok, json_select_options, json_server_error, require_json_data, require_json_keys
from app.utils.error_handling import handle_json_view_exception
from config.config import Config

bp = Blueprint('organization', __name__, url_prefix='/admin/organization')

@bp.before_request
def enforce_organization_rbac():
    """
    Enforce RBAC permissions for organization management.

    Note: Many routes in this blueprint historically used a broad admin gate.
    This hook adds defense-in-depth and prevents unauthorized admins from
    accessing create/edit/delete operations via direct URL access.
    """
    try:
        # Avoid importing at module load if extensions aren't ready
        from app.services.authorization_service import AuthorizationService
        from flask import request
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("before_request auth import fallback: %s", e)
        return None

    # Require authentication (routes use permission decorators that enforce login; keep this safe)
    if not getattr(current_user, "is_authenticated", False):
        return None

    # System manager: full access
    if AuthorizationService.is_system_manager(current_user):
        return None

    # Must be an admin at all to reach /admin/organization
    if not AuthorizationService.is_admin(current_user):
        flash("Access denied. Admin privileges required.", "warning")
        return redirect(url_for("main.dashboard"))

    endpoint = (request.endpoint or "").strip()

    # Index page: allow either org managers or country viewers/editors (read-only UI must still be gated)
    if endpoint == "organization.index":
        if (
            AuthorizationService.has_rbac_permission(current_user, "admin.organization.manage")
            or AuthorizationService.has_rbac_permission(current_user, "admin.countries.view")
            or AuthorizationService.has_rbac_permission(current_user, "admin.countries.edit")
        ):
            return None
        flash("Access denied.", "warning")
        return redirect(url_for("main.dashboard"))

    # Country CRUD routes (within this blueprint)
    country_mutation_endpoints = {
        "organization.new_country",
        "organization.edit_country",
        "organization.delete_country",
    }
    if endpoint in country_mutation_endpoints:
        if (
            AuthorizationService.has_rbac_permission(current_user, "admin.countries.edit")
            or AuthorizationService.has_rbac_permission(current_user, "admin.organization.manage")
        ):
            return None
        flash("Access denied. Country edit permission required.", "warning")
        return redirect(url_for("main.dashboard"))

    # Country export/template: allow view or edit
    country_read_endpoints = {"organization.export_countries", "organization.countries_template"}
    if endpoint in country_read_endpoints:
        if (
            AuthorizationService.has_rbac_permission(current_user, "admin.countries.view")
            or AuthorizationService.has_rbac_permission(current_user, "admin.countries.edit")
            or AuthorizationService.has_rbac_permission(current_user, "admin.organization.manage")
        ):
            return None
        flash("Access denied.", "warning")
        return redirect(url_for("main.dashboard"))

    # Everything else here is organization structure management
    if not AuthorizationService.has_rbac_permission(current_user, "admin.organization.manage"):
        flash("Access denied. Organization management permission required.", "warning")
        return redirect(url_for("main.dashboard"))

    return None

def _get_translation_languages():
    """Return translation languages based on current supported languages."""
    # Prefer runtime config so orgs can change languages without code changes.
    # Must be safe to call during module import (no app context yet).
    if has_app_context():
        langs = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
    else:
        langs = []
    langs = langs or getattr(Config, "TRANSLATABLE_LANGUAGES", []) or []
    all_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
    return [(code, all_names.get(code, code.upper())) for code in langs]


def _get_translation_codes():
    return [code for code, _ in _get_translation_languages()]


def _add_translation_fields(form_cls, base_name, label_prefix, max_length):
    """Dynamically attach language-specific StringFields to a WTForms class."""
    added_any = False
    for code, language in _get_translation_languages():
        field_name = f'{base_name}_{code}'
        if not hasattr(form_cls, field_name):
            setattr(
                form_cls,
                field_name,
                StringField(
                    f'{label_prefix} ({language})',
                    validators=[Optional(), Length(max=max_length)]
                ),
            )
            added_any = True

    # WTForms clears `form_cls._unbound_fields` to None when new fields are added
    # at runtime (via FormMeta.__setattr__). If we add fields during `__init__`,
    # we must rebuild it before calling `super().__init__()`; otherwise WTForms
    # will crash trying to iterate None.
    if added_any or getattr(form_cls, "_unbound_fields", None) is None:
        fields = []
        for name in dir(form_cls):
            if not name.startswith("_"):
                unbound_field = getattr(form_cls, name)
                if hasattr(unbound_field, "_formfield"):
                    fields.append((name, unbound_field))
        # Stable sort: creation order, then name.
        fields.sort(key=lambda x: (x[1].creation_counter, x[0]))
        form_cls._unbound_fields = fields


def _collect_translations(form, field_prefix):
    """Extract non-empty translation values from a form for a given field prefix."""
    translations = {}
    for code in _get_translation_codes():
        field = getattr(form, f'{field_prefix}_{code}', None)
        if field and field.data and field.data.strip():
            translations[code] = field.data.strip()
    return translations or None


def _clear_translation_fields(form, field_prefix):
    """Clear translation fields to prevent WTForms from using property fallbacks
    that return English names when translations don't exist.
    """
    for code in _get_translation_codes():
        field = getattr(form, f'{field_prefix}_{code}', None)
        if field:
            field.data = ''


def _populate_translation_fields(form, entity, attr_name, field_prefix):
    """Populate form translation fields from an entity JSONB attribute.

    Only populates fields if a translation value exists. Missing translations
    are left empty (not filled with English values).

    Note: Call _clear_translation_fields() first if the entity has properties
    that fall back to English names.
    """
    raw_translations = getattr(entity, attr_name, None)
    translations = None

    if raw_translations:
        translations = raw_translations
        if isinstance(raw_translations, str):
            try:
                translations = json.loads(raw_translations)
            except (TypeError, ValueError):
                translations = None
        if not isinstance(translations, dict):
            translations = None

    for code in _get_translation_codes():
        field = getattr(form, f'{field_prefix}_{code}', None)
        if field:
            value = ''
            # Only set value if translation exists in name_translations JSONB field
            # Do NOT fall back to legacy properties as they return English when translation is missing
            if translations and code in translations:
                translation_value = translations.get(code)
                # Only use the value if it's a non-empty string
                if translation_value and isinstance(translation_value, str) and translation_value.strip():
                    value = translation_value.strip()
            # Always set to empty string if no valid translation found (never use English as fallback)
            field.data = value


def _count_missing_name_translations(entities) -> Dict[str, int]:
    """Count missing translations for the provided entities."""
    counts: Dict[str, int] = {}
    if has_app_context():
        lang_codes = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
    else:
        lang_codes = getattr(Config, "TRANSLATABLE_LANGUAGES", []) or []
    for entity in entities:
        base_name = getattr(entity, 'name', '')
        if not base_name or not str(base_name).strip():
            continue

        raw = getattr(entity, 'name_translations', None)
        translations: Dict[str, Any] = {}
        if isinstance(raw, dict):
            translations = raw
        elif isinstance(raw, str):
            with suppress((TypeError, ValueError, json.JSONDecodeError)):
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    translations = parsed

        for lang_code in lang_codes:
            translated_value = translations.get(lang_code) if translations else None
            if not translated_value or not str(translated_value).strip():
                counts[lang_code] = counts.get(lang_code, 0) + 1

    return counts


# ==================== Forms ====================

class CountryForm(FlaskForm):
    """Form for creating/editing countries."""
    name = StringField('Country Name', validators=[DataRequired(), Length(max=100)])
    iso3 = StringField('ISO3 Code', validators=[DataRequired(), Length(min=3, max=3)])
    iso2 = StringField('ISO2 Code', validators=[Optional(), Length(min=2, max=2)])
    region = SelectField('Region', validators=[DataRequired()],
                        choices=[('Africa', 'Africa'), ('Americas', 'Americas'), ('Asia Pacific', 'Asia Pacific'),
                                ('Europe', 'Europe'), ('Middle East and North Africa', 'Middle East and North Africa')])
    status = SelectField('Status', validators=[Optional()], choices=[('Active', 'Active'), ('Inactive', 'Inactive')])
    preferred_language = StringField('Preferred Language', validators=[Optional()])
    currency_code = StringField('Currency Code', validators=[Optional(), Length(max=3)])

    def __init__(self, *args, **kwargs):
        # Add language fields at runtime (requires app context).
        _add_translation_fields(self.__class__, 'name', 'Country Name', 100)
        super().__init__(*args, **kwargs)


class NationalSocietyForm(FlaskForm):
    """Form for creating/editing National Societies."""
    name = StringField('National Society Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    country_id = SelectField('Country', coerce=int, validators=[DataRequired()])
    is_active = BooleanField('Active', default=True)
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        _add_translation_fields(self.__class__, 'name', 'National Society Name', 255)
        super().__init__(*args, **kwargs)


class NSBranchForm(FlaskForm):
    """Form for creating/editing NS branches."""
    name = StringField('Branch Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Branch Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    country_id = SelectField('Country', coerce=int, validators=[DataRequired()])
    address = TextAreaField('Address', validators=[Optional()])
    city = StringField('City', validators=[Optional(), Length(max=100)])
    postal_code = StringField('Postal Code', validators=[Optional(), Length(max=20)])
    coordinates = StringField('Coordinates (Lat,Long)', validators=[Optional(), Length(max=100)])
    phone = StringField('Phone', validators=[Optional(), Length(max=50)])
    email = StringField('Email', validators=[Optional(), Length(max=255)])
    website = StringField('Website', validators=[Optional(), Length(max=255)])
    is_active = BooleanField('Active', default=True)
    established_date = DateField('Established Date', validators=[Optional()], format='%Y-%m-%d')
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        _add_translation_fields(self.__class__, 'name', 'Branch Name', 255)
        super().__init__(*args, **kwargs)


class NSSubBranchForm(FlaskForm):
    """Form for creating/editing NS sub-branches."""
    name = StringField('Sub-branch Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Sub-branch Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    branch_id = SelectField('Parent Branch', coerce=int, validators=[DataRequired()])
    address = TextAreaField('Address', validators=[Optional()])
    city = StringField('City', validators=[Optional(), Length(max=100)])
    postal_code = StringField('Postal Code', validators=[Optional(), Length(max=20)])
    coordinates = StringField('Coordinates (Lat,Long)', validators=[Optional(), Length(max=100)])
    phone = StringField('Phone', validators=[Optional(), Length(max=50)])
    email = StringField('Email', validators=[Optional(), Length(max=255)])
    is_active = BooleanField('Active', default=True)
    established_date = DateField('Established Date', validators=[Optional()], format='%Y-%m-%d')
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        _add_translation_fields(self.__class__, 'name', 'Sub-branch Name', 255)
        super().__init__(*args, **kwargs)


class NSLocalUnitForm(FlaskForm):
    """Form for creating/editing NS local units."""
    name = StringField('Local Unit Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Local Unit Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    branch_id = SelectField('Parent Branch', coerce=int, validators=[DataRequired()])
    subbranch_id = SelectField('Parent Sub-branch (Optional)', coerce=int, validators=[Optional()])
    address = TextAreaField('Address', validators=[Optional()])
    city = StringField('City', validators=[Optional(), Length(max=100)])
    postal_code = StringField('Postal Code', validators=[Optional(), Length(max=20)])
    coordinates = StringField('Coordinates (Lat,Long)', validators=[Optional(), Length(max=100)])
    phone = StringField('Phone', validators=[Optional(), Length(max=50)])
    email = StringField('Email', validators=[Optional(), Length(max=255)])
    is_active = BooleanField('Active', default=True)
    established_date = DateField('Established Date', validators=[Optional()], format='%Y-%m-%d')
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        _add_translation_fields(self.__class__, 'name', 'Local Unit Name', 255)
        super().__init__(*args, **kwargs)


class SecretariatDivisionForm(FlaskForm):
    """Form for creating/editing Secretariat divisions."""
    name = StringField('Division Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Division Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    is_active = BooleanField('Active', default=True)
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        _add_translation_fields(self.__class__, 'name', 'Division Name', 255)
        super().__init__(*args, **kwargs)


class SecretariatDepartmentForm(FlaskForm):
    """Form for creating/editing Secretariat departments."""
    name = StringField('Department Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Department Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    division_id = SelectField('Parent Division', coerce=int, validators=[DataRequired()])
    is_active = BooleanField('Active', default=True)
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        _add_translation_fields(self.__class__, 'name', 'Department Name', 255)
        super().__init__(*args, **kwargs)


class SecretariatRegionalOfficeForm(FlaskForm):
    """Form for creating/editing Secretariat regional offices."""
    name = StringField('Regional Office Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Regional Office Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    is_active = BooleanField('Active', default=True)
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        _add_translation_fields(self.__class__, 'name', 'Regional Office Name', 255)
        super().__init__(*args, **kwargs)


class SecretariatClusterOfficeForm(FlaskForm):
    """Form for creating/editing Secretariat cluster offices."""
    name = StringField('Cluster Office Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Cluster Office Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    regional_office_id = SelectField('Parent Regional Office', coerce=int, validators=[DataRequired()])
    is_active = BooleanField('Active', default=True)
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        _add_translation_fields(self.__class__, 'name', 'Cluster Office Name', 255)
        super().__init__(*args, **kwargs)
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
    countries = Country.query.order_by(Country.name).all() if countries_enabled else []
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
                         # Filter parameters
                         selected_country_id=selected_country_id,
                         selected_division_id=selected_division_id,
                         selected_branch_id=branch_id,
                         active_only=active_only,
                         enabled_entity_types=enabled_entity_groups,
                         websocket_enabled=current_app.config.get('WEBSOCKET_ENABLED', True))


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
            region=form.region.data,
            status=form.status.data or 'Active',
            preferred_language=form.preferred_language.data,
            currency_code=form.currency_code.data
        )
        country.name_translations = _collect_translations(form, 'name')
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
        form.region.data = country.region
        form.status.data = country.status
        form.preferred_language.data = country.preferred_language
        form.currency_code.data = country.currency_code

        # Clear translation fields first to ensure they start empty
        _clear_translation_fields(form, 'name')
        # Now populate from actual translations in name_translations (only if they exist)
        _populate_translation_fields(form, country, 'name_translations', 'name')

    if form.validate_on_submit():
        country.name = form.name.data
        country.iso3 = form.iso3.data.upper()
        country.iso2 = form.iso2.data.upper() if form.iso2.data else None
        country.region = form.region.data
        country.status = form.status.data
        country.preferred_language = form.preferred_language.data
        country.currency_code = form.currency_code.data
        country.name_translations = _collect_translations(form, 'name')

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


# ==================== Countries Excel Export/Import ====================

@bp.route('/countries/export', methods=['GET'])
@permission_required_any('admin.countries.view', 'admin.countries.edit', 'admin.organization.manage')
def export_countries():
    """Export all countries to an Excel file."""
    try:
        translatable = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        display_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
        countries = Country.query.order_by(Country.name).all()
        data = []
        for c in countries:
            row = {
                'ID': c.id,
                'Name': c.name or '',
                'Short Name': c.short_name or '',
                'ISO3': c.iso3 or '',
                'ISO2': c.iso2 or '',
                'Region': c.region or '',
                'Status': c.status or 'Active',
                'Preferred Language': c.preferred_language_code or 'en',
                'Currency Code': c.currency_code or '',
            }
            for code in translatable:
                header = display_names.get(code, code.upper())
                row[header] = (c.name_translations or {}).get(code, '') or ''
            data.append(row)
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Countries', index=False)
            ws = writer.sheets['Countries']
            for column in ws.columns:
                max_length = max(len(str(cell.value or '')) for cell in column)
                column_letter = column[0].column_letter
                ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
        output.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'countries_export_{timestamp}.xlsx',
        )
    except Exception as e:
        current_app.logger.error(f"Error exporting countries: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for('organization.index', tab='countries'))


@bp.route('/countries/template', methods=['GET'])
@permission_required_any('admin.countries.view', 'admin.countries.edit', 'admin.organization.manage')
def countries_template():
    """Download Excel template for countries import."""
    try:
        translatable = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        display_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
        base_cols = ['Name', 'Short Name', 'ISO3', 'ISO2', 'Region', 'Status', 'Preferred Language', 'Currency Code']
        sample = [{
            'Name': 'Sample Country',
            'Short Name': 'Sample',
            'ISO3': 'XXX',
            'ISO2': 'XX',
            'Region': 'Other',
            'Status': 'Active',
            'Preferred Language': 'en',
            'Currency Code': 'USD',
        }]
        for code in translatable:
            base_cols.append(display_names.get(code, code.upper()))
        df = pd.DataFrame(sample, columns=base_cols)
        for code in translatable:
            header = display_names.get(code, code.upper())
            df[header] = ''
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Countries Template', index=False)
            ws = writer.sheets['Countries Template']
            for column in ws.columns:
                max_length = max(len(str(cell.value or '')) for cell in column)
                column_letter = column[0].column_letter
                ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='countries_template.xlsx',
        )
    except Exception as e:
        current_app.logger.error(f"Error downloading countries template: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for('organization.index', tab='countries'))


@bp.route('/countries/import', methods=['POST'])
@permission_required_any('admin.countries.edit', 'admin.organization.manage')
def import_countries():
    """Import countries from an uploaded Excel file."""
    try:
        if 'excel_file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(url_for('organization.index', tab='countries'))
        file = request.files['excel_file']
        if not file or file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(url_for('organization.index', tab='countries'))
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            flash('Invalid file format. Please upload an Excel file (.xlsx or .xls).', 'danger')
            return redirect(url_for('organization.index', tab='countries'))

        # SECURITY: Validate file size (max 10MB for Excel imports)
        MAX_EXCEL_SIZE_MB = 10
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        if file_size > MAX_EXCEL_SIZE_MB * 1024 * 1024:
            flash(f'File too large. Maximum size is {MAX_EXCEL_SIZE_MB}MB.', 'danger')
            return redirect(url_for('organization.index', tab='countries'))

        # SECURITY: Validate MIME type to prevent file spoofing
        try:
            from app.utils.advanced_validation import AdvancedValidator
            file_ext = os.path.splitext(file.filename)[1].lower()
            is_valid_mime, detected_mime = AdvancedValidator.validate_mime_type(file, [file_ext])
            if not is_valid_mime:
                current_app.logger.warning(f"Excel import MIME mismatch: claimed {file_ext}, detected {detected_mime}")
                flash('File content does not match its extension. Please upload a valid Excel file.', 'danger')
                return redirect(url_for('organization.index', tab='countries'))
        except Exception as e:
            current_app.logger.warning(f"MIME validation error for Excel import: {e}")
            flash('Unable to validate file type. Please try again.', 'danger')
            return redirect(url_for('organization.index', tab='countries'))

        df = pd.read_excel(file, engine='openpyxl')
        required = ['Name', 'ISO3']
        missing = [c for c in required if c not in df.columns]
        if missing:
            flash(f'Missing required columns: {", ".join(missing)}', 'danger')
            return redirect(url_for('organization.index', tab='countries'))
        translatable = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        display_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
        overwrite = request.form.get('overwrite_existing') == 'on'
        imported = 0
        updated = 0
        errors = []
        for idx, row in df.iterrows():
            try:
                name = str(row['Name']).strip() if pd.notna(row.get('Name')) else ''
                iso3 = str(row['ISO3']).strip().upper() if pd.notna(row.get('ISO3')) else ''
                if not name or not iso3:
                    continue
                existing = Country.query.filter_by(iso3=iso3).first()
                if existing and not overwrite:
                    errors.append(f'ISO3 "{iso3}" already exists (row {idx + 2})')
                    continue
                trans = {}
                for code in translatable:
                    header = display_names.get(code, code.upper())
                    if header in df.columns and pd.notna(row.get(header)):
                        val = str(row[header]).strip()
                        if val:
                            trans[code] = val
                short_name = str(row['Short Name']).strip() if 'Short Name' in df.columns and pd.notna(row.get('Short Name')) else None
                short_name = short_name or None
                iso2 = str(row['ISO2']).strip().upper() if 'ISO2' in df.columns and pd.notna(row.get('ISO2')) else None
                iso2 = iso2 or None
                region = str(row['Region']).strip() if 'Region' in df.columns and pd.notna(row.get('Region')) else 'Other'
                region = region or 'Other'
                status = str(row['Status']).strip() if 'Status' in df.columns and pd.notna(row.get('Status')) else 'Active'
                status = status or 'Active'
                pref_lang = str(row['Preferred Language']).strip() if 'Preferred Language' in df.columns and pd.notna(row.get('Preferred Language')) else 'en'
                pref_lang = Country.normalize_language_code(pref_lang) if pref_lang else 'en'
                currency = str(row['Currency Code']).strip().upper() if 'Currency Code' in df.columns and pd.notna(row.get('Currency Code')) else None
                currency = currency or None
                if existing and overwrite:
                    existing.name = name
                    existing.short_name = short_name
                    existing.iso2 = iso2
                    existing.region = region
                    existing.status = status
                    existing.preferred_language = pref_lang
                    existing.currency_code = currency
                    existing.name_translations = trans
                    updated += 1
                else:
                    country = Country(
                        name=name,
                        short_name=short_name,
                        iso3=iso3,
                        iso2=iso2,
                        region=region,
                        status=status,
                        preferred_language=pref_lang,
                        currency_code=currency,
                        name_translations=trans,
                    )
                    db.session.add(country)
                    imported += 1
            except Exception as e:
                errors.append(f'Row {idx + 2}: error.')
        db.session.flush()
        if imported or updated:
            msg = f'Imported {imported} new countries'
            if updated:
                msg += f' and updated {updated} existing'
            flash(msg + '.', 'success')
        if errors:
            flash('Import issues: ' + '; '.join(errors[:5]) + ('...' if len(errors) > 5 else ''), 'warning')
        return redirect(url_for('organization.index', tab='countries'))
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error importing countries: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for('organization.index', tab='countries'))


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
        ns.name_translations = _collect_translations(form, 'name')
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
        _clear_translation_fields(form, 'name')
        # Now populate from actual translations in name_translations (only if they exist)
        _populate_translation_fields(form, ns, 'name_translations', 'name')

    if form.validate_on_submit():
        ns.name = form.name.data
        ns.code = form.code.data
        ns.description = form.description.data
        ns.country_id = form.country_id.data
        ns.is_active = form.is_active.data
        ns.display_order = form.display_order.data or 0
        ns.name_translations = _collect_translations(form, 'name')

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


# ==================== National Societies Excel Export/Import ====================

@bp.route('/national-societies/export', methods=['GET'])
@permission_required_any('admin.organization.manage', 'admin.countries.view')
def export_national_societies():
    """Export all national societies to an Excel file."""
    try:
        translatable = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        display_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
        nss = NationalSociety.query.join(Country).order_by(Country.name, NationalSociety.display_order, NationalSociety.name).all()
        data = []
        for ns in nss:
            row = {
                'ID': ns.id,
                'Name': ns.name or '',
                'Code': ns.code or '',
                'Description': ns.description or '',
                'Country ISO3': ns.country.iso3 if ns.country else '',
                'Country Name': ns.country.name if ns.country else '',
                'Is Active': 'Yes' if ns.is_active else 'No',
                'Display Order': ns.display_order or 0,
            }
            for code in translatable:
                header = display_names.get(code, code.upper())
                row[header] = (ns.name_translations or {}).get(code, '') or ''
            if ns.part_of and isinstance(ns.part_of, list):
                row['Part Of (Categories)'] = ', '.join(str(p) for p in ns.part_of)
            else:
                row['Part Of (Categories)'] = ''
            data.append(row)
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='National Societies', index=False)
            ws = writer.sheets['National Societies']
            for column in ws.columns:
                max_length = max(len(str(cell.value or '')) for cell in column)
                column_letter = column[0].column_letter
                ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
        output.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'national_societies_export_{timestamp}.xlsx',
        )
    except Exception as e:
        current_app.logger.error(f"Error exporting national societies: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for('organization.index', tab='nss'))


@bp.route('/national-societies/template', methods=['GET'])
@permission_required_any('admin.organization.manage', 'admin.countries.view')
def national_societies_template():
    """Download Excel template for national societies import."""
    try:
        translatable = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        display_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
        base_cols = ['Name', 'Code', 'Description', 'Country ISO3', 'Is Active', 'Display Order', 'Part Of (Categories)']
        name_cols = [display_names.get(code, code.upper()) for code in translatable]
        sample = [{
            'Name': 'Sample National Society',
            'Code': 'SNS',
            'Description': '',
            'Country ISO3': 'XXX',
            'Is Active': 'Yes',
            'Display Order': 0,
            'Part Of (Categories)': '',
        }]
        df = pd.DataFrame(sample, columns=base_cols)
        for header in name_cols:
            df[header] = ''
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='National Societies Template', index=False)
            ws = writer.sheets['National Societies Template']
            for column in ws.columns:
                max_length = max(len(str(cell.value or '')) for cell in column)
                column_letter = column[0].column_letter
                ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='national_societies_template.xlsx',
        )
    except Exception as e:
        current_app.logger.error(f"Error downloading national societies template: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for('organization.index', tab='nss'))


@bp.route('/national-societies/import', methods=['POST'])
@permission_required('admin.organization.manage')
def import_national_societies():
    """Import national societies from an uploaded Excel file."""
    try:
        if 'excel_file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(url_for('organization.index', tab='nss'))
        file = request.files['excel_file']
        if not file or file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(url_for('organization.index', tab='nss'))
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            flash('Invalid file format. Please upload an Excel file (.xlsx or .xls).', 'danger')
            return redirect(url_for('organization.index', tab='nss'))
        df = pd.read_excel(file, engine='openpyxl')
        required = ['Name', 'Country ISO3']
        missing = [c for c in required if c not in df.columns]
        if missing:
            flash(f'Missing required columns: {", ".join(missing)}', 'danger')
            return redirect(url_for('organization.index', tab='nss'))
        translatable = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        display_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
        overwrite = request.form.get('overwrite_existing') == 'on'
        imported = 0
        updated = 0
        errors = []
        for idx, row in df.iterrows():
            try:
                name = str(row['Name']).strip() if pd.notna(row.get('Name')) else ''
                country_iso3 = str(row['Country ISO3']).strip().upper() if pd.notna(row.get('Country ISO3')) else ''
                if not name or not country_iso3:
                    continue
                country = Country.query.filter_by(iso3=country_iso3).first()
                if not country:
                    errors.append(f'Country ISO3 "{country_iso3}" not found (row {idx + 2})')
                    continue
                code_val = str(row['Code']).strip() if 'Code' in df.columns and pd.notna(row.get('Code')) else None
                code_val = code_val or None
                existing = None
                if code_val:
                    existing = NationalSociety.query.filter_by(code=code_val).first()
                if not existing:
                    existing = NationalSociety.query.filter_by(name=name, country_id=country.id).first()
                if existing and not overwrite:
                    errors.append(f'NS "{name}" for {country_iso3} already exists (row {idx + 2})')
                    continue
                trans = {}
                for code in translatable:
                    header = display_names.get(code, code.upper())
                    if header in df.columns and pd.notna(row.get(header)):
                        val = str(row[header]).strip()
                        if val:
                            trans[code] = val
                description = str(row['Description']).strip() if 'Description' in df.columns and pd.notna(row.get('Description')) else None
                description = description or None
                is_active = True
                if 'Is Active' in df.columns and pd.notna(row.get('Is Active')):
                    v = str(row['Is Active']).strip().upper()
                    is_active = v in ('YES', 'TRUE', '1', 'ACTIVE')
                display_order = 0
                if 'Display Order' in df.columns and pd.notna(row.get('Display Order')):
                    try:
                        display_order = int(float(row['Display Order']))
                    except (ValueError, TypeError):
                        pass
                part_of = None
                part_of_col = 'Part Of (Categories)' if 'Part Of (Categories)' in df.columns else 'Part Of (Programs)'
                if part_of_col in df.columns and pd.notna(row.get(part_of_col)):
                    raw = str(row[part_of_col]).strip()
                    if raw:
                        part_of = [p.strip() for p in raw.split(',') if p.strip()]
                if existing and overwrite:
                    existing.name = name
                    existing.code = code_val
                    existing.description = description
                    existing.country_id = country.id
                    existing.is_active = is_active
                    existing.display_order = display_order
                    existing.name_translations = trans
                    if part_of is not None:
                        existing.part_of = part_of
                    updated += 1
                else:
                    ns = NationalSociety(
                        name=name,
                        code=code_val,
                        description=description,
                        country_id=country.id,
                        is_active=is_active,
                        display_order=display_order,
                        name_translations=trans,
                        part_of=part_of,
                    )
                    db.session.add(ns)
                    imported += 1
            except Exception as e:
                errors.append(f'Row {idx + 2}: error.')
        db.session.flush()
        if imported or updated:
            msg = f'Imported {imported} new national societies'
            if updated:
                msg += f' and updated {updated} existing'
            flash(msg + '.', 'success')
        if errors:
            flash('Import issues: ' + '; '.join(errors[:5]) + ('...' if len(errors) > 5 else ''), 'warning')
        return redirect(url_for('organization.index', tab='nss'))
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error importing national societies: {e}", exc_info=True)
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
        branch.name_translations = _collect_translations(form, 'name')
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
        _clear_translation_fields(form, 'name')
        _populate_translation_fields(form, branch, 'name_translations', 'name')

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
        branch.name_translations = _collect_translations(form, 'name')

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
        subbranch.name_translations = _collect_translations(form, 'name')
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
        _clear_translation_fields(form, 'name')
        _populate_translation_fields(form, subbranch, 'name_translations', 'name')

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
        subbranch.name_translations = _collect_translations(form, 'name')

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
        localunit.name_translations = _collect_translations(form, 'name')
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
        _clear_translation_fields(form, 'name')
        _populate_translation_fields(form, localunit, 'name_translations', 'name')

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
        localunit.name_translations = _collect_translations(form, 'name')

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
        division.name_translations = _collect_translations(form, 'name')
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
        _clear_translation_fields(form, 'name')
        _populate_translation_fields(form, division, 'name_translations', 'name')

    if form.validate_on_submit():
        division.name = form.name.data
        division.code = form.code.data
        division.description = form.description.data
        division.is_active = form.is_active.data
        division.display_order = form.display_order.data
        division.name_translations = _collect_translations(form, 'name')

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
        department.name_translations = _collect_translations(form, 'name')
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
        _clear_translation_fields(form, 'name')
        _populate_translation_fields(form, department, 'name_translations', 'name')

    if form.validate_on_submit():
        department.name = form.name.data
        department.code = form.code.data
        department.description = form.description.data
        department.division_id = form.division_id.data
        department.is_active = form.is_active.data
        department.display_order = form.display_order.data
        department.name_translations = _collect_translations(form, 'name')

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
            code=form.code.data,
            description=form.description.data,
            is_active=form.is_active.data,
            display_order=form.display_order.data or 0
        )
        region.name_translations = _collect_translations(form, 'name')
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
        _clear_translation_fields(form, 'name')
        _populate_translation_fields(form, region, 'name_translations', 'name')

    if form.validate_on_submit():
        region.name = form.name.data
        region.code = form.code.data
        region.description = form.description.data
        region.is_active = form.is_active.data
        region.display_order = form.display_order.data
        region.name_translations = _collect_translations(form, 'name')

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
        cluster.name_translations = _collect_translations(form, 'name')
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
        _clear_translation_fields(form, 'name')
        _populate_translation_fields(form, cluster, 'name_translations', 'name')

    if form.validate_on_submit():
        cluster.name = form.name.data
        cluster.code = form.code.data
        cluster.description = form.description.data
        cluster.regional_office_id = form.regional_office_id.data
        cluster.is_active = form.is_active.data
        cluster.display_order = form.display_order.data
        cluster.name_translations = _collect_translations(form, 'name')

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


# ==================== API Endpoints for Dynamic Selectors ====================

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

        # Initialize counts for all languages
        counts = {}
        for lang_code in Config.TRANSLATABLE_LANGUAGES:
            counts[lang_code] = 0

        def _merge_counts(extra_counts: Dict[str, int]):
            for lang_key, value in extra_counts.items():
                counts[lang_key] = counts.get(lang_key, 0) + value

        if entity_type == 'countries':
            _merge_counts(_count_missing_name_translations(Country.query.all()))

        elif entity_type == 'national_societies':
            _merge_counts(_count_missing_name_translations(NationalSociety.query.all()))

        elif entity_type == 'ns_structure':
            entities = (
                NSBranch.query.all()
                + NSSubBranch.query.all()
                + NSLocalUnit.query.all()
            )
            _merge_counts(_count_missing_name_translations(entities))

        elif entity_type == 'secretariat':
            secretariat_entities = (
                SecretariatDivision.query.all()
                + SecretariatDepartment.query.all()
                + SecretariatRegionalOffice.query.all()
                + SecretariatClusterOffice.query.all()
            )
            _merge_counts(_count_missing_name_translations(secretariat_entities))

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
        from app.utils.auto_translator import get_auto_translator
        from config.config import Config
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

        if not current_app.config.get('WEBSOCKET_ENABLED', True):
            current_app.logger.info('WebSocket is disabled; rejecting streaming translation request')
            return json_error(
                'Live translation streaming is disabled on this environment.',
                503,
                success=False,
                message='Live translation streaming is disabled on this environment.',
                websocket_enabled=False
            )

        # Normalize target languages to ISO codes (e.g., 'fr_FR' -> 'fr')
        normalized_languages = []
        for lang in target_languages:
            if isinstance(lang, str):
                lang_norm = lang.split('_', 1)[0].strip().lower()
                if lang_norm:
                    normalized_languages.append(lang_norm)

        if not normalized_languages:
            return json_bad_request('Invalid target languages')

        def generate():
            """Generator function that yields HTTP streaming events as translations complete."""
            try:
                from sqlalchemy.orm.attributes import flag_modified

                auto_translator = get_auto_translator()
                total_count = 0
                processed_count = 0
                success_count = 0
                error_count = 0

                # Process translations and stream results (combining count and process in one pass)
                if entity_type == 'countries':
                    # First pass: calculate total count
                    countries = Country.query.all()
                    for country in countries:
                        if not country.name or not country.name.strip():
                            continue
                        translations = country.name_translations or {}
                        for lang_code in Config.TRANSLATABLE_LANGUAGES:
                            if lang_code not in normalized_languages:
                                continue
                            if lang_code not in translations or not translations.get(lang_code, '').strip():
                                total_count += 1

                    # Send initial message with total count
                    yield f"data: {json.dumps({'type': 'start', 'total': total_count})}\n\n"

                    # Second pass: process translations
                    for country in countries:
                        if not country.name or not country.name.strip():
                            continue

                        translations = country.name_translations or {}
                        for lang_code in Config.TRANSLATABLE_LANGUAGES:
                            if lang_code not in normalized_languages:
                                continue
                            # Check if translation already exists (using short code)
                            if lang_code in translations and translations.get(lang_code, '').strip():
                                continue  # Already translated

                            # Translate
                            translated = auto_translator.translate_text(
                                country.name,
                                lang_code,
                                'en',
                                translation_service
                            )

                            if translated:
                                if not country.name_translations:
                                    country.name_translations = {}
                                # Store using short ISO code (e.g., 'fr')
                                country.name_translations[lang_code] = translated
                                # CRITICAL: Mark the JSONB field as modified so SQLAlchemy detects the change
                                flag_modified(country, 'name_translations')

                                result = {
                                    'success': True,
                                    'entity_type': 'country',
                                    'entity_id': country.id,
                                    'language': lang_code
                                }
                                success_count += 1
                            else:
                                result = {
                                    'success': False,
                                    'entity_type': 'country',
                                    'entity_id': country.id,
                                    'language': lang_code,
                                    'error': 'Translation service returned no result'
                                }
                                error_count += 1

                            processed_count += 1

                            # Persist changes to database (flush within current transaction)
                            try:
                                db.session.add(country)  # Ensure entity is in session
                                db.session.flush()
                            except Exception as e:
                                request_transaction_rollback()
                                current_app.logger.error(f"Error committing translation for country {country.id}, language {lang_code}: {e}")
                                result['success'] = False
                                result['error'] = GENERIC_ERROR_MESSAGE
                                error_count += 1
                                success_count -= 1  # Adjust counts since we marked it as success earlier

                            # Stream the result immediately after commit
                            yield f"data: {json.dumps({'type': 'progress', 'result': result, 'processed': processed_count, 'total': total_count, 'success': success_count, 'error': error_count})}\n\n"

                elif entity_type == 'national_societies':
                    # First pass: calculate total count
                    nss = NationalSociety.query.all()
                    for ns in nss:
                        if not ns.name or not ns.name.strip():
                            continue
                        translations = ns.name_translations or {}
                        for lang_code in Config.TRANSLATABLE_LANGUAGES:
                            if lang_code not in normalized_languages:
                                continue
                            if lang_code not in translations or not translations.get(lang_code, '').strip():
                                total_count += 1

                    # Send initial message with total count
                    yield f"data: {json.dumps({'type': 'start', 'total': total_count})}\n\n"

                    # Second pass: process translations
                    for ns in nss:
                        if not ns.name or not ns.name.strip():
                            continue

                        translations = ns.name_translations or {}
                        for lang_code in Config.TRANSLATABLE_LANGUAGES:
                            if lang_code not in normalized_languages:
                                continue
                            # Check if translation already exists (using short code)
                            if lang_code in translations and translations.get(lang_code, '').strip():
                                continue

                            translated = auto_translator.translate_text(
                                ns.name,
                                lang_code,
                                'en',
                                translation_service
                            )

                            if translated:
                                if not ns.name_translations:
                                    ns.name_translations = {}
                                # Store using short ISO code (e.g., 'fr')
                                ns.name_translations[lang_code] = translated
                                # CRITICAL: Mark the JSONB field as modified so SQLAlchemy detects the change
                                flag_modified(ns, 'name_translations')

                                result = {
                                    'success': True,
                                    'entity_type': 'national_society',
                                    'entity_id': ns.id,
                                    'language': lang_code
                                }
                                success_count += 1
                            else:
                                result = {
                                    'success': False,
                                    'entity_type': 'national_society',
                                    'entity_id': ns.id,
                                    'language': lang_code,
                                    'error': 'Translation service returned no result'
                                }
                                error_count += 1

                            processed_count += 1

                            # Persist changes to database (flush within current transaction)
                            try:
                                db.session.add(ns)  # Ensure entity is in session
                                db.session.flush()
                            except Exception as e:
                                request_transaction_rollback()
                                current_app.logger.error(f"Error committing translation for NS {ns.id}, language {lang_code}: {e}")
                                result['success'] = False
                                result['error'] = GENERIC_ERROR_MESSAGE
                                error_count += 1
                                success_count -= 1  # Adjust counts since we marked it as success earlier

                            # Stream the result immediately after commit
                            yield f"data: {json.dumps({'type': 'progress', 'result': result, 'processed': processed_count, 'total': total_count, 'success': success_count, 'error': error_count})}\n\n"

                elif entity_type == 'ns_structure':
                    yield f"data: {json.dumps({'type': 'error', 'message': 'NS Structure entities do not currently support translations. Translation fields need to be added to the models first.'})}\n\n"
                    return

                elif entity_type == 'secretariat':
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Secretariat entities do not currently support translations. Translation fields need to be added to the models first.'})}\n\n"
                    return

                else:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Invalid entity type'})}\n\n"
                    return

                # Send completion message (all commits already done per-translation)
                yield f"data: {json.dumps({'type': 'complete', 'processed': processed_count, 'total': total_count, 'success': success_count, 'error': error_count})}\n\n"

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
@admin_permission_required_any('admin.organization.manage', 'admin.countries.view')
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
        category_name = data.get('category_name') or data.get('program_name', '').strip()
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
