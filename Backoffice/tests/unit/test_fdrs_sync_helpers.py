"""Unit tests for FDRS sync helpers (income matrix + document metadata plan)."""
from __future__ import annotations

import json
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
backoffice_dir = os.path.dirname(os.path.dirname(script_dir))
scripts_dir = os.path.join(backoffice_dir, "scripts")
for p in (backoffice_dir, scripts_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

from fdrs_assignment_status_sync import (  # noqa: E402
    build_assignment_status_plan,
    derive_assignment_status_from_sections,
    derive_assignment_timestamps,
)
from fdrs_documents_sync import build_document_import_plan  # noqa: E402
from fdrs_sync_constants import (  # noqa: E402
    FDRS_INCOME_SOURCES_MATRIX_ITEM_ID,
    FDRS_NETWORK_SUPPORT_GIVEN_ITEM_ID,
    FDRS_NETWORK_SUPPORT_RECEIVED_ITEM_ID,
    fdrs_document_status_from_approval,
)
from fdrs_data_fetcher import (  # noqa: E402
    build_disability_by_key,
    _disability_combined_from_raw,
)
from import_fdrs_form_data import (  # noqa: E402
    build_income_sources_matrix_rows,
    build_network_support_matrix_rows,
    build_ready_to_import_from_new_pipeline,
    _merge_disability_into_disagg_data,
    _parse_don_code_amount_pairs,
)


def test_build_income_sources_matrix_rows_aggregates_cells():
    fdrs_data = [
        {"ISO3": "SYR", "year": "2024", "BaseKPI": "h_gov_CHF", "KPI_code": "h_gov_CHF", "Value": "1000"},
        {"ISO3": "SYR", "year": "2024", "BaseKPI": "corp_CHF", "KPI_code": "corp_CHF", "Value": "250"},
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "SYR", "assignment_entity_status_id": 42},
    ]
    rows = build_income_sources_matrix_rows(fdrs_data, assignment_rows)
    assert len(rows) == 1
    item_col = rows[0].get("item_id") or rows[0].get("form_item_id")
    assert str(item_col) == str(FDRS_INCOME_SOURCES_MATRIX_ITEM_ID)
    disagg = json.loads(rows[0]["disagg_data"])
    assert disagg["Home Government_Funding"] == 1000
    assert disagg["Corporations_Funding"] == 250
    assert rows[0].get("_debug_disagg_type") == "matrix"


def test_build_document_import_plan_maps_fdrs_types():
    documents = [
        {
            "don_code": "DUS001",
            "iso3": "USA",
            "document_type": "Our Annual Report",
            "document_typeId": 1,
            "year": 2024,
            "YearText": "2024",
            "name": "Annual Report_USA_2024_en.pdf",
            "url": "https://data-api.ifrc.org/documents/US/Annual Report_USA_2024_en.pdf",
            "LangCode": "en",
            "Public": 1,
            "ApprovalStatus": "Validated (Public)",
            "ModifiedAt": "2025-01-01T00:00:00",
        }
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "USA", "assignment_entity_status_id": 99},
    ]
    plan, summary = build_document_import_plan(documents, assignment_rows)
    assert summary["planned"] == 1
    assert plan[0]["form_item_id"] == 923
    assert plan[0]["source_url"].startswith("https://")
    assert plan[0]["file_pending"] is True
    assert plan[0]["fdrs_import_key"]
    assert plan[0]["status"] == "approved"


def test_fdrs_document_status_from_approval_maps_validated_and_pending():
    assert fdrs_document_status_from_approval("Validated (Public)") == "approved"
    assert fdrs_document_status_from_approval("Validated (Private)") == "approved"
    assert fdrs_document_status_from_approval("Under Validation (Public)") == "pending"
    assert fdrs_document_status_from_approval("Under Validation (Private)") == "pending"
    assert fdrs_document_status_from_approval("Rejected (Public)") == "rejected"
    assert fdrs_document_status_from_approval(None) == "pending"


def test_build_document_import_plan_maps_under_validation_to_pending():
    documents = [
        {
            "don_code": "DUS001",
            "iso3": "USA",
            "document_type": "Our Annual Report",
            "document_typeId": 1,
            "year": 2024,
            "YearText": "2024",
            "name": "Annual Report_USA_2024_en.pdf",
            "url": "https://data-api.ifrc.org/documents/US/Annual Report_USA_2024_en.pdf",
            "LangCode": "en",
            "Public": 2,
            "ApprovalStatus": "Under Validation (Public)",
            "ModifiedAt": "2025-01-01T00:00:00",
        }
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "USA", "assignment_entity_status_id": 99},
    ]
    plan, summary = build_document_import_plan(documents, assignment_rows)
    assert summary["planned"] == 1
    assert plan[0]["status"] == "pending"


def test_build_document_import_plan_maps_multi_year_annual_report_to_end_year():
    documents = [
        {
            "don_code": "DBH001",
            "iso3": "BHR",
            "document_type": "Our Annual Report",
            "document_typeId": 1,
            "year": 2021,
            "YearText": "2021-2024",
            "name": "Annual Report_Bahrain_2021-2024_ar.pdf",
            "url": "https://data-api.ifrc.org/documents/BH/Annual Report_Bahrain_2021-2024_ar.pdf",
            "LangCode": "ar",
            "Public": 1,
            "ApprovalStatus": "Validated (Public)",
            "ModifiedAt": "2025-01-01T00:00:00",
        }
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "BHR", "assignment_entity_status_id": 386},
        {"period_name": "2021", "iso3": "BHR", "assignment_entity_status_id": 100},
    ]
    plan, summary = build_document_import_plan(documents, assignment_rows, sync_years=[2024])
    assert summary["planned"] == 1
    assert plan[0]["form_item_id"] == 923
    assert plan[0]["assignment_entity_status_id"] == 386
    assert plan[0]["year"] == "2024"


def test_build_document_import_plan_skips_unmapped_type():
    documents = [
        {
            "don_code": "DUS001",
            "iso3": "USA",
            "document_type": "Other",
            "year": 2024,
            "name": "x.pdf",
            "Public": 1,
            "ApprovalStatus": "Validated (Public)",
        }
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "USA", "assignment_entity_status_id": 99},
    ]
    plan, summary = build_document_import_plan(documents, assignment_rows)
    assert plan == []
    assert summary["skipped_unmapped_type"] == 1


def test_parse_don_code_amount_pairs_zips_parallel_csv():
    pairs = _parse_don_code_amount_pairs("DGB001,DDE001", "100,200")
    assert pairs == [("DGB001", 100), ("DDE001", 200)]


def test_parse_don_code_amount_pairs_skips_empty_amounts():
    pairs = _parse_don_code_amount_pairs("DBB001,DBD001", ",500")
    assert pairs == [("DBD001", 500)]


def test_build_network_support_matrix_rows():
    fdrs_data = [
        {"ISO3": "GBR", "year": "2024", "KPI_code": "supported1", "Value": "DFR001,DDE001"},
        {"ISO3": "GBR", "year": "2024", "KPI_code": "supported1_amount", "Value": "1000000,200000"},
        {"ISO3": "GBR", "year": "2024", "KPI_code": "received_support1", "Value": "DNO001"},
        {"ISO3": "GBR", "year": "2024", "KPI_code": "received_support1_amount", "Value": "50000"},
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "GBR", "assignment_entity_status_id": 55},
    ]
    don_to_label = {"DFR001": "French Red Cross", "DDE001": "German Red Cross", "DNO001": "Norwegian Red Cross"}
    rows = build_network_support_matrix_rows(
        fdrs_data,
        assignment_rows,
        don_to_label=don_to_label,
    )
    assert len(rows) == 2
    by_item = {int(r["item_id"]): json.loads(r["disagg_data"]) for r in rows}
    given = by_item[FDRS_NETWORK_SUPPORT_GIVEN_ITEM_ID]
    received = by_item[FDRS_NETWORK_SUPPORT_RECEIVED_ITEM_ID]
    assert given["French Red Cross_Funding provided"] == 1000000
    assert given["German Red Cross_Funding provided"] == 200000
    assert received["Norwegian Red Cross_Funding Received"] == 50000


def test_derive_assignment_status_all_validated():
    sections = [
        {"started": True, "submitted": True, "validated": True, "published": False,
         "validation_date": None, "publish_date": None},
        {"started": True, "submitted": True, "validated": True, "published": False,
         "validation_date": None, "publish_date": None},
        {"started": True, "submitted": True, "validated": True, "published": False,
         "validation_date": None, "publish_date": None},
    ]
    assert derive_assignment_status_from_sections(sections) == "approved"


def test_derive_assignment_status_governance_started_only_is_in_progress():
    sections = [
        {"started": True, "submitted": False, "validated": False, "published": False,
         "validation_date": None, "publish_date": None},
        {"started": False, "submitted": False, "validated": False, "published": False,
         "validation_date": None, "publish_date": None},
        {"started": False, "submitted": False, "validated": False, "published": False,
         "validation_date": None, "publish_date": None},
    ]
    assert derive_assignment_status_from_sections(sections) == "in_progress"


def test_derive_assignment_status_partial_submitted():
    sections = [
        {"started": True, "submitted": True, "validated": False, "published": False,
         "validation_date": None, "publish_date": None},
        {"started": True, "submitted": False, "validated": False, "published": False,
         "validation_date": None, "publish_date": None},
        {"started": False, "submitted": False, "validated": False, "published": False,
         "validation_date": None, "publish_date": None},
    ]
    assert derive_assignment_status_from_sections(sections) == "submitted"


def test_build_assignment_status_plan_maps_workflow_kpis():
    workflow_rows = [
        {"DonCode": "DGB001", "year": "2024", "KPI_code": "KPI_NSGS_WasSubmitted", "value": True},
        {"DonCode": "DGB001", "year": "2024", "KPI_code": "KPI_NSGS_WasValidated", "value": True},
        {"DonCode": "DGB001", "year": "2024", "KPI_code": "KPI_NSGS_ValidationDate", "value": "2025-07-28T09:51:49.607"},
        {"DonCode": "DGB001", "year": "2024", "KPI_code": "KPI_NSFP_WasSubmitted", "value": True},
        {"DonCode": "DGB001", "year": "2024", "KPI_code": "KPI_NSFP_WasValidated", "value": True},
        {"DonCode": "DGB001", "year": "2024", "KPI_code": "KPI_NSFP_ValidationDate", "value": "2025-07-28T10:05:38.053"},
        {"DonCode": "DGB001", "year": "2024", "KPI_code": "KPI_NSR_WasSubmitted", "value": True},
        {"DonCode": "DGB001", "year": "2024", "KPI_code": "KPI_NSR_WasValidated", "value": True},
        {"DonCode": "DGB001", "year": "2024", "KPI_code": "KPI_NSR_ValidationDate", "value": "2025-07-28T11:00:00"},
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "GBR", "assignment_entity_status_id": 77},
    ]
    plan, summary = build_assignment_status_plan(
        workflow_rows,
        assignment_rows,
        don_to_iso={"DGB001": "GBR"},
    )
    assert summary["planned"] == 1
    assert plan[0]["status"] == "approved"
    assert plan[0]["assignment_entity_status_id"] == 77
    status_ts, submitted_at = derive_assignment_timestamps(plan[0]["status"], plan[0]["sections"])
    assert submitted_at is not None
    assert status_ts is not None
    assert status_ts >= submitted_at


def test_disability_combined_from_raw_includes_excluded_codebook_kpis():
    raw = [
        {
            "DonCode": "DKEN001",
            "Year": 2024,
            "KPICode": "KPI_PeopleVol_ddd",
            "BoolValue": True,
            "State": 400,
        },
        {
            "DonCode": "DKEN001",
            "Year": 2024,
            "KPICode": "KPI_PeopleVol",
            "IntValue": 100,
            "State": 400,
        },
    ]
    country_map = {"DKEN001": "KEN"}
    combined = _disability_combined_from_raw(raw, country_map, frozenset({100, 200, 300, 400, 500}))
    by_key = build_disability_by_key(combined)
    assert by_key[("KEN", "2024", "KPI_PeopleVol")] == {"disaggregated_by_disability": True}


def test_build_disability_by_key_maps_ddd_and_wgq():
    combined = [
        {"ISO3": "SYR", "year": 2024, "KPI_code": "KPI_PeopleVol_ddd", "Value": "1"},
        {"ISO3": "SYR", "year": 2024, "KPI_code": "KPI_PeopleVol_wgq", "Value": "0"},
        {"ISO3": "USA", "year": 2024, "KPI_code": "KPI_PeopleVol_ddd", "Value": "0"},
    ]
    by_key = build_disability_by_key(combined)
    assert by_key[("SYR", "2024", "KPI_PeopleVol")] == {
        "disaggregated_by_disability": True,
        "washington_group_compliant": False,
    }
    assert by_key[("USA", "2024", "KPI_PeopleVol")] == {
        "disaggregated_by_disability": False,
    }


def test_merge_disability_into_disagg_data_preserves_existing_breakdown():
    merged = _merge_disability_into_disagg_data(
        json.dumps({"mode": "sex_age", "values": {"direct": {"male": 10}, "indirect": 5}}),
        {"disaggregated_by_disability": True, "washington_group_compliant": True},
    )
    obj = json.loads(merged)
    assert obj["values"]["direct"]["male"] == 10
    assert obj["values"]["indirect"] == 5
    assert obj["values"]["disability"] == {
        "disaggregated_by_disability": True,
        "washington_group_compliant": True,
    }


def test_build_ready_to_import_merges_disability_into_disagg_data():
    fdrs_data = [
        {
            "ISO3": "SYR",
            "year": "2024",
            "BaseKPI": "KPI_PeopleVol",
            "KPI_code": "KPI_PeopleVol_Tot",
            "Value": "500",
        },
    ]
    disagg_by_key = {
        ("SYR", "2024", "KPI_PeopleVol"): json.dumps(
            {"mode": "total", "values": {"direct": {"total": 500}, "indirect": None}}
        ),
    }
    disability_by_key = {
        ("SYR", "2024", "KPI_PeopleVol"): {
            "disaggregated_by_disability": True,
            "washington_group_compliant": True,
        },
    }
    assignment_rows = [{"period_name": "2024", "iso3": "SYR", "assignment_entity_status_id": 42}]
    form_item_rows = [{"bank_id": 7, "item_id": 900}]
    indicator_bank_rows = [{"id": 7, "fdrs_kpi_code": "KPI_PeopleVol"}]
    rows = build_ready_to_import_from_new_pipeline(
        fdrs_data,
        disagg_by_key,
        assignment_rows,
        form_item_rows,
        indicator_bank_rows,
        disability_by_key=disability_by_key,
    )
    assert len(rows) == 1
    disagg = json.loads(rows[0]["disagg_data"])
    assert disagg["values"]["disability"] == {
        "disaggregated_by_disability": True,
        "washington_group_compliant": True,
    }


def test_build_ready_to_import_emits_disability_only_row():
    disability_by_key = {
        ("SYR", "2024", "KPI_PeopleVol"): {"disaggregated_by_disability": False},
    }
    assignment_rows = [{"period_name": "2024", "iso3": "SYR", "assignment_entity_status_id": 42}]
    form_item_rows = [{"bank_id": 7, "item_id": 900}]
    indicator_bank_rows = [{"id": 7, "fdrs_kpi_code": "KPI_PeopleVol"}]
    rows = build_ready_to_import_from_new_pipeline(
        [],
        {},
        assignment_rows,
        form_item_rows,
        indicator_bank_rows,
        disability_by_key=disability_by_key,
    )
    assert len(rows) == 1
    assert rows[0]["value"] == ""
    disagg = json.loads(rows[0]["disagg_data"])
    assert disagg == {"mode": "total", "values": {"disability": {"disaggregated_by_disability": False}}}
