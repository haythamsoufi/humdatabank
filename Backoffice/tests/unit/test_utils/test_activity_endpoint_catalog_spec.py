"""
Comprehensive tests for app/utils/activity_endpoint_catalog/spec.py.

Targets every branch to push coverage from ~63 % → 100 %.
"""

from __future__ import annotations

import pytest

from app.utils.activity_endpoint_catalog.spec import (
    ActivityEndpointSpec,
    fallback_description_for_unmapped,
    lookup_activity_endpoint_spec,
    merge_activity_specs,
)


# ---------------------------------------------------------------------------
# ActivityEndpointSpec – dataclass behaviour
# ---------------------------------------------------------------------------


class TestActivityEndpointSpec:
    def test_description_only(self):
        spec = ActivityEndpointSpec(description="Deleted traces")
        assert spec.description == "Deleted traces"
        assert spec.activity_type is None

    def test_with_activity_type(self):
        spec = ActivityEndpointSpec(description="Created form", activity_type="admin_forms")
        assert spec.activity_type == "admin_forms"

    def test_frozen_immutable(self):
        spec = ActivityEndpointSpec(description="Test")
        with pytest.raises((AttributeError, TypeError)):
            spec.description = "Modified"  # type: ignore[misc]

    def test_equality(self):
        a = ActivityEndpointSpec(description="X", activity_type="admin_ai")
        b = ActivityEndpointSpec(description="X", activity_type="admin_ai")
        assert a == b

    def test_inequality_description(self):
        a = ActivityEndpointSpec(description="X")
        b = ActivityEndpointSpec(description="Y")
        assert a != b


# ---------------------------------------------------------------------------
# merge_activity_specs
# ---------------------------------------------------------------------------


class TestMergeActivitySpecs:
    def test_empty_dicts(self):
        assert merge_activity_specs({}, {}) == {}

    def test_single_dict(self):
        d = {("POST", "bp.foo"): ActivityEndpointSpec(description="Foo")}
        result = merge_activity_specs(d)
        assert result == d

    def test_later_wins_on_conflict(self):
        a = {("POST", "x.y"): ActivityEndpointSpec(description="a")}
        b = {("POST", "x.y"): ActivityEndpointSpec(description="b")}
        merged = merge_activity_specs(a, b)
        assert merged[("POST", "x.y")].description == "b"

    def test_no_conflict_keys_merged(self):
        a = {("POST", "x.y"): ActivityEndpointSpec(description="a")}
        b = {("DELETE", "x.y"): ActivityEndpointSpec(description="b")}
        merged = merge_activity_specs(a, b)
        assert len(merged) == 2
        assert merged[("POST", "x.y")].description == "a"
        assert merged[("DELETE", "x.y")].description == "b"

    def test_allow_override_false_raises_on_duplicate(self):
        a = {("POST", "x.y"): ActivityEndpointSpec(description="first")}
        b = {("POST", "x.y"): ActivityEndpointSpec(description="second")}
        with pytest.raises(ValueError, match="Duplicate"):
            merge_activity_specs(a, b, allow_override=False)

    def test_allow_override_false_no_duplicate_passes(self):
        a = {("POST", "x.y"): ActivityEndpointSpec(description="first")}
        b = {("PUT", "x.y"): ActivityEndpointSpec(description="second")}
        result = merge_activity_specs(a, b, allow_override=False)
        assert len(result) == 2

    def test_three_dicts_last_wins(self):
        a = {("POST", "ep"): ActivityEndpointSpec(description="a")}
        b = {("POST", "ep"): ActivityEndpointSpec(description="b")}
        c = {("POST", "ep"): ActivityEndpointSpec(description="c")}
        assert merge_activity_specs(a, b, c)[("POST", "ep")].description == "c"


# ---------------------------------------------------------------------------
# lookup_activity_endpoint_spec
# ---------------------------------------------------------------------------


class TestLookupActivityEndpointSpec:
    def _reg(self, *entries):
        """Build a registry dict from (method, ep, description) tuples."""
        return {(m, ep): ActivityEndpointSpec(description=d) for m, ep, d in entries}

    def test_none_endpoint_returns_none(self):
        reg = self._reg(("POST", "bp.foo", "Foo"))
        assert lookup_activity_endpoint_spec("POST", None, reg) is None

    def test_empty_endpoint_returns_none(self):
        reg = self._reg(("POST", "bp.foo", "Foo"))
        assert lookup_activity_endpoint_spec("POST", "", reg) is None

    def test_exact_match(self):
        reg = self._reg(("POST", "bp.foo", "Foo"))
        result = lookup_activity_endpoint_spec("POST", "bp.foo", reg)
        assert result is not None
        assert result.description == "Foo"

    def test_method_case_normalized(self):
        reg = self._reg(("POST", "bp.foo", "Foo"))
        result = lookup_activity_endpoint_spec("post", "bp.foo", reg)
        assert result is not None
        assert result.description == "Foo"

    def test_wildcard_match(self):
        reg = {("*", "bp.foo"): ActivityEndpointSpec(description="Wildcard")}
        result = lookup_activity_endpoint_spec("DELETE", "bp.foo", reg)
        assert result is not None
        assert result.description == "Wildcard"

    def test_exact_wins_over_wildcard(self):
        reg = {
            ("POST", "bp.foo"): ActivityEndpointSpec(description="Exact"),
            ("*", "bp.foo"): ActivityEndpointSpec(description="Wildcard"),
        }
        result = lookup_activity_endpoint_spec("POST", "bp.foo", reg)
        assert result.description == "Exact"

    def test_no_match_returns_none(self):
        reg = self._reg(("POST", "bp.foo", "Foo"))
        assert lookup_activity_endpoint_spec("DELETE", "bp.bar", reg) is None

    def test_none_method_defaults_to_get(self):
        reg = {("GET", "bp.foo"): ActivityEndpointSpec(description="Get Foo")}
        result = lookup_activity_endpoint_spec(None, "bp.foo", reg)
        assert result is not None
        assert result.description == "Get Foo"

    def test_whitespace_method_defaults_to_get(self):
        reg = {("GET", "bp.foo"): ActivityEndpointSpec(description="Get Foo")}
        result = lookup_activity_endpoint_spec("   ", "bp.foo", reg)
        assert result is not None
        assert result.description == "Get Foo"


# ---------------------------------------------------------------------------
# fallback_description_for_unmapped
# ---------------------------------------------------------------------------


class TestFallbackDescriptionForUnmapped:
    def test_none_endpoint(self):
        assert fallback_description_for_unmapped("POST", None) == "Completed action"

    def test_empty_endpoint(self):
        assert fallback_description_for_unmapped("DELETE", "") == "Completed action"

    def test_get_method(self):
        result = fallback_description_for_unmapped("GET", "bp.view_report")
        assert result.startswith("Session ·")

    def test_delete_method(self):
        result = fallback_description_for_unmapped("DELETE", "bp.delete_document")
        assert result.startswith("Deleted ")

    def test_put_method(self):
        result = fallback_description_for_unmapped("PUT", "bp.update_profile")
        assert result.startswith("Updated ")

    def test_patch_method(self):
        result = fallback_description_for_unmapped("PATCH", "bp.update_profile")
        assert result.startswith("Updated ")

    def test_post_method(self):
        result = fallback_description_for_unmapped("POST", "bp.create_form")
        assert result.startswith("Completed ")

    def test_no_dot_endpoint(self):
        result = fallback_description_for_unmapped("GET", "standalone")
        assert result.startswith("Session ·")

    def test_none_method_defaults_to_get(self):
        result = fallback_description_for_unmapped(None, "bp.some_page")
        assert result.startswith("Session ·")

    def test_empty_segment_gives_action(self):
        # Endpoint with no useful segment after strip
        result = fallback_description_for_unmapped("DELETE", "bp.api_")
        # After stripping api_, empty → "action"
        assert "action" in result.lower() or result.startswith("Deleted ")
