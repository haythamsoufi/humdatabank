"""Unit tests for app/forms/base.py — targets 100% coverage."""
import pytest
from unittest.mock import patch, MagicMock
from wtforms import StringField, TextAreaField
from wtforms.validators import Optional, ValidationError

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

class TestGetSupportedLanguageCodes:
    def test_returns_from_app_config(self, app):
        with app.app_context():
            app.config['SUPPORTED_LANGUAGES'] = ['en', 'fr', 'ar']
            from app.forms.base import _get_supported_language_codes
            codes = _get_supported_language_codes()
            assert 'en' in codes
            assert 'fr' in codes

    def test_falls_back_to_config_without_app_context(self):
        from app.forms.base import _get_supported_language_codes
        with patch('app.forms.base.Config') as mock_cfg:
            mock_cfg.LANGUAGES = ['en', 'es']
            codes = _get_supported_language_codes()
            assert 'en' in codes

    def test_empty_config_falls_back_to_en(self, app):
        """When SUPPORTED_LANGUAGES is empty/missing and Config.LANGUAGES is None, falls back to ['en']."""
        with app.app_context():
            # Set SUPPORTED_LANGUAGES to empty list so function falls through to Config fallback
            app.config['SUPPORTED_LANGUAGES'] = []
            from app.forms.base import _get_supported_language_codes
            with patch('app.forms.base.Config') as mock_cfg:
                mock_cfg.LANGUAGES = None
                codes = _get_supported_language_codes()
            assert codes == ['en']

    def test_strips_and_lowercases(self, app):
        with app.app_context():
            app.config['SUPPORTED_LANGUAGES'] = ['  EN ', ' FR ']
            from app.forms.base import _get_supported_language_codes
            codes = _get_supported_language_codes()
            assert 'en' in codes
            assert 'fr' in codes

    def test_filters_empty_strings(self, app):
        with app.app_context():
            app.config['SUPPORTED_LANGUAGES'] = ['en', '', '  ']
            from app.forms.base import _get_supported_language_codes
            codes = _get_supported_language_codes()
            assert '' not in codes
            assert '  ' not in codes

    def test_app_config_not_a_list_falls_back(self, app):
        with app.app_context():
            app.config['SUPPORTED_LANGUAGES'] = 'en'  # not a list
            from app.forms.base import _get_supported_language_codes
            with patch('app.forms.base.Config') as mock_cfg:
                mock_cfg.LANGUAGES = ['en', 'de']
                codes = _get_supported_language_codes()
                assert 'en' in codes


class TestGetTranslatableLanguageCodes:
    def test_excludes_en(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr', 'ar']
            from app.forms.base import _get_translatable_language_codes
            codes = _get_translatable_language_codes()
            assert 'en' not in codes
            assert 'fr' in codes

    def test_falls_back_when_no_app_context(self):
        from app.forms.base import _get_translatable_language_codes
        with patch('app.forms.base.Config') as mock_cfg:
            mock_cfg.LANGUAGES = ['en', 'fr']
            mock_cfg.LANGUAGE_DISPLAY_NAMES = {}
            mock_cfg.ALL_LANGUAGES_DISPLAY_NAMES = {}
            codes = _get_translatable_language_codes()
            assert 'en' not in codes

    def test_empty_list_when_only_en_supported(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = []
            from app.forms.base import _get_translatable_language_codes
            codes = _get_translatable_language_codes()
            assert codes == []

    def test_filters_en_from_translatable_list(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['en', 'fr', 'es']
            from app.forms.base import _get_translatable_language_codes
            codes = _get_translatable_language_codes()
            assert 'en' not in codes
            assert 'fr' in codes
            assert 'es' in codes


class TestGetLanguageDisplayName:
    def test_known_code_from_display_names(self):
        from app.forms.base import _get_language_display_name
        with patch('app.forms.base.Config') as mock_cfg:
            mock_cfg.LANGUAGE_DISPLAY_NAMES = {'fr': 'French'}
            mock_cfg.ALL_LANGUAGES_DISPLAY_NAMES = {}
            result = _get_language_display_name('fr')
            assert result == 'French'

    def test_fallback_to_all_languages(self):
        from app.forms.base import _get_language_display_name
        with patch('app.forms.base.Config') as mock_cfg:
            mock_cfg.LANGUAGE_DISPLAY_NAMES = {}
            mock_cfg.ALL_LANGUAGES_DISPLAY_NAMES = {'es': 'Spanish'}
            result = _get_language_display_name('es')
            assert result == 'Spanish'

    def test_fallback_to_uppercase_code(self):
        from app.forms.base import _get_language_display_name
        with patch('app.forms.base.Config') as mock_cfg:
            mock_cfg.LANGUAGE_DISPLAY_NAMES = {}
            mock_cfg.ALL_LANGUAGES_DISPLAY_NAMES = {}
            result = _get_language_display_name('zz')
            assert result == 'ZZ'

    def test_empty_code_returns_empty_string(self):
        from app.forms.base import _get_language_display_name
        assert _get_language_display_name('') == ''

    def test_none_code_returns_empty_string(self):
        from app.forms.base import _get_language_display_name
        assert _get_language_display_name(None) == ''

    def test_strips_and_lowercases_input(self):
        from app.forms.base import _get_language_display_name
        with patch('app.forms.base.Config') as mock_cfg:
            mock_cfg.LANGUAGE_DISPLAY_NAMES = {'fr': 'French'}
            mock_cfg.ALL_LANGUAGES_DISPLAY_NAMES = {}
            result = _get_language_display_name('  FR  ')
            assert result == 'French'


class TestIntOrNone:
    def test_valid_integer_string(self):
        from app.forms.base import int_or_none
        assert int_or_none('42') == 42

    def test_valid_integer(self):
        from app.forms.base import int_or_none
        assert int_or_none(10) == 10

    def test_none_returns_none(self):
        from app.forms.base import int_or_none
        assert int_or_none(None) is None

    def test_empty_string_returns_none(self):
        from app.forms.base import int_or_none
        assert int_or_none('') is None

    def test_whitespace_returns_none(self):
        from app.forms.base import int_or_none
        assert int_or_none('   ') is None

    def test_non_numeric_returns_none(self):
        from app.forms.base import int_or_none
        assert int_or_none('abc') is None

    def test_float_string_returns_none(self):
        from app.forms.base import int_or_none
        assert int_or_none('3.14') is None


class TestLookupListIdCoerce:
    def test_none_returns_none(self):
        from app.forms.base import lookup_list_id_coerce
        assert lookup_list_id_coerce(None) is None

    def test_empty_string_returns_none(self):
        from app.forms.base import lookup_list_id_coerce
        assert lookup_list_id_coerce('') is None

    def test_whitespace_returns_none(self):
        from app.forms.base import lookup_list_id_coerce
        assert lookup_list_id_coerce('   ') is None

    def test_numeric_string_returns_int(self):
        from app.forms.base import lookup_list_id_coerce
        assert lookup_list_id_coerce('7') == 7

    def test_integer_returns_int(self):
        from app.forms.base import lookup_list_id_coerce
        assert lookup_list_id_coerce(7) == 7

    def test_non_numeric_plugin_id_returns_string(self):
        from app.forms.base import lookup_list_id_coerce
        result = lookup_list_id_coerce('country_map')
        assert result == 'country_map'

    def test_plugin_id_strips_whitespace(self):
        from app.forms.base import lookup_list_id_coerce
        result = lookup_list_id_coerce('  national_society  ')
        assert result == 'national_society'


# ---------------------------------------------------------------------------
# Base form classes
# ---------------------------------------------------------------------------

class TestBaseForm:
    def test_instantiation(self, app):
        with app.app_context():
            from app.forms.base import BaseForm
            form = BaseForm(data={})
            assert form is not None

    def test_setup_multilingual_fields_called(self, app):
        with app.app_context():
            from app.forms.base import BaseForm
            form = BaseForm(data={})
            # _setup_multilingual_fields is a no-op but must not raise
            form._setup_multilingual_fields()


class TestMultilingualForm:
    def test_has_languages_attribute(self, app):
        with app.app_context():
            app.config['SUPPORTED_LANGUAGES'] = ['en', 'fr']
            from app.forms.base import MultilingualForm
            form = MultilingualForm(data={})
            assert isinstance(form.languages, list)
            assert 'en' in form.languages

    def test_has_language_display_names(self, app):
        with app.app_context():
            from app.forms.base import MultilingualForm
            form = MultilingualForm(data={})
            assert isinstance(form.language_display_names, dict)

    def test_create_language_fields_adds_fields(self, app):
        with app.app_context():
            app.config['SUPPORTED_LANGUAGES'] = ['en', 'fr']
            from app.forms.base import MultilingualForm
            form = MultilingualForm(data={})
            form._create_language_fields('test_field', StringField)
            # Check that language-specific fields are created
            for lang in form.languages:
                assert hasattr(form, f'test_field_{lang}')

    def test_create_language_fields_with_custom_validators(self, app):
        with app.app_context():
            app.config['SUPPORTED_LANGUAGES'] = ['en']
            from app.forms.base import MultilingualForm
            form = MultilingualForm(data={})
            form._create_language_fields('myfield', StringField, validators=[Optional()])
            assert hasattr(form, 'myfield_en')

    def test_create_language_fields_does_not_overwrite_existing(self, app):
        with app.app_context():
            app.config['SUPPORTED_LANGUAGES'] = ['en']
            from app.forms.base import MultilingualForm
            form = MultilingualForm(data={})
            form.existing_en = 'already_here'
            form._create_language_fields('existing', StringField)
            # Should not overwrite
            assert form.existing_en == 'already_here'


class TestFileUploadForm:
    def test_document_validators_exist(self):
        from app.forms.base import FileUploadForm
        assert len(FileUploadForm.document_validators) > 0

    def test_image_validators_exist(self):
        from app.forms.base import FileUploadForm
        assert len(FileUploadForm.image_validators) > 0

    def test_instantiation(self, app):
        with app.app_context():
            from app.forms.base import FileUploadForm
            form = FileUploadForm(data={})
            assert form is not None


class TestCommonFields:
    def test_layout_column_width_choices_exist(self):
        from app.forms.base import CommonFields
        assert len(CommonFields.LAYOUT_COLUMN_WIDTH_CHOICES) > 0

    def test_data_availability_fields_exist(self):
        from app.forms.base import CommonFields
        assert 'allow_data_not_available' in CommonFields.DATA_AVAILABILITY_FIELDS
        assert 'allow_not_applicable' in CommonFields.DATA_AVAILABILITY_FIELDS
        assert 'allow_disability_questions' in CommonFields.DATA_AVAILABILITY_FIELDS
        assert 'indirect_reach' in CommonFields.DATA_AVAILABILITY_FIELDS

    def test_skip_logic_fields_exist(self):
        from app.forms.base import CommonFields
        assert 'relevance_condition' in CommonFields.SKIP_LOGIC_FIELDS
        assert 'validation_condition' in CommonFields.SKIP_LOGIC_FIELDS
        assert 'validation_message' in CommonFields.SKIP_LOGIC_FIELDS

    def test_layout_fields_exist(self):
        from app.forms.base import CommonFields
        assert 'layout_column_width' in CommonFields.LAYOUT_FIELDS
        assert 'layout_break_after' in CommonFields.LAYOUT_FIELDS


# ---------------------------------------------------------------------------
# CommonValidators
# ---------------------------------------------------------------------------

class TestCommonValidatorsValidateUniqueName:
    def test_no_existing_record_passes(self, app):
        with app.app_context():
            from app.forms.base import CommonValidators
            mock_model = MagicMock()
            mock_model.__name__ = 'TestModel'
            mock_model.query.filter_by.return_value.first.return_value = None
            field = MagicMock()
            field.data = 'Unique Name'
            CommonValidators.validate_unique_name(mock_model, field)

    def test_existing_record_raises(self, app):
        with app.app_context():
            from app.forms.base import CommonValidators
            mock_model = MagicMock()
            mock_model.__name__ = 'Sector'
            mock_model.query.filter_by.return_value.first.return_value = MagicMock()
            field = MagicMock()
            field.data = 'Duplicate'
            with pytest.raises(ValidationError):
                CommonValidators.validate_unique_name(mock_model, field)

    def test_exclude_id_skips_self(self, app):
        with app.app_context():
            from app.forms.base import CommonValidators
            mock_model = MagicMock()
            mock_model.__name__ = 'Sector'
            mock_model.id = MagicMock()
            mock_q = MagicMock()
            mock_q.filter.return_value.first.return_value = None
            mock_model.query.filter_by.return_value = mock_q
            field = MagicMock()
            field.data = 'Existing Name'
            CommonValidators.validate_unique_name(mock_model, field, exclude_id=1)


class TestCommonValidatorsValidateIso3Unique:
    def test_unique_iso3_passes(self, app):
        with app.app_context():
            from app.forms.base import CommonValidators
            with patch('app.forms.base.Country') as mock_country:
                mock_country.query.filter_by.return_value.first.return_value = None
                field = MagicMock()
                field.data = 'XYZ'
                CommonValidators.validate_iso3_unique(field)

    def test_duplicate_iso3_raises(self, app):
        with app.app_context():
            from app.forms.base import CommonValidators
            with patch('app.forms.base.Country') as mock_country:
                mock_country.query.filter_by.return_value.first.return_value = MagicMock()
                field = MagicMock()
                field.data = 'XYZ'
                with pytest.raises(ValidationError):
                    CommonValidators.validate_iso3_unique(field)

    def test_exclude_id_skips_self(self, app):
        with app.app_context():
            from app.forms.base import CommonValidators
            with patch('app.forms.base.Country') as mock_country:
                mock_q = MagicMock()
                mock_q.filter.return_value.first.return_value = None
                mock_country.query.filter_by.return_value = mock_q
                mock_country.id = MagicMock()
                field = MagicMock()
                field.data = 'XYZ'
                CommonValidators.validate_iso3_unique(field, exclude_id=5)


class TestCommonValidatorsValidateAgeGroupsConfig:
    def test_passes_when_no_age_disaggregation(self):
        from app.forms.base import CommonValidators
        field = MagicMock()
        field.data = ''
        CommonValidators.validate_age_groups_config(field, ['total'], 'people', 'Number')

    def test_raises_when_age_selected_unsupported_unit(self):
        from app.forms.base import CommonValidators
        with patch('app.utils.indicator_utils.supports_disaggregation', return_value=False):
            field = MagicMock()
            field.data = ''
            with pytest.raises(ValidationError, match="Age disaggregation is only allowed"):
                CommonValidators.validate_age_groups_config(field, ['age'], 'percentage', 'Number')

    def test_valid_age_groups_format(self):
        from app.forms.base import CommonValidators
        with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
            field = MagicMock()
            field.data = '0-4,5-9,10-14'
            CommonValidators.validate_age_groups_config(field, ['age'], 'people', 'Number')

    def test_empty_parts_in_age_groups_raises(self):
        from app.forms.base import CommonValidators
        with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
            field = MagicMock()
            field.data = '0-4,,10-14'
            with pytest.raises(ValidationError, match="must not contain empty parts"):
                CommonValidators.validate_age_groups_config(field, ['age'], 'people', 'Number')

    def test_invalid_characters_in_age_group_raises(self):
        from app.forms.base import CommonValidators
        with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
            field = MagicMock()
            field.data = '0-4,5@9'
            with pytest.raises(ValidationError, match="invalid characters"):
                CommonValidators.validate_age_groups_config(field, ['age'], 'people', 'Number')

    def test_sex_age_in_options_triggers_age_check(self):
        from app.forms.base import CommonValidators
        with patch('app.utils.indicator_utils.supports_disaggregation', return_value=False):
            field = MagicMock()
            field.data = ''
            with pytest.raises(ValidationError):
                CommonValidators.validate_age_groups_config(field, ['sex_age'], 'text', 'Text')

    def test_no_unit_with_age_raises(self):
        from app.forms.base import CommonValidators
        with patch('app.utils.indicator_utils.supports_disaggregation', return_value=False):
            field = MagicMock()
            field.data = ''
            with pytest.raises(ValidationError):
                CommonValidators.validate_age_groups_config(field, ['age'], None, None)


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------

class TestMultilingualFieldsMixin:
    def test_rebuild_unbound_fields_sets_list(self, app):
        with app.app_context():
            from app.forms.base import MultilingualFieldsMixin, BaseForm

            class TestForm(BaseForm, MultilingualFieldsMixin):
                pass

            form = TestForm(data={})
            MultilingualFieldsMixin._rebuild_unbound_fields(TestForm)
            assert isinstance(TestForm._unbound_fields, list)

    def test_rebuild_unbound_fields_handles_exception(self, app):
        with app.app_context():
            from app.forms.base import MultilingualFieldsMixin, BaseForm

            class BadForm(BaseForm, MultilingualFieldsMixin):
                pass

            # Force an exception path by making dir() return non-iterable somehow
            with patch('builtins.dir', side_effect=RuntimeError("bad")):
                MultilingualFieldsMixin._rebuild_unbound_fields(BadForm)
            assert BadForm._unbound_fields == []

    def test_add_multilingual_name_fields_string(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            from app.forms.base import MultilingualFieldsMixin, BaseForm

            class MyForm(BaseForm, MultilingualFieldsMixin):
                name = StringField("Name")

            form = MyForm(data={})
            form.add_multilingual_name_fields("name", max_length=100)
            assert hasattr(MyForm, 'name_fr')

    def test_add_multilingual_name_fields_textarea(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            from app.forms.base import MultilingualFieldsMixin, BaseForm

            class MyTextareaForm(BaseForm, MultilingualFieldsMixin):
                description = TextAreaField("Desc")

            form = MyTextareaForm(data={})
            form.add_multilingual_name_fields("description", max_length=500, use_textarea=True, textarea_rows=4)
            assert hasattr(MyTextareaForm, 'description_fr')

    def test_add_multilingual_name_fields_does_not_overwrite(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            from app.forms.base import MultilingualFieldsMixin, BaseForm

            class ExistingForm(BaseForm, MultilingualFieldsMixin):
                name = StringField("Name")
                name_fr = StringField("Name FR already here")

            form = ExistingForm(data={})
            original = ExistingForm.name_fr
            form.add_multilingual_name_fields("name", max_length=100)
            # Should not have been replaced
            assert ExistingForm.name_fr is original


class TestLayoutFieldsMixin:
    def test_add_layout_fields(self, app):
        with app.app_context():
            from app.forms.base import LayoutFieldsMixin, BaseForm

            class LayoutForm(BaseForm, LayoutFieldsMixin):
                pass

            form = LayoutForm(data={})
            form.add_layout_fields()
            assert hasattr(form, 'layout_column_width') or hasattr(LayoutForm, 'layout_column_width')

    def test_add_layout_fields_idempotent(self, app):
        with app.app_context():
            from app.forms.base import LayoutFieldsMixin, BaseForm

            class LayoutForm2(BaseForm, LayoutFieldsMixin):
                pass

            form = LayoutForm2(data={})
            form.add_layout_fields()
            form.add_layout_fields()  # second call should not raise


class TestDataAvailabilityMixin:
    def test_add_data_availability_fields(self, app):
        with app.app_context():
            from app.forms.base import DataAvailabilityMixin, BaseForm

            class DAForm(BaseForm, DataAvailabilityMixin):
                pass

            form = DAForm(data={})
            form.add_data_availability_fields()
            assert hasattr(form, 'allow_data_not_available') or hasattr(DAForm, 'allow_data_not_available')

    def test_add_data_availability_fields_idempotent(self, app):
        with app.app_context():
            from app.forms.base import DataAvailabilityMixin, BaseForm

            class DAForm2(BaseForm, DataAvailabilityMixin):
                pass

            form = DAForm2(data={})
            form.add_data_availability_fields()
            form.add_data_availability_fields()


class TestSkipLogicMixin:
    def test_add_skip_logic_fields(self, app):
        with app.app_context():
            from app.forms.base import SkipLogicMixin, BaseForm

            class SLForm(BaseForm, SkipLogicMixin):
                pass

            form = SLForm(data={})
            form.add_skip_logic_fields()
            assert hasattr(form, 'relevance_condition') or hasattr(SLForm, 'relevance_condition')

    def test_add_skip_logic_fields_idempotent(self, app):
        with app.app_context():
            from app.forms.base import SkipLogicMixin, BaseForm

            class SLForm2(BaseForm, SkipLogicMixin):
                pass

            form = SLForm2(data={})
            form.add_skip_logic_fields()
            form.add_skip_logic_fields()
