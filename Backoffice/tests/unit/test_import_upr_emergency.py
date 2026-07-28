"""Unit tests for UPR master import emergency appeal mapping."""

import sys
from pathlib import Path

imports_dir = Path(__file__).resolve().parents[2] / "scripts" / "imports"
if str(imports_dir) not in sys.path:
    sys.path.insert(0, str(imports_dir))

from import_upr_excel_data import (  # noqa: E402
    UprImportContext,
    _format_emergency_operation_display,
    _parse_ns_emergency_slot_field,
    _parse_row_text_value,
    _resolve_emergency_operation_labels,
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
        assert any("not found in GO API" in w for w in ctx.warnings)
