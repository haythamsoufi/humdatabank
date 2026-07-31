"""Development-only default data seeding."""

import os
import secrets

from sqlalchemy import inspect

from app.extensions import db

# Granular admin roles that match the "Full (All admin roles)" UI preset.
# Assigning these (not just the admin_full bundle role) keeps the user edit form
# in sync with what the account can actually do.
_DEV_TEST_ADMIN_ROLE_CODES = (
    "admin_core",
    "admin_docs_viewer",
    "admin_users_manager",
    "admin_templates_manager",
    "admin_assignments_manager",
    "admin_countries_manager",
    "admin_indicator_bank_manager",
    "admin_content_manager",
    "admin_documents_manager",
    "admin_communication_manager",
    "admin_translations_manager",
    "admin_analytics_viewer",
    "admin_audit_viewer",
    "admin_security_responder",
    "admin_ai_manager",
    "admin_governance_viewer",
    "admin_data_explorer_data_table",
    "admin_data_explorer_analysis",
    "admin_data_explorer_compliance",
    "admin_validation_dashboard",
    "admin_validation_questions",
    "admin_validation_rules",
    "admin_api_manager",
)

# Backward-compatible alias used by create_admin CLI.
_DEV_TEST_ADMIN_ROLE_CODE = "admin_full"


def _baseline_role_defs_by_code():
    from app.services.organization.rbac_seed_service import _baseline_roles, _permission_catalog

    catalog = _permission_catalog()
    return {
        str(role_def["code"]): role_def
        for role_def in _baseline_roles(catalog)
        if role_def.get("code")
    }


def _ensure_rbac_seeded(app_instance) -> None:
    """Best-effort RBAC catalog seed so role-permission links exist."""
    try:
        from app.services.organization.rbac_seed_service import seed_rbac_permissions_and_roles

        stats = seed_rbac_permissions_and_roles(use_advisory_lock=False)
        app_instance.logger.debug("RBAC seed during default data: %s", stats)
    except Exception as e:
        app_instance.logger.debug("RBAC seed skipped during default data: %s", e)


def _assign_role_to_user(user_id: int, role_code: str, *, name: str | None = None, description: str | None = None) -> bool:
    """Assign an RBAC role if missing. Returns True when a new link was added."""
    from app.models.rbac import RbacRole, RbacUserRole

    role = RbacRole.query.filter_by(code=role_code).first()
    if not role:
        role_def = _baseline_role_defs_by_code().get(role_code, {})
        role = RbacRole(
            code=role_code,
            name=name or role_def.get("name") or role_code,
            description=description if description is not None else role_def.get("description"),
        )
        db.session.add(role)
        db.session.flush()

    existing = RbacUserRole.query.filter_by(user_id=user_id, role_id=role.id).first()
    if existing:
        return False

    db.session.add(RbacUserRole(user_id=user_id, role_id=role.id))
    return True


def _assign_roles_to_user(user_id: int, role_codes) -> int:
    """Assign multiple RBAC roles. Returns count of newly added links."""
    added = 0
    for role_code in role_codes:
        if _assign_role_to_user(int(user_id), str(role_code)):
            added += 1
    return added


def _ensure_user_country_entity_permission(user, country_id: int | None, app_instance) -> None:
    """Grant Testland via UserEntityPermission (User.countries is view-only)."""
    from app.models.core import UserEntityPermission

    if not user or not country_id:
        return

    user_id = int(user.id)
    country_id = int(country_id)
    existing = UserEntityPermission.query.filter_by(
        user_id=user_id,
        entity_type="country",
        entity_id=country_id,
    ).first()
    if existing:
        return

    try:
        user.add_entity_permission(entity_type="country", entity_id=country_id)
        db.session.commit()
        app_instance.logger.info(
            "Granted Testland entity permission to '%s'",
            user.email,
        )
    except Exception as e:
        db.session.rollback()
        app_instance.logger.debug("Entity permission assignment failed for '%s': %s", user.email, e)


def _ensure_dev_test_admin_roles(user, app_instance) -> None:
    """Ensure the dev test admin has full admin permissions and matching UI roles."""
    try:
        added = _assign_roles_to_user(int(user.id), _DEV_TEST_ADMIN_ROLE_CODES)
        if added:
            db.session.commit()
            app_instance.logger.info(
                "Granted %d dev admin role(s) to test admin '%s'",
                added,
                user.email,
            )
    except Exception as e:
        db.session.rollback()
        app_instance.logger.debug("RBAC test admin role assignment failed: %s", e)


def create_default_data(app_instance):
    """Seed test country, RBAC roles, and test users. Development only."""
    flask_config = os.environ.get('FLASK_CONFIG', '').lower()
    if flask_config in ('production', 'staging'):
        app_instance.logger.warning(
            "Refusing to create test data in %s environment.", flask_config
        )
        return

    with app_instance.app_context():
        from app.models import User, Country
        from app.models.organization import NationalSociety

        inspector = inspect(db.engine)
        essential_tables = ["country", "user"]
        if not all(inspector.has_table(table_name) for table_name in essential_tables):
            app_instance.logger.warning(
                "Skipping default data creation: Essential tables (country, user) do not exist."
            )
            return

        app_instance.logger.info("Checking for default data...")
        try:
            if inspector.has_table("system_settings"):
                from app.models.system import SystemSettings
                from app.services.platform.app_settings_service import (
                    set_age_groups,
                    set_document_types,
                    set_enabled_entity_types,
                    set_sex_categories,
                    set_supported_languages,
                )

                if SystemSettings.query.count() == 0:
                    app_instance.logger.info("Initializing default system settings...")
                    set_supported_languages(["en", "fr", "es", "ar", "ru", "zh"], user_id=None)
                    app_instance.logger.info("  - Set default languages: en, fr, es, ar, ru, zh")

                    default_document_types = [
                        "Annual Report",
                        "Audited Financial Statement",
                        "Unaudited Financial Statement",
                        "Strategic Plan",
                        "Operational Plan",
                        "Evaluation Report",
                        "Policy Document",
                        "Unified Network Plan",
                        "Unified Network Annual Report",
                        "Unified Network Midyear Report",
                        "Legal Document",
                        "Cover Image",
                        "Agreement",
                        "Other",
                    ]
                    set_document_types(default_document_types, user_id=None)
                    app_instance.logger.info(
                        "  - Set default document types: %s types", len(default_document_types)
                    )

                    default_age_groups = ["<5", "5-17", "18-49", "50+", "Unknown"]
                    set_age_groups(default_age_groups, user_id=None)
                    app_instance.logger.info(
                        "  - Set default age groups: %s", ", ".join(default_age_groups)
                    )

                    default_sex_categories = ["Male", "Female", "Non-binary", "Unknown"]
                    set_sex_categories(default_sex_categories, user_id=None)
                    app_instance.logger.info(
                        "  - Set default sex categories: %s", ", ".join(default_sex_categories)
                    )

                    set_enabled_entity_types(
                        ["countries", "ns_structure", "secretariat"], user_id=None
                    )
                    app_instance.logger.info(
                        "  - Set default enabled entity types: countries, ns_structure, secretariat"
                    )
                    app_instance.logger.info("Default system settings initialized!")

            testland_exists = Country.query.filter_by(name="Testland").first()
            if not testland_exists:
                test_country = Country(name="Testland", iso3="TST", region="Europe")
                db.session.add(test_country)
                db.session.commit()
                app_instance.logger.info("Created default country 'Testland'")
            else:
                app_instance.logger.info("Default country 'Testland' already exists.")
                test_country = testland_exists

            if test_country:
                ns_exists = NationalSociety.query.filter_by(
                    country_id=test_country.id, name="Testlandic Red Emblem Society"
                ).first()
                if not ns_exists:
                    ns = NationalSociety(
                        name="Testland NS", country_id=test_country.id, is_active=True
                    )
                    db.session.add(ns)
                    db.session.commit()
                    app_instance.logger.info("Created default National Society for Testland")

            test_country_id = int(test_country.id) if test_country else None

            _ensure_rbac_seeded(app_instance)

            from app.utils.organization_helpers import get_org_email_domain

            org_email_domain = get_org_email_domain()
            test_admin_email = f"test_admin@{org_email_domain}"
            test_focal_email = f"test_focal@{org_email_domain}"

            admin_exists = User.query.filter_by(email=test_admin_email).first()
            if not admin_exists:
                if test_country:
                    admin_password = os.environ.get('TEST_ADMIN_PASSWORD') or secrets.token_urlsafe(16)
                    admin = User(email=test_admin_email, name="Test Admin User")
                    admin.set_password(admin_password)
                    db.session.add(admin)
                    db.session.flush()

                    try:
                        _assign_roles_to_user(int(admin.id), _DEV_TEST_ADMIN_ROLE_CODES)
                        if test_country_id:
                            admin.add_entity_permission(entity_type="country", entity_id=test_country_id)
                    except Exception as e:
                        app_instance.logger.debug("RBAC admin role assignment failed: %s", e)

                    db.session.commit()
                    if not os.environ.get('TEST_ADMIN_PASSWORD'):
                        app_instance.logger.info(
                            "Created default admin user '%s' with generated password. "
                            "Set TEST_ADMIN_PASSWORD environment variable to use a fixed password.",
                            test_admin_email,
                        )
                    else:
                        app_instance.logger.info(
                            "Created default admin user '%s' and assigned Testland",
                            test_admin_email,
                        )
                else:
                    app_instance.logger.warning(
                        "Default country 'Testland' not found, cannot create default admin."
                    )
            else:
                app_instance.logger.info("Default admin user '%s' already exists.", test_admin_email)
                _ensure_dev_test_admin_roles(admin_exists, app_instance)
                _ensure_user_country_entity_permission(admin_exists, test_country_id, app_instance)

            focal_point_user = User.query.filter_by(email=test_focal_email).first()
            if not focal_point_user:
                if test_country:
                    focal_password = os.environ.get('TEST_FOCAL_PASSWORD') or secrets.token_urlsafe(16)
                    focal_point = User(email=test_focal_email, name="Test Focal Point")
                    focal_point.set_password(focal_password)
                    db.session.add(focal_point)
                    db.session.flush()

                    try:
                        _assign_role_to_user(
                            int(focal_point.id),
                            "assignment_editor_submitter",
                            name="Assignment Editor/Submitter",
                            description="Enter/edit/submit assignments for assigned entities",
                        )
                        if test_country_id:
                            focal_point.add_entity_permission(entity_type="country", entity_id=test_country_id)
                    except Exception as e:
                        app_instance.logger.debug("RBAC focal point role assignment failed: %s", e)

                    db.session.commit()
                    if not os.environ.get('TEST_FOCAL_PASSWORD'):
                        app_instance.logger.info(
                            "Created default focal point user '%s' with generated password. "
                            "Set TEST_FOCAL_PASSWORD environment variable to use a fixed password.",
                            test_focal_email,
                        )
                    else:
                        app_instance.logger.info(
                            "Created default focal point user '%s' and assigned Testland",
                            test_focal_email,
                        )
                else:
                    app_instance.logger.warning(
                        "Default country 'Testland' not found, cannot create default focal point."
                    )
            elif focal_point_user and test_country_id:
                _ensure_user_country_entity_permission(focal_point_user, test_country_id, app_instance)
            elif focal_point_user:
                app_instance.logger.info(
                    "Default focal point user '%s' already has countries assigned or Testland doesn't exist.",
                    focal_point_user.email,
                )

            test_sys_email = f"test_sys@{org_email_domain}"
            sys_manager_user = User.query.filter_by(email=test_sys_email).first()
            if not sys_manager_user:
                if test_country:
                    sys_password = os.environ.get('TEST_SYS_MANAGER_PASSWORD') or secrets.token_urlsafe(16)
                    sys_manager = User(email=test_sys_email, name="Test System Manager")
                    sys_manager.set_password(sys_password)
                    db.session.add(sys_manager)
                    db.session.flush()

                    try:
                        _assign_role_to_user(
                            int(sys_manager.id),
                            "system_manager",
                            name="System Manager",
                            description="Full access (superuser).",
                        )
                        if test_country_id:
                            sys_manager.add_entity_permission(entity_type="country", entity_id=test_country_id)
                    except Exception as e:
                        app_instance.logger.debug("RBAC system manager role assignment failed: %s", e)

                    db.session.commit()
                    if not os.environ.get('TEST_SYS_MANAGER_PASSWORD'):
                        app_instance.logger.info(
                            "Created default system manager user '%s' with generated password. "
                            "Set TEST_SYS_MANAGER_PASSWORD environment variable to use a fixed password.",
                            test_sys_email,
                        )
                    else:
                        app_instance.logger.info(
                            "Created default system manager user '%s' and assigned Testland",
                            test_sys_email,
                        )
                else:
                    app_instance.logger.warning(
                        "Default country 'Testland' not found, cannot create default system manager."
                    )
            else:
                app_instance.logger.info(
                    "Default system manager user '%s' already exists.", test_sys_email
                )
                _ensure_user_country_entity_permission(sys_manager_user, test_country_id, app_instance)

        except Exception as e:
            db.session.rollback()
            app_instance.logger.error("Error during default data check/creation: %s", e, exc_info=True)
            raise
