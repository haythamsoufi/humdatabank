"""Row locking and re-validation of AssignmentEntityStatus transitions (TOCTOU).

Single-session tests cover the helpers in ``app.utils.form_authorization``; the
``TestConcurrent*`` classes run real Postgres row-lock contention with one Flask app context
(and therefore one DB connection / transaction) per thread.
"""

import threading
import time

import pytest
from sqlalchemy import event, text

from app import db
from app.models import AssignmentEntityStatus
from app.utils.form_authorization import (
    TRANSITION_FORBIDDEN,
    TRANSITION_GONE,
    TRANSITION_OK,
    TRANSITION_STALE,
    begin_aes_transition,
    lock_aes_rows_for_update,
)
from tests.factories import (
    create_test_assignment_entity_status,
    create_test_country,
    create_test_template,
    create_test_user,
)
from tests.helpers import login_session

pytestmark = pytest.mark.integration

WAIT = 15


def _status(app, aes_id):
    with app.app_context():
        row = db.session.execute(
            text("SELECT status FROM assignment_entity_status WHERE id = :i"), {"i": aes_id}
        ).scalar_one()
        db.session.rollback()
        return str(getattr(row, "value", row))


def _lock_waiters(app):
    """Number of backends currently blocked on a row lock in this database."""
    with app.app_context():
        with db.engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock' "
                    "AND pid <> pg_backend_pid()"
                )
            ).scalar_one()


def _wait_for(predicate, timeout=WAIT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def sm_user(db_session, app):
    with app.app_context():
        return create_test_user(db_session, role="system_manager").id


@pytest.fixture
def make_aes(db_session, app):
    def _make(status="submitted", *, count=1):
        with app.app_context():
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            first = create_test_assignment_entity_status(
                db_session, country=country, template=template, status=status
            )
            ids = [first.id]
            for _ in range(count - 1):
                other = create_test_assignment_entity_status(
                    db_session,
                    country=create_test_country(db_session),
                    template=template,
                    status=status,
                    period_name=f"P{len(ids)}",
                )
                ids.append(other.id)
            return ids if count > 1 else ids[0]

    return _make


class TestTransitionHelpers:
    def test_ok_when_row_is_current_and_allowed(self, app, make_aes, sm_user):
        aes_id = make_aes("submitted")
        with app.app_context():
            aes = db.session.get(AssignmentEntityStatus, aes_id)
            result = begin_aes_transition(aes, None, allowed_from={"submitted"})
            assert result.ok and result.reason == TRANSITION_OK and result.changed is False
            db.session.rollback()

    def test_stale_when_status_moved_after_load(self, app, make_aes):
        aes_id = make_aes("submitted")
        with app.app_context():
            aes = db.session.get(AssignmentEntityStatus, aes_id)
            db.session.execute(
                text("UPDATE assignment_entity_status SET status = 'approved' WHERE id = :i"),
                {"i": aes_id},
            )
            result = begin_aes_transition(aes, None, allowed_from={"submitted"})
            assert not result.ok
            assert result.reason == TRANSITION_STALE
            assert result.changed is True and result.status == "approved"
            db.session.rollback()

    def test_permission_is_evaluated_against_the_locked_row(self, app, make_aes):
        aes_id = make_aes("submitted")
        seen = []

        def permission(row, user):
            seen.append(str(getattr(row.status, "value", row.status)))
            return False

        with app.app_context():
            aes = db.session.get(AssignmentEntityStatus, aes_id)
            db.session.execute(
                text("UPDATE assignment_entity_status SET status = 'approved' WHERE id = :i"),
                {"i": aes_id},
            )
            result = begin_aes_transition(aes, None, permission=permission)
            assert result.reason == TRANSITION_FORBIDDEN
            assert seen == ["approved"]
            db.session.rollback()

    def test_gone_when_row_deleted(self, app, make_aes):
        aes_id = make_aes("submitted")
        with app.app_context():
            aes = db.session.get(AssignmentEntityStatus, aes_id)
            db.session.execute(
                text("DELETE FROM assignment_entity_status WHERE id = :i"), {"i": aes_id}
            )
            result = begin_aes_transition(aes, None)
            assert result.reason == TRANSITION_GONE and not result.ok
            db.session.rollback()

    def test_bulk_lock_is_ascending_and_scoped(self, app, make_aes):
        ids = make_aes("submitted", count=3)
        with app.app_context():
            statements = []

            def capture(conn, cursor, statement, params, context, executemany):
                statements.append(statement)

            event.listen(db.engine, "before_cursor_execute", capture)
            try:
                rows = lock_aes_rows_for_update(list(reversed(ids)) + [ids[0]])
            finally:
                event.remove(db.engine, "before_cursor_execute", capture)
            assert [r.id for r in rows] == sorted(ids)
            locking = [s for s in statements if "FOR UPDATE" in s]
            assert locking and "ORDER BY assignment_entity_status.id" in locking[-1]
            assert "FOR UPDATE OF assignment_entity_status" in locking[-1]

            other_form = db.session.get(AssignmentEntityStatus, ids[1]).assigned_form_id
            scoped = lock_aes_rows_for_update(ids, assigned_form_id=other_form)
            assert [r.id for r in scoped] == [ids[1]]
            db.session.rollback()

    def test_bulk_lock_with_no_ids_is_a_noop(self, app):
        with app.app_context():
            assert lock_aes_rows_for_update([]) == []


class TestTransitionRoutes:
    def _post(self, client, app, user_id, path):
        login_session(client, user_id)
        return client.post(path, follow_redirects=False)

    def test_approve_requires_submitted_source_status(self, client, app, make_aes, sm_user):
        aes_id = make_aes("in_progress")
        resp = self._post(client, app, sm_user, f"/approve_assignment/{aes_id}")
        assert resp.status_code in (301, 302, 303)
        assert _status(app, aes_id) == "in_progress"

    def test_double_approve_transitions_once(self, client, app, make_aes, sm_user, monkeypatch):
        aes_id = make_aes("submitted")
        calls = []
        monkeypatch.setattr(
            "app.services.notification.core.notify_assignment_approved",
            lambda aes: calls.append(aes.id),
        )
        self._post(client, app, sm_user, f"/approve_assignment/{aes_id}")
        self._post(client, app, sm_user, f"/approve_assignment/{aes_id}")
        assert _status(app, aes_id) == "approved"
        assert calls == [aes_id]

    def test_return_for_revision_only_from_sent_for_review(self, client, app, make_aes, sm_user):
        aes_id = make_aes("approved")
        self._post(client, app, sm_user, f"/return_assignment_for_revision/{aes_id}")
        assert _status(app, aes_id) == "approved"

    def test_double_reopen_transitions_once(self, client, app, make_aes, sm_user, monkeypatch):
        aes_id = make_aes("approved")
        calls = []
        monkeypatch.setattr(
            "app.services.notification.core.notify_assignment_reopened",
            lambda aes: calls.append(aes.id),
        )
        self._post(client, app, sm_user, f"/reopen_assignment/{aes_id}")
        self._post(client, app, sm_user, f"/reopen_assignment/{aes_id}")
        assert _status(app, aes_id) == "in_progress"
        assert calls == [aes_id]

    def test_admin_bulk_status_update_locks_in_ascending_order(self, client, app, make_aes, sm_user):
        ids = make_aes("submitted", count=3)
        with app.app_context():
            form_id = db.session.get(AssignmentEntityStatus, ids[0]).assigned_form_id
        login_session(client, sm_user)
        statements = []

        def capture(conn, cursor, statement, params, context, executemany):
            statements.append(statement)

        with app.app_context():
            event.listen(db.engine, "before_cursor_execute", capture)
        try:
            resp = client.post(
                f"/admin/assignments/{form_id}/entities/bulk-update-status",
                json={"status_ids": list(reversed(ids)), "status": "approved"},
            )
        finally:
            with app.app_context():
                event.remove(db.engine, "before_cursor_execute", capture)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        locking = [s for s in statements if "FOR UPDATE OF assignment_entity_status" in s]
        assert locking and "ORDER BY assignment_entity_status.id" in locking[0]
        assert _status(app, ids[0]) == "approved"

    def test_admin_put_status_for_vanished_row_is_404(self, client, app, make_aes, sm_user):
        aes_id = make_aes("submitted")
        with app.app_context():
            form_id = db.session.get(AssignmentEntityStatus, aes_id).assigned_form_id
        login_session(client, sm_user)
        resp = client.put(
            f"/admin/assignments/{form_id}/entities/{aes_id + 9999}", json={"status": "approved"}
        )
        assert resp.status_code == 404


class TestConcurrentHelper:
    def test_second_transition_blocks_then_is_rejected(self, app, make_aes):
        aes_id = make_aes("submitted")
        first_locked = threading.Event()
        release_first = threading.Event()
        both_loaded = threading.Barrier(2, timeout=WAIT)
        results = {}
        errors = []

        def worker(name):
            try:
                with app.app_context():
                    aes = db.session.get(AssignmentEntityStatus, aes_id)
                    both_loaded.wait()
                    if name == "second":
                        assert first_locked.wait(WAIT)
                    result = begin_aes_transition(aes, None, allowed_from={"submitted"})
                    results[name] = result
                    if result.ok:
                        db.session.execute(
                            text("UPDATE assignment_entity_status SET status = 'approved' WHERE id = :i"),
                            {"i": aes_id},
                        )
                        first_locked.set()
                        assert release_first.wait(WAIT)
                        db.session.commit()
                    else:
                        db.session.rollback()
            except Exception as exc:
                errors.append(exc)
                first_locked.set()

        first = threading.Thread(target=worker, args=("first",))
        second = threading.Thread(target=worker, args=("second",))
        first.start()
        second.start()
        assert first_locked.wait(WAIT)
        assert _wait_for(lambda: _lock_waiters(app) >= 1), "second transition never blocked on the row lock"
        assert "second" not in results, "second transition must wait for the first row lock"
        release_first.set()
        first.join(WAIT)
        second.join(WAIT)

        assert not errors, errors
        assert results["first"].ok
        assert not results["second"].ok
        assert results["second"].reason == TRANSITION_STALE
        assert results["second"].changed is True and results["second"].status == "approved"
        assert _status(app, aes_id) == "approved"

    def test_bulk_lockers_with_opposite_orders_do_not_deadlock(self, app, make_aes):
        low, high = make_aes("submitted", count=2)
        first_has_low = threading.Event()
        second_started = threading.Event()
        errors = []
        order = []

        def first():
            try:
                with app.app_context():
                    lock_aes_rows_for_update([low])
                    first_has_low.set()
                    assert second_started.wait(WAIT)
                    assert _wait_for(lambda: _lock_waiters(app) >= 1)
                    lock_aes_rows_for_update([high])
                    order.append("first")
                    db.session.commit()
            except Exception as exc:
                errors.append(exc)
                first_has_low.set()

        def second():
            try:
                with app.app_context():
                    assert first_has_low.wait(WAIT)
                    second_started.set()
                    rows = lock_aes_rows_for_update([high, low])
                    assert [r.id for r in rows] == [low, high]
                    order.append("second")
                    db.session.commit()
            except Exception as exc:
                errors.append(exc)
                second_started.set()

        threads = [threading.Thread(target=first), threading.Thread(target=second)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(WAIT * 2)

        assert not errors, errors
        assert order == ["first", "second"]


class TestConcurrentRoutes:
    def test_concurrent_approve_requests_transition_once(self, app, make_aes, sm_user, monkeypatch):
        aes_id = make_aes("submitted")
        first_in_critical_section = threading.Event()
        release_first = threading.Event()
        notified = []
        responses = {}
        errors = []

        def slow_notify(aes):
            notified.append(aes.id)
            first_in_critical_section.set()
            assert release_first.wait(WAIT)

        monkeypatch.setattr("app.services.notification.core.notify_assignment_approved", slow_notify)

        def request_worker(name):
            try:
                client = app.test_client()
                login_session(client, sm_user)
                if name == "second":
                    assert first_in_critical_section.wait(WAIT)
                responses[name] = client.post(f"/approve_assignment/{aes_id}")
            except Exception as exc:
                errors.append(exc)
                first_in_critical_section.set()

        first = threading.Thread(target=request_worker, args=("first",))
        second = threading.Thread(target=request_worker, args=("second",))
        first.start()
        second.start()
        assert first_in_critical_section.wait(WAIT)
        assert _wait_for(lambda: _lock_waiters(app) >= 1), "second request never blocked on the row lock"
        assert "second" not in responses
        release_first.set()
        first.join(WAIT)
        second.join(WAIT)

        assert not errors, errors
        assert responses["first"].status_code in (301, 302, 303)
        assert responses["second"].status_code in (301, 302, 303)
        assert notified == [aes_id]
        assert _status(app, aes_id) == "approved"

    def test_reopen_waits_for_inflight_approve_then_applies_to_fresh_state(
        self, app, make_aes, sm_user, monkeypatch
    ):
        aes_id = make_aes("submitted")
        approve_holding_lock = threading.Event()
        release_approve = threading.Event()
        responses = {}
        errors = []

        def slow_notify(aes):
            approve_holding_lock.set()
            assert release_approve.wait(WAIT)

        monkeypatch.setattr("app.services.notification.core.notify_assignment_approved", slow_notify)
        monkeypatch.setattr("app.services.notification.core.notify_assignment_reopened", lambda aes: None)

        def approve():
            try:
                client = app.test_client()
                login_session(client, sm_user)
                responses["approve"] = client.post(f"/approve_assignment/{aes_id}")
            except Exception as exc:
                errors.append(exc)
                approve_holding_lock.set()

        def reopen():
            try:
                client = app.test_client()
                login_session(client, sm_user)
                assert approve_holding_lock.wait(WAIT)
                responses["reopen"] = client.post(f"/reopen_assignment/{aes_id}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=approve), threading.Thread(target=reopen)]
        for t in threads:
            t.start()
        assert approve_holding_lock.wait(WAIT)
        assert _wait_for(lambda: _lock_waiters(app) >= 1), "reopen never blocked on the row lock"
        assert "reopen" not in responses
        assert _status(app, aes_id) == "submitted"
        release_approve.set()
        for t in threads:
            t.join(WAIT)

        assert not errors, errors
        assert _status(app, aes_id) == "in_progress"


class TestBatchWritersLockRows:
    def _recorder(self, monkeypatch):
        calls = []
        real = lock_aes_rows_for_update

        def recording(ids, **kwargs):
            calls.append(sorted(ids))
            return real(ids, **kwargs)

        monkeypatch.setattr("app.utils.form_authorization.lock_aes_rows_for_update", recording)
        return calls

    def test_upr_pending_reset_locks_only_when_writing(self, app, make_aes, monkeypatch):
        from plugins.upr.scripts.import_upr_excel_data import apply_pns_pending_status_resets

        ids = make_aes("submitted", count=2)
        plan = [{"assignment_entity_status_id": i} for i in reversed(ids)]
        calls = self._recorder(monkeypatch)
        with app.app_context():
            apply_pns_pending_status_resets(plan, dry_run=True)
            assert calls == []
            stats = apply_pns_pending_status_resets(plan)
            assert calls == [sorted(ids)]
            assert stats["updated"] == 2
        assert _status(app, ids[0]) == "pending"

    def test_page_mode_toggle_locks_entities_in_ascending_order(self, app, make_aes, monkeypatch):
        from app.models import AssignedForm
        from app.services.assignments.page_submission_service import apply_page_submission_mode_change

        ids = make_aes("submitted", count=2)
        calls = self._recorder(monkeypatch)
        with app.app_context():
            aes = db.session.get(AssignmentEntityStatus, ids[0])
            assignment = db.session.get(AssignedForm, aes.assigned_form_id)
            summary = apply_page_submission_mode_change(assignment, True, None)
            db.session.rollback()
        assert calls == [[ids[0]]]
        assert summary["entities"] == 1
