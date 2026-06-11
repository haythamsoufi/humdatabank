"""
Unit tests for app/utils/request_validation.py

Covers: enforce_csrf_json, enforce_api_or_csrf_protection
"""
import pytest
from unittest.mock import patch, MagicMock
from werkzeug.exceptions import Forbidden


@pytest.mark.unit
class TestEnforceCsrfJson:
    def test_get_request_returns_none(self, app):
        """GET is not an unsafe method so CSRF is not enforced."""
        from app.utils.request_validation import enforce_csrf_json
        with app.test_request_context("/test", method="GET"):
            result = enforce_csrf_json()
            assert result is None

    def test_post_with_valid_csrf_returns_none(self, app):
        from app.utils.request_validation import enforce_csrf_json
        with app.test_request_context("/test", method="POST"):
            with patch("app.utils.request_validation.csrf") as mock_csrf:
                mock_csrf.protect.return_value = None
                result = enforce_csrf_json()
                assert result is None

    def test_post_with_csrf_error_returns_error_response(self, app):
        from app.utils.request_validation import enforce_csrf_json
        from flask_wtf.csrf import CSRFError
        with app.test_request_context("/test", method="POST"):
            with patch("app.utils.request_validation.csrf") as mock_csrf:
                exc = CSRFError("CSRF token missing")
                exc.description = "CSRF token missing"
                mock_csrf.protect.side_effect = exc
                result = enforce_csrf_json()
                # Should return a (response, status) tuple, not None
                assert result is not None

    def test_put_with_csrf_error_returns_error_response(self, app):
        from app.utils.request_validation import enforce_csrf_json
        from flask_wtf.csrf import CSRFError
        with app.test_request_context("/test", method="PUT"):
            with patch("app.utils.request_validation.csrf") as mock_csrf:
                exc = CSRFError("CSRF invalid")
                exc.description = "CSRF invalid"
                mock_csrf.protect.side_effect = exc
                result = enforce_csrf_json()
                assert result is not None

    def test_method_not_in_custom_list_returns_none(self, app):
        """PUT is not in the custom methods list so it is skipped."""
        from app.utils.request_validation import enforce_csrf_json
        with app.test_request_context("/test", method="PUT"):
            result = enforce_csrf_json(methods=["POST", "DELETE"])
            assert result is None

    def test_method_in_custom_list_validates(self, app):
        from app.utils.request_validation import enforce_csrf_json
        with app.test_request_context("/test", method="DELETE"):
            with patch("app.utils.request_validation.csrf") as mock_csrf:
                mock_csrf.protect.return_value = None
                result = enforce_csrf_json(methods=["DELETE"])
                assert result is None

    def test_csrf_error_without_description(self, app):
        """Ensure we handle CSRFError with no description attribute gracefully."""
        from app.utils.request_validation import enforce_csrf_json
        from flask_wtf.csrf import CSRFError
        with app.test_request_context("/test", method="POST"):
            with patch("app.utils.request_validation.csrf") as mock_csrf:
                exc = CSRFError()
                exc.description = None
                mock_csrf.protect.side_effect = exc
                result = enforce_csrf_json()
                assert result is not None

    def test_patch_method_checked_by_default(self, app):
        """PATCH is in the default UNSAFE_HTTP_METHODS set."""
        from app.utils.request_validation import enforce_csrf_json
        with app.test_request_context("/test", method="PATCH"):
            with patch("app.utils.request_validation.csrf") as mock_csrf:
                mock_csrf.protect.return_value = None
                result = enforce_csrf_json()
                assert result is None


@pytest.mark.unit
class TestEnforceApiOrCsrfProtection:
    def test_no_mobile_auth_valid_csrf_passes(self, app):
        from app.utils.request_validation import enforce_api_or_csrf_protection
        with app.test_request_context("/test", method="POST"):
            with patch("app.utils.request_validation.csrf") as mock_csrf:
                mock_csrf.protect.return_value = None
                # Should not raise
                enforce_api_or_csrf_protection()

    def test_valid_mobile_auth_token_passes(self, app):
        from app.utils.request_validation import enforce_api_or_csrf_protection
        with app.test_request_context(
            "/test",
            method="POST",
            headers={"X-Mobile-Auth": "valid-api-key"},
        ):
            with patch(
                "app.services.security.api_authentication.validate_plaintext_db_api_key_for_mobile_auth",
                return_value=True,
            ):
                # Should not raise
                enforce_api_or_csrf_protection()

    def test_invalid_mobile_auth_token_raises_forbidden(self, app):
        from app.utils.request_validation import enforce_api_or_csrf_protection
        with app.test_request_context(
            "/test",
            method="POST",
            headers={"X-Mobile-Auth": "bad-token"},
        ):
            with patch(
                "app.services.security.api_authentication.validate_plaintext_db_api_key_for_mobile_auth",
                return_value=False,
            ):
                with pytest.raises(Forbidden):
                    enforce_api_or_csrf_protection()

    def test_csrf_error_propagates_when_no_mobile_auth(self, app):
        from app.utils.request_validation import enforce_api_or_csrf_protection
        from flask_wtf.csrf import CSRFError
        with app.test_request_context("/test", method="POST"):
            with patch("app.utils.request_validation.csrf") as mock_csrf:
                mock_csrf.protect.side_effect = CSRFError("bad token")
                with pytest.raises(CSRFError):
                    enforce_api_or_csrf_protection()

    def test_whitespace_only_mobile_auth_header_treated_as_missing(self, app):
        """Whitespace-only X-Mobile-Auth should fall through to CSRF."""
        from app.utils.request_validation import enforce_api_or_csrf_protection
        with app.test_request_context(
            "/test",
            method="POST",
            headers={"X-Mobile-Auth": "   "},
        ):
            with patch("app.utils.request_validation.csrf") as mock_csrf:
                mock_csrf.protect.return_value = None
                # Should not raise; strips to empty string -> no mobile auth -> CSRF
                enforce_api_or_csrf_protection()
