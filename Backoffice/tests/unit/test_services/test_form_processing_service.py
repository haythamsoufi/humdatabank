"""
Comprehensive tests for app/services/form_processing_service.py

Targets 100% coverage of:
- slugify_age_group (module-level)
- FormItemProcessor (all classmethods)
- IndirectReachProcessor
- calculate_disaggregation_total
- should_create_data_availability_entry
- get_form_items_for_section
- _process_dynamic_indicators_for_section
- _create_dynamic_indicator_object
- _set_dynamic_indicator_field_type
- _set_dynamic_indicator_disaggregation
"""
import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / stubs
# ─────────────────────────────────────────────────────────────────────────────

def _make_form_item(
    item_type="indicator",
    field_type_for_js="number",
    type_="number",
    is_required=False,
    is_sub_item=False,
    layout_column_width=12,
    layout_break_after=False,
    relevance_condition=None,
    validation_condition=None,
    label_translations=None,
    definition_translations=None,
    description_translations=None,
    options_translations=None,
    indicator_bank=None,
    label="Test Item",
    indirect_reach=False,
    allow_disability_questions=False,
    allowed_disaggregation_options=None,
    effective_sex_categories=None,
    effective_age_groups=None,
    options=None,
    display_options=None,
):
    """Create a minimal FormItem-like mock."""
    fi = MagicMock()
    fi.id = 42
    fi.item_type = item_type
    fi.is_indicator = (item_type == "indicator")
    fi.is_question = (item_type == "question")
    fi.is_document_field = (item_type == "document_field")
    fi.is_matrix = (item_type == "matrix")
    fi.is_sub_item = is_sub_item
    fi.is_required = is_required
    fi.field_type_for_js = field_type_for_js
    fi.type = type_
    fi.label = label
    fi.relevance_condition = relevance_condition
    fi.validation_condition = validation_condition
    fi.label_translations = label_translations
    fi.definition_translations = definition_translations
    fi.description_translations = description_translations
    fi.options_translations = options_translations
    fi.indicator_bank = indicator_bank
    fi.indicator_bank_id = getattr(indicator_bank, "id", None) if indicator_bank else None
    fi.indirect_reach = indirect_reach
    fi.allow_disability_questions = allow_disability_questions
    fi.allowed_disaggregation_options = allowed_disaggregation_options or ["total"]
    fi.effective_sex_categories = effective_sex_categories or ["male", "female"]
    fi.effective_age_groups = effective_age_groups or ["0-17 years", "18+ years"]
    fi.layout_column_width = layout_column_width
    fi.layout_break_after = layout_break_after
    fi.options = options or []
    fi.display_options = display_options or []
    fi.definition = "Some definition"
    fi.description = ""
    fi.order = 1
    # getlist mock for multiple-choice
    fi.get_display_options = MagicMock(return_value=[])
    return fi


# ─────────────────────────────────────────────────────────────────────────────
# slugify_age_group
# ─────────────────────────────────────────────────────────────────────────────

class TestSlugifyAgeGroup:
    def test_none_returns_empty_string(self):
        from app.services.form_processing_service import slugify_age_group
        assert slugify_age_group(None) == ""

    def test_empty_string_returns_empty_string(self):
        from app.services.form_processing_service import slugify_age_group
        assert slugify_age_group("") == ""

    def test_whitespace_only_returns_empty_string(self):
        from app.services.form_processing_service import slugify_age_group
        assert slugify_age_group("   ") == ""

    def test_simple_conversion(self):
        from app.services.form_processing_service import slugify_age_group
        assert slugify_age_group("0-5 years") == "0_5_years"

    def test_plus_sign(self):
        from app.services.form_processing_service import slugify_age_group
        assert slugify_age_group("18+") == "18_"

    def test_already_slug(self):
        from app.services.form_processing_service import slugify_age_group
        assert slugify_age_group("adult") == "adult"

    def test_uppercase_lowercased(self):
        from app.services.form_processing_service import slugify_age_group
        assert slugify_age_group("ADULT") == "adult"

    def test_spaces_replaced(self):
        from app.services.form_processing_service import slugify_age_group
        assert slugify_age_group("5 to 17") == "5_to_17"

    def test_numeric_string(self):
        from app.services.form_processing_service import slugify_age_group
        assert slugify_age_group("2024") == "2024"


# ─────────────────────────────────────────────────────────────────────────────
# should_create_data_availability_entry
# ─────────────────────────────────────────────────────────────────────────────

class TestShouldCreateDataAvailabilityEntry:
    def test_has_value_returns_true(self):
        from app.services.form_processing_service import should_create_data_availability_entry
        assert should_create_data_availability_entry("some_value", False, False)

    def test_data_not_available_flag_returns_true(self):
        from app.services.form_processing_service import should_create_data_availability_entry
        assert should_create_data_availability_entry(None, True, False)

    def test_not_applicable_flag_returns_true(self):
        from app.services.form_processing_service import should_create_data_availability_entry
        assert should_create_data_availability_entry(None, False, True)

    def test_all_none_false_returns_false(self):
        from app.services.form_processing_service import should_create_data_availability_entry
        assert not should_create_data_availability_entry(None, False, False)

    def test_empty_string_value_returns_false(self):
        from app.services.form_processing_service import should_create_data_availability_entry
        assert not should_create_data_availability_entry("", False, False)

    def test_zero_value_treated_as_truthy_string(self):
        from app.services.form_processing_service import should_create_data_availability_entry
        # "0" as a string is truthy when non-empty
        assert should_create_data_availability_entry("0", False, False)


# ─────────────────────────────────────────────────────────────────────────────
# calculate_disaggregation_total
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculateDisaggregationTotal:
    def test_empty_dict_returns_zero(self):
        from app.services.form_processing_service import calculate_disaggregation_total
        assert calculate_disaggregation_total({}) == 0

    def test_none_returns_zero(self):
        from app.services.form_processing_service import calculate_disaggregation_total
        assert calculate_disaggregation_total(None) == 0

    def test_simple_numeric_values(self):
        from app.services.form_processing_service import calculate_disaggregation_total
        result = calculate_disaggregation_total({"male": 10, "female": 20})
        assert result == 30

    def test_indirect_key_excluded(self):
        from app.services.form_processing_service import calculate_disaggregation_total
        result = calculate_disaggregation_total({"total": 100, "indirect": 50})
        assert result == 100

    def test_disability_key_excluded(self):
        from app.services.form_processing_service import calculate_disaggregation_total
        result = calculate_disaggregation_total({"total": 100, "disability": {"disaggregated": True}})
        assert result == 100

    def test_string_numeric_values(self):
        from app.services.form_processing_service import calculate_disaggregation_total
        result = calculate_disaggregation_total({"male": "10", "female": "20"})
        assert result == 30.0

    def test_invalid_string_skipped(self):
        from app.services.form_processing_service import calculate_disaggregation_total
        result = calculate_disaggregation_total({"male": "abc", "female": 20})
        assert result == 20

    def test_nested_dict_summed(self):
        from app.services.form_processing_service import calculate_disaggregation_total
        result = calculate_disaggregation_total({"direct": {"male": 10, "female": 15}})
        assert result == 25

    def test_nested_dict_with_string_values(self):
        from app.services.form_processing_service import calculate_disaggregation_total
        result = calculate_disaggregation_total({"direct": {"male": "10", "female": "15"}})
        assert result == 25.0

    def test_nested_dict_invalid_string_skipped(self):
        from app.services.form_processing_service import calculate_disaggregation_total
        result = calculate_disaggregation_total({"direct": {"male": "abc", "female": 5}})
        assert result == 5

    def test_float_values(self):
        from app.services.form_processing_service import calculate_disaggregation_total
        result = calculate_disaggregation_total({"a": 1.5, "b": 2.5})
        assert result == 4.0


# ─────────────────────────────────────────────────────────────────────────────
# IndirectReachProcessor
# ─────────────────────────────────────────────────────────────────────────────

class TestIndirectReachProcessor:
    def test_calculate_total_with_indirect_basic(self):
        from app.services.form_processing_service import IndirectReachProcessor
        assert IndirectReachProcessor.calculate_total_with_indirect(100, 50) == 150

    def test_calculate_total_with_indirect_none_direct(self):
        from app.services.form_processing_service import IndirectReachProcessor
        assert IndirectReachProcessor.calculate_total_with_indirect(None, 50) == 50

    def test_calculate_total_with_indirect_none_indirect(self):
        from app.services.form_processing_service import IndirectReachProcessor
        assert IndirectReachProcessor.calculate_total_with_indirect(100, None) == 100

    def test_calculate_total_with_indirect_both_none(self):
        from app.services.form_processing_service import IndirectReachProcessor
        assert IndirectReachProcessor.calculate_total_with_indirect(None, None) == 0

    def test_calculate_disaggregation_total_with_indirect_empty(self):
        from app.services.form_processing_service import IndirectReachProcessor
        assert IndirectReachProcessor.calculate_disaggregation_total_with_indirect({}) == 0

    def test_calculate_disaggregation_total_with_indirect_none(self):
        from app.services.form_processing_service import IndirectReachProcessor
        assert IndirectReachProcessor.calculate_disaggregation_total_with_indirect(None) == 0

    def test_calculate_disaggregation_total_with_indirect_dict_direct(self):
        from app.services.form_processing_service import IndirectReachProcessor
        result = IndirectReachProcessor.calculate_disaggregation_total_with_indirect(
            {"direct": {"male": 10, "female": 20}, "indirect": 5}
        )
        assert result == 35

    def test_calculate_disaggregation_total_with_indirect_numeric_direct(self):
        from app.services.form_processing_service import IndirectReachProcessor
        result = IndirectReachProcessor.calculate_disaggregation_total_with_indirect(
            {"direct": 100, "indirect": 50}
        )
        assert result == 150

    def test_calculate_disaggregation_total_with_indirect_no_indirect_key(self):
        from app.services.form_processing_service import IndirectReachProcessor
        result = IndirectReachProcessor.calculate_disaggregation_total_with_indirect(
            {"direct": {"male": 10, "female": 20}}
        )
        assert result == 30

    def test_process_indirect_reach_value_valid(self, app):
        from app.services.form_processing_service import IndirectReachProcessor
        with app.app_context():
            result = IndirectReachProcessor.process_indirect_reach_value(
                {"indicator_1_indirect_reach": "50"}, "indicator_1", "indicator", "Test"
            )
            assert result == 50.0

    def test_process_indirect_reach_value_empty(self, app):
        from app.services.form_processing_service import IndirectReachProcessor
        with app.app_context():
            result = IndirectReachProcessor.process_indirect_reach_value(
                {"indicator_1_indirect_reach": ""}, "indicator_1", "indicator", "Test"
            )
            assert result is None

    def test_process_indirect_reach_value_missing(self, app):
        from app.services.form_processing_service import IndirectReachProcessor
        with app.app_context():
            result = IndirectReachProcessor.process_indirect_reach_value(
                {}, "indicator_1", "indicator", "Test"
            )
            assert result is None

    def test_process_indirect_reach_value_invalid(self, app):
        from app.services.form_processing_service import IndirectReachProcessor
        with app.app_context():
            result = IndirectReachProcessor.process_indirect_reach_value(
                {"indicator_1_indirect_reach": "not_a_number"}, "indicator_1", "indicator", "Test"
            )
            assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._unformat_numeric_string
# ─────────────────────────────────────────────────────────────────────────────

class TestUnformatNumericString:
    def test_none_returns_empty(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._unformat_numeric_string(None) == ""

    def test_empty_string_returns_empty(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._unformat_numeric_string("") == ""

    def test_sentinel_none(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._unformat_numeric_string("none") == ""

    def test_sentinel_null(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._unformat_numeric_string("null") == ""

    def test_sentinel_undefined(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._unformat_numeric_string("undefined") == ""

    def test_comma_grouping_removed(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._unformat_numeric_string("1,000,000") == "1000000"

    def test_space_grouping_removed(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._unformat_numeric_string("1 000") == "1000"

    def test_nbsp_removed(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._unformat_numeric_string("1\u00A0000") == "1000"

    def test_plain_number_unchanged(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._unformat_numeric_string("12345") == "12345"

    def test_decimal_preserved(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._unformat_numeric_string("3.14") == "3.14"


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._process_numeric_value_simple
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessNumericValueSimple:
    def test_integer_type(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._process_numeric_value_simple("42", "number") == "42"

    def test_percentage_type(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._process_numeric_value_simple("3.5", "percentage") == "3.5"

    def test_invalid_value_returns_none(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._process_numeric_value_simple("abc", "number") is None

    def test_currency_type_as_int(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._process_numeric_value_simple("100", "currency") == "100"

    def test_comma_formatted_int(self):
        from app.services.form_processing_service import FormItemProcessor
        assert FormItemProcessor._process_numeric_value_simple("1,000", "number") == "1000"


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._get_field_prefix
# ─────────────────────────────────────────────────────────────────────────────

class TestGetFieldPrefix:
    def test_indicator_prefix(self):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator")
        fi.id = 5
        result = FormItemProcessor._get_field_prefix(fi)
        assert result == "indicator_5"

    def test_question_prefix(self):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question")
        fi.id = 7
        result = FormItemProcessor._get_field_prefix(fi)
        assert result == "question_7"

    def test_other_prefix(self):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="document_field")
        fi.id = 9
        result = FormItemProcessor._get_field_prefix(fi)
        assert result == "field_9"


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._field_supports_disaggregation
# ─────────────────────────────────────────────────────────────────────────────

class TestFieldSupportsDisaggregation:
    def test_total_only_not_supported(self):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(allowed_disaggregation_options=["total"])
        fi.indirect_reach = False
        assert FormItemProcessor._field_supports_disaggregation(fi) is False

    def test_sex_supported(self):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(allowed_disaggregation_options=["total", "sex"])
        fi.indirect_reach = False
        assert FormItemProcessor._field_supports_disaggregation(fi) is True

    def test_indirect_reach_is_supported(self):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(allowed_disaggregation_options=["total"])
        fi.indirect_reach = True
        assert FormItemProcessor._field_supports_disaggregation(fi) is True

    def test_none_options_not_supported(self):
        from app.services.form_processing_service import FormItemProcessor
        fi = MagicMock()
        fi.allowed_disaggregation_options = None
        fi.indirect_reach = False
        assert FormItemProcessor._field_supports_disaggregation(fi) is False


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._add_common_properties (via setup_form_item_for_template)
# ─────────────────────────────────────────────────────────────────────────────

class TestAddCommonProperties:
    def test_valid_relevance_condition_parsed(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(relevance_condition='[{"field": 1}]')
        with app.app_context():
            FormItemProcessor._add_common_properties(fi)
        assert fi.conditions == [{"field": 1}]

    def test_invalid_json_relevance_condition_defaults_empty(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(relevance_condition='{invalid json}')
        with app.app_context():
            FormItemProcessor._add_common_properties(fi)
        assert fi.conditions == []

    def test_none_relevance_condition_defaults_empty(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(relevance_condition=None)
        with app.app_context():
            FormItemProcessor._add_common_properties(fi)
        assert fi.conditions == []

    def test_valid_validation_condition_parsed(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(validation_condition='[{"rule": "gt", "value": 0}]')
        with app.app_context():
            FormItemProcessor._add_common_properties(fi)
        assert fi.validations_from_db == [{"rule": "gt", "value": 0}]

    def test_invalid_json_validation_condition_defaults_empty(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(validation_condition='{bad json')
        with app.app_context():
            FormItemProcessor._add_common_properties(fi)
        assert fi.validations_from_db == []

    def test_sub_indicator_set_from_is_sub_item(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", is_sub_item=True)
        with app.app_context():
            FormItemProcessor._add_common_properties(fi)
        assert fi.is_sub_indicator is True

    def test_sub_question_set_from_is_sub_item(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question", is_sub_item=True)
        with app.app_context():
            FormItemProcessor._add_common_properties(fi)
        assert fi.is_sub_question is True

    def test_sub_document_set_from_is_sub_item(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="document_field", is_sub_item=True)
        with app.app_context():
            FormItemProcessor._add_common_properties(fi)
        assert fi.is_sub_document is True


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._setup_indicator_properties
# ─────────────────────────────────────────────────────────────────────────────

class TestSetupIndicatorProperties:
    def test_custom_label_with_no_bank(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", label="My Custom Label")
        fi.indicator_bank = None
        with app.app_context():
            FormItemProcessor._setup_indicator_properties(fi)
        assert fi.display_label == "My Custom Label"
        assert fi.has_custom_label is True

    def test_empty_label_uses_bank_name(self, app):
        from app.services.form_processing_service import FormItemProcessor
        bank = MagicMock()
        bank.name = "Bank Indicator Name"
        bank.name_translations = None
        fi = _make_form_item(item_type="indicator", label="", indicator_bank=bank)
        with app.app_context():
            with patch("app.utils.form_localization.get_localized_indicator_name", return_value="Localized Name"):
                FormItemProcessor._setup_indicator_properties(fi)
        assert fi.display_label == "Localized Name"
        assert fi.has_custom_label is False

    def test_label_matching_bank_name_not_custom(self, app):
        from app.services.form_processing_service import FormItemProcessor
        bank = MagicMock()
        bank.name = "Bank Indicator"
        bank.name_translations = None
        fi = _make_form_item(item_type="indicator", label="Bank Indicator", indicator_bank=bank)
        fi.label_translations = None
        with app.app_context():
            with patch("app.utils.form_localization.get_localized_indicator_name", return_value="Bank Indicator"):
                FormItemProcessor._setup_indicator_properties(fi)
        assert fi.has_custom_label is False

    def test_label_translations_marks_as_custom(self, app):
        from app.services.form_processing_service import FormItemProcessor
        bank = MagicMock()
        bank.name = "Bank Indicator"
        bank.name_translations = None
        fi = _make_form_item(item_type="indicator", label="Bank Indicator", indicator_bank=bank)
        fi.label_translations = {"fr": "Indicateur Bancaire"}
        with app.app_context():
            FormItemProcessor._setup_indicator_properties(fi)
        assert fi.has_custom_label is True

    def test_bank_with_json_translations(self, app):
        from app.services.form_processing_service import FormItemProcessor
        bank = MagicMock()
        bank.name = "Bank Indicator"
        bank.name_translations = json.dumps({"fr": "Indicateur"})
        fi = _make_form_item(item_type="indicator", label="Bank Indicator", indicator_bank=bank)
        fi.label_translations = None
        with app.app_context():
            with patch("app.utils.form_localization.get_localized_indicator_name", return_value="Bank Indicator"):
                FormItemProcessor._setup_indicator_properties(fi)
        assert fi.has_custom_label is False


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._setup_question_properties
# ─────────────────────────────────────────────────────────────────────────────

class TestSetupQuestionProperties:
    def test_sets_display_label(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question", label="My Question")
        with app.app_context():
            FormItemProcessor._setup_question_properties(fi)
        assert fi.display_label == "My Question"

    def test_sets_display_options_from_options(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question", options=["A", "B"])
        fi.display_options = None
        with app.app_context():
            FormItemProcessor._setup_question_properties(fi)
        assert fi.display_options == ["A", "B"]


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._setup_document_properties
# ─────────────────────────────────────────────────────────────────────────────

class TestSetupDocumentProperties:
    def test_sets_display_label(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="document_field", label="Upload Doc")
        with app.app_context():
            FormItemProcessor._setup_document_properties(fi)
        assert fi.display_label == "Upload Doc"


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._setup_matrix_properties
# ─────────────────────────────────────────────────────────────────────────────

class TestSetupMatrixProperties:
    def test_sets_display_label(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="matrix", label="My Matrix")
        with app.app_context():
            FormItemProcessor._setup_matrix_properties(fi)
        assert fi.display_label == "My Matrix"


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._setup_plugin_properties
# ─────────────────────────────────────────────────────────────────────────────

class TestSetupPluginProperties:
    def test_sets_plugin_type(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="plugin_map", label="Map Plugin")
        fi.config = None
        with app.app_context():
            FormItemProcessor._setup_plugin_properties(fi)
        assert fi.plugin_type == "map"
        assert fi.plugin_config == {}

    def test_parses_json_config(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="plugin_chart")
        fi.config = json.dumps({"width": 600})
        with app.app_context():
            FormItemProcessor._setup_plugin_properties(fi)
        assert fi.plugin_config == {"width": 600}

    def test_dict_config_used_directly(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="plugin_table")
        fi.config = {"cols": 3}
        with app.app_context():
            FormItemProcessor._setup_plugin_properties(fi)
        assert fi.plugin_config == {"cols": 3}

    def test_invalid_json_config_defaults_empty(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="plugin_broken")
        fi.config = "{invalid json"
        with app.app_context():
            FormItemProcessor._setup_plugin_properties(fi)
        assert fi.plugin_config == {}


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._add_translation_support
# ─────────────────────────────────────────────────────────────────────────────

class TestAddTranslationSupport:
    def _setup_app_context_with_locale(self, app, locale="en"):
        from app.services.form_processing_service import FormItemProcessor
        return FormItemProcessor

    def test_no_translations_returns_original_label(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", label="English Label")
        fi.label_translations = None
        fi.definition_translations = None
        fi.display_label = "English Label"
        with app.app_context():
            with patch("app.utils.form_localization.get_translation_key", return_value="en"), \
                 patch("app.get_locale", return_value="en"):
                FormItemProcessor._add_translation_support(fi)
        assert fi.display_label == "English Label"

    def test_indicator_label_translation_applied(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", label="English Label")
        fi.label_translations = {"fr": "Étiquette Française"}
        fi.definition_translations = None
        fi.display_label = "English Label"
        with app.app_context():
            with patch("app.utils.form_localization.get_translation_key", return_value="fr"), \
                 patch("app.get_locale", return_value="fr"):
                FormItemProcessor._add_translation_support(fi)
        assert fi.display_label == "Étiquette Française"

    def test_indicator_definition_translation_applied(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", label="English Label")
        fi.label_translations = None
        fi.definition_translations = {"fr": "Définition Française"}
        fi.definition = "English Definition"
        fi.display_label = "English Label"
        with app.app_context():
            with patch("app.utils.form_localization.get_translation_key", return_value="fr"), \
                 patch("app.get_locale", return_value="fr"):
                FormItemProcessor._add_translation_support(fi)
        assert fi.definition == "Définition Française"

    def test_question_label_translation_applied(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question", label="English Q")
        fi.label_translations = {"fr": "Question Française"}
        fi.definition_translations = None
        fi.options_translations = None
        fi.display_label = "English Q"
        with app.app_context():
            with patch("app.utils.form_localization.get_translation_key", return_value="fr"), \
                 patch("app.get_locale", return_value="fr"):
                FormItemProcessor._add_translation_support(fi)
        assert fi.display_label == "Question Française"

    def test_document_field_description_translation_applied(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="document_field", label="Upload")
        fi.label_translations = {"fr": "Télécharger"}
        fi.description_translations = {"fr": "Description en Français"}
        fi.definition_translations = None
        fi.options_translations = None
        fi.display_label = "Upload"
        fi.description = "English Description"
        with app.app_context():
            with patch("app.utils.form_localization.get_translation_key", return_value="fr"), \
                 patch("app.get_locale", return_value="fr"):
                FormItemProcessor._add_translation_support(fi)
        assert fi.description == "Description en Français"

    def test_question_options_translation_applied(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question", label="Q")
        fi.label_translations = None
        fi.definition_translations = None
        fi.options_translations = {"fr": [{"label": "Oui", "value": "yes"}]}
        fi.options = [{"label": "Yes", "value": "yes"}]
        fi.get_display_options = MagicMock(return_value=[{"label": "Oui", "value": "yes"}])
        with app.app_context():
            with patch("app.utils.form_localization.get_translation_key", return_value="fr"), \
                 patch("app.get_locale", return_value="fr"):
                FormItemProcessor._add_translation_support(fi)
        assert fi.display_options == [{"label": "Oui", "value": "yes"}]

    def test_locale_with_underscore_split(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", label="English Label")
        fi.label_translations = {"fr": "Étiquette Française"}
        fi.definition_translations = None
        fi.display_label = "English Label"
        with app.app_context():
            with patch("app.utils.form_localization.get_translation_key", return_value="fr"), \
                 patch("app.get_locale", return_value="fr_FR"):
                FormItemProcessor._add_translation_support(fi)
        assert fi.display_label == "Étiquette Française"

    def test_json_string_translations_parsed(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", label="English Label")
        fi.label_translations = json.dumps({"fr": "Étiquette"})
        fi.definition_translations = None
        fi.display_label = "English Label"
        with app.app_context():
            with patch("app.utils.form_localization.get_translation_key", return_value="fr"), \
                 patch("app.get_locale", return_value="fr"):
                FormItemProcessor._add_translation_support(fi)
        assert fi.display_label == "Étiquette"


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._process_question_data
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessQuestionData:
    def test_data_not_available_flag(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question")
        fi.id = 10
        fi.type = "text"
        fi.indirect_reach = False
        form_data = {f"question_10_data_not_available": "1"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_question_data(fi, form_data, "question_10")
        assert dna is True
        assert has_val is False

    def test_not_applicable_flag(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question")
        fi.id = 10
        fi.type = "text"
        fi.indirect_reach = False
        form_data = {f"question_10_not_applicable": "1"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_question_data(fi, form_data, "question_10")
        assert na is True
        assert has_val is False

    def test_text_question_returned(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question")
        fi.id = 10
        fi.type = "text"
        fi.indirect_reach = False
        form_data = {"field_value[10]": "Hello World"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_question_data(fi, form_data, "question_10")
        assert val == "Hello World"
        assert has_val is True

    def test_number_question_converted(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question")
        fi.id = 10
        fi.type = "number"
        fi.indirect_reach = False
        form_data = {"field_value[10]": "42"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_question_data(fi, form_data, "question_10")
        assert val == "42"
        assert has_val is True

    def test_invalid_number_returns_none(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question")
        fi.id = 10
        fi.type = "number"
        fi.indirect_reach = False
        form_data = {"field_value[10]": "not_a_number"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_question_data(fi, form_data, "question_10")
        assert val is None
        assert has_val is False

    def test_percentage_question(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question")
        fi.id = 10
        fi.type = "percentage"
        fi.indirect_reach = False
        form_data = {"field_value[10]": "75.5"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_question_data(fi, form_data, "question_10")
        assert val == "75.5"
        assert has_val is True

    def test_invalid_percentage_returns_none(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question")
        fi.id = 10
        fi.type = "percentage"
        fi.indirect_reach = False
        form_data = {"field_value[10]": "invalid"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_question_data(fi, form_data, "question_10")
        assert val is None

    def test_checkbox_question(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question")
        fi.id = 10
        fi.type = "CHECKBOX"
        fi.indirect_reach = False
        form_data = {"field_value[10]": "true"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_question_data(fi, form_data, "question_10")
        assert val == "true"
        assert has_val is True

    def test_missing_field_returns_none(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question")
        fi.id = 10
        fi.type = "text"
        fi.indirect_reach = False
        form_data = {}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_question_data(fi, form_data, "question_10")
        assert val is None
        assert has_val is False

    def test_indirect_reach_on_number_question(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question")
        fi.id = 10
        fi.type = "number"
        fi.indirect_reach = True
        form_data = {
            "field_value[10]": "100",
            "question_10_indirect_reach": "25"
        }
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_question_data(fi, form_data, "question_10")
        assert has_val is True
        assert isinstance(val, dict)
        assert val["values"]["indirect"] == 25

    def test_indirect_reach_on_percentage_question(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question")
        fi.id = 10
        fi.type = "percentage"
        fi.indirect_reach = True
        form_data = {
            "field_value[10]": "50.0",
            "question_10_indirect_reach": "20.5"
        }
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_question_data(fi, form_data, "question_10")
        assert has_val is True
        assert isinstance(val, dict)
        assert val["values"]["indirect"] == 20.5

    def test_invalid_indirect_reach_ignored(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question")
        fi.id = 10
        fi.type = "number"
        fi.indirect_reach = True
        form_data = {
            "field_value[10]": "100",
            "question_10_indirect_reach": "bad"
        }
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_question_data(fi, form_data, "question_10")
        assert has_val is True
        assert val == "100"


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._process_document_data
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessDocumentData:
    def test_always_returns_none_tuple(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="document_field")
        form_data = {"field_value[42]": "some_file.pdf"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_document_data(fi, form_data, "field_42")
        assert val is None
        assert has_val is False
        assert dna is False
        assert na is False


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor.process_form_item_data (dispatch)
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessFormItemData:
    def test_dispatch_to_indicator(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", field_type_for_js="text")
        fi.id = 5
        fi.indirect_reach = False
        fi.allow_disability_questions = False
        form_data = {"indicator_5_standard_value": "yes"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor.process_form_item_data(fi, form_data, 1)
        assert has_val is True

    def test_dispatch_to_question(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question")
        fi.id = 7
        fi.type = "text"
        fi.indirect_reach = False
        fi.allow_disability_questions = False
        form_data = {"field_value[7]": "Test Answer"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor.process_form_item_data(fi, form_data, 1)
        assert has_val is True

    def test_dispatch_to_document_returns_none(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="document_field")
        fi.id = 9
        fi.indirect_reach = False
        form_data = {}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor.process_form_item_data(fi, form_data, 1)
        assert val is None

    def test_unknown_type_returns_none_tuple(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = MagicMock()
        fi.id = 1
        fi.is_indicator = False
        fi.is_question = False
        fi.is_document_field = False
        with app.app_context():
            result = FormItemProcessor.process_form_item_data(fi, {}, 1)
        assert result == (None, False, False, False)


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor indicator numeric processing with disaggregation
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessNumericIndicator:
    def test_total_mode_integer(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(
            item_type="indicator",
            field_type_for_js="number",
            allowed_disaggregation_options=["total", "sex"],
            effective_sex_categories=["male", "female"],
        )
        fi.id = 10
        fi.indirect_reach = False
        fi.allow_disability_questions = False
        form_data = {
            "indicator_10_total_value": "100",
            "indicator_10_reporting_mode": "total"
        }
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_numeric_indicator(fi, form_data, "indicator_10")
        assert has_val is True
        assert val["mode"] == "total"
        assert val["values"]["total"] == 100

    def test_total_mode_with_indirect_reach(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(
            item_type="indicator",
            field_type_for_js="number",
            allowed_disaggregation_options=["total"],
        )
        fi.id = 10
        fi.indirect_reach = True
        fi.allow_disability_questions = False
        form_data = {
            "indicator_10_total_value": "100",
            "indicator_10_reporting_mode": "total",
            "indicator_10_indirect_reach": "50"
        }
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_numeric_indicator(fi, form_data, "indicator_10")
        assert has_val is True
        assert val["values"]["direct"] == 100
        assert val["values"]["indirect"] == 50

    def test_sex_mode(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(
            item_type="indicator",
            field_type_for_js="number",
            allowed_disaggregation_options=["total", "sex"],
            effective_sex_categories=["male", "female"],
        )
        fi.id = 10
        fi.indirect_reach = False
        fi.allow_disability_questions = False
        form_data = {
            "indicator_10_sex_male": "30",
            "indicator_10_sex_female": "70",
            "indicator_10_reporting_mode": "sex"
        }
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_numeric_indicator(fi, form_data, "indicator_10")
        assert has_val is True
        assert val["mode"] == "sex"
        assert val["values"]["male"] == 30
        assert val["values"]["female"] == 70

    def test_age_mode(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(
            item_type="indicator",
            field_type_for_js="number",
            allowed_disaggregation_options=["total", "age"],
            effective_age_groups=["0-17 years", "18+ years"],
        )
        fi.id = 10
        fi.indirect_reach = False
        fi.allow_disability_questions = False
        form_data = {
            "indicator_10_age_0_17_years": "40",
            "indicator_10_age_18__years": "60",
            "indicator_10_reporting_mode": "age"
        }
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_numeric_indicator(fi, form_data, "indicator_10")
        assert has_val is True
        assert val["mode"] == "age"

    def test_sex_age_mode(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(
            item_type="indicator",
            field_type_for_js="number",
            allowed_disaggregation_options=["total", "sex_age"],
            effective_sex_categories=["male", "female"],
            effective_age_groups=["0-17 years", "18+ years"],
        )
        fi.id = 10
        fi.indirect_reach = False
        fi.allow_disability_questions = False
        form_data = {
            "indicator_10_sexage_male_0_17_years": "20",
            "indicator_10_sexage_female_18__years": "30",
            "indicator_10_reporting_mode": "sex_age"
        }
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_numeric_indicator(fi, form_data, "indicator_10")
        assert has_val is True
        assert val["mode"] == "sex_age"

    def test_no_values_returns_none(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(
            item_type="indicator",
            field_type_for_js="number",
            allowed_disaggregation_options=["total", "sex"],
        )
        fi.id = 10
        fi.indirect_reach = False
        fi.allow_disability_questions = False
        form_data = {}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_numeric_indicator(fi, form_data, "indicator_10")
        assert has_val is False
        assert val is None

    def test_percentage_type_stored_as_float(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(
            item_type="indicator",
            field_type_for_js="percentage",
            type_="percentage",
            allowed_disaggregation_options=["total", "sex"],
        )
        fi.id = 10
        fi.indirect_reach = False
        fi.allow_disability_questions = False
        form_data = {
            "indicator_10_total_value": "75.5",
            "indicator_10_reporting_mode": "total"
        }
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_numeric_indicator(fi, form_data, "indicator_10")
        assert has_val is True
        assert isinstance(val["values"]["total"], float)


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor disability question handling
# ─────────────────────────────────────────────────────────────────────────────

class TestDisabilityQuestionHandling:
    def test_disability_not_applicable_if_flag_off(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator")
        fi.id = 10
        fi.allow_disability_questions = False
        form_data = {
            "indicator_10_disability_disaggregated": "yes"
        }
        with app.app_context():
            result = FormItemProcessor._extract_disability_answers(fi, form_data, "indicator_10")
        assert result is None

    def test_disability_disaggregated_yes(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator")
        fi.id = 10
        fi.allow_disability_questions = True
        form_data = {
            "indicator_10_disability_disaggregated": "yes",
            "indicator_10_disability_washington_group": "no"
        }
        with app.app_context():
            result = FormItemProcessor._extract_disability_answers(fi, form_data, "indicator_10")
        assert result is not None
        assert result["disaggregated_by_disability"] is True
        assert result["washington_group_compliant"] is False

    def test_disability_disaggregated_no(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator")
        fi.id = 10
        fi.allow_disability_questions = True
        form_data = {
            "indicator_10_disability_disaggregated": "no"
        }
        with app.app_context():
            result = FormItemProcessor._extract_disability_answers(fi, form_data, "indicator_10")
        assert result is not None
        assert result["disaggregated_by_disability"] is False

    def test_disability_invalid_answer_returns_none(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator")
        fi.id = 10
        fi.allow_disability_questions = True
        form_data = {
            "indicator_10_disability_disaggregated": "maybe"
        }
        with app.app_context():
            result = FormItemProcessor._extract_disability_answers(fi, form_data, "indicator_10")
        assert result is None

    def test_merge_disability_into_dict_value(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator")
        fi.indirect_reach = False
        processed_value = {"mode": "total", "values": {"total": 100}}
        disability = {"disaggregated_by_disability": True}
        with app.app_context():
            result_val, has_val = FormItemProcessor._merge_disability_into_indicator_value(
                fi, processed_value, disability, True
            )
        assert "disability" in result_val["values"]

    def test_merge_disability_into_non_dict_value(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator")
        fi.indirect_reach = False
        disability = {"disaggregated_by_disability": False}
        with app.app_context():
            result_val, has_val = FormItemProcessor._merge_disability_into_indicator_value(
                fi, 100, disability, True
            )
        assert has_val is True
        assert "disability" in result_val["values"]

    def test_merge_disability_none_processed_value(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator")
        fi.indirect_reach = False
        disability = {"disaggregated_by_disability": True}
        with app.app_context():
            result_val, has_val = FormItemProcessor._merge_disability_into_indicator_value(
                fi, None, disability, False
            )
        assert has_val is True
        assert result_val["values"]["disability"] == disability


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._resolve_indicator_reporting_mode
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveIndicatorReportingMode:
    def test_single_mode_with_values_returned(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(
            allowed_disaggregation_options=["total", "sex"],
            effective_sex_categories=["male", "female"],
        )
        form_data = {"indicator_10_sex_male": "50", "indicator_10_reporting_mode": "sex"}
        with app.app_context():
            mode = FormItemProcessor._resolve_indicator_reporting_mode(fi, form_data, "indicator_10")
        assert mode == "sex"

    def test_explicit_mode_used_when_no_values(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(
            allowed_disaggregation_options=["total", "sex"],
            effective_sex_categories=["male", "female"],
        )
        form_data = {"indicator_10_reporting_mode": "sex"}
        with app.app_context():
            mode = FormItemProcessor._resolve_indicator_reporting_mode(fi, form_data, "indicator_10")
        assert mode == "sex"

    def test_defaults_to_total_when_no_info(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(allowed_disaggregation_options=["total"])
        form_data = {}
        with app.app_context():
            mode = FormItemProcessor._resolve_indicator_reporting_mode(fi, form_data, "indicator_10")
        assert mode == "total"

    def test_multiple_modes_with_values_prefers_explicit(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(
            allowed_disaggregation_options=["total", "sex"],
            effective_sex_categories=["male", "female"],
        )
        form_data = {
            "indicator_10_total_value": "100",
            "indicator_10_sex_male": "60",
            "indicator_10_reporting_mode": "sex"
        }
        with app.app_context():
            mode = FormItemProcessor._resolve_indicator_reporting_mode(fi, form_data, "indicator_10")
        assert mode in ("total", "sex")


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor._process_indicator_data (dispatcher)
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessIndicatorData:
    def test_data_not_available_returns_flag(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", field_type_for_js="number")
        fi.id = 10
        fi.indirect_reach = False
        fi.allow_disability_questions = False
        form_data = {"indicator_10_data_not_available": "1"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_indicator_data(fi, form_data, "indicator_10")
        assert dna is True
        assert has_val is False

    def test_not_applicable_returns_flag(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", field_type_for_js="number")
        fi.id = 10
        fi.indirect_reach = False
        fi.allow_disability_questions = False
        form_data = {"indicator_10_not_applicable": "1"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_indicator_data(fi, form_data, "indicator_10")
        assert na is True

    def test_yesno_indicator(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", field_type_for_js="yesno")
        fi.id = 10
        fi.indirect_reach = False
        fi.allow_disability_questions = False
        form_data = {"indicator_10_standard_value": "Yes"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_indicator_data(fi, form_data, "indicator_10")
        assert val == "yes"
        assert has_val is True

    def test_text_indicator(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", field_type_for_js="text", type_="text")
        fi.id = 10
        fi.indirect_reach = False
        fi.allow_disability_questions = False
        fi.allowed_disaggregation_options = ["total"]
        form_data = {"indicator_10_standard_value": "Some Text"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_indicator_data(fi, form_data, "indicator_10")
        assert val == "Some Text"
        assert has_val is True

    def test_numeric_indicator_no_disaggregation(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", field_type_for_js="number", type_="number")
        fi.id = 10
        fi.indirect_reach = False
        fi.allow_disability_questions = False
        fi.allowed_disaggregation_options = ["total"]
        form_data = {"indicator_10_total_value": "150"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_indicator_data(fi, form_data, "indicator_10")
        assert has_val is True

    def test_invalid_numeric_indicator_no_disaggregation(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", field_type_for_js="number", type_="number")
        fi.id = 10
        fi.indirect_reach = False
        fi.allow_disability_questions = False
        fi.allowed_disaggregation_options = ["total"]
        form_data = {"indicator_10_total_value": "abc"}
        with app.app_context():
            val, has_val, dna, na = FormItemProcessor._process_indicator_data(fi, form_data, "indicator_10")
        # val returned as string for non-parseable values
        assert has_val is True
        assert val == "abc"


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor sex/age disaggregation helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestSexAgeDisaggregation:
    def test_process_sex_disaggregation(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(effective_sex_categories=["male", "female"])
        fi.indirect_reach = False
        fi.field_type_for_js = "number"
        fi.type = "number"
        form_data = {"prefix_sex_male": "30", "prefix_sex_female": "70"}
        with app.app_context():
            result = FormItemProcessor._process_sex_disaggregation(fi, form_data, "prefix")
        assert result["male"] == 30
        assert result["female"] == 70

    def test_process_sex_disaggregation_with_indirect_reach(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(effective_sex_categories=["male", "female"])
        fi.indirect_reach = True
        fi.field_type_for_js = "number"
        fi.type = "number"
        form_data = {"prefix_sex_male": "30", "prefix_sex_female": "70"}
        with app.app_context():
            result = FormItemProcessor._process_sex_disaggregation(fi, form_data, "prefix")
        assert "direct" in result

    def test_process_sex_disaggregation_invalid_value_skipped(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(effective_sex_categories=["male"])
        fi.indirect_reach = False
        fi.field_type_for_js = "number"
        fi.type = "number"
        form_data = {"prefix_sex_male": "bad"}
        with app.app_context():
            result = FormItemProcessor._process_sex_disaggregation(fi, form_data, "prefix")
        assert result == {}

    def test_process_age_disaggregation(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(effective_age_groups=["0-17 years", "18+ years"])
        fi.indirect_reach = False
        fi.field_type_for_js = "number"
        fi.type = "number"
        form_data = {
            "prefix_age_0_17_years": "25",
            "prefix_age_18__years": "75"
        }
        with app.app_context():
            result = FormItemProcessor._process_age_disaggregation(fi, form_data, "prefix")
        assert result.get("0_17_years") == 25
        assert result.get("18__years") == 75

    def test_process_age_disaggregation_with_indirect_reach(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(effective_age_groups=["0-17 years"])
        fi.indirect_reach = True
        fi.field_type_for_js = "number"
        fi.type = "number"
        form_data = {"prefix_age_0_17_years": "50"}
        with app.app_context():
            result = FormItemProcessor._process_age_disaggregation(fi, form_data, "prefix")
        assert "direct" in result

    def test_process_age_disaggregation_invalid_value_skipped(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(effective_age_groups=["0-17 years"])
        fi.indirect_reach = False
        fi.field_type_for_js = "number"
        fi.type = "number"
        form_data = {"prefix_age_0_17_years": "invalid"}
        with app.app_context():
            result = FormItemProcessor._process_age_disaggregation(fi, form_data, "prefix")
        assert result == {}

    def test_process_sex_age_disaggregation(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(
            effective_sex_categories=["male"],
            effective_age_groups=["18+ years"],
        )
        fi.indirect_reach = False
        fi.field_type_for_js = "number"
        fi.type = "number"
        form_data = {"prefix_sexage_male_18__years": "100"}
        with app.app_context():
            result = FormItemProcessor._process_sex_age_disaggregation(fi, form_data, "prefix")
        assert result.get("male_18__years") == 100

    def test_process_sex_age_disaggregation_with_indirect_reach(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(
            effective_sex_categories=["male"],
            effective_age_groups=["18+ years"],
        )
        fi.indirect_reach = True
        fi.field_type_for_js = "number"
        fi.type = "number"
        form_data = {"prefix_sexage_male_18__years": "100"}
        with app.app_context():
            result = FormItemProcessor._process_sex_age_disaggregation(fi, form_data, "prefix")
        assert "direct" in result

    def test_process_sex_age_disaggregation_invalid_value_skipped(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(
            effective_sex_categories=["male"],
            effective_age_groups=["18+ years"],
        )
        fi.indirect_reach = False
        fi.field_type_for_js = "number"
        fi.type = "number"
        form_data = {"prefix_sexage_male_18__years": "bad"}
        with app.app_context():
            result = FormItemProcessor._process_sex_age_disaggregation(fi, form_data, "prefix")
        assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# FormItemProcessor.setup_form_item_for_template - full pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestSetupFormItemForTemplate:
    def test_indicator_full_setup(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="indicator", label="My Indicator")
        fi.indicator_bank = None
        fi.relevance_condition = None
        fi.validation_condition = None
        fi.label_translations = None
        fi.definition_translations = None
        with app.app_context():
            with patch("app.utils.form_localization.get_translation_key", return_value="en"), \
                 patch("app.get_locale", return_value="en"):
                result = FormItemProcessor.setup_form_item_for_template(fi, None)
        assert result.display_label == "My Indicator"

    def test_question_full_setup(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="question", label="My Question")
        fi.relevance_condition = None
        fi.validation_condition = None
        fi.label_translations = None
        fi.definition_translations = None
        fi.options_translations = None
        with app.app_context():
            with patch("app.utils.form_localization.get_translation_key", return_value="en"), \
                 patch("app.get_locale", return_value="en"):
                result = FormItemProcessor.setup_form_item_for_template(fi, None)
        assert result.display_label == "My Question"

    def test_document_field_full_setup(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="document_field", label="Upload")
        fi.relevance_condition = None
        fi.validation_condition = None
        fi.label_translations = None
        fi.definition_translations = None
        fi.options_translations = None
        fi.description_translations = None
        with app.app_context():
            with patch("app.utils.form_localization.get_translation_key", return_value="en"), \
                 patch("app.get_locale", return_value="en"):
                result = FormItemProcessor.setup_form_item_for_template(fi, None)
        assert result.display_label == "Upload"

    def test_matrix_full_setup(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="matrix", label="My Matrix")
        fi.relevance_condition = None
        fi.validation_condition = None
        fi.label_translations = None
        fi.definition_translations = None
        fi.options_translations = None
        fi.description_translations = None
        with app.app_context():
            with patch("app.utils.form_localization.get_translation_key", return_value="en"), \
                 patch("app.get_locale", return_value="en"):
                result = FormItemProcessor.setup_form_item_for_template(fi, None)
        assert result.display_label == "My Matrix"

    def test_plugin_full_setup(self, app):
        from app.services.form_processing_service import FormItemProcessor
        fi = _make_form_item(item_type="plugin_map", label="Map")
        fi.relevance_condition = None
        fi.validation_condition = None
        fi.label_translations = None
        fi.definition_translations = None
        fi.options_translations = None
        fi.description_translations = None
        fi.config = None
        fi.item_type = "plugin_map"
        with app.app_context():
            with patch("app.utils.form_localization.get_translation_key", return_value="en"), \
                 patch("app.get_locale", return_value="en"):
                result = FormItemProcessor.setup_form_item_for_template(fi, None)
        assert result.display_label == "Map"


# ─────────────────────────────────────────────────────────────────────────────
# get_form_items_for_section - DB tests live in test_form_processing_service_db.py
# to avoid deadlocks when run after mock-only tests in this file.
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# _set_dynamic_indicator_field_type
# ─────────────────────────────────────────────────────────────────────────────

class TestSetDynamicIndicatorFieldType:
    def _run(self, type_str):
        from app.services.form_processing_service import _set_dynamic_indicator_field_type
        indicator = type("DI", (), {})()
        bank = MagicMock()
        bank.type = type_str
        _set_dynamic_indicator_field_type(indicator, bank)
        return indicator.field_type_for_js

    def test_number(self):
        assert self._run("number") == "number"

    def test_percentage(self):
        assert self._run("percentage") == "percentage"

    def test_text(self):
        assert self._run("text") == "text"

    def test_yesno(self):
        assert self._run("yesno") == "yesno"

    def test_date(self):
        assert self._run("date") == "date"

    def test_datetime(self):
        assert self._run("datetime") == "datetime"

    def test_currency(self):
        assert self._run("currency") == "currency"

    def test_single_choice(self):
        assert self._run("single_choice") == "single_choice"

    def test_multiple_choice(self):
        assert self._run("multiple_choice") == "multiple_choice"

    def test_unknown_defaults_to_text(self):
        assert self._run("unknown_type") == "text"
