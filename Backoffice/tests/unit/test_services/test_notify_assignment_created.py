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
                return_value="/assignment/1",
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
                return_value="/assignment/1",
            ):
                result = notify_assignment_created(pending_aes)

        mock_create.assert_called_once()
        assert mock_create.call_args.kwargs["user_ids"] == [admin_only_id]
        assert result == ["admin-notification"]

    def test_focal_points_bucket_disabled_skips_grouped_email_to_focal(self, app, pending_aes):
        """Regression test: notify_assignment_created previously computed focal_user_ids
        unconditionally and always emailed them, even when the focal_points audience
        bucket was disabled — only the in-app notification was gated. The grouped email
        must respect the same bucket flag as notify_entity_focal_points (and as
        preview_assignment_created_grouped_email, which already checked this)."""
        would_be_focal_ids = [101]

        with app.app_context():
            with patch(
                "app.services.notification.notifiers.assignment.audience_bucket_enabled",
                return_value=False,
            ), patch(
                "app.services.notification.notifiers.assignment.get_assignment_editor_submitter_user_ids_for_entity",
                return_value=would_be_focal_ids,
            ) as mock_get_focal, patch(
                "app.services.notification.notifiers.assignment.notify_entity_focal_points",
                return_value=[],
            ), patch(
                "app.services.notification.notifiers.assignment.collect_entity_admin_audience_recipient_ids",
                return_value=[],
            ), patch(
                "app.services.notification.notifiers.assignment._send_grouped_assignment_created_email",
            ) as mock_send_email, patch(
                "app.services.notification.notifiers.assignment.log_entity_activity",
            ), patch(
                "app.services.notification.notifiers.assignment.url_for",
                return_value="/assignment/1",
            ):
                notify_assignment_created(pending_aes)

        # The bucket check must short-circuit before even querying for focal points.
        mock_get_focal.assert_not_called()
        # No focal recipients and no admin recipients => no grouped email at all.
        mock_send_email.assert_not_called()

    def test_focal_points_bucket_disabled_still_emails_admin_only_recipients(self, app, pending_aes):
        """Admins are a separate audience bucket, so disabling focal_points must not
        suppress admin CC emails — they should become the sole 'to' recipients."""
        admin_only_id = 202

        with app.app_context():
            with patch(
                "app.services.notification.notifiers.assignment.audience_bucket_enabled",
                return_value=False,
            ), patch(
                "app.services.notification.notifiers.assignment.get_assignment_editor_submitter_user_ids_for_entity",
            ) as mock_get_focal, patch(
                "app.services.notification.notifiers.assignment.notify_entity_focal_points",
                return_value=[],
            ), patch(
                "app.services.notification.notifiers.assignment.collect_entity_admin_audience_recipient_ids",
                return_value=[admin_only_id],
            ), patch(
                "app.services.notification.notifiers.assignment.create_notification",
                return_value=["admin-notification"],
            ), patch(
                "app.services.notification.notifiers.assignment._send_grouped_assignment_created_email",
            ) as mock_send_email, patch(
                "app.services.notification.notifiers.assignment.log_entity_activity",
            ), patch(
                "app.services.notification.notifiers.assignment.url_for",
                return_value="/assignment/1",
            ):
                notify_assignment_created(pending_aes, notify_admins=True)

        mock_get_focal.assert_not_called()
        mock_send_email.assert_called_once()
        assert mock_send_email.call_args.kwargs["focal_user_ids"] == []
        assert mock_send_email.call_args.kwargs["admin_user_ids"] == [admin_only_id]

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
                return_value="/assignment/1",
            ):
                notify_assignment_created(pending_aes)

        assert mock_focal.call_args.kwargs["exclude_user_ids"] == [creator_id]
        assert mock_admin.call_args.kwargs["exclude_user_ids"] == [creator_id]

    def test_actor_user_id_param_overrides_current_user(self, app, pending_aes):
        """
        actor_user_id must win over current_user for creator-exclusion.

        This is exercised by the async notification dispatch (see
        docs/runbooks/incidents/2026-08-12-prod-assignment-create-gateway-timeout.md):
        that code runs on a background thread with no request context, where
        current_user always resolves to anonymous, so the caller must pass the
        actor id captured earlier on the request thread explicitly.
        """
        explicit_actor_id = 555
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 999  # must be ignored once actor_user_id is provided

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
                return_value="/assignment/1",
            ):
                notify_assignment_created(pending_aes, actor_user_id=explicit_actor_id)

        assert mock_focal.call_args.kwargs["exclude_user_ids"] == [explicit_actor_id]
        assert mock_admin.call_args.kwargs["exclude_user_ids"] == [explicit_actor_id]

    def test_actor_user_id_none_without_current_user_excludes_no_one(self, app, pending_aes):
        """Documents the failure mode the actor_user_id param fixes: with no explicit
        actor and no request-bound current_user (i.e. called from a bare app context,
        like a background thread), nobody is excluded from the notification."""
        with app.app_context():
            with patch(
                "app.services.notification.notifiers.assignment.current_user",
                None,
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
                return_value="/assignment/1",
            ):
                notify_assignment_created(pending_aes)

        assert mock_focal.call_args.kwargs["exclude_user_ids"] is None
        assert mock_admin.call_args.kwargs["exclude_user_ids"] is None

    def test_grouped_email_sample_includes_assignment_related_url(self, app, pending_aes):
        with app.app_context():
            with patch(
                "app.services.notification.notifiers.assignment.notify_entity_focal_points",
                return_value=[{"user_id": 101}],
            ), patch(
                "app.services.notification.notifiers.assignment.collect_entity_admin_audience_recipient_ids",
                return_value=[],
            ), patch(
                "app.services.notification.notifiers.assignment.get_assignment_editor_submitter_user_ids_for_entity",
                return_value=[101],
            ), patch(
                "app.services.notification.notifiers.assignment._send_grouped_assignment_created_email",
            ) as mock_send_email, patch(
                "app.services.notification.notifiers.assignment.log_entity_activity",
            ), patch(
                "app.services.notification.notifiers.assignment.url_for",
                return_value="/assignment/99",
            ):
                notify_assignment_created(pending_aes)

        mock_send_email.assert_called_once()
        sample = mock_send_email.call_args.kwargs["sample_notification"]
        assert sample.related_url == "/assignment/99"


class TestPreviewAssignmentCreatedGroupedEmail:
    def test_renders_body_without_notify_admins_or_recipients(self, app, db_session):
        from types import SimpleNamespace
        from app.services.notification.notifiers.assignment import (
            preview_assignment_created_grouped_email,
        )

        template = SimpleNamespace(id=42, name="FDRS Annual")

        with app.app_context():
            with patch(
                "app.models.forms.FormTemplate.query"
            ) as mock_query, patch(
                "app.services.notification.notifiers.assignment.get_assignment_editor_submitter_user_ids_for_entity",
                return_value=[],
            ), patch(
                "app.services.notification.notifiers.assignment.collect_entity_admin_audience_recipient_ids",
                return_value=[501],
            ), patch(
                "app.services.notification.notifiers.assignment._resolve_entity_name",
                return_value="Kenya",
            ), patch(
                "app.services.platform.app_settings_service.audience_bucket_enabled",
                return_value=True,
            ):
                mock_query.get.return_value = template
                preview = preview_assignment_created_grouped_email(
                    country_id=1,
                    template_id=template.id,
                    period_name="Annual 2026",
                    notify_admins=False,
                )

        assert not preview.get("empty_reason")
        assert preview.get("html_body")
        assert preview.get("subject")
        assert preview.get("to") == []
        assert preview.get("cc") == []

    def test_preview_includes_open_assignment_button(self, app, db_session):
        from types import SimpleNamespace
        from app.services.notification.notifiers.assignment import (
            preview_assignment_created_grouped_email,
        )

        template = SimpleNamespace(id=42, name="Unified Country Plan")

        with app.app_context():
            with patch(
                "app.models.forms.FormTemplate.query"
            ) as mock_query, patch(
                "app.services.notification.notifiers.assignment.get_assignment_editor_submitter_user_ids_for_entity",
                return_value=[],
            ), patch(
                "app.services.notification.notifiers.assignment.collect_entity_admin_audience_recipient_ids",
                return_value=[],
            ), patch(
                "app.services.notification.notifiers.assignment._resolve_entity_name",
                return_value="Afghanistan",
            ), patch(
                "app.services.platform.app_settings_service.audience_bucket_enabled",
                return_value=True,
            ):
                mock_query.get.return_value = template
                preview = preview_assignment_created_grouped_email(
                    country_id=1,
                    template_id=template.id,
                    period_name="2027",
                    notify_admins=False,
                )

        html = preview.get("html_body") or ""
        assert 'href="' in html
        assert "/forms/" in html or 'href="/"' in html or "Open Assignment" in html
