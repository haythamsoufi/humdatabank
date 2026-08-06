"""Tests for assignment-created notification routing."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.notification.notifiers.assignment import notify_assignment_created


@pytest.fixture
def pending_aes(db_session):
    from tests.factories import create_test_assignment_entity_status

    aes = create_test_assignment_entity_status(db_session, status="pending")
    db_session.commit()
    return aes


class TestNotifyAssignmentCreated:
    def test_suppresses_loadtest_assignments(self, app, pending_aes):
        pending_aes.assigned_form.period_name = "[LOADTEST] smoke"

        with app.app_context():
            with patch(
                "app.services.notification.notifiers.assignment.notify_entity_focal_points",
            ) as mock_focal, patch(
                "app.services.notification.notifiers.assignment.log_entity_activity",
            ):
                result = notify_assignment_created(pending_aes)

        assert result == []
        mock_focal.assert_not_called()

    def test_notifies_focal_points(self, app, pending_aes):
        with app.app_context():
            with patch(
                "app.services.notification.notifiers.assignment.notify_entity_focal_points",
                return_value=["focal-notification"],
            ) as mock_focal, patch(
                "app.services.notification.notifiers.assignment.collect_entity_admin_audience_recipient_ids",
                return_value=[],
            ), patch(
                "app.services.notification.notifiers.assignment.log_entity_activity",
            ), patch(
                "app.services.notification.notifiers.assignment.url_for",
                return_value="/forms/assignment/1",
            ):
                result = notify_assignment_created(pending_aes)

        mock_focal.assert_called_once()
        assert mock_focal.call_args.kwargs["notification_type"].value == "assignment_created"
        assert result == ["focal-notification"]

    def test_notifies_admin_only_recipients_not_already_focal(self, app, pending_aes):
        focal_id = 101
        admin_only_id = 202

        with app.app_context():
            with patch(
                "app.services.notification.notifiers.assignment.notify_entity_focal_points",
                return_value=[],
            ), patch(
                "app.services.notification.notifiers.assignment.collect_entity_admin_audience_recipient_ids",
                return_value=[focal_id, admin_only_id],
            ), patch(
                "app.services.notification.notifiers.assignment.get_assignment_editor_submitter_user_ids_for_entity",
                return_value=[focal_id],
            ), patch(
                "app.services.notification.notifiers.assignment.create_notification",
                return_value=["admin-notification"],
            ) as mock_create, patch(
                "app.services.notification.notifiers.assignment.log_entity_activity",
            ), patch(
                "app.services.notification.notifiers.assignment.url_for",
                return_value="/forms/assignment/1",
            ):
                result = notify_assignment_created(pending_aes)

        mock_create.assert_called_once()
        assert mock_create.call_args.kwargs["user_ids"] == [admin_only_id]
        assert result == ["admin-notification"]

    def test_excludes_assignment_creator(self, app, pending_aes):
        creator_id = 999
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = creator_id

        with app.app_context():
            with patch(
                "app.services.notification.notifiers.assignment.current_user",
                mock_user,
            ), patch(
                "app.services.notification.notifiers.assignment.notify_entity_focal_points",
                return_value=[],
            ) as mock_focal, patch(
                "app.services.notification.notifiers.assignment.collect_entity_admin_audience_recipient_ids",
                return_value=[],
            ) as mock_admin, patch(
                "app.services.notification.notifiers.assignment.log_entity_activity",
            ), patch(
                "app.services.notification.notifiers.assignment.url_for",
                return_value="/forms/assignment/1",
            ):
                notify_assignment_created(pending_aes)

        assert mock_focal.call_args.kwargs["exclude_user_ids"] == [creator_id]
        assert mock_admin.call_args.kwargs["exclude_user_ids"] == [creator_id]
