"""Direct unit tests for app.routes.auth view functions (mocked templates/forms)."""
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from flask import make_response
from flask_login import login_user

from tests.factories import create_test_country, create_test_user

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]


def _mock_html_response():
    return make_response('html', 200)


def _view_result(result):
    """Normalize direct view return (Response or (body, status) tuple)."""
    if isinstance(result, tuple):
        return result[0], result[1]
    return result, result.status_code


@pytest.mark.unit
class TestLoginRouteDirect:
    def test_login_already_authenticated_redirects_to_dashboard(self, app, test_user):
        from app.routes.auth import login

        with app.test_request_context('/login'):
            login_user(test_user)
            with patch('app.routes.auth.redirect', side_effect=lambda loc: loc) as mock_redirect, \
                 patch('app.routes.auth.url_for', return_value='/dashboard'):
                result = login()
        mock_redirect.assert_called()

    def test_login_already_authenticated_respects_next(self, app, test_user):
        from app.routes.auth import login

        with app.test_request_context('/login?next=/safe/path'):
            login_user(test_user)
            with patch('app.routes.auth.is_safe_redirect_url', return_value=True), \
                 patch('app.routes.auth.redirect', side_effect=lambda loc: loc) as mock_redirect:
                login()
        mock_redirect.assert_called_with('/safe/path')

    def test_login_invalid_credentials_renders_template(self, app, db_session):
        from app.routes.auth import login

        with app.app_context():
            create_test_user(db_session, email='direct-login@example.com', password='TestPass123!')
        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = 'direct-login@example.com'
        mock_form.password.data = 'WrongPass123!'

        with app.test_request_context('/login', method='POST'):
            with patch('app.routes.auth.LoginForm', return_value=mock_form), \
                 patch('app.routes.auth.RegisterForm'), \
                 patch('app.routes.auth.ForgotPasswordForm'), \
                 patch('app.routes.auth.render_template', return_value=_mock_html_response()) as mock_render, \
                 patch('app.routes.auth.log_login_attempt'):
                resp, status = _view_result(login())
        assert status == 200
        mock_render.assert_called()

    def test_login_get_renders_template(self, app):
        from app.routes.auth import login

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = False
        with app.test_request_context('/login', method='GET'):
            with patch('app.routes.auth.LoginForm', return_value=mock_form), \
                 patch('app.routes.auth.RegisterForm'), \
                 patch('app.routes.auth.ForgotPasswordForm'), \
                 patch('app.routes.auth.render_template', return_value=_mock_html_response()) as mock_render:
                resp, status = _view_result(login())
        assert status == 200
        mock_render.assert_called()


@pytest.mark.unit
class TestRegisterRouteDirect:
    def test_check_register_email_missing(self, app):
        from app.routes.auth import check_register_email

        with app.test_request_context('/register/check-email'):
            with patch('app.routes.auth.is_azure_b2c_configured', return_value=False):
                _, status = _view_result(check_register_email())
        assert status == 400

    def test_check_register_email_b2c_disabled(self, app):
        from app.routes.auth import check_register_email

        with app.test_request_context('/register/check-email?email=test@example.com'):
            with patch('app.routes.auth.is_azure_b2c_configured', return_value=True):
                _, status = _view_result(check_register_email())
        assert status == 403

    def test_register_validation_errors_render(self, app):
        from app.routes.auth import register

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = False
        with app.test_request_context('/register', method='POST'):
            with patch('app.routes.auth.current_user') as mock_user, \
                 patch('app.routes.auth.is_azure_b2c_configured', return_value=False), \
                 patch('app.routes.auth.RegisterForm', return_value=mock_form), \
                 patch('app.routes.auth.LoginForm'), \
                 patch('app.routes.auth.ForgotPasswordForm'), \
                 patch('app.routes.auth.render_template', return_value=_mock_html_response()) as mock_render:
                mock_user.is_authenticated = False
                _, status = _view_result(register())
        assert status == 200
        mock_render.assert_called()


@pytest.mark.unit
class TestForgotPasswordRouteDirect:
    def test_forgot_password_get_redirects(self, app):
        from app.routes.auth import forgot_password

        with app.test_request_context('/forgot-password', method='GET'):
            with patch('app.routes.auth.redirect', side_effect=lambda loc: loc) as mock_redirect, \
                 patch('app.routes.auth.url_for', return_value='/login'):
                forgot_password()
        mock_redirect.assert_called()

    def test_forgot_password_success_redirects(self, app, db_session):
        from app.routes.auth import forgot_password

        with app.app_context():
            create_test_user(db_session, email='forgot-direct@example.com')
        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = 'forgot-direct@example.com'

        with app.test_request_context('/forgot-password', method='POST'):
            with patch('app.routes.auth.ForgotPasswordForm', return_value=mock_form), \
                 patch('app.routes.auth._generate_reset_token', return_value='tok'), \
                 patch('app.routes.auth._send_password_reset_email', return_value=True), \
                 patch('app.routes.auth.redirect', side_effect=lambda loc: loc) as mock_redirect, \
                 patch('app.routes.auth.url_for', return_value='/login'):
                forgot_password()
        mock_redirect.assert_called()


@pytest.mark.unit
class TestResetPasswordRouteDirect:
    def test_reset_password_invalid_token_redirects(self, app):
        from app.routes.auth import reset_password

        with app.test_request_context('/reset-password/bad-token'):
            with patch('app.routes.auth._verify_reset_token', return_value=(None, None)), \
                 patch('app.routes.auth.redirect', side_effect=lambda loc: loc) as mock_redirect, \
                 patch('app.routes.auth.url_for', return_value='/forgot-password'):
                reset_password('bad-token')
        mock_redirect.assert_called()

    def test_reset_password_get_renders_form(self, app, db_session):
        from app.routes.auth import reset_password

        with app.app_context():
            user = create_test_user(db_session, email='reset-get@example.com')
            token_rec = MagicMock()
            token_rec.id = 1
        with app.test_request_context('/reset-password/good-token'):
            with patch('app.routes.auth._verify_reset_token', return_value=('reset-get@example.com', token_rec)), \
                 patch('app.routes.auth.is_azure_b2c_configured', return_value=False), \
                 patch('app.routes.auth.ResetPasswordForm') as MockForm, \
                 patch('app.routes.auth.render_template', return_value=_mock_html_response()) as mock_render:
                mock_form = MockForm.return_value
                mock_form.validate_on_submit.return_value = False
                _, status = _view_result(reset_password('good-token'))
        assert status == 200
        mock_render.assert_called()


@pytest.mark.unit
class TestAccountSettingsRouteDirect:
    def test_account_settings_get_prepopulates_form(self, app, admin_user, db_session):
        from app.routes.auth import account_settings

        with app.app_context():
            user_id = int(admin_user.id)

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = False
        with app.test_request_context('/account-settings', method='GET'):
            from app.models import User
            login_user(User.query.get(user_id))
            with patch('app.routes.auth.AccountSettingsForm', return_value=mock_form), \
                 patch('app.forms.auth_forms.RequestCountryAccessForm'), \
                 patch('app.routes.auth.render_template', return_value=_mock_html_response()) as mock_render, \
                 patch('app.routes.auth.user_has_ai_beta_access', return_value=False), \
                 patch('app.services.notification_service.NotificationService.get_notification_preferences', return_value={}), \
                 patch('app.routes.notifications.get_notification_types_for_user', return_value={'for_user': []}), \
                 patch('app.routes.notifications.get_notification_type_labels', return_value={}):
                _, status = _view_result(account_settings())
        assert status == 200
        assert mock_form.name.data == admin_user.name
        mock_render.assert_called()


@pytest.mark.unit
class TestLoginRouteDirectExtended:
    def test_login_success_redirects(self, app, db_session):
        from app.routes.auth import login

        with app.app_context():
            create_test_user(db_session, email='login-success@example.com', password='TestPass123!')
        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = 'login-success@example.com'
        mock_form.password.data = 'TestPass123!'

        with app.test_request_context('/login', method='POST'):
            with patch('app.routes.auth.LoginForm', return_value=mock_form), \
                 patch('app.routes.auth.RegisterForm'), \
                 patch('app.routes.auth.ForgotPasswordForm'), \
                 patch('app.routes.auth.log_login_attempt'), \
                 patch('app.routes.auth.start_user_session'), \
                 patch('app.routes.auth.log_user_activity'), \
                 patch('app.routes.auth.safe_redirect', return_value='redirected') as mock_redirect:
                result = login()
        mock_redirect.assert_called_once()
        assert result == 'redirected'

    def test_login_deactivated_user_wrong_password(self, app, db_session):
        from app.routes.auth import login

        with app.app_context():
            create_test_user(
                db_session,
                email='deact-wrong@example.com',
                password='TestPass123!',
                active=False,
            )
        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = 'deact-wrong@example.com'
        mock_form.password.data = 'WrongPass123!'

        with app.test_request_context('/login', method='POST'):
            with patch('app.routes.auth.LoginForm', return_value=mock_form), \
                 patch('app.routes.auth.RegisterForm'), \
                 patch('app.routes.auth.ForgotPasswordForm'), \
                 patch('app.routes.auth.render_template', return_value=_mock_html_response()), \
                 patch('app.routes.auth.log_login_attempt'):
                _, status = _view_result(login())
        assert status == 200

    def test_login_deactivated_user_correct_password(self, app, db_session):
        from app.routes.auth import login

        with app.app_context():
            create_test_user(
                db_session,
                email='deact-ok@example.com',
                password='TestPass123!',
                active=False,
            )
        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = 'deact-ok@example.com'
        mock_form.password.data = 'TestPass123!'

        with app.test_request_context('/login', method='POST'):
            with patch('app.routes.auth.LoginForm', return_value=mock_form), \
                 patch('app.routes.auth.RegisterForm'), \
                 patch('app.routes.auth.ForgotPasswordForm'), \
                 patch('app.routes.auth.render_template', return_value=_mock_html_response()), \
                 patch('app.routes.auth.log_login_attempt'), \
                 patch('app.routes.auth.create_security_event'):
                _, status = _view_result(login())
        assert status == 200

    def test_login_account_locked(self, app, db_session):
        from app.models.core import UserLoginLog
        from app.routes.auth import login
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            create_test_user(db_session, email='locked-direct@example.com', password='TestPass123!')
            for _ in range(10):
                db_session.add(UserLoginLog(
                    email_attempted='locked-direct@example.com',
                    event_type='login_failed',
                    timestamp=utcnow(),
                    ip_address='127.0.0.1',
                ))
            db_session.commit()
        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = 'locked-direct@example.com'
        mock_form.password.data = 'TestPass123!'

        with app.test_request_context('/login', method='POST'):
            with patch('app.routes.auth.LoginForm', return_value=mock_form), \
                 patch('app.routes.auth.RegisterForm'), \
                 patch('app.routes.auth.ForgotPasswordForm'), \
                 patch('app.routes.auth.render_template', return_value=_mock_html_response()), \
                 patch('app.routes.auth.log_login_attempt'):
                _, status = _view_result(login())
        assert status == 200


@pytest.mark.unit
class TestRegisterRouteDirectExtended:
    def test_register_authenticated_redirects(self, app, test_user):
        from app.routes.auth import register

        with app.test_request_context('/register', method='POST'):
            login_user(test_user)
            with patch('app.routes.auth.redirect', side_effect=lambda loc: loc) as mock_redirect, \
                 patch('app.routes.auth.url_for', return_value='/dashboard'):
                register()
        mock_redirect.assert_called()

    def test_register_duplicate_email(self, app, db_session):
        from app.routes.auth import register

        with app.app_context():
            country = create_test_country(db_session)
            create_test_user(db_session, email='dup-direct@example.com')
            country_id = country.id
        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = 'dup-direct@example.com'

        with app.test_request_context('/register', method='POST'):
            with patch('app.routes.auth.current_user') as mock_user, \
                 patch('app.routes.auth.is_azure_b2c_configured', return_value=False), \
                 patch('app.routes.auth.RegisterForm', return_value=mock_form), \
                 patch('app.routes.auth.LoginForm'), \
                 patch('app.routes.auth.ForgotPasswordForm'), \
                 patch('app.routes.auth.render_template', return_value=_mock_html_response()):
                mock_user.is_authenticated = False
                _, status = _view_result(register())
        assert status == 200

    def test_register_success_redirects(self, app, db_session):
        from app.routes.auth import register

        with app.app_context():
            country = create_test_country(db_session)
            country_id = country.id
        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = f'new-{uuid4().hex[:8]}@example.com'
        mock_form.name.data = 'New User'
        mock_form.title.data = 'Analyst'
        mock_form.requested_country_id.data = country_id
        mock_form.request_message.data = 'Please grant access'
        mock_form.password.data = 'SecurePass123!'

        with app.test_request_context('/register', method='POST'):
            with patch('app.routes.auth.current_user') as mock_user, \
                 patch('app.routes.auth.is_azure_b2c_configured', return_value=False), \
                 patch('app.routes.auth.RegisterForm', return_value=mock_form), \
                 patch('app.routes.auth.validate_password_strength', return_value=(True, [])), \
                 patch('app.routes.auth.log_user_activity_for_user'), \
                 patch('app.routes.auth.redirect', side_effect=lambda loc: loc) as mock_redirect, \
                 patch('app.routes.auth.url_for', return_value='/login'):
                mock_user.is_authenticated = False
                register()
        mock_redirect.assert_called()

    def test_check_register_email_exists(self, app, db_session):
        from app.routes.auth import check_register_email

        with app.app_context():
            create_test_user(db_session, email='exists-direct@example.com')
        with app.test_request_context('/register/check-email?email=exists-direct@example.com'):
            with patch('app.routes.auth.is_azure_b2c_configured', return_value=False):
                body, status = _view_result(check_register_email())
        assert status == 200
        assert body.get_json()['exists'] is True


@pytest.mark.unit
class TestResetPasswordRouteDirectExtended:
    def test_reset_password_submit_success(self, app, db_session):
        from app.routes.auth import reset_password

        with app.app_context():
            user = create_test_user(db_session, email='reset-post@example.com', password='OldPass123!')
            token_rec = MagicMock()
            token_rec.id = 1
        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.password.data = 'NewPass123!'

        with app.test_request_context('/reset-password/tok', method='POST'):
            with patch('app.routes.auth._verify_reset_token', return_value=('reset-post@example.com', token_rec)), \
                 patch('app.routes.auth.is_azure_b2c_configured', return_value=False), \
                 patch('app.routes.auth.ResetPasswordForm', return_value=mock_form), \
                 patch('app.routes.auth.validate_password_strength', return_value=(True, [])), \
                 patch('app.routes.auth.log_user_activity_for_user'), \
                 patch('app.routes.auth.redirect', side_effect=lambda loc: loc) as mock_redirect, \
                 patch('app.routes.auth.url_for', return_value='/login'):
                reset_password('tok')
        mock_redirect.assert_called()

    def test_reset_password_weak_password(self, app, db_session):
        from app.routes.auth import reset_password

        with app.app_context():
            create_test_user(db_session, email='reset-weak@example.com')
            token_rec = MagicMock()
        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.password.data = '12345678'

        with app.test_request_context('/reset-password/tok', method='POST'):
            with patch('app.routes.auth._verify_reset_token', return_value=('reset-weak@example.com', token_rec)), \
                 patch('app.routes.auth.is_azure_b2c_configured', return_value=False), \
                 patch('app.routes.auth.ResetPasswordForm', return_value=mock_form), \
                 patch('app.routes.auth.validate_password_strength', return_value=(False, ['Too weak'])), \
                 patch('app.routes.auth.render_template', return_value=_mock_html_response()):
                _, status = _view_result(reset_password('tok'))
        assert status == 200


@pytest.mark.unit
class TestLogoutAndDevicesDirect:
    def test_logout_clears_session(self, app, admin_user, db_session):
        from app.routes.auth import logout

        with app.app_context():
            user_id = int(admin_user.id)
            from app.models import User
            user = User.query.get(user_id)

        with app.test_request_context('/logout'):
            login_user(user)
            with patch('app.routes.auth.log_user_activity'), \
                 patch('app.routes.auth.log_logout'), \
                 patch('app.routes.auth._b2c_get_required_config', return_value=None), \
                 patch('app.routes.auth.clear_mobile_app_embed_cookie', side_effect=lambda r: r):
                resp = logout()
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_kickout_own_device_success(self, app, admin_user, db_session):
        from app.models.system import UserDevice
        from app.routes.auth import kickout_own_device

        with app.app_context():
            from app.models import User
            user_id = int(admin_user.id)
            device = UserDevice(
                user_id=user_id,
                device_token=f'token-{uuid4().hex}',
                platform='android',
                device_name='Phone',
            )
            db_session.add(device)
            db_session.commit()
            device_id = int(device.id)

        with app.test_request_context(f'/account-settings/devices/{device_id}/kickout', method='POST'):
            login_user(User.query.get(user_id))
            resp, status = kickout_own_device(device_id)
            db_session.commit()
        assert status == 200
        assert resp.get_json()['success'] is True
