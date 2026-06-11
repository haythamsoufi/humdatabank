"""
Tests for app/services/notification/audience.py

Targets 100% coverage of all audience helper functions.
"""
from unittest.mock import patch, MagicMock
import pytest

from app.services.notification.audience import (
    get_admin_capable_user_ids,
    get_system_manager_user_ids,
    get_entity_scoped_non_system_manager_admin_user_ids,
    collect_entity_admin_audience_recipient_ids,
    get_assignment_editor_submitter_user_ids_for_entity,
)
from app.models.enums import NotificationType


# ---------------------------------------------------------------------------
# get_admin_capable_user_ids
# ---------------------------------------------------------------------------

class TestGetAdminCapableUserIds:
    def test_returns_list_with_no_users(self, app, db_session):
        with app.app_context():
            result = get_admin_capable_user_ids()
        assert isinstance(result, list)

    def test_excludes_specified_user_ids(self, app, db_session):
        from app.models import User
        from app.models.rbac import RbacRole, RbacUserRole
        from app import db

        with app.app_context():
            user = User(email='admin_capable@test.com', name='Capable', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            role = RbacRole.query.filter_by(code='admin_core').first()
            if not role:
                role = RbacRole(code='admin_core', name='Admin Core')
                db.session.add(role)
                db.session.flush()

            user_role = RbacUserRole(user_id=user.id, role_id=role.id)
            db.session.add(user_role)
            db.session.commit()

            all_ids = get_admin_capable_user_ids()
            excluded_ids = get_admin_capable_user_ids(exclude_user_ids=[user.id])

        assert user.id in all_ids
        assert user.id not in excluded_ids

    def test_exclude_none_values_in_exclude_list(self, app, db_session):
        with app.app_context():
            result = get_admin_capable_user_ids(exclude_user_ids=[None, None])
        assert isinstance(result, list)

    def test_empty_exclude_list(self, app, db_session):
        with app.app_context():
            result = get_admin_capable_user_ids(exclude_user_ids=[])
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# get_system_manager_user_ids
# ---------------------------------------------------------------------------

class TestGetSystemManagerUserIds:
    def test_returns_list(self, app, db_session):
        with app.app_context():
            result = get_system_manager_user_ids()
        assert isinstance(result, list)

    def test_only_active_users(self, app, db_session):
        from app.models import User
        from app.models.rbac import RbacRole, RbacUserRole
        from app import db

        with app.app_context():
            inactive_user = User(email='sm_inactive@test.com', name='Inactive SM', active=False)
            inactive_user.set_password('pw')
            db.session.add(inactive_user)
            db.session.flush()

            role = RbacRole.query.filter_by(code='system_manager').first()
            if not role:
                role = RbacRole(code='system_manager', name='System Manager')
                db.session.add(role)
                db.session.flush()

            ur = RbacUserRole(user_id=inactive_user.id, role_id=role.id)
            db.session.add(ur)
            db.session.commit()

            result = get_system_manager_user_ids()

        assert inactive_user.id not in result

    def test_exclude_user_ids(self, app, db_session):
        from app.models import User
        from app.models.rbac import RbacRole, RbacUserRole
        from app import db

        with app.app_context():
            active_sm = User(email='sm_active@test.com', name='Active SM', active=True)
            active_sm.set_password('pw')
            db.session.add(active_sm)
            db.session.flush()

            role = RbacRole.query.filter_by(code='system_manager').first()
            if not role:
                role = RbacRole(code='system_manager', name='System Manager')
                db.session.add(role)
                db.session.flush()

            ur = RbacUserRole(user_id=active_sm.id, role_id=role.id)
            db.session.add(ur)
            db.session.commit()

            all_ids = get_system_manager_user_ids()
            excluded = get_system_manager_user_ids(exclude_user_ids=[active_sm.id])

        assert active_sm.id in all_ids
        assert active_sm.id not in excluded


# ---------------------------------------------------------------------------
# get_entity_scoped_non_system_manager_admin_user_ids
# ---------------------------------------------------------------------------

class TestGetEntityScopedNonSystemManagerAdminUserIds:
    def test_returns_empty_when_entity_type_is_none(self, app, db_session):
        with app.app_context():
            result = get_entity_scoped_non_system_manager_admin_user_ids(None, 1)
        assert result == []

    def test_returns_empty_when_entity_id_is_none(self, app, db_session):
        with app.app_context():
            result = get_entity_scoped_non_system_manager_admin_user_ids('country', None)
        assert result == []

    def test_returns_empty_when_entity_type_is_blank(self, app, db_session):
        with app.app_context():
            result = get_entity_scoped_non_system_manager_admin_user_ids('   ', 1)
        assert result == []

    def test_invalid_entity_id_type(self, app, db_session):
        with app.app_context():
            result = get_entity_scoped_non_system_manager_admin_user_ids('country', 'not_int')
        assert result == []

    def test_returns_list_for_valid_entity(self, app, db_session):
        with app.app_context():
            result = get_entity_scoped_non_system_manager_admin_user_ids('country', 999)
        assert isinstance(result, list)

    def test_excludes_specified_user_ids(self, app, db_session):
        from app.models import User
        from app.models.rbac import RbacRole, RbacUserRole
        from app.models.core import UserEntityPermission
        from app import db

        with app.app_context():
            user = User(email='admin_entity@test.com', name='Admin Entity', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            role = RbacRole.query.filter_by(code='admin_core').first()
            if not role:
                role = RbacRole(code='admin_core', name='Admin Core')
                db.session.add(role)
                db.session.flush()

            ur = RbacUserRole(user_id=user.id, role_id=role.id)
            db.session.add(ur)

            perm = UserEntityPermission(user_id=user.id, entity_type='country', entity_id=42)
            db.session.add(perm)
            db.session.commit()

            all_ids = get_entity_scoped_non_system_manager_admin_user_ids('country', 42)
            excluded = get_entity_scoped_non_system_manager_admin_user_ids('country', 42, exclude_user_ids=[user.id])

        if user.id in all_ids:
            assert user.id not in excluded


# ---------------------------------------------------------------------------
# collect_entity_admin_audience_recipient_ids
# ---------------------------------------------------------------------------

class TestCollectEntityAdminAudienceRecipientIds:
    def test_returns_empty_when_entity_type_is_none(self, app, db_session):
        with app.app_context():
            result = collect_entity_admin_audience_recipient_ids(
                NotificationType.admin_message, None, 1
            )
        assert result == []

    def test_returns_empty_when_entity_id_is_none(self, app, db_session):
        with app.app_context():
            result = collect_entity_admin_audience_recipient_ids(
                NotificationType.admin_message, 'country', None
            )
        assert result == []

    def test_returns_list_when_both_buckets_disabled(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.audience.audience_bucket_enabled', return_value=False):
                result = collect_entity_admin_audience_recipient_ids(
                    NotificationType.admin_message, 'country', 1
                )
        assert result == []

    def test_calls_admin_users_bucket_when_enabled(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.audience.audience_bucket_enabled') as mock_abe:
                mock_abe.side_effect = lambda nt, bucket: bucket == 'admin_users'
                with patch('app.services.notification.audience.get_entity_scoped_non_system_manager_admin_user_ids', return_value=[10, 20]) as mock_admin:
                    with patch('app.services.notification.audience.get_system_manager_user_ids', return_value=[]) as mock_sm:
                        result = collect_entity_admin_audience_recipient_ids(
                            NotificationType.admin_message, 'country', 1
                        )
        assert 10 in result
        assert 20 in result

    def test_calls_system_managers_bucket_when_enabled(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.audience.audience_bucket_enabled') as mock_abe:
                mock_abe.side_effect = lambda nt, bucket: bucket == 'system_managers'
                with patch('app.services.notification.audience.get_system_manager_user_ids', return_value=[30]) as mock_sm:
                    with patch('app.services.notification.audience.get_entity_scoped_non_system_manager_admin_user_ids', return_value=[]):
                        result = collect_entity_admin_audience_recipient_ids(
                            NotificationType.admin_message, 'country', 1
                        )
        assert 30 in result

    def test_deduplicates_and_excludes(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.audience.audience_bucket_enabled', return_value=True):
                with patch('app.services.notification.audience.get_entity_scoped_non_system_manager_admin_user_ids', return_value=[1, 2, 3]):
                    with patch('app.services.notification.audience.get_system_manager_user_ids', return_value=[2, 3, 4]):
                        result = collect_entity_admin_audience_recipient_ids(
                            NotificationType.admin_message, 'country', 1,
                            exclude_user_ids=[1, 4]
                        )
        assert 1 not in result
        assert 4 not in result
        assert 2 in result
        assert 3 in result


# ---------------------------------------------------------------------------
# get_assignment_editor_submitter_user_ids_for_entity
# ---------------------------------------------------------------------------

class TestGetAssignmentEditorSubmitterUserIdsForEntity:
    def test_returns_list(self, app, db_session):
        with app.app_context():
            result = get_assignment_editor_submitter_user_ids_for_entity('country', 999)
        assert isinstance(result, list)

    def test_returns_correct_user_ids(self, app, db_session):
        from app.models import User
        from app.models.rbac import RbacRole, RbacUserRole
        from app.models.core import UserEntityPermission
        from app import db

        with app.app_context():
            user = User(email='aes_user@test.com', name='AES User', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            role = RbacRole.query.filter_by(code='assignment_editor_submitter').first()
            if not role:
                role = RbacRole(code='assignment_editor_submitter', name='Assignment Editor Submitter')
                db.session.add(role)
                db.session.flush()

            ur = RbacUserRole(user_id=user.id, role_id=role.id)
            db.session.add(ur)

            perm = UserEntityPermission(user_id=user.id, entity_type='country', entity_id=77)
            db.session.add(perm)
            db.session.commit()

            result = get_assignment_editor_submitter_user_ids_for_entity('country', 77)

        assert user.id in result

    def test_excludes_specified_user_ids(self, app, db_session):
        from app.models import User
        from app.models.rbac import RbacRole, RbacUserRole
        from app.models.core import UserEntityPermission
        from app import db

        with app.app_context():
            user = User(email='aes_excl@test.com', name='AES Excl', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            role = RbacRole.query.filter_by(code='assignment_editor_submitter').first()
            if not role:
                role = RbacRole(code='assignment_editor_submitter', name='AES')
                db.session.add(role)
                db.session.flush()

            ur = RbacUserRole(user_id=user.id, role_id=role.id)
            db.session.add(ur)

            perm = UserEntityPermission(user_id=user.id, entity_type='country', entity_id=88)
            db.session.add(perm)
            db.session.commit()

            result = get_assignment_editor_submitter_user_ids_for_entity(
                'country', 88, exclude_user_ids=[user.id]
            )

        assert user.id not in result
