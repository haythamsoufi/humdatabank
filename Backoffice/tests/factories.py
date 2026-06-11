"""
Test data factories for creating test objects.

This module provides factory functions to create test data consistently
across all tests, reducing boilerplate and improving test readability.
"""
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func

from app.models import User, Country, FormTemplate, FormTemplateVersion, FormItem, FormSection, LookupList
from app.models import IndicatorBank, IndicatorSuggestion, AssignedForm, PublicSubmission
from app.models import APIKey
from app.models.assignments import AssignmentEntityStatus
from app.models.core import UserEntityPermission
from app.models.enums import EntityType
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
        sp = db_session.begin_nested()
        try:
            db_session.flush()
            sp.commit()
        except Exception:
            sp.rollback()
            db_session.expunge(role)
            role = db_session.query(RbacRole).filter_by(code=code).first()
            if role:
                return int(role.id)
            raise
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
        sp = db_session.begin_nested()
        try:
            db_session.flush()
            sp.commit()
        except Exception:
            sp.rollback()
            db_session.expunge(role)
            role = db_session.query(RbacRole).filter_by(code=code).first()
            if role:
                return int(role.id)
            raise
        return int(role.id)

    def _ensure_permission(code: str) -> int:
        perm = db_session.query(RbacPermission).filter_by(code=code).first()
        if perm:
            return int(perm.id)
        perm = RbacPermission(code=code, name=code, description=code)
        db_session.add(perm)
        sp = db_session.begin_nested()
        try:
            db_session.flush()
            sp.commit()
        except Exception:
            sp.rollback()
            db_session.expunge(perm)
            perm = db_session.query(RbacPermission).filter_by(code=code).first()
            if perm:
                return int(perm.id)
            raise
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

    # Optional granular toggles (backward compatible with legacy kwargs names)
    if kwargs.get("can_manage_users", True):
        _grant(role_id, "admin.users.view")
        _grant(role_id, "admin.users.edit")
        _grant(role_id, "admin.users.create")
        _grant(role_id, "admin.users.deactivate")
        _grant(role_id, "admin.users.delete")
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
        _grant(role_id, "admin.resources.manage")
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
    # Additional permissions for mobile admin endpoints
    _grant(role_id, "admin.access_requests.view")
    _grant(role_id, "admin.access_requests.manage")
    _grant(role_id, "admin.access_requests.approve")
    _grant(role_id, "admin.access_requests.reject")
    _grant(role_id, "admin.organization.manage")
    _grant(role_id, "admin.organization.view")
    _grant(role_id, "admin.indicator_bank.view")
    _grant(role_id, "admin.indicator_bank.edit")
    _grant(role_id, "admin.indicator_bank.archive")
    _grant(role_id, "admin.indicator_bank.delete")
    _grant(role_id, "admin.translations.view")
    _grant(role_id, "admin.translations.edit")
    _grant(role_id, "admin.translations.manage")
    _grant(role_id, "admin.notifications.manage")
    _grant(role_id, "admin.assignments.public_submissions.manage")
    _grant(role_id, "admin.assignments.entities.manage")
    _grant(role_id, "admin.assignments.create")
    _grant(role_id, "admin.assignments.delete")
    _grant(role_id, "admin.templates.delete")
    _grant(role_id, "admin.analytics.manage")

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
    owner_id = kwargs.pop('owner_id', None)

    # Create the template first
    template = FormTemplate()
    if owner_id is not None:
        template.owned_by = owner_id
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

    # Set as published version when status is published
    if kwargs.get('status', 'published') == 'published':
        template.published_version_id = version.id

    db_session.commit()
    db_session.refresh(template)
    return template


def create_test_draft_version(db_session, template, **kwargs):
    """Create a draft FormTemplateVersion for an existing template."""
    max_version = (
        db_session.query(func.max(FormTemplateVersion.version_number))
        .filter_by(template_id=template.id)
        .scalar()
    )
    next_version_number = (max_version or 0) + 1
    counter = _get_unique_suffix()

    version = FormTemplateVersion(
        template_id=template.id,
        version_number=kwargs.get('version_number', next_version_number),
        status='draft',
        name=kwargs.get('name', f"Draft Version {counter}"),
        description=kwargs.get('description', f"Draft description {counter}"),
    )
    db_session.add(version)
    db_session.commit()
    db_session.refresh(version)
    return version


def create_test_section(db_session, template, version=None, **kwargs):
    """Create a FormSection for a template version."""
    if version is None:
        version = db_session.query(FormTemplateVersion).filter_by(
            id=template.published_version_id
        ).first()
        if version is None:
            version = (
                db_session.query(FormTemplateVersion)
                .filter_by(template_id=template.id)
                .order_by(FormTemplateVersion.created_at.desc())
                .first()
            )

    counter = _get_unique_suffix()
    section = FormSection(
        template_id=template.id,
        version_id=version.id,
        name=kwargs.get('name', f"Test Section {counter}"),
        order=kwargs.get('order', 1),
        section_type=kwargs.get('section_type', 'standard'),
        parent_section_id=kwargs.get('parent_section_id'),
        archived=kwargs.get('archived', False),
    )
    db_session.add(section)
    db_session.commit()
    db_session.refresh(section)
    return section


def create_test_item(db_session, section, template, version=None, item_type="indicator", **kwargs):
    """Create a FormItem in a section."""
    if version is None:
        version = db_session.query(FormTemplateVersion).filter_by(
            id=section.version_id
        ).first()

    counter = _get_unique_suffix()
    defaults = {
        'section_id': section.id,
        'template_id': template.id,
        'version_id': version.id,
        'item_type': item_type,
        'label': kwargs.get('label', f"Test Item {counter}"),
        'order': kwargs.get('order', 1),
        'archived': kwargs.get('archived', False),
    }
    if item_type == 'indicator':
        defaults['type'] = kwargs.get('type', 'number')
        defaults['indicator_bank_id'] = kwargs.get('indicator_bank_id')
    elif item_type == 'question':
        defaults['type'] = kwargs.get('type', 'text')

    defaults.update({k: v for k, v in kwargs.items() if k not in defaults})
    item = FormItem(**defaults)
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def create_test_api_key(db_session, **kwargs):
    """Helper to create a test API key in the database.

    Returns:
        tuple: (api_key_obj, full_key_string)
    """
    counter = _get_unique_suffix()

    # Generate new API key
    full_key, key_id, key_hash, key_prefix = APIKey.generate_key()

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


def create_test_assignment_entity_status(
    db_session,
    *,
    country=None,
    template=None,
    status="in_progress",
    period_name="2024",
    commit=True,
    **kwargs,
):
    """Create AssignedForm + AssignmentEntityStatus for integration/route tests."""
    if country is None:
        country = create_test_country(db_session)
    if template is None:
        template = create_test_template(db_session)

    assigned_form = AssignedForm(
        template_id=template.id,
        period_name=period_name,
        **{k: v for k, v in kwargs.items() if k in ("is_active", "unique_token", "is_public_active")},
    )
    db_session.add(assigned_form)
    db_session.flush()

    aes = AssignmentEntityStatus(
        assigned_form_id=assigned_form.id,
        entity_type=EntityType.country.value,
        entity_id=country.id,
        status=status,
    )
    db_session.add(aes)
    if commit:
        db_session.commit()
        db_session.refresh(aes)
    else:
        db_session.flush()
    return aes


def _ensure_permission(db_session, code: str, name: str | None = None) -> int:
    perm = db_session.query(RbacPermission).filter_by(code=code).first()
    if perm:
        return int(perm.id)
    perm = RbacPermission(code=code, name=name or code, description=code)
    db_session.add(perm)
    db_session.flush()
    return int(perm.id)


def _grant_role_permission(db_session, role_code: str, perm_code: str) -> None:
    role = db_session.query(RbacRole).filter_by(code=role_code).first()
    if not role:
        return
    pid = _ensure_permission(db_session, perm_code)
    existing = (
        db_session.query(RbacRolePermission)
        .filter_by(role_id=role.id, permission_id=pid)
        .first()
    )
    if not existing:
        db_session.add(RbacRolePermission(role_id=role.id, permission_id=pid))


def _grant_entity_permission(db_session, user, entity_type, entity_id):
    """Grant UserEntityPermission if not already present."""
    existing = (
        db_session.query(UserEntityPermission)
        .filter_by(user_id=user.id, entity_type=entity_type, entity_id=entity_id)
        .first()
    )
    if existing:
        return existing
    perm = UserEntityPermission(
        user_id=user.id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db_session.add(perm)
    db_session.flush()
    return perm


def create_focal_point_with_country(db_session, *, country=None, **user_kwargs):
    """Focal-point user with entity permission and an in-progress assignment.

    Returns:
        tuple: (user, country, assignment_entity_status)
    """
    if country is None:
        country = create_test_country(db_session)

    user_kwargs.setdefault("role", "focal_point")
    user = create_test_user(db_session, **user_kwargs)

    for perm_code in (
        "assignment.view",
        "assignment.edit",
        "assignment.submit",
    ):
        _grant_role_permission(db_session, "assignment_editor_submitter", perm_code)

    _grant_entity_permission(db_session, user, EntityType.country.value, country.id)
    try:
        if country not in user.countries:
            user.countries.append(country)
    except Exception:
        pass

    aes = create_test_assignment_entity_status(db_session, country=country, commit=False)
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(aes)
    return user, country, aes


def create_test_public_submission(
    db_session,
    *,
    country=None,
    template=None,
    period_name="2024",
    status="pending",
    **kwargs,
):
    """Create AssignedForm configured for public access plus a PublicSubmission row."""
    if country is None:
        country = create_test_country(db_session)
    if template is None:
        template = create_test_template(db_session)

    token = kwargs.pop("unique_token", str(uuid4()))
    assigned_form = AssignedForm(
        template_id=template.id,
        period_name=period_name,
        unique_token=token,
        is_public_active=True,
        is_active=True,
    )
    db_session.add(assigned_form)
    db_session.flush()
    assigned_form.public_countries.append(country)

    submission = PublicSubmission(
        assigned_form_id=assigned_form.id,
        country_id=country.id,
        submitter_name=kwargs.pop("submitter_name", "Public User"),
        submitter_email=kwargs.pop("submitter_email", "public@example.com"),
        status=status,
        **kwargs,
    )
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)
    return submission, assigned_form, token
