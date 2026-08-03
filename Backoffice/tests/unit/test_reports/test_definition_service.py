"""Report definition service tests."""

from __future__ import annotations

import pytest

from app.services.reports.definition_service import narrow_id_list

pytestmark = pytest.mark.unit


def test_narrow_id_list_empty_requested_returns_allowed():
    narrowed, warnings = narrow_id_list([], [1, 2, 3])
    assert set(narrowed) == {1, 2, 3}
    assert warnings == []


def test_narrow_id_list_intersection():
    narrowed, warnings = narrow_id_list([1, 2, 99], [1, 2, 3])
    assert narrowed == [1, 2]
    assert warnings


def test_narrow_id_list_unrestricted():
    narrowed, warnings = narrow_id_list([5, 6], None)
    assert narrowed == [5, 6]
    assert warnings == []
