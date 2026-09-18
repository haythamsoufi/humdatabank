"""Unit tests for durable import change logs."""
from __future__ import annotations

import json
from unittest.mock import patch

from app.services.imports.import_change_log import (
    ImportChangeLogWriter,
    compact_import_value,
    is_valid_import_log_id,
    persist_import_change_log,
    staged_payload_changes,
)


class TestImportLogId:
    def test_accepts_32_hex(self):
        assert is_valid_import_log_id("a" * 32)
        assert is_valid_import_log_id("0123456789abcdef" * 2)

    def test_rejects_other_shapes(self):
        assert not is_valid_import_log_id("short")
        assert not is_valid_import_log_id("g" * 32)
        assert not is_valid_import_log_id("")
        assert not is_valid_import_log_id(None)


class TestCompactImportValue:
    def test_passthrough_scalars(self):
        assert compact_import_value(None) is None
        assert compact_import_value("") is None
        assert compact_import_value(12) == 12
        assert compact_import_value(True) is True

    def test_truncates_long_text(self):
        text = "x" * 500
        out = compact_import_value(text, limit=20)
        assert out.endswith("…")
        assert len(out) == 21


class TestStagedPayloadChanges:
    def test_fields_and_matrices(self):
        rows = staged_payload_changes(
            {
                "fields": {"10": "hello", "11": {"value": 3, "disagg_data": {"mode": "sex"}}},
                "matrices": {"20": {"a": 1}},
                "dynamic_indicators": [{"name": "Floods", "value": 9}],
            }
        )
        assert rows[0]["op"] == "stage"
        assert rows[0]["item_id"] == "10"
        assert rows[0]["new_value"] == "hello"
        assert rows[1]["new_value"] == 3
        assert rows[2]["item_id"] == "20"
        assert rows[3]["label"] == "Floods"

    def test_empty_payload(self):
        assert staged_payload_changes(None) == []
        assert staged_payload_changes({}) == []


class TestImportChangeLogWriter:
    def test_writes_summary_and_jsonl(self, tmp_path):
        log_id = "b" * 32
        persist_import_change_log(
            log_id=log_id,
            kind="assignment_excel",
            meta={"filename": "form.xlsx"},
            changes=[
                {"op": "insert", "item_id": 1, "iso3": "KEN", "new_value": 5},
                {"op": "update", "item_id": 2, "old_value": 1, "new_value": 2},
            ],
            stats={"updated_count": 2, "success": True},
            log_dir=str(tmp_path),
        )
        summary = json.loads((tmp_path / f"{log_id}.json").read_text(encoding="utf-8"))
        assert summary["kind"] == "assignment_excel"
        assert summary["change_count"] == 2
        assert summary["stats"]["updated_count"] == 2
        lines = (tmp_path / f"{log_id}.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["iso3"] == "KEN"
        assert first["new_value"] == 5

    def test_context_manager_finalizes_on_error(self, tmp_path):
        log_id = "c" * 32
        try:
            with ImportChangeLogWriter(log_id, kind="upr_excel", log_dir=str(tmp_path)) as writer:
                writer.record({"op": "insert", "item_id": 9, "new_value": 1})
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        summary = json.loads((tmp_path / f"{log_id}.json").read_text(encoding="utf-8"))
        assert summary["change_count"] == 1
        assert summary["stats"]["success"] is False


class TestSetImportAuditDetails:
    def test_stores_change_log_url(self):
        from app.services.imports.import_change_log import set_import_audit_details

        captured = {}

        def _capture(**fields):
            captured.update(fields)

        log_id = "d" * 32
        with patch("app.services.imports.import_change_log.set_audit_details", side_effect=_capture):
            set_import_audit_details(
                log_id=log_id,
                import_kind="fdrs_data_sync",
                filename="n/a",
                dry_run=True,
            )
        assert captured["job_id"] == log_id
        assert captured["import_kind"] == "fdrs_data_sync"
        assert captured["change_log_url"].endswith(f"/admin/import-logs/{log_id}")
        assert captured["dry_run"] is True
