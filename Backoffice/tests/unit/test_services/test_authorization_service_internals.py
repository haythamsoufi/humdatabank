"""Unit tests for AuthorizationService caches, private helpers, and decorators."""
from unittest.mock import MagicMock, patch

import pytest
from flask import g
from flask_login import login_user

from app.models import TemplateShare
from app.models.enums import AssignmentEntityStatusValue
from app.services.authorization_service import (
    AuthorizationService,
    _rbac_cache_get,
    _rbac_cache_set,
    _request_g,
)
from tests.factories import (
    create_focal_point_with_country,
    create_test_assignment_entity_status,
    create_test_template,
    create_test_user,
    create_test_admin,
)

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]


@pytest.mark.unit
class TestRbacCacheHelpers:
    def test_request_g_inside_request(self, app):
        with app.test_request_context():
            assert _request_g() is g

    def test_rbac_cache_roundtrip(self, app):
        with app.test_request_context():
            _rbac_cache_set(g, '_test_cache', 'key1', True)
            assert _rbac_cache_get(g, '_test_cache', 'key1') is True
            assert _rbac_cache_get(g, '_test_cache', 'missing') is None

    def test_rbac_cache_get_with_none_g(self):
        assert _rbac_cache_get(None, '_test_cache', 'key') is None

    def test_rbac_cache_get_handles_bad_cache_object(self, app):
        with app.test_request_context():
            g._bad_cache = 'not-a-dict'
            assert _rbac_cache_get(g, '_bad_cache', 'key') is None

    def test_rbac_cache_set_no_op_without_g(self):
        _rbac_cache_set(None, '_test_cache', 'key', True)


@pytest.mark.unit
class TestHasRoleEdgeCases:
    def test_empty_role_code_returns_false(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            assert AuthorizationService.has_role(user, '') is False
            assert AuthorizationService.has_role(user, '   ') is False

    def test_has_role_uses_request_cache(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, role='focal_point')
        with app.test_request_context():
            first = AuthorizationService.has_role(user, 'assignment_editor_submitter')
            g._rbac_role_cache[('rbac_has_role', user.id, 'assignment_editor_submitter')] = False
            second = AuthorizationService.has_role(user, 'assignment_editor_submitter')
        assert first is True
        assert second is False

    def test_get_role_ids_for_user_id(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, role='focal_point')
            role_ids = AuthorizationService._get_role_ids_for_user_id(user.id)
        assert isinstance(role_ids, list)
        assert len(role_ids) >= 1

    def test_get_role_ids_for_zero_user(self, app):
        with app.app_context():
            assert AuthorizationService._get_role_ids_for_user_id(0) == []

    def test_prefetch_role_codes_empty_input(self, app):
        with app.app_context():
            assert AuthorizationService.prefetch_role_codes([]) == {}
            assert AuthorizationService.prefetch_role_codes([None]) == {}


@pytest.mark.unit
class TestAdminDetectionHelpers:
    def test_has_admin_role_with_admin_core(self, app, db_session):
        with app.app_context():
            admin = create_test_admin(db_session)
            assert AuthorizationService._has_admin_role(admin) is True

    def test_has_admin_role_unauthenticated(self):
        user = MagicMock()
        user.is_authenticated = False
        assert AuthorizationService._has_admin_role(user) is False

    def test_permissions_seeded_returns_bool(self, app):
        with app.app_context():
            assert isinstance(AuthorizationService._permissions_seeded(), bool)

    def test_rbac_enabled_caches_on_g(self, app):
        with app.test_request_context():
            first = AuthorizationService.rbac_enabled()
            assert hasattr(g, '_rbac_enabled')
            g._rbac_enabled = not first
            second = AuthorizationService.rbac_enabled()
        assert second is not first


@pytest.mark.unit
class TestAssignmentInternalHelpers:
    def test_assignment_is_effectively_closed_when_form_closed(self, app, db_session):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.is_closed = True
            assert AuthorizationService._assignment_is_effectively_closed(aes) is True

    def test_assignment_needs_reopen_for_submitted(self, app, db_session):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status='submitted')
            assert AuthorizationService._assignment_needs_reopen(aes) is True

    def test_can_access_assignment_unauthenticated(self, app, db_session):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            anon = MagicMock()
            anon.is_authenticated = False
            assert AuthorizationService.can_access_assignment(aes, anon) is False

    def test_can_edit_assignment_without_enter_permission(self, app, db_session):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            with patch.object(
                AuthorizationService,
                'has_rbac_permission',
                side_effect=lambda _user, code, **kwargs: code != 'assignment.enter',
            ):
                assert AuthorizationService.can_edit_assignment(aes, user) is False

    def test_can_submit_assignment_unauthenticated(self, app, db_session):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            anon = MagicMock()
            anon.is_authenticated = False
            assert AuthorizationService.can_submit_assignment(aes, anon) is False

    def test_can_send_for_review_unauthenticated(self, app, db_session):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            anon = MagicMock()
            anon.is_authenticated = False
            assert AuthorizationService.can_send_for_review(aes, anon) is False

    def test_can_return_for_revision_unauthenticated(self, app, db_session):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status='sent_for_review')
            anon = MagicMock()
            anon.is_authenticated = False
            assert AuthorizationService.can_return_for_revision(aes, anon) is False

    def test_can_reopen_assignment_unauthenticated(self, app, db_session):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status='submitted')
            anon = MagicMock()
            anon.is_authenticated = False
            assert AuthorizationService.can_reopen_assignment(aes, anon) is False

    def test_can_manage_closed_assignment_unauthenticated(self):
        anon = MagicMock()
        anon.is_authenticated = False
        assert AuthorizationService.can_manage_closed_assignment(anon) is False

    def test_can_manage_closed_assignment_system_manager(self, app, db_session):
        with app.app_context():
            sm = create_test_user(db_session, role='system_manager')
            assert AuthorizationService.can_manage_closed_assignment(sm) is True

    def test_assignment_is_effectively_closed_when_round_check_raises(self, app, db_session):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.is_closed = True
            with patch.object(
                type(aes),
                'is_round_closed_for_entity',
                side_effect=RuntimeError('round check failed'),
            ):
                assert AuthorizationService._assignment_is_effectively_closed(aes) is True

    def test_can_edit_assignment_when_closed_for_manager(self, app, db_session):
        with app.app_context():
            sm = create_test_user(db_session, role='system_manager')
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.is_closed = True
            with patch.object(AuthorizationService, 'can_access_assignment', return_value=True):
                assert AuthorizationService.can_edit_assignment(aes, sm) is True

    def test_has_country_access_via_admin_countries_view(self, app, db_session):
        from tests.factories import create_test_country
        with app.app_context():
            admin = create_test_admin(db_session, can_manage_countries=True)
            country = create_test_country(db_session)
            assert AuthorizationService.has_country_access(admin, country.id) is True


@pytest.mark.unit
class TestTemplateAccessExtended:
    def test_check_template_access_missing_template(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            assert AuthorizationService.check_template_access(999999, user.id) is False

    def test_check_template_access_shared_template(self, app, db_session):
        from app import db
        with app.app_context():
            owner = create_test_user(db_session)
            user = create_test_user(db_session)
            template = create_test_template(db_session, owner_id=owner.id)
            db.session.add(
                TemplateShare(
                    template_id=template.id,
                    shared_with_user_id=user.id,
                    shared_by_user_id=owner.id,
                )
            )
            db.session.commit()
            assert AuthorizationService.check_template_access(template.id, user.id) is True

    def test_get_scoped_grant_effect_none(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            assert AuthorizationService.get_scoped_grant_effect(
                user, 'nonexistent.permission', scope={'entity_type': 'country', 'entity_id': 1},
            ) is None


@pytest.mark.unit
class TestAuthorizationServiceDecorators:
    def test_admin_required_delegates(self, app):
        with patch('app.routes.admin.shared.admin_required', side_effect=lambda f: f) as mock_admin:
            @AuthorizationService.admin_required
            def view():
                return 'ok'
            assert view() == 'ok'
            mock_admin.assert_called_once()

    def test_permission_required_delegates(self, app):
        with patch('app.routes.admin.shared.permission_required', side_effect=lambda _p: (lambda f: f)) as mock_perm:
            @AuthorizationService.permission_required('admin.users.view')
            def view():
                return 'ok'
            assert view() == 'ok'
            mock_perm.assert_called_once_with('admin.users.view')

    def test_assignment_access_required_exception_redirects(self, app):
        @AuthorizationService.assignment_access_required
        def view(aid):
            return {'ok': aid}

        with app.test_request_context():
            with patch(
                'app.services.authorization_service.AssignmentEntityStatus.query.get_or_404',
                side_effect=RuntimeError('boom'),
            ):
                result = view(1)
        assert result.status_code in (301, 302, 303, 307, 308)

    def test_assignment_edit_required_access_denied(self, app, db_session):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            other = create_test_user(db_session, role='focal_point')
            other_id = int(other.id)
            aes_id = aes.id

        @AuthorizationService.assignment_edit_required
        def view(aid):
            return {'ok': aid}

        with app.test_request_context():
            from app.models import User
            login_user(User.query.get(other_id))
            result = view(aes_id)
        assert result.status_code in (301, 302, 303, 307, 308)

    def test_assignment_edit_required_edit_denied_with_access(self, app, db_session):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            aes.status = AssignmentEntityStatusValue.submitted.value
            db_session.commit()
            user_id = int(user.id)
            aes_id = aes.id

        @AuthorizationService.assignment_edit_required
        def view(aid):
            return {'ok': aid}

        with app.test_request_context():
            from app.models import User
            login_user(User.query.get(user_id))
            result = view(aes_id)
        assert result.status_code in (301, 302, 303, 307, 308)

    def test_assignment_edit_required_exception_redirects(self, app):
        @AuthorizationService.assignment_edit_required
        def view(aid):
            return {'ok': aid}

        with app.test_request_context():
            with patch(
                'app.services.authorization_service.AssignmentEntityStatus.query.get_or_404',
                side_effect=RuntimeError('boom'),
            ):
                result = view(1)
        assert result.status_code in (301, 302, 303, 307, 308)


@pytest.mark.unit
class TestHasRbacPermissionExtended:
    def test_empty_permission_code_returns_false(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            assert AuthorizationService.has_rbac_permission(user, '') is False
            assert AuthorizationService.has_rbac_permission(user, '   ') is False

    def test_system_manager_has_any_permission(self, app, db_session):
        with app.app_context():
            sm = create_test_user(db_session, role='system_manager')
            assert AuthorizationService.has_rbac_permission(sm, 'anything.custom') is True

    def test_has_rbac_permission_uses_request_cache(self, app, db_session):
        with app.app_context():
            user = create_test_admin(db_session, can_manage_users=True)
        with app.test_request_context():
            first = AuthorizationService.has_rbac_permission(user, 'admin.users.view')
            g._rbac_cache[(user.id, 'admin.users.view', '', 0, 0, 0)] = False
            second = AuthorizationService.has_rbac_permission(user, 'admin.users.view')
        assert first is True
        assert second is False

    def test_get_role_codes_cached(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, role='focal_point')
        with app.test_request_context():
            codes = AuthorizationService.get_role_codes(user)
            assert 'assignment_editor_submitter' in codes
            g._rbac_role_codes_cache[user.id] = ['cached_role']
            assert AuthorizationService.get_role_codes(user) == ['cached_role']

    def test_assignment_access_required_allows_focal_point(self, app, db_session):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            user_id = int(user.id)
            aes_id = aes.id

        @AuthorizationService.assignment_access_required
        def view(aid):
            return {'ok': aid}

        with app.test_request_context():
            from app.models import User
            login_user(User.query.get(user_id))
            result = view(aes_id)
        assert result == {'ok': aes_id}

    def test_check_self_report_access_non_self_report_period(self, app, db_session):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            assert AuthorizationService.check_self_report_access(aes, user) is False

    def test_validate_country_list_access_admin_returns_all(self, app, db_session):
        from tests.factories import create_test_country
        with app.app_context():
            admin = create_test_admin(db_session)
            c1 = create_test_country(db_session)
            c2 = create_test_country(db_session)
            result = AuthorizationService.validate_country_list_access(admin, [c1.id, c2.id])
        assert result == [c1.id, c2.id]

    def test_rbac_active_for_user_unauthenticated(self):
        anon = MagicMock()
        anon.is_authenticated = False
        assert AuthorizationService.rbac_active_for_user(anon) is False
