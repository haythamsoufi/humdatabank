"""
Reproduce pentest behaviour for GET /api/users/profile-summary.

When a low-privileged user shares any UserEntityPermission scope with a
high-privileged user, the endpoint returns profile payloads (including
role_badge_key coarse bucket) for that user — matching production evidence
where e.g. user_ids=1 returns a System Manager profile to another account.
"""

from __future__ import annotations

import uuid

import pytest

from app import db
from app.models.core import UserEntityPermission
from tests.factories import create_test_user


@pytest.mark.integration
def test_profile_summary_focal_point_gets_full_profile_when_one_scope_overlaps(
    client, db_session, app
):
    suffix = uuid.uuid4().hex[:10]
    with app.app_context():
        focal = create_test_user(
            db_session,
            email=f"focal_ps_{suffix}@example.com",
            name="Focal PS",
            password="TestPassword123!",
            role="focal_point",
        )
        privileged = create_test_user(
            db_session,
            email=f"privileged_ps_{suffix}@example.com",
            name="Privileged PS",
            password="TestPassword123!",
            role="system_manager",
        )
        branch_id = 4242000 + (hash(suffix) % 9000)
        db.session.add(
            UserEntityPermission(
                user_id=focal.id,
                entity_type="ns_branch",
                entity_id=branch_id,
            )
        )
        db.session.add(
            UserEntityPermission(
                user_id=privileged.id,
                entity_type="ns_branch",
                entity_id=branch_id,
            )
        )
        db.session.commit()
        db.session.refresh(privileged)

    with client.session_transaction() as sess:
        sess["_user_id"] = str(focal.id)
        sess["_fresh"] = True

    ext = str(privileged.external_id)
    resp = client.get(f"/api/users/profile-summary?external_ids={ext}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("success") is True
    profiles = body.get("profiles") or []
    assert len(profiles) == 1
    row = profiles[0]
    assert row.get("id") is None
    assert row.get("external_id") == ext
    assert row["email"] == privileged.email
    assert row.get("role_badge_key") == "system_manager"


@pytest.mark.integration
def test_profile_summary_focal_point_empty_when_no_scope_overlap(
    client, db_session, app
):
    suffix = uuid.uuid4().hex[:10]
    with app.app_context():
        focal = create_test_user(
            db_session,
            email=f"focal_iso_{suffix}@example.com",
            name="Focal ISO",
            password="TestPassword123!",
            role="focal_point",
        )
        other = create_test_user(
            db_session,
            email=f"other_iso_{suffix}@example.com",
            name="Other ISO",
            password="TestPassword123!",
            role="system_manager",
        )
        db.session.add(
            UserEntityPermission(
                user_id=focal.id,
                entity_type="ns_branch",
                entity_id=1111111,
            )
        )
        db.session.add(
            UserEntityPermission(
                user_id=other.id,
                entity_type="ns_branch",
                entity_id=2222222,
            )
        )
        db.session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = str(focal.id)
        sess["_fresh"] = True

    resp = client.get(f"/api/users/profile-summary?user_ids={other.id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("profiles") == []
