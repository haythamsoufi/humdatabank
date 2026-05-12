"""Email send failures create security events (without recursion on alert send)."""

import pytest
from unittest.mock import MagicMock, patch
from flask import Flask

from app.services.email.client import send_email


@pytest.fixture
def email_app():
    """Minimal app context (no DB) for exercising send_email + security hook."""
    app = Flask(__name__)
    app.config["EMAIL_API_KEY"] = "test-key"
    app.config["EMAIL_API_URL"] = "https://email-api.example.com/send"
    app.config["MAIL_DEFAULT_SENDER"] = "sender@example.com"
    app.config["MAIL_NOREPLY_SENDER"] = "noreply@example.com"
    return app


@patch("app.services.security.monitoring.SecurityMonitor.log_security_event")
@patch("app.services.email.client.requests.post")
def test_ifrc_http_error_records_security_event(mock_post, mock_log_security, email_app):
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "bad request"
    mock_resp.headers = {}
    mock_resp.content = b"bad request"
    mock_post.return_value = mock_resp

    with email_app.app_context():
        failure: list = []
        ok = send_email(
            subject="Hello",
            recipients=["user@example.com"],
            html="<p>Hi</p>",
            _failure_info=failure,
        )

    assert ok is False
    assert failure and failure[-1].get("code") == "email_api_http_error"
    mock_log_security.assert_called_once()
    call_kw = mock_log_security.call_args.kwargs
    assert call_kw["event_type"] == "email_delivery_failure"
    assert call_kw["severity"] == "high"
    assert call_kw["notify_admins"] is True


@patch("app.services.security.monitoring.SecurityMonitor.log_security_event")
@patch("app.services.email.client.requests.post")
def test_suppress_flag_skips_security_event(mock_post, mock_log_security, email_app):
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.text = "unavailable"
    mock_resp.headers = {}
    mock_resp.content = b"unavailable"
    mock_post.return_value = mock_resp

    with email_app.app_context():
        ok = send_email(
            subject="Alert",
            recipients=["admin@example.com"],
            html="<p>x</p>",
            _failure_info=[],
            _suppress_email_failure_security_event=True,
        )

    assert ok is False
    mock_log_security.assert_not_called()
