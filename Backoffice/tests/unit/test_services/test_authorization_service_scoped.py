"""Scoped RBAC and workflow tests for AuthorizationService."""
from unittest.mock import MagicMock

import pytest

from app.models.rbac import RbacAccessGrant
from app.services.organization.authorization_service import AuthorizationService
from tests.factories import (
    create_test_user,
    create_test_admin,
    create_test_assignment_entity_status,
    create_focal_point_with_country,
    _ensure_permission,
)

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]


def _grant_access(db_session, *, principal_type, principal_id, perm_code, scope_kind='global', effect='allow', **scope):
    pid = _ensure_permission(db_session, perm_code)
    grant = RbacAccessGrant(
        principal_type=principal_type,
        principal_id=principal_id,
        permission_id=pid,
        scope_kind=scope_kind,
        effect=effect,
        entity_type=scope.get('entity_type'),
        entity_id=scope.get('entity_id'),
        template_id=scope.get('template_id'),
        assigned_form_id=scope.get('assigned_form_id'),
    )
    db_session.add(grant)
    db_session.commit()
    return grant


@pytest.mark.unit
class TestScopedRbac:
    def test_entity_scoped_allow_grant(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_access(
                db_session,
                principal_type='user',
                principal_id=user.id,
                perm_code='assignment.view',
                scope_kind='entity',
                entity_type='country',
                entity_id=country.id,
            )
            scope = {
                'entity_type': 'country',
                'entity_id': country.id,
                'assigned_form_id': aes.assigned_form_id,
                'template_id': aes.assigned_form.template_id,
            }
            assert AuthorizationService.has_rbac_permission(user, 'assignment.view', scope=scope) is True
            decision = AuthorizationService.get_scoped_grant_decision(user, 'assignment.view', scope=scope)
            assert decision is not None
            assert decision['effect'] == 'allow'

    def test_entity_scoped_deny_wins(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_access(
                db_session,
                principal_type='user',
                principal_id=user.id,
                perm_code='assignment.view',
                scope_kind='entity',
                entity_type='country',
                entity_id=country.id,
                effect='allow',
            )
            _grant_access(
                db_session,
                principal_type='user',
                principal_id=user.id,
                perm_code='assignment.view',
                scope_kind='entity',
                entity_type='country',
                entity_id=country.id,
                effect='deny',
            )
            scope = {'entity_type': 'country', 'entity_id': country.id}
            assert AuthorizationService.has_rbac_permission(user, 'assignment.view', scope=scope) is False

    def test_unknown_permission_code_returns_false(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            assert AuthorizationService.has_rbac_permission(user, 'nonexistent.permission.code') is False

    def test_prefetch_role_codes(self, db_session, app):
        with app.app_context():
            u1 = create_test_user(db_session, role='focal_point')
            u2 = create_test_admin(db_session)
            result = AuthorizationService.prefetch_role_codes([u1.id, u2.id])
            assert u1.id in result
            assert 'assignment_editor_submitter' in result[u1.id]

    def test_get_scoped_grant_effect(self, db_session, app):
        with app.app_context():
            user, country, _aes = create_focal_point_with_country(db_session)
            _grant_access(
                db_session,
                principal_type='user',
                principal_id=user.id,
                perm_code='assignment.edit',
                scope_kind='entity',
                entity_type='country',
                entity_id=country.id,
            )
            scope = {'entity_type': 'country', 'entity_id': country.id}
            effect = AuthorizationService.get_scoped_grant_effect(user, 'assignment.edit', scope=scope)
            assert effect == 'allow'


@pytest.mark.unit
class TestAssignmentWorkflowMethods:
    def test_can_submit_assignment_focal_point(self, db_session, app):
        from tests.factories import _grant_role_permission
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, 'assignment_editor_submitter', 'assignment.submit')
            assert AuthorizationService.can_submit_assignment(aes, user) is True

    def test_can_send_for_review(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            aes.assigned_form.requires_delegation_review = True
            db_session.commit()
            db_session.refresh(aes)
            assert AuthorizationService.can_send_for_review(aes, user) is True

    def test_can_return_for_revision_system_manager(self, db_session, app):
        with app.app_context():
            sm = create_test_user(db_session, role='system_manager')
            aes = create_test_assignment_entity_status(db_session, status='sent_for_review')
            assert AuthorizationService.can_return_for_revision(aes, sm) is True

    def test_can_approve_system_manager(self, db_session, app):
        with app.app_context():
            sm = create_test_user(db_session, role='system_manager')
            aes = create_test_assignment_entity_status(db_session, status='submitted')
            assert AuthorizationService.can_approve_assignment(aes, sm) is True

    def test_can_reopen_system_manager(self, db_session, app):
        with app.app_context():
            sm = create_test_user(db_session, role='system_manager')
            aes = create_test_assignment_entity_status(db_session, status='submitted')
            assert AuthorizationService.can_reopen_assignment(aes, sm) is True

    def test_can_edit_assignment_focal_in_progress(self, db_session, app):
        from tests.factories import _grant_role_permission
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, 'assignment_editor_submitter', 'assignment.enter')
            assert AuthorizationService.can_edit_assignment(aes, user) is True

    def test_can_submit_assignment_focal_in_progress(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            assert AuthorizationService.can_submit_assignment(aes, user) is True

    def test_has_role_unauthenticated(self):
        user = MagicMock()
        user.is_authenticated = False
        assert AuthorizationService.has_role(user, 'admin_core') is False


@pytest.mark.unit
class TestAuthorizationDecorators:
    def test_assignment_access_required_allows(self, app, db_session):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            user_id = int(user.id)
            aes_id = aes.id

        @AuthorizationService.assignment_access_required
        def view(aid):
            return {'ok': aid}

        with app.test_request_context():
            from flask_login import login_user
            from app.models import User
            login_user(User.query.get(user_id))
            result = view(aes_id)
        assert result == {'ok': aes_id}

    def test_assignment_edit_required_denies_without_permission(self, app, db_session):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            aes.status = 'submitted'
            db_session.commit()
            user_id = int(user.id)
            aes_id = aes.id

        @AuthorizationService.assignment_edit_required
        def view(aid):
            return {'ok': aid}

        with app.test_request_context():
            from flask_login import login_user
            from app.models import User
            login_user(User.query.get(user_id))
            result = view(aes_id)
        assert result.status_code in (301, 302, 303, 307, 308)
