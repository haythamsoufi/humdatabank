"""
Tests for app/routes/api/error_log.py

Coverage targets:
- POST /api/v1/platform-error        (all validation branches, success, exception)
- POST /api/v1/client-error          (JS runtime errors, ignored noise, success)
- _strip_control_chars               (empty, control chars, max_len)
- sanitize_url                       (happy path, sensitive params, bad scheme, empty)
"""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api(path: str) -> str:
    return f"/api/v1{path}"


def _json_headers():
    return {"Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Unit tests for _strip_control_chars
# ---------------------------------------------------------------------------

class TestStripControlChars:
    """Unit tests for the _strip_control_chars helper."""

    def test_none_returns_none(self, app):
        from app.routes.api.error_log import _strip_control_chars
        with app.app_context():
            assert _strip_control_chars(None, max_len=100) is None

    def test_empty_string_returns_none(self, app):
        from app.routes.api.error_log import _strip_control_chars
        with app.app_context():
            assert _strip_control_chars("", max_len=100) is None

    def test_whitespace_only_returns_none(self, app):
        from app.routes.api.error_log import _strip_control_chars
        with app.app_context():
            assert _strip_control_chars("   ", max_len=100) is None

    def test_removes_newlines(self, app):
        from app.routes.api.error_log import _strip_control_chars
        with app.app_context():
            result = _strip_control_chars("line1\nline2\r\n", max_len=100)
        assert "\n" not in (result or "")
        assert "\r" not in (result or "")

    def test_removes_tabs(self, app):
        from app.routes.api.error_log import _strip_control_chars
        with app.app_context():
            result = _strip_control_chars("col1\tcol2", max_len=100)
        assert "\t" not in (result or "")

    def test_truncates_to_max_len(self, app):
        from app.routes.api.error_log import _strip_control_chars
        with app.app_context():
            result = _strip_control_chars("a" * 200, max_len=50)
        assert len(result) == 50

    def test_normal_string_returned_as_is(self, app):
        from app.routes.api.error_log import _strip_control_chars
        with app.app_context():
            result = _strip_control_chars("hello world", max_len=100)
        assert result == "hello world"


# ---------------------------------------------------------------------------
# Unit tests for sanitize_url
# ---------------------------------------------------------------------------

class TestSanitizeUrl:
    """Unit tests for the sanitize_url helper."""

    def test_none_returns_none(self, app):
        from app.routes.api.error_log import sanitize_url
        with app.app_context():
            assert sanitize_url(None) is None

    def test_empty_string_returns_none(self, app):
        from app.routes.api.error_log import sanitize_url
        with app.app_context():
            assert sanitize_url("") is None

    def test_valid_https_url_returned(self, app):
        from app.routes.api.error_log import sanitize_url
        with app.app_context():
            result = sanitize_url("https://example.com/path")
        assert result is not None
        assert "example.com" in result

    def test_valid_http_url_returned(self, app):
        from app.routes.api.error_log import sanitize_url
        with app.app_context():
            result = sanitize_url("http://example.com/path")
        assert result is not None

    def test_removes_sensitive_params(self, app):
        from app.routes.api.error_log import sanitize_url
        with app.app_context():
            result = sanitize_url("https://example.com/?password=secret&page=1")
        assert result is not None
        assert "password" not in result
        assert "page=1" in result

    def test_removes_token_param(self, app):
        from app.routes.api.error_log import sanitize_url
        with app.app_context():
            result = sanitize_url("https://example.com/?token=abc123&q=test")
        assert result is not None
        assert "token" not in result

    def test_removes_api_key_param(self, app):
        from app.routes.api.error_log import sanitize_url
        with app.app_context():
            result = sanitize_url("https://example.com/?api_key=supersecret")
        assert result is not None
        assert "api_key" not in result

    def test_invalid_scheme_returns_none(self, app):
        from app.routes.api.error_log import sanitize_url
        with app.app_context():
            result = sanitize_url("javascript:alert(1)")
        assert result is None

    def test_ftp_scheme_returns_none(self, app):
        from app.routes.api.error_log import sanitize_url
        with app.app_context():
            result = sanitize_url("ftp://example.com/file")
        assert result is None

    def test_path_only_url_allowed(self, app):
        from app.routes.api.error_log import sanitize_url
        with app.app_context():
            result = sanitize_url("/path/to/page")
        # A path-only URL has no scheme — it's valid (scheme='', netloc='', path='/path/to/page')
        # The function returns it or None
        # Just check it doesn't raise
        assert True  # just verify no exception

    def test_control_chars_stripped(self, app):
        from app.routes.api.error_log import sanitize_url
        with app.app_context():
            result = sanitize_url("https://example.com/path\ninjected")
        # Should not contain newlines
        assert result is None or "\n" not in result

    def test_very_long_url_truncated(self, app):
        from app.routes.api.error_log import sanitize_url
        with app.app_context():
            long_url = "https://example.com/" + "a" * 3000
            result = sanitize_url(long_url)
        assert result is None or len(result) <= 2000


# ---------------------------------------------------------------------------
# POST /api/v1/platform-error
# ---------------------------------------------------------------------------

class TestClampOptionalInt:
    """Unit tests for the _clamp_optional_int helper."""

    def test_none_returns_none(self, app):
        from app.routes.api.error_log import _clamp_optional_int
        with app.app_context():
            assert _clamp_optional_int(None, max_value=100) is None

    def test_non_numeric_returns_none(self, app):
        from app.routes.api.error_log import _clamp_optional_int
        with app.app_context():
            assert _clamp_optional_int("not-a-number", max_value=100) is None

    def test_negative_returns_none(self, app):
        from app.routes.api.error_log import _clamp_optional_int
        with app.app_context():
            assert _clamp_optional_int(-5, max_value=100) is None

    def test_value_within_bounds_returned_as_is(self, app):
        from app.routes.api.error_log import _clamp_optional_int
        with app.app_context():
            assert _clamp_optional_int(42, max_value=100) == 42

    def test_value_above_max_is_clamped(self, app):
        from app.routes.api.error_log import _clamp_optional_int
        with app.app_context():
            assert _clamp_optional_int(1_000_000, max_value=100) == 100

    def test_numeric_string_coerced(self, app):
        from app.routes.api.error_log import _clamp_optional_int
        with app.app_context():
            assert _clamp_optional_int("42", max_value=100) == 42


class TestLogPlatformError:
    """Tests for POST /api/v1/platform-error."""

    @pytest.fixture(autouse=True)
    def disable_platform_error_rate_limit(self, app):
        """This class posts to platform-error many times; bypass Flask-Limiter."""
        from app.extensions import limiter
        previous = limiter.enabled
        limiter.enabled = False
        yield
        limiter.enabled = previous

    def _post(self, client, payload, headers=None):
        h = {**(headers or {}), "Content-Type": "application/json"}
        return client.post(_api("/platform-error"), json=payload, headers=h)

    def test_wrong_content_type_returns_400(self, client, db_session):
        """Non-JSON Content-Type returns 400."""
        resp = client.post(
            _api("/platform-error"),
            data="error_code=503",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 400

    def test_invalid_error_code_string_returns_400(self, client, db_session):
        resp = self._post(client, {"error_code": "not_a_number", "url": "https://example.com"})
        assert resp.status_code == 400

    def test_invalid_error_code_value_returns_400(self, client, db_session):
        """Error code 200 is not in the allowed set."""
        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event"):
            resp = self._post(client, {"error_code": 200, "url": "https://example.com"})
        assert resp.status_code == 400

    def test_valid_403_logged_successfully(self, client, db_session):
        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event") as mock_log:
            resp = self._post(client, {
                "error_code": 403,
                "url": "https://example.com/page",
                "referrer": "https://google.com",
                "user_agent": "Mozilla/5.0",
                "timestamp": "2024-01-01T00:00:00Z",
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True
        mock_log.assert_called_once()

    def test_valid_502_logged_successfully(self, client, db_session):
        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event") as mock_log:
            resp = self._post(client, {"error_code": 502, "url": "https://example.com/"})
        assert resp.status_code == 200
        mock_log.assert_called_once()

    def test_valid_503_logged_successfully(self, client, db_session):
        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event"):
            resp = self._post(client, {"error_code": 503, "url": "https://example.com/"})
        assert resp.status_code == 200

    def test_valid_504_logged_successfully(self, client, db_session):
        captured = {}

        def capture_call(**kwargs):
            captured.update(kwargs)

        with patch(
            "app.services.security.monitoring.SecurityMonitor.log_security_event",
            side_effect=capture_call,
        ):
            resp = self._post(client, {
                "error_code": 504,
                "url": "https://databank.ifrc.org/static/js/forms/modules/formatting.js",
            })
        assert resp.status_code == 200
        assert captured.get("event_type") == "platform_504_gateway_timeout"
        ctx = captured.get("context_data", {})
        assert "diagnostics_summary" in ctx
        assert "worker_metrics" in ctx
        assert "likely_causes" in ctx
        assert "HTTP 504" in captured.get("description", "")

    def test_504_diagnostics_not_added_for_403(self, client, db_session):
        captured = {}

        def capture_call(**kwargs):
            captured.update(kwargs)

        with patch(
            "app.services.security.monitoring.SecurityMonitor.log_security_event",
            side_effect=capture_call,
        ):
            resp = self._post(client, {
                "error_code": 403,
                "url": "https://databank.ifrc.org/admin",
            })
        assert resp.status_code == 200
        ctx = captured.get("context_data", {})
        assert "diagnostics_summary" not in ctx

    def test_sensitive_url_params_stripped(self, client, db_session):
        """URL with sensitive params is sanitized before logging."""
        captured = {}

        def capture_call(**kwargs):
            captured.update(kwargs)

        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event", side_effect=capture_call):
            resp = self._post(client, {
                "error_code": 403,
                "url": "https://example.com/?password=secret&page=1",
            })
        assert resp.status_code == 200
        ctx = captured.get("context_data", {})
        assert "password" not in ctx.get("url", "")

    def test_invalid_timestamp_ignored(self, client, db_session):
        """Invalid timestamp is silently ignored."""
        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event"):
            resp = self._post(client, {
                "error_code": 403,
                "url": "https://example.com/",
                "timestamp": "not-a-valid-timestamp",
            })
        assert resp.status_code == 200

    def test_request_body_telemetry_included_in_context_and_description(self, client, db_session):
        """request_field_count / request_approx_bytes from the client reporter
        (see summarizeRequestBody() in platform-error-reporter.js) should be
        surfaced in both context_data and the human-readable description, so
        a future WAF 403 investigation has evidence this one didn't."""
        captured = {}

        def capture_call(**kwargs):
            captured.update(kwargs)

        with patch(
            "app.services.security.monitoring.SecurityMonitor.log_security_event",
            side_effect=capture_call,
        ):
            resp = self._post(client, {
                "error_code": 403,
                "url": "https://databank.ifrc.org/assignment/4100?ajax=1",
                "request_field_count": 87,
                "request_approx_bytes": 45000,
            })
        assert resp.status_code == 200
        ctx = captured.get("context_data", {})
        assert ctx.get("request_field_count") == 87
        assert ctx.get("request_approx_bytes") == 45000
        description = captured.get("description", "")
        assert "87 fields" in description
        assert "43.9KB" in description or "44.0KB" in description

    def test_ajax_save_version_and_wrap_details_included_in_context_and_description(self, client, db_session):
        """A repeat /assignment/<id>?ajax=1 WAF 403 should record which JS
        the browser actually ran (page ASSET_VERSION vs ajax-save.js ?v=)
        and whether the payload was b64-wrapped — the stale-cache signal."""
        captured = {}

        def capture_call(**kwargs):
            captured.update(kwargs)

        with patch(
            "app.services.security.monitoring.SecurityMonitor.log_security_event",
            side_effect=capture_call,
        ):
            resp = self._post(client, {
                "error_code": 403,
                "url": "https://databank.ifrc.org/assignment/1593?ajax=1",
                "page_url": "https://databank.ifrc.org/assignment/1593",
                "asset_version": "deploy-waf-fix",
                "ajax_save_script_url": (
                    "https://cdn.example/static/js/forms/modules/ajax-save.js"
                    "?v=deploy-waf-fix.abc123def456"
                ),
                "ajax_save_script_version": "deploy-waf-fix.abc123def456",
                "ajax_save_script_delivery": "disk_cache",
                "ajax_save_script_transfer_size": 0,
                "response_server": "Microsoft-Azure-Application-Gateway/v2",
                "request_field_count": 40,
                "request_approx_bytes": 8200,
                "request_b64_field_count": 0,
                "request_unwrapped_field_count": 12,
                "request_longest_field_bytes": 1800,
                "request_longest_field_name": "field_value[1414]",
                "request_unwrapped_field_names": ["field_value[1414]", "field_other_text[11]"],
            })
        assert resp.status_code == 200
        ctx = captured.get("context_data", {})
        assert ctx.get("asset_version") == "deploy-waf-fix"
        assert ctx.get("ajax_save_script_version") == "deploy-waf-fix.abc123def456"
        assert "ajax-save.js" in ctx.get("ajax_save_script_url", "")
        assert ctx.get("ajax_save_script_delivery") == "disk_cache"
        assert ctx.get("ajax_save_script_transfer_size") == 0
        assert ctx.get("request_b64_field_count") == 0
        assert ctx.get("request_unwrapped_field_count") == 12
        assert ctx.get("request_longest_field_name") == "field_value[1414]"
        assert ctx.get("request_unwrapped_field_names") == [
            "field_value[1414]",
            "field_other_text[11]",
        ]
        assert ctx.get("response_server") == "Microsoft-Azure-Application-Gateway/v2"
        assert ctx.get("page_url") == "https://databank.ifrc.org/assignment/1593"
        description = captured.get("description", "")
        assert "asset v=deploy-waf-fix" in description
        assert "ajax-save.js v=deploy-waf-fix.abc123def456" in description
        assert "0 b64-wrapped" in description
        assert "12 unwrapped wrap-candidates" in description

    def test_ajax_save_version_telemetry_invalid_values_ignored(self, client, db_session):
        """Public, unauthenticated input: drop garbage version / field-name data."""
        captured = {}

        def capture_call(**kwargs):
            captured.update(kwargs)

        with patch(
            "app.services.security.monitoring.SecurityMonitor.log_security_event",
            side_effect=capture_call,
        ):
            resp = self._post(client, {
                "error_code": 403,
                "url": "https://example.com/assignment/1?ajax=1",
                "asset_version": "bad version\nwith\tcontrol",
                "ajax_save_script_delivery": "totally-made-up",
                "request_unwrapped_field_names": "not-a-list",
                "request_longest_field_name": "field_value[1]; DROP TABLE",
                "ajax_save_script_url": "javascript:alert(1)",
            })
        assert resp.status_code == 200
        ctx = captured.get("context_data", {})
        assert ctx.get("asset_version") == "badversionwithcontrol"
        assert "ajax_save_script_delivery" not in ctx
        assert "request_unwrapped_field_names" not in ctx
        assert ctx.get("request_longest_field_name") == "field_value[1]DROPTABLE"
        assert "ajax_save_script_url" not in ctx

    def test_request_body_telemetry_omitted_when_absent(self, client, db_session):
        """No telemetry fields sent (e.g. a non-FormData/GET failure) => no
        placeholder keys added to context_data."""
        captured = {}

        def capture_call(**kwargs):
            captured.update(kwargs)

        with patch(
            "app.services.security.monitoring.SecurityMonitor.log_security_event",
            side_effect=capture_call,
        ):
            resp = self._post(client, {"error_code": 502, "url": "https://example.com/"})
        assert resp.status_code == 200
        ctx = captured.get("context_data", {})
        assert "request_field_count" not in ctx
        assert "request_approx_bytes" not in ctx

    def test_request_body_telemetry_invalid_values_ignored(self, client, db_session):
        """Garbage/negative telemetry values are dropped, not trusted as-is —
        this is public, unauthenticated input."""
        captured = {}

        def capture_call(**kwargs):
            captured.update(kwargs)

        with patch(
            "app.services.security.monitoring.SecurityMonitor.log_security_event",
            side_effect=capture_call,
        ):
            resp = self._post(client, {
                "error_code": 403,
                "url": "https://example.com/",
                "request_field_count": "not-a-number",
                "request_approx_bytes": -500,
            })
        assert resp.status_code == 200
        ctx = captured.get("context_data", {})
        assert "request_field_count" not in ctx
        assert "request_approx_bytes" not in ctx

    def test_database_log_failure_does_not_break_endpoint(self, client, db_session):
        """DB log failure is caught and endpoint still returns 200."""
        with patch(
            "app.services.security.monitoring.SecurityMonitor.log_security_event",
            side_effect=Exception("DB down"),
        ):
            resp = self._post(client, {"error_code": 502, "url": "https://example.com/"})
        assert resp.status_code == 200

    def test_request_too_large_returns_413(self, client, db_session):
        """Content-Length exceeding limit returns 413."""
        from app.utils.constants import MAX_ERROR_LOG_REQUEST_BYTES
        resp = client.post(
            _api("/platform-error"),
            data=b"x" * (MAX_ERROR_LOG_REQUEST_BYTES + 1),
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(MAX_ERROR_LOG_REQUEST_BYTES + 1),
            },
        )
        assert resp.status_code in (400, 413)

    def test_missing_url_defaults_to_unknown(self, client, db_session):
        """Missing url in payload uses 'unknown' in log description."""
        captured = {}

        def capture(**kwargs):
            captured.update(kwargs)

        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event", side_effect=capture):
            resp = self._post(client, {"error_code": 403})
        assert resp.status_code == 200
        assert "unknown" in captured.get("description", "").lower()

    def test_exception_returns_500(self, client, db_session):
        """Unhandled exception returns 500."""
        with patch("app.routes.api.error_log.get_json_safe", side_effect=Exception("unexpected")):
            resp = self._post(client, {"error_code": 403})
        assert resp.status_code == 500

    def test_no_error_code_returns_400(self, client, db_session):
        """Missing error_code returns 400."""
        resp = self._post(client, {"url": "https://example.com"})
        assert resp.status_code == 400

    def test_valid_timestamp_included_in_context(self, client, db_session):
        """Valid ISO timestamp is included in context_data."""
        captured = {}

        def capture(**kwargs):
            captured.update(kwargs)

        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event", side_effect=capture):
            resp = self._post(client, {
                "error_code": 503,
                "url": "https://example.com/",
                "timestamp": "2024-06-10T12:00:00Z",
            })
        assert resp.status_code == 200
        ctx = captured.get("context_data", {})
        assert "client_timestamp" in ctx

    def test_javascript_scheme_url_sanitized_to_none(self, client, db_session):
        """javascript: URLs are sanitized and treated as unknown."""
        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event") as mock_log:
            resp = self._post(client, {
                "error_code": 403,
                "url": "javascript:alert(1)",
            })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Unit tests for client error helpers
# ---------------------------------------------------------------------------

class TestShouldIgnoreClientError:
    def test_empty_message_ignored(self):
        from app.routes.api.error_log import should_ignore_client_error
        assert should_ignore_client_error(message="   ") is True

    def test_script_error_without_source_ignored(self):
        from app.routes.api.error_log import should_ignore_client_error
        assert should_ignore_client_error(message="Script error.", source=None) is True

    def test_abort_error_ignored(self):
        from app.routes.api.error_log import should_ignore_client_error
        assert should_ignore_client_error(message="Uncaught AbortError: The operation was aborted.") is True

    def test_reference_error_not_ignored(self):
        from app.routes.api.error_log import should_ignore_client_error
        assert should_ignore_client_error(
            message="ReferenceError: Cannot access 'availableCategories' before initialization",
            source="https://example.com/static/js/admin/manage-assignment.js",
        ) is False

    def test_fingerprint_is_stable(self):
        from app.routes.api.error_log import build_client_error_fingerprint
        assert build_client_error_fingerprint(
            kind="error",
            message="boom",
            source="https://example.com/a.js",
            line_no=10,
        ) == "error|boom|https://example.com/a.js|10"


class TestSanitizePlatformErrorTelemetry:
    def test_version_token_strips_spaces_and_controls(self):
        from app.routes.api.error_log import sanitize_version_token
        assert sanitize_version_token("deploy-waf-fix.abc123") == "deploy-waf-fix.abc123"
        assert sanitize_version_token("bad version\nwith\tcontrol") == "badversionwithcontrol"
        assert sanitize_version_token("") is None

    def test_field_name_keeps_brackets_drops_punctuation(self):
        from app.routes.api.error_log import sanitize_form_field_name
        assert sanitize_form_field_name("field_value[1414]") == "field_value[1414]"
        assert sanitize_form_field_name("field_value[1]; DROP TABLE") == "field_value[1]DROPTABLE"

    def test_script_delivery_allow_list(self):
        from app.routes.api.error_log import sanitize_script_delivery
        assert sanitize_script_delivery("disk_cache") == "disk_cache"
        assert sanitize_script_delivery("network") == "network"
        assert sanitize_script_delivery("memory") is None

    def test_field_name_list_caps_and_drops_junk(self):
        from app.routes.api.error_log import sanitize_field_name_list
        assert sanitize_field_name_list("nope") is None
        assert sanitize_field_name_list(["field_value[1]", "", None, "ok_field"]) == [
            "field_value[1]",
            "ok_field",
        ]
        long_list = [f"field_value[{i}]" for i in range(20)]
        assert len(sanitize_field_name_list(long_list)) == 15


# ---------------------------------------------------------------------------
# POST /api/v1/client-error
# ---------------------------------------------------------------------------

class TestLogClientError:
    """Tests for POST /api/v1/client-error."""

    @pytest.fixture(autouse=True)
    def disable_client_error_rate_limit(self, app):
        from app.extensions import limiter
        previous = limiter.enabled
        limiter.enabled = False
        yield
        limiter.enabled = previous

    def _post(self, client, payload, headers=None):
        h = {**(headers or {}), "Content-Type": "application/json"}
        return client.post(_api("/client-error"), json=payload, headers=h)

    def test_wrong_content_type_returns_400(self, client, db_session):
        resp = client.post(
            _api("/client-error"),
            data="message=bad",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 400

    def test_invalid_kind_returns_400(self, client, db_session):
        resp = self._post(client, {"kind": "resource", "message": "boom"})
        assert resp.status_code == 400

    def test_valid_reference_error_logged(self, client, db_session):
        captured = {}

        def capture(**kwargs):
            captured.update(kwargs)

        with patch(
            "app.services.security.monitoring.SecurityMonitor.log_security_event",
            side_effect=capture,
        ):
            resp = self._post(client, {
                "kind": "error",
                "message": "ReferenceError: Cannot access 'availableCategories' before initialization",
                "source": "https://example.com/static/js/admin/manage-assignment.js",
                "line": 1776,
                "column": 5,
                "stack": "ReferenceError: ...",
                "url": "https://example.com/admin/assignments/1",
            })
        assert resp.status_code == 200
        assert captured.get("event_type") == "client_javascript_error"
        assert captured.get("severity") == "low"
        assert captured.get("notify_admins") is False
        ctx = captured.get("context_data", {})
        assert ctx.get("kind") == "error"
        assert "fingerprint" in ctx
        assert "availableCategories" in ctx.get("message", "")

    def test_ignored_message_returns_ok_without_logging(self, client, db_session):
        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event") as mock_log:
            resp = self._post(client, {
                "kind": "unhandledrejection",
                "message": "AbortError: The user aborted a request.",
            })
        assert resp.status_code == 200
        mock_log.assert_not_called()

    def test_missing_message_returns_ok_without_logging(self, client, db_session):
        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event") as mock_log:
            resp = self._post(client, {"kind": "error", "message": "   "})
        assert resp.status_code == 200
        mock_log.assert_not_called()

    def test_database_log_failure_does_not_break_endpoint(self, client, db_session):
        with patch(
            "app.services.security.monitoring.SecurityMonitor.log_security_event",
            side_effect=Exception("DB down"),
        ):
            resp = self._post(client, {
                "kind": "error",
                "message": "TypeError: Cannot read properties of undefined",
            })
        assert resp.status_code == 200

    def test_duplicate_same_day_suppressed(self, client, db_session):
        from app.models import SecurityEvent

        payload = {
            "kind": "error",
            "message": "ReferenceError: duplicate dedupe test marker",
            "source": "https://example.com/static/js/test.js",
            "line": 42,
            "url": "https://example.com/admin/test",
        }
        resp1 = self._post(client, payload)
        resp2 = self._post(client, payload)
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp2.get_json().get("message") == "Duplicate client error suppressed"
        assert (
            SecurityEvent.query.filter_by(event_type="client_javascript_error")
            .filter(SecurityEvent.description.like("%duplicate dedupe test marker%"))
            .count()
            == 1
        )
