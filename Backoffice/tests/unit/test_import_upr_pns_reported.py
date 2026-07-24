"""Unit tests for UPR import PNS reported gating."""

import json
import sys
from pathlib import Path

scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from datetime import datetime

from import_upr_excel_data import (  # noqa: E402
    ITEM_FUNDING_REQUIREMENTS_T22,
    UprImportContext,
    _apply_pns_pending_reset_fields,
    _build_pns_reported_yes_sets,
    _pns_pending_reset_needs_update,
    _t22_pns_import_cell_value,
    is_planning_funding_requirement_row,
    parse_pns_reported_yes,
    plan_non_reported_pns_aes_by_template,
    plan_pns_assignment_status_updates,
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
        ctx.staff_matrix_item_id = 1367
        ctx.pns_funding_item_id = 952
        ctx.assignment_by_template = {
            22: {("2026", "GBR"): 3221, ("2026", "NLD"): 3208},
            23: {("2026", "NLD"): 5001},
        }
        by_tpl = plan_non_reported_pns_aes_by_template(ctx, [22, 23], periods={"2026"})
        assert by_tpl[22] == {3208}
        assert by_tpl[23] == {5001}
        assert upr_pns_import_item_ids(ctx, 22) == {1303, 1367}
        assert upr_pns_import_item_ids(ctx, 23) == {952}


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
