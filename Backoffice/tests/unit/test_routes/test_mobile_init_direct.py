"""Tests for app/routes/api/mobile/__init__.py — version enforcement logic."""
import pytest
from unittest.mock import patch

pytestmark = [pytest.mark.unit]


class TestParseVersion:
    def test_valid_semver(self, app):
        from app.routes.api.mobile import _parse_version
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_single_segment(self, app):
        from app.routes.api.mobile import _parse_version
        assert _parse_version("5") == (5,)

    def test_invalid_non_numeric(self, app):
        from app.routes.api.mobile import _parse_version
        # Non-numeric segments should return an empty tuple
        assert _parse_version("abc.1.2") == ()

    def test_invalid_none(self, app):
        from app.routes.api.mobile import _parse_version
        # None value should return an empty tuple (AttributeError path)
        assert _parse_version(None) == ()

    def test_leading_trailing_whitespace(self, app):
        from app.routes.api.mobile import _parse_version
        assert _parse_version("  2.0.1  ") == (2, 0, 1)


class TestCheckMinimumAppVersion:
    """Tests for the before_request hook that rejects outdated client versions."""

    def test_no_min_version_configured_returns_none(self, app):
        """When no min version is set the hook should return None (pass-through)."""
        from app.routes.api.mobile import _check_minimum_app_version

        with app.test_request_context('/api/mobile/v1/test', headers={}):
            with patch(
                'app.routes.api.mobile.get_mobile_min_app_version',
                return_value=None,
                create=True,
            ):
                app.config.pop('MOBILE_MIN_APP_VERSION', None)
                # Patch via module import path used inside the function
                with patch(
                    'app.services.platform.app_settings_service.get_mobile_min_app_version',
                    return_value=None,
                ):
                    result = _check_minimum_app_version()
        assert result is None

    def test_no_client_version_header_returns_none(self, app):
        """Missing X-App-Version header should pass through even if min version is set."""
        from app.routes.api.mobile import _check_minimum_app_version

        with app.test_request_context('/api/mobile/v1/test', headers={}):
            with patch(
                'app.services.platform.app_settings_service.get_mobile_min_app_version',
                return_value='2.0.0',
            ):
                result = _check_minimum_app_version()
        assert result is None

    def test_client_version_meets_minimum_returns_none(self, app):
        """Client that meets or exceeds the minimum should pass through."""
        from app.routes.api.mobile import _check_minimum_app_version

        with app.test_request_context(
            '/api/mobile/v1/test',
            headers={'X-App-Version': '2.1.0'},
        ):
            with patch(
                'app.services.platform.app_settings_service.get_mobile_min_app_version',
                return_value='2.0.0',
            ):
                result = _check_minimum_app_version()
        assert result is None

    def test_client_version_below_minimum_returns_426(self, app):
        """Outdated client version should receive 426 Upgrade Required."""
        from app.routes.api.mobile import _check_minimum_app_version

        with app.test_request_context(
            '/api/mobile/v1/test',
            headers={'X-App-Version': '1.9.0'},
        ):
            with patch(
                'app.services.platform.app_settings_service.get_mobile_min_app_version',
                return_value='2.0.0',
            ):
                result = _check_minimum_app_version()

        assert result is not None
        if isinstance(result, tuple):
            resp, status = result[0], result[1]
        else:
            resp, status = result, result.status_code
        assert status == 426

    def test_service_exception_falls_back_to_config(self, app):
        """When get_mobile_min_app_version raises, fall back to MOBILE_MIN_APP_VERSION config."""
        from app.routes.api.mobile import _check_minimum_app_version

        app.config['MOBILE_MIN_APP_VERSION'] = '3.0.0'
        try:
            with app.test_request_context(
                '/api/mobile/v1/test',
                headers={'X-App-Version': '2.0.0'},
            ):
                with patch(
                    'app.services.platform.app_settings_service.get_mobile_min_app_version',
                    side_effect=RuntimeError('db down'),
                ):
                    result = _check_minimum_app_version()

            assert result is not None
            if isinstance(result, tuple):
                _, status = result[0], result[1]
            else:
                status = result.status_code
            assert status == 426
        finally:
            app.config.pop('MOBILE_MIN_APP_VERSION', None)

    def test_service_exception_no_config_returns_none(self, app):
        """When service raises and no config key, return None."""
        from app.routes.api.mobile import _check_minimum_app_version

        app.config.pop('MOBILE_MIN_APP_VERSION', None)
        with app.test_request_context('/api/mobile/v1/test', headers={}):
            with patch(
                'app.services.platform.app_settings_service.get_mobile_min_app_version',
                side_effect=RuntimeError('db down'),
            ):
                result = _check_minimum_app_version()
        assert result is None

    def test_equal_version_returns_none(self, app):
        """Exact match with minimum version should pass through."""
        from app.routes.api.mobile import _check_minimum_app_version

        with app.test_request_context(
            '/api/mobile/v1/test',
            headers={'X-App-Version': '2.0.0'},
        ):
            with patch(
                'app.services.platform.app_settings_service.get_mobile_min_app_version',
                return_value='2.0.0',
            ):
                result = _check_minimum_app_version()
        assert result is None
