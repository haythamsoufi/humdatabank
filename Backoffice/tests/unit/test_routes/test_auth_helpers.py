"""Unit tests for app.routes.auth helper functions."""
import base64
import hashlib
import json
import os
from datetime import timedelta
from unittest.mock import MagicMock, patch

import jwt
import pytest
from flask import session

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]

from app.models.core import UserLoginLog
from app.models.password_reset_token import PasswordResetToken
from app.routes.auth import (
    _is_account_locked_out,
    _flag_deactivated_account_login_attempt,
    _get_test_passwords,
    _generate_pkce_pair,
    _decode_jwt_payload_unverified,
    _generate_reset_token,
    _verify_reset_token,
    _send_password_reset_email,
    _mobile_deep_link_for_user,
)
from app.utils.datetime_helpers import utcnow
from tests.factories import create_test_user


@pytest.mark.unit
class TestAccountLockout:
    def test_not_locked_with_few_failures(self, app, db_session):
        with app.app_context():
            email = 'lockout1@example.com'
            assert _is_account_locked_out(email) is False

    def test_locked_after_threshold_failures(self, app, db_session):
        with app.app_context():
            email = 'locked@example.com'
            for _ in range(10):
                db_session.add(UserLoginLog(
                    email_attempted=email,
                    event_type='login_failed',
                    timestamp=utcnow(),
                    ip_address='127.0.0.1',
                ))
            db_session.commit()
            assert _is_account_locked_out(email) is True

    def test_success_after_failures_resets_lockout(self, app, db_session):
        with app.app_context():
            email = 'reset-lock@example.com'
            for _ in range(10):
                db_session.add(UserLoginLog(
                    email_attempted=email,
                    event_type='login_failed',
                    timestamp=utcnow(),
                    ip_address='127.0.0.1',
                ))
            db_session.add(UserLoginLog(
                email_attempted=email,
                event_type='login',
                timestamp=utcnow(),
                ip_address='127.0.0.1',
            ))
            db_session.commit()
            assert _is_account_locked_out(email) is False

    def test_db_error_fails_closed(self, app):
        from app.models.core import UserLoginLog
        with app.app_context():
            with patch.object(UserLoginLog, 'query') as mock_query:
                mock_query.filter.side_effect = RuntimeError('db')
                assert _is_account_locked_out('any@example.com') is True


@pytest.mark.unit
class TestFlagDeactivatedAccountLoginAttempt:
    def test_creates_security_event(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, email='deact@example.com', active=False)
            with patch('app.routes.auth.create_security_event') as mock_event:
                _flag_deactivated_account_login_attempt(
                    user=user,
                    auth_method='password',
                    email='deact@example.com',
                    password_verified=True,
                )
            mock_event.assert_called_once()
            assert mock_event.call_args.kwargs['event_type'] == 'deactivated_account_login_attempt'

    def test_event_failure_is_non_blocking(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, email='deact2@example.com', active=False)
            with patch('app.routes.auth.create_security_event', side_effect=RuntimeError('fail')):
                _flag_deactivated_account_login_attempt(
                    user=user, auth_method='password', email='deact2@example.com',
                )


@pytest.mark.unit
class TestGetTestPasswords:
    def test_empty_outside_development(self, app, monkeypatch):
        monkeypatch.setenv('FLASK_CONFIG', 'production')
        assert _get_test_passwords() == {}

    def test_returns_passwords_when_env_set(self, app, monkeypatch):
        monkeypatch.setenv('FLASK_CONFIG', 'development')
        monkeypatch.setenv('TEST_ADMIN_PASSWORD', 'admin-pw')
        monkeypatch.setenv('TEST_FOCAL_PASSWORD', 'focal-pw')
        monkeypatch.setenv('TEST_SYS_MANAGER_PASSWORD', 'sys-pw')
        result = _get_test_passwords()
        assert result['admin'] == 'admin-pw'
        assert result['focal'] == 'focal-pw'
        assert result['sys_manager'] == 'sys-pw'


@pytest.mark.unit
class TestPkceAndJwtHelpers:
    def test_generate_pkce_pair(self):
        verifier, challenge = _generate_pkce_pair()
        assert len(verifier) > 20
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode('ascii')).digest()
        ).rstrip(b'=').decode('ascii')
        assert challenge == expected

    def test_decode_jwt_payload_unverified(self, app):
        payload = {'sub': '123', 'email': 'u@test.com'}
        token = jwt.encode(payload, 'secret', algorithm='HS256')
        with app.app_context():
            decoded = _decode_jwt_payload_unverified(token)
        assert decoded['sub'] == '123'

    def test_decode_jwt_invalid_returns_none(self, app):
        with app.app_context():
            assert _decode_jwt_payload_unverified('not-a-jwt') is None

    def test_decode_jwt_payload_json_error_returns_none(self, app):
        bad_payload = base64.urlsafe_b64encode(b'not-json').decode('ascii').rstrip('=')
        token = f'header.{bad_payload}.sig'
        with app.app_context():
            assert _decode_jwt_payload_unverified(token) is None


@pytest.mark.unit
class TestPasswordResetHelpers:
    def test_generate_and_verify_token(self, app, db_session):
        from app import db
        with app.app_context():
            user = create_test_user(db_session, email='reset-helper@example.com')
            user_id = int(user.id)
            with app.test_request_context(environ_base={'REMOTE_ADDR': '127.0.0.1'}):
                token = _generate_reset_token('reset-helper@example.com')
                assert token is not None
                db.session.commit()
            email, rec = _verify_reset_token(token)
            assert email == 'reset-helper@example.com'
            assert rec is not None
            assert rec.user_id == user_id

    def test_verify_invalid_token(self, app):
        with app.app_context():
            email, rec = _verify_reset_token('totally-invalid')
            assert email is None
            assert rec is None

    def test_generate_token_unknown_email_still_returns_token(self, app):
        with app.app_context():
            with app.test_request_context():
                token = _generate_reset_token('nobody@example.com')
            assert token is not None

    def test_send_password_reset_email(self, app, db_session):
        with app.app_context():
            with patch('app.routes.auth.send_email', return_value=True) as mock_send:
                ok = _send_password_reset_email('user@example.com', 'fake-token')
            assert ok is True
            mock_send.assert_called_once()

    def test_send_password_reset_email_failure(self, app):
        with app.app_context():
            with patch('app.routes.auth.send_email', side_effect=RuntimeError('smtp down')):
                ok = _send_password_reset_email('user@example.com', 'fake-token')
            assert ok is False


@pytest.mark.unit
class TestMobileDeepLinkForUser:
    def test_returns_oauth_success_redirect(self, app, db_session, test_user):
        with app.app_context():
            with app.test_request_context():
                session['session_id'] = 'web-session-123'
                response = _mobile_deep_link_for_user(test_user)
        assert response.status_code in (301, 302, 303, 307, 308)
        location = response.headers.get('Location', '')
        assert location.startswith('humdatabank://oauth-success')


@pytest.mark.unit
class TestPasswordResetTokenEdgeCases:
    def test_verify_reset_token_used_token_rejected(self, app, db_session):
        from app import db
        with app.app_context():
            user = create_test_user(db_session, email='used-token@example.com')
            with app.test_request_context(environ_base={'REMOTE_ADDR': '127.0.0.1'}):
                token = _generate_reset_token('used-token@example.com')
                db.session.commit()
            token_hash = PasswordResetToken.hash_token(token)
            rec = PasswordResetToken.query.filter_by(token_hash=token_hash).first()
            rec.mark_as_used()
            db.session.commit()
            email, reset_rec = _verify_reset_token(token)
            assert email is None
            assert reset_rec is None

    def test_generate_reset_token_db_failure_returns_none(self, app, db_session):
        from app import db
        with app.app_context():
            create_test_user(db_session, email='db-fail@example.com')
            with app.test_request_context():
                with patch.object(db.session, 'flush', side_effect=RuntimeError('db down')):
                    token = _generate_reset_token('db-fail@example.com')
            assert token is None
