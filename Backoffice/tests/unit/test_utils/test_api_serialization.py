"""
Unit tests for api_serialization utilities.

Covers: format_country_info, format_country_info_minimal, format_form_item_info,
format_indicator_details, serialize_assigned_data_item, serialize_public_data_item,
format_dim_template, format_dim_period, format_dim_submission_assigned,
format_dim_submission_public, format_fact_form_value_row, format_bridge_disagg_rows,
build_bridge_disagg_from_flat_rows, build_star_schema_tables.
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

from app.utils.api_serialization import (
    format_country_info,
    format_country_info_minimal,
    format_form_item_info,
    format_indicator_details,
    serialize_assigned_data_item,
    serialize_public_data_item,
    format_dim_template,
    format_dim_period,
    format_dim_submission_assigned,
    format_dim_submission_public,
    format_fact_form_value_row,
    format_bridge_disagg_rows,
    build_bridge_disagg_from_flat_rows,
    build_star_schema_tables,
    _wrap_disagg_dict,
    _resolve_matrix_cell,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_country(name='Test Country', iso3='TST', iso2='TS', region='Europe',
                  partof=None, status='active', preferred_language='en',
                  currency_code='USD', name_translations=None):
    c = MagicMock()
    c.id = 1
    c.name = name
    c.iso3 = iso3
    c.iso2 = iso2
    c.region = region
    c.partof = partof
    c.status = status
    c.preferred_language = preferred_language
    c.currency_code = currency_code
    c.name_translations = name_translations or {}
    c.primary_national_society = None
    return c


def _make_form_item(is_indicator=False, is_question=False, is_document_field=False):
    fi = MagicMock()
    fi.id = 10
    fi.item_type = 'indicator' if is_indicator else ('question' if is_question else 'document')
    fi.label = 'Test Item'
    fi.order = 1
    fi.display_order = 1
    fi.is_required = True
    fi.layout_column_width = 6
    fi.layout_break_after = False
    fi.is_indicator = is_indicator
    fi.is_question = is_question
    fi.is_document_field = is_document_field
    fi.indicator_bank = None
    fi.unit = None
    fi.is_sub_item = False
    fi.allowed_disaggregation_options = []
    fi.validation_condition = None
    fi.validation_message = None
    fi.allow_data_not_available = False
    fi.allow_not_applicable = False
    fi.allow_disability_questions = False
    fi.type = 'text'
    fi.definition = 'A test definition'
    fi.options = []
    fi.lookup_list_id = None
    fi.list_display_column = None
    fi.list_filters_json = None
    fi.description = 'A document description'
    return fi


# ---------------------------------------------------------------------------
# format_country_info
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormatCountryInfo:
    def test_none_returns_none(self, app):
        with app.test_request_context():
            result = format_country_info(None)
            assert result is None

    def test_basic_country_fields(self, app):
        with app.test_request_context():
            country = _make_country()
            result = format_country_info(country)
            assert result['id'] == 1
            assert result['name'] == 'Test Country'
            assert result['iso3'] == 'TST'
            assert result['iso2'] == 'TS'
            assert result['region'] == 'Europe'

    def test_country_without_national_society(self, app):
        with app.test_request_context():
            country = _make_country()
            country.primary_national_society = None
            result = format_country_info(country)
            assert result['national_society_name'] is None

    def test_country_with_national_society(self, app):
        with app.test_request_context():
            country = _make_country()
            ns = MagicMock()
            ns.name = 'Test NS'
            ns.name_translations = {}
            country.primary_national_society = ns
            result = format_country_info(country)
            assert result['national_society_name'] == 'Test NS'

    def test_primary_ns_exception_handled(self, app):
        with app.test_request_context():
            country = _make_country()
            type(country).primary_national_society = PropertyMock(
                side_effect=Exception('DB error')
            )
            result = format_country_info(country)
            # Should not raise; ns defaults to None
            assert result['national_society_name'] is None

    def test_name_translations_included_for_configured_languages(self, app):
        with app.test_request_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr', 'ar']
            country = _make_country(name_translations={'fr': 'Pays Test', 'ar': 'دولة'})
            result = format_country_info(country)
            assert result['multilingual_names']['fr'] == 'Pays Test'
            assert result['multilingual_names']['ar'] == 'دولة'

    def test_multilingual_names_uses_supported_languages_fallback(self, app):
        with app.test_request_context():
            app.config['TRANSLATABLE_LANGUAGES'] = None
            app.config['SUPPORTED_LANGUAGES'] = ['es']
            country = _make_country(name_translations={'es': 'País de prueba'})
            result = format_country_info(country)
            assert 'es' in result['multilingual_names']

    def test_name_translations_not_dict_uses_empty(self, app):
        with app.test_request_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            country = _make_country()
            country.name_translations = 'not-a-dict'
            result = format_country_info(country)
            assert result['multilingual_names']['fr'] is None

    def test_english_excluded_from_multilingual_names(self, app):
        with app.test_request_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['en', 'fr']
            country = _make_country(name_translations={'en': 'English', 'fr': 'Français'})
            result = format_country_info(country)
            assert 'en' not in result['multilingual_names']
            assert 'fr' in result['multilingual_names']


# ---------------------------------------------------------------------------
# format_country_info_minimal
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormatCountryInfoMinimal:
    def test_none_returns_none(self):
        assert format_country_info_minimal(None) is None

    def test_returns_only_minimal_fields(self):
        country = _make_country()
        result = format_country_info_minimal(country)
        assert result == {
            'id': 1,
            'name': 'Test Country',
            'iso3': 'TST',
            'iso2': 'TS',
            'region': 'Europe',
        }

    def test_no_national_society_or_translations_in_result(self):
        country = _make_country()
        result = format_country_info_minimal(country)
        assert 'national_society_name' not in result
        assert 'multilingual_names' not in result


# ---------------------------------------------------------------------------
# format_form_item_info
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormatFormItemInfo:
    def test_none_returns_none(self):
        result = format_form_item_info(None)
        assert result is None

    def test_basic_form_item_no_section_template(self):
        fi = _make_form_item()
        result = format_form_item_info(fi)
        assert result['id'] == 10
        assert result['label'] == 'Test Item'
        assert result['section'] is None
        assert result['template'] is None
        assert result['assignment'] is None

    def test_with_section(self):
        fi = _make_form_item()
        section = MagicMock()
        section.id = 5; section.name = 'Section A'; section.order = 1; section.section_type = 'standard'
        result = format_form_item_info(fi, section=section)
        assert result['section']['id'] == 5
        assert result['section']['name'] == 'Section A'

    def test_with_template(self):
        fi = _make_form_item()
        template = MagicMock()
        template.id = 99; template.name = 'My Template'; template.description = 'Desc'
        result = format_form_item_info(fi, template=template)
        assert result['template']['id'] == 99
        assert result['template']['name'] == 'My Template'

    def test_with_assignment(self):
        fi = _make_form_item()
        assignment = MagicMock()
        assignment.id = 77
        assignment.period_name = '2024'
        assignment.assigned_at = datetime(2024, 1, 1)
        result = format_form_item_info(fi, assignment=assignment)
        assert result['assignment']['id'] == 77
        assert result['assignment']['period_name'] == '2024'
        assert result['assignment']['assigned_at'] == '2024-01-01T00:00:00'

    def test_with_assignment_no_assigned_at(self):
        fi = _make_form_item()
        assignment = MagicMock()
        assignment.id = 77
        assignment.period_name = '2024'
        assignment.assigned_at = None
        result = format_form_item_info(fi, assignment=assignment)
        assert result['assignment']['assigned_at'] is None

    def test_with_public_assignment(self):
        fi = _make_form_item()
        pub_assignment = MagicMock()
        pub_assignment.id = 55
        pub_assignment.period_name = 'Q1'
        pub_assignment.created_at = datetime(2024, 3, 1)
        result = format_form_item_info(fi, public_assignment=pub_assignment)
        assert result['assignment']['id'] == 55
        assert result['assignment']['created_at'] == '2024-03-01T00:00:00'

    def test_with_public_assignment_no_created_at(self):
        fi = _make_form_item()
        pub_assignment = MagicMock()
        pub_assignment.id = 55
        pub_assignment.period_name = 'Q1'
        pub_assignment.created_at = None
        result = format_form_item_info(fi, public_assignment=pub_assignment)
        assert result['assignment']['created_at'] is None

    def test_indicator_type_adds_bank_details(self):
        fi = _make_form_item(is_indicator=True)
        bank = MagicMock()
        bank.id = 1; bank.type = 'numeric'; bank.unit = 'people'
        bank.definition = 'def'; bank.sector = 'Health'; bank.sub_sector = 'Nutrition'
        bank.emergency = False; bank.related_programs_list = []; bank.archived = False
        fi.indicator_bank = bank

        with patch('app.utils.api_serialization.get_localized_indicator_name', return_value='Bank Name'):
            result = format_form_item_info(fi)
        assert 'bank_details' in result
        assert result['bank_details']['type'] == 'numeric'

    def test_indicator_type_without_bank(self):
        fi = _make_form_item(is_indicator=True)
        fi.indicator_bank = None
        with patch('app.utils.api_serialization.get_localized_indicator_name', return_value=None):
            result = format_form_item_info(fi)
        assert result['bank_details'] is None

    def test_question_type_adds_question_fields(self):
        fi = _make_form_item(is_question=True)
        result = format_form_item_info(fi)
        assert 'question_type' in result
        assert result['question_type'] == fi.type
        assert 'definition' in result
        assert 'options' in result

    def test_document_field_type_adds_description(self):
        fi = _make_form_item(is_document_field=True)
        result = format_form_item_info(fi)
        assert 'description' in result
        assert result['description'] == 'A document description'


# ---------------------------------------------------------------------------
# format_indicator_details
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormatIndicatorDetails:
    def test_none_form_item_returns_none(self):
        assert format_indicator_details(None) is None

    def test_non_indicator_returns_none(self):
        fi = _make_form_item(is_indicator=False)
        fi.is_indicator = False
        assert format_indicator_details(fi) is None

    def test_indicator_with_bank(self):
        fi = _make_form_item(is_indicator=True)
        bank = MagicMock()
        bank.id = 5; bank.type = 'percentage'; bank.unit = '%'
        bank.definition = 'A %'; bank.sector = 'Health'
        bank.sub_sector = 'WASH'; bank.emergency = True
        bank.related_programs_list = ['PROG1']; bank.archived = False
        fi.indicator_bank = bank

        with patch('app.utils.api_serialization.get_localized_indicator_name', return_value='Indicator Name'):
            result = format_indicator_details(fi)
        assert result is not None
        assert result['id'] == 10
        assert result['label'] == 'Test Item'
        assert result['bank_details']['type'] == 'percentage'
        assert result['bank_details']['sector'] == 'Health'

    def test_indicator_without_bank(self):
        fi = _make_form_item(is_indicator=True)
        fi.indicator_bank = None
        with patch('app.utils.api_serialization.get_localized_indicator_name', return_value=None):
            result = format_indicator_details(fi)
        assert result['bank_details']['id'] is None
        assert result['bank_details']['name'] is None


# ---------------------------------------------------------------------------
# serialize_assigned_data_item
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSerializeAssignedDataItem:
    def _make_item(self, value=100, data_not_avail=None, not_applic=None):
        item = MagicMock()
        item.id = 1
        item.form_item_id = 10
        item.data_not_available = data_not_avail
        item.not_applicable = not_applic
        item.value = value
        item.submitted_at = datetime(2024, 3, 15)
        item.form_item = None
        item.disagg_data = None
        item.imputed_value = None
        item.prefilled_value = None
        item.prefilled_disagg_data = None
        item.imputed_disagg_data = None

        status = MagicMock()
        status.id = 50
        af = MagicMock()
        af.period_name = '2024'
        af.template_id = 5
        af.template = MagicMock()
        af.template.name = 'Main Template'
        status.assigned_form = af
        status.country = None
        item.assignment_entity_status = status
        return item

    def test_basic_serialization(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                result = serialize_assigned_data_item(item)
        assert result['id'] == 1
        assert result['submission_type'] == 'assigned'
        assert result['value'] == 100
        assert result['data_status'] == 'available'

    def test_data_not_available_sets_status(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item(data_not_avail=True)
                result = serialize_assigned_data_item(item)
        assert result['data_status'] == 'data_not_available'
        assert result['value'] is None

    def test_not_applicable_sets_status(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item(not_applic=True)
                result = serialize_assigned_data_item(item)
        assert result['data_status'] == 'not_applicable'
        assert result['value'] is None

    def test_submitted_at_isoformat(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                result = serialize_assigned_data_item(item)
        assert result['submitted_at'] == '2024-03-15T00:00:00'

    def test_submitted_at_none(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                item.submitted_at = None
                result = serialize_assigned_data_item(item)
        assert result['submitted_at'] is None

    def test_minimal_country_info_used_when_flag_set(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info_minimal', return_value={'id': 1}) as mock_min, \
                 patch('app.utils.api_serialization.format_country_info', return_value={'id': 1, 'name': 'full'}):
                item = self._make_item()
                result = serialize_assigned_data_item(item, minimal_country_info=True)
                mock_min.assert_called_once()

    def test_include_full_info_adds_form_item_info(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None), \
                 patch('app.utils.api_serialization.format_form_item_info', return_value={'field': 'data'}):
                item = self._make_item()
                form_item = MagicMock()
                form_item.form_section = MagicMock()
                item.form_item = form_item
                result = serialize_assigned_data_item(item, include_full_info=True)
        assert result['form_item_info'] == {'field': 'data'}

    def test_standard_disagg_sex(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                item.disagg_data = {'mode': 'sex', 'values': {'male': 10, 'female': 20}}
                result = serialize_assigned_data_item(item)
        assert result['disaggregation_data'] is not None
        assert result['disaggregation_data']['mode'] == 'sex'
        assert result['disaggregation_data']['values'] == {'male': 10, 'female': 20}

    def test_none_disagg_data_returns_none(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                item.disagg_data = None
                result = serialize_assigned_data_item(item)
        assert result['disaggregation_data'] is None

    def test_non_dict_disagg_returns_none(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                item.disagg_data = 'not-a-dict'
                result = serialize_assigned_data_item(item)
        assert result['disaggregation_data'] is None

    def test_bad_values_type_uses_empty_dict(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                item.disagg_data = {'mode': 'sex', 'values': 'bad-values'}
                result = serialize_assigned_data_item(item)
        assert result['disaggregation_data']['values'] == {}

    def test_matrix_flat_format_normalised(self, app):
        """Flat matrix disagg_data (no 'values' key) is wrapped as mode='matrix'."""
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                item.disagg_data = {'_table': 'ns', '10_SP2': 4107000, '11_SP2': 3000000}
                result = serialize_assigned_data_item(item)
        d = result['disaggregation_data']
        assert d is not None
        assert d['mode'] == 'matrix'
        assert d['values'] == {'10_SP2': 4107000, '11_SP2': 3000000}
        assert '_table' not in d['values']

    def test_disability_merged_disagg(self, app):
        """Disability questions merged into values dict are preserved."""
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                item.disagg_data = {
                    'mode': 'total',
                    'values': {'total': 100, 'disability': {'disaggregated_by_disability': True}},
                }
                result = serialize_assigned_data_item(item)
        d = result['disaggregation_data']
        assert d['mode'] == 'total'
        assert d['values']['total'] == 100
        assert d['values']['disability'] == {'disaggregated_by_disability': True}

    def test_no_assigned_form_template_name_is_none(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                item.assignment_entity_status.assigned_form = None
                result = serialize_assigned_data_item(item)
        assert result['template_name'] is None

    def test_imputed_value_included(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                item.imputed_value = 99
                result = serialize_assigned_data_item(item)
        assert result['imputed_value'] == 99


# ---------------------------------------------------------------------------
# serialize_public_data_item
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSerializePublicDataItem:
    def _make_item(self, value='answer', data_not_avail=None, not_applic=None):
        item = MagicMock()
        item.id = 2
        item.form_item_id = 20
        item.data_not_available = data_not_avail
        item.not_applicable = not_applic
        item.value = value
        item.form_item = None
        item.disagg_data = None
        item.imputed_value = None
        item.prefilled_value = None
        item.prefilled_disagg_data = None
        item.imputed_disagg_data = None

        submission = MagicMock()
        submission.id = 200
        submission.submitted_at = datetime(2024, 6, 1)
        submission.country = None

        assignment = MagicMock()
        assignment.id = 50
        assignment.period_name = 'Q2 2024'
        assignment.template_id = 5
        assignment.template = MagicMock()
        assignment.template.name = 'Public Template'
        submission.assigned_form = assignment
        item.public_submission = submission
        return item

    def test_basic_serialization(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                result = serialize_public_data_item(item)
        assert result['submission_type'] == 'public'
        assert result['id'] == 2
        assert result['data_status'] == 'available'

    def test_data_not_available_status(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item(data_not_avail=True)
                result = serialize_public_data_item(item)
        assert result['data_status'] == 'data_not_available'

    def test_not_applicable_status(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item(not_applic=True)
                result = serialize_public_data_item(item)
        assert result['data_status'] == 'not_applicable'

    def test_submitted_at_from_submission(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                result = serialize_public_data_item(item)
        assert result['submitted_at'] == '2024-06-01T00:00:00'

    def test_submission_none(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                item.public_submission = None
                result = serialize_public_data_item(item)
        assert result['submission_id'] is None
        assert result['submitted_at'] is None

    def test_template_name_from_assignment(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                result = serialize_public_data_item(item)
        assert result['template_name'] == 'Public Template'

    def test_include_disagg(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None):
                item = self._make_item()
                item.disagg_data = {'mode': 'age', 'values': {'0-18': 3}}
                result = serialize_public_data_item(item)
        assert result['disaggregation_data']['mode'] == 'age'

    def test_minimal_country_info(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info_minimal', return_value={'id': 2}) as mock_min, \
                 patch('app.utils.api_serialization.format_country_info', return_value={'id': 2, 'name': 'full'}):
                item = self._make_item()
                serialize_public_data_item(item, minimal_country_info=True)
                mock_min.assert_called_once()

    def test_include_full_info(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None), \
                 patch('app.utils.api_serialization.format_form_item_info', return_value={'fi': 'data'}):
                item = self._make_item()
                fi = MagicMock()
                fi.form_section = MagicMock()
                item.form_item = fi
                result = serialize_public_data_item(item, include_full_info=True)
        assert result['form_item_info'] == {'fi': 'data'}


# ---------------------------------------------------------------------------
# format_dim_template
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormatDimTemplate:
    def test_none_returns_none(self):
        assert format_dim_template(None) is None

    def test_with_published_version(self):
        template = MagicMock()
        template.id = 1; template.name = 'T1'
        template.published_version = MagicMock()
        template.published_version.description = 'Published desc'
        result = format_dim_template(template)
        assert result['id'] == 1
        assert result['name'] == 'T1'
        assert result['description'] == 'Published desc'

    def test_without_published_version_uses_first_version(self):
        template = MagicMock()
        template.id = 2; template.name = 'T2'
        template.published_version = None
        first_ver = MagicMock()
        first_ver.description = 'First version desc'
        template.versions.order_by.return_value.first.return_value = first_ver
        result = format_dim_template(template)
        assert result['description'] == 'First version desc'

    def test_without_published_version_and_no_versions(self):
        template = MagicMock()
        template.id = 3; template.name = 'T3'
        template.published_version = None
        template.versions.order_by.return_value.first.return_value = None
        result = format_dim_template(template)
        assert result['description'] is None


# ---------------------------------------------------------------------------
# format_dim_period
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormatDimPeriod:
    def test_none_returns_none(self):
        assert format_dim_period(None) is None

    def test_with_period_start_and_end(self):
        af = MagicMock()
        af.period_name = '2024'
        af.period_id = 10
        af.period_start = datetime(2024, 1, 1)
        af.period_end = datetime(2024, 12, 31)
        af.template_id = 5
        result = format_dim_period(af)
        assert result['period_name'] == '2024'
        assert result['period_start'] == '2024-01-01T00:00:00'
        assert result['period_end'] == '2024-12-31T00:00:00'
        assert result['template_id'] == 5

    def test_without_period_start_and_end(self):
        af = MagicMock()
        af.period_name = 'Q1'
        af.period_id = None
        af.period_start = None
        af.period_end = None
        af.template_id = 1
        result = format_dim_period(af)
        assert result['period_start'] is None
        assert result['period_end'] is None


# ---------------------------------------------------------------------------
# format_dim_submission_assigned
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormatDimSubmissionAssigned:
    def test_none_returns_none(self):
        assert format_dim_submission_assigned(None) is None

    def test_with_enum_status(self):
        aes = MagicMock()
        aes.id = 1
        status_enum = MagicMock()
        status_enum.value = 'submitted'
        aes.status = status_enum
        aes.entity_type = 'national_society'
        aes.entity_id = 5
        aes.submitted_at = datetime(2024, 1, 10)
        aes.due_date = datetime(2024, 2, 1)
        aes.assigned_form_id = 99
        result = format_dim_submission_assigned(aes)
        assert result['id'] == 1
        assert result['type'] == 'assigned'
        assert result['status'] == 'submitted'
        assert result['submitted_at'] == '2024-01-10T00:00:00'

    def test_with_string_status(self):
        aes = MagicMock()
        aes.id = 2
        aes.status = 'pending'  # plain string, no .value
        aes.entity_type = 'country'
        aes.entity_id = 1
        aes.submitted_at = None
        aes.due_date = None
        aes.assigned_form_id = 10
        result = format_dim_submission_assigned(aes)
        assert result['status'] == 'pending'

    def test_no_submitted_at(self):
        aes = MagicMock()
        aes.id = 3
        aes.status = 'draft'
        aes.submitted_at = None
        aes.due_date = None
        aes.entity_type = 'branch'
        aes.entity_id = 7
        aes.assigned_form_id = 5
        result = format_dim_submission_assigned(aes)
        assert result['submitted_at'] is None
        assert result['due_date'] is None


# ---------------------------------------------------------------------------
# format_dim_submission_public
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormatDimSubmissionPublic:
    def test_none_returns_none(self):
        assert format_dim_submission_public(None) is None

    def test_with_submitted_at(self):
        ps = MagicMock()
        ps.id = 10
        ps.status = MagicMock(); ps.status.value = 'complete'
        ps.country_id = 3
        ps.submitted_at = datetime(2024, 5, 20)
        ps.submitter_name = 'John'
        ps.assigned_form_id = 7
        result = format_dim_submission_public(ps)
        assert result['id'] == 10
        assert result['type'] == 'public'
        assert result['status'] == 'complete'
        assert result['submitted_at'] == '2024-05-20T00:00:00'
        assert result['submitter_name'] == 'John'

    def test_without_submitted_at(self):
        ps = MagicMock()
        ps.id = 11
        ps.status = 'pending'
        ps.country_id = 1
        ps.submitted_at = None
        ps.submitter_name = None
        ps.assigned_form_id = 8
        result = format_dim_submission_public(ps)
        assert result['submitted_at'] is None


# ---------------------------------------------------------------------------
# format_fact_form_value_row
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormatFactFormValueRow:
    def test_none_returns_none(self):
        assert format_fact_form_value_row(None) is None

    def test_all_fields_mapped(self):
        row = {
            'id': 1, 'form_item_id': 10, 'country_id': 3, 'template_id': 5,
            'period_name': '2024', 'submission_id': 100, 'submission_type': 'assigned',
            'value': 42, 'num_value': 42.0, 'data_status': 'available',
            'submitted_at': '2024-01-01', 'is_missing': False
        }
        result = format_fact_form_value_row(row)
        assert result['id'] == 1
        assert result['form_item_id'] == 10
        assert result['submission_type'] == 'assigned'
        assert result['is_missing'] is False

    def test_missing_key_defaults_to_none(self):
        row = {'id': 5}
        result = format_fact_form_value_row(row)
        assert result['form_item_id'] is None
        assert result['value'] is None

    def test_is_missing_defaults_to_false(self):
        row = {'id': 1}
        result = format_fact_form_value_row(row)
        assert result['is_missing'] is False


# ---------------------------------------------------------------------------
# _wrap_disagg_dict
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWrapDisaggDict:
    def test_none_returns_none(self):
        assert _wrap_disagg_dict(None) is None

    def test_empty_dict_returns_none(self):
        assert _wrap_disagg_dict({}) is None

    def test_non_dict_returns_none(self):
        assert _wrap_disagg_dict('string') is None
        assert _wrap_disagg_dict(42) is None

    def test_standard_sex_disagg(self):
        dd = {'mode': 'sex', 'values': {'male': 10, 'female': 20}}
        result = _wrap_disagg_dict(dd)
        assert result == {'mode': 'sex', 'values': {'male': 10, 'female': 20}}

    def test_standard_age_disagg(self):
        dd = {'mode': 'age', 'values': {'0-17': 5, '18+': 95}}
        result = _wrap_disagg_dict(dd)
        assert result['mode'] == 'age'
        assert result['values'] == {'0-17': 5, '18+': 95}

    def test_total_mode_with_disability(self):
        dd = {'mode': 'total', 'values': {'total': 100, 'disability': {'disaggregated_by_disability': True}}}
        result = _wrap_disagg_dict(dd)
        assert result['mode'] == 'total'
        assert result['values']['disability'] == {'disaggregated_by_disability': True}

    def test_bad_values_type_uses_empty_dict(self):
        dd = {'mode': 'sex', 'values': 'bad'}
        result = _wrap_disagg_dict(dd)
        assert result == {'mode': 'sex', 'values': {}}

    def test_matrix_flat_format(self):
        """Flat matrix dict (no 'values' key) -> mode='matrix', reserved '_' keys stripped."""
        dd = {'_table': 'ns', '10_SP2': 4107000, '11_SP2': 3000000}
        result = _wrap_disagg_dict(dd)
        assert result['mode'] == 'matrix'
        assert result['values'] == {'10_SP2': 4107000, '11_SP2': 3000000}
        assert '_table' not in result['values']

    def test_matrix_all_reserved_keys_returns_none_mode(self):
        """All keys start with '_' → values empty → mode is None."""
        dd = {'_table': 'ns', '_meta': 'x'}
        result = _wrap_disagg_dict(dd)
        assert result['mode'] is None
        assert result['values'] == {}

    def test_plugin_arbitrary_json(self):
        """Arbitrary plugin dict without 'values' key is treated like matrix."""
        dd = {'field_a': 1, 'field_b': 'hello'}
        result = _wrap_disagg_dict(dd)
        assert result['mode'] == 'matrix'
        assert result['values'] == {'field_a': 1, 'field_b': 'hello'}

    def test_variable_column_cell_modified_resolved_to_int(self):
        """Variable-column numeric strings are coerced to int."""
        dd = {
            '_table': 'ns',
            '10_SP2': {'original': '1000', 'modified': '1200', 'isModified': True},
            '11_SP2': {'original': '500', 'modified': '500', 'isModified': False},
        }
        result = _wrap_disagg_dict(dd)
        assert result['mode'] == 'matrix'
        assert result['values']['10_SP2'] == 1200
        assert isinstance(result['values']['10_SP2'], int)
        assert result['values']['11_SP2'] == 500
        assert '_table' not in result['values']

    def test_variable_column_cell_null_modified_falls_back_to_original(self):
        """When modified is None/absent, original is used and coerced."""
        dd = {
            '10_SP2': {'original': '999', 'modified': None, 'isModified': False},
        }
        result = _wrap_disagg_dict(dd)
        assert result['values']['10_SP2'] == 999
        assert isinstance(result['values']['10_SP2'], int)

    def test_variable_column_mixed_with_plain_cells(self):
        """Mix of plain scalar cells and variable-column cells is handled correctly."""
        dd = {
            '_table': 'ns',
            '10_SP2': 4107000,
            '11_SP2': {'original': '500', 'modified': '600', 'isModified': True},
        }
        result = _wrap_disagg_dict(dd)
        assert result['values']['10_SP2'] == 4107000
        assert result['values']['11_SP2'] == 600
        assert isinstance(result['values']['11_SP2'], int)


# ---------------------------------------------------------------------------
# _resolve_matrix_cell
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResolveMatrixCell:
    def test_plain_scalar_returned_unchanged(self):
        assert _resolve_matrix_cell(42) == 42
        assert _resolve_matrix_cell('hello') == 'hello'
        assert _resolve_matrix_cell(None) is None

    def test_modified_preferred_and_coerced_to_int(self):
        assert _resolve_matrix_cell({'original': '100', 'modified': '200', 'isModified': True}) == 200
        assert isinstance(_resolve_matrix_cell({'original': '100', 'modified': '200', 'isModified': True}), int)

    def test_original_used_when_modified_is_none_and_coerced(self):
        assert _resolve_matrix_cell({'original': '100', 'modified': None, 'isModified': False}) == 100

    def test_original_used_when_modified_absent_and_coerced(self):
        assert _resolve_matrix_cell({'original': '100'}) == 100

    def test_float_value_coerced(self):
        assert _resolve_matrix_cell({'original': '3.14', 'modified': '2.71', 'isModified': True}) == 2.71

    def test_thousands_separator_stripped(self):
        assert _resolve_matrix_cell({'original': '1,000', 'modified': '4,107,000', 'isModified': True}) == 4107000

    def test_non_numeric_string_returned_as_string(self):
        assert _resolve_matrix_cell({'original': 'yes', 'modified': 'no', 'isModified': True}) == 'no'

    def test_modified_zero_is_returned_not_skipped(self):
        assert _resolve_matrix_cell({'original': '100', 'modified': 0, 'isModified': True}) == 0

    def test_modified_empty_string_preserved(self):
        assert _resolve_matrix_cell({'original': '100', 'modified': '', 'isModified': True}) == ''


# ---------------------------------------------------------------------------
# format_bridge_disagg_rows
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormatBridgeDisaggRows:
    def test_none_payload_returns_empty(self):
        assert format_bridge_disagg_rows(1, None) == []

    def test_empty_dict_payload_returns_empty(self):
        assert format_bridge_disagg_rows(1, {}) == []

    def test_non_dict_payload_returns_empty(self):
        assert format_bridge_disagg_rows(1, 'string') == []

    def test_missing_values_returns_empty(self):
        assert format_bridge_disagg_rows(1, {'mode': 'sex'}) == []

    def test_empty_values_dict_returns_empty(self):
        assert format_bridge_disagg_rows(1, {'mode': 'sex', 'values': {}}) == []

    def test_values_not_dict_returns_empty(self):
        assert format_bridge_disagg_rows(1, {'mode': 'sex', 'values': 'bad'}) == []

    def test_normal_disagg_rows(self):
        payload = {'mode': 'sex', 'values': {'male': 10, 'female': 20}}
        rows = format_bridge_disagg_rows(42, payload, source='reported')
        assert len(rows) == 2
        assert all(r['form_data_id'] == 42 for r in rows)
        assert all(r['source'] == 'reported' for r in rows)
        assert all(r['mode'] == 'sex' for r in rows)
        keys = {r['key'] for r in rows}
        assert keys == {'male', 'female'}

    def test_underscore_keys_skipped(self):
        payload = {'mode': 'sex', 'values': {'_total': 100, 'male': 60, 'female': 40}}
        rows = format_bridge_disagg_rows(1, payload)
        keys = {r['key'] for r in rows}
        assert '_total' not in keys
        assert 'male' in keys

    def test_none_key_skipped(self):
        payload = {'mode': 'sex', 'values': {None: 5, 'male': 10}}
        rows = format_bridge_disagg_rows(1, payload)
        keys = {r['key'] for r in rows}
        assert 'male' in keys
        assert len(keys) == 1

    def test_default_source_is_reported(self):
        payload = {'mode': 'age', 'values': {'0-18': 5}}
        rows = format_bridge_disagg_rows(1, payload)
        assert rows[0]['source'] == 'reported'


# ---------------------------------------------------------------------------
# build_bridge_disagg_from_flat_rows
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBuildBridgeDisaggFromFlatRows:
    def test_always_builds_bridge_from_disagg_rows(self):
        rows = [{'id': 1, 'disaggregation_data': {'mode': 'sex', 'values': {'male': 5}}}]
        result = build_bridge_disagg_from_flat_rows(rows)
        assert len(result) == 1

    def test_none_rows_returns_empty(self):
        result = build_bridge_disagg_from_flat_rows(None)
        assert result == []

    def test_non_dict_row_skipped(self):
        result = build_bridge_disagg_from_flat_rows(['not-a-dict'])
        assert result == []

    def test_row_without_id_skipped(self):
        result = build_bridge_disagg_from_flat_rows(
            [{'disaggregation_data': {'mode': 'sex', 'values': {'male': 5}}}],
        )
        assert result == []

    def test_normal_rows_with_reported_disagg(self):
        rows = [{
            'id': 1,
            'disaggregation_data': {'mode': 'sex', 'values': {'male': 5, 'female': 8}},
            'prefilled_disaggregation_data': None,
            'imputed_disaggregation_data': None,
        }]
        result = build_bridge_disagg_from_flat_rows(rows)
        assert len(result) == 2
        sources = {r['source'] for r in result}
        assert sources == {'reported'}

    def test_multiple_sources_in_rows(self):
        rows = [{
            'id': 1,
            'disaggregation_data': {'mode': 'sex', 'values': {'male': 5}},
            'prefilled_disaggregation_data': {'mode': 'sex', 'values': {'male': 4}},
            'imputed_disaggregation_data': {'mode': 'sex', 'values': {'male': 3}},
        }]
        result = build_bridge_disagg_from_flat_rows(rows)
        sources = {r['source'] for r in result}
        assert sources == {'reported', 'prefilled', 'imputed'}


# ---------------------------------------------------------------------------
# build_star_schema_tables
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBuildStarSchemaTables:
    def test_empty_data_rows_returns_empty_tables(self, app):
        with app.app_context():
            result = build_star_schema_tables([], [], [])
            assert result['fact_form_values'] == []
            assert result['dim_country'] == []
            assert result['dim_template'] == []
            assert result['dim_period'] == []
            assert result['dim_submission'] == []

    def test_none_data_rows_returns_empty(self, app):
        with app.app_context():
            result = build_star_schema_tables(None, None, None)
            assert result['fact_form_values'] == []

    def test_fact_rows_formatted(self, app):
        with app.app_context():
            rows = [{
                'id': 1, 'form_item_id': 10, 'country_id': 2,
                'template_id': None, 'period_name': None,
                'submission_id': None, 'submission_type': 'assigned',
                'value': 5, 'num_value': 5.0,
                'data_status': 'available', 'submitted_at': '2024-01-01',
                'is_missing': False,
            }]
            result = build_star_schema_tables(rows, [], [])
            assert len(result['fact_form_values']) == 1
            assert result['fact_form_values'][0]['id'] == 1

    def test_countries_table_passed_through(self, app):
        with app.app_context():
            countries = [{'id': 1, 'name': 'Country A'}]
            result = build_star_schema_tables([], [], countries)
            assert result['dim_country'] == countries

    def test_form_items_table_passed_through(self, app):
        with app.app_context():
            items = [{'id': 10, 'label': 'Item'}]
            result = build_star_schema_tables([], items, [])
            assert result['dim_form_item'] == items

    def test_include_disagg_builds_bridge(self, app):
        with app.app_context():
            rows = [{
                'id': 1, 'form_item_id': 10, 'country_id': 2,
                'template_id': None, 'period_name': None,
                'submission_id': None, 'submission_type': 'assigned',
                'value': 5, 'num_value': 5.0, 'data_status': 'available',
                'submitted_at': '2024-01-01', 'is_missing': False,
                'disaggregation_data': {'mode': 'sex', 'values': {'male': 3, 'female': 2}},
                'prefilled_disaggregation_data': None,
                'imputed_disaggregation_data': None,
            }]
            result = build_star_schema_tables(rows, [], [])
            assert len(result['bridge_disagg_values']) == 2

    def test_with_template_ids_queries_db(self, app):
        with app.app_context():
            rows = [{
                'id': 1, 'form_item_id': 10, 'country_id': 2,
                'template_id': 5, 'period_name': '2024',
                'submission_id': 100, 'submission_type': 'assigned',
                'value': 5, 'num_value': 5.0, 'data_status': 'available',
                'submitted_at': '2024-01-01', 'is_missing': False,
            }]
            mock_template = MagicMock()
            mock_template.id = 5; mock_template.name = 'T5'
            mock_template.published_version = MagicMock()
            mock_template.published_version.description = 'Desc'

            mock_assigned_form = MagicMock()
            mock_assigned_form.template_id = 5
            mock_assigned_form.period_name = '2024'
            mock_assigned_form.period_id = 1
            mock_assigned_form.period_start = None
            mock_assigned_form.period_end = None

            mock_aes = MagicMock()
            mock_aes.id = 100
            mock_aes.status = 'submitted'
            mock_aes.entity_type = 'ns'
            mock_aes.entity_id = 1
            mock_aes.submitted_at = None
            mock_aes.due_date = None
            mock_aes.assigned_form_id = 10

            with patch('app.utils.api_serialization._joinedload_impl') as _mock_jl, \
                 patch('app.utils.api_serialization.FormTemplate') as mock_ft_cls, \
                 patch('app.utils.api_serialization.AssignedForm') as mock_af_cls, \
                 patch('app.utils.api_serialization.AssignmentEntityStatus') as mock_aes_cls, \
                 patch('app.utils.api_serialization.PublicSubmission') as mock_ps_cls:

                mock_ft_cls.query.options.return_value.filter.return_value.all.return_value = [mock_template]
                mock_af_cls.query.filter.return_value.all.return_value = [mock_assigned_form]
                mock_aes_cls.query.filter.return_value.all.return_value = [mock_aes]
                mock_ps_cls.query.filter.return_value.all.return_value = []

                result = build_star_schema_tables(rows, [], [])
            assert len(result['dim_template']) == 1
            assert result['dim_template'][0]['name'] == 'T5'
