"""Tests for country access request reconciliation."""

import pytest

from app.models import CountryAccessRequest, UserEntityPermission
from app.models.enums import CountryAccessRequestStatusValue, EntityType
from app.services.country_access_request_service import (
    AUTO_RESOLVED_ADMIN_NOTE,
    count_pending_country_access_requests_needing_action,
    is_auto_resolved_country_access_request,
    pending_country_access_requests_query,
    reconcile_fulfilled_pending_country_access_requests,
)
from tests.factories import create_test_country, create_test_user

pytestmark = [pytest.mark.unit]


def _make_access_request(db_session, user, country, status="pending"):
    req = CountryAccessRequest(
        user_id=user.id,
        country_id=country.id,
        status=status,
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)
    return req


def _grant_country_permission(db_session, user, country):
    perm = UserEntityPermission(
        user_id=user.id,
        entity_type=EntityType.country.value,
        entity_id=country.id,
    )
    db_session.add(perm)
    db_session.commit()
    return perm


class TestCountryAccessRequestReconciliation:
    def test_pending_query_excludes_requests_with_existing_permission(self, db_session):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="reconcile-query@example.com")
        req = _make_access_request(db_session, user, country)
        _grant_country_permission(db_session, user, country)

        pending_ids = {r.id for r in pending_country_access_requests_query().all()}
        assert req.id not in pending_ids
        assert count_pending_country_access_requests_needing_action() == 0

    def test_reconcile_marks_fulfilled_pending_as_approved(self, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="reconcile-close@example.com")
        req = _make_access_request(db_session, user, country)
        _grant_country_permission(db_session, user, country)

        resolved = reconcile_fulfilled_pending_country_access_requests(
            user_id=user.id,
            processed_by_user_id=admin_user.id,
            log_actions=False,
        )

        db_session.refresh(req)
        assert resolved == 1
        assert req.status == CountryAccessRequestStatusValue.approved.value
        assert req.processed_by_user_id == admin_user.id
        assert req.admin_notes == AUTO_RESOLVED_ADMIN_NOTE
        assert count_pending_country_access_requests_needing_action() == 0

    def test_reconcile_leaves_unfulfilled_pending_unchanged(self, db_session):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="still-pending@example.com")
        req = _make_access_request(db_session, user, country)

        resolved = reconcile_fulfilled_pending_country_access_requests(user_id=user.id)

        db_session.refresh(req)
        assert resolved == 0
        assert req.status == CountryAccessRequestStatusValue.pending.value
        assert count_pending_country_access_requests_needing_action() == 1

    def test_processed_query_includes_auto_resolved_requests(self, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="auto-resolved-processed@example.com")
        req = _make_access_request(db_session, user, country)
        _grant_country_permission(db_session, user, country)

        reconcile_fulfilled_pending_country_access_requests(
            user_id=user.id,
            processed_by_user_id=admin_user.id,
        )

        db_session.refresh(req)
        from app.services.country_access_request_service import processed_country_access_requests_query

        processed_ids = {r.id for r in processed_country_access_requests_query().all()}
        assert req.id in processed_ids
        assert is_auto_resolved_country_access_request(req)
