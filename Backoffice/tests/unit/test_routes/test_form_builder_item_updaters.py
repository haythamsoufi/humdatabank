"""Unit tests for app.routes.admin.form_builder.helpers.item_updaters.

All update functions modify item attributes in place - no db.session needed.
FormItem objects are created directly as Python objects (no DB required).
The app fixture (session-scoped) provides Flask app context for current_app access.
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from werkzeug.datastructures import ImmutableMultiDict

pytestmark = [pytest.mark.unit]

from app.routes.admin.form_builder.helpers.item_updaters import (
    is_conditions_meaningful,
    _update_indicator_fields,
    _update_question_fields,
    _update_document_field_fields,
    _update_matrix_fields,
    _update_image_fields,
    _update_item_config,
    _update_plugin_fields,
)

_BASE = 'app.routes.admin.form_builder.helpers.item_updaters'


def _make_indicator():
    """Create an indicator FormItem without DB."""
    from app.models import FormItem
    item = FormItem(
        item_type='indicator',
        section_id=1,
        template_id=1,
        version_id=1,
        label='Test Indicator',
        type='number',
        unit='count',
        order=1,
    )
    item.config = {
        'is_required': False,
        'layout_column_width': 12,
        'layout_break_after': False,
        'allowed_disaggregation_options': ['total'],
        'age_groups_config': None,
        'allow_data_not_available': False,
        'allow_not_applicable': False,
        'indirect_reach': False,
    }
    return item


def _make_question():
    """Create a question FormItem without DB."""
    from app.models import FormItem
    item = FormItem(
        item_type='question',
        section_id=1,
        template_id=1,
        version_id=1,
        label='Test Question',
        type='text',
        order=1,
    )
    item.config = {}
    return item


def _make_doc_field():
    """Create a document_field FormItem without DB."""
    from app.models import FormItem
    item = FormItem(
        item_type='document_field',
        section_id=1,
        template_id=1,
        version_id=1,
        label='Test Doc Field',
        type='document',
        order=1,
    )
    item.config = {}
    return item


def _make_matrix():
    """Create a matrix FormItem without DB."""
    from app.models import FormItem
    item = FormItem(
        item_type='matrix',
        section_id=1,
        template_id=1,
        version_id=1,
        label='Test Matrix',
        type='matrix',
        order=1,
    )
    item.config = {}
    return item


def _make_plugin_item():
    """Create a plugin FormItem without DB."""
    from app.models import FormItem
    item = FormItem(
        item_type='plugin_interactive_map',
        section_id=1,
        template_id=1,
        version_id=1,
        label='Test Plugin',
        type='plugin',
        order=1,
    )
    item.config = {}
    return item


# ---------------------------------------------------------------------------
# is_conditions_meaningful — pure logic, no DB needed
# ---------------------------------------------------------------------------

class TestIsConditionsMeaningful:
    def test_none_returns_false(self):
        assert is_conditions_meaningful(None) is False

    def test_empty_string_returns_false(self):
        assert is_conditions_meaningful("") is False

    def test_empty_dict_returns_false(self):
        assert is_conditions_meaningful({}) is False

    def test_dict_with_empty_conditions_returns_false(self):
        assert is_conditions_meaningful({"conditions": []}) is False

    def test_dict_with_no_conditions_key_returns_false(self):
        assert is_conditions_meaningful({"other": "value"}) is False

    def test_valid_conditions_dict_returns_true(self):
        data = {"conditions": [{"item_id": "1", "value": "yes"}]}
        assert is_conditions_meaningful(data) is True

    def test_valid_conditions_json_string_returns_true(self):
        data = json.dumps({"conditions": [{"item_id": "1"}]})
        assert is_conditions_meaningful(data) is True

    def test_invalid_json_returns_false(self):
        assert is_conditions_meaningful("{not-valid") is False

    def test_non_dict_json_returns_false(self):
        assert is_conditions_meaningful(json.dumps([1, 2, 3])) is False

    def test_non_list_conditions_returns_false(self):
        assert is_conditions_meaningful({"conditions": "not-a-list"}) is False

    def test_conditions_array_with_items_returns_true(self):
        data = {"conditions": [{"item_id": "5"}]}
        assert is_conditions_meaningful(json.dumps(data)) is True


# ---------------------------------------------------------------------------
# _update_indicator_fields
# ---------------------------------------------------------------------------

class TestUpdateIndicatorFields:
    def test_no_indicator_bank_change(self, app):
        indicator = _make_indicator()
        form = MagicMock()
        form.indicator_bank_id.data = indicator.indicator_bank_id
        form.allowed_disaggregation_options.data = ['total']
        form.age_groups_config.data = None
        request_form = MagicMock()
        request_form.getlist.return_value = ['total']
        request_form.get.return_value = None

        with patch(f'{_BASE}.IndicatorBank') as MockIB:
            MockIB.query.get.return_value = None
            with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
                _update_indicator_fields(indicator, form, request_form)

    def test_indicator_bank_change_updates_fields(self, app):
        indicator = _make_indicator()
        new_bank = MagicMock()
        new_bank.name = "New Indicator"
        new_bank.type = "percentage"
        new_bank.unit = "percent"
        new_bank.indicator_type_id = 5
        new_bank.indicator_unit_id = 6
        new_bank.id = 999

        form = MagicMock()
        form.indicator_bank_id.data = 999
        form.allowed_disaggregation_options.data = ['total']
        form.age_groups_config.data = None
        request_form = MagicMock()
        request_form.getlist.return_value = ['total']
        request_form.get.return_value = None

        with patch(f'{_BASE}.IndicatorBank') as MockIB:
            MockIB.query.get.return_value = new_bank
            with patch('app.utils.indicator_utils.supports_disaggregation', return_value=False):
                _update_indicator_fields(indicator, form, request_form)

        assert indicator.label == "New Indicator"

    def test_label_override_applied(self, app):
        indicator = _make_indicator()
        form = MagicMock()
        form.indicator_bank_id.data = indicator.indicator_bank_id
        form.allowed_disaggregation_options.data = ['total']
        form.age_groups_config.data = None
        request_form = ImmutableMultiDict([
            ('indicator_label_override', 'Custom Label'),
            ('allowed_disaggregation_options', 'total'),
        ])

        with patch(f'{_BASE}.IndicatorBank') as MockIB:
            MockIB.query.get.return_value = None
            with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
                _update_indicator_fields(indicator, form, request_form)

        assert indicator.label == 'Custom Label'

    def test_empty_label_override_reverts_to_bank_name(self, app):
        indicator = _make_indicator()
        indicator.indicator_bank = MagicMock()
        indicator.indicator_bank.name = "Bank Name"
        form = MagicMock()
        form.indicator_bank_id.data = indicator.indicator_bank_id
        form.allowed_disaggregation_options.data = ['total']
        form.age_groups_config.data = None
        request_form = ImmutableMultiDict([
            ('indicator_label_override', ''),
            ('allowed_disaggregation_options', 'total'),
        ])

        with patch(f'{_BASE}.IndicatorBank') as MockIB:
            MockIB.query.get.return_value = None
            with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
                _update_indicator_fields(indicator, form, request_form)

    def test_definition_override(self, app):
        indicator = _make_indicator()
        form = MagicMock()
        form.indicator_bank_id.data = indicator.indicator_bank_id
        form.allowed_disaggregation_options.data = ['total']
        form.age_groups_config.data = None
        request_form = MagicMock()
        request_form.__contains__ = lambda s, k: k in ['definition', 'allowed_disaggregation_options']
        request_form.getlist.side_effect = lambda k: ['My definition'] if k == 'definition' else ['total']
        request_form.get.return_value = None

        with patch(f'{_BASE}.IndicatorBank') as MockIB:
            MockIB.query.get.return_value = None
            with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
                _update_indicator_fields(indicator, form, request_form)

        assert indicator.definition == 'My definition'

    def test_empty_definition_clears(self, app):
        indicator = _make_indicator()
        indicator.definition = "Old def"
        form = MagicMock()
        form.indicator_bank_id.data = indicator.indicator_bank_id
        form.allowed_disaggregation_options.data = ['total']
        form.age_groups_config.data = None
        request_form = MagicMock()
        request_form.__contains__ = lambda s, k: k in ['definition', 'allowed_disaggregation_options']
        request_form.getlist.side_effect = lambda k: [''] if k == 'definition' else ['total']
        request_form.get.return_value = None

        with patch(f'{_BASE}.IndicatorBank') as MockIB:
            MockIB.query.get.return_value = None
            with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
                _update_indicator_fields(indicator, form, request_form)

        assert indicator.definition is None

    def test_label_translations_filtered(self, app):
        indicator = _make_indicator()
        form = MagicMock()
        form.indicator_bank_id.data = indicator.indicator_bank_id
        form.allowed_disaggregation_options.data = ['total']
        form.age_groups_config.data = None

        lt = json.dumps({"en": "English Label", "xx": "Unknown Label"})
        request_form = ImmutableMultiDict([
            ('label_translations', lt),
            ('allowed_disaggregation_options', 'total'),
        ])

        app.config['SUPPORTED_LANGUAGES'] = ['en']
        with patch(f'{_BASE}.IndicatorBank') as MockIB:
            MockIB.query.get.return_value = None
            with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
                _update_indicator_fields(indicator, form, request_form)

        assert indicator.label_translations == {"en": "English Label"}

    def test_label_translations_cleared_on_empty(self, app):
        indicator = _make_indicator()
        indicator.label_translations = {"en": "old"}
        form = MagicMock()
        form.indicator_bank_id.data = indicator.indicator_bank_id
        form.allowed_disaggregation_options.data = ['total']
        form.age_groups_config.data = None
        request_form = ImmutableMultiDict([
            ('label_translations', ''),
            ('allowed_disaggregation_options', 'total'),
        ])

        with patch(f'{_BASE}.IndicatorBank') as MockIB:
            MockIB.query.get.return_value = None
            with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
                _update_indicator_fields(indicator, form, request_form)

        assert indicator.label_translations is None

    def test_definition_translations(self, app):
        indicator = _make_indicator()
        form = MagicMock()
        form.indicator_bank_id.data = indicator.indicator_bank_id
        form.allowed_disaggregation_options.data = ['total']
        form.age_groups_config.data = None

        dt = json.dumps({"en": "English Def"})
        request_form = ImmutableMultiDict([
            ('definition_translations', dt),
            ('allowed_disaggregation_options', 'total'),
        ])

        app.config['SUPPORTED_LANGUAGES'] = ['en']
        with patch(f'{_BASE}.IndicatorBank') as MockIB:
            MockIB.query.get.return_value = None
            with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
                _update_indicator_fields(indicator, form, request_form)

        assert indicator.definition_translations == {"en": "English Def"}

    def test_disaggregation_forced_to_total_when_not_supported(self, app):
        indicator = _make_indicator()
        form = MagicMock()
        form.indicator_bank_id.data = indicator.indicator_bank_id
        form.allowed_disaggregation_options.data = ['age', 'gender']
        form.age_groups_config.data = None
        request_form = MagicMock()
        request_form.getlist.return_value = ['age', 'gender']
        request_form.get.return_value = None

        with patch(f'{_BASE}.IndicatorBank') as MockIB:
            MockIB.query.get.return_value = MagicMock()
            with patch('app.utils.indicator_utils.supports_disaggregation', return_value=False):
                _update_indicator_fields(indicator, form, request_form)

        assert indicator.config['allowed_disaggregation_options'] == ['total']

    def test_default_value_updated(self, app):
        indicator = _make_indicator()
        form = MagicMock()
        form.indicator_bank_id.data = indicator.indicator_bank_id
        form.allowed_disaggregation_options.data = ['total']
        form.age_groups_config.data = None
        request_form = MagicMock()
        request_form.getlist.return_value = ['total']
        request_form.get.side_effect = lambda k, d=None: '42' if k == 'default_value' else d

        with patch(f'{_BASE}.IndicatorBank') as MockIB:
            MockIB.query.get.return_value = None
            with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
                _update_indicator_fields(indicator, form, request_form)

        assert indicator.config.get('default_value') == '42'

    def test_config_initialized_when_none(self, app):
        indicator = _make_indicator()
        indicator.config = None
        form = MagicMock()
        form.indicator_bank_id.data = indicator.indicator_bank_id
        form.allowed_disaggregation_options.data = ['total']
        form.age_groups_config.data = None
        request_form = MagicMock()
        request_form.getlist.return_value = ['total']
        request_form.get.return_value = None

        with patch(f'{_BASE}.IndicatorBank') as MockIB:
            MockIB.query.get.return_value = None
            with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
                _update_indicator_fields(indicator, form, request_form)

        assert indicator.config is not None
        assert 'allowed_disaggregation_options' in indicator.config


# ---------------------------------------------------------------------------
# _update_question_fields
# ---------------------------------------------------------------------------

def _make_question_form(label="Q1", definition="", question_type='text',
                        unit=None, options_json_data=None):
    form = MagicMock()
    form.definition.data = definition
    form.label.data = label
    form.question_type.data = question_type
    form.unit = MagicMock()
    form.unit.data = unit
    form.prefix = None
    form.options_json = MagicMock()
    form.options_json.data = options_json_data
    return form


class TestUpdateQuestionFields:
    def test_updates_basic_fields(self, app):
        question = _make_question()
        form = _make_question_form(label="My label", definition="My definition")
        _update_question_fields(question, form, {})
        assert question.definition == "My definition"
        assert question.label == "My label"
        assert question.type == 'text'

    def test_blank_question_allows_empty_label(self, app):
        question = _make_question()
        form = _make_question_form(label="", question_type='blank')
        _update_question_fields(question, form, {})
        assert question.label == ""

    def test_non_blank_question_gets_default_label(self, app):
        question = _make_question()
        form = _make_question_form(label="", question_type='text')
        _update_question_fields(question, form, {})
        assert question.label == 'Question'

    def test_single_choice_with_manual_options(self, app):
        question = _make_question()
        options = [{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}]
        form = _make_question_form(label="Q1", question_type='single_choice',
                                   options_json_data=json.dumps(options))
        _update_question_fields(question, form, {'options_source': 'manual'})
        assert question.options_json == options
        assert question.lookup_list_id is None

    def test_single_choice_with_invalid_options_json(self, app):
        question = _make_question()
        form = _make_question_form(label="Q1", question_type='single_choice',
                                   options_json_data="invalid-json")
        _update_question_fields(question, form, {'options_source': 'manual'})
        assert question.options_json is None

    def test_calculated_with_plugin_lookup_list(self, app):
        question = _make_question()
        form = _make_question_form(label="Q1", question_type='single_choice')
        request_form = {
            'options_source': 'calculated',
            'lookup_list_id': 'reporting_currency',
            'list_display_column': 'code'
        }
        _update_question_fields(question, form, request_form)
        assert question.lookup_list_id == 'reporting_currency'
        assert question.list_display_column == 'code'
        assert question.options_json is None

    def test_calculated_with_db_lookup_list(self, app):
        question = _make_question()
        form = _make_question_form(label="Q1", question_type='multiple_choice')
        request_form = {
            'options_source': 'calculated',
            'lookup_list_id': '5',
            'list_display_column': 'name'
        }

        with patch(f'{_BASE}.LookupList') as MockLL:
            mock_ll = MagicMock()
            mock_ll.columns_config = [{'name': 'name'}]
            MockLL.query.get.return_value = mock_ll
            _update_question_fields(question, form, request_form)

        assert question.lookup_list_id == 5

    def test_calculated_with_unknown_db_lookup_list(self, app):
        question = _make_question()
        form = _make_question_form(label="Q1", question_type='single_choice')
        request_form = {
            'options_source': 'calculated',
            'lookup_list_id': '999',
        }

        with patch(f'{_BASE}.LookupList') as MockLL:
            MockLL.query.get.return_value = None
            _update_question_fields(question, form, request_form)

        assert question.lookup_list_id is None

    def test_label_translations(self, app):
        question = _make_question()
        form = _make_question_form(label="Q1")
        lt = json.dumps({"en": "English Q"})
        request_form = {'label_translations': lt}
        app.config['SUPPORTED_LANGUAGES'] = ['en', 'fr']
        _update_question_fields(question, form, request_form)
        assert question.label_translations == {"en": "English Q"}

    def test_options_translations(self, app):
        question = _make_question()
        form = _make_question_form(label="Q1", question_type='single_choice')
        ot = json.dumps([{"en": "Yes", "fr": "Oui"}, {"en": "No", "fr": "Non"}])
        _update_question_fields(question, form, {'options_source': 'manual', 'options_translations_json': ot})
        assert question.options_translations is not None

    def test_filters_json_for_calculated_list(self, app):
        question = _make_question()
        form = _make_question_form(label="Q1", question_type='single_choice')
        filters = json.dumps([{"field": "active", "value": "true"}])
        request_form = {
            'options_source': 'calculated',
            'lookup_list_id': 'my_list',
            'list_filters_json': filters
        }
        _update_question_fields(question, form, request_form)
        assert question.list_filters_json is not None

    def test_invalid_filter_json_is_cleared(self, app):
        question = _make_question()
        form = _make_question_form(label="Q1", question_type='single_choice')
        request_form = {
            'options_source': 'calculated',
            'lookup_list_id': 'my_list',
            'list_filters_json': 'invalid-json'
        }
        _update_question_fields(question, form, request_form)
        assert question.list_filters_json is None

    def test_definition_translations(self, app):
        question = _make_question()
        form = _make_question_form(label="Q1")
        dt = json.dumps({"en": "English Def"})
        app.config['SUPPORTED_LANGUAGES'] = ['en']
        _update_question_fields(question, form, {'definition_translations': dt})
        assert question.definition_translations == {"en": "English Def"}

    def test_columns_config_display_column_default(self, app):
        question = _make_question()
        form = _make_question_form(label="Q1", question_type='single_choice')
        request_form = {
            'options_source': 'calculated',
            'lookup_list_id': '10',
        }

        with patch(f'{_BASE}.LookupList') as MockLL:
            mock_ll = MagicMock()
            mock_ll.columns_config = [{'name': 'first_col'}]
            MockLL.query.get.return_value = mock_ll
            _update_question_fields(question, form, request_form)

        assert question.list_display_column == 'first_col'


# ---------------------------------------------------------------------------
# _update_document_field_fields
# ---------------------------------------------------------------------------

def _make_doc_form(label="Doc", description="", max_documents=None):
    form = MagicMock()
    form.label.data = label
    form.description.data = description
    form.max_documents = MagicMock()
    form.max_documents.data = max_documents
    return form


class TestUpdateDocumentFieldFields:
    def test_updates_label_and_description(self, app):
        doc = _make_doc_field()
        form = _make_doc_form(label="Document Label", description="Document Description", max_documents=5)
        _update_document_field_fields(doc, form, {})
        assert doc.label == "Document Label"
        assert doc.description == "Document Description"
        assert doc.config['max_documents'] == 5

    def test_max_documents_from_request_form(self, app):
        doc = _make_doc_field()
        form = _make_doc_form()
        _update_document_field_fields(doc, form, {'max_documents': '3'})
        assert doc.config['max_documents'] == 3

    def test_invalid_max_documents_is_none(self, app):
        doc = _make_doc_field()
        form = _make_doc_form()
        _update_document_field_fields(doc, form, {'max_documents': 'not-a-number'})
        assert doc.config['max_documents'] is None

    def test_document_type_from_form(self, app):
        doc = _make_doc_field()
        form = _make_doc_form()
        form.document_type = MagicMock()
        form.document_type.data = "report"
        _update_document_field_fields(doc, form, {})
        assert doc.config['document_type'] == 'report'

    def test_document_type_from_request_form(self, app):
        doc = _make_doc_field()
        form = _make_doc_form()
        del form.document_type
        _update_document_field_fields(doc, form, {'document_type': 'contract'})
        assert doc.config['document_type'] == 'contract'

    def test_show_year_true_clears_preset_period(self, app):
        doc = _make_doc_field()
        doc.config = {'preset_period': '2024', 'preset_period_use_assignment': True}
        form = _make_doc_form()
        _update_document_field_fields(doc, form, {'show_year': 'true'})
        assert doc.config['show_year'] is True
        assert 'preset_period' not in doc.config
        assert 'preset_period_use_assignment' not in doc.config

    def test_preset_period_assignment_mode(self, app):
        doc = _make_doc_field()
        form = _make_doc_form()
        _update_document_field_fields(doc, form, {
            'show_year': '',
            'preset_period_mode_value': 'assignment'
        })
        assert doc.config['preset_period_use_assignment'] is True
        assert doc.config['preset_period'] is None

    def test_preset_period_custom_mode(self, app):
        doc = _make_doc_field()
        form = _make_doc_form()
        _update_document_field_fields(doc, form, {
            'show_year': '',
            'preset_period_mode': 'custom',
            'preset_period': '2025'
        })
        assert doc.config['preset_period_use_assignment'] is False
        assert doc.config['preset_period'] == '2025'

    def test_config_initialized_when_none(self, app):
        doc = _make_doc_field()
        doc.config = None
        form = _make_doc_form()
        _update_document_field_fields(doc, form, {})
        assert doc.config is not None
        assert 'show_language' in doc.config

    def test_display_options_set(self, app):
        doc = _make_doc_field()
        form = _make_doc_form()
        _update_document_field_fields(doc, form, {
            'show_language': 'on',
            'show_document_type': 'true',
            'show_public_checkbox': '1',
            'allow_single_year': 'true',
            'allow_year_range': 'on',
            'allow_month_range': '1',
            'cross_assignment_period_reuse': 'true',
        })
        assert doc.config['show_language'] is True
        assert doc.config['show_document_type'] is True
        assert doc.config['show_public_checkbox'] is True
        assert doc.config['allow_single_year'] is True
        assert doc.config['allow_year_range'] is True
        assert doc.config['allow_month_range'] is True
        assert doc.config['cross_assignment_period_reuse'] is True


# ---------------------------------------------------------------------------
# _update_matrix_fields
# ---------------------------------------------------------------------------

def _make_matrix_form(label="M", description="", matrix_config_data=None):
    form = MagicMock()
    form.label.data = label
    form.description.data = description
    form.matrix_config = MagicMock()
    form.matrix_config.data = matrix_config_data
    return form


class TestUpdateMatrixFields:
    def test_updates_label_and_description(self, app):
        matrix = _make_matrix()
        form = _make_matrix_form(label="Matrix Label", description="Matrix Desc")
        _update_matrix_fields(matrix, form, {})
        assert matrix.label == "Matrix Label"
        assert matrix.description == "Matrix Desc"

    def test_matrix_config_parsed_and_stored(self, app):
        matrix = _make_matrix()
        mc = {"type": "matrix", "rows": ["Row1", "Row2"], "columns": [{"name": "Col1"}]}
        form = _make_matrix_form(matrix_config_data=json.dumps(mc))
        app.config['SUPPORTED_LANGUAGES'] = ['en']
        _update_matrix_fields(matrix, form, {})
        assert matrix.config['matrix_config']['type'] == 'matrix'
        assert matrix.config['matrix_config']['rows'] == ["Row1", "Row2"]

    def test_invalid_matrix_config_is_ignored(self, app):
        matrix = _make_matrix()
        matrix.config = {'existing': True}
        form = _make_matrix_form(matrix_config_data="invalid-json")
        _update_matrix_fields(matrix, form, {})
        # Invalid JSON is skipped for matrix_config, but other form fields may still update config
        assert 'existing' in matrix.config
        assert 'matrix_config' not in matrix.config

    def test_list_library_mode_sets_lookup_fields(self, app):
        matrix = _make_matrix()
        mc = {
            "type": "matrix",
            "row_mode": "list_library",
            "lookup_list_id": 10,
            "list_display_column": "name",
            "list_filters": [{"field": "active"}],
            "columns": []
        }
        form = _make_matrix_form(matrix_config_data=json.dumps(mc))
        app.config['SUPPORTED_LANGUAGES'] = ['en']
        _update_matrix_fields(matrix, form, {})
        assert matrix.lookup_list_id == 10
        assert matrix.list_display_column == "name"

    def test_manual_mode_clears_lookup_fields(self, app):
        matrix = _make_matrix()
        matrix.lookup_list_id = 5
        matrix.list_display_column = "name"
        mc = {"type": "matrix", "row_mode": "manual", "columns": []}
        form = _make_matrix_form(matrix_config_data=json.dumps(mc))
        app.config['SUPPORTED_LANGUAGES'] = ['en']
        _update_matrix_fields(matrix, form, {})
        assert matrix.lookup_list_id is None
        assert matrix.list_display_column is None

    def test_label_translations_stored(self, app):
        matrix = _make_matrix()
        form = _make_matrix_form()
        lt = json.dumps({"en": "Matrix En"})
        app.config['SUPPORTED_LANGUAGES'] = ['en']
        _update_matrix_fields(matrix, form, {'label_translations': lt})
        assert matrix.label_translations == {"en": "Matrix En"}

    def test_column_name_translations_normalized(self, app):
        matrix = _make_matrix()
        mc = {
            "type": "matrix",
            "columns": [
                {"name": "Col1", "name_translations": {"en": "English Col", "xx": "Invalid"}}
            ]
        }
        form = _make_matrix_form(matrix_config_data=json.dumps(mc))
        app.config['SUPPORTED_LANGUAGES'] = ['en']
        _update_matrix_fields(matrix, form, {})
        stored_cols = matrix.config['matrix_config']['columns']
        assert stored_cols[0].get('name_translations') == {"en": "English Col"}

    def test_description_translations_stored(self, app):
        matrix = _make_matrix()
        form = _make_matrix_form()
        dt = json.dumps({"en": "Desc En"})
        app.config['SUPPORTED_LANGUAGES'] = ['en']
        _update_matrix_fields(matrix, form, {'description_translations': dt})
        assert matrix.description_translations == {"en": "Desc En"}

    def test_additional_config_fields_updated(self, app):
        matrix = _make_matrix()
        form = _make_matrix_form()
        form.allow_data_not_available = MagicMock()
        form.allow_data_not_available.data = True
        form.allow_not_applicable = MagicMock()
        form.allow_not_applicable.data = True
        form.indirect_reach = MagicMock()
        form.indirect_reach.data = True
        _update_matrix_fields(matrix, form, {})
        assert matrix.allow_data_not_available is True


# ---------------------------------------------------------------------------
# _update_item_config
# ---------------------------------------------------------------------------

def _make_form_with_config(is_required=False, width='12', break_after=False,
                           allow_dna=False, allow_na=False, allow_disability=False,
                           indirect_reach=False, privacy='ifrc_network'):
    form = MagicMock()
    form.is_required = MagicMock()
    form.is_required.data = is_required
    form.layout_column_width = MagicMock()
    form.layout_column_width.data = width
    form.layout_break_after = MagicMock()
    form.layout_break_after.data = break_after
    form.allow_data_not_available = MagicMock()
    form.allow_data_not_available.data = allow_dna
    form.allow_not_applicable = MagicMock()
    form.allow_not_applicable.data = allow_na
    form.allow_disability_questions = MagicMock()
    form.allow_disability_questions.data = allow_disability
    form.indirect_reach = MagicMock()
    form.indirect_reach.data = indirect_reach
    form.privacy = MagicMock()
    form.privacy.data = privacy
    return form


class TestUpdateItemConfig:
    def test_initializes_empty_config(self, app):
        from app.models import FormItem
        item = FormItem(item_type='indicator', section_id=1, template_id=1, version_id=1,
                        label='I', type='number', order=1)
        item.config = None
        form = _make_form_with_config(is_required=True, width='6', privacy='ifrc_network')
        _update_item_config(item, form, {})
        assert item.config is not None
        assert item.config['is_required'] is True
        assert item.config['layout_column_width'] == '6'

    def test_allow_over_100_from_request_form(self, app):
        from app.models import FormItem
        item = FormItem(item_type='indicator', section_id=1, template_id=1, version_id=1,
                        label='I', type='number', order=1)
        item.config = {}
        form = _make_form_with_config(privacy='public')
        _update_item_config(item, form, {'allow_over_100': 'true'})
        assert item.config['allow_over_100'] is True

    def test_allow_over_100_from_config_json(self, app):
        from app.models import FormItem
        item = FormItem(item_type='indicator', section_id=1, template_id=1, version_id=1,
                        label='I', type='number', order=1)
        item.config = {}
        form = _make_form_with_config()
        _update_item_config(item, form, {'config': json.dumps({'allow_over_100': True})})
        assert item.config['allow_over_100'] is True

    def test_privacy_normalized_to_ifrc_network_for_unknown_value(self, app):
        from app.models import FormItem
        item = FormItem(item_type='indicator', section_id=1, template_id=1, version_id=1,
                        label='I', type='number', order=1)
        item.config = {}
        form = _make_form_with_config(privacy='unknown_value')
        _update_item_config(item, form, {})
        assert item.config['privacy'] == 'ifrc_network'

    def test_privacy_public_accepted(self, app):
        from app.models import FormItem
        item = FormItem(item_type='indicator', section_id=1, template_id=1, version_id=1,
                        label='I', type='number', order=1)
        item.config = {}
        form = _make_form_with_config(privacy='public')
        _update_item_config(item, form, {})
        assert item.config['privacy'] == 'public'

    def test_layout_width_fallback_from_request_form(self, app):
        from app.models import FormItem
        item = FormItem(item_type='indicator', section_id=1, template_id=1, version_id=1,
                        label='I', type='number', order=1)
        item.config = {}
        form = MagicMock()
        del form.layout_column_width
        form.is_required = MagicMock()
        form.is_required.data = False
        form.layout_break_after = MagicMock()
        form.layout_break_after.data = False
        form.allow_data_not_available = MagicMock()
        form.allow_data_not_available.data = False
        form.allow_not_applicable = MagicMock()
        form.allow_not_applicable.data = False
        form.allow_disability_questions = MagicMock()
        form.allow_disability_questions.data = False
        form.indirect_reach = MagicMock()
        form.indirect_reach.data = False
        form.privacy = MagicMock()
        form.privacy.data = 'ifrc_network'
        _update_item_config(item, form, {'layout_column_width': '4'})
        assert item.config['layout_column_width'] == '4'

    def test_all_flags_set(self, app):
        from app.models import FormItem
        item = FormItem(item_type='indicator', section_id=1, template_id=1, version_id=1,
                        label='I', type='number', order=1)
        item.config = {}
        form = _make_form_with_config(
            is_required=True, width='12', break_after=True,
            allow_dna=True, allow_na=True, allow_disability=True,
            indirect_reach=True, privacy='public'
        )
        _update_item_config(item, form, {})
        assert item.config['is_required'] is True
        assert item.config['layout_break_after'] is True
        assert item.config['allow_data_not_available'] is True
        assert item.config['allow_not_applicable'] is True
        assert item.config['allow_disability_questions'] is True
        assert item.config['indirect_reach'] is True
        assert item.config['privacy'] == 'public'


# ---------------------------------------------------------------------------
# _update_plugin_fields
# ---------------------------------------------------------------------------

def _make_plugin_form(label="Plugin", description="", is_required=False,
                      layout_width=12, break_after=False, allow_dna=False,
                      allow_na=False, indirect_reach=False, privacy='ifrc_network'):
    form = MagicMock()
    form.label = MagicMock()
    form.label.data = label
    form.description = MagicMock()
    form.description.data = description
    form.is_required = MagicMock()
    form.is_required.data = is_required
    form.layout_column_width = MagicMock()
    form.layout_column_width.data = layout_width
    form.layout_break_after = MagicMock()
    form.layout_break_after.data = break_after
    form.allow_data_not_available = MagicMock()
    form.allow_data_not_available.data = allow_dna
    form.allow_not_applicable = MagicMock()
    form.allow_not_applicable.data = allow_na
    form.indirect_reach = MagicMock()
    form.indirect_reach.data = indirect_reach
    form.privacy = MagicMock()
    form.privacy.data = privacy
    return form


class TestUpdatePluginFields:
    def test_updates_label_and_description(self, app):
        plugin = _make_plugin_item()
        form = _make_plugin_form(label="Plugin Label", description="Plugin Desc")
        _update_plugin_fields(plugin, form, {})
        assert plugin.label == "Plugin Label"
        assert plugin.description == "Plugin Desc"

    def test_plugin_config_updated(self, app):
        plugin = _make_plugin_item()
        form = _make_plugin_form()
        plugin_cfg = {'zoom': 5}
        _update_plugin_fields(plugin, form, {'plugin_config': json.dumps(plugin_cfg)})
        assert plugin.config['plugin_config'] == plugin_cfg

    def test_allow_over_100_set_via_request(self, app):
        plugin = _make_plugin_item()
        form = _make_plugin_form(privacy='public')
        _update_plugin_fields(plugin, form, {'allow_over_100': 'on'})
        assert plugin.config['allow_over_100'] is True

    def test_config_initialized_when_none(self, app):
        plugin = _make_plugin_item()
        plugin.config = None
        form = _make_plugin_form()
        _update_plugin_fields(plugin, form, {})
        assert plugin.config is not None

    def test_layout_width_from_request_form(self, app):
        plugin = _make_plugin_item()
        form = _make_plugin_form()
        del form.layout_column_width
        _update_plugin_fields(plugin, form, {'layout_column_width': '8'})
        assert plugin.config['layout_column_width'] == 8


def _make_image_item():
    from app.models import FormItem
    return FormItem(
        item_type='image',
        label='Caption',
        description='Alt',
        config={'image': {'alignment': 'center', 'max_width': '100%', 'sources': {}}},
    )


def _make_image_form(label='Caption', description='Alt', image_config_data=None):
    form = MagicMock()
    form.label.data = label
    form.description.data = description
    form.image_config = MagicMock()
    form.image_config.data = image_config_data
    return form


class TestUpdateImageFields:
    def test_updates_label_description_and_config(self, app):
        image = _make_image_item()
        cfg = {
            'image': {
                'alignment': 'right',
                'max_width': '75%',
                'sources': {'en': {'source_type': 'url', 'url': 'https://example.org/a.png'}},
            }
        }
        form = _make_image_form(image_config_data=json.dumps(cfg))
        app.config['SUPPORTED_LANGUAGES'] = ['en']
        _update_image_fields(image, form, {})
        assert image.label == 'Caption'
        assert image.description == 'Alt'
        assert image.config['image']['sources']['en']['url'] == 'https://example.org/a.png'
        assert image.config['is_required'] is False

    def test_label_translations_stored(self, app):
        image = _make_image_item()
        form = _make_image_form()
        app.config['SUPPORTED_LANGUAGES'] = ['en', 'fr']
        _update_image_fields(image, form, {'label_translations': json.dumps({'fr': 'Légende'})})
        assert image.label_translations == {'fr': 'Légende'}
