"""
Unit tests for app/utils/assignment_document_carryover.py – 100% coverage target.
"""
import pytest
from unittest.mock import MagicMock, patch

from app.utils.assignment_document_carryover import (
    extract_years_from_text,
    assignment_target_years,
    document_period_year_bounds,
    document_covers_assignment_years,
    _norm_doc_type,
    document_types_match,
    _config_bool_true,
    _same_document_slot_across_versions,
    _document_matches_carryover_field,
    _merge_docs_for_key,
    merge_carryover_into_submitted_documents_dict,
    find_carryover_documents_for_field,
)


# ---------------------------------------------------------------------------
# extract_years_from_text
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestExtractYearsFromText:
    def test_none_returns_empty(self):
        assert extract_years_from_text(None) == []

    def test_empty_string_returns_empty(self):
        assert extract_years_from_text('') == []

    def test_single_year(self):
        assert extract_years_from_text('Report 2023') == [2023]

    def test_two_years(self):
        assert extract_years_from_text('2020-2022') == [2020, 2022]

    def test_duplicate_years_deduplicated(self):
        result = extract_years_from_text('2023 and 2023')
        assert result == [2023]

    def test_no_year_in_text(self):
        assert extract_years_from_text('Hello world') == []

    def test_year_like_1800_not_matched(self):
        # regex only matches 19xx or 20xx
        result = extract_years_from_text('Year 1800')
        assert 1800 not in result

    def test_year_2100_not_matched(self):
        result = extract_years_from_text('Year 2100')
        assert 2100 not in result

    def test_returns_sorted(self):
        result = extract_years_from_text('2022 and 2020')
        assert result == sorted(result)

    def test_multiple_years(self):
        result = extract_years_from_text('2020 2021 2022')
        assert result == [2020, 2021, 2022]


# ---------------------------------------------------------------------------
# assignment_target_years
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestAssignmentTargetYears:
    def test_none_returns_empty(self):
        assert assignment_target_years(None) == set()

    def test_empty_string_returns_empty(self):
        assert assignment_target_years('') == set()

    def test_single_year(self):
        assert assignment_target_years('Fiscal Year 2022') == {2022}

    def test_two_adjacent_years_gives_range(self):
        # 2021-2022 → {2021, 2022}
        assert assignment_target_years('2021-2022') == {2021, 2022}

    def test_contiguous_range_filled(self):
        # All four years mentioned explicitly → contiguous range detected
        result = assignment_target_years('2020 2021 2022 2023')
        assert result == {2020, 2021, 2022, 2023}

    def test_two_year_string_only_extracts_endpoints(self):
        # '2020-2023' only has two year tokens (2020 and 2023) → non-contiguous
        result = assignment_target_years('Period 2020-2023')
        assert result == {2020, 2023}

    def test_non_contiguous_years_uses_explicit(self):
        # 2019 and 2023 — gap of 4 years, not contiguous
        result = assignment_target_years('2019 and 2023')
        assert result == {2019, 2023}


# ---------------------------------------------------------------------------
# document_period_year_bounds
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDocumentPeriodYearBounds:
    def test_none_returns_none(self):
        assert document_period_year_bounds(None) is None

    def test_no_year_returns_none(self):
        assert document_period_year_bounds('no year here') is None

    def test_single_year_returns_same_min_max(self):
        assert document_period_year_bounds('2022') == (2022, 2022)

    def test_two_years(self):
        assert document_period_year_bounds('2020-2023') == (2020, 2023)


# ---------------------------------------------------------------------------
# document_covers_assignment_years
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDocumentCoversAssignmentYears:
    def test_empty_assignment_years_returns_false(self):
        assert document_covers_assignment_years('2020-2023', set()) is False

    def test_no_years_in_period_returns_false(self):
        assert document_covers_assignment_years('no year', {2022}) is False

    def test_none_period_returns_false(self):
        assert document_covers_assignment_years(None, {2022}) is False

    def test_covers_single_year(self):
        assert document_covers_assignment_years('2020-2023', {2022}) is True

    def test_covers_multiple_years(self):
        assert document_covers_assignment_years('2020-2023', {2020, 2021, 2022, 2023}) is True

    def test_does_not_cover_year_outside_bounds(self):
        assert document_covers_assignment_years('2020-2022', {2023}) is False

    def test_partial_coverage_returns_false(self):
        assert document_covers_assignment_years('2020-2021', {2020, 2022}) is False


# ---------------------------------------------------------------------------
# _norm_doc_type
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestNormDocType:
    def test_none_returns_empty(self):
        assert _norm_doc_type(None) == ''

    def test_strips_and_casefolds(self):
        assert _norm_doc_type('  Annual Report  ') == 'annual report'

    def test_integer_input(self):
        result = _norm_doc_type(42)
        assert result == '42'


# ---------------------------------------------------------------------------
# document_types_match
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDocumentTypesMatch:
    def test_matching_same_case(self):
        assert document_types_match('Annual Report', 'annual report') is True

    def test_matching_both_lowercase(self):
        assert document_types_match('audit', 'audit') is True

    def test_not_matching(self):
        assert document_types_match('Audit', 'Financial') is False

    def test_none_expected_returns_false(self):
        assert document_types_match(None, 'audit') is False

    def test_empty_expected_returns_false(self):
        assert document_types_match('', 'audit') is False

    def test_none_submitted_compared_to_empty(self):
        assert document_types_match('audit', None) is False


# ---------------------------------------------------------------------------
# _config_bool_true
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestConfigBoolTrue:
    def test_true_literal(self):
        assert _config_bool_true(True) is True

    def test_int_1(self):
        assert _config_bool_true(1) is True

    def test_string_1(self):
        assert _config_bool_true('1') is True

    def test_string_true(self):
        assert _config_bool_true('true') is True

    def test_string_True(self):
        assert _config_bool_true('True') is True

    def test_string_on(self):
        assert _config_bool_true('on') is True

    def test_string_yes(self):
        assert _config_bool_true('yes') is True

    def test_false_literal(self):
        assert _config_bool_true(False) is False

    def test_zero(self):
        assert _config_bool_true(0) is False

    def test_none(self):
        assert _config_bool_true(None) is False

    def test_string_false(self):
        assert _config_bool_true('false') is False


# ---------------------------------------------------------------------------
# _same_document_slot_across_versions
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSameDocumentSlotAcrossVersions:
    def _make_item(self, item_type='document_field', template_id=1, section_id=2, order=3):
        m = MagicMock()
        m.item_type = item_type
        m.template_id = template_id
        m.section_id = section_id
        m.order = order
        return m

    def test_none_source_returns_false(self):
        field = self._make_item()
        assert _same_document_slot_across_versions(None, field) is False

    def test_wrong_item_type_returns_false(self):
        source = self._make_item(item_type='text_field')
        field = self._make_item()
        assert _same_document_slot_across_versions(source, field) is False

    def test_same_slot_returns_true(self):
        source = self._make_item(template_id=1, section_id=2, order=3)
        field = self._make_item(template_id=1, section_id=2, order=3)
        assert _same_document_slot_across_versions(source, field) is True

    def test_different_template_id_returns_false(self):
        source = self._make_item(template_id=1, section_id=2, order=3)
        field = self._make_item(template_id=9, section_id=2, order=3)
        assert _same_document_slot_across_versions(source, field) is False

    def test_different_section_id_returns_false(self):
        source = self._make_item(template_id=1, section_id=2, order=3)
        field = self._make_item(template_id=1, section_id=9, order=3)
        assert _same_document_slot_across_versions(source, field) is False

    def test_different_order_returns_false(self):
        source = self._make_item(template_id=1, section_id=2, order=3)
        field = self._make_item(template_id=1, section_id=2, order=99)
        assert _same_document_slot_across_versions(source, field) is False

    def test_type_error_in_order_comparison_returns_false(self):
        source = self._make_item()
        source.order = 'not_a_number'
        field = self._make_item()
        field.order = 'also_not_a_number'
        # float('not_a_number') raises ValueError
        assert _same_document_slot_across_versions(source, field) is False


# ---------------------------------------------------------------------------
# _document_matches_carryover_field
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDocumentMatchesCarryoverField:
    def _make_field(self, field_id=10, template_id=1, section_id=2, order=3, item_type='document_field'):
        f = MagicMock()
        f.id = field_id
        f.template_id = template_id
        f.section_id = section_id
        f.order = order
        f.item_type = item_type
        return f

    def _make_doc(self, doc_id=100, form_item_id=10, document_type=None):
        d = MagicMock()
        d.id = doc_id
        d.form_item_id = form_item_id
        d.document_type = document_type
        return d

    def test_exact_field_id_match(self):
        field = self._make_field(field_id=10)
        doc = self._make_doc(form_item_id=10)
        result = _document_matches_carryover_field(doc, field, {}, {})
        assert result is True

    def test_type_match_returns_true(self):
        field = self._make_field(field_id=10)
        doc = self._make_doc(form_item_id=99, document_type='audit')
        cfg = {'document_type': 'Audit'}
        result = _document_matches_carryover_field(doc, field, cfg, {})
        assert result is True

    def test_no_match_no_source_returns_false(self):
        field = self._make_field(field_id=10)
        doc = self._make_doc(form_item_id=99, document_type='financial')
        cfg = {'document_type': 'audit'}
        result = _document_matches_carryover_field(doc, field, cfg, {})
        assert result is False

    def test_same_slot_no_expected_type(self):
        field = self._make_field(field_id=10, template_id=1, section_id=2, order=3)
        doc = self._make_doc(form_item_id=20, document_type=None)
        src = self._make_field(field_id=20, template_id=1, section_id=2, order=3)
        src.config = {}
        result = _document_matches_carryover_field(doc, field, {}, {20: src})
        assert result is True

    def test_source_type_matches_expected(self):
        field = self._make_field(field_id=10)
        doc = self._make_doc(form_item_id=20, document_type='audit')
        src = self._make_field(field_id=20)
        src.config = {'document_type': 'Audit'}
        cfg = {'document_type': 'audit'}
        result = _document_matches_carryover_field(doc, field, cfg, {20: src})
        assert result is True

    def test_expected_type_with_same_slot_returns_true(self):
        field = self._make_field(field_id=10, template_id=1, section_id=2, order=3)
        doc = self._make_doc(form_item_id=20)
        src = self._make_field(field_id=20, template_id=1, section_id=2, order=3)
        src.config = {}
        cfg = {'document_type': 'audit'}
        result = _document_matches_carryover_field(doc, field, cfg, {20: src})
        assert result is True

    def test_none_form_item_id_returns_false(self):
        field = self._make_field(field_id=10)
        doc = self._make_doc(form_item_id=None, document_type='other')
        cfg = {'document_type': 'audit'}
        result = _document_matches_carryover_field(doc, field, cfg, {})
        assert result is False


# ---------------------------------------------------------------------------
# _merge_docs_for_key
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestMergeDocsForKey:
    def _make_doc(self, doc_id):
        d = MagicMock()
        d.id = doc_id
        return d

    def test_merges_carryover_into_empty_dict(self):
        d = {}
        doc1 = self._make_doc(1)
        _merge_docs_for_key('k', [doc1], d)
        assert d['k'] == doc1

    def test_merges_carryover_with_existing_single_doc(self):
        doc1 = self._make_doc(1)
        doc2 = self._make_doc(2)
        d = {'k': doc1}
        _merge_docs_for_key('k', [doc2], d)
        assert isinstance(d['k'], list)
        assert len(d['k']) == 2

    def test_merges_carryover_with_existing_list(self):
        doc1 = self._make_doc(1)
        doc2 = self._make_doc(2)
        doc3 = self._make_doc(3)
        d = {'k': [doc1, doc2]}
        _merge_docs_for_key('k', [doc3], d)
        assert isinstance(d['k'], list)
        assert len(d['k']) == 3

    def test_deduplicates_by_id(self):
        doc1 = self._make_doc(1)
        d = {'k': doc1}
        _merge_docs_for_key('k', [doc1], d)
        # doc1 already in there; should not be duplicated
        assert d['k'] == doc1  # only one → stays as single

    def test_empty_carryover_with_existing(self):
        doc1 = self._make_doc(1)
        d = {'k': doc1}
        _merge_docs_for_key('k', [], d)
        assert d['k'] == doc1

    def test_no_existing_and_empty_carryover_no_key_set(self):
        d = {}
        _merge_docs_for_key('k', [], d)
        assert 'k' not in d

    def test_single_result_stored_as_scalar(self):
        doc1 = self._make_doc(1)
        d = {}
        _merge_docs_for_key('k', [doc1], d)
        assert not isinstance(d['k'], list)

    def test_multiple_results_stored_as_list(self):
        doc1 = self._make_doc(1)
        doc2 = self._make_doc(2)
        d = {}
        _merge_docs_for_key('k', [doc1, doc2], d)
        assert isinstance(d['k'], list)
        assert len(d['k']) == 2


# ---------------------------------------------------------------------------
# merge_carryover_into_submitted_documents_dict
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestMergeCarryoverIntoSubmittedDocumentsDict:
    def test_section_without_fields_ordered_skipped(self):
        aes = MagicMock()
        section_without = MagicMock(spec=[])  # no fields_ordered attribute
        result = merge_carryover_into_submitted_documents_dict({}, aes, [section_without])
        assert result == set()

    def test_non_document_fields_skipped(self):
        aes = MagicMock()
        field = MagicMock()
        field.is_document_field = False
        section = MagicMock()
        section.fields_ordered = [field]
        result = merge_carryover_into_submitted_documents_dict({}, aes, [section])
        assert result == set()

    def test_document_field_with_no_carryover(self):
        # Field has cross_assignment_period_reuse disabled → skipped, returns empty set.
        aes = MagicMock()
        field = MagicMock()
        field.is_document_field = True
        field.config = {}  # no cross_assignment_period_reuse
        field.id = 5
        section = MagicMock()
        section.fields_ordered = [field]
        result = merge_carryover_into_submitted_documents_dict({}, aes, [section])
        assert result == set()

    @patch('app.utils.assignment_document_carryover.joinedload')
    @patch('app.utils.assignment_document_carryover.FormItem')
    @patch('app.utils.assignment_document_carryover.SubmittedDocument')
    def test_document_field_with_carryover(self, MockSD, MockFI, mock_joinedload):
        # Field with carryover enabled; DB query returns a matching document.
        doc = MagicMock()
        doc.id = 99
        doc.form_item_id = 5
        doc.period = '2022'
        doc.document_type = None

        aes = MagicMock()
        aes.id = 1
        aes.entity_type = 'country'
        aes.entity_id = 5
        af = MagicMock()
        af.period_name = 'Annual Report 2022'
        af.template_id = 3
        aes.assigned_form = af

        field = MagicMock()
        field.is_document_field = True
        field.id = 5
        field.config = {'cross_assignment_period_reuse': True}

        query_mock = MagicMock()
        query_mock.options.return_value = query_mock
        query_mock.join.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.all.return_value = [doc]
        MockSD.query = query_mock

        fi_mock = MagicMock()
        fi_mock.all.return_value = []
        fi_query_chain = MagicMock()
        fi_query_chain.filter.return_value = fi_mock
        MockFI.query = fi_query_chain

        section = MagicMock()
        section.fields_ordered = [field]
        existing = {}
        result = merge_carryover_into_submitted_documents_dict(existing, aes, [section])
        assert 99 in result
        assert 'field_value[5]' in existing


# ---------------------------------------------------------------------------
# find_carryover_documents_for_field – unit (mocked DB)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestFindCarryoverDocumentsForField:
    def test_no_reuse_flag_returns_empty(self):
        field = MagicMock()
        field.config = {}  # no cross_assignment_period_reuse
        aes = MagicMock()
        result = find_carryover_documents_for_field(field, aes)
        assert result == []

    def test_reuse_flag_false_returns_empty(self):
        field = MagicMock()
        field.config = {'cross_assignment_period_reuse': False}
        aes = MagicMock()
        result = find_carryover_documents_for_field(field, aes)
        assert result == []

    def test_no_assigned_form_returns_empty(self):
        field = MagicMock()
        field.config = {'cross_assignment_period_reuse': True}
        aes = MagicMock()
        aes.assigned_form = None
        result = find_carryover_documents_for_field(field, aes)
        assert result == []

    def test_no_period_name_returns_empty(self):
        field = MagicMock()
        field.config = {'cross_assignment_period_reuse': True}
        aes = MagicMock()
        aes.assigned_form = MagicMock()
        aes.assigned_form.period_name = ''  # no years extractable
        result = find_carryover_documents_for_field(field, aes)
        assert result == []

    @patch('app.utils.assignment_document_carryover.joinedload')
    @patch('app.utils.assignment_document_carryover.FormItem')
    @patch('app.utils.assignment_document_carryover.SubmittedDocument')
    def test_returns_matching_documents(self, MockSD, MockFI, mock_joinedload):
        field = MagicMock()
        field.id = 10
        field.config = {'cross_assignment_period_reuse': True}

        aes = MagicMock()
        aes.id = 1
        aes.entity_type = 'country'
        aes.entity_id = 5
        af = MagicMock()
        af.period_name = 'Annual Report 2022'
        af.template_id = 3
        aes.assigned_form = af

        # Build a matching doc
        doc = MagicMock()
        doc.id = 55
        doc.form_item_id = 10
        doc.period = '2022'
        doc.document_type = None

        # Mock query chain
        query_mock = MagicMock()
        query_mock.options.return_value = query_mock
        query_mock.join.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.all.return_value = [doc]
        MockSD.query = query_mock

        # FormItem.query.filter() used for looking up source items by id set
        fi_query = MagicMock()
        fi_query.filter.return_value = iter([])
        MockFI.query = fi_query

        result = find_carryover_documents_for_field(field, aes)
        assert doc in result
