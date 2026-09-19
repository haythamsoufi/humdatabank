"""Unit tests for durable import change logs."""
from __future__ import annotations

import json
from unittest.mock import patch

from app.services.imports.import_change_log import (
    ImportChangeLogWriter,
    compact_import_value,
    count_import_log_changes,
    is_noop_import_change,
    is_valid_import_log_id,
    iter_import_log_changes,
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


class TestIsNoopImportChange:
    def test_identical_update_is_noop(self):
        assert is_noop_import_change({
            "op": "update",
            "old_value": "9365",
            "new_value": "9365",
        })

    def test_changed_update_is_not_noop(self):
        assert not is_noop_import_change({
            "op": "update",
            "old_value": "1",
            "new_value": "2",
        })

    def test_insert_is_never_noop(self):
        assert not is_noop_import_change({"op": "insert", "new_value": None})

    def test_same_disagg_different_key_order_is_noop(self):
        assert is_noop_import_change({
            "op": "update",
            "old_value": "56",
            "new_value": "56",
            "old_disagg": {"mode": "sex_age", "values": {"direct": {"male_50_": 7, "female_18_49": 15}}},
            "new_disagg": {"values": {"direct": {"female_18_49": 15, "male_50_": 7}}, "mode": "sex_age"},
        })

    def test_compacted_preview_same_pairs_is_noop(self):
        old = {
            "keys": 2,
            "preview": '{"mode": "sex_age", "values": {"direct": {"male_50_": 7, "female_18_49": 15}}}…',
        }
        new = {
            "keys": 2,
            "preview": '{"mode": "sex_age", "values": {"direct": {"female_18_49": 15, "male_50_": 7}}}…',
        }
        assert is_noop_import_change({
            "op": "update",
            "old_value": "56",
            "new_value": "56",
            "old_disagg": old,
            "new_disagg": new,
        })

    def test_truncated_previews_with_same_value_and_key_count_are_noop(self):
        assert is_noop_import_change({
            "op": "update",
            "old_value": "27332",
            "new_value": "27332",
            "old_disagg": {"keys": 2, "preview": '{"mode": "sex_age", "values": {"direct": {"female_unknown": 2}}}…'},
            "new_disagg": {"keys": 2, "preview": '{"mode": "sex_age", "values": {"direct": {"unknown_5_17": 1176}}}…'},
        })


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

    def test_skips_identical_before_after_updates(self, tmp_path):
        log_id = "e" * 32
        persist_import_change_log(
            log_id=log_id,
            kind="fdrs_data_sync",
            changes=[
                {"op": "update", "iso3": "SLE", "old_value": "9365", "new_value": "9365"},
                {"op": "insert", "iso3": "KEN", "new_value": 5},
                {"op": "update", "iso3": "BGD", "old_value": "16", "new_value": "99"},
            ],
            stats={"updated": 1, "inserted": 1, "unchanged": 1, "success": True},
            log_dir=str(tmp_path),
        )
        summary = json.loads((tmp_path / f"{log_id}.json").read_text(encoding="utf-8"))
        assert summary["change_count"] == 2
        assert summary["stats"]["unchanged"] == 1
        rows = list(iter_import_log_changes(log_id, log_dir=str(tmp_path)))
        assert [row["iso3"] for row in rows] == ["KEN", "BGD"]
        assert count_import_log_changes(log_id, log_dir=str(tmp_path)) == 2

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
