"""Tests for validation/rule_labels.py — 100% coverage target."""

import pytest

from app.services.validation.rule_labels import (
    RULE_LABELS,
    format_rule_label,
    format_rule_labels,
)


class TestFormatRuleLabel:
    def test_none_returns_empty(self):
        assert format_rule_label(None) == ""

    def test_empty_string_returns_empty(self):
        assert format_rule_label("") == ""

    def test_known_codes_return_mapped_label(self):
        assert format_rule_label("indicator_not_reported") == "Not reported"
        assert format_rule_label("not_reported") == "Not reported"
        assert format_rule_label("non_zero") == "Not reported"

    def test_unknown_code_is_title_cased(self):
        assert format_rule_label("past_year_threshold") == "Past Year Threshold"

    def test_unknown_code_with_single_word(self):
        assert format_rule_label("volunteer_deaths") == "Volunteer Deaths"

    def test_code_not_in_rule_labels_replaces_underscores(self):
        assert format_rule_label("fiscal_year") == "Fiscal Year"

    def test_all_known_codes_covered(self):
        for code in RULE_LABELS:
            label = format_rule_label(code)
            assert label == RULE_LABELS[code]


class TestFormatRuleLabels:
    def test_empty_list_returns_empty(self):
        assert format_rule_labels([]) == []

    def test_single_code(self):
        result = format_rule_labels(["not_reported"])
        assert result == ["Not reported"]

    def test_deduplicates_same_label(self):
        # "indicator_not_reported" and "not_reported" both map to "Not reported"
        result = format_rule_labels(["indicator_not_reported", "not_reported"])
        assert result == ["Not reported"]

    def test_deduplicates_case_insensitively(self):
        # "non_zero" also maps to "Not reported"
        result = format_rule_labels(["not_reported", "non_zero"])
        assert len(result) == 1
        assert result[0] == "Not reported"

    def test_multiple_distinct_codes(self):
        result = format_rule_labels(["volunteer_deaths", "fiscal_year"])
        assert "Volunteer Deaths" in result
        assert "Fiscal Year" in result
        assert len(result) == 2

    def test_preserves_order_of_first_occurrence(self):
        result = format_rule_labels(["fiscal_year", "volunteer_deaths"])
        assert result[0] == "Fiscal Year"
        assert result[1] == "Volunteer Deaths"

    def test_skips_empty_label_codes(self):
        # An empty string code produces "" label → should be skipped
        result = format_rule_labels(["", "fiscal_year"])
        assert result == ["Fiscal Year"]
