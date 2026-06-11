"""
Unit tests for app.utils.auth (API key and session decorators).
"""
from unittest.mock import MagicMock, patch

import pytest
from flask import g
from flask_login import login_user

from app.utils.api_helpers import api_error
from app.utils.auth import (
    _extract_api_key,
    require_api_key,
    require_api_key_or_session,
)

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]


@pytest.mark.unit
class TestExtractApiKey:
    """Test Bearer token extraction from Authorization header."""

    def test_bearer_token_returns_key_and_header_source(self, app):
        with app.test_request_context(
            path='/api/foo',
            headers={'Authorization': 'Bearer secret-key-123'},
        ):
            key, source = _extract_api_key()
            assert key == 'secret-key-123'
            assert source == 'header'

    def test_bearer_token_strips_surrounding_whitespace(self, app):
        with app.test_request_context(
            path='/api/foo',
            headers={'Authorization': 'Bearer   padded-key  '},
        ):
            key, source = _extract_api_key()
            assert key == 'padded-key'
            assert source == 'header'

    def test_empty_bearer_returns_empty_string(self, app):
        with app.test_request_context(
            path='/api/foo',
            headers={'Authorization': 'Bearer '},
        ):
            key, source = _extract_api_key()
            assert key == ''
            assert source == 'header'

    def test_missing_authorization_header(self, app):
        with app.test_request_context(path='/api/foo'):
            key, source = _extract_api_key()
            assert key is None
            assert source is None

    def test_non_bearer_authorization_header(self, app):
        with app.test_request_context(
            path='/api/foo',
            headers={'Authorization': 'Basic dXNlcjpwYXNz'},
        ):
            key, source = _extract_api_key()
            assert key is None
            assert source is None

    def test_bearer_prefix_case_sensitive(self, app):
        with app.test_request_context(
            path='/api/foo',
            headers={'Authorization': 'bearer secret-key'},
        ):
            key, source = _extract_api_key()
            assert key is None
            assert source is None


@pytest.mark.unit
class TestRequireApiKey:
    """Test require_api_key decorator."""

    def test_success_calls_wrapped_function(self, app):
        @require_api_key
        def protected():
            return {'ok': True}

        with app.test_request_context('/api/test'):
            with patch('app.utils.auth.authenticate_db_api_key_only', return_value=True):
                result = protected()
            assert result == {'ok': True}

    def test_success_sets_skip_auth(self, app):
        @require_api_key
        def protected():
            return 'done'

        with app.test_request_context('/api/test'):
            with patch('app.utils.auth.authenticate_db_api_key_only', return_value=True):
                protected()
            assert g.skip_auth is True

    def test_auth_failure_returns_response_without_calling_view(self, app):
        error_response = api_error('Authentication required', 401)

        @require_api_key
        def protected():
            pytest.fail('view must not run when auth fails')

        with app.test_request_context('/api/test'):
            with patch(
                'app.utils.auth.authenticate_db_api_key_only',
                return_value=error_response,
            ):
                result = protected()
            assert result is error_response
            assert result.status_code == 401

    def test_sets_endpoint_registry_metadata(self, app):
        @require_api_key
        def protected():
            return None

        assert protected._ep_auth == 'api_key'

    def test_preserves_wrapped_function_name(self, app):
        @require_api_key
        def protected():
            return None

        assert protected.__name__ == 'protected'

    def test_logs_usage_when_config_enabled(self, app):
        @require_api_key
        def protected():
            return None

        app.config['LOG_API_KEY_USAGE'] = True
        with app.test_request_context('/api/test', environ_base={'REMOTE_ADDR': '10.0.0.1'}):
            with patch('app.utils.auth.authenticate_db_api_key_only', return_value=True):
                with patch.object(app.logger, 'info') as mock_info:
                    protected()
            mock_info.assert_called_once()
            message = mock_info.call_args[0][0]
            assert '10.0.0.1' in message
            assert 'API key authenticated' in message

    def test_does_not_log_when_config_disabled(self, app):
        @require_api_key
        def protected():
            return None

        app.config['LOG_API_KEY_USAGE'] = False
        with app.test_request_context('/api/test'):
            with patch('app.utils.auth.authenticate_db_api_key_only', return_value=True):
                with patch.object(app.logger, 'info') as mock_info:
                    protected()
            mock_info.assert_not_called()

    def test_with_valid_db_api_key(self, app, db_session, api_key):
        _api_key_obj, full_key = api_key

        @require_api_key
        def protected():
            return {'authenticated': True}

        with app.test_request_context(
            '/api/test',
            headers={'Authorization': f'Bearer {full_key}'},
        ):
            result = protected()
        assert result == {'authenticated': True}
        assert g.skip_auth is True

    def test_with_missing_api_key_returns_401(self, app):
        @require_api_key
        def protected():
            pytest.fail('view must not run without API key')

        with app.test_request_context('/api/test'):
            result = protected()
        assert result.status_code == 401


@pytest.mark.unit
class TestRequireApiKeyOrSession:
    """Test require_api_key_or_session decorator."""

    def test_authenticated_session_skips_api_key_check(self, app, test_user):
        @require_api_key_or_session
        def protected():
            return {'via': 'session'}

        with app.test_request_context('/api/test'):
            login_user(test_user)
            with patch('app.utils.auth.authenticate_db_api_key_only') as mock_auth:
                result = protected()
            mock_auth.assert_not_called()
        assert result == {'via': 'session'}
        assert g.skip_auth is True

    def test_unauthenticated_user_falls_back_to_api_key(self, app):
        mock_user = MagicMock()
        mock_user.is_authenticated = False

        @require_api_key_or_session
        def protected():
            return {'via': 'api_key'}

        with app.test_request_context('/api/test'):
            with patch('app.utils.auth.current_user', mock_user):
                with patch(
                    'app.utils.auth.authenticate_db_api_key_only',
                    return_value=True,
                ) as mock_auth:
                    result = protected()
            mock_auth.assert_called_once()
        assert result == {'via': 'api_key'}
        assert g.skip_auth is True

    def test_anonymous_current_user_requires_api_key(self, app):
        @require_api_key_or_session
        def protected():
            return {'via': 'api_key'}

        with app.test_request_context('/api/test'):
            with patch('app.utils.auth.current_user', None):
                with patch(
                    'app.utils.auth.authenticate_db_api_key_only',
                    return_value=True,
                ) as mock_auth:
                    result = protected()
            mock_auth.assert_called_once()
        assert result == {'via': 'api_key'}

    def test_api_key_failure_returns_error_response(self, app):
        mock_user = MagicMock()
        mock_user.is_authenticated = False
        error_response = api_error('Invalid API key', 401)

        @require_api_key_or_session
        def protected():
            pytest.fail('view must not run when auth fails')

        with app.test_request_context('/api/test'):
            with patch('app.utils.auth.current_user', mock_user):
                with patch(
                    'app.utils.auth.authenticate_db_api_key_only',
                    return_value=error_response,
                ):
                    result = protected()
        assert result is error_response
        assert result.status_code == 401

    def test_sets_endpoint_registry_metadata(self, app):
        @require_api_key_or_session
        def protected():
            return None

        assert protected._ep_auth == 'api_key_or_session'

    def test_preserves_wrapped_function_name(self, app):
        @require_api_key_or_session
        def protected():
            return None

        assert protected.__name__ == 'protected'

    def test_with_valid_db_api_key_when_not_logged_in(self, app, db_session, api_key):
        _api_key_obj, full_key = api_key

        @require_api_key_or_session
        def protected():
            return {'authenticated': True}

        with app.test_request_context(
            '/api/test',
            headers={'Authorization': f'Bearer {full_key}'},
        ):
            result = protected()
        assert result == {'authenticated': True}
        assert g.skip_auth is True

    def test_with_missing_credentials_returns_401(self, app):
        @require_api_key_or_session
        def protected():
            pytest.fail('view must not run without session or API key')

        with app.test_request_context('/api/test'):
            result = protected()
        assert result.status_code == 401
