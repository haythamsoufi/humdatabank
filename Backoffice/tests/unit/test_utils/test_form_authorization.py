"""Unit tests for form_authorization decorators and helpers."""
from unittest.mock import MagicMock, patch

import pytest
from flask import g

from app.utils.form_authorization import (
    redirect_if_assignment_entry_blocked,
    has_country_access,
    can_edit_assignment,
    validate_country_list_access,
    check_self_report_access,
    check_assignment_access,
    check_assignment_edit_access,
    check_document_access,
    assignment_is_round_closed_for_entity,
    assignment_readonly_notice_reason,
    READONLY_NOTICE_PUBLIC,
    READONLY_NOTICE_SENT_FOR_REVIEW,
    READONLY_NOTICE_APPROVED,
    READONLY_NOTICE_SUBMITTED,
    READONLY_NOTICE_VIEW_ONLY,
    READONLY_NOTICE_ROUND_CLOSED,
    READONLY_NOTICE_GENERIC,
)

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]


@pytest.mark.unit
class TestRedirectIfAssignmentEntryBlocked:
    def test_none_assignment_returns_none(self):
        assert redirect_if_assignment_entry_blocked(None, inactive_message='x') is None

    def test_active_assignment_returns_none(self, app):
        assigned = MagicMock()
        assigned.is_entry_allowed = True
        with app.test_request_context():
            assert redirect_if_assignment_entry_blocked(assigned, inactive_message='inactive') is None

    def test_inactive_assignment_redirects(self, app):
        assigned = MagicMock()
        assigned.is_entry_allowed = False
        with app.test_request_context():
            result = redirect_if_assignment_entry_blocked(assigned, inactive_message='inactive')
        assert result is not None
        assert result.status_code in (301, 302, 303, 307, 308)


@pytest.mark.unit
class TestFormAuthorizationWrappers:
    def test_has_country_access_delegates(self, app, db_session):
        from tests.factories import create_test_admin
        with app.app_context():
            admin = create_test_admin(db_session)
            assert has_country_access(admin, 999) is True

    def test_can_edit_assignment_delegates(self, app):
        from unittest.mock import MagicMock
        aes = MagicMock()
        user = MagicMock()
        user.is_authenticated = True
        with app.app_context():
            with patch(
                'app.services.organization.authorization_service.AuthorizationService.can_edit_assignment',
                return_value=True,
            ) as mock_fn:
                assert can_edit_assignment(aes, user) is True
            mock_fn.assert_called_once_with(aes, user)

    def test_validate_country_list_access_delegates(self, app, db_session):
        from tests.factories import create_test_admin
        with app.app_context():
            admin = create_test_admin(db_session)
            assert validate_country_list_access(admin, [1, 2, 3]) == [1, 2, 3]

    def test_check_self_report_access_delegates(self, app):
        aes = MagicMock()
        user = MagicMock()
        with app.app_context():
            with patch(
                'app.services.organization.authorization_service.AuthorizationService.check_self_report_access',
                return_value=False,
            ) as mock_fn:
                assert check_self_report_access(aes, user) is False
            mock_fn.assert_called_once_with(aes, user)


def _readonly_aes(*, status='in_progress', round_closed=False):
    aes = MagicMock()
    aes.status = status
    aes.entity_type = 'country'
    aes.entity_id = 1
    aes.assigned_form_id = 10
    aes.assigned_form = MagicMock(template_id=20)
    aes.is_round_closed_for_entity = MagicMock(return_value=round_closed)
    return aes


def _readonly_user(*, authenticated=True):
    user = MagicMock()
    user.is_authenticated = authenticated
    return user


@pytest.mark.unit
class TestAssignmentReadonlyNoticeReason:
    def test_public_submission(self):
        assert assignment_readonly_notice_reason(None, None, is_public_submission=True) == READONLY_NOTICE_PUBLIC

    def test_workflow_status_before_permissions(self):
        aes = _readonly_aes(status='submitted', round_closed=True)
        user = _readonly_user()
        with patch(
            'app.services.organization.authorization_service.AuthorizationService.has_rbac_permission',
            return_value=False,
        ):
            assert assignment_readonly_notice_reason(aes, user) == READONLY_NOTICE_SUBMITTED

        aes.status = 'approved'
        with patch(
            'app.services.organization.authorization_service.AuthorizationService.has_rbac_permission',
            return_value=False,
        ):
            assert assignment_readonly_notice_reason(aes, user) == READONLY_NOTICE_APPROVED

        aes.status = 'sent_for_review'
        with patch(
            'app.services.organization.authorization_service.AuthorizationService.has_rbac_permission',
            return_value=False,
        ):
            assert assignment_readonly_notice_reason(aes, user) == READONLY_NOTICE_SENT_FOR_REVIEW

    def test_viewer_on_open_assignment_is_view_only_not_round_closed(self):
        """Jinja used to treat the unbound method as truthy, so viewers always saw 'round closed'."""
        aes = _readonly_aes(status='in_progress', round_closed=False)
        user = _readonly_user()
        with patch(
            'app.services.organization.authorization_service.AuthorizationService.has_rbac_permission',
            return_value=False,
        ) as mock_perm:
            assert assignment_readonly_notice_reason(aes, user) == READONLY_NOTICE_VIEW_ONLY
        mock_perm.assert_called_once()
        assert mock_perm.call_args.args[1] == 'assignment.enter'

    def test_viewer_on_closed_round_is_still_view_only(self):
        aes = _readonly_aes(status='pending', round_closed=True)
        user = _readonly_user()
        with patch(
            'app.services.organization.authorization_service.AuthorizationService.has_rbac_permission',
            return_value=False,
        ):
            assert assignment_readonly_notice_reason(aes, user) == READONLY_NOTICE_VIEW_ONLY

    def test_enterer_on_closed_round_sees_round_closed(self):
        aes = _readonly_aes(status='in_progress', round_closed=True)
        user = _readonly_user()
        with patch(
            'app.services.organization.authorization_service.AuthorizationService.has_rbac_permission',
            return_value=True,
        ):
            assert assignment_readonly_notice_reason(aes, user) == READONLY_NOTICE_ROUND_CLOSED

    def test_enterer_on_open_assignment_falls_back_to_generic(self):
        aes = _readonly_aes(status='cancelled', round_closed=False)
        user = _readonly_user()
        with patch(
            'app.services.organization.authorization_service.AuthorizationService.has_rbac_permission',
            return_value=True,
        ):
            assert assignment_readonly_notice_reason(aes, user) == READONLY_NOTICE_GENERIC

    def test_enum_status_value_is_unwrapped(self):
        status = MagicMock()
        status.value = 'approved'
        aes = _readonly_aes(status=status, round_closed=False)
        assert assignment_readonly_notice_reason(aes, _readonly_user()) == READONLY_NOTICE_APPROVED

    def test_round_closed_helper_requires_calling_the_method(self):
        aes = _readonly_aes(round_closed=False)
        assert assignment_is_round_closed_for_entity(aes) is False
        aes.is_round_closed_for_entity.assert_called_once_with()

        aes.is_round_closed_for_entity.return_value = True
        assert assignment_is_round_closed_for_entity(aes) is True

        dummy = MagicMock(spec=[])
        assert assignment_is_round_closed_for_entity(dummy) is False
        assert assignment_is_round_closed_for_entity(None) is False


@pytest.mark.unit
class TestCheckAssignmentAccessDecorator:
    def _view(self, aes_id):
        return {'aes_id': aes_id}

    def test_success_calls_view(self, app):
        aes = MagicMock()
        aes.assigned_form = MagicMock(is_entry_allowed=True)
        decorated = check_assignment_access(self._view)
        with app.test_request_context():
            with patch('app.utils.form_authorization.AssignmentEntityStatus.query') as mock_q, \
                 patch('app.services.organization.authorization_service.AuthorizationService.can_access_assignment', return_value=True), \
                 patch('app.utils.form_authorization.current_user', MagicMock(email='u@test.com')):
                mock_q.get_or_404.return_value = aes
                result = decorated(42)
        assert result == {'aes_id': 42}

    def test_success_without_assigned_form(self, app):
        aes = MagicMock()
        aes.assigned_form = None
        decorated = check_assignment_access(self._view)
        with app.test_request_context():
            with patch('app.utils.form_authorization.AssignmentEntityStatus.query') as mock_q, \
                 patch('app.services.organization.authorization_service.AuthorizationService.can_access_assignment', return_value=True), \
                 patch('app.utils.form_authorization.current_user', MagicMock(email='u@test.com')):
                mock_q.get_or_404.return_value = aes
                result = decorated(42)
        assert result == {'aes_id': 42}

    def test_inactive_assignment_redirects(self, app):
        aes = MagicMock()
        aes.assigned_form = MagicMock(is_entry_allowed=False)
        decorated = check_assignment_access(self._view)
        with app.test_request_context():
            with patch('app.utils.form_authorization.AssignmentEntityStatus.query') as mock_q:
                mock_q.get_or_404.return_value = aes
                result = decorated(42)
        assert result.status_code in (301, 302, 303, 307, 308)

    def test_access_denied_redirects(self, app):
        aes = MagicMock()
        aes.assigned_form = MagicMock(is_entry_allowed=True)
        aes.entity_type = 'country'
        aes.entity_id = 1
        decorated = check_assignment_access(self._view)
        with app.test_request_context():
            with patch('app.utils.form_authorization.AssignmentEntityStatus.query') as mock_q, \
                 patch('app.services.organization.authorization_service.AuthorizationService.can_access_assignment', return_value=False), \
                 patch('app.services.organization.entity_service.EntityService.get_entity_display_name', return_value='Testland'), \
                 patch('app.utils.form_authorization.current_user', MagicMock(email='u@test.com')):
                mock_q.get_or_404.return_value = aes
                result = decorated(42)
        assert result.status_code in (301, 302, 303, 307, 308)

    def test_exception_redirects_to_dashboard(self, app):
        decorated = check_assignment_access(self._view)
        with app.test_request_context():
            with patch(
                'app.utils.form_authorization.AssignmentEntityStatus.query.get_or_404',
                side_effect=RuntimeError('boom'),
            ):
                result = decorated(42)
        assert result.status_code in (301, 302, 303, 307, 308)


@pytest.mark.unit
class TestCheckAssignmentEditAccessDecorator:
    def _view(self, aes_id):
        return {'edited': aes_id}

    def test_edit_allowed(self, app):
        aes = MagicMock()
        aes.assigned_form = MagicMock(is_entry_allowed=True)
        aes.id = 7
        aes.status = 'in_progress'
        aes.country = MagicMock(name='Testland')
        decorated = check_assignment_edit_access(self._view)
        with app.test_request_context():
            with patch('app.utils.form_authorization.AssignmentEntityStatus.query') as mock_q, \
                 patch('app.services.organization.authorization_service.AuthorizationService.can_access_assignment', return_value=True), \
                 patch('app.utils.form_authorization.can_edit_assignment', return_value=True), \
                 patch('app.utils.form_authorization.current_user', MagicMock(email='u@test.com')):
                mock_q.get_or_404.return_value = aes
                result = decorated(7)
        assert result == {'edited': 7}

    def test_edit_denied_redirects_to_form(self, app):
        aes = MagicMock()
        aes.assigned_form = MagicMock(is_entry_allowed=True)
        aes.id = 7
        aes.status = 'submitted'
        aes.country = None
        decorated = check_assignment_edit_access(self._view)
        with app.test_request_context():
            with patch('app.utils.form_authorization.AssignmentEntityStatus.query') as mock_q, \
                 patch('app.services.organization.authorization_service.AuthorizationService.can_access_assignment', return_value=True), \
                 patch('app.utils.form_authorization.can_edit_assignment', return_value=False), \
                 patch('app.utils.form_authorization.current_user', MagicMock(email='u@test.com')):
                mock_q.get_or_404.return_value = aes
                result = decorated(7)
        assert result.status_code in (301, 302, 303, 307, 308)

    def test_edit_inactive_assignment_redirects(self, app):
        aes = MagicMock()
        aes.assigned_form = MagicMock(is_entry_allowed=False)
        decorated = check_assignment_edit_access(self._view)
        with app.test_request_context():
            with patch('app.utils.form_authorization.AssignmentEntityStatus.query') as mock_q:
                mock_q.get_or_404.return_value = aes
                result = decorated(7)
        assert result.status_code in (301, 302, 303, 307, 308)

    def test_edit_access_denied_redirects(self, app):
        aes = MagicMock()
        aes.assigned_form = MagicMock(is_entry_allowed=True)
        aes.entity_type = 'country'
        aes.entity_id = 1
        decorated = check_assignment_edit_access(self._view)
        with app.test_request_context():
            with patch('app.utils.form_authorization.AssignmentEntityStatus.query') as mock_q, \
                 patch('app.services.organization.authorization_service.AuthorizationService.can_access_assignment', return_value=False), \
                 patch('app.services.organization.entity_service.EntityService.get_entity_display_name', return_value='Testland'), \
                 patch('app.utils.form_authorization.current_user', MagicMock(email='u@test.com')):
                mock_q.get_or_404.return_value = aes
                result = decorated(7)
        assert result.status_code in (301, 302, 303, 307, 308)

    def test_edit_exception_redirects(self, app):
        decorated = check_assignment_edit_access(self._view)
        with app.test_request_context():
            with patch(
                'app.utils.form_authorization.AssignmentEntityStatus.query.get_or_404',
                side_effect=RuntimeError('boom'),
            ):
                result = decorated(7)
        assert result.status_code in (301, 302, 303, 307, 308)


@pytest.mark.unit
class TestAdminRequiredPassthrough:
    def test_delegates_to_admin_shared(self, app):
        from app.utils.form_authorization import admin_required
        with patch('app.routes.admin.shared.admin_required', side_effect=lambda f: f) as mock_admin:
            @admin_required
            def view():
                return 'ok'
            assert view() == 'ok'
            mock_admin.assert_called_once()


@pytest.mark.unit
class TestCheckDocumentAccessDecorator:
    def _view(self, document_id):
        return {'doc': document_id}

    def test_document_not_found(self, app):
        decorated = check_document_access(self._view)
        with app.test_request_context():
            with patch('app.models.SubmittedDocument.query') as mock_q:
                mock_q.get.return_value = None
                result = decorated(99)
        assert result.status_code in (301, 302, 303, 307, 308)

    def test_document_access_granted(self, app):
        doc = MagicMock()
        aes = MagicMock()
        aes.assigned_form = MagicMock(is_entry_allowed=True)
        aes.entity_type = 'country'
        aes.entity_id = 5
        aes.status = 'in_progress'
        aes.country = MagicMock(name='Testland')
        doc.assignment_entity_status = aes
        decorated = check_document_access(self._view)
        user = MagicMock()
        user.is_authenticated = True
        with app.test_request_context():
            with patch('app.models.SubmittedDocument.query') as mock_q, \
                 patch('app.utils.form_authorization.has_country_access', return_value=True), \
                 patch('app.utils.form_authorization.can_edit_assignment', return_value=True), \
                 patch('app.utils.form_authorization.current_user', user):
                mock_q.get.return_value = doc
                result = decorated(10)
        assert result == {'doc': 10}

    def test_document_no_aes_redirects(self, app):
        doc = MagicMock()
        doc.assignment_entity_status = None
        decorated = check_document_access(self._view)
        with app.test_request_context():
            with patch('app.models.SubmittedDocument.query') as mock_q:
                mock_q.get.return_value = doc
                result = decorated(10)
        assert result.status_code in (301, 302, 303, 307, 308)

    def test_document_country_access_denied(self, app):
        doc = MagicMock()
        aes = MagicMock()
        aes.assigned_form = MagicMock(is_entry_allowed=True)
        aes.entity_type = 'country'
        aes.entity_id = 5
        doc.assignment_entity_status = aes
        decorated = check_document_access(self._view)
        with app.test_request_context():
            with patch('app.models.SubmittedDocument.query') as mock_q, \
                 patch('app.utils.form_authorization.has_country_access', return_value=False), \
                 patch('app.utils.form_authorization.current_user', MagicMock()):
                mock_q.get.return_value = doc
                result = decorated(10)
        assert result.status_code in (301, 302, 303, 307, 308)

    def test_document_non_country_entity_denied(self, app):
        doc = MagicMock()
        aes = MagicMock()
        aes.assigned_form = MagicMock(is_entry_allowed=True)
        aes.entity_type = 'region'
        aes.entity_id = 5
        doc.assignment_entity_status = aes
        decorated = check_document_access(self._view)
        with app.test_request_context():
            with patch('app.models.SubmittedDocument.query') as mock_q, \
                 patch('app.utils.form_authorization.current_user', MagicMock()):
                mock_q.get.return_value = doc
                result = decorated(10)
        assert result.status_code in (301, 302, 303, 307, 308)

    def test_document_inactive_assignment_redirects(self, app):
        doc = MagicMock()
        aes = MagicMock()
        aes.assigned_form = MagicMock(is_entry_allowed=False)
        doc.assignment_entity_status = aes
        decorated = check_document_access(self._view)
        with app.test_request_context():
            with patch('app.models.SubmittedDocument.query') as mock_q:
                mock_q.get.return_value = doc
                result = decorated(10)
        assert result.status_code in (301, 302, 303, 307, 308)

    def test_document_edit_blocked_redirects(self, app):
        doc = MagicMock()
        aes = MagicMock()
        aes.assigned_form = MagicMock(is_entry_allowed=True)
        aes.entity_type = 'country'
        aes.entity_id = 5
        aes.status = 'submitted'
        aes.country = MagicMock(name='Testland')
        doc.assignment_entity_status = aes
        decorated = check_document_access(self._view)
        with app.test_request_context():
            with patch('app.models.SubmittedDocument.query') as mock_q, \
                 patch('app.utils.form_authorization.has_country_access', return_value=True), \
                 patch('app.utils.form_authorization.can_edit_assignment', return_value=False), \
                 patch('app.utils.form_authorization.current_user', MagicMock()):
                mock_q.get.return_value = doc
                result = decorated(10)
        assert result.status_code in (301, 302, 303, 307, 308)

    def test_document_exception_redirects(self, app):
        decorated = check_document_access(self._view)
        with app.test_request_context():
            with patch(
                'app.models.SubmittedDocument.query.get',
                side_effect=RuntimeError('boom'),
            ):
                result = decorated(10)
        assert result.status_code in (301, 302, 303, 307, 308)


@pytest.mark.unit
class TestFormAuthorizationIntegration:
    def test_check_assignment_access_with_real_aes(self, app, db_session):
        from tests.factories import create_focal_point_with_country
        from flask_login import login_user
        from app.models import User

        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            user_id = int(user.id)
            aes_id = aes.id

        @check_assignment_access
        def view(aid):
            return {'ok': aid}

        with app.test_request_context():
            login_user(User.query.get(user_id))
            result = view(aes_id)
        assert result == {'ok': aes_id}
