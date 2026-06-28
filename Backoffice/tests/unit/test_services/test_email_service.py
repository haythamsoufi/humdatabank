"""
Comprehensive tests for app/services/email/service.py.

Covers:
- normalize_sector_data
- create_comparison_table
- create_new_indicator_details
- send_suggestion_confirmation_email
- send_admin_notification_email
- _security_alert_fallback_html_body
- send_security_alert
- send_welcome_email
"""
import pytest
import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock, call

from app import db
from app.models import User
from app.services.email.service import (
    normalize_sector_data,
    create_comparison_table,
    create_new_indicator_details,
    send_suggestion_confirmation_email,
    send_admin_notification_email,
    _security_alert_fallback_html_body,
    send_security_alert,
    send_welcome_email,
)


def _make_user(suffix=None, email=None, name=None, active=True):
    suffix = suffix or uuid.uuid4().hex
    user = User(
        email=email or f"svc-{suffix}@example.com",
        name=name or f"Svc User {suffix}",
        active=active,
    )
    user.set_password("test")
    return user


def _make_suggestion(suggestion_type="new_indicator", is_correction=False):
    sug = MagicMock()
    sug.id = 1
    sug.indicator_name = "Test Indicator"
    sug.definition = "A test definition"
    sug.type = "Count"
    sug.unit = "People"
    sug.emergency = False
    sug.related_programs = "Program A"
    sug.sector = None
    sug.sub_sector = None
    sug.suggestion_type = "correction" if is_correction else "new_indicator"
    sug.suggestion_type_display = "Correction" if is_correction else "New Indicator"
    sug.submitter_name = "Alice Tester"
    sug.submitter_email = "alice@example.com"
    sug.submitted_at = datetime(2024, 6, 1, 10, 0, 0)
    sug.reason = "Test reason"
    sug.additional_notes = "Some notes"
    sug.indicator = None
    return sug


# ---------------------------------------------------------------------------
# normalize_sector_data
# ---------------------------------------------------------------------------

class TestNormalizeSectorData:
    def test_none_returns_none(self):
        assert normalize_sector_data(None) is None

    def test_simple_string(self):
        assert normalize_sector_data("Health") == "Health"

    def test_empty_string(self):
        assert normalize_sector_data("") is None

    def test_whitespace_string(self):
        assert normalize_sector_data("  ") is None

    def test_strips_string(self):
        assert normalize_sector_data("  Health  ") == "Health"

    def test_integer_returns_str_or_db_name(self, app):
        with app.app_context():
            with patch("app.models.Sector.query") as mock_q:
                mock_sector = MagicMock()
                mock_sector.name = "Shelter"
                mock_q.get.return_value = mock_sector
                result = normalize_sector_data({"primary": 3}, is_sector=True)
            assert "Shelter" in result

    def test_integer_sector_not_found_uses_str(self, app):
        with app.app_context():
            with patch("app.models.Sector.query") as mock_q:
                mock_q.get.return_value = None
                result = normalize_sector_data({"primary": 99}, is_sector=True)
            assert "99" in result

    def test_integer_sector_exception_uses_str(self, app):
        with app.app_context():
            with patch("app.models.Sector.query") as mock_q:
                mock_q.get.side_effect = Exception("DB error")
                result = normalize_sector_data({"primary": 5}, is_sector=True)
            assert "5" in result

    def test_dict_primary_only(self):
        result = normalize_sector_data({"primary": "Health"})
        assert result == "Health"

    def test_dict_primary_secondary(self):
        result = normalize_sector_data({"primary": "Health", "secondary": "Mental"})
        assert "Health" in result
        assert "Mental" in result
        assert " | " in result

    def test_dict_all_levels(self):
        result = normalize_sector_data({
            "primary": "Health",
            "secondary": "Mental",
            "tertiary": "Counseling"
        })
        assert "Health" in result
        assert "Mental" in result
        assert "Counseling" in result

    def test_dict_empty_values(self):
        result = normalize_sector_data({"primary": None, "secondary": None})
        assert result is None

    def test_non_string_non_dict(self):
        result = normalize_sector_data(42)
        assert result == "42"

    def test_subsector_lookup(self, app):
        with app.app_context():
            with patch("app.models.SubSector.query") as mock_q:
                mock_sub = MagicMock()
                mock_sub.name = "Nutrition"
                mock_q.get.return_value = mock_sub
                result = normalize_sector_data({"primary": 7}, is_sector=False)
            assert "Nutrition" in result


# ---------------------------------------------------------------------------
# create_comparison_table
# ---------------------------------------------------------------------------

class TestCreateComparisonTable:
    def _make_indicator(self, **kwargs):
        ind = MagicMock()
        ind.name = kwargs.get("name", "Original Name")
        ind.definition = kwargs.get("definition", "Original Def")
        ind.type = kwargs.get("type", "Count")
        ind.unit = kwargs.get("unit", "People")
        ind.emergency = kwargs.get("emergency", False)
        ind.related_programs = kwargs.get("related_programs", "Prog")
        ind.sector = kwargs.get("sector", None)
        ind.sub_sector = kwargs.get("sub_sector", None)
        return ind

    def test_returns_html_string(self):
        sug = _make_suggestion(is_correction=True)
        result = create_comparison_table(sug, self._make_indicator())
        assert isinstance(result, str)
        assert "<table" in result

    def test_includes_all_fields(self):
        sug = _make_suggestion(is_correction=True)
        result = create_comparison_table(sug, self._make_indicator())
        assert "Indicator Name" in result
        assert "Definition" in result
        assert "Type" in result
        assert "Unit" in result
        assert "Sector" in result
        assert "Emergency Context" in result

    def test_changed_field_marked_changed(self):
        sug = _make_suggestion(is_correction=True)
        sug.definition = "New Definition"
        original = self._make_indicator(definition="Old Definition")
        result = create_comparison_table(sug, original)
        assert "changed" in result

    def test_unchanged_field_marked_unchanged(self):
        sug = _make_suggestion(is_correction=True)
        sug.name = "Same Name"
        sug.indicator_name = "Same Name"
        original = self._make_indicator(name="Same Name")
        result = create_comparison_table(sug, original)
        assert "unchanged" in result

    def test_none_original_indicator(self):
        sug = _make_suggestion(is_correction=True)
        result = create_comparison_table(sug, None)
        assert isinstance(result, str)
        assert "<table" in result

    def test_emergency_true_displays_yes(self):
        sug = _make_suggestion(is_correction=True)
        sug.emergency = True
        result = create_comparison_table(sug, self._make_indicator(emergency=False))
        assert "Yes" in result

    def test_emergency_none_displays_not_provided(self):
        sug = _make_suggestion(is_correction=True)
        sug.emergency = False
        original = self._make_indicator()
        original.emergency = None
        result = create_comparison_table(sug, original)
        assert "Not provided" in result

    def test_sector_dict_format_in_suggestion(self):
        sug = _make_suggestion(is_correction=True)
        sug.sector = {"primary": "Health", "secondary": "Mental"}
        result = create_comparison_table(sug, self._make_indicator())
        assert "Health" in result

    def test_subsector_dict_format_in_suggestion(self):
        sug = _make_suggestion(is_correction=True)
        sug.sub_sector = {"primary": "Nutrition"}
        result = create_comparison_table(sug, self._make_indicator())
        assert "Nutrition" in result

    def test_sector_string_format_in_suggestion(self):
        sug = _make_suggestion(is_correction=True)
        sug.sector = "Health"
        result = create_comparison_table(sug, self._make_indicator())
        assert "Health" in result

    def test_original_indicator_sector_dict(self):
        sug = _make_suggestion(is_correction=True)
        sug.sector = None
        original = self._make_indicator()
        original.sector = {"primary": "WASH", "secondary": "Sanitation"}
        result = create_comparison_table(sug, original)
        assert "WASH" in result or "Sanitation" in result

    def test_original_indicator_sub_sector_dict(self):
        sug = _make_suggestion(is_correction=True)
        sug.sub_sector = None
        original = self._make_indicator()
        original.sub_sector = {"primary": "Nutrition", "tertiary": "Infant"}
        result = create_comparison_table(sug, original)
        assert isinstance(result, str)

    def test_html_escaped_field_values(self):
        sug = _make_suggestion(is_correction=True)
        sug.indicator_name = "<script>alert(1)</script>"
        result = create_comparison_table(sug, self._make_indicator())
        assert "<script>" not in result

    def test_comparison_table_structure(self):
        sug = _make_suggestion(is_correction=True)
        result = create_comparison_table(sug, self._make_indicator())
        assert "<thead>" in result
        assert "<tbody>" in result
        assert "Original Value" in result
        assert "Suggested Value" in result


# ---------------------------------------------------------------------------
# create_new_indicator_details
# ---------------------------------------------------------------------------

class TestCreateNewIndicatorDetails:
    def test_returns_html_list(self):
        sug = _make_suggestion()
        result = create_new_indicator_details(sug)
        assert "<ul" in result
        assert "<li" in result

    def test_includes_all_fields(self):
        sug = _make_suggestion()
        sug.sector = "Health"
        sug.sub_sector = "Mental"
        result = create_new_indicator_details(sug)
        assert "Indicator Name" in result
        assert "Definition" in result
        assert "Type" in result
        assert "Unit" in result
        assert "Emergency Context" in result

    def test_emergency_true_shows_yes(self):
        sug = _make_suggestion()
        sug.emergency = True
        result = create_new_indicator_details(sug)
        assert "Yes" in result

    def test_emergency_false_shows_no(self):
        sug = _make_suggestion()
        sug.emergency = False
        result = create_new_indicator_details(sug)
        assert "No" in result

    def test_none_value_shows_not_provided(self):
        sug = _make_suggestion()
        sug.definition = None
        result = create_new_indicator_details(sug)
        assert "Not provided" in result

    def test_sector_string(self):
        sug = _make_suggestion()
        sug.sector = "WASH"
        result = create_new_indicator_details(sug)
        assert "WASH" in result

    def test_sector_dict(self):
        sug = _make_suggestion()
        sug.sector = {"primary": "Health", "secondary": "Mental", "tertiary": "Counseling"}
        result = create_new_indicator_details(sug)
        assert "Health" in result
        assert "Mental" in result
        assert "Counseling" in result

    def test_sector_none_shows_not_provided(self):
        sug = _make_suggestion()
        sug.sector = None
        result = create_new_indicator_details(sug)
        assert "Not provided" in result

    def test_sub_sector_string(self):
        sug = _make_suggestion()
        sug.sub_sector = "Nutrition"
        result = create_new_indicator_details(sug)
        assert "Nutrition" in result

    def test_sub_sector_dict(self):
        sug = _make_suggestion()
        sug.sub_sector = {"primary": "Nutrition", "secondary": "Infant"}
        result = create_new_indicator_details(sug)
        assert "Nutrition" in result

    def test_sub_sector_none_shows_not_provided(self):
        sug = _make_suggestion()
        sug.sub_sector = None
        result = create_new_indicator_details(sug)
        assert "Not provided" in result

    def test_html_escaped_values(self):
        sug = _make_suggestion()
        sug.indicator_name = "<script>xss</script>"
        result = create_new_indicator_details(sug)
        assert "<script>" not in result

    def test_sector_dict_empty_primary(self):
        sug = _make_suggestion()
        sug.sector = {"primary": None, "secondary": "Mental"}
        result = create_new_indicator_details(sug)
        assert "Mental" in result

    def test_sub_sector_dict_empty(self):
        sug = _make_suggestion()
        sug.sub_sector = {}
        result = create_new_indicator_details(sug)
        # empty dict is falsy-ish but sub_sector is set, so should show not provided path
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _security_alert_fallback_html_body
# ---------------------------------------------------------------------------

class TestSecurityAlertFallbackHtmlBody:
    def test_includes_event_type(self):
        context = {"event_type": "login_failure", "severity": "high", "description": "Too many attempts"}
        result = _security_alert_fallback_html_body(context)
        assert "login_failure" in result

    def test_includes_severity(self):
        context = {"event_type": "x", "severity": "critical", "description": "Desc"}
        result = _security_alert_fallback_html_body(context)
        assert "critical" in result

    def test_includes_description(self):
        context = {"event_type": "x", "severity": "medium", "description": "Suspicious activity"}
        result = _security_alert_fallback_html_body(context)
        assert "Suspicious activity" in result

    def test_includes_ip_when_provided(self):
        context = {"event_type": "x", "severity": "low", "description": "D", "ip_address": "1.2.3.4"}
        result = _security_alert_fallback_html_body(context)
        assert "1.2.3.4" in result

    def test_excludes_ip_when_not_provided(self):
        context = {"event_type": "x", "severity": "low", "description": "D"}
        result = _security_alert_fallback_html_body(context)
        assert "IP address" not in result

    def test_includes_user_email_when_provided(self):
        context = {"event_type": "x", "severity": "low", "description": "D",
                   "user_email": "u@x.com", "user_id": 42}
        result = _security_alert_fallback_html_body(context)
        assert "u@x.com" in result
        assert "42" in result

    def test_includes_user_id_without_email(self):
        context = {"event_type": "x", "severity": "low", "description": "D", "user_id": 7}
        result = _security_alert_fallback_html_body(context)
        assert "7" in result

    def test_includes_admin_url_link(self):
        context = {"event_type": "x", "severity": "low", "description": "D",
                   "admin_url": "http://admin.example.com"}
        result = _security_alert_fallback_html_body(context)
        assert "http://admin.example.com" in result

    def test_includes_org_name(self):
        context = {"event_type": "x", "severity": "low", "description": "D",
                   "org_name": "IFRC"}
        result = _security_alert_fallback_html_body(context)
        assert "IFRC" in result

    def test_timestamp_datetime_formatted(self):
        ts = datetime(2024, 6, 1, 9, 0, 0)
        context = {"event_type": "x", "severity": "low", "description": "D", "timestamp": ts}
        result = _security_alert_fallback_html_body(context)
        assert "2024-06-01" in result

    def test_timestamp_none_shows_na(self):
        context = {"event_type": "x", "severity": "low", "description": "D", "timestamp": None}
        result = _security_alert_fallback_html_body(context)
        assert "N/A" in result

    def test_html_escaped_description(self):
        context = {"event_type": "x", "severity": "low",
                   "description": "<script>alert(1)</script>"}
        result = _security_alert_fallback_html_body(context)
        assert "<script>" not in result

    def test_html_escaped_event_type(self):
        context = {"event_type": "<b>evil</b>", "severity": "low", "description": "D"}
        result = _security_alert_fallback_html_body(context)
        assert "<b>evil</b>" not in result

    def test_timestamp_ensure_utc_exception(self):
        ts = datetime(2024, 1, 1)
        context = {"event_type": "x", "severity": "low", "description": "D", "timestamp": ts}
        with patch("app.utils.datetime_helpers.ensure_utc", side_effect=Exception("tz fail")):
            result = _security_alert_fallback_html_body(context)
        # falls back to str(ts)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# send_security_alert
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("db_session")
class TestSendSecurityAlert:
    def test_no_admin_emails_returns_false(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = []
            result = send_security_alert(event_type="test", severity="low")
        assert result is False

    def test_sends_with_admin_emails_config(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            with patch("app.services.email.service.send_email", return_value=True) as mock_send:
                result = send_security_alert(event_type="login_failure", severity="high",
                                             description="Too many attempts")
        assert result is True
        mock_send.assert_called_once()

    def test_recipients_override_admin_emails(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            with patch("app.services.email.service.send_email", return_value=True) as mock_send:
                send_security_alert(
                    event_type="test", severity="low",
                    recipients=["override@example.com"]
                )
        kwargs = mock_send.call_args.kwargs
        assert "override@example.com" in kwargs["recipients"]

    def test_subject_auto_generated(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            with patch("app.services.email.service.send_email", return_value=True) as mock_send:
                send_security_alert(event_type="login_failure", severity="critical")
        kwargs = mock_send.call_args.kwargs
        assert "CRITICAL" in kwargs["subject"]
        assert "Login Failure" in kwargs["subject"]

    def test_custom_subject_used(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            with patch("app.services.email.service.send_email", return_value=True) as mock_send:
                send_security_alert(subject="Custom Alert", event_type="test", severity="low")
        kwargs = mock_send.call_args.kwargs
        assert kwargs["subject"] == "Custom Alert"

    def test_user_email_looked_up_by_user_id(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            with patch("app.services.email.service.send_email", return_value=True):
                with patch("app.models.User.query") as mock_q:
                    mock_q.get.return_value = user
                    result = send_security_alert(event_type="test", severity="low", user_id=user.id)
        assert result is True

    def test_user_lookup_exception_swallowed(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            with patch("app.services.email.service.send_email", return_value=True):
                with patch("app.models.User.query") as mock_q:
                    mock_q.get.side_effect = Exception("DB error")
                    result = send_security_alert(event_type="test", severity="low", user_id=999)
        assert result is True

    def test_timestamp_string_parsed(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            with patch("app.services.email.service.send_email", return_value=True):
                result = send_security_alert(
                    event_type="test", severity="low",
                    timestamp="2024-06-01T10:00:00"
                )
        assert result is True

    def test_invalid_timestamp_string_falls_back(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            with patch("app.services.email.service.send_email", return_value=True):
                result = send_security_alert(
                    event_type="test", severity="low",
                    timestamp="not-a-date"
                )
        assert result is True

    def test_datetime_timestamp_used_directly(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            with patch("app.services.email.service.send_email", return_value=True):
                result = send_security_alert(
                    event_type="test", severity="low",
                    timestamp=datetime(2024, 1, 1)
                )
        assert result is True

    def test_no_timestamp_uses_utcnow(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            with patch("app.services.email.service.send_email", return_value=True):
                result = send_security_alert(event_type="test", severity="low")
        assert result is True

    def test_empty_html_uses_fallback(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            with patch("app.services.email.service.render_admin_email_template", return_value=""), \
                 patch("app.services.email.service.send_email", return_value=True) as mock_send:
                send_security_alert(event_type="test", severity="low")
        # Fallback HTML should have been used
        kwargs = mock_send.call_args.kwargs
        assert kwargs["html"]  # not empty

    def test_suppresses_security_event_recursion(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            with patch("app.services.email.service.send_email", return_value=True) as mock_send:
                send_security_alert(event_type="test", severity="low")
        kwargs = mock_send.call_args.kwargs
        assert kwargs.get("_suppress_email_failure_security_event") is True

    def test_exception_returns_false(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            with patch("app.services.email.service.get_org_name", side_effect=Exception("crash")):
                result = send_security_alert(event_type="test", severity="low")
        assert result is False

    def test_send_failure_returns_false(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            with patch("app.services.email.service.send_email", return_value=False):
                result = send_security_alert(event_type="test", severity="low")
        assert result is False


# ---------------------------------------------------------------------------
# send_suggestion_confirmation_email
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("db_session")
class TestSendSuggestionConfirmationEmail:
    def test_sends_to_submitter(self, app):
        with app.app_context():
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            sug = _make_suggestion()
            with patch("app.services.email.service.send_email", return_value=True) as mock_send, \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"):
                result = send_suggestion_confirmation_email(sug)
        assert result is True
        kwargs = mock_send.call_args.kwargs
        assert "alice@example.com" in kwargs["recipients"]

    def test_correction_uses_comparison_table(self, app):
        with app.app_context():
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            sug = _make_suggestion(is_correction=True)
            original_ind = MagicMock()
            original_ind.name = "Original"
            original_ind.definition = "Def"
            original_ind.type = "Count"
            original_ind.unit = "People"
            original_ind.emergency = False
            original_ind.related_programs = None
            original_ind.sector = None
            original_ind.sub_sector = None
            sug.indicator = original_ind

            with patch("app.services.email.service.send_email", return_value=True), \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"), \
                 patch("app.services.email.service.create_comparison_table", return_value="<table/>") as mock_ct:
                result = send_suggestion_confirmation_email(sug)
        assert result is True
        mock_ct.assert_called_once()

    def test_new_indicator_uses_new_indicator_details(self, app):
        with app.app_context():
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            sug = _make_suggestion(is_correction=False)

            with patch("app.services.email.service.send_email", return_value=True), \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"), \
                 patch("app.services.email.service.create_new_indicator_details", return_value="<ul/>") as mock_nid:
                result = send_suggestion_confirmation_email(sug)
        assert result is True
        mock_nid.assert_called_once()

    def test_improvement_uses_comparison_table(self, app):
        with app.app_context():
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            sug = _make_suggestion(is_correction=True)
            sug.suggestion_type = "improvement"
            sug.indicator = MagicMock()
            sug.indicator.name = "Orig"
            sug.indicator.definition = "D"
            sug.indicator.type = "C"
            sug.indicator.unit = "U"
            sug.indicator.emergency = False
            sug.indicator.related_programs = None
            sug.indicator.sector = None
            sug.indicator.sub_sector = None

            with patch("app.services.email.service.send_email", return_value=True), \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"), \
                 patch("app.services.email.service.create_comparison_table", return_value="<table/>") as mock_ct:
                result = send_suggestion_confirmation_email(sug)
        assert result is True
        mock_ct.assert_called_once()

    def test_uses_team_email_as_bcc(self, app):
        with app.app_context():
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            app.config["TEAM_EMAIL"] = "team@example.com"
            sug = _make_suggestion()

            with patch("app.services.email.service.send_email", return_value=True) as mock_send, \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"):
                send_suggestion_confirmation_email(sug)
        kwargs = mock_send.call_args.kwargs
        assert kwargs.get("bcc") == ["team@example.com"]

    def test_exception_returns_false(self, app):
        with app.app_context():
            sug = _make_suggestion()
            with patch("app.services.email.service.get_org_name", side_effect=Exception("boom")):
                result = send_suggestion_confirmation_email(sug)
        assert result is False


# ---------------------------------------------------------------------------
# send_admin_notification_email
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("db_session")
class TestSendAdminNotificationEmail:
    def test_no_admin_emails_returns_false(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = []
            sug = _make_suggestion()
            result = send_admin_notification_email(sug)
        assert result is False

    def test_sends_to_admin_emails(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            sug = _make_suggestion()

            with patch("app.services.email.service.send_email", return_value=True) as mock_send, \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"):
                result = send_admin_notification_email(sug)
        assert result is True
        kwargs = mock_send.call_args.kwargs
        assert "admin@example.com" in kwargs["recipients"]

    def test_correction_uses_comparison_table(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            sug = _make_suggestion(is_correction=True)
            sug.indicator = MagicMock()
            sug.indicator.name = "Orig"
            sug.indicator.definition = "D"
            sug.indicator.type = "C"
            sug.indicator.unit = "U"
            sug.indicator.emergency = False
            sug.indicator.related_programs = None
            sug.indicator.sector = None
            sug.indicator.sub_sector = None

            with patch("app.services.email.service.send_email", return_value=True), \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"), \
                 patch("app.services.email.service.create_comparison_table", return_value="<table/>") as mock_ct:
                result = send_admin_notification_email(sug)
        assert result is True
        mock_ct.assert_called_once()

    def test_new_indicator_uses_details(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            sug = _make_suggestion(is_correction=False)

            with patch("app.services.email.service.send_email", return_value=True), \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"), \
                 patch("app.services.email.service.create_new_indicator_details", return_value="<ul/>") as mock_nid:
                result = send_admin_notification_email(sug)
        assert result is True
        mock_nid.assert_called_once()

    def test_exception_returns_false(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            sug = _make_suggestion()
            with patch("app.services.email.service.get_org_name", side_effect=Exception("crash")):
                result = send_admin_notification_email(sug)
        assert result is False

    def test_uses_base_url_for_admin_link(self, app):
        with app.app_context():
            app.config["ADMIN_EMAILS"] = ["admin@example.com"]
            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            app.config["BASE_URL"] = "https://app.example.com"
            sug = _make_suggestion()
            sug.id = 42

            with patch("app.services.email.service.send_email", return_value=True), \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"), \
                 patch("app.services.email.service.render_admin_email_template") as mock_render:
                mock_render.return_value = "<html>content</html>"
                send_admin_notification_email(sug)

        call_kwargs = mock_render.call_args.kwargs
        admin_url = call_kwargs.get("admin_url", "")
        assert "https://app.example.com" in admin_url
        assert admin_url.endswith("/admin/indicator_suggestions/view/42")


# ---------------------------------------------------------------------------
# send_welcome_email
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("db_session")
class TestSendWelcomeEmail:
    def test_no_user_returns_false(self, app):
        with app.app_context():
            result = send_welcome_email(None)
        assert result is False

    def test_no_email_returns_false(self, app):
        with app.app_context():
            user = MagicMock()
            user.email = None
            result = send_welcome_email(user)
        assert result is False

    def test_sends_welcome_email_successfully(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            app.config.setdefault("MAIL_NOREPLY_SENDER", "noreply@example.com")

            with patch("app.services.email.service.send_email", return_value=True) as mock_send, \
                 patch("app.services.email.service._create_welcome_notification", return_value=99) as mock_create_notif, \
                 patch("app.services.email.service.log_email_attempt") as mock_log, \
                 patch("app.services.email.service.mark_email_sent") as mock_sent, \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"):
                mock_log.return_value = MagicMock(id=1)
                result = send_welcome_email(user)

        assert result is True
        mock_create_notif.assert_called_once()
        mock_log.assert_called_once()
        assert mock_log.call_args[0][0] == 99
        mock_send.assert_called_once()
        mock_sent.assert_called_once_with(1)

    def test_creates_notification_and_links_email_log(self, app):
        from app.models import Notification, EmailDeliveryLog
        from app.models.enums import NotificationType

        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
            app.config.setdefault("MAIL_NOREPLY_SENDER", "noreply@example.com")

            with patch("app.services.email.service.send_email", return_value=True), \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_notification_templates", return_value={
                     "email_template_welcome": {
                         "title": "Welcome to {{org_name}}!",
                         "message": "Hello from {{org_name}}",
                         "priority": "normal",
                     }
                 }), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"):
                result = send_welcome_email(user)

            assert result is True
            notification = Notification.query.filter_by(
                user_id=user.id,
                notification_type=NotificationType.account_welcome,
            ).first()
            assert notification is not None
            assert "IFRC" in notification.title

            email_log = EmailDeliveryLog.query.filter_by(notification_id=notification.id).first()
            assert email_log is not None
            assert email_log.user_id == user.id
            assert email_log.status == "sent"

    def test_send_failure_marks_email_failed(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"

            with patch("app.services.email.service.send_email", return_value=False), \
                 patch("app.services.email.service._create_welcome_notification", return_value=99), \
                 patch("app.services.email.service.log_email_attempt") as mock_log, \
                 patch("app.services.email.service.mark_email_failed") as mock_failed, \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"):
                mock_log.return_value = MagicMock(id=2)
                result = send_welcome_email(user)

        assert result is False
        mock_failed.assert_called_once()

    def test_send_exception_marks_email_failed(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"

            with patch("app.services.email.service.send_email", side_effect=Exception("SMTP error")), \
                 patch("app.services.email.service._create_welcome_notification", return_value=99), \
                 patch("app.services.email.service.log_email_attempt") as mock_log, \
                 patch("app.services.email.service.mark_email_failed") as mock_failed, \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"):
                mock_log.return_value = MagicMock(id=3)
                result = send_welcome_email(user)

        assert result is False
        mock_failed.assert_called_once()

    def test_uses_name_from_email_when_no_name(self, app):
        with app.app_context():
            user = _make_user()
            user.name = None
            user.email = "johndoe@example.com"
            db.session.add(user)
            db.session.commit()

            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"

            with patch("app.services.email.service.send_email", return_value=True), \
                 patch("app.services.email.service._create_welcome_notification", return_value=1), \
                 patch("app.services.email.service.log_email_attempt", return_value=MagicMock(id=1)), \
                 patch("app.services.email.service.mark_email_sent"), \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"), \
                 patch("app.services.email.service.render_admin_email_template") as mock_render:
                mock_render.return_value = "<html>hi</html>"
                send_welcome_email(user)

        # user_name derived from email prefix 'johndoe'
        call_kwargs = mock_render.call_args.kwargs
        assert call_kwargs.get("user_name") == "johndoe"

    def test_user_name_used_when_available(self, app):
        with app.app_context():
            user = _make_user(name="Alice Smith")
            db.session.add(user)
            db.session.commit()

            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"

            with patch("app.services.email.service.send_email", return_value=True), \
                 patch("app.services.email.service._create_welcome_notification", return_value=1), \
                 patch("app.services.email.service.log_email_attempt", return_value=MagicMock(id=1)), \
                 patch("app.services.email.service.mark_email_sent"), \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"), \
                 patch("app.services.email.service.render_admin_email_template") as mock_render:
                mock_render.return_value = "<html>hi</html>"
                send_welcome_email(user)

        call_kwargs = mock_render.call_args.kwargs
        assert call_kwargs.get("user_name") == "Alice Smith"

    def test_outer_exception_returns_false(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            with patch("app.services.email.service.get_org_name", side_effect=Exception("crash")):
                result = send_welcome_email(user)
        assert result is False

    def test_sends_to_user_email(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"

            with patch("app.services.email.service.send_email", return_value=True) as mock_send, \
                 patch("app.services.email.service._create_welcome_notification", return_value=1), \
                 patch("app.services.email.service.log_email_attempt", return_value=MagicMock(id=1)), \
                 patch("app.services.email.service.mark_email_sent"), \
                 patch("app.services.email.service.get_email_template", side_effect=lambda k, d: d), \
                 patch("app.services.email.service.get_org_name", return_value="IFRC"), \
                 patch("app.services.email.service.get_org_copyright_year", return_value="2024"):
                send_welcome_email(user)

        kwargs = mock_send.call_args.kwargs
        assert user.email in kwargs["recipients"]
