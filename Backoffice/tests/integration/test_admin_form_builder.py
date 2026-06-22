"""Integration tests for form builder edit page and mutation routes."""

import json

import pytest

from app.models import FormItem, FormSection, FormTemplate, FormTemplateVersion, db
from app.models.rbac import RbacPermission, RbacRole, RbacRolePermission

from tests.factories import (
    _grant_role_permission,
    create_test_admin,
    create_test_draft_version,
    create_test_item,
    create_test_section,
    create_test_template,
)
from tests.helpers import assert_redirect, login_session


def _create_admin_with_permissions(db_session, permissions):
    admin = create_test_admin(
        db_session,
        can_manage_templates=False,
        can_manage_users=False,
        can_manage_assignments=False,
        can_manage_countries=False,
        can_manage_content=False,
        can_manage_api_keys=False,
        can_manage_system=False,
    )
    for perm_code in permissions:
        _grant_role_permission(db_session, "admin_core", perm_code)
    db_session.commit()
    db_session.refresh(admin)
    return admin


@pytest.mark.integration
class TestFormBuilderEditPage:
    def test_edit_page_renders(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            previous_csrf = app.config.get("WTF_CSRF_ENABLED")
            app.config["WTF_CSRF_ENABLED"] = True
            try:
                template = create_test_template(
                    db_session,
                    name="Editable Template",
                    owner_id=system_manager_user.id,
                )
                template_id = template.id

                resp = logged_in_sm_client.get(f"/admin/templates/edit/{template_id}")
                assert resp.status_code == 200
                body = resp.get_data(as_text=True)
                assert "Editable Template" in body
                assert "form-builder-page.css" in body
            finally:
                app.config["WTF_CSRF_ENABLED"] = previous_csrf

    def test_edit_page_404_for_missing_template(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/templates/edit/999999")
        assert resp.status_code == 404

    def test_edit_page_redirects_for_non_owner(self, logged_in_admin_client, db_session, app, admin_user):
        with app.app_context():
            owner = create_test_admin(db_session, email="template_owner@example.com")
            template = create_test_template(
                db_session,
                name="Foreign Template",
                owner_id=owner.id,
            )
            template_id = template.id

            resp = logged_in_admin_client.get(
                f"/admin/templates/edit/{template_id}",
                follow_redirects=False,
            )
            assert_redirect(resp, "/admin/templates")


@pytest.mark.integration
class TestTemplateDetailsSave:
    def test_post_template_details(self, logged_in_admin_client, db_session, app, admin_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                name="Details Template",
                owner_id=admin_user.id,
            )
            template_id = template.id
            version_id = template.published_version_id

            resp = logged_in_admin_client.post(
                f"/admin/templates/edit/{template_id}",
                data={
                    "submit": "Save Template",
                    "name": "Updated Details Template",
                    "description": "Updated from test",
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
            assert_redirect(resp, f"/admin/templates/edit/{template_id}")

            version = db.session.get(FormTemplateVersion, version_id)
            assert version.name == "Updated Details Template"
            assert version.description == "Updated from test"


@pytest.mark.integration
class TestSectionCRUD:
    def test_new_section(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id
            version_id = template.published_version_id
            before_count = db_session.query(FormSection).count()

            resp = logged_in_sm_client.post(
                f"/admin/templates/{template_id}/sections/new",
                data={
                    "section-name": "Brand New Section",
                    "section-order": "1",
                    "section-section_type": "standard",
                    "version_id": str(version_id),
                },
                follow_redirects=False,
            )
            assert_redirect(resp, f"/admin/templates/edit/{template_id}")
            assert db_session.query(FormSection).count() == before_count + 1
            created = (
                db_session.query(FormSection)
                .filter_by(template_id=template_id, name="Brand New Section")
                .first()
            )
            assert created is not None

    def test_edit_section(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            section = create_test_section(db_session, template, name="Original Section")
            section_id = section.id
            version_id = section.version_id

            resp = logged_in_sm_client.post(
                f"/admin/sections/edit/{section_id}",
                data={
                    "section-name": "Renamed Section",
                    "version_id": str(version_id),
                },
                follow_redirects=False,
            )
            assert resp.status_code in (200, 302, 303, 307, 308)
            updated = db.session.get(FormSection, section_id)
            assert updated.name == "Renamed Section"

    def test_delete_section(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            section = create_test_section(db_session, template, name="Delete Section")
            template_id = template.id
            section_id = section.id
            version_id = section.version_id

            resp = logged_in_sm_client.post(
                f"/admin/sections/delete/{section_id}",
                data={
                    "delete_data": "true",
                    "version_id": str(version_id),
                },
                follow_redirects=False,
            )
            assert_redirect(resp, f"/admin/templates/edit/{template_id}")
            assert db.session.get(FormSection, section_id) is None

    def test_duplicate_section(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id
            section = create_test_section(db_session, template, name="Duplicate Section")
            section_id = section.id
            version_id = section.version_id
            before_count = db_session.query(FormSection).filter_by(template_id=template_id).count()

            resp = logged_in_sm_client.post(
                f"/admin/sections/duplicate/{section_id}",
                data={"version_id": str(version_id)},
                follow_redirects=False,
            )
            assert_redirect(resp, f"/admin/templates/edit/{template_id}")
            assert (
                db_session.query(FormSection).filter_by(template_id=template_id).count()
                == before_count + 1
            )

    def test_unarchive_section(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id
            section = create_test_section(
                db_session,
                template,
                name="Archived Section",
                archived=True,
            )
            section_id = section.id
            version_id = section.version_id

            resp = logged_in_sm_client.post(
                f"/admin/sections/unarchive/{section_id}",
                data={"version_id": str(version_id)},
                follow_redirects=False,
            )
            assert_redirect(resp, f"/admin/templates/edit/{template_id}")
            restored = db.session.get(FormSection, section_id)
            assert restored.archived is False


@pytest.mark.integration
class TestItemCRUD:
    def test_new_item(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id
            section = create_test_section(db_session, template)
            section_id = section.id
            version_id = section.version_id
            before_count = db_session.query(FormItem).count()

            resp = logged_in_sm_client.post(
                f"/admin/templates/{template_id}/sections/{section_id}/items/new",
                json={
                    "item_type": "question",
                    "question_type": "text",
                    "label": "Integration Question",
                    "layout_column_width": "12",
                    "version_id": version_id,
                },
                headers={"Accept": "application/json"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert db_session.query(FormItem).count() == before_count + 1
            created = (
                db_session.query(FormItem)
                .filter_by(section_id=section_id, label="Integration Question")
                .first()
            )
            assert created is not None
            assert created.item_type == "question"

    def test_edit_item(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            section = create_test_section(db_session, template)
            item = create_test_item(
                db_session,
                section,
                template,
                item_type="question",
                label="Original Question",
                type="text",
            )
            item_id = item.id
            section_id = section.id
            version_id = item.version_id

            resp = logged_in_sm_client.post(
                f"/admin/items/edit/{item_id}",
                json={
                    "item_type": "question",
                    "question_type": "textarea",
                    "section_id": section_id,
                    "layout_column_width": "12",
                    "version_id": version_id,
                },
                headers={"Accept": "application/json"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            updated = db.session.get(FormItem, item_id)
            assert updated.type == "textarea"

    def test_delete_item(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            section = create_test_section(db_session, template)
            item = create_test_item(
                db_session,
                section,
                template,
                item_type="question",
                label="Delete Question",
                type="text",
            )
            item_id = item.id
            version_id = item.version_id

            resp = logged_in_sm_client.post(
                f"/admin/items/delete/{item_id}",
                json={
                    "delete_data": "true",
                    "version_id": version_id,
                },
                headers={"Accept": "application/json"},
            )
            assert resp.status_code == 200
            assert db.session.get(FormItem, item_id) is None

    def test_duplicate_item(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            section = create_test_section(db_session, template)
            section_id = section.id
            item = create_test_item(
                db_session,
                section,
                template,
                item_type="question",
                label="Duplicate Question",
                type="text",
            )
            item_id = item.id
            version_id = item.version_id
            before_count = db_session.query(FormItem).filter_by(section_id=section_id).count()

            resp = logged_in_sm_client.post(
                f"/admin/items/duplicate/{item_id}",
                json={"version_id": version_id},
                headers={"Accept": "application/json"},
            )
            assert resp.status_code == 200
            assert (
                db_session.query(FormItem).filter_by(section_id=section_id).count()
                == before_count + 1
            )

    def test_unarchive_item(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            section = create_test_section(db_session, template)
            template_id = template.id
            item = create_test_item(
                db_session,
                section,
                template,
                item_type="question",
                label="Archived Question",
                type="text",
                archived=True,
            )
            item_id = item.id
            version_id = item.version_id

            resp = logged_in_sm_client.post(
                f"/admin/items/unarchive/{item_id}",
                json={"version_id": version_id},
                headers={"Accept": "application/json"},
            )
            assert_redirect(resp, f"/admin/templates/edit/{template_id}")
            restored = db.session.get(FormItem, item_id)
            assert restored.archived is False


@pytest.mark.integration
class TestVersioningRoutes:
    def test_create_draft_version(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id
            before_count = (
                db_session.query(FormTemplateVersion)
                .filter_by(template_id=template_id, status="draft")
                .count()
            )

            resp = logged_in_sm_client.post(
                f"/admin/templates/{template_id}/versions/new",
                follow_redirects=False,
            )
            assert_redirect(resp, f"/admin/templates/edit/{template_id}")
            assert (
                db_session.query(FormTemplateVersion)
                .filter_by(template_id=template_id, status="draft")
                .count()
                == before_count + 1
            )

    def test_deploy_version(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            _grant_role_permission(db_session, "admin_core", "admin.templates.publish")
            db_session.commit()

            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id
            draft = create_test_draft_version(db_session, template, name="Deploy Draft")
            draft_id = draft.id

            resp = logged_in_sm_client.post(
                f"/admin/templates/{template_id}/deploy",
                data={"version_id": str(draft_id)},
                follow_redirects=False,
            )
            assert_redirect(resp, f"/admin/templates/edit/{template_id}")

            template = db.session.get(FormTemplate, template_id)
            draft = db.session.get(FormTemplateVersion, draft_id)
            assert template.published_version_id == draft_id
            assert draft.status == "published"

    def test_discard_draft(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id
            draft = create_test_draft_version(db_session, template, name="Discard Draft")
            draft_id = draft.id

            resp = logged_in_sm_client.post(
                f"/admin/templates/{template_id}/discard_draft",
                follow_redirects=False,
            )
            assert_redirect(resp, f"/admin/templates/edit/{template_id}")
            assert db.session.get(FormTemplateVersion, draft_id) is None

    def test_delete_version(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            _grant_role_permission(db_session, "admin_core", "admin.templates.delete")
            db_session.commit()

            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id
            draft = create_test_draft_version(db_session, template, name="Delete Draft")
            draft_id = draft.id

            resp = logged_in_sm_client.post(
                f"/admin/templates/{template_id}/versions/{draft_id}/delete",
                follow_redirects=False,
            )
            assert_redirect(resp, f"/admin/templates/edit/{template_id}")
            assert db.session.get(FormTemplateVersion, draft_id) is None

    def test_cannot_delete_published_version(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            _grant_role_permission(db_session, "admin_core", "admin.templates.delete")
            db_session.commit()

            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id
            published_version_id = template.published_version_id

            resp = logged_in_sm_client.post(
                f"/admin/templates/{template_id}/versions/{published_version_id}/delete",
                follow_redirects=False,
            )
            assert_redirect(resp, f"/admin/templates/edit/{template_id}")
            assert db.session.get(FormTemplateVersion, published_version_id) is not None

    def test_update_draft_comment(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id
            draft = create_test_draft_version(db_session, template, name="Commented Draft")
            draft_id = draft.id

            resp = logged_in_sm_client.post(
                f"/admin/templates/{template_id}/draft_comment",
                data={"comment": "Integration test note"},
                follow_redirects=False,
            )
            assert_redirect(resp, f"/admin/templates/edit/{template_id}")
            updated_draft = db.session.get(FormTemplateVersion, draft_id)
            assert updated_draft.comment == "Integration test note"

    def test_update_version_comment(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id
            draft = create_test_draft_version(db_session, template, name="Version Note Draft")
            draft_id = draft.id

            resp = logged_in_sm_client.post(
                f"/admin/templates/{template_id}/versions/{draft_id}/comment",
                data={"comment": "Per-version note"},
                follow_redirects=False,
            )
            assert resp.status_code in (302, 303)
            updated_draft = db.session.get(FormTemplateVersion, draft_id)
            assert updated_draft.comment == "Per-version note"


@pytest.mark.integration
class TestTemplateVariables:
    def test_get_variables_page(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id

            resp = logged_in_sm_client.get(
                f"/admin/templates/{template_id}/variables",
                headers={"Accept": "application/json"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert "variables" in data
            assert isinstance(data["variables"], dict)

    def test_post_variable(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id
            version_id = template.published_version_id
            payload = {
                "variables": {
                    "country_name": {
                        "type": "text",
                        "default": "Test Country",
                    }
                }
            }

            resp = logged_in_sm_client.post(
                f"/admin/templates/{template_id}/variables",
                data=json.dumps(payload),
                content_type="application/json",
                headers={"Accept": "application/json"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True

            version = db.session.get(FormTemplateVersion, version_id)
            assert version.variables == payload["variables"]


@pytest.mark.integration
class TestExcelRoutes:
    def test_export_excel_returns_file(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            _grant_role_permission(db_session, "admin_core", "admin.templates.export_excel")
            db_session.commit()

            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id
            section = create_test_section(db_session, template)
            create_test_item(
                db_session,
                section,
                template,
                item_type="question",
                label="Export Question",
                type="text",
            )

            resp = logged_in_sm_client.get(
                f"/admin/templates/{template_id}/export_excel",
            )
            assert resp.status_code == 200
            assert (
                resp.headers.get("Content-Type")
                == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    def test_import_excel_without_file_redirects(self, logged_in_sm_client, db_session, app, system_manager_user):
        with app.app_context():
            _grant_role_permission(db_session, "admin_core", "admin.templates.import_excel")
            db_session.commit()

            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id

            resp = logged_in_sm_client.post(
                f"/admin/templates/{template_id}/import_excel",
                data={},
                follow_redirects=False,
            )
            assert_redirect(resp, f"/admin/templates/edit/{template_id}")

    def test_import_excel_invalid_extension_redirects(self, logged_in_sm_client, db_session, app, system_manager_user):
        import io
        with app.app_context():
            _grant_role_permission(db_session, "admin_core", "admin.templates.import_excel")
            db_session.commit()

            template = create_test_template(
                db_session,
                owner_id=system_manager_user.id,
            )
            template_id = template.id

            resp = logged_in_sm_client.post(
                f"/admin/templates/{template_id}/import_excel",
                data={
                    "excel_file": (io.BytesIO(b"not an xlsx"), "template.csv"),
                },
                content_type="multipart/form-data",
                follow_redirects=False,
            )
            assert_redirect(resp, f"/admin/templates/edit/{template_id}")


@pytest.mark.integration
class TestFormBuilderPermissions:
    def test_section_route_requires_edit_permission(self, client, db_session, app):
        with app.app_context():
            admin = _create_admin_with_permissions(db_session, ["admin.templates.view"])
            template = create_test_template(db_session, owner_id=admin.id)
            template_id = template.id
            login_session(client, admin.id)

            resp = client.post(
                f"/admin/templates/{template_id}/sections/new",
                data={
                    "section-name": "Denied Section",
                    "section-order": "1",
                    "section-section_type": "standard",
                },
                follow_redirects=False,
            )
            assert_redirect(resp)

    def test_deploy_requires_publish_permission(self, client, db_session, app):
        with app.app_context():
            admin = _create_admin_with_permissions(
                db_session,
                ["admin.templates.view", "admin.templates.edit"],
            )
            template = create_test_template(db_session, owner_id=admin.id)
            template_id = template.id
            draft = create_test_draft_version(db_session, template)
            draft_id = draft.id
            login_session(client, admin.id)

            resp = client.post(
                f"/admin/templates/{template_id}/deploy",
                data={"version_id": str(draft_id)},
                follow_redirects=False,
            )
            assert_redirect(resp)

    def test_unauthenticated_redirected(self, client, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            template_id = template.id
            section = create_test_section(db_session, template)
            item = create_test_item(
                db_session,
                section,
                template,
                item_type="question",
                type="text",
            )

            routes = [
                ("POST", f"/admin/templates/{template_id}/sections/new", {"section-name": "X"}),
                ("POST", f"/admin/templates/{template_id}/versions/new", {}),
                ("POST", f"/admin/items/delete/{item.id}", {}),
            ]
            for method, path, payload in routes:
                resp = client.open(
                    path,
                    method=method,
                    data=payload,
                    follow_redirects=False,
                )
                assert_redirect(resp)
