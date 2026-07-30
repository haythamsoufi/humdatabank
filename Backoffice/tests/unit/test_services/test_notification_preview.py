"""Tests for notification preview service."""
from unittest.mock import patch

import pytest

from app.services.notification.preview import (
    list_notification_preview_variants,
    render_notification_preview,
)


class TestNotificationPreview:
    def test_assignment_sent_for_review_has_two_variants(self, app, db_session):
        with app.app_context():
            variants = list_notification_preview_variants("assignment_sent_for_review")
        assert len(variants) == 2
        assert variants[0]["id"] == "default"
        assert variants[1]["id"] == "admin"

    def test_render_preview_includes_country_and_template(self, app, db_session):
        with app.app_context():
            with patch("app.services.notification.emails.get_org_name", return_value="Test Org"):
                preview = render_notification_preview(
                    "assignment_sent_for_review",
                    variant_id="default",
                    locale="en",
                )
        assert "Unified Country Report" in preview["title"]
        assert "Example National Society" in preview["message"]
        assert "Jamie Example" in preview["message"]
        assert preview["email_html"]
        assert "View Details" in preview["email_html"] or "View Submission" in preview["email_html"]

    def test_document_uploaded_is_in_app_only_email_unavailable(self, app, db_session):
        with app.app_context():
            preview = render_notification_preview("document_uploaded", locale="en")
        assert preview["email_html"] is None
        assert preview["sends_email"] is False

    def test_unknown_type_raises(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                render_notification_preview("not_a_real_type")
