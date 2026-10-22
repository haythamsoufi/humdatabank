"""Saved Everyone Counts calculation: one row, one build at a time."""

from datetime import timedelta

import pytest

from app.extensions import db
from app.utils.datetime_helpers import naive_utc, utcnow
from plugins.fdrs.models import EveryoneCountsSnapshot
from plugins.fdrs.services import ecr_snapshot

TEMPLATE_ID = 9021


@pytest.fixture
def snapshot_table(app):
    with app.app_context():
        db.create_all()
        EveryoneCountsSnapshot.query.filter_by(template_id=TEMPLATE_ID).delete()
        db.session.commit()
        yield
        EveryoneCountsSnapshot.query.filter_by(template_id=TEMPLATE_ID).delete()
        db.session.commit()


def _capture_build(monkeypatch):
    started = []

    def _start(app, template_id, token, *, refresh_external=False):
        started.append(
            {
                "template_id": template_id,
                "token": token,
                "refresh_external": refresh_external,
            }
        )

    monkeypatch.setattr(ecr_snapshot, "start_snapshot_build", _start)
    return started


@pytest.mark.db
def test_missing_snapshot_is_empty(app, snapshot_table):
    with app.app_context():
        payload, meta = ecr_snapshot.read_snapshot(TEMPLATE_ID)
    assert payload is None
    assert meta["status"] == "empty"
    assert meta["busy"] is False


@pytest.mark.db
def test_refresh_starts_one_build_until_it_finishes(app, snapshot_table, monkeypatch):
    started = _capture_build(monkeypatch)
    with app.app_context():
        first = ecr_snapshot.request_rebuild(TEMPLATE_ID, None)
        second = ecr_snapshot.request_rebuild(TEMPLATE_ID, None)
        payload, meta = ecr_snapshot.read_snapshot(TEMPLATE_ID)

    assert first["started"] is True
    assert first["busy"] is True
    assert second["started"] is False
    assert len(started) == 1
    assert payload is None
    assert meta["status"] == "building"


@pytest.mark.db
def test_abandoned_build_can_be_started_again(app, snapshot_table, monkeypatch):
    started = _capture_build(monkeypatch)
    with app.app_context():
        ecr_snapshot.request_rebuild(TEMPLATE_ID, None)
        row = EveryoneCountsSnapshot.query.filter_by(template_id=TEMPLATE_ID).one()
        row.started_at = naive_utc(utcnow() - timedelta(minutes=21))
        db.session.commit()
        _, stale = ecr_snapshot.read_snapshot(TEMPLATE_ID)
        again = ecr_snapshot.request_rebuild(TEMPLATE_ID, None)

    assert stale["busy"] is False
    assert stale["status"] == "failed"
    assert again["started"] is True
    assert started[0]["token"] != started[1]["token"]


@pytest.mark.db
def test_finished_calculation_is_served_and_a_failed_retry_keeps_it(app, snapshot_table, monkeypatch):
    started = _capture_build(monkeypatch)
    with app.app_context():
        ecr_snapshot.request_rebuild(TEMPLATE_ID, None)
        assert ecr_snapshot.complete_snapshot(
            TEMPLATE_ID,
            started[0]["token"],
            {"chapters": [{"id": "volunteers"}], "notes": ["saved"]},
        )
        payload, meta = ecr_snapshot.read_snapshot(TEMPLATE_ID)
        assert payload["chapters"][0]["id"] == "volunteers"
        assert meta["status"] == "ready"
        assert meta["built_at"]

        ecr_snapshot.request_rebuild(TEMPLATE_ID, None)
        assert ecr_snapshot.fail_snapshot(TEMPLATE_ID, started[1]["token"])
        kept, failed = ecr_snapshot.read_snapshot(TEMPLATE_ID)

    assert kept["chapters"][0]["id"] == "volunteers"
    assert failed["status"] == "failed"
    assert failed["busy"] is False
    assert failed["built_at"] == meta["built_at"]


@pytest.mark.db
def test_old_build_cannot_replace_a_newer_one(app, snapshot_table, monkeypatch):
    started = _capture_build(monkeypatch)
    with app.app_context():
        ecr_snapshot.request_rebuild(TEMPLATE_ID, None)
        ecr_snapshot.complete_snapshot(TEMPLATE_ID, started[0]["token"], {"chapters": [{"id": "first"}]})
        ecr_snapshot.request_rebuild(TEMPLATE_ID, None)
        replaced = ecr_snapshot.complete_snapshot(
            TEMPLATE_ID,
            started[0]["token"],
            {"chapters": [{"id": "stale"}]},
        )
        payload, meta = ecr_snapshot.read_snapshot(TEMPLATE_ID)

    assert replaced is False
    assert payload["chapters"][0]["id"] == "first"
    assert meta["status"] == "building"


@pytest.mark.db
def test_snapshot_rejects_values_postgres_cannot_store(app, snapshot_table, monkeypatch):
    started = _capture_build(monkeypatch)
    with app.app_context():
        ecr_snapshot.request_rebuild(TEMPLATE_ID, None)
        with pytest.raises(ValueError):
            ecr_snapshot.complete_snapshot(
                TEMPLATE_ID,
                started[0]["token"],
                {"chapters": [{"value": float("nan")}]},
            )
        payload, meta = ecr_snapshot.read_snapshot(TEMPLATE_ID)

    assert payload is None
    assert meta["status"] == "building"
