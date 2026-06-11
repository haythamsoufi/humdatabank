"""
Comprehensive tests for app/services/email/protection.py.

Covers:
- _normalize_emails
- check_email_recipients_allowed
- EmailProtectionResult dataclass
"""
import pytest
from flask import Flask
from unittest.mock import patch

from app.services.email.protection import (
    check_email_recipients_allowed,
    _normalize_emails,
    EmailProtectionResult,
)


@pytest.fixture
def prot_app():
    """Minimal Flask app for protection tests."""
    app = Flask(__name__)
    app.config["FLASK_CONFIG"] = "testing"
    return app


# ---------------------------------------------------------------------------
# _normalize_emails
# ---------------------------------------------------------------------------

class TestNormalizeEmails:
    def test_empty_list(self):
        assert _normalize_emails([]) == []

    def test_none_input(self):
        assert _normalize_emails(None) == []

    def test_basic_emails(self):
        result = _normalize_emails(["Alice@Example.COM", "BOB@TEST.ORG"])
        assert result == ["alice@example.com", "bob@test.org"]

    def test_strips_whitespace(self):
        result = _normalize_emails(["  user@example.com  "])
        assert result == ["user@example.com"]

    def test_skips_empty_strings(self):
        result = _normalize_emails(["", "  ", "user@example.com"])
        assert result == ["user@example.com"]

    def test_skips_none_values(self):
        result = _normalize_emails([None, "user@example.com"])
        assert result == ["user@example.com"]

    def test_preserves_order(self):
        emails = ["c@x.com", "a@x.com", "b@x.com"]
        result = _normalize_emails(emails)
        assert result == ["c@x.com", "a@x.com", "b@x.com"]

    def test_multiple_mixed_case(self):
        result = _normalize_emails(["USER@DOMAIN.COM"])
        assert result == ["user@domain.com"]

    def test_generator_input(self):
        def gen():
            yield "A@B.COM"
            yield "C@D.ORG"
        result = _normalize_emails(gen())
        assert "a@b.com" in result
        assert "c@d.org" in result


# ---------------------------------------------------------------------------
# EmailProtectionResult dataclass
# ---------------------------------------------------------------------------

class TestEmailProtectionResult:
    def test_is_frozen(self):
        r = EmailProtectionResult(
            enabled=False,
            environment="testing",
            allowed=[],
            requested=["a@b.com"],
            allowed_requested=["a@b.com"],
            blocked_requested=[],
            reason=None,
        )
        with pytest.raises((AttributeError, TypeError)):
            r.enabled = True  # type: ignore

    def test_fields(self):
        r = EmailProtectionResult(
            enabled=True,
            environment="production",
            allowed=["safe@example.com"],
            requested=["x@x.com"],
            allowed_requested=["x@x.com"],
            blocked_requested=[],
            reason="test",
        )
        assert r.enabled is True
        assert r.environment == "production"
        assert r.allowed == ["safe@example.com"]
        assert r.reason == "test"


# ---------------------------------------------------------------------------
# check_email_recipients_allowed
# ---------------------------------------------------------------------------

class TestCheckEmailRecipientsAllowed:
    def test_always_enabled_false(self, prot_app):
        with prot_app.app_context():
            result = check_email_recipients_allowed(["user@example.com"])
        assert result.enabled is False

    def test_all_emails_allowed(self, prot_app):
        emails = ["user1@example.com", "user2@test.org"]
        with prot_app.app_context():
            result = check_email_recipients_allowed(emails)
        assert result.allowed_requested == ["user1@example.com", "user2@test.org"]
        assert result.blocked_requested == []

    def test_empty_list(self, prot_app):
        with prot_app.app_context():
            result = check_email_recipients_allowed([])
        assert result.allowed_requested == []
        assert result.blocked_requested == []
        assert result.requested == []

    def test_reason_is_none(self, prot_app):
        with prot_app.app_context():
            result = check_email_recipients_allowed(["x@y.com"])
        assert result.reason is None

    def test_allowed_list_is_empty(self, prot_app):
        with prot_app.app_context():
            result = check_email_recipients_allowed(["x@y.com"])
        assert result.allowed == []

    def test_emails_normalized_to_lowercase(self, prot_app):
        with prot_app.app_context():
            result = check_email_recipients_allowed(["USER@EXAMPLE.COM"])
        assert "user@example.com" in result.requested
        assert "user@example.com" in result.allowed_requested

    def test_environment_set_from_config(self, prot_app):
        prot_app.config["FLASK_CONFIG"] = "production"
        with prot_app.app_context():
            result = check_email_recipients_allowed(["a@b.com"])
        assert result.environment == "production"

    def test_none_input(self, prot_app):
        with prot_app.app_context():
            result = check_email_recipients_allowed(None)
        assert result.allowed_requested == []
        assert result.blocked_requested == []

    def test_strips_whitespace_from_emails(self, prot_app):
        with prot_app.app_context():
            result = check_email_recipients_allowed(["  admin@example.com  "])
        assert "admin@example.com" in result.allowed_requested

    def test_multiple_emails(self, prot_app):
        emails = [f"user{i}@example.com" for i in range(10)]
        with prot_app.app_context():
            result = check_email_recipients_allowed(emails)
        assert len(result.allowed_requested) == 10
        assert len(result.blocked_requested) == 0

    def test_missing_flask_config(self):
        app = Flask(__name__)
        # No FLASK_CONFIG set
        with app.app_context():
            result = check_email_recipients_allowed(["a@b.com"])
        assert result.environment == ""

    def test_result_requested_matches_normalized_input(self, prot_app):
        with prot_app.app_context():
            result = check_email_recipients_allowed(["A@B.COM", "C@D.ORG"])
        assert result.requested == ["a@b.com", "c@d.org"]
