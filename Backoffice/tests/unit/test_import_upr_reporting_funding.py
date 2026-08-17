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
    PLANNING_EA_FUNDING_AREAS,
    REPORTING_FUNDING_MATRIX_COLUMN,
    UprImportContext,
    _clear_matrix_key_schema_cache,
    _ensure_funding_ea_col_header,
    _matrix_column_name_from_form_item,
    _matrix_key_schema,
    _matrix_key_warning,
    is_skipped_legacy_funding_area,
    transform_to_import_rows,
)
from upr_import_warnings import warning_text  # noqa: E402


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
        assert not is_skipped_legacy_funding_area("EA1")
        assert not is_skipped_legacy_funding_area("SP2")
        assert not is_skipped_legacy_funding_area("EFs")
        assert "EA1" in PLANNING_EA_FUNDING_AREAS

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

    def test_planning_funding_imports_ea1_with_reach_ea_code_and_col_header(self):
        ctx = UprImportContext(template_ids=[24])
        ctx.assignment_by_template = {24: {("2026", "AFG"): 9001}}
        ctx.emergency_ops_by_iso["AFG"] = {
            "MDRAF018": {
                "name": "Afghanistan - Earthquake",
                "code": "MDRAF018",
            }
        }
        ctx.emergency_ops_ordered_by_iso["AFG"] = [ctx.emergency_ops_by_iso["AFG"]["MDRAF018"]]
        rows = [
            {
                "ISO3": "AFG",
                "Round": "P26",
                "Section": "Reach",
                "Area": "EA1",
                "Indicator": "People to be reached",
                "ValueNum": 875000,
                "EA Code": "MDRAF018",
            },
            _planning_funding_row(
                Round="P26",
                Year=2026,
                Area="EA1",
                **{"Country Value": 12000000},
            ),
        ]
        import_rows = transform_to_import_rows(rows, ctx, template_ids=[24], rounds={"P26"})
        funding_rows = [r for r in import_rows if r[COL_ITEM] == "967"]
        assert len(funding_rows) == 1
        cells = json.loads(funding_rows[0][COL_DISAGG])
        assert cells["IFRC Secretariat_EA1"] == 12000000
        assert cells["col_header|EA1"] == "Afghanistan - Earthquake (MDRAF018)"


class TestMatrixKeyWarning:
    """_matrix_key_warning/_matrix_key_schema: catch a form admin renaming a matrix
    column/manual row after the SP-breakdown/support/funding key constants were
    written, so values don't get silently stored under a key the UI never reads."""

    def teardown_method(self):
        _clear_matrix_key_schema_cache()

    def test_none_when_schema_unavailable(self):
        # No app/DB context and an id that was never cached -> "can't verify", not a warning.
        _clear_matrix_key_schema_cache()
        assert _matrix_key_warning(item_id=987654321, cell_key="row_col", column_name="col") is None

    def test_flags_unknown_column(self, monkeypatch):
        from import_upr_excel_data import _MATRIX_KEY_SCHEMA_CACHE

        monkeypatch.setitem(_MATRIX_KEY_SCHEMA_CACHE, 4242, {"columns": {"ns_fun"}, "rows": None})
        warning = _matrix_key_warning(
            item_id=4242, cell_key="IFRC Secretariat_tot_fn", column_name="tot_fn",
        )
        assert warning is not None
        text = warning_text(warning)
        assert "tot_fn" in text
        assert warning.get("item_id") == 4242

    def test_flags_unknown_manual_row(self, monkeypatch):
        from import_upr_excel_data import _MATRIX_KEY_SCHEMA_CACHE

        monkeypatch.setitem(
            _MATRIX_KEY_SCHEMA_CACHE,
            4243,
            {"columns": {"Funding (CHF)"}, "rows": {"Resilience - Climate and environment"}},
        )
        warning = _matrix_key_warning(
            item_id=4243,
            cell_key="Bogus Row_Funding (CHF)",
            column_name="Funding (CHF)",
            row_name="Bogus Row",
        )
        assert warning is not None
        assert "Bogus Row" in warning_text(warning)

    def test_silent_when_column_and_row_match(self, monkeypatch):
        from import_upr_excel_data import _MATRIX_KEY_SCHEMA_CACHE

        monkeypatch.setitem(
            _MATRIX_KEY_SCHEMA_CACHE,
            4244,
            {"columns": {"Funding (CHF)"}, "rows": {"Resilience - Climate and environment"}},
        )
        warning = _matrix_key_warning(
            item_id=4244,
            cell_key="Resilience - Climate and environment_Funding (CHF)",
            column_name="Funding (CHF)",
            row_name="Resilience - Climate and environment",
        )
        assert warning is None

    def test_skips_row_check_when_rows_come_from_a_lookup_list(self, monkeypatch):
        """row_mode != 'manual' (e.g. Support's national-society rows) -> rows is None
        in the cached schema, meaning "don't try to validate row identity here"."""
        from import_upr_excel_data import _MATRIX_KEY_SCHEMA_CACHE

        monkeypatch.setitem(_MATRIX_KEY_SCHEMA_CACHE, 4245, {"columns": {"SP1 Supported"}, "rows": None})
        warning = _matrix_key_warning(
            item_id=4245,
            cell_key="912_SP1 Supported",
            column_name="SP1 Supported",
            row_name="912",  # an NS row id that's obviously not a manual row label
        )
        assert warning is None

    def test_schema_reads_manual_columns_and_rows_from_live_form_item(self, app, db_session):
        from app.models.form_items import FormItem
        from tests.factories import create_test_section, create_test_template

        with app.app_context():
            _clear_matrix_key_schema_cache()
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item = FormItem(
                section_id=section.id,
                template_id=template.id,
                version_id=section.version_id,
                item_type="matrix",
                label="Test SP Breakdown Matrix",
                order=1,
                config={
                    "matrix_config": {
                        "row_mode": "manual",
                        "columns": [{"name": "Funding (CHF)"}, {"name": "Expenditure (CHF)"}],
                        "rows": [{"text": "Resilience - Climate and environment"}, {"text": "Enabling functions"}],
                    }
                },
            )
            db_session.add(item)
            db_session.commit()

            schema = _matrix_key_schema(item.id)
            assert schema["columns"] == {"Funding (CHF)", "Expenditure (CHF)"}
            assert schema["rows"] == {"Resilience - Climate and environment", "Enabling functions"}
            assert schema["label"] == "Test SP Breakdown Matrix"

    def test_schema_has_no_row_set_for_list_library_row_mode(self, app, db_session):
        from app.models.form_items import FormItem
        from tests.factories import create_test_section, create_test_template

        with app.app_context():
            _clear_matrix_key_schema_cache()
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item = FormItem(
                section_id=section.id,
                template_id=template.id,
                version_id=section.version_id,
                item_type="matrix",
                label="Test Support Matrix",
                order=1,
                config={
                    "matrix_config": {
                        "row_mode": "list_library",
                        "lookup_list_id": 1,
                        "columns": [{"name": "SP1 Supported"}, {"name": "SP2 Supported"}],
                    }
                },
            )
            db_session.add(item)
            db_session.commit()

            schema = _matrix_key_schema(item.id)
            assert schema["columns"] == {"SP1 Supported", "SP2 Supported"}
            assert schema["rows"] is None

    def test_transform_warns_when_sp_breakdown_column_was_renamed_in_form_builder(self, app, db_session):
        """End-to-end: transform_to_import_rows must still store the SP-breakdown value
        (never silently drop it), but must also warn that the hardcoded 'Funding (CHF)'
        column name no longer matches the live matrix, so a reviewer can catch it."""
        from app.models.form_items import FormItem
        from tests.factories import create_test_section, create_test_template

        with app.app_context():
            _clear_matrix_key_schema_cache()
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item = FormItem(
                section_id=section.id,
                template_id=template.id,
                version_id=section.version_id,
                item_type="matrix",
                label="Test SP Breakdown Matrix (renamed column)",
                order=1,
                config={
                    "matrix_config": {
                        "row_mode": "manual",
                        # Deliberately does NOT include "Funding (CHF)" -- simulates a
                        # form admin renaming the column after this script was written.
                        "columns": [{"name": "Funding Amount (CHF)"}],
                        "rows": [{"text": "Response - Disasters and crises"}],
                    }
                },
            )
            db_session.add(item)
            db_session.commit()

            ctx = UprImportContext(template_ids=[33])
            ctx.assignment_by_template = {33: {("Jan-Jun 2026", "AFG"): 5001}}
            ctx.reporting_special_items = {33: {"sp_breakdown": item.id}}
            rows = [{
                "ISO3": "AFG",
                "Round": "MYR26",
                "Section": "Funding",
                "Entity": "HNS",
                "Attribute": "SP Breakdown",
                "indicatorId": 733,
                "Indicator": "Funding",
                "ValueNum": 12345,
                "Area": "SP2",
            }]
            import_rows = transform_to_import_rows(rows, ctx, template_ids=[33], rounds={"MYR26"})

            sp_rows = [r for r in import_rows if r[COL_ITEM] == str(item.id)]
            assert len(sp_rows) == 1
            cells = json.loads(sp_rows[0][COL_DISAGG])
            # Value is still stored (never silently dropped)...
            assert cells == {"Response - Disasters and crises_Funding (CHF)": 12345}
            # ...but the mismatch is now visible instead of silent.
            assert any(
                "Funding (CHF)" in warning_text(w) and "does not match a column" in warning_text(w)
                for w in ctx.warnings
            ), f"Expected a matrix column mismatch warning; got: {ctx.warnings}"

    def test_schema_reads_plain_string_rows(self, app, db_session):
        """Published T33 matrices store rows as strings, not {text: ...} objects."""
        from app.models.form_items import FormItem
        from tests.factories import create_test_section, create_test_template

        with app.app_context():
            _clear_matrix_key_schema_cache()
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item = FormItem(
                section_id=section.id,
                template_id=template.id,
                version_id=section.version_id,
                item_type="matrix",
                label="Optional breakdown by SP/EF (CHF)",
                order=1,
                config={
                    "matrix_config": {
                        "row_mode": "manual",
                        "columns": [{"name": "Funding (CHF)"}, {"name": "Expenditure (CHF)"}],
                        "rows": [
                            "Response - Disasters and crises",
                            "Resilience - Climate and environment",
                            "Enabling functions",
                        ],
                    }
                },
            )
            db_session.add(item)
            db_session.commit()

            schema = _matrix_key_schema(item.id)
            assert schema["rows"] == {
                "Response - Disasters and crises",
                "Resilience - Climate and environment",
                "Enabling functions",
            }
            assert _matrix_key_warning(
                item_id=item.id,
                cell_key="Resilience - Climate and environment_Funding (CHF)",
                column_name="Funding (CHF)",
                row_name="Resilience - Climate and environment",
            ) is None
            # Case-only differences must not warn (Excel labels use "Crises").
            assert _matrix_key_warning(
                item_id=item.id,
                cell_key="Response - Disasters and Crises_Funding (CHF)",
                column_name="Funding (CHF)",
                row_name="Response - Disasters and Crises",
            ) is None
