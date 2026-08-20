"""Tests for single-document processing heartbeat and async reprocess dispatch."""

import threading
import time
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models import AIDocument
from app.routes.admin.ai_management import _auto_recover_stale_processing_documents
from app.routes.ai_documents.upload import (
    _mark_processing_stage,
    get_document_processing_stage_from_db,
    start_single_document_processing,
)
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE

pytestmark = [pytest.mark.unit]


def _create_processing_doc(db_session, admin_user, *, heartbeat_at=None, stage=None):
    doc = AIDocument(
        title="Heartbeat test",
        filename="test.pdf",
        file_type="pdf",
        file_size_bytes=100,
        storage_path="test.pdf",
        content_hash=f"hash-{uuid.uuid4().hex}",
        processing_status="processing",
        user_id=admin_user.id,
        processing_stage=stage,
        processing_heartbeat_at=heartbeat_at,
    )
    db_session.add(doc)
    db_session.commit()
    return doc


class TestProcessingStageHeartbeat:
    def test_mark_processing_stage_persists_columns(self, db_session, admin_user):
        doc = _create_processing_doc(db_session, admin_user)
        _mark_processing_stage(int(doc.id), "extracting")
        refreshed = AIDocument.query.get(doc.id)
        assert refreshed.processing_stage == "extracting"
        assert refreshed.processing_heartbeat_at is not None
        assert get_document_processing_stage_from_db(int(doc.id)) == "extracting"


class TestAutoRecoverStaleProcessing:
    def test_auto_recover_skips_doc_with_fresh_heartbeat(self, app, db_session, admin_user):
        from app.routes.ai_documents import upload as upload_mod

        upload_mod._document_processing_stage.clear()
        doc = _create_processing_doc(
            db_session,
            admin_user,
            heartbeat_at=datetime.utcnow(),
            stage="embedding",
        )
        doc.updated_at = datetime.utcnow() - timedelta(hours=2)
        db_session.commit()

        with app.app_context():
            app.config["AI_DOCS_AUTOFIX_STALE_PROCESSING_TIMEOUT_SECONDS"] = 60
            updated = _auto_recover_stale_processing_documents()

        assert updated == 0
        assert AIDocument.query.get(doc.id).processing_status == "processing"

    def test_auto_recover_marks_doc_without_heartbeat(self, app, db_session, admin_user):
        from app.routes.ai_documents import upload as upload_mod

        upload_mod._document_processing_stage.clear()
        doc = _create_processing_doc(db_session, admin_user)
        doc.updated_at = datetime.utcnow() - timedelta(hours=2)
        db_session.commit()

        with app.app_context():
            app.config["AI_DOCS_AUTOFIX_STALE_PROCESSING_TIMEOUT_SECONDS"] = 60
            updated = _auto_recover_stale_processing_documents()

        assert updated == 1
        db_session.expire_all()
        assert AIDocument.query.get(doc.id).processing_status == "failed"

    def test_auto_recover_marks_doc_with_stale_job_item(self, app, db_session, admin_user):
        """Days-old ai_job_items.processing rows must not keep the banner/docs stuck."""
        from app.models import AIJob, AIJobItem
        from app.routes.ai_documents import upload as upload_mod

        upload_mod._document_processing_stage.clear()
        doc = _create_processing_doc(db_session, admin_user)
        stale_at = datetime.utcnow() - timedelta(hours=6)
        doc.updated_at = stale_at
        doc.created_at = stale_at
        job = AIJob(
            id=str(uuid.uuid4()),
            job_type="docs.bulk_reprocess",
            user_id=admin_user.id,
            status="running",
            total_items=1,
            created_at=stale_at,
            started_at=stale_at,
        )
        db_session.add(job)
        db_session.flush()
        db_session.add(
            AIJobItem(
                job_id=job.id,
                item_index=0,
                entity_type="ai_document",
                entity_id=doc.id,
                status="processing",
                created_at=stale_at,
                updated_at=stale_at,
            )
        )
        db_session.commit()

        with app.app_context():
            app.config["AI_DOCS_AUTOFIX_STALE_PROCESSING_TIMEOUT_SECONDS"] = 60
            updated = _auto_recover_stale_processing_documents()

        assert updated == 1
        db_session.expire_all()
        assert AIDocument.query.get(doc.id).processing_status == "failed"

    def test_auto_recover_skips_doc_with_fresh_job_item(self, app, db_session, admin_user):
        from app.models import AIJob, AIJobItem
        from app.routes.ai_documents import upload as upload_mod

        upload_mod._document_processing_stage.clear()
        doc = _create_processing_doc(db_session, admin_user)
        doc.updated_at = datetime.utcnow() - timedelta(hours=2)
        job = AIJob(
            id=str(uuid.uuid4()),
            job_type="docs.bulk_reprocess",
            user_id=admin_user.id,
            status="running",
            total_items=1,
        )
        db_session.add(job)
        db_session.flush()
        db_session.add(
            AIJobItem(
                job_id=job.id,
                item_index=0,
                entity_type="ai_document",
                entity_id=doc.id,
                status="processing",
                updated_at=datetime.utcnow(),
            )
        )
        db_session.commit()

        with app.app_context():
            app.config["AI_DOCS_AUTOFIX_STALE_PROCESSING_TIMEOUT_SECONDS"] = 60
            updated = _auto_recover_stale_processing_documents()

        assert updated == 0
        assert AIDocument.query.get(doc.id).processing_status == "processing"


class TestDocumentProcessingStatusStuckDetection:
    """Regression coverage for document_processing_status's stuck-detection heartbeat
    logic: processing_heartbeat_at is never cleared between runs, so picking the first
    non-null candidate (instead of the most recent one) could let a stale heartbeat from
    a much older run outrank a fresh updated_at and cause a false "stuck" failure."""

    def _call_status(self, app, admin_user, doc_id, *, timeout_seconds=3600):
        from app.routes.ai_documents import upload as upload_mod

        upload_mod._document_processing_stage.clear()

        with patch(
            "app.routes.admin.shared.AuthorizationService.has_rbac_permission",
            return_value=True,
        ):
            from app.routes.admin.ai_management import document_processing_status

            with app.test_request_context(
                f"/admin/ai/documents/{doc_id}/status",
                method="GET",
            ):
                from flask_login import login_user

                login_user(admin_user)
                app.config["AI_DOCS_STUCK_NO_STAGE_TIMEOUT_SECONDS"] = timeout_seconds
                return document_processing_status(doc_id)

    def test_fresh_updated_at_beats_stale_heartbeat(self, app, db_session, admin_user):
        doc = _create_processing_doc(
            db_session,
            admin_user,
            heartbeat_at=datetime.utcnow() - timedelta(days=3),
        )
        doc.processing_status = "processing"
        doc.updated_at = datetime.utcnow()
        db_session.commit()

        self._call_status(app, admin_user, doc.id, timeout_seconds=3600)

        db_session.expire_all()
        refreshed = AIDocument.query.get(doc.id)
        # A 3-day-old heartbeat must not outrank a just-now updated_at: the doc isn't
        # actually stuck, so status polling must not flip it to "failed".
        assert refreshed.processing_status == "processing"

    def test_stale_heartbeat_and_updated_at_still_marked_failed(self, app, db_session, admin_user):
        doc = _create_processing_doc(
            db_session,
            admin_user,
            heartbeat_at=datetime.utcnow() - timedelta(hours=2),
        )
        doc.processing_status = "processing"
        doc.updated_at = datetime.utcnow() - timedelta(hours=2)
        # created_at defaults to "now" at insert time; it must also be backdated here,
        # or its freshness alone would (correctly) prevent stuck-detection regardless of
        # what the other two timestamps say — that's the whole point of the max() fix.
        doc.created_at = datetime.utcnow() - timedelta(hours=2)
        db_session.commit()

        self._call_status(app, admin_user, doc.id, timeout_seconds=60)

        db_session.expire_all()
        refreshed = AIDocument.query.get(doc.id)
        assert refreshed.processing_status == "failed"


class TestSingleDocumentDispatch:
    def test_start_single_document_processing_spawns_background_thread(self, app, db_session, admin_user):
        doc = _create_processing_doc(db_session, admin_user, stage="pending")
        doc.processing_status = "pending"
        db_session.commit()

        started = threading.Event()

        def fake_process(document_id, file_path, filename):
            started.set()

        with patch("app.routes.ai_documents.upload._process_document_sync", side_effect=fake_process):
            start_single_document_processing(
                app,
                int(doc.id),
                file_path="/tmp/fake.pdf",
                filename="fake.pdf",
            )
            assert started.wait(timeout=5)

    def test_admin_reprocess_returns_immediately(self, app, db_session, admin_user):
        doc = _create_processing_doc(db_session, admin_user)
        doc.processing_status = "completed"
        db_session.commit()

        with patch(
            "app.routes.ai_documents.upload.start_single_document_processing",
        ) as mock_start, patch(
            "app.routes.admin.ai_management._resolve_ai_doc_file_for_processing",
            return_value=("/tmp/fake.pdf", None, "fake.pdf", False),
        ):
            from app.routes.admin.ai_management import reprocess_document

            with app.test_request_context(
                f"/admin/ai/documents/{doc.id}/reprocess",
                method="POST",
            ):
                from flask_login import login_user

                login_user(admin_user)
                with patch(
                    "app.routes.admin.shared.AuthorizationService.has_rbac_permission",
                    return_value=True,
                ):
                    resp = reprocess_document(doc.id)

        assert resp.status_code == 202
        assert mock_start.called

    def test_user_reprocess_returns_immediately(self, app, db_session, admin_user):
        """Non-admin app.routes.ai_documents.upload.reprocess_document (owner-initiated
        reprocess of a local-storage document) must also dispatch and return 202 without
        blocking on background-thread work."""
        doc = _create_processing_doc(db_session, admin_user)
        doc.processing_status = "completed"
        db_session.commit()

        with patch(
            "app.routes.ai_documents.upload.start_single_document_processing",
        ) as mock_start, patch(
            "app.routes.ai_documents.upload._ai_doc_source_ready",
            return_value=True,
        ), patch(
            "app.routes.ai_documents.upload._storage.get_absolute_path",
            return_value="/tmp/fake.pdf",
        ):
            from app.routes.ai_documents.upload import reprocess_document

            with app.test_request_context(
                f"/api/ai/documents/{doc.id}/reprocess",
                method="POST",
            ):
                from flask_login import login_user

                login_user(admin_user)
                resp = reprocess_document(doc.id)

        assert resp.status_code == 202
        assert mock_start.called

    def test_user_reprocess_with_source_url_defers_download_to_background(self, app, db_session, admin_user):
        """A source_url document's network download must happen inside the background
        thread (via resolve_file), not synchronously on the request thread before the
        202 response — otherwise a slow/hanging download blocks the HTTP response."""
        doc = _create_processing_doc(db_session, admin_user)
        doc.processing_status = "completed"
        doc.source_url = "https://example.org/report.pdf"
        db_session.commit()

        with patch(
            "app.routes.ai_documents.upload.start_single_document_processing",
        ) as mock_start, patch(
            "app.routes.ai_documents.upload._download_ifrc_document",
        ) as mock_download:
            from app.routes.ai_documents.upload import reprocess_document

            with app.test_request_context(
                f"/api/ai/documents/{doc.id}/reprocess",
                method="POST",
            ):
                from flask_login import login_user

                login_user(admin_user)
                resp = reprocess_document(doc.id)

        assert resp.status_code == 202
        assert mock_start.called
        mock_download.assert_not_called()

        _, kwargs = mock_start.call_args
        assert callable(kwargs.get("resolve_file"))


class TestResolveFileDeferredResolution:
    """start_single_document_processing's resolve_file contract: a zero-arg callable run
    inside the background thread whose (file_path, temp_path, filename, clear_storage_path)
    result overrides the keyword args, or whose exception fails the document without ever
    reaching _process_document_sync."""

    def test_resolve_file_result_overrides_context_and_processing_runs(self, app, db_session, admin_user):
        doc = _create_processing_doc(db_session, admin_user, stage="pending")
        doc.processing_status = "pending"
        db_session.commit()

        started = threading.Event()
        captured = {}

        def fake_process(document_id, file_path, filename):
            captured["file_path"] = file_path
            captured["filename"] = filename
            started.set()

        def resolve_file():
            return "/tmp/resolved.pdf", "/tmp/resolved.pdf", "resolved.pdf", True

        with patch("app.routes.ai_documents.upload._process_document_sync", side_effect=fake_process):
            start_single_document_processing(
                app,
                int(doc.id),
                file_path="/tmp/should-be-overridden.pdf",
                filename="original.pdf",
                resolve_file=resolve_file,
            )
            assert started.wait(timeout=5)

        assert captured["file_path"] == "/tmp/resolved.pdf"
        assert captured["filename"] == "resolved.pdf"

    def test_resolve_file_exception_marks_document_failed_without_processing(self, app, db_session, admin_user):
        doc = _create_processing_doc(db_session, admin_user, stage="pending")
        doc.processing_status = "pending"
        db_session.commit()
        doc_id = int(doc.id)

        def resolve_file():
            raise RuntimeError("network download blew up")

        with patch("app.routes.ai_documents.upload._process_document_sync") as mock_process:
            start_single_document_processing(
                app,
                doc_id,
                resolve_file=resolve_file,
            )

            refreshed = None
            for _ in range(50):
                db_session.expire_all()
                refreshed = AIDocument.query.get(doc_id)
                if refreshed.processing_status == "failed":
                    break
                time.sleep(0.1)

            mock_process.assert_not_called()

        assert refreshed.processing_status == "failed"
        assert refreshed.processing_error == GENERIC_ERROR_MESSAGE
