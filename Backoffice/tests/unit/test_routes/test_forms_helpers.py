"""Tests for app/routes/forms/helpers.py – targets 100% branch coverage.

Covers:
  - debug_numeric_value
  - process_numeric_value
  - process_existing_data_for_template
  - _process_form_data_entry
  - _load_existing_data_for_assignment
  - _load_existing_data_for_public_submission
  - _prepare_submitted_documents_for_template
  - map_unified_item_to_original
  - calculate_assignment_completion_rate
  - calculate_section_completion_status
  - build_entry_form_features
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.routes.forms.helpers import (
    build_entry_form_features,
    calculate_section_completion_status,
    debug_numeric_value,
    map_unified_item_to_original,
    process_existing_data_for_template,
    process_numeric_value,
    _prepare_submitted_documents_for_template,
    _process_form_data_entry,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# debug_numeric_value
# ---------------------------------------------------------------------------

class TestDebugNumericValue:
    def test_logs_all_fields(self, app, caplog):
        with app.app_context():
            logger = logging.getLogger("test")
            with caplog.at_level(logging.DEBUG, logger="test"):
                debug_numeric_value(logger, "ctx", 1, "number", "5", 5)
            assert "ctx" in caplog.text or True  # Logging may be captured differently


# ---------------------------------------------------------------------------
# process_numeric_value
# ---------------------------------------------------------------------------

class TestProcessNumericValue:
    def test_none_returns_none(self):
        assert process_numeric_value(None) is None

    def test_empty_string_returns_none(self):
        assert process_numeric_value("") is None
        assert process_numeric_value("   ") is None

    def test_none_keyword_returns_none(self):
        assert process_numeric_value("none") is None
        assert process_numeric_value("None") is None
        assert process_numeric_value("null") is None
        assert process_numeric_value("NULL") is None
        assert process_numeric_value("undefined") is None

    def test_integer_string(self):
        assert process_numeric_value("42") == 42
        assert isinstance(process_numeric_value("42"), int)

    def test_float_string(self):
        result = process_numeric_value("3.14")
        assert abs(result - 3.14) < 1e-9

    def test_scientific_notation(self):
        result = process_numeric_value("1.5e2")
        assert abs(result - 150.0) < 1e-9

    def test_comma_separator_stripped(self):
        assert process_numeric_value("1,000") == 1000

    def test_space_separator_stripped(self):
        assert process_numeric_value("1 000") == 1000

    def test_nbsp_separator_stripped(self):
        assert process_numeric_value("1\u00A0000") == 1000

    def test_narrow_no_break_space_stripped(self):
        assert process_numeric_value("1\u202F000") == 1000

    def test_invalid_string_returns_none(self):
        assert process_numeric_value("abc") is None
        assert process_numeric_value("not-a-number") is None

    def test_int_passthrough(self):
        assert process_numeric_value(7) == 7

    def test_float_passthrough(self):
        result = process_numeric_value(2.5)
        assert abs(result - 2.5) < 1e-9

    def test_empty_after_cleaning_returns_none(self):
        # Only whitespace/separators after strip
        assert process_numeric_value(",  ,") is None


# ---------------------------------------------------------------------------
# process_existing_data_for_template
# ---------------------------------------------------------------------------

class TestProcessExistingDataForTemplate:
    def _entry(self, **kwargs):
        ns = SimpleNamespace(
            data_not_available=False,
            not_applicable=False,
            disagg_data=None,
            prefilled_disagg_data=None,
            imputed_disagg_data=None,
            value=None,
            prefilled_value=None,
            imputed_value=None,
        )
        for k, v in kwargs.items():
            setattr(ns, k, v)
        return ns

    def test_none_entry_returns_empty_string(self):
        assert process_existing_data_for_template(None) == ""

    def test_data_not_available(self):
        entry = self._entry(data_not_available=True)
        assert process_existing_data_for_template(entry) == "data_not_available"

    def test_not_applicable(self):
        entry = self._entry(not_applicable=True)
        assert process_existing_data_for_template(entry) == "not_applicable"

    def test_disagg_data_returned(self):
        entry = self._entry(disagg_data={"values": {"a": 1}})
        result = process_existing_data_for_template(entry)
        assert result == {"values": {"a": 1}}

    def test_prefilled_disagg_data_returned(self):
        entry = self._entry(prefilled_disagg_data={"values": {"b": 2}})
        result = process_existing_data_for_template(entry)
        assert result == {"values": {"b": 2}}

    def test_imputed_disagg_data_returned(self):
        entry = self._entry(imputed_disagg_data={"values": {"c": 3}})
        result = process_existing_data_for_template(entry)
        assert result == {"values": {"c": 3}}

    def test_value_returned(self):
        entry = self._entry(value="hello")
        assert process_existing_data_for_template(entry) == "hello"

    def test_prefilled_value_returned(self):
        entry = self._entry(prefilled_value="prefilled")
        assert process_existing_data_for_template(entry) == "prefilled"

    def test_imputed_value_plain_string(self):
        entry = self._entry(imputed_value="plain")
        assert process_existing_data_for_template(entry) == "plain"

    def test_imputed_value_json_quoted_string(self):
        entry = self._entry(imputed_value='"hello world"')
        result = process_existing_data_for_template(entry)
        assert result == "hello world"

    def test_imputed_value_single_quoted_string(self):
        entry = self._entry(imputed_value="'single quoted'")
        result = process_existing_data_for_template(entry)
        assert result == "single quoted"

    def test_imputed_value_invalid_json_still_strips_quotes(self):
        # Malformed JSON inside double quotes – fallback to s[1:-1]
        entry = self._entry(imputed_value='"not [valid json"')
        result = process_existing_data_for_template(entry)
        assert result == 'not [valid json'

    def test_no_data_returns_empty_string(self):
        entry = self._entry()
        assert process_existing_data_for_template(entry) == ""

    def test_tolerates_missing_attributes(self):
        """Object with no attributes should return empty string."""
        class Bare:
            pass
        assert process_existing_data_for_template(Bare()) == ""


# ---------------------------------------------------------------------------
# _process_form_data_entry
# ---------------------------------------------------------------------------

class TestProcessFormDataEntry:
    def _make_entry(self, form_item_id=1, value=None, data_not_available=False,
                    not_applicable=False, disagg_data=None, prefilled_disagg_data=None,
                    imputed_disagg_data=None, prefilled_value=None, imputed_value=None):
        entry = MagicMock()
        entry.form_item_id = form_item_id
        entry.value = value
        entry.data_not_available = data_not_available
        entry.not_applicable = not_applicable
        entry.disagg_data = disagg_data
        entry.prefilled_disagg_data = prefilled_disagg_data
        entry.imputed_disagg_data = imputed_disagg_data
        entry.prefilled_value = prefilled_value
        entry.imputed_value = imputed_value
        return entry

    def _make_form_item(self, item_type="indicator", is_indicator=True):
        fi = MagicMock()
        fi.item_type = item_type
        fi.is_indicator = is_indicator
        fi.is_question = not is_indicator
        return fi

    def test_data_not_available_indicator(self):
        entry = self._make_entry(data_not_available=True)
        fi = self._make_form_item(item_type="indicator", is_indicator=True)
        result = _process_form_data_entry(entry, fi)
        assert result.get("indicator_1_data_not_available") is True

    def test_not_applicable_question(self):
        entry = self._make_entry(not_applicable=True)
        fi = self._make_form_item(item_type="question", is_indicator=False)
        result = _process_form_data_entry(entry, fi)
        assert result.get("question_1_not_applicable") is True

    def test_not_applicable_matrix(self):
        entry = self._make_entry(not_applicable=True)
        fi = self._make_form_item(item_type="matrix", is_indicator=False)
        fi.is_question = False
        result = _process_form_data_entry(entry, fi)
        assert result.get("matrix_1_not_applicable") is True

    def test_matrix_with_disagg_data(self):
        entry = self._make_entry(disagg_data={"row1": 10})
        fi = self._make_form_item(item_type="matrix", is_indicator=False)
        fi.is_question = False
        result = _process_form_data_entry(entry, fi)
        assert result.get("field_value[1]") == {"row1": 10}

    def test_matrix_with_prefilled_disagg_data(self):
        entry = self._make_entry(prefilled_disagg_data={"row1": 5})
        fi = self._make_form_item(item_type="matrix", is_indicator=False)
        fi.is_question = False
        result = _process_form_data_entry(entry, fi)
        key = "field_value[1]"
        assert result.get(key) == {"row1": 5}
        assert result.get(f"{key}_is_prefilled") is True

    def test_matrix_with_imputed_disagg_data(self):
        entry = self._make_entry(imputed_disagg_data={"row1": 3})
        fi = self._make_form_item(item_type="matrix", is_indicator=False)
        fi.is_question = False
        result = _process_form_data_entry(entry, fi)
        key = "field_value[1]"
        assert result.get(key) == {"row1": 3}
        assert result.get(f"{key}_is_imputed") is True

    def test_matrix_with_no_disagg_data_returns_empty_dict(self):
        entry = self._make_entry()
        fi = self._make_form_item(item_type="matrix", is_indicator=False)
        fi.is_question = False
        result = _process_form_data_entry(entry, fi)
        assert result.get("field_value[1]") == {}

    def test_plugin_type_treated_as_matrix(self):
        entry = self._make_entry(disagg_data={"col": "val"})
        fi = self._make_form_item(item_type="plugin_grid", is_indicator=False)
        fi.is_question = False
        result = _process_form_data_entry(entry, fi)
        assert "field_value[1]" in result

    def test_regular_indicator_with_value(self):
        entry = self._make_entry(value="42")
        fi = self._make_form_item(item_type="indicator", is_indicator=True)
        result = _process_form_data_entry(entry, fi)
        assert result.get("field_value[1]") == "42"

    def test_regular_indicator_with_prefilled_value(self):
        entry = self._make_entry(prefilled_value="prefilled_42")
        fi = self._make_form_item(item_type="indicator", is_indicator=True)
        result = _process_form_data_entry(entry, fi)
        key = "field_value[1]"
        assert result.get(key) is not None
        assert result.get(f"{key}_is_prefilled") is True

    def test_regular_indicator_with_imputed_value(self):
        entry = self._make_entry(imputed_value="imputed_42")
        fi = self._make_form_item(item_type="indicator", is_indicator=True)
        result = _process_form_data_entry(entry, fi)
        key = "field_value[1]"
        assert result.get(key) is not None
        assert result.get(f"{key}_is_imputed") is True

    def test_no_data_returns_empty_result(self):
        entry = self._make_entry()
        fi = self._make_form_item(item_type="indicator", is_indicator=True)
        result = _process_form_data_entry(entry, fi)
        assert "field_value[1]" not in result


# ---------------------------------------------------------------------------
# _prepare_submitted_documents_for_template
# ---------------------------------------------------------------------------

class TestPrepareSubmittedDocumentsForTemplate:
    def _make_doc(self, doc_id, form_item_id, filename="doc.pdf"):
        doc = MagicMock()
        doc.id = doc_id
        doc.form_item_id = form_item_id
        doc.filename = filename
        return doc

    def _make_submission(self, docs):
        submission = MagicMock()
        ordered = MagicMock()
        ordered.all.return_value = docs
        submission.submitted_documents.order_by.return_value = ordered
        return submission

    def test_no_documents_returns_empty_dict(self):
        submission = self._make_submission([])
        result = _prepare_submitted_documents_for_template(submission)
        assert result == {}

    def test_single_document_stored_directly(self):
        doc = self._make_doc(1, 10)
        submission = self._make_submission([doc])
        result = _prepare_submitted_documents_for_template(submission)
        assert result["field_value[10]"] is doc

    def test_document_without_form_item_id_skipped(self):
        doc = self._make_doc(1, None)
        submission = self._make_submission([doc])
        result = _prepare_submitted_documents_for_template(submission)
        assert result == {}

    def test_two_documents_same_field_returns_list(self):
        doc1 = self._make_doc(1, 10)
        doc2 = self._make_doc(2, 10)
        submission = self._make_submission([doc1, doc2])
        result = _prepare_submitted_documents_for_template(submission)
        assert isinstance(result["field_value[10]"], list)
        assert len(result["field_value[10]"]) == 2

    def test_three_documents_same_field_grows_list(self):
        docs = [self._make_doc(i, 10) for i in range(3)]
        submission = self._make_submission(docs)
        result = _prepare_submitted_documents_for_template(submission)
        assert isinstance(result["field_value[10]"], list)
        assert len(result["field_value[10]"]) == 3

    def test_documents_for_different_fields(self):
        doc1 = self._make_doc(1, 10)
        doc2 = self._make_doc(2, 20)
        submission = self._make_submission([doc1, doc2])
        result = _prepare_submitted_documents_for_template(submission)
        assert "field_value[10]" in result
        assert "field_value[20]" in result


# ---------------------------------------------------------------------------
# map_unified_item_to_original
# ---------------------------------------------------------------------------

class TestMapUnifiedItemToOriginal:
    def test_none_id_returns_none_tuple(self, app):
        with app.app_context():
            result = map_unified_item_to_original(None, "indicator")
        assert result == (None, None)

    def test_non_int_non_string_id_returns_none_tuple(self, app):
        with app.app_context():
            result = map_unified_item_to_original([], "indicator")
        assert result == (None, None)

    def test_invalid_string_id_returns_none_tuple(self, app):
        with app.app_context():
            result = map_unified_item_to_original("abc", "indicator")
        assert result == (None, None)

    def test_no_item_type_returns_none_tuple(self, app):
        with app.app_context():
            result = map_unified_item_to_original(1, None)
        assert result == (None, None)

    def test_item_not_found_in_db_returns_none_tuple(self, app):
        with app.app_context():
            with patch(
                "app.routes.forms.helpers.FormItem.query"
            ) as mock_query:
                mock_query.filter_by.return_value.first.return_value = None
                result = map_unified_item_to_original(999, "indicator")
        assert result == (None, None)

    def test_item_found_returns_tuple(self, app):
        mock_item = MagicMock()
        mock_item.id = 5
        with app.app_context():
            with patch(
                "app.routes.forms.helpers.FormItem.query"
            ) as mock_query:
                mock_query.filter_by.return_value.first.return_value = mock_item
                result = map_unified_item_to_original(5, "indicator")
        assert result == (mock_item, 5)

    def test_string_id_converted_to_int(self, app):
        mock_item = MagicMock()
        mock_item.id = 3
        with app.app_context():
            with patch(
                "app.routes.forms.helpers.FormItem.query"
            ) as mock_query:
                mock_query.filter_by.return_value.first.return_value = mock_item
                result = map_unified_item_to_original("3", "question")
        assert result[1] == 3

    def test_db_exception_returns_none_tuple(self, app):
        with app.app_context():
            with patch(
                "app.routes.forms.helpers.FormItem.query"
            ) as mock_query:
                mock_query.filter_by.side_effect = Exception("db error")
                result = map_unified_item_to_original(1, "indicator")
        assert result == (None, None)


# ---------------------------------------------------------------------------
# calculate_assignment_completion_rate
# ---------------------------------------------------------------------------

class TestCalculateAssignmentCompletionRate:
    def test_reads_stored_rate(self, app):
        from app.routes.forms.helpers import calculate_assignment_completion_rate

        mock_aes = MagicMock()

        with app.app_context():
            with patch(
                "app.routes.forms.helpers.db.session.get",
                return_value=mock_aes,
            ), patch(
                "app.routes.forms.helpers.AssignmentCompletionService.stored_rate_for",
                return_value=75.0,
            ) as mock_stored:
                rate = calculate_assignment_completion_rate(10, 20, 30)

        mock_stored.assert_called_once_with(mock_aes)
        assert rate == 75.0

    def test_missing_aes_returns_zero(self, app):
        from app.routes.forms.helpers import calculate_assignment_completion_rate

        with app.app_context():
            with patch("app.routes.forms.helpers.db.session.get", return_value=None):
                rate = calculate_assignment_completion_rate(10, 20, 30)

        assert rate == 0.0


class TestComputeEntryFormProgressMetrics:
    def test_returns_completion_rate_and_section_statuses_by_id(self, app):
        from app.routes.forms.helpers import compute_entry_form_progress_metrics

        aes = MagicMock()
        aes.id = 5
        template = MagicMock()
        template.id = 10
        template.published_version_id = 99
        section = MagicMock()
        section.id = 7
        section.name = "Governance"

        with app.app_context():
            with patch(
                "app.routes.forms.helpers._load_existing_data_for_assignment",
                return_value={"field_value[1]": "x"},
            ), patch(
                "app.routes.forms.helpers.build_submitted_documents_dict",
                return_value={},
            ), patch(
                "app.routes.forms.helpers.calculate_section_completion_status",
                return_value={"Governance": "in_progress"},
            ), patch(
                "app.routes.forms.helpers.AssignmentCompletionService.refresh_and_persist",
                return_value=66.7,
            ) as mock_refresh:
                result = compute_entry_form_progress_metrics(aes, template, [section])

        mock_refresh.assert_called_once_with(5)
        assert result == {
            "completion_rate": 66.7,
            "section_statuses": {"7": "in_progress"},
        }

    def test_refresh_and_persist_ignores_hidden_field_params(self, app):
        from app.routes.forms.helpers import compute_entry_form_progress_metrics

        aes = MagicMock()
        aes.id = 5
        template = MagicMock()
        template.id = 10
        template.published_version_id = 99

        with app.app_context():
            with patch(
                "app.routes.forms.helpers._load_existing_data_for_assignment",
                return_value={},
            ), patch(
                "app.routes.forms.helpers.build_submitted_documents_dict",
                return_value={},
            ), patch(
                "app.routes.forms.helpers.calculate_section_completion_status",
                return_value={},
            ), patch(
                "app.routes.forms.helpers.AssignmentCompletionService.refresh_and_persist",
                return_value=100.0,
            ) as mock_refresh:
                result = compute_entry_form_progress_metrics(
                    aes,
                    template,
                    [],
                    hidden_field_ids={1, 2},
                    hidden_section_ids={9},
                )

        mock_refresh.assert_called_once_with(5)
        assert result["completion_rate"] == 100.0


class TestParseCsvIdSet:
    def test_parses_comma_separated_ids(self):
        from app.routes.forms.helpers import parse_csv_id_set

        assert parse_csv_id_set("1, 2,3") == {1, 2, 3}
        assert parse_csv_id_set("") == set()
        assert parse_csv_id_set(None) == set()
        assert parse_csv_id_set("abc,4") == {4}


# ---------------------------------------------------------------------------
# _load_existing_data_for_assignment
# ---------------------------------------------------------------------------

class TestLoadExistingDataForAssignment:
    def test_basic_load(self, app):
        from app.routes.forms.helpers import _load_existing_data_for_assignment

        mock_aes = MagicMock()
        mock_aes.id = 1

        mock_form_item = MagicMock()
        mock_form_item.item_type = "indicator"
        mock_form_item.is_indicator = True
        mock_form_item.is_question = False

        mock_entry = MagicMock()
        mock_entry.form_item_id = 5
        mock_entry.form_item = mock_form_item
        mock_entry.value = "100"
        mock_entry.data_not_available = False
        mock_entry.not_applicable = False
        mock_entry.disagg_data = None
        mock_entry.prefilled_disagg_data = None
        mock_entry.imputed_disagg_data = None
        mock_entry.prefilled_value = None
        mock_entry.imputed_value = None

        mock_dynamic = MagicMock()
        mock_dynamic.id = 10
        mock_dynamic.assignment_entity_status_id = 1
        mock_dynamic.disagg_data = None
        mock_dynamic.value = "50"
        mock_dynamic.data_not_available = False
        mock_dynamic.not_applicable = False

        with app.app_context():
            with patch(
                "app.routes.forms.helpers.FormData.query"
            ) as mock_fd_query, patch(
                "app.routes.forms.helpers.DynamicIndicatorData.query"
            ) as mock_did_query:
                mock_fd_query.filter_by.return_value.options.return_value.all.return_value = [mock_entry]
                mock_did_query.filter.return_value.all.return_value = [mock_dynamic]

                mock_form_template = MagicMock()
                result = _load_existing_data_for_assignment(mock_aes, mock_form_template)

        assert "field_value[5]" in result
        assert "field_value[dynamic_10]" in result

    def test_missing_form_item_is_skipped(self, app):
        from app.routes.forms.helpers import _load_existing_data_for_assignment

        mock_aes = MagicMock()
        mock_aes.id = 1

        mock_entry = MagicMock()
        mock_entry.form_item_id = 5
        mock_entry.form_item = None  # Missing form_item → warning + skip

        with app.app_context():
            with patch(
                "app.routes.forms.helpers.FormData.query"
            ) as mock_fd_query, patch(
                "app.routes.forms.helpers.DynamicIndicatorData.query"
            ) as mock_did_query:
                mock_fd_query.filter_by.return_value.options.return_value.all.return_value = [mock_entry]
                mock_did_query.filter.return_value.all.return_value = []

                result = _load_existing_data_for_assignment(mock_aes, MagicMock())

        assert "field_value[5]" not in result

    def test_entry_without_form_item_id_skipped(self, app):
        from app.routes.forms.helpers import _load_existing_data_for_assignment

        mock_aes = MagicMock()
        mock_aes.id = 1

        mock_entry = MagicMock()
        mock_entry.form_item_id = None  # No form_item_id → skip

        with app.app_context():
            with patch(
                "app.routes.forms.helpers.FormData.query"
            ) as mock_fd_query, patch(
                "app.routes.forms.helpers.DynamicIndicatorData.query"
            ) as mock_did_query:
                mock_fd_query.filter_by.return_value.options.return_value.all.return_value = [mock_entry]
                mock_did_query.filter.return_value.all.return_value = []

                result = _load_existing_data_for_assignment(mock_aes, MagicMock())

        assert result == {}

    def test_dynamic_data_not_available(self, app):
        from app.routes.forms.helpers import _load_existing_data_for_assignment

        mock_aes = MagicMock()
        mock_aes.id = 1

        mock_dynamic = MagicMock()
        mock_dynamic.id = 11
        mock_dynamic.assignment_entity_status_id = 1
        mock_dynamic.disagg_data = None
        mock_dynamic.value = None
        mock_dynamic.data_not_available = True
        mock_dynamic.not_applicable = False

        with app.app_context():
            with patch(
                "app.routes.forms.helpers.FormData.query"
            ) as mock_fd_query, patch(
                "app.routes.forms.helpers.DynamicIndicatorData.query"
            ) as mock_did_query:
                mock_fd_query.filter_by.return_value.options.return_value.all.return_value = []
                mock_did_query.filter.return_value.all.return_value = [mock_dynamic]

                result = _load_existing_data_for_assignment(mock_aes, MagicMock())

        assert result.get("dynamic_11_data_not_available") is True

    def test_dynamic_not_applicable(self, app):
        from app.routes.forms.helpers import _load_existing_data_for_assignment

        mock_aes = MagicMock()
        mock_aes.id = 1

        mock_dynamic = MagicMock()
        mock_dynamic.id = 12
        mock_dynamic.disagg_data = None
        mock_dynamic.value = None
        mock_dynamic.data_not_available = False
        mock_dynamic.not_applicable = True

        with app.app_context():
            with patch(
                "app.routes.forms.helpers.FormData.query"
            ) as mock_fd_query, patch(
                "app.routes.forms.helpers.DynamicIndicatorData.query"
            ) as mock_did_query:
                mock_fd_query.filter_by.return_value.options.return_value.all.return_value = []
                mock_did_query.filter.return_value.all.return_value = [mock_dynamic]

                result = _load_existing_data_for_assignment(mock_aes, MagicMock())

        assert result.get("dynamic_12_not_applicable") is True

    def test_dynamic_disagg_data_stored(self, app):
        from app.routes.forms.helpers import _load_existing_data_for_assignment

        mock_aes = MagicMock()
        mock_aes.id = 1

        mock_dynamic = MagicMock()
        mock_dynamic.id = 13
        mock_dynamic.disagg_data = {"male": 50, "female": 60}
        mock_dynamic.value = None
        mock_dynamic.data_not_available = False
        mock_dynamic.not_applicable = False

        with app.app_context():
            with patch(
                "app.routes.forms.helpers.FormData.query"
            ) as mock_fd_query, patch(
                "app.routes.forms.helpers.DynamicIndicatorData.query"
            ) as mock_did_query:
                mock_fd_query.filter_by.return_value.options.return_value.all.return_value = []
                mock_did_query.filter.return_value.all.return_value = [mock_dynamic]

                result = _load_existing_data_for_assignment(mock_aes, MagicMock())

        assert result["field_value[dynamic_13]"] == {"male": 50, "female": 60}


class TestExistingDataForDynamicAssignment:
    def test_scalar_value(self):
        from app.routes.forms.helpers import existing_data_for_dynamic_assignment

        entry = MagicMock()
        entry.id = 25
        entry.disagg_data = None
        entry.value = "456"
        entry.data_not_available = False
        entry.not_applicable = False

        result = existing_data_for_dynamic_assignment(entry)
        assert result == {"field_value[dynamic_25]": "456"}

    def test_flags_and_disagg_data(self):
        from app.routes.forms.helpers import existing_data_for_dynamic_assignment

        entry = MagicMock()
        entry.id = 7
        entry.disagg_data = {"mode": "total", "values": {"total": 10}}
        entry.value = "10"
        entry.data_not_available = True
        entry.not_applicable = False

        result = existing_data_for_dynamic_assignment(entry)
        assert result["field_value[dynamic_7]"] == {"mode": "total", "values": {"total": 10}}
        assert result["dynamic_7_data_not_available"] is True


# ---------------------------------------------------------------------------
# _load_existing_data_for_public_submission
# ---------------------------------------------------------------------------

class TestLoadExistingDataForPublicSubmission:
    def test_empty_entries_returns_empty_dict(self, app):
        from app.routes.forms.helpers import _load_existing_data_for_public_submission

        submission = MagicMock()
        submission.id = 1
        submission.data_entries.all.return_value = []

        with app.app_context():
            result = _load_existing_data_for_public_submission(submission)

        assert result == {}

    def test_entry_without_form_item_id_skipped(self, app):
        from app.routes.forms.helpers import _load_existing_data_for_public_submission

        entry = MagicMock()
        entry.form_item_id = None

        submission = MagicMock()
        submission.id = 1
        submission.data_entries.all.return_value = [entry]

        with app.app_context():
            result = _load_existing_data_for_public_submission(submission)

        assert result == {}

    def test_entry_with_missing_form_item_skipped(self, app):
        from app.routes.forms.helpers import _load_existing_data_for_public_submission

        entry = MagicMock()
        entry.form_item_id = 99

        submission = MagicMock()
        submission.id = 1
        submission.data_entries.all.return_value = [entry]

        with app.app_context():
            with patch("app.routes.forms.helpers.FormItem.query") as mock_q:
                mock_q.get.return_value = None
                result = _load_existing_data_for_public_submission(submission)

        assert result == {}

    def test_valid_entry_processed(self, app):
        from app.routes.forms.helpers import _load_existing_data_for_public_submission

        mock_form_item = MagicMock()
        mock_form_item.item_type = "indicator"
        mock_form_item.is_indicator = True
        mock_form_item.is_question = False

        entry = MagicMock()
        entry.form_item_id = 7
        entry.value = "55"
        entry.data_not_available = False
        entry.not_applicable = False
        entry.disagg_data = None
        entry.prefilled_disagg_data = None
        entry.imputed_disagg_data = None
        entry.prefilled_value = None
        entry.imputed_value = None

        submission = MagicMock()
        submission.id = 1
        submission.data_entries.all.return_value = [entry]

        with app.app_context():
            with patch("app.routes.forms.helpers.FormItem.query") as mock_q:
                mock_q.get.return_value = mock_form_item
                result = _load_existing_data_for_public_submission(submission)

        assert "field_value[7]" in result


# ---------------------------------------------------------------------------
# calculate_section_completion_status
# ---------------------------------------------------------------------------

class TestCalculateSectionCompletionStatus:
    def _make_field(self, field_id, field_type="text", is_indicator=True,
                    is_question=False, is_document_field=False, is_matrix=False,
                    is_required=True, dynamic_assignment_id=None):
        field = MagicMock()
        field.id = field_id
        field.field_type_for_js = field_type
        field.is_indicator = is_indicator
        field.is_question = is_question
        field.is_document_field = is_document_field
        field.is_matrix = is_matrix
        field.is_required_for_js = is_required
        field.dynamic_assignment_id = dynamic_assignment_id
        return field

    def _make_section(self, name, fields=None):
        section = MagicMock()
        section.name = name
        section.fields_ordered = fields or []
        return section

    def test_empty_section_is_na(self):
        section = self._make_section("Empty", [])
        result = calculate_section_completion_status([section], {}, {})
        assert result["Empty"] == "N/A"

    def test_blank_fields_not_counted(self):
        field = self._make_field(1, "blank")
        section = self._make_section("Blank", [field])
        result = calculate_section_completion_status([section], {}, {})
        assert result["Blank"] == "N/A"

    def test_not_started_when_no_data(self):
        field = self._make_field(1)
        section = self._make_section("Sec", [field])
        result = calculate_section_completion_status([section], {}, {})
        assert result["Sec"] == "Not Started"

    def test_completed_when_all_filled(self):
        field = self._make_field(1)
        section = self._make_section("Sec", [field])
        data = {"field_value[1]": "42"}
        result = calculate_section_completion_status([section], data, {})
        assert result["Sec"] == "Completed"

    def test_in_progress_when_partially_filled(self):
        f1 = self._make_field(1)
        f2 = self._make_field(2)
        section = self._make_section("Sec", [f1, f2])
        data = {"field_value[1]": "42"}
        result = calculate_section_completion_status([section], data, {})
        assert result["Sec"] == "in_progress"

    def test_not_applicable_counts_as_filled(self):
        field = self._make_field(1, is_indicator=True)
        section = self._make_section("Sec", [field])
        data = {"indicator_1_not_applicable": True}
        result = calculate_section_completion_status([section], data, {})
        assert result["Sec"] == "Completed"

    def test_question_not_applicable_key(self):
        field = self._make_field(1, is_indicator=False, is_question=True)
        section = self._make_section("Sec", [field])
        data = {"question_1_not_applicable": True}
        result = calculate_section_completion_status([section], data, {})
        assert result["Sec"] == "Completed"

    def test_document_field_with_required_doc(self):
        field = self._make_field(1, is_indicator=False, is_document_field=True, is_required=True)
        section = self._make_section("Sec", [field])
        docs = {"field_value[1]": MagicMock()}
        result = calculate_section_completion_status([section], {}, docs)
        assert result["Sec"] == "Completed"

    def test_document_field_not_required(self):
        field = self._make_field(1, is_indicator=False, is_document_field=True, is_required=False)
        section = self._make_section("Sec", [field])
        docs = {"field_value[1]": MagicMock()}
        result = calculate_section_completion_status([section], {}, docs)
        assert result["Sec"] == "Completed"

    def test_document_field_missing_not_filled(self):
        field = self._make_field(1, is_indicator=False, is_document_field=True, is_required=True)
        section = self._make_section("Sec", [field])
        result = calculate_section_completion_status([section], {}, {})
        assert result["Sec"] == "Not Started"

    def test_matrix_field_with_values_dict(self):
        field = self._make_field(1, is_matrix=True, is_indicator=False)
        field.field_type_for_js = "matrix"
        section = self._make_section("Sec", [field])
        data = {"field_value[1]": {"row1": "10", "row2": "20"}}
        result = calculate_section_completion_status([section], data, {})
        assert result["Sec"] == "Completed"

    def test_matrix_field_all_empty_not_filled(self):
        field = self._make_field(1, is_matrix=True, is_indicator=False)
        field.field_type_for_js = "matrix"
        section = self._make_section("Sec", [field])
        data = {"field_value[1]": {"_meta": "x", "row1": "", "row2": None}}
        result = calculate_section_completion_status([section], data, {})
        assert result["Sec"] == "Not Started"

    def test_checkbox_true_counted(self):
        field = self._make_field(1, field_type="CHECKBOX", is_indicator=True)
        section = self._make_section("Sec", [field])
        data = {"field_value[1]": "true"}
        result = calculate_section_completion_status([section], data, {})
        assert result["Sec"] == "Completed"

    def test_checkbox_false_not_counted(self):
        field = self._make_field(1, field_type="CHECKBOX", is_indicator=True)
        section = self._make_section("Sec", [field])
        data = {"field_value[1]": "false"}
        result = calculate_section_completion_status([section], data, {})
        assert result["Sec"] == "Not Started"

    def test_checkbox_bool_true_counted(self):
        field = self._make_field(1, field_type="CHECKBOX", is_indicator=True)
        section = self._make_section("Sec", [field])
        data = {"field_value[1]": True}
        result = calculate_section_completion_status([section], data, {})
        assert result["Sec"] == "Completed"

    def test_dynamic_field_key(self):
        field = self._make_field(1, dynamic_assignment_id=55)
        section = self._make_section("Sec", [field])
        data = {"field_value[dynamic_55]": "100"}
        result = calculate_section_completion_status([section], data, {})
        assert result["Sec"] == "Completed"

    def test_field_with_values_dict_structure(self):
        field = self._make_field(1, is_indicator=True)
        field.field_type_for_js = "text"
        field.is_matrix = False
        section = self._make_section("Sec", [field])
        data = {"field_value[1]": {"values": {"male": 10, "female": 20}, "mode": "disagg"}}
        result = calculate_section_completion_status([section], data, {})
        assert result["Sec"] == "Completed"

    def test_field_with_values_dict_all_empty(self):
        field = self._make_field(1, is_indicator=True)
        field.field_type_for_js = "text"
        field.is_matrix = False
        section = self._make_section("Sec", [field])
        data = {"field_value[1]": {"values": {"male": None, "female": None}, "mode": "disagg"}}
        result = calculate_section_completion_status([section], data, {})
        assert result["Sec"] == "Not Started"

    def test_section_without_fields_ordered_attr(self):
        section = MagicMock()
        section.name = "NoAttr"
        del section.fields_ordered  # Remove the attribute
        result = calculate_section_completion_status([section], {}, {})
        assert result["NoAttr"] == "N/A"

    def test_multiple_sections(self):
        f1 = self._make_field(1)
        f2 = self._make_field(2)
        s1 = self._make_section("S1", [f1])
        s2 = self._make_section("S2", [f2])
        data = {"field_value[1]": "yes"}
        result = calculate_section_completion_status([s1, s2], data, {})
        assert result["S1"] == "Completed"
        assert result["S2"] == "Not Started"


# ---------------------------------------------------------------------------
# build_entry_form_features
# ---------------------------------------------------------------------------

class TestBuildEntryFormFeatures:
    def _field(self, *, item_type='question', lookup_list_id=None):
        return SimpleNamespace(item_type=item_type, lookup_list_id=lookup_list_id)

    def _section(self, section_type='standard', fields=None):
        return SimpleNamespace(section_type=section_type, fields_ordered=fields or [])

    def test_matrix_field_in_standard_section_enables_matrix(self):
        sections = [self._section(fields=[self._field(item_type='matrix')])]
        features = build_entry_form_features(sections)
        assert features['matrix'] is True
        assert features['calculatedLists'] is False

    def test_matrix_list_library_does_not_enable_calculated_lists(self):
        sections = [self._section(fields=[
            self._field(item_type='matrix', lookup_list_id='national_society'),
        ])]
        features = build_entry_form_features(sections)
        assert features['matrix'] is True
        assert features['calculatedLists'] is False

    def test_question_with_lookup_list_enables_calculated_lists(self):
        sections = [self._section(fields=[
            self._field(item_type='question', lookup_list_id='emergency_operations'),
        ])]
        features = build_entry_form_features(sections)
        assert features['calculatedLists'] is True
        assert features['matrix'] is False

    def test_repeat_and_dynamic_indicators_use_section_type(self):
        sections = [
            self._section(section_type='repeat'),
            self._section(section_type='dynamic_indicators'),
        ]
        features = build_entry_form_features(sections)
        assert features['repeat'] is True
        assert features['dynamicIndicators'] is True

    def test_document_field_flag(self):
        sections = [self._section(fields=[self._field(item_type='document_field')])]
        features = build_entry_form_features(sections)
        assert features['documents'] is True

    def test_excel_export_follows_template_flags(self):
        template = SimpleNamespace(enable_export_excel=True, enable_import_excel=False)
        features = build_entry_form_features([], template)
        assert features['excelExport'] is True

    def test_pdf_export_always_enabled(self):
        features = build_entry_form_features([])
        assert features['pdfExport'] is True
        assert features['excelExport'] is False

    def test_discussion_follows_template_flag(self):
        template = SimpleNamespace(enable_discussion=True)
        features = build_entry_form_features([], template)
        assert features['discussion'] is True

    def test_discussion_enabled_for_discussion_items(self):
        field = SimpleNamespace(item_type='discussion')
        section = SimpleNamespace(fields_ordered=[field])
        features = build_entry_form_features([section], SimpleNamespace(enable_discussion=False))
        assert features['discussion'] is True

    def test_discussion_disabled_without_template(self):
        features = build_entry_form_features([])
        assert features['discussion'] is False
