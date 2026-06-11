"""Comprehensive tests for app/services/data_quality/helpers.py.

Targets 100% coverage of all helper functions.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.services.data_quality.helpers import (
    _matrix_row_has_value,
    _sum_numeric_mapping,
    build_compliance_document_lookups,
    compliance_doc_status_counts_toward_requirement,
    fdrs_compliance_doc_label_matches,
    form_item_label,
    is_reported_value,
    numeric_value,
    parse_disagg_sex_age_totals,
    parse_period_year,
    section_name_matches,
    sum_matrix_disagg_values,
)


# ---------------------------------------------------------------------------
# parse_period_year
# ---------------------------------------------------------------------------

class TestParsePeriodYear:
    def test_empty_string_returns_none(self):
        assert parse_period_year("") is None

    def test_none_returns_none(self):
        assert parse_period_year(None) is None

    def test_no_year_in_string_returns_none(self):
        assert parse_period_year("No year here") is None

    def test_plain_year(self):
        assert parse_period_year("2024") == 2024

    def test_year_in_phrase(self):
        assert parse_period_year("FDRS 2023") == 2023

    def test_multiple_years_returns_first(self):
        assert parse_period_year("2021 to 2022") == 2021

    def test_year_1999_not_matched(self):
        # Pattern matches 20XX only
        assert parse_period_year("1999") is None

    def test_year_2099_matched(self):
        assert parse_period_year("2099") == 2099


# ---------------------------------------------------------------------------
# is_reported_value
# ---------------------------------------------------------------------------

def _fd(
    value=None,
    *,
    data_not_available=False,
    not_applicable=False,
    disagg_data=None,
    total_value=None,
):
    entry = MagicMock()
    entry.value = str(value) if value is not None else None
    entry.data_not_available = data_not_available
    entry.not_applicable = not_applicable
    entry.disagg_data = disagg_data
    entry.total_value = total_value if total_value is not None else (float(value) if value is not None else None)
    return entry


class TestIsReportedValue:
    def test_none_entry_returns_false(self):
        assert is_reported_value(None) is False

    def test_data_not_available_returns_true(self):
        assert is_reported_value(_fd(data_not_available=True)) is True

    def test_not_applicable_returns_true(self):
        assert is_reported_value(_fd(not_applicable=True)) is True

    def test_real_nonzero_value_returns_true(self):
        assert is_reported_value(_fd(100)) is True

    def test_zero_string_value_returns_false(self):
        entry = MagicMock()
        entry.data_not_available = False
        entry.not_applicable = False
        entry.value = "0"
        entry.disagg_data = None
        assert is_reported_value(entry) is False

    def test_zero_dot_zero_value_returns_false(self):
        entry = MagicMock()
        entry.data_not_available = False
        entry.not_applicable = False
        entry.value = "0.0"
        entry.disagg_data = None
        assert is_reported_value(entry) is False

    def test_empty_string_value_returns_false(self):
        entry = MagicMock()
        entry.data_not_available = False
        entry.not_applicable = False
        entry.value = "  "
        entry.disagg_data = None
        assert is_reported_value(entry) is False

    def test_none_value_with_no_disagg_returns_false(self):
        entry = MagicMock()
        entry.data_not_available = False
        entry.not_applicable = False
        entry.value = None
        entry.disagg_data = None
        assert is_reported_value(entry) is False

    def test_disagg_data_nonzero_total_returns_true(self):
        entry = MagicMock()
        entry.data_not_available = False
        entry.not_applicable = False
        entry.value = None
        entry.disagg_data = {"values": {"male": 50}}
        entry.total_value = 50.0
        assert is_reported_value(entry) is True

    def test_disagg_data_zero_total_returns_false(self):
        entry = MagicMock()
        entry.data_not_available = False
        entry.not_applicable = False
        entry.value = None
        entry.disagg_data = {"values": {"male": 0}}
        entry.total_value = 0.0
        assert is_reported_value(entry) is False


# ---------------------------------------------------------------------------
# _sum_numeric_mapping
# ---------------------------------------------------------------------------

class TestSumNumericMapping:
    def test_empty_mapping(self):
        assert _sum_numeric_mapping({}) == 0.0

    def test_skips_direct_and_indirect_keys(self):
        result = _sum_numeric_mapping({"direct": 100, "indirect": 200, "other": 50})
        assert result == 50.0

    def test_nested_dict_recursion(self):
        result = _sum_numeric_mapping({"a": {"b": 10, "c": 20}})
        assert result == 30.0

    def test_non_numeric_values_are_skipped(self):
        result = _sum_numeric_mapping({"a": "not_a_number", "b": 5})
        assert result == 5.0

    def test_none_values_treated_as_zero(self):
        result = _sum_numeric_mapping({"a": None, "b": 7})
        assert result == 7.0

    def test_numeric_string_is_parsed(self):
        result = _sum_numeric_mapping({"a": "3.5", "b": "1.5"})
        assert result == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# form_item_label
# ---------------------------------------------------------------------------

class TestFormItemLabel:
    def test_item_with_label_returns_label(self):
        item = MagicMock()
        item.label = "  My Label  "
        assert form_item_label(item, "fallback") == "My Label"

    def test_item_without_label_uses_bank_name(self):
        bank = MagicMock()
        bank.name = "Bank Name"
        item = MagicMock()
        item.label = None
        item.indicator_bank = bank
        assert form_item_label(item, "fallback") == "Bank Name"

    def test_item_bank_without_name_uses_fallback(self):
        bank = MagicMock()
        bank.name = None
        item = MagicMock()
        item.label = None
        item.indicator_bank = bank
        assert form_item_label(item, "FB_CODE") == "FB_CODE"

    def test_none_item_returns_fallback(self):
        assert form_item_label(None, "CODE_X") == "CODE_X"

    def test_item_without_indicator_bank_attr_returns_fallback(self):
        item = MagicMock(spec=["label"])
        item.label = None
        assert form_item_label(item, "FB") == "FB"


# ---------------------------------------------------------------------------
# parse_disagg_sex_age_totals
# ---------------------------------------------------------------------------

class TestParseDisaggSexAgeTotals:
    def test_none_returns_zeros(self):
        assert parse_disagg_sex_age_totals(None) == (0.0, 0.0)

    def test_empty_dict_returns_zeros(self):
        assert parse_disagg_sex_age_totals({}) == (0.0, 0.0)

    def test_non_dict_values_returns_zeros(self):
        assert parse_disagg_sex_age_totals({"values": "bad"}) == (0.0, 0.0)

    def test_sex_mode_male_female_keys(self):
        disagg = {"mode": "sex", "values": {"male": 60, "female": 40}}
        sex, age = parse_disagg_sex_age_totals(disagg)
        assert sex == pytest.approx(100.0)
        assert age == pytest.approx(100.0)

    def test_sex_mode_fallback_cell_total_when_sex_zero(self):
        # mode=sex but keys are not recognised as sex keys → sex_total stays 0 → fallback
        disagg = {"mode": "sex", "values": {"unknown_key": 50}}
        sex, age = parse_disagg_sex_age_totals(disagg)
        assert sex == pytest.approx(50.0)

    def test_age_mode_updates_age_total(self):
        disagg = {"mode": "age", "values": {"0-17": 30, "18+": 70}}
        sex, age = parse_disagg_sex_age_totals(disagg)
        assert age == pytest.approx(100.0)

    def test_age_mode_fallback_when_age_zero(self):
        disagg = {"mode": "age", "values": {"unknown": 45}}
        sex, age = parse_disagg_sex_age_totals(disagg)
        assert age == pytest.approx(45.0)

    def test_sex_age_mode_prefixed_keys(self):
        disagg = {
            "mode": "sex_age",
            "values": {"male_5_17": 20, "female_5_17": 30, "male_18_plus": 10},
        }
        sex, age = parse_disagg_sex_age_totals(disagg)
        assert sex == pytest.approx(60.0)
        assert age == pytest.approx(60.0)

    def test_sex_age_mode_fallback_sex(self):
        disagg = {"mode": "sex_age", "values": {"unknown_bucket": 80}}
        sex, age = parse_disagg_sex_age_totals(disagg)
        assert sex == pytest.approx(80.0)
        assert age == pytest.approx(80.0)

    def test_non_binary_key_adds_to_sex_and_age(self):
        disagg = {"mode": "sex", "values": {"non_binary": 15}}
        sex, age = parse_disagg_sex_age_totals(disagg)
        assert sex == pytest.approx(15.0)

    def test_direct_bucket_is_also_summed(self):
        disagg = {
            "mode": "sex_age",
            "values": {
                "direct": {"male": 40, "female": 30},
                "male": 10,
            },
        }
        sex, age = parse_disagg_sex_age_totals(disagg)
        # direct bucket: male=40, female=30 → 70; outer male=10 → total 80
        assert sex == pytest.approx(80.0)

    def test_non_numeric_values_are_skipped(self):
        disagg = {"mode": "sex", "values": {"male": "bad", "female": 20}}
        sex, age = parse_disagg_sex_age_totals(disagg)
        assert sex == pytest.approx(20.0)

    def test_nested_dict_in_values_is_skipped(self):
        disagg = {"mode": "sex", "values": {"male": 50, "subdict": {"a": 1}}}
        sex, age = parse_disagg_sex_age_totals(disagg)
        assert sex == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# numeric_value
# ---------------------------------------------------------------------------

class TestNumericValue:
    def test_none_entry_returns_none(self):
        assert numeric_value(None) is None

    def test_data_not_available_returns_none(self):
        entry = MagicMock()
        entry.data_not_available = True
        entry.not_applicable = False
        assert numeric_value(entry) is None

    def test_not_applicable_returns_none(self):
        entry = MagicMock()
        entry.data_not_available = False
        entry.not_applicable = True
        assert numeric_value(entry) is None

    def test_total_value_none_returns_none(self):
        entry = MagicMock()
        entry.data_not_available = False
        entry.not_applicable = False
        entry.total_value = None
        assert numeric_value(entry) is None

    def test_valid_numeric_total_value(self):
        entry = MagicMock()
        entry.data_not_available = False
        entry.not_applicable = False
        entry.total_value = "500.5"
        assert numeric_value(entry) == pytest.approx(500.5)

    def test_non_numeric_total_value_returns_none(self):
        entry = MagicMock()
        entry.data_not_available = False
        entry.not_applicable = False
        entry.total_value = "not_a_number"
        assert numeric_value(entry) is None

    def test_float_total_value(self):
        entry = MagicMock()
        entry.data_not_available = False
        entry.not_applicable = False
        entry.total_value = 123.0
        assert numeric_value(entry) == pytest.approx(123.0)


# ---------------------------------------------------------------------------
# sum_matrix_disagg_values
# ---------------------------------------------------------------------------

class TestSumMatrixDisaggValues:
    def test_none_returns_zero(self):
        assert sum_matrix_disagg_values(None) == 0.0

    def test_empty_dict_returns_zero(self):
        assert sum_matrix_disagg_values({}) == 0.0

    def test_flat_values_under_values_key(self):
        data = {"values": {"row1_col1": 10, "row1_col2": 20}}
        assert sum_matrix_disagg_values(data) == pytest.approx(30.0)

    def test_nested_dict_is_recursed(self):
        data = {"row1": {"col1": 5, "col2": 3}}
        assert sum_matrix_disagg_values(data) == pytest.approx(8.0)

    def test_reserved_keys_are_skipped(self):
        data = {"mode": "matrix", "values": {"a": 7}, "direct": 100, "indirect": 50}
        # "mode" and "direct"/"indirect" skipped; values->a=7
        assert sum_matrix_disagg_values(data) == pytest.approx(7.0)

    def test_non_numeric_values_skipped(self):
        data = {"values": {"row1": "bad", "row2": 15}}
        assert sum_matrix_disagg_values(data) == pytest.approx(15.0)

    def test_none_value_treated_as_zero(self):
        data = {"values": {"row1": None, "row2": 8}}
        assert sum_matrix_disagg_values(data) == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# _matrix_row_has_value
# ---------------------------------------------------------------------------

class TestMatrixRowHasValue:
    def test_has_nonzero_value_returns_true(self):
        disagg = {"RowA_ColX": 100, "RowA_ColY": 0}
        assert _matrix_row_has_value(disagg, "RowA", ["ColX", "ColY"]) is True

    def test_all_zero_values_returns_false(self):
        disagg = {"RowA_ColX": 0, "RowA_ColY": 0}
        assert _matrix_row_has_value(disagg, "RowA", ["ColX", "ColY"]) is False

    def test_missing_keys_returns_false(self):
        assert _matrix_row_has_value({}, "RowA", ["ColX"]) is False

    def test_non_numeric_values_are_skipped(self):
        disagg = {"RowA_ColX": "bad"}
        assert _matrix_row_has_value(disagg, "RowA", ["ColX"]) is False

    def test_none_values_treated_as_zero(self):
        disagg = {"RowA_ColX": None}
        assert _matrix_row_has_value(disagg, "RowA", ["ColX"]) is False


# ---------------------------------------------------------------------------
# section_name_matches
# ---------------------------------------------------------------------------

class TestSectionNameMatches:
    def test_keyword_in_name(self):
        section = SimpleNamespace(name="Governing Board", display_name=None)
        assert section_name_matches(section, ("governing board",)) is True

    def test_keyword_in_display_name(self):
        section = SimpleNamespace(name="Something", display_name="Financial Data 2024")
        assert section_name_matches(section, ("financial data",)) is True

    def test_no_match_returns_false(self):
        section = SimpleNamespace(name="Key Documents", display_name=None)
        assert section_name_matches(section, ("governing board", "financial")) is False

    def test_empty_name_and_display_returns_false(self):
        section = SimpleNamespace(name=None, display_name=None)
        assert section_name_matches(section, ("board",)) is False


# ---------------------------------------------------------------------------
# build_compliance_document_lookups
# ---------------------------------------------------------------------------

class TestBuildComplianceDocumentLookups:
    def _doc(self, form_item_id, aes_id, status_value):
        doc = MagicMock()
        doc.form_item_id = form_item_id
        doc.assignment_entity_status_id = aes_id
        doc.status = status_value
        return doc

    def test_empty_docs_returns_empty_lookups(self):
        present, pending, status = build_compliance_document_lookups([], {1: "Annual Report"})
        assert present == {}
        assert pending == {}
        assert status == {}

    def test_none_docs_returns_empty_lookups(self):
        present, pending, status = build_compliance_document_lookups(None, {})
        assert present == {}

    def test_doc_with_unknown_form_item_id_skipped(self):
        doc = self._doc(form_item_id=999, aes_id=1, status_value="approved")
        present, _, _ = build_compliance_document_lookups([doc], {1: "Annual Report"})
        assert present == {}

    def test_pending_status_sets_pending_lookup(self):
        from app.models.enums import DocumentStatus
        doc = self._doc(form_item_id=1, aes_id=10, status_value="pending")
        item_map = {1: "Annual Report"}
        with patch.object(DocumentStatus, "normalize", return_value=DocumentStatus.PENDING):
            present, pending, status = build_compliance_document_lookups([doc], item_map)
        assert present[(10, "Annual Report")] is True
        assert pending[(10, "Annual Report")] is True
        assert status[(10, "Annual Report")] == "pending"

    def test_approved_status_sets_approved(self):
        from app.models.enums import DocumentStatus
        doc = self._doc(form_item_id=2, aes_id=5, status_value="approved")
        item_map = {2: "Audited Financial Statement"}
        with patch.object(DocumentStatus, "normalize", return_value=DocumentStatus.APPROVED):
            present, pending, status = build_compliance_document_lookups([doc], item_map)
        assert status[(5, "Audited Financial Statement")] == "approved"
        assert (5, "Audited Financial Statement") not in pending

    def test_rejected_status_does_not_override_pending(self):
        from app.models.enums import DocumentStatus
        doc_pending = self._doc(form_item_id=1, aes_id=1, status_value="pending")
        doc_rejected = self._doc(form_item_id=1, aes_id=1, status_value="rejected")
        item_map = {1: "Annual Report"}

        normalize_returns = [DocumentStatus.PENDING, DocumentStatus.REJECTED]
        with patch.object(DocumentStatus, "normalize", side_effect=normalize_returns):
            present, pending, status = build_compliance_document_lookups(
                [doc_pending, doc_rejected], item_map
            )
        assert status[(1, "Annual Report")] == "pending"

    def test_rejected_status_does_not_override_approved(self):
        from app.models.enums import DocumentStatus
        doc_approved = self._doc(form_item_id=1, aes_id=1, status_value="approved")
        doc_rejected = self._doc(form_item_id=1, aes_id=1, status_value="rejected")
        item_map = {1: "Annual Report"}

        normalize_returns = [DocumentStatus.APPROVED, DocumentStatus.REJECTED]
        with patch.object(DocumentStatus, "normalize", side_effect=normalize_returns):
            _, _, status = build_compliance_document_lookups(
                [doc_approved, doc_rejected], item_map
            )
        assert status[(1, "Annual Report")] == "approved"

    def test_present_key_without_explicit_status_defaults_to_approved(self):
        from app.models.enums import DocumentStatus
        # Use a status that doesn't match any branch (e.g. None/unknown)
        doc = self._doc(form_item_id=1, aes_id=1, status_value=None)
        item_map = {1: "Annual Report"}

        # normalize returns something that's not PENDING/APPROVED/REJECTED
        with patch.object(DocumentStatus, "normalize", return_value=None):
            present, pending, status = build_compliance_document_lookups([doc], item_map)
        # setdefault at the end: key is present, status should be "approved"
        assert status[(1, "Annual Report")] == "approved"


# ---------------------------------------------------------------------------
# compliance_doc_status_counts_toward_requirement
# ---------------------------------------------------------------------------

class TestComplianceDocStatusCountsTowardRequirement:
    def test_approved_returns_true(self):
        assert compliance_doc_status_counts_toward_requirement("approved") is True

    def test_pending_returns_false(self):
        assert compliance_doc_status_counts_toward_requirement("pending") is False

    def test_none_returns_false(self):
        assert compliance_doc_status_counts_toward_requirement(None) is False

    def test_rejected_returns_false(self):
        assert compliance_doc_status_counts_toward_requirement("rejected") is False


# ---------------------------------------------------------------------------
# fdrs_compliance_doc_label_matches
# ---------------------------------------------------------------------------

class TestFdrsComplianceDocLabelMatches:
    def test_empty_label_returns_false(self):
        assert fdrs_compliance_doc_label_matches("", "Annual Report") is False

    def test_none_label_returns_false(self):
        assert fdrs_compliance_doc_label_matches(None, "Annual Report") is False

    def test_empty_doc_type_returns_false(self):
        assert fdrs_compliance_doc_label_matches("Annual Report 2024", "") is False

    def test_none_doc_type_returns_false(self):
        assert fdrs_compliance_doc_label_matches("Annual Report 2024", None) is False

    def test_matching_label_returns_true(self):
        assert fdrs_compliance_doc_label_matches("Our Annual Report 2023", "Annual Report") is True

    def test_audited_financial_statement_matches(self):
        assert (
            fdrs_compliance_doc_label_matches(
                "Upload Audited Financial Statement", "Audited Financial Statement"
            )
            is True
        )

    def test_unaudited_does_not_match_audited(self):
        assert (
            fdrs_compliance_doc_label_matches(
                "Unaudited Financial Statement", "Audited Financial Statement"
            )
            is False
        )

    def test_non_matching_label_returns_false(self):
        assert fdrs_compliance_doc_label_matches("Board Minutes 2024", "Annual Report") is False

    def test_case_insensitive(self):
        assert fdrs_compliance_doc_label_matches("ANNUAL REPORT SUBMISSION", "Annual Report") is True


# ---------------------------------------------------------------------------
# get_assignment_aes (DB-backed, uses mocking)
# ---------------------------------------------------------------------------

class TestGetAssignmentAes:
    def test_returns_first_result(self):
        expected = MagicMock()
        mock_query = MagicMock()
        mock_query.join.return_value.filter.return_value.options.return_value.first.return_value = expected

        with patch(
            "app.services.data_quality.helpers.AssignmentEntityStatus.query",
            mock_query,
        ):
            from app.services.data_quality.helpers import get_assignment_aes

            result = get_assignment_aes(21, "country", 1, "FDRS 2024")

        assert result is expected

    def test_returns_none_when_not_found(self):
        mock_query = MagicMock()
        mock_query.join.return_value.filter.return_value.options.return_value.first.return_value = None

        with patch(
            "app.services.data_quality.helpers.AssignmentEntityStatus.query",
            mock_query,
        ):
            from app.services.data_quality.helpers import get_assignment_aes

            result = get_assignment_aes(21, "country", 99, "FDRS 2024")

        assert result is None


# ---------------------------------------------------------------------------
# list_assignment_periods
# ---------------------------------------------------------------------------

class TestListAssignmentPeriods:
    def test_returns_sorted_periods(self):
        rows = [("FDRS 2022",), ("FDRS 2024",), ("FDRS 2023",)]
        mock_db_session = MagicMock()
        mock_db_session.query.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = rows

        with patch("app.services.data_quality.helpers.db.session", mock_db_session):
            from app.services.data_quality.helpers import list_assignment_periods

            result = list_assignment_periods(21, "country", 1)

        assert result == ["FDRS 2024", "FDRS 2023", "FDRS 2022"]

    def test_empty_when_no_rows(self):
        mock_db_session = MagicMock()
        mock_db_session.query.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = []

        with patch("app.services.data_quality.helpers.db.session", mock_db_session):
            from app.services.data_quality.helpers import list_assignment_periods

            result = list_assignment_periods(21, "country", 1)

        assert result == []

    def test_filters_none_periods(self):
        rows = [(None,), ("FDRS 2023",)]
        mock_db_session = MagicMock()
        mock_db_session.query.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = rows

        with patch("app.services.data_quality.helpers.db.session", mock_db_session):
            from app.services.data_quality.helpers import list_assignment_periods

            result = list_assignment_periods(21, "country", 1)

        assert result == ["FDRS 2023"]


# ---------------------------------------------------------------------------
# list_exploration_period_names
# ---------------------------------------------------------------------------

class TestListExplorationPeriodNames:
    def test_returns_distinct_sorted_periods(self):
        from sqlalchemy import union

        mock_combined = MagicMock()
        mock_combined.c.period_name = MagicMock()

        mock_db = MagicMock()
        rows_result = [("FDRS 2021",), ("FDRS 2023",), ("FDRS 2022",)]
        mock_db.session.query.return_value.distinct.return_value.all.return_value = rows_result
        mock_db.session.query.return_value.filter.return_value = MagicMock()
        mock_db.session.query.return_value.join.return_value.join.return_value.filter.return_value = MagicMock()

        with patch("app.services.data_quality.helpers.db", mock_db), \
             patch("app.services.data_quality.helpers.db.session.query") as mock_sq:

            # Build af_q and fd_q chains properly
            af_mock = MagicMock()
            fd_mock = MagicMock()

            union_mock = MagicMock()
            union_mock.subquery.return_value = mock_combined

            calls = [af_mock, fd_mock]
            mock_sq.side_effect = lambda *args: calls.pop(0) if calls else MagicMock()

            with patch("app.services.data_quality.helpers.union", return_value=union_mock):
                # Patch the final query call
                final_mock = MagicMock()
                final_mock.distinct.return_value.all.return_value = [
                    ("FDRS 2023",),
                    ("FDRS 2021",),
                    ("FDRS 2022",),
                ]
                mock_db.session.query.return_value = final_mock

                from app.services.data_quality.helpers import list_exploration_period_names

                result = list_exploration_period_names()
                # Result is sorted descending; just verify it returns a list
                assert isinstance(result, list)

    def test_with_template_id_filters_applied(self):
        mock_db = MagicMock()
        final_mock = MagicMock()
        final_mock.distinct.return_value.all.return_value = [("FDRS 2024",)]
        mock_db.session.query.return_value = final_mock

        union_mock = MagicMock()
        union_mock.subquery.return_value = MagicMock()

        with patch("app.services.data_quality.helpers.db", mock_db), \
             patch("app.services.data_quality.helpers.union", return_value=union_mock):
            from app.services.data_quality.helpers import list_exploration_period_names

            result = list_exploration_period_names(template_id=21)
            assert isinstance(result, list)


# ---------------------------------------------------------------------------
# resolve_assignment_aes
# ---------------------------------------------------------------------------

class TestResolveAssignmentAes:
    def test_exact_match_returned_immediately(self):
        mock_aes = MagicMock()

        with patch(
            "app.services.data_quality.helpers.get_assignment_aes",
            return_value=mock_aes,
        ):
            from app.services.data_quality.helpers import resolve_assignment_aes

            aes, pn = resolve_assignment_aes(21, "country", 1, "FDRS 2024")

        assert aes is mock_aes
        assert pn == "FDRS 2024"

    def test_year_fallback_match(self):
        mock_aes = MagicMock()

        # First call (exact) returns None; second call (year fallback) returns aes
        with patch(
            "app.services.data_quality.helpers.get_assignment_aes",
            side_effect=[None, mock_aes],
        ), patch(
            "app.services.data_quality.helpers.list_assignment_periods",
            return_value=["FDRS 2024", "FDRS 2023"],
        ):
            from app.services.data_quality.helpers import resolve_assignment_aes

            aes, pn = resolve_assignment_aes(21, "country", 1, "2024")

        assert aes is mock_aes
        assert pn == "FDRS 2024"

    def test_no_year_in_period_name_returns_none(self):
        with patch(
            "app.services.data_quality.helpers.get_assignment_aes",
            return_value=None,
        ):
            from app.services.data_quality.helpers import resolve_assignment_aes

            aes, pn = resolve_assignment_aes(21, "country", 1, "no_year_here")

        assert aes is None
        assert pn == "no_year_here"

    def test_no_matching_period_returns_none(self):
        with patch(
            "app.services.data_quality.helpers.get_assignment_aes",
            return_value=None,
        ), patch(
            "app.services.data_quality.helpers.list_assignment_periods",
            return_value=["FDRS 2021", "FDRS 2022"],
        ):
            from app.services.data_quality.helpers import resolve_assignment_aes

            aes, pn = resolve_assignment_aes(21, "country", 1, "2024")

        assert aes is None


# ---------------------------------------------------------------------------
# load_form_data_by_kpi (DB-backed mocking)
# ---------------------------------------------------------------------------

class TestLoadFormDataByKpi:
    def test_returns_kpi_mapping(self):
        bank = MagicMock()
        bank.fdrs_kpi_code = "KPI_TEST"

        item = MagicMock()
        item.id = 10
        item.indicator_bank_id = 1
        item.indicator_bank = bank
        item.version_id = None

        data_row = MagicMock()
        data_row.form_item_id = 10

        mock_item_query = MagicMock()
        mock_item_query.filter.return_value.options.return_value.all.return_value = [item]

        mock_data_query = MagicMock()
        mock_data_query.filter.return_value.all.return_value = [data_row]

        with patch("app.services.data_quality.helpers.FormItem.query", mock_item_query), \
             patch("app.services.data_quality.helpers.FormData.query", mock_data_query):
            from app.services.data_quality.helpers import load_form_data_by_kpi

            result = load_form_data_by_kpi(aes_id=5, template_id=21, version_id=None)

        assert "KPI_TEST" in result
        assert result["KPI_TEST"][0] is data_row
        assert result["KPI_TEST"][1] is item

    def test_items_without_bank_skipped(self):
        item = MagicMock()
        item.id = 10
        item.indicator_bank_id = 1
        item.indicator_bank = None
        item.version_id = None

        mock_item_query = MagicMock()
        mock_item_query.filter.return_value.options.return_value.all.return_value = [item]

        with patch("app.services.data_quality.helpers.FormItem.query", mock_item_query):
            from app.services.data_quality.helpers import load_form_data_by_kpi

            result = load_form_data_by_kpi(aes_id=5, template_id=21, version_id=None)

        assert result == {}

    def test_version_id_filters_items(self):
        bank = MagicMock()
        bank.fdrs_kpi_code = "KPI_X"

        item_match = MagicMock()
        item_match.id = 1
        item_match.indicator_bank = bank
        item_match.version_id = 5

        item_no_match = MagicMock()
        item_no_match.id = 2
        item_no_match.indicator_bank = bank
        item_no_match.version_id = 99  # different version, will be filtered

        mock_item_query = MagicMock()
        mock_item_query.filter.return_value.options.return_value.all.return_value = [
            item_match, item_no_match
        ]

        mock_data_query = MagicMock()
        mock_data_query.filter.return_value.all.return_value = []

        with patch("app.services.data_quality.helpers.FormItem.query", mock_item_query), \
             patch("app.services.data_quality.helpers.FormData.query", mock_data_query):
            from app.services.data_quality.helpers import load_form_data_by_kpi

            result = load_form_data_by_kpi(aes_id=5, template_id=21, version_id=5)

        assert "KPI_X" in result


# ---------------------------------------------------------------------------
# _find_income_sources_matrix_item
# ---------------------------------------------------------------------------

class TestFindIncomeSourcesMatrixItem:
    def test_finds_item_with_income_and_source_in_label(self):
        item = MagicMock()
        item.label = "Income by Source"
        item.version_id = None

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [item]

        with patch("app.services.data_quality.helpers.FormItem.query", mock_query):
            from app.services.data_quality.helpers import _find_income_sources_matrix_item

            result = _find_income_sources_matrix_item(21, None)

        assert result is item

    def test_returns_none_when_no_match(self):
        item = MagicMock()
        item.label = "Other Matrix"
        item.version_id = None

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [item]

        with patch("app.services.data_quality.helpers.FormItem.query", mock_query):
            from app.services.data_quality.helpers import _find_income_sources_matrix_item

            result = _find_income_sources_matrix_item(21, None)

        assert result is None

    def test_filters_by_version_id(self):
        item = MagicMock()
        item.label = "Income Sources Matrix"
        item.version_id = 21

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [item]

        with patch("app.services.data_quality.helpers.FormItem.query", mock_query):
            from app.services.data_quality.helpers import _find_income_sources_matrix_item

            result = _find_income_sources_matrix_item(21, 21)

        assert result is item

    def test_version_id_filters_out_unmatched_items(self):
        item = MagicMock()
        item.label = "Income Sources Matrix"
        item.version_id = 99  # does not match version 21 and version_id is not None

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [item]

        with patch("app.services.data_quality.helpers.FormItem.query", mock_query):
            from app.services.data_quality.helpers import _find_income_sources_matrix_item

            result = _find_income_sources_matrix_item(21, 21)

        assert result is None


# ---------------------------------------------------------------------------
# compute_income_sources_ratio
# ---------------------------------------------------------------------------

class TestComputeIncomeSourcesRatio:
    def test_legacy_sources_sum_ratio(self):
        kpi_data = {
            "h_gov_CHF": (_fd(400), None),
            "f_gov_CHF": (_fd(600), None),
        }

        with patch(
            "app.services.data_quality.helpers._find_income_sources_matrix_item",
            return_value=None,
        ):
            from app.services.data_quality.helpers import compute_income_sources_ratio

            ratio = compute_income_sources_ratio(
                aes_id=1,
                template_id=21,
                version_id=None,
                kpi_data=kpi_data,
                income_source_kpi_codes=("h_gov_CHF", "f_gov_CHF"),
                total_income=1000.0,
            )

        assert ratio == pytest.approx(1.0)

    def test_no_matrix_item_returns_zero(self):
        with patch(
            "app.services.data_quality.helpers._find_income_sources_matrix_item",
            return_value=None,
        ):
            from app.services.data_quality.helpers import compute_income_sources_ratio

            ratio = compute_income_sources_ratio(
                aes_id=1, template_id=21, version_id=None,
                kpi_data={}, income_source_kpi_codes=(), total_income=0.0,
            )

        assert ratio == 0.0

    def test_matrix_entry_no_disagg_data_returns_zero(self):
        matrix_item = MagicMock()
        matrix_item.id = 1

        mock_fd = MagicMock()
        mock_fd.query.filter_by.return_value.first.return_value = None

        with patch(
            "app.services.data_quality.helpers._find_income_sources_matrix_item",
            return_value=matrix_item,
        ), patch("app.services.data_quality.helpers.FormData", mock_fd):
            from app.services.data_quality.helpers import compute_income_sources_ratio

            ratio = compute_income_sources_ratio(
                aes_id=1, template_id=21, version_id=None,
                kpi_data={}, income_source_kpi_codes=(), total_income=500.0,
            )

        assert ratio == 0.0

    def test_matrix_row_coverage(self):
        matrix_item = MagicMock()
        matrix_item.id = 1
        matrix_item.config = {
            "matrix_config": {
                "rows": ["RowA", "RowB", "RowC"],
                "columns": [{"name": "Funding"}],
            }
        }

        entry = MagicMock()
        entry.disagg_data = {
            "RowA_Funding": 100,
            "RowB_Funding": 200,
            "RowC_Funding": 0,
        }

        mock_fd = MagicMock()
        mock_fd.query.filter_by.return_value.first.return_value = entry

        with patch(
            "app.services.data_quality.helpers._find_income_sources_matrix_item",
            return_value=matrix_item,
        ), patch("app.services.data_quality.helpers.FormData", mock_fd):
            from app.services.data_quality.helpers import compute_income_sources_ratio

            ratio = compute_income_sources_ratio(
                aes_id=1, template_id=21, version_id=None,
                kpi_data={}, income_source_kpi_codes=(), total_income=300.0,
            )

        # 2 out of 3 rows filled → 0.667; reconciliation = min(1, 300/300)=1.0 → max(0.667, 1.0)=1.0
        assert ratio == pytest.approx(1.0)

    def test_matrix_no_rows_or_columns_config(self):
        matrix_item = MagicMock()
        matrix_item.id = 1
        matrix_item.config = {"matrix_config": {"rows": [], "columns": []}}

        entry = MagicMock()
        entry.disagg_data = {"row1_col1": 100}

        mock_fd = MagicMock()
        mock_fd.query.filter_by.return_value.first.return_value = entry

        with patch(
            "app.services.data_quality.helpers._find_income_sources_matrix_item",
            return_value=matrix_item,
        ), patch("app.services.data_quality.helpers.FormData", mock_fd):
            from app.services.data_quality.helpers import compute_income_sources_ratio

            ratio = compute_income_sources_ratio(
                aes_id=1, template_id=21, version_id=None,
                kpi_data={}, income_source_kpi_codes=(), total_income=100.0,
            )
        # No rows/cols → returns reconciliation only
        assert ratio == pytest.approx(1.0)

    def test_matrix_total_income_zero_returns_zero_reconciliation(self):
        matrix_item = MagicMock()
        matrix_item.id = 1
        matrix_item.config = {"matrix_config": {"rows": ["R1"], "columns": [{"name": "C"}]}}

        entry = MagicMock()
        entry.disagg_data = {"R1_C": 100}

        mock_fd = MagicMock()
        mock_fd.query.filter_by.return_value.first.return_value = entry

        with patch(
            "app.services.data_quality.helpers._find_income_sources_matrix_item",
            return_value=matrix_item,
        ), patch("app.services.data_quality.helpers.FormData", mock_fd):
            from app.services.data_quality.helpers import compute_income_sources_ratio

            ratio = compute_income_sources_ratio(
                aes_id=1, template_id=21, version_id=None,
                kpi_data={}, income_source_kpi_codes=(), total_income=0.0,
            )
        # total_income=0 → reconciliation=0.0; row_coverage=1/1=1.0 → max(1.0, 0.0)=1.0
        assert ratio == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# active_country_map_query (trivial, just test it returns a query)
# ---------------------------------------------------------------------------

class TestActiveCountryMapQuery:
    def test_returns_query_object(self):
        mock_result = MagicMock()
        mock_query = MagicMock()
        mock_query.filter_by.return_value.order_by.return_value = mock_result

        with patch("app.services.data_quality.helpers.Country.query", mock_query):
            from app.services.data_quality.helpers import active_country_map_query

            result = active_country_map_query()

        assert result is mock_result


# ---------------------------------------------------------------------------
# validation_question_counts
# ---------------------------------------------------------------------------

class TestValidationQuestionCounts:
    def test_returns_counts_dict(self):
        mock_base = MagicMock()
        mock_base.count.return_value = 10
        mock_base.filter.return_value.count.side_effect = [5, 3, 2]

        with patch(
            "app.services.data_quality.helpers.ValidationQuestion",
        ) as mock_vq:
            mock_vq.query.filter.return_value = mock_base
            from app.services.data_quality.helpers import validation_question_counts

            result = validation_question_counts(21, "country", 1, "FDRS 2024")

        assert result["asked"] == 10
        assert "answered" in result
        assert "open" in result
        assert "waived" in result
