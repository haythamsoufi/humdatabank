"""Regression tests for document notification logging with stale user IDs."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestNotifyStandaloneDocumentUploadedLogging:
    def test_pending_admin_email_logging_skips_deleted_user_ids(self, app):
        """Email logging must not crash when recipient IDs include deleted users."""
        with app.app_context():
            document = MagicMock()
            document.id = 1
            document.filename = "policy.pdf"
            document.document_type = "Policy"
            document.status = "pending"
            document.is_public = False
            document.linked_entity_type = None
            document.linked_entity_id = None

            valid_user = MagicMock()
            valid_user.id = 10
            valid_user.email = "admin@example.com"
            stale_user_id = 9_999_999

            mock_create = MagicMock(return_value=[])
            with patch(
                "app.services.notification.notifiers.documents.collect_entity_admin_audience_recipient_ids",
                return_value=[valid_user.id, stale_user_id],
            ), patch(
                "app.services.notification.notifiers.documents.create_notification",
                mock_create,
            ), patch(
                "app.services.notification.notifiers.documents.log_entity_activity",
            ), patch(
                "app.services.notification.notifiers.documents.current_user",
                MagicMock(is_authenticated=True, id=5, email="uploader@example.com"),
            ), patch(
                "app.services.notification.notifiers.documents.Country"
            ) as MockCountry, patch(
                "app.services.notification.notifiers.documents.User"
            ) as MockUser:
                MockCountry.query.get.return_value = MagicMock(name="Test Country")
                MockUser.query.filter.return_value.all.return_value = [valid_user]

                from app.services.notification.core import notify_standalone_document_uploaded

                result = notify_standalone_document_uploaded(document, country_id=1)

            assert result == []
            mock_create.assert_called_once()
            MockUser.query.filter.assert_called()
            MockUser.query.get.assert_not_called()
