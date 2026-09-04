"""
Tests for app/services/audit_trail_session_query.py.

Covers:
  - apply_audit_trail_user_activity_noise_filters (returns a filtered query object)
  - count_audit_visible_entries_for_session (all branches)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.services.audit.trail_session_query import (
    AUDIT_TRAIL_EXCLUDED_ACTIVITY_TYPES,
    apply_audit_trail_user_activity_noise_filters,
    count_audit_visible_entries_for_session,
    count_audit_visible_entries_for_sessions,
)


# ---------------------------------------------------------------------------
# apply_audit_trail_user_activity_noise_filters
# ---------------------------------------------------------------------------
class TestApplyAuditTrailNoiseFilters:
    def test_returns_query_object(self, app):
        with app.app_context():
            from app.models import UserActivityLog

            # Just verify the function accepts a query and returns a query
            q = UserActivityLog.query
            result = apply_audit_trail_user_activity_noise_filters(q)
            # Result should be a SQLAlchemy Query or BaseQuery
            assert result is not None

    def test_chained_filters_do_not_crash(self, app, db_session):
        """Execute a count to ensure the filter chain is valid SQL."""
        from app.models import UserActivityLog

        q = UserActivityLog.query
        filtered = apply_audit_trail_user_activity_noise_filters(q)
        # This should not raise; tables created by db_session
        count = filtered.count()
        assert count >= 0

    def test_excludes_wizard_endpoint_but_keeps_profile_update(self, app, db_session):
        from app.models import UserActivityLog
        from app.utils.datetime_helpers import utcnow
        from tests.factories import create_test_user

        user = create_test_user(db_session)
        now = utcnow()
        db_session.add(
            UserActivityLog(
                user_id=user.id,
                activity_type="request",
                endpoint="auth.complete_profile",
                url_path="/complete-profile",
                ip_address="127.0.0.1",
                timestamp=now,
            )
        )
        db_session.add(
            UserActivityLog(
                user_id=user.id,
                activity_type="profile_update",
                endpoint="auth.complete_profile",
                url_path="/complete-profile",
                ip_address="127.0.0.1",
                timestamp=now,
            )
        )
        db_session.commit()

        visible = apply_audit_trail_user_activity_noise_filters(UserActivityLog.query).all()
        visible_types = {row.activity_type for row in visible}
        assert visible_types == {"profile_update"}

    def test_excludes_login_and_logout(self, app, db_session):
        """login/logout rows are omitted from audit trail queries."""
        from app.models import UserActivityLog
        from app.utils.datetime_helpers import utcnow
        from tests.factories import create_test_user

        user = create_test_user(db_session)
        now = utcnow()

        for atype in AUDIT_TRAIL_EXCLUDED_ACTIVITY_TYPES:
            db_session.add(
                UserActivityLog(
                    user_id=user.id,
                    activity_type=atype,
                    endpoint="auth.login",
                    url_path="/login",
                    ip_address="127.0.0.1",
                    timestamp=now,
                )
            )
        db_session.add(
            UserActivityLog(
                user_id=user.id,
                activity_type="data_modified",
                endpoint="analytics.audit_trail",
                url_path="/admin/analytics/audit-trail",
                ip_address="127.0.0.1",
                timestamp=now,
            )
        )
        db_session.commit()

        visible = apply_audit_trail_user_activity_noise_filters(UserActivityLog.query).all()
        visible_types = {row.activity_type for row in visible}
        assert visible_types == {"data_modified"}


# ---------------------------------------------------------------------------
# count_audit_visible_entries_for_session
# ---------------------------------------------------------------------------
def _make_session_log(
    session_id="sid-001",
    session_start=None,
    session_end=None,
    actions_performed=5,
    user_id=1,
):
    """Build a mock UserSessionLog."""
    now = datetime.now(timezone.utc)
    sl = MagicMock()
    sl.session_id = session_id
    sl.session_start = session_start or (now - timedelta(hours=1))
    sl.session_end = session_end
    sl.actions_performed = actions_performed
    sl.user_id = user_id
    return sl


class TestCountAuditVisibleEntriesForSession:
    def test_none_session_log_returns_zero(self, app):
        with app.app_context():
            assert count_audit_visible_entries_for_session(None) == 0

    def test_empty_session_id_returns_actions_performed(self, app):
        with app.app_context():
            sl = _make_session_log(session_id="")
            result = count_audit_visible_entries_for_session(sl)
            assert result == sl.actions_performed

    def test_whitespace_session_id_returns_actions_performed(self, app):
        with app.app_context():
            sl = _make_session_log(session_id="   ")
            result = count_audit_visible_entries_for_session(sl)
            assert result == sl.actions_performed

    def test_none_session_start_returns_actions_performed(self, app):
        with app.app_context():
            sl = _make_session_log(session_id="sid-x")
            sl.session_start = None
            result = count_audit_visible_entries_for_session(sl)
            assert result == sl.actions_performed

    def test_valid_session_with_db(self, app, db_session):
        """When a valid session exists, count returns a non-negative integer."""
        from app.models import UserSessionLog
        from app.utils.datetime_helpers import utcnow
        from tests.factories import create_test_user

        now = utcnow()
        user = create_test_user(db_session)
        sl = UserSessionLog(
            session_id="test-count-valid-001",
            user_id=user.id,
            session_start=now - timedelta(hours=1),
            session_end=now,
            actions_performed=0,
            ip_address="127.0.0.1",
        )
        db_session.add(sl)
        db_session.commit()

        result = count_audit_visible_entries_for_session(sl)
        assert isinstance(result, int)
        assert result >= 0

    def test_session_end_before_start_uses_utcnow(self, app, db_session):
        """When session_end < session_start the function falls back to utcnow."""
        from app.models import UserSessionLog
        from app.utils.datetime_helpers import utcnow
        from tests.factories import create_test_user

        now = utcnow()
        user = create_test_user(db_session)
        sl = UserSessionLog(
            session_id="test-backwards-valid-001",
            user_id=user.id,
            session_start=now,
            session_end=now - timedelta(hours=2),  # end before start
            actions_performed=0,
            ip_address="127.0.0.1",
        )
        db_session.add(sl)
        db_session.commit()

        result = count_audit_visible_entries_for_session(sl)
        assert isinstance(result, int)

    def test_session_without_end_uses_utcnow(self, app, db_session):
        """When session_end is None, utcnow() is used as the window end."""
        from app.models import UserSessionLog
        from app.utils.datetime_helpers import utcnow
        from tests.factories import create_test_user

        now = utcnow()
        user = create_test_user(db_session)
        sl = UserSessionLog(
            session_id="test-no-end-valid-001",
            user_id=user.id,
            session_start=now - timedelta(minutes=30),
            session_end=None,
            actions_performed=0,
            ip_address="127.0.0.1",
        )
        db_session.add(sl)
        db_session.commit()

        result = count_audit_visible_entries_for_session(sl)
        assert isinstance(result, int)

    def test_count_includes_activity_and_admin_rows(self, app, db_session):
        """Activity + admin action counts are summed."""
        from app.models import UserActivityLog, AdminActionLog, UserSessionLog
        from app.utils.datetime_helpers import utcnow
        from tests.factories import create_test_user

        now = utcnow()
        session_start = now - timedelta(hours=1)
        user = create_test_user(db_session)

        sl = UserSessionLog(
            session_id="test-count-sum-valid-001",
            user_id=user.id,
            session_start=session_start,
            session_end=now,
            actions_performed=0,
            ip_address="127.0.0.1",
        )
        db_session.add(sl)

        # Add 2 activity logs with countable activity types
        for i in range(2):
            ual = UserActivityLog(
                user_id=user.id,
                user_session_id="test-count-sum-valid-001",
                activity_type="data_modified",
                endpoint="analytics.audit_trail",
                url_path="/admin/analytics/audit-trail",
                ip_address="127.0.0.1",
                timestamp=session_start + timedelta(minutes=i + 5),
            )
            db_session.add(ual)

        # Add 1 admin action log
        aal = AdminActionLog(
            admin_user_id=user.id,
            action_type="user_update",
            action_description="Updated user",
            ip_address="127.0.0.1",
            timestamp=session_start + timedelta(minutes=10),
        )
        db_session.add(aal)
        db_session.commit()

        result = count_audit_visible_entries_for_session(sl)
        assert isinstance(result, int)
        assert result == 3  # 2 activity + 1 admin

    def test_login_logout_not_counted(self, app, db_session):
        """login/logout activity types should be excluded from the count."""
        from app.models import UserActivityLog, UserSessionLog
        from app.utils.datetime_helpers import utcnow
        from tests.factories import create_test_user

        user = create_test_user(db_session)
        now = utcnow()
        session_start = now - timedelta(hours=1)

        sl = UserSessionLog(
            session_id="test-login-excluded-01",
            user_id=user.id,
            session_start=session_start,
            session_end=now,
            actions_performed=0,
            ip_address="127.0.0.1",
        )
        db_session.add(sl)

        for atype in ("login", "logout"):
            ual = UserActivityLog(
                user_id=user.id,
                user_session_id="test-login-excluded-01",
                activity_type=atype,
                ip_address="127.0.0.1",
                timestamp=session_start + timedelta(minutes=1),
            )
            db_session.add(ual)

        db_session.commit()

        result = count_audit_visible_entries_for_session(sl)
        assert result == 0

    def test_noise_endpoints_not_counted(self, app, db_session):
        """Heartbeat/noise endpoints should be filtered out."""
        from app.models import UserActivityLog, UserSessionLog
        from app.utils.datetime_helpers import utcnow
        from tests.factories import create_test_user

        user = create_test_user(db_session)
        now = utcnow()
        session_start = now - timedelta(hours=1)

        sl = UserSessionLog(
            session_id="test-noise-excluded-01",
            user_id=user.id,
            session_start=session_start,
            session_end=now,
            actions_performed=0,
            ip_address="127.0.0.1",
        )
        db_session.add(sl)

        ual = UserActivityLog(
            user_id=user.id,
            user_session_id="test-noise-excluded-01",
            activity_type="page_view",
            endpoint="mobile_api.device_heartbeat",
            ip_address="127.0.0.1",
            timestamp=session_start + timedelta(minutes=1),
        )
        db_session.add(ual)

        db_session.commit()

        result = count_audit_visible_entries_for_session(sl)
        assert result == 0

    def test_wizard_endpoints_not_counted_form_saved_is(self, app, db_session):
        from app.models import UserActivityLog, UserSessionLog
        from app.utils.datetime_helpers import utcnow
        from tests.factories import create_test_user

        user = create_test_user(db_session)
        now = utcnow()
        session_start = now - timedelta(hours=1)

        sl = UserSessionLog(
            session_id="test-draft-excluded-01",
            user_id=user.id,
            session_start=session_start,
            session_end=now,
            actions_performed=0,
            ip_address="127.0.0.1",
        )
        db_session.add(sl)
        db_session.add(
            UserActivityLog(
                user_id=user.id,
                user_session_id="test-draft-excluded-01",
                activity_type="form_saved",
                endpoint="forms.view_edit_form",
                url_path="/forms/assignment/1",
                ip_address="127.0.0.1",
                timestamp=session_start + timedelta(minutes=1),
            )
        )
        db_session.add(
            UserActivityLog(
                user_id=user.id,
                user_session_id="test-draft-excluded-01",
                activity_type="admin_other",
                endpoint="upr_excel_import.analyze",
                url_path="/upr-excel/analyze",
                ip_address="127.0.0.1",
                timestamp=session_start + timedelta(minutes=2),
            )
        )
        db_session.add(
            UserActivityLog(
                user_id=user.id,
                user_session_id="test-draft-excluded-01",
                activity_type="form_submitted",
                endpoint="forms.view_edit_form",
                url_path="/forms/assignment/1",
                ip_address="127.0.0.1",
                timestamp=session_start + timedelta(minutes=3),
            )
        )
        db_session.commit()

        result = count_audit_visible_entries_for_session(sl)
        # form_saved + form_submitted; wizard analyze endpoint is still excluded
        assert result == 2


class TestCountAuditVisibleEntriesForSessionsBatch:
    def test_batch_matches_single_session(self, app, db_session):
        """Batch helper returns the same count as the single-session helper."""
        from app.models import UserActivityLog, UserSessionLog
        from app.utils.datetime_helpers import utcnow
        from tests.factories import create_test_user

        now = utcnow()
        session_start = now - timedelta(hours=1)
        user = create_test_user(db_session)

        sl = UserSessionLog(
            session_id="test-batch-count-001",
            user_id=user.id,
            session_start=session_start,
            session_end=now,
            actions_performed=0,
            ip_address="127.0.0.1",
        )
        db_session.add(sl)
        db_session.add(
            UserActivityLog(
                user_id=user.id,
                user_session_id="test-batch-count-001",
                activity_type="data_modified",
                endpoint="analytics.audit_trail",
                url_path="/admin/analytics/audit-trail",
                ip_address="127.0.0.1",
                timestamp=session_start + timedelta(minutes=5),
            )
        )
        db_session.commit()

        single = count_audit_visible_entries_for_session(sl)
        batch = count_audit_visible_entries_for_sessions([sl])
        assert batch[sl.id] == single

    def test_batch_handles_fallback_sessions(self, app):
        with app.app_context():
            sl = _make_session_log(session_id="", actions_performed=7)
            batch = count_audit_visible_entries_for_sessions([sl])
            assert batch[sl.id] == 7
