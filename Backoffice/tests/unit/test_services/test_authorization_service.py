"""
Unit tests for authorization service.

These tests are critical for security and should have high coverage.
"""
import pytest
from app.services.authorization_service import AuthorizationService
from tests.factories import create_test_user, create_test_admin


@pytest.mark.unit
class TestAuthorizationService:
    """Test authorization service methods."""

    def test_is_admin_with_admin_user(self, db_session, app):
        """Test is_admin returns True for admin users."""
        with app.app_context():
            admin = create_test_admin(db_session)
            assert AuthorizationService.is_admin(admin) is True

    def test_is_admin_with_system_manager(self, db_session, app):
        """Test is_admin returns True for system managers."""
        with app.app_context():
            manager = create_test_user(db_session, role='system_manager')
            assert AuthorizationService.is_admin(manager) is True

    def test_is_admin_with_regular_user(self, db_session, app):
        """Test is_admin returns False for regular users."""
        with app.app_context():
            user = create_test_user(db_session, role='user')
            assert AuthorizationService.is_admin(user) is False

    def test_is_admin_with_none(self):
        """Test is_admin returns False for None."""
        assert AuthorizationService.is_admin(None) is False

    def test_has_rbac_permission_system_manager(self, db_session, app):
        """Test that system managers have all permissions (RBAC superuser)."""
        with app.app_context():
            manager = create_test_user(db_session, role='system_manager')
            assert AuthorizationService.has_rbac_permission(manager, 'admin.users.view') is True
            assert AuthorizationService.has_rbac_permission(manager, 'admin.api.manage') is True
            assert AuthorizationService.has_rbac_permission(manager, 'anything.at.all') is True

    def test_has_rbac_permission_admin_with_permission(self, db_session, app):
        """Test admin with specific RBAC permission."""
        with app.app_context():
            admin = create_test_admin(db_session, can_manage_users=True)
            assert AuthorizationService.has_rbac_permission(admin, 'admin.users.view') is True

    def test_has_rbac_permission_admin_without_permission(self, db_session, app):
        """Test admin without a specific RBAC permission."""
        with app.app_context():
            admin = create_test_admin(db_session, can_manage_users=False)
            assert AuthorizationService.is_admin(admin) is True  # still an admin via other permissions
            assert AuthorizationService.has_rbac_permission(admin, 'admin.users.view') is False

    def test_focal_point_is_not_admin(self, db_session, app):
        """Test focal point is not treated as admin."""
        with app.app_context():
            focal = create_test_user(db_session, role='focal_point')
            assert AuthorizationService.is_admin(focal) is False
            assert AuthorizationService.has_role(focal, "assignment_editor_submitter") is True

    def test_focal_point_does_not_have_admin_users_permission(self, db_session, app):
        """Test focal point does not have admin.users.* permissions."""
        with app.app_context():
            focal = create_test_user(db_session, role='focal_point')
            assert AuthorizationService.has_rbac_permission(focal, 'admin.users.view') is False

    def test_has_rbac_permission_unauthenticated(self):
        """Test has_rbac_permission returns False for unauthenticated user."""
        from unittest.mock import MagicMock
        user = MagicMock()
        user.is_authenticated = False
        assert AuthorizationService.has_rbac_permission(user, 'admin.users.view') is False

    def test_has_country_access_admin(self, db_session, app):
        """Test admin has access to all countries."""
        with app.app_context():
            admin = create_test_admin(db_session)
            assert AuthorizationService.has_country_access(admin, 1) is True
            assert AuthorizationService.has_country_access(admin, 999) is True

    def test_has_country_access_system_manager(self, db_session, app):
        """Test system manager has access to all countries."""
        with app.app_context():
            manager = create_test_user(db_session, role='system_manager')
            assert AuthorizationService.has_country_access(manager, 1) is True

    def test_has_country_access_focal_point_assigned(self, db_session, app):
        """Test focal point has access to assigned countries."""
        with app.app_context():
            from tests.factories import create_test_country
            from app.models import UserEntityPermission
            focal = create_test_user(db_session, role='focal_point')
            country = create_test_country(db_session)
            # Use add_entity_permission to properly set up the relationship
            focal.add_entity_permission('country', country.id)
            db_session.commit()

            assert AuthorizationService.has_country_access(focal, country.id) is True

    def test_has_country_access_focal_point_not_assigned(self, db_session, app):
        """Test focal point does not have access to unassigned countries."""
        with app.app_context():
            from tests.factories import create_test_country
            focal = create_test_user(db_session, role='focal_point')
            country = create_test_country(db_session)

            assert AuthorizationService.has_country_access(focal, country.id) is False

    def test_has_country_access_unauthenticated(self):
        """Test has_country_access returns False for unauthenticated user."""
        from unittest.mock import MagicMock
        user = MagicMock()
        user.is_authenticated = False
        assert AuthorizationService.has_country_access(user, 1) is False
