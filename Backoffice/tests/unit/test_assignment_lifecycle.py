"""Assignment close vs deactivate lifecycle."""
from datetime import timedelta

import pytest

from app import db
from app.models.assignments import AssignedForm, AssignmentEntityStatus
from app.utils.datetime_helpers import utcnow


class TestAssignmentEntryAllowed:
    def test_active_open_assignment_allows_entry(self):
        assignment = AssignedForm(is_active=True, is_closed=False)
        assert assignment.is_entry_allowed is True

    def test_inactive_assignment_blocks_entry(self):
        assignment = AssignedForm(is_active=False, is_closed=False)
        assert assignment.is_entry_allowed is False

    def test_closed_but_active_assignment_allows_entry(self):
        assignment = AssignedForm(is_active=True, is_closed=True)
        assert assignment.is_entry_allowed is True
        assert assignment.is_public_submission_allowed is False

    def test_expired_assignment_allows_entry_but_not_public_submission(self):
        assignment = AssignedForm(
            is_active=True,
            is_closed=False,
            expiry_date=utcnow().date() - timedelta(days=1),
        )
        assert assignment.is_entry_allowed is True
        assert assignment.is_public_submission_allowed is False


@pytest.mark.unit
class TestClosedAssignmentAuthorization:
    def _closed_aes(self, *, reopened_after_close=False, status="in_progress"):
        assignment = AssignedForm(is_active=True, is_closed=True)
        aes = AssignmentEntityStatus()
        aes.assigned_form = assignment
        aes.entity_type = "country"
        aes.entity_id = 1
        aes.assigned_form_id = 1
        aes.status = status
        aes.reopened_after_close = reopened_after_close
        return aes

    def test_focal_point_cannot_edit_closed_assignment(self, app):
        from unittest.mock import MagicMock, patch
        from app.services.organization.authorization_service import AuthorizationService

        user = MagicMock()
        user.is_authenticated = True
        aes = self._closed_aes()

        def _focal_point_perm(user, code, scope=None):
            return code == "assignment.enter"

        with app.app_context():
            with patch.object(AuthorizationService, "can_access_assignment", return_value=True), \
                 patch.object(AuthorizationService, "is_system_manager", return_value=False), \
                 patch.object(AuthorizationService, "has_rbac_permission", side_effect=_focal_point_perm):
                assert AuthorizationService.can_edit_assignment(aes, user) is False

    def test_assignment_admin_can_edit_closed_assignment(self, app):
        from unittest.mock import MagicMock, patch
        from app.services.organization.authorization_service import AuthorizationService

        user = MagicMock()
        user.is_authenticated = True
        aes = self._closed_aes()

        def _perm(user, code, scope=None):
            return code == "admin.assignments.edit"

        with app.app_context():
            with patch.object(AuthorizationService, "can_access_assignment", return_value=True), \
                 patch.object(AuthorizationService, "is_system_manager", return_value=False), \
                 patch.object(AuthorizationService, "has_rbac_permission", side_effect=_perm):
                assert AuthorizationService.can_edit_assignment(aes, user) is True

    def test_entity_reopen_allows_focal_point_edit_while_round_stays_closed(self, app):
        from unittest.mock import MagicMock, patch
        from app.services.organization.authorization_service import AuthorizationService

        user = MagicMock()
        user.is_authenticated = True
        aes = self._closed_aes(reopened_after_close=True)

        def _focal_point_perm(user, code, scope=None):
            return code == "assignment.enter"

        with app.app_context():
            with patch.object(AuthorizationService, "can_access_assignment", return_value=True), \
                 patch.object(AuthorizationService, "is_system_manager", return_value=False), \
                 patch.object(AuthorizationService, "has_rbac_permission", side_effect=_focal_point_perm):
                assert AuthorizationService.can_edit_assignment(aes, user) is True

    def test_can_reopen_closed_round_for_entity_only(self, app):
        from unittest.mock import MagicMock, patch
        from app.services.organization.authorization_service import AuthorizationService

        user = MagicMock()
        user.is_authenticated = True
        aes = self._closed_aes()

        with app.app_context():
            with patch.object(AuthorizationService, "can_access_assignment", return_value=True), \
                 patch.object(AuthorizationService, "is_system_manager", return_value=True):
                assert AuthorizationService.can_reopen_assignment(aes, user) is True

            reopened = self._closed_aes(reopened_after_close=True)
            with patch.object(AuthorizationService, "can_access_assignment", return_value=True), \
                 patch.object(AuthorizationService, "is_system_manager", return_value=True):
                assert AuthorizationService.can_reopen_assignment(reopened, user) is False


@pytest.mark.unit
class TestCloseAssignmentRoute:
    def test_close_does_not_deactivate(self, app, logged_in_client, db_session):
        from tests.factories import create_test_template

        template = create_test_template(db_session)
        assignment = AssignedForm(
            template_id=template.id,
            period_name="2024-close-test",
            is_active=True,
            is_closed=False,
        )
        db_session.add(assignment)
        db_session.commit()
        assignment_id = assignment.id

        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/close",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

        updated = db.session.get(AssignedForm, assignment_id)
        assert updated.is_closed is True
        assert updated.is_active is True


@pytest.mark.unit
class TestReopenClosedAssignmentRoute:
    def test_reopen_does_not_force_activate(self, app, logged_in_client, db_session):
        from tests.factories import create_test_template

        template = create_test_template(db_session)
        assignment = AssignedForm(
            template_id=template.id,
            period_name="2024-reopen-test",
            is_active=False,
            is_closed=True,
            expiry_date=utcnow().date() - timedelta(days=1),
        )
        db_session.add(assignment)
        db_session.commit()
        assignment_id = assignment.id

        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/reopen_closed",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

        updated = db.session.get(AssignedForm, assignment_id)
        assert updated.is_closed is False
        assert updated.expiry_date is None
        assert updated.is_active is False
