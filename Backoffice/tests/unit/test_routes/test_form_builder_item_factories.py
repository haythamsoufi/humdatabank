"""Unit tests for app.routes.admin.form_builder.helpers.item_factories.

All tests mock db.session and model queries so no DB tables are needed.
The app fixture (session-scoped) provides the Flask app context.

Key insight about get_field_value(field, prefix):
  - When called with default prefix (e.g. 'add_ind_modal-'), it tries 'add_ind_modal-<field>' then '<field>'.
  - When called with explicit empty prefix '', it only tries '<field>' (unprefixed).
  - 'layout_column_width' is looked up via get_field_value('layout_column_width', '12') where '12' is the
    prefix, so it tries '12layout_column_width' (absent) then 'layout_column_width'.
    _form() always adds ('layout_column_width', '12') to satisfy this.
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from werkzeug.datastructures import ImmutableMultiDict

pytestmark = [pytest.mark.unit]

from app.routes.admin.form_builder.helpers.item_factories import (
    _create_form_item,
    _create_indicator_form_item,
    _create_question_form_item,
    _create_document_field_form_item,
    _create_matrix_form_item,
    _create_plugin_form_item,
)

_BASE = 'app.routes.admin.form_builder.helpers.item_factories'


def _form(*pairs, **kwargs):
    """Build ImmutableMultiDict with layout_column_width always present."""
    base = [('layout_column_width', '12')]
    extra = list(pairs)
    for k, v in kwargs.items():
        extra.append((k, v))
    return ImmutableMultiDict(base + extra)


def _mock_template():
    return MagicMock(id=1)


def _mock_section():
    return MagicMock(id=1, version_id=1)


@pytest.fixture
def mock_db():
    """Mock db.session.add/flush so no DB is needed."""
    with patch(f'{_BASE}.db') as m:
        yield m


@pytest.fixture
def mock_fi_query():
    """Mock FormItem class so no DB query is issued for order calculation."""
    with patch(f'{_BASE}.FormItem') as MockFI:
        from app.models import FormItem as RealFI
        MockFI.side_effect = lambda **kw: RealFI(**kw)
        MockFI.query.filter_by.return_value.order_by.return_value.first.return_value = None
        yield MockFI


@pytest.fixture
def mock_ib():
    """Mock IndicatorBank so no DB query is issued."""
    with patch(f'{_BASE}.IndicatorBank') as MockIB:
        MockIB.query.get.return_value = None
        yield MockIB


@pytest.fixture
def mock_ll():
    """Mock LookupList so no DB query is issued."""
    with patch(f'{_BASE}.LookupList') as MockLL:
        MockLL.query.get.return_value = None
        yield MockLL


@pytest.fixture
def mock_fs():
    """Mock FormSection so no DB query is issued."""
    with patch(f'{_BASE}.FormSection') as MockFS:
        mock_section = MagicMock()
        mock_section.version_id = 1
        MockFS.query.get.return_value = mock_section
        yield MockFS


# ---------------------------------------------------------------------------
# _create_form_item dispatcher
# ---------------------------------------------------------------------------

class TestCreateFormItem:
    def test_dispatches_to_indicator(self, app, mock_db, mock_fi_query, mock_ib):
        template = _mock_template()
        section = _mock_section()
        form_data = _form(('allowed_disaggregation_options', 'total'))
        item = _create_form_item(template, section, form_data, 'indicator')
        assert item is not None
        assert item.item_type == 'indicator'

    def test_dispatches_to_question(self, app, mock_db, mock_fi_query):
        template = _mock_template()
        section = _mock_section()
        # question_type uses default prefix 'add_q_modal-'
        form_data = _form(('add_q_modal-question_type', 'text'))
        item = _create_form_item(template, section, form_data, 'question')
        assert item is not None
        assert item.item_type == 'question'

    def test_dispatches_to_document_field(self, app, mock_db, mock_fi_query, mock_fs):
        template = _mock_template()
        section = _mock_section()
        item = _create_form_item(template, section, _form(), 'document_field')
        assert item is not None
        assert item.item_type == 'document_field'

    def test_dispatches_to_matrix(self, app, mock_db, mock_fi_query, mock_fs):
        template = _mock_template()
        section = _mock_section()
        item = _create_form_item(template, section, ImmutableMultiDict([]), 'matrix')
        assert item is not None
        assert item.item_type == 'matrix'

    def test_dispatches_to_image(self, app, mock_db, mock_fi_query, mock_fs):
        template = _mock_template()
        section = _mock_section()
        item = _create_form_item(template, section, ImmutableMultiDict([]), 'image')
        assert item is not None
        assert item.item_type == 'image'
        assert item.config.get('is_required') is False

    def test_dispatches_to_plugin(self, app, mock_db, mock_fi_query):
        template = _mock_template()
        section = _mock_section()
        item = _create_form_item(template, section, ImmutableMultiDict([]), 'plugin_interactive_map')
        assert item is not None
        assert item.item_type == 'plugin_interactive_map'

    def test_unknown_type_returns_none(self, app, mock_db, mock_fi_query):
        template = _mock_template()
        section = _mock_section()
        item = _create_form_item(template, section, ImmutableMultiDict([]), 'unknown_type')
        assert item is None

    def test_uses_existing_item_order(self, app, mock_db, mock_fi_query, mock_ib):
        template = _mock_template()
        section = _mock_section()
        existing = MagicMock()
        existing.order = 5
        mock_fi_query.query.filter_by.return_value.order_by.return_value.first.return_value = existing

        form_data = _form(('allowed_disaggregation_options', 'total'))
        item = _create_form_item(template, section, form_data, 'indicator')
        assert item.order == 6


# ---------------------------------------------------------------------------
# _create_indicator_form_item
# NOTE: get_field_value(name) uses default prefix 'add_ind_modal-'.
#       get_field_value(name, '') uses prefix '' -> looks for bare field name.
# ---------------------------------------------------------------------------

class TestCreateIndicatorFormItem:
    def test_creates_indicator_with_defaults(self, app, mock_db, mock_ib):
        template, section = _mock_template(), _mock_section()
        form_data = _form(('allowed_disaggregation_options', 'total'))
        item = _create_indicator_form_item(template, section, form_data, 1)
        assert item is not None
        assert item.item_type == 'indicator'
        assert item.label == 'Indicator'
        assert item.type == 'number'

    def test_creates_indicator_with_label(self, app, mock_db, mock_ib):
        # label uses get_field_value('label', '') -> prefix '' -> key 'label'
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('label', 'My Custom Label'),
            ('allowed_disaggregation_options', 'total'),
        )
        item = _create_indicator_form_item(template, section, form_data, 1)
        assert item.label == 'My Custom Label'

    def test_creates_indicator_with_bank(self, app, mock_db):
        # indicator_bank_id uses get_field_value('indicator_bank_id') default prefix
        template, section = _mock_template(), _mock_section()
        mock_bank = MagicMock()
        mock_bank.id = 42
        mock_bank.name = "Bank Name"
        mock_bank.type = "percentage"
        mock_bank.unit = "%"
        mock_bank.indicator_type_id = 1
        mock_bank.indicator_unit_id = 2

        form_data = _form(
            ('add_ind_modal-indicator_bank_id', '42'),
            ('allowed_disaggregation_options', 'total'),
        )
        with patch(f'{_BASE}.IndicatorBank') as MockIB:
            MockIB.query.get.return_value = mock_bank
            item = _create_indicator_form_item(template, section, form_data, 1)

        assert item.label == "Bank Name"
        assert item.type == "percentage"
        assert item.indicator_bank_id == 42

    def test_order_from_form_data(self, app, mock_db, mock_ib):
        # order uses get_field_value('order', '') -> prefix '' -> key 'order'
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('order', '7'),
            ('allowed_disaggregation_options', 'total'),
        )
        item = _create_indicator_form_item(template, section, form_data, 1)
        assert item.order == 7.0

    def test_custom_definition_stored(self, app, mock_db, mock_ib):
        # definition uses get_field_value('definition', '') -> key 'definition'
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('definition', 'My definition text'),
            ('allowed_disaggregation_options', 'total'),
        )
        item = _create_indicator_form_item(template, section, form_data, 1)
        assert item.definition == 'My definition text'

    def test_allow_over_100_set_from_form(self, app, mock_db, mock_ib):
        # allow_over_100 uses get_field_value('allow_over_100', '') -> key 'allow_over_100'
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('allow_over_100', 'true'),
            ('allowed_disaggregation_options', 'total'),
        )
        item = _create_indicator_form_item(template, section, form_data, 1)
        assert item.config['allow_over_100'] is True

    def test_allow_over_100_from_config_json(self, app, mock_db, mock_ib):
        template, section = _mock_template(), _mock_section()
        config = json.dumps({'allow_over_100': True})
        form_data = _form(
            ('config', config),
            ('allowed_disaggregation_options', 'total'),
        )
        item = _create_indicator_form_item(template, section, form_data, 1)
        assert item.config['allow_over_100'] is True

    def test_disaggregation_options_set_via_prefix(self, app, mock_db, mock_ib):
        # disagg options are read via form_data.getlist (both prefixed and unprefixed)
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('add_ind_modal-allowed_disaggregation_options', 'age'),
            ('add_ind_modal-allowed_disaggregation_options', 'gender'),
        )
        item = _create_indicator_form_item(template, section, form_data, 1)
        assert 'age' in item.config['allowed_disaggregation_options']
        assert 'gender' in item.config['allowed_disaggregation_options']

    def test_age_groups_config_stored(self, app, mock_db, mock_ib):
        # age_groups_config uses get_field_value('age_groups_config') default prefix
        template, section = _mock_template(), _mock_section()
        age_cfg = json.dumps({"groups": ["0-5", "6-17"]})
        form_data = _form(
            ('add_ind_modal-age_groups_config', age_cfg),
            ('allowed_disaggregation_options', 'total'),
        )
        item = _create_indicator_form_item(template, section, form_data, 1)
        assert item.config['age_groups_config'] == {"groups": ["0-5", "6-17"]}

    def test_age_groups_config_invalid_json_stored_as_string(self, app, mock_db, mock_ib):
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('add_ind_modal-age_groups_config', 'invalid-json'),
            ('allowed_disaggregation_options', 'total'),
        )
        item = _create_indicator_form_item(template, section, form_data, 1)
        assert item.config['age_groups_config'] == 'invalid-json'

    def test_relevance_condition_meaningful(self, app, mock_db, mock_ib):
        # relevance_condition uses get_field_value('relevance_condition', '') -> key 'relevance_condition'
        template, section = _mock_template(), _mock_section()
        cond = json.dumps({"conditions": [{"item_id": "5"}]})
        form_data = _form(
            ('relevance_condition', cond),
            ('allowed_disaggregation_options', 'total'),
        )
        item = _create_indicator_form_item(template, section, form_data, 1)
        assert item.relevance_condition == cond

    def test_relevance_condition_not_meaningful_is_null(self, app, mock_db, mock_ib):
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('relevance_condition', '{}'),
            ('allowed_disaggregation_options', 'total'),
        )
        item = _create_indicator_form_item(template, section, form_data, 1)
        assert item.relevance_condition is None

    def test_label_translations_stored_and_filtered(self, app, mock_db, mock_ib):
        # label_translations uses get_field_value('label_translations', '') -> 'label_translations'
        template, section = _mock_template(), _mock_section()
        lt = json.dumps({"en": "English", "xx_bad": "Bad"})
        form_data = _form(
            ('label_translations', lt),
            ('allowed_disaggregation_options', 'total'),
        )
        with app.test_request_context():
            app.config['SUPPORTED_LANGUAGES'] = ['en']
            item = _create_indicator_form_item(template, section, form_data, 1)
        assert item.label_translations == {"en": "English"}

    def test_invalid_bank_id_ignored(self, app, mock_db, mock_ib):
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('add_ind_modal-indicator_bank_id', 'not-a-number'),
            ('allowed_disaggregation_options', 'total'),
        )
        item = _create_indicator_form_item(template, section, form_data, 1)
        assert item is not None
        assert item.indicator_bank_id is None

    def test_privacy_stored_in_config(self, app, mock_db, mock_ib):
        # privacy uses get_field_value('privacy', '') -> key 'privacy'
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('privacy', 'public'),
            ('allowed_disaggregation_options', 'total'),
        )
        item = _create_indicator_form_item(template, section, form_data, 1)
        assert item.config['privacy'] == 'public'

    def test_default_value_stored(self, app, mock_db, mock_ib):
        # default_value uses get_field_value('default_value', '') -> key 'default_value'
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('default_value', '100'),
            ('allowed_disaggregation_options', 'total'),
        )
        item = _create_indicator_form_item(template, section, form_data, 1)
        assert item.config['default_value'] == '100'


# ---------------------------------------------------------------------------
# _create_question_form_item
# NOTE: get_field_value(name) uses default prefix 'add_q_modal-'.
#       get_field_value(name, '') uses prefix '' -> bare field name.
# ---------------------------------------------------------------------------

class TestCreateQuestionFormItem:
    def test_creates_text_question(self, app, mock_db):
        # question_type uses default prefix; label uses prefix ''
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('label', 'My Question'),
            ('add_q_modal-question_type', 'text'),
        )
        item = _create_question_form_item(template, section, form_data, 1)
        assert item is not None
        assert item.item_type == 'question'
        assert item.type == 'text'
        assert item.label == 'My Question'

    def test_missing_question_type_returns_none(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = _form(('label', 'My Question'))
        item = _create_question_form_item(template, section, form_data, 1)
        assert item is None

    def test_invalid_question_type_returns_none(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('label', 'My Question'),
            ('add_q_modal-question_type', 'invalid_type'),
        )
        item = _create_question_form_item(template, section, form_data, 1)
        assert item is None

    def test_blank_question_allows_empty_label(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = _form(('add_q_modal-question_type', 'blank'))
        item = _create_question_form_item(template, section, form_data, 1)
        assert item is not None
        assert item.label == ''

    def test_non_blank_empty_label_gets_default(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = _form(('add_q_modal-question_type', 'number'))
        item = _create_question_form_item(template, section, form_data, 1)
        assert item.label == 'Question'

    def test_single_choice_manual_options(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        opts = [{"label": "A", "value": "a"}]
        form_data = _form(
            ('label', 'Choice Q'),
            ('add_q_modal-question_type', 'single_choice'),
            ('add_q_modal-options_source', 'manual'),
            ('add_q_modal-options_json', json.dumps(opts)),
        )
        item = _create_question_form_item(template, section, form_data, 1)
        assert item.options_json == opts
        assert item.lookup_list_id is None

    def test_single_choice_non_list_options_cleared(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('label', 'Choice Q'),
            ('add_q_modal-question_type', 'single_choice'),
            ('add_q_modal-options_source', 'manual'),
            ('add_q_modal-options_json', json.dumps({"not": "a list"})),
        )
        item = _create_question_form_item(template, section, form_data, 1)
        assert item.options_json is None

    def test_calculated_list_with_plugin_lookup(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('label', 'Currency Q'),
            ('add_q_modal-question_type', 'single_choice'),
            ('add_q_modal-options_source', 'calculated'),
            ('add_q_modal-lookup_list_id', 'reporting_currency'),
            ('add_q_modal-list_display_column', 'code'),
        )
        item = _create_question_form_item(template, section, form_data, 1)
        assert item.lookup_list_id == 'reporting_currency'
        assert item.list_display_column == 'code'
        assert item.options_json is None

    def test_calculated_list_reporting_currency_default_display_column(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('label', 'Currency Q'),
            ('add_q_modal-question_type', 'single_choice'),
            ('add_q_modal-options_source', 'calculated'),
            ('add_q_modal-lookup_list_id', 'reporting_currency'),
        )
        item = _create_question_form_item(template, section, form_data, 1)
        assert item.list_display_column == 'code'

    def test_calculated_list_generic_plugin_default_display_name(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('label', 'Generic List Q'),
            ('add_q_modal-question_type', 'single_choice'),
            ('add_q_modal-options_source', 'calculated'),
            ('add_q_modal-lookup_list_id', 'some_plugin_list'),
        )
        item = _create_question_form_item(template, section, form_data, 1)
        assert item.list_display_column == 'name'

    def test_calculated_list_with_db_lookup(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('label', 'DB List Q'),
            ('add_q_modal-question_type', 'single_choice'),
            ('add_q_modal-options_source', 'calculated'),
            ('add_q_modal-lookup_list_id', '10'),
            ('add_q_modal-list_display_column', 'title'),
        )
        with patch(f'{_BASE}.LookupList') as MockLL:
            mock_ll = MagicMock()
            mock_ll.columns_config = [{'name': 'title'}]
            MockLL.query.get.return_value = mock_ll
            item = _create_question_form_item(template, section, form_data, 1)
        assert item.lookup_list_id == 10

    def test_list_filters_json_stored(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        filters = json.dumps([{"field": "active", "value": "1"}])
        form_data = _form(
            ('label', 'List Q'),
            ('add_q_modal-question_type', 'multiple_choice'),
            ('add_q_modal-options_source', 'calculated'),
            ('add_q_modal-lookup_list_id', 'my_list'),
            ('add_q_modal-list_filters_json', filters),
        )
        item = _create_question_form_item(template, section, form_data, 1)
        assert item.list_filters_json is not None

    def test_list_filters_invalid_json_cleared(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('label', 'List Q'),
            ('add_q_modal-question_type', 'single_choice'),
            ('add_q_modal-options_source', 'calculated'),
            ('add_q_modal-lookup_list_id', 'my_list'),
            ('add_q_modal-list_filters_json', 'invalid'),
        )
        item = _create_question_form_item(template, section, form_data, 1)
        assert item.list_filters_json is None

    def test_order_from_form_data(self, app, mock_db):
        # order uses get_field_value('order', '') -> key 'order'
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('add_q_modal-question_type', 'text'),
            ('order', '3'),
        )
        item = _create_question_form_item(template, section, form_data, 1)
        assert item.order == 3.0

    def test_allow_over_100_set_from_direct_field(self, app, mock_db):
        # allow_over_100 uses get_field_value('allow_over_100', '') -> key 'allow_over_100'
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('add_q_modal-question_type', 'number'),
            ('allow_over_100', 'on'),
        )
        item = _create_question_form_item(template, section, form_data, 1)
        assert item.config['allow_over_100'] is True


# ---------------------------------------------------------------------------
# _create_document_field_form_item
# NOTE: get_field_value(name) uses default prefix 'doc_field-'.
#       get_field_value(name, '') uses prefix '' -> bare field name.
# ---------------------------------------------------------------------------

class TestCreateDocumentFieldFormItem:
    def test_creates_with_defaults(self, app, mock_db, mock_fs):
        template, section = _mock_template(), _mock_section()
        item = _create_document_field_form_item(template, section, _form(), 1)
        assert item is not None
        assert item.item_type == 'document_field'
        assert item.label == 'Document Field'

    def test_creates_with_label(self, app, mock_db, mock_fs):
        # label uses get_field_value('label', '') -> key 'label'
        template, section = _mock_template(), _mock_section()
        form_data = _form(('label', 'My Doc Field'))
        item = _create_document_field_form_item(template, section, form_data, 1)
        assert item.label == 'My Doc Field'

    def test_max_documents_stored(self, app, mock_db, mock_fs):
        # max_documents uses get_field_value('max_documents', '') -> key 'max_documents'
        template, section = _mock_template(), _mock_section()
        form_data = _form(('max_documents', '5'))
        item = _create_document_field_form_item(template, section, form_data, 1)
        assert item.config['max_documents'] == 5

    def test_invalid_max_documents_is_none(self, app, mock_db, mock_fs):
        template, section = _mock_template(), _mock_section()
        form_data = _form(('max_documents', 'xyz'))
        item = _create_document_field_form_item(template, section, form_data, 1)
        assert item.config['max_documents'] is None

    def test_show_year_flag(self, app, mock_db, mock_fs):
        # show_year uses get_field_value('show_year', '') -> key 'show_year'
        template, section = _mock_template(), _mock_section()
        form_data = _form(('show_year', 'true'))
        item = _create_document_field_form_item(template, section, form_data, 1)
        assert item.config['show_year'] is True

    def test_preset_period_assignment_mode(self, app, mock_db, mock_fs):
        # preset_period_mode_value uses get_field_value(..., '') -> unprefixed key
        template, section = _mock_template(), _mock_section()
        form_data = _form(('preset_period_mode_value', 'assignment'))
        item = _create_document_field_form_item(template, section, form_data, 1)
        assert item.config['preset_period_use_assignment'] is True
        assert item.config['preset_period'] is None

    def test_preset_period_custom_mode(self, app, mock_db, mock_fs):
        template, section = _mock_template(), _mock_section()
        form_data = _form(
            ('preset_period_mode', 'custom'),
            ('preset_period', '2025'),
        )
        item = _create_document_field_form_item(template, section, form_data, 1)
        assert item.config['preset_period'] == '2025'
        assert item.config['preset_period_use_assignment'] is False

    def test_document_type_stored(self, app, mock_db, mock_fs):
        # document_type uses get_field_value('document_type', '') -> key 'document_type'
        template, section = _mock_template(), _mock_section()
        form_data = _form(('document_type', 'report'))
        item = _create_document_field_form_item(template, section, form_data, 1)
        assert item.config['document_type'] == 'report'

    def test_relevance_condition_meaningful(self, app, mock_db, mock_fs):
        # relevance_condition uses get_field_value(..., '') -> key 'relevance_condition'
        template, section = _mock_template(), _mock_section()
        cond = json.dumps({"conditions": [{"item_id": "5"}]})
        form_data = _form(('relevance_condition', cond))
        item = _create_document_field_form_item(template, section, form_data, 1)
        assert item.relevance_condition == cond

    def test_section_id_override_from_form(self, app, mock_db, mock_fs):
        # section_id uses get_field_value('section_id') default prefix 'doc_field-'
        template = _mock_template()
        section1 = MagicMock(id=1, version_id=1)
        form_data = _form(('doc_field-section_id', '2'))
        item = _create_document_field_form_item(template, section1, form_data, 1)
        assert item.section_id == 2

    def test_order_from_form(self, app, mock_db, mock_fs):
        # order uses get_field_value('order', '') -> key 'order'
        template, section = _mock_template(), _mock_section()
        form_data = _form(('order', '4'))
        item = _create_document_field_form_item(template, section, form_data, 1)
        assert item.order == 4.0


# ---------------------------------------------------------------------------
# _create_matrix_form_item
# ---------------------------------------------------------------------------

class TestCreateMatrixFormItem:
    def test_creates_with_defaults(self, app, mock_db, mock_fs):
        template, section = _mock_template(), _mock_section()
        item = _create_matrix_form_item(template, section, ImmutableMultiDict([]), 1)
        assert item is not None
        assert item.item_type == 'matrix'
        assert item.label == 'Matrix Table'

    def test_creates_with_label(self, app, mock_db, mock_fs):
        template, section = _mock_template(), _mock_section()
        form_data = ImmutableMultiDict([('label', 'My Matrix')])
        item = _create_matrix_form_item(template, section, form_data, 1)
        assert item.label == 'My Matrix'

    def test_matrix_config_parsed(self, app, mock_db, mock_fs):
        template, section = _mock_template(), _mock_section()
        mc = {"type": "matrix", "rows": ["R1", "R2"], "columns": [{"name": "C1"}]}
        form_data = ImmutableMultiDict([('matrix_config', json.dumps(mc))])
        item = _create_matrix_form_item(template, section, form_data, 1)
        assert item.config['matrix_config']['rows'] == ["R1", "R2"]

    def test_invalid_matrix_config_uses_defaults(self, app, mock_db, mock_fs):
        template, section = _mock_template(), _mock_section()
        form_data = ImmutableMultiDict([('matrix_config', 'invalid-json')])
        item = _create_matrix_form_item(template, section, form_data, 1)
        assert item.config['matrix_config']['type'] == 'matrix'
        assert item.config['matrix_config']['rows'] == []

    def test_list_library_mode_sets_lookup_fields(self, app, mock_db, mock_fs):
        template, section = _mock_template(), _mock_section()
        mc = {
            "type": "matrix",
            "row_mode": "list_library",
            "lookup_list_id": 7,
            "list_display_column": "name",
            "list_filters": [{"field": "active"}],
            "columns": []
        }
        form_data = ImmutableMultiDict([('matrix_config', json.dumps(mc))])
        item = _create_matrix_form_item(template, section, form_data, 1)
        assert item.lookup_list_id == 7
        assert item.list_display_column == "name"

    def test_relevance_condition_set(self, app, mock_db, mock_fs):
        template, section = _mock_template(), _mock_section()
        cond = json.dumps({"conditions": [{"item_id": "10"}]})
        form_data = ImmutableMultiDict([('relevance_condition', cond)])
        item = _create_matrix_form_item(template, section, form_data, 1)
        assert item.relevance_condition == cond

    def test_order_from_form(self, app, mock_db, mock_fs):
        template, section = _mock_template(), _mock_section()
        form_data = ImmutableMultiDict([('order', '5')])
        item = _create_matrix_form_item(template, section, form_data, 1)
        assert item.order == 5.0


# ---------------------------------------------------------------------------
# _create_plugin_form_item
# ---------------------------------------------------------------------------

class TestCreatePluginFormItem:
    def test_creates_plugin_item(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = ImmutableMultiDict([('label', 'My Plugin'), ('description', 'Plugin desc')])
        item = _create_plugin_form_item(template, section, form_data, 'plugin_interactive_map', 1)
        assert item is not None
        assert item.item_type == 'plugin_interactive_map'
        assert item.label == 'My Plugin'

    def test_creates_plugin_with_default_label(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = ImmutableMultiDict([])
        item = _create_plugin_form_item(template, section, form_data, 'plugin_interactive_map', 1)
        # plugin_type = 'interactive_map'; 'interactive_map'.title() = 'Interactive_Map'
        assert item.label == 'Interactive_Map Field'

    def test_plugin_config_parsed(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        cfg = {"zoom": 10, "center": [0, 0]}
        form_data = ImmutableMultiDict([('plugin_config', json.dumps(cfg))])
        item = _create_plugin_form_item(template, section, form_data, 'plugin_interactive_map', 1)
        assert item.config['plugin_config'] == cfg

    def test_invalid_plugin_config_defaults_empty(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = ImmutableMultiDict([('plugin_config', 'invalid-json')])
        item = _create_plugin_form_item(template, section, form_data, 'plugin_interactive_map', 1)
        assert item.config['plugin_config'] == {}

    def test_allow_over_100_set(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = ImmutableMultiDict([('allow_over_100', 'true')])
        item = _create_plugin_form_item(template, section, form_data, 'plugin_numeric', 1)
        assert item.config['allow_over_100'] is True

    def test_allow_over_100_from_config_json(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = ImmutableMultiDict([('config', json.dumps({'allow_over_100': True}))])
        item = _create_plugin_form_item(template, section, form_data, 'plugin_numeric', 1)
        assert item.config['allow_over_100'] is True

    def test_relevance_condition_set(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        cond = json.dumps({"conditions": [{"item_id": "5"}]})
        form_data = ImmutableMultiDict([('relevance_condition', cond)])
        item = _create_plugin_form_item(template, section, form_data, 'plugin_text', 1)
        assert item.relevance_condition == cond

    def test_validation_condition_set(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        cond = json.dumps({"conditions": [{"item_id": "5"}]})
        form_data = ImmutableMultiDict([
            ('validation_condition', cond),
            ('validation_message', 'Must be filled'),
        ])
        item = _create_plugin_form_item(template, section, form_data, 'plugin_text', 1)
        assert item.validation_condition == cond
        assert item.validation_message == 'Must be filled'

    def test_validation_message_translations_set(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = ImmutableMultiDict([
            ('validation_message', 'Must be filled'),
            ('validation_message_translations', json.dumps({'fr': 'Doit être rempli'})),
        ])
        item = _create_plugin_form_item(template, section, form_data, 'plugin_text', 1)
        assert item.validation_message == 'Must be filled'
        assert item.validation_message_translations == {'fr': 'Doit être rempli'}

    def test_order_from_form(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = ImmutableMultiDict([('order', '8')])
        item = _create_plugin_form_item(template, section, form_data, 'plugin_map', 1)
        assert item.order == 8.0

    def test_privacy_stored(self, app, mock_db):
        template, section = _mock_template(), _mock_section()
        form_data = ImmutableMultiDict([('privacy', 'public')])
        item = _create_plugin_form_item(template, section, form_data, 'plugin_map', 1)
        assert item.config['privacy'] == 'public'
