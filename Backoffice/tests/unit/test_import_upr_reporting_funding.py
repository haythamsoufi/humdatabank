"""Unit tests for UPR import — template 33 item 1403 funding matrix column keys."""

import json
import sys
from pathlib import Path

imports_dir = Path(__file__).resolve().parents[2] / "scripts" / "imports"
if str(imports_dir) not in sys.path:
    sys.path.insert(0, str(imports_dir))

from import_fdrs_form_data import COL_DISAGG, COL_ITEM  # noqa: E402
from import_upr_excel_data import (  # noqa: E402
    ITEM_REPORTING_COUNTRY_FUNDING,
    REPORTING_FUNDING_MATRIX_COLUMN,
    UprImportContext,
    _matrix_column_name_from_form_item,
    is_skipped_legacy_funding_area,
    transform_to_import_rows,
)


def _funding_source_row(**overrides):
    base = {
        "ISO3": "AFG",
        "Round": "MYR26",
        "Section": "Funding",
        "Entity": "IFRC Secretariat",
        "Attribute": "Funding Source",
        "indicatorId": 733,
        "Indicator": "Funding",
        "ValueNum": 815093,
        "Area": "Total",
    }
    base.update(overrides)
    return base


def _planning_funding_row(**overrides):
    base = {
        "ISO3": "AFG",
        "Round": "P23",
        "Section": "Funding",
        "Entity": "IFRC Secretariat",
        "Attribute": "Total",
        "Area": "SP2",
        "Year": 2023,
        "Indicator": "Funding Requirement",
        "indicatorId": 2,
        "Country Value": 5000000,
        "ValueNum": 5000000,
    }
    base.update(overrides)
    return base


class TestT33FundingMatrixColumnKeys:
    def test_funding_source_uses_ctx_funding_col_not_legacy_suffix(self):
        ctx = UprImportContext(template_ids=[33])
        ctx.assignment_by_template = {33: {("Jan-Jun 2026", "AFG"): 5001}}
        ctx.reporting_special_items = {
            33: {
                "funding": ITEM_REPORTING_COUNTRY_FUNDING,
                "funding_col": "ns_fun",
            }
        }
        rows = [_funding_source_row()]
        import_rows = transform_to_import_rows(rows, ctx, template_ids=[33], rounds={"MYR26"})
        funding_rows = [r for r in import_rows if r[COL_ITEM] == str(ITEM_REPORTING_COUNTRY_FUNDING)]
        assert len(funding_rows) == 1
        cells = json.loads(funding_rows[0][COL_DISAGG])
        assert cells == {"IFRC Secretariat_ns_fun": 815093}
        assert "IFRC Secretariat_NS 2025 Total Funding" not in cells
        assert "IFRC Secretariat_tot_fn" not in cells

    def test_matrix_column_fallback_is_ns_fun(self):
        assert REPORTING_FUNDING_MATRIX_COLUMN == "ns_fun"

    def test_matrix_column_name_from_form_item_reads_config_name(self):
        class _Item:
            config = {
                "matrix_config": {
                    "columns": [{"name": "ns_fun", "label": "National Society Total Funding"}],
                }
            }

        assert _matrix_column_name_from_form_item(_Item()) == "ns_fun"


class TestSkippedLegacyFundingAreas:
    def test_legacy_area_detector(self):
        assert is_skipped_legacy_funding_area("EO")
        assert is_skipped_legacy_funding_area("EA1")
        assert not is_skipped_legacy_funding_area("SP2")
        assert not is_skipped_legacy_funding_area("EFs")

    def test_planning_funding_skips_legacy_eo_area(self):
        ctx = UprImportContext(template_ids=[24])
        ctx.assignment_by_template = {24: {("2023", "AFG"): 9001}}
        rows = [_planning_funding_row(Area="EO")]
        import_rows = transform_to_import_rows(rows, ctx, template_ids=[24], rounds={"P23"})
        assert import_rows == []

    def test_planning_funding_imports_sp_breakdown(self):
        ctx = UprImportContext(template_ids=[24])
        ctx.assignment_by_template = {24: {("2023", "AFG"): 9001}}
        rows = [_planning_funding_row(Area="SP2")]
        import_rows = transform_to_import_rows(rows, ctx, template_ids=[24], rounds={"P23"})
        assert len(import_rows) == 1
        cells = json.loads(import_rows[0][COL_DISAGG])
        assert cells == {"IFRC Secretariat_SP2": 5000000}
