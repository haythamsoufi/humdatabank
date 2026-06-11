"""Tests for activity_endpoint_catalog/__init__.py – covers the duplicate-key guard."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.utils.activity_endpoint_catalog import (
    ENDPOINT_ACTIVITY_SPECS,
    resolve_activity_catalog_spec,
)
from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


# ---------------------------------------------------------------------------
# _merge_registry – duplicate-key guard
# ---------------------------------------------------------------------------


def test_merge_registry_wildcard_removes_method_specific_rows():
    """
    _merge_registry applies wildcard '*' overrides by removing all existing
    (method, endpoint) pairs for that endpoint and inserting ('*', endpoint).
    """
    from app.utils.activity_endpoint_catalog import _merge_registry
    from app.utils.activity_endpoint_catalog.manual_overrides import MANUAL_ACTIVITY_OVERRIDES

    # Build a fake generated catalog that has an entry for an endpoint that
    # also has a wildcard in MANUAL_ACTIVITY_OVERRIDES (if any), or inject one.
    wildcard_entries = [(m, ep) for (m, ep) in MANUAL_ACTIVITY_OVERRIDES if m == "*"]
    if wildcard_entries:
        _, ep = wildcard_entries[0]
        result = _merge_registry()
        # The wildcard entry should be in the merged registry
        assert ("*", ep) in result
    else:
        # No real wildcard entries – inject a fake wildcard override and fake generated spec
        fake_spec_gen = {
            ("POST", "fake_bp.some_action"): ActivityEndpointSpec(description="Generated"),
        }
        fake_override = {
            ("*", "fake_bp.some_action"): ActivityEndpointSpec(description="Wildcard override"),
        }
        with patch(
            "app.utils.activity_endpoint_catalog.GENERATED_ACTIVITY_SPECS",
            fake_spec_gen,
        ), patch(
            "app.utils.activity_endpoint_catalog.MANUAL_ACTIVITY_OVERRIDES",
            fake_override,
        ):
            result = _merge_registry()
            assert ("*", "fake_bp.some_action") in result
            assert ("POST", "fake_bp.some_action") not in result
            assert result[("*", "fake_bp.some_action")].description == "Wildcard override"


# ---------------------------------------------------------------------------
# resolve_activity_catalog_spec – None / missing inputs
# ---------------------------------------------------------------------------


def test_resolve_activity_catalog_spec_none_endpoint():
    result = resolve_activity_catalog_spec("POST", None)
    assert result is None


def test_resolve_activity_catalog_spec_none_method_normalizes_to_get():
    # GET entries should not generally appear, but the lookup normalizes None → "GET"
    # and falls through to wildcard; just asserting no exception and returns Optional
    result = resolve_activity_catalog_spec(None, "some.nonexistent_endpoint_xyz")
    assert result is None


def test_resolve_activity_catalog_spec_known_entry():
    s = resolve_activity_catalog_spec("POST", "ai_management.traces_bulk_delete")
    assert s is not None
    assert isinstance(s, ActivityEndpointSpec)


def test_endpoint_activity_specs_populated():
    assert len(ENDPOINT_ACTIVITY_SPECS) > 0


def test_endpoint_activity_specs_all_have_description():
    for key, spec in ENDPOINT_ACTIVITY_SPECS.items():
        assert spec.description, f"Spec for {key!r} has empty description"


def test_wildcard_method_resolution():
    """Wildcard '*' entries are correctly resolved regardless of HTTP method."""
    wildcard_registry = {
        ("*", "some.action"): ActivityEndpointSpec(description="wildcard hit"),
    }
    from app.utils.activity_endpoint_catalog.spec import lookup_activity_endpoint_spec

    result = lookup_activity_endpoint_spec("DELETE", "some.action", wildcard_registry)
    assert result is not None
    assert result.description == "wildcard hit"


def test_manual_overrides_win_over_generated():
    """Manual overrides replace generated entries for the same (method, endpoint) key."""
    s = resolve_activity_catalog_spec("POST", "ai_management.traces_bulk_delete")
    assert s is not None
    assert s.description == "Deleted traces"
    assert s.activity_type == "admin_ai"
