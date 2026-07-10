"""Unit tests for orphaned P&B progress build recovery."""

from __future__ import annotations

from unittest.mock import patch

from app.pb_progress.service import PBProgressService


def _reset_service_state() -> None:
    PBProgressService._loaded_status = False
    PBProgressService._state = {
        "status": "idle",
        "job_id": None,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "build_stage": None,
        "build_pid": None,
        "output_names": [],
    }


class TestPBProgressReconcile:
    def setup_method(self) -> None:
        _reset_service_state()

    def test_reconcile_dead_pid_marks_failed(self) -> None:
        PBProgressService._state.update(
            {
                "status": "running",
                "build_pid": 99_999_999,
                "build_stage": "figures",
                "job_id": "job-dead",
            }
        )
        with patch.object(PBProgressService, "_persist_status"):
            PBProgressService._reconcile_running_status()
        assert PBProgressService._state["status"] == "failed"
        assert PBProgressService._state["build_pid"] is None
        assert "restarted" in (PBProgressService._state["error"] or "").lower()

    def test_reconcile_missing_build_pid_marks_failed_when_stale(self) -> None:
        PBProgressService._state.update(
            {
                "status": "running",
                "build_stage": "figures",
                "job_id": "job-legacy",
                "started_at": "2020-01-01T00:00:00+00:00",
                "heartbeat": "2020-01-01T00:00:00+00:00",
            }
        )
        with patch.object(PBProgressService, "_persist_status"):
            PBProgressService._reconcile_running_status()
        assert PBProgressService._state["status"] == "failed"

    def test_reconcile_missing_build_pid_keeps_fresh_run(self) -> None:
        PBProgressService._state.update(
            {
                "status": "running",
                "build_stage": "preparing",
                "job_id": "job-starting",
                "heartbeat": PBProgressService._now_iso(),
                "started_at": PBProgressService._now_iso(),
            }
        )
        with patch.object(PBProgressService, "_persist_status"):
            PBProgressService._reconcile_running_status()
        assert PBProgressService._state["status"] == "running"

    def test_reconcile_keeps_live_subprocess_running(self) -> None:
        PBProgressService._state.update(
            {
                "status": "running",
                "build_pid": 42_424,
                "build_stage": "figures",
                "heartbeat": PBProgressService._now_iso(),
                "started_at": PBProgressService._now_iso(),
                "job_id": "job-live",
            }
        )
        with (
            patch.object(PBProgressService, "_persist_status"),
            patch.object(PBProgressService, "_process_is_alive", return_value=True),
        ):
            PBProgressService._reconcile_running_status()
        assert PBProgressService._state["status"] == "running"

    def test_is_run_active_false_for_dead_pid(self) -> None:
        persisted = {
            "status": "running",
            "build_pid": 99_999_999,
            "heartbeat": PBProgressService._now_iso(),
        }
        assert PBProgressService._is_run_active(persisted) is False
