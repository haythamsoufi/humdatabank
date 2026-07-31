"""Unit tests for assignment completion service."""

from unittest.mock import MagicMock, patch

from app.services.assignments.completion_service import (
    AssignmentCompletionService,
    CompletionMetrics,
    CompletionPrefetch,
    MissingCompletionItem,
    _countable_form_item_filter,
    _published_filters_single,
    completion_rate_percent,
    matrix_entry_is_filled,
)


def test_matrix_entry_is_filled_not_applicable():
    assert matrix_entry_is_filled(None, True) is True


def test_matrix_entry_is_filled_with_cell_value():
    assert matrix_entry_is_filled({'_meta': 'x', 'cell_a': '5'}, False) is True


def test_matrix_entry_is_filled_with_lookup_cell_object():
    assert matrix_entry_is_filled(
        {'row_col': {'original': '42', 'modified': '42', 'isModified': False}},
        False,
    ) is True


def test_matrix_entry_is_filled_with_empty_lookup_cell_object():
    assert matrix_entry_is_filled(
        {'row_col': {'original': '', 'modified': '', 'isModified': False}},
        False,
    ) is False


def test_matrix_entry_is_filled_empty():
    assert matrix_entry_is_filled({'_meta': 'x'}, False) is False
    assert matrix_entry_is_filled(None, False) is False


def test_completion_rate_percent():
    assert completion_rate_percent(37, 40) == 92.5
    assert completion_rate_percent(0, 0) == 0.0


def test_completion_prefetch_metrics_for():
    prefetch = CompletionPrefetch(
        metrics_by_aes={
            4100: CompletionMetrics(filled_items=37, total_items=40, completion_rate=92.5),
        },
    )
    metrics = prefetch.metrics_for(4100, 21)
    assert metrics == CompletionMetrics(filled_items=37, total_items=40, completion_rate=92.5)


def test_missing_completion_item_as_dict():
    item = MissingCompletionItem(
        form_item_id=10,
        section_id=3,
        item_type='indicator',
        label='Staff count',
        question_type=None,
    )
    assert item.as_dict() == {
        'form_item_id': 10,
        'section_id': 3,
        'item_type': 'indicator',
        'label': 'Staff count',
        'question_type': None,
    }


def test_list_missing_items_returns_unfilled_only():
    rows = [
        (1, 10, 'indicator', 'Filled field', None),
        (2, 10, 'document_field', 'Missing doc', None),
        (3, 11, 'matrix', 'Missing matrix', None),
    ]

    query = MagicMock()
    query.join.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.side_effect = [
        rows,
        [(99,)],  # filled documents (not item 2)
    ]
    query.distinct.return_value = query

    with patch.object(
        AssignmentCompletionService,
        '_filled_non_matrix_form_item_ids',
        return_value={1},
    ), patch.object(
        AssignmentCompletionService,
        '_matrix_fill_state_by_item_id',
        return_value={},
    ), patch('app.services.assignments.completion_service.db.session.query', return_value=query):
        missing = AssignmentCompletionService.list_missing_items(5, 21, 99)

    assert [item.form_item_id for item in missing] == [2, 3]
    assert missing[0].item_type == 'document_field'
    assert missing[1].item_type == 'matrix'


def test_list_missing_items_excludes_hidden_fields():
    rows = [
        (1, 10, 'indicator', 'Visible missing', None),
    ]

    query = MagicMock()
    query.join.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.side_effect = [
        rows,
        [],
    ]
    query.distinct.return_value = query

    with patch.object(
        AssignmentCompletionService,
        '_filled_non_matrix_form_item_ids',
        return_value=set(),
    ), patch.object(
        AssignmentCompletionService,
        '_matrix_fill_state_by_item_id',
        return_value={},
    ), patch('app.services.assignments.completion_service.db.session.query', return_value=query):
        missing = AssignmentCompletionService.list_missing_items(
            5, 21, 99, hidden_field_ids={2},
        )

    assert [item.form_item_id for item in missing] == [1]
    assert query.filter.call_count >= 1


def test_compute_for_assignment_excludes_hidden_from_total():
    with patch.object(
        AssignmentCompletionService,
        '_count_template_total_items',
        return_value=5,
    ) as count_total, patch.object(
        AssignmentCompletionService,
        '_count_filled_items',
        return_value=3,
    ) as count_filled:
        metrics = AssignmentCompletionService.compute_for_assignment(
            5, 21, 99, hidden_field_ids={2, 3}, hidden_section_ids={10},
        )

    count_total.assert_called_once_with(21, 99, {2, 3}, {10})
    count_filled.assert_called_once_with(5, 21, 99, {2, 3}, {10})
    assert metrics == CompletionMetrics(filled_items=3, total_items=5, completion_rate=60.0)


def test_stored_rate_for_returns_persisted_value():
    aes = MagicMock()
    aes.id = 5
    aes.completion_rate = 77.6
    assert AssignmentCompletionService.stored_rate_for(aes) == 77.6


def test_stored_rate_for_refreshes_when_missing():
    aes = MagicMock()
    aes.id = 5
    aes.completion_rate = None
    with patch.object(
        AssignmentCompletionService,
        'refresh_and_persist',
        return_value=42.0,
    ) as refresh:
        assert AssignmentCompletionService.stored_rate_for(aes) == 42.0
    refresh.assert_called_once_with(5)


def test_refresh_and_persist_writes_rate():
    aes = MagicMock()
    aes.id = 5
    metrics = CompletionMetrics(filled_items=3, total_items=4, completion_rate=75.0)
    with patch(
        'app.services.assignments.completion_service.db.session.get',
        return_value=aes,
    ), patch.object(
        AssignmentCompletionService,
        '_template_context_for_aes',
        return_value=(10, 99),
    ), patch.object(
        AssignmentCompletionService,
        'compute_for_assignment',
        return_value=metrics,
    ), patch('app.services.assignments.completion_service.db.session.flush'):
        rate = AssignmentCompletionService.refresh_and_persist(5)

    assert rate == 75.0
    assert aes.completion_rate == 75.0


def test_backfill_persisted_rates_batches_updates(app, db_session):
    batch_one = [(1, 10, 20), (2, 10, 20)]
    batch_two = [(3, 11, None)]

    def _query_side_effect(*_args, **_kwargs):
        chain = MagicMock()
        chain.join.return_value = chain
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.limit.return_value = chain
        if not hasattr(_query_side_effect, "calls"):
            _query_side_effect.calls = 0
        _query_side_effect.calls += 1
        if _query_side_effect.calls == 1:
            chain.all.return_value = batch_one
        elif _query_side_effect.calls == 2:
            chain.all.return_value = batch_two
        else:
            chain.all.return_value = []
        return chain

    with app.app_context():
        with patch(
            'app.services.assignments.completion_service.db.session.query',
            side_effect=_query_side_effect,
        ), patch.object(
            AssignmentCompletionService,
            '_count_template_total_items',
            return_value=5,
        ) as count_total, patch.object(
            AssignmentCompletionService,
            '_count_filled_items',
            side_effect=[3, 4],
        ) as count_filled, patch(
            'app.services.assignments.completion_service.db.session.bulk_update_mappings',
        ) as bulk_update, patch(
            'app.services.assignments.completion_service.db.session.commit',
        ) as commit:
            updated = AssignmentCompletionService.backfill_persisted_rates(batch_size=2)

    assert updated == 3
    assert count_total.call_count == 1
    assert count_filled.call_count == 2
    assert bulk_update.call_count == 2
    assert commit.call_count == 2


def test_filled_non_matrix_query_uses_countable_form_item_filter():
    """Excluded items with saved data must not count toward filled_items (regression for >100% rates)."""
    filter_clauses = []

    class Chain:
        def join(self, *args, **kwargs):
            return self

        def filter(self, *args):
            filter_clauses.extend(args)
            return self

        def all(self):
            return []

    with patch(
        'app.services.assignments.completion_service.db.session.query',
        return_value=Chain(),
    ), patch(
        'app.services.assignments.completion_service._repeat_section_id_by_section_id',
        return_value={},
    ), patch.object(
        AssignmentCompletionService,
        '_filled_repeat_non_matrix_item_ids',
        return_value=set(),
    ):
        AssignmentCompletionService._filled_non_matrix_form_item_ids(
            1,
            10,
            20,
            _published_filters_single(10, 20),
        )

    countable_str = str(_countable_form_item_filter())
    assert any(countable_str in str(clause) for clause in filter_clauses)


def test_calculate_section_completion_skips_excluded_fields():
    from types import SimpleNamespace

    from app.routes.forms.helpers import calculate_section_completion_status

    excluded = SimpleNamespace(
        id=1414,
        field_type_for_js='textarea',
        is_image=False,
        is_indicator=False,
        is_question=True,
        is_document_field=False,
        is_matrix=False,
        is_required_for_js=False,
        config={'exclude_from_completion_rate': True},
    )
    required = SimpleNamespace(
        id=100,
        field_type_for_js='text',
        is_image=False,
        is_indicator=False,
        is_question=True,
        is_document_field=False,
        is_matrix=False,
        is_required_for_js=True,
        config={},
    )
    section = SimpleNamespace(name='Test section', fields_ordered=[excluded, required])

    statuses = calculate_section_completion_status([section], {}, {})
    assert statuses['Test section'] == 'Not Started'


def test_repeat_group_row_is_filled_with_value():
    from types import SimpleNamespace

    from app.services.assignments.completion_service import _repeat_group_row_is_filled

    row = SimpleNamespace(
        not_applicable=False,
        data_not_available=False,
        disagg_data={'name': '__other__', 'code': ''},
        prefilled_disagg_data=None,
        imputed_disagg_data=None,
        value='Uganda - Ebola Outbreak (MDRUG055)',
        prefilled_value=None,
        imputed_value=None,
    )
    assert _repeat_group_row_is_filled(row) is True


def test_maybe_refresh_after_exclude_change_skips_draft_version():
    form_item = MagicMock()
    form_item.version_id = 2
    form_item.config = {'exclude_from_completion_rate': True}
    form_item.template = MagicMock(published_version_id=1)

    refreshed = AssignmentCompletionService.maybe_refresh_after_exclude_from_completion_change(
        form_item, False
    )

    assert refreshed == 0


def test_maybe_refresh_after_exclude_change_refreshes_published_version():
    form_item = MagicMock()
    form_item.version_id = 1
    form_item.config = {'exclude_from_completion_rate': True}
    form_item.template = MagicMock(id=10, published_version_id=1)

    with patch.object(
        AssignmentCompletionService,
        'refresh_for_template_with_existing_rates',
        return_value=3,
    ) as refresh:
        refreshed = AssignmentCompletionService.maybe_refresh_after_exclude_from_completion_change(
            form_item, False
        )

    refresh.assert_called_once_with(10)
    assert refreshed == 3


def test_maybe_refresh_after_exclude_change_no_op_when_unchanged():
    form_item = MagicMock()
    form_item.version_id = 1
    form_item.config = {'exclude_from_completion_rate': False}
    form_item.template = MagicMock(id=10, published_version_id=1)

    with patch.object(
        AssignmentCompletionService,
        'refresh_for_template_with_existing_rates',
    ) as refresh:
        refreshed = AssignmentCompletionService.maybe_refresh_after_exclude_from_completion_change(
            form_item, False
        )

    refresh.assert_not_called()
    assert refreshed == 0


def test_refresh_for_template_with_existing_rates_only_targets_non_zero_rows():
    with patch(
        'app.services.assignments.completion_service.db.session.query',
    ) as query, patch.object(
        AssignmentCompletionService,
        'refresh_and_persist',
    ) as refresh:
        chain = MagicMock()
        query.return_value = chain
        chain.join.return_value = chain
        chain.filter.return_value = chain
        chain.all.return_value = [(11,), (12,)]

        count = AssignmentCompletionService.refresh_for_template_with_existing_rates(10)

    assert count == 2
    refresh.assert_any_call(11)
    refresh.assert_any_call(12)
