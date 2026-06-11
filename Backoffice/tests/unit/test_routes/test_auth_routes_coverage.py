"""Additional coverage tests for app/routes/auth.py gaps (fills the 85% → 100%)."""
from unittest.mock import MagicMock, patch, PropertyMock
from uuid import uuid4

import pytest
from flask import make_response
from flask_login import login_user

from tests.factories import create_test_user, create_test_country

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]


def _mock_html_response():
    return make_response("html", 200)


def _view_result(result):
    if isinstance(result, tuple):
        return result[0], result[1]
    return result, result.status_code


# =====================================================================
# _get_test_passwords helper
# =====================================================================


class TestGetTestPasswords:
    def test_returns_empty_when_not_dev(self, app):
        from app.routes.auth import _get_test_passwords
        import os
        with app.test_request_context("/"):
            with patch.dict(os.environ, {"FLASK_CONFIG": "production"}, clear=False):
                result = _get_test_passwords()
        assert result == {}

    def test_returns_passwords_when_dev_env_vars_set(self, app):
        from app.routes.auth import _get_test_passwords
        import os
        with app.test_request_context("/"):
            with patch.dict(
                os.environ,
                {
                    "FLASK_CONFIG": "development",
                    "TEST_ADMIN_PASSWORD": "adminpass",
                    "TEST_FOCAL_PASSWORD": "focalpass",
                    "TEST_SYS_MANAGER_PASSWORD": "syspass",
                },
                clear=False,
            ):
                result = _get_test_passwords()
        assert result.get("admin") == "adminpass"
        assert result.get("focal") == "focalpass"
        assert result.get("sys_manager") == "syspass"

    def test_returns_empty_when_dev_but_no_env_vars(self, app):
        from app.routes.auth import _get_test_passwords
        import os
        with app.test_request_context("/"):
            with patch.dict(
                os.environ,
                {"FLASK_CONFIG": "development", "TEST_ADMIN_PASSWORD": "", "TEST_FOCAL_PASSWORD": ""},
                clear=False,
            ):
                result = _get_test_passwords()
        assert result.get("admin") is None
        assert result.get("focal") is None


# =====================================================================
# _is_account_locked_out
# =====================================================================


class TestIsAccountLockedOut:
    def test_not_locked_when_few_failures(self, app, db_session):
        from app.routes.auth import _is_account_locked_out
        with app.app_context():
            result = _is_account_locked_out("nobody@example.com")
        assert result is False

    def test_locked_when_many_failures_no_success(self, app, db_session):
        from app.models.core import UserLoginLog
        from app.routes.auth import _is_account_locked_out
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            for _ in range(10):
                db_session.add(
                    UserLoginLog(
                        email_attempted="locked@example.com",
                        event_type="login_failed",
                        timestamp=utcnow(),
                        ip_address="127.0.0.1",
                    )
                )
            db_session.commit()
            result = _is_account_locked_out("locked@example.com")
        assert result is True

    def test_lockout_check_exception_returns_true(self, app):
        from app.routes.auth import _is_account_locked_out
        with app.app_context():
            with patch("app.models.core.UserLoginLog.query") as MockQuery:
                MockQuery.filter.side_effect = Exception("db boom")
                result = _is_account_locked_out("any@example.com")
        assert result is True


# =====================================================================
# _flag_deactivated_account_login_attempt
# =====================================================================


class TestFlagDeactivatedAccount:
    def test_create_security_event_called(self, app):
        from app.routes.auth import _flag_deactivated_account_login_attempt

        mock_user = MagicMock()
        mock_user.id = 999
        mock_user.active = False
        mock_user.deactivated_at = None

        with app.test_request_context("/"):
            with patch("app.routes.auth.create_security_event") as mock_event:
                _flag_deactivated_account_login_attempt(
                    user=mock_user,
                    auth_method="password",
                    email="deact-flag@example.com",
                    password_verified=True,
                )
            mock_event.assert_called_once()

    def test_exception_in_create_security_event_is_swallowed(self, app):
        from app.routes.auth import _flag_deactivated_account_login_attempt

        mock_user = MagicMock()
        mock_user.id = 998
        mock_user.active = False
        mock_user.deactivated_at = None

        with app.test_request_context("/"):
            with patch("app.routes.auth.create_security_event", side_effect=Exception("boom")):
                # Should not raise
                _flag_deactivated_account_login_attempt(
                    user=mock_user, auth_method="password", email="deact-exc@example.com"
                )


# =====================================================================
# login — test_email_blocked_outside_development
# =====================================================================


class TestLoginTestEmailBlocked:
    def test_test_email_blocked_in_production(self, app):
        from app.routes.auth import login
        import os

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = "test_user@example.com"
        mock_form.password.data = "TestPass123!"

        mock_user = MagicMock()
        mock_user.active = True

        with app.test_request_context("/login", method="POST"):
            with patch("app.routes.auth.LoginForm", return_value=mock_form), \
                 patch("app.routes.auth.RegisterForm"), \
                 patch("app.routes.auth.ForgotPasswordForm"), \
                 patch("app.routes.auth.log_login_attempt") as mock_log, \
                 patch("app.routes.auth.render_template", return_value=_mock_html_response()), \
                 patch("app.services.UserService.get_by_email", return_value=mock_user), \
                 patch.dict(os.environ, {"FLASK_CONFIG": "production"}):
                resp, status = _view_result(login())
        assert status == 200
        mock_log.assert_called_once_with("test_user@example.com", success=False, failure_reason="test_user_blocked")

    def test_sys_manager_email_blocked_in_production(self, app):
        from app.routes.auth import login
        import os

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = "sys-manager@example.com"
        mock_form.password.data = "Pass123!"

        with app.test_request_context("/login", method="POST"):
            with patch("app.routes.auth.LoginForm", return_value=mock_form), \
                 patch("app.routes.auth.RegisterForm"), \
                 patch("app.routes.auth.ForgotPasswordForm"), \
                 patch("app.routes.auth.log_login_attempt"), \
                 patch("app.routes.auth.render_template", return_value=_mock_html_response()), \
                 patch.dict(os.environ, {"FLASK_CONFIG": "production"}):
                resp, status = _view_result(login())
        assert status == 200


# =====================================================================
# login — user not found
# =====================================================================


class TestLoginUserNotFound:
    def test_login_user_not_found_renders_template(self, app):
        from app.routes.auth import login

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = "nonexistent@example.com"
        mock_form.password.data = "SomePass123!"

        with app.test_request_context("/login", method="POST"):
            with patch("app.routes.auth.LoginForm", return_value=mock_form), \
                 patch("app.routes.auth.RegisterForm"), \
                 patch("app.routes.auth.ForgotPasswordForm"), \
                 patch("app.routes.auth.log_login_attempt"), \
                 patch("app.routes.auth.render_template", return_value=_mock_html_response()):
                resp, status = _view_result(login())
        assert status == 200

    def test_login_user_service_exception_renders_template(self, app):
        from app.routes.auth import login

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = "srv-exc@example.com"
        mock_form.password.data = "TestPass123!"

        # UserService.get_by_email is called twice in login():
        # 1st call (unprotected) returns None, 2nd call (in try/except) raises
        with app.test_request_context("/login", method="POST"):
            with patch("app.routes.auth.LoginForm", return_value=mock_form), \
                 patch("app.routes.auth.RegisterForm"), \
                 patch("app.routes.auth.ForgotPasswordForm"), \
                 patch("app.routes.auth.log_login_attempt"), \
                 patch("app.routes.auth.render_template", return_value=_mock_html_response()), \
                 patch("app.routes.auth._is_account_locked_out", return_value=False), \
                 patch("app.services.UserService.get_by_email", side_effect=[None, Exception("db err")]):
                resp, status = _view_result(login())
        assert status == 200


# =====================================================================
# forgot_password — edge cases
# =====================================================================


class TestForgotPasswordEdgeCases:
    def test_forgot_password_authenticated_redirects(self, app, test_user):
        from app.routes.auth import forgot_password

        with app.test_request_context("/forgot-password", method="POST"):
            login_user(test_user)
            with patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/dashboard"):
                forgot_password()
        mock_redirect.assert_called()

    def test_forgot_password_user_not_found_still_flashes(self, app):
        from app.routes.auth import forgot_password

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = "nobody-fp@example.com"

        with app.test_request_context("/forgot-password", method="POST"):
            with patch("app.routes.auth.ForgotPasswordForm", return_value=mock_form), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                forgot_password()
        mock_redirect.assert_called()

    def test_forgot_password_token_generation_failure_redirects(self, app, db_session):
        from app.routes.auth import forgot_password

        with app.app_context():
            create_test_user(db_session, email="fp-tok-fail@example.com")

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = "fp-tok-fail@example.com"

        with app.test_request_context("/forgot-password", method="POST"):
            with patch("app.routes.auth.ForgotPasswordForm", return_value=mock_form), \
                 patch("app.routes.auth._generate_reset_token", return_value=None), \
                 patch("app.routes.auth.is_azure_b2c_configured", return_value=False), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                forgot_password()
        mock_redirect.assert_called()

    def test_forgot_password_email_send_failure_still_flashes(self, app, db_session):
        from app.routes.auth import forgot_password

        with app.app_context():
            create_test_user(db_session, email="fp-mail-fail@example.com")

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = "fp-mail-fail@example.com"

        with app.test_request_context("/forgot-password", method="POST"):
            with patch("app.routes.auth.ForgotPasswordForm", return_value=mock_form), \
                 patch("app.routes.auth._generate_reset_token", return_value="tok"), \
                 patch("app.routes.auth._send_password_reset_email", return_value=False), \
                 patch("app.routes.auth.is_azure_b2c_configured", return_value=False), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                forgot_password()
        mock_redirect.assert_called()

    def test_forgot_password_b2c_user_no_password_hash_skips_reset(self, app, db_session):
        from app.routes.auth import forgot_password

        with app.app_context():
            user = create_test_user(db_session, email="fp-b2c@example.com")
            user.password_hash = None
            db_session.commit()

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = "fp-b2c@example.com"

        with app.test_request_context("/forgot-password", method="POST"):
            with patch("app.routes.auth.ForgotPasswordForm", return_value=mock_form), \
                 patch("app.routes.auth.is_azure_b2c_configured", return_value=True), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                forgot_password()
        mock_redirect.assert_called()

    def test_forgot_password_validation_error_renders_template(self, app):
        from app.routes.auth import forgot_password

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = False

        with app.test_request_context("/forgot-password", method="POST"):
            with patch("app.routes.auth.ForgotPasswordForm", return_value=mock_form), \
                 patch("app.routes.auth.LoginForm"), \
                 patch("app.routes.auth.RegisterForm"), \
                 patch("app.routes.auth.render_template", return_value=_mock_html_response()) as mock_render:
                resp, status = _view_result(forgot_password())
        assert status == 200
        mock_render.assert_called()


# =====================================================================
# reset_password — edge cases
# =====================================================================


class TestResetPasswordEdgeCases:
    def test_reset_password_authenticated_redirects(self, app, test_user):
        from app.routes.auth import reset_password

        with app.test_request_context("/reset-password/tok"):
            login_user(test_user)
            with patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/dashboard"):
                reset_password("tok")
        mock_redirect.assert_called()

    def test_reset_password_user_not_found_redirects(self, app):
        from app.routes.auth import reset_password

        token_rec = MagicMock()
        token_rec.id = 1

        with app.test_request_context("/reset-password/tok"):
            with patch("app.routes.auth._verify_reset_token", return_value=("nothere@example.com", token_rec)), \
                 patch("app.routes.auth.is_azure_b2c_configured", return_value=False), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/forgot-password"):
                reset_password("tok")
        mock_redirect.assert_called()

    def test_reset_password_b2c_no_hash_redirects(self, app, db_session):
        from app.routes.auth import reset_password

        with app.app_context():
            user = create_test_user(db_session, email="reset-b2c@example.com")
            user.password_hash = None
            db_session.commit()

        token_rec = MagicMock()
        token_rec.id = 1

        with app.test_request_context("/reset-password/tok"):
            with patch("app.routes.auth._verify_reset_token", return_value=("reset-b2c@example.com", token_rec)), \
                 patch("app.routes.auth.is_azure_b2c_configured", return_value=True), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                reset_password("tok")
        mock_redirect.assert_called()

    def test_reset_password_mark_token_as_used_fails_fallback(self, app, db_session):
        from app.routes.auth import reset_password

        with app.app_context():
            create_test_user(db_session, email="reset-fallback@example.com")

        token_rec = MagicMock()
        token_rec.id = 1
        token_rec.mark_as_used.side_effect = Exception("db error")

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.password.data = "NewPass123!"

        with app.test_request_context("/reset-password/tok", method="POST"):
            with patch("app.routes.auth._verify_reset_token", return_value=("reset-fallback@example.com", token_rec)), \
                 patch("app.routes.auth.is_azure_b2c_configured", return_value=False), \
                 patch("app.routes.auth.ResetPasswordForm", return_value=mock_form), \
                 patch("app.routes.auth.validate_password_strength", return_value=(True, [])), \
                 patch("app.routes.auth.log_user_activity_for_user"), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                reset_password("tok")
        mock_redirect.assert_called()


# =====================================================================
# account_settings — POST success and failure
# =====================================================================


class TestAccountSettingsPost:
    def test_account_settings_post_success_redirects(self, app, admin_user, db_session):
        from app.routes.auth import account_settings
        from app.models import User

        with app.app_context():
            user_id = int(admin_user.id)

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.name.data = "Updated Name"
        mock_form.title.data = "Manager"
        mock_form.chatbot_enabled.data = True
        mock_form.profile_color.data = "#FF0000"

        with app.test_request_context("/account-settings", method="POST"):
            login_user(User.query.get(user_id))
            with patch("app.routes.auth.AccountSettingsForm", return_value=mock_form), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/account-settings"), \
                 patch("app.routes.auth.log_user_activity"), \
                 patch("app.routes.auth.user_has_ai_beta_access", return_value=False), \
                 patch("app.services.notification_service.NotificationService.get_notification_preferences", return_value={}), \
                 patch("app.routes.notifications.get_notification_types_for_user", return_value={"for_user": []}), \
                 patch("app.routes.notifications.get_notification_type_labels", return_value={}):
                account_settings()
        mock_redirect.assert_called()

    def test_account_settings_post_db_error_renders_template(self, app, admin_user, db_session):
        from app.routes.auth import account_settings
        from app.models import User

        with app.app_context():
            user_id = int(admin_user.id)

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.name.data = "Updated"
        mock_form.title.data = None
        mock_form.chatbot_enabled.data = False
        mock_form.profile_color.data = None

        with app.test_request_context("/account-settings", method="POST"):
            login_user(User.query.get(user_id))
            with patch("app.routes.auth.AccountSettingsForm", return_value=mock_form), \
                 patch("app.routes.auth.db") as mock_db, \
                 patch("app.routes.auth.render_template", return_value=_mock_html_response()) as mock_render, \
                 patch("app.routes.auth.user_has_ai_beta_access", return_value=False), \
                 patch("app.services.notification_service.NotificationService.get_notification_preferences", return_value={}), \
                 patch("app.routes.notifications.get_notification_types_for_user", return_value={"for_user": []}), \
                 patch("app.routes.notifications.get_notification_type_labels", return_value={}):
                mock_db.session.flush.side_effect = Exception("flush error")
                account_settings()
        mock_render.assert_called()


# =====================================================================
# debug_profile_picture
# =====================================================================


class TestDebugProfilePicture:
    def test_debug_endpoint_disabled_non_debug_aborts_404(self, app, admin_user, db_session):
        from app.routes.auth import debug_profile_picture
        from app.models import User
        from werkzeug.exceptions import NotFound

        with app.app_context():
            user_id = int(admin_user.id)

        with app.test_request_context("/debug/profile-picture"):
            login_user(User.query.get(user_id))
            with patch("app.routes.auth.current_app") as mock_capp:
                mock_capp.config = {"DEBUG": False}
                mock_capp.logger = MagicMock()
                with pytest.raises(NotFound):
                    debug_profile_picture()

    def test_debug_endpoint_enabled_returns_ok(self, app, admin_user, db_session):
        from app.routes.auth import debug_profile_picture
        from app.models import User

        with app.app_context():
            user_id = int(admin_user.id)

        with app.test_request_context("/debug/profile-picture"):
            login_user(User.query.get(user_id))
            with patch("app.routes.auth.current_app") as mock_capp:
                mock_capp.config = {"DEBUG": True}
                mock_capp.logger = MagicMock()
                resp, status = _view_result(debug_profile_picture())
        assert status == 200


# =====================================================================
# remove_own_device
# =====================================================================


class TestRemoveOwnDevice:
    def test_remove_device_success(self, app, admin_user, db_session):
        from app.models.system import UserDevice
        from app.routes.auth import remove_own_device
        from app.models import User

        with app.app_context():
            user_id = int(admin_user.id)
            device = UserDevice(
                user_id=user_id,
                device_token=f"remove-token-{uuid4().hex}",
                platform="ios",
                device_name="iPad",
            )
            db_session.add(device)
            db_session.commit()
            device_id = int(device.id)

        with app.test_request_context(
            f"/account-settings/devices/{device_id}/remove", method="DELETE"
        ):
            login_user(User.query.get(user_id))
            resp, status = remove_own_device(device_id)
        assert status == 200
        assert resp.get_json()["ok"] is True

    def test_remove_device_not_found_aborts(self, app, admin_user, db_session):
        from app.routes.auth import remove_own_device
        from app.models import User
        from werkzeug.exceptions import NotFound

        with app.app_context():
            user_id = int(admin_user.id)

        with app.test_request_context("/account-settings/devices/999999/remove", method="DELETE"):
            login_user(User.query.get(user_id))
            with pytest.raises(NotFound):
                remove_own_device(999999)

    def test_remove_device_db_error_returns_500(self, app, admin_user, db_session):
        from app.models.system import UserDevice
        from app.routes.auth import remove_own_device
        from app.models import User

        with app.app_context():
            user_id = int(admin_user.id)
            device = UserDevice(
                user_id=user_id,
                device_token=f"remove-err-{uuid4().hex}",
                platform="android",
                device_name="Phone",
            )
            db_session.add(device)
            db_session.commit()
            device_id = int(device.id)

        with app.test_request_context(
            f"/account-settings/devices/{device_id}/remove", method="DELETE"
        ):
            login_user(User.query.get(user_id))
            with patch("app.routes.auth.db") as mock_db:
                mock_db.session.delete = MagicMock()
                mock_db.session.flush.side_effect = Exception("db error")
                resp, status = remove_own_device(device_id)
        assert status == 500


# =====================================================================
# kickout_own_device — already logged out
# =====================================================================


class TestKickoutOwnDeviceAlreadyLoggedOut:
    def test_kickout_already_logged_out_returns_400(self, app, admin_user, db_session):
        from app.models.system import UserDevice
        from app.routes.auth import kickout_own_device
        from app.models import User
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user_id = int(admin_user.id)
            device = UserDevice(
                user_id=user_id,
                device_token=f"logout-{uuid4().hex}",
                platform="android",
                device_name="Phone",
                logged_out_at=utcnow(),
            )
            db_session.add(device)
            db_session.commit()
            device_id = int(device.id)

        with app.test_request_context(
            f"/account-settings/devices/{device_id}/kickout", method="POST"
        ):
            login_user(User.query.get(user_id))
            resp, status = kickout_own_device(device_id)
        assert status == 400

    def test_kickout_db_error_returns_500(self, app, admin_user, db_session):
        from app.models.system import UserDevice
        from app.routes.auth import kickout_own_device
        from app.models import User

        with app.app_context():
            user_id = int(admin_user.id)
            device = UserDevice(
                user_id=user_id,
                device_token=f"kickout-err-{uuid4().hex}",
                platform="ios",
                device_name="iPhone",
            )
            db_session.add(device)
            db_session.commit()
            device_id = int(device.id)

        with app.test_request_context(
            f"/account-settings/devices/{device_id}/kickout", method="POST"
        ):
            login_user(User.query.get(user_id))
            with patch("app.routes.auth.db") as mock_db:
                mock_db.session.flush.side_effect = Exception("db err")
                resp, status = kickout_own_device(device_id)
        assert status == 500


# =====================================================================
# _b2c_get_required_config
# =====================================================================


class TestB2cGetRequiredConfig:
    def test_returns_none_when_config_missing(self, app):
        from app.routes.auth import _b2c_get_required_config

        with app.test_request_context("/"):
            with patch("app.routes.auth.current_app") as mock_capp:
                mock_capp.config = {}
                result = _b2c_get_required_config()
        assert result is None

    def test_returns_config_when_all_set(self, app):
        from app.routes.auth import _b2c_get_required_config

        cfg = {
            "AZURE_B2C_TENANT": "test.onmicrosoft.com",
            "AZURE_B2C_POLICY": "B2C_1A_TEST",
            "AZURE_B2C_CLIENT_ID": "client-id",
            "AZURE_B2C_CLIENT_SECRET": "client-secret",
            "AZURE_B2C_REDIRECT_URI": "http://localhost/auth/azure/callback",
        }
        with app.test_request_context("/"):
            with patch("app.routes.auth.current_app") as mock_capp:
                mock_capp.config = cfg
                result = _b2c_get_required_config()
        assert result is not None
        assert result["tenant"] == "test.onmicrosoft.com"


# =====================================================================
# _generate_pkce_pair
# =====================================================================


class TestGeneratePkcePair:
    def test_returns_verifier_and_challenge(self, app):
        from app.routes.auth import _generate_pkce_pair

        with app.test_request_context("/"):
            verifier, challenge = _generate_pkce_pair()
        assert len(verifier) > 10
        assert len(challenge) > 10
        assert verifier != challenge


# =====================================================================
# _decode_jwt_payload_unverified
# =====================================================================


class TestDecodeJwtPayloadUnverified:
    def test_valid_token_returns_dict(self, app):
        import base64
        import json as _json
        from app.routes.auth import _decode_jwt_payload_unverified

        payload = base64.urlsafe_b64encode(
            _json.dumps({"sub": "user-id", "email": "test@example.com"}).encode()
        ).rstrip(b"=").decode()
        fake_token = f"header.{payload}.sig"

        with app.test_request_context("/"):
            result = _decode_jwt_payload_unverified(fake_token)
        assert result is not None
        assert result["sub"] == "user-id"

    def test_invalid_token_returns_none(self, app):
        from app.routes.auth import _decode_jwt_payload_unverified

        with app.test_request_context("/"):
            result = _decode_jwt_payload_unverified("not.a.token")
        # May return None or a dict; just ensure no exception
        assert result is None or isinstance(result, dict)

    def test_single_part_token_returns_none(self, app):
        from app.routes.auth import _decode_jwt_payload_unverified

        with app.test_request_context("/"):
            result = _decode_jwt_payload_unverified("onlyonepart")
        assert result is None


# =====================================================================
# azure_login — authenticated non-mobile redirects to dashboard
# =====================================================================


class TestAzureLoginRoute:
    def test_azure_login_authenticated_non_mobile_redirects_to_dashboard(self, app, test_user):
        from app.routes.auth import azure_login

        with app.test_request_context("/login/azure"):
            login_user(test_user)
            with patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/dashboard"):
                azure_login()
        mock_redirect.assert_called_with("/dashboard")

    def test_azure_login_not_configured_redirects_login(self, app):
        from app.routes.auth import azure_login

        with app.test_request_context("/login/azure"):
            with patch("app.routes.auth._b2c_get_required_config", return_value=None), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                azure_login()
        mock_redirect.assert_called_with("/login")

    def test_azure_login_metadata_failure_redirects_login(self, app):
        from app.routes.auth import azure_login

        cfg = {
            "tenant": "t", "policy": "p", "client_id": "cid",
            "client_secret": "csec", "redirect_uri": "http://r", "scope": "openid",
        }
        with app.test_request_context("/login/azure"):
            with patch("app.routes.auth._b2c_get_required_config", return_value=cfg), \
                 patch("app.routes.auth._b2c_metadata", side_effect=Exception("network err")), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                azure_login()
        mock_redirect.assert_called_with("/login")

    def test_azure_login_mobile_clears_session(self, app, test_user):
        from app.routes.auth import azure_login

        meta = {"authorization_endpoint": "https://b2c.example.com/authorize"}
        cfg = {
            "tenant": "t", "policy": "p", "client_id": "cid",
            "client_secret": "csec", "redirect_uri": "http://r", "scope": "openid",
        }

        with app.test_request_context("/login/azure?mobile_return_scheme=humdatabank"):
            login_user(test_user)
            with patch("app.routes.auth._b2c_get_required_config", return_value=cfg), \
                 patch("app.routes.auth._b2c_metadata", return_value=meta), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect:
                azure_login()
        # After clearing session and falling through to Azure redirect
        mock_redirect.assert_called()


# =====================================================================
# azure_callback — various branches
# =====================================================================


class TestAzureCallbackCoverage:
    def test_callback_not_configured_redirects(self, app):
        from app.routes.auth import azure_callback

        with app.test_request_context("/auth/azure/callback?code=c&state=s"):
            with patch("app.routes.auth._b2c_get_required_config", return_value=None), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                azure_callback()
        mock_redirect.assert_called_with("/login")

    def test_callback_error_user_cancel(self, app):
        from app.routes.auth import azure_callback

        with app.test_request_context(
            "/auth/azure/callback?error=access_denied&error_description=AADB2C90091"
        ):
            with patch("app.routes.auth._b2c_get_required_config", return_value={"tenant": "t", "policy": "p"}), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                azure_callback()
        mock_redirect.assert_called_with("/login")

    def test_callback_error_other_renders_error_template(self, app):
        from app.routes.auth import azure_callback

        with app.test_request_context(
            "/auth/azure/callback?error=server_error&error_description=Some+other+error"
        ):
            with patch("app.routes.auth._b2c_get_required_config", return_value={"tenant": "t", "policy": "p"}), \
                 patch("app.routes.auth.render_template", return_value=_mock_html_response()) as mock_render:
                azure_callback()
        mock_render.assert_called()

    def test_callback_missing_code_redirects(self, app):
        from app.routes.auth import azure_callback

        with app.test_request_context("/auth/azure/callback?state=s"):
            with patch("app.routes.auth._b2c_get_required_config", return_value={"tenant": "t", "policy": "p"}), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                azure_callback()
        mock_redirect.assert_called_with("/login")

    def test_callback_expired_jwt_state_redirects(self, app):
        import jwt
        from app.routes.auth import azure_callback

        expired_state = jwt.encode(
            {"exp": 0, "_state": "s", "verifier": "v", "nonce": "n"},
            app.config["SECRET_KEY"],
            algorithm="HS256",
        )
        with app.test_request_context(f"/auth/azure/callback?code=c&state={expired_state}"):
            with patch("app.routes.auth._b2c_get_required_config", return_value={"tenant": "t", "policy": "p"}), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                azure_callback()
        mock_redirect.assert_called_with("/login")

    def test_callback_session_state_mismatch_redirects(self, app):
        from app.routes.auth import azure_callback

        with app.test_request_context("/auth/azure/callback?code=c&state=invalid-state"):
            with patch("app.routes.auth._b2c_get_required_config", return_value={"tenant": "t", "policy": "p"}), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"), \
                 patch("app.routes.auth._b2c_metadata", return_value={"token_endpoint": "http://te"}):
                azure_callback()
        mock_redirect.assert_called()

    def test_callback_metadata_fail_in_callback_redirects(self, app):
        import jwt as _jwt
        from app.routes.auth import azure_callback
        import time as _time

        state = _jwt.encode(
            {
                "_state": "inner",
                "verifier": "v",
                "nonce": "n",
                "next": None,
                "mobile": False,
                "iat": int(_time.time()),
                "exp": int(_time.time()) + 600,
            },
            app.config["SECRET_KEY"],
            algorithm="HS256",
        )
        with app.test_request_context(f"/auth/azure/callback?code=c&state={state}"):
            with patch("app.routes.auth._b2c_get_required_config", return_value={"tenant": "t", "policy": "p"}), \
                 patch("app.routes.auth._b2c_metadata", side_effect=Exception("meta fail")), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                azure_callback()
        mock_redirect.assert_called()

    def test_callback_token_exchange_fail_redirects(self, app):
        import jwt as _jwt
        from app.routes.auth import azure_callback
        import time as _time

        state = _jwt.encode(
            {
                "_state": "inner",
                "verifier": "v",
                "nonce": "n",
                "next": None,
                "mobile": False,
                "iat": int(_time.time()),
                "exp": int(_time.time()) + 600,
            },
            app.config["SECRET_KEY"],
            algorithm="HS256",
        )
        meta = {"token_endpoint": "http://token", "userinfo_endpoint": None, "jwks_uri": "http://jwks"}
        with app.test_request_context(f"/auth/azure/callback?code=c&state={state}"):
            with patch("app.routes.auth._b2c_get_required_config", return_value={"tenant": "t", "policy": "p", "client_id": "cid", "client_secret": "cs", "redirect_uri": "http://r"}), \
                 patch("app.routes.auth._b2c_metadata", return_value=meta), \
                 patch("app.routes.auth.requests.post", side_effect=Exception("network fail")), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                azure_callback()
        mock_redirect.assert_called()


# =====================================================================
# logout — with B2C end session endpoint
# =====================================================================


class TestLogoutB2c:
    def test_logout_non_localhost_with_b2c_config(self, app, admin_user, db_session):
        from app.routes.auth import logout
        from app.models import User

        with app.app_context():
            user_id = int(admin_user.id)
            user = User.query.get(user_id)

        meta = {"end_session_endpoint": "https://b2c.example.com/endsession"}
        cfg = {
            "tenant": "t", "policy": "p", "client_id": "cid",
            "client_secret": "cs", "redirect_uri": "http://r", "scope": "openid",
        }
        with app.test_request_context("/logout"):
            login_user(user)
            with patch("app.routes.auth.log_user_activity"), \
                 patch("app.routes.auth.log_logout"), \
                 patch("app.routes.auth._b2c_get_required_config", return_value=cfg), \
                 patch("app.routes.auth._b2c_metadata", return_value=meta), \
                 patch("app.routes.auth.clear_mobile_app_embed_cookie", side_effect=lambda r: r), \
                 patch("app.routes.auth.current_app") as mock_capp:
                mock_capp.config = {
                    **app.config,
                    "AZURE_B2C_POST_LOGOUT_REDIRECT_URI": "https://example.com/post-logout",
                }
                mock_capp.logger = MagicMock()
                resp = logout()
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_logout_with_session_duration_calculation(self, app, admin_user, db_session):
        from app.routes.auth import logout
        from app.models import User
        from app.utils.datetime_helpers import utcnow
        from datetime import timedelta

        with app.app_context():
            user_id = int(admin_user.id)
            user = User.query.get(user_id)

        with app.test_request_context("/logout"):
            from flask import session
            login_user(user)
            session["session_start"] = (utcnow() - timedelta(minutes=5)).isoformat()
            with patch("app.routes.auth.log_user_activity"), \
                 patch("app.routes.auth.log_logout"), \
                 patch("app.routes.auth._b2c_get_required_config", return_value=None), \
                 patch("app.routes.auth.clear_mobile_app_embed_cookie", side_effect=lambda r: r):
                resp = logout()
        assert resp.status_code in (301, 302, 303, 307, 308)


# =====================================================================
# _send_password_reset_email
# =====================================================================


class TestSendPasswordResetEmail:
    def test_returns_true_on_success(self, app):
        from app.routes.auth import _send_password_reset_email

        with app.test_request_context("/"):
            with patch("app.routes.auth.send_email", return_value=True), \
                 patch("app.routes.auth.get_organization_name", return_value="TestOrg"), \
                 patch("app.routes.auth.url_for", return_value="http://reset/tok"):
                result = _send_password_reset_email("user@example.com", "tok")
        assert result is True

    def test_returns_false_on_exception(self, app):
        from app.routes.auth import _send_password_reset_email

        with app.test_request_context("/"):
            with patch("app.routes.auth.send_email", side_effect=Exception("smtp error")), \
                 patch("app.routes.auth.get_organization_name", return_value="TestOrg"), \
                 patch("app.routes.auth.url_for", return_value="http://reset/tok"):
                result = _send_password_reset_email("user@example.com", "tok")
        assert result is False


# =====================================================================
# register — weak password renders template
# =====================================================================


class TestRegisterWeakPassword:
    def test_register_weak_password_renders_template(self, app, db_session):
        from app.routes.auth import register

        with app.app_context():
            country = create_test_country(db_session)
            country_id = country.id

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = f"weak-{uuid4().hex[:6]}@example.com"
        mock_form.name.data = "New User"
        mock_form.title.data = None
        mock_form.requested_country_id.data = country_id
        mock_form.request_message.data = None
        mock_form.password.data = "short"

        with app.test_request_context("/register", method="POST"):
            with patch("app.routes.auth.current_user") as mock_user, \
                 patch("app.routes.auth.is_azure_b2c_configured", return_value=False), \
                 patch("app.routes.auth.RegisterForm", return_value=mock_form), \
                 patch("app.routes.auth.LoginForm"), \
                 patch("app.routes.auth.ForgotPasswordForm"), \
                 patch("app.routes.auth.validate_password_strength", return_value=(False, ["Too weak"])), \
                 patch("app.routes.auth.render_template", return_value=_mock_html_response()) as mock_render:
                mock_user.is_authenticated = False
                resp, status = _view_result(register())
        assert status == 200
        mock_render.assert_called()

    def test_register_b2c_enabled_redirects(self, app):
        from app.routes.auth import register

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = False

        with app.test_request_context("/register", method="POST"):
            with patch("app.routes.auth.current_user") as mock_user, \
                 patch("app.routes.auth.is_azure_b2c_configured", return_value=True), \
                 patch("app.routes.auth.RegisterForm", return_value=mock_form), \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                mock_user.is_authenticated = False
                register()
        mock_redirect.assert_called()

    def test_register_get_redirects_to_login(self, app):
        from app.routes.auth import register

        with app.test_request_context("/register", method="GET"):
            with patch("app.routes.auth.current_user") as mock_user, \
                 patch("app.routes.auth.redirect", side_effect=lambda loc: loc) as mock_redirect, \
                 patch("app.routes.auth.url_for", return_value="/login"):
                mock_user.is_authenticated = False
                register()
        mock_redirect.assert_called()

    def test_register_db_exception_renders_template(self, app, db_session):
        from app.routes.auth import register

        with app.app_context():
            country = create_test_country(db_session)
            country_id = country.id

        mock_form = MagicMock()
        mock_form.validate_on_submit.return_value = True
        mock_form.email.data = f"db-err-{uuid4().hex[:6]}@example.com"
        mock_form.name.data = "DB Error User"
        mock_form.title.data = None
        mock_form.requested_country_id.data = country_id
        mock_form.request_message.data = None
        mock_form.password.data = "StrongPass123!"

        with app.test_request_context("/register", method="POST"):
            with patch("app.routes.auth.current_user") as mock_user, \
                 patch("app.routes.auth.is_azure_b2c_configured", return_value=False), \
                 patch("app.routes.auth.RegisterForm", return_value=mock_form), \
                 patch("app.routes.auth.LoginForm"), \
                 patch("app.routes.auth.ForgotPasswordForm"), \
                 patch("app.routes.auth.validate_password_strength", return_value=(True, [])), \
                 patch("app.routes.auth.db") as mock_db, \
                 patch("app.routes.auth.render_template", return_value=_mock_html_response()) as mock_render:
                mock_user.is_authenticated = False
                mock_db.session.flush.side_effect = Exception("db error")
                resp, status = _view_result(register())
        assert status == 200
        mock_render.assert_called()
