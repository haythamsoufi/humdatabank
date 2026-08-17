"""Unit tests for UPR master import emergency appeal mapping."""

import sys
from pathlib import Path

imports_dir = Path(__file__).resolve().parents[2] / "scripts" / "imports"
if str(imports_dir) not in sys.path:
    sys.path.insert(0, str(imports_dir))

from import_upr_excel_data import (  # noqa: E402
    EMERGENCY_APPEALS_COLUMN,
    COL_HEADER_GO_UNMATCHED_PREFIX,
    ROW_GO_UNMATCHED_PREFIX,
    UprImportContext,
    _ensure_funding_ea_col_header,
    _format_emergency_operation_display,
    _parse_ns_emergency_slot_field,
    _parse_row_text_value,
    _resolve_emergency_operation_labels,
    _resolve_emergency_matrix_cells,
    _resolve_emergency_row_key,
    _stage_emergency_slot_meta,
    REPORTING_EMERGENCY_EXCEL_SECTION_TO_SLOT,
)


class TestNsEmergencyFieldParsing:
    def test_data_eo_slots(self):
        assert _parse_ns_emergency_slot_field("Data_EO1") == (1, "name")
        assert _parse_ns_emergency_slot_field("data_eo3") == (3, "name")

    def test_data_mdr_slots(self):
        assert _parse_ns_emergency_slot_field("Data_MDR2") == (2, "code")

    def test_non_emergency_returns_none(self):
        assert _parse_ns_emergency_slot_field("Number of staff") is None


class TestEmergencySlotStaging:
    def test_stage_name_and_code(self):
        ctx = UprImportContext(template_ids=[33])
        _stage_emergency_slot_meta(ctx, aes_id=10, slot=1, field="name", value="Floods")
        _stage_emergency_slot_meta(ctx, aes_id=10, slot=1, field="code", value="MDRAF015")
        assert ctx.emergency_slot_meta[(10, 1)] == {"name": "Floods", "code": "MDRAF015"}


class TestEmergencyExcelSections:
    def test_section_to_slot_map(self):
        assert REPORTING_EMERGENCY_EXCEL_SECTION_TO_SLOT["Emergency 1"] == 1
        assert REPORTING_EMERGENCY_EXCEL_SECTION_TO_SLOT["Emergency 3"] == 3


class TestParseRowTextValue:
    def test_prefers_value_column(self):
        assert _parse_row_text_value({"Value": " MDRAF007 ", "ValueNum": 1}) == "MDRAF007"


class TestResolveEmergencyOperationLabels:
    def test_prefers_go_api_name_when_code_matches(self):
        ctx = UprImportContext(template_ids=[33])
        ctx.emergency_ops_by_iso["NGA"] = {
            "MDRNG041": {"name": "Nigeria - Floods", "code": "MDRNG041"},
        }
        ctx.emergency_ops_ordered_by_iso["NGA"] = [ctx.emergency_ops_by_iso["NGA"]["MDRNG041"]]
        name, code, display = _resolve_emergency_operation_labels(
            ctx,
            iso3="NGA",
            excel_name="Nigeria Floods EA",
            excel_code="MDRNG041",
        )
        assert name == "Nigeria - Floods"
        assert code == "MDRNG041"
        assert display == "Nigeria - Floods (MDRNG041)"

    def test_falls_back_to_excel_labels_when_code_missing_in_api(self):
        ctx = UprImportContext(template_ids=[33])
        ctx.emergency_ops_by_iso["NGA"] = {}
        ctx.emergency_ops_ordered_by_iso["NGA"] = []
        name, code, display = _resolve_emergency_operation_labels(
            ctx,
            iso3="NGA",
            excel_name="Nigeria Floods EA",
            excel_code="MDRNG999",
        )
        assert name == "Nigeria Floods EA"
        assert code == "MDRNG999"
        assert display == _format_emergency_operation_display("Nigeria Floods EA", "MDRNG999")
        from upr_import_warnings import warning_text

        assert any("is not listed for this country in GO" in warning_text(w) for w in ctx.warnings)

    def test_warns_once_when_same_code_resolved_with_different_casing(self):
        ctx = UprImportContext(template_ids=[24])
        ctx.emergency_ops_by_iso["AFG"] = {}
        ctx.emergency_ops_ordered_by_iso["AFG"] = []
        _resolve_emergency_operation_labels(ctx, iso3="AFG", excel_name="Appeal A", excel_code="rfqwerqw")
        _resolve_emergency_operation_labels(ctx, iso3="AFG", excel_name="Appeal A", excel_code="RFQWERQW")
        from upr_import_warnings import warning_text

        ea_warnings = [w for w in ctx.warnings if "is not listed for this country in GO" in warning_text(w)]
        assert len(ea_warnings) == 1
        assert "RFQWERQW" in warning_text(ea_warnings[0])


class TestResolveEmergencyRowKey:
    def test_falls_back_to_excel_labels_when_code_missing_in_api(self):
        ctx = UprImportContext(template_ids=[24])
        ctx.emergency_ops_by_iso["NGA"] = {}
        ctx.emergency_ops_ordered_by_iso["NGA"] = []
        cell_key = _resolve_emergency_row_key(
            ctx,
            iso3="NGA",
            area="EA1",
            ea_code="MDRNG999",
            excel_name="Nigeria Floods EA",
        )
        assert cell_key == f"Nigeria Floods EA (MDRNG999)_{EMERGENCY_APPEALS_COLUMN}"
        from upr_import_warnings import warning_text

        assert any("The Excel name and code were imported" in warning_text(w) for w in ctx.warnings)

    def test_uses_go_api_labels_when_code_matches(self):
        ctx = UprImportContext(template_ids=[24])
        ctx.emergency_ops_by_iso["NGA"] = {
            "MDRNG041": {"name": "Nigeria - Floods", "code": "MDRNG041"},
        }
        ctx.emergency_ops_ordered_by_iso["NGA"] = [ctx.emergency_ops_by_iso["NGA"]["MDRNG041"]]
        cell_key = _resolve_emergency_row_key(
            ctx,
            iso3="NGA",
            area="EA1",
            ea_code="MDRNG041",
            excel_name="Excel-only name",
        )
        assert cell_key == f"Nigeria - Floods (MDRNG041)_{EMERGENCY_APPEALS_COLUMN}"
        from upr_import_warnings import warning_text

        assert not any("is not listed for this country in GO" in warning_text(w) for w in ctx.warnings)


class TestResolveEmergencyMatrixCells:
    def test_sets_row_go_unmatched_for_excel_fallback(self):
        ctx = UprImportContext(template_ids=[24])
        ctx.emergency_ops_by_iso["NGA"] = {}
        ctx.emergency_ops_ordered_by_iso["NGA"] = []
        cells = _resolve_emergency_matrix_cells(
            ctx,
            iso3="NGA",
            area="EA2",
            ea_code="MDRNG999",
            excel_name="Nigeria Floods EA",
            amount=1200,
        )
        row_label = "Nigeria Floods EA (MDRNG999)"
        assert cells[f"{row_label}_{EMERGENCY_APPEALS_COLUMN}"] == 1200
        assert cells[f"{ROW_GO_UNMATCHED_PREFIX}{row_label}"] == 1

    def test_omits_row_go_unmatched_when_go_matches(self):
        ctx = UprImportContext(template_ids=[24])
        ctx.emergency_ops_by_iso["NGA"] = {
            "MDRNG041": {"name": "Nigeria - Floods", "code": "MDRNG041"},
        }
        ctx.emergency_ops_ordered_by_iso["NGA"] = [ctx.emergency_ops_by_iso["NGA"]["MDRNG041"]]
        cells = _resolve_emergency_matrix_cells(
            ctx,
            iso3="NGA",
            area="EA1",
            ea_code="MDRNG041",
            excel_name="Excel-only name",
            amount=500,
        )
        row_label = "Nigeria - Floods (MDRNG041)"
        assert cells[f"{row_label}_{EMERGENCY_APPEALS_COLUMN}"] == 500
        assert f"{ROW_GO_UNMATCHED_PREFIX}{row_label}" not in cells


class TestFundingEaColHeaderGoUnmatched:
    def test_sets_col_header_go_unmatched_for_excel_fallback(self):
        ctx = UprImportContext(template_ids=[24])
        ctx.emergency_ops_by_iso["AFG"] = {}
        ctx.emergency_ops_ordered_by_iso["AFG"] = []
        matrix_cells = {}
        aes_id = 99
        funding_item_id = 967
        matrix_cells[(aes_id, funding_item_id)] = {}
        ok = _ensure_funding_ea_col_header(
            matrix_cells,
            ctx,
            aes_id=aes_id,
            funding_item_id=funding_item_id,
            iso3="AFG",
            rnd="MYR26",
            area="EA2",
            ea_code_raw="MDRAF070",
            reach_ea_codes={("AFG", "MYR26", "EA2"): "MDRAF070"},
            excel_name_raw="Afghanistan: Population Movement",
            reach_ea_names={("AFG", "MYR26", "EA2"): "Afghanistan: Population Movement"},
        )
        cells = matrix_cells[(aes_id, funding_item_id)]
        assert ok is True
        assert cells["col_header|EA2"] == "Afghanistan: Population Movement (MDRAF070)"
        assert cells[f"{COL_HEADER_GO_UNMATCHED_PREFIX}EA2"] == 1
