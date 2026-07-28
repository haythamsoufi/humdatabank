"""Tests for OAuth callback idempotency (duplicate session prevention)."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models import UserSessionLog
from app.services.platform.oauth_callback_guard import resolve_azure_b2c_login_session
from app.utils.datetime_helpers import utcnow
from tests.factories import create_test_user


def _session_log(**kwargs):
    defaults = {
        'session_start': utcnow(),
        'last_activity': utcnow(),
        'ip_address': '10.0.0.1',
        'browser': 'Chrome 120.0.0',
        'device_type': 'Desktop',
        'is_active': True,
    }
    defaults.update(kwargs)
    return UserSessionLog(**defaults)


@pytest.mark.unit
class TestOAuthCallbackGuard:
    def test_first_callback_creates_new_session(self, app, db_session):
        user = create_test_user(db_session, email='oauth-guard-new@example.com')
        with app.app_context():
            session_id, created = resolve_azure_b2c_login_session(
                user=user,
                ip_address='10.0.0.1',
                browser='Chrome 120.0.0',
                device_type='Desktop',
            )
        assert created is True
        assert session_id

    def test_second_callback_same_device_reuses_session(self, app, db_session):
        user = create_test_user(db_session, email='oauth-guard-dedup@example.com')
        now = utcnow()
        existing_sid = 'existing-active-session-id'
        db_session.add(
            _session_log(
                user_id=user.id,
                session_id=existing_sid,
                session_start=now - timedelta(seconds=5),
                ip_address='10.0.0.3',
            )
        )
        db_session.commit()

        with app.app_context():
            session_id, created = resolve_azure_b2c_login_session(
                user=user,
                ip_address='10.0.0.3',
                browser='Chrome 120.0.0',
                device_type='Desktop',
            )
        assert created is False
        assert session_id == existing_sid

    def test_different_ip_creates_new_session(self, app, db_session):
        user = create_test_user(db_session, email='oauth-guard-ip@example.com')
        db_session.add(
            _session_log(
                user_id=user.id,
                session_id='other-ip-session',
                ip_address='10.0.0.10',
            )
        )
        db_session.commit()

        with app.app_context():
            session_id, created = resolve_azure_b2c_login_session(
                user=user,
                ip_address='10.0.0.99',
                browser='Chrome 120.0.0',
                device_type='Desktop',
            )
        assert created is True
        assert session_id != 'other-ip-session'

    def test_old_session_outside_window_allows_new_session(self, app, db_session):
        user = create_test_user(db_session, email='oauth-guard-expired@example.com')
        now = utcnow()
        db_session.add(
            _session_log(
                user_id=user.id,
                session_id='old-session-outside-window',
                session_start=now - timedelta(minutes=5),
                last_activity=now - timedelta(minutes=5),
            )
        )
        db_session.commit()

        with app.app_context():
            with patch.dict(app.config, {'OAUTH_LOGIN_DEDUP_SECONDS': 90}):
                session_id, created = resolve_azure_b2c_login_session(
                    user=user,
                    ip_address='10.0.0.1',
                    browser='Chrome 120.0.0',
                    device_type='Desktop',
                )
        assert created is True
        assert session_id != 'old-session-outside-window'


@pytest.mark.integration
class TestAzureCallbackDeduplication:
    def test_second_callback_reuses_recent_session_log(self, client, app, db_session):
        from tests.unit.test_routes.test_auth_b2c import _b2c_config, _signed_oauth_state

        user = create_test_user(db_session, email='dedup-distinct-code@example.com')
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
                 'email': user.email,
                 'sub': 'sub-2',
             }), \
             patch('app.routes.auth.log_user_activity'), \
             patch('app.routes.auth.log_login_attempt'):
            client.get(
                f'/auth/azure/callback?code=first-code&state={state}',
                follow_redirects=False,
            )
            client.get(
                f'/auth/azure/callback?code=second-code&state={state}',
                follow_redirects=False,
            )

        sessions = UserSessionLog.query.filter_by(user_id=user.id).all()
        assert len(sessions) == 1
