"""
Extended coverage tests for assignment_workflow_service.

Targets the ~5 lines still uncovered after test_assignment_workflow_service.py.
"""
import pytest
from unittest.mock import MagicMock, patch

from app.models.assignments import AssignedForm, AssignmentEntityStatus
from app.models.enums import AssignmentEntityStatusValue
from app.services.assignment_workflow_service import (
    _status_value,
    delegation_review_source_statuses,
    is_delegation_user,
    resolve_submit_action,
    review_enabled,
    should_apply_sent_for_review,
)

pytestmark = pytest.mark.unit


def _aes(*, requires_delegation_review=False, status=AssignmentEntityStatusValue.in_progress):
    af = MagicMock(spec=AssignedForm)
    af.requires_delegation_review = requires_delegation_review
    aes = MagicMock(spec=AssignmentEntityStatus)
    aes.assigned_form = af
    aes.status = status
    return aes


# ---------------------------------------------------------------------------
# is_delegation_user
# ---------------------------------------------------------------------------

class TestIsDelegationUser:
    def test_none_user_returns_false(self):
        assert is_delegation_user(None) is False

    @patch("app.services.assignment_workflow_service.is_organization_email", return_value=True)
    def test_delegation_user_with_org_email(self, _):
        user = MagicMock()
        user.email = "person@ifrc.org"
        assert is_delegation_user(user) is True

    @patch("app.services.assignment_workflow_service.is_organization_email", return_value=False)
    def test_non_delegation_user(self, _):
        user = MagicMock()
        user.email = "fp@ns.org"
        assert is_delegation_user(user) is False

    @patch("app.services.assignment_workflow_service.is_organization_email", return_value=False)
    def test_user_without_email_attribute(self, _):
        user = MagicMock(spec=[])  # No attributes at all
        assert is_delegation_user(user) is False


# ---------------------------------------------------------------------------
# _status_value
# ---------------------------------------------------------------------------

class TestStatusValue:
    def test_enum_status_returns_value(self):
        aes = _aes(status=AssignmentEntityStatusValue.submitted)
        assert _status_value(aes) == AssignmentEntityStatusValue.submitted.value

    def test_string_status_returns_string(self):
        aes = _aes()
        aes.status = "in_progress"
        assert _status_value(aes) == "in_progress"


# ---------------------------------------------------------------------------
# resolve_submit_action — remaining branches
# ---------------------------------------------------------------------------

class TestResolveSubmitActionEdgeCases:
    @patch("app.services.assignment_workflow_service.is_organization_email", return_value=False)
    def test_save_action_returns_save(self, _):
        aes = _aes(requires_delegation_review=True)
        user = MagicMock()
        assert resolve_submit_action(aes, user, "save") == "save"

    @patch("app.services.assignment_workflow_service.is_organization_email", return_value=False)
    def test_send_for_review_action_returns_send_for_review(self, _):
        aes = _aes(requires_delegation_review=True)
        user = MagicMock()
        assert resolve_submit_action(aes, user, "send_for_review") == "send_for_review"

    @patch("app.services.assignment_workflow_service.is_organization_email", return_value=False)
    def test_empty_action_defaults_to_save(self, _):
        aes = _aes()
        user = MagicMock()
        assert resolve_submit_action(aes, user, "") == "save"

    @patch("app.services.assignment_workflow_service.is_organization_email", return_value=False)
    def test_none_action_defaults_to_save(self, _):
        aes = _aes()
        user = MagicMock()
        assert resolve_submit_action(aes, user, None) == "save"

    @patch("app.services.assignment_workflow_service.is_organization_email", return_value=False)
    def test_unknown_action_returned_as_is(self, _):
        """An unrecognised action that is not 'submit' should be returned verbatim."""
        aes = _aes(requires_delegation_review=True)
        user = MagicMock()
        # 'approve' is not 'save', 'send_for_review', or 'submit' → returned unchanged
        assert resolve_submit_action(aes, user, "approve") == "approve"

    @patch("app.services.assignment_workflow_service.is_organization_email", return_value=False)
    def test_ns_user_approved_status_submit_stays_submit(self, _):
        """If review enabled but status is approved (not in source statuses), stays submit."""
        aes = _aes(
            requires_delegation_review=True,
            status=AssignmentEntityStatusValue.approved,
        )
        user = MagicMock()
        user.email = "fp@ns.org"
        assert resolve_submit_action(aes, user, "submit") == "submit"


# ---------------------------------------------------------------------------
# should_apply_sent_for_review — review disabled path
# ---------------------------------------------------------------------------

class TestShouldApplySentForReviewDisabled:
    @patch("app.services.assignment_workflow_service.is_organization_email", return_value=False)
    def test_review_not_enabled_send_for_review_is_false(self, _):
        aes = _aes(requires_delegation_review=False)
        assert should_apply_sent_for_review(aes, "send_for_review") is False

    @patch("app.services.assignment_workflow_service.is_organization_email", return_value=False)
    def test_save_action_always_false(self, _):
        aes = _aes(requires_delegation_review=True)
        assert should_apply_sent_for_review(aes, "save") is False


# ---------------------------------------------------------------------------
# delegation_review_source_statuses
# ---------------------------------------------------------------------------

class TestDelegationReviewSourceStatuses:
    def test_returns_tuple(self):
        sources = delegation_review_source_statuses()
        assert isinstance(sources, tuple)
        assert len(sources) == 2


# ---------------------------------------------------------------------------
# review_enabled — edge: no assigned_form
# ---------------------------------------------------------------------------

class TestReviewEnabledEdge:
    def test_review_enabled_no_assigned_form(self):
        aes = MagicMock(spec=AssignmentEntityStatus)
        aes.assigned_form = None
        assert review_enabled(aes) is False

    def test_review_enabled_assigned_form_without_flag_attr(self):
        aes = MagicMock(spec=AssignmentEntityStatus)
        aes.assigned_form = MagicMock(spec=[])  # No attributes
        assert review_enabled(aes) is False
