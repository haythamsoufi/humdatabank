"""
Unit tests for api_pagination utilities.

Covers: query_filter_in_batches, validate_pagination_params, parse_date_range,
get_sort_params, validate_data_endpoint_params, build_paginated_response,
build_pagination_queries, get_paginated_data_ids, fetch_paginated_rows.
"""
import pytest
from unittest.mock import MagicMock, patch, call
from werkzeug.datastructures import ImmutableMultiDict

from app.utils.api_pagination import (
    query_filter_in_batches,
    validate_pagination_params,
    parse_date_range,
    get_sort_params,
    validate_data_endpoint_params,
    build_paginated_response,
    build_pagination_queries,
    get_paginated_data_ids,
    fetch_paginated_rows,
)
from app.utils.api_helpers import MAX_PER_PAGE, DEFAULT_PER_PAGE, DEFAULT_PAGE


# ---------------------------------------------------------------------------
# query_filter_in_batches
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestQueryFilterInBatches:
    def test_empty_ids_returns_empty_list(self):
        base_query = MagicMock()
        result = query_filter_in_batches(base_query, MagicMock(), [])
        assert result == []
        base_query.filter.assert_not_called()

    def test_single_batch_all_ids(self):
        base_query = MagicMock()
        column = MagicMock()
        base_query.filter.return_value.all.return_value = ['row1', 'row2']
        result = query_filter_in_batches(base_query, column, [1, 2, 3], batch_size=10)
        assert result == ['row1', 'row2']
        assert base_query.filter.call_count == 1

    def test_multiple_batches_combined(self):
        base_query = MagicMock()
        column = MagicMock()
        base_query.filter.return_value.all.side_effect = [['a', 'b'], ['c']]
        result = query_filter_in_batches(base_query, column, [1, 2, 3], batch_size=2)
        assert result == ['a', 'b', 'c']
        assert base_query.filter.call_count == 2

    def test_deduplicates_ids_preserves_order(self):
        base_query = MagicMock()
        column = MagicMock()
        base_query.filter.return_value.all.return_value = ['row1']
        query_filter_in_batches(base_query, column, [1, 1, 2, 2], batch_size=10)
        # Should be deduplicated to [1, 2] before batching
        assert base_query.filter.call_count == 1

    def test_default_batch_size(self):
        from app.utils.api_pagination import SQL_IN_BATCH_SIZE
        base_query = MagicMock()
        base_query.filter.return_value.all.return_value = []
        query_filter_in_batches(base_query, MagicMock(), list(range(5)))
        assert base_query.filter.call_count == 1  # all fit in one batch


# ---------------------------------------------------------------------------
# validate_pagination_params
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestValidatePaginationParams:
    def test_empty_args_returns_defaults(self):
        args = ImmutableMultiDict()
        page, per_page = validate_pagination_params(args)
        assert page == DEFAULT_PAGE
        assert per_page == DEFAULT_PER_PAGE

    def test_valid_page_and_per_page(self):
        args = ImmutableMultiDict([('page', '3'), ('per_page', '50')])
        page, per_page = validate_pagination_params(args)
        assert page == 3
        assert per_page == 50

    def test_page_zero_clamped_to_one(self):
        args = ImmutableMultiDict([('page', '0')])
        page, per_page = validate_pagination_params(args)
        assert page == 1

    def test_negative_page_clamped_to_one(self):
        args = ImmutableMultiDict([('page', '-5')])
        page, per_page = validate_pagination_params(args)
        assert page == 1

    def test_per_page_above_max_capped(self):
        args = ImmutableMultiDict([('per_page', str(MAX_PER_PAGE + 1000))])
        page, per_page = validate_pagination_params(args)
        assert per_page == MAX_PER_PAGE

    def test_per_page_zero_uses_default(self):
        args = ImmutableMultiDict([('per_page', '0')])
        page, per_page = validate_pagination_params(args)
        assert per_page == DEFAULT_PER_PAGE

    def test_per_page_negative_uses_default(self):
        args = ImmutableMultiDict([('per_page', '-1')])
        page, per_page = validate_pagination_params(args)
        assert per_page == DEFAULT_PER_PAGE

    def test_custom_default_per_page(self):
        args = ImmutableMultiDict()
        page, per_page = validate_pagination_params(args, default_per_page=5)
        assert per_page == 5

    def test_custom_max_per_page(self):
        args = ImmutableMultiDict([('per_page', '100')])
        page, per_page = validate_pagination_params(args, max_per_page=30)
        assert per_page == 30

    def test_invalid_page_string_falls_back_to_default(self):
        args = ImmutableMultiDict([('page', 'abc')])
        page, per_page = validate_pagination_params(args)
        assert page == DEFAULT_PAGE

    def test_invalid_per_page_string_falls_back_to_default(self):
        args = ImmutableMultiDict([('per_page', 'abc')])
        page, per_page = validate_pagination_params(args)
        assert per_page == DEFAULT_PER_PAGE

    def test_per_page_one_is_minimum(self):
        args = ImmutableMultiDict([('per_page', '1')])
        page, per_page = validate_pagination_params(args)
        assert per_page == 1


# ---------------------------------------------------------------------------
# parse_date_range
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestParseDateRange:
    def test_no_dates_returns_none_none(self, app):
        with app.test_request_context():
            date_from, date_to = parse_date_range(ImmutableMultiDict())
            assert date_from is None
            assert date_to is None

    def test_valid_date_from_parsed(self, app):
        with app.test_request_context():
            args = ImmutableMultiDict([('date_from', '2024-01-15')])
            date_from, date_to = parse_date_range(args)
            assert date_from is not None
            assert date_from.year == 2024
            assert date_from.month == 1
            assert date_from.day == 15
            assert date_from.hour == 0
            assert date_from.minute == 0
            assert date_from.second == 0

    def test_valid_date_to_set_to_end_of_day(self, app):
        with app.test_request_context():
            args = ImmutableMultiDict([('date_to', '2024-12-31')])
            date_from, date_to = parse_date_range(args)
            assert date_to is not None
            assert date_to.hour == 23
            assert date_to.minute == 59
            assert date_to.second == 59

    def test_datetime_with_T_separator(self, app):
        with app.test_request_context():
            args = ImmutableMultiDict([('date_from', '2024-01-15T10:30:00')])
            date_from, date_to = parse_date_range(args)
            assert date_from is not None
            assert date_from.hour == 10
            assert date_from.minute == 30

    def test_datetime_with_Z_suffix(self, app):
        with app.test_request_context():
            args = ImmutableMultiDict([('date_from', '2024-01-15T10:30:00Z')])
            date_from, date_to = parse_date_range(args)
            assert date_from is not None

    def test_date_to_with_T_separator(self, app):
        with app.test_request_context():
            args = ImmutableMultiDict([('date_to', '2024-06-30T23:59:59')])
            date_from, date_to = parse_date_range(args)
            assert date_to is not None

    def test_date_from_too_long_returns_none(self, app):
        with app.test_request_context():
            args = ImmutableMultiDict([('date_from', 'x' * 51)])
            date_from, date_to = parse_date_range(args)
            assert date_from is None

    def test_date_to_too_long_returns_none(self, app):
        with app.test_request_context():
            args = ImmutableMultiDict([('date_to', 'y' * 51)])
            date_from, date_to = parse_date_range(args)
            assert date_to is None

    def test_invalid_date_from_format_returns_none(self, app):
        with app.test_request_context():
            args = ImmutableMultiDict([('date_from', 'not-a-date')])
            date_from, date_to = parse_date_range(args)
            assert date_from is None

    def test_invalid_date_to_format_returns_none(self, app):
        with app.test_request_context():
            args = ImmutableMultiDict([('date_to', '31/12/2024')])
            date_from, date_to = parse_date_range(args)
            assert date_to is None

    def test_date_from_after_date_to_returns_none_none(self, app):
        with app.test_request_context():
            args = ImmutableMultiDict([
                ('date_from', '2024-12-31'),
                ('date_to', '2024-01-01'),
            ])
            date_from, date_to = parse_date_range(args)
            assert date_from is None
            assert date_to is None

    def test_valid_range_both_returned(self, app):
        with app.test_request_context():
            args = ImmutableMultiDict([
                ('date_from', '2024-01-01'),
                ('date_to', '2024-12-31'),
            ])
            date_from, date_to = parse_date_range(args)
            assert date_from is not None
            assert date_to is not None
            assert date_from < date_to


# ---------------------------------------------------------------------------
# get_sort_params
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetSortParams:
    def test_defaults(self):
        args = ImmutableMultiDict()
        sort_field, sort_order, sort_col = get_sort_params(args)
        assert sort_field == 'submitted_at'
        assert sort_order == 'desc'
        assert sort_col == 'submitted_at'

    def test_valid_sort_field(self):
        args = ImmutableMultiDict([('sort', 'template_id')])
        sort_field, sort_order, sort_col = get_sort_params(args)
        assert sort_field == 'template_id'

    def test_valid_asc_order(self):
        args = ImmutableMultiDict([('order', 'asc')])
        sort_field, sort_order, sort_col = get_sort_params(args)
        assert sort_order == 'asc'

    def test_invalid_sort_field_falls_back_to_default(self):
        args = ImmutableMultiDict([('sort', 'nonexistent_column')])
        sort_field, sort_order, sort_col = get_sort_params(args)
        assert sort_field == 'submitted_at'

    def test_invalid_order_falls_back_to_default(self):
        args = ImmutableMultiDict([('order', 'sideways')])
        sort_field, sort_order, sort_col = get_sort_params(args)
        assert sort_order == 'desc'

    def test_custom_defaults(self):
        args = ImmutableMultiDict()
        sort_field, sort_order, sort_col = get_sort_params(
            args, default_sort='created_at', default_order='asc'
        )
        assert sort_field == 'created_at'
        assert sort_order == 'asc'

    def test_case_insensitive_sort_and_order(self):
        args = ImmutableMultiDict([('sort', 'TEMPLATE_ID'), ('order', 'ASC')])
        sort_field, sort_order, sort_col = get_sort_params(args)
        assert sort_field == 'template_id'
        assert sort_order == 'asc'

    def test_all_valid_sort_fields(self):
        valid_fields = ['submitted_at', 'template_id', 'country_id', 'period_name', 'created_at', 'updated_at']
        for field in valid_fields:
            args = ImmutableMultiDict([('sort', field)])
            sort_field, sort_order, sort_col = get_sort_params(args)
            assert sort_field == field, f"Expected {field}, got {sort_field}"
            assert sort_col is not None

    def test_sort_col_none_for_invalid_field(self):
        args = ImmutableMultiDict([('sort', 'bogus')])
        sort_field, sort_order, sort_col = get_sort_params(args)
        # Falls back to default -> sort_col should be default's value
        assert sort_col == 'submitted_at'


# ---------------------------------------------------------------------------
# validate_data_endpoint_params
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestValidateDataEndpointParams:
    def test_defaults(self):
        args = ImmutableMultiDict()
        result = validate_data_endpoint_params(args)
        assert result['page'] == 1
        assert result['per_page'] == 20
        assert result['include_disagg'] is False
        assert result['include_full_info'] is False

    @pytest.mark.parametrize('val', ['1', 'true', 'yes', 'y'])
    def test_disagg_truthy_values(self, val):
        args = ImmutableMultiDict([('disagg', val)])
        result = validate_data_endpoint_params(args)
        assert result['include_disagg'] is True, f"disagg='{val}' should be True"

    @pytest.mark.parametrize('val', ['0', 'false', 'no', 'n', 'off'])
    def test_disagg_falsy_values(self, val):
        args = ImmutableMultiDict([('disagg', val)])
        result = validate_data_endpoint_params(args)
        assert result['include_disagg'] is False

    @pytest.mark.parametrize('val', ['1', 'true', 'yes', 'y'])
    def test_include_full_info_truthy_values(self, val):
        args = ImmutableMultiDict([('include_full_info', val)])
        result = validate_data_endpoint_params(args)
        assert result['include_full_info'] is True

    def test_page_zero_clamped_to_one(self):
        args = ImmutableMultiDict([('page', '0')])
        result = validate_data_endpoint_params(args)
        assert result['page'] == 1

    def test_per_page_capped_at_max(self):
        args = ImmutableMultiDict([('per_page', str(MAX_PER_PAGE + 1))])
        result = validate_data_endpoint_params(args)
        assert result['per_page'] == MAX_PER_PAGE

    def test_per_page_zero_uses_default_20(self):
        args = ImmutableMultiDict([('per_page', '0')])
        result = validate_data_endpoint_params(args)
        assert result['per_page'] == 20

    def test_invalid_page_falls_back_to_1(self):
        args = ImmutableMultiDict([('page', 'nope')])
        result = validate_data_endpoint_params(args)
        assert result['page'] == 1

    def test_invalid_per_page_falls_back_to_20(self):
        args = ImmutableMultiDict([('per_page', 'nope')])
        result = validate_data_endpoint_params(args)
        assert result['per_page'] == 20

    def test_disagg_none_when_not_provided(self):
        args = ImmutableMultiDict()
        result = validate_data_endpoint_params(args)
        assert result['include_disagg'] is False


# ---------------------------------------------------------------------------
# build_paginated_response
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBuildPaginatedResponse:
    def test_normal_case(self):
        data = [{'id': 1}, {'id': 2}]
        result = build_paginated_response(data, total_items=10, page=1, per_page=2)
        assert result['data'] == data
        assert result['total_items'] == 10
        assert result['total_pages'] == 5
        assert result['current_page'] == 1
        assert result['per_page'] == 2

    def test_zero_total_items(self):
        result = build_paginated_response([], total_items=0, page=1, per_page=10)
        assert result['total_items'] == 0
        assert result['total_pages'] == 0

    def test_partial_last_page(self):
        result = build_paginated_response([], total_items=11, page=2, per_page=10)
        assert result['total_pages'] == 2

    def test_exact_division(self):
        result = build_paginated_response([], total_items=20, page=1, per_page=10)
        assert result['total_pages'] == 2

    def test_per_page_zero_returns_one_total_page(self):
        result = build_paginated_response([], total_items=10, page=1, per_page=0)
        assert result['total_pages'] == 1

    def test_single_item_single_page(self):
        result = build_paginated_response([{'x': 1}], total_items=1, page=1, per_page=20)
        assert result['total_pages'] == 1
        assert result['data'] == [{'x': 1}]


# ---------------------------------------------------------------------------
# build_pagination_queries
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBuildPaginationQueries:
    def test_both_queries_when_submission_type_none(self):
        assigned_q = MagicMock()
        public_q = MagicMock()
        assigned_result = MagicMock()
        public_result = MagicMock()
        assigned_q.with_entities.return_value = assigned_result
        public_q.with_entities.return_value = public_result

        a_q, p_q = build_pagination_queries(assigned_q, public_q, submission_type=None)
        assert a_q == assigned_result
        assert p_q == public_result

    def test_only_assigned_when_submission_type_assigned(self):
        assigned_q = MagicMock()
        public_q = MagicMock()
        assigned_result = MagicMock()
        assigned_q.with_entities.return_value = assigned_result

        a_q, p_q = build_pagination_queries(assigned_q, public_q, submission_type='assigned')
        assert a_q == assigned_result
        assert p_q is None
        public_q.with_entities.assert_not_called()

    def test_only_public_when_submission_type_public(self):
        assigned_q = MagicMock()
        public_q = MagicMock()
        public_result = MagicMock()
        public_q.with_entities.return_value = public_result

        a_q, p_q = build_pagination_queries(assigned_q, public_q, submission_type='public')
        assert a_q is None
        assert p_q == public_result
        assigned_q.with_entities.assert_not_called()


# ---------------------------------------------------------------------------
# get_paginated_data_ids
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetPaginatedDataIds:
    def test_both_none_returns_empty_and_zero(self, app):
        with app.app_context():
            page_rows, total = get_paginated_data_ids(None, None, page=1, per_page=10)
            assert page_rows == []
            assert total == 0

    def test_total_from_assigned_only(self, app):
        with app.app_context():
            assigned_q = MagicMock()
            assigned_q.order_by.return_value.count.return_value = 7

            subq = MagicMock()
            subq.c.id = MagicMock()
            subq.c.submitted_at = MagicMock()
            subq.c.submission_type = MagicMock()
            assigned_q.subquery.return_value = subq

            mock_chain = MagicMock()
            mock_chain.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

            with patch('app.utils.api_pagination.db') as mock_db:
                mock_db.session.query.return_value = mock_chain
                page_rows, total = get_paginated_data_ids(assigned_q, None, page=1, per_page=10)
            assert total == 7

    def test_total_sum_from_both_queries(self, app):
        with app.app_context():
            assigned_q = MagicMock()
            public_q = MagicMock()
            assigned_q.order_by.return_value.count.return_value = 5
            public_q.order_by.return_value.count.return_value = 3

            combined = MagicMock()
            assigned_q.union_all.return_value = combined
            subq = MagicMock()
            combined.subquery.return_value = subq
            subq.c.submitted_at = MagicMock()

            mock_chain = MagicMock()
            mock_chain.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

            with patch('app.utils.api_pagination.db') as mock_db:
                mock_db.session.query.return_value = mock_chain
                page_rows, total = get_paginated_data_ids(assigned_q, public_q, page=1, per_page=10)
            assert total == 8

    def test_no_paginate_returns_all(self, app):
        with app.app_context():
            assigned_q = MagicMock()
            assigned_q.order_by.return_value.count.return_value = 3
            subq = MagicMock()
            subq.c.id = MagicMock()
            subq.c.submitted_at = MagicMock()
            subq.c.submission_type = MagicMock()
            assigned_q.subquery.return_value = subq

            mock_rows = [MagicMock(), MagicMock(), MagicMock()]
            mock_chain = MagicMock()
            mock_chain.order_by.return_value.all.return_value = mock_rows

            with patch('app.utils.api_pagination.db') as mock_db:
                mock_db.session.query.return_value = mock_chain
                page_rows, total = get_paginated_data_ids(
                    assigned_q, None, page=1, per_page=10, paginate=False
                )
            assert total == 3

    def test_non_default_sort_field_logs_and_falls_back(self, app):
        with app.app_context():
            assigned_q = MagicMock()
            assigned_q.order_by.return_value.count.return_value = 2
            subq = MagicMock()
            subq.c.submitted_at = MagicMock()
            assigned_q.subquery.return_value = subq

            mock_chain = MagicMock()
            mock_chain.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

            with patch('app.utils.api_pagination.db') as mock_db:
                mock_db.session.query.return_value = mock_chain
                # sort_field != 'submitted_at' triggers the fallback log path
                page_rows, total = get_paginated_data_ids(
                    assigned_q, None, page=1, per_page=10, sort_field='country_id'
                )
            assert total == 2


# ---------------------------------------------------------------------------
# fetch_paginated_rows
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFetchPaginatedRows:
    def test_empty_page_rows(self):
        assigned_q = MagicMock()
        public_q = MagicMock()
        assigned_map, public_map = fetch_paginated_rows(assigned_q, public_q, [])
        assert assigned_map == {}
        assert public_map == {}

    def test_assigned_rows_mapped_by_id(self):
        assigned_q = MagicMock()
        public_q = MagicMock()

        page_row = MagicMock()
        page_row.id = 1
        page_row.submission_type = 'assigned'

        fetched = MagicMock()
        fetched.id = 1

        with patch('app.utils.api_pagination.query_filter_in_batches', return_value=[fetched]):
            assigned_map, public_map = fetch_paginated_rows(assigned_q, public_q, [page_row])

        assert assigned_map == {1: fetched}
        assert public_map == {}

    def test_public_rows_mapped_by_id(self):
        assigned_q = MagicMock()
        public_q = MagicMock()

        page_row = MagicMock()
        page_row.id = 42
        page_row.submission_type = 'public'

        fetched = MagicMock()
        fetched.id = 42

        with patch('app.utils.api_pagination.query_filter_in_batches', return_value=[fetched]):
            assigned_map, public_map = fetch_paginated_rows(assigned_q, public_q, [page_row])

        assert assigned_map == {}
        assert public_map == {42: fetched}

    def test_mixed_rows_split_correctly(self):
        assigned_q = MagicMock()
        public_q = MagicMock()

        row_a = MagicMock(); row_a.id = 1; row_a.submission_type = 'assigned'
        row_p = MagicMock(); row_p.id = 2; row_p.submission_type = 'public'

        fetched_a = MagicMock(); fetched_a.id = 1
        fetched_p = MagicMock(); fetched_p.id = 2

        call_count = {'n': 0}
        def side_effect(q, col, ids):
            call_count['n'] += 1
            if call_count['n'] == 1:
                return [fetched_a]
            return [fetched_p]

        with patch('app.utils.api_pagination.query_filter_in_batches', side_effect=side_effect):
            assigned_map, public_map = fetch_paginated_rows(
                assigned_q, public_q, [row_a, row_p]
            )

        assert 1 in assigned_map
        assert 2 in public_map
