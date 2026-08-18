"""Tests for the self-hosted NLLB sidecar integration (long-tail languages).

Covers NLLBTranslationService (translate_text/translate_batch/check_health,
circuit breaker) and its opt-in wiring into AutoTranslator._init_services.
"""

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
        with patch(
            "app.services.translation.auto_translator.requests.post",
            return_value=_response(200, {"text": "Selam alem", "engine": "nllb", "deferred": False}),
        ) as mock_post:
            result = svc.translate_text("Hello world", "am", "en")
        assert result == "Selam alem"
        args, kwargs = mock_post.call_args
        assert args[0] == "http://nllb:9100/api/translate"
        assert kwargs["timeout"] == 30

    def test_api_key_sent_as_header(self):
        svc = NLLBTranslationService(api_key="k123", base_url="http://nllb:9100")
        with patch(
            "app.services.translation.auto_translator.requests.post",
            return_value=_response(200, {"text": "x", "deferred": False}),
        ) as mock_post:
            svc.translate_text("Hello", "am", "en")
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["x-api-key"] == "k123"

    def test_same_source_and_target_short_circuits(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch("app.services.translation.auto_translator.requests.post") as mock_post:
            assert svc.translate_text("Hello", "en", "en") is None
        mock_post.assert_not_called()

    def test_deferred_response_treated_as_no_translation(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch(
            "app.services.translation.auto_translator.requests.post",
            return_value=_response(200, {"text": "Hello", "deferred": True}),
        ):
            assert svc.translate_text("Hello", "am", "en") is None

    def test_core_language_409_returns_none(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch(
            "app.services.translation.auto_translator.requests.post",
            return_value=_response(409, text="core language"),
        ):
            assert svc.translate_text("Hello", "fr", "en") is None

    def test_model_loading_503_returns_none(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch(
            "app.services.translation.auto_translator.requests.post",
            return_value=_response(503, text="loading"),
        ):
            assert svc.translate_text("Hello", "am", "en") is None

    def test_unsupported_language_400_returns_none(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch(
            "app.services.translation.auto_translator.requests.post",
            return_value=_response(400, text="bad code"),
        ):
            assert svc.translate_text("Hello", "zz", "en") is None

    def test_invalid_api_key_401_returns_none(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch(
            "app.services.translation.auto_translator.requests.post",
            return_value=_response(401, text="bad key"),
        ):
            assert svc.translate_text("Hello", "am", "en") is None

    def test_connection_error_trips_circuit_breaker(self):
        import requests as requests_module

        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch(
            "app.services.translation.auto_translator.requests.post",
            side_effect=requests_module.exceptions.ConnectionError("refused"),
        ):
            assert svc.translate_text("Hello", "am", "en") is None
        assert svc._is_circuit_open()

        # Subsequent calls short-circuit without hitting the network.
        with patch("app.services.translation.auto_translator.requests.post") as mock_post:
            assert svc.translate_text("Hello", "am", "en") is None
        mock_post.assert_not_called()


class TestNLLBTranslateBatch:
    def test_successful_batch(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        batch_response = [
            {"text": "A1", "deferred": False},
            {"text": "A2", "deferred": False},
        ]
        with patch(
            "app.services.translation.auto_translator.requests.post",
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
        with patch(
            "app.services.translation.auto_translator.requests.post",
            return_value=_response(200, batch_response),
        ):
            result = svc.translate_batch(["Hello", "World"], "am", "en")
        assert result == ["A1", None]

    def test_empty_input_returns_empty_list(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch("app.services.translation.auto_translator.requests.post") as mock_post:
            assert svc.translate_batch([], "am", "en") == []
        mock_post.assert_not_called()

    def test_response_shape_mismatch_returns_all_none(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch(
            "app.services.translation.auto_translator.requests.post",
            return_value=_response(200, [{"text": "only-one", "deferred": False}]),
        ):
            result = svc.translate_batch(["Hello", "World"], "am", "en")
        assert result == [None, None]

    def test_non_200_returns_all_none(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch(
            "app.services.translation.auto_translator.requests.post",
            return_value=_response(500, text="boom"),
        ):
            result = svc.translate_batch(["Hello", "World"], "am", "en")
        assert result == [None, None]


class TestNLLBCheckHealth:
    def test_ready_model_reports_healthy(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch(
            "app.services.translation.auto_translator.requests.get",
            return_value=_response(200, {"ok": True, "status": "ready"}),
        ) as mock_get:
            assert svc.check_health() is True
        args, kwargs = mock_get.call_args
        assert args[0] == "http://nllb:9100/health"
        assert kwargs["timeout"] == STATUS_PROBE_TIMEOUT_SECONDS

    def test_loading_model_reports_unhealthy_despite_200(self):
        """/health always answers 200 -- readiness is signalled by the `ok` field."""
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch(
            "app.services.translation.auto_translator.requests.get",
            return_value=_response(200, {"ok": False, "status": "loading"}),
        ):
            assert svc.check_health() is False

    def test_non_200_reports_unhealthy(self):
        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch(
            "app.services.translation.auto_translator.requests.get",
            return_value=_response(503),
        ):
            assert svc.check_health() is False

    def test_connection_error_trips_circuit_and_reports_unhealthy(self):
        import requests as requests_module

        svc = NLLBTranslationService(base_url="http://nllb:9100")
        with patch(
            "app.services.translation.auto_translator.requests.get",
            side_effect=requests_module.exceptions.ConnectionError("refused"),
        ):
            assert svc.check_health() is False
        assert svc._is_circuit_open()
