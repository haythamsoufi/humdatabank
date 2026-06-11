"""Unit tests for app/forms/form_builder/field_forms.py — targets 100% coverage."""
import json
import pytest
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.unit]


def _make_mock_indicator(id_=1, name='Test Indicator', type_='Number', unit='people'):
    ib = MagicMock()
    ib.id = id_
    ib.name = name
    ib.type = type_
    ib.unit = unit
    return ib


def _make_mock_lookup_list(id_=1, name='Test List'):
    ll = MagicMock()
    ll.id = id_
    ll.name = name
    return ll


# ---------------------------------------------------------------------------
# IndicatorForm
# ---------------------------------------------------------------------------

class TestIndicatorForm:
    def _make_form(self, app, data=None, choices=None):
        with patch('app.forms.form_builder.field_forms.IndicatorBank') as mock_ib:
            mock_ib.query.order_by.return_value.all.return_value = []
            from app.forms.form_builder.field_forms import IndicatorForm
            form = IndicatorForm(
                data=data or {},
                indicator_bank_choices_with_unit=choices or [],
            )
            form.section_id.choices = [(1, 'Section 1')]
            form.indicator_bank_id.choices = [('1', 'Indicator 1')]
            return form

    def test_instantiation_no_choices(self, app):
        with app.app_context():
            with patch('app.forms.form_builder.field_forms.IndicatorBank') as mock_ib:
                mock_ib.query.order_by.return_value.all.return_value = []
                from app.forms.form_builder.field_forms import IndicatorForm
                form = IndicatorForm(data={})
                assert form is not None

    def test_choices_from_db_when_no_kwargs(self, app):
        with app.app_context():
            ib = _make_mock_indicator()
            with patch('app.forms.form_builder.field_forms.IndicatorBank') as mock_ib:
                mock_ib.query.order_by.return_value.all.return_value = [ib]
                from app.forms.form_builder.field_forms import IndicatorForm
                form = IndicatorForm(data={})
                assert len(form.indicator_bank_id.choices) > 0

    def test_choices_from_kwargs_override_db(self, app):
        with app.app_context():
            choices = [{'value': 5, 'label': 'My Indicator', 'type': 'Number', 'unit': 'people'}]
            with patch('app.forms.form_builder.field_forms.IndicatorBank') as mock_ib:
                mock_ib.query.order_by.return_value.all.return_value = []
                from app.forms.form_builder.field_forms import IndicatorForm
                form = IndicatorForm(data={}, indicator_bank_choices_with_unit=choices)
                choice_values = [c[0] for c in form.indicator_bank_id.choices]
                assert '5' in choice_values

    def test_db_exception_falls_back_to_empty(self, app):
        with app.app_context():
            with patch('app.forms.form_builder.field_forms.IndicatorBank') as mock_ib:
                mock_ib.query.order_by.side_effect = RuntimeError('db down')
                from app.forms.form_builder.field_forms import IndicatorForm
                form = IndicatorForm(data={})
                assert 'No standard indicators available' in form.indicator_bank_id.choices[0][1]

    def test_adds_layout_fields(self, app):
        with app.app_context():
            with patch('app.forms.form_builder.field_forms.IndicatorBank') as mock_ib:
                mock_ib.query.order_by.return_value.all.return_value = []
                from app.forms.form_builder.field_forms import IndicatorForm
                form = IndicatorForm(data={})
                assert hasattr(form, 'layout_column_width') or hasattr(IndicatorForm, 'layout_column_width')

    def test_adds_data_availability_fields(self, app):
        with app.app_context():
            with patch('app.forms.form_builder.field_forms.IndicatorBank') as mock_ib:
                mock_ib.query.order_by.return_value.all.return_value = []
                from app.forms.form_builder.field_forms import IndicatorForm
                form = IndicatorForm(data={})
                assert hasattr(form, 'allow_data_not_available') or hasattr(IndicatorForm, 'allow_data_not_available')

    def test_section_id_choices_empty_by_default(self, app):
        with app.app_context():
            with patch('app.forms.form_builder.field_forms.IndicatorBank') as mock_ib:
                mock_ib.query.order_by.return_value.all.return_value = []
                from app.forms.form_builder.field_forms import IndicatorForm
                form = IndicatorForm(data={})
                assert form.section_id.choices == []


class TestIndicatorFormValidateAgeGroupsConfig:
    def test_no_indicator_no_age_option_passes(self, app):
        with app.app_context():
            with patch('app.forms.form_builder.field_forms.IndicatorBank') as mock_ib:
                mock_ib.query.order_by.return_value.all.return_value = []
                from app.forms.form_builder.field_forms import IndicatorForm
                form = IndicatorForm(data={})
                form.indicator_bank_id.data = None
                form.allowed_disaggregation_options.data = ['total']
                field = MagicMock()
                field.data = ''
                form.validate_age_groups_config(field)

    def test_indicator_from_kwargs_used(self, app):
        with app.app_context():
            choices = [{'value': 1, 'label': 'People Indicator', 'type': 'Number', 'unit': 'people'}]
            with patch('app.forms.form_builder.field_forms.IndicatorBank') as mock_ib:
                mock_ib.query.order_by.return_value.all.return_value = []
                from app.forms.form_builder.field_forms import IndicatorForm
                form = IndicatorForm(data={}, indicator_bank_choices_with_unit=choices)
                form.indicator_bank_id.data = 1
                form.allowed_disaggregation_options.data = ['total']
                field = MagicMock()
                field.data = ''
                with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
                    form.validate_age_groups_config(field)

    def test_indicator_from_db_fallback(self, app):
        with app.app_context():
            with patch('app.forms.form_builder.field_forms.IndicatorBank') as mock_ib:
                mock_indicator = _make_mock_indicator()
                mock_ib.query.order_by.return_value.all.return_value = []
                mock_ib.query.get.return_value = mock_indicator
                from app.forms.form_builder.field_forms import IndicatorForm
                form = IndicatorForm(data={}, indicator_bank_choices_with_unit=[])
                form.indicator_bank_id.data = 1
                form.allowed_disaggregation_options.data = ['total']
                field = MagicMock()
                field.data = ''
                with patch('app.utils.indicator_utils.supports_disaggregation', return_value=True):
                    form.validate_age_groups_config(field)


# ---------------------------------------------------------------------------
# QuestionForm
# ---------------------------------------------------------------------------

class TestQuestionForm:
    def _mock_lookup(self):
        return patch('app.forms.form_builder.field_forms.LookupList.query') 

    def test_instantiation(self, app):
        with app.app_context():
            with self._mock_lookup() as mock_q:
                mock_q.order_by.return_value.all.return_value = []
                from app.forms.form_builder.field_forms import QuestionForm
                form = QuestionForm(data={})
                assert form is not None

    def test_lookup_list_choices_populated(self, app):
        with app.app_context():
            ll = _make_mock_lookup_list()
            with self._mock_lookup() as mock_q:
                mock_q.order_by.return_value.all.return_value = [ll]
                from app.forms.form_builder.field_forms import QuestionForm
                form = QuestionForm(data={})
                assert any(ll.name in str(c) for c in form.lookup_list_id.choices)

    def test_plugin_choices_added(self, app):
        with app.app_context():
            with self._mock_lookup() as mock_q:
                mock_q.order_by.return_value.all.return_value = []
                # Set form_integration on the actual app since current_app is a proxy
                mock_integration = MagicMock()
                mock_integration.get_plugin_lookup_lists.return_value = [
                    {'id': 'plugin_list_1', 'name': 'Plugin List'}
                ]
                app.form_integration = mock_integration
                try:
                    from app.forms.form_builder.field_forms import QuestionForm
                    form = QuestionForm(data={})
                    choice_ids = [str(c[0]) for c in form.lookup_list_id.choices]
                    assert 'plugin_list_1' in choice_ids
                finally:
                    if hasattr(app, 'form_integration'):
                        delattr(app, 'form_integration')

    def test_plugin_choices_fallback_on_exception(self, app):
        with app.app_context():
            with self._mock_lookup() as mock_q:
                mock_q.order_by.return_value.all.return_value = []
                # Set form_integration that raises to trigger the except fallback
                mock_integration = MagicMock()
                mock_integration.get_plugin_lookup_lists.side_effect = RuntimeError('integration down')
                app.form_integration = mock_integration
                try:
                    from app.forms.form_builder.field_forms import QuestionForm
                    form = QuestionForm(data={})
                    choice_ids = [str(c[0]) for c in form.lookup_list_id.choices]
                    assert 'emergency_operations' in choice_ids
                finally:
                    if hasattr(app, 'form_integration'):
                        delattr(app, 'form_integration')

    def test_system_choices_present(self, app):
        with app.app_context():
            with self._mock_lookup() as mock_q:
                mock_q.order_by.return_value.all.return_value = []
                from app.forms.form_builder.field_forms import QuestionForm
                form = QuestionForm(data={})
                choice_ids = [str(c[0]) for c in form.lookup_list_id.choices]
                assert 'country_map' in choice_ids
                assert 'indicator_bank' in choice_ids
                assert 'national_society' in choice_ids


class TestQuestionFormValidateOptionsJson:
    def _make_form(self, app, data=None):
        with patch('app.forms.form_builder.field_forms.LookupList.query') as mock_q:
            mock_q.order_by.return_value.all.return_value = []
            from app.forms.form_builder.field_forms import QuestionForm
            form = QuestionForm(data=data or {})
            form.section_id.choices = [(1, 'Section 1')]
            return form

    def test_valid_options_for_single_choice(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'single_choice'
            form.options_source.data = 'manual'
            field = MagicMock()
            field.data = json.dumps(['Option A', 'Option B'])
            form.validate_options_json(field)

    def test_missing_options_for_single_choice_raises(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'single_choice'
            form.options_source.data = 'manual'
            field = MagicMock()
            field.data = ''
            from wtforms.validators import ValidationError
            with pytest.raises(ValidationError, match="Options are required"):
                form.validate_options_json(field)

    def test_empty_array_for_single_choice_raises(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'single_choice'
            form.options_source.data = 'manual'
            field = MagicMock()
            field.data = json.dumps([])
            from wtforms.validators import ValidationError
            with pytest.raises(ValidationError, match="non-empty JSON array"):
                form.validate_options_json(field)

    def test_invalid_json_raises(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'single_choice'
            form.options_source.data = 'manual'
            field = MagicMock()
            field.data = 'not json'
            from wtforms.validators import ValidationError
            with pytest.raises(ValidationError, match="Invalid JSON"):
                form.validate_options_json(field)

    def test_non_list_json_raises(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'single_choice'
            form.options_source.data = 'manual'
            field = MagicMock()
            field.data = json.dumps({'key': 'value'})
            from wtforms.validators import ValidationError
            with pytest.raises(ValidationError, match="non-empty JSON array"):
                form.validate_options_json(field)

    def test_text_type_skips_options_validation(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'text'
            form.options_source.data = 'manual'
            field = MagicMock()
            field.data = ''
            form.validate_options_json(field)  # should not raise

    def test_calculated_source_requires_lookup_list(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'single_choice'
            form.options_source.data = 'calculated'
            form.lookup_list_id.data = None
            field = MagicMock()
            field.data = ''
            from wtforms.validators import ValidationError
            with pytest.raises(ValidationError, match="lookup list must be selected"):
                form.validate_options_json(field)

    def test_calculated_source_system_choice_valid(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'single_choice'
            form.options_source.data = 'calculated'
            form.lookup_list_id.data = 'country_map'
            form.list_display_column.data = 'name'
            field = MagicMock()
            field.data = ''
            form.validate_options_json(field)  # should not raise

    def test_calculated_source_no_display_column_raises(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'single_choice'
            form.options_source.data = 'calculated'
            form.lookup_list_id.data = 'country_map'
            form.list_display_column.data = ''
            field = MagicMock()
            field.data = ''
            from wtforms.validators import ValidationError
            with pytest.raises(ValidationError, match="display column must be selected"):
                form.validate_options_json(field)

    def test_calculated_source_numeric_db_id(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'single_choice'
            form.options_source.data = 'calculated'
            form.lookup_list_id.data = 5
            form.list_display_column.data = 'label'
            field = MagicMock()
            field.data = ''
            form.validate_options_json(field)  # should not raise

    def test_calculated_source_unknown_plugin_id_raises(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'single_choice'
            form.options_source.data = 'calculated'
            form.lookup_list_id.data = 'unknown_plugin'
            form.list_display_column.data = 'col'
            field = MagicMock()
            field.data = ''
            mock_integration = MagicMock()
            mock_integration.get_plugin_lookup_lists.return_value = []
            app.form_integration = mock_integration
            try:
                from wtforms.validators import ValidationError
                with pytest.raises(ValidationError, match="Invalid lookup list ID"):
                    form.validate_options_json(field)
            finally:
                if hasattr(app, 'form_integration'):
                    delattr(app, 'form_integration')

    def test_calculated_source_plugin_exception_falls_back(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'single_choice'
            form.options_source.data = 'calculated'
            form.lookup_list_id.data = 'unknown_plugin'
            form.list_display_column.data = 'col'
            field = MagicMock()
            field.data = ''
            # No form_integration set -> exception -> falls back to system_choice_ids check
            app_had_integration = hasattr(app, 'form_integration')
            if app_had_integration:
                orig = app.form_integration
                delattr(app, 'form_integration')
            try:
                # Override get_plugin_lookup_lists to raise exception
                mock_integration = MagicMock()
                mock_integration.get_plugin_lookup_lists.side_effect = RuntimeError('no integration')
                app.form_integration = mock_integration
                from wtforms.validators import ValidationError
                with pytest.raises(ValidationError):
                    form.validate_options_json(field)
            finally:
                if app_had_integration:
                    app.form_integration = orig
                elif hasattr(app, 'form_integration'):
                    delattr(app, 'form_integration')

    def test_multiple_choice_type_also_requires_options(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'multiple_choice'
            form.options_source.data = 'manual'
            field = MagicMock()
            field.data = ''
            from wtforms.validators import ValidationError
            with pytest.raises(ValidationError):
                form.validate_options_json(field)


class TestQuestionFormValidateLabel:
    def _make_form(self, app):
        with patch('app.forms.form_builder.field_forms.LookupList.query') as mock_q:
            mock_q.order_by.return_value.all.return_value = []
            from app.forms.form_builder.field_forms import QuestionForm
            form = QuestionForm(data={})
            return form

    def test_blank_type_allows_empty_label(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'blank'
            field = MagicMock()
            field.data = ''
            form.validate_label(field)  # should not raise

    def test_non_blank_requires_label(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'text'
            field = MagicMock()
            field.data = ''
            from wtforms.validators import ValidationError
            with pytest.raises(ValidationError, match="required"):
                form.validate_label(field)

    def test_label_too_short_raises(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'text'
            field = MagicMock()
            field.data = 'ab'
            from wtforms.validators import ValidationError
            with pytest.raises(ValidationError, match="at least 3 characters"):
                form.validate_label(field)

    def test_valid_label_passes(self, app):
        with app.app_context():
            form = self._make_form(app)
            form.question_type.data = 'text'
            field = MagicMock()
            field.data = 'What is your name?'
            form.validate_label(field)  # should not raise


# ---------------------------------------------------------------------------
# DocumentFieldForm
# ---------------------------------------------------------------------------

class TestDocumentFieldForm:
    def test_instantiation(self, app):
        with app.app_context():
            from app.forms.form_builder.field_forms import DocumentFieldForm
            form = DocumentFieldForm(data={})
            assert form is not None

    def test_section_id_choices_empty(self, app):
        with app.app_context():
            from app.forms.form_builder.field_forms import DocumentFieldForm
            form = DocumentFieldForm(data={})
            assert form.section_id.choices == []

    def test_valid_data(self, app):
        with app.app_context():
            from app.forms.form_builder.field_forms import DocumentFieldForm
            form = DocumentFieldForm(data={
                'label': 'My Document',
            })
            form.section_id.choices = [(1, 'Section 1')]
            form.section_id.data = 1
            assert form.validate() is True

    def test_missing_label_fails(self, app):
        with app.app_context():
            from app.forms.form_builder.field_forms import DocumentFieldForm
            form = DocumentFieldForm(data={})
            form.section_id.choices = [(1, 'Section 1')]
            form.section_id.data = 1
            assert form.validate() is False
            assert 'label' in form.errors

    def test_has_layout_and_skip_logic_fields(self, app):
        with app.app_context():
            from app.forms.form_builder.field_forms import DocumentFieldForm
            form = DocumentFieldForm(data={})
            assert hasattr(form, 'relevance_condition') or hasattr(DocumentFieldForm, 'relevance_condition')


# ---------------------------------------------------------------------------
# MatrixForm
# ---------------------------------------------------------------------------

class TestMatrixForm:
    def test_instantiation(self, app):
        with app.app_context():
            from app.forms.form_builder.field_forms import MatrixForm
            form = MatrixForm(data={})
            assert form is not None

    def test_section_id_choices_empty(self, app):
        with app.app_context():
            from app.forms.form_builder.field_forms import MatrixForm
            form = MatrixForm(data={})
            assert form.section_id.choices == []

    def test_valid_data(self, app):
        with app.app_context():
            from app.forms.form_builder.field_forms import MatrixForm
            form = MatrixForm(data={})
            form.section_id.choices = [(1, 'Section 1')]
            form.section_id.data = 1
            assert form.validate() is True

    def test_has_data_availability_fields(self, app):
        with app.app_context():
            from app.forms.form_builder.field_forms import MatrixForm
            form = MatrixForm(data={})
            assert hasattr(form, 'allow_data_not_available') or hasattr(MatrixForm, 'allow_data_not_available')


# ---------------------------------------------------------------------------
# PluginItemForm
# ---------------------------------------------------------------------------

class TestPluginItemForm:
    def test_instantiation(self, app):
        with app.app_context():
            from app.forms.form_builder.field_forms import PluginItemForm
            form = PluginItemForm(data={})
            assert form is not None

    def test_section_id_choices_empty(self, app):
        with app.app_context():
            from app.forms.form_builder.field_forms import PluginItemForm
            form = PluginItemForm(data={})
            assert form.section_id.choices == []

    def test_has_layout_and_availability_fields(self, app):
        with app.app_context():
            from app.forms.form_builder.field_forms import PluginItemForm
            form = PluginItemForm(data={})
            assert hasattr(form, 'allow_data_not_available') or hasattr(PluginItemForm, 'allow_data_not_available')

    def test_valid_data(self, app):
        with app.app_context():
            from app.forms.form_builder.field_forms import PluginItemForm
            form = PluginItemForm(data={})
            form.section_id.choices = [(1, 'Section 1')]
            form.section_id.data = 1
            assert form.validate() is True
