"""
Tests for app/routes/main/__init__.py — the Blueprint context processor.

The ``inject_rbac_helpers`` app-context-processor returns a dict of callables
that are injected into every Jinja2 template rendered by the ``main`` blueprint.
We test each inner helper for:
  * Normal return values (delegating to AuthorizationService)
  * Graceful ``False`` fallback when AuthorizationService raises an exception
  * Edge-case logic (e.g. ``can_reopen_closed_assignment`` with None assignment)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask_login import login_user

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_helpers(app, user):
    """
    Call ``inject_rbac_helpers`` inside a request context logged in as *user*.

    Returns the dict that the context processor would inject into templates.
    ``AuthorizationService`` is imported inside the context-processor body so
    we always patch at the source module level to affect the live class object.
    """
    from app.routes.main import inject_rbac_helpers

    with app.test_request_context("/"):
        login_user(user)
        return inject_rbac_helpers()


# Convenience shorthand for the authorization service patch target
_AUTH_SVC = "app.services.authorization_service.AuthorizationService"


# ---------------------------------------------------------------------------
# Context-processor return value
# ---------------------------------------------------------------------------

class TestInjectRbacHelpersReturnValue:
    """The context processor must return a dict with exactly the expected keys."""

    def test_returns_dict_with_all_keys(self, app, test_user):
        helpers = _get_helpers(app, test_user)

        expected_keys = {
            "has_permission",
            "can_approve_assignment",
            "can_reopen_assignment",
            "can_reopen_closed_assignment",
            "can_send_for_review",
            "can_return_for_revision",
            "can_submit_assignment",
        }
        assert set(helpers.keys()) == expected_keys

    def test_all_values_are_callable(self, app, test_user):
        helpers = _get_helpers(app, test_user)
        for key, val in helpers.items():
            assert callable(val), f"Expected {key!r} to be callable"


# ---------------------------------------------------------------------------
# has_permission
# ---------------------------------------------------------------------------

class TestHasPermission:
    def test_returns_true_when_service_returns_true(self, app, test_user):
        with patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True):
            helpers = _get_helpers(app, test_user)
            assert helpers["has_permission"]("some.permission") is True

    def test_returns_false_when_service_returns_false(self, app, test_user):
        with patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=False):
            helpers = _get_helpers(app, test_user)
            assert helpers["has_permission"]("some.permission") is False

    def test_passes_scope_to_service(self, app, test_user):
        with patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True) as mock_check:
            helpers = _get_helpers(app, test_user)
            helpers["has_permission"]("some.permission", scope="country:1")
            mock_check.assert_called_once()
            call_args = mock_check.call_args
            # scope is passed as keyword argument
            assert call_args.kwargs.get("scope") == "country:1"

    def test_returns_false_on_exception(self, app, test_user):
        with patch(f"{_AUTH_SVC}.has_rbac_permission", side_effect=RuntimeError("DB error")):
            helpers = _get_helpers(app, test_user)
            assert helpers["has_permission"]("some.permission") is False


# ---------------------------------------------------------------------------
# can_approve_assignment
# ---------------------------------------------------------------------------

class TestCanApproveAssignment:
    def test_returns_true_when_service_returns_true(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_approve_assignment", return_value=True):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_approve_assignment"](aes) is True

    def test_returns_false_when_service_returns_false(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_approve_assignment", return_value=False):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_approve_assignment"](aes) is False

    def test_returns_false_on_exception(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_approve_assignment", side_effect=Exception("boom")):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_approve_assignment"](aes) is False


# ---------------------------------------------------------------------------
# can_reopen_assignment
# ---------------------------------------------------------------------------

class TestCanReopenAssignment:
    def test_returns_true_when_service_returns_true(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_reopen_assignment", return_value=True):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_reopen_assignment"](aes) is True

    def test_returns_false_when_service_returns_false(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_reopen_assignment", return_value=False):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_reopen_assignment"](aes) is False

    def test_returns_false_on_exception(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_reopen_assignment", side_effect=Exception("boom")):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_reopen_assignment"](aes) is False


# ---------------------------------------------------------------------------
# can_reopen_closed_assignment
# ---------------------------------------------------------------------------

class TestCanReopenClosedAssignment:
    def test_returns_false_for_none_assignment(self, app, test_user):
        helpers = _get_helpers(app, test_user)
        assert helpers["can_reopen_closed_assignment"](None) is False

    def test_returns_true_for_system_manager(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=True):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_reopen_closed_assignment"](aes) is True

    def test_returns_true_when_has_assignments_edit_permission(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_reopen_closed_assignment"](aes) is True

    def test_returns_false_when_not_system_manager_and_no_permission(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=False):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_reopen_closed_assignment"](aes) is False

    def test_returns_false_on_exception(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.is_system_manager", side_effect=Exception("db error")):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_reopen_closed_assignment"](aes) is False


# ---------------------------------------------------------------------------
# can_send_for_review
# ---------------------------------------------------------------------------

class TestCanSendForReview:
    def test_returns_true_when_service_returns_true(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_send_for_review", return_value=True):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_send_for_review"](aes) is True

    def test_returns_false_when_service_returns_false(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_send_for_review", return_value=False):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_send_for_review"](aes) is False

    def test_returns_false_on_exception(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_send_for_review", side_effect=Exception("boom")):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_send_for_review"](aes) is False


# ---------------------------------------------------------------------------
# can_return_for_revision
# ---------------------------------------------------------------------------

class TestCanReturnForRevision:
    def test_returns_true_when_service_returns_true(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_return_for_revision", return_value=True):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_return_for_revision"](aes) is True

    def test_returns_false_when_service_returns_false(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_return_for_revision", return_value=False):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_return_for_revision"](aes) is False

    def test_returns_false_on_exception(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_return_for_revision", side_effect=Exception("boom")):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_return_for_revision"](aes) is False


# ---------------------------------------------------------------------------
# can_submit_assignment
# ---------------------------------------------------------------------------

class TestCanSubmitAssignment:
    def test_returns_true_when_service_returns_true(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_submit_assignment", return_value=True):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_submit_assignment"](aes) is True

    def test_returns_false_when_service_returns_false(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_submit_assignment", return_value=False):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_submit_assignment"](aes) is False

    def test_returns_false_on_exception(self, app, test_user):
        aes = MagicMock()
        with patch(f"{_AUTH_SVC}.can_submit_assignment", side_effect=Exception("boom")):
            helpers = _get_helpers(app, test_user)
            assert helpers["can_submit_assignment"](aes) is False
