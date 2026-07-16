"""Admin HTML user edit: demoting Admin → Focal Point must strip admin RBAC roles."""

import uuid

import pytest
from werkzeug.datastructures import MultiDict
from flask import url_for

from app.models.rbac import RbacRole, RbacUserRole
from app.models.enums import NotificationType
from tests.factories import create_test_user


def _ensure_role(db_session, code: str, name: str) -> RbacRole:
    role = db_session.query(RbacRole).filter_by(code=code).first()
    if role:
        return role
    role = RbacRole(code=code, name=name)
    db_session.add(role)
    db_session.flush()
    return role


@pytest.mark.integration
def test_edit_user_admin_to_focal_point_strips_documents_manage(
    app, db_session, logged_in_sm_client, monkeypatch
):
    """
    Even if Documents (Manage) is still present in the POST body (UI can hide
    admin sections without unchecking), saving as Focal Point must remove it.
    """
    suffix = uuid.uuid4().hex[:8]
    monkeypatch.setattr(
        "app.routes.admin.user_management.crud._is_azure_sso_enabled",
        lambda: False,
    )

    with app.app_context():
        target = create_test_user(
            db_session,
            email=f"demote_docs_{suffix}@example.com",
            name="Demote Docs User",
            password="TargetPw123!",
            role="admin",
        )
        docs_role = _ensure_role(
            db_session, "admin_documents_manager", "Admin: Documents (Manage)"
        )
        viewer_role = _ensure_role(
            db_session, "assignment_viewer", "Assignment Viewer"
        )
        db_session.add(RbacUserRole(user_id=target.id, role_id=docs_role.id))
        db_session.commit()
        uid = target.id
        docs_role_id = docs_role.id
        viewer_role_id = viewer_role.id
        target_name = target.name

    form_data = []
    for nt in NotificationType:
        form_data.append(("notification_type_email", nt.value))
        form_data.append(("notification_type_push", nt.value))
    form_data.extend(
        [
            ("email", f"demote_docs_{suffix}@example.com"),
            ("name", target_name),
            ("title", ""),
            ("profile_color", "#3B82F6"),
            ("notification_frequency", "instant"),
            ("role_type", "focal_point"),
            # Simulate stale checked admin role still being submitted
            ("rbac_roles", str(docs_role_id)),
            ("rbac_roles", str(viewer_role_id)),
            ("csrf_token", "disabled"),
            ("submit", "Save User"),
        ]
    )

    with app.app_context():
        url = url_for("user_management.edit_user", user_id=uid)

    resp = logged_in_sm_client.post(url, data=MultiDict(form_data), follow_redirects=False)
    assert resp.status_code in (302, 303), resp.get_data(as_text=True)[:1500]

    with app.app_context():
        codes = {
            code
            for code, in (
                RbacUserRole.query.join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                .with_entities(RbacRole.code)
                .filter(RbacUserRole.user_id == uid)
                .all()
            )
        }
        assert "admin_documents_manager" not in codes
        assert "admin_core" not in codes
        assert any(c.startswith("assignment_") for c in codes)
        assert not any(c.startswith("admin_") or c == "system_manager" for c in codes)


@pytest.mark.integration
def test_edit_user_validation_failure_keeps_focal_point_selection(
    app, db_session, logged_in_sm_client, monkeypatch
):
    """On validation errors, Role Type must stay Focal Point and admin ticks must be cleared."""
    suffix = uuid.uuid4().hex[:8]
    monkeypatch.setattr(
        "app.routes.admin.user_management.crud._is_azure_sso_enabled",
        lambda: False,
    )

    with app.app_context():
        target = create_test_user(
            db_session,
            email=f"keep_focal_{suffix}@example.com",
            name="Keep Focal User",
            password="TargetPw123!",
            role="admin",
        )
        docs_role = _ensure_role(
            db_session, "admin_documents_manager", "Admin: Documents (Manage)"
        )
        viewer_role = _ensure_role(
            db_session, "assignment_viewer", "Assignment Viewer"
        )
        db_session.add(RbacUserRole(user_id=target.id, role_id=docs_role.id))
        db_session.commit()
        uid = target.id
        docs_role_id = docs_role.id
        viewer_role_id = viewer_role.id

    form_data = []
    for nt in NotificationType:
        form_data.append(("notification_type_email", nt.value))
        form_data.append(("notification_type_push", nt.value))
    form_data.extend(
        [
            # Invalid email forces validate_on_submit() to fail
            ("email", "not-an-email"),
            ("name", "Keep Focal User"),
            ("title", ""),
            ("profile_color", "#3B82F6"),
            ("notification_frequency", "instant"),
            ("role_type", "focal_point"),
            ("rbac_roles", str(docs_role_id)),
            ("rbac_roles", str(viewer_role_id)),
            ("csrf_token", "disabled"),
            ("submit", "Save User"),
        ]
    )

    with app.app_context():
        url = url_for("user_management.edit_user", user_id=uid)

    resp = logged_in_sm_client.post(url, data=MultiDict(form_data), follow_redirects=False)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'value="focal_point"' in html
    assert 'selected' in html
    # Focal Point option should be the selected one
    assert 'value="focal_point" selected' in html or "value='focal_point' selected" in html or (
        'value="focal_point"' in html and 'selected' in html.split('id="role_type_select"')[1].split("</select>")[0]
    )
    # Documents manage checkbox must not remain checked after scrub
    assert f'value="{docs_role_id}"' in html
    docs_idx = html.find(f'name="rbac_roles" value="{docs_role_id}"')
    if docs_idx < 0:
        docs_idx = html.find(f'value="{docs_role_id}"')
    assert docs_idx >= 0
    checkbox_snippet = html[max(0, docs_idx - 120): docs_idx + 80]
    assert "checked" not in checkbox_snippet.lower()
