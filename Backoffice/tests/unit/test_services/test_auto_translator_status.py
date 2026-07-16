"""Tests for non-blocking translation service status checks.

Regression coverage for the 2026-07-16 gateway-504 incident:
/admin/api/translation_services must answer immediately from cache (or an
optimistic default) and never run service probes on the request thread; the
probes themselves must be cheap calls bounded by STATUS_PROBE_TIMEOUT_SECONDS,
never real translations with production timeouts/retries.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app.services.translation.auto_translator import (
    STATUS_PROBE_TIMEOUT_SECONDS,
    AutoTranslator,
    GoogleTranslateService,
    IFRCTranslationService,
    LibreTranslateService,
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
    def test_cold_cache_returns_optimistic_immediately(self):
        tr = _make_translator({'ifrc': _service(healthy=False, delay=0.4)})

        t0 = time.monotonic()
        result = tr.check_service_status()
        elapsed = time.monotonic() - t0

        assert result == {'ifrc': True}  # optimistic while probing
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
            assert result == {'ifrc': True}
            svc.check_health.assert_not_called()
        finally:
            tr._status_probe_lock.release()

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
