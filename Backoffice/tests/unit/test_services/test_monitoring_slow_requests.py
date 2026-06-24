"""Tests for slow/stuck request logging."""

import time
from unittest.mock import MagicMock, patch

import pytest
from flask import g

from app.services.monitoring import slow_requests


@pytest.fixture(autouse=True)
def enable_slow_request_logging(app):
    app.config['SLOW_REQUEST_LOG_ENABLED'] = True
    app.config['SLOW_REQUEST_THRESHOLD_SECONDS'] = 30
    app.config['SLOW_REQUEST_STUCK_WARNING_SECONDS'] = 60
    app.config['SLOW_REQUEST_STUCK_CRITICAL_SECONDS'] = 100
    slow_requests.configure(app)
    yield
    slow_requests.configure(app)


class TestShouldTrack:
    def test_disabled_when_config_off(self, app):
        app.config['SLOW_REQUEST_LOG_ENABLED'] = False
        slow_requests.configure(app)
        with app.test_request_context('/slow'):
            assert slow_requests._should_track() is False

    def test_skips_static_assets(self, app):
        with app.test_request_context('/static/js/main.js'):
            assert slow_requests._should_track() is False

    def test_skips_health_check(self, app):
        with app.test_request_context('/health'):
            assert slow_requests._should_track() is False

    def test_skips_long_lived_connections(self, app):
        with app.test_request_context('/api/notifications/ws'):
            assert slow_requests._should_track() is False

    def test_tracks_normal_requests(self, app):
        with app.test_request_context('/forms/entry'):
            assert slow_requests._should_track() is True


class TestTrackSlowRequestStart:
    def test_disabled_does_nothing(self, app):
        app.config['SLOW_REQUEST_LOG_ENABLED'] = False
        slow_requests.configure(app)
        with app.test_request_context('/forms/entry'):
            slow_requests.track_slow_request_start()
            assert not hasattr(g, 'slow_request_start')

    def test_sets_tracking_attributes(self, app):
        with app.test_request_context('/forms/entry', method='POST', query_string='id=1'):
            slow_requests.track_slow_request_start()
            assert hasattr(g, 'slow_request_start')
            assert g.slow_request_path == '/forms/entry'
            assert g.slow_request_method == 'POST'
            assert g.slow_request_query == 'id=1'
            slow_requests.track_slow_request_teardown()

    def test_schedules_inflight_timers(self, app):
        with patch.object(slow_requests, '_InflightTimer') as mock_timer_cls:
            mock_timer = MagicMock()
            mock_timer_cls.return_value = mock_timer
            with app.test_request_context('/forms/entry'):
                slow_requests.track_slow_request_start()
            assert mock_timer_cls.call_count == 2
            assert mock_timer.start.call_count == 2
            slow_requests.track_slow_request_teardown()


class TestTrackSlowRequestEnd:
    def test_fast_request_not_logged(self, app):
        with app.test_request_context('/fast'):
            slow_requests.track_slow_request_start()
            with patch.object(app.logger, 'warning') as mock_warning:
                slow_requests.track_slow_request_end()
            mock_warning.assert_not_called()

    def test_slow_request_logged_on_completion(self, app):
        with app.test_request_context('/slow', method='GET'):
            slow_requests.track_slow_request_start()
            g.slow_request_start = time.time() - 35.0
            with patch.object(app.logger, 'warning') as mock_warning:
                slow_requests.track_slow_request_end()
            mock_warning.assert_called_once()
            message = mock_warning.call_args[0][0]
            assert '[SLOW_REQUEST]' in message
            assert '/slow' in message

    def test_cancels_inflight_timers(self, app):
        mock_timer = MagicMock()
        with app.test_request_context('/slow'):
            g.slow_request_start = time.time() - 35.0
            g.slow_request_timers = [mock_timer]
            slow_requests.track_slow_request_end()
        mock_timer.cancel.assert_called_once()


class TestInflightTimer:
    def test_cancelled_timer_does_not_raise(self, app):
        timer = slow_requests._InflightTimer(
            app,
            start_time=time.time(),
            delay_seconds=0.05,
            level='warning',
            tag='STUCK_REQUEST',
            method='GET',
            path='/slow',
        )
        timer.start()
        timer.cancel()
        time.sleep(0.08)

    def test_fires_outside_request_context(self, app):
        timer = slow_requests._InflightTimer(
            app,
            start_time=time.time(),
            delay_seconds=0.05,
            level='warning',
            tag='STUCK_REQUEST',
            method='GET',
            path='/slow',
            query='id=1',
        )
        with patch.object(app.logger, 'warning') as mock_warning:
            timer.start()
            time.sleep(0.1)
        mock_warning.assert_called_once()
        message = mock_warning.call_args[0][0]
        assert '[STUCK_REQUEST]' in message
        assert '/slow' in message
        assert 'method=GET' in message
