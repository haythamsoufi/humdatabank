"""Authorization rules for NS review workflow."""

import pytest
from unittest.mock import MagicMock, patch

from app.models.assignments import AssignedForm, AssignmentEntityStatus
from app.models.enums import AssignmentEntityStatusValue
from app.services.authorization_service import AuthorizationService


@pytest.mark.unit
class TestAssignmentNsReviewAuthorization:
    def _aes(self, *, requires_delegation_review=True, status=AssignmentEntityStatusValue.sent_for_review):
        assigned_form = MagicMock(spec=AssignedForm)
        assigned_form.requires_delegation_review = requires_delegation_review
        assigned_form.template_id = 1
        aes = MagicMock(spec=AssignmentEntityStatus)
        aes.assigned_form = assigned_form
        aes.status = status
        aes.entity_type = 'country'
        aes.entity_id = 1
        aes.assigned_form_id = 1
        return aes

    def _user(self, email='user@example.org', authenticated=True):
        user = MagicMock()
        user.is_authenticated = authenticated
        user.email = email
        return user

    def test_ns_cannot_edit_sent_for_review(self, app):
        with app.app_context():
            with patch.object(AuthorizationService, 'can_access_assignment', return_value=True), \
                 patch.object(AuthorizationService, 'has_rbac_permission', return_value=True), \
                 patch('app.services.assignment_workflow_service.is_organization_email', return_value=False):
                aes = self._aes()
                assert AuthorizationService.can_edit_assignment(aes, self._user()) is False

    def test_org_can_edit_sent_for_review(self, app):
        with app.app_context():
            with patch.object(AuthorizationService, 'can_access_assignment', return_value=True), \
                 patch.object(AuthorizationService, 'has_rbac_permission', return_value=True), \
                 patch('app.services.assignment_workflow_service.is_organization_email', return_value=True):
                aes = self._aes()
                assert AuthorizationService.can_edit_assignment(aes, self._user('del@ifrc.org')) is True

    def test_org_can_submit_from_sent_for_review(self, app):
        with app.app_context():
            with patch.object(AuthorizationService, 'can_access_assignment', return_value=True), \
                 patch.object(AuthorizationService, 'has_rbac_permission', return_value=True), \
                 patch('app.services.assignment_workflow_service.is_organization_email', return_value=True):
                aes = self._aes()
                assert AuthorizationService.can_submit_assignment(aes, self._user('del@ifrc.org')) is True

    def test_ns_cannot_submit_from_sent_for_review(self, app):
        with app.app_context():
            with patch.object(AuthorizationService, 'can_access_assignment', return_value=True), \
                 patch.object(AuthorizationService, 'has_rbac_permission', return_value=True), \
                 patch('app.services.assignment_workflow_service.is_organization_email', return_value=False):
                aes = self._aes()
                assert AuthorizationService.can_submit_assignment(aes, self._user()) is False

    def test_ns_can_send_for_review_from_in_progress(self, app):
        with app.app_context():
            with patch.object(AuthorizationService, 'can_access_assignment', return_value=True), \
                 patch.object(AuthorizationService, 'has_rbac_permission', return_value=True), \
                 patch('app.services.assignment_workflow_service.is_organization_email', return_value=False):
                aes = self._aes(status=AssignmentEntityStatusValue.in_progress)
                assert AuthorizationService.can_send_for_review(aes, self._user()) is True

    def test_ns_can_send_for_review_from_pending(self, app):
        """Focal point on a brand-new (pending) assignment must see Send for Review, not Submit."""
        with app.app_context():
            with patch.object(AuthorizationService, 'can_access_assignment', return_value=True), \
                 patch.object(AuthorizationService, 'has_rbac_permission', return_value=True), \
                 patch('app.services.assignment_workflow_service.is_organization_email', return_value=False):
                aes = self._aes(status=AssignmentEntityStatusValue.pending)
                assert AuthorizationService.can_send_for_review(aes, self._user()) is True

    def test_ns_cannot_submit_from_pending_when_review_required(self, app):
        """Submit must be hidden for focal points on pending assignments that require delegation review."""
        with app.app_context():
            with patch.object(AuthorizationService, 'can_access_assignment', return_value=True), \
                 patch.object(AuthorizationService, 'has_rbac_permission', return_value=True), \
                 patch('app.services.assignment_workflow_service.is_organization_email', return_value=False):
                aes = self._aes(status=AssignmentEntityStatusValue.pending)
                assert AuthorizationService.can_submit_assignment(aes, self._user()) is False

    def test_org_cannot_send_for_review(self, app):
        with app.app_context():
            with patch.object(AuthorizationService, 'can_access_assignment', return_value=True), \
                 patch.object(AuthorizationService, 'has_rbac_permission', return_value=True), \
                 patch('app.services.assignment_workflow_service.is_organization_email', return_value=True):
                aes = self._aes(status=AssignmentEntityStatusValue.in_progress)
                assert AuthorizationService.can_send_for_review(aes, self._user('del@ifrc.org')) is False

    def test_system_manager_org_cannot_send_for_review(self, app):
        with app.app_context():
            with patch.object(AuthorizationService, 'can_access_assignment', return_value=True), \
                 patch.object(AuthorizationService, 'is_system_manager', return_value=True), \
                 patch('app.services.assignment_workflow_service.is_organization_email', return_value=True):
                aes = self._aes(status=AssignmentEntityStatusValue.in_progress)
                assert AuthorizationService.can_send_for_review(aes, self._user('admin@ifrc.org')) is False

    def test_org_can_return_for_revision(self, app):
        with app.app_context():
            with patch.object(AuthorizationService, 'can_access_assignment', return_value=True), \
                 patch.object(AuthorizationService, 'has_rbac_permission', return_value=True), \
                 patch('app.services.assignment_workflow_service.is_organization_email', return_value=True):
                aes = self._aes()
                assert AuthorizationService.can_return_for_revision(aes, self._user('del@ifrc.org')) is True

    def test_org_cannot_return_for_revision_from_in_progress(self, app):
        with app.app_context():
            with patch.object(AuthorizationService, 'can_access_assignment', return_value=True), \
                 patch.object(AuthorizationService, 'has_rbac_permission', return_value=True), \
                 patch('app.services.assignment_workflow_service.is_organization_email', return_value=True):
                aes = self._aes(status=AssignmentEntityStatusValue.in_progress)
                assert AuthorizationService.can_return_for_revision(aes, self._user('del@ifrc.org')) is False

    def test_system_manager_can_return_for_revision_from_sent_for_review(self, app):
        with app.app_context():
            with patch.object(AuthorizationService, 'can_access_assignment', return_value=True), \
                 patch.object(AuthorizationService, 'is_system_manager', return_value=True):
                aes = self._aes()
                assert AuthorizationService.can_return_for_revision(aes, self._user('admin@ifrc.org')) is True

    def test_system_manager_cannot_return_for_revision_from_in_progress(self, app):
        with app.app_context():
            with patch.object(AuthorizationService, 'can_access_assignment', return_value=True), \
                 patch.object(AuthorizationService, 'is_system_manager', return_value=True):
                aes = self._aes(status=AssignmentEntityStatusValue.in_progress)
                assert AuthorizationService.can_return_for_revision(aes, self._user('admin@ifrc.org')) is False
