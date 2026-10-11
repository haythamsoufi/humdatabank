"""Regression: missing module-level names made get_value_breakdown fail with 'Failed to compute value breakdown'."""
import app.services.ai.data.form_retrieval as form_retrieval


def test_point_indicator_sorting_helpers_are_importable():
    assert callable(form_retrieval.period_chronology_sort_key)
    assert form_retrieval._dt.min is not None
