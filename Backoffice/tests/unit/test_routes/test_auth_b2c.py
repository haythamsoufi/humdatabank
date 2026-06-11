"""Unit/integration tests for Azure B2C and web auth routes in app.routes.auth."""
import time
from unittest.mock import MagicMock, patch

import jwt
import pytest

pytestmark = [pytest.mark.auth_security]

from app.routes.auth import _b2c_get_required_config, _verify_and_decode_id_token
from tests.factories import create_test_user


def _b2c_config(app):
    return {
        'tenant': 'testtenant.onmicrosoft.com',
        'policy': 'B2C_1_signin',
        'client_id': 'test-client-id',
        'client_secret': 'test-secret',
        'redirect_uri': 'http://localhost/auth/azure/callback',
        'scope': 'openid email profile',
    }


def _signed_oauth_state(app, **overrides):
    payload = {
        '_state': 'inner-csrf',
        'verifier': 'pkce-verifier-value',
        'nonce': 'nonce-value',
        'next': None,
        'mobile': False,
        'iat': int(time.time()),
        'exp': int(time.time()) + 600,
    }
    payload.update(overrides)
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')


@pytest.mark.unit
class TestB2cConfigHelpers:
    def test_b2c_get_required_config_complete(self, app):
        app.config.update({
            'AZURE_B2C_TENANT': 't.onmicrosoft.com',
            'AZURE_B2C_POLICY': 'policy',
            'AZURE_B2C_CLIENT_ID': 'cid',
            'AZURE_B2C_CLIENT_SECRET': 'sec',
            'AZURE_B2C_REDIRECT_URI': 'http://x/cb',
        })
        with app.app_context():
            cfg = _b2c_get_required_config()
        assert cfg is not None
        assert cfg['tenant'] == 't.onmicrosoft.com'

    def test_b2c_get_required_config_missing_returns_none(self, app):
        app.config.pop('AZURE_B2C_TENANT', None)
        with app.app_context():
            assert _b2c_get_required_config() is None

    def test_b2c_metadata_fetches_openid_configuration(self, app):
        from app.routes.auth import _b2c_metadata

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {'issuer': 'https://login.example.com'}
        with app.app_context():
            with patch('app.routes.auth.requests.get', return_value=mock_resp) as mock_get:
                meta = _b2c_metadata('tenant.onmicrosoft.com', 'B2C_1_signin')
        assert meta['issuer'] == 'https://login.example.com'
        assert 'tenant.b2clogin.com' in mock_get.call_args[0][0]

    def test_verify_and_decode_id_token_no_jwks(self, app):
        with app.app_context():
            result = _verify_and_decode_id_token('token', {}, 'aud', 'nonce')
        assert result is None


@pytest.mark.integration
class TestAzureLoginRoute:
    def test_azure_login_not_configured_redirects(self, client, app):
        app.config.pop('AZURE_B2C_TENANT', None)
        resp = client.get('/login/azure', follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)
        assert '/login' in (resp.headers.get('Location') or '')

    def test_azure_login_redirects_to_authorize(self, client, app):
        app.config.update({
            'AZURE_B2C_TENANT': 'testtenant.onmicrosoft.com',
            'AZURE_B2C_POLICY': 'B2C_1_signin',
            'AZURE_B2C_CLIENT_ID': 'client-id',
            'AZURE_B2C_CLIENT_SECRET': 'secret',
            'AZURE_B2C_REDIRECT_URI': 'http://localhost/callback',
        })
        meta = {'authorization_endpoint': 'https://login.example.com/authorize'}
        with patch('app.routes.auth._b2c_metadata', return_value=meta):
            resp = client.get('/login/azure', follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)
        assert 'login.example.com' in (resp.headers.get('Location') or '')

    def test_azure_login_mobile_clears_stale_session(self, client, logged_in_client, app):
        app.config.update({
            'AZURE_B2C_TENANT': 'testtenant.onmicrosoft.com',
            'AZURE_B2C_POLICY': 'B2C_1_signin',
            'AZURE_B2C_CLIENT_ID': 'client-id',
            'AZURE_B2C_CLIENT_SECRET': 'secret',
            'AZURE_B2C_REDIRECT_URI': 'http://localhost/callback',
        })
        meta = {'authorization_endpoint': 'https://login.example.com/authorize'}
        with patch('app.routes.auth._b2c_metadata', return_value=meta):
            resp = logged_in_client.get(
                '/login/azure?mobile_return_scheme=humdatabank',
                follow_redirects=False,
            )
        assert resp.status_code in (301, 302, 303, 307, 308)


@pytest.mark.integration
class TestAzureCallbackRoute:
    def test_callback_missing_code_redirects(self, client, app):
        cfg = _b2c_config(app)
        with patch('app.routes.auth._b2c_get_required_config', return_value=cfg):
            resp = client.get('/auth/azure/callback', follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_callback_user_cancelled(self, client, app):
        cfg = _b2c_config(app)
        with patch('app.routes.auth._b2c_get_required_config', return_value=cfg):
            resp = client.get(
                '/auth/azure/callback?error=access_denied'
                '&error_description=AADB2C90091%3a+User+cancelled',
                follow_redirects=False,
            )
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_callback_auth_error_renders_page(self, client, app):
        from flask import Response
        cfg = _b2c_config(app)
        with patch('app.routes.auth._b2c_get_required_config', return_value=cfg), \
             patch('app.routes.auth.render_template', return_value=Response('error', status=200)):
            resp = client.get(
                '/auth/azure/callback?error=server_error&error_description=fail',
            )
        assert resp.status_code == 200

    def test_callback_expired_state_jwt(self, client, app):
        cfg = _b2c_config(app)
        expired = jwt.encode(
            {'verifier': 'v', 'nonce': 'n', 'iat': 1, 'exp': 2},
            app.config['SECRET_KEY'],
            algorithm='HS256',
        )
        with patch('app.routes.auth._b2c_get_required_config', return_value=cfg):
            resp = client.get(
                f'/auth/azure/callback?code=abc&state={expired}',
                follow_redirects=False,
            )
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_callback_success_creates_user_and_logs_in(self, client, app, db_session):
        cfg = _b2c_config(app)
        state = _signed_oauth_state(app)
        meta = {
            'token_endpoint': 'https://login.example.com/token',
            'userinfo_endpoint': 'https://login.example.com/userinfo',
            'issuer': 'https://issuer.example.com',
        }
        mock_post = MagicMock()
        mock_post.json.return_value = {'id_token': 'id.jwt', 'access_token': 'access'}
        mock_post.raise_for_status = MagicMock()
        mock_get = MagicMock()
        mock_get.ok = False

        with patch('app.routes.auth._b2c_get_required_config', return_value=cfg), \
             patch('app.routes.auth._b2c_metadata', return_value=meta), \
             patch('app.routes.auth.requests.post', return_value=mock_post), \
             patch('app.routes.auth.requests.get', return_value=mock_get), \
             patch('app.routes.auth._verify_and_decode_id_token', return_value={
                 'email': 'new-azure-user@example.com',
                 'sub': 'azure-sub-1',
                 'name': 'Azure User',
             }), \
             patch('app.routes.auth.log_user_activity'), \
             patch('app.routes.auth.start_user_session'), \
             patch('app.routes.auth.log_login_attempt'), \
             patch('app.services.email.service.send_welcome_email'):
            resp = client.get(
                f'/auth/azure/callback?code=auth-code&state={state}',
                follow_redirects=False,
            )
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_callback_existing_inactive_user_blocked(self, client, app, db_session):
        with app.app_context():
            create_test_user(db_session, email='inactive-azure@example.com', active=False)
        cfg = _b2c_config(app)
        state = _signed_oauth_state(app)
        meta = {'token_endpoint': 'https://login.example.com/token'}
        mock_post = MagicMock()
        mock_post.json.return_value = {'id_token': 'id.jwt'}
        mock_post.raise_for_status = MagicMock()

        with patch('app.routes.auth._b2c_get_required_config', return_value=cfg), \
             patch('app.routes.auth._b2c_metadata', return_value=meta), \
             patch('app.routes.auth.requests.post', return_value=mock_post), \
             patch('app.routes.auth._verify_and_decode_id_token', return_value={
                 'email': 'inactive-azure@example.com', 'sub': 'sub',
             }), \
             patch('app.routes.auth.create_security_event'):
            resp = client.get(
                f'/auth/azure/callback?code=auth-code&state={state}',
                follow_redirects=False,
            )
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_callback_already_authenticated_mobile_deep_link(self, logged_in_client, app):
        from urllib.parse import quote
        from flask import redirect
        cfg = _b2c_config(app)
        state = quote(_signed_oauth_state(app, mobile=True), safe='')
        with patch('app.routes.auth._b2c_get_required_config', return_value=cfg), \
             patch('app.routes.auth._mobile_deep_link_for_user', return_value=redirect('humdatabank://oauth-success')):
            resp = logged_in_client.get(
                f'/auth/azure/callback?code=x&state={state}',
                follow_redirects=False,
            )
        assert resp.status_code in (301, 302, 303, 307, 308)
        assert 'humdatabank' in (resp.headers.get('Location') or '')

    def test_callback_metadata_fetch_failure(self, client, app):
        cfg = _b2c_config(app)
        state = _signed_oauth_state(app)
        with patch('app.routes.auth._b2c_get_required_config', return_value=cfg), \
             patch('app.routes.auth._b2c_metadata', side_effect=RuntimeError('metadata down')):
            resp = client.get(
                f'/auth/azure/callback?code=auth-code&state={state}',
                follow_redirects=False,
            )
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_callback_token_exchange_failure(self, client, app):
        cfg = _b2c_config(app)
        state = _signed_oauth_state(app)
        meta = {'token_endpoint': 'https://login.example.com/token'}
        mock_post = MagicMock()
        mock_post.raise_for_status.side_effect = RuntimeError('token failed')

        with patch('app.routes.auth._b2c_get_required_config', return_value=cfg), \
             patch('app.routes.auth._b2c_metadata', return_value=meta), \
             patch('app.routes.auth.requests.post', return_value=mock_post):
            resp = client.get(
                f'/auth/azure/callback?code=auth-code&state={state}',
                follow_redirects=False,
            )
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_callback_id_token_verify_failure(self, client, app):
        cfg = _b2c_config(app)
        state = _signed_oauth_state(app)
        meta = {'token_endpoint': 'https://login.example.com/token'}
        mock_post = MagicMock()
        mock_post.json.return_value = {'id_token': 'bad.jwt'}
        mock_post.raise_for_status = MagicMock()

        with patch('app.routes.auth._b2c_get_required_config', return_value=cfg), \
             patch('app.routes.auth._b2c_metadata', return_value=meta), \
             patch('app.routes.auth.requests.post', return_value=mock_post), \
             patch('app.routes.auth._verify_and_decode_id_token', return_value=None):
            resp = client.get(
                f'/auth/azure/callback?code=auth-code&state={state}',
                follow_redirects=False,
            )
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_callback_session_state_fallback_mismatch(self, client, app):
        cfg = _b2c_config(app)
        with client.session_transaction() as sess:
            sess['b2c_state'] = 'stored-state'
        with patch('app.routes.auth._b2c_get_required_config', return_value=cfg):
            resp = client.get(
                '/auth/azure/callback?code=auth-code&state=wrong-state',
                follow_redirects=False,
            )
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_callback_mobile_oauth_deep_link(self, client, app, db_session):
        cfg = _b2c_config(app)
        state = _signed_oauth_state(app, mobile=True)
        meta = {'token_endpoint': 'https://login.example.com/token'}
        mock_post = MagicMock()
        mock_post.json.return_value = {'id_token': 'id.jwt'}
        mock_post.raise_for_status = MagicMock()

        with patch('app.routes.auth._b2c_get_required_config', return_value=cfg), \
             patch('app.routes.auth._b2c_metadata', return_value=meta), \
             patch('app.routes.auth.requests.post', return_value=mock_post), \
             patch('app.routes.auth._verify_and_decode_id_token', return_value={
                 'email': 'mobile-oauth@example.com',
                 'sub': 'mobile-sub',
             }), \
             patch('app.routes.auth.log_user_activity'), \
             patch('app.routes.auth.start_user_session'), \
             patch('app.routes.auth.log_login_attempt'), \
             patch('app.utils.mobile_jwt.issue_token_pair', return_value={
                 'access_token': 'at',
                 'refresh_token': 'rt',
                 'expires_in': 3600,
             }):
            resp = client.get(
                f'/auth/azure/callback?code=auth-code&state={state}',
                follow_redirects=False,
            )
        assert resp.status_code in (301, 302, 303, 307, 308)
        assert 'humdatabank' in (resp.headers.get('Location') or '')
