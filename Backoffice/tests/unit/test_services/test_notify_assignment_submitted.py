"""Tests for assignment submission team/admin notification routing."""

from unittest.mock import patch

import pytest

from app.services.notification.notifiers.assignment import notify_assignment_submitted


@pytest.fixture
def submitted_aes(db_session):
    from tests.factories import create_test_assignment_entity_status, create_test_user

    submitter = create_test_user(db_session, email="submitter@example.org", name="Submitter User")
    aes = create_test_assignment_entity_status(db_session, status="submitted")
    aes.submitted_by_user_id = submitter.id
    db_session.commit()
    aes._test_submitter = submitter
    return aes


class TestNotifyAssignmentSubmitted:
    def test_submitter_and_peers_get_different_in_app_notifications(self, app, submitted_aes):
        submitter_id = submitted_aes._test_submitter.id
        peer_ids = [501, 502]
        focal_ids = [submitter_id, *peer_ids]

        with app.app_context():
            with patch(
                "app.services.notification.notifiers.assignment.get_assignment_editor_submitter_user_ids_for_entity",
                return_value=focal_ids,
            ), patch(
                "app.services.notification.notifiers.assignment.audience_bucket_enabled",
                return_value=True,
            ), patch(
                "app.services.notification.notifiers.assignment.create_notification",
                return_value=[],
            ) as mock_create, patch(
                "app.services.notification.emails.send_assignment_submitted_team_email",
            ) as mock_team_email, patch(
                "app.services.notification.notifiers.assignment.resolve_submission_review_recipient_user_ids",
                return_value=[],
            ), patch(
                "app.services.notification.notifiers.assignment.log_entity_activity",
            ), patch(
                "app.services.notification.notifiers.assignment.url_for",
                return_value="/forms/assignment/1",
            ):
                notify_assignment_submitted(submitted_aes)

                assert mock_create.call_count == 2
                submitter_call = mock_create.call_args_list[0].kwargs
                peer_call = mock_create.call_args_list[1].kwargs

                assert submitter_call["user_ids"] == [submitter_id]
                assert submitter_call["message_key"] == "notification.assignment_submitted.submitter.message"
                assert submitter_call["send_email_notifications"] is False

                assert peer_call["user_ids"] == peer_ids
                assert peer_call["message_key"] == "notification.assignment_submitted.message"
                assert peer_call["send_email_notifications"] is False

                mock_team_email.assert_called_once()
                assert mock_team_email.call_args.kwargs["user_ids"] == focal_ids

    def test_sends_one_team_email_to_all_focal_points(self, app, submitted_aes):
        focal_ids = [submitted_aes._test_submitter.id, 501]

        with app.app_context():
            with patch(
                "app.services.notification.notifiers.assignment.get_assignment_editor_submitter_user_ids_for_entity",
                return_value=focal_ids,
            ), patch(
                "app.services.notification.notifiers.assignment.audience_bucket_enabled",
                return_value=True,
            ), patch(
                "app.services.notification.notifiers.assignment.create_notification",
                return_value=[],
            ), patch(
                "app.services.notification.emails.send_assignment_submitted_team_email",
            ) as mock_team_email, patch(
                "app.services.notification.notifiers.assignment.resolve_submission_review_recipient_user_ids",
                return_value=[],
            ), patch(
                "app.services.notification.notifiers.assignment.log_entity_activity",
            ), patch(
                "app.services.notification.notifiers.assignment.url_for",
                return_value="/forms/assignment/1",
            ):
                notify_assignment_submitted(submitted_aes)

                mock_team_email.assert_called_once()
                assert mock_team_email.call_args.kwargs["submitter_name"] == "Submitter User"
                assert "assignment_title" in mock_team_email.call_args.kwargs

    def test_excludes_submitter_from_admin_review_channel(self, app, submitted_aes):
        submitter_id = submitted_aes._test_submitter.id
        reviewer_id = 777

        with app.app_context():
            with patch(
                "app.services.notification.notifiers.assignment.get_assignment_editor_submitter_user_ids_for_entity",
                return_value=[],
            ), patch(
                "app.services.notification.notifiers.assignment.audience_bucket_enabled",
                return_value=True,
            ), patch(
                "app.services.notification.notifiers.assignment.resolve_submission_review_recipient_user_ids",
                return_value=[reviewer_id],
            ) as mock_resolve, patch(
                "app.services.notification.notifiers.assignment.create_notification",
                return_value=[],
            ) as mock_admin, patch(
                "app.services.notification.notifiers.assignment.log_entity_activity",
            ), patch(
                "app.services.notification.notifiers.assignment.url_for",
                return_value="/forms/assignment/1",
            ):
                notify_assignment_submitted(submitted_aes)

                mock_resolve.assert_called_once()
                assert mock_resolve.call_args.kwargs["exclude_user_ids"] == [submitter_id]
                mock_admin.assert_called_once()
                assert mock_admin.call_args.kwargs["user_ids"] == [reviewer_id]

    def test_notification_copy(self, app):
        from app.services.notification.core import translate_notification_message

        with app.app_context():
            submitter_message = translate_notification_message(
                "notification.assignment_submitted.submitter.message",
                {"assignment_title": "Annual Report \u2013 Jan-Jun 2026"},
            )
            peer_message = translate_notification_message(
                "notification.assignment_submitted.message",
                {"assignment_title": "Annual Report \u2013 Jan-Jun 2026"},
            )
            team_email = translate_notification_message(
                "notification.assignment_submitted.team_email.message",
                {
                    "assignment_title": "Annual Report \u2013 Jan-Jun 2026",
                    "submitter_name": "Sabrina Raff",
                },
            )

        assert "You submitted" in submitter_message
        assert "successfully" in submitter_message.lower()
        assert "another focal point" in peer_message.lower()
        assert "Sabrina Raff" in team_email
