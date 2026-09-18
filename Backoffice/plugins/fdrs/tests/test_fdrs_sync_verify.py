"""Unit tests for FDRS API vs Backoffice form_data verification."""
from __future__ import annotations

import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
backoffice_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
imports_dir = os.path.join(backoffice_dir, "scripts", "imports")
fdrs_scripts = os.path.join(backoffice_dir, "plugins", "fdrs", "scripts")
for p in (backoffice_dir, fdrs_scripts, imports_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

from fdrs_sync_constants import FDRS_INCOME_SOURCES_MATRIX_ITEM_ID  # noqa: E402
from fdrs_sync_verify import (  # noqa: E402
    STATUS_MATCHED,
    STATUS_MISSING,
    STATUS_MISMATCH,
    STATUS_SKIPPED,
    DatabankValue,
    FdrsDataPoint,
    apply_mapping_skips,
    attach_classification,
    attach_databank_values,
    classify_point,
    group_snapshot_to_points,
    kpi_kind,
    values_equal,
)


def test_values_equal_rounds_like_importer():
    assert values_equal("1500", 1500)
    assert values_equal("1,234", 1234)
    assert values_equal("10.4", 10)
    assert values_equal("10.5", 11)
    assert values_equal("Male", "male")
    assert not values_equal("1500", 1499)
    assert values_equal("", None)
    assert not values_equal("1", None)


def test_kpi_kind():
    assert kpi_kind("KPI_PeopleVol") == "indicator"
    assert kpi_kind("KPI_pr_sex") == "question"
    assert kpi_kind("h_gov_CHF") == "income_matrix"
    assert kpi_kind("supported3") == "network_support"
    assert kpi_kind("supported3_amount") == "network_support"
    assert kpi_kind("received_support1") == "network_support"
    assert kpi_kind("KPI_NSGS_WasSubmitted") == "workflow"
    assert kpi_kind("KPI_NSGS") == "workflow"


def _snapshot_row(**kwargs):
    row = {
        "ISO3": "KEN",
        "DonCode": "DKEN001",
        "year": "2024",
        "KPI_code": "KPI_PeopleVol_Tot",
        "BaseKPI": "KPI_PeopleVol",
        "Value": "1500",
        "ReportedValue": "1500",
        "ImputedValue": "",
        "ValueStatus": "Published Reported",
        "State": 500,
        "in_fdrs_data_stage": "yes",
        "fdrs_data_filter_reason": "",
    }
    row.update(kwargs)
    return row


def test_group_snapshot_picks_tot_not_sex_breakdown():
    points = group_snapshot_to_points(
        [
            _snapshot_row(KPI_code="KPI_PeopleVol_Tot_M", Value="900"),
            _snapshot_row(KPI_code="KPI_PeopleVol_Tot", Value="1500"),
            _snapshot_row(KPI_code="KPI_PeopleVol_Tot_F", Value="600"),
        ]
    )
    assert len(points) == 1
    point = points[0]
    assert point.base_kpi == "KPI_PeopleVol"
    assert point.kpi_code_used == "KPI_PeopleVol_Tot"
    assert str(point.fdrs_value) == "1500"
    assert point.skip_reason is None


def test_zero_value_is_intentional_skip():
    points = group_snapshot_to_points([_snapshot_row(Value="0")])
    assert points[0].skip_reason == "main_value_empty_or_zero"
    attach_classification(points)
    assert points[0].status == STATUS_SKIPPED


def test_workflow_and_network_slots_are_intentional_skips():
    points = group_snapshot_to_points(
        [
            _snapshot_row(
                KPI_code="KPI_NSGS_WasSubmitted",
                BaseKPI="KPI_NSGS",
                Value="true",
            ),
            _snapshot_row(
                KPI_code="supported1",
                BaseKPI="supported1",
                Value="DAFG001,DBGD001",
            ),
        ]
    )
    by_kpi = {p.base_kpi: p for p in points}
    assert by_kpi["KPI_NSGS"].skip_reason == "assignment_workflow"
    assert by_kpi["supported1"].skip_reason == "network_support_slot"
    attach_classification(points)
    assert all(p.status == STATUS_SKIPPED for p in points)


def test_filtered_unpublished_row_is_skipped():
    points = group_snapshot_to_points(
        [
            _snapshot_row(
                Value=None,
                ValueStatus="Unpublished Reported",
                State=0,
                in_fdrs_data_stage="no",
                fdrs_data_filter_reason="null_or_empty_value",
            )
        ]
    )
    assert points[0].skip_reason == "unpublished_or_not_filled"


def test_classify_matched_missing_mismatch():
    matched = FdrsDataPoint(
        year="2024",
        iso3="KEN",
        don_code="DKEN001",
        base_kpi="KPI_PeopleVol",
        fdrs_value="1500",
        item_id=1,
        aes_id=10,
        databank=DatabankValue(value="1500", numeric_value=1500.0),
    )
    assert classify_point(matched) == (STATUS_MATCHED, "value")

    missing = FdrsDataPoint(
        year="2024",
        iso3="KEN",
        don_code="DKEN001",
        base_kpi="KPI_PeopleVol",
        fdrs_value="1500",
        item_id=1,
        aes_id=10,
        databank=None,
    )
    assert classify_point(missing) == (STATUS_MISSING, "value_not_in_databank")

    mismatch = FdrsDataPoint(
        year="2024",
        iso3="KEN",
        don_code="DKEN001",
        base_kpi="KPI_PeopleVol",
        fdrs_value="1500",
        item_id=1,
        aes_id=10,
        databank=DatabankValue(value="1400", numeric_value=1400.0),
    )
    assert classify_point(mismatch) == (STATUS_MISMATCH, "value_differs")


def test_classify_income_matrix_cell():
    point = FdrsDataPoint(
        year="2024",
        iso3="KEN",
        don_code="DKEN001",
        base_kpi="h_gov_CHF",
        kind="income_matrix",
        fdrs_value="1000",
        item_id=FDRS_INCOME_SOURCES_MATRIX_ITEM_ID,
        aes_id=10,
        matrix_cell="Home Government_Funding",
        databank=DatabankValue(
            value=None,
            disagg_data={"Home Government_Funding": 1000},
            disagg_type="matrix",
        ),
    )
    assert classify_point(point) == (STATUS_MATCHED, "value")
    point.databank = DatabankValue(disagg_data={"Home Government_Funding": 50}, disagg_type="matrix")
    assert classify_point(point) == (STATUS_MISMATCH, "value_differs")


def test_classify_availability_flags():
    point = FdrsDataPoint(
        year="2024",
        iso3="KEN",
        don_code="DKEN001",
        base_kpi="KPI_PeopleVol",
        data_not_available=True,
        item_id=1,
        aes_id=10,
        databank=DatabankValue(data_not_available=True),
    )
    assert classify_point(point) == (STATUS_MATCHED, "availability_flags")
    point.databank = None
    assert classify_point(point) == (STATUS_MISSING, "availability_flag_not_in_databank")


def test_apply_mapping_skips_unmapped_and_no_assignment():
    unmapped = FdrsDataPoint(year="2024", iso3="KEN", don_code="DKEN001", base_kpi="KPI_UnknownThing")
    no_aes = FdrsDataPoint(year="2024", iso3="ZZZ", don_code="DZZZ001", base_kpi="KPI_PeopleVol")
    apply_mapping_skips(
        [unmapped, no_aes],
        assignment_by_key={("2024", "KEN"): 99},
        base_to_item_id={"KPI_PeopleVol": 17},
        bank_kpi_codes={"KPI_PeopleVol"},
    )
    assert unmapped.skip_reason == "no_indicator_bank_match"
    assert no_aes.item_id == 17
    assert no_aes.skip_reason == "no_assignment"


def test_attach_databank_and_classify_end_to_end():
    points = group_snapshot_to_points([_snapshot_row()])
    apply_mapping_skips(
        points,
        assignment_by_key={("2024", "KEN"): 42},
        base_to_item_id={"KPI_PeopleVol": 17},
        bank_kpi_codes={"KPI_PeopleVol"},
    )
    attach_databank_values(
        points,
        by_iso_year_item={
            ("KEN", "2024", 17): DatabankValue(value="1500", numeric_value=1500.0),
        },
        country_names={"KEN": "Kenya"},
        kpi_names={"KPI_PeopleVol": "Number of volunteers"},
    )
    attach_classification(points)
    assert points[0].status == STATUS_MATCHED
    assert points[0].country_name == "Kenya"
    assert points[0].aes_id == 42
    assert points[0].item_id == 17
