"""Tools that return an error dict (instead of raising) must not be reported as successful."""
from app.services.ai.tools.registry import _soft_error_from_result


def test_error_dict_is_a_failure():
    assert _soft_error_from_result({"error": "Failed to compute value breakdown"}) == (
        "Failed to compute value breakdown"
    )
    assert _soft_error_from_result({"success": False, "error": "boom"}) == "boom"
    assert _soft_error_from_result({"success": False}) is not None


def test_normal_results_are_not_failures():
    assert _soft_error_from_result({"total": 47, "records_count": 1}) is None
    assert _soft_error_from_result({"success": True, "value": "47"}) is None
    assert _soft_error_from_result({"success": True, "error": None}) is None
    assert _soft_error_from_result([{"content": "x"}]) is None
    assert _soft_error_from_result(None) is None
