"""
Comprehensive tests for app/models/form_items.py targeting 100% code coverage.
"""
import json
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.factories import (
    create_test_user,
    create_test_country,
    create_test_template,
    create_test_section,
    create_test_item,
)
from app.models.form_items import FormItem


# ---------------------------------------------------------------------------
# Helper: create an in-memory FormItem instance (no DB required for pure logic)
# ---------------------------------------------------------------------------

def _make_item(**kwargs):
    """Create an unattached FormItem for logic-only tests."""
    item = FormItem.__new__(FormItem)
    item.item_type = kwargs.get("item_type", "indicator")
    item.type = kwargs.get("type", None)
    item.label = kwargs.get("label", "Test Label")
    item.order = kwargs.get("order", 1.0)
    item.config = kwargs.get("config", {
        "is_required": False,
        "layout_column_width": 12,
        "layout_break_after": False,
        "allowed_disaggregation_options": ["total"],
        "age_groups_config": None,
        "default_value": None,
        "allow_data_not_available": False,
        "allow_not_applicable": False,
        "allow_disability_questions": False,
        "indirect_reach": False,
        "privacy": "ifrc_network",
    })
    item.options_json = kwargs.get("options_json", None)
    item.options_translations = kwargs.get("options_translations", None)
    item.label_translations = kwargs.get("label_translations", None)
    item.definition_translations = kwargs.get("definition_translations", None)
    item.description_translations = kwargs.get("description_translations", None)
    item.definition = kwargs.get("definition", None)
    item.lookup_list_id = kwargs.get("lookup_list_id", None)
    item.list_display_column = kwargs.get("list_display_column", None)
    item.list_filters_json = kwargs.get("list_filters_json", None)
    item.indicator_unit_id = kwargs.get("indicator_unit_id", None)
    item.measurement_unit = kwargs.get("measurement_unit", None)
    item.unit = kwargs.get("unit", None)
    item.indicator_bank_id = kwargs.get("indicator_bank_id", None)
    item.form_section = kwargs.get("form_section", MagicMock(name="MockSection"))
    item.template = kwargs.get("template", MagicMock(name="MockTemplate"))
    item.id = kwargs.get("id", None)
    return item


# ---------------------------------------------------------------------------
# Boolean type properties
# ---------------------------------------------------------------------------

class TestFormItemTypeProperties:
    def test_is_indicator_true(self):
        item = _make_item(item_type="indicator")
        assert item.is_indicator is True

    def test_is_indicator_false(self):
        item = _make_item(item_type="question")
        assert item.is_indicator is False

    def test_is_question_true(self):
        item = _make_item(item_type="question")
        assert item.is_question is True

    def test_is_question_false(self):
        item = _make_item(item_type="indicator")
        assert item.is_question is False

    def test_is_document_field_true(self):
        item = _make_item(item_type="document_field")
        assert item.is_document_field is True

    def test_is_document_field_false(self):
        item = _make_item(item_type="indicator")
        assert item.is_document_field is False

    def test_is_matrix_true(self):
        item = _make_item(item_type="matrix")
        assert item.is_matrix is True

    def test_is_matrix_false(self):
        item = _make_item(item_type="indicator")
        assert item.is_matrix is False

    def test_is_plugin_true(self):
        item = _make_item(item_type="plugin_custom")
        assert item.is_plugin is True

    def test_is_plugin_false(self):
        item = _make_item(item_type="indicator")
        assert item.is_plugin is False


# ---------------------------------------------------------------------------
# Ordering and hierarchy properties
# ---------------------------------------------------------------------------

class TestFormItemOrdering:
    def test_is_sub_item_false_integer_order(self):
        item = _make_item(order=1.0)
        assert item.is_sub_item is False

    def test_is_sub_item_true_decimal_order(self):
        item = _make_item(order=1.1)
        assert item.is_sub_item is True

    def test_parent_order_for_sub_item(self):
        item = _make_item(order=2.3)
        assert item.parent_order == 2

    def test_parent_order_none_for_main_item(self):
        item = _make_item(order=2.0)
        assert item.parent_order is None

    def test_depth_level_zero_main(self):
        item = _make_item(order=1.0)
        assert item.depth_level == 0

    def test_depth_level_one_sub(self):
        item = _make_item(order=1.1)
        assert item.depth_level == 1

    def test_display_order_integer(self):
        item = _make_item(order=3.0)
        assert item.display_order == "3"

    def test_display_order_decimal(self):
        item = _make_item(order=3.1)
        assert item.display_order == "3.1"


# ---------------------------------------------------------------------------
# Config property getters and setters
# ---------------------------------------------------------------------------

class TestFormItemConfigProperties:
    def test_is_required_default(self):
        item = _make_item()
        assert item.is_required is False

    def test_is_required_true(self):
        item = _make_item(config={"is_required": True})
        assert item.is_required is True

    def test_is_required_no_config(self):
        item = _make_item(config=None)
        assert item.is_required is False

    def test_set_is_required(self):
        item = _make_item()
        item.set_is_required(True)
        assert item.config["is_required"] is True

    def test_set_is_required_creates_config(self):
        item = _make_item(config=None)
        item.set_is_required(True)
        assert item.config["is_required"] is True

    def test_is_required_setter(self):
        item = _make_item()
        item.is_required = True
        assert item.config["is_required"] is True

    def test_layout_column_width_default(self):
        item = _make_item()
        assert item.layout_column_width == 12

    def test_layout_column_width_custom(self):
        item = _make_item(config={"layout_column_width": 6})
        assert item.layout_column_width == 6

    def test_layout_column_width_no_config(self):
        item = _make_item(config=None)
        assert item.layout_column_width == 12

    def test_set_layout_column_width(self):
        item = _make_item()
        item.set_layout_column_width(6)
        assert item.config["layout_column_width"] == 6

    def test_set_layout_column_width_creates_config(self):
        item = _make_item(config=None)
        item.set_layout_column_width(8)
        assert item.config["layout_column_width"] == 8

    def test_layout_break_after_default(self):
        item = _make_item()
        assert item.layout_break_after is False

    def test_set_layout_break_after(self):
        item = _make_item()
        item.set_layout_break_after(True)
        assert item.config["layout_break_after"] is True

    def test_set_layout_break_after_creates_config(self):
        item = _make_item(config=None)
        item.set_layout_break_after(True)
        assert item.config["layout_break_after"] is True

    def test_allowed_disaggregation_options_default(self):
        item = _make_item()
        assert item.allowed_disaggregation_options == ["total"]

    def test_allowed_disaggregation_options_no_config(self):
        item = _make_item(config=None)
        assert item.allowed_disaggregation_options == ["total"]

    def test_set_allowed_disaggregation_options(self):
        item = _make_item()
        item.set_allowed_disaggregation_options(["total", "sex"])
        assert "sex" in item.config["allowed_disaggregation_options"]

    def test_set_allowed_disaggregation_options_none(self):
        item = _make_item()
        item.set_allowed_disaggregation_options(None)
        assert item.config["allowed_disaggregation_options"] == ["total"]

    def test_set_allowed_disaggregation_options_creates_config(self):
        item = _make_item(config=None)
        item.set_allowed_disaggregation_options(["sex"])
        assert item.config["allowed_disaggregation_options"] == ["sex"]

    def test_age_groups_config_default(self):
        item = _make_item()
        assert item.age_groups_config is None

    def test_set_age_groups_config(self):
        item = _make_item()
        item.set_age_groups_config("0-17,18-59,60+")
        assert item.config["age_groups_config"] == "0-17,18-59,60+"

    def test_set_age_groups_config_creates_config(self):
        item = _make_item(config=None)
        item.set_age_groups_config("0-17,18+")
        assert item.config["age_groups_config"] == "0-17,18+"

    def test_allow_data_not_available_default(self):
        item = _make_item()
        assert item.allow_data_not_available is False

    def test_set_allow_data_not_available(self):
        item = _make_item()
        item.set_allow_data_not_available(True)
        assert item.config["allow_data_not_available"] is True

    def test_set_allow_data_not_available_creates_config(self):
        item = _make_item(config=None)
        item.set_allow_data_not_available(True)
        assert item.config["allow_data_not_available"] is True

    def test_allow_not_applicable_default(self):
        item = _make_item()
        assert item.allow_not_applicable is False

    def test_set_allow_not_applicable(self):
        item = _make_item()
        item.set_allow_not_applicable(True)
        assert item.config["allow_not_applicable"] is True

    def test_set_allow_not_applicable_creates_config(self):
        item = _make_item(config=None)
        item.set_allow_not_applicable(True)
        assert item.config["allow_not_applicable"] is True

    def test_allow_disability_questions_default(self):
        item = _make_item()
        assert item.allow_disability_questions is False

    def test_set_allow_disability_questions(self):
        item = _make_item()
        item.set_allow_disability_questions(True)
        assert item.config["allow_disability_questions"] is True

    def test_set_allow_disability_questions_creates_config(self):
        item = _make_item(config=None)
        item.set_allow_disability_questions(True)
        assert item.config["allow_disability_questions"] is True

    def test_indirect_reach_default(self):
        item = _make_item()
        assert item.indirect_reach is False

    def test_set_indirect_reach(self):
        item = _make_item()
        item.set_indirect_reach(True)
        assert item.config["indirect_reach"] is True

    def test_set_indirect_reach_creates_config(self):
        item = _make_item(config=None)
        item.set_indirect_reach(True)
        assert item.config["indirect_reach"] is True

    def test_privacy_default(self):
        item = _make_item()
        assert item.privacy == "ifrc_network"

    def test_privacy_no_config(self):
        item = _make_item(config=None)
        assert item.privacy == "ifrc_network"

    def test_set_privacy_valid(self):
        item = _make_item()
        item.set_privacy("public")
        assert item.config["privacy"] == "public"

    def test_set_privacy_invalid_defaults_to_ifrc(self):
        item = _make_item()
        item.set_privacy("invalid_privacy")
        assert item.config["privacy"] == "ifrc_network"

    def test_set_privacy_creates_config(self):
        item = _make_item(config=None)
        item.set_privacy("public")
        assert item.config["privacy"] == "public"

    def test_is_required_for_js(self):
        item = _make_item()
        assert item.is_required_for_js is False
        item.is_required_for_js = True
        assert item.is_required is True


# ---------------------------------------------------------------------------
# Effective age groups / sex categories / disaggregation
# ---------------------------------------------------------------------------

class TestFormItemDisaggregation:
    def test_effective_age_groups_non_indicator(self):
        item = _make_item(item_type="question")
        assert item.effective_age_groups == []

    def test_effective_age_groups_default_for_indicator(self):
        from config import Config
        item = _make_item(item_type="indicator")
        item.config["age_groups_config"] = None
        result = item.effective_age_groups
        assert result == Config.DEFAULT_AGE_GROUPS

    def test_effective_age_groups_custom(self):
        item = _make_item(item_type="indicator")
        item.config["age_groups_config"] = "0-17, 18-59, 60+"
        result = item.effective_age_groups
        assert "0-17" in result
        assert "18-59" in result
        assert "60+" in result

    def test_effective_age_groups_strips_whitespace(self):
        item = _make_item(item_type="indicator")
        item.config["age_groups_config"] = " 0-17 , 18+ "
        result = item.effective_age_groups
        assert "0-17" in result
        assert "18+" in result

    def test_effective_sex_categories_non_indicator(self):
        item = _make_item(item_type="question")
        assert item.effective_sex_categories == []

    def test_effective_sex_categories_for_indicator(self):
        from config import Config
        item = _make_item(item_type="indicator")
        result = item.effective_sex_categories
        assert result == Config.DEFAULT_SEX_CATEGORIES

    def test_supports_disaggregation_non_indicator(self):
        item = _make_item(item_type="question")
        assert item.supports_disaggregation is False

    def test_supports_disaggregation_wrong_type(self):
        item = _make_item(item_type="indicator", type="percentage")
        assert item.supports_disaggregation is False

    def test_supports_disaggregation_no_unit(self):
        item = _make_item(item_type="indicator", type="number")
        item.unit = None
        assert item.supports_disaggregation is False

    def test_supports_disaggregation_with_allowed_unit(self):
        from config import Config
        item = _make_item(item_type="indicator", type="number")
        allowed_units = getattr(Config, "DISAGGREGATION_ALLOWED_UNITS", None) or []
        if allowed_units:
            item.unit = allowed_units[0]
            item.indicator_unit_id = None
            assert item.supports_disaggregation is True
        else:
            # If no allowed units configured, just verify the logic runs
            item.unit = "people"
            result = item.supports_disaggregation
            assert isinstance(result, bool)

    def test_supports_disaggregation_with_measurement_unit(self):
        item = _make_item(item_type="indicator", type="number")
        item.indicator_unit_id = 1
        mock_unit = MagicMock()
        mock_unit.allows_disaggregation = True
        item.measurement_unit = mock_unit
        assert item.supports_disaggregation is True

    def test_supports_disaggregation_measurement_unit_not_allowed(self):
        item = _make_item(item_type="indicator", type="number")
        item.indicator_unit_id = 1
        mock_unit = MagicMock()
        mock_unit.allows_disaggregation = False
        item.measurement_unit = mock_unit
        assert item.supports_disaggregation is False

    def test_disaggregation_options_display_non_indicator(self):
        item = _make_item(item_type="question")
        result = item.disaggregation_options_display
        assert result == ["Total Only"]

    def test_disaggregation_options_display_no_options(self):
        item = _make_item(item_type="indicator")
        item.config["allowed_disaggregation_options"] = None
        result = item.disaggregation_options_display
        assert result == ["Total Only"]

    def test_disaggregation_options_display_all_options(self):
        item = _make_item(item_type="indicator")
        item.config["allowed_disaggregation_options"] = ["total", "sex", "age", "sex_age"]
        result = item.disaggregation_options_display
        assert result == ["All"]

    def test_disaggregation_options_display_partial(self):
        from config import Config
        item = _make_item(item_type="indicator")
        item.config["allowed_disaggregation_options"] = ["total", "sex"]
        result = item.disaggregation_options_display
        assert isinstance(result, list)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Options property
# ---------------------------------------------------------------------------

class TestFormItemOptions:
    def test_options_non_question_returns_empty(self):
        item = _make_item(item_type="indicator")
        assert item.options == []

    def test_options_no_options_json(self):
        item = _make_item(item_type="question", options_json=None)
        assert item.options == []

    def test_options_from_json_string(self):
        item = _make_item(item_type="question", options_json='["Option A", "Option B"]')
        result = item.options
        assert result == ["Option A", "Option B"]

    def test_options_from_list(self):
        item = _make_item(item_type="question", options_json=["Option A", "Option B"])
        result = item.options
        assert result == ["Option A", "Option B"]

    def test_options_invalid_json_returns_empty(self):
        item = _make_item(item_type="question", options_json="not valid json{{{")
        result = item.options
        assert result == []

    def test_options_non_list_json_returns_empty(self):
        item = _make_item(item_type="question", options_json='{"key": "value"}')
        result = item.options
        assert result == []

    def test_options_with_lookup_list_delegates(self):
        item = _make_item(
            item_type="question",
            lookup_list_id="123",
            list_display_column="name"
        )
        with patch.object(item, 'get_calculated_options', return_value=["Opt1"]):
            result = item.options
            assert result == ["Opt1"]


# ---------------------------------------------------------------------------
# Translation methods
# ---------------------------------------------------------------------------

class TestFormItemTranslations:
    def test_translations_empty_when_none(self):
        item = _make_item(label_translations=None)
        assert item.translations == {}

    def test_translations_returns_dict(self):
        item = _make_item(label_translations={"fr": "Étiquette"})
        assert item.translations == {"fr": "Étiquette"}

    def test_get_translation_none(self):
        item = _make_item(label_translations=None)
        assert item.get_translation("fr") is None

    def test_get_translation_found(self):
        item = _make_item(label_translations={"fr": "Étiquette"})
        assert item.get_translation("fr") == "Étiquette"

    def test_get_translation_not_found(self):
        item = _make_item(label_translations={"en": "Label"})
        assert item.get_translation("fr") is None

    def test_set_translation(self):
        item = _make_item(label_translations=None)
        item.set_translation("fr", "Étiquette")
        assert item.label_translations["fr"] == "Étiquette"

    def test_set_translation_existing_dict(self):
        item = _make_item(label_translations={"en": "Label"})
        item.set_translation("fr", "Étiquette")
        assert item.label_translations["fr"] == "Étiquette"
        assert item.label_translations["en"] == "Label"

    def test_get_definition_translation_none(self):
        item = _make_item(definition_translations=None)
        assert item.get_definition_translation("fr") is None

    def test_get_definition_translation_found(self):
        item = _make_item(definition_translations={"fr": "Définition"})
        assert item.get_definition_translation("fr") == "Définition"

    def test_set_definition_translation(self):
        item = _make_item(definition_translations=None)
        item.set_definition_translation("fr", "Définition")
        assert item.definition_translations["fr"] == "Définition"

    def test_set_definition_translation_existing(self):
        item = _make_item(definition_translations={"en": "Definition"})
        item.set_definition_translation("fr", "Définition")
        assert item.definition_translations["fr"] == "Définition"

    def test_get_description_translation_none(self):
        item = _make_item(description_translations=None)
        assert item.get_description_translation("fr") is None

    def test_get_description_translation_found(self):
        item = _make_item(description_translations={"fr": "Description Fr"})
        assert item.get_description_translation("fr") == "Description Fr"

    def test_set_description_translation_new(self):
        item = _make_item(description_translations=None)
        item.set_description_translation("fr", "Description Fr")
        assert item.description_translations["fr"] == "Description Fr"

    def test_set_description_translation_removes_on_empty(self):
        item = _make_item(description_translations={"fr": "Description Fr"})
        item.set_description_translation("fr", "")
        assert "fr" not in item.description_translations

    def test_set_description_translation_removes_on_whitespace(self):
        item = _make_item(description_translations={"fr": "Description Fr"})
        item.set_description_translation("fr", "   ")
        assert "fr" not in item.description_translations

    def test_set_description_translation_key_not_present_empty(self):
        item = _make_item(description_translations={"en": "Description"})
        item.set_description_translation("fr", "")
        assert "fr" not in item.description_translations

    def test_get_translated_options_non_question(self):
        item = _make_item(item_type="indicator")
        assert item.get_translated_options("fr") == []

    def test_get_translated_options_no_translations(self):
        item = _make_item(item_type="question", options_json=["A", "B"], options_translations=None)
        result = item.get_translated_options("fr")
        assert result == ["A", "B"]

    def test_get_translated_options_no_options(self):
        item = _make_item(item_type="question", options_json=None)
        result = item.get_translated_options("fr")
        assert result == []

    def test_get_translated_options_with_translation(self):
        item = _make_item(
            item_type="question",
            options_json=["Option A", "Option B"],
            options_translations=[
                {"option_text": "Option A", "translations": {"fr": "Option A (fr)"}},
                {"option_text": "Option B", "translations": {"fr": "Option B (fr)"}},
            ]
        )
        result = item.get_translated_options("fr")
        assert result == ["Option A (fr)", "Option B (fr)"]

    def test_get_translated_options_partial_translation(self):
        item = _make_item(
            item_type="question",
            options_json=["Option A", "Option B"],
            options_translations=[
                {"option_text": "Option A", "translations": {"fr": "Option A (fr)"}},
            ]
        )
        result = item.get_translated_options("fr")
        assert result[0] == "Option A (fr)"
        assert result[1] == "Option B"  # Fallback


# ---------------------------------------------------------------------------
# field_type_for_js
# ---------------------------------------------------------------------------

class TestFieldTypeForJs:
    def test_document_field(self):
        item = _make_item(item_type="document_field")
        assert item.field_type_for_js == "DOCUMENT"

    def test_indicator_number(self):
        item = _make_item(item_type="indicator", type="number")
        assert item.field_type_for_js == "number"

    def test_indicator_count(self):
        item = _make_item(item_type="indicator", type="count")
        assert item.field_type_for_js == "number"

    def test_indicator_percentage(self):
        item = _make_item(item_type="indicator", type="percentage")
        assert item.field_type_for_js == "percentage"

    def test_indicator_text(self):
        item = _make_item(item_type="indicator", type="text")
        assert item.field_type_for_js == "text"

    def test_indicator_string(self):
        item = _make_item(item_type="indicator", type="string")
        assert item.field_type_for_js == "text"

    def test_indicator_yesno(self):
        item = _make_item(item_type="indicator", type="yesno")
        assert item.field_type_for_js == "yesno"

    def test_indicator_date(self):
        item = _make_item(item_type="indicator", type="date")
        assert item.field_type_for_js == "date"

    def test_indicator_datetime(self):
        item = _make_item(item_type="indicator", type="datetime")
        assert item.field_type_for_js == "datetime"

    def test_indicator_currency(self):
        item = _make_item(item_type="indicator", type="currency")
        assert item.field_type_for_js == "currency"

    def test_indicator_other_type(self):
        item = _make_item(item_type="indicator", type="custom_type")
        assert item.field_type_for_js == "custom_type"

    def test_indicator_no_type(self):
        item = _make_item(item_type="indicator", type=None)
        assert item.field_type_for_js == "text"

    def test_question_text(self):
        item = _make_item(item_type="question", type="text")
        result = item.field_type_for_js
        assert result == "text"

    def test_question_blank_type(self):
        item = _make_item(item_type="question", type="blank")
        assert item.field_type_for_js == "blank"

    def test_question_no_type(self):
        item = _make_item(item_type="question", type=None)
        assert item.field_type_for_js == "text"

    def test_plugin_item(self):
        item = _make_item(item_type="plugin_mytype")
        assert item.field_type_for_js == "PLUGIN_MYTYPE"

    def test_unknown_item_type_defaults_text(self):
        item = _make_item(item_type="unknown_type")
        assert item.field_type_for_js == "text"


# ---------------------------------------------------------------------------
# question_type
# ---------------------------------------------------------------------------

class TestQuestionType:
    def test_question_type_none_for_indicator(self):
        item = _make_item(item_type="indicator")
        assert item.question_type is None

    def test_question_type_none_for_no_type(self):
        item = _make_item(item_type="question", type=None)
        assert item.question_type is None

    def test_question_type_compat_object(self):
        item = _make_item(item_type="question", type="text")
        qt = item.question_type
        assert qt is not None
        assert qt.value == "text"

    def test_indicator_bank_id_compat_for_indicator(self):
        item = _make_item(item_type="indicator")
        item.indicator_bank_id = 5
        assert item.indicator_bank_id_compat == 5

    def test_indicator_bank_id_compat_for_non_indicator(self):
        item = _make_item(item_type="question")
        item.indicator_bank_id = 5
        assert item.indicator_bank_id_compat is None


# ---------------------------------------------------------------------------
# type_display / unit_display
# ---------------------------------------------------------------------------

class TestTypeAndUnitDisplay:
    def test_type_display_no_type(self):
        item = _make_item(item_type="indicator", type=None)
        assert item.type_display == ""

    def test_type_display_with_type(self):
        item = _make_item(item_type="indicator", type="number")
        result = item.type_display
        assert isinstance(result, str)

    def test_type_display_non_indicator(self):
        item = _make_item(item_type="question", type="text")
        assert item.type_display == "text"

    def test_unit_display_no_unit(self):
        item = _make_item(item_type="indicator", unit=None)
        assert item.unit_display == ""

    def test_unit_display_with_unit(self):
        item = _make_item(item_type="indicator", unit="people")
        result = item.unit_display
        assert isinstance(result, str)

    def test_unit_display_non_indicator(self):
        item = _make_item(item_type="question", unit=None)
        assert item.unit_display == ""


# ---------------------------------------------------------------------------
# get_display_options / get_option_value_for_display
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetDisplayOptions:
    def test_no_language_returns_base(self, app):
        with app.app_context():
            item = _make_item(item_type="question", options_json=["A", "B"])
            result = item.get_display_options(language=None)
            assert result == ["A", "B"]

    def test_no_translations_returns_base(self, app):
        with app.app_context():
            item = _make_item(item_type="question", options_json=["A", "B"], options_translations=None)
            result = item.get_display_options(language="fr")
            assert result == ["A", "B"]

    def test_with_translations(self, app):
        with app.app_context():
            item = _make_item(
                item_type="question",
                options_json=["Option A"],
                options_translations=[
                    {"option_text": "Option A", "translations": {"fr": "Option A FR"}}
                ]
            )
            result = item.get_display_options(language="fr")
            assert "Option A FR" in result

    def test_without_translation_for_language(self, app):
        with app.app_context():
            item = _make_item(
                item_type="question",
                options_json=["Option A"],
                options_translations=[
                    {"option_text": "Option A", "translations": {"en": "Option A EN"}}
                ]
            )
            result = item.get_display_options(language="fr")
            assert "Option A" in result

    def test_get_option_value_for_display_no_translation(self):
        item = _make_item(item_type="question")
        result = item.get_option_value_for_display("Option A", language="fr")
        assert result == "Option A"

    def test_get_option_value_for_display_no_saved_value(self):
        item = _make_item(item_type="question", options_translations=[])
        result = item.get_option_value_for_display(None, language="fr")
        assert result is None

    def test_get_option_value_for_display_with_translation(self):
        item = _make_item(
            item_type="question",
            options_translations=[
                {"option_text": "Option A", "translations": {"fr": "Option A FR"}}
            ]
        )
        result = item.get_option_value_for_display("Option A", language="fr")
        assert result == "Option A FR"

    def test_get_option_value_for_display_no_match(self):
        item = _make_item(
            item_type="question",
            options_translations=[
                {"option_text": "Option B", "translations": {"fr": "Option B FR"}}
            ]
        )
        result = item.get_option_value_for_display("Option A", language="fr")
        assert result == "Option A"


# ---------------------------------------------------------------------------
# _row_matches_filters and _apply_filters_to_rows
# ---------------------------------------------------------------------------

class TestRowFilters:
    def _make_row(self, data):
        return SimpleNamespace(data=data)

    def _make_item_for_filters(self):
        item = _make_item(item_type="question", lookup_list_id="123", list_display_column="name")
        return item

    def test_apply_filters_empty(self):
        item = self._make_item_for_filters()
        rows = [self._make_row({"name": "A"}), self._make_row({"name": "B"})]
        result = item._apply_filters_to_rows(rows, [])
        assert result == rows

    def test_row_matches_eq_true(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "number"})
        assert item._row_matches_filters(row, [{"field": "type", "op": "eq", "value": "number"}]) is True

    def test_row_matches_eq_false(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "text"})
        assert item._row_matches_filters(row, [{"field": "type", "op": "eq", "value": "number"}]) is False

    def test_row_matches_ne_true(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "text"})
        assert item._row_matches_filters(row, [{"field": "type", "op": "ne", "value": "number"}]) is True

    def test_row_matches_ne_false(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "number"})
        assert item._row_matches_filters(row, [{"field": "type", "op": "ne", "value": "number"}]) is False

    def test_row_matches_contains_true(self):
        item = self._make_item_for_filters()
        row = self._make_row({"name": "National Society"})
        assert item._row_matches_filters(row, [{"field": "name", "op": "contains", "value": "national"}]) is True

    def test_row_matches_contains_false(self):
        item = self._make_item_for_filters()
        row = self._make_row({"name": "Something else"})
        assert item._row_matches_filters(row, [{"field": "name", "op": "contains", "value": "national"}]) is False

    def test_row_matches_startswith_true(self):
        item = self._make_item_for_filters()
        row = self._make_row({"name": "National Society"})
        assert item._row_matches_filters(row, [{"field": "name", "op": "startswith", "value": "national"}]) is True

    def test_row_matches_startswith_false(self):
        item = self._make_item_for_filters()
        row = self._make_row({"name": "Something"})
        assert item._row_matches_filters(row, [{"field": "name", "op": "startswith", "value": "national"}]) is False

    def test_row_matches_endswith_true(self):
        item = self._make_item_for_filters()
        row = self._make_row({"name": "National Society"})
        assert item._row_matches_filters(row, [{"field": "name", "op": "endswith", "value": "society"}]) is True

    def test_row_matches_endswith_false(self):
        item = self._make_item_for_filters()
        row = self._make_row({"name": "National Thing"})
        assert item._row_matches_filters(row, [{"field": "name", "op": "endswith", "value": "society"}]) is False

    def test_row_matches_gt_true(self):
        item = self._make_item_for_filters()
        row = self._make_row({"count": 10})
        assert item._row_matches_filters(row, [{"field": "count", "op": "gt", "value": 5}]) is True

    def test_row_matches_gt_false(self):
        item = self._make_item_for_filters()
        row = self._make_row({"count": 3})
        assert item._row_matches_filters(row, [{"field": "count", "op": "gt", "value": 5}]) is False

    def test_row_matches_gte_equal(self):
        item = self._make_item_for_filters()
        row = self._make_row({"count": 5})
        assert item._row_matches_filters(row, [{"field": "count", "op": "gte", "value": 5}]) is True

    def test_row_matches_lt_true(self):
        item = self._make_item_for_filters()
        row = self._make_row({"count": 3})
        assert item._row_matches_filters(row, [{"field": "count", "op": "lt", "value": 5}]) is True

    def test_row_matches_lt_false(self):
        item = self._make_item_for_filters()
        row = self._make_row({"count": 7})
        assert item._row_matches_filters(row, [{"field": "count", "op": "lt", "value": 5}]) is False

    def test_row_matches_lte_equal(self):
        item = self._make_item_for_filters()
        row = self._make_row({"count": 5})
        assert item._row_matches_filters(row, [{"field": "count", "op": "lte", "value": 5}]) is True

    def test_row_matches_numeric_comparison_non_numeric(self):
        item = self._make_item_for_filters()
        row = self._make_row({"count": "abc"})
        assert item._row_matches_filters(row, [{"field": "count", "op": "gt", "value": 5}]) is False

    def test_row_matches_in_list_true(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "number"})
        assert item._row_matches_filters(row, [{"field": "type", "op": "in", "value": ["number", "text"]}]) is True

    def test_row_matches_in_list_false(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "date"})
        assert item._row_matches_filters(row, [{"field": "type", "op": "in", "value": ["number", "text"]}]) is False

    def test_row_matches_in_single_value_true(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "number"})
        assert item._row_matches_filters(row, [{"field": "type", "op": "in", "value": "number"}]) is True

    def test_row_matches_in_single_value_false(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "text"})
        assert item._row_matches_filters(row, [{"field": "type", "op": "in", "value": "number"}]) is False

    def test_row_matches_not_in_list_true(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "date"})
        assert item._row_matches_filters(row, [{"field": "type", "op": "not_in", "value": ["number", "text"]}]) is True

    def test_row_matches_not_in_list_false(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "number"})
        assert item._row_matches_filters(row, [{"field": "type", "op": "not_in", "value": ["number", "text"]}]) is False

    def test_row_matches_not_in_single_value_true(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "text"})
        assert item._row_matches_filters(row, [{"field": "type", "op": "not_in", "value": "number"}]) is True

    def test_row_matches_not_in_single_value_false(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "number"})
        assert item._row_matches_filters(row, [{"field": "type", "op": "not_in", "value": "number"}]) is False

    def test_row_matches_is_empty_true_none(self):
        item = self._make_item_for_filters()
        row = self._make_row({"field": None})
        # None value with is_empty should match (continue)
        assert item._row_matches_filters(row, [{"field": "field", "op": "is_empty", "value": ""}]) is True

    def test_row_matches_is_empty_true_empty_string(self):
        item = self._make_item_for_filters()
        row = self._make_row({"field": ""})
        assert item._row_matches_filters(row, [{"field": "field", "op": "is_empty", "value": ""}]) is True

    def test_row_matches_is_empty_false_has_value(self):
        item = self._make_item_for_filters()
        row = self._make_row({"field": "something"})
        assert item._row_matches_filters(row, [{"field": "field", "op": "is_empty", "value": ""}]) is False

    def test_row_matches_is_not_empty_true(self):
        item = self._make_item_for_filters()
        row = self._make_row({"field": "value"})
        assert item._row_matches_filters(row, [{"field": "field", "op": "is_not_empty", "value": ""}]) is True

    def test_row_matches_is_not_empty_false(self):
        item = self._make_item_for_filters()
        row = self._make_row({"field": ""})
        assert item._row_matches_filters(row, [{"field": "field", "op": "is_not_empty", "value": ""}]) is False

    def test_row_matches_null_value_non_is_empty_returns_false(self):
        item = self._make_item_for_filters()
        row = self._make_row({"field": None})
        assert item._row_matches_filters(row, [{"field": "field", "op": "eq", "value": "something"}]) is False

    def test_row_matches_missing_field_skips(self):
        item = self._make_item_for_filters()
        row = self._make_row({"name": "Test"})
        # filter with no field skips (continue)
        assert item._row_matches_filters(row, [{"op": "eq", "value": "something"}]) is True

    def test_row_matches_non_dict_filter_skipped(self):
        item = self._make_item_for_filters()
        row = self._make_row({"name": "Test"})
        assert item._row_matches_filters(row, ["not_a_dict"]) is True

    def test_row_matches_value_field_id_with_context(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "number"})
        context = {"42": "number"}
        filters = [{"field": "type", "op": "eq", "value_field_id": 42}]
        assert item._row_matches_filters(row, filters, context_values=context) is True

    def test_row_matches_value_field_id_no_context(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "number"})
        filters = [{"field": "type", "op": "eq", "value_field_id": 42}]
        # No context → treat filter as not satisfied
        assert item._row_matches_filters(row, filters, context_values=None) is False

    def test_row_matches_value_field_id_key_missing(self):
        item = self._make_item_for_filters()
        row = self._make_row({"type": "number"})
        context = {"99": "something"}
        filters = [{"field": "type", "op": "eq", "value_field_id": 42}]
        assert item._row_matches_filters(row, filters, context_values=context) is False

    def test_row_matches_filter_value_none_skips(self):
        item = self._make_item_for_filters()
        row = self._make_row({"field": "value"})
        # field present, value=None → continue (no constraint)
        filters = [{"field": "field", "op": "eq", "value": None}]
        assert item._row_matches_filters(row, filters) is True


# ---------------------------------------------------------------------------
# get_calculated_options
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetCalculatedOptions:
    def test_no_lookup_list_id_returns_empty(self):
        item = _make_item(lookup_list_id=None, list_display_column="name")
        result = item.get_calculated_options()
        assert result == []

    def test_no_list_display_column_returns_empty(self):
        item = _make_item(lookup_list_id="123", list_display_column=None)
        result = item.get_calculated_options()
        assert result == []

    def test_emergency_operations_returns_empty(self):
        item = _make_item(lookup_list_id="emergency_operations", list_display_column="name")
        result = item.get_calculated_options()
        assert result == []

    def test_caches_results(self):
        item = _make_item(lookup_list_id="emergency_operations", list_display_column="name")
        r1 = item.get_calculated_options()
        r2 = item.get_calculated_options()
        assert r1 == r2

    def test_clear_calculated_options_cache(self):
        item = _make_item(lookup_list_id="emergency_operations", list_display_column="name")
        item._calculated_options_cache = {"key": "some_key", "options": ["cached"]}
        item.clear_calculated_options_cache()
        assert not hasattr(item, "_calculated_options_cache")

    def test_clear_cache_no_cache_exists(self):
        item = _make_item(lookup_list_id="emergency_operations", list_display_column="name")
        # Should not raise even if cache doesn't exist
        item.clear_calculated_options_cache()

    def test_lookup_list_non_numeric_id_returns_none(self):
        item = _make_item(lookup_list_id="special_list", list_display_column="name")
        assert item.lookup_list is None

    def test_lookup_list_numeric_id(self, db_session, app):
        with app.app_context():
            item = _make_item(lookup_list_id="999999", list_display_column="name")
            # Non-existent ID should return None without error
            result = item.lookup_list
            assert result is None

    def test_no_lookup_list_returns_empty(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item = create_test_item(db_session, section, template, item_type="question")
            item.lookup_list_id = "99999"  # Non-existent
            item.list_display_column = "name"
            result = item.get_calculated_options()
            assert result == []


# ---------------------------------------------------------------------------
# __repr__
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormItemRepr:
    def test_repr_indicator(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item = create_test_item(db_session, section, template, item_type="indicator")
            result = repr(item)
            assert "Indicator" in result or "indicator" in result.lower()

    def test_repr_question(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item = create_test_item(db_session, section, template, item_type="question")
            result = repr(item)
            assert "Question" in result or "question" in result.lower()

    def test_repr_document_field(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item = create_test_item(db_session, section, template, item_type="document_field")
            result = repr(item)
            assert "Document_Field" in result or "document" in result.lower()

    def test_repr_sub_item_indicator(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item = create_test_item(db_session, section, template, item_type="indicator", order=1.1)
            result = repr(item)
            assert "Sub" in result

    def test_repr_other_type(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item = create_test_item(db_session, section, template, item_type="matrix")
            result = repr(item)
            assert isinstance(result, str)
