"""Assignment-approved notifications copy the country's FDS admin."""

from unittest.mock import patch

import pytest

from app.services.notification.notifiers.assignment import (
    _resolve_country_fds_admin_user_id,
    notify_assignment_approved,
)


@pytest.fixture
def pending_aes(db_session):
    from tests.factories import create_test_assignment_entity_status

    aes = create_test_assignment_entity_status(db_session, status="submitted")
    db_session.commit()
    return aes


def _patches(*, focal_ids, fds_admin_id, focal_notifications=None, fds_notifications=None):
    """Patches around notify_assignment_approved. Yields (focal, create, send_email)."""
    return [
        patch(
            "app.services.notification.notifiers.assignment.audience_bucket_enabled",
            return_value=True,
        ),
        patch(
            "app.services.notification.notifiers.assignment.get_assignment_editor_submitter_user_ids_for_entity",
            return_value=list(focal_ids),
        ),
        patch(
            "app.services.notification.notifiers.assignment._resolve_country_fds_admin_user_id",
            return_value=fds_admin_id,
        ),
        patch(
            "app.services.notification.notifiers.assignment.notify_entity_focal_points",
            return_value=list(focal_notifications or []),
        ),
        patch(
            "app.services.notification.notifiers.assignment.create_notification",
            return_value=list(fds_notifications or []),
        ),
        patch(
            "app.services.notification.notifiers.assignment._send_grouped_assignment_email",
        ),
        patch(
            "app.services.notification.notifiers.assignment._assignment_approved_snapshot_attachments",
            return_value=[("form.pdf", b"%PDF", "application/pdf")],
        ),
        patch(
            "app.services.notification.notifiers.assignment.log_entity_activity",
        ),
        patch(
            "app.services.notification.notifiers.assignment.url_for",
            return_value="/assignment/1",
        ),
    ]


class TestNotifyAssignmentApproved:
    def test_without_fds_admin_keeps_individual_focal_emails(self, app, pending_aes):
        managers = _patches(focal_ids=[11], fds_admin_id=None, focal_notifications=["focal"])
        with app.app_context():
            started = [p.start() for p in managers]
            try:
                focal = started[3]
                create = started[4]
                send_email = started[5]
                result = notify_assignment_approved(pending_aes)
            finally:
                for p in managers:
                    p.stop()

        focal.assert_called_once()
        assert "send_email_notifications" not in focal.call_args.kwargs
        create.assert_not_called()
        send_email.assert_not_called()
        assert result == ["focal"]

    def test_copies_fds_admin_on_one_shared_email(self, app, pending_aes):
        managers = _patches(
            focal_ids=[11],
            fds_admin_id=22,
            focal_notifications=["focal"],
            fds_notifications=["fds"],
        )
        with app.app_context():
            started = [p.start() for p in managers]
            try:
                focal = started[3]
                create = started[4]
                send_email = started[5]
                result = notify_assignment_approved(pending_aes)
            finally:
                for p in managers:
                    p.stop()

        assert focal.call_args.kwargs["send_email_notifications"] is False
        create.assert_called_once()
        assert create.call_args.kwargs["user_ids"] == [22]
        assert create.call_args.kwargs["send_email_notifications"] is False
        assert create.call_args.kwargs["notification_type"].value == "assignment_approved"
        send_email.assert_called_once()
        assert send_email.call_args.kwargs["focal_user_ids"] == [11]
        assert send_email.call_args.kwargs["admin_user_ids"] == [22]
        assert send_email.call_args.kwargs["attachments"] == [
            ("form.pdf", b"%PDF", "application/pdf")
        ]
        assert send_email.call_args.kwargs["sample_notification"].notification_type.value == (
            "assignment_approved"
        )
        assert result == ["focal", "fds"]

    def test_fds_admin_who_is_already_a_focal_is_not_copied_again(self, app, pending_aes):
        managers = _patches(focal_ids=[22], fds_admin_id=22, focal_notifications=["focal"])
        with app.app_context():
            started = [p.start() for p in managers]
            try:
                focal = started[3]
                create = started[4]
                send_email = started[5]
                notify_assignment_approved(pending_aes)
            finally:
                for p in managers:
                    p.stop()

        assert "send_email_notifications" not in focal.call_args.kwargs
        create.assert_not_called()
        send_email.assert_not_called()

    def test_fds_admin_is_still_notified_when_there_are_no_focal_points(self, app, pending_aes):
        managers = _patches(focal_ids=[], fds_admin_id=22, fds_notifications=["fds"])
        with app.app_context():
            started = [p.start() for p in managers]
            try:
                focal = started[3]
                create = started[4]
                send_email = started[5]
                result = notify_assignment_approved(pending_aes)
            finally:
                for p in managers:
                    p.stop()

        focal.assert_not_called()
        assert create.call_args.kwargs["user_ids"] == [22]
        assert send_email.call_args.kwargs["focal_user_ids"] == []
        assert send_email.call_args.kwargs["admin_user_ids"] == [22]
        assert result == ["fds"]


class TestResolveCountryFdsAdmin:
    def test_returns_active_designated_fds_admin(self, app, db_session):
        from tests.factories import create_test_assignment_entity_status, create_test_user

        fds_admin = create_test_user(db_session, name="FDS Admin", active=True)
        aes = create_test_assignment_entity_status(db_session, status="submitted")
        aes.assigned_form  # ensure relationship
        from app.models import Country

        country = db_session.get(Country, aes.entity_id)
        country.fds_member_user_id = fds_admin.id
        db_session.commit()

        with app.app_context():
            assert _resolve_country_fds_admin_user_id(aes) == fds_admin.id

    def test_inactive_fds_admin_is_not_copied(self, app, db_session):
        from tests.factories import create_test_assignment_entity_status, create_test_user

        fds_admin = create_test_user(db_session, name="Former FDS", active=False)
        aes = create_test_assignment_entity_status(db_session, status="submitted")
        from app.models import Country

        country = db_session.get(Country, aes.entity_id)
        country.fds_member_user_id = fds_admin.id
        db_session.commit()

        with app.app_context():
            assert _resolve_country_fds_admin_user_id(aes) is None
