"""
Extended tests for app/utils/activity_form_data_redaction.py.

Complements the existing test_activity_form_data_redaction.py by covering the
remaining branches: empty / None inputs, non-string values, redact_activity_form_dict,
and edge-cases in _is_sensitive_key.
"""

from __future__ import annotations

from app.utils.activity_form_data_redaction import (
    _is_sensitive_key,
    redact_activity_form_data,
    redact_activity_form_dict,
)


# ---------------------------------------------------------------------------
# _is_sensitive_key
# ---------------------------------------------------------------------------


class TestIsSensitiveKey:
    def test_empty_key_not_sensitive(self):
        assert _is_sensitive_key("") is False

    def test_none_key_not_sensitive(self):
        # None is cast to "" inside the function
        assert _is_sensitive_key(None) is False  # type: ignore[arg-type]

    def test_password_sensitive(self):
        assert _is_sensitive_key("password") is True

    def test_password_confirm_sensitive(self):
        assert _is_sensitive_key("password_confirm") is True

    def test_token_sensitive(self):
        assert _is_sensitive_key("auth_token") is True

    def test_csrf_sensitive(self):
        assert _is_sensitive_key("csrf_token") is True

    def test_api_key_sensitive(self):
        assert _is_sensitive_key("api_key") is True

    def test_apikey_sensitive(self):
        assert _is_sensitive_key("myapikey") is True

    def test_secret_sensitive(self):
        assert _is_sensitive_key("client_secret") is True

    def test_credit_card_sensitive(self):
        assert _is_sensitive_key("credit_card_number") is True

    def test_creditcard_sensitive(self):
        assert _is_sensitive_key("creditcard") is True

    def test_cvv_sensitive(self):
        assert _is_sensitive_key("cvv") is True

    def test_ssn_sensitive(self):
        assert _is_sensitive_key("ssn") is True

    def test_otp_sensitive(self):
        assert _is_sensitive_key("otp_code") is True

    def test_recovery_code_sensitive(self):
        assert _is_sensitive_key("recovery_code") is True

    def test_private_key_sensitive(self):
        assert _is_sensitive_key("private_key") is True

    def test_authorization_sensitive(self):
        assert _is_sensitive_key("authorization") is True

    def test_normal_key_not_sensitive(self):
        assert _is_sensitive_key("username") is False

    def test_email_not_sensitive(self):
        assert _is_sensitive_key("email") is False

    def test_case_insensitive(self):
        assert _is_sensitive_key("PASSWORD") is True
        assert _is_sensitive_key("CSRF_TOKEN") is True


# ---------------------------------------------------------------------------
# redact_activity_form_data – edge cases not covered by existing tests
# ---------------------------------------------------------------------------


class TestRedactActivityFormDataExtended:
    def test_none_input_returns_empty_dict(self):
        assert redact_activity_form_data(None) == {}  # type: ignore[arg-type]

    def test_empty_list_returns_empty_dict(self):
        assert redact_activity_form_data([]) == {}

    def test_empty_key_is_dropped(self):
        result = redact_activity_form_data([("", "value")])
        assert result == {}

    def test_non_string_value_short_kept(self):
        result = redact_activity_form_data([("count", 42)])
        assert result == {"count": "42"}

    def test_non_string_value_long_truncated(self):
        long_int_like = 12345678901234567890
        result = redact_activity_form_data([("bignum", long_int_like)], max_value_len=5)
        assert result["bignum"].endswith("...")
        assert len(result["bignum"]) == 8  # 5 chars + "..."

    def test_non_string_value_exact_length(self):
        # value str representation has exactly max_value_len chars → no ellipsis
        result = redact_activity_form_data([("x", 12345)], max_value_len=5)
        assert result["x"] == "12345"

    def test_max_value_len_clamped_to_minimum_one(self):
        # max_value_len=0 or negative → clamped to 1
        result = redact_activity_form_data([("note", "hello")], max_value_len=0)
        assert result["note"].startswith("h")
        assert len(result["note"]) <= 4  # 1 char + "..."

    def test_multiple_sensitive_keys_dropped(self):
        result = redact_activity_form_data(
            [
                ("passwd", "x"),
                ("secret_answer", "y"),
                ("token", "z"),
                ("safe_field", "ok"),
            ]
        )
        assert set(result.keys()) == {"safe_field"}

    def test_string_value_exact_max_len_no_ellipsis(self):
        val = "a" * 100
        result = redact_activity_form_data([("note", val)], max_value_len=100)
        assert result["note"] == val
        assert not result["note"].endswith("...")

    def test_string_value_over_max_len_ellipsis(self):
        val = "a" * 101
        result = redact_activity_form_data([("note", val)], max_value_len=100)
        assert result["note"].endswith("...")
        assert len(result["note"]) == 103  # 100 + "..."


# ---------------------------------------------------------------------------
# redact_activity_form_dict
# ---------------------------------------------------------------------------


class TestRedactActivityFormDict:
    def test_none_returns_empty_dict(self):
        assert redact_activity_form_dict(None) == {}

    def test_empty_dict_returns_empty_dict(self):
        assert redact_activity_form_dict({}) == {}

    def test_redacts_sensitive_keys(self):
        result = redact_activity_form_dict({"username": "alice", "password": "secret"})
        assert result == {"username": "alice"}

    def test_truncates_long_values(self):
        result = redact_activity_form_dict({"note": "x" * 200}, max_value_len=50)
        assert result["note"].endswith("...")
        assert len(result["note"]) == 53

    def test_does_not_mutate_original(self):
        original = {"name": "Bob", "password": "hunter2"}
        redact_activity_form_dict(original)
        assert "password" in original  # original untouched

    def test_non_string_values_stringified(self):
        result = redact_activity_form_dict({"count": 7})
        assert result == {"count": "7"}
