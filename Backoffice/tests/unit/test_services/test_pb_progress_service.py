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
    PBProgressService._build_process = None
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

    def test_store_excel_replaces_workbook_without_archiving(self, app) -> None:
        with app.app_context():
            with patch.object(PBProgressService, "workbook_exists", return_value=True), patch(
                "plugins.pb_progress.db_source.validate_uploaded_workbook",
                return_value={"valid": True, "warnings": []},
            ), patch.object(PBProgressService, "_import_system_config_after_excel_upload", return_value={"excel": {}}), patch(
                "plugins.pb_progress.service.storage_service.upload"
            ) as upload_mock, patch.object(PBProgressService, "_persist_status"):
                result = PBProgressService.store_excel(
                    DEFAULT_VERSION,
                    _file_storage("Updated.xlsx"),
                )
        upload_mock.assert_called_once()
        assert "archived_workbook" not in result
        assert "workbook_history" not in result

    def test_store_excel_first_upload(self, app) -> None:
        with app.app_context():
            with patch.object(PBProgressService, "workbook_exists", return_value=False), patch(
                "plugins.pb_progress.db_source.validate_uploaded_workbook",
                return_value={"valid": True, "warnings": []},
            ), patch.object(PBProgressService, "_import_system_config_after_excel_upload", return_value={"excel": {}}), patch(
                "plugins.pb_progress.service.storage_service.upload"
            ), patch.object(PBProgressService, "_persist_status"):
                result = PBProgressService.store_excel(
                    DEFAULT_VERSION,
                    _file_storage(),
                )
        assert "archived_workbook" not in result


class TestPBProgressStatusSync:
    def setup_method(self) -> None:
        _reset_service_state()

    def test_sync_status_from_storage_merges_persisted_running(self, app) -> None:
        persisted = {
            "status": "running",
            "job_id": "remote-job",
            "build_stage": "figures",
            "started_at": "2026-01-01T00:00:00+00:00",
        }
        with app.app_context():
            with patch.object(PBProgressService, "_reload_status_from_storage", return_value=persisted):
                PBProgressService._sync_status_from_storage(DEFAULT_VERSION)
        state = PBProgressService._state_for(DEFAULT_VERSION)
        assert state["status"] == "running"
        assert state["job_id"] == "remote-job"

    def test_sync_status_skips_when_local_build_active(self, app) -> None:
        local = {"status": "running", "job_id": "local-job", "build_stage": "html"}
        PBProgressService._state_for(DEFAULT_VERSION).update(local)
        PBProgressService._build_version = DEFAULT_VERSION
        PBProgressService._build_thread = type("T", (), {"is_alive": lambda self: True})()
        persisted = {"status": "running", "job_id": "remote-job", "build_stage": "figures"}
        with app.app_context():
            with patch.object(PBProgressService, "_reload_status_from_storage", return_value=persisted):
                PBProgressService._sync_status_from_storage(DEFAULT_VERSION)
        state = PBProgressService._state_for(DEFAULT_VERSION)
        assert state["job_id"] == "local-job"
        assert state["build_stage"] == "html"


class TestPBProgressCancelGeneration:
    def setup_method(self) -> None:
        _reset_service_state()

    def test_cancel_generation_marks_cancelled(self, app) -> None:
        state = PBProgressService._state_for(DEFAULT_VERSION)
        state.update({"status": "running", "job_id": "job-cancel"})
        with app.app_context():
            with patch.object(PBProgressService, "_ensure_status_loaded"), patch.object(
                PBProgressService, "_sync_status_from_storage"
            ), patch.object(PBProgressService, "_persist_status"), patch.object(
                PBProgressService, "_terminate_build_process"
            ), patch.object(PBProgressService, "get_status", return_value={"status": "cancelled"}):
                result = PBProgressService.cancel_generation(DEFAULT_VERSION)
        assert result["status"] == "cancelled"
        assert state["status"] == "cancelled"
        assert state["job_id"] is None
        assert state["build_stage"] is None

    def test_cancel_generation_rejects_when_idle(self, app) -> None:
        with app.app_context():
            with pytest.raises(RuntimeError, match="in progress"):
                PBProgressService.cancel_generation(DEFAULT_VERSION)


class TestPBProgressCopyOutputsToStorage:
    def setup_method(self) -> None:
        _reset_service_state()

    def test_copy_outputs_uploads_publishable_files(self, app, tmp_path) -> None:
        output_dir = tmp_path / "report" / "output"
        output_dir.mkdir(parents=True)
        (output_dir / "pb-report.html").write_bytes(b"<html></html>")
        (output_dir / "pb-report-english.pdf").write_bytes(b"%PDF")
        (output_dir / "pb-report.pdf").write_bytes(b"%PDF-default")
        (output_dir / "_internal.txt").write_bytes(b"skip")

        uploads: list[tuple[str, str, bytes]] = []

        def fake_upload(category, rel_path, data):
            uploads.append((category, rel_path, data))
            return rel_path

        with app.app_context():
            with patch.object(PBProgressService, "_report_output_dir", return_value=output_dir), patch(
                "plugins.pb_progress.service.storage_service.upload",
                side_effect=fake_upload,
            ), patch(
                "plugins.pb_progress.service.storage_service.exists",
                return_value=True,
            ), patch(
                "plugins.pb_progress.service.storage_service.get_size",
                return_value=123,
            ):
                copied = PBProgressService._copy_outputs_to_storage(DEFAULT_VERSION)

        assert sorted(copied) == ["pb-report-english.pdf", "pb-report.html"]
        assert len(uploads) == 2
        assert all(category == "pb_progress" for category, _, _ in uploads)
        rel_paths = {rel for _, rel, _ in uploads}
        assert rel_paths == {
            "versions/2025-2026/output/pb-report.html",
            "versions/2025-2026/output/pb-report-english.pdf",
        }

    def test_copy_outputs_raises_when_storage_verify_fails(self, app, tmp_path) -> None:
        output_dir = tmp_path / "report" / "output"
        output_dir.mkdir(parents=True)
        (output_dir / "pb-report.html").write_bytes(b"<html></html>")

        with app.app_context():
            with patch.object(PBProgressService, "_report_output_dir", return_value=output_dir), patch(
                "plugins.pb_progress.service.storage_service.upload",
                return_value="versions/2025-2026/output/pb-report.html",
            ), patch(
                "plugins.pb_progress.service.storage_service.exists",
                return_value=False,
            ):
                with pytest.raises(RuntimeError, match="not persisted"):
                    PBProgressService._copy_outputs_to_storage(DEFAULT_VERSION)


class TestPBProgressOutputRetention:
    def setup_method(self) -> None:
        _reset_service_state()

    def test_get_status_rebuilds_outputs_when_cancelled(self, app) -> None:
        state = PBProgressService._state_for(DEFAULT_VERSION)
        state.update(
            {
                "status": "cancelled",
                "output_names": ["pb-report.html"],
            }
        )
        with app.app_context():
            with patch.object(PBProgressService, "_ensure_status_loaded"), patch.object(
                PBProgressService, "_sync_status_from_storage"
            ), patch("plugins.pb_progress.service.storage_service.exists", return_value=True), patch(
                "plugins.pb_progress.service.storage_service.get_size", return_value=1024
            ), patch.object(
                PBProgressService, "_output_url", return_value="/admin/data-exploration/pb-progress/2025-2026/output/pb-report.html"
            ):
                status = PBProgressService.get_status(DEFAULT_VERSION)
        assert len(status["outputs"]) == 1
        assert status["outputs"][0]["name"] == "pb-report.html"

    def test_start_generation_preserves_output_names(self, app) -> None:
        state = PBProgressService._state_for(DEFAULT_VERSION)
        state.update(
            {
                "status": "idle",
                "output_names": ["pb-report.html", "pb-report-pdf-all.zip"],
            }
        )
        with app.app_context():
            with patch.object(PBProgressService, "_check_build_prerequisites"), patch.object(
                PBProgressService, "_ensure_status_loaded"
            ), patch.object(PBProgressService, "_reload_status_from_storage", return_value=dict(state)), patch.object(
                PBProgressService, "_clear_orphaned_run"
            ), patch(
                "plugins.pb_progress.service.PBProgressDataStore.get_data_source", return_value="excel"
            ), patch(
                "plugins.pb_progress.service.storage_service.exists", return_value=True
            ), patch(
                "plugins.pb_progress.service.PBProgressDataStore.get_version_status", return_value=dict(state)
            ), patch(
                "plugins.pb_progress.service.PBProgressDataStore.try_set_version_status_if_not_running",
                return_value=True,
            ) as claim_mock, patch("plugins.pb_progress.service.threading.Thread") as thread_cls:
                thread_cls.return_value.start = MagicMock()
                PBProgressService.start_generation(DEFAULT_VERSION)
        running_status = claim_mock.call_args[0][1]
        assert running_status["output_names"] == ["pb-report.html", "pb-report-pdf-all.zip"]


class TestPBProgressRenderStack:
    def test_verify_render_stack_smoke(self) -> None:
        PBProgressService._verify_render_stack()

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
