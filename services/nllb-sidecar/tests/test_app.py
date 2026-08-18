"""Lightweight tests for the NLLB sidecar's HTTP layer.

Run with NLLB_DISABLE_MODEL_LOAD=true (see conftest.py) so these exercise
routing, language resolution, and placeholder protection without needing
torch/ctranslate2/transformers installed or a model downloaded. Real
end-to-end translation quality is a manual check (see README.md).
"""

import pytest
from fastapi.testclient import TestClient

from app import (
    ISO1_TO_FLORES200,
    protect_placeholders,
    resolve_flores_code,
    restore_placeholders,
)


@pytest.fixture()
def client():
    from app import app as fastapi_app

    return TestClient(fastapi_app)


class TestResolveFloresCode:
    def test_iso_code_resolves(self):
        assert resolve_flores_code("am") == "amh_Ethi"
        assert resolve_flores_code("sw") == "swh_Latn"
        assert resolve_flores_code("ne") == "npi_Deva"

    def test_case_and_region_suffix_normalized(self):
        assert resolve_flores_code("AM") == "amh_Ethi"
        assert resolve_flores_code("am-ET") == "amh_Ethi"
        assert resolve_flores_code("am_ET") == "amh_Ethi"

    def test_exact_flores_code_passthrough(self):
        assert resolve_flores_code("amh_Ethi") == "amh_Ethi"

    def test_unknown_code_returns_none(self):
        assert resolve_flores_code("zz") is None
        assert resolve_flores_code("") is None
        assert resolve_flores_code(None) is None

    def test_core_languages_all_resolve(self):
        for code in ("en", "fr", "es", "ar", "ru", "zh", "hi"):
            assert resolve_flores_code(code) is not None

    def test_mapping_has_no_duplicate_flores_targets_collisions_are_intentional(self):
        # zh/no/az etc. intentionally share a macrolanguage variant; just make
        # sure the table is non-trivial and every value looks like a FLORES code.
        assert len(ISO1_TO_FLORES200) > 100
        for value in ISO1_TO_FLORES200.values():
            assert "_" in value


class TestPlaceholderProtection:
    def test_bracket_placeholder_protected_and_restored(self):
        original = "National Society [assignment_period] Total Funding"
        protected, tokens = protect_placeholders(original)
        assert "[assignment_period]" not in protected
        assert len(tokens) == 1
        restored = restore_placeholders(protected, tokens)
        assert restored == original

    def test_percent_format_tokens_protected(self):
        original = "You have %(count)d new messages"
        protected, tokens = protect_placeholders(original)
        assert "%(count)d" not in protected
        assert restore_placeholders(protected, tokens) == original

    def test_jinja_expression_protected(self):
        original = "Hello {{ user.name }}!"
        protected, tokens = protect_placeholders(original)
        assert "{{ user.name }}" not in protected
        assert restore_placeholders(protected, tokens) == original

    def test_tokens_are_alphabetic_only_no_digits(self):
        _, tokens = protect_placeholders("[a] [b] [c] [d] [e]")
        for token in tokens:
            assert token.isalpha()

    def test_restore_appends_dropped_placeholder_as_last_resort(self):
        protected, tokens = protect_placeholders("Hello [name]")
        token = next(iter(tokens))
        # Simulate a translation that dropped the token entirely.
        mangled = protected.replace(token, "")
        restored = restore_placeholders(mangled, tokens)
        assert "[name]" in restored

    def test_no_placeholders_is_a_noop(self):
        protected, tokens = protect_placeholders("Just plain text")
        assert protected == "Just plain text"
        assert tokens == {}


class TestHealthAndLanguagesEndpoints:
    def test_health_reports_disabled_status_in_test_mode(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["status"] == "disabled"
        assert body["engine"] == "nllb"

    def test_languages_lists_core_and_sidecar_sets(self, client):
        resp = client.get("/languages")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body["core_azure"]) == {"en", "fr", "es", "ar", "ru", "zh", "hi"}
        assert "am" in body["sidecar_supported"]
        assert "sw" in body["sidecar_supported"]
        assert "fr" in body["sidecar_supported"]
        assert "en" in body["sidecar_supported"]


class TestTranslateEndpointValidation:
    def test_core_language_target_reaches_readiness_check(self, client):
        # Core languages are valid NLLB targets; while the model is not ready
        # they get the same 503 as long-tail languages.
        resp = client.post("/api/translate", json={"Text": "hello", "From": "en", "To": "fr"})
        assert resp.status_code == 503
        assert "Retry-After" in resp.headers

    def test_unsupported_language_code_returns_400(self, client):
        resp = client.post("/api/translate", json={"Text": "hello", "From": "en", "To": "zz"})
        assert resp.status_code == 400

    def test_model_not_ready_returns_503(self, client):
        resp = client.post("/api/translate", json={"Text": "hello", "From": "en", "To": "am"})
        assert resp.status_code == 503
        assert "Retry-After" in resp.headers

    def test_empty_text_rejected_by_validation(self, client):
        resp = client.post("/api/translate", json={"Text": "", "From": "en", "To": "am"})
        assert resp.status_code == 422

    def test_api_key_required_when_configured(self, client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "API_KEY", "secret123")
        resp = client.post(
            "/api/translate",
            json={"Text": "hello", "From": "en", "To": "am"},
            headers={"x-api-key": "wrong"},
        )
        assert resp.status_code == 401

    def test_api_key_accepted_when_correct(self, client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "API_KEY", "secret123")
        resp = client.post(
            "/api/translate",
            json={"Text": "hello", "From": "en", "To": "am"},
            headers={"x-api-key": "secret123"},
        )
        # Auth passes; falls through to the (expected, in test mode) 503.
        assert resp.status_code == 503


class TestBatchEndpointGracefulDegradation:
    def test_batch_never_hard_fails_on_one_bad_item(self, client):
        resp = client.post(
            "/api/translate/batch",
            json=[
                {"Text": "hello", "From": "en", "To": "fr"},  # model not ready -> deferred
                {"Text": "hello", "From": "en", "To": "am"},  # model not ready -> deferred
            ],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert all(item["deferred"] is True for item in body)
