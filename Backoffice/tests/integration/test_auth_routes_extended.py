"""Extended integration tests for app.routes.auth web routes."""
import os
from unittest.mock import patch
from uuid import uuid4

import pytest
from flask import make_response

pytestmark = [pytest.mark.integration, pytest.mark.auth_security]

from app.models.system import UserDevice
from tests.factories import create_test_user, create_test_country


def _mock_html_response():
    return make_response('html', 200)


def _view_result(result):
    """Normalize direct view return (Response or (body, status) tuple)."""
    if isinstance(result, tuple):
        return result[0], result[1]
    return result, result.status_code


@pytest.mark.integration
class TestLoginRouteExtended:
    def test_login_success_redirects(self, client, db_session, app):
        with app.app_context():
            create_test_user(db_session, email='login-ok@example.com', password='TestPass123!')
        with patch('app.routes.auth.log_user_activity'), \
             patch('app.routes.auth.start_user_session'), \
             patch('app.routes.auth.log_login_attempt'):
            resp = client.post('/login', data={
                'email': 'login-ok@example.com',
                'password': 'TestPass123!',
            }, follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_login_account_locked(self, client, db_session, app):
        from app.models.core import UserLoginLog
        from app.utils.datetime_helpers import utcnow
        with app.app_context():
            create_test_user(db_session, email='locked-login@example.com', password='TestPass123!')
            for _ in range(10):
                db_session.add(UserLoginLog(
                    email_attempted='locked-login@example.com',
                    event_type='login_failed',
                    timestamp=utcnow(),
                    ip_address='127.0.0.1',
                ))
            db_session.commit()
        with patch('app.routes.auth.render_template', return_value=('locked', 200)):
            resp = client.post('/login', data={
                'email': 'locked-login@example.com',
                'password': 'TestPass123!',
            })
        assert resp.status_code == 200

    def test_login_blocks_test_email_in_production(self, client, db_session, app, monkeypatch):
        monkeypatch.setenv('FLASK_CONFIG', 'production')
        with app.app_context():
            create_test_user(db_session, email='test_blocked@example.com', password='TestPass123!')
        with patch('app.routes.auth.render_template', return_value=('blocked', 200)):
            resp = client.post('/login', data={
                'email': 'test_blocked@example.com',
                'password': 'TestPass123!',
            })
        assert resp.status_code == 200


@pytest.mark.integration
class TestRegisterRoute:
    def test_register_post_success(self, client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            country_id = country.id
        with patch('app.routes.auth.is_azure_b2c_configured', return_value=False), \
             patch('app.routes.auth.validate_password_strength', return_value=(True, [])), \
             patch('app.routes.auth.log_user_activity_for_user'):
            resp = client.post('/register', data={
                'email': f'register-{uuid4().hex[:8]}@example.com',
                'name': 'New User',
                'requested_country_id': country_id,
                'password': 'SecurePass123!',
                'confirm_password': 'SecurePass123!',
            }, follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_register_duplicate_email(self, client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            country_id = int(country.id)
            create_test_user(db_session, email='dup-reg@example.com')
        with patch('app.routes.auth.is_azure_b2c_configured', return_value=False), \
             patch('app.routes.auth.render_template', return_value='dup'):
            resp = client.post('/register', data={
                'email': 'dup-reg@example.com',
                'requested_country_id': country_id,
                'password': 'SecurePass123!',
                'confirm_password': 'SecurePass123!',
            })
        assert resp.status_code == 200


@pytest.mark.integration
class TestAccountSettingsAndDevices:
    def test_account_settings_get(self, logged_in_client, app, test_user):
        with patch('app.routes.auth.render_template', return_value=('settings', 200)) as mock_render, \
             patch('app.routes.auth.user_has_ai_beta_access', return_value=False), \
             patch('app.services.notification.service.NotificationService.get_notification_preferences', return_value={}), \
             patch('app.routes.notifications.get_notification_types_for_user', return_value={'for_user': []}), \
             patch('app.routes.notifications.get_notification_type_labels', return_value={}):
            resp = logged_in_client.get('/account-settings')
        assert resp.status_code == 200
        mock_render.assert_called_once()

    def test_account_settings_post_updates_profile(self, app, admin_user, db_session):
        from flask_login import login_user
        from app.extensions import db
        from app.models import User
        from app.routes.auth import account_settings

        with app.app_context():
            user_id = int(admin_user.id)

        with app.test_request_context('/account-settings', method='POST'):
            login_user(User.query.get(user_id))
            with patch('app.routes.auth.AccountSettingsForm') as MockForm, \
                 patch('app.routes.auth.log_user_activity'):
                form = MockForm.return_value
                form.validate_on_submit.return_value = True
                form.name.data = 'Updated Name'
                form.title.data = 'Analyst'
                form.chatbot_enabled.data = True
                form.profile_color.data = '#3B82F6'
                resp = account_settings()
            db.session.commit()
            assert resp.status_code in (301, 302, 303, 307, 308)

        with app.app_context():
            updated = User.query.get(user_id)
            assert updated.name == 'Updated Name'
            assert updated.title == 'Analyst'

    def test_debug_profile_picture_debug_only(self, logged_in_client, app):
        app.config['DEBUG'] = True
        resp = logged_in_client.get('/debug/profile-picture')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['user_info']['email']

    def test_debug_profile_picture_hidden_when_not_debug(self, logged_in_client, app):
        app.config['DEBUG'] = False
        resp = logged_in_client.get('/debug/profile-picture')
        assert resp.status_code == 404

    def test_kickout_own_device(self, app, admin_user, db_session):
        from flask_login import login_user
        from app.extensions import db
        from app.models import User
        from app.routes.auth import kickout_own_device

        with app.app_context():
            user_id = int(admin_user.id)
            device = UserDevice(
                user_id=user_id,
                device_token=f'token-kick-{uuid4().hex}',
                platform='android',
                device_name='Test Phone',
            )
            db_session.add(device)
            db_session.commit()
            device_id = int(device.id)

        with app.test_request_context(
            f'/account-settings/devices/{device_id}/kickout',
            method='POST',
        ):
            login_user(User.query.get(user_id))
            resp, status = kickout_own_device(device_id)
            db.session.commit()
        assert status == 200
        assert resp.get_json()['success'] is True

        with app.app_context():
            kicked = UserDevice.query.get(device_id)
            assert kicked.logged_out_at is not None

    def test_remove_own_device(self, app, admin_user, db_session):
        from flask_login import login_user
        from app.extensions import db
        from app.models import User
        from app.routes.auth import remove_own_device

        with app.app_context():
            user_id = int(admin_user.id)
            device = UserDevice(
                user_id=user_id,
                device_token=f'token-remove-{uuid4().hex}',
                platform='ios',
                device_name='Old Phone',
            )
            db_session.add(device)
            db_session.commit()
            device_id = int(device.id)

        with app.test_request_context(
            f'/account-settings/devices/{device_id}/remove',
            method='DELETE',
        ):
            login_user(User.query.get(user_id))
            resp, status = remove_own_device(device_id)
            db.session.commit()
        assert status == 200
        assert resp.get_json()['success'] is True

        with app.app_context():
            assert UserDevice.query.get(device_id) is None

    def test_kickout_already_logged_out_device(self, app, admin_user, db_session):
        from flask_login import login_user
        from app.extensions import db
        from app.models import User
        from app.routes.auth import kickout_own_device
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user_id = int(admin_user.id)
            device = UserDevice(
                user_id=user_id,
                device_token=f'token-kicked-{uuid4().hex}',
                platform='android',
                device_name='Logged Out Phone',
                logged_out_at=utcnow(),
            )
            db_session.add(device)
            db_session.commit()
            device_id = int(device.id)

        with app.test_request_context(
            f'/account-settings/devices/{device_id}/kickout',
            method='POST',
        ):
            login_user(User.query.get(user_id))
            resp, status = kickout_own_device(device_id)
            db.session.commit()
        assert status == 400
        assert resp.get_json()['success'] is False


@pytest.mark.integration
class TestLogoutExtended:
    def test_logout_with_session_duration(self, logged_in_client, app):
        with logged_in_client.session_transaction() as sess:
            sess['session_start'] = '2020-01-01T00:00:00+00:00'
        with patch('app.routes.auth.log_user_activity'), \
             patch('app.routes.auth.log_logout'), \
             patch('app.routes.auth._b2c_get_required_config', return_value=None):
            resp = logged_in_client.get('/logout', follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_logout_b2c_end_session_redirect(self, logged_in_client, app):
        cfg = {
            'tenant': 't.onmicrosoft.com',
            'policy': 'B2C_1_signin',
            'client_id': 'cid',
            'client_secret': 'sec',
            'redirect_uri': 'https://app.example.com/auth/azure/callback',
        }
        meta = {'end_session_endpoint': 'https://login.example.com/logout'}
        with logged_in_client.session_transaction() as sess:
            sess['b2c_id_token'] = 'id-token-hint'
        app.config['AZURE_B2C_POST_LOGOUT_REDIRECT_URI'] = 'https://app.example.com/login'
        with patch('app.routes.auth.log_user_activity'), \
             patch('app.routes.auth.log_logout'), \
             patch('app.routes.auth._b2c_get_required_config', return_value=cfg), \
             patch('app.routes.auth._b2c_metadata', return_value=meta):
            resp = logged_in_client.get('/logout', follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)
        assert 'login.example.com/logout' in (resp.headers.get('Location') or '')


@pytest.mark.integration
class TestLoginRouteCoverage:
    def test_login_get_renders_page(self, client, app):
        with patch('app.routes.auth.render_template', return_value=('login', 200)) as mock_render:
            resp = client.get('/login')
        assert resp.status_code == 200
        mock_render.assert_called_once()

    def test_login_wrong_password(self, client, db_session, app):
        with app.app_context():
            create_test_user(db_session, email='wrong-pw@example.com', password='TestPass123!')
        with patch('app.routes.auth.render_template', return_value=('bad', 200)), \
             patch('app.routes.auth.log_login_attempt') as mock_log:
            resp = client.post('/login', data={
                'email': 'wrong-pw@example.com',
                'password': 'WrongPassword!',
            })
        assert resp.status_code == 200
        mock_log.assert_called()

    def test_login_user_fetch_error(self, client, app):
        with patch('app.routes.auth.render_template', return_value=_mock_html_response()), \
             patch(
                 'app.services.platform.user_service.UserService.get_by_email',
                 side_effect=[None, RuntimeError('db down')],
             ):
            resp = client.post('/login', data={
                'email': 'any@example.com',
                'password': 'TestPass123!',
            })
        assert resp.status_code == 200

    def test_register_weak_password(self, client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            country_id = country.id
        with patch('app.routes.auth.is_azure_b2c_configured', return_value=False), \
             patch('app.routes.auth.validate_password_strength', return_value=(False, ['Too weak'])), \
             patch('app.routes.auth.render_template', return_value=('weak', 200)):
            resp = client.post('/register', data={
                'email': 'weak-reg@example.com',
                'requested_country_id': country_id,
                'password': 'weakpass',
                'confirm_password': 'weakpass',
            })
        assert resp.status_code == 200

    def test_register_db_failure(self, client, db_session, app):
        from app import db
        with app.app_context():
            country = create_test_country(db_session)
            country_id = country.id
        with patch('app.routes.auth.is_azure_b2c_configured', return_value=False), \
             patch('app.routes.auth.validate_password_strength', return_value=(True, [])), \
             patch.object(db.session, 'flush', side_effect=RuntimeError('db down')), \
             patch('app.routes.auth.render_template', return_value=('fail', 200)):
            resp = client.post('/register', data={
                'email': f'fail-reg-{uuid4().hex[:8]}@example.com',
                'requested_country_id': country_id,
                'password': 'SecurePass123!',
                'confirm_password': 'SecurePass123!',
            })
        assert resp.status_code == 200

    def test_register_blocked_when_b2c_configured(self, client, app):
        with patch('app.routes.auth.is_azure_b2c_configured', return_value=True):
            resp = client.post('/register', data={
                'email': 'b2c-block@example.com',
                'requested_country_id': 1,
                'password': 'SecurePass123!',
                'confirm_password': 'SecurePass123!',
            }, follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_forgot_password_token_generation_failure(self, client, db_session, app):
        with app.app_context():
            create_test_user(db_session, email='token-fail@example.com')
        with patch('app.routes.auth._generate_reset_token', return_value=None), \
             patch('app.routes.auth.render_template', return_value=('fail', 200)):
            resp = client.post('/forgot-password', data={'email': 'token-fail@example.com'}, follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_forgot_password_email_send_failure(self, client, db_session, app):
        with app.app_context():
            create_test_user(db_session, email='email-fail@example.com')
        with patch('app.routes.auth._generate_reset_token', return_value='fake-token'), \
             patch('app.routes.auth._send_password_reset_email', return_value=False), \
             patch('app.routes.auth.render_template', return_value=('fail', 200)):
            resp = client.post('/forgot-password', data={'email': 'email-fail@example.com'}, follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_reset_password_redirects_when_authenticated(self, logged_in_client):
        resp = logged_in_client.get('/reset-password/some-token', follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_account_settings_post_error(self, app, admin_user, db_session):
        from flask_login import login_user
        from app import db
        from app.models import User
        from app.routes.auth import account_settings

        with app.app_context():
            user_id = int(admin_user.id)

        with app.test_request_context('/account-settings', method='POST'):
            login_user(User.query.get(user_id))
            with patch('app.routes.auth.AccountSettingsForm') as MockForm, \
                 patch('app.routes.auth.render_template', return_value=_mock_html_response()), \
                 patch.object(db.session, 'flush', side_effect=RuntimeError('db down')):
                form = MockForm.return_value
                form.validate_on_submit.return_value = True
                form.name.data = 'Broken'
                form.title.data = None
                form.chatbot_enabled.data = False
                form.profile_color.data = '#3B82F6'
                _, status = _view_result(account_settings())
        assert status == 200

    def test_kickout_device_not_found(self, app, admin_user, db_session):
        from flask_login import login_user
        from app.models import User
        from app.routes.auth import kickout_own_device

        with app.app_context():
            user_id = int(admin_user.id)

        with app.test_request_context('/account-settings/devices/999999/kickout', method='POST'):
            login_user(User.query.get(user_id))
            resp, status = kickout_own_device(999999)
        assert status == 500

    def test_remove_device_error_returns_500(self, app, admin_user, db_session):
        from flask_login import login_user
        from app import db
        from app.models import User
        from app.models.system import UserDevice
        from app.routes.auth import remove_own_device

        with app.app_context():
            user_id = int(admin_user.id)
            device = UserDevice(
                user_id=user_id,
                device_token=f'token-err-{uuid4().hex}',
                platform='android',
                device_name='Err Phone',
            )
            db_session.add(device)
            db_session.commit()
            device_id = int(device.id)

        with app.test_request_context(
            f'/account-settings/devices/{device_id}/remove',
            method='DELETE',
        ):
            login_user(User.query.get(user_id))
            with patch.object(db.session, 'flush', side_effect=RuntimeError('db down')):
                resp, status = remove_own_device(device_id)
        assert status == 500
