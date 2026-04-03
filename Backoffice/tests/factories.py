"""
Test data factories for creating test objects.

This module provides factory functions to create test data consistently
across all tests, reducing boilerplate and improving test readability.
"""
from datetime import datetime, timedelta
from app.models import User, Country, FormTemplate, FormTemplateVersion, FormItem, LookupList
from app.models import IndicatorBank, IndicatorSuggestion, AssignedForm, PublicSubmission
from app.models import APIKey
from app.models.rbac import RbacRole, RbacPermission, RbacRolePermission, RbacUserRole

# Counter for generating unique values.
# SECURITY/RELIABILITY: avoid time-based seeding which can collide in parallel runs.
import uuid as _uuid
_run_id = _uuid.uuid4().hex[:8]
_counter = 0


def _get_next_counter() -> int:
    """Get next integer counter value for unique generation."""
    global _counter
    _counter += 1
    return _counter


def _get_unique_suffix() -> str:
    """Get a run-scoped unique suffix safe for string identifiers."""
    return f"{_run_id}_{_get_next_counter()}"


def create_test_user(db_session, **kwargs):
    """Helper to create a test user in the database."""
    counter = _get_unique_suffix()
    email = kwargs.get('email', f"user{counter}@example.com")

    # Check if user with this email already exists
    existing = db_session.query(User).filter_by(email=email).first()
    if existing:
        # Update existing user if needed
        for key, value in kwargs.items():
            if key != 'password' and hasattr(existing, key):
                setattr(existing, key, value)
        if 'password' in kwargs:
            existing.set_password(kwargs['password'])
        db_session.commit()
        db_session.refresh(existing)
        return existing

    # Backward-compatible: callers may pass legacy `role` ("admin"/"focal_point"/"system_manager"/"user").
    access_level = (kwargs.get("role") or "user").strip()
    defaults = {
        'email': email,
        'name': kwargs.get('name', f"Test User {counter}"),
        'active': kwargs.get('active', True)
    }
    # Extract password before updating defaults to avoid passing it to User constructor
    password = kwargs.pop('password', 'TestPassword123!')
    # Exclude non-User-column kwargs (role is handled above for RBAC mapping)
    _skip_keys = {'password', 'role'}
    defaults.update({k: v for k, v in kwargs.items() if k not in _skip_keys})

    user = User(**defaults)
    user.set_password(password)

    db_session.add(user)
    db_session.flush()

    # RBAC role assignment (legacy-free)
    def _ensure_role(code: str, name: str) -> int:
        role = db_session.query(RbacRole).filter_by(code=code).first()
        if role:
            return int(role.id)
        role = RbacRole(code=code, name=name)
        db_session.add(role)
        db_session.flush()
        return int(role.id)

    role_codes = []
    if access_level == "system_manager":
        role_codes = ["system_manager"]
    elif access_level == "focal_point":
        role_codes = ["assignment_editor_submitter"]
    elif access_level == "admin":
        role_codes = ["admin_core"]
    else:
        role_codes = ["assignment_viewer"]

    role_name_by_code = {
        "system_manager": "System Manager",
        "admin_core": "Admin (Core)",
        "assignment_editor_submitter": "Assignment Editor/Submitter",
        "assignment_viewer": "Assignment Viewer",
    }
    for code in role_codes:
        rid = _ensure_role(code, role_name_by_code.get(code, code))
        db_session.add(RbacUserRole(user_id=user.id, role_id=rid))

    db_session.commit()
    db_session.refresh(user)
    return user


def create_test_admin(db_session, **kwargs):
    """Helper to create a test admin user in the database."""
    counter = _get_unique_suffix()
    defaults = {
        'email': kwargs.get('email', f"admin{counter}@example.com"),
        'name': kwargs.get('name', f"Test Admin {counter}"),
        'active': kwargs.get('active', True),
    }
    # Extract password before updating defaults; exclude non-User-column kwargs
    password = kwargs.pop('password', 'TestPassword123!')
    _skip_keys = {'password', 'can_manage_users', 'can_manage_templates',
                  'can_manage_assignments', 'can_manage_countries',
                  'can_manage_indicator_bank', 'can_manage_content',
                  'can_manage_api_keys', 'can_manage_system'}
    defaults.update({k: v for k, v in kwargs.items() if k not in _skip_keys})

    user = User(**defaults)
    user.set_password(password)

    db_session.add(user)
    db_session.flush()

    # RBAC: make the user an admin by granting admin permissions via a role
    def _ensure_role(code: str, name: str) -> int:
        role = db_session.query(RbacRole).filter_by(code=code).first()
        if role:
            return int(role.id)
        role = RbacRole(code=code, name=name)
        db_session.add(role)
        db_session.flush()
        return int(role.id)

    def _ensure_permission(code: str) -> int:
        perm = db_session.query(RbacPermission).filter_by(code=code).first()
        if perm:
            return int(perm.id)
        perm = RbacPermission(code=code, name=code, description=code)
        db_session.add(perm)
        db_session.flush()
        return int(perm.id)

    def _grant(role_id: int, perm_code: str) -> None:
        pid = _ensure_permission(perm_code)
        existing = db_session.query(RbacRolePermission).filter_by(role_id=role_id, permission_id=pid).first()
        if existing:
            return
        db_session.add(RbacRolePermission(role_id=role_id, permission_id=pid))

    # Always give the admin *some* admin permission so AuthorizationService.is_admin() is True.
    role_id = _ensure_role("admin_core", "Admin (Core)")
    db_session.add(RbacUserRole(user_id=user.id, role_id=role_id))
    _grant(role_id, "admin.analytics.view")

    # Optional granular toggles (backward compatible with legacy kwargs names)
    if kwargs.get("can_manage_users", True):
        _grant(role_id, "admin.users.view")
        _grant(role_id, "admin.users.edit")
    if kwargs.get("can_manage_templates", True):
        _grant(role_id, "admin.templates.view")
        _grant(role_id, "admin.templates.edit")
    if kwargs.get("can_manage_assignments", True):
        _grant(role_id, "admin.assignments.view")
        _grant(role_id, "admin.assignments.edit")
    if kwargs.get("can_manage_countries", True):
        _grant(role_id, "admin.countries.view")
        _grant(role_id, "admin.countries.edit")
    if kwargs.get("can_manage_publications", True):
        _grant(role_id, "admin.publications.manage")
        _grant(role_id, "admin.documents.manage")
    if kwargs.get("can_manage_api", True):
        _grant(role_id, "admin.api.manage")
    if kwargs.get("can_manage_plugins", True):
        _grant(role_id, "admin.plugins.manage")
    if kwargs.get("can_view_audit_trail", True):
        _grant(role_id, "admin.audit.view")
    if kwargs.get("can_view_analytics", True):
        _grant(role_id, "admin.analytics.view")
    if kwargs.get("can_explore_data", True):
        _grant(role_id, "admin.data_explore.data_table")
        _grant(role_id, "admin.data_explore.analysis")
        _grant(role_id, "admin.data_explore.compliance")

    db_session.commit()
    db_session.refresh(user)
    return user


def create_test_country(db_session, **kwargs):
    """Helper to create a test country in the database."""
    counter = _get_next_counter()

    # Generate unique ISO codes if not provided
    iso2 = kwargs.get('iso2')
    iso3 = kwargs.get('iso3')
    name = kwargs.get('name', f"Test Country {_run_id}_{counter}")

    # Check for existing country by name, ISO2, or ISO3
    existing = None
    if name:
        existing = db_session.query(Country).filter_by(name=name).first()
    if not existing and iso3:
        existing = db_session.query(Country).filter_by(iso3=iso3).first()
    if not existing and iso2:
        existing = db_session.query(Country).filter_by(iso2=iso2).first()

    if existing:
        # Return existing country instead of creating duplicate
        return existing

    # Generate unique ISO codes if not provided
    if not iso2:
        # Generate unique ISO2 code
        base = counter * 2
        iso2 = f"{chr(65 + (base % 26))}{chr(65 + ((base // 26) % 26))}"
        # Ensure uniqueness
        while db_session.query(Country).filter_by(iso2=iso2).first():
            base += 1
            iso2 = f"{chr(65 + (base % 26))}{chr(65 + ((base // 26) % 26))}"

    if not iso3:
        # Generate unique ISO3 code
        base = counter * 3
        iso3 = f"{chr(65 + (base % 26))}{chr(65 + ((base // 26) % 26))}{chr(65 + ((base // 676) % 26))}"
        # Ensure uniqueness
        while db_session.query(Country).filter_by(iso3=iso3).first():
            base += 1
            iso3 = f"{chr(65 + (base % 26))}{chr(65 + ((base // 26) % 26))}{chr(65 + ((base // 676) % 26))}"

    # Ensure name is unique
    if name:
        base_name = name
        name_counter = 1
        while db_session.query(Country).filter_by(name=name).first():
            name = f"{base_name} {name_counter}"
            name_counter += 1

    defaults = {
        'name': name,
        'iso2': iso2,
        'iso3': iso3,
        'region': kwargs.get('region', 'Europe')
    }
    defaults.update({k: v for k, v in kwargs.items() if k not in ['iso2', 'iso3', 'name', 'region']})

    country = Country(**defaults)
    db_session.add(country)
    db_session.commit()
    db_session.refresh(country)
    return country


def create_test_template(db_session, **kwargs):
    """Helper to create a test form template in the database.

    Creates a FormTemplate with a FormTemplateVersion (since template.name is a property
    that reads from the published version).
    """
    counter = _get_unique_suffix()
    template_name = kwargs.get('name', f"Test Template {counter}")
    template_description = kwargs.get('description', f"Test template description {counter}")

    # Create the template first
    template = FormTemplate()
    db_session.add(template)
    db_session.flush()  # Get the template ID

    # Create a version with the name
    version = FormTemplateVersion(
        template_id=template.id,
        version_number=kwargs.get('version', 1),
        status=kwargs.get('status', 'published'),
        name=template_name,
        description=template_description
    )
    db_session.add(version)
    db_session.flush()

    # Set as published version
    template.published_version_id = version.id

    db_session.commit()
    db_session.refresh(template)
    return template


def create_test_api_key(db_session, **kwargs):
    """Helper to create a test API key in the database.

    Returns:
        tuple: (api_key_obj, full_key_string)
    """
    counter = _get_unique_suffix()

    # Generate new API key
    full_key, key_hash, key_prefix = APIKey.generate_key()
    key_id = full_key[:32]

    defaults = {
        'key_id': key_id,
        'key_hash': key_hash,
        'key_prefix': key_prefix,
        'client_name': kwargs.get('client_name', f"Test Client {counter}"),
        'client_description': kwargs.get('client_description', f"Test API key {counter}"),
        'rate_limit_per_minute': kwargs.get('rate_limit_per_minute', 1000),
        'is_active': kwargs.get('is_active', True),
        'is_revoked': kwargs.get('is_revoked', False)
    }
    defaults.update(kwargs)

    api_key = APIKey(**defaults)
    db_session.add(api_key)
    db_session.commit()
    db_session.refresh(api_key)

    return api_key, full_key
