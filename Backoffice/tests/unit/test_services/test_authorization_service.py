"""
Unit tests for authorization service.

These tests are critical for security and should have high coverage.
"""
import pytest
from app.services.authorization_service import AuthorizationService
from tests.factories import create_test_user, create_test_admin

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]


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


@pytest.mark.unit
class TestAuthorizationServiceExtended:
    """Additional authorization service coverage."""

    def test_has_role(self, db_session, app):
        with app.app_context():
            focal = create_test_user(db_session, role='focal_point')
            assert AuthorizationService.has_role(focal, 'assignment_editor_submitter') is True
            assert AuthorizationService.has_role(focal, 'system_manager') is False

    def test_is_system_manager(self, db_session, app):
        with app.app_context():
            sm = create_test_user(db_session, role='system_manager')
            assert AuthorizationService.is_system_manager(sm) is True

    def test_access_level(self, db_session, app):
        from unittest.mock import MagicMock
        with app.app_context():
            anon = MagicMock()
            anon.is_authenticated = False
            assert AuthorizationService.access_level(anon) == 'public'
            assert AuthorizationService.access_level(create_test_admin(db_session)) == 'admin'
            assert AuthorizationService.access_level(create_test_user(db_session, role='system_manager')) == 'system_manager'
            assert AuthorizationService.access_level(create_test_user(db_session, role='focal_point')) == 'focal_point'

    def test_get_role_codes(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            codes = AuthorizationService.get_role_codes(admin)
            assert 'admin_core' in codes

    def test_validate_country_list_access_focal_point(self, db_session, app):
        from tests.factories import create_test_country
        with app.app_context():
            focal = create_test_user(db_session, role='focal_point')
            c1 = create_test_country(db_session)
            c2 = create_test_country(db_session)
            focal.add_entity_permission('country', c1.id)
            db_session.commit()
            allowed = AuthorizationService.validate_country_list_access(focal, [c1.id, c2.id])
            assert allowed == [c1.id]

    def test_can_access_assignment_focal_point(self, db_session, app):
        from tests.factories import create_focal_point_with_country
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            assert AuthorizationService.can_access_assignment(aes, user) is True

    def test_can_access_assignment_unassigned_country(self, db_session, app):
        from tests.factories import create_test_assignment_entity_status, create_test_user
        with app.app_context():
            focal = create_test_user(db_session, role='focal_point')
            aes = create_test_assignment_entity_status(db_session)
            assert AuthorizationService.can_access_assignment(aes, focal) is False

    def test_can_approve_assignment_admin(self, db_session, app):
        from tests.factories import create_test_assignment_entity_status
        with app.app_context():
            admin = create_test_user(db_session, role='system_manager')
            aes = create_test_assignment_entity_status(db_session)
            assert AuthorizationService.can_approve_assignment(aes, admin) is True

    def test_can_approve_assignment_focal_point_denied(self, db_session, app):
        from tests.factories import create_focal_point_with_country
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            assert AuthorizationService.can_approve_assignment(aes, user) is False

    def test_can_manage_closed_assignment(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            focal = create_test_user(db_session, role='focal_point')
            assert AuthorizationService.can_manage_closed_assignment(admin) is True
            assert AuthorizationService.can_manage_closed_assignment(focal) is False

    def test_check_self_report_access_wrong_period(self, db_session, app):
        from tests.factories import create_focal_point_with_country
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            assert AuthorizationService.check_self_report_access(aes, user) is False

    def test_check_self_report_access_self_report_period(self, db_session, app):
        from tests.factories import create_focal_point_with_country, create_test_assignment_entity_status, _grant_role_permission
        from app.utils.constants import SELF_REPORT_PERIOD_NAME
        with app.app_context():
            user, country, _ = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, 'assignment_editor_submitter', 'assignment.enter')
            aes = create_test_assignment_entity_status(
                db_session, country=country, period_name=SELF_REPORT_PERIOD_NAME,
            )
            assert AuthorizationService.check_self_report_access(aes, user) is True

    def test_check_template_access_owner(self, db_session, app):
        from tests.factories import create_test_template
        with app.app_context():
            user = create_test_user(db_session)
            template = create_test_template(db_session, owner_id=user.id)
            assert AuthorizationService.check_template_access(template.id, user.id) is True

    def test_check_template_access_denied(self, db_session, app):
        from tests.factories import create_test_template
        with app.app_context():
            owner = create_test_user(db_session)
            other = create_test_user(db_session)
            template = create_test_template(db_session, owner_id=owner.id)
            assert AuthorizationService.check_template_access(template.id, other.id) is False

    def test_rbac_enabled_and_active_for_user(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            assert AuthorizationService.rbac_enabled() in (True, False)
            assert AuthorizationService.rbac_active_for_user(user) is True

    def test_can_reopen_assignment_when_submitted(self, db_session, app):
        from tests.factories import create_test_assignment_entity_status
        with app.app_context():
            admin = create_test_user(db_session, role='system_manager')
            aes = create_test_assignment_entity_status(db_session, status='submitted')
            assert AuthorizationService.can_reopen_assignment(aes, admin) is True
