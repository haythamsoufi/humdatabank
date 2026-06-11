"""
Comprehensive tests for app/utils/activity_types.py.

Pushes coverage from ~83 % → 100 % by exercising all branches of
normalize_activity_type and validating the data dictionaries.
"""

from __future__ import annotations

import pytest

from app.utils.activity_types import (
    CANONICAL_ACTIVITY_TYPES,
    LEGACY_ACTIVITY_TYPE_MAP,
    normalize_activity_type,
)


# ---------------------------------------------------------------------------
# normalize_activity_type – all branches
# ---------------------------------------------------------------------------


class TestNormalizeActivityType:
    def test_none_returns_none(self):
        assert normalize_activity_type(None) is None

    def test_empty_string_returns_empty(self):
        assert normalize_activity_type("") == ""

    def test_whitespace_only_returns_empty(self):
        # strip() of "  " → "" → returned as-is (not None)
        result = normalize_activity_type("   ")
        assert result == ""

    def test_canonical_type_returned_unchanged(self):
        for ct in CANONICAL_ACTIVITY_TYPES:
            assert normalize_activity_type(ct) == ct, f"Failed for {ct!r}"

    def test_legacy_type_mapped(self):
        for legacy, canonical in LEGACY_ACTIVITY_TYPE_MAP.items():
            assert normalize_activity_type(legacy) == canonical, f"Failed for {legacy!r}"

    def test_unknown_type_passthrough(self):
        assert normalize_activity_type("totally_unknown") == "totally_unknown"

    def test_page_view_canonical(self):
        assert normalize_activity_type("page_view") == "page_view"

    def test_login_canonical(self):
        assert normalize_activity_type("login") == "login"

    def test_form_submit_legacy(self):
        assert normalize_activity_type("form_submit") == "form_submitted"

    def test_form_save_legacy(self):
        assert normalize_activity_type("form_save") == "form_saved"

    def test_data_save_legacy(self):
        assert normalize_activity_type("data_save") == "form_saved"

    def test_data_update_legacy(self):
        assert normalize_activity_type("data_update") == "data_modified"

    def test_data_delete_legacy(self):
        assert normalize_activity_type("data_delete") == "data_deleted"

    def test_file_upload_legacy(self):
        assert normalize_activity_type("file_upload") == "file_uploaded"

    def test_strips_surrounding_whitespace(self):
        assert normalize_activity_type("  login  ") == "login"

    def test_non_string_coerced(self):
        # activity_type is cast via str()
        result = normalize_activity_type(42)  # type: ignore[arg-type]
        assert result == "42"

    def test_admin_ai_canonical(self):
        assert normalize_activity_type("admin_ai") == "admin_ai"

    def test_admin_other_canonical(self):
        assert normalize_activity_type("admin_other") == "admin_other"


# ---------------------------------------------------------------------------
# Data dict integrity
# ---------------------------------------------------------------------------


class TestDataDictIntegrity:
    def test_canonical_activity_types_not_empty(self):
        assert len(CANONICAL_ACTIVITY_TYPES) > 0

    def test_legacy_map_values_are_canonical(self):
        for legacy, canonical in LEGACY_ACTIVITY_TYPE_MAP.items():
            assert canonical in CANONICAL_ACTIVITY_TYPES, (
                f"Legacy type {legacy!r} maps to {canonical!r} which is not canonical"
            )

    def test_canonical_types_are_strings(self):
        for ct in CANONICAL_ACTIVITY_TYPES:
            assert isinstance(ct, str), f"Non-string canonical type: {ct!r}"

    def test_no_overlap_legacy_and_canonical(self):
        """Legacy keys should not appear in canonical set (they are aliases, not canonical)."""
        overlapping = set(LEGACY_ACTIVITY_TYPE_MAP.keys()) & CANONICAL_ACTIVITY_TYPES
        assert not overlapping, f"Legacy keys found in canonical set: {overlapping}"
