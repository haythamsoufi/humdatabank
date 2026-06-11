"""
Comprehensive tests for app/services/email/campaigns.py.

Covers:
- get_entity_contacts
- categorize_contacts
- send_entity_email_campaign
- send_multiple_entity_email_campaigns
"""
import pytest
import uuid
from unittest.mock import patch, MagicMock, call

from app import db
from app.models import User, UserEntityPermission
from app.services.email.campaigns import (
    get_entity_contacts,
    categorize_contacts,
    send_entity_email_campaign,
    send_multiple_entity_email_campaigns,
)


def _make_user(suffix=None, active=True, email=None):
    suffix = suffix or uuid.uuid4().hex
    email = email or f"campaign-{suffix}@example.com"
    user = User(email=email, name=f"Campaign User {suffix}", active=active)
    user.set_password("test")
    return user


def _make_permission(user_id, entity_type, entity_id):
    return UserEntityPermission(
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )


# ---------------------------------------------------------------------------
# get_entity_contacts
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("db_session")
class TestGetEntityContacts:
    def test_returns_users_with_permissions(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.flush()

            perm = _make_permission(user.id, "country", 1)
            db.session.add(perm)
            db.session.commit()

            contacts = get_entity_contacts("country", 1)
            ids = [u.id for u in contacts]
            assert user.id in ids

    def test_returns_empty_when_no_permissions(self, app):
        with app.app_context():
            contacts = get_entity_contacts("country", 999999)
            assert contacts == []

    def test_excludes_inactive_users(self, app):
        with app.app_context():
            user = _make_user(active=False)
            db.session.add(user)
            db.session.flush()

            perm = _make_permission(user.id, "ns_branch", 2)
            db.session.add(perm)
            db.session.commit()

            contacts = get_entity_contacts("ns_branch", 2)
            ids = [u.id for u in contacts]
            assert user.id not in ids

    def test_excludes_users_without_email(self, app):
        with app.app_context():
            user = User(email=None, name="No Email", active=True)
            user.set_password("test")
            db.session.add(user)
            db.session.flush()

            perm = _make_permission(user.id, "country", 3)
            db.session.add(perm)
            db.session.commit()

            contacts = get_entity_contacts("country", 3)
            ids = [u.id for u in contacts]
            assert user.id not in ids

    def test_excludes_users_with_empty_email(self, app):
        with app.app_context():
            user = User(email="", name="Empty Email", active=True)
            user.set_password("test")
            db.session.add(user)
            db.session.flush()

            perm = _make_permission(user.id, "country", 4)
            db.session.add(perm)
            db.session.commit()

            contacts = get_entity_contacts("country", 4)
            ids = [u.id for u in contacts]
            assert user.id not in ids

    def test_returns_empty_on_exception(self, app):
        with app.app_context():
            with patch("app.services.email.campaigns.UserEntityPermission.query") as mock_q:
                mock_q.filter_by.side_effect = Exception("DB error")
                contacts = get_entity_contacts("country", 1)
            assert contacts == []

    def test_returns_multiple_users(self, app):
        with app.app_context():
            eid = 100 + hash(uuid.uuid4().hex) % 1000
            users = [_make_user() for _ in range(3)]
            for u in users:
                db.session.add(u)
            db.session.flush()

            for u in users:
                perm = _make_permission(u.id, "country", eid)
                db.session.add(perm)
            db.session.commit()

            contacts = get_entity_contacts("country", eid)
            ids = [u.id for u in contacts]
            for u in users:
                assert u.id in ids


# ---------------------------------------------------------------------------
# categorize_contacts
# ---------------------------------------------------------------------------

class TestCategorizeContacts:
    def _user(self, email):
        u = MagicMock(spec=User)
        u.email = email
        return u

    def test_empty_list_returns_empty_categories(self):
        result = categorize_contacts([])
        assert result["organization"] == []
        assert result["non_organization"] == []
        assert result["focal_point"] == []
        assert result["admin"] == []
        assert result["system_manager"] == []

    def test_skips_users_without_email(self):
        u = MagicMock(spec=User)
        u.email = None
        with patch("app.services.email.campaigns.is_org_email", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.is_system_manager", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.is_admin", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.has_role", return_value=False):
            result = categorize_contacts([u])
        assert result["organization"] == []
        assert result["non_organization"] == []

    def test_org_email_goes_to_organization(self):
        u = self._user("admin@ifrc.org")
        with patch("app.services.email.campaigns.is_org_email", return_value=True), \
             patch("app.services.email.campaigns.AuthorizationService.is_system_manager", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.is_admin", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.has_role", return_value=False):
            result = categorize_contacts([u])
        assert "admin@ifrc.org" in result["organization"]
        assert "admin@ifrc.org" not in result["non_organization"]

    def test_non_org_email_goes_to_non_organization(self):
        u = self._user("user@gmail.com")
        with patch("app.services.email.campaigns.is_org_email", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.is_system_manager", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.is_admin", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.has_role", return_value=False):
            result = categorize_contacts([u])
        assert "user@gmail.com" in result["non_organization"]

    def test_system_manager_categorized(self):
        u = self._user("sysm@x.com")
        with patch("app.services.email.campaigns.is_org_email", return_value=True), \
             patch("app.services.email.campaigns.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.services.email.campaigns.AuthorizationService.is_admin", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.has_role", return_value=False):
            result = categorize_contacts([u])
        assert "sysm@x.com" in result["system_manager"]
        assert "sysm@x.com" not in result["admin"]

    def test_admin_categorized(self):
        u = self._user("admin@x.com")
        with patch("app.services.email.campaigns.is_org_email", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.is_system_manager", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.is_admin", return_value=True), \
             patch("app.services.email.campaigns.AuthorizationService.has_role", return_value=False):
            result = categorize_contacts([u])
        assert "admin@x.com" in result["admin"]

    def test_focal_point_categorized(self):
        u = self._user("fp@x.com")
        with patch("app.services.email.campaigns.is_org_email", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.is_system_manager", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.is_admin", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.has_role", return_value=True):
            result = categorize_contacts([u])
        assert "fp@x.com" in result["focal_point"]

    def test_multiple_users_categorized(self):
        u1 = self._user("org@x.com")
        u2 = self._user("non@y.com")

        def is_org(email):
            return email.endswith("@x.com")

        with patch("app.services.email.campaigns.is_org_email", side_effect=is_org), \
             patch("app.services.email.campaigns.AuthorizationService.is_system_manager", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.is_admin", return_value=False), \
             patch("app.services.email.campaigns.AuthorizationService.has_role", return_value=False):
            result = categorize_contacts([u1, u2])
        assert "org@x.com" in result["organization"]
        assert "non@y.com" in result["non_organization"]


# ---------------------------------------------------------------------------
# send_entity_email_campaign
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("db_session")
class TestSendEntityEmailCampaign:
    def test_no_contacts_returns_false(self, app):
        with app.app_context():
            with patch("app.services.email.campaigns.get_entity_contacts", return_value=[]), \
                 patch("app.services.email.campaigns.EntityService.get_entity_display_name", return_value="Test Country"):
                result = send_entity_email_campaign("country", 1, "Subject", "<p>Hi</p>")
        assert result is False

    def test_sends_email_successfully(self, app):
        with app.app_context():
            u = MagicMock(spec=User)
            u.email = "user@gmail.com"
            with patch("app.services.email.campaigns.get_entity_contacts", return_value=[u]), \
                 patch("app.services.email.campaigns.is_org_email", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.is_system_manager", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.is_admin", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.has_role", return_value=False), \
                 patch("app.services.email.campaigns.send_email", return_value=True) as mock_send, \
                 patch("app.services.email.campaigns.EntityService.get_entity_display_name", return_value="Country A"):
                result = send_entity_email_campaign("country", 1, "Subject", "<p>Hi</p>")
        assert result is True
        mock_send.assert_called_once()

    def test_default_distribution_rules_applied(self, app):
        with app.app_context():
            u_non_org = MagicMock(spec=User)
            u_non_org.email = "fp@gmail.com"
            u_org = MagicMock(spec=User)
            u_org.email = "admin@ifrc.org"

            def is_org(email):
                return email.endswith("@ifrc.org")

            with patch("app.services.email.campaigns.get_entity_contacts", return_value=[u_non_org, u_org]), \
                 patch("app.services.email.campaigns.is_org_email", side_effect=is_org), \
                 patch("app.services.email.campaigns.AuthorizationService.is_system_manager", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.is_admin", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.has_role", return_value=False), \
                 patch("app.services.email.campaigns.send_email", return_value=True) as mock_send, \
                 patch("app.services.email.campaigns.EntityService.get_entity_display_name", return_value="Country"):
                result = send_entity_email_campaign("country", 1, "Subj", "<p>Hi</p>")

        assert result is True
        call_kwargs = mock_send.call_args.kwargs
        # non-org goes to To, org goes to CC
        assert "fp@gmail.com" in call_kwargs["recipients"]
        assert "admin@ifrc.org" in (call_kwargs["cc"] or [])

    def test_cc_emails_removed_from_cc_if_also_in_to(self, app):
        with app.app_context():
            u = MagicMock(spec=User)
            u.email = "both@x.com"

            with patch("app.services.email.campaigns.get_entity_contacts", return_value=[u]), \
                 patch("app.services.email.campaigns.is_org_email", return_value=True), \
                 patch("app.services.email.campaigns.AuthorizationService.is_system_manager", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.is_admin", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.has_role", return_value=False), \
                 patch("app.services.email.campaigns.send_email", return_value=True) as mock_send, \
                 patch("app.services.email.campaigns.EntityService.get_entity_display_name", return_value="X"):
                # distribution_rules puts org email in both to and cc
                result = send_entity_email_campaign(
                    "country", 1, "Subj", "<p>Hi</p>",
                    distribution_rules={"to": ["organization"], "cc": ["organization"]}
                )

        call_kwargs = mock_send.call_args.kwargs
        cc = call_kwargs.get("cc") or []
        assert "both@x.com" not in cc  # removed from CC since in To

    def test_no_to_moves_cc_to_to(self, app):
        with app.app_context():
            u = MagicMock(spec=User)
            u.email = "org@ifrc.org"

            with patch("app.services.email.campaigns.get_entity_contacts", return_value=[u]), \
                 patch("app.services.email.campaigns.is_org_email", return_value=True), \
                 patch("app.services.email.campaigns.AuthorizationService.is_system_manager", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.is_admin", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.has_role", return_value=False), \
                 patch("app.services.email.campaigns.send_email", return_value=True) as mock_send, \
                 patch("app.services.email.campaigns.EntityService.get_entity_display_name", return_value="X"):
                # Only org emails in CC, no non-org in To → CC should be promoted to To
                result = send_entity_email_campaign(
                    "country", 1, "Subj", "<p>Hi</p>",
                    distribution_rules={"to": ["non_organization"], "cc": ["organization"]}
                )

        assert result is True
        call_kwargs = mock_send.call_args.kwargs
        # org@ifrc.org promoted from CC to To
        assert "org@ifrc.org" in call_kwargs["recipients"]

    def test_no_valid_emails_returns_false(self, app):
        with app.app_context():
            u = MagicMock(spec=User)
            u.email = "user@x.com"

            with patch("app.services.email.campaigns.get_entity_contacts", return_value=[u]), \
                 patch("app.services.email.campaigns.is_org_email", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.is_system_manager", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.is_admin", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.has_role", return_value=False), \
                 patch("app.services.email.campaigns.EntityService.get_entity_display_name", return_value="X"):
                # distribution_rules specifying types that contain no emails
                result = send_entity_email_campaign(
                    "country", 1, "Subj", "<p>Hi</p>",
                    distribution_rules={"to": ["system_manager"], "cc": ["admin"]}
                )
        assert result is False

    def test_exception_returns_false(self, app):
        with app.app_context():
            with patch("app.services.email.campaigns.get_entity_contacts", side_effect=Exception("boom")), \
                 patch("app.services.email.campaigns.EntityService.get_entity_display_name", return_value="X"):
                result = send_entity_email_campaign("country", 1, "Subj", "<p>Hi</p>")
        assert result is False

    def test_passes_optional_params(self, app):
        with app.app_context():
            u = MagicMock(spec=User)
            u.email = "user@x.com"

            with patch("app.services.email.campaigns.get_entity_contacts", return_value=[u]), \
                 patch("app.services.email.campaigns.is_org_email", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.is_system_manager", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.is_admin", return_value=False), \
                 patch("app.services.email.campaigns.AuthorizationService.has_role", return_value=False), \
                 patch("app.services.email.campaigns.send_email", return_value=True) as mock_send, \
                 patch("app.services.email.campaigns.EntityService.get_entity_display_name", return_value="X"):
                send_entity_email_campaign(
                    "country", 1, "Subj", "<p>Hi</p>",
                    text_content="plain text",
                    sender="sender@x.com",
                    reply_to="reply@x.com",
                    importance="high",
                    attachments=[("doc.pdf", b"bytes", "application/pdf")],
                )

        kwargs = mock_send.call_args.kwargs
        assert kwargs["text"] == "plain text"
        assert kwargs["sender"] == "sender@x.com"
        assert kwargs["reply_to"] == "reply@x.com"
        assert kwargs["importance"] == "high"
        assert len(kwargs["attachments"]) == 1


# ---------------------------------------------------------------------------
# send_multiple_entity_email_campaigns
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("db_session")
class TestSendMultipleEntityEmailCampaigns:
    def test_empty_selections_returns_zeros(self, app):
        with app.app_context():
            result = send_multiple_entity_email_campaigns([], "Subject", "<p>Hi</p>")
        assert result["success_count"] == 0
        assert result["failure_count"] == 0
        assert result["total"] == 0
        assert result["results"] == []

    def test_invalid_entity_selection_counted_as_failure(self, app):
        with app.app_context():
            result = send_multiple_entity_email_campaigns(
                [{"entity_type": None, "entity_id": None}], "Subject", "<p>Hi</p>"
            )
        assert result["failure_count"] == 1
        assert result["success_count"] == 0
        assert result["results"][0]["success"] is False
        assert result["results"][0]["error"] == "Invalid entity selection"

    def test_missing_entity_type_counted_as_failure(self, app):
        with app.app_context():
            result = send_multiple_entity_email_campaigns(
                [{"entity_id": 1}], "Subject", "<p>Hi</p>"
            )
        assert result["failure_count"] == 1

    def test_missing_entity_id_counted_as_failure(self, app):
        with app.app_context():
            result = send_multiple_entity_email_campaigns(
                [{"entity_type": "country"}], "Subject", "<p>Hi</p>"
            )
        assert result["failure_count"] == 1

    def test_successful_send_counted(self, app):
        with app.app_context():
            with patch("app.services.email.campaigns.send_entity_email_campaign", return_value=True):
                result = send_multiple_entity_email_campaigns(
                    [{"entity_type": "country", "entity_id": 1}], "Subject", "<p>Hi</p>"
                )
        assert result["success_count"] == 1
        assert result["failure_count"] == 0

    def test_failed_send_counted(self, app):
        with app.app_context():
            with patch("app.services.email.campaigns.send_entity_email_campaign", return_value=False):
                result = send_multiple_entity_email_campaigns(
                    [{"entity_type": "country", "entity_id": 1}], "Subject", "<p>Hi</p>"
                )
        assert result["failure_count"] == 1
        assert result["success_count"] == 0

    def test_multiple_entities_mixed_results(self, app):
        with app.app_context():
            call_results = [True, False, True]
            with patch("app.services.email.campaigns.send_entity_email_campaign",
                       side_effect=call_results):
                result = send_multiple_entity_email_campaigns(
                    [
                        {"entity_type": "country", "entity_id": 1},
                        {"entity_type": "country", "entity_id": 2},
                        {"entity_type": "country", "entity_id": 3},
                    ],
                    "Subject", "<p>Hi</p>"
                )
        assert result["success_count"] == 2
        assert result["failure_count"] == 1
        assert result["total"] == 3

    def test_static_attachments_passed_to_campaign(self, app):
        with app.app_context():
            attachments = [("doc.pdf", b"data", "application/pdf")]
            with patch("app.services.email.campaigns.send_entity_email_campaign", return_value=True) as mock_c:
                send_multiple_entity_email_campaigns(
                    [{"entity_type": "country", "entity_id": 1}],
                    "Subject", "<p>Hi</p>",
                    static_attachments=attachments,
                )
        kwargs = mock_c.call_args.kwargs
        assert kwargs["attachments"] is not None
        assert len(kwargs["attachments"]) == 1

    def test_assignment_pdf_attached_when_aes_found(self, app):
        with app.app_context():
            mock_aes = MagicMock()
            mock_aes.id = 42

            def mock_get_pdf(aes_id):
                return b"pdf-bytes", "assignment.pdf"

            with patch("app.services.email.campaigns.send_entity_email_campaign", return_value=True) as mock_c, \
                 patch("app.models.assignments.AssignmentEntityStatus.query") as mock_q:
                mock_q.filter_by.return_value.first.return_value = mock_aes
                send_multiple_entity_email_campaigns(
                    [{"entity_type": "country", "entity_id": 1}],
                    "Subject", "<p>Hi</p>",
                    assignment_pdf_assigned_form_id=10,
                    get_pdf_bytes_for_aes=mock_get_pdf,
                )

        kwargs = mock_c.call_args.kwargs
        assert kwargs["attachments"] is not None
        # Should include the PDF
        filenames = [a[0] for a in kwargs["attachments"]]
        assert "assignment.pdf" in filenames

    def test_assignment_pdf_skipped_when_no_aes(self, app):
        with app.app_context():
            with patch("app.services.email.campaigns.send_entity_email_campaign", return_value=True) as mock_c, \
                 patch("app.models.assignments.AssignmentEntityStatus.query") as mock_q:
                mock_q.filter_by.return_value.first.return_value = None
                send_multiple_entity_email_campaigns(
                    [{"entity_type": "country", "entity_id": 1}],
                    "Subject", "<p>Hi</p>",
                    assignment_pdf_assigned_form_id=10,
                    get_pdf_bytes_for_aes=lambda aid: (b"pdf", "file.pdf"),
                )

        kwargs = mock_c.call_args.kwargs
        # No PDF attached → attachments=None (no static, no pdf)
        assert not kwargs.get("attachments")

    def test_pdf_generation_exception_is_swallowed(self, app):
        with app.app_context():
            def bad_pdf(aes_id):
                raise RuntimeError("PDF generation failed")

            with patch("app.services.email.campaigns.send_entity_email_campaign", return_value=True), \
                 patch("app.models.assignments.AssignmentEntityStatus.query") as mock_q:
                mock_aes = MagicMock()
                mock_aes.id = 1
                mock_q.filter_by.return_value.first.return_value = mock_aes
                # Should NOT raise
                result = send_multiple_entity_email_campaigns(
                    [{"entity_type": "country", "entity_id": 1}],
                    "Subject", "<p>Hi</p>",
                    assignment_pdf_assigned_form_id=10,
                    get_pdf_bytes_for_aes=bad_pdf,
                )
        assert result["success_count"] == 1

    def test_pdf_bytes_none_not_attached(self, app):
        with app.app_context():
            with patch("app.services.email.campaigns.send_entity_email_campaign", return_value=True) as mock_c, \
                 patch("app.models.assignments.AssignmentEntityStatus.query") as mock_q:
                mock_aes = MagicMock()
                mock_aes.id = 1
                mock_q.filter_by.return_value.first.return_value = mock_aes
                send_multiple_entity_email_campaigns(
                    [{"entity_type": "country", "entity_id": 1}],
                    "Subject", "<p>Hi</p>",
                    assignment_pdf_assigned_form_id=10,
                    get_pdf_bytes_for_aes=lambda aid: (None, None),
                )

        kwargs = mock_c.call_args.kwargs
        assert not kwargs.get("attachments")

    def test_distribution_rules_forwarded(self, app):
        with app.app_context():
            rules = {"to": ["focal_point"], "cc": ["admin"]}
            with patch("app.services.email.campaigns.send_entity_email_campaign", return_value=True) as mock_c:
                send_multiple_entity_email_campaigns(
                    [{"entity_type": "country", "entity_id": 1}],
                    "Subject", "<p>Hi</p>",
                    distribution_rules=rules,
                )
        kwargs = mock_c.call_args.kwargs
        assert kwargs["distribution_rules"] == rules

    def test_results_list_populated(self, app):
        with app.app_context():
            with patch("app.services.email.campaigns.send_entity_email_campaign", return_value=True):
                result = send_multiple_entity_email_campaigns(
                    [{"entity_type": "country", "entity_id": 5}],
                    "Subject", "<p>Hi</p>"
                )
        assert result["results"][0]["entity_type"] == "country"
        assert result["results"][0]["entity_id"] == 5
        assert result["results"][0]["success"] is True
