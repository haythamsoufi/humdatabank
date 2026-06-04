"""Admin HTML user edit: email must not change when Azure B2C / SSO is enabled."""

import uuid

import pytest
from werkzeug.datastructures import MultiDict
from flask import url_for

from app import db
from app.models.enums import NotificationType
from app.models.rbac import RbacUserRole
from tests.factories import create_test_user


@pytest.mark.integration
def test_edit_user_email_rejected_when_azure_b2c_enabled(
    app, db_session, logged_in_client, admin_user, monkeypatch
):
    """Tampering the hidden email field must not change DB email when B2C config is present."""
    with app.app_context():
        target = create_test_user(
            db_session,
            email="target_user_b2c@example.com",
            name="Target User",
            password="TargetPw123!",
            role="user",
        )
        role_ids = [
            ur.role_id
            for ur in RbacUserRole.query.filter_by(user_id=target.id).all()
        ]
        assert role_ids
        original_email = target.email
        uid = target.id
        target_name = target.name
        target_title = target.title or ""

    monkeypatch.setattr(
        "app.routes.admin.user_management.crud._is_azure_sso_enabled",
        lambda: True,
    )

    form_data = []
    for nt in NotificationType:
        form_data.append(("notification_type_email", nt.value))
        form_data.append(("notification_type_push", nt.value))
    form_data.extend(
        [
            ("email", "attacker_tampered@evil.example"),
            ("name", target_name),
            ("title", target_title),
            ("profile_color", "#3B82F6"),
            ("notification_frequency", "instant"),
            ("role_type", "focal_point"),
            ("csrf_token", "disabled"),
            ("submit", "Save User"),
        ]
    )
    for rid in role_ids:
        form_data.append(("rbac_roles", str(rid)))

    with app.app_context():
        url = url_for("user_management.edit_user", user_id=uid)

    resp = logged_in_client.post(url, data=MultiDict(form_data), follow_redirects=False)
    assert resp.status_code == 200

    with app.app_context():
        from app.models import User

        again = db.session.get(User, uid)
        assert again is not None
        assert again.email == original_email


@pytest.mark.integration
def test_edit_user_email_allowed_when_local_auth_only(
    app, db_session, logged_in_client, admin_user, monkeypatch
):
    """Without B2C config, admin edit may update email (local identity management)."""
    suffix = uuid.uuid4().hex[:8]
    with app.app_context():
        target = create_test_user(
            db_session,
            email=f"local_user_old_{suffix}@example.com",
            name="Local User",
            password="LocalPw123!",
            role="user",
        )
        role_ids = [
            ur.role_id
            for ur in RbacUserRole.query.filter_by(user_id=target.id).all()
        ]
        assert role_ids
        uid = target.id
        local_name = target.name

    monkeypatch.setattr(
        "app.routes.admin.user_management.crud._is_azure_sso_enabled",
        lambda: False,
    )

    new_email = f"local_user_new_{suffix}@example.com"
    form_data = []
    for nt in NotificationType:
        form_data.append(("notification_type_email", nt.value))
        form_data.append(("notification_type_push", nt.value))
    form_data.extend(
        [
            ("email", new_email),
            ("name", local_name),
            ("title", ""),
            ("profile_color", "#3B82F6"),
            ("notification_frequency", "instant"),
            ("role_type", "focal_point"),
            ("csrf_token", "disabled"),
            ("submit", "Save User"),
        ]
    )
    # Omit rbac_roles from POST: non-system-manager admins may not have the target's
    # role in filtered choices; the route preserves existing roles when not assigning.

    with app.app_context():
        url = url_for("user_management.edit_user", user_id=uid)

    resp = logged_in_client.post(url, data=MultiDict(form_data), follow_redirects=False)
    assert resp.status_code in (302, 303), resp.get_data(as_text=True)[:1000]

    with app.app_context():
        from app.models import User

        again = db.session.get(User, uid)
        assert again is not None
        assert again.email == new_email
