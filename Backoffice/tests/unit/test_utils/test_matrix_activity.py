"""Tests for matrix recent-activity display helpers."""

from app.utils.matrix_activity import (
    matrix_cell_activity_values_differ,
    matrix_cell_display_value,
    trim_matrix_activity_maps,
)


class TestMatrixCellActivityValuesDiffer:
    def test_missing_vs_zero_scalar_is_not_a_change(self):
        assert matrix_cell_activity_values_differ(None, 0) is False
        assert matrix_cell_activity_values_differ(0, None) is False

    def test_zero_metadata_blob_vs_zero_scalar_is_not_a_change(self):
        blob = {"original": 0, "modified": "", "isModified": False}
        assert matrix_cell_activity_values_differ(blob, 0) is False

    def test_cleared_vs_lookup_scalar_is_a_change(self):
        cleared = {"original": 108020, "modified": "", "isModified": True}
        assert matrix_cell_activity_values_differ(cleared, 108020) is True

    def test_restore_cleared_to_scalar(self):
        cleared = {"original": 108020, "modified": "", "isModified": True}
        assert matrix_cell_display_value(cleared) == ""
        assert matrix_cell_display_value(108020) == 108020


class TestTrimMatrixActivityMaps:
    def test_only_changed_cells_kept(self):
        old = {
            "13_SP2": {"original": 108020, "modified": "", "isModified": True},
            "14_SP1": None,
            "14_SP2": 0,
        }
        new = {
            "13_SP2": 108020,
            "14_SP1": 0,
            "14_SP2": 0,
        }
        trimmed_old, trimmed_new = trim_matrix_activity_maps(old, new)
        assert trimmed_old is not None
        assert trimmed_new is not None
        assert set(trimmed_old.keys()) == {"_matrix_change", "13_SP2"}
        assert set(trimmed_new.keys()) == {"_matrix_change", "13_SP2"}
        assert trimmed_old["13_SP2"] == ""
        assert trimmed_new["13_SP2"] == 108020

    def test_no_display_changes_returns_none(self):
        old = {"14_SP1": 0, "14_SP2": {"original": 0, "modified": "", "isModified": False}}
        new = {"14_SP1": None, "14_SP2": 0}
        assert trim_matrix_activity_maps(old, new) == (None, None)
