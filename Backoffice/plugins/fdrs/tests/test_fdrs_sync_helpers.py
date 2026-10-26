"""Unit tests for FDRS sync helpers (income matrix + document metadata plan)."""
from __future__ import annotations

import json
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
backoffice_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
imports_dir = os.path.join(backoffice_dir, "scripts", "imports")
fdrs_scripts = os.path.join(backoffice_dir, "plugins", "fdrs", "scripts")
for p in (backoffice_dir, fdrs_scripts, imports_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

from fdrs_assignment_ensure import (  # noqa: E402
    plan_missing_fdrs_assignments,
    years_from_fdrs_data,
)
from fdrs_assignment_status_sync import (  # noqa: E402
    build_assignment_status_plan,
    derive_assignment_status_from_sections,
    derive_assignment_timestamps,
)
from fdrs_documents_sync import (  # noqa: E402
    build_document_import_plan,
    choose_fdrs_slot_document,
    clean_fdrs_document_period,
    encode_fdrs_document_url,
    fetch_fdrs_document_bytes,
    fdrs_document_removal_allowed,
    fdrs_pending_slot_siblings,
    fdrs_url_without_duplicate_suffix,
    public_document_sync_summary,
    scoped_fdrs_assignment_ids,
    select_fdrs_document_for_upsert,
    select_stale_fdrs_documents,
    _fdrs_document_import_key,
    _resolve_download_outcome,
    _should_attempt_download,
)
from fdrs_sync_constants import (  # noqa: E402
    FDRS_INCOME_SOURCES_MATRIX_ITEM_ID,
    FDRS_NETWORK_SUPPORT_GIVEN_ITEM_ID,
    FDRS_NETWORK_SUPPORT_RECEIVED_ITEM_ID,
    fdrs_approval_is_importable,
    fdrs_document_is_public_visibility,
    fdrs_document_status_from_approval,
)
from fdrs_data_fetcher import (  # noqa: E402
    build_disability_by_key,
    build_fdrs_combined,
    build_fdrs_data,
    _classify_fdrs_combined_row,
    _disability_combined_from_raw,
    _extract_fdrs_row_value,
    _fdrsdata_rows,
)
from fdrs_sync_constants import fdrs_kpi_data_availability_kind  # noqa: E402
from import_fdrs_form_data import (  # noqa: E402
    build_income_sources_matrix_rows,
    build_network_support_matrix_rows,
    _network_support_cells_from_slots,
    build_ready_to_import_from_new_pipeline,
    _data_availability_from_group_rows,
    _merge_disability_into_disagg_data,
    _parse_scalar_field,
    _parse_don_code_amount_pairs,
    row_to_payload,
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
    assert rows[0]["published_value"] == ""
    assert rows[0]["published_disagg_data"] == ""


def test_income_matrix_splits_local_and_chf_when_currency_is_not_chf():
    fdrs_data = [
        {"ISO3": "AFG", "year": "2024", "BaseKPI": "KPI_CUR_Code", "KPI_code": "KPI_CUR_Code", "Value": "AFN"},
        {"ISO3": "AFG", "year": "2024", "BaseKPI": "h_gov", "KPI_code": "h_gov", "Value": "1000"},
        {"ISO3": "AFG", "year": "2024", "BaseKPI": "h_gov_CHF", "KPI_code": "h_gov_CHF", "Value": "25"},
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "AFG", "assignment_entity_status_id": 42},
    ]
    rows = build_income_sources_matrix_rows(fdrs_data, assignment_rows)
    disagg = json.loads(rows[0]["disagg_data"])
    assert disagg["Home Government_Funding"] == 1000
    assert disagg["_chf|Home Government_Funding"] == 25


def test_income_matrix_published_disagg_keeps_only_state_500():
    fdrs_data = [
        {"ISO3": "SYR", "year": "2024", "BaseKPI": "si_CHF", "KPI_code": "si_CHF", "Value": "80", "State": 500},
        {"ISO3": "SYR", "year": "2024", "BaseKPI": "h_gov_CHF", "KPI_code": "h_gov_CHF", "Value": "20", "State": 300},
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "SYR", "assignment_entity_status_id": 42},
    ]
    rows = build_income_sources_matrix_rows(fdrs_data, assignment_rows)
    disagg = json.loads(rows[0]["disagg_data"])
    published = json.loads(rows[0]["published_disagg_data"])
    assert disagg["Service income_Funding"] == 80
    assert disagg["Home Government_Funding"] == 20
    assert disagg["_chf|Service income_Funding"] == 80
    assert disagg["_chf|Home Government_Funding"] == 20
    assert published["Service income_Funding"] == 80
    assert published["_chf|Service income_Funding"] == 80
    assert "Home Government_Funding" not in published
    assert rows[0]["published_value"] == ""


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
    assert plan[0]["fdrs_import_key"]
    assert plan[0]["status"] == "approved"


def test_fdrs_document_status_from_approval_maps_validated_and_pending():
    assert fdrs_document_status_from_approval("Validated (Public)") == "approved"
    assert fdrs_document_status_from_approval("Validated (Private)") == "approved"
    assert fdrs_document_status_from_approval("Under Validation (Public)") == "pending"
    assert fdrs_document_status_from_approval("Under Validation (Private)") == "pending"
    assert fdrs_document_status_from_approval("Rejected (Public)") == "rejected"
    assert fdrs_document_status_from_approval("Rejected (Private)") == "rejected"
    assert fdrs_document_status_from_approval(None) == "pending"


def test_fdrs_document_status_uses_public_code_when_label_is_missing():
    assert fdrs_document_status_from_approval(None, public_code=1) == "approved"
    assert fdrs_document_status_from_approval(None, public_code=0) == "approved"
    assert fdrs_document_status_from_approval("", public_code="3") == "rejected"
    assert fdrs_document_status_from_approval(None, public_code=2) == "pending"
    assert fdrs_document_status_from_approval(None, public_code=4) == "pending"
    assert fdrs_document_status_from_approval(1) == "approved"
    assert fdrs_document_status_from_approval("Rejected (Public)", public_code=1) == "rejected"
    assert fdrs_approval_is_importable(None, 1) is True
    assert fdrs_approval_is_importable("Nope", None) is False
    assert fdrs_approval_is_importable("Nope", 1) is True


class _Doc:
    def __init__(self, *, key, filename="a.pdf", status="pending", uploaded_at="2024-01-01", row_id=1):
        self.fdrs_import_key = key
        self.filename = filename
        self.status = status
        self.uploaded_at = uploaded_at
        self.id = row_id


def test_select_fdrs_document_reuses_slot_row_when_filename_changes():
    old = _Doc(key="old", filename="rejected.pdf", status="pending", row_id=2)
    chosen, adopted = select_fdrs_document_for_upsert(None, [old], filename="validated.pdf")
    assert chosen is old
    assert adopted is True
    keyed = _Doc(key="same", filename="validated.pdf", status="approved", row_id=9)
    chosen, adopted = select_fdrs_document_for_upsert(keyed, [old, keyed], filename="validated.pdf")
    assert chosen is keyed
    assert adopted is False


def test_pending_siblings_follow_approved_slot_status():
    canonical = _Doc(key="new", filename="validated.pdf", status="pending", row_id=2)
    leftover = _Doc(key="old", filename="old.pdf", status="pending", row_id=1)
    user_upload = _Doc(key=None, filename="manual.pdf", status="pending", row_id=3)
    already = _Doc(key="other", filename="kept.pdf", status="rejected", row_id=4)
    pending = fdrs_pending_slot_siblings(canonical, [canonical, leftover, user_upload, already], "approved")
    assert pending == [leftover]
    assert fdrs_pending_slot_siblings(canonical, [leftover], "pending") == []
    named = choose_fdrs_slot_document([leftover, canonical], filename="validated.pdf")
    assert named is canonical


def test_build_document_import_plan_maps_public_code_without_approval_label():
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
            "ModifiedAt": "2025-01-01T00:00:00",
        },
        {
            "don_code": "DGA001",
            "iso3": "GAB",
            "document_type": "Our Audited Financial Statements",
            "document_typeId": 2,
            "year": 2024,
            "YearText": "2024",
            "name": "audited.pdf",
            "url": "https://example.org/b.pdf",
            "LangCode": "fr",
            "Public": 3,
            "ModifiedAt": "2025-01-01T00:00:00",
        },
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "USA", "assignment_entity_status_id": 99},
        {"period_name": "2024", "iso3": "GAB", "assignment_entity_status_id": 77},
    ]
    plan, summary = build_document_import_plan(documents, assignment_rows)
    by_iso = {row["iso3"]: row for row in plan}
    assert summary["planned"] == 2
    assert summary["skipped_approval"] == 0
    assert by_iso["USA"]["status"] == "approved"
    assert by_iso["GAB"]["status"] == "rejected"
    assert summary["status_approved"] == 1
    assert summary["status_rejected"] == 1


def test_public_document_sync_summary_reads_job_stats():
    summary = public_document_sync_summary(
        {
            "documents_inserted": 2,
            "documents_updated": 5,
            "documents_errors": 1,
            "documents_status_approved": 4,
            "documents_status_pending": 2,
            "documents_status_rejected": 1,
            "documents_status_changed": 3,
            "documents_sync_error": None,
        }
    )
    assert summary["inserted"] == 2
    assert summary["removed"] == 0
    assert summary["status_approved"] == 4
    assert summary["status_changed"] == 3
    assert summary["sync_error"] is None


def test_public_document_sync_summary_includes_removed():
    summary = public_document_sync_summary({"documents_removed": 7, "documents_inserted": 1})
    assert summary["removed"] == 7
    assert summary["inserted"] == 1


def test_catalog_keeps_every_importable_key_including_deduped_files():
    documents = [
        {
            "don_code": "DUS001",
            "iso3": "USA",
            "document_type": "Our Annual Report",
            "document_typeId": 1,
            "year": 2024,
            "YearText": "2024",
            "name": "old-report.pdf",
            "url": "https://example.org/old.pdf",
            "LangCode": "en",
            "Public": 1,
            "ModifiedAt": "2024-01-01T00:00:00",
        },
        {
            "don_code": "DUS001",
            "iso3": "USA",
            "document_type": "Our Annual Report",
            "document_typeId": 1,
            "year": 2024,
            "YearText": "2024",
            "name": "new-report.pdf",
            "url": "https://example.org/new.pdf",
            "LangCode": "en",
            "Public": 1,
            "ModifiedAt": "2025-06-01T00:00:00",
        },
        {
            "don_code": "DUS001",
            "iso3": "USA",
            "document_type": "Our Annual Report",
            "document_typeId": 1,
            "year": 2023,
            "YearText": "2023",
            "name": "report-2023.pdf",
            "url": "https://example.org/2023.pdf",
            "LangCode": "en",
            "Public": 1,
            "ModifiedAt": "2023-06-01T00:00:00",
        },
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "USA", "assignment_entity_status_id": 99},
        {"period_name": "2023", "iso3": "USA", "assignment_entity_status_id": 98},
    ]
    plan, summary = build_document_import_plan(documents, assignment_rows, sync_years=[2024])
    present = summary["present_import_keys"]
    assert summary["planned"] == 1
    assert plan[0]["filename"] == "new-report.pdf"
    assert plan[0]["fdrs_import_key"] in present
    older = [doc for doc in documents if doc["name"] == "old-report.pdf"][0]
    assert _fdrs_document_import_key(older) in present
    assert len(present) == 2
    assert summary["skipped_sync_year"] == 1


def test_removal_requires_a_mapped_catalog():
    assert fdrs_document_removal_allowed({"total_api_docs": 0, "planned": 0}) is False
    assert fdrs_document_removal_allowed(
        {"total_api_docs": 4, "planned": 0, "skipped_no_iso3": 4}
    ) is False
    assert fdrs_document_removal_allowed(
        {"total_api_docs": 4, "planned": 0, "skipped_no_assignment": 4, "skipped_sync_year": 0}
    ) is False
    assert fdrs_document_removal_allowed({"total_api_docs": 4, "planned": 2}) is True
    assert fdrs_document_removal_allowed(
        {"total_api_docs": 4, "planned": 0, "skipped_sync_year": 4, "skipped_no_iso3": 0}
    ) is True


def test_removal_scope_follows_synced_years_and_spares_user_uploads():
    rows = [
        {"period_name": "2024", "iso3": "USA", "assignment_entity_status_id": 99},
        {"period_name": "2023", "iso3": "USA", "assignment_entity_status_id": 98},
    ]
    assert scoped_fdrs_assignment_ids(rows, [2024]) == {99}
    assert scoped_fdrs_assignment_ids(rows, None) == {99, 98}
    kept = _Doc(key="keep", filename="current.pdf")
    gone = _Doc(key="gone", filename="retired.pdf")
    upload = _Doc(key=None, filename="manual.pdf")
    stale = select_stale_fdrs_documents([kept, gone, upload], {"keep"})
    assert stale == [gone]


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


def test_build_document_import_plan_imports_under_validation_private():
    documents = [
        {
            "don_code": "DAF001",
            "iso3": "AFG",
            "document_type": "Our Annual Report",
            "document_typeId": 1,
            "year": 2024,
            "YearText": "2024",
            "name": "Annual Report_Afghanistan_2024-2024_zz.pdf",
            "url": "https://data-api.ifrc.org/documents/AF/report.pdf",
            "LangCode": "zz",
            "Public": 4,
            "ApprovalStatus": "Under Validation (Private)",
            "ModifiedAt": "2025-01-01T00:00:00",
        }
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "AFG", "assignment_entity_status_id": 88},
    ]
    plan, summary = build_document_import_plan(documents, assignment_rows)
    assert summary["planned"] == 1
    assert summary["skipped_approval"] == 0
    assert summary["status_pending"] == 1
    assert plan[0]["status"] == "pending"
    assert plan[0]["is_public"] is False


def test_build_document_import_plan_tracks_status_counts():
    documents = [
        {
            "don_code": "DUS001",
            "iso3": "USA",
            "document_type": "Our Annual Report",
            "document_typeId": 1,
            "year": 2024,
            "YearText": "2024",
            "name": "Annual Report_USA_2024_en.pdf",
            "url": "https://example.org/a.pdf",
            "LangCode": "en",
            "Public": 1,
            "ApprovalStatus": "Validated (Public)",
            "ModifiedAt": "2025-01-01T00:00:00",
        },
        {
            "don_code": "DGA001",
            "iso3": "GAB",
            "document_type": "Our Audited Financial Statements",
            "document_typeId": 2,
            "year": 2024,
            "YearText": "2024",
            "name": "audited Financial Statement_Gabon_2024.pdf",
            "url": "https://example.org/b.pdf",
            "LangCode": "fr",
            "Public": 3,
            "ApprovalStatus": "Rejected (Public)",
            "ModifiedAt": "2025-01-01T00:00:00",
        },
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "USA", "assignment_entity_status_id": 99},
        {"period_name": "2024", "iso3": "GAB", "assignment_entity_status_id": 77},
    ]
    plan, summary = build_document_import_plan(documents, assignment_rows)
    assert summary["planned"] == 2
    assert summary["status_approved"] == 1
    assert summary["status_rejected"] == 1
    assert summary["status_pending"] == 0


def test_build_document_import_plan_maps_rejected_status():
    documents = [
        {
            "don_code": "DGA001",
            "iso3": "GAB",
            "document_type": "Our Audited Financial Statements",
            "document_typeId": 2,
            "year": 2024,
            "YearText": "2024",
            "name": "audited Financial Statement_Gabon_2024.pdf",
            "url": "https://data-api.ifrc.org/documents/GA/audited Financial Statement_Gabon_2024.pdf",
            "LangCode": "fr",
            "Public": 3,
            "ApprovalStatus": "Rejected (Public)",
            "ModifiedAt": "2025-01-01T00:00:00",
        }
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "GAB", "assignment_entity_status_id": 77},
    ]
    plan, summary = build_document_import_plan(documents, assignment_rows)
    assert summary["planned"] == 1
    assert summary["skipped_approval"] == 0
    assert plan[0]["status"] == "rejected"
    assert plan[0]["form_item_id"] == 933


def test_build_document_import_plan_prefers_validated_over_rejected():
    documents = [
        {
            "don_code": "DGA001",
            "iso3": "GAB",
            "document_type": "Our Audited Financial Statements",
            "document_typeId": 2,
            "year": 2024,
            "YearText": "2024",
            "name": "audited Financial Statement_Gabon_2024_rejected.pdf",
            "url": "https://data-api.ifrc.org/documents/GA/rejected.pdf",
            "LangCode": "fr",
            "Public": 3,
            "ApprovalStatus": "Rejected (Public)",
            "ModifiedAt": "2025-01-01T00:00:00",
        },
        {
            "don_code": "DGA001",
            "iso3": "GAB",
            "document_type": "Our Audited Financial Statements",
            "document_typeId": 2,
            "year": 2024,
            "YearText": "2024",
            "name": "audited Financial Statement_Gabon_2024.pdf",
            "url": "https://data-api.ifrc.org/documents/GA/validated.pdf",
            "LangCode": "fr",
            "Public": 1,
            "ApprovalStatus": "Validated (Public)",
            "ModifiedAt": "2025-02-01T00:00:00",
        },
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "GAB", "assignment_entity_status_id": 77},
    ]
    plan, summary = build_document_import_plan(documents, assignment_rows)
    assert summary["planned"] == 1
    assert plan[0]["status"] == "approved"
    assert plan[0]["source_url"].endswith("validated.pdf")


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
    assert plan[0]["period"] == "2021-2024"


def test_same_year_period_range_is_stored_as_the_year():
    assert clean_fdrs_document_period("2024-2024") == "2024"
    assert clean_fdrs_document_period(" 2024 - 2024 ") == "2024"
    assert clean_fdrs_document_period("2024–2024") == "2024"
    assert clean_fdrs_document_period("2024") == "2024"
    assert clean_fdrs_document_period("2021-2024") == "2021-2024"
    assert clean_fdrs_document_period("2024-2025") == "2024-2025"

    documents = [
        {
            "don_code": "DAF001",
            "iso3": "AFG",
            "document_type": "Our Annual Report",
            "document_typeId": 1,
            "year": 2024,
            "YearText": "2024-2024",
            "name": "Annual Report_Afghanistan_2024-2024_en.pdf",
            "url": "https://data-api.ifrc.org/documents/AF/report.pdf",
            "LangCode": "en",
            "Public": 1,
            "ApprovalStatus": "Validated (Public)",
            "ModifiedAt": "2025-01-01T00:00:00",
        }
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "AFG", "assignment_entity_status_id": 88},
    ]
    plan, summary = build_document_import_plan(documents, assignment_rows)
    assert summary["planned"] == 1
    assert plan[0]["period"] == "2024"
    assert plan[0]["year"] == "2024"


def test_build_document_import_plan_imports_library_types_without_form_item():
    documents = [
        {
            "don_code": "DUS001",
            "iso3": "USA",
            "document_type": "Other",
            "year": 2024,
            "name": "x.pdf",
            "Public": 1,
            "ApprovalStatus": "Validated (Public)",
        },
        {
            "don_code": "DUS001",
            "iso3": "USA",
            "document_type": "Our Statutes in Force",
            "year": 2024,
            "name": "statutes.pdf",
            "Public": 1,
            "ApprovalStatus": "Validated (Public)",
        },
        {
            "don_code": "DUS001",
            "iso3": "USA",
            "document_type": "EveryoneCounts",
            "year": 2024,
            "name": "ec.pdf",
            "Public": 1,
            "ApprovalStatus": "Validated (Public)",
        },
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "USA", "assignment_entity_status_id": 99},
    ]
    plan, summary = build_document_import_plan(documents, assignment_rows)
    assert summary["skipped_global_type"] == 1
    assert summary["planned_library"] == 2
    assert summary["planned_template_slots"] == 0
    assert {row["document_type"] for row in plan} == {"Other", "Statutes in Force"}
    assert all(row["form_item_id"] is None for row in plan)
    assert all(row["assignment_entity_status_id"] == 99 for row in plan)


def test_build_document_import_plan_keeps_all_other_docs_same_year():
    documents = [
        {
            "don_code": "DUS001",
            "iso3": "USA",
            "document_type": "Other",
            "year": 2024,
            "name": "plan-a.pdf",
            "Public": 1,
            "ApprovalStatus": "Validated (Public)",
        },
        {
            "don_code": "DUS001",
            "iso3": "USA",
            "document_type": "Other",
            "year": 2024,
            "name": "plan-b.pdf",
            "Public": 1,
            "ApprovalStatus": "Validated (Public)",
        },
    ]
    assignment_rows = [
        {"period_name": "2024", "iso3": "USA", "assignment_entity_status_id": 99},
    ]
    plan, summary = build_document_import_plan(documents, assignment_rows)
    assert summary["planned"] == 2
    assert {row["filename"] for row in plan} == {"plan-a.pdf", "plan-b.pdf"}


def test_parse_don_code_amount_pairs_zips_parallel_csv():
    pairs = _parse_don_code_amount_pairs("DGB001,DDE001", "100,200")
    assert pairs == [("DGB001", 100), ("DDE001", 200)]


def test_parse_don_code_amount_pairs_keeps_blank_amounts():
    pairs = _parse_don_code_amount_pairs("DBB001,DBD001,DXX001", ",500,0")
    assert pairs == [("DBB001", None), ("DBD001", 500)]


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


def test_public_network_list_keeps_partners_with_blank_amounts():
    from types import SimpleNamespace

    from plugins.fdrs.services.fdrs_public_adapter import KIND_NETWORK, SeriesSpec, _network_value

    row = SimpleNamespace(
        published_disagg_data={
            "Costa Rican Red Cross_Funding provided": None,
            "Paraguayan Red Cross_Funding provided": 500,
        }
    )
    names = {
        "costa rican red cross": "DCR001",
        "paraguayan red cross": "DPY001",
    }
    codes = SeriesSpec("supported1", KIND_NETWORK, network_prefix="supported", network_amount=False)
    amounts = SeriesSpec("supported1_amount", KIND_NETWORK, network_prefix="supported", network_amount=True)
    assert _network_value(codes, row, names) == "DCR001,DPY001"
    assert _network_value(amounts, row, names) == ",500"


def test_network_support_keeps_partner_names_when_amount_is_blank():
    cells = _network_support_cells_from_slots(
        {"supported1": "DCR001,DPY001", "supported1_amount": ","},
        code_prefix="supported",
        column="Funding provided",
        don_to_label={"DCR001": "Costa Rican Red Cross", "DPY001": "Paraguayan Red Cross"},
    )
    assert cells == {
        "Costa Rican Red Cross_Funding provided": None,
        "Paraguayan Red Cross_Funding provided": None,
    }
    published = _network_support_cells_from_slots(
        {"supported1": "DCR001", "supported1_amount": "100"},
        code_prefix="supported",
        column="Funding provided",
        don_to_label={"DCR001": "Costa Rican Red Cross"},
        kpi_states={"supported1": 500, "supported1_amount": 100},
        published_only=True,
    )
    assert published == {"Costa Rican Red Cross_Funding provided": None}


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


def test_climate_not_available_uses_bool_value_not_the_not_collected_flag():
    parsed = _fdrsdata_rows([
        {
            "DonCode": "DAF001",
            "Year": 2025,
            "KPICode": "KPI_Climate_D_IsDataNotAvailable",
            "value": None,
            "BoolValue": False,
            "State": 200,
        },
        {
            "DonCode": "DAF001",
            "Year": 2025,
            "KPICode": "KPI_Climate_D_isDataNotCollected",
            "value": None,
            "BoolValue": True,
            "State": 200,
        },
    ], valid_kpi_codes=[
        "KPI_Climate_D_IsDataNotAvailable",
        "KPI_Climate_D_isDataNotCollected",
    ])
    by_code = {row["KPI_code"]: row["value"] for row in parsed}
    assert by_code["KPI_Climate_D_IsDataNotAvailable"] == "False"
    assert by_code["KPI_Climate_D_isDataNotCollected"] == "True"
    combined = build_fdrs_combined(
        parsed,
        [],
        {"DAF001": "AFG"},
        import_state_allowlist=frozenset({100, 200, 300, 400, 500}),
    )
    data = build_fdrs_data(combined)
    data_na, not_applic = _data_availability_from_group_rows(data)
    assert data_na is False
    assert not_applic is True


def test_null_value_does_not_fall_back_to_int_value():
    row = {"value": None, "IntValue": 6219, "KPICode": "KPI_ReachSI_D_Tot_UnknownSex", "State": 100}
    assert _extract_fdrs_row_value(row) is None
    parsed = _fdrsdata_rows([
        {
            "DonCode": "DDJ001",
            "Year": 2025,
            "KPICode": "KPI_ReachSI_D_Tot_UnknownSex",
            "value": None,
            "IntValue": 6219,
            "State": 100,
        }
    ])
    assert parsed[0]["value"] is None


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


def test_fdrs_kpi_data_availability_kind_accepts_api_casing_variants():
    assert fdrs_kpi_data_availability_kind("KPI_Climate_IsDataNotAvailable") == "data_not_available"
    assert fdrs_kpi_data_availability_kind("KPI_Climate_isDataNotCollected") == "not_applicable"
    assert fdrs_kpi_data_availability_kind("KPI_Climate_IsDataNotCollected") == "not_applicable"


def test_data_availability_from_group_rows_maps_is_data_not_collected_to_not_applicable():
    group_rows = [
        {"KPI_code": "KPI_PeopleVol_IsDataNotCollected", "Value": True},
    ]
    data_na, not_applic = _data_availability_from_group_rows(group_rows)
    assert data_na is False
    assert not_applic is True


def test_network_amount_keeps_its_own_base_kpi():
    """Partner NS codes and amounts are different fields, including received-support slots."""
    _, _, _, _, given_code = _classify_fdrs_combined_row({
        "KPI_code": "supported1",
        "Value": "DFR001",
        "year": 2024,
    })
    _, _, _, _, given_amount = _classify_fdrs_combined_row({
        "KPI_code": "supported1_amount",
        "Value": "100",
        "year": 2024,
    })
    _, _, _, _, received_code = _classify_fdrs_combined_row({
        "KPI_code": "received_support1",
        "Value": "DNO001",
        "year": 2024,
    })
    _, _, _, _, received_amount = _classify_fdrs_combined_row({
        "KPI_code": "received_support1_amount",
        "Value": "50",
        "year": 2024,
    })
    assert given_code == "supported1"
    assert given_amount == "supported1_amount"
    assert received_code == "received_support1"
    assert received_amount == "received_support1_amount"


def test_classify_fdrs_combined_row_keeps_is_data_not_collected_with_empty_value():
    include, reason, _, _, base_kpi = _classify_fdrs_combined_row({
        "KPI_code": "KPI_PeopleVol_isDataNotCollected",
        "Value": None,
        "year": 2024,
    })
    assert include is True
    assert reason == ""
    assert base_kpi == "KPI_PeopleVol"


def test_build_fdrs_combined_keeps_reported_and_imputed_separate():
    reported = [{
        "KPI_code": "KPI_PeopleVol_Tot",
        "DonCode": "DSK001",
        "year": 2024,
        "value": "1743",
        "State": 100,
        "SourceType": "Reported",
    }]
    imputed = [{
        "KPI_code": "KPI_PeopleVol",
        "DonCode": "DSK001",
        "year": 2024,
        "value": "1574",
        "State": None,
        "SourceType": "Imputed",
    }]
    combined = build_fdrs_combined(
        reported,
        imputed,
        {"DSK001": "SVK"},
        import_state_allowlist=frozenset({100, 200, 300, 400, 500}),
    )
    by_kpi = {(r["KPI_code"], r["DonCode"]): r for r in combined}
    tot = by_kpi[("KPI_PeopleVol_Tot", "DSK001")]
    base = by_kpi[("KPI_PeopleVol", "DSK001")]
    assert tot["Value"] == "1743"
    assert tot["ReportedValue"] == "1743"
    assert tot["ImputedValue"] is None
    assert base["Value"] is None
    assert base["ReportedValue"] is None
    assert base["ImputedValue"] == "1574"


def test_build_ready_to_import_splits_reported_value_and_imputed_value():
    fdrs_data = [
        {
            "ISO3": "SVK",
            "year": "2024",
            "BaseKPI": "KPI_PeopleVol",
            "KPI_code": "KPI_PeopleVol_Tot",
            "Value": "1743",
            "ImputedValue": "",
        },
        {
            "ISO3": "SVK",
            "year": "2024",
            "BaseKPI": "KPI_PeopleVol",
            "KPI_code": "KPI_PeopleVol",
            "Value": "",
            "ImputedValue": "1574",
        },
    ]
    assignment_rows = [{"period_name": "2024", "iso3": "SVK", "assignment_entity_status_id": 42}]
    form_item_rows = [{"bank_id": 7, "item_id": 900}]
    indicator_bank_rows = [{"id": 7, "fdrs_kpi_code": "KPI_PeopleVol"}]
    rows = build_ready_to_import_from_new_pipeline(
        fdrs_data,
        {},
        assignment_rows,
        form_item_rows,
        indicator_bank_rows,
    )
    assert len(rows) == 1
    assert rows[0]["value"] == "1743"
    assert rows[0]["imputed_value"] == "1574"


def test_build_ready_to_import_imputed_only_populates_imputed_value_column():
    fdrs_data = [
        {
            "ISO3": "SYR",
            "year": "2024",
            "BaseKPI": "KPI_PeopleVol",
            "KPI_code": "KPI_PeopleVol",
            "Value": "",
            "ImputedValue": "1200",
        },
    ]
    assignment_rows = [{"period_name": "2024", "iso3": "SYR", "assignment_entity_status_id": 42}]
    form_item_rows = [{"bank_id": 7, "item_id": 900}]
    indicator_bank_rows = [{"id": 7, "fdrs_kpi_code": "KPI_PeopleVol"}]
    rows = build_ready_to_import_from_new_pipeline(
        fdrs_data,
        {},
        assignment_rows,
        form_item_rows,
        indicator_bank_rows,
    )
    assert len(rows) == 1
    assert rows[0]["value"] == ""
    assert rows[0]["imputed_value"] == "1200"


def test_parse_scalar_field_decodes_json_scalars_without_accepting_objects():
    assert _parse_scalar_field('"CHF"') == "CHF"
    assert _parse_scalar_field("1200") == "1200"
    assert _parse_scalar_field('["A", "B"]') == '["A", "B"]'
    assert _parse_scalar_field('{"mode": "total", "values": {"direct": 1}}') is None


def test_row_to_payload_keeps_prefilled_and_imputed_values_as_strings():
    _, _, _, payload = row_to_payload({
        "assignment_entity_status_id": "42",
        "item_id": "900",
        "value": "",
        "disagg_data": "",
        "data_not_available": "",
        "not_applicable": "",
        "prefilled_value": '"CHF"',
        "imputed_value": "1200",
        "submitted_at": "",
    })
    assert payload["prefilled_value"] == "CHF"
    assert payload["imputed_value"] == "1200"


def test_build_fdrs_data_includes_imputed_only_rows():
    combined = [{
        "ISO3": "SYR",
        "DonCode": "DSYR001",
        "year": 2024,
        "KPI_code": "KPI_PeopleVol",
        "Value": None,
        "ReportedValue": None,
        "ImputedValue": "1200",
        "ValueStatus": "Imputed",
        "State": None,
    }]
    rows = build_fdrs_data(combined)
    assert len(rows) == 1
    assert rows[0]["Value"] == ""
    assert rows[0]["ImputedValue"] == "1200"
    assert rows[0]["State"] is None or rows[0]["State"] == ""


def test_build_ready_to_import_copies_value_into_published_only_for_state_500():
    assignment_rows = [{"period_name": "2024", "iso3": "SYR", "assignment_entity_status_id": 42}]
    form_item_rows = [{"bank_id": 7, "item_id": 900}]
    indicator_bank_rows = [{"id": 7, "fdrs_kpi_code": "KPI_PeopleVol"}]

    def one(state):
        return build_ready_to_import_from_new_pipeline(
            [{
                "ISO3": "SYR",
                "year": "2024",
                "BaseKPI": "KPI_PeopleVol",
                "KPI_code": "KPI_PeopleVol",
                "Value": "15",
                "State": state,
            }],
            {},
            assignment_rows,
            form_item_rows,
            indicator_bank_rows,
        )[0]

    published = one(500)
    submitted = one(300)
    assert published["value"] == "15"
    assert published["published_value"] == "15"
    assert submitted["value"] == "15"
    assert submitted["published_value"] == ""
    assert submitted["published_disagg_data"] == ""


def test_build_ready_to_import_sets_not_applicable_from_is_data_not_collected():
    fdrs_data = [
        {
            "ISO3": "SYR",
            "year": "2024",
            "BaseKPI": "KPI_PeopleVol",
            "KPI_code": "KPI_PeopleVol_IsDataNotCollected",
            "Value": "",
        },
    ]
    assignment_rows = [{"period_name": "2024", "iso3": "SYR", "assignment_entity_status_id": 42}]
    form_item_rows = [{"bank_id": 7, "item_id": 900}]
    indicator_bank_rows = [{"id": 7, "fdrs_kpi_code": "KPI_PeopleVol"}]
    rows = build_ready_to_import_from_new_pipeline(
        fdrs_data,
        {},
        assignment_rows,
        form_item_rows,
        indicator_bank_rows,
    )
    assert len(rows) == 1
    assert rows[0]["value"] == ""
    assert rows[0]["not_applicable"] == "true"
    assert rows[0]["data_not_available"] == ""


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


def test_encode_fdrs_document_url_percent_encodes_spaces():
    raw = "https://data-api.ifrc.org/documents/US/Annual Report_USA_2024_en.pdf"
    enc = encode_fdrs_document_url(raw)
    assert " " not in enc
    assert "Annual%20Report_USA_2024_en.pdf" in enc


def test_fetch_fdrs_document_bytes_success(monkeypatch):
    class FakeResp:
        status = 200

        def read(self):
            return b"%PDF-1.4"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "fdrs_documents_sync.urllib.request.urlopen",
        lambda req, timeout=120: FakeResp(),
    )
    data, status = fetch_fdrs_document_bytes("https://example.test/doc/a b.pdf")
    assert status == 200
    assert data == b"%PDF-1.4"


def test_fetch_fdrs_document_bytes_403(monkeypatch):
    import urllib.error

    def _raise(req, timeout=120):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", hdrs=None, fp=None)

    monkeypatch.setattr("fdrs_documents_sync.urllib.request.urlopen", _raise)
    data, status = fetch_fdrs_document_bytes("https://example.test/doc/forbidden.pdf")
    assert status == 403
    assert data is None


def test_fdrs_url_without_duplicate_suffix():
    paraguay = (
        "https://data-api.ifrc.org/documents/PY/"
        "audited Financial Statement_Paraguay_2016_es_1.pdf"
    )
    assert fdrs_url_without_duplicate_suffix(paraguay) == (
        "https://data-api.ifrc.org/documents/PY/"
        "audited Financial Statement_Paraguay_2016_es.pdf"
    )
    assert fdrs_url_without_duplicate_suffix("https://x/a_12.docx") == "https://x/a.docx"
    assert fdrs_url_without_duplicate_suffix("https://x/a_2016_es.pdf") is None
    assert fdrs_url_without_duplicate_suffix("https://x/Statutes_Gambia_0.doc") is None
    assert fdrs_url_without_duplicate_suffix("https://x/file.pdf") is None


def test_fetch_fdrs_document_bytes_retries_without_duplicate_suffix(monkeypatch):
    import urllib.error

    class FakeResp:
        status = 200

        def read(self):
            return b"%PDF-1.4"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    calls = []

    def _open(req, timeout=120):
        calls.append(req.full_url)
        if req.full_url.endswith("_1.pdf"):
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", hdrs=None, fp=None)
        return FakeResp()

    monkeypatch.setattr("fdrs_documents_sync.urllib.request.urlopen", _open)
    data, status = fetch_fdrs_document_bytes("https://example.test/doc/file_es_1.pdf")
    assert status == 200
    assert data == b"%PDF-1.4"
    assert len(calls) == 2
    assert calls[0].endswith("file_es_1.pdf")
    assert calls[1].endswith("file_es.pdf")


def test_fetch_fdrs_document_bytes_keeps_403_when_suffix_retry_fails(monkeypatch):
    import urllib.error

    def _raise(req, timeout=120):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", hdrs=None, fp=None)

    monkeypatch.setattr("fdrs_documents_sync.urllib.request.urlopen", _raise)
    data, status = fetch_fdrs_document_bytes("https://example.test/doc/file_es_1.pdf")
    assert status == 403
    assert data is None


def test_should_attempt_download_skips_when_already_stored(monkeypatch):
    class Doc:
        file_pending = False
        storage_path = "country/1/99/file.pdf"
        source_url = "https://example.test/same.pdf"

    monkeypatch.setattr("fdrs_documents_sync._fdrs_local_file_exists", lambda _path: True)
    row = {"source_url": "https://example.test/same.pdf", "is_public": True}
    assert _should_attempt_download(row, Doc()) is False


def test_should_attempt_download_skips_private_documents():
    row = {"source_url": "https://example.test/doc.pdf", "is_public": False}
    assert _should_attempt_download(row, None) is False


def test_should_attempt_download_retries_when_storage_path_missing_on_disk(monkeypatch):
    class Doc:
        file_pending = False
        storage_path = "country/1/99/file.pdf"
        source_url = "https://example.test/same.pdf"

    monkeypatch.setattr("fdrs_documents_sync._fdrs_local_file_exists", lambda _path: False)
    row = {"source_url": "https://example.test/same.pdf", "is_public": True}
    assert _should_attempt_download(row, Doc()) is True


def test_fdrs_document_is_public_visibility_private_and_public_codes():
    assert fdrs_document_is_public_visibility("Validated (Private)", public_code=0) is False
    assert fdrs_document_is_public_visibility("Validated (Public)", public_code=1) is True
    assert fdrs_document_is_public_visibility("Under Validation (Public)", public_code=2) is True


def test_build_document_import_plan_marks_under_validation_public_as_public():
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
    assert plan[0]["is_public"] is True


def test_resolve_download_outcome_keeps_existing_file_on_403(monkeypatch):
    class Doc:
        storage_path = "country/1/99/file.pdf"
        file_pending = False

    monkeypatch.setattr("fdrs_documents_sync._fdrs_local_file_exists", lambda _path: True)
    data, pending = _resolve_download_outcome(Doc(), 403, None)
    assert data is None
    assert pending is False


def test_resolve_download_outcome_pending_on_403_when_local_file_missing(monkeypatch):
    class Doc:
        storage_path = "country/1/99/file.pdf"
        file_pending = False

    monkeypatch.setattr("fdrs_documents_sync._fdrs_local_file_exists", lambda _path: False)
    data, pending = _resolve_download_outcome(Doc(), 403, None)
    assert data is None
    assert pending is True


def test_resolve_download_outcome_pending_when_no_file_and_404():
    data, pending = _resolve_download_outcome(None, 404, None)
    assert data is None
    assert pending is True


def test_fdrs_url_is_downloadable():
    from fdrs_documents_sync import fdrs_url_is_downloadable

    assert fdrs_url_is_downloadable(200) is True
    assert fdrs_url_is_downloadable(206) is True
    assert fdrs_url_is_downloadable(403) is False
    assert fdrs_url_is_downloadable(None) is False


def test_resolve_fdrs_source_url_http_status_clears_on_local_file():
    from fdrs_documents_sync import resolve_fdrs_source_url_http_status

    assert resolve_fdrs_source_url_http_status(
        is_public=True,
        source_url="https://example.test/doc.pdf",
        file_pending=False,
        has_local_file=True,
        probe_status=403,
        existing_status=403,
    ) is None


def test_resolve_fdrs_source_url_http_status_stores_403():
    from fdrs_documents_sync import resolve_fdrs_source_url_http_status

    assert resolve_fdrs_source_url_http_status(
        is_public=True,
        source_url="https://example.test/doc.pdf",
        file_pending=True,
        has_local_file=False,
        probe_status=403,
    ) == 403


def test_resolve_fdrs_source_url_http_status_empty_url():
    from fdrs_documents_sync import resolve_fdrs_source_url_http_status

    assert resolve_fdrs_source_url_http_status(
        is_public=True,
        source_url="",
        file_pending=True,
        has_local_file=False,
        probe_status=None,
    ) == 0


def test_resolve_fdrs_source_url_http_status_private_doc():
    from fdrs_documents_sync import resolve_fdrs_source_url_http_status

    assert resolve_fdrs_source_url_http_status(
        is_public=False,
        source_url="https://example.test/doc.pdf",
        file_pending=True,
        has_local_file=False,
        probe_status=403,
    ) is None


def test_document_progress_percent_scales_within_range():
    from fdrs_documents_sync import _document_progress_percent

    assert _document_progress_percent(0, 100, progress_start_pct=82.0, progress_end_pct=94.0) == 82.0
    assert _document_progress_percent(50, 100, progress_start_pct=82.0, progress_end_pct=94.0) == 88.0
    assert _document_progress_percent(100, 100, progress_start_pct=82.0, progress_end_pct=94.0) == 94.0


def test_check_cancel_raises_fdrs_sync_cancelled():
    from fdrs_documents_sync import _check_cancel
    from fdrs_sync_constants import FdrsSyncCancelled

    raised = False
    try:
        _check_cancel(lambda: True)
    except FdrsSyncCancelled:
        raised = True
    assert raised
    _check_cancel(lambda: False)
    _check_cancel(None)


def test_years_from_fdrs_data_dedupes_and_sorts():
    years = years_from_fdrs_data(
        [
            {"year": "2024"},
            {"year": 2018},
            {"year": "2024-01-01"},
            {"year": ""},
            {"year": None},
            {"year": "nope"},
        ]
    )
    assert years == [2018, 2024]


def test_plan_missing_fdrs_assignments_creates_period_and_aes():
    plan = plan_missing_fdrs_assignments(
        years=[2018, 2024],
        country_iso3_to_id={"KEN": 10, "FRA": 20},
        existing_period_names={"2024"},
        existing_period_iso3={("2024", "KEN")},
    )
    assert plan["periods_to_create"] == ["2018"]
    assert plan["target_pairs"] == 4
    aes = {(row["period_name"], row["iso3"], row["country_id"]) for row in plan["aes_to_create"]}
    assert aes == {
        ("2018", "FRA", 20),
        ("2018", "KEN", 10),
        ("2024", "FRA", 20),
    }


def test_plan_missing_fdrs_assignments_noop_when_complete():
    plan = plan_missing_fdrs_assignments(
        years=[2024],
        country_iso3_to_id={"KEN": 10},
        existing_period_names={"2024"},
        existing_period_iso3={("2024", "KEN")},
    )
    assert plan["periods_to_create"] == []
    assert plan["aes_to_create"] == []
    assert plan["target_pairs"] == 1
