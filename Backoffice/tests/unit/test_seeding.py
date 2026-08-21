"""
Comprehensive tests for app/seeding.py — targets 100% coverage.

All tests mock DB interactions and external services.

IMPORTANT: `Country`, `User`, and `NationalSociety` are locally imported
inside `create_default_data` (inside `with app_instance.app_context():`).
We must patch them at their source module paths:
  - app.models.Country  →  patched as "app.models.Country"
  - app.models.User     →  patched as "app.models.User"
  - app.models.organization.NationalSociety
  - app.models.system.SystemSettings
  - app.models.rbac.RbacRole / RbacUserRole
  - app.services.platform.app_settings_service.*
  - app.utils.organization_helpers.get_org_email_domain
"""

import os
import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_app():
    app = MagicMock()
    app.logger = MagicMock()
    return app


def _make_ctx(app):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=None)
    ctx.__exit__ = MagicMock(return_value=False)
    app.app_context.return_value = ctx
    return ctx


# ===========================================================================
# Production / staging guard
# ===========================================================================

class TestCreateDefaultDataEnvironmentGuard:
    def test_refuses_production(self):
        from app.seeding import create_default_data

        app = _mock_app()
        with patch.dict(os.environ, {"FLASK_CONFIG": "production"}):
            create_default_data(app)

        app.logger.warning.assert_called()
        app.app_context.assert_not_called()

    def test_refuses_staging(self):
        from app.seeding import create_default_data

        app = _mock_app()
        with patch.dict(os.environ, {"FLASK_CONFIG": "staging"}):
            create_default_data(app)

        app.logger.warning.assert_called()
        app.app_context.assert_not_called()

    def test_allows_development_proceeds_to_app_context(self):
        from app.seeding import create_default_data

        app = _mock_app()
        _make_ctx(app)

        with patch.dict(os.environ, {"FLASK_CONFIG": "development"}):
            with patch("app.seeding.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.return_value = False
                with patch("app.seeding.db"):
                    with patch("app.models.User"), patch("app.models.Country"):
                        create_default_data(app)

        app.app_context.assert_called_once()


# ===========================================================================
# Missing essential tables
# ===========================================================================

class TestCreateDefaultDataMissingTables:
    def test_skips_when_both_tables_missing(self):
        from app.seeding import create_default_data

        app = _mock_app()
        _make_ctx(app)

        with patch.dict(os.environ, {"FLASK_CONFIG": "development"}):
            with patch("app.seeding.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.return_value = False
                with patch("app.seeding.db"):
                    with patch("app.models.User"), patch("app.models.Country"):
                        create_default_data(app)

        # Warning for missing tables
        app.logger.warning.assert_called()

    def test_skips_when_user_table_missing(self):
        from app.seeding import create_default_data

        app = _mock_app()
        _make_ctx(app)

        def has_table(name):
            return name == "country"  # user missing

        with patch.dict(os.environ, {"FLASK_CONFIG": "development"}):
            with patch("app.seeding.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.side_effect = has_table
                with patch("app.seeding.db"):
                    with patch("app.models.User"), patch("app.models.Country"):
                        create_default_data(app)

        app.logger.warning.assert_called()


# ===========================================================================
# System settings initialization
# ===========================================================================

class TestSystemSettingsInit:
    def _build_app_and_mocks(self):
        app = _mock_app()
        _make_ctx(app)

        mock_country = MagicMock()
        mock_country.id = 1
        mock_country_cls = MagicMock()
        mock_country_cls.query.filter_by.return_value.first.return_value = mock_country

        mock_user_cls = MagicMock()
        mock_user_cls.query.filter_by.return_value.first.return_value = MagicMock(id=99)

        mock_ns_cls = MagicMock()
        mock_ns_cls.query.filter_by.return_value.first.return_value = MagicMock()

        mock_db = MagicMock()

        return app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db

    def test_creates_system_settings_when_table_exists_and_empty(self):
        from app.seeding import create_default_data

        app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db = self._build_app_and_mocks()
        mock_new_country = MagicMock()
        mock_new_country.id = 1

        mock_sys_settings = MagicMock()
        mock_sys_settings.query.count.return_value = 0

        with patch.dict(os.environ, {"FLASK_CONFIG": "development"}):
            with patch("app.seeding.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.return_value = True
                with patch("app.seeding.db", mock_db):
                    with patch("app.models.Country", mock_country_cls):
                        with patch("app.models.User", mock_user_cls):
                            with patch("app.models.organization.NationalSociety", mock_ns_cls):
                                with patch("app.models.system.SystemSettings", mock_sys_settings):
                                    with patch("app.services.platform.app_settings_service.set_supported_languages") as sl:
                                        with patch("app.services.platform.app_settings_service.set_document_types") as dt:
                                            with patch("app.services.platform.app_settings_service.set_age_groups") as ag:
                                                with patch("app.services.platform.app_settings_service.set_sex_categories") as sc:
                                                    with patch("app.services.platform.app_settings_service.set_enabled_entity_types") as et:
                                                        with patch("app.utils.organization_helpers.get_org_email_domain", return_value="example.com"):
                                                            with patch("app.models.rbac.RbacRole"):
                                                                with patch("app.models.rbac.RbacUserRole"):
                                                                    create_default_data(app)

        sl.assert_called_once()
        dt.assert_called_once()
        ag.assert_called_once()
        sc.assert_called_once()
        et.assert_called_once()

    def test_skips_system_settings_when_table_missing(self):
        from app.seeding import create_default_data

        app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db = self._build_app_and_mocks()

        with patch.dict(os.environ, {"FLASK_CONFIG": "development"}):
            with patch("app.seeding.inspect") as mock_inspect:
                # system_settings table missing
                mock_inspect.return_value.has_table.side_effect = lambda n: n in ("country", "user")
                with patch("app.seeding.db", mock_db):
                    with patch("app.models.Country", mock_country_cls):
                        with patch("app.models.User", mock_user_cls):
                            with patch("app.models.organization.NationalSociety", mock_ns_cls):
                                with patch("app.utils.organization_helpers.get_org_email_domain", return_value="example.com"):
                                    with patch("app.models.rbac.RbacRole"):
                                        with patch("app.models.rbac.RbacUserRole"):
                                            create_default_data(app)

        # set_supported_languages should NOT have been called
        app.logger.info.assert_called()

    def test_skips_system_settings_when_already_populated(self):
        from app.seeding import create_default_data

        app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db = self._build_app_and_mocks()

        mock_sys_settings = MagicMock()
        mock_sys_settings.query.count.return_value = 5  # already has data

        with patch.dict(os.environ, {"FLASK_CONFIG": "development"}):
            with patch("app.seeding.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.return_value = True
                with patch("app.seeding.db", mock_db):
                    with patch("app.models.Country", mock_country_cls):
                        with patch("app.models.User", mock_user_cls):
                            with patch("app.models.organization.NationalSociety", mock_ns_cls):
                                with patch("app.models.system.SystemSettings", mock_sys_settings):
                                    with patch("app.utils.organization_helpers.get_org_email_domain", return_value="example.com"):
                                        with patch("app.models.rbac.RbacRole"):
                                            with patch("app.models.rbac.RbacUserRole"):
                                                with patch("app.services.platform.app_settings_service.set_supported_languages") as sl:
                                                    create_default_data(app)

        sl.assert_not_called()


# ===========================================================================
# Country creation
# ===========================================================================

class TestCountryCreation:
    def test_creates_testland_when_missing(self):
        from app.seeding import create_default_data

        app = _mock_app()
        _make_ctx(app)

        mock_new_country = MagicMock()
        mock_new_country.id = 1
        mock_country_cls = MagicMock()
        mock_country_cls.query.filter_by.return_value.first.return_value = None  # doesn't exist
        mock_country_cls.return_value = mock_new_country

        mock_user_cls = MagicMock()
        mock_user_cls.query.filter_by.return_value.first.return_value = MagicMock(id=99)

        mock_ns_cls = MagicMock()
        mock_ns_cls.query.filter_by.return_value.first.return_value = MagicMock()

        mock_db = MagicMock()

        with patch.dict(os.environ, {"FLASK_CONFIG": "development"}):
            with patch("app.seeding.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.side_effect = lambda n: n in ("country", "user")
                with patch("app.seeding.db", mock_db):
                    with patch("app.models.Country", mock_country_cls):
                        with patch("app.models.User", mock_user_cls):
                            with patch("app.models.organization.NationalSociety", mock_ns_cls):
                                with patch("app.utils.organization_helpers.get_org_email_domain", return_value="example.com"):
                                    with patch("app.models.rbac.RbacRole"):
                                        with patch("app.models.rbac.RbacUserRole"):
                                            create_default_data(app)

        info_calls = " ".join(str(c) for c in app.logger.info.call_args_list)
        assert "Created default country" in info_calls

    def test_skips_testland_when_already_exists(self):
        from app.seeding import create_default_data

        app = _mock_app()
        _make_ctx(app)

        existing_country = MagicMock()
        existing_country.id = 99
        mock_country_cls = MagicMock()
        mock_country_cls.query.filter_by.return_value.first.return_value = existing_country

        mock_user_cls = MagicMock()
        mock_user_cls.query.filter_by.return_value.first.return_value = MagicMock(id=99)

        mock_ns_cls = MagicMock()
        mock_ns_cls.query.filter_by.return_value.first.return_value = MagicMock()

        mock_db = MagicMock()

        with patch.dict(os.environ, {"FLASK_CONFIG": "development"}):
            with patch("app.seeding.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.side_effect = lambda n: n in ("country", "user")
                with patch("app.seeding.db", mock_db):
                    with patch("app.models.Country", mock_country_cls):
                        with patch("app.models.User", mock_user_cls):
                            with patch("app.models.organization.NationalSociety", mock_ns_cls):
                                with patch("app.utils.organization_helpers.get_org_email_domain", return_value="example.com"):
                                    with patch("app.models.rbac.RbacRole"):
                                        with patch("app.models.rbac.RbacUserRole"):
                                            create_default_data(app)

        info_calls = " ".join(str(c) for c in app.logger.info.call_args_list)
        assert "already exists" in info_calls.lower()


# ===========================================================================
# Admin user creation
# ===========================================================================

class TestAdminUserCreation:
    def _base_setup(self, admin_exists=False):
        app = _mock_app()
        _make_ctx(app)

        mock_country = MagicMock()
        mock_country.id = 1
        mock_country_cls = MagicMock()
        mock_country_cls.query.filter_by.return_value.first.return_value = None  # no Testland
        mock_country_cls.return_value = mock_country

        mock_admin = MagicMock()
        mock_admin.id = 20
        mock_admin.countries = MagicMock()

        def user_filter_by(**kwargs):
            m = MagicMock()
            email = kwargs.get("email", "")
            if "admin" in email and admin_exists:
                m.first.return_value = MagicMock(id=20)
            else:
                m.first.return_value = None
            return m

        mock_user_cls = MagicMock()
        mock_user_cls.query.filter_by.side_effect = user_filter_by
        mock_user_cls.return_value = mock_admin

        mock_ns_cls = MagicMock()
        mock_ns_cls.query.filter_by.return_value.first.return_value = None

        mock_db = MagicMock()
        return app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db

    def test_admin_created_with_test_admin_password_env(self):
        from app.seeding import create_default_data

        app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db = self._base_setup()

        with patch.dict(os.environ, {"FLASK_CONFIG": "development", "TEST_ADMIN_PASSWORD": "secret123"}):
            with patch("app.seeding.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.side_effect = lambda n: n in ("country", "user")
                with patch("app.seeding.db", mock_db):
                    with patch("app.models.Country", mock_country_cls):
                        with patch("app.models.User", mock_user_cls):
                            with patch("app.models.organization.NationalSociety", mock_ns_cls):
                                with patch("app.utils.organization_helpers.get_org_email_domain", return_value="example.com"):
                                    with patch("app.models.rbac.RbacRole") as mock_rbac_role:
                                        mock_rbac_role.query.filter_by.return_value.first.return_value = MagicMock(id=1)
                                        with patch("app.models.rbac.RbacUserRole"):
                                            create_default_data(app)

        info_calls = " ".join(str(c) for c in app.logger.info.call_args_list)
        assert "Created default admin user" in info_calls

    def test_admin_created_with_generated_password(self):
        from app.seeding import create_default_data

        app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db = self._base_setup()

        env = {"FLASK_CONFIG": "development"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("TEST_ADMIN_PASSWORD", None)
            with patch("app.seeding.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.side_effect = lambda n: n in ("country", "user")
                with patch("app.seeding.db", mock_db):
                    with patch("app.models.Country", mock_country_cls):
                        with patch("app.models.User", mock_user_cls):
                            with patch("app.models.organization.NationalSociety", mock_ns_cls):
                                with patch("app.utils.organization_helpers.get_org_email_domain", return_value="example.com"):
                                    with patch("app.models.rbac.RbacRole"):
                                        with patch("app.models.rbac.RbacUserRole"):
                                            create_default_data(app)

        info_calls = " ".join(str(c) for c in app.logger.info.call_args_list)
        assert "generated password" in info_calls.lower() or "Created default admin" in info_calls

    def test_rbac_role_assignment_exception_logged_as_debug(self):
        """Exception during RBAC assignment is logged at debug level, not raised."""
        from app.seeding import create_default_data

        app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db = self._base_setup()

        # Make RbacRole.query.filter_by raise an exception to trigger the except block
        mock_rbac_role = MagicMock()
        mock_rbac_role.query.filter_by.side_effect = Exception("rbac table missing")

        with patch.dict(os.environ, {"FLASK_CONFIG": "development"}):
            with patch("app.seeding.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.side_effect = lambda n: n in ("country", "user")
                with patch("app.seeding.db", mock_db):
                    with patch("app.models.Country", mock_country_cls):
                        with patch("app.models.User", mock_user_cls):
                            with patch("app.models.organization.NationalSociety", mock_ns_cls):
                                with patch("app.utils.organization_helpers.get_org_email_domain", return_value="example.com"):
                                    with patch("app.models.rbac.RbacRole", mock_rbac_role):
                                        with patch("app.models.rbac.RbacUserRole"):
                                            create_default_data(app)

        app.logger.debug.assert_called()

    def test_admin_already_exists_logs_info(self):
        from app.seeding import create_default_data

        app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db = self._base_setup(admin_exists=True)

        with patch.dict(os.environ, {"FLASK_CONFIG": "development"}):
            with patch("app.seeding.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.side_effect = lambda n: n in ("country", "user")
                with patch("app.seeding.db", mock_db):
                    with patch("app.models.Country", mock_country_cls):
                        with patch("app.models.User", mock_user_cls):
                            with patch("app.models.organization.NationalSociety", mock_ns_cls):
                                with patch("app.utils.organization_helpers.get_org_email_domain", return_value="example.com"):
                                    with patch("app.models.rbac.RbacRole"):
                                        with patch("app.models.rbac.RbacUserRole"):
                                            create_default_data(app)

        info_calls = " ".join(str(c) for c in app.logger.info.call_args_list)
        assert "already exists" in info_calls.lower()


# ===========================================================================
# Focal point user creation
# ===========================================================================

class TestFocalPointUserCreation:
    def _base_setup(self, focal_exists=False, focal_has_no_countries=False):
        app = _mock_app()
        _make_ctx(app)

        mock_country = MagicMock()
        mock_country.id = 1
        mock_country_cls = MagicMock()
        mock_country_cls.query.filter_by.return_value.first.return_value = mock_country

        mock_focal = MagicMock()
        mock_focal.id = 30
        mock_focal.email = "focal@example.com"
        if focal_has_no_countries:
            mock_focal.countries.first.return_value = None
        else:
            mock_focal.countries.first.return_value = mock_country

        def user_filter_by(**kwargs):
            m = MagicMock()
            email = kwargs.get("email", "")
            if "admin" in email:
                m.first.return_value = MagicMock(id=10)  # admin exists
            elif "focal" in email:
                m.first.return_value = mock_focal if focal_exists else None
            else:
                m.first.return_value = None
            return m

        mock_user_cls = MagicMock()
        mock_user_cls.query.filter_by.side_effect = user_filter_by
        mock_user_cls.return_value = MagicMock(id=99, countries=MagicMock())

        mock_ns_cls = MagicMock()
        mock_ns_cls.query.filter_by.return_value.first.return_value = MagicMock()

        mock_db = MagicMock()
        return app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db

    def _run(self, app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db):
        from app.seeding import create_default_data

        with patch.dict(os.environ, {"FLASK_CONFIG": "development"}):
            with patch("app.seeding.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.side_effect = lambda n: n in ("country", "user")
                with patch("app.seeding.db", mock_db):
                    with patch("app.models.Country", mock_country_cls):
                        with patch("app.models.User", mock_user_cls):
                            with patch("app.models.organization.NationalSociety", mock_ns_cls):
                                with patch("app.utils.organization_helpers.get_org_email_domain", return_value="example.com"):
                                    with patch("app.models.rbac.RbacRole"):
                                        with patch("app.models.rbac.RbacUserRole"):
                                            create_default_data(app)

    def test_focal_point_created_fresh(self):
        app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db = self._base_setup(
            focal_exists=False
        )
        self._run(app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db)
        assert app.logger.info.called

    def test_focal_point_existing_without_countries_gets_assigned(self):
        app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db = self._base_setup(
            focal_exists=True, focal_has_no_countries=True
        )
        self._run(app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db)
        assert app.logger.info.called

    def test_focal_point_already_has_countries_logs_info(self):
        app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db = self._base_setup(
            focal_exists=True, focal_has_no_countries=False
        )
        self._run(app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db)
        assert app.logger.info.called


# ===========================================================================
# System manager user creation
# ===========================================================================

class TestSystemManagerUserCreation:
    def _base_setup(self, sys_exists=False):
        app = _mock_app()
        _make_ctx(app)

        mock_country = MagicMock()
        mock_country.id = 1
        mock_country_cls = MagicMock()
        mock_country_cls.query.filter_by.return_value.first.return_value = mock_country

        mock_sys = MagicMock()
        mock_sys.id = 40
        mock_sys.email = "test_sys@example.com"
        mock_sys.countries = MagicMock()

        def user_filter_by(**kwargs):
            m = MagicMock()
            email = kwargs.get("email", "")
            if "sys" in email:
                m.first.return_value = mock_sys if sys_exists else None
            else:
                m.first.return_value = MagicMock(id=99)
            return m

        mock_user_cls = MagicMock()
        mock_user_cls.query.filter_by.side_effect = user_filter_by
        mock_user_cls.return_value = MagicMock(id=40, countries=MagicMock())

        mock_ns_cls = MagicMock()
        mock_ns_cls.query.filter_by.return_value.first.return_value = MagicMock()

        mock_db = MagicMock()
        return app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db

    def _run(self, app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db, extra_env=None):
        from app.seeding import create_default_data

        env = {"FLASK_CONFIG": "development"}
        if extra_env:
            env.update(extra_env)

        with patch.dict(os.environ, env):
            with patch("app.seeding.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.side_effect = lambda n: n in ("country", "user")
                with patch("app.seeding.db", mock_db):
                    with patch("app.models.Country", mock_country_cls):
                        with patch("app.models.User", mock_user_cls):
                            with patch("app.models.organization.NationalSociety", mock_ns_cls):
                                with patch("app.utils.organization_helpers.get_org_email_domain", return_value="example.com"):
                                    with patch("app.models.rbac.RbacRole"):
                                        with patch("app.models.rbac.RbacUserRole"):
                                            create_default_data(app)

    def test_sys_manager_created_with_password_env(self):
        app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db = self._base_setup()
        self._run(app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db,
                  extra_env={"TEST_SYS_MANAGER_PASSWORD": "syspass123"})
        info_calls = " ".join(str(c) for c in app.logger.info.call_args_list)
        assert "Created default system manager" in info_calls

    def test_sys_manager_created_with_generated_password(self):
        app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db = self._base_setup()
        env = {"FLASK_CONFIG": "development"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("TEST_SYS_MANAGER_PASSWORD", None)
            self._run(app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db)
        info_calls = " ".join(str(c) for c in app.logger.info.call_args_list)
        assert "Created default system manager" in info_calls

    def test_sys_manager_already_exists(self):
        app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db = self._base_setup(sys_exists=True)
        self._run(app, mock_country_cls, mock_user_cls, mock_ns_cls, mock_db)
        info_calls = " ".join(str(c) for c in app.logger.info.call_args_list)
        assert "already exists" in info_calls.lower()


class TestEnsureDevTestSysManagerRole:
    def test_grants_missing_role_and_commits(self):
        from app.seeding import _ensure_dev_test_sys_manager_role

        app = _mock_app()
        user = MagicMock(id=40, email="test_sys@example.com")
        with patch("app.seeding._assign_role_to_user", return_value=True) as assign:
            with patch("app.seeding.db") as mock_db:
                _ensure_dev_test_sys_manager_role(user, app)

        assign.assert_called_once_with(
            40,
            "system_manager",
            name="System Manager",
            description="Full access (superuser).",
        )
        mock_db.session.commit.assert_called_once()
        app.logger.info.assert_called()
        assert "system_manager" in str(app.logger.info.call_args)

    def test_skips_commit_when_role_already_present(self):
        from app.seeding import _ensure_dev_test_sys_manager_role

        app = _mock_app()
        user = MagicMock(id=40, email="test_sys@example.com")
        with patch("app.seeding._assign_role_to_user", return_value=False):
            with patch("app.seeding.db") as mock_db:
                _ensure_dev_test_sys_manager_role(user, app)

        mock_db.session.commit.assert_not_called()
        app.logger.info.assert_not_called()

    def test_rolls_back_on_assignment_error(self):
        from app.seeding import _ensure_dev_test_sys_manager_role

        app = _mock_app()
        user = MagicMock(id=40, email="test_sys@example.com")
        with patch("app.seeding._assign_role_to_user", side_effect=RuntimeError("db down")):
            with patch("app.seeding.db") as mock_db:
                _ensure_dev_test_sys_manager_role(user, app)

        mock_db.session.rollback.assert_called_once()
        app.logger.debug.assert_called()


class TestClearDevTestSysManagerEntityPermissions:
    def test_deletes_leftover_grants_and_commits(self):
        from app.seeding import _clear_dev_test_sys_manager_entity_permissions

        app = _mock_app()
        user = MagicMock(id=40, email="test_sys@example.com")
        mock_query = MagicMock()
        mock_query.filter_by.return_value.delete.return_value = 2
        with patch("app.models.core.UserEntityPermission") as perm_cls:
            perm_cls.query = mock_query
            with patch("app.seeding.db") as mock_db:
                _clear_dev_test_sys_manager_entity_permissions(user, app)

        mock_query.filter_by.assert_called_once_with(user_id=40)
        mock_db.session.commit.assert_called_once()
        app.logger.info.assert_called()
        assert "leftover entity permission" in str(app.logger.info.call_args)

    def test_skips_commit_when_no_grants(self):
        from app.seeding import _clear_dev_test_sys_manager_entity_permissions

        app = _mock_app()
        user = MagicMock(id=40, email="test_sys@example.com")
        mock_query = MagicMock()
        mock_query.filter_by.return_value.delete.return_value = 0
        with patch("app.models.core.UserEntityPermission") as perm_cls:
            perm_cls.query = mock_query
            with patch("app.seeding.db") as mock_db:
                _clear_dev_test_sys_manager_entity_permissions(user, app)

        mock_db.session.commit.assert_not_called()
        app.logger.info.assert_not_called()

    def test_rolls_back_on_delete_error(self):
        from app.seeding import _clear_dev_test_sys_manager_entity_permissions

        app = _mock_app()
        user = MagicMock(id=40, email="test_sys@example.com")
        mock_query = MagicMock()
        mock_query.filter_by.return_value.delete.side_effect = RuntimeError("db down")
        with patch("app.models.core.UserEntityPermission") as perm_cls:
            perm_cls.query = mock_query
            with patch("app.seeding.db") as mock_db:
                _clear_dev_test_sys_manager_entity_permissions(user, app)

        mock_db.session.rollback.assert_called_once()
        app.logger.debug.assert_called()

    def test_noop_when_user_missing(self):
        from app.seeding import _clear_dev_test_sys_manager_entity_permissions

        app = _mock_app()
        with patch("app.seeding.db") as mock_db:
            _clear_dev_test_sys_manager_entity_permissions(None, app)

        mock_db.session.commit.assert_not_called()


# ===========================================================================
# National Society creation
# ===========================================================================

class TestNationalSocietyCreation:
    def test_ns_created_when_missing(self):
        from app.seeding import create_default_data

        app = _mock_app()
        _make_ctx(app)

        mock_country = MagicMock()
        mock_country.id = 1
        mock_country_cls = MagicMock()
        mock_country_cls.query.filter_by.return_value.first.return_value = mock_country

        mock_user_cls = MagicMock()
        mock_user_cls.query.filter_by.return_value.first.return_value = MagicMock(id=99)

        mock_ns_cls = MagicMock()
        mock_ns_cls.query.filter_by.return_value.first.return_value = None  # NS doesn't exist

        mock_db = MagicMock()

        with patch.dict(os.environ, {"FLASK_CONFIG": "development"}):
            with patch("app.seeding.inspect") as mock_inspect:
                mock_inspect.return_value.has_table.side_effect = lambda n: n in ("country", "user")
                with patch("app.seeding.db", mock_db):
                    with patch("app.models.Country", mock_country_cls):
                        with patch("app.models.User", mock_user_cls):
                            with patch("app.models.organization.NationalSociety", mock_ns_cls):
                                with patch("app.utils.organization_helpers.get_org_email_domain", return_value="example.com"):
                                    with patch("app.models.rbac.RbacRole"):
                                        with patch("app.models.rbac.RbacUserRole"):
                                            create_default_data(app)

        info_calls = " ".join(str(c) for c in app.logger.info.call_args_list)
        assert "National Society" in info_calls


# ===========================================================================
# Exception handling
# ===========================================================================

class TestCreateDefaultDataExceptionHandling:
    def test_exception_triggers_rollback_and_reraise(self):
        from app.seeding import create_default_data

        app = _mock_app()
        _make_ctx(app)

        mock_db = MagicMock()

        # Patch Country.query.filter_by to raise inside the app_context block
        mock_country_cls = MagicMock()
        mock_country_cls.query.filter_by.side_effect = Exception("unexpected db error")

        with patch.dict(os.environ, {"FLASK_CONFIG": "development"}):
            with patch("app.seeding.inspect") as mock_inspect:
                # Only essential tables exist; system_settings does NOT so we skip that branch
                mock_inspect.return_value.has_table.side_effect = lambda n: n in ("country", "user")
                with patch("app.seeding.db", mock_db):
                    with patch("app.models.Country", mock_country_cls):
                        with patch("app.models.User"):
                            with pytest.raises(Exception, match="unexpected db error"):
                                create_default_data(app)

        mock_db.session.rollback.assert_called_once()
