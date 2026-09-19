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
