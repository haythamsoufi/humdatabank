"""Tests for non-blocking translation service status checks.

Regression coverage for the 2026-07-16 gateway-504 incident:
/admin/api/translation_services must answer immediately from cache (or
unavailable when never probed) and never run service probes on the request
thread; the probes themselves must be cheap calls bounded by
STATUS_PROBE_TIMEOUT_SECONDS, never real translations with production
timeouts/retries.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

import requests

from app.services.translation.auto_translator import (
    STATUS_PROBE_TIMEOUT_SECONDS,
    AutoTranslator,
    GoogleTranslateService,
    IFRCTranslationService,
    LibreTranslateService,
    _ENGINE_BATCH_WORKERS,
)

pytestmark = [pytest.mark.unit]


def _make_translator(services):
    """Build an AutoTranslator with injected services, bypassing env-based init."""
    tr = AutoTranslator.__new__(AutoTranslator)
    tr.services = services
    tr.default_service = next(iter(services), None)
    tr._status_cache = None
    tr._status_probe_lock = threading.Lock()
    return tr


def _service(healthy=True, delay=0.0):
    svc = MagicMock()

    def _check_health():
        if delay:
            time.sleep(delay)
        return healthy

    svc.check_health.side_effect = _check_health
    return svc


def _wait_for_cache(tr, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if tr._status_cache is not None:
            return True
        time.sleep(0.01)
    return False


class TestCheckServiceStatusNonBlocking:
    def test_cold_cache_returns_unverified_unavailable_immediately(self):
        tr = _make_translator({'ifrc': _service(healthy=False, delay=0.4)})

        t0 = time.monotonic()
        result = tr.check_service_status()
        elapsed = time.monotonic() - t0

        assert result == {'ifrc': False}  # never available until probed
        assert elapsed < 0.3, f'check_service_status blocked for {elapsed:.2f}s'

    def test_background_refresh_populates_cache(self):
        tr = _make_translator({'ifrc': _service(healthy=False)})

        tr.check_service_status()
        assert _wait_for_cache(tr), 'background probe never populated the cache'

        assert tr.check_service_status() == {'ifrc': False}

    def test_fresh_cache_served_without_probing(self):
        svc = _service()
        tr = _make_translator({'ifrc': svc})
        tr._status_cache = (time.monotonic(), {'ifrc': False})

        assert tr.check_service_status() == {'ifrc': False}
        svc.check_health.assert_not_called()

    def test_stale_cache_served_while_refreshing(self):
        svc = _service(healthy=True, delay=0.4)
        tr = _make_translator({'ifrc': svc})
        stale_ts = time.monotonic() - AutoTranslator._STATUS_CACHE_TTL_SECONDS - 1
        tr._status_cache = (stale_ts, {'ifrc': False})

        t0 = time.monotonic()
        result = tr.check_service_status()
        elapsed = time.monotonic() - t0

        assert result == {'ifrc': False}  # last-known beats blocking
        assert elapsed < 0.3

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and tr._status_cache[0] == stale_ts:
            time.sleep(0.01)
        assert tr._status_cache[0] > stale_ts, 'background refresh never replaced the stale entry'
        assert tr._status_cache[1] == {'ifrc': True}

    def test_probe_in_flight_does_not_stack_and_returns_immediately(self):
        svc = _service()
        tr = _make_translator({'ifrc': svc})

        assert tr._status_probe_lock.acquire(blocking=False)
        try:
            with patch(
                'app.services.translation.auto_translator.threading.Thread'
            ) as mock_thread:
                result = tr.check_service_status()
            mock_thread.assert_not_called()
            assert result == {'ifrc': False}
            svc.check_health.assert_not_called()
        finally:
            tr._status_probe_lock.release()

    def test_wait_for_fresh_status_probes_when_cold(self):
        svc = _service(healthy=False)
        tr = _make_translator({'libre': svc})

        assert tr.wait_for_fresh_status() == {'libre': False}
        svc.check_health.assert_called_once()
        assert tr.has_status_cache() is True

    def test_wait_for_fresh_status_reuses_fresh_cache(self):
        svc = _service(healthy=True)
        tr = _make_translator({'libre': svc})
        tr._status_cache = (time.monotonic(), {'libre': False})

        assert tr.wait_for_fresh_status() == {'libre': False}
        svc.check_health.assert_not_called()

    def test_use_cache_false_probes_synchronously(self):
        svc = _service(healthy=False)
        tr = _make_translator({'ifrc': svc})

        assert tr.check_service_status(use_cache=False) == {'ifrc': False}
        svc.check_health.assert_called_once()

    def test_probe_lock_released_after_background_refresh(self):
        tr = _make_translator({'ifrc': _service()})
        tr.check_service_status()
        assert _wait_for_cache(tr)

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if tr._status_probe_lock.acquire(blocking=False):
                tr._status_probe_lock.release()
                return
            time.sleep(0.01)
        pytest.fail('probe lock was never released after background refresh')

    def test_test_service_swallows_probe_exceptions(self):
        svc = MagicMock()
        svc.check_health.side_effect = RuntimeError('boom')
        svc.service_name = 'ifrc'
        tr = _make_translator({'ifrc': svc})

        assert tr._test_service(svc) is False


class TestServiceSessionReuse:
    """Each service pools persistent connections instead of a fresh TCP+TLS
    handshake per translate_text()/translate_batch() call."""

    def test_service_gets_a_pooled_session(self):
        svc = IFRCTranslationService(api_key='k', base_url='https://ifrc.example.org')
        assert isinstance(svc.session, requests.Session)
        adapter = svc.session.get_adapter('https://ifrc.example.org/api/translate')
        assert adapter.poolmanager.connection_pool_kw.get('maxsize') >= _ENGINE_BATCH_WORKERS

    def test_each_instance_has_its_own_session(self):
        svc_a = IFRCTranslationService(api_key='k', base_url='https://ifrc.example.org')
        svc_b = GoogleTranslateService(api_key='k')
        assert svc_a.session is not svc_b.session


class TestServiceHealthProbes:
    """check_health must be a cheap, tightly-bounded call — never a translation."""

    def _response(self, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        return resp

    def test_google_uses_languages_endpoint_with_tight_timeout(self):
        svc = GoogleTranslateService(api_key='k')
        with patch(
            'app.services.translation.auto_translator.requests.get',
            return_value=self._response(200),
        ) as mock_get:
            assert svc.check_health() is True
        args, kwargs = mock_get.call_args
        assert args[0].endswith('/languages')
        assert kwargs['timeout'] == STATUS_PROBE_TIMEOUT_SECONDS

    def test_google_without_key_is_unavailable(self):
        svc = GoogleTranslateService(api_key=None)
        assert svc.check_health() is False

    def test_libre_uses_languages_endpoint_with_tight_timeout(self):
        svc = LibreTranslateService(base_url='https://libre.example.org')
        with patch(
            'app.services.translation.auto_translator.requests.get',
            return_value=self._response(200),
        ) as mock_get:
            assert svc.check_health() is True
        args, kwargs = mock_get.call_args
        assert args[0] == 'https://libre.example.org/languages'
        assert kwargs['timeout'] == STATUS_PROBE_TIMEOUT_SECONDS

    def test_libre_localhost_short_circuits(self):
        svc = LibreTranslateService(base_url='http://localhost:5001')
        with patch(
            'app.services.translation.auto_translator.requests.get'
        ) as mock_get:
            assert svc.check_health() is False
        mock_get.assert_not_called()

    def test_libre_open_circuit_short_circuits(self):
        svc = LibreTranslateService(base_url='https://libre.example.org')
        svc._trip_circuit()
        with patch(
            'app.services.translation.auto_translator.requests.get'
        ) as mock_get:
            assert svc.check_health() is False
        mock_get.assert_not_called()

    def test_ifrc_probe_is_bounded_and_minimal(self):
        svc = IFRCTranslationService(api_key='k', base_url='https://ifrc.example.org')
        with patch(
            'app.services.translation.auto_translator.requests.post',
            return_value=self._response(200),
        ) as mock_post:
            assert svc.check_health() is True
        _, kwargs = mock_post.call_args
        assert kwargs['timeout'] == STATUS_PROBE_TIMEOUT_SECONDS

    def test_rate_limited_service_counts_as_up(self):
        svc = IFRCTranslationService(api_key='k')
        with patch(
            'app.services.translation.auto_translator.requests.post',
            return_value=self._response(429),
        ):
            assert svc.check_health() is True

    def test_server_error_counts_as_down(self):
        svc = IFRCTranslationService(api_key='k')
        with patch(
            'app.services.translation.auto_translator.requests.post',
            return_value=self._response(503),
        ):
            assert svc.check_health() is False


class TestIfrcRetriesTransientFailures:
    """translate_text() must retry 429/500/502/503/504 like LibreTranslateService,
    instead of dropping the fragment on the first rate-limit or wrapper 500."""

    def _response(self, status_code, *, translated=None, text=""):
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = text
        if translated is not None:
            resp.headers = {'Content-Type': 'application/json'}
            resp.json.return_value = [{"translations": [{"text": translated}]}]
        else:
            resp.headers = {'Content-Type': 'text/plain'}
        return resp

    def test_retries_rate_limit_then_succeeds(self, monkeypatch):
        svc = IFRCTranslationService(api_key='k', base_url='https://ifrc.example.org')
        mock_post = MagicMock(
            side_effect=[
                self._response(429, text="rate limited"),
                self._response(200, translated="Salut"),
            ]
        )
        monkeypatch.setattr(svc.session, 'post', mock_post)
        monkeypatch.setattr('time.sleep', lambda _s: None)

        assert svc.translate_text("Hello", "fr") == "Salut"
        assert mock_post.call_count == 2

    def test_retries_upstream_5xx_like_libretranslate(self, monkeypatch):
        svc = IFRCTranslationService(api_key='k', base_url='https://ifrc.example.org')
        mock_post = MagicMock(
            side_effect=[
                self._response(503, text="upstream down"),
                self._response(200, translated="Salut"),
            ]
        )
        monkeypatch.setattr(svc.session, 'post', mock_post)
        monkeypatch.setattr('time.sleep', lambda _s: None)

        assert svc.translate_text("Hello", "fr") == "Salut"
        assert mock_post.call_count == 2

    def test_retries_wrapper_500_then_succeeds(self, monkeypatch):
        svc = IFRCTranslationService(api_key='k', base_url='https://ifrc.example.org')
        mock_post = MagicMock(
            side_effect=[
                self._response(
                    500,
                    text='{"type":"https://tools.ietf.org/html/rfc9110#section-15.6.1","title":"An error occurred while processing your request.","status":500}',
                ),
                self._response(200, translated="Contexte"),
            ]
        )
        monkeypatch.setattr(svc.session, 'post', mock_post)
        monkeypatch.setattr('time.sleep', lambda _s: None)

        assert svc.translate_text("Context", "fr") == "Contexte"
        assert mock_post.call_count == 2

    def test_gives_up_after_three_rate_limit_responses(self, monkeypatch):
        svc = IFRCTranslationService(api_key='k', base_url='https://ifrc.example.org')
        mock_post = MagicMock(return_value=self._response(429, text="rate limited"))
        monkeypatch.setattr(svc.session, 'post', mock_post)
        sleeps = []
        monkeypatch.setattr('time.sleep', lambda s: sleeps.append(s))

        assert svc.translate_text("Hello", "fr") is None
        assert mock_post.call_count == 3
        assert sleeps == [0.6, 1.2]

    def test_non_transient_error_does_not_retry(self, monkeypatch):
        svc = IFRCTranslationService(api_key='k', base_url='https://ifrc.example.org')
        mock_post = MagicMock(return_value=self._response(401, text="unauthorized"))
        monkeypatch.setattr(svc.session, 'post', mock_post)

        assert svc.translate_text("Hello", "fr") is None
        assert mock_post.call_count == 1

    def test_request_failure_is_warning_not_error(self, monkeypatch):
        svc = IFRCTranslationService(api_key='k', base_url='https://ifrc.example.org')
        monkeypatch.setattr(
            svc.session,
            'post',
            MagicMock(side_effect=requests.exceptions.Timeout("timed out")),
        )

        with patch('app.services.translation.auto_translator.logger.warning') as warn, patch(
            'app.services.translation.auto_translator.logger.error'
        ) as err:
            assert svc.translate_text("Context", "fr") is None
        warn.assert_called()
        assert any("IFRC API request failed" in str(c) for c in warn.call_args_list)
        err.assert_not_called()


class TestGoogleRetriesTransientFailures:
    def _response(self, status_code, *, translated=None, text=""):
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = text
        if status_code >= 400:
            resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
                f"{status_code}", response=resp
            )
        else:
            resp.raise_for_status.return_value = None
        if translated is not None:
            resp.json.return_value = {"data": {"translations": [{"translatedText": translated}]}}
        return resp

    def test_retries_wrapper_500_then_succeeds(self, monkeypatch):
        svc = GoogleTranslateService(api_key='k')
        mock_post = MagicMock(
            side_effect=[
                self._response(500, text="upstream"),
                self._response(200, translated="Contexte"),
            ]
        )
        monkeypatch.setattr(svc.session, 'post', mock_post)
        monkeypatch.setattr('time.sleep', lambda _s: None)

        assert svc.translate_text("Context", "fr") == "Contexte"
        assert mock_post.call_count == 2

    def test_exhausted_500_is_warning_not_error(self, monkeypatch):
        svc = GoogleTranslateService(api_key='k')
        monkeypatch.setattr(
            svc.session, 'post', MagicMock(return_value=self._response(500, text="boom"))
        )
        monkeypatch.setattr('time.sleep', lambda _s: None)

        with patch('app.services.translation.auto_translator.logger.warning') as warn, patch(
            'app.services.translation.auto_translator.logger.error'
        ) as err:
            assert svc.translate_text("Context", "fr") is None
        warn.assert_called()
        assert any("Google Translate API transient" in str(c) for c in warn.call_args_list)
        err.assert_not_called()


class TestLibreRetriesTransientFailures:
    def _response(self, status_code, *, translated=None, text=""):
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = text
        if status_code >= 400:
            resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
                f"{status_code}", response=resp
            )
        else:
            resp.raise_for_status.return_value = None
        if translated is not None:
            resp.json.return_value = {"translatedText": translated}
        return resp

    def test_retries_500_then_succeeds(self, monkeypatch):
        svc = LibreTranslateService(base_url='https://libre.example.org')
        mock_post = MagicMock(
            side_effect=[
                self._response(500, text="upstream"),
                self._response(200, translated="Contexte"),
            ]
        )
        monkeypatch.setattr(svc.session, 'post', mock_post)
        monkeypatch.setattr(svc, '_get_supported_languages', lambda: None)
        monkeypatch.setattr('time.sleep', lambda _s: None)

        assert svc.translate_text("Context", "fr") == "Contexte"
        assert mock_post.call_count == 2


class TestEngineBatchParallel:
    def test_ifrc_batch_preserves_order(self):
        svc = IFRCTranslationService(api_key='k', base_url='https://ifrc.example.org')

        def fake(text, target_language, source_language='en'):
            return f"{text}:{target_language}"

        svc.translate_text = fake
        assert svc.translate_batch(['Hello', 'Save', 'Cancel'], 'fr') == [
            'Hello:fr',
            'Save:fr',
            'Cancel:fr',
        ]

    def test_ifrc_batch_runs_concurrently(self):
        svc = IFRCTranslationService(api_key='k', base_url='https://ifrc.example.org')
        started = threading.Event()
        release = threading.Event()
        inflight = 0
        lock = threading.Lock()
        peak = 0

        def fake(text, target_language, source_language='en'):
            nonlocal inflight, peak
            with lock:
                inflight += 1
                peak = max(peak, inflight)
                if inflight >= 2:
                    started.set()
            assert release.wait(timeout=2)
            with lock:
                inflight -= 1
            return text

        svc.translate_text = fake
        worker = threading.Thread(target=lambda: svc.translate_batch(['a', 'b', 'c', 'd'], 'es'))
        worker.start()
        assert started.wait(timeout=2)
        release.set()
        worker.join(timeout=2)
        assert peak >= 2


def test_language_has_machine_translation_skips_romansh():
    from app.services.translation.auto_translator import (
        IFRCTranslationService,
        language_has_machine_translation,
    )

    assert language_has_machine_translation("de") is True
    assert language_has_machine_translation("rm") is False
    svc = IFRCTranslationService.__new__(IFRCTranslationService)
    svc.service_name = "ifrc"
    assert svc.translate_text("Not reported", "rm") is None
