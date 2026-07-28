"""Unit tests for assignment completion service."""

from app.services.assignments.completion_service import (
    CompletionMetrics,
    CompletionPrefetch,
    completion_rate_percent,
    matrix_entry_is_filled,
)


def test_matrix_entry_is_filled_not_applicable():
    assert matrix_entry_is_filled(None, True) is True


def test_matrix_entry_is_filled_with_cell_value():
    assert matrix_entry_is_filled({'_meta': 'x', 'cell_a': '5'}, False) is True


def test_matrix_entry_is_filled_empty():
    assert matrix_entry_is_filled({'_meta': 'x'}, False) is False
    assert matrix_entry_is_filled(None, False) is False


def test_completion_rate_percent():
    assert completion_rate_percent(37, 40) == 92.5
    assert completion_rate_percent(0, 0) == 0.0


def test_completion_prefetch_metrics_for():
    prefetch = CompletionPrefetch(
        total_items_by_template={21: 40},
        filled_data_by_aes={4100: 34},
        filled_documents_by_aes={4100: 3},
    )
    metrics = prefetch.metrics_for(4100, 21)
    assert metrics == CompletionMetrics(filled_items=37, total_items=40, completion_rate=92.5)
