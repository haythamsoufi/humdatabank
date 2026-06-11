"""Unit tests for app/forms/system/country_forms.py — targets 100% coverage."""
import pytest
from unittest.mock import patch, MagicMock
from wtforms.validators import ValidationError

pytestmark = [pytest.mark.unit]


class TestCountryFormInit:
    def test_instantiation(self, app):
        with app.app_context():
            from app.forms.system.country_forms import CountryForm
            form = CountryForm(data={})
            assert form is not None

    def test_preferred_language_choices_populated(self, app):
        with app.app_context():
            from app.forms.system.country_forms import CountryForm
            from config import Config
            form = CountryForm(data={})
            all_names = getattr(Config, 'ALL_LANGUAGES_DISPLAY_NAMES', {}) or {}
            if all_names:
                assert len(form.preferred_language.choices) > 0

    def test_english_first_in_choices(self, app):
        with app.app_context():
            from app.forms.system.country_forms import CountryForm
            from config import Config
            all_names = getattr(Config, 'ALL_LANGUAGES_DISPLAY_NAMES', {}) or {}
            if 'en' in all_names:
                form = CountryForm(data={})
                assert form.preferred_language.choices[0][0] == 'en'

    def test_original_country_id_extracted(self, app):
        with app.app_context():
            from app.forms.system.country_forms import CountryForm
            form = CountryForm(data={}, original_country_id=42)
            assert form.original_country_id == 42

    def test_original_country_id_defaults_none(self, app):
        with app.app_context():
            from app.forms.system.country_forms import CountryForm
            form = CountryForm(data={})
            assert form.original_country_id is None

    def test_multilingual_name_fields_added(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            from app.forms.system.country_forms import CountryForm
            form = CountryForm(data={})
            assert hasattr(CountryForm, 'name_fr')

    def test_multilingual_national_society_name_fields_added(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            from app.forms.system.country_forms import CountryForm
            form = CountryForm(data={})
            assert hasattr(CountryForm, 'national_society_name_fr')


class TestCountryFormValidation:
    def _patch_country(self, return_value=None):
        """Patch Country.query in both the form module and base module."""
        return patch('app.forms.base.Country') 

    def test_valid_data(self, app, db_session):
        with app.app_context():
            from app.forms.system.country_forms import CountryForm
            with patch('app.forms.base.Country') as mock_country:
                mock_country.query.filter_by.return_value.first.return_value = None
                mock_country.id = MagicMock()
                form = CountryForm(data={
                    'name': 'Testland',
                    'iso3': 'TLN',
                    'status': 'Active',
                })
                assert form.validate() is True

    def test_missing_name(self, app):
        with app.app_context():
            from app.forms.system.country_forms import CountryForm
            with patch('app.forms.base.Country') as mock_country:
                mock_country.query.filter_by.return_value.first.return_value = None
                mock_country.id = MagicMock()
                form = CountryForm(data={'iso3': 'XYZ'})
                assert form.validate() is False
                assert 'name' in form.errors

    def test_name_too_short(self, app):
        with app.app_context():
            from app.forms.system.country_forms import CountryForm
            with patch('app.forms.base.Country') as mock_country:
                mock_country.query.filter_by.return_value.first.return_value = None
                mock_country.id = MagicMock()
                form = CountryForm(data={'name': 'X', 'iso3': 'XYZ'})
                assert form.validate() is False
                assert 'name' in form.errors

    def test_missing_iso3(self, app):
        with app.app_context():
            from app.forms.system.country_forms import CountryForm
            with patch('app.forms.base.Country') as mock_country:
                mock_country.query.filter_by.return_value.first.return_value = None
                form = CountryForm(data={'name': 'Test Country'})
                assert form.validate() is False
                assert 'iso3' in form.errors

    def test_iso3_wrong_length(self, app):
        with app.app_context():
            from app.forms.system.country_forms import CountryForm
            with patch('app.forms.base.Country') as mock_country:
                mock_country.query.filter_by.return_value.first.return_value = None
                mock_country.id = MagicMock()
                form = CountryForm(data={'name': 'Test Country', 'iso3': 'XY'})
                assert form.validate() is False
                assert 'iso3' in form.errors

    def test_iso3_too_long(self, app):
        with app.app_context():
            from app.forms.system.country_forms import CountryForm
            with patch('app.forms.base.Country') as mock_country:
                mock_country.query.filter_by.return_value.first.return_value = None
                form = CountryForm(data={'name': 'Test Country', 'iso3': 'XYZA'})
                assert form.validate() is False
                assert 'iso3' in form.errors


class TestCountryFormValidateIso3:
    def test_unique_iso3_passes(self, app):
        with app.app_context():
            with patch('app.forms.system.country_forms.Country') as mock_country, \
                 patch('app.forms.base.Country') as mock_base_country:
                mock_country.query.filter_by.return_value.first.return_value = None
                mock_base_country.query.filter_by.return_value.first.return_value = None
                from app.forms.system.country_forms import CountryForm
                form = CountryForm(data={'name': 'France', 'iso3': 'FRA'})
                assert form.validate() is True

    def test_duplicate_iso3_fails(self, app):
        with app.app_context():
            existing = MagicMock()
            with patch('app.forms.system.country_forms.Country') as mock_country, \
                 patch('app.forms.base.Country') as mock_base_country:
                mock_country.query.filter_by.return_value.first.return_value = None
                mock_base_country.query.filter_by.return_value.first.return_value = existing
                from app.forms.system.country_forms import CountryForm
                form = CountryForm(data={'name': 'France', 'iso3': 'FRA'})
                assert form.validate() is False
                assert 'iso3' in form.errors

    def test_validate_iso3_with_original_id_excludes_self(self, app):
        with app.app_context():
            with patch('app.forms.system.country_forms.Country') as mock_country, \
                 patch('app.forms.base.Country') as mock_base_country:
                mock_country.query.filter_by.return_value.first.return_value = None
                mock_q = MagicMock()
                mock_q.filter.return_value.first.return_value = None
                mock_base_country.query.filter_by.return_value = mock_q
                mock_base_country.id = MagicMock()
                from app.forms.system.country_forms import CountryForm
                form = CountryForm(data={'name': 'France', 'iso3': 'FRA'}, original_country_id=5)
                result = form.validate()
                assert result is True

    def test_validate_iso3_directly(self, app):
        with app.app_context():
            with patch('app.forms.base.Country') as mock_country:
                mock_country.query.filter_by.return_value.first.return_value = MagicMock()
                from app.forms.system.country_forms import CountryForm
                form = CountryForm(data={'name': 'France', 'iso3': 'FRA'})
                field = MagicMock()
                field.data = 'FRA'
                from wtforms.validators import ValidationError
                with pytest.raises(ValidationError, match="already exists"):
                    form.validate_iso3(field)

    def test_validate_iso3_uppercase_normalized(self, app):
        with app.app_context():
            with patch('app.forms.base.Country') as mock_country:
                mock_country.query.filter_by.return_value.first.return_value = None
                from app.forms.system.country_forms import CountryForm
                form = CountryForm(data={'name': 'France', 'iso3': 'fra'})
                field = MagicMock()
                field.data = 'fra'
                form.validate_iso3(field)  # Should not raise (unique)
                mock_country.query.filter_by.assert_called_with(iso3='FRA')
