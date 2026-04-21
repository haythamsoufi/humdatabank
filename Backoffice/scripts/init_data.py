#!/usr/bin/env python3
"""
Default data initialization script
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

# Set up environment
# Note: DATABASE_URL should be provided via environment variable, not hardcoded
# Only set FLASK_CONFIG if not already set
if 'FLASK_CONFIG' not in os.environ:
    os.environ['FLASK_CONFIG'] = 'production'

from sqlalchemy.exc import IntegrityError

def main():
    try:
        flask_config = (os.environ.get('FLASK_CONFIG') or '').strip().lower()
        if flask_config in ('production', 'staging'):
            logger.error(
                "Refusing to seed test data in %s environment. "
                "This script is for local development only.",
                flask_config,
            )
            return 1

        from app import create_app
        from app.models import User, Country
        from app.models.organization import NationalSociety
        from sqlalchemy import inspect
        from app.extensions import db
        from app.utils.transactions import atomic

        app = create_app()
        with app.app_context():
            # Check if tables exist
            inspector = inspect(db.engine)
            essential_tables = ['user', 'country']

            if all(inspector.has_table(table) for table in essential_tables):
                # Initialize default system settings if system_settings table exists and is empty
                if inspector.has_table('system_settings'):
                    from app.models.system import SystemSettings
                    settings_count = SystemSettings.query.count()
                    if settings_count == 0:
                        logger.info('Initializing default system settings...')
                        from app.services.app_settings_service import set_supported_languages, set_document_types, set_age_groups, set_sex_categories, set_enabled_entity_types

                        # Set default languages
                        set_supported_languages(["en", "fr", "es", "ar", "ru", "zh"], user_id=None)
                        logger.info('  - Set default languages: en, fr, es, ar, ru, zh')

                        # Set default document types
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
                            "Other"
                        ]
                        set_document_types(default_document_types, user_id=None)
                        logger.info('  - Set default document types: %d types', len(default_document_types))

                        # Set default age groups
                        default_age_groups = ["<5", "5-17", "18-49", "50+", "Unknown"]
                        set_age_groups(default_age_groups, user_id=None)
                        logger.info('  - Set default age groups: %s', ", ".join(default_age_groups))

                        # Set default sex categories
                        default_sex_categories = ["Male", "Female", "Non-binary", "Unknown"]
                        set_sex_categories(default_sex_categories, user_id=None)
                        logger.info('  - Set default sex categories: %s', ", ".join(default_sex_categories))

                        # Set default enabled entity types
                        set_enabled_entity_types(["countries", "ns_structure", "secretariat"], user_id=None)
                        logger.info('  - Set default enabled entity types: countries, ns_structure, secretariat')

                        logger.info('Default system settings initialized!')

                # Check if data already exists
                user_count = User.query.count()
                if user_count == 0:
                    logger.info('Creating default data...')

                    # Create test country
                    testland_exists = Country.query.filter_by(name='Testland').first()
                    if not testland_exists:
                        test_country = Country(
                            name='Testland',
                            iso3='TST',
                            region='Europe'
                        )
                        with atomic(remove_session=True):
                            db.session.add(test_country)
                        logger.info('Created default country Testland')
                        # `atomic(remove_session=True)` detaches ORM instances; re-load from DB
                        # to avoid "Instance ... is not bound to a Session" errors.
                        test_country = Country.query.filter_by(iso3='TST').first()
                    else:
                        test_country = testland_exists

                    if test_country:
                        # Cache ID before any session-removing operations.
                        test_country_id = test_country.id
                        ns_exists = NationalSociety.query.filter_by(
                            country_id=test_country_id,
                            name='Testland NS'
                        ).first()
                        if not ns_exists:
                            ns = NationalSociety(
                                name='Testland NS',
                                country_id=test_country_id,
                                is_active=True
                            )
                            with atomic(remove_session=True):
                                db.session.add(ns)
                            logger.info('Created default National Society for Testland')

                    # Ensure baseline RBAC roles exist (legacy-free)
                    from app.models.rbac import RbacRole, RbacUserRole
                    def _ensure_role(code: str, name: str) -> int:
                        role = RbacRole.query.filter_by(code=code).first()
                        if role:
                            return int(role.id)
                        role = RbacRole(code=code, name=name)
                        db.session.add(role)
                        db.session.flush()
                        return int(role.id)

                    admin_role_id = _ensure_role("admin_core", "Admin (Core)")
                    focal_role_id = _ensure_role("assignment_editor_submitter", "Assignment Editor/Submitter")
                    sys_role_id = _ensure_role("system_manager", "System Manager")

                    # Create admin user
                    admin_exists = User.query.filter_by(email='test_admin@humdatabank.org').first()
                    if not admin_exists:
                        admin = User(email='test_admin@humdatabank.org', name='Test Admin')
                        admin.set_password('test123')
                        try:
                            with atomic(remove_session=True):
                                # Attach country (best-effort)
                                if test_country:
                                    country = Country.query.get(test_country_id)
                                    if country:
                                        admin.countries.append(country)
                                db.session.add(admin)
                                db.session.flush()
                                db.session.add(RbacUserRole(user_id=admin.id, role_id=admin_role_id))
                            logger.info('Created default admin user')
                        except IntegrityError:
                            logger.info('Default admin user already exists (skipped)')

                    # Create second admin user
                    second_admin_exists = User.query.filter_by(email='test_admin2@humdatabank.org').first()
                    if not second_admin_exists:
                        admin2 = User(email='test_admin2@humdatabank.org', name='Test Admin 2')
                        admin2.set_password('test123')
                        try:
                            with atomic(remove_session=True):
                                if test_country:
                                    country = Country.query.get(test_country_id)
                                    if country:
                                        admin2.countries.append(country)
                                db.session.add(admin2)
                                db.session.flush()
                                db.session.add(RbacUserRole(user_id=admin2.id, role_id=admin_role_id))
                            logger.info('Created second default admin user')
                        except IntegrityError:
                            logger.info('Second default admin user already exists (skipped)')

                    # Create focal point user
                    focal_point_exists = User.query.filter_by(email='test_focal@humdatabank.org').first()
                    if not focal_point_exists:
                        focal_point = User(email='test_focal@humdatabank.org', name='Test Focal Point')
                        focal_point.set_password('test123')
                        try:
                            with atomic(remove_session=True):
                                if test_country:
                                    country = Country.query.get(test_country_id)
                                    if country:
                                        focal_point.countries.append(country)
                                db.session.add(focal_point)
                                db.session.flush()
                                db.session.add(RbacUserRole(user_id=focal_point.id, role_id=focal_role_id))
                            logger.info('Created default focal point user')
                        except IntegrityError:
                            logger.info('Default focal point user already exists (skipped)')

                    # Create second focal point user
                    second_focal_exists = User.query.filter_by(email='test_focal2@humdatabank.org').first()
                    if not second_focal_exists:
                        focal_point2 = User(email='test_focal2@humdatabank.org', name='Test Focal Point 2')
                        focal_point2.set_password('test123')
                        try:
                            with atomic(remove_session=True):
                                if test_country:
                                    country = Country.query.get(test_country_id)
                                    if country:
                                        focal_point2.countries.append(country)
                                db.session.add(focal_point2)
                                db.session.flush()
                                db.session.add(RbacUserRole(user_id=focal_point2.id, role_id=focal_role_id))
                            logger.info('Created second default focal point user')
                        except IntegrityError:
                            logger.info('Second default focal point user already exists (skipped)')

                    # Create system manager user
                    sys_manager_exists = User.query.filter_by(email='test_sys@humdatabank.org').first()
                    if not sys_manager_exists:
                        sys_manager = User(email='test_sys@humdatabank.org', name='Test System Manager')
                        sys_manager.set_password('test123')
                        try:
                            with atomic(remove_session=True):
                                if test_country:
                                    country = Country.query.get(test_country_id)
                                    if country:
                                        sys_manager.countries.append(country)
                                db.session.add(sys_manager)
                                db.session.flush()
                                db.session.add(RbacUserRole(user_id=sys_manager.id, role_id=sys_role_id))
                            logger.info('Created default system manager user')
                        except IntegrityError:
                            logger.info('Default system manager user already exists (skipped)')

                    logger.info('Default data creation complete!')
                else:
                    logger.info('Found %d existing users, skipping default data creation', user_count)
            else:
                logger.info('Essential tables do not exist, skipping default data creation')

    except Exception as e:
        logger.error("Error creating default data: %s", e)
        sys.exit(1)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
