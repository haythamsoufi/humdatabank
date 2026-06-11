"""Unit tests for auth WTForms."""
import pytest
from unittest.mock import patch

from app.forms.auth_forms import (
    LoginForm,
    AccountSettingsForm,
    RegisterForm,
    ForgotPasswordForm,
    ResetPasswordForm,
    RequestCountryAccessForm,
)

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]


@pytest.mark.unit
class TestLoginForm:
    def test_valid_data(self, app):
        with app.app_context():
            form = LoginForm(data={'email': 'user@example.com', 'password': 'secret'})
            assert form.validate() is True

    def test_missing_email(self, app):
        with app.app_context():
            form = LoginForm(data={'password': 'secret'})
            assert form.validate() is False
            assert 'email' in form.errors

    def test_invalid_email(self, app):
        with app.app_context():
            form = LoginForm(data={'email': 'not-an-email', 'password': 'secret'})
            assert form.validate() is False
            assert 'email' in form.errors

    def test_missing_password(self, app):
        with app.app_context():
            form = LoginForm(data={'email': 'user@example.com'})
            assert form.validate() is False
            assert 'password' in form.errors


@pytest.mark.unit
class TestAccountSettingsForm:
    def test_optional_fields(self, app):
        with app.app_context():
            form = AccountSettingsForm(data={})
            assert form.validate() is True

    def test_profile_color_choices_populated(self, app):
        with app.app_context():
            form = AccountSettingsForm()
            assert len(form.profile_color.choices) > 0

    def test_name_and_title_optional(self, app):
        with app.app_context():
            form = AccountSettingsForm(data={'name': 'Ada Lovelace', 'title': 'Analyst'})
            assert form.validate() is True
            assert form.name.data == 'Ada Lovelace'


@pytest.mark.unit
class TestRegisterForm:
    def test_valid_data(self, app, db_session):
        from tests.factories import create_test_country
        with app.app_context():
            country = create_test_country(db_session)
            form = RegisterForm(data={
                'email': 'new@example.com',
                'requested_country_id': country.id,
                'password': 'SecurePass123!',
                'confirm_password': 'SecurePass123!',
            })
            assert form.validate() is True

    def test_password_mismatch(self, app, db_session):
        from tests.factories import create_test_country
        with app.app_context():
            country = create_test_country(db_session)
            form = RegisterForm(data={
                'email': 'new@example.com',
                'requested_country_id': country.id,
                'password': 'SecurePass123!',
                'confirm_password': 'DifferentPass123!',
            })
            assert form.validate() is False
            assert 'confirm_password' in form.errors

    def test_missing_country(self, app, db_session):
        with app.app_context():
            form = RegisterForm(data={
                'email': 'new@example.com',
                'password': 'SecurePass123!',
                'confirm_password': 'SecurePass123!',
            })
            assert form.validate() is False
            assert 'requested_country_id' in form.errors

    def test_db_failure_fallback_choices(self, app):
        with app.app_context():
            with patch('app.models.Country.query') as mock_query:
                mock_query.order_by.side_effect = RuntimeError('db down')
                form = RegisterForm()
            assert form.requested_country_id.choices == [('', '— Select a country —')]

    def test_password_too_short(self, app, db_session):
        from tests.factories import create_test_country
        with app.app_context():
            country = create_test_country(db_session)
            form = RegisterForm(data={
                'email': 'short@example.com',
                'requested_country_id': country.id,
                'password': 'short',
                'confirm_password': 'short',
            })
            assert form.validate() is False
            assert 'password' in form.errors

    def test_invalid_email_format(self, app, db_session):
        from tests.factories import create_test_country
        with app.app_context():
            country = create_test_country(db_session)
            form = RegisterForm(data={
                'email': 'not-an-email',
                'requested_country_id': country.id,
                'password': 'SecurePass123!',
                'confirm_password': 'SecurePass123!',
            })
            assert form.validate() is False
            assert 'email' in form.errors


@pytest.mark.unit
class TestForgotPasswordForm:
    def test_valid_email(self, app):
        with app.app_context():
            form = ForgotPasswordForm(data={'email': 'user@example.com'})
            assert form.validate() is True

    def test_invalid_email(self, app):
        with app.app_context():
            form = ForgotPasswordForm(data={'email': 'bad'})
            assert form.validate() is False

    def test_missing_email(self, app):
        with app.app_context():
            form = ForgotPasswordForm(data={})
            assert form.validate() is False
            assert 'email' in form.errors


@pytest.mark.unit
class TestResetPasswordForm:
    def test_valid_matching_passwords(self, app):
        with app.app_context():
            form = ResetPasswordForm(data={
                'password': 'NewSecure123!',
                'confirm_password': 'NewSecure123!',
            })
            assert form.validate() is True

    def test_password_mismatch(self, app):
        with app.app_context():
            form = ResetPasswordForm(data={
                'password': 'NewSecure123!',
                'confirm_password': 'OtherPass123!',
            })
            assert form.validate() is False
            assert 'confirm_password' in form.errors

    def test_password_too_short(self, app):
        with app.app_context():
            form = ResetPasswordForm(data={
                'password': 'short',
                'confirm_password': 'short',
            })
            assert form.validate() is False

    def test_missing_confirm_password(self, app):
        with app.app_context():
            form = ResetPasswordForm(data={'password': 'NewSecure123!'})
            assert form.validate() is False
            assert 'confirm_password' in form.errors


@pytest.mark.unit
class TestRequestCountryAccessForm:
    def test_loads_countries(self, app, db_session):
        from tests.factories import create_test_country
        with app.app_context():
            create_test_country(db_session)
            form = RequestCountryAccessForm()
            assert len(form.requested_country_id.choices) >= 1

    def test_excludes_user_existing_access(self, app, db_session):
        from tests.factories import create_test_country, create_test_user
        with app.app_context():
            user = create_test_user(db_session, role='focal_point')
            country = create_test_country(db_session)
            user.add_entity_permission('country', country.id)
            db_session.commit()
            form = RequestCountryAccessForm(user_id=user.id)
            assert country.id in form._user_has_access

    def test_requires_at_least_one_country(self, app, db_session):
        with app.app_context():
            form = RequestCountryAccessForm(data={'requested_country_id': []})
            assert form.validate() is False

    def test_db_failure_empty_choices(self, app):
        with app.app_context():
            with patch('app.models.Country.query') as mock_query:
                mock_query.order_by.side_effect = RuntimeError('db down')
                form = RequestCountryAccessForm()
            assert form.requested_country_id.choices == []
            assert form._user_has_access == set()

    def test_without_user_id_has_empty_access_set(self, app, db_session):
        from tests.factories import create_test_country
        with app.app_context():
            create_test_country(db_session)
            form = RequestCountryAccessForm()
            assert form._user_has_access == set()
            assert len(form.requested_country_id.choices) >= 1

    def test_valid_country_selection(self, app, db_session):
        from tests.factories import create_test_country
        with app.app_context():
            country = create_test_country(db_session)
            form = RequestCountryAccessForm(data={'requested_country_id': [country.id]})
            assert form.validate() is True


@pytest.mark.unit
class TestRegisterFormOptionalFields:
    def test_register_optional_name_and_message(self, app, db_session):
        from tests.factories import create_test_country
        with app.app_context():
            country = create_test_country(db_session)
            form = RegisterForm(data={
                'email': 'full@example.com',
                'name': 'Full Name',
                'title': 'Analyst',
                'request_message': 'Need access for reporting',
                'requested_country_id': country.id,
                'password': 'SecurePass123!',
                'confirm_password': 'SecurePass123!',
            })
            assert form.validate() is True

    def test_account_settings_chatbot_toggle(self, app):
        with app.app_context():
            form = AccountSettingsForm(data={'chatbot_enabled': True})
            assert form.validate() is True
            assert form.chatbot_enabled.data is True
