"""Unit tests for app/forms/system/user_forms.py — targets 100% coverage."""
import pytest
from unittest.mock import patch, MagicMock
from wtforms.validators import ValidationError

pytestmark = [pytest.mark.unit]


class TestUserFormInit:
    def test_instantiation(self, app):
        with app.app_context():
            with patch('app.forms.system.user_forms.Country') as mock_country:
                mock_country.query.order_by.return_value.all.return_value = []
                from app.forms.system.user_forms import UserForm
                form = UserForm(data={})
                assert form is not None

    def test_countries_choices_populated(self, app):
        with app.app_context():
            country = MagicMock()
            country.id = 1
            country.name = 'France'
            with patch('app.forms.system.user_forms.Country') as mock_country:
                mock_country.query.order_by.return_value.all.return_value = [country]
                from app.forms.system.user_forms import UserForm
                form = UserForm(data={})
                choice_ids = [c[0] for c in form.countries.choices]
                assert 1 in choice_ids

    def test_rbac_roles_choices_populated(self, app):
        with app.app_context():
            with patch('app.forms.system.user_forms.Country') as mock_country:
                mock_country.query.order_by.return_value.all.return_value = []
                from app.forms.system.user_forms import UserForm
                from app.models.rbac import RbacRole
                mock_role = MagicMock()
                mock_role.id = 1
                mock_role.name = 'Admin'
                with patch.object(RbacRole, 'query') as mock_q:
                    mock_q.order_by.return_value.all.return_value = [mock_role]
                    form = UserForm(data={})
                    assert len(form.rbac_roles.choices) > 0

    def test_rbac_roles_exception_falls_back(self, app):
        with app.app_context():
            with patch('app.forms.system.user_forms.Country') as mock_country:
                mock_country.query.order_by.return_value.all.return_value = []
                # Patch the RbacRole query to raise to simulate a DB failure
                with patch('app.models.rbac.RbacRole.query') as mock_q:
                    mock_q.order_by.side_effect = RuntimeError('RBAC not available')
                    from app.forms.system.user_forms import UserForm
                    form = UserForm(data={})
                    assert form.rbac_roles.choices == []


class TestUserFormValidation:
    def _make_form(self, app, data):
        with patch('app.forms.system.user_forms.Country') as mock_country:
            mock_country.query.order_by.return_value.all.return_value = []
            from app.forms.system.user_forms import UserForm
            form = UserForm(data=data)
            form.rbac_roles.choices = []  # disable RBAC check for simple tests
            return form

    def test_valid_minimal(self, app):
        with app.app_context():
            form = self._make_form(app, {'email': 'user@test.com', 'name': 'Alice'})
            assert form.validate() is True

    def test_missing_email(self, app):
        with app.app_context():
            form = self._make_form(app, {'name': 'Alice'})
            assert form.validate() is False
            assert 'email' in form.errors

    def test_invalid_email(self, app):
        with app.app_context():
            form = self._make_form(app, {'email': 'not-valid', 'name': 'Alice'})
            assert form.validate() is False
            assert 'email' in form.errors

    def test_missing_name(self, app):
        with app.app_context():
            form = self._make_form(app, {'email': 'user@test.com'})
            assert form.validate() is False
            assert 'name' in form.errors

    def test_valid_with_optional_title(self, app):
        with app.app_context():
            form = self._make_form(app, {
                'email': 'user@test.com',
                'name': 'Alice',
                'title': 'Analyst',
            })
            assert form.validate() is True

    def test_valid_profile_color_hex(self, app):
        with app.app_context():
            from werkzeug.datastructures import ImmutableMultiDict
            with patch('app.forms.system.user_forms.Country') as mock_country:
                mock_country.query.order_by.return_value.all.return_value = []
                from app.forms.system.user_forms import UserForm
                form = UserForm(formdata=ImmutableMultiDict([
                    ('email', 'user@test.com'),
                    ('name', 'Alice'),
                    ('profile_color', '#FF5733'),
                ]))
                form.rbac_roles.choices = []
                assert form.validate() is True

    def test_invalid_profile_color_format(self, app):
        with app.app_context():
            from werkzeug.datastructures import ImmutableMultiDict
            with patch('app.forms.system.user_forms.Country') as mock_country:
                mock_country.query.order_by.return_value.all.return_value = []
                from app.forms.system.user_forms import UserForm
                form = UserForm(formdata=ImmutableMultiDict([
                    ('email', 'user@test.com'),
                    ('name', 'Alice'),
                    ('profile_color', 'red'),
                ]))
                form.rbac_roles.choices = []
                assert form.validate() is False
                assert 'profile_color' in form.errors

    def test_profile_color_optional(self, app):
        with app.app_context():
            form = self._make_form(app, {
                'email': 'user@test.com',
                'name': 'Alice',
            })
            assert form.validate() is True


class TestUserFormValidateRbacRoles:
    def test_no_choices_skips_validation(self, app):
        with app.app_context():
            with patch('app.forms.system.user_forms.Country') as mock_country:
                mock_country.query.order_by.return_value.all.return_value = []
                from app.forms.system.user_forms import UserForm
                form = UserForm(data={'email': 'user@test.com', 'name': 'Alice'})
                form.rbac_roles.choices = []  # No choices = skip validation
                field = MagicMock()
                field.data = []
                form.validate_rbac_roles(field)  # Should not raise

    def test_empty_roles_with_choices_raises(self, app):
        with app.app_context():
            with patch('app.forms.system.user_forms.Country') as mock_country:
                mock_country.query.order_by.return_value.all.return_value = []
                from app.forms.system.user_forms import UserForm
                form = UserForm(data={'email': 'user@test.com', 'name': 'Alice'})
                form.rbac_roles.choices = [(1, 'Admin'), (2, 'Viewer')]
                field = MagicMock()
                field.data = []
                with pytest.raises(ValidationError):
                    form.validate_rbac_roles(field)

    def test_roles_selected_with_choices_passes(self, app):
        with app.app_context():
            with patch('app.forms.system.user_forms.Country') as mock_country:
                mock_country.query.order_by.return_value.all.return_value = []
                from app.forms.system.user_forms import UserForm
                form = UserForm(data={'email': 'user@test.com', 'name': 'Alice'})
                form.rbac_roles.choices = [(1, 'Admin')]
                field = MagicMock()
                field.data = [1]
                form.validate_rbac_roles(field)  # Should not raise

    def test_validate_rbac_roles_method_called_when_choices_exist(self, app):
        """Verify validate_rbac_roles raises when roles are required but none selected."""
        with app.app_context():
            with patch('app.forms.system.user_forms.Country') as mock_country:
                mock_country.query.order_by.return_value.all.return_value = []
                from app.forms.system.user_forms import UserForm
                form = UserForm(data={'email': 'user@test.com', 'name': 'Alice'})
                form.rbac_roles.choices = [(1, 'Admin')]
                # Call the method validator directly as the form does internally
                from wtforms.validators import ValidationError
                field = MagicMock()
                field.data = []  # No roles selected
                with pytest.raises(ValidationError):
                    form.validate_rbac_roles(field)
