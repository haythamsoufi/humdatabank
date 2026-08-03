"""
Organization Management Routes - Unified management for all organizational entities.

This blueprint provides CRUD operations for:
- Countries
- NS Branches, Sub-branches, and Local Units
- Secretariat Divisions and Departments
"""
from flask import Blueprint, flash, redirect, url_for, request
from flask_login import current_user

from app.utils.api_responses import json_error

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
        from app.services.organization.authorization_service import AuthorizationService
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
        "organization.import_countries",
    }
    if endpoint in country_mutation_endpoints:
        if (
            AuthorizationService.has_rbac_permission(current_user, "admin.countries.edit")
            or AuthorizationService.has_rbac_permission(current_user, "admin.organization.manage")
        ):
            return None
        flash("Access denied. Country edit permission required.", "warning")
        return redirect(url_for("main.dashboard"))

    # Country / NS export & templates: allow view or edit
    country_read_endpoints = {
        "organization.export_countries",
        "organization.countries_template",
        "organization.export_national_societies",
        "organization.national_societies_template",
    }
    if endpoint in country_read_endpoints:
        if (
            AuthorizationService.has_rbac_permission(current_user, "admin.countries.view")
            or AuthorizationService.has_rbac_permission(current_user, "admin.countries.edit")
            or AuthorizationService.has_rbac_permission(current_user, "admin.organization.manage")
        ):
            return None
        flash("Access denied.", "warning")
        return redirect(url_for("main.dashboard"))

    # Intentionally public selector APIs (no auth on decorator; do not block logged-in viewers)
    public_api_endpoints = {
        "organization.api_get_branches_by_country_public",
        "organization.api_get_subbranches_by_branch_public",
        "organization.api_get_subbranches_by_country_public",
    }
    if endpoint in public_api_endpoints:
        return None

    # Read-only APIs used by the organization index for country viewers
    # (must stay aligned with the route-level @admin_permission_required_any decorators)
    country_viewer_read_apis = {
        "organization.api_get_part_of_programs",
    }
    if endpoint in country_viewer_read_apis:
        if (
            AuthorizationService.has_rbac_permission(current_user, "admin.countries.view")
            or AuthorizationService.has_rbac_permission(current_user, "admin.countries.edit")
            or AuthorizationService.has_rbac_permission(current_user, "admin.organization.manage")
        ):
            return None
        if request.path.startswith("/admin/organization/api/"):
            return json_error("Access denied.", status=403)
        flash("Access denied.", "warning")
        return redirect(url_for("main.dashboard"))

    # Everything else here is organization structure management
    if not AuthorizationService.has_rbac_permission(current_user, "admin.organization.manage"):
        # Prefer JSON 403 for API calls so clients don't try to parse an HTML redirect
        if request.path.startswith("/admin/organization/api/"):
            return json_error("Access denied. Organization management permission required.", status=403)
        flash("Access denied. Organization management permission required.", "warning")
        return redirect(url_for("main.dashboard"))

    return None


# Register route modules (must follow bp definition)
from app.routes.admin.organization import countries, import_export, ns_structure, secretariat  # noqa: E402, F401

# Re-export forms and helpers for backward compatibility
from app.forms.organization import (  # noqa: E402
    CountryForm,
    NationalSocietyForm,
    NSBranchForm,
    NSSubBranchForm,
    NSLocalUnitForm,
    SecretariatDivisionForm,
    SecretariatDepartmentForm,
    SecretariatRegionalOfficeForm,
    SecretariatClusterOfficeForm,
    count_missing_name_translations,
    regional_office_translation_fields,
    resolve_field_translation,
    get_translation_languages,
    get_translation_codes,
)

__all__ = [
    "bp",
    "CountryForm",
    "NationalSocietyForm",
    "NSBranchForm",
    "NSSubBranchForm",
    "NSLocalUnitForm",
    "SecretariatDivisionForm",
    "SecretariatDepartmentForm",
    "SecretariatRegionalOfficeForm",
    "SecretariatClusterOfficeForm",
    "count_missing_name_translations",
    "regional_office_translation_fields",
    "resolve_field_translation",
    "get_translation_languages",
    "get_translation_codes",
]
