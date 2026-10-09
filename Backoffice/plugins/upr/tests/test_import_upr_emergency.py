"""Unit tests for UPR master import emergency appeal mapping."""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_plugin_scripts = _HERE.parents[1] / "scripts"
_core_imports = _HERE.parents[3] / "scripts" / "imports"
for _p in (_plugin_scripts, _core_imports):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

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
        assert display == "MDRNG041 Nigeria - Floods"

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
        assert cell_key == f"MDRNG999 Nigeria Floods EA_{EMERGENCY_APPEALS_COLUMN}"
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
        assert cell_key == f"MDRNG041 Nigeria - Floods_{EMERGENCY_APPEALS_COLUMN}"
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
        row_label = "MDRNG999 Nigeria Floods EA"
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
        row_label = "MDRNG041 Nigeria - Floods"
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
        assert cells["col_header|EA2"] == "MDRAF070 Afghanistan: Population Movement"
        assert cells[f"{COL_HEADER_GO_UNMATCHED_PREFIX}EA2"] == 1


class TestGroupedAppealResolution:
    def _ctx(self):
        ctx = UprImportContext(template_ids=[33])
        ctx.iso2_by_iso3["TCD"] = "TD"
        ctx.country_name_by_iso3["TCD"] = "Chad"
        ctx.assignment_by_template[33] = {("2025", "TCD"): 42}
        ctx.appeal_catalogue_rows = []
        return ctx

    def test_group_code_resolves_to_the_country_child(self):
        ctx = self._ctx()
        child = {
            "name": "Chad - Pop. Movement 2023",
            "code": "MDRTD022",
            "part_of": "MDRS1001",
            "country": {"iso": "TD"},
        }
        ctx.emergency_ops_by_iso["TCD"] = {"MDRTD022": child, "MDRS1001": {"name": "Sudan Crisis", "code": "MDRS1001"}}
        ctx.emergency_ops_ordered_by_iso["TCD"] = [child, ctx.emergency_ops_by_iso["TCD"]["MDRS1001"]]
        name, code, display = _resolve_emergency_operation_labels(
            ctx,
            iso3="TCD",
            excel_name="Sudan Crisis",
            excel_code="MDRS1001",
            aes_id=42,
        )
        assert code == "MDRTD022"
        assert name == "Chad - Pop. Movement 2023"
        assert "part of MDRS1001" in display
        from upr_import_warnings import warning_text

        assert any("was matched to" in warning_text(w) and "Chad (TCD)" in warning_text(w) for w in ctx.warnings)
        assert not any("is not listed for this country in GO" in warning_text(w) for w in ctx.warnings)

    def test_child_code_resolves_to_the_listed_group(self):
        ctx = self._ctx()
        group = {"name": "Sudan Crisis Regional Population Movement", "code": "MDRS1001", "country": {"iso": "AFR"}}
        ctx.emergency_ops_by_iso["TCD"] = {"MDRS1001": group}
        ctx.emergency_ops_ordered_by_iso["TCD"] = [group]
        ctx.appeal_catalogue_rows = [
            {
                "code": "MDRTD099",
                "name": "Chad - old child",
                "part_of": "MDRS1001",
                "country": {"iso": "TD"},
            },
            group,
        ]
        name, code, _display = _resolve_emergency_operation_labels(
            ctx,
            iso3="TCD",
            excel_name="old",
            excel_code="MDRTD099",
            aes_id=42,
        )
        assert code == "MDRS1001"
        assert name == "Sudan Crisis Regional Population Movement"

    def test_child_code_resolves_to_the_country_sibling(self):
        ctx = self._ctx()
        child = {
            "name": "Chad - Pop. Movement 2023",
            "code": "MDRTD022",
            "part_of": "MDRS1001",
            "country": {"iso": "TD"},
        }
        ctx.emergency_ops_by_iso["TCD"] = {"MDRTD022": child}
        ctx.emergency_ops_ordered_by_iso["TCD"] = [child]
        ctx.appeal_catalogue_rows = [
            child,
            {
                "code": "MDRTD099",
                "name": "Chad - old code",
                "part_of": "MDRS1001",
                "country": {"iso": "TD"},
            },
            {
                "code": "MDRET030",
                "name": "Ethiopia - Population Movement",
                "part_of": "MDRS1001",
                "country": {"iso": "ET"},
            },
        ]
        _name, code, _display = _resolve_emergency_operation_labels(
            ctx,
            iso3="TCD",
            excel_name="old",
            excel_code="MDRTD099",
        )
        assert code == "MDRTD022"

    def test_unmatched_warning_names_country_and_assignment(self):
        ctx = self._ctx()
        ctx.emergency_ops_by_iso["TCD"] = {}
        ctx.emergency_ops_ordered_by_iso["TCD"] = []
        _resolve_emergency_operation_labels(
            ctx,
            iso3="TCD",
            excel_name="Missing",
            excel_code="MDRTD999",
            aes_id=42,
        )
        from upr_import_warnings import warning_text

        text = warning_text(ctx.warnings[0])
        assert "MDRTD999" in text
        assert "Chad (TCD)" in text
        assert "Reporting - Country" in text
        assert "assignment 42" in text
        assert ctx.warnings[0]["place"].startswith("Chad (TCD)")

    def test_ambiguous_children_are_listed_instead_of_guessed(self):
        ctx = self._ctx()
        first = {"name": "Chad floods", "code": "MDRTD024", "part_of": "MDRGRP01", "country": {"iso": "TD"}}
        second = {"name": "Chad cholera", "code": "MDRTD030", "part_of": "MDRGRP01", "country": {"iso": "TD"}}
        ctx.emergency_ops_by_iso["TCD"] = {"MDRTD024": first, "MDRTD030": second}
        ctx.emergency_ops_ordered_by_iso["TCD"] = [first, second]
        _name, code, _display = _resolve_emergency_operation_labels(
            ctx,
            iso3="TCD",
            excel_name="Group",
            excel_code="MDRGRP01",
        )
        assert code == "MDRGRP01"
        from upr_import_warnings import warning_text

        text = warning_text(ctx.warnings[0])
        assert "MDRTD024" in text
        assert "MDRTD030" in text

    def test_ensure_emergency_ops_queries_iso2_before_iso3(self, monkeypatch):
        import import_upr_excel_data as mod

        ctx = UprImportContext(template_ids=[24])
        ctx.iso2_by_iso3["TCD"] = "TD"
        seen = []

        def fake(iso, _cfg):
            seen.append(iso)
            if iso == "TD":
                op = {"code": "MDRTD022", "name": "Chad - Pop. Movement 2023", "part_of": "MDRS1001"}
                return [op], {"MDRTD022": op}
            return [], {}

        monkeypatch.setattr(mod, "_fetch_emergency_ops_for_country", fake)
        _ordered, by_code = mod._ensure_emergency_ops(ctx, "tcd")
        assert seen == ["TD", "TCD"]
        assert by_code["MDRTD022"]["name"] == "Chad - Pop. Movement 2023"
