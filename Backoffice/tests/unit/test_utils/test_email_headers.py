import base64
from unittest.mock import patch

import pytest
from flask import Flask

from app.services.email.client import send_email
from app.utils.email_headers import (
    filter_valid_addresses,
    sanitize_filename,
    sanitize_header_value,
    sanitize_sender,
    sanitize_subject,
    validate_email_address,
)


@pytest.fixture
def email_app():
    app = Flask(__name__)
    app.config["EMAIL_API_KEY"] = "k"
    app.config["EMAIL_API_URL"] = "https://email-api.example.com/send"
    app.config["MAIL_DEFAULT_SENDER"] = "sender@example.com"
    app.config["MAIL_NOREPLY_SENDER"] = "noreply@example.com"
    return app


@pytest.mark.parametrize(
    "raw",
    [
        "Hello\r\nBcc: evil@example.com",
        "Hello\nBcc: evil@example.com",
        "Hello\rBcc: evil@example.com",
        "Hello\x00Bcc: evil@example.com",
        "Hello\u2028Bcc: evil@example.com",
        "Hello\x85Bcc: evil@example.com",
        "Hello\x0bBcc: evil@example.com",
    ],
)
def test_sanitize_header_value_removes_line_breaks(raw):
    out = sanitize_header_value(raw)
    assert not any(c in out for c in "\r\n\x00\x0b\x85\u2028")
    assert out.startswith("Hello")


def test_sanitize_header_value_keeps_unicode_and_collapses_space():
    assert sanitize_header_value("  Rapport   d'activité \t 2026  ") == "Rapport d'activité 2026"


def test_sanitize_header_value_truncates_and_handles_none():
    assert sanitize_header_value(None) == ""
    assert len(sanitize_header_value("a" * 5000)) == 998
    assert len(sanitize_subject("b" * 5000)) == 300


def test_sanitize_filename_strips_paths_quotes_and_controls():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename('a"b\r\n.pdf') == "a'b .pdf"
    assert sanitize_filename("") == "attachment"
    assert sanitize_filename(None) == "attachment"


@pytest.mark.parametrize(
    "addr",
    [
        "a@example.com",
        "first.last+tag@sub.example.org",
        "o'brien@example.com",
        "user@bücher.example",
    ],
)
def test_validate_email_address_accepts(addr):
    assert validate_email_address(addr) == addr


@pytest.mark.parametrize(
    "addr",
    [
        None,
        "",
        "   ",
        "plainstring",
        "a@b",
        "a@@example.com",
        "a@example.com\r\nBcc: evil@example.com",
        "a@example.com\nBcc: evil@example.com",
        "a@example.com,evil@example.com",
        "a@example.com;evil@example.com",
        "a@example.com evil@example.com",
        "Name <a@example.com>",
        '"a"@example.com',
        "a(comment)@example.com",
        ".a@example.com",
        "a.@example.com",
        "a..b@example.com",
        "a@-example.com",
        "a@example..com",
        "a@example.com.",
        "a@exa mple.com",
        "a\x00@example.com",
        "x" * 65 + "@example.com",
        "a@" + "x" * 260 + ".com",
    ],
)
def test_validate_email_address_rejects(addr):
    assert validate_email_address(addr) is None


def test_sanitize_sender_allows_display_name_and_rejects_injection():
    assert sanitize_sender("noreply@example.com") == "noreply@example.com"
    assert sanitize_sender("Backoffice <noreply@example.com>") == '"Backoffice" <noreply@example.com>'
    assert sanitize_sender("Evil\r\nBcc: x@y.com <noreply@example.com>") is None
    assert sanitize_sender("noreply@example.com\r\nBcc: x@y.com") is None
    assert sanitize_sender("not an address") is None
    assert sanitize_sender("") is None


def test_filter_valid_addresses_splits():
    valid, rejected = filter_valid_addresses(["a@example.com", "bad", "b@example.com,c@example.com"])
    assert valid == ["a@example.com"]
    assert len(rejected) == 2


def _payload_field(mock_post, key):
    payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1]["json"]
    return base64.b64decode(payload[key]).decode("utf-8")


def test_send_email_sanitizes_subject_and_drops_bad_recipients(email_app):
    with patch("app.services.email.client._send_via_ifrc", return_value=True) as mock_send:
        with email_app.app_context():
            ok = send_email(
                "Hi\r\nBcc: evil@example.com",
                ["good@example.com", "bad@example.com\r\nBcc: evil@example.com", "x@example.com,y@example.com"],
                "<p>hi</p>",
                cc=["Name <cc@example.com>"],
                bcc="bcc@example.com",
            )
    assert ok is True
    kwargs = mock_send.call_args.kwargs
    assert "\r" not in kwargs["subject"] and "\n" not in kwargs["subject"]
    assert kwargs["recipients"] == ["good@example.com"]
    assert kwargs["cc"] == []
    assert kwargs["bcc"] == ["bcc@example.com"]


def test_send_email_all_recipients_invalid_fails_without_sending(email_app):
    with patch("app.services.email.client._send_via_ifrc") as mock_send:
        with email_app.app_context():
            failure = []
            ok = send_email("s", ["nope", "a@b"], "<p>x</p>", _failure_info=failure)
    assert ok is False
    assert failure[-1]["code"] == "no_recipients"
    mock_send.assert_not_called()


def test_send_email_rejects_invalid_sender(email_app):
    with patch("app.services.email.client._send_via_ifrc") as mock_send:
        with email_app.app_context():
            failure = []
            ok = send_email(
                "s", ["a@example.com"], "<p>x</p>",
                sender="x@example.com\r\nBcc: evil@example.com",
                _failure_info=failure,
            )
    assert ok is False
    assert failure[-1]["code"] == "invalid_sender"
    mock_send.assert_not_called()


def test_send_email_string_recipient_is_not_split_into_characters(email_app):
    with patch("app.services.email.client._send_via_ifrc", return_value=True) as mock_send:
        with email_app.app_context():
            send_email("s", "solo@example.com", "<p>x</p>")
    assert mock_send.call_args.kwargs["recipients"] == ["solo@example.com"]


def test_ifrc_payload_fields_are_sanitized(email_app):
    from app.services.email import client

    class _Resp:
        status_code = 200
        text = '{"guid": "g"}'
        headers = {}
        content = b'{"guid": "g"}'

        def json(self):
            return {"guid": "g"}

    with patch.object(client.requests, "post", return_value=_Resp()) as mock_post:
        with email_app.app_context():
            client._send_via_ifrc(
                subject="A\r\nBcc: e@example.com",
                sender="sender@example.com",
                recipients=["r@example.com"],
                html="<p>hi</p>",
                text=None,
                reply_to=None,
                cc=[],
                bcc=[],
                attachments=[("../evil\r\n.txt", b"x", "text/plain")],
            )
    subject = _payload_field(mock_post, "SubjectAsBase64")
    assert "\r" not in subject and "\n" not in subject
    payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1]["json"]
    fname = base64.b64decode(payload["Attachments"][0]["FileNameAsBase64"]).decode()
    assert "\n" not in fname and "/" not in fname
