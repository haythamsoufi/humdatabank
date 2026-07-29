"""
Advanced coverage tests for AuthorizationService.

Targets branches not yet exercised by:
  - test_authorization_service.py
  - test_authorization_service_internals.py
  - test_authorization_service_scoped.py
"""
import pytest
from unittest.mock import MagicMock, patch

from app.models.enums import AssignmentEntityStatusValue
from app.services.organization.authorization_service import AuthorizationService, _rbac_cache_set
from tests.factories import (
    create_test_admin,
    create_test_assignment_entity_status,
    create_test_user,
    create_focal_point_with_country,
    _grant_role_permission,
    _ensure_permission,
)

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_aes(
    *,
    status=AssignmentEntityStatusValue.in_progress.value,
    entity_type="country",
    entity_id=1,
    assigned_form_id=10,
    template_id=5,
    requires_delegation_review=False,
    is_effectively_closed=False,
    period_name="2024",
):
    """Build a lightweight mock AssignmentEntityStatus."""
    af = MagicMock()
    af.template_id = template_id
    af.requires_delegation_review = requires_delegation_review
    af.is_effectively_closed = is_effectively_closed
    af.period_name = period_name

    aes = MagicMock()
    aes.status = status
    aes.entity_type = entity_type
    aes.entity_id = entity_id
    aes.assigned_form_id = assigned_form_id
    aes.assigned_form = af
    aes.reopened_after_close = False
    return aes


# ---------------------------------------------------------------------------
# _rbac_cache_set error handling
# ---------------------------------------------------------------------------

class TestRbacCacheSetError:
    def test_cache_set_swallows_exception(self, app):
        """_rbac_cache_set should not raise when g.attr assignment fails."""
        with app.test_request_context():
            class _FrozenG:
                def __setattr__(self, name, value):
                    raise AttributeError("frozen")

            bad_g = _FrozenG()
            _rbac_cache_set(bad_g, "_test_cache", "k", "v")


# ---------------------------------------------------------------------------
# _has_any_admin_permission — scoped grants branch
# ---------------------------------------------------------------------------

class TestHasAnyAdminPermissionScopedGrants:
    def test_admin_via_scoped_grant(self, db_session, app):
        """A user with a global allow grant for an admin.* permission is admin."""
        from app.models.rbac import RbacAccessGrant
        from tests.factories import _ensure_permission

        with app.app_context():
            user = create_test_user(db_session)
            pid = _ensure_permission(db_session, "admin.users.view")
            db_session.add(
                RbacAccessGrant(
                    principal_type="user",
                    principal_id=user.id,
                    permission_id=pid,
                    scope_kind="global",
                    effect="allow",
                )
            )
            db_session.commit()
            db_session.refresh(user)
            assert AuthorizationService._has_any_admin_permission(user) is True

    def test_entity_scoped_admin_grant_does_not_make_admin(self, db_session, app):
        """A *scoped* (non-global) admin grant should NOT make is_admin() True."""
        from app.models.rbac import RbacAccessGrant
        from tests.factories import _ensure_permission

        with app.app_context():
            user = create_test_user(db_session)
            pid = _ensure_permission(db_session, "admin.entity.special")
            db_session.add(
                RbacAccessGrant(
                    principal_type="user",
                    principal_id=user.id,
                    permission_id=pid,
                    scope_kind="entity",
                    effect="allow",
                    entity_type="country",
                    entity_id=1,
                )
            )
            db_session.commit()
            db_session.refresh(user)
            # entity-scoped grant should not elevate to admin
            assert AuthorizationService._has_any_admin_permission(user) is False


# ---------------------------------------------------------------------------
# rbac_active_for_user — rbac disabled path
# ---------------------------------------------------------------------------

class TestRbacActiveForUser:
    def test_rbac_not_active_when_rbac_disabled(self, db_session, app):
        """When rbac_enabled() is False, rbac_active_for_user returns False."""
        with app.app_context():
            user = create_test_user(db_session)
            with patch.object(AuthorizationService, "rbac_enabled", return_value=False):
                result = AuthorizationService.rbac_active_for_user(user)
            assert result is False

    def test_rbac_active_for_system_manager_always(self, db_session, app):
        """System manager is always active even if rbac_enabled is False."""
        with app.app_context():
            sm = create_test_user(db_session, role="system_manager")
            with patch.object(AuthorizationService, "rbac_enabled", return_value=False):
                result = AuthorizationService.rbac_active_for_user(sm)
            assert result is True


# ---------------------------------------------------------------------------
# get_scoped_grant_decision — edge cases
# ---------------------------------------------------------------------------

class TestGetScopedGrantDecision:
    def test_unauthenticated_user_returns_none(self):
        user = MagicMock()
        user.is_authenticated = False
        result = AuthorizationService.get_scoped_grant_decision(user, "assignment.view")
        assert result is None

    def test_system_manager_returns_global_allow(self, db_session, app):
        with app.app_context():
            sm = create_test_user(db_session, role="system_manager")
            result = AuthorizationService.get_scoped_grant_decision(sm, "anything.permission")
        assert result == {"effect": "allow", "scope_kind": "global"}

    def test_empty_permission_code_returns_none(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            assert AuthorizationService.get_scoped_grant_decision(user, "") is None
            assert AuthorizationService.get_scoped_grant_decision(user, "   ") is None

    def test_unknown_permission_returns_none(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            assert AuthorizationService.get_scoped_grant_decision(user, "totally.unknown.xyz.abc") is None

    def test_template_scoped_grant(self, db_session, app):
        from app.models.rbac import RbacAccessGrant
        from tests.factories import _ensure_permission, create_test_template

        with app.app_context():
            user = create_test_user(db_session)
            template = create_test_template(db_session)
            pid = _ensure_permission(db_session, "assignment.template_edit")
            db_session.add(
                RbacAccessGrant(
                    principal_type="user",
                    principal_id=user.id,
                    permission_id=pid,
                    scope_kind="template",
                    effect="allow",
                    template_id=template.id,
                )
            )
            db_session.commit()
            scope = {"template_id": template.id}
            decision = AuthorizationService.get_scoped_grant_decision(
                user, "assignment.template_edit", scope=scope
            )
            assert decision is not None
            assert decision["effect"] == "allow"
            assert decision["scope_kind"] == "template"

    def test_assignment_scoped_grant(self, db_session, app):
        from app.models.rbac import RbacAccessGrant
        from tests.factories import _ensure_permission, create_test_assignment_entity_status

        with app.app_context():
            user = create_test_user(db_session)
            aes = create_test_assignment_entity_status(db_session)
            pid = _ensure_permission(db_session, "assignment.form_view")
            db_session.add(
                RbacAccessGrant(
                    principal_type="user",
                    principal_id=user.id,
                    permission_id=pid,
                    scope_kind="assignment",
                    effect="allow",
                    assigned_form_id=aes.assigned_form_id,
                )
            )
            db_session.commit()
            scope = {"assigned_form_id": aes.assigned_form_id}
            decision = AuthorizationService.get_scoped_grant_decision(
                user, "assignment.form_view", scope=scope
            )
            assert decision is not None
            assert decision["scope_kind"] == "assignment"


# ---------------------------------------------------------------------------
# get_scoped_grant_effect — backward-compat wrapper
# ---------------------------------------------------------------------------

class TestGetScopedGrantEffect:
    def test_returns_effect_string(self, db_session, app):
        with app.app_context():
            sm = create_test_user(db_session, role="system_manager")
            effect = AuthorizationService.get_scoped_grant_effect(sm, "any.perm")
        assert effect == "allow"

    def test_returns_none_when_no_grant(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            effect = AuthorizationService.get_scoped_grant_effect(user, "totally.unknown.perm2")
        assert effect is None


# ---------------------------------------------------------------------------
# _assignment_is_effectively_closed — remaining branches
# ---------------------------------------------------------------------------

class TestAssignmentIsEffectivelyClosed:
    def test_reopened_after_close_is_not_closed(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.is_closed = True
            aes.reopened_after_close = True
            # Patch is_round_closed_for_entity to raise so we hit the fallback
            with patch.object(type(aes), "is_round_closed_for_entity", side_effect=Exception("no round")):
                result = AuthorizationService._assignment_is_effectively_closed(aes)
            # reopened_after_close=True means not effectively closed
            assert result is False

    def test_returns_false_when_no_assigned_form(self, app):
        aes = MagicMock()
        aes.reopened_after_close = False
        aes.assigned_form = None
        aes.is_round_closed_for_entity = MagicMock(side_effect=Exception("no round"))
        result = AuthorizationService._assignment_is_effectively_closed(aes)
        assert result is False

    def test_returns_true_when_round_closed_bool(self, db_session, app):
        """is_round_closed_for_entity() returning True bool → effectively closed."""
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            with patch.object(type(aes), "is_round_closed_for_entity", return_value=True):
                result = AuthorizationService._assignment_is_effectively_closed(aes)
        assert result is True

    def test_returns_false_when_round_closed_false_bool(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            with patch.object(type(aes), "is_round_closed_for_entity", return_value=False):
                result = AuthorizationService._assignment_is_effectively_closed(aes)
        assert result is False


# ---------------------------------------------------------------------------
# _assignment_needs_reopen — remaining status values
# ---------------------------------------------------------------------------

class TestAssignmentNeedsReopen:
    def test_approved_status_needs_reopen(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status="approved")
            assert AuthorizationService._assignment_needs_reopen(aes) is True

    def test_requires_revision_needs_reopen(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status="requires_revision")
            assert AuthorizationService._assignment_needs_reopen(aes) is True

    def test_sent_for_review_needs_reopen(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
            assert AuthorizationService._assignment_needs_reopen(aes) is True

    def test_in_progress_no_reopen_needed(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status="in_progress")
            # in_progress is not locked and not closed
            result = AuthorizationService._assignment_needs_reopen(aes)
            assert result is False

    def test_effectively_closed_needs_reopen_unless_reopened(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status="in_progress")
            aes.reopened_after_close = False
            with patch.object(type(aes), "is_round_closed_for_entity", return_value=True):
                result = AuthorizationService._assignment_needs_reopen(aes)
        assert result is True

    def test_effectively_closed_but_already_reopened_no_reopen(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status="in_progress")
            aes.reopened_after_close = True
            with patch.object(type(aes), "is_round_closed_for_entity", return_value=True):
                result = AuthorizationService._assignment_needs_reopen(aes)
        assert result is False


# ---------------------------------------------------------------------------
# can_edit_assignment — status-locked paths
# ---------------------------------------------------------------------------

class TestCanEditAssignment:
    def test_submitted_status_is_locked(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.enter")
            aes.status = AssignmentEntityStatusValue.submitted.value
            db_session.commit()
            result = AuthorizationService.can_edit_assignment(aes, user)
        assert result is False

    def test_approved_status_is_locked(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.enter")
            aes.status = AssignmentEntityStatusValue.approved.value
            db_session.commit()
            result = AuthorizationService.can_edit_assignment(aes, user)
        assert result is False

    def test_cancelled_status_is_locked(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.enter")
            aes.status = AssignmentEntityStatusValue.cancelled.value
            db_session.commit()
            result = AuthorizationService.can_edit_assignment(aes, user)
        assert result is False

    def test_sent_for_review_delegation_user_can_edit(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.enter")
            aes.assigned_form.requires_delegation_review = True
            aes.status = AssignmentEntityStatusValue.sent_for_review.value
            db_session.commit()
            with patch("app.services.organization.authorization_service.is_delegation_user", return_value=True):
                with patch("app.services.organization.authorization_service.review_enabled", return_value=True):
                    result = AuthorizationService.can_edit_assignment(aes, user)
        assert result is True

    def test_sent_for_review_non_delegation_cannot_edit(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.enter")
            aes.assigned_form.requires_delegation_review = True
            aes.status = AssignmentEntityStatusValue.sent_for_review.value
            db_session.commit()
            with patch("app.services.organization.authorization_service.is_delegation_user", return_value=False):
                with patch("app.services.organization.authorization_service.review_enabled", return_value=True):
                    result = AuthorizationService.can_edit_assignment(aes, user)
        assert result is False

    def test_scope_build_exception_fallback(self, db_session, app):
        """Exception during scope build should still complete via fallback scope."""
        from unittest.mock import PropertyMock
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.enter")
            with patch.object(
                type(aes.assigned_form),
                "template_id",
                new_callable=PropertyMock,
                side_effect=AttributeError("no template_id"),
            ):
                aes.assigned_form.requires_delegation_review = False
                db_session.commit()
                result = AuthorizationService.can_edit_assignment(aes, user)
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# can_submit_assignment — remaining branches
# ---------------------------------------------------------------------------

class TestCanSubmitAssignment:
    def test_approved_status_cannot_submit(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.submit")
            aes.status = AssignmentEntityStatusValue.approved.value
            db_session.commit()
            result = AuthorizationService.can_submit_assignment(aes, user)
        assert result is False

    def test_sent_for_review_delegation_user_can_submit(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.submit")
            aes.assigned_form.requires_delegation_review = True
            aes.status = AssignmentEntityStatusValue.sent_for_review.value
            db_session.commit()
            with patch("app.services.organization.authorization_service.is_delegation_user", return_value=True):
                with patch("app.services.organization.authorization_service.review_enabled", return_value=True):
                    result = AuthorizationService.can_submit_assignment(aes, user)
        assert result is True

    def test_review_enabled_non_delegation_in_source_status_cannot_submit(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.submit")
            aes.assigned_form.requires_delegation_review = True
            aes.status = AssignmentEntityStatusValue.in_progress.value
            db_session.commit()
            with patch("app.services.organization.authorization_service.is_delegation_user", return_value=False):
                with patch("app.services.organization.authorization_service.review_enabled", return_value=True):
                    from app.services.assignments.workflow_service import delegation_review_source_statuses
                    with patch("app.services.organization.authorization_service.delegation_review_source_statuses", return_value=delegation_review_source_statuses()):
                        result = AuthorizationService.can_submit_assignment(aes, user)
        assert result is False

    def test_closed_assignment_cannot_submit(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            aes.assigned_form.is_closed = True
            db_session.commit()
            with patch.object(type(aes), "is_round_closed_for_entity", return_value=True):
                result = AuthorizationService.can_submit_assignment(aes, user)
        assert result is False

    def test_no_access_cannot_submit(self, db_session, app):
        with app.app_context():
            focal = create_test_user(db_session, role="focal_point")
            aes = create_test_assignment_entity_status(db_session)
            result = AuthorizationService.can_submit_assignment(aes, focal)
        assert result is False


# ---------------------------------------------------------------------------
# can_send_for_review — all branches
# ---------------------------------------------------------------------------

class TestCanSendForReview:
    def test_review_not_enabled_returns_false(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            aes.assigned_form.requires_delegation_review = False
            db_session.commit()
            result = AuthorizationService.can_send_for_review(aes, user)
        assert result is False

    def test_delegation_user_cannot_send_for_review(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            aes.assigned_form.requires_delegation_review = True
            db_session.commit()
            with patch("app.services.organization.authorization_service.is_delegation_user", return_value=True):
                with patch("app.services.organization.authorization_service.review_enabled", return_value=True):
                    result = AuthorizationService.can_send_for_review(aes, user)
        assert result is False

    def test_system_manager_can_send_for_review(self, db_session, app):
        with app.app_context():
            sm = create_test_user(db_session, role="system_manager")
            aes = create_test_assignment_entity_status(db_session, status="in_progress")
            aes.assigned_form.requires_delegation_review = True
            db_session.commit()
            with patch("app.services.organization.authorization_service.is_delegation_user", return_value=False):
                with patch("app.services.organization.authorization_service.review_enabled", return_value=True):
                    result = AuthorizationService.can_send_for_review(aes, sm)
        assert result is True

    def test_wrong_status_cannot_send_for_review(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.submit")
            aes.assigned_form.requires_delegation_review = True
            aes.status = AssignmentEntityStatusValue.submitted.value
            db_session.commit()
            with patch("app.services.organization.authorization_service.is_delegation_user", return_value=False):
                with patch("app.services.organization.authorization_service.review_enabled", return_value=True):
                    result = AuthorizationService.can_send_for_review(aes, user)
        assert result is False

    def test_no_access_cannot_send_for_review(self, db_session, app):
        with app.app_context():
            focal = create_test_user(db_session, role="focal_point")
            aes = create_test_assignment_entity_status(db_session)
            result = AuthorizationService.can_send_for_review(aes, focal)
        assert result is False

    def test_closed_assignment_cannot_send_for_review(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            aes.assigned_form.is_closed = True
            db_session.commit()
            with patch.object(type(aes), "is_round_closed_for_entity", return_value=True):
                result = AuthorizationService.can_send_for_review(aes, user)
        assert result is False


# ---------------------------------------------------------------------------
# can_return_for_revision — all branches
# ---------------------------------------------------------------------------

class TestCanReturnForRevision:
    def test_wrong_status_returns_false(self, db_session, app):
        with app.app_context():
            sm = create_test_user(db_session, role="system_manager")
            aes = create_test_assignment_entity_status(db_session, status="in_progress")
            result = AuthorizationService.can_return_for_revision(aes, sm)
        assert result is False

    def test_system_manager_can_return_for_revision(self, db_session, app):
        with app.app_context():
            sm = create_test_user(db_session, role="system_manager")
            aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
            result = AuthorizationService.can_return_for_revision(aes, sm)
        assert result is True

    def test_review_not_enabled_returns_false(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            aes.status = AssignmentEntityStatusValue.sent_for_review.value
            aes.assigned_form.requires_delegation_review = False
            db_session.commit()
            with patch("app.services.organization.authorization_service.review_enabled", return_value=False):
                result = AuthorizationService.can_return_for_revision(aes, user)
        assert result is False

    def test_not_delegation_user_returns_false(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            aes.status = AssignmentEntityStatusValue.sent_for_review.value
            aes.assigned_form.requires_delegation_review = True
            db_session.commit()
            with patch("app.services.organization.authorization_service.review_enabled", return_value=True):
                with patch("app.services.organization.authorization_service.is_delegation_user", return_value=False):
                    result = AuthorizationService.can_return_for_revision(aes, user)
        assert result is False

    def test_delegation_user_with_rbac_can_return(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.submit")
            aes.status = AssignmentEntityStatusValue.sent_for_review.value
            aes.assigned_form.requires_delegation_review = True
            db_session.commit()
            with patch("app.services.organization.authorization_service.review_enabled", return_value=True):
                with patch("app.services.organization.authorization_service.is_delegation_user", return_value=True):
                    result = AuthorizationService.can_return_for_revision(aes, user)
        assert result is True

    def test_no_access_cannot_return_for_revision(self, db_session, app):
        with app.app_context():
            focal = create_test_user(db_session, role="focal_point")
            aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
            result = AuthorizationService.can_return_for_revision(aes, focal)
        assert result is False


# ---------------------------------------------------------------------------
# can_reopen_assignment — remaining branches
# ---------------------------------------------------------------------------

class TestCanReopenAssignment:
    def test_does_not_need_reopen_returns_false(self, db_session, app):
        with app.app_context():
            sm = create_test_user(db_session, role="system_manager")
            aes = create_test_assignment_entity_status(db_session, status="in_progress")
            result = AuthorizationService.can_reopen_assignment(aes, sm)
        assert result is False

    def test_no_access_cannot_reopen(self, db_session, app):
        with app.app_context():
            focal = create_test_user(db_session, role="focal_point")
            aes = create_test_assignment_entity_status(db_session, status="submitted")
            result = AuthorizationService.can_reopen_assignment(aes, focal)
        assert result is False

    def test_focal_with_reopen_rbac_can_reopen(self, db_session, app):
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.reopen")
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.view")
            aes.status = AssignmentEntityStatusValue.submitted.value
            db_session.commit()
            result = AuthorizationService.can_reopen_assignment(aes, user)
        assert result is True


# ---------------------------------------------------------------------------
# check_self_report_access — remaining branches
# ---------------------------------------------------------------------------

class TestCheckSelfReportAccess:
    def test_unauthenticated_returns_false(self, app):
        anon = MagicMock()
        anon.is_authenticated = False
        aes = _mock_aes()
        with app.app_context():
            result = AuthorizationService.check_self_report_access(aes, anon)
        assert result is False

    def test_system_manager_can_access_self_report(self, db_session, app):
        from app.utils.constants import SELF_REPORT_PERIOD_NAME
        with app.app_context():
            sm = create_test_user(db_session, role="system_manager")
            aes = create_test_assignment_entity_status(
                db_session, period_name=SELF_REPORT_PERIOD_NAME
            )
            result = AuthorizationService.check_self_report_access(aes, sm)
        assert result is True

    def test_non_country_entity_returns_false(self, db_session, app):
        from app.utils.constants import SELF_REPORT_PERIOD_NAME
        with app.app_context():
            user, country, _ = create_focal_point_with_country(db_session)
            aes = create_test_assignment_entity_status(
                db_session, period_name=SELF_REPORT_PERIOD_NAME
            )
            # Make entity_type not a country
            aes.entity_type = "ns_branch"
            db_session.commit()
            result = AuthorizationService.check_self_report_access(aes, user)
        assert result is False

    def test_no_country_access_returns_false(self, db_session, app):
        from app.utils.constants import SELF_REPORT_PERIOD_NAME
        with app.app_context():
            focal = create_test_user(db_session, role="focal_point")
            aes = create_test_assignment_entity_status(
                db_session, period_name=SELF_REPORT_PERIOD_NAME
            )
            # focal has no entity permissions for that country
            result = AuthorizationService.check_self_report_access(aes, focal)
        assert result is False


# ---------------------------------------------------------------------------
# check_template_access — system_manager via current_user path
# ---------------------------------------------------------------------------

class TestCheckTemplateAccessSystemManager:
    def test_system_manager_matching_current_user(self, db_session, app):
        from tests.factories import create_test_template

        with app.app_context():
            sm = create_test_user(db_session, role="system_manager")
            template = create_test_template(db_session)

            with app.test_request_context():
                from flask_login import login_user
                from app.models import User

                login_user(User.query.get(sm.id))
                result = AuthorizationService.check_template_access(template.id, sm.id)
            assert result is True

    def test_system_manager_via_db_query(self, db_session, app):
        """When current_user doesn't match, fall back to querying the user by ID."""
        from tests.factories import create_test_template

        with app.app_context():
            sm = create_test_user(db_session, role="system_manager")
            other_user = create_test_user(db_session)
            template = create_test_template(db_session)

            with app.test_request_context():
                from flask_login import login_user
                from app.models import User

                # Log in as other_user so current_user.id != sm.id
                login_user(User.query.get(other_user.id))
                result = AuthorizationService.check_template_access(template.id, sm.id)
            assert result is True


# ---------------------------------------------------------------------------
# has_rbac_permission — unknown permission with DEBUG=True
# ---------------------------------------------------------------------------

class TestHasRbacPermissionDebugPath:
    def test_unknown_permission_logs_warning_in_debug_mode(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            original_debug = app.config.get("DEBUG")
            try:
                app.config["DEBUG"] = True
                with app.test_request_context():
                    result = AuthorizationService.has_rbac_permission(
                        user, "debug.only.unknown.permission.xyz"
                    )
            finally:
                app.config["DEBUG"] = original_debug
        assert result is False


# ---------------------------------------------------------------------------
# can_access_assignment — scope build exception fallback
# ---------------------------------------------------------------------------

class TestCanAccessAssignmentScopeException:
    def test_scope_build_exception_still_evaluates(self, db_session, app):
        from unittest.mock import PropertyMock
        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.view")
            with patch.object(
                type(aes.assigned_form),
                "template_id",
                new_callable=PropertyMock,
                side_effect=AttributeError("no tmpl"),
            ):
                db_session.commit()
                result = AuthorizationService.can_access_assignment(aes, user)
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# can_access_assignment — scoped grant pathways
# ---------------------------------------------------------------------------

class TestCanAccessAssignmentScopedGrant:
    def test_entity_scoped_allow_grant_gives_access(self, db_session, app):
        from app.models.rbac import RbacAccessGrant

        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            pid = _ensure_permission(db_session, "assignment.view")
            db_session.add(
                RbacAccessGrant(
                    principal_type="user",
                    principal_id=user.id,
                    permission_id=pid,
                    scope_kind="entity",
                    effect="allow",
                    entity_type="country",
                    entity_id=country.id,
                )
            )
            db_session.commit()
            result = AuthorizationService.can_access_assignment(aes, user)
        assert result is True

    def test_deny_grant_blocks_access(self, db_session, app):
        from app.models.rbac import RbacAccessGrant

        with app.app_context():
            user, country, aes = create_focal_point_with_country(db_session)
            pid = _ensure_permission(db_session, "assignment.view")
            db_session.add(
                RbacAccessGrant(
                    principal_type="user",
                    principal_id=user.id,
                    permission_id=pid,
                    scope_kind="entity",
                    effect="deny",
                    entity_type="country",
                    entity_id=country.id,
                )
            )
            db_session.commit()
            result = AuthorizationService.can_access_assignment(aes, user)
        assert result is False
