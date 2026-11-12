"""Session length measurement: sub-minute sessions, idle endings, touch throttling."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.platform import user_analytics_service as svc
from app.utils.common.datetime_helpers import iso_utc, utcnow
from app.utils.activity.page_view_paths import (
    PAGE_VIEW_PATH_MAX_KEYS,
    merge_page_view_path_count,
    template_path_key,
)
from app.utils.http.request_utils import parse_bool_arg

pytestmark = pytest.mark.unit


def _row(**kw):
    start = kw.pop("start", utcnow() - timedelta(hours=1))
    defaults = dict(
        session_start=start,
        session_end=None,
        last_activity=start,
        ended_by=None,
        is_active=False,
        duration_minutes=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class TestEffectiveDuration:
    def test_sub_minute_session_keeps_seconds(self):
        start = utcnow() - timedelta(minutes=5)
        row = _row(start=start, session_end=start + timedelta(seconds=42), ended_by="logout")
        assert svc.effective_session_duration_seconds(row) == 42
        assert svc.effective_session_duration_minutes(row) == 0

    def test_idle_timeout_ends_at_last_activity(self):
        start = utcnow() - timedelta(hours=5)
        row = _row(
            start=start,
            last_activity=start + timedelta(minutes=10),
            session_end=start + timedelta(hours=3),
            ended_by="timeout",
        )
        assert svc.effective_session_duration_seconds(row) == 600

    def test_logout_end_is_not_clamped(self):
        start = utcnow() - timedelta(hours=5)
        row = _row(
            start=start,
            last_activity=start + timedelta(minutes=10),
            session_end=start + timedelta(minutes=30),
            ended_by="logout",
        )
        assert svc.effective_session_duration_seconds(row) == 1800

    def test_naive_timestamps_are_treated_as_utc(self):
        start = datetime(2025, 1, 1, 10, 0, 0)
        row = _row(start=start, session_end=datetime(2025, 1, 1, 10, 0, 30), ended_by="logout")
        assert svc.effective_session_duration_seconds(row) == 30

    def test_open_session_measures_to_now(self):
        row = _row(start=utcnow() - timedelta(seconds=90), is_active=True)
        assert 89 <= svc.effective_session_duration_seconds(row) <= 95

    def test_duration_minutes_is_fallback_without_end(self):
        assert svc.effective_session_duration_seconds(_row(duration_minutes=7)) == 420

    def test_active_duration_runs_to_last_activity(self):
        start = utcnow() - timedelta(hours=1)
        row = _row(start=start, last_activity=start + timedelta(seconds=20))
        assert svc.effective_session_active_duration_seconds(row) == 20


class TestFormatSessionDuration:
    @pytest.mark.parametrize(
        "seconds,expected",
        [(0, "< 1 min"), (59, "< 1 min"), (60, "1 min"), (3599, "59 min"), (3600, "1 h"), (5400, "1 h 30 min")],
    )
    def test_labels(self, app, seconds, expected):
        with app.test_request_context("/"):
            assert svc.format_session_duration(seconds) == expected

    def test_none_is_blank(self, app):
        with app.test_request_context("/"):
            assert svc.format_session_duration(None) == ""


class TestResolveSessionEnd:
    def test_timeout_uses_last_activity(self):
        now = utcnow()
        row = _row(start=now - timedelta(hours=4), last_activity=now - timedelta(hours=3))
        assert svc._resolve_session_end(row, "timeout", now) == row.last_activity

    def test_logout_after_recent_activity_uses_now(self):
        now = utcnow()
        row = _row(start=now - timedelta(minutes=5), last_activity=now - timedelta(seconds=5))
        assert svc._resolve_session_end(row, "logout", now) == now

    def test_logout_after_long_idle_ends_at_last_activity(self):
        now = utcnow()
        row = _row(start=now - timedelta(hours=9), last_activity=now - timedelta(hours=8))
        assert svc._resolve_session_end(row, "logout", now) == row.last_activity

    def test_close_stores_whole_minutes_floor(self):
        now = utcnow()
        row = _row(start=now - timedelta(seconds=119), last_activity=now, is_active=True)
        svc._close_session_log(row, "logout", now)
        assert row.duration_minutes == 1
        assert row.is_active is False
        assert row.ended_by == "logout"


class TestTouchThrottle:
    def test_rapid_touches_write_once(self):
        row = SimpleNamespace(last_activity=utcnow() - timedelta(seconds=1), actions_performed=0)
        before = row.last_activity
        svc._apply_session_activity(row, "heartbeat")
        assert row.last_activity == before

    def test_stale_touch_refreshes(self):
        old = utcnow() - timedelta(seconds=svc.SESSION_TOUCH_MIN_INTERVAL_SECONDS + 5)
        row = SimpleNamespace(last_activity=old, actions_performed=0)
        svc._apply_session_activity(row, "action")
        assert row.last_activity > old
        assert row.actions_performed == 0


class TestPathTemplating:
    def test_template_path_key(self):
        assert template_path_key("/forms/assignment/123/edit") == "/forms/assignment/:id/edit"
        assert template_path_key("/admin/users") == "/admin/users"

    def test_ids_fold_into_template_after_cap(self):
        row = SimpleNamespace(page_view_path_counts={})
        for i in range(PAGE_VIEW_PATH_MAX_KEYS):
            merge_page_view_path_count(row, f"/page-{i}")
        merge_page_view_path_count(row, "/forms/assignment/1")
        merge_page_view_path_count(row, "/forms/assignment/2")
        merge_page_view_path_count(row, "/not-templatable")
        assert row.page_view_path_counts["/forms/assignment/:id"] == 2
        assert row.page_view_path_counts["_other"] == 1


class TestSmallHelpers:
    @pytest.mark.parametrize("value,expected", [
        ("true", True), ("1", True), ("on", True), ("false", False), ("0", False), ("", False), (None, False),
    ])
    def test_parse_bool_arg(self, value, expected):
        assert parse_bool_arg(value) is expected

    def test_iso_utc_has_offset_for_naive_values(self):
        assert iso_utc(datetime(2025, 3, 1, 12, 0, 0)).endswith("+00:00")
        assert iso_utc(None) is None
        assert iso_utc(datetime(2025, 3, 1, 12, 0, 0, tzinfo=timezone.utc)) == "2025-03-01T12:00:00+00:00"


class TestSessionTimeoutPersistsEnd:
    def test_persist_commits(self, app):
        from app.middleware import session_timeout as mod

        with app.app_context(), patch.object(mod, "db") as mock_db:
            mod._persist_session_end()
            mock_db.session.commit.assert_called_once()

    def test_persist_rolls_back_on_failure(self, app):
        from app.middleware import session_timeout as mod

        with app.app_context(), patch.object(mod, "db") as mock_db, patch.object(mod, "safe_rollback") as rb:
            mock_db.session.commit.side_effect = RuntimeError("boom")
            mod._persist_session_end()
            rb.assert_called_once()
