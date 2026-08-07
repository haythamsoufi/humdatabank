"""Tests for cross-worker AI document batch job runner."""

import threading
import time
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.extensions import db
from app.models import AIJob, AIJobItem
from app.services.ai.ai_job_runner import (
    AI_DOCUMENTS_JOB_TTL_SECONDS,
    AI_DOCUMENTS_JOB_TYPES,
    _claim_job_item,
    _job_lock_id,
    cleanup_expired_ai_document_jobs,
    job_cancel_requested,
    reconcile_stale_ai_job,
    run_ai_job,
    signal_job_cancel,
)
from app.utils.pg_advisory_lock import release_session_advisory_lock, try_session_advisory_lock

pytestmark = [pytest.mark.unit]


def _create_ai_doc_job(db_session, admin_user, *, job_id=None, status="queued", job_type="docs.bulk_reprocess"):
    job_id = job_id or str(uuid.uuid4())
    job = AIJob(
        id=job_id,
        job_type=job_type,
        user_id=admin_user.id,
        status=status,
        total_items=1,
        meta={"concurrency": 1},
    )
    db_session.add(job)
    db_session.flush()
    item = AIJobItem(
        job_id=job_id,
        item_index=0,
        entity_type="ai_document",
        entity_id=123,
        status="queued",
        payload={"document_id": 123},
    )
    db_session.add(item)
    db_session.commit()
    return job_id, item.id


class TestAIJobRunnerCancel:
    def test_job_cancel_requested_reads_db_status(self, db_session, admin_user):
        job_id, _item_id = _create_ai_doc_job(db_session, admin_user, status="cancel_requested")
        assert job_cancel_requested(job_id) is True

    def test_signal_job_cancel_sets_in_memory_flag(self, db_session, admin_user):
        job_id, _item_id = _create_ai_doc_job(db_session, admin_user)
        signal_job_cancel(job_id)
        assert job_cancel_requested(job_id) is True


class TestAIJobRunnerLocks:
    def test_job_lock_id_is_stable_and_in_namespace(self):
        job_id = "abc-123"
        assert _job_lock_id(job_id) == _job_lock_id(job_id)
        assert _job_lock_id(job_id) >= 950_000_000


class TestAIJobRunnerItemClaim:
    def test_claim_job_item_only_claims_queued(self, db_session, admin_user):
        job_id, item_id = _create_ai_doc_job(db_session, admin_user)
        assert _claim_job_item(item_id) is True
        assert _claim_job_item(item_id) is False

        item = AIJobItem.query.get(item_id)
        assert item.status == "processing"


class TestAIJobRunnerCleanup:
    def test_cleanup_expired_ai_document_jobs_removes_old_terminal_jobs(self, db_session, admin_user):
        job_id = str(uuid.uuid4())
        old_created = datetime.utcnow() - timedelta(seconds=AI_DOCUMENTS_JOB_TTL_SECONDS + 100)
        db_session.add(
            AIJob(
                id=job_id,
                job_type="docs.bulk_reprocess",
                user_id=admin_user.id,
                status="completed",
                total_items=0,
                created_at=old_created,
            )
        )
        db_session.commit()

        cleanup_expired_ai_document_jobs(time.time())
        assert AIJob.query.get(job_id) is None

    def test_cleanup_preserves_fresh_jobs(self, db_session, admin_user):
        job_id, _ = _create_ai_doc_job(db_session, admin_user, status="completed")
        cleanup_expired_ai_document_jobs(time.time())
        assert AIJob.query.get(job_id) is not None


class TestAIJobRunnerStaleReconcile:
    def test_reconcile_stale_ai_job_finalizes_when_all_items_terminal(self, db_session, admin_user):
        job_id, item_id = _create_ai_doc_job(db_session, admin_user, status="running")
        item = AIJobItem.query.get(item_id)
        item.status = "completed"
        db_session.commit()

        assert reconcile_stale_ai_job(job_id) is True
        job = AIJob.query.get(job_id)
        assert job.status == "completed"

    def test_reconcile_abandons_idle_job_without_live_thread(self, db_session, admin_user, app):
        job_id, item_id = _create_ai_doc_job(db_session, admin_user, status="running")
        job = AIJob.query.get(job_id)
        job.started_at = datetime.utcnow() - timedelta(hours=6)
        item = AIJobItem.query.get(item_id)
        item.status = "processing"
        item.updated_at = datetime.utcnow() - timedelta(hours=6)
        db_session.commit()

        with app.app_context():
            app.config["AI_DOCS_JOB_STALE_SECONDS"] = 60
            assert reconcile_stale_ai_job(job_id) is True

        db_session.expire_all()
        job = AIJob.query.get(job_id)
        assert getattr(job.status, "value", job.status) == "failed"


class TestRunAiJobEndToEnd:
    """Exercises run_ai_job as a whole: claim -> process (via a real ThreadPoolExecutor
    of item_processor calls) -> finalize, instead of only unit-testing its helpers."""

    def test_run_ai_job_processes_all_items_and_completes(self, app, db_session, admin_user):
        job_id, first_item_id = _create_ai_doc_job(db_session, admin_user, status="queued")
        second_item = AIJobItem(
            job_id=job_id,
            item_index=1,
            entity_type="ai_document",
            entity_id=456,
            status="queued",
            payload={"document_id": 456},
        )
        db_session.add(second_item)
        db_session.commit()
        second_item_id = second_item.id

        processed: list[int] = []
        processed_lock = threading.Lock()

        def item_processor(app, *, job_id, item_id):
            # Mirrors the shape of real item processors (e.g. _process_reprocess_job_item_sync):
            # each pool worker opens its own app context / session.
            with app.app_context():
                from app.extensions import db as _db
                from app.models import AIJobItem as _AIJobItem

                item = _AIJobItem.query.get(int(item_id))
                if item:
                    item.status = "completed"
                    _db.session.commit()
            with processed_lock:
                processed.append(int(item_id))

        run_ai_job(app, job_id, item_processor)

        assert sorted(processed) == sorted([first_item_id, second_item_id])

        db_session.expire_all()
        job = AIJob.query.get(job_id)
        assert getattr(job.status, "value", job.status) == "completed"
        assert job.started_at is not None
        assert job.finished_at is not None
        for item in job.items:
            assert getattr(item.status, "value", item.status) == "completed"

    def test_run_ai_job_marks_job_failed_when_an_item_fails(self, app, db_session, admin_user):
        job_id, item_id = _create_ai_doc_job(db_session, admin_user, status="queued")

        def item_processor(app, *, job_id, item_id):
            with app.app_context():
                from app.extensions import db as _db
                from app.models import AIJobItem as _AIJobItem

                item = _AIJobItem.query.get(int(item_id))
                if item:
                    item.status = "failed"
                    item.error = "boom"
                    _db.session.commit()

        run_ai_job(app, job_id, item_processor)

        db_session.expire_all()
        job = AIJob.query.get(job_id)
        assert getattr(job.status, "value", job.status) == "failed"
        assert job.error


class TestRunAiJobLockContention:
    """Verifies the cross-worker ownership-claim guarantee: a second run_ai_job call for
    the same job_id must not do any work while another connection holds that job's
    PostgreSQL advisory lock (simulating a second worker/instance already running it)."""

    def test_run_ai_job_skips_when_lock_already_held_elsewhere(self, app, db_session, admin_user):
        if db.engine.dialect.name != "postgresql":
            pytest.skip("Advisory lock contention requires a PostgreSQL test database")

        job_id, item_id = _create_ai_doc_job(db_session, admin_user, status="queued")
        lock_id = _job_lock_id(job_id)

        # A separate connection (not routed through Flask-SQLAlchemy's app-context-scoped
        # session) standing in for another worker process/thread that already owns this job.
        holder_session = sessionmaker(bind=db.engine)()
        try:
            assert try_session_advisory_lock(holder_session, lock_id) is True

            processed: list[int] = []

            def item_processor(app, *, job_id, item_id):
                processed.append(int(item_id))

            run_ai_job(app, job_id, item_processor)

            assert processed == [], "run_ai_job must not process items when it cannot claim the job lock"

            db_session.expire_all()
            job = AIJob.query.get(job_id)
            assert getattr(job.status, "value", job.status) == "queued"
            item = AIJobItem.query.get(item_id)
            assert getattr(item.status, "value", item.status) == "queued"
        finally:
            release_session_advisory_lock(holder_session, lock_id, acquired=True)
            holder_session.close()

    def test_run_ai_job_proceeds_once_the_lock_is_free(self, app, db_session, admin_user):
        """Sanity check for the test above: run_ai_job *can* claim and complete the same
        job once no other connection holds its advisory lock, so the "skips" assertion
        is actually exercising lock contention rather than some other silent no-op."""
        if db.engine.dialect.name != "postgresql":
            pytest.skip("Advisory lock contention requires a PostgreSQL test database")

        job_id, item_id = _create_ai_doc_job(db_session, admin_user, status="queued")
        lock_id = _job_lock_id(job_id)

        holder_session = sessionmaker(bind=db.engine)()
        assert try_session_advisory_lock(holder_session, lock_id) is True
        release_session_advisory_lock(holder_session, lock_id, acquired=True)
        holder_session.close()

        def item_processor(app, *, job_id, item_id):
            with app.app_context():
                from app.extensions import db as _db
                from app.models import AIJobItem as _AIJobItem

                item = _AIJobItem.query.get(int(item_id))
                if item:
                    item.status = "completed"
                    _db.session.commit()

        run_ai_job(app, job_id, item_processor)

        db_session.expire_all()
        job = AIJob.query.get(job_id)
        assert getattr(job.status, "value", job.status) == "completed"


class TestRunAiJobConcurrencyClaiming:
    def test_run_ai_job_only_claims_concurrency_items_per_batch(self, app, db_session, admin_user):
        """Queued items must stay queued until a worker slot opens — not all marked processing upfront."""
        job_id = str(uuid.uuid4())
        job = AIJob(
            id=job_id,
            job_type="docs.bulk_reprocess",
            user_id=admin_user.id,
            status="queued",
            total_items=5,
            meta={"concurrency": 2},
        )
        db_session.add(job)
        db_session.flush()
        for idx in range(5):
            db_session.add(
                AIJobItem(
                    job_id=job_id,
                    item_index=idx,
                    entity_type="ai_document",
                    entity_id=100 + idx,
                    status="queued",
                )
            )
        db_session.commit()

        gate = threading.Event()
        started = threading.Event()

        def item_processor(app, *, job_id, item_id):
            with app.app_context():
                started.set()
                gate.wait(timeout=10)
                from app.extensions import db as _db
                from app.models import AIJobItem as _AIJobItem

                item = _AIJobItem.query.get(int(item_id))
                if item:
                    item.status = "completed"
                    _db.session.commit()

        runner = threading.Thread(
            target=run_ai_job,
            args=(app, job_id, item_processor),
            kwargs={"default_concurrency": 2},
            daemon=True,
        )
        runner.start()
        assert started.wait(timeout=5)

        db_session.expire_all()
        items = AIJobItem.query.filter_by(job_id=job_id).all()
        processing = sum(1 for it in items if getattr(it.status, "value", it.status) == "processing")
        queued = sum(1 for it in items if getattr(it.status, "value", it.status) == "queued")
        assert processing <= 2
        assert queued >= 3

        gate.set()
        runner.join(timeout=30)
        assert not runner.is_alive()


class TestRunAiJobConcurrencyClaiming:
    def test_run_ai_job_only_claims_concurrency_items_per_batch(self, app, db_session, admin_user):
        """Queued items must stay queued until a worker slot opens — not all marked processing upfront."""
        job_id = str(uuid.uuid4())
        job = AIJob(
            id=job_id,
            job_type="docs.bulk_reprocess",
            user_id=admin_user.id,
            status="queued",
            total_items=5,
            meta={"concurrency": 2},
        )
        db_session.add(job)
        db_session.flush()
        for idx in range(5):
            db_session.add(
                AIJobItem(
                    job_id=job_id,
                    item_index=idx,
                    entity_type="ai_document",
                    entity_id=100 + idx,
                    status="queued",
                )
            )
        db_session.commit()

        gate = threading.Event()
        started = threading.Event()

        def item_processor(app, *, job_id, item_id):
            with app.app_context():
                started.set()
                gate.wait(timeout=10)
                from app.extensions import db as _db
                from app.models import AIJobItem as _AIJobItem

                item = _AIJobItem.query.get(int(item_id))
                if item:
                    item.status = "completed"
                    _db.session.commit()

        runner = threading.Thread(
            target=run_ai_job,
            args=(app, job_id, item_processor),
            kwargs={"default_concurrency": 2},
            daemon=True,
        )
        runner.start()
        assert started.wait(timeout=5)

        db_session.expire_all()
        items = AIJobItem.query.filter_by(job_id=job_id).all()
        processing = sum(1 for it in items if getattr(it.status, "value", it.status) == "processing")
        queued = sum(1 for it in items if getattr(it.status, "value", it.status) == "queued")
        assert processing <= 2
        assert queued >= 3

        gate.set()
        runner.join(timeout=30)
        assert not runner.is_alive()
