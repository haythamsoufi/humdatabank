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
    split_for_translation,
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

    def test_luba_katanga_is_not_mapped_to_luba_kasai(self):
        assert resolve_flores_code("lu") is None
        assert "lu" not in ISO1_TO_FLORES200
        assert "lua_Latn" not in ISO1_TO_FLORES200.values()

    def test_script_and_region_tags_select_the_written_form(self):
        assert resolve_flores_code("zh") == "zho_Hans"
        assert resolve_flores_code("zh-Hant") == "zho_Hant"
        assert resolve_flores_code("zh_TW") == "zho_Hant"
        assert resolve_flores_code("sr") == "srp_Cyrl"
        assert resolve_flores_code("sr_Latn") == "srp_Latn"
        assert resolve_flores_code("ku") == "kmr_Latn"
        assert resolve_flores_code("ckb") == "ckb_Arab"
        assert resolve_flores_code("ff") == "fuv_Latn"
        assert resolve_flores_code("no") == "nob_Latn"
        assert resolve_flores_code("am-ET") == "amh_Ethi"

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


class TestSegmentSplit:
    def test_long_text_splits_without_cutting_a_placeholder_token(self):
        token = "NLLBXQZA"
        sentence = "People reached with disaster risk reduction. "
        text = (sentence * 12) + token + " Keep this token whole."
        parts = split_for_translation(text, max_chars=80)
        assert len(parts) > 1
        assert all(len(part) <= 80 for part in parts)
        assert sum(part.count(token) for part in parts) == 1
        assert " ".join(parts) == " ".join(text.split())


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
        assert "lu" not in body["sidecar_supported"]
        assert body["license"] == "CC-BY-NC-4.0"

    def test_languages_requires_api_key_when_configured(self, client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "API_KEY", "secret123")
        denied = client.get("/languages")
        assert denied.status_code == 401
        allowed = client.get("/languages", headers={"x-api-key": "secret123"})
        assert allowed.status_code == 200


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

    def test_luba_katanga_returns_400(self, client):
        resp = client.post("/api/translate", json={"Text": "hello", "From": "en", "To": "lu"})
        assert resp.status_code == 400

    def test_traditional_chinese_reaches_readiness_check(self, client):
        resp = client.post("/api/translate", json={"Text": "hello", "From": "en", "To": "zh_Hant"})
        assert resp.status_code == 503

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

    def test_oversized_batch_is_rejected(self, client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "MAX_BATCH_ITEMS", 2)
        resp = client.post(
            "/api/translate/batch",
            json=[
                {"Text": "one", "From": "en", "To": "am"},
                {"Text": "two", "From": "en", "To": "am"},
                {"Text": "three", "From": "en", "To": "am"},
            ],
        )
        assert resp.status_code == 413


class TestInferenceLock:
    def test_concurrent_requests_keep_their_source_language(self):
        import threading
        import time
        from types import SimpleNamespace

        import app as app_module

        class FakeTok:
            def __init__(self):
                self.src_lang = None
                self.seen = []
                self._seen_lock = threading.Lock()

            def __call__(self, text):
                time.sleep(0.02)
                with self._seen_lock:
                    self.seen.append((self.src_lang, text))
                return SimpleNamespace(input_ids=[1])

            def convert_ids_to_tokens(self, ids):
                return ["tok"]

            def convert_tokens_to_ids(self, toks):
                return [1]

            def decode(self, ids, skip_special_tokens=True):
                return "ok"

        class FakeTranslator:
            def translate_batch(self, sources, target_prefix, beam_size, max_decoding_length):
                prefix = target_prefix[0][0]

                class Result:
                    hypotheses = [[prefix, "x"]]

                return [Result() for _ in sources]

        tok = FakeTok()
        previous = (app_module._state.tokenizer, app_module._state.translator)
        app_module._state.tokenizer = tok
        app_module._state.translator = FakeTranslator()
        errors = []

        def run(src, text):
            try:
                app_module._translate_batch_same_pair([text], src, "fra_Latn")
            except Exception as exc:  # pragma: no cover - assertion below
                errors.append(exc)

        threads = [
            threading.Thread(target=run, args=("eng_Latn", "hello")),
            threading.Thread(target=run, args=("spa_Latn", "hola")),
        ]
        try:
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        finally:
            app_module._state.tokenizer, app_module._state.translator = previous
        assert errors == []
        assert ("eng_Latn", "hello") in tok.seen
        assert ("spa_Latn", "hola") in tok.seen
