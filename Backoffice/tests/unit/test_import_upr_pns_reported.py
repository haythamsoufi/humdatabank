"""Unit tests for UPR import PNS reported gating."""

import json
import sys
from pathlib import Path

imports_dir = Path(__file__).resolve().parents[2] / "scripts" / "imports"
if str(imports_dir) not in sys.path:
    sys.path.insert(0, str(imports_dir))

from datetime import datetime

from import_upr_excel_data import (  # noqa: E402
    ITEM_FUNDING_REQUIREMENTS_T22,
    UprImportContext,
    _apply_pns_pending_reset_fields,
    _build_pns_reported_yes_sets,
    _pns_pending_reset_needs_update,
    _t22_pns_import_cell_value,
    canonical_upr_period,
    is_planning_funding_requirement_row,
    is_pns_data_source,
    parse_pns_reported_yes,
    plan_non_reported_pns_aes_by_template,
    plan_pns_assignment_status_updates,
    t23_matrix_has_funding_columns,
    transform_to_import_rows,
    upr_pns_import_item_ids,
)
from app.models.enums import AssignmentEntityStatusValue  # noqa: E402


def _funding_row(**overrides):
    base = {
        "ISO3": "BFA",
        "Round": "P26",
        "Section": "Funding",
        "Entity": "PNS",
        "NS": "British Red Cross",
        "Area": "Total",
        "Year": 2026,
        "Indicator": "Funding Requirement",
        "indicatorId": 2,
        "Country Value": None,
        "PNS Value": 242030,
        "PNS reported": "Yes",
        "ValueNum": 242030,
    }
    base.update(overrides)
    return base


class TestParsePnsReportedYes:
    def test_yes_values(self):
        assert parse_pns_reported_yes({"PNS reported": "Yes"}) is True
        assert parse_pns_reported_yes({"PNS reported": "yes"}) is True
        assert parse_pns_reported_yes({"PNS reported": "Y"}) is True

    def test_non_yes_values(self):
        assert parse_pns_reported_yes({"PNS reported": "No"}) is False
        assert parse_pns_reported_yes({"PNS reported": ""}) is False
        assert parse_pns_reported_yes({}) is False


class TestBuildPnsReportedYesSets:
    def test_collects_t22_pair_when_reported_yes(self):
        ctx = UprImportContext(template_ids=[22])
        ctx.ns_home_country_iso3 = {"british red cross": "GBR"}
        ctx.assignment_by_template = {22: {("2026", "GBR"): 3221}}
        rows = [_funding_row()]
        t22_yes, t23_yes = _build_pns_reported_yes_sets(rows, ctx, [22])
        assert t22_yes == {(3221, "BFA")}
        assert t23_yes == set()

    def test_skips_when_not_reported(self):
        ctx = UprImportContext(template_ids=[22])
        ctx.ns_home_country_iso3 = {"british red cross": "GBR"}
        ctx.assignment_by_template = {22: {("2026", "GBR"): 3221}}
        rows = [_funding_row(**{"PNS reported": "No"})]
        t22_yes, _ = _build_pns_reported_yes_sets(rows, ctx, [22])
        assert t22_yes == set()


class TestTransformT22PnsReportedGate:
    def test_imports_total_when_pns_reported_yes(self):
        ctx = UprImportContext(template_ids=[24, 22])
        ctx.ns_home_country_iso3 = {"british red cross": "GBR"}
        ctx.country_id_by_iso3 = {"BFA": 34}
        ctx.assignment_by_template = {22: {("2026", "GBR"): 3221}, 24: {("2026", "BFA"): 9999}}
        rows = [_funding_row()]
        import_rows = transform_to_import_rows(rows, ctx, template_ids=[24, 22], rounds={"P26"})
        item_rows = [r for r in import_rows if r["item_id"] == str(ITEM_FUNDING_REQUIREMENTS_T22)]
        assert len(item_rows) == 1
        cells = json.loads(item_rows[0]["disagg_data"])
        assert cells["34_Total"] == 242030

    def test_skips_t22_when_pns_not_reported(self):
        ctx = UprImportContext(template_ids=[24, 22])
        ctx.ns_home_country_iso3 = {"netherlands red cross": "NLD"}
        ctx.country_id_by_iso3 = {"UGA": 184}
        ctx.assignment_by_template = {22: {("2026", "NLD"): 3208}, 24: {("2026", "UGA"): 8888}}
        rows = [
            _funding_row(
                ISO3="UGA",
                NS="Netherlands Red Cross",
                Area="SP2",
                **{
                    "Country Value": 616508,
                    "PNS Value": None,
                    "PNS reported": "No",
                },
                ValueNum=616508,
            )
        ]
        import_rows = transform_to_import_rows(rows, ctx, template_ids=[24, 22], rounds={"P26"})
        item_rows = [r for r in import_rows if r["item_id"] == str(ITEM_FUNDING_REQUIREMENTS_T22)]
        assert item_rows == []


class TestConfirmedFundingSkipped:
    def test_is_planning_funding_requirement_row_rejects_confirmed_funding(self):
        assert is_planning_funding_requirement_row(
            {"Indicator": "Confirmed Funding", "indicatorId": "", "PNS Value": 850000}
        ) is False

    def test_confirmed_funding_does_not_overwrite_funding_requirement_total(self):
        ctx = UprImportContext(template_ids=[24, 22])
        ctx.ns_home_country_iso3 = {"finnish red cross": "FIN"}
        ctx.country_id_by_iso3 = {"BDI": 27}
        ctx.assignment_by_template = {22: {("2026", "FIN"): 3206}, 24: {("2026", "BDI"): 8888}}
        rows = [
            _funding_row(
                ISO3="BDI",
                NS="Finnish Red Cross",
                Area="Total",
                **{
                    "Country Value": 229936,
                    "PNS Value": 1350000,
                    "PNS reported": "Yes",
                },
                ValueNum=1350000,
            ),
            _funding_row(
                ISO3="BDI",
                NS="Finnish Red Cross",
                Area="Total",
                Indicator="Confirmed Funding",
                indicatorId="",
                **{
                    "Country Value": None,
                    "PNS Value": 850000,
                    "PNS reported": "Yes",
                },
                ValueNum=850000,
            ),
        ]
        import_rows = transform_to_import_rows(rows, ctx, template_ids=[24, 22], rounds={"P26"})
        item_rows = [r for r in import_rows if r["item_id"] == str(ITEM_FUNDING_REQUIREMENTS_T22)]
        assert len(item_rows) == 1
        cells = json.loads(item_rows[0]["disagg_data"])
        assert cells["27_Total"] == 1350000


class TestT22PnsValueOnlyWhenReported:
    def test_jordan_cleared_when_pns_value_blank(self):
        ctx = UprImportContext(template_ids=[24, 22])
        ctx.ns_home_country_iso3 = {"british red cross": "GBR"}
        ctx.country_id_by_iso3 = {"JOR": 99, "BFA": 34}
        ctx.assignment_by_template = {22: {("2026", "GBR"): 3221}, 24: {("2026", "JOR"): 8888}}
        rows = [
            _funding_row(
                ISO3="JOR",
                NS="British Red Cross",
                Area="Total",
                **{
                    "Country Value": 50000,
                    "PNS Value": None,
                    "PNS reported": "Yes",
                },
                ValueNum=50000,
            )
        ]
        import_rows = transform_to_import_rows(rows, ctx, template_ids=[24, 22], rounds={"P26"})
        item_rows = [r for r in import_rows if r["item_id"] == str(ITEM_FUNDING_REQUIREMENTS_T22)]
        assert len(item_rows) == 1
        cells = json.loads(item_rows[0]["disagg_data"])
        assert cells["99_Total"] == {
            "original": 50000.0,
            "modified": "",
            "isModified": True,
        }


class TestPlanPnsAssignmentStatusUpdates:
    def test_pending_for_non_reported_t22_in_import_period(self):
        ctx = UprImportContext(template_ids=[22])
        ctx.pns_t22_reported_aes = {3221}
        ctx.assignment_by_template = {
            22: {
                ("2026", "GBR"): 3221,
                ("2026", "NLD"): 3208,
                ("2025", "NLD"): 9999,
            }
        }
        plan = plan_pns_assignment_status_updates(ctx, [22], periods={"2026"})
        assert {row["assignment_entity_status_id"] for row in plan} == {3208}
        assert all(row["status"] == "pending" for row in plan)

    def test_skips_reported_pns_assignment(self):
        ctx = UprImportContext(template_ids=[22])
        ctx.pns_t22_reported_aes = {3221}
        ctx.assignment_by_template = {22: {("2026", "GBR"): 3221}}
        plan = plan_pns_assignment_status_updates(ctx, [22], periods={"2026"})
        assert plan == []


class TestNonReportedPnsPlanning:
    def test_aes_by_template_and_item_ids(self):
        ctx = UprImportContext(template_ids=[22, 23])
        ctx.pns_t22_reported_aes = {3221}
        ctx.pns_t23_reported_aes = set()
        ctx.staff_matrix_item_id = 1314
        ctx.t22_funding_item_id = 1303
        ctx.pns_funding_item_id = 1433
        ctx.assignment_by_template = {
            22: {("2026", "GBR"): 3221, ("2026", "NLD"): 3208},
            23: {("2026", "NLD"): 5001},
        }
        by_tpl = plan_non_reported_pns_aes_by_template(ctx, [22, 23], periods={"2026"})
        assert by_tpl[22] == {3208}
        assert by_tpl[23] == {5001}
        assert upr_pns_import_item_ids(ctx, 22) == {1303, 1314}
        assert upr_pns_import_item_ids(ctx, 23) == {1433}


class TestPnsPendingResetMetadata:
    def test_needs_update_when_already_pending_but_wrong_timestamp(self):
        assigned_at = datetime(2026, 1, 15, 10, 0, 0)

        class _Aes:
            status = AssignmentEntityStatusValue.pending
            status_timestamp = datetime(2026, 6, 1, 12, 0, 0)
            submitted_at = None
            submitted_by_user_id = None
            approved_by_user_id = None
            sent_for_review_by_user_id = None
            sent_for_review_at = None

        assert _pns_pending_reset_needs_update(_Aes(), assigned_at=assigned_at) is True

    def test_apply_sets_assignment_date_and_clears_submission_metadata(self):
        assigned_at = datetime(2026, 1, 15, 10, 0, 0)

        class _Aes:
            status = AssignmentEntityStatusValue.in_progress
            status_timestamp = datetime(2026, 6, 1, 12, 0, 0)
            submitted_at = datetime(2026, 5, 1, 9, 0, 0)
            submitted_by_user_id = 42
            approved_by_user_id = 7
            sent_for_review_by_user_id = 3
            sent_for_review_at = datetime(2026, 4, 1, 8, 0, 0)

        aes = _Aes()
        _apply_pns_pending_reset_fields(aes, assigned_at=assigned_at)
        assert aes.status == AssignmentEntityStatusValue.pending
        assert aes.status_timestamp == assigned_at
        assert aes.submitted_at is None
        assert aes.submitted_by_user_id is None
        assert aes.approved_by_user_id is None
        assert aes.sent_for_review_by_user_id is None
        assert aes.sent_for_review_at is None


def _ar25_pns_funding_row(**overrides):
    base = {
        "ISO3": "BFA",
        "Round": "AR25",
        "Section": "Funding",
        "Entity": "PNS",
        "NS": "British Red Cross",
        "Area": "Total",
        "Year": 2025,
        "Indicator": "Funding",
        "indicatorId": 733,
        "ValueNum": 100000,
        "Source": "PNS Data",
        "PNS reported": "",
        "Attribute": "Funding Source",
    }
    base.update(overrides)
    return base


class TestCanonicalUprPeriod:
    def test_ar_and_annual_aliases(self):
        assert canonical_upr_period("AR25") == "2025"
        assert canonical_upr_period("2025") == "2025"
        assert canonical_upr_period("2025 Annual") == "2025"
        assert canonical_upr_period("Annual 2025") == "2025"

    def test_midyear_aliases(self):
        assert canonical_upr_period("MYR26") == "Jan-Jun 2026"
        assert canonical_upr_period("Jan-Jun 2026") == "Jan-Jun 2026"
        assert canonical_upr_period("2026 Midyear") == "Jan-Jun 2026"


class TestT23ReportingPnsDataSource:
    def _ctx(self, period_key="2025"):
        ctx = UprImportContext(template_ids=[23])
        ctx.ns_home_country_iso3 = {"british red cross": "GBR"}
        ctx.iso3_to_hns_id = {"BFA": 77}
        ctx.assignment_by_template = {23: {(period_key, "GBR"): 4001}}
        ctx.pns_funding_item_id = 1433
        return ctx

    def test_is_pns_data_source(self):
        assert is_pns_data_source({"Source": "PNS Data"}) is True
        assert is_pns_data_source({"Source": "Country Data"}) is False
        assert is_pns_data_source({}) is False

    def test_collects_t23_from_source_not_pns_reported_column(self):
        ctx = self._ctx()
        t22_yes, t23_yes = _build_pns_reported_yes_sets(
            [_ar25_pns_funding_row()], ctx, [23], rounds={"AR25"}
        )
        assert t22_yes == set()
        assert t23_yes == {(4001, "BFA")}

    def test_does_not_collect_country_data_even_if_pns_reported_yes(self):
        ctx = self._ctx()
        t22_yes, t23_yes = _build_pns_reported_yes_sets(
            [_ar25_pns_funding_row(Source="Country Data", **{"PNS reported": "Yes"})],
            ctx,
            [23],
            rounds={"AR25"},
        )
        assert t23_yes == set()

    def test_imports_valuenum_when_source_pns_data(self):
        ctx = self._ctx()
        import_rows = transform_to_import_rows(
            [_ar25_pns_funding_row()], ctx, template_ids=[23], rounds={"AR25"}
        )
        item_rows = [r for r in import_rows if r["item_id"] == "1433"]
        assert len(item_rows) == 1
        cells = json.loads(item_rows[0]["disagg_data"])
        assert cells["77_Total Funding"] == 100000

    def test_skips_country_data_source(self):
        ctx = self._ctx()
        import_rows = transform_to_import_rows(
            [_ar25_pns_funding_row(Source="Country Data", ValueNum=100000, **{"PNS reported": "Yes"})],
            ctx,
            template_ids=[23],
            rounds={"AR25"},
        )
        item_rows = [r for r in import_rows if r["item_id"] == "1433"]
        assert item_rows == []

    def test_skips_when_published_matrix_unresolved(self):
        ctx = self._ctx()
        ctx.pns_funding_item_id = 0
        import_rows = transform_to_import_rows(
            [_ar25_pns_funding_row()], ctx, template_ids=[23], rounds={"AR25"}
        )
        assert import_rows == []
        assert any("published PNS funding matrix was not resolved" in w for w in ctx.warnings)

    def test_matches_assignment_named_2025_annual(self):
        ctx = self._ctx(period_key="2025 Annual")
        import_rows = transform_to_import_rows(
            [_ar25_pns_funding_row()], ctx, template_ids=[23], rounds={"AR25"}
        )
        item_rows = [r for r in import_rows if r["item_id"] == "1433"]
        assert len(item_rows) == 1

    def test_warns_when_t23_assignment_missing(self):
        ctx = self._ctx()
        ctx.assignment_by_template = {23: {}}
        transform_to_import_rows(
            [_ar25_pns_funding_row()], ctx, template_ids=[23], rounds={"AR25"}
        )
        assert any("No template 23 assignment" in w for w in ctx.warnings)


class TestT23FundingMatrixColumns:
    def test_matches_untitled_published_matrix(self):
        item = type(
            "Item",
            (),
            {
                "config": {
                    "matrix_config": {
                        "columns": [
                            {"name": "Funding Requirement"},
                            {"name": "Total Funding"},
                            {"name": "Total Expenditure"},
                            {"name": "Total Transferred to HNS"},
                        ]
                    }
                }
            },
        )()
        assert t23_matrix_has_funding_columns(item) is True

    def test_rejects_staff_matrix(self):
        item = type(
            "Item",
            (),
            {
                "config": {
                    "matrix_config": {
                        "columns": [{"name": "intl_delegates_hns"}]
                    }
                }
            },
        )()
        assert t23_matrix_has_funding_columns(item) is False


