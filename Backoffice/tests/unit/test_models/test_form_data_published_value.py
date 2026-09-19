"""Unit tests for FormData's published-snapshot helpers (see plugins/fdrs publication tool).

Pure logic on ``value``/``disagg_data`` vs. ``published_value``/``published_disagg_data`` —
no DB required (mirrors the transient-instance style in test_form_data_aux_scalar_values.py).
"""

import pytest

from app.models.forms import FormData


@pytest.mark.unit
class TestIsBlankValue:
    def test_none_value_and_no_disagg_is_blank(self):
        assert FormData._is_blank_value(None, None) is True

    def test_empty_string_value_is_blank(self):
        assert FormData._is_blank_value("", None) is True

    def test_whitespace_only_value_is_blank(self):
        assert FormData._is_blank_value("   ", None) is True

    def test_empty_disagg_dict_does_not_count_as_present(self):
        # `not {}` is True in Python — an empty disagg payload is still "blank".
        assert FormData._is_blank_value(None, {}) is True

    def test_numeric_looking_string_value_is_not_blank(self):
        assert FormData._is_blank_value("5", None) is False

    def test_nonempty_disagg_makes_it_not_blank_even_without_scalar_value(self):
        assert FormData._is_blank_value(None, {"mode": "total", "values": {"direct": 1}}) is False


@pytest.mark.unit
class TestIsPublished:
    def test_false_when_nothing_published(self):
        entry = FormData(published_value=None, published_disagg_data=None)
        assert entry.is_published() is False

    def test_true_when_published_value_set(self):
        entry = FormData(published_value="42", published_disagg_data=None)
        assert entry.is_published() is True

    def test_true_when_only_published_disagg_data_set(self):
        entry = FormData(published_value=None, published_disagg_data={"mode": "total", "values": {"direct": 1}})
        assert entry.is_published() is True

    def test_false_when_published_value_is_blank_string(self):
        entry = FormData(published_value="   ", published_disagg_data=None)
        assert entry.is_published() is False


@pytest.mark.unit
class TestPublicationDiffKind:
    def test_empty_when_nothing_reported_and_nothing_published(self):
        entry = FormData(value=None, disagg_data=None, published_value=None, published_disagg_data=None)
        assert entry.publication_diff_kind() == "empty"

    def test_new_when_reported_but_never_published(self):
        entry = FormData(value="10", disagg_data=None, published_value=None, published_disagg_data=None)
        assert entry.publication_diff_kind() == "new"

    def test_new_when_reported_via_disagg_only(self):
        entry = FormData(
            value=None,
            disagg_data={"mode": "total", "values": {"direct": 5}},
            published_value=None,
            published_disagg_data=None,
        )
        assert entry.publication_diff_kind() == "new"

    def test_removed_when_published_before_but_no_longer_reported(self):
        entry = FormData(value=None, disagg_data=None, published_value="10", published_disagg_data=None)
        assert entry.publication_diff_kind() == "removed"

    def test_unchanged_when_scalar_and_disagg_both_match(self):
        entry = FormData(
            value="10",
            disagg_data={"mode": "total", "values": {"direct": 10}},
            published_value="10",
            published_disagg_data={"mode": "total", "values": {"direct": 10}},
            published_source=FormData.PUBLISHED_SOURCE_REPORTED,
        )
        assert entry.publication_diff_kind() == "unchanged"

    def test_changed_when_scalar_value_differs(self):
        entry = FormData(value="20", disagg_data=None, published_value="10", published_disagg_data=None)
        assert entry.publication_diff_kind() == "changed"

    def test_changed_when_scalar_matches_but_disagg_differs(self):
        entry = FormData(
            value="10",
            disagg_data={"mode": "total", "values": {"direct": 10}},
            published_value="10",
            published_disagg_data={"mode": "total", "values": {"direct": 7}},
        )
        assert entry.publication_diff_kind() == "changed"

    def test_new_when_only_imputed_value_exists(self):
        entry = FormData(
            value=None,
            disagg_data=None,
            imputed_value="12",
            published_value=None,
            published_disagg_data=None,
        )
        assert entry.publication_diff_kind() == "new"

    def test_unchanged_when_imputed_matches_published(self):
        entry = FormData(
            value=None,
            disagg_data=None,
            imputed_value="12",
            published_value="12",
            published_disagg_data=None,
            published_source=FormData.PUBLISHED_SOURCE_IMPUTED,
        )
        assert entry.publication_diff_kind() == "unchanged"

    def test_changed_when_imputed_differs_from_published(self):
        entry = FormData(
            value=None,
            disagg_data=None,
            imputed_value="15",
            published_value="12",
            published_disagg_data=None,
        )
        assert entry.publication_diff_kind() == "changed"

    def test_reported_takes_precedence_over_imputed(self):
        entry = FormData(
            value="10",
            disagg_data=None,
            imputed_value="99",
            published_value="10",
            published_disagg_data=None,
            published_source=FormData.PUBLISHED_SOURCE_REPORTED,
        )
        assert entry.publication_diff_kind() == "unchanged"

    def test_source_when_values_match_but_published_source_missing(self):
        entry = FormData(
            value="10",
            published_value="10",
            published_source=None,
        )
        assert entry.publication_diff_kind() == "source"

    def test_source_when_published_source_does_not_match_current(self):
        entry = FormData(
            value="10",
            published_value="10",
            published_source=FormData.PUBLISHED_SOURCE_IMPUTED,
        )
        assert entry.publication_diff_kind() == "source"

    def test_removed_when_neither_reported_nor_imputed(self):
        entry = FormData(
            value=None,
            disagg_data=None,
            imputed_value=None,
            published_value="10",
            published_disagg_data=None,
        )
        assert entry.publication_diff_kind() == "removed"


@pytest.mark.unit
class TestPublicationCurrentPayload:
    def test_uses_reported_when_present(self):
        entry = FormData(value="10", numeric_value=10, imputed_value="99", imputed_numeric_value=99)
        assert entry.publication_current_payload() == ("10", None, 10)
        assert entry.publication_uses_imputed() is False

    def test_falls_back_to_imputed_when_reported_missing(self):
        entry = FormData(
            value=None,
            numeric_value=None,
            imputed_value="12",
            imputed_numeric_value=12,
        )
        assert entry.publication_current_payload() == ("12", None, 12)
        assert entry.publication_uses_imputed() is True

    def test_falls_back_to_imputed_disagg_when_reported_missing(self):
        imputed_disagg = {"mode": "total", "values": {"direct": 8}}
        entry = FormData(
            value=None,
            disagg_data=None,
            imputed_value=None,
            imputed_disagg_data=imputed_disagg,
            imputed_numeric_value=8,
        )
        assert entry.publication_current_payload() == (None, imputed_disagg, 8)
        assert entry.publication_uses_imputed() is True

    def test_blank_when_neither_reported_nor_imputed(self):
        entry = FormData(value=None, disagg_data=None, imputed_value=None, imputed_disagg_data=None)
        assert entry.publication_current_payload() == (None, None, None)
        assert entry.publication_uses_imputed() is False

    def test_whitespace_reported_is_treated_as_missing(self):
        entry = FormData(value="   ", imputed_value="12", imputed_numeric_value=12)
        assert entry.publication_current_payload() == ("12", None, 12)
        assert entry.publication_uses_imputed() is True
        assert entry.publication_source_kind() == FormData.PUBLISHED_SOURCE_IMPUTED

    def test_source_kind_is_reported_when_value_present(self):
        entry = FormData(value="10", imputed_value="99")
        assert entry.publication_source_kind() == FormData.PUBLISHED_SOURCE_REPORTED

    def test_source_kind_is_none_when_nothing_to_publish(self):
        entry = FormData(value=None, imputed_value=None)
        assert entry.publication_source_kind() is None
