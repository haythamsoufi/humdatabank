"""Unit tests for the X-App-Version enforcement middleware."""
import pytest

PREFIX = '/api/mobile/v1'


@pytest.mark.unit
class TestVersionMiddleware:
    def test_no_config_passes(self, client, app):
        """When MOBILE_MIN_APP_VERSION is not set, all requests pass."""
        app.config.pop('MOBILE_MIN_APP_VERSION', None)
        resp = client.get(f'{PREFIX}/auth/session')
        assert resp.status_code != 426

    def test_no_header_passes(self, client, app):
        """When X-App-Version is absent, the middleware does not block."""
        app.config['MOBILE_MIN_APP_VERSION'] = '2.0.0'
        try:
            resp = client.get(f'{PREFIX}/auth/session')
            assert resp.status_code != 426
        finally:
            app.config.pop('MOBILE_MIN_APP_VERSION', None)

    def test_old_version_blocked(self, client, app):
        """Client below minimum gets 426."""
        app.config['MOBILE_MIN_APP_VERSION'] = '2.0.0'
        try:
            resp = client.get(
                f'{PREFIX}/auth/session',
                headers={'X-App-Version': '1.5.0'},
            )
            assert resp.status_code == 426
            body = resp.get_json()
            assert body['error_code'] == 'APP_UPDATE_REQUIRED'
        finally:
            app.config.pop('MOBILE_MIN_APP_VERSION', None)

    def test_current_version_passes(self, client, app):
        """Client at or above minimum passes."""
        app.config['MOBILE_MIN_APP_VERSION'] = '2.0.0'
        try:
            resp = client.get(
                f'{PREFIX}/auth/session',
                headers={'X-App-Version': '2.0.0'},
            )
            assert resp.status_code != 426
        finally:
            app.config.pop('MOBILE_MIN_APP_VERSION', None)
