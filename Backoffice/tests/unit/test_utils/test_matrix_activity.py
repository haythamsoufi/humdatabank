"""Tests for matrix recent-activity display helpers."""

from app.utils.matrix_activity import (
    collect_matrix_activity_cell_changes,
    is_matrix_activity_payload,
    matrix_activity_has_visible_changes,
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

    def test_missing_vs_metadata_zero_string_is_not_a_change(self):
        blob = {"original": "0", "modified": "0", "isModified": False}
        assert matrix_cell_activity_values_differ(None, blob) is False
        assert matrix_cell_activity_values_differ(blob, None) is False

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


class TestCollectMatrixActivityCellChanges:
    def test_added_matrix_with_all_zeros_has_no_visible_changes(self):
        new = {
            "_matrix_change": True,
            "Response - Disasters and crises_Funding (CHF)": 0,
            "Response - Disasters and crises_Expenditure (CHF)": 0,
        }
        assert collect_matrix_activity_cell_changes({}, new) == {}
        assert matrix_activity_has_visible_changes({}, new) is False

    def test_updated_matrix_with_only_new_zero_columns_has_no_visible_changes(self):
        old = {
            "_matrix_change": True,
            "IFRC Secretariat_NS 2025 Total Funding": 58793,
            "PNSs_NS 2025 Total Funding": 5621,
        }
        new = {
            "_matrix_change": True,
            "IFRC Secretariat_NS 2025 Total Funding": 58793,
            "PNSs_NS 2025 Total Funding": 5621,
            "IFRC Secretariat_ns_fun": 0,
        }
        assert matrix_activity_has_visible_changes(old, new) is False

    def test_real_numeric_change_is_visible(self):
        old = {"_matrix_change": True, "13_SP2": 0}
        new = {"_matrix_change": True, "13_SP2": 108020}
        assert matrix_activity_has_visible_changes(old, new) is True
        rows = collect_matrix_activity_cell_changes(old, new)
        assert "13" in rows
        assert rows["13"][0][0] == "SP2"

    def test_single_checkbox_tick_ignores_unchanged_zero_cells(self):
        """Only the ticked Supported cell should appear, not Planned 0→0 rows."""
        new = {
            "_matrix_change": True,
            "45_EFs Planned": {"original": "0", "modified": "0", "isModified": False},
            "45_SP1 Planned": {"original": "0", "modified": "0", "isModified": False},
            "45_SP2 Planned": {"original": "0", "modified": "0", "isModified": False},
            "45_SP2 Supported": {"original": "0", "modified": "1", "isModified": True},
            "45_SP3 Planned": {"original": "0", "modified": "0", "isModified": False},
            "45_SP4 Planned": {"original": "0", "modified": "0", "isModified": False},
            "45_SP5 Planned": {"original": "0", "modified": "0", "isModified": False},
        }
        rows = collect_matrix_activity_cell_changes({}, new)
        assert list(rows.keys()) == ["45"]
        assert len(rows["45"]) == 1
        assert rows["45"][0][0] == "SP2 Supported"


class TestIsMatrixActivityPayload:
    def test_detects_matrix_sentinel(self):
        assert is_matrix_activity_payload("", {"_matrix_change": True, "a_b": 1}) is True
        assert is_matrix_activity_payload("plain", "text") is False
