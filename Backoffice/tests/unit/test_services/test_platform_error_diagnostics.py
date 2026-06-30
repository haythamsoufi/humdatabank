"""Tests for platform 5xx diagnostics and request pressure tracking."""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.services.monitoring import request_pressure
from app.services.monitoring.platform_error_diagnostics import (
    attach_platform_5xx_diagnostics,
    build_platform_5xx_diagnostics,
    is_platform_5xx,
)


@pytest.fixture(autouse=True)
def reset_pressure_state():
    request_pressure.reset_for_tests()
    yield
    request_pressure.reset_for_tests()


class TestIsPlatform5xx:
    def test_true_for_gateway_errors(self):
        assert is_platform_5xx(502) is True
        assert is_platform_5xx(503) is True
        assert is_platform_5xx(504) is True

    def test_false_for_403(self):
        assert is_platform_5xx(403) is False


class TestRequestPressure:
    def test_register_and_snapshot_inflight(self):
        rid = request_pressure.register_inflight(
            method='GET',
            path='/forms/assignment/1',
            endpoint='forms.entry',
        )
        snap = request_pressure.snapshot_inflight(stale_after_seconds=25)
        assert snap['in_flight_count'] == 1
        assert snap['in_flight_requests'][0]['path'] == '/forms/assignment/1'
        request_pressure.unregister_inflight(rid, duration_seconds=0.01)
        snap2 = request_pressure.snapshot_inflight()
        assert snap2['in_flight_count'] == 0

    def test_stale_inflight_flagged(self):
        rid = request_pressure.register_inflight(method='POST', path='/slow')
        with patch('app.services.monitoring.request_pressure.time') as mock_time:
            mock_time.time.return_value = time.time() + 30
            snap = request_pressure.snapshot_inflight(stale_after_seconds=25)
        assert snap['stale_in_flight_count'] == 1
        assert snap['in_flight_requests'][0]['stale'] is True
        request_pressure.unregister_inflight(rid, duration_seconds=30)

    def test_traffic_counts(self):
        now = time.time()
        with patch('app.services.monitoring.request_pressure.time') as mock_time:
            mock_time.time.return_value = now
            request_pressure.record_traffic()
            request_pressure.record_traffic()
            snap = request_pressure.snapshot_inflight()
        assert snap['traffic_last_60s'] == 2
        assert snap['traffic_last_5m'] == 2

    def test_slow_completion_recorded(self):
        rid = request_pressure.register_inflight(method='GET', path='/heavy')
        request_pressure.unregister_inflight(rid, duration_seconds=6.5)
        snap = request_pressure.snapshot_inflight()
        assert len(snap['recent_slow_completions']) == 1
        assert snap['recent_slow_completions'][0]['path'] == '/heavy'


class TestBuildPlatform5xxDiagnostics:
    def test_includes_summary_and_causes(self):
        request_pressure.register_inflight(method='GET', path='/forms/assignment/1641')
        diag = build_platform_5xx_diagnostics(error_code=504, failed_url='/api/forms/presence/sync')
        assert 'diagnostics_summary' in diag
        assert 'likely_causes' in diag
        assert 'worker_metrics' in diag
        assert '504' in diag['diagnostics_summary']

    def test_attach_merges_into_context(self):
        request_pressure.register_inflight(method='POST', path='/api/save')
        ctx = attach_platform_5xx_diagnostics(
            {'url': '/api/save', 'platform': 'azure_app_service'},
            error_code=502,
            failed_url='/api/save',
        )
        assert 'diagnostics_summary' in ctx
        assert 'worker_metrics' in ctx
        assert ctx['likely_causes']

    def test_skips_diagnostics_for_403(self):
        ctx = attach_platform_5xx_diagnostics({'url': '/x'}, error_code=403, failed_url='/x')
        assert 'diagnostics_summary' not in ctx

    def test_db_pool_pressure_cause(self, app):
        request_pressure.register_inflight(method='GET', path='/admin')
        with app.app_context():
            from app import db

            pool = MagicMock()
            pool.size.return_value = 5
            pool.checkedout.return_value = 5
            pool.checkedin.return_value = 0
            pool.overflow.return_value = 3
            with patch.object(db.engine, 'pool', pool):
                diag = build_platform_5xx_diagnostics(error_code=504)
        assert 'db_pool_pressure' in diag['likely_causes']
