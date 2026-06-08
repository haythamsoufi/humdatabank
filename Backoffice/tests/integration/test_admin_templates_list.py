"""Integration tests for admin template list page and template lifecycle routes."""

import pytest

from app.models import FormTemplate, db
from app.models.rbac import RbacPermission, RbacRole, RbacRolePermission

from tests.factories import (
    _grant_role_permission,
    create_test_admin,
    create_test_template,
)
from tests.helpers import assert_redirect, login_session


def _create_admin_without_template_delete(db_session):
    admin = create_test_admin(
        db_session,
        can_manage_templates=True,
        can_manage_users=False,
        can_manage_assignments=False,
        can_manage_countries=False,
        can_manage_content=False,
        can_manage_api_keys=False,
        can_manage_system=False,
    )
    role = db_session.query(RbacRole).filter_by(code="admin_core").first()
    perm = db_session.query(RbacPermission).filter_by(code="admin.templates.delete").first()
    if role and perm:
        db_session.query(RbacRolePermission).filter_by(
            role_id=role.id,
            permission_id=perm.id,
        ).delete()
    db_session.commit()
    db_session.refresh(admin)
    return admin


@pytest.mark.integration
class TestTemplatesListPage:
    def test_list_renders_template_names(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            template = create_test_template(
                db_session,
                name="Coverage Template Alpha",
            )
            template_id = template.id

            resp = logged_in_sm_client.get("/admin/templates")
            assert resp.status_code == 200
            body = resp.get_data(as_text=True)
            assert "Coverage Template Alpha" in body
            assert 'id="templatesGrid"' in body
            assert str(template_id) in body

    def test_list_empty_state(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/templates")
        assert resp.status_code == 200
        assert "No form templates found." in resp.get_data(as_text=True)

    def test_list_requires_auth(self, client):
        resp = client.get("/admin/templates", follow_redirects=False)
        assert_redirect(resp)


@pytest.mark.integration
class TestTemplateDeleteFlow:
    def test_get_delete_info_returns_json(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                name="Delete Info Template",
                owner_id=system_manager_user.id,
            )
            template_id = template.id

            resp = logged_in_sm_client.get(
                f"/admin/templates/{template_id}/delete-info",
                headers={"Accept": "application/json"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["template_id"] == template_id
            assert data["template_name"] == "Delete Info Template"
            assert "structure_counts" in data
            assert "assignments" in data

    def test_delete_template(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                name="Delete Me Template",
                owner_id=system_manager_user.id,
            )
            template_id = template.id

            resp = logged_in_sm_client.post(
                f"/admin/templates/delete/{template_id}",
                data={"confirmed": "true"},
                follow_redirects=False,
            )
            assert_redirect(resp, "/admin/templates")
            assert db.session.get(FormTemplate, template_id) is None

    def test_delete_requires_permission(self, client, db_session, app):
        with app.app_context():
            admin = _create_admin_without_template_delete(db_session)
            template = create_test_template(
                db_session,
                name="Protected Delete Template",
                owner_id=admin.id,
            )
            template_id = template.id
            login_session(client, admin.id)

            resp = client.get(
                f"/admin/templates/{template_id}/delete-info",
                headers={"Accept": "application/json"},
                follow_redirects=False,
            )
            assert resp.status_code in (301, 302, 303, 307, 308, 403)


@pytest.mark.integration
class TestTemplateDuplicate:
    def test_duplicate_template(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            _grant_role_permission(db_session, "admin_core", "admin.templates.duplicate")
            db_session.commit()

            source = create_test_template(
                db_session,
                name="Source Template",
                owner_id=system_manager_user.id,
            )
            source_id = source.id
            before_count = db_session.query(FormTemplate).count()

            resp = logged_in_sm_client.post(
                f"/admin/templates/duplicate/{source_id}",
                follow_redirects=False,
            )
            assert_redirect(resp, "/admin/templates/edit/")
            assert db_session.query(FormTemplate).count() == before_count + 1

            copied_template = (
                db_session.query(FormTemplate)
                .filter(FormTemplate.id != source_id)
                .order_by(FormTemplate.id.desc())
                .first()
            )
            assert copied_template is not None
            assert copied_template.owned_by == system_manager_user.id


@pytest.mark.integration
class TestTemplateCreate:
    def test_create_form_renders(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            _grant_role_permission(db_session, "admin_core", "admin.templates.create")
            db_session.commit()

            resp = logged_in_sm_client.get("/admin/templates/new")
            assert resp.status_code == 200
            assert "Create New Form Template" in resp.get_data(as_text=True)

    def test_create_template_post(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            _grant_role_permission(db_session, "admin_core", "admin.templates.create")
            db_session.commit()
            before_count = db_session.query(FormTemplate).count()

            resp = logged_in_sm_client.post(
                "/admin/templates/new",
                data={
                    "name": "Brand New Template",
                    "description": "Created from integration test",
                    "add_to_self_report": "n",
                    "display_order_visible": "n",
                    "is_paginated": "n",
                    "enable_export_pdf": "n",
                    "enable_export_excel": "n",
                    "enable_import_excel": "n",
                    "enable_ai_validation": "n",
                    "enable_data_quality": "n",
                },
                follow_redirects=False,
            )
            assert_redirect(resp, "/admin/templates/edit/")
            assert db_session.query(FormTemplate).count() == before_count + 1
