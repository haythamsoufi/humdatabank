"""Unit tests for assignment completion service."""

from unittest.mock import MagicMock, patch

from types import SimpleNamespace

from app.services.assignments.completion_service import (
    AssignmentCompletionService,
    CompletionMetrics,
    CompletionPrefetch,
    MissingCompletionItem,
    _countable_form_item_filter,
    _published_filters_single,
    completion_rate_percent,
    emergency_operations_option_count,
    matrix_entry_is_filled,
    matrix_has_manual_rows,
    matrix_is_list_backed,
    resolved_list_option_count,
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
    ), patch.object(
        AssignmentCompletionService,
        '_empty_option_list_ids_for_assignment',
        return_value=frozenset(),
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
    ), patch.object(
        AssignmentCompletionService,
        '_empty_option_list_ids_for_assignment',
        return_value=frozenset(),
    ), patch('app.services.assignments.completion_service.db.session.query', return_value=query):
        missing = AssignmentCompletionService.list_missing_items(
            5, 21, 99, hidden_field_ids={2},
        )

    assert [item.form_item_id for item in missing] == [1]
    assert query.filter.call_count >= 1


def test_compute_for_assignment_excludes_hidden_from_total():
    with patch.object(
        AssignmentCompletionService,
        '_relevance_hidden_ids_for_assignment',
        return_value=(frozenset(), frozenset()),
    ), patch.object(
        AssignmentCompletionService,
        '_empty_option_list_ids_for_assignment',
        return_value=frozenset(),
    ), patch.object(
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


def test_compute_for_assignment_merges_relevance_hidden_ids():
    """Server-resolvable relevance hiding (e.g. a period-gated section) must be
    merged into the client-supplied hidden ids, not override them."""
    with patch.object(
        AssignmentCompletionService,
        '_relevance_hidden_ids_for_assignment',
        return_value=(frozenset({99}), frozenset({262})),
    ), patch.object(
        AssignmentCompletionService,
        '_empty_option_list_ids_for_assignment',
        return_value=frozenset(),
    ), patch.object(
        AssignmentCompletionService,
        '_count_template_total_items',
        return_value=6,
    ) as count_total, patch.object(
        AssignmentCompletionService,
        '_count_filled_items',
        return_value=6,
    ) as count_filled:
        metrics = AssignmentCompletionService.compute_for_assignment(
            5, 21, 99, hidden_field_ids={2}, hidden_section_ids={10},
        )

    count_total.assert_called_once_with(21, 99, {2, 99}, {10, 262})
    count_filled.assert_called_once_with(5, 21, 99, {2, 99}, {10, 262})
    assert metrics == CompletionMetrics(filled_items=6, total_items=6, completion_rate=100.0)


def test_compute_for_assignment_no_client_hidden_ids_still_applies_relevance():
    """Regression: the persisted/dashboard rate (no client-supplied hidden ids)
    must still exclude relevance-hidden sections, e.g. a section gated on
    assignment_period that doesn't match the current assignment."""
    with patch.object(
        AssignmentCompletionService,
        '_relevance_hidden_ids_for_assignment',
        return_value=(frozenset(), frozenset({262})),
    ), patch.object(
        AssignmentCompletionService,
        '_empty_option_list_ids_for_assignment',
        return_value=frozenset(),
    ), patch.object(
        AssignmentCompletionService,
        '_count_template_total_items',
        return_value=6,
    ) as count_total, patch.object(
        AssignmentCompletionService,
        '_count_filled_items',
        return_value=6,
    ):
        metrics = AssignmentCompletionService.compute_for_assignment(5, 21, 99)

    count_total.assert_called_once_with(21, 99, set(), {262})
    assert metrics.completion_rate == 100.0


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
    aes.completion_rate = 10.0
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
    ), patch('app.services.assignments.completion_service.db.session.flush') as flush:
        rate = AssignmentCompletionService.refresh_and_persist(5)

    assert rate == 75.0
    assert aes.completion_rate == 75.0
    flush.assert_called_once()


def test_refresh_and_persist_skips_write_when_unchanged():
    aes = MagicMock()
    aes.id = 5
    aes.completion_rate = 95.9
    metrics = CompletionMetrics(filled_items=47, total_items=49, completion_rate=95.918)
    with patch(
        'app.services.assignments.completion_service.db.session.get',
        return_value=aes,
    ), patch.object(
        AssignmentCompletionService,
        '_template_context_for_aes',
        return_value=(33, 37),
    ), patch.object(
        AssignmentCompletionService,
        'compute_for_assignment',
        return_value=metrics,
    ), patch('app.services.assignments.completion_service.db.session.flush') as flush:
        rate = AssignmentCompletionService.refresh_and_persist(5)

    assert rate == 95.9
    flush.assert_not_called()


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
            '_relevance_hidden_ids_for_assignment',
            return_value=(frozenset(), frozenset()),
        ), patch.object(
            AssignmentCompletionService,
            '_empty_option_list_ids_for_assignment',
            return_value=frozenset(),
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


def test_backfill_persisted_rates_bypasses_total_cache_when_relevance_hidden(app, db_session):
    """When a row has relevance-hidden sections, total_items must be recomputed
    fresh (not shared via the per-template-version cache), since the hidden set
    can differ from other assignments on the same template/version."""
    rows = [(1, 10, 20)]

    def _query_side_effect(*_args, **_kwargs):
        chain = MagicMock()
        chain.join.return_value = chain
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.limit.return_value = chain
        if not hasattr(_query_side_effect, "calls"):
            _query_side_effect.calls = 0
        _query_side_effect.calls += 1
        chain.all.return_value = rows if _query_side_effect.calls == 1 else []
        return chain

    with app.app_context():
        with patch(
            'app.services.assignments.completion_service.db.session.query',
            side_effect=_query_side_effect,
        ), patch.object(
            AssignmentCompletionService,
            '_relevance_hidden_ids_for_assignment',
            return_value=(frozenset(), frozenset({262})),
        ), patch.object(
            AssignmentCompletionService,
            '_empty_option_list_ids_for_assignment',
            return_value=frozenset(),
        ), patch.object(
            AssignmentCompletionService,
            '_count_template_total_items',
            return_value=6,
        ) as count_total, patch.object(
            AssignmentCompletionService,
            '_count_filled_items',
            return_value=6,
        ) as count_filled, patch(
            'app.services.assignments.completion_service.db.session.bulk_update_mappings',
        ), patch(
            'app.services.assignments.completion_service.db.session.commit',
        ):
            updated = AssignmentCompletionService.backfill_persisted_rates(batch_size=2)

    assert updated == 1
    count_total.assert_called_once_with(10, 20, frozenset(), frozenset({262}))
    count_filled.assert_called_once_with(1, 10, 20, frozenset(), frozenset({262}))


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


def _list_backed_matrix_item(item_id=960, row_mode='list_library', rows=None, plugin_config=None):
    return SimpleNamespace(
        id=item_id,
        lookup_list_id='emergency_operations',
        list_filters_json=None,
        config={
            'matrix_config': {
                'row_mode': row_mode,
                'lookup_list_id': 'emergency_operations',
                'rows': rows or [],
                'plugin_config': plugin_config or {
                    'emops_operation_types': ['Emergency Appeal'],
                },
            },
        },
    )


def test_matrix_is_list_backed_for_library_and_hybrid():
    assert matrix_is_list_backed(_list_backed_matrix_item()) is True
    assert matrix_is_list_backed(_list_backed_matrix_item(row_mode='hybrid')) is True
    assert matrix_is_list_backed(SimpleNamespace(
        lookup_list_id=None,
        config={'matrix_config': {'row_mode': 'manual', 'rows': ['A']}},
    )) is False


def test_matrix_has_manual_rows_detects_static_hybrid_rows():
    assert matrix_has_manual_rows(_list_backed_matrix_item(rows=[{'name': 'Static'}])) is True
    assert matrix_has_manual_rows(_list_backed_matrix_item(rows=[])) is False


def test_emergency_operations_option_count_unknown_when_cache_cold():
    item = _list_backed_matrix_item()
    with patch(
        'app.services.assignments.completion_service._emergency_operations_cache_is_warm',
        return_value=False,
    ), patch(
        'app.services.forms.emergency_section_binding._country_iso_for_aes',
        return_value='BGR',
    ):
        assert emergency_operations_option_count(item, SimpleNamespace()) is None


def test_emergency_operations_cache_is_warm_requires_nonempty_results():
    from app.services.assignments.completion_service import _emergency_operations_cache_is_warm

    # Missing file → cold
    with patch(
        'plugins.emergency_operations.data_store.get_data_store',
    ) as mock_store:
        mock_store.return_value.load_cached.return_value = None
        assert _emergency_operations_cache_is_warm() is False

    # File exists but results=[] → cold (cannot distinguish from a failed refresh)
    with patch(
        'plugins.emergency_operations.data_store.get_data_store',
    ) as mock_store:
        mock_store.return_value.load_cached.return_value = {'results': [], 'fetched_at': '2026-01-01T00:00:00Z'}
        assert _emergency_operations_cache_is_warm() is False

    # File exists with actual results → warm
    with patch(
        'plugins.emergency_operations.data_store.get_data_store',
    ) as mock_store:
        mock_store.return_value.load_cached.return_value = {'results': [{'code': 'MDRBG001'}]}
        assert _emergency_operations_cache_is_warm() is True


def test_emergency_operations_option_count_zero_when_cache_warm_and_empty():
    from app.services.assignments import completion_service as completion_mod

    item = _list_backed_matrix_item()
    completion_mod._eo_option_count_cache.clear()
    with patch(
        'app.services.assignments.completion_service._emergency_operations_cache_is_warm',
        return_value=True,
    ), patch(
        'app.services.forms.emergency_section_binding._country_iso_for_aes',
        return_value='BGR',
    ), patch(
        'app.services.forms.emergency_section_binding._assignment_period_for_aes',
        return_value='Annual 2024',
    ), patch(
        'plugins.emergency_operations.routes.get_emergency_operations_data',
        return_value=[],
    ):
        assert emergency_operations_option_count(item, SimpleNamespace()) == 0


def test_resolved_list_option_count_delegates_to_emergency_operations():
    item = _list_backed_matrix_item()
    with patch(
        'app.services.assignments.completion_service.emergency_operations_option_count',
        return_value=0,
    ) as eo_count:
        assert resolved_list_option_count(item, SimpleNamespace()) == 0
    eo_count.assert_called_once()


def test_empty_option_list_ids_excludes_empty_list_library_matrix():
    item = _list_backed_matrix_item()
    query = MagicMock()
    query.join.return_value = query
    query.filter.return_value = query
    query.all.return_value = [item]

    with patch(
        'app.services.assignments.completion_service.db.session.query',
        return_value=query,
    ), patch(
        'app.services.assignments.completion_service.db.session.get',
        return_value=SimpleNamespace(id=4397),
    ), patch(
        'app.services.assignments.completion_service.resolved_list_option_count',
        return_value=0,
    ):
        empty = AssignmentCompletionService._empty_option_list_ids_for_assignment(4397, 24, 99)

    assert empty == frozenset({960})


def test_empty_option_list_ids_keeps_matrix_when_options_exist():
    item = _list_backed_matrix_item()
    query = MagicMock()
    query.join.return_value = query
    query.filter.return_value = query
    query.all.return_value = [item]

    with patch(
        'app.services.assignments.completion_service.db.session.query',
        return_value=query,
    ), patch(
        'app.services.assignments.completion_service.db.session.get',
        return_value=SimpleNamespace(id=4397),
    ), patch(
        'app.services.assignments.completion_service.resolved_list_option_count',
        return_value=3,
    ):
        empty = AssignmentCompletionService._empty_option_list_ids_for_assignment(4397, 24, 99)

    assert empty == frozenset()


def test_empty_option_list_ids_keeps_hybrid_with_static_rows():
    item = _list_backed_matrix_item(row_mode='hybrid', rows=[{'name': 'Static'}])
    query = MagicMock()
    query.join.return_value = query
    query.filter.return_value = query
    query.all.return_value = [item]

    with patch(
        'app.services.assignments.completion_service.db.session.query',
        return_value=query,
    ), patch(
        'app.services.assignments.completion_service.db.session.get',
        return_value=SimpleNamespace(id=4397),
    ), patch(
        'app.services.assignments.completion_service.resolved_list_option_count',
        return_value=0,
    ) as option_count:
        empty = AssignmentCompletionService._empty_option_list_ids_for_assignment(4397, 24, 99)

    option_count.assert_not_called()
    assert empty == frozenset()


def test_empty_option_list_ids_keeps_matrix_when_count_unknown():
    item = _list_backed_matrix_item()
    query = MagicMock()
    query.join.return_value = query
    query.filter.return_value = query
    query.all.return_value = [item]

    with patch(
        'app.services.assignments.completion_service.db.session.query',
        return_value=query,
    ), patch(
        'app.services.assignments.completion_service.db.session.get',
        return_value=SimpleNamespace(id=4397),
    ), patch(
        'app.services.assignments.completion_service.resolved_list_option_count',
        return_value=None,
    ):
        empty = AssignmentCompletionService._empty_option_list_ids_for_assignment(4397, 24, 99)

    assert empty == frozenset()


def test_compute_for_assignment_excludes_empty_option_list_items():
    with patch.object(
        AssignmentCompletionService,
        '_relevance_hidden_ids_for_assignment',
        return_value=(frozenset(), frozenset()),
    ), patch.object(
        AssignmentCompletionService,
        '_empty_option_list_ids_for_assignment',
        return_value=frozenset({960}),
    ), patch.object(
        AssignmentCompletionService,
        '_count_template_total_items',
        return_value=10,
    ) as count_total, patch.object(
        AssignmentCompletionService,
        '_count_filled_items',
        return_value=10,
    ) as count_filled:
        metrics = AssignmentCompletionService.compute_for_assignment(4397, 24, 99)

    count_total.assert_called_once_with(24, 99, {960}, set())
    count_filled.assert_called_once_with(4397, 24, 99, {960}, set())
    assert metrics.completion_rate == 100.0


def test_list_missing_items_skips_empty_option_list_matrices():
    rows = [
        (960, 10, 'matrix', 'Emergency Appeals', None),
        (2, 10, 'indicator', 'Visible missing', None),
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
    ), patch.object(
        AssignmentCompletionService,
        '_empty_option_list_ids_for_assignment',
        return_value=frozenset({960}),
    ), patch('app.services.assignments.completion_service.db.session.query', return_value=query):
        missing = AssignmentCompletionService.list_missing_items(4397, 24, 99)

    assert [item.form_item_id for item in missing] == [2]


def test_backfill_persisted_rates_bypasses_total_cache_when_empty_option_list(app, db_session):
    rows = [(1, 10, 20)]

    def _query_side_effect(*_args, **_kwargs):
        chain = MagicMock()
        chain.join.return_value = chain
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.limit.return_value = chain
        if not hasattr(_query_side_effect, "calls"):
            _query_side_effect.calls = 0
        _query_side_effect.calls += 1
        chain.all.return_value = rows if _query_side_effect.calls == 1 else []
        return chain

    with app.app_context():
        with patch(
            'app.services.assignments.completion_service.db.session.query',
            side_effect=_query_side_effect,
        ), patch.object(
            AssignmentCompletionService,
            '_relevance_hidden_ids_for_assignment',
            return_value=(frozenset(), frozenset()),
        ), patch.object(
            AssignmentCompletionService,
            '_empty_option_list_ids_for_assignment',
            return_value=frozenset({960}),
        ), patch.object(
            AssignmentCompletionService,
            '_count_template_total_items',
            return_value=9,
        ) as count_total, patch.object(
            AssignmentCompletionService,
            '_count_filled_items',
            return_value=9,
        ) as count_filled, patch(
            'app.services.assignments.completion_service.db.session.bulk_update_mappings',
        ), patch(
            'app.services.assignments.completion_service.db.session.commit',
        ):
            updated = AssignmentCompletionService.backfill_persisted_rates(batch_size=2)

    assert updated == 1
    count_total.assert_called_once_with(10, 20, {960}, frozenset())
    count_filled.assert_called_once_with(1, 10, 20, {960}, frozenset())
