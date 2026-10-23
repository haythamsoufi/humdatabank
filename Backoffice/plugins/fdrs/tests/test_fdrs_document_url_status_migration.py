"""Unit tests for FDRS document URL status ↔ Backoffice migration enrichment."""
from __future__ import annotations

import hashlib
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
backoffice_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
fdrs_scripts = os.path.join(backoffice_dir, "plugins", "fdrs", "scripts")
for p in (backoffice_dir, fdrs_scripts):
    if p not in sys.path:
        sys.path.insert(0, p)

from export_fdrs_document_url_status import (  # noqa: E402
    MIGRATION_MIGRATED,
    MIGRATION_NOT_IN_BACKOFFICE,
    MIGRATION_PENDING_DOWNLOAD,
    document_import_key,
    enrich_rows_with_backoffice_migration,
)


def _expected_sync_import_key(doc: dict) -> str:
    """Mirror ``fdrs_documents_sync._fdrs_document_import_key`` without importing sync."""
    raw = "|".join(
        [
            (doc.get("don_code") or "").strip(),
            str(doc.get("year") or ""),
            str(doc.get("document_typeId") or ""),
            (doc.get("name") or "").strip(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def test_document_import_key_matches_sync_helper():
    doc = {
        "don_code": "DKI001",
        "year": 2023,
        "document_typeId": 12,
        "name": "Annual Report.pdf",
    }
    assert document_import_key(doc) == _expected_sync_import_key(doc)


def test_document_import_key_accepts_probe_row_field_names():
    catalog = {
        "don_code": "DKI001",
        "year": 2023,
        "document_typeId": 12,
        "name": "Annual Report.pdf",
    }
    probe = {
        "don_code": "DKI001",
        "year": 2023,
        "document_type_id": 12,
        "name": "Annual Report.pdf",
    }
    assert document_import_key(probe) == document_import_key(catalog)


def test_enrich_marks_migrated_pending_and_missing():
    key_ok = document_import_key(
        {"don_code": "A", "year": 2021, "document_typeId": 1, "name": "ok.pdf"}
    )
    key_pending = document_import_key(
        {"don_code": "B", "year": 2021, "document_typeId": 1, "name": "pending.pdf"}
    )
    key_missing = document_import_key(
        {"don_code": "C", "year": 2021, "document_typeId": 1, "name": "missing.pdf"}
    )

    rows = [
        {
            "don_code": "A",
            "year": 2021,
            "document_type_id": 1,
            "name": "ok.pdf",
            "downloadable": True,
        },
        {
            "don_code": "B",
            "year": 2021,
            "document_type_id": 1,
            "name": "pending.pdf",
            "downloadable": True,
        },
        {
            "don_code": "C",
            "year": 2021,
            "document_type_id": 1,
            "name": "missing.pdf",
            "downloadable": False,
        },
    ]
    index = {
        key_ok: {
            "backoffice_doc_id": 10,
            "file_pending": False,
            "file_migrated": True,
            "storage_path": "country/1/10/ok.pdf",
            "backoffice_source_url_http_status": None,
            "backoffice_is_public": True,
            "backoffice_status": "approved",
            "migration_status": MIGRATION_MIGRATED,
        },
        key_pending: {
            "backoffice_doc_id": 11,
            "file_pending": True,
            "file_migrated": False,
            "storage_path": "",
            "backoffice_source_url_http_status": 403,
            "backoffice_is_public": True,
            "backoffice_status": "approved",
            "migration_status": MIGRATION_PENDING_DOWNLOAD,
        },
    }

    counts = enrich_rows_with_backoffice_migration(rows, index)

    assert counts["file_migrated_count"] == 1
    assert counts["pending_download_count"] == 1
    assert counts["not_in_backoffice_count"] == 1
    assert counts["not_migrated_count"] == 2
    assert counts["migration_lookup_available"] == 1

    assert rows[0]["migration_status"] == MIGRATION_MIGRATED
    assert rows[0]["file_migrated"] is True
    assert rows[0]["in_backoffice"] is True
    assert rows[0]["fdrs_import_key"] == key_ok
    assert rows[0]["backoffice_doc_id"] == 10

    assert rows[1]["migration_status"] == MIGRATION_PENDING_DOWNLOAD
    assert rows[1]["file_migrated"] is False
    assert rows[1]["file_pending"] is True
    assert rows[1]["fdrs_import_key"] == key_pending

    assert rows[2]["migration_status"] == MIGRATION_NOT_IN_BACKOFFICE
    assert rows[2]["in_backoffice"] is False
    assert rows[2]["file_migrated"] is False
    assert rows[2]["fdrs_import_key"] == key_missing


def test_enrich_leaves_blank_when_lookup_unavailable():
    rows = [
        {
            "don_code": "A",
            "year": 2021,
            "document_type_id": 1,
            "name": "ok.pdf",
        }
    ]
    counts = enrich_rows_with_backoffice_migration(rows, None)
    assert counts["migration_lookup_available"] == 0
    assert counts["not_migrated_count"] == 0
    assert rows[0]["migration_status"] == ""
    assert rows[0]["in_backoffice"] == ""
    assert rows[0]["file_migrated"] == ""
    assert rows[0]["fdrs_import_key"] == ""
