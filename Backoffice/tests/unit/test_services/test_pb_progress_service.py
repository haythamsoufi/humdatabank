"""Unit tests for P&B progress orphan build recovery."""

from __future__ import annotations

from unittest.mock import patch

from app.pb_progress.service import PBProgressService


def _reset_service_state() -> None:
    PBProgressService._loaded_status = False
    PBProgressService._build_thread = None
    PBProgressService._state = {
        "status": "idle",
        "job_id": None,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "build_stage": None,
        "output_names": [],
    }


class TestPBProgressOrphanRecovery:
    def setup_method(self) -> None:
        _reset_service_state()

    def test_clear_orphaned_run_marks_failed_without_thread(self) -> None:
        PBProgressService._state.update(
            {
                "status": "running",
                "build_stage": "figures",
                "job_id": "job-orphan",
            }
        )
        with patch.object(PBProgressService, "_persist_status"):
            PBProgressService._clear_orphaned_run()
        assert PBProgressService._state["status"] == "failed"
        assert "restarted" in (PBProgressService._state["error"] or "").lower()

    def test_clear_orphaned_run_keeps_active_thread(self) -> None:
        PBProgressService._state.update(
            {
                "status": "running",
                "build_stage": "figures",
                "job_id": "job-live",
            }
        )
        PBProgressService._build_thread = type(
            "T", (), {"is_alive": lambda self: True}
        )()
        with patch.object(PBProgressService, "_persist_status"):
            PBProgressService._clear_orphaned_run()
        assert PBProgressService._state["status"] == "running"
