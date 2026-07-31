"""Unit tests for P&B progress orphan build recovery and workbook upload."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.datastructures import FileStorage

from plugins.pb_progress.service import PBProgressService
from plugins.pb_progress.versions import DEFAULT_VERSION


def _reset_service_state() -> None:
    PBProgressService._loaded_versions = set()
    PBProgressService._legacy_migrated = True
    PBProgressService._build_thread = None
    PBProgressService._build_version = None
    PBProgressService._states = {
        DEFAULT_VERSION: {
            "status": "idle",
            "job_id": None,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "build_stage": None,
            "output_names": [],
        }
    }


def _dummy_workbook_bytes() -> bytes:
    return b"PK dummy xlsx"


def _file_storage(name: str = "SG Report.xlsx") -> FileStorage:
    return FileStorage(
        stream=io.BytesIO(_dummy_workbook_bytes()),
        filename=name,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class TestPBProgressOrphanRecovery:
    def setup_method(self) -> None:
        _reset_service_state()

    def test_clear_orphaned_run_marks_failed_without_thread(self) -> None:
        state = PBProgressService._state_for(DEFAULT_VERSION)
        state.update(
            {
                "status": "running",
                "build_stage": "figures",
                "job_id": "job-orphan",
            }
        )
        with patch.object(PBProgressService, "_persist_status"):
            PBProgressService._clear_orphaned_run(DEFAULT_VERSION)
        assert state["status"] == "failed"
        assert "restarted" in (state["error"] or "").lower()

    def test_clear_orphaned_run_keeps_active_thread(self) -> None:
        state = PBProgressService._state_for(DEFAULT_VERSION)
        state.update(
            {
                "status": "running",
                "build_stage": "figures",
                "job_id": "job-live",
            }
        )
        PBProgressService._build_version = DEFAULT_VERSION
        PBProgressService._build_thread = type(
            "T", (), {"is_alive": lambda self: True}
        )()
        with patch.object(PBProgressService, "_persist_status"):
            PBProgressService._clear_orphaned_run(DEFAULT_VERSION)
        assert state["status"] == "running"


class TestPBProgressWorkbookUpload:
    def setup_method(self) -> None:
        _reset_service_state()

    def test_store_excel_archives_previous_workbook(self, app) -> None:
        archived = {"id": "archive-1", "filename": "SG Report.xlsx"}
        with app.app_context():
            with patch.object(PBProgressService, "workbook_exists", return_value=True), patch.object(
                PBProgressService, "_archive_current_workbook", return_value=archived
            ) as archive_mock, patch(
                "plugins.pb_progress.db_source.validate_uploaded_workbook",
                return_value={"valid": True, "warnings": []},
            ), patch.object(PBProgressService, "_import_system_config_after_excel_upload", return_value={"excel": {}}), patch.object(
                PBProgressService, "list_workbook_history", return_value=[archived]
            ), patch(
                "plugins.pb_progress.service.storage_service.upload"
            ) as upload_mock, patch.object(PBProgressService, "_persist_status"):
                result = PBProgressService.store_excel(
                    DEFAULT_VERSION,
                    _file_storage("Updated.xlsx"),
                )
        archive_mock.assert_called_once_with(DEFAULT_VERSION)
        upload_mock.assert_called_once()
        assert result["archived_workbook"] == archived

    def test_store_excel_first_upload_skips_archive(self, app) -> None:
        with app.app_context():
            with patch.object(PBProgressService, "workbook_exists", return_value=False), patch.object(
                PBProgressService, "_archive_current_workbook"
            ) as archive_mock, patch(
                "plugins.pb_progress.db_source.validate_uploaded_workbook",
                return_value={"valid": True, "warnings": []},
            ), patch.object(PBProgressService, "_import_system_config_after_excel_upload", return_value={"excel": {}}), patch.object(
                PBProgressService, "list_workbook_history", return_value=[]
            ), patch(
                "plugins.pb_progress.service.storage_service.upload"
            ), patch.object(PBProgressService, "_persist_status"):
                result = PBProgressService.store_excel(
                    DEFAULT_VERSION,
                    _file_storage(),
                )
        archive_mock.assert_not_called()
        assert "archived_workbook" not in result


class TestPBProgressRenderStack:
    def test_render_stack_error_detail_detects_missing_cairo(self) -> None:
        stderr = "OSError: no library called \"cairo-2\" was found"
        detail = PBProgressService._render_stack_error_detail("", stderr)
        assert "cairo" in detail.lower()

    def test_render_stack_error_detail_detects_missing_weasyprint(self) -> None:
        stderr = "ModuleNotFoundError: No module named 'weasyprint'"
        detail = PBProgressService._render_stack_error_detail("", stderr)
        assert "weasyprint" in detail.lower()

    def test_render_stack_error_detail_prefers_syntax_error_over_file_line(self) -> None:
        stderr = (
            'File "<string>", line 1\n'
            "    with tempfile.TemporaryDirectory() as tmp: pass\n"
            "    ^^^^\n"
            "SyntaxError: invalid syntax\n"
        )
        detail = PBProgressService._render_stack_error_detail("", stderr)
        assert "invalid syntax" in detail.lower()
