"""Unit tests for assignment delegation review workflow helpers."""

import pytest
from unittest.mock import MagicMock, patch

from app.models.assignments import AssignedForm, AssignmentEntityStatus
from app.models.enums import AssignmentEntityStatusValue, EntityType
from app.services.assignment_workflow_service import (
    delegation_review_source_statuses,
    resolve_submit_action,
    review_enabled,
    should_apply_sent_for_review,
)


@pytest.mark.unit
class TestAssignmentWorkflowService:
    def _aes(self, *, requires_delegation_review=False, status=AssignmentEntityStatusValue.in_progress):
        assigned_form = MagicMock(spec=AssignedForm)
        assigned_form.requires_delegation_review = requires_delegation_review
        aes = MagicMock(spec=AssignmentEntityStatus)
        aes.assigned_form = assigned_form
        aes.status = status
        return aes

    def test_review_enabled_false_by_default(self):
        aes = self._aes(requires_delegation_review=False)
        assert review_enabled(aes) is False

    def test_review_enabled_when_flag_set(self):
        aes = self._aes(requires_delegation_review=True)
        assert review_enabled(aes) is True

    @patch('app.services.assignment_workflow_service.is_organization_email', return_value=False)
    def test_ns_user_submit_becomes_send_for_review(self, _mock_org):
        aes = self._aes(requires_delegation_review=True)
        user = MagicMock()
        user.email = 'fp@national-society.org'
        assert resolve_submit_action(aes, user, 'submit') == 'send_for_review'

    @patch('app.services.assignment_workflow_service.is_organization_email', return_value=True)
    def test_org_user_submit_stays_submit(self, _mock_org):
        aes = self._aes(requires_delegation_review=True)
        user = MagicMock()
        user.email = 'fp@ifrc.org'
        assert resolve_submit_action(aes, user, 'submit') == 'submit'

    @patch('app.services.assignment_workflow_service.is_organization_email', return_value=False)
    def test_ns_user_without_review_flag_submits(self, _mock_org):
        aes = self._aes(requires_delegation_review=False)
        user = MagicMock()
        assert resolve_submit_action(aes, user, 'submit') == 'submit'

    @patch('app.services.assignment_workflow_service.is_organization_email', return_value=False)
    def test_should_apply_sent_for_review(self, _mock_org):
        aes = self._aes(requires_delegation_review=True)
        assert should_apply_sent_for_review(aes, 'send_for_review') is True
        assert should_apply_sent_for_review(aes, 'submit') is False

    @patch('app.services.assignment_workflow_service.is_organization_email', return_value=False)
    def test_requires_revision_also_sends_for_review(self, _mock_org):
        """NS focal points can re-send after delegation returns for changes."""
        aes = self._aes(
            requires_delegation_review=True,
            status=AssignmentEntityStatusValue.requires_revision,
        )
        user = MagicMock()
        user.email = 'fp@national-society.org'
        assert resolve_submit_action(aes, user, 'submit') == 'send_for_review'

    def test_delegation_review_source_statuses_contains_expected(self):
        sources = delegation_review_source_statuses()
        assert AssignmentEntityStatusValue.in_progress in sources
        assert AssignmentEntityStatusValue.requires_revision in sources
        assert AssignmentEntityStatusValue.submitted not in sources
