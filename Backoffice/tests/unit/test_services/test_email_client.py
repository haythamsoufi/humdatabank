"""
Comprehensive tests for app/services/email/client.py.

Covers:
- Helper utilities: _b64_utf8, _to_list, _redact_email_api_url_for_logs
- _email_api_edge_headers_for_log
- _email_api_response_body_metrics
- _email_api_waf_vnet_triage_hint
- _ifrc_envelope_to_cc_bcc
- _ifrc_http_error_diag
- _is_production_flask_config
- _failure_warrants_security_event
- _maybe_record_email_delivery_failure
- _filter_recipients_for_environment
- send_email (all branches)
- _send_via_ifrc (all branches)
"""
import os
import base64
import pytest
from unittest.mock import patch, MagicMock, call
from flask import Flask

from app.services.email.client import (
    _b64_utf8,
    _to_list,
    _redact_email_api_url_for_logs,
    _email_api_edge_headers_for_log,
    _email_api_response_body_metrics,
    _email_api_waf_vnet_triage_hint,
    _ifrc_envelope_to_cc_bcc,
    _ifrc_http_error_diag,
    _is_production_flask_config,
    _failure_warrants_security_event,
    _maybe_record_email_delivery_failure,
    _filter_recipients_for_environment,
    send_email,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def email_app():
    app = Flask(__name__)
    app.config["EMAIL_API_KEY"] = "test-key-abc"
    app.config["EMAIL_API_URL"] = "https://email-api.example.com/send"
    app.config["MAIL_DEFAULT_SENDER"] = "sender@example.com"
    app.config["MAIL_NOREPLY_SENDER"] = "noreply@example.com"
    return app


@pytest.fixture
def email_app_prod(email_app):
    email_app.config["FLASK_CONFIG"] = "production"
    return email_app


# ---------------------------------------------------------------------------
# _b64_utf8
# ---------------------------------------------------------------------------

class TestB64Utf8:
    def test_basic_string(self):
        result = _b64_utf8("hello")
        assert result == base64.b64encode(b"hello").decode("utf-8")

    def test_unicode_string(self):
        text = "héllo"
        result = _b64_utf8(text)
        assert result == base64.b64encode(text.encode("utf-8")).decode("utf-8")

    def test_empty_string(self):
        result = _b64_utf8("")
        assert result == ""

    def test_roundtrip(self):
        original = "test@example.com"
        encoded = _b64_utf8(original)
        decoded = base64.b64decode(encoded).decode("utf-8")
        assert decoded == original


# ---------------------------------------------------------------------------
# _to_list
# ---------------------------------------------------------------------------

class TestToList:
    def test_none_returns_empty(self):
        assert _to_list(None) == []

    def test_empty_iterable(self):
        assert _to_list([]) == []

    def test_strips_whitespace(self):
        assert _to_list(["  a@b.com  "]) == ["a@b.com"]

    def test_filters_empty_strings(self):
        assert _to_list(["", " ", "a@b.com"]) == ["a@b.com"]

    def test_converts_to_strings(self):
        result = _to_list([1, "a@b.com"])
        assert "1" in result
        assert "a@b.com" in result

    def test_generator_input(self):
        result = _to_list(e for e in ["a@b.com", "c@d.com"])
        assert result == ["a@b.com", "c@d.com"]


# ---------------------------------------------------------------------------
# _redact_email_api_url_for_logs
# ---------------------------------------------------------------------------

class TestRedactEmailApiUrlForLogs:
    def test_redacts_apiKey(self):
        url = "https://api.example.com/send?apiKey=secret123"
        result = _redact_email_api_url_for_logs(url)
        assert "secret123" not in result
        assert "***REDACTED***" in result

    def test_redacts_apikey_lowercase(self):
        url = "https://api.example.com/send?apikey=secret"
        result = _redact_email_api_url_for_logs(url)
        assert "secret" not in result
        assert "***REDACTED***" in result

    def test_no_apikey_unchanged(self):
        url = "https://api.example.com/send?other=value"
        result = _redact_email_api_url_for_logs(url)
        assert "value" in result

    def test_empty_url_returns_as_is(self):
        assert _redact_email_api_url_for_logs("") == ""

    def test_none_url(self):
        assert _redact_email_api_url_for_logs(None) is None

    def test_url_without_query(self):
        url = "https://api.example.com/send"
        assert _redact_email_api_url_for_logs(url) == url

    def test_preserves_other_params(self):
        url = "https://api.example.com/send?apiKey=secret&other=keep"
        result = _redact_email_api_url_for_logs(url)
        assert "keep" in result
        assert "secret" not in result

    def test_unparseable_url(self):
        # Simulate urlparse exception
        with patch("app.services.email.client.urlparse", side_effect=Exception("bad")):
            result = _redact_email_api_url_for_logs("http://example.com?apiKey=x")
        assert result == "<email_api_url_unparseable>"


# ---------------------------------------------------------------------------
# _email_api_edge_headers_for_log
# ---------------------------------------------------------------------------

class TestEmailApiEdgeHeadersForLog:
    def _make_resp(self, headers):
        r = MagicMock()
        r.headers = headers
        return r

    def test_returns_none_matched_when_no_matching_headers(self):
        resp = self._make_resp({"X-Foo": "bar"})
        result = _email_api_edge_headers_for_log(resp)
        assert "none_matched_whitelist" in result

    def test_includes_server_header(self):
        resp = self._make_resp({"server": "nginx"})
        result = _email_api_edge_headers_for_log(resp)
        assert "server" in result.lower()
        assert "nginx" in result

    def test_includes_x_azure_ref(self):
        resp = self._make_resp({"x-azure-ref": "123"})
        result = _email_api_edge_headers_for_log(resp)
        assert "123" in result

    def test_truncates_long_values(self):
        long_value = "x" * 300
        resp = self._make_resp({"server": long_value})
        result = _email_api_edge_headers_for_log(resp)
        assert "…" in result

    def test_sanitizes_newlines(self):
        resp = self._make_resp({"server": "nginx\nevil"})
        result = _email_api_edge_headers_for_log(resp)
        assert "\n" not in result

    def test_includes_x_ms_prefix(self):
        resp = self._make_resp({"x-ms-request-id": "req123"})
        result = _email_api_edge_headers_for_log(resp)
        assert "req123" in result


# ---------------------------------------------------------------------------
# _email_api_response_body_metrics
# ---------------------------------------------------------------------------

class TestEmailApiResponseBodyMetrics:
    def test_returns_tuple(self):
        r = MagicMock()
        r.content = b"hello"
        r.headers = {"Content-Type": "application/json; charset=utf-8"}
        r.text = "hello"
        raw_len, ct, text_len = _email_api_response_body_metrics(r)
        assert raw_len == 5
        assert ct == "application/json"
        assert text_len == 5

    def test_empty_content(self):
        r = MagicMock()
        r.content = b""
        r.headers = {}
        r.text = ""
        raw_len, ct, text_len = _email_api_response_body_metrics(r)
        assert raw_len == 0
        assert ct == "missing"

    def test_content_exception_returns_minus_one(self):
        r = MagicMock()
        type(r).content = property(lambda self: (_ for _ in ()).throw(Exception("bad")))
        r.headers = {}
        r.text = ""
        raw_len, ct, text_len = _email_api_response_body_metrics(r)
        assert raw_len == -1

    def test_text_exception_returns_minus_one(self):
        r = MagicMock()
        r.content = b"x"
        r.headers = {}
        type(r).text = property(lambda self: (_ for _ in ()).throw(Exception("bad")))
        raw_len, ct, text_len = _email_api_response_body_metrics(r)
        assert text_len == -1


# ---------------------------------------------------------------------------
# _email_api_waf_vnet_triage_hint
# ---------------------------------------------------------------------------

class TestEmailApiWafVnetTriageHint:
    def test_success_range_returns_compare_hint(self):
        result = _email_api_waf_vnet_triage_hint(200, 100, 50, "application/json")
        assert "compare_envs" in result

    def test_empty_body_400_hint(self):
        result = _email_api_waf_vnet_triage_hint(400, 0, 0, "application/json")
        assert "empty_response_body" in result

    def test_html_body_400_hint(self):
        result = _email_api_waf_vnet_triage_hint(400, 100, 50, "text/html")
        assert "HTML_response_body" in result

    def test_403_rate_limit_hint(self):
        result = _email_api_waf_vnet_triage_hint(403, 0, 0, "application/json")
        assert "edge_rate_limit" in result

    def test_always_contains_vnet_hint(self):
        result = _email_api_waf_vnet_triage_hint(500, 10, 10, "application/json")
        assert "VNet_NSG_NAT" in result

    def test_429_hint(self):
        result = _email_api_waf_vnet_triage_hint(429, 0, 0, "application/json")
        assert "edge_rate_limit" in result


# ---------------------------------------------------------------------------
# _ifrc_envelope_to_cc_bcc
# ---------------------------------------------------------------------------

class TestIfrcEnvelopeToCcBcc:
    def test_single_recipient_no_cc_bcc(self):
        to, cc, bcc = _ifrc_envelope_to_cc_bcc("noreply@x.com", ["user@x.com"], [], [])
        assert to == "user@x.com"
        assert cc == ""
        assert bcc == ""

    def test_multiple_recipients_no_cc_bcc(self):
        to, cc, bcc = _ifrc_envelope_to_cc_bcc("noreply@x.com", ["a@x.com", "b@x.com"], [], [])
        assert to == "noreply@x.com"
        assert cc == ""
        assert "a@x.com" in bcc
        assert "b@x.com" in bcc

    def test_recipients_and_cc(self):
        to, cc, bcc = _ifrc_envelope_to_cc_bcc("noreply@x.com", ["a@x.com"], ["c@x.com"], [])
        assert to == "noreply@x.com"
        assert "c@x.com" in cc
        assert "a@x.com" in bcc

    def test_no_to_only_cc(self):
        to, cc, bcc = _ifrc_envelope_to_cc_bcc("noreply@x.com", [], ["cc@x.com"], [])
        assert to == "noreply@x.com"
        assert "cc@x.com" in cc
        assert bcc == ""

    def test_no_to_only_bcc(self):
        to, cc, bcc = _ifrc_envelope_to_cc_bcc("noreply@x.com", [], [], ["bcc@x.com"])
        assert to == "noreply@x.com"
        assert cc == ""
        assert "bcc@x.com" in bcc

    def test_no_recipients_at_all(self):
        to, cc, bcc = _ifrc_envelope_to_cc_bcc("noreply@x.com", [], [], [])
        assert to == "noreply@x.com"
        assert cc == ""
        assert bcc == ""

    def test_recipients_with_bcc(self):
        to, cc, bcc = _ifrc_envelope_to_cc_bcc("noreply@x.com", ["a@x.com"], [], ["b@x.com"])
        assert to == "noreply@x.com"
        assert "a@x.com" in bcc
        assert "b@x.com" in bcc


# ---------------------------------------------------------------------------
# _ifrc_http_error_diag
# ---------------------------------------------------------------------------

class TestIfrcHttpErrorDiag:
    def test_returns_string(self):
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {}
        payload = {"key": "val"}
        result = _ifrc_http_error_diag(resp, payload, "b64==", "<html>", True, ["r@x.com"], [], [])
        assert isinstance(result, str)
        assert "status=400" in result

    def test_includes_counts(self):
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {}
        result = _ifrc_http_error_diag(resp, {}, "b64", "<p>x</p>", False,
                                       ["a@x.com", "b@x.com"], ["c@x.com"], ["d@x.com"])
        assert "to_n=2" in result
        assert "cc_n=1" in result
        assert "bcc_n=1" in result

    def test_includes_correlation_id_header(self):
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {"X-Request-Id": "corr-123"}
        result = _ifrc_http_error_diag(resp, {}, "b64", "<p>x</p>", True, [], [], [])
        assert "corr-123" in result

    def test_invalid_payload_json(self):
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {}
        result = _ifrc_http_error_diag(resp, {"bad": object()}, "b64", "<p>x</p>", True, [], [], [])
        # Should still return a string
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _is_production_flask_config
# ---------------------------------------------------------------------------

class TestIsProductionFlaskConfig:
    def test_production_returns_true(self):
        with patch.dict(os.environ, {"FLASK_CONFIG": "production"}):
            assert _is_production_flask_config() is True

    def test_testing_returns_false(self):
        with patch.dict(os.environ, {"FLASK_CONFIG": "testing"}):
            assert _is_production_flask_config() is False

    def test_empty_returns_false(self):
        with patch.dict(os.environ, {"FLASK_CONFIG": ""}):
            assert _is_production_flask_config() is False

    def test_production_case_insensitive(self):
        with patch.dict(os.environ, {"FLASK_CONFIG": "PRODUCTION"}):
            assert _is_production_flask_config() is True


# ---------------------------------------------------------------------------
# _failure_warrants_security_event
# ---------------------------------------------------------------------------

class TestFailureWarrantsSecurityEvent:
    def test_http_error_always_warrants(self):
        assert _failure_warrants_security_event({"code": "email_api_http_error"}) is True

    def test_request_error_always_warrants(self):
        assert _failure_warrants_security_event({"code": "email_api_request_error"}) is True

    def test_no_api_key_only_in_prod(self):
        with patch.dict(os.environ, {"FLASK_CONFIG": "testing"}):
            assert _failure_warrants_security_event({"code": "no_email_api_key"}) is False
        with patch.dict(os.environ, {"FLASK_CONFIG": "production"}):
            assert _failure_warrants_security_event({"code": "no_email_api_key"}) is True

    def test_no_sender_only_in_prod(self):
        with patch.dict(os.environ, {"FLASK_CONFIG": "testing"}):
            assert _failure_warrants_security_event({"code": "no_default_sender"}) is False

    def test_no_recipients_does_not_warrant(self):
        assert _failure_warrants_security_event({"code": "no_recipients"}) is False

    def test_empty_dict_returns_false(self):
        assert _failure_warrants_security_event({}) is False

    def test_none_dict_returns_false(self):
        assert _failure_warrants_security_event(None) is False


# ---------------------------------------------------------------------------
# _maybe_record_email_delivery_failure
# ---------------------------------------------------------------------------

class TestMaybeRecordEmailDeliveryFailure:
    def test_suppressed_skips(self, email_app):
        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event") as mock_log:
            with email_app.app_context():
                from app.services.email.client import _maybe_record_email_delivery_failure
                _maybe_record_email_delivery_failure(
                    "subj", ["r@x.com"],
                    {"code": "email_api_http_error"},
                    suppress_security_hook=True,
                )
        mock_log.assert_not_called()

    def test_security_event_recorded_for_http_error(self, email_app):
        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event") as mock_log:
            with email_app.app_context():
                from app.services.email.client import _maybe_record_email_delivery_failure
                _maybe_record_email_delivery_failure(
                    "subj", ["r@x.com"],
                    {"code": "email_api_http_error", "http_status": 400, "response_excerpt": "bad"},
                    suppress_security_hook=False,
                )
        mock_log.assert_called_once()

    def test_security_event_skipped_for_non_warranted_code(self, email_app):
        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event") as mock_log:
            with email_app.app_context():
                from app.services.email.client import _maybe_record_email_delivery_failure
                _maybe_record_email_delivery_failure(
                    "subj", [],
                    {"code": "no_recipients"},
                    suppress_security_hook=False,
                )
        mock_log.assert_not_called()

    def test_security_monitor_import_exception_swallowed(self, email_app):
        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event",
                   side_effect=Exception("crash")):
            with email_app.app_context():
                from app.services.email.client import _maybe_record_email_delivery_failure
                # Should not raise
                _maybe_record_email_delivery_failure(
                    "subj", ["r@x.com"],
                    {"code": "email_api_http_error"},
                    suppress_security_hook=False,
                )


# ---------------------------------------------------------------------------
# _filter_recipients_for_environment
# ---------------------------------------------------------------------------

class TestFilterRecipientsForEnvironment:
    def test_production_skips_filter(self, email_app_prod):
        with email_app_prod.app_context():
            email_app_prod.config["ALLOWED_EMAIL_RECIPIENTS_DEV"] = ["allowed@x.com"]
            r, cc, bcc = _filter_recipients_for_environment(
                ["any@x.com"], ["cc@x.com"], ["bcc@x.com"]
            )
        assert "any@x.com" in r

    def test_no_allowlist_returns_all(self, email_app):
        email_app.config["ALLOWED_EMAIL_RECIPIENTS_DEV"] = []
        with email_app.app_context():
            r, cc, bcc = _filter_recipients_for_environment(
                ["a@x.com", "b@x.com"], [], []
            )
        assert "a@x.com" in r
        assert "b@x.com" in r

    def test_allowlist_filters_recipients(self, email_app):
        email_app.config["ALLOWED_EMAIL_RECIPIENTS_DEV"] = ["allowed@x.com"]
        with email_app.app_context():
            r, cc, bcc = _filter_recipients_for_environment(
                ["allowed@x.com", "blocked@x.com"], [], []
            )
        assert "allowed@x.com" in r
        assert "blocked@x.com" not in r

    def test_allowlist_filters_cc_and_bcc(self, email_app):
        email_app.config["ALLOWED_EMAIL_RECIPIENTS_DEV"] = ["a@x.com"]
        with email_app.app_context():
            r, cc, bcc = _filter_recipients_for_environment(
                [], ["a@x.com", "b@x.com"], ["c@x.com"]
            )
        assert "a@x.com" in cc
        assert "b@x.com" not in cc
        assert bcc == []

    def test_allowlist_case_insensitive(self, email_app):
        email_app.config["ALLOWED_EMAIL_RECIPIENTS_DEV"] = ["USER@X.COM"]
        with email_app.app_context():
            r, cc, bcc = _filter_recipients_for_environment(["user@x.com"], [], [])
        assert "user@x.com" in r

    def test_none_allowlist_returns_all(self, email_app):
        email_app.config["ALLOWED_EMAIL_RECIPIENTS_DEV"] = None
        with email_app.app_context():
            r, cc, bcc = _filter_recipients_for_environment(["a@x.com"], [], [])
        assert "a@x.com" in r


# ---------------------------------------------------------------------------
# send_email
# ---------------------------------------------------------------------------

class TestSendEmail:
    def test_no_recipients_returns_false(self, email_app):
        with email_app.app_context():
            failure = []
            ok = send_email("subj", [], "<p>hi</p>", _failure_info=failure)
        assert ok is False
        assert failure[-1]["code"] == "no_recipients"

    def test_no_default_sender_returns_false(self, email_app):
        email_app.config.pop("MAIL_DEFAULT_SENDER", None)
        email_app.config["MAIL_DEFAULT_SENDER"] = None
        with email_app.app_context():
            failure = []
            ok = send_email("subj", ["r@x.com"], "<p>hi</p>", _failure_info=failure)
        assert ok is False
        assert failure[-1]["code"] == "no_default_sender"

    def test_all_filtered_out_returns_false(self, email_app):
        email_app.config["ALLOWED_EMAIL_RECIPIENTS_DEV"] = ["allowed@x.com"]
        with email_app.app_context():
            filtered = []
            failure = []
            ok = send_email("subj", ["blocked@x.com"], "<p>hi</p>",
                            _filtered_out=filtered, _failure_info=failure)
        assert ok is False
        assert filtered
        assert failure[-1]["code"] == "recipient_allowlist"

    def test_high_importance_adds_prefix(self, email_app):
        with patch("app.services.email.client._send_via_ifrc", return_value=True) as mock_send:
            with email_app.app_context():
                send_email("My Subject", ["r@x.com"], "<p>hi</p>", importance="high")
        args = mock_send.call_args
        assert "[HIGH PRIORITY]" in args.kwargs.get("subject", args[1].get("subject", ""))

    def test_high_importance_not_doubled(self, email_app):
        with patch("app.services.email.client._send_via_ifrc", return_value=True) as mock_send:
            with email_app.app_context():
                send_email("[HIGH PRIORITY] My Subject", ["r@x.com"], "<p>hi</p>", importance="high")
        args = mock_send.call_args
        subject = args.kwargs.get("subject") or args[0][0]
        assert subject.count("[HIGH PRIORITY]") == 1

    def test_urgent_importance_adds_prefix(self, email_app):
        with patch("app.services.email.client._send_via_ifrc", return_value=True) as mock_send:
            with email_app.app_context():
                send_email("My Subject", ["r@x.com"], "<p>hi</p>", importance="urgent")
        args = mock_send.call_args
        subject = args.kwargs.get("subject") or args[0][0]
        assert "[URGENT]" in subject

    def test_urgent_not_doubled(self, email_app):
        with patch("app.services.email.client._send_via_ifrc", return_value=True) as mock_send:
            with email_app.app_context():
                send_email("[URGENT] My Subject", ["r@x.com"], "<p>hi</p>", importance="urgent")
        args = mock_send.call_args
        subject = args.kwargs.get("subject") or args[0][0]
        assert subject.count("[URGENT]") == 1

    def test_normal_importance_no_prefix(self, email_app):
        with patch("app.services.email.client._send_via_ifrc", return_value=True) as mock_send:
            with email_app.app_context():
                send_email("Normal Subject", ["r@x.com"], "<p>hi</p>", importance="normal")
        args = mock_send.call_args
        subject = args.kwargs.get("subject") or args[0][0]
        assert "[HIGH PRIORITY]" not in subject
        assert "[URGENT]" not in subject

    def test_successful_send_returns_true(self, email_app):
        with patch("app.services.email.client._send_via_ifrc", return_value=True):
            with email_app.app_context():
                ok = send_email("subj", ["r@x.com"], "<p>hi</p>")
        assert ok is True

    def test_failed_send_calls_security_event(self, email_app):
        with patch("app.services.email.client._send_via_ifrc", return_value=False):
            with patch("app.services.email.client._maybe_record_email_delivery_failure") as mock_rec:
                with email_app.app_context():
                    failure = [{"code": "email_api_http_error"}]
                    send_email("subj", ["r@x.com"], "<p>hi</p>", _failure_info=failure)
        mock_rec.assert_called_once()

    def test_suppress_flag_passed_through(self, email_app):
        with patch("app.services.email.client._send_via_ifrc", return_value=False):
            with patch("app.services.email.client._maybe_record_email_delivery_failure") as mock_rec:
                with email_app.app_context():
                    failure = [{"code": "email_api_http_error"}]
                    send_email("subj", ["r@x.com"], "<p>hi</p>",
                               _failure_info=failure,
                               _suppress_email_failure_security_event=True)
        call_kwargs = mock_rec.call_args.kwargs
        assert call_kwargs["suppress_security_hook"] is True

    def test_cc_and_bcc_passed_to_ifrc(self, email_app):
        with patch("app.services.email.client._send_via_ifrc", return_value=True) as mock_send:
            with email_app.app_context():
                send_email("subj", ["r@x.com"], "<p>hi</p>",
                           cc=["cc@x.com"], bcc=["bcc@x.com"])
        kwargs = mock_send.call_args.kwargs
        assert "cc@x.com" in kwargs["cc"]
        assert "bcc@x.com" in kwargs["bcc"]


# ---------------------------------------------------------------------------
# _send_via_ifrc
# ---------------------------------------------------------------------------

class TestSendViaIfrc:
    """Tests for _send_via_ifrc via send_email (which calls it internally)."""

    def _mock_success_response(self):
        resp = MagicMock()
        resp.status_code = 202
        resp.text = '"some-guid-1234"'
        resp.headers = {}
        resp.content = b'"some-guid-1234"'
        resp.history = []
        resp.url = "https://email-api.example.com/send?apiKey=***"
        return resp

    def test_success_200(self, email_app):
        resp = self._mock_success_response()
        with patch("app.services.email.client.requests.post", return_value=resp):
            with email_app.app_context():
                ok = send_email("subj", ["r@x.com"], "<p>hi</p>")
        assert ok is True

    def test_success_no_guid_in_response(self, email_app):
        resp = self._mock_success_response()
        resp.text = None
        with patch("app.services.email.client.requests.post", return_value=resp):
            with email_app.app_context():
                ok = send_email("subj", ["r@x.com"], "<p>hi</p>")
        assert ok is True

    def test_missing_api_key(self, email_app):
        email_app.config.pop("EMAIL_API_KEY", None)
        email_app.config["EMAIL_API_KEY"] = None
        with email_app.app_context():
            failure = []
            ok = send_email("subj", ["r@x.com"], "<p>hi</p>", _failure_info=failure)
        assert ok is False
        assert failure[-1]["code"] == "no_email_api_key"

    def test_missing_api_url(self, email_app):
        email_app.config["EMAIL_API_URL"] = ""
        with email_app.app_context():
            failure = []
            ok = send_email("subj", ["r@x.com"], "<p>hi</p>", _failure_info=failure)
        assert ok is False
        assert failure[-1]["code"] == "no_email_api_url"

    def test_empty_html_body_returns_false(self, email_app):
        with email_app.app_context():
            failure = []
            ok = send_email("subj", ["r@x.com"], "   \x00  ", _failure_info=failure)
        assert ok is False
        assert failure[-1]["code"] == "empty_email_body"

    def test_http_400_returns_false_with_failure_info(self, email_app):
        resp = MagicMock()
        resp.status_code = 400
        resp.text = "bad request body"
        resp.content = b"bad request body"
        resp.headers = {}
        resp.history = []
        resp.url = ""
        with patch("app.services.email.client.requests.post", return_value=resp):
            with email_app.app_context():
                failure = []
                ok = send_email("subj", ["r@x.com"], "<p>hi</p>", _failure_info=failure)
        assert ok is False
        assert failure[-1]["code"] == "email_api_http_error"
        assert failure[-1]["http_status"] == 400

    def test_http_401_returns_false(self, email_app):
        resp = MagicMock()
        resp.status_code = 401
        resp.text = "Unauthorized"
        resp.content = b"Unauthorized"
        resp.headers = {}
        resp.history = []
        resp.url = ""
        with patch("app.services.email.client.requests.post", return_value=resp):
            with email_app.app_context():
                ok = send_email("subj", ["r@x.com"], "<p>hi</p>")
        assert ok is False

    def test_http_403_returns_false(self, email_app):
        resp = MagicMock()
        resp.status_code = 403
        resp.text = "Forbidden"
        resp.content = b"Forbidden"
        resp.headers = {}
        resp.history = []
        resp.url = ""
        with patch("app.services.email.client.requests.post", return_value=resp):
            with email_app.app_context():
                ok = send_email("subj", ["r@x.com"], "<p>hi</p>")
        assert ok is False

    def test_http_500_returns_false(self, email_app):
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "Internal Server Error"
        resp.content = b"Internal Server Error"
        resp.headers = {}
        resp.history = []
        resp.url = ""
        with patch("app.services.email.client.requests.post", return_value=resp):
            with email_app.app_context():
                ok = send_email("subj", ["r@x.com"], "<p>hi</p>")
        assert ok is False

    def test_request_exception_returns_false(self, email_app):
        import requests
        with patch("app.services.email.client.requests.post",
                   side_effect=requests.RequestException("timeout")):
            with email_app.app_context():
                failure = []
                ok = send_email("subj", ["r@x.com"], "<p>hi</p>", _failure_info=failure)
        assert ok is False
        assert failure[-1]["code"] == "email_api_request_error"

    def test_api_key_already_in_url(self, email_app):
        email_app.config["EMAIL_API_URL"] = "https://api.example.com/send?apiKey=existing-key"
        resp = self._mock_success_response()
        with patch("app.services.email.client.requests.post", return_value=resp) as mock_post:
            with email_app.app_context():
                ok = send_email("subj", ["r@x.com"], "<p>hi</p>")
        assert ok is True
        called_url = mock_post.call_args[0][0]
        # Should not double-add the key
        assert called_url.count("apiKey=") == 1

    def test_attachments_added_to_payload(self, email_app):
        resp = self._mock_success_response()
        with patch("app.services.email.client.requests.post", return_value=resp) as mock_post:
            with email_app.app_context():
                ok = send_email(
                    "subj", ["r@x.com"], "<p>hi</p>",
                    attachments=[("test.pdf", b"%PDF-1.4 content", "application/pdf")]
                )
        assert ok is True
        json_payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert "Attachments" in json_payload
        assert json_payload["Attachments"][0]["ContentType"] == "application/pdf"

    def test_empty_response_body_fallback(self, email_app):
        resp = MagicMock()
        resp.status_code = 400
        resp.text = ""
        resp.content = b""
        resp.headers = {}
        resp.history = []
        resp.url = ""
        with patch("app.services.email.client.requests.post", return_value=resp):
            with email_app.app_context():
                failure = []
                ok = send_email("subj", ["r@x.com"], "<p>hi</p>", _failure_info=failure)
        assert ok is False
        assert "No response body" in failure[-1].get("response_excerpt", "")

    def test_raw_bytes_fallback_on_empty_text(self, email_app):
        resp = MagicMock()
        resp.status_code = 400
        resp.text = ""
        resp.content = b"\x00\x01\x02"
        resp.headers = {}
        resp.history = []
        resp.url = ""
        with patch("app.services.email.client.requests.post", return_value=resp):
            with email_app.app_context():
                failure = []
                ok = send_email("subj", ["r@x.com"], "<p>hi</p>", _failure_info=failure)
        assert ok is False

    def test_multiple_recipients_uses_bcc_envelope(self, email_app):
        resp = self._mock_success_response()
        with patch("app.services.email.client.requests.post", return_value=resp) as mock_post:
            with email_app.app_context():
                ok = send_email("subj", ["a@x.com", "b@x.com"], "<p>hi</p>")
        assert ok is True
        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        # BccAsBase64 should contain both addresses
        bcc_decoded = base64.b64decode(payload["BccAsBase64"]).decode("utf-8")
        assert "a@x.com" in bcc_decoded
        assert "b@x.com" in bcc_decoded
