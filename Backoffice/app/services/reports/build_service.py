"""Background publish jobs for static report artifacts."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, ClassVar

from flask import current_app

from app import db
from app.models import ReportDefinition, ReportRun, User
from app.services.platform import storage_service
from app.services.reports.data_service import ReportDataService
from app.services.reports.export_service import ReportExportService
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)

STORAGE_CATEGORY = "reports"
BUILD_STAGES = ("preparing", "rendering_widgets", "html", "pdf", "saving")


class ReportBuildService:
    _lock: ClassVar[threading.Lock] = threading.Lock()
    _active_threads: ClassVar[dict[str, threading.Thread]] = {}

    @classmethod
    def start_publish(cls, report_id: int, user: User) -> ReportRun:
        with cls._lock:
            report = db.session.get(ReportDefinition, report_id)
            if not report:
                raise ValueError("Report not found")

            run_id = str(uuid.uuid4())
            run = ReportRun(
                id=run_id,
                report_id=report_id,
                status="queued",
                build_stage=BUILD_STAGES[0],
                triggered_by_id=user.id,
            )
            db.session.add(run)
            db.session.commit()

            app = current_app._get_current_object()
            thread = threading.Thread(
                target=cls._run_publish,
                args=(app, run_id, report_id, user.id),
                daemon=True,
                name=f"report-publish-{run_id[:8]}",
            )
            cls._active_threads[run_id] = thread
            thread.start()
            return run

    @classmethod
    def get_run(cls, run_id: str) -> ReportRun | None:
        return db.session.get(ReportRun, run_id)

    @classmethod
    def cancel_publish(cls, run_id: str) -> bool:
        run = db.session.get(ReportRun, run_id)
        if not run or run.status in {"completed", "failed", "cancelled"}:
            return False
        run.status = "cancelled"
        run.finished_at = utcnow()
        db.session.commit()
        return True

    @classmethod
    def _run_publish(cls, app, run_id: str, report_id: int, user_id: int) -> None:
        with app.app_context():
            run = db.session.get(ReportRun, run_id)
            if not run:
                return
            try:
                run.status = "running"
                run.started_at = utcnow()
                run.build_stage = BUILD_STAGES[0]
                db.session.commit()

                user = db.session.get(User, user_id)
                run.build_stage = BUILD_STAGES[1]
                db.session.commit()
                result = ReportDataService.execute_report(report_id, user)

                run.build_stage = BUILD_STAGES[2]
                db.session.commit()
                report = db.session.get(ReportDefinition, report_id)
                html_key = f"{report_id}/{run_id}/report.html"
                pdf_key = f"{report_id}/{run_id}/report.pdf"

                run.build_stage = BUILD_STAGES[3]
                db.session.commit()
                pdf_bytes = ReportExportService.export_pdf(report, result)

                run.build_stage = BUILD_STAGES[4]
                db.session.commit()
                storage_service.upload(STORAGE_CATEGORY, pdf_key, pdf_bytes)
                excel_bytes = ReportExportService.export_excel(report, result)
                xlsx_key = f"{report_id}/{run_id}/report.xlsx"
                storage_service.upload(STORAGE_CATEGORY, xlsx_key, excel_bytes)

                run.status = "completed"
                run.build_stage = "done"
                run.output_paths = {"pdf": pdf_key, "excel": xlsx_key, "html": html_key}
                run.finished_at = utcnow()
                db.session.commit()
            except Exception as exc:
                logger.exception("Report publish failed for run %s", run_id)
                run = db.session.get(ReportRun, run_id)
                if run:
                    run.status = "failed"
                    run.error = str(exc)
                    run.finished_at = utcnow()
                    db.session.commit()

    @classmethod
    def serialize_run(cls, run: ReportRun) -> dict[str, Any]:
        return {
            "id": run.id,
            "report_id": run.report_id,
            "status": run.status,
            "build_stage": run.build_stage,
            "error": run.error,
            "output_paths": run.output_paths,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }
