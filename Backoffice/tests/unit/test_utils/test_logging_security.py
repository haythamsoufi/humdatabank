"""Tests for the shared redaction policy in app/utils/logging_security.py."""

from __future__ import annotations

import json

import pytest

from app.utils.logging_security import (
    REDACTED,
    is_sensitive_key,
    redact_payload_for_storage,
    redact_query_params_in_text,
    redact_sensitive,
    redact_url,
    sanitize_dict_for_logging,
    sanitize_for_logging,
    sanitize_headers_for_logging,
)

# Assembled at import time so secret scanners do not flag a JWT-shaped literal.
_JWT = ".".join(
    [
        "eyJ" + "hbGciOiJIUzI1NiJ9",
        "eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0",
        "dBjftJeZ4CVPmB92K27uhbUJU1p1r",
    ]
)


class TestIsSensitiveKey:
    @pytest.mark.parametrize(
        "key",
        [
            "password", "newPassword", "new_password", "NEW-PASSWORD", "passwd", "passphrase",
            "client_secret", "clientSecret", "access_token", "refreshToken", "id_token",
            "api_key", "apiKey", "APIKey", "X-Api-Key", "x-api-key", "authorization",
            "Proxy-Authorization", "Cookie", "Set-Cookie", "csrf_token", "X-CSRFToken",
            "private_key", "credit_card_number", "cvv", "ssn", "userSSN", "otp_code", "pwd",
            "recovery_code", "session_id", "connection_string", "jwt",
        ],
    )
    def test_sensitive(self, key):
        assert is_sensitive_key(key) is True

    @pytest.mark.parametrize(
        "key",
        [
            "username", "email", "name", "business_name", "class_name", "footprint",
            "country_id", "assignment_id", "description", "author", "status", "", None,
        ],
    )
    def test_not_sensitive(self, key):
        assert is_sensitive_key(key) is False


class TestRedactSensitive:
    def test_nested_dicts_and_lists_are_redacted(self):
        payload = {
            "user": {"name": "a", "password": "p", "profile": {"apiKey": "k", "bio": "hi"}},
            "items": [{"token": "t", "id": 1}, {"ok": True}],
            "headers": {"Authorization": "Bearer abcdefghijklmnop"},
        }
        out = redact_sensitive(payload)
        assert out["user"]["password"] == REDACTED
        assert out["user"]["profile"]["apiKey"] == REDACTED
        assert out["user"]["profile"]["bio"] == "hi"
        assert out["items"][0] == {"token": REDACTED, "id": 1}
        assert out["headers"]["Authorization"] == REDACTED

    def test_camel_case_keys(self):
        out = redact_sensitive({"newPassword": "x", "confirmPassword": "x", "accessToken": "y"})
        assert set(out.values()) == {REDACTED}

    def test_input_is_not_mutated(self):
        payload = {"password": "p", "nested": {"secret": "s"}}
        redact_sensitive(payload)
        assert payload == {"password": "p", "nested": {"secret": "s"}}

    def test_sensitive_key_redacted_regardless_of_value_type(self):
        out = redact_sensitive({"token": {"a": 1}, "secret": [1, 2], "password": None})
        assert out == {"token": REDACTED, "secret": REDACTED, "password": REDACTED}

    def test_inline_credentials_in_strings_are_masked(self):
        out = redact_sensitive(
            {
                "note": f"call with Bearer abcdefghijklmnop and {_JWT}",
                "url": "postgresql://admin:hunter2@db.example.org/app",
                "text": "password=hunter2&x=1",
            }
        )
        blob = json.dumps(out)
        assert "abcdefghijklmnop" not in blob
        assert _JWT not in blob
        assert "hunter2" not in blob

    def test_depth_limit(self):
        deep = current = {}
        for _ in range(20):
            current["a"] = {}
            current = current["a"]
        out = redact_sensitive(deep, max_depth=3)
        assert "<max depth exceeded>" in json.dumps(out)

    def test_item_limit(self):
        out = redact_sensitive({"list": list(range(500))}, max_items=10)
        assert len(out["list"]) == 11
        assert out["list"][-1] == "<490 more items>"

    def test_long_strings_truncated(self):
        out = redact_sensitive({"a": "x" * 5000}, max_string_length=100)
        assert len(out["a"]) < 200
        assert "TRUNCATED" in out["a"]

    def test_bytes_and_unknown_objects_are_stringified_safely(self):
        out = redact_sensitive({"b": b"secretbytes", "o": object()})
        assert out["b"] == "<11 bytes>"
        assert isinstance(out["o"], str)


class TestRedactPayloadForStorage:
    def test_empty_payloads_store_none(self):
        assert redact_payload_for_storage(None) is None
        assert redact_payload_for_storage({}) is None

    def test_small_payload_is_redacted_and_kept(self):
        out = redact_payload_for_storage({"password": "p", "name": "n"})
        assert out == {"password": REDACTED, "name": "n"}

    def test_oversized_payload_becomes_values_free_summary(self):
        payload = {f"field_{i}": "y" * 400 for i in range(80)}
        payload["password"] = "hunter2"
        out = redact_payload_for_storage(payload, max_bytes=2048, max_items=100)
        assert out["_truncated"] is True
        assert out["_size_bytes"] > 2048
        assert "field_0" in out["keys"]
        assert "hunter2" not in json.dumps(out)
        assert len(json.dumps(out)) < 2048

    def test_result_is_json_serialisable(self):
        out = redact_payload_for_storage({"when": object(), "items": {1, 2}})
        json.dumps(out)


class TestUrlAndTextRedaction:
    def test_redact_url_masks_query_and_userinfo(self):
        url = "https://user:pw@example.org/reset?token=abc123&next=%2Fhome&api_key=zzz#frag"
        out = redact_url(url)
        assert "abc123" not in out and "zzz" not in out and "user:pw" not in out
        assert "next=/home" in out or "next=%2Fhome" in out
        assert "#frag" not in out

    def test_redact_url_passthrough_for_empty(self):
        assert redact_url("") == ""
        assert redact_url(None) is None

    def test_query_params_in_access_log_line(self):
        line = 'GET /login?next=/x&access_token=abc&password=p HTTP/1.1'
        out = redact_query_params_in_text(line)
        assert "access_token=***MASKED***" in out
        assert "password=***MASKED***" in out
        assert "next=/x" in out

    def test_headers(self):
        out = sanitize_headers_for_logging(
            {"Authorization": "Bearer x" * 5, "Cookie": "session=abc", "Accept": "text/html", "X-API-Key": "k"}
        )
        assert out["Authorization"] == REDACTED
        assert out["Cookie"] == REDACTED
        assert out["X-API-Key"] == REDACTED
        assert out["Accept"] == "text/html"


class TestLegacyHelpers:
    def test_sanitize_for_logging_masks_common_secrets(self):
        assert "hunter2" not in sanitize_for_logging("password=hunter2")
        assert "hunter2" not in sanitize_for_logging('{"password": "hunter2"}')
        assert "hunter2" not in sanitize_for_logging("api_key: hunter2")
        assert sanitize_for_logging(None) == "None"

    def test_sanitize_dict_for_logging_uses_shared_policy_by_default(self):
        out = sanitize_dict_for_logging({"newPassword": "x", "name": "n"})
        assert out["newPassword"] == REDACTED
        assert out["name"] == "n"

    def test_sanitize_dict_for_logging_explicit_keys_keep_legacy_behaviour(self):
        out = sanitize_dict_for_logging({"custom_field": "x", "name": "n"}, sensitive_keys=["custom"])
        assert out["custom_field"] == "***MASKED***"
        assert out["name"] == "n"
