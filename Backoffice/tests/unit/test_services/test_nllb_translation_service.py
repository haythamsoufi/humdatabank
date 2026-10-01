"""Tests for the self-hosted NLLB sidecar integration (long-tail languages).

Covers NLLBTranslationService (translate_text/translate_batch/check_health,
circuit breaker) and its opt-in wiring into AutoTranslator._init_services.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.translation.auto_translator import (
    STATUS_PROBE_TIMEOUT_SECONDS,
    AutoTranslator,
    NLLBTranslationService,
)

pytestmark = [pytest.mark.unit]


def _response(status_code=200, json_body=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text or ""
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = ValueError("no json")
    return resp


class TestInitServicesWiring:
    """NLLB is opt-in (NLLB_SIDECAR_URL) and never the default unless nothing else is configured."""

    def _clean_env(self, monkeypatch):
        for var in (
            "GOOGLE_TRANSLATE_API_KEY",
            "TRANSLATE_API_KEY",
            "LIBRE_TRANSLATE_API_KEY",
            "LIBRE_TRANSLATE_URL",
            "IFRC_TRANSLATE_API_KEY",
            "IFRC_TRANSLATE_URL",
            "NLLB_SIDECAR_API_KEY",
            "NLLB_SIDECAR_URL",
        ):
            monkeypatch.delenv(var, raising=False)

    def test_disabled_when_url_not_set(self, monkeypatch):
        self._clean_env(monkeypatch)
        tr = AutoTranslator()
        assert "nllb" not in tr.services

    def test_enabled_when_url_set(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setenv("NLLB_SIDECAR_URL", "http://nllb:9100")
        tr = AutoTranslator()
        assert "nllb" in tr.services
        assert isinstance(tr.services["nllb"], NLLBTranslationService)
        assert tr.services["nllb"].base_url == "http://nllb:9100"

    def test_api_key_passed_through(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setenv("NLLB_SIDECAR_URL", "http://nllb:9100")
        monkeypatch.setenv("NLLB_SIDECAR_API_KEY", "secret123")
        tr = AutoTranslator()
        assert tr.services["nllb"].api_key == "secret123"

    def test_nllb_is_last_resort_default(self, monkeypatch):
        """Only becomes default_service when no other engine is configured."""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("NLLB_SIDECAR_URL", "http://nllb:9100")
        tr = AutoTranslator()
        assert tr.default_service == "nllb"

    def test_ifrc_still_preferred_over_nllb(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setenv("NLLB_SIDECAR_URL", "http://nllb:9100")
        monkeypatch.setenv("IFRC_TRANSLATE_API_KEY", "ifrc-key")
        tr = AutoTranslator()
        assert tr.default_service == "ifrc"
        assert "nllb" in tr.services  # still registered, just not default

    def test_explicit_nllb_stays_exclusive(self, monkeypatch):
        """Selecting NLLB uses only NLLB, including for core languages."""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("NLLB_SIDECAR_URL", "http://nllb:9100")
        monkeypatch.setenv("IFRC_TRANSLATE_API_KEY", "ifrc-key")
        tr = AutoTranslator()
        names = [getattr(s, "service_name", None) for s in tr._ordered_services_to_try("nllb")]
        assert names == ["nllb"]

    def test_explicit_ifrc_stays_exclusive(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setenv("NLLB_SIDECAR_URL", "http://nllb:9100")
        monkeypatch.setenv("IFRC_TRANSLATE_API_KEY", "ifrc-key")
        tr = AutoTranslator()
        names = [getattr(s, "service_name", None) for s in tr._ordered_services_to_try("ifrc")]
        assert names == ["ifrc"]


class TestNLLBTranslateText:
    def test_successful_translation(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(
            svc.session, "post",
            return_value=_response(200, {"text": "Selam alem", "engine": "nllb", "deferred": False}),
        ) as mock_post:
            result = svc.translate_text("Hello world", "am", "en")
        assert result == "Selam alem"
        args, kwargs = mock_post.call_args
        assert args[0] == "http://nllb:9100/api/translate"
        assert kwargs["timeout"] == 30

    def test_api_key_sent_as_header(self):
        svc = NLLBTranslationService(api_key="k123", base_url="http://nllb:9100")
        with patch.object(
            svc.session, "post",
            return_value=_response(200, {"text": "x", "deferred": False}),
        ) as mock_post:
            svc.translate_text("Hello", "am", "en")
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["x-api-key"] == "k123"

    def test_same_source_and_target_short_circuits(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(svc.session, "post") as mock_post:
            assert svc.translate_text("Hello", "en", "en") is None
        mock_post.assert_not_called()

    def test_deferred_response_treated_as_no_translation(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(
            svc.session, "post",
            return_value=_response(200, {"text": "Hello", "deferred": True}),
        ):
            assert svc.translate_text("Hello", "am", "en") is None

    def test_truncated_response_is_discarded(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(
            svc.session, "post",
            return_value=_response(200, {"text": "partial", "truncated": True, "deferred": False}),
        ):
            assert svc.translate_text("Hello", "fr", "en") is None

    def test_script_hint_is_forwarded(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(
            svc.session, "post",
            return_value=_response(200, {"text": "bonjour", "truncated": False, "deferred": False}),
        ) as mock_post:
            assert svc.translate_text("Hello", "zh_Hant", "en") == "bonjour"
        sent = json.loads(mock_post.call_args.kwargs["data"])
        assert sent["To"] == "zh_Hant"
        assert sent["From"] == "en"

    def test_model_loading_503_returns_none(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(
            svc.session, "post",
            return_value=_response(503, text="loading"),
        ):
            assert svc.translate_text("Hello", "am", "en") is None

    def test_unsupported_language_400_returns_none(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(
            svc.session, "post",
            return_value=_response(400, text="bad code"),
        ):
            assert svc.translate_text("Hello", "zz", "en") is None

    def test_invalid_api_key_401_returns_none(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(
            svc.session, "post",
            return_value=_response(401, text="bad key"),
        ):
            assert svc.translate_text("Hello", "am", "en") is None

    def test_connection_error_trips_circuit_breaker(self):
        import requests as requests_module

        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(
            svc.session, "post",
            side_effect=requests_module.exceptions.ConnectionError("refused"),
        ):
            assert svc.translate_text("Hello", "am", "en") is None
        assert svc._is_circuit_open()

        # Subsequent calls short-circuit without hitting the network.
        with patch.object(svc.session, "post") as mock_post:
            assert svc.translate_text("Hello", "am", "en") is None
        mock_post.assert_not_called()


class TestNLLBTranslateBatch:
    def test_successful_batch(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        batch_response = [
            {"text": "A1", "deferred": False},
            {"text": "A2", "deferred": False},
        ]
        with patch.object(
            svc.session, "post",
            return_value=_response(200, batch_response),
        ):
            result = svc.translate_batch(["Hello", "World"], "am", "en")
        assert result == ["A1", "A2"]

    def test_deferred_items_become_none_for_fallback(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        batch_response = [
            {"text": "A1", "deferred": False},
            {"text": "World", "deferred": True},
        ]
        with patch.object(
            svc.session, "post",
            return_value=_response(200, batch_response),
        ):
            result = svc.translate_batch(["Hello", "World"], "am", "en")
        assert result == ["A1", None]

    def test_empty_input_returns_empty_list(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(svc.session, "post") as mock_post:
            assert svc.translate_batch([], "am", "en") == []
        mock_post.assert_not_called()

    def test_response_shape_mismatch_returns_all_none(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(
            svc.session, "post",
            return_value=_response(200, [{"text": "only-one", "deferred": False}]),
        ):
            result = svc.translate_batch(["Hello", "World"], "am", "en")
        assert result == [None, None]

    def test_non_200_returns_all_none(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(
            svc.session, "post",
            return_value=_response(500, text="boom"),
        ):
            result = svc.translate_batch(["Hello", "World"], "am", "en")
        assert result == [None, None]


class TestNLLBCheckHealth:
    def test_ready_model_reports_healthy(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(
            svc.session, "get",
            return_value=_response(200, {"ok": True, "status": "ready"}),
        ) as mock_get:
            assert svc.check_health() is True
        args, kwargs = mock_get.call_args
        assert args[0] == "http://nllb:9100/health"
        assert kwargs["timeout"] == STATUS_PROBE_TIMEOUT_SECONDS

    def test_loading_model_reports_unhealthy_despite_200(self):
        """/health always answers 200 -- readiness is signalled by the `ok` field."""
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(
            svc.session, "get",
            return_value=_response(200, {"ok": False, "status": "loading"}),
        ):
            assert svc.check_health() is False

    def test_non_200_reports_unhealthy(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(
            svc.session, "get",
            return_value=_response(503),
        ):
            assert svc.check_health() is False

    def test_connection_error_trips_circuit_and_reports_unhealthy(self):
        import requests as requests_module

        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch.object(
            svc.session, "get",
            side_effect=requests_module.exceptions.ConnectionError("refused"),
        ):
            assert svc.check_health() is False
        assert svc._is_circuit_open()


def test_nllb_language_table_matches_sidecar_and_omits_luba_katanga():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    sidecar = json.loads((root / "services/nllb-sidecar/iso1_to_flores200.json").read_text(encoding="utf-8"))
    vendored = json.loads((root / "Backoffice/config/nllb_iso1_to_flores200.json").read_text(encoding="utf-8"))
    assert sidecar == vendored
    assert "lu" not in sidecar["languages"]
    assert sidecar["languages"]["ff"] == "fuv_Latn"
    assert sidecar["model_license"] == "CC-BY-NC-4.0"


def test_nllb_only_language_requires_configured_sidecar(monkeypatch):
    from app.services.translation.auto_translator import language_has_machine_translation

    monkeypatch.delenv("NLLB_SIDECAR_URL", raising=False)
    assert language_has_machine_translation("ak") is False
    assert language_has_machine_translation("de") is True
    assert language_has_machine_translation("lu") is False
    monkeypatch.setenv("NLLB_SIDECAR_URL", "http://nllb:9100")
    assert language_has_machine_translation("ak") is True
    assert language_has_machine_translation("lu") is False


def test_verified_down_engine_is_not_swapped():
    from app.services.translation.auto_translator import resolve_requested_service

    name, err = resolve_requested_service(
        "nllb",
        ["ifrc", "nllb"],
        {"nllb": False, "ifrc": True},
        status_verified=True,
    )
    assert name == "nllb"
    assert err and "unavailable" in err

    kept, quiet = resolve_requested_service(
        "nllb",
        ["nllb"],
        {"nllb": False},
        status_verified=False,
    )
    assert kept == "nllb"
    assert quiet is None

    fallback, fallback_err = resolve_requested_service(
        "missing",
        ["ifrc"],
        {},
        status_verified=True,
    )
    assert fallback is None
    assert fallback_err is None


def test_engine_trace_reports_the_engine_that_ran():
    import threading

    from app.services.translation.auto_translator import AutoTranslator

    translator = AutoTranslator.__new__(AutoTranslator)
    translator._engine_trace = threading.local()
    translator.begin_engine_trace()
    translator.note_engine("nllb")
    assert translator.finish_engine_trace(fallback="ifrc") == "nllb"
    assert translator.finish_engine_trace(fallback="ifrc") == "nllb"


def test_shipped_gold_set_is_not_an_engine_quality_claim():
    from app.services.translation.gold_eval import gold_set_ready, load_gold_set

    assert gold_set_ready(load_gold_set()) is False
