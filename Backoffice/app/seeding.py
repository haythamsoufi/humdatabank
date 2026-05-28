"""Development-only default data seeding."""

import os
import secrets

from sqlalchemy import inspect

from app.extensions import db


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
                from app.services.app_settings_service import (
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
                    country_id=test_country.id, name="Testland NS"
                ).first()
                if not ns_exists:
                    ns = NationalSociety(
                        name="Testland NS", country_id=test_country.id, is_active=True
                    )
                    db.session.add(ns)
                    db.session.commit()
                    app_instance.logger.info("Created default National Society for Testland")

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
                    admin.countries.append(test_country)
                    db.session.add(admin)
                    db.session.flush()

                    try:
                        from app.models.rbac import RbacRole, RbacUserRole

                        admin_role = RbacRole.query.filter_by(code="admin_core").first()
                        if not admin_role:
                            admin_role = RbacRole(
                                code="admin_core",
                                name="Admin (Core)",
                                description="Baseline admin role",
                            )
                            db.session.add(admin_role)
                            db.session.flush()

                        db.session.add(RbacUserRole(user_id=admin.id, role_id=admin_role.id))
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

            focal_point_user = User.query.filter_by(email=test_focal_email).first()
            if not focal_point_user:
                if test_country:
                    focal_password = os.environ.get('TEST_FOCAL_PASSWORD') or secrets.token_urlsafe(16)
                    focal_point = User(email=test_focal_email, name="Test Focal Point")
                    focal_point.set_password(focal_password)
                    focal_point.countries.append(test_country)
                    db.session.add(focal_point)
                    db.session.flush()

                    try:
                        from app.models.rbac import RbacRole, RbacUserRole

                        fp_role = RbacRole.query.filter_by(code="assignment_editor_submitter").first()
                        if not fp_role:
                            fp_role = RbacRole(
                                code="assignment_editor_submitter",
                                name="Assignment Editor/Submitter",
                                description="Enter/edit/submit assignments for assigned entities",
                            )
                            db.session.add(fp_role)
                            db.session.flush()

                        db.session.add(RbacUserRole(user_id=focal_point.id, role_id=fp_role.id))
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
            elif focal_point_user and test_country and not focal_point_user.countries.first():
                focal_point_user.countries.append(test_country)
                db.session.commit()
                app_instance.logger.info(
                    "Assigned Testland to default focal point user '%s'",
                    focal_point_user.email,
                )
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
                    sys_manager.countries.append(test_country)
                    db.session.add(sys_manager)
                    db.session.flush()

                    try:
                        from app.models.rbac import RbacRole, RbacUserRole

                        sys_role = RbacRole.query.filter_by(code="system_manager").first()
                        if not sys_role:
                            sys_role = RbacRole(
                                code="system_manager",
                                name="System Manager",
                                description="Full access (superuser).",
                            )
                            db.session.add(sys_role)
                            db.session.flush()

                        db.session.add(RbacUserRole(user_id=sys_manager.id, role_id=sys_role.id))
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

        except Exception as e:
            db.session.rollback()
            app_instance.logger.error("Error during default data check/creation: %s", e, exc_info=True)
            raise
