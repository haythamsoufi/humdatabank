"""Tracked background jobs for assignment-created notifications."""

from unittest.mock import patch

import pytest

from app.models import AIJob
from app.services.notification import assignment_notification_jobs as jobs
from tests.factories import create_test_assignment_entity_status, create_test_country

pytestmark = [pytest.mark.unit]


def _value(status):
    return getattr(status, "value", status)


def _make_aes_rows(db_session, count=2):
    rows = []
    for _ in range(count):
        country = create_test_country(db_session)
        rows.append(create_test_assignment_entity_status(db_session, country=country, status="pending"))
    db_session.commit()
    return [r.id for r in rows]


def _queue(app, db_session, admin_user, aes_ids, notify_admins=False):
    with app.app_context():
        job_id = jobs.create_assignment_notification_job(
            aes_ids, notify_admins, admin_user.id, source="create"
        )
        assert job_id
        db_session.commit()
    return job_id


def _notify_ok(aes, **kwargs):
    kwargs["outcome"].update({"email_status": "sent", "email_detail": ""})
    return ["n1", "n2"]


def _load(job_id, db_session):
    db_session.expire_all()
    return AIJob.query.get(job_id)


class TestCreateJob:
    def test_creates_one_item_per_entity(self, app, db_session, admin_user):
        aes_ids = _make_aes_rows(db_session, 3)
        job_id = _queue(app, db_session, admin_user, aes_ids, notify_admins=True)

        job = _load(job_id, db_session)
        assert job.job_type == jobs.JOB_TYPE
        assert _value(job.status) == "queued"
        assert job.total_items == 3
        assert job.user_id == admin_user.id
        assert job.meta["notify_admins"] is True
        assert [i.entity_id for i in job.items] == sorted(aes_ids)

    def test_requires_acting_user_and_entities(self, app, db_session):
        aes_ids = _make_aes_rows(db_session, 1)
        with app.app_context():
            assert jobs.create_assignment_notification_job(aes_ids, False, None) is None
            assert jobs.create_assignment_notification_job([], False, 1) is None


class TestRunJob:
    def test_success_completes_every_entity(self, app, db_session, admin_user):
        job_id = _queue(app, db_session, admin_user, _make_aes_rows(db_session, 2))

        with patch("app.services.notification.core.notify_assignment_created", side_effect=_notify_ok):
            jobs.run_assignment_notification_job(app, job_id)

        job = _load(job_id, db_session)
        assert _value(job.status) == "completed"
        data = jobs.serialize_job(job)
        assert data["counts"]["completed"] == 2
        assert data["counts"]["emails_sent"] == 2
        assert data["counts"]["failed"] == 0
        assert data["percent"] == 100.0

    def test_worker_has_request_context_for_url_building(self, app, db_session, admin_user):
        """Worker threads have no request; url_for must still work or every entity fails."""
        aes_ids = _make_aes_rows(db_session, 1)
        job_id = _queue(app, db_session, admin_user, aes_ids)
        seen = {}

        def _notify(aes, **kwargs):
            from flask import has_request_context, url_for

            seen["request"] = has_request_context()
            seen["url"] = url_for("assignments.view_assignment", aes_id=aes.id)
            return _notify_ok(aes, **kwargs)

        with patch("app.services.notification.core.notify_assignment_created", side_effect=_notify):
            jobs.run_assignment_notification_job(app, job_id)

        assert seen["request"] is True
        assert str(aes_ids[0]) in seen["url"]

    def test_passes_actor_and_admin_flag(self, app, db_session, admin_user):
        job_id = _queue(app, db_session, admin_user, _make_aes_rows(db_session, 1), notify_admins=True)

        with patch(
            "app.services.notification.core.notify_assignment_created", side_effect=_notify_ok
        ) as mock_notify:
            jobs.run_assignment_notification_job(app, job_id)

        assert mock_notify.call_args.kwargs["actor_user_id"] == admin_user.id
        assert mock_notify.call_args.kwargs["notify_admins"] is True

    def test_email_failure_is_reported_not_swallowed(self, app, db_session, admin_user):
        job_id = _queue(app, db_session, admin_user, _make_aes_rows(db_session, 2))

        calls = {"n": 0}

        def _notify(aes, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                kwargs["outcome"].update({"email_status": "failed", "email_detail": "SMTP down"})
                return ["n1"]
            return _notify_ok(aes, **kwargs)

        with patch("app.services.notification.core.notify_assignment_created", side_effect=_notify):
            jobs.run_assignment_notification_job(app, job_id)

        job = _load(job_id, db_session)
        assert _value(job.status) == "failed"
        data = jobs.serialize_job(job)
        assert data["counts"]["failed"] == 1
        assert data["counts"]["completed"] == 1
        assert len(data["failures"]) == 1
        assert "SMTP down" in data["failures"][0]["error"]
        assert "1 in-app notification" in data["failures"][0]["error"]
        assert data["error"]

    def test_one_entity_exception_does_not_stop_the_rest(self, app, db_session, admin_user):
        job_id = _queue(app, db_session, admin_user, _make_aes_rows(db_session, 3))

        calls = {"n": 0}

        def _notify(aes, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom")
            return _notify_ok(aes, **kwargs)

        with patch("app.services.notification.core.notify_assignment_created", side_effect=_notify):
            jobs.run_assignment_notification_job(app, job_id)

        job = _load(job_id, db_session)
        data = jobs.serialize_job(job)
        assert _value(job.status) == "failed"
        assert data["counts"]["completed"] == 2
        assert data["counts"]["failed"] == 1
        assert "boom" in data["failures"][0]["error"]

    def test_entity_without_recipients_is_not_counted_as_notified(self, app, db_session, admin_user):
        job_id = _queue(app, db_session, admin_user, _make_aes_rows(db_session, 1))

        def _notify(aes, **kwargs):
            kwargs["outcome"].update(
                {"email_status": "skipped", "email_detail": "No recipients for this entity."}
            )
            return []

        with patch("app.services.notification.core.notify_assignment_created", side_effect=_notify):
            jobs.run_assignment_notification_job(app, job_id)

        job = _load(job_id, db_session)
        data = jobs.serialize_job(job, include_items=True)
        assert _value(job.status) == "completed"
        assert data["counts"]["notified"] == 0
        assert data["counts"]["no_recipients"] == 1
        assert data["items"][0]["email_detail"] == "No recipients for this entity."

    def test_entity_removed_before_processing_is_skipped(self, app, db_session, admin_user):
        aes_ids = _make_aes_rows(db_session, 1)
        job_id = _queue(app, db_session, admin_user, aes_ids)

        with patch("app.services.notification.core.notify_assignment_created") as mock_notify, patch(
            "app.models.assignments.AssignmentEntityStatus.query"
        ) as mock_query:
            mock_query.get.return_value = None
            jobs.run_assignment_notification_job(app, job_id)

        mock_notify.assert_not_called()
        job = _load(job_id, db_session)
        assert _value(job.status) == "completed"

    def test_cancel_before_start_notifies_nobody(self, app, db_session, admin_user):
        job_id = _queue(app, db_session, admin_user, _make_aes_rows(db_session, 2))

        with app.app_context():
            assert jobs.request_cancel(job_id) is True

        with patch("app.services.notification.core.notify_assignment_created") as mock_notify:
            jobs.run_assignment_notification_job(app, job_id)

        mock_notify.assert_not_called()
        job = _load(job_id, db_session)
        assert _value(job.status) == "cancelled"
        assert all(_value(i.status) == "cancelled" for i in job.items)


class TestStartJob:
    def test_worker_start_failure_marks_job_failed(self, app, db_session, admin_user):
        job_id = _queue(app, db_session, admin_user, _make_aes_rows(db_session, 2))

        with app.app_context(), patch.dict(app.config, {"TESTING": False}), patch(
            "app.services.ai.ai_job_runner.start_ai_job_thread",
            side_effect=RuntimeError("can't start new thread"),
        ):
            jobs.start_assignment_notification_job(job_id)

        job = _load(job_id, db_session)
        assert _value(job.status) == "failed"
        assert "can't start new thread" in job.error
        assert all(_value(i.status) == "failed" for i in job.items)

    def test_stale_runner_errors_get_a_friendly_message(self, app, db_session, admin_user):
        job_id = _queue(app, db_session, admin_user, _make_aes_rows(db_session, 1))
        job = _load(job_id, db_session)
        job.items[0].status = "failed"
        job.items[0].error = "Processing interrupted (worker stopped). Re-run import or reprocess."
        job.status = "failed"
        job.error = "The background worker stopped responding (likely after an app restart). Re-run the job."
        db_session.commit()

        data = jobs.serialize_job(_load(job_id, db_session))
        assert "Re-run" not in data["error"]
        assert "Re-run" not in data["failures"][0]["error"]


    def test_interrupted_item_of_a_failed_job_is_reported_as_failed(self, app, db_session, admin_user):
        """A worker that died mid-entity leaves the item 'processing' while the job ends failed;
        the UI must show that entity as failed, not as endless progress."""
        job_id = _queue(app, db_session, admin_user, _make_aes_rows(db_session, 2))
        job = _load(job_id, db_session)
        job.items[0].status = "completed"
        job.items[1].status = "processing"
        job.status = "failed"
        db_session.commit()

        data = jobs.serialize_job(_load(job_id, db_session), include_items=True)
        assert data["counts"]["failed"] == 1
        assert data["counts"]["processed"] == 2
        assert data["percent"] == 100.0
        assert data["failures"] and "stopped" in data["failures"][0]["error"]
        assert data["items"][1]["status"] == "failed"


class TestBannerSummary:
    def test_counts_active_and_undismissed_failures(self, app, db_session, admin_user):
        active_id = _queue(app, db_session, admin_user, _make_aes_rows(db_session, 1))
        failed_id = _queue(app, db_session, admin_user, _make_aes_rows(db_session, 1))
        dismissed_id = _queue(app, db_session, admin_user, _make_aes_rows(db_session, 1))
        for jid in (failed_id, dismissed_id):
            job = _load(jid, db_session)
            job.status = "failed"
            db_session.commit()

        with app.app_context():
            assert jobs.dismiss_job(dismissed_id) is True
            assert jobs.dismiss_job(active_id) is False  # active jobs cannot be dismissed
            summary = jobs.get_banner_summary()

        assert summary["active"] >= 1
        assert summary["failed"] >= 1
        with app.app_context():
            assert jobs.get_job(dismissed_id).meta["dismissed"] is True


class TestBackgroundJobApi:
    def test_list_detail_cancel_and_dismiss(self, logged_in_client, app, db_session, admin_user):
        job_id = _queue(app, db_session, admin_user, _make_aes_rows(db_session, 2))

        resp = logged_in_client.get("/admin/api/communications/background-jobs")
        assert resp.status_code == 200
        body = resp.get_json()
        mine = [j for j in body["jobs"] if j["job_id"] == job_id]
        assert mine and mine[0]["counts"]["total"] == 2

        resp = logged_in_client.get(f"/admin/api/communications/background-jobs/{job_id}")
        assert resp.status_code == 200
        assert len(resp.get_json()["job"]["items"]) == 2

        resp = logged_in_client.post(f"/admin/api/communications/background-jobs/{job_id}/cancel")
        assert resp.status_code == 200
        assert _value(_load(job_id, db_session).status) == "cancelled"

        # A finished job can no longer be cancelled, but it can be dismissed.
        resp = logged_in_client.post(f"/admin/api/communications/background-jobs/{job_id}/cancel")
        assert resp.status_code == 400
        resp = logged_in_client.post(f"/admin/api/communications/background-jobs/{job_id}/dismiss")
        assert resp.status_code == 200

    def test_unknown_job_is_404(self, logged_in_client):
        resp = logged_in_client.get("/admin/api/communications/background-jobs/does-not-exist")
        assert resp.status_code == 404

    def test_other_job_types_are_not_exposed(self, logged_in_client, app, db_session, admin_user):
        db_session.add(AIJob(id="other-job-1", job_type="docs.bulk_reprocess", user_id=admin_user.id, status="queued"))
        db_session.commit()

        resp = logged_in_client.get("/admin/api/communications/background-jobs/other-job-1")
        assert resp.status_code == 404
