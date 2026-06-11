"""Tests for validation/question_assembler.py — 100% coverage target."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.validation.question_assembler import (
    _format_suffix,
    assemble_question_for_kpi,
    lookup_template_text,
)
from app.services.validation.types import CheckResult


class TestFormatSuffix:
    def test_past_year_threshold_with_ytd_pct(self):
        result = _format_suffix("past_year_threshold", {"ytd_pct": 0.25})
        assert result == "25.00%"

    def test_past_year_threshold_with_yoy_pct(self):
        result = _format_suffix("past_year_threshold", {"yoy_pct": 0.1})
        assert result == "10.00%"

    def test_past_year_threshold_no_pct(self):
        result = _format_suffix("past_year_threshold", {})
        assert result == ""

    def test_past_3years_avg_with_ytd_pct(self):
        result = _format_suffix("past_3years_avg", {"ytd_pct": -0.5})
        assert result == "-50.00%"

    def test_higher_than_pop_with_population(self):
        result = _format_suffix("higher_than_pop", {"population": 1000000})
        assert result == "1,000,000"

    def test_higher_than_pop_no_population(self):
        result = _format_suffix("higher_than_pop", {})
        assert result == ""

    def test_significant_pop_with_ratio(self):
        result = _format_suffix("significant_pop", {"ratio": 0.35})
        assert result == "35.00%"

    def test_significant_pop_no_ratio(self):
        result = _format_suffix("significant_pop", {})
        assert result == ""

    def test_branches_higher_units_with_units(self):
        result = _format_suffix("branches_higher_units", {"local_units": 5000})
        assert result == "5,000"

    def test_branches_higher_units_no_units(self):
        result = _format_suffix("branches_higher_units", {})
        assert result == ""

    def test_fiscal_year_with_days(self):
        result = _format_suffix("fiscal_year", {"fiscal_days": 400})
        assert result == "400"

    def test_fiscal_year_no_days(self):
        result = _format_suffix("fiscal_year", {})
        assert result == ""

    def test_awsd_check_with_deaths(self):
        result = _format_suffix("awsd_check", {"awsd_deaths": 3})
        assert result == "3"

    def test_awsd_check_no_deaths(self):
        result = _format_suffix("awsd_check", {})
        assert result == ""

    def test_typeofprograms_with_programmes(self):
        result = _format_suffix("typeofprograms", {"programmes": ["KPI_A", "KPI_B"]})
        assert result == "KPI_A, KPI_B."

    def test_typeofprograms_empty_programmes(self):
        result = _format_suffix("typeofprograms", {"programmes": []})
        assert result == ""

    def test_typeofprograms_missing_key(self):
        result = _format_suffix("typeofprograms", {})
        assert result == ""

    def test_unknown_rule_code(self):
        result = _format_suffix("some_other_rule", {"foo": "bar"})
        assert result == ""


class TestLookupTemplateText:
    def test_returns_template_text_when_found(self):
        mock_row = MagicMock()
        mock_row.template_text = "Please check the value."
        mock_row.needs_ending_value = False

        with patch(
            "app.services.validation.question_assembler.ValidationQuestionTemplate.query"
        ) as mock_q:
            mock_q.filter_by.return_value.first.return_value = mock_row
            text, needs = lookup_template_text("not_reported", "en", "fdrs_matrix_v1")

        assert text == "Please check the value."
        assert needs is False

    def test_fallback_to_english_when_language_missing(self):
        mock_en_row = MagicMock()
        mock_en_row.template_text = "English fallback text."
        mock_en_row.needs_ending_value = True

        with patch(
            "app.services.validation.question_assembler.ValidationQuestionTemplate.query"
        ) as mock_q:
            # First call (non-en language) returns None; second call (en) returns row
            mock_q.filter_by.return_value.first.side_effect = [None, mock_en_row]
            text, needs = lookup_template_text("not_reported", "fr", "fdrs_matrix_v1")

        assert text == "English fallback text."
        assert needs is True

    def test_returns_default_text_when_no_template_found(self):
        with patch(
            "app.services.validation.question_assembler.ValidationQuestionTemplate.query"
        ) as mock_q:
            mock_q.filter_by.return_value.first.return_value = None
            text, needs = lookup_template_text("my_rule_code", "en", None)

        assert "my rule code" in text.lower()
        assert needs is False

    def test_english_language_does_not_double_query(self):
        """When language is 'en' and no row found, should not trigger fallback."""
        with patch(
            "app.services.validation.question_assembler.ValidationQuestionTemplate.query"
        ) as mock_q:
            mock_q.filter_by.return_value.first.return_value = None
            text, needs = lookup_template_text("missing_rule", "en", "some_pack")

        assert "missing rule" in text.lower()


class TestAssembleQuestionForKpi:
    def test_returns_none_when_no_fired_results(self):
        results = [
            CheckResult(rule_code="not_reported", form_item_id=1, fired=False)
        ]
        draft = assemble_question_for_kpi(
            results, definition_text=None, language="en", rule_pack=None
        )
        assert draft is None

    def test_returns_none_for_empty_list(self):
        draft = assemble_question_for_kpi(
            [], definition_text=None, language="en", rule_pack=None
        )
        assert draft is None

    def test_picks_most_severe_winner(self):
        results = [
            CheckResult(rule_code="warning_rule", form_item_id=1, fired=True, severity="warning"),
            CheckResult(rule_code="error_rule", form_item_id=1, fired=True, severity="error"),
        ]
        with patch(
            "app.services.validation.question_assembler.ValidationQuestionTemplate.query"
        ) as mock_q:
            mock_q.filter_by.return_value.first.return_value = None
            draft = assemble_question_for_kpi(
                results, definition_text=None, language="en", rule_pack=None
            )

        assert draft is not None
        assert draft.rule_code == "error_rule"
        assert draft.severity == "error"

    def test_includes_definition_text_when_provided(self):
        results = [CheckResult(rule_code="not_reported", form_item_id=5, fired=True)]
        with patch(
            "app.services.validation.question_assembler.ValidationQuestionTemplate.query"
        ) as mock_q:
            mock_q.filter_by.return_value.first.return_value = None
            draft = assemble_question_for_kpi(
                results, definition_text="The indicator measures X.", language="en", rule_pack=None
            )

        assert "The indicator measures X." in draft.question_text
        assert draft.definition_text == "The indicator measures X."

    def test_no_definition_text(self):
        results = [CheckResult(rule_code="fiscal_year", form_item_id=3, fired=True)]
        with patch(
            "app.services.validation.question_assembler.ValidationQuestionTemplate.query"
        ) as mock_q:
            mock_q.filter_by.return_value.first.return_value = None
            draft = assemble_question_for_kpi(
                results, definition_text=None, language="en", rule_pack=None
            )

        assert draft is not None
        assert draft.definition_text is None

    def test_suffix_appended_when_needed(self):
        mock_row = MagicMock()
        mock_row.template_text = "The change is:"
        mock_row.needs_ending_value = True

        results = [
            CheckResult(
                rule_code="past_year_threshold",
                form_item_id=1,
                fired=True,
                context={"ytd_pct": 0.75},
            )
        ]
        with patch(
            "app.services.validation.question_assembler.ValidationQuestionTemplate.query"
        ) as mock_q:
            mock_q.filter_by.return_value.first.return_value = mock_row
            draft = assemble_question_for_kpi(
                results, definition_text=None, language="en", rule_pack="fdrs_matrix_v1"
            )

        assert "75.00%" in draft.question_text

    def test_context_includes_all_triggered_rules(self):
        results = [
            CheckResult(rule_code="not_reported", form_item_id=1, fired=True, severity="warning"),
            CheckResult(rule_code="indicator_not_reported", form_item_id=1, fired=True, severity="warning"),
        ]
        with patch(
            "app.services.validation.question_assembler.ValidationQuestionTemplate.query"
        ) as mock_q:
            mock_q.filter_by.return_value.first.return_value = None
            draft = assemble_question_for_kpi(
                results, definition_text=None, language="en", rule_pack=None
            )

        assert set(draft.context["triggered_rules"]) == {"not_reported", "indicator_not_reported"}

    def test_language_is_preserved(self):
        results = [CheckResult(rule_code="grbmp", form_item_id=None, fired=True)]
        with patch(
            "app.services.validation.question_assembler.ValidationQuestionTemplate.query"
        ) as mock_q:
            mock_q.filter_by.return_value.first.return_value = None
            draft = assemble_question_for_kpi(
                results, definition_text=None, language="fr", rule_pack=None
            )

        assert draft.language == "fr"

    def test_form_item_id_from_winner(self):
        results = [CheckResult(rule_code="grbmp", form_item_id=42, fired=True)]
        with patch(
            "app.services.validation.question_assembler.ValidationQuestionTemplate.query"
        ) as mock_q:
            mock_q.filter_by.return_value.first.return_value = None
            draft = assemble_question_for_kpi(
                results, definition_text=None, language="en", rule_pack=None
            )

        assert draft.form_item_id == 42
