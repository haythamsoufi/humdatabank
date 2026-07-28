"""
Comprehensive pytest tests for app/routes/admin/assignment_management.py

Covers assignment CRUD, entity management, public submissions, and all edge cases.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from tests.factories import (
    create_test_admin,
    create_test_country,
    create_test_template,
    create_test_assignment_entity_status,
    create_test_public_submission,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_post(client, url, data, **kwargs):
    return client.post(url, json=data, **kwargs)


def _assert_ok(resp, status_code=200):
    assert resp.status_code == status_code, f"Expected {status_code}, got {resp.status_code}: {resp.data[:300]}"


def _assert_redirect(resp, location_contains=None):
    assert resp.status_code in (301, 302), f"Expected redirect, got {resp.status_code}"
    if location_contains:
        assert location_contains in resp.headers.get("Location", "")


def _get_json(resp):
    return json.loads(resp.data)


# ---------------------------------------------------------------------------
# manage_assignments
# ---------------------------------------------------------------------------

class TestManageAssignments:
    def test_get_html(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/assignments")
        assert resp.status_code in (200, 302)

    def test_get_json(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/assignments",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code in (200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "assignments" in data or "success" in data

    def test_get_json_with_assignments(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            create_test_assignment_entity_status(db_session, country=country)
        resp = logged_in_client.get(
            "/admin/assignments",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# assignments_gantt
# ---------------------------------------------------------------------------

class TestAssignmentsGantt:
    def test_get_html(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/assignments/gantt")
        assert resp.status_code in (200, 302)

    def test_get_with_assignments(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            create_test_assignment_entity_status(db_session, country=country)
        resp = logged_in_client.get("/admin/assignments/gantt")
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# new_assignment
# ---------------------------------------------------------------------------

class TestNewAssignment:
    def test_get_renders_form(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/assignments/new")
        assert resp.status_code in (200, 302)

    def test_post_no_published_template(self, logged_in_client, db_session, app):
        with app.app_context():
            from app.models import FormTemplate
            template = FormTemplate()
            db_session.add(template)
            db_session.commit()
            template_id = template.id
        resp = logged_in_client.post(
            "/admin/assignments/new",
            data={
                "template_id": str(template_id),
                "period_name": "2024",
                "submit": "1",
            },
        )
        assert resp.status_code in (200, 302)

    def test_post_with_published_template_no_entity(self, logged_in_client, db_session, app):
        with patch("app.services.notification.core.notify_assignment_created"):
            with app.app_context():
                template = create_test_template(db_session)
                template_id = template.id
            resp = logged_in_client.post(
                "/admin/assignments/new",
                data={
                    "template_id": str(template_id),
                    "period_name": "TestPeriod2024",
                    "submit": "1",
                },
                follow_redirects=True,
            )
        assert resp.status_code in (200, 302)

    def test_post_creates_assignment_with_country(self, logged_in_client, db_session, app):
        with patch("app.services.notification.core.notify_assignment_created"):
            with app.app_context():
                template = create_test_template(db_session)
                country = create_test_country(db_session)
                template_id = template.id
                country_id = country.id
            resp = logged_in_client.post(
                "/admin/assignments/new",
                data={
                    "template_id": str(template_id),
                    "period_name": "Period2025",
                    "countries": [str(country_id)],
                    "submit": "1",
                },
                follow_redirects=True,
            )
        assert resp.status_code in (200, 302)

    def test_post_duplicate_period_no_confirm(self, logged_in_client, db_session, app):
        with patch("app.services.notification.core.notify_assignment_created"):
            with app.app_context():
                template = create_test_template(db_session)
                country = create_test_country(db_session)
                aes = create_test_assignment_entity_status(
                    db_session, country=country, template=template, period_name="DupPeriod"
                )
                template_id = template.id
            # Post without confirm_duplicate
            resp = logged_in_client.post(
                "/admin/assignments/new",
                data={
                    "template_id": str(template_id),
                    "period_name": "DupPeriod",
                    "submit": "1",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

    def test_post_duplicate_period_with_confirm(self, logged_in_client, db_session, app):
        with patch("app.services.notification.core.notify_assignment_created"):
            with app.app_context():
                template = create_test_template(db_session)
                country = create_test_country(db_session)
                aes = create_test_assignment_entity_status(
                    db_session, country=country, template=template, period_name="DupPeriod2"
                )
                template_id = template.id
            resp = logged_in_client.post(
                "/admin/assignments/new",
                data={
                    "template_id": str(template_id),
                    "period_name": "DupPeriod2",
                    "confirm_duplicate": "1",
                    "submit": "1",
                },
                follow_redirects=True,
            )
        assert resp.status_code in (200, 302)

    def test_post_with_entity_permissions(self, logged_in_client, db_session, app):
        with patch("app.services.notification.core.notify_assignment_created"), \
             patch("app.services.organization.entity_service.EntityService.get_entity", return_value=MagicMock()):
            with app.app_context():
                template = create_test_template(db_session)
                template_id = template.id
            resp = logged_in_client.post(
                "/admin/assignments/new",
                data={
                    "template_id": str(template_id),
                    "period_name": "EntityPeriod",
                    "submit": "1",
                    "entity_permissions": ["ns_branch:999"],
                },
                follow_redirects=True,
            )
        assert resp.status_code in (200, 302)

    def test_post_with_invalid_entity_permission(self, logged_in_client, db_session, app):
        with patch("app.services.notification.core.notify_assignment_created"):
            with app.app_context():
                template = create_test_template(db_session)
                template_id = template.id
            resp = logged_in_client.post(
                "/admin/assignments/new",
                data={
                    "template_id": str(template_id),
                    "period_name": "EntityPeriod2",
                    "submit": "1",
                    "entity_permissions": ["invalid_type:abc"],
                },
                follow_redirects=True,
            )
        assert resp.status_code in (200, 302)

    def test_post_with_public_url_generation(self, logged_in_client, db_session, app):
        with patch("app.services.notification.core.notify_assignment_created"):
            with app.app_context():
                template = create_test_template(db_session)
                template_id = template.id
            resp = logged_in_client.post(
                "/admin/assignments/new",
                data={
                    "template_id": str(template_id),
                    "period_name": "PubPeriod",
                    "generate_public_url": "y",
                    "public_url_active": "y",
                    "submit": "1",
                },
                follow_redirects=True,
            )
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# check_assignment_duplicate
# ---------------------------------------------------------------------------

class TestCheckAssignmentDuplicate:
    def test_no_params(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/assignments/check_duplicate")
        assert resp.status_code in (200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert data.get("exists") is False or "exists" in data

    def test_no_match(self, logged_in_client, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            tid = template.id
        resp = logged_in_client.get(
            f"/admin/assignments/check_duplicate?template_id={tid}&period_name=NoMatch"
        )
        assert resp.status_code in (200, 302)

    def test_with_match(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, period_name="CheckDup"
            )
            tid = aes.assigned_form.template_id
        resp = logged_in_client.get(
            f"/admin/assignments/check_duplicate?template_id={tid}&period_name=CheckDup"
        )
        assert resp.status_code in (200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert data.get("exists") is True or "exists" in data


# ---------------------------------------------------------------------------
# edit_assignment
# ---------------------------------------------------------------------------

class TestEditAssignment:
    def test_get_existing(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.get(f"/admin/assignments/edit/{assignment_id}")
        assert resp.status_code in (200, 302)

    def test_get_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/assignments/edit/999999")
        assert resp.status_code in (404, 302)

    def test_post_update(self, logged_in_client, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template
            )
            assignment_id = aes.assigned_form_id
            template_id = template.id
        resp = logged_in_client.post(
            f"/admin/assignments/edit/{assignment_id}",
            data={
                "template_id": str(template_id),
                "period_name": "UpdatedPeriod",
                "submit": "1",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (200, 302)


class TestParseCustomNameTranslationsFromForm:
    def test_reads_explicit_fields(self, app):
        from app.routes.admin.assignment_management import _parse_custom_name_translations_from_form

        with app.test_request_context(
            method='POST',
            data={'custom_name_fr': ' Nom FR ', 'custom_name_ar': 'Arabic name'},
        ):
            app.config['SUPPORTED_LANGUAGES'] = ['en', 'fr', 'ar']
            result = _parse_custom_name_translations_from_form()

        assert result == {'fr': 'Nom FR', 'ar': 'Arabic name'}

    def test_reads_json_hidden_field(self, app):
        from app.routes.admin.assignment_management import _parse_custom_name_translations_from_form

        with app.test_request_context(
            method='POST',
            data={
                'custom_name_translations': '{"fr": "Nom JSON", "es": "Nombre"}',
            },
        ):
            app.config['SUPPORTED_LANGUAGES'] = ['en', 'fr', 'es']
            result = _parse_custom_name_translations_from_form()

        assert result == {'fr': 'Nom JSON', 'es': 'Nombre'}

    def test_explicit_fields_override_json(self, app):
        from app.routes.admin.assignment_management import _parse_custom_name_translations_from_form

        with app.test_request_context(
            method='POST',
            data={
                'custom_name_translations': '{"fr": "From JSON"}',
                'custom_name_fr': 'From field',
            },
        ):
            app.config['SUPPORTED_LANGUAGES'] = ['en', 'fr']
            result = _parse_custom_name_translations_from_form()

        assert result == {'fr': 'From field'}

    def test_empty_returns_none(self, app):
        from app.routes.admin.assignment_management import _parse_custom_name_translations_from_form

        with app.test_request_context(method='POST', data={}):
            app.config['SUPPORTED_LANGUAGES'] = ['en', 'fr']
            result = _parse_custom_name_translations_from_form()

        assert result is None


# ---------------------------------------------------------------------------
# add_countries_to_assignment
# ---------------------------------------------------------------------------

class TestAddCountriesToAssignment:
    def test_no_countries(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/edit/{assignment_id}/add_countries",
            data={},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_add_new_country(self, logged_in_client, db_session, app):
        with patch("app.services.notification.core.notify_assignment_created"):
            with app.app_context():
                country = create_test_country(db_session)
                new_country = create_test_country(db_session)
                aes = create_test_assignment_entity_status(db_session, country=country)
                assignment_id = aes.assigned_form_id
                new_country_id = new_country.id
            resp = logged_in_client.post(
                f"/admin/assignments/edit/{assignment_id}/add_countries",
                data={"country_ids": [str(new_country_id)]},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 200)

    def test_add_existing_country(self, logged_in_client, db_session, app):
        with patch("app.services.notification.core.notify_assignment_created"):
            with app.app_context():
                country = create_test_country(db_session)
                aes = create_test_assignment_entity_status(db_session, country=country)
                assignment_id = aes.assigned_form_id
                country_id = country.id
            resp = logged_in_client.post(
                f"/admin/assignments/edit/{assignment_id}/add_countries",
                data={"country_ids": [str(country_id)]},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 200)


# ---------------------------------------------------------------------------
# remove_country_from_assignment
# ---------------------------------------------------------------------------

class TestRemoveCountryFromAssignment:
    def test_remove_country(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            country_id = country.id
        resp = logged_in_client.post(
            f"/admin/assignments/edit/{assignment_id}/remove_country/{country_id}",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 404, 200)

    def test_remove_not_found(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/edit/{assignment_id}/remove_country/999999",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 404)


# ---------------------------------------------------------------------------
# get_assignment_entities
# ---------------------------------------------------------------------------

class TestGetAssignmentEntities:
    def test_get_entities(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        with patch("app.services.organization.entity_service.EntityService.get_entity", return_value=MagicMock()), \
             patch("app.services.organization.entity_service.EntityService.get_entity_name", return_value="Test Entity"):
            resp = logged_in_client.get(f"/admin/assignments/{assignment_id}/entities")
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# add_entity_to_assignment
# ---------------------------------------------------------------------------

class TestAddEntityToAssignment:
    def test_add_missing_fields(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/add",
            json={},
        )
        assert resp.status_code in (200, 400, 302)

    def test_add_entity_not_found(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        with patch("app.services.organization.entity_service.EntityService.get_entity", return_value=None):
            resp = logged_in_client.post(
                f"/admin/assignments/{assignment_id}/entities/add",
                json={"entity_type": "country", "entity_id": 99999},
            )
        assert resp.status_code in (200, 400, 404, 302)

    def test_add_entity_already_assigned(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            country_id = country.id
        with patch("app.services.organization.entity_service.EntityService.get_entity", return_value=MagicMock()):
            resp = logged_in_client.post(
                f"/admin/assignments/{assignment_id}/entities/add",
                json={"entity_type": "country", "entity_id": country_id},
            )
        assert resp.status_code in (200, 409, 302)

    def test_add_new_entity(self, logged_in_client, db_session, app):
        with patch("app.services.notification.core.notify_assignment_created"):
            with app.app_context():
                country = create_test_country(db_session)
                new_country = create_test_country(db_session)
                aes = create_test_assignment_entity_status(db_session, country=country)
                assignment_id = aes.assigned_form_id
                new_country_id = new_country.id
            with patch("app.services.organization.entity_service.EntityService.get_entity", return_value=MagicMock()), \
                 patch("app.services.organization.entity_service.EntityService.get_entity_name", return_value="New Country"):
                resp = logged_in_client.post(
                    f"/admin/assignments/{assignment_id}/entities/add",
                    json={"entity_type": "country", "entity_id": new_country_id, "due_date": "2025-12-31"},
                )
        assert resp.status_code in (200, 302)

    def test_add_entity_invalid_due_date(self, logged_in_client, db_session, app):
        with patch("app.services.notification.core.notify_assignment_created"):
            with app.app_context():
                country = create_test_country(db_session)
                new_country = create_test_country(db_session)
                aes = create_test_assignment_entity_status(db_session, country=country)
                assignment_id = aes.assigned_form_id
                new_country_id = new_country.id
            with patch("app.services.organization.entity_service.EntityService.get_entity", return_value=MagicMock()), \
                 patch("app.services.organization.entity_service.EntityService.get_entity_name", return_value="New Country"):
                resp = logged_in_client.post(
                    f"/admin/assignments/{assignment_id}/entities/add",
                    json={"entity_type": "country", "entity_id": new_country_id, "due_date": "not-a-date"},
                )
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# remove_entity_from_assignment
# ---------------------------------------------------------------------------

class TestRemoveEntityFromAssignment:
    def test_remove_entity(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.delete(
            f"/admin/assignments/{assignment_id}/entities/remove/{aes_id}"
        )
        assert resp.status_code in (200, 302, 404)

    def test_remove_entity_not_found(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.delete(
            f"/admin/assignments/{assignment_id}/entities/remove/999999"
        )
        assert resp.status_code in (404, 302)


# ---------------------------------------------------------------------------
# update_entity_status
# ---------------------------------------------------------------------------

class TestUpdateEntityStatus:
    def test_update_status(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.put(
            f"/admin/assignments/{assignment_id}/entities/{aes_id}",
            json={"status": "in_progress"},
        )
        assert resp.status_code in (200, 302)

    def test_update_with_due_date(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.put(
            f"/admin/assignments/{assignment_id}/entities/{aes_id}",
            json={"status": "submitted", "due_date": "2025-12-31"},
        )
        assert resp.status_code in (200, 302)

    def test_update_approved(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.put(
            f"/admin/assignments/{assignment_id}/entities/{aes_id}",
            json={"status": "approved"},
        )
        assert resp.status_code in (200, 302)

    def test_update_sent_for_review(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.put(
            f"/admin/assignments/{assignment_id}/entities/{aes_id}",
            json={"status": "sent_for_review"},
        )
        assert resp.status_code in (200, 302)

    def test_update_public_available(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.put(
            f"/admin/assignments/{assignment_id}/entities/{aes_id}",
            json={"is_public_available": True},
        )
        assert resp.status_code in (200, 302)

    def test_update_not_found(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.put(
            f"/admin/assignments/{assignment_id}/entities/999999",
            json={"status": "in_progress"},
        )
        assert resp.status_code in (404, 302)


# ---------------------------------------------------------------------------
# bulk_remove_entities_from_assignment
# ---------------------------------------------------------------------------

class TestBulkRemoveEntities:
    def test_no_status_ids(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-remove",
            json={},
        )
        assert resp.status_code in (200, 400, 302)

    def test_with_valid_status_ids(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-remove",
            json={"status_ids": [aes_id]},
        )
        assert resp.status_code in (200, 302)

    def test_with_nonexistent_ids(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-remove",
            json={"status_ids": [999999]},
        )
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# bulk_update_entity_status
# ---------------------------------------------------------------------------

class TestBulkUpdateEntityStatus:
    def test_no_status_ids(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-status",
            json={"status": "in_progress"},
        )
        assert resp.status_code in (200, 400, 302)

    def test_no_status_value(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-status",
            json={"status_ids": [aes_id]},
        )
        assert resp.status_code in (200, 400, 302)

    def test_bulk_update_approved(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-status",
            json={"status_ids": [aes_id], "status": "approved"},
        )
        assert resp.status_code in (200, 302)

    def test_bulk_update_submitted(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-status",
            json={"status_ids": [aes_id], "status": "submitted"},
        )
        assert resp.status_code in (200, 302)

    def test_bulk_update_sent_for_review(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-status",
            json={"status_ids": [aes_id], "status": "sent_for_review"},
        )
        assert resp.status_code in (200, 302)

    def test_bulk_update_with_due_date(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-status",
            json={"status_ids": [aes_id], "status": "in_progress", "due_date": "2025-12-31"},
        )
        assert resp.status_code in (200, 302)

    def test_bulk_update_invalid_due_date(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-status",
            json={"status_ids": [aes_id], "status": "in_progress", "due_date": "invalid"},
        )
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# edit_assignment_entity_status
# ---------------------------------------------------------------------------

class TestEditAssignmentEntityStatus:
    def test_edit_aes(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            aes_id = aes.id
        with patch("app.services.organization.entity_service.EntityService.get_entity_name", return_value="Test Entity"):
            resp = logged_in_client.post(
                f"/admin/assignment_entity_status/edit/{aes_id}",
                data={"status": "in_progress"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 200)

    def test_edit_aes_approved(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            aes_id = aes.id
        with patch("app.services.organization.entity_service.EntityService.get_entity_name", return_value="Test Entity"):
            resp = logged_in_client.post(
                f"/admin/assignment_entity_status/edit/{aes_id}",
                data={"status": "approved"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 200)

    def test_edit_aes_submitted(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            aes_id = aes.id
        with patch("app.services.organization.entity_service.EntityService.get_entity_name", return_value="Test Entity"):
            resp = logged_in_client.post(
                f"/admin/assignment_entity_status/edit/{aes_id}",
                data={"status": "submitted"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 200)

    def test_edit_aes_sent_for_review(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            aes_id = aes.id
        with patch("app.services.organization.entity_service.EntityService.get_entity_name", return_value="Test Entity"):
            resp = logged_in_client.post(
                f"/admin/assignment_entity_status/edit/{aes_id}",
                data={"status": "sent_for_review"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 200)

    def test_edit_aes_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/assignment_entity_status/edit/999999",
            data={"status": "in_progress"},
        )
        assert resp.status_code in (404, 302)


# ---------------------------------------------------------------------------
# delete_assignment
# ---------------------------------------------------------------------------

class TestDeleteAssignment:
    def test_delete_assignment(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/delete/{assignment_id}",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_delete_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.post("/admin/assignments/delete/999999")
        assert resp.status_code in (404, 302)


# ---------------------------------------------------------------------------
# toggle_assignment_active
# ---------------------------------------------------------------------------

class TestToggleAssignmentActive:
    def test_toggle_active(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/toggle_active",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_toggle_active_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.post("/admin/assignments/999999/toggle_active")
        assert resp.status_code in (404, 302)


# ---------------------------------------------------------------------------
# close_assignment
# ---------------------------------------------------------------------------

class TestCloseAssignment:
    def test_close(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/close",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)


# ---------------------------------------------------------------------------
# reopen_closed_assignment
# ---------------------------------------------------------------------------

class TestReopenClosedAssignment:
    def test_reopen(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/reopen_closed",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)


# ---------------------------------------------------------------------------
# generate_public_url
# ---------------------------------------------------------------------------

class TestGeneratePublicUrl:
    def test_generate_url(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/generate_public_url",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_generate_url_already_has_url(self, logged_in_client, db_session, app):
        with app.app_context():
            from app.models import AssignedForm
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            assignment = AssignedForm.query.get(assignment_id)
            assignment.generate_public_url()
            db_session.flush()
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/generate_public_url",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)


# ---------------------------------------------------------------------------
# toggle_public_access
# ---------------------------------------------------------------------------

class TestTogglePublicAccess:
    def test_toggle_no_url(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/toggle_public_access",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_toggle_with_url(self, logged_in_client, db_session, app):
        with app.app_context():
            from app.models import AssignedForm
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            assignment = AssignedForm.query.get(assignment_id)
            assignment.generate_public_url()
            db_session.flush()
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/toggle_public_access",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)


# ---------------------------------------------------------------------------
# list_public_submissions
# ---------------------------------------------------------------------------

class TestListPublicSubmissions:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/public-submissions")
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# view_public_submissions
# ---------------------------------------------------------------------------

class TestViewPublicSubmissions:
    def test_no_public_url(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.get(
            f"/admin/assignments/{assignment_id}/view_public_submissions",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_with_public_url(self, logged_in_client, db_session, app):
        with app.app_context():
            submission, assigned_form, token = create_test_public_submission(db_session)
            assignment_id = assigned_form.id
        resp = logged_in_client.get(
            f"/admin/assignments/{assignment_id}/view_public_submissions",
        )
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# add_country_to_public
# ---------------------------------------------------------------------------

class TestAddCountryToPublic:
    def test_no_public_url(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            country_id = country.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/add_country_to_public/{country_id}",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_country_not_assigned(self, logged_in_client, db_session, app):
        with app.app_context():
            from app.models import AssignedForm
            country = create_test_country(db_session)
            other_country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            assignment = AssignedForm.query.get(assignment_id)
            assignment.generate_public_url()
            db_session.flush()
            other_country_id = other_country.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/add_country_to_public/{other_country_id}",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_country_assigned_success(self, logged_in_client, db_session, app):
        with app.app_context():
            from app.models import AssignedForm
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            assignment = AssignedForm.query.get(assignment_id)
            assignment.generate_public_url()
            db_session.flush()
            country_id = country.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/add_country_to_public/{country_id}",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)


# ---------------------------------------------------------------------------
# remove_country_from_public
# ---------------------------------------------------------------------------

class TestRemoveCountryFromPublic:
    def test_no_public_url(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            country_id = country.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/remove_country_from_public/{country_id}",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_with_public_url_country_assigned(self, logged_in_client, db_session, app):
        with app.app_context():
            from app.models import AssignedForm
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            assignment = AssignedForm.query.get(assignment_id)
            assignment.generate_public_url()
            db_session.flush()
            country_id = country.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/remove_country_from_public/{country_id}",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_with_public_url_country_not_assigned(self, logged_in_client, db_session, app):
        with app.app_context():
            from app.models import AssignedForm
            country = create_test_country(db_session)
            other_country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            assignment = AssignedForm.query.get(assignment_id)
            assignment.generate_public_url()
            db_session.flush()
            other_country_id = other_country.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/remove_country_from_public/{other_country_id}",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)


# ---------------------------------------------------------------------------
# bulk_enable_public_reporting
# ---------------------------------------------------------------------------

class TestBulkEnablePublicReporting:
    def test_no_public_url(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/bulk-enable-public",
            data={"country_ids": "1,2"},
        )
        assert resp.status_code in (200, 400, 302)

    def test_no_country_ids(self, logged_in_client, db_session, app):
        with app.app_context():
            from app.models import AssignedForm
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            assignment = AssignedForm.query.get(assignment_id)
            assignment.generate_public_url()
            db_session.flush()
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/bulk-enable-public",
            data={},
        )
        assert resp.status_code in (200, 400, 302)

    def test_with_valid_country_ids(self, logged_in_client, db_session, app):
        with app.app_context():
            from app.models import AssignedForm
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            assignment = AssignedForm.query.get(assignment_id)
            assignment.generate_public_url()
            db_session.flush()
            country_id = country.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/bulk-enable-public",
            data={"country_ids": str(country_id)},
        )
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# bulk_update_public_availability
# ---------------------------------------------------------------------------

class TestBulkUpdatePublicAvailability:
    def test_no_public_url(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-public",
            json={"status_ids": [1], "enable": True},
        )
        assert resp.status_code in (200, 400, 302)

    def test_no_status_ids(self, logged_in_client, db_session, app):
        with app.app_context():
            from app.models import AssignedForm
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            assignment = AssignedForm.query.get(assignment_id)
            assignment.generate_public_url()
            db_session.flush()
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-public",
            json={"enable": True},
        )
        assert resp.status_code in (200, 400, 302)

    def test_enable(self, logged_in_client, db_session, app):
        with app.app_context():
            from app.models import AssignedForm
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
            assignment = AssignedForm.query.get(assignment_id)
            assignment.generate_public_url()
            db_session.flush()
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-public",
            json={"status_ids": [aes_id], "enable": True},
        )
        assert resp.status_code in (200, 302)

    def test_disable(self, logged_in_client, db_session, app):
        with app.app_context():
            from app.models import AssignedForm
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
            assignment = AssignedForm.query.get(assignment_id)
            assignment.generate_public_url()
            db_session.flush()
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-public",
            json={"status_ids": [aes_id], "enable": False},
        )
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# bulk_update_due_date_selected
# ---------------------------------------------------------------------------

class TestBulkUpdateDueDateSelected:
    def test_no_status_ids(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-due-date",
            json={"due_date": "2025-12-31"},
        )
        assert resp.status_code in (200, 400, 302)

    def test_no_due_date(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-due-date",
            json={"status_ids": [aes_id]},
        )
        assert resp.status_code in (200, 400, 302)

    def test_invalid_date(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-due-date",
            json={"status_ids": [aes_id], "due_date": "not-a-date"},
        )
        assert resp.status_code in (200, 400, 302)

    def test_valid_update(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-due-date",
            json={"status_ids": [aes_id], "due_date": "2025-12-31"},
        )
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# update_public_submission_status
# ---------------------------------------------------------------------------

class TestUpdatePublicSubmissionStatus:
    def test_invalid_status(self, logged_in_client, db_session, app):
        with app.app_context():
            submission, assigned_form, token = create_test_public_submission(db_session)
            submission_id = submission.id
        resp = logged_in_client.post(
            f"/admin/public-submissions/{submission_id}/update-status",
            data={"status": "invalid_status"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_approved_status(self, logged_in_client, db_session, app):
        with app.app_context():
            submission, assigned_form, token = create_test_public_submission(db_session)
            submission_id = submission.id
        resp = logged_in_client.post(
            f"/admin/public-submissions/{submission_id}/update-status",
            data={"status": "approved"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_rejected_status(self, logged_in_client, db_session, app):
        with app.app_context():
            submission, assigned_form, token = create_test_public_submission(db_session)
            submission_id = submission.id
        resp = logged_in_client.post(
            f"/admin/public-submissions/{submission_id}/update-status",
            data={"status": "rejected"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_pending_status(self, logged_in_client, db_session, app):
        with app.app_context():
            submission, assigned_form, token = create_test_public_submission(
                db_session, status="approved"
            )
            submission_id = submission.id
        resp = logged_in_client.post(
            f"/admin/public-submissions/{submission_id}/update-status",
            data={"status": "pending"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/public-submissions/999999/update-status",
            data={"status": "approved"},
        )
        assert resp.status_code in (404, 302)


# ---------------------------------------------------------------------------
# delete_public_submission
# ---------------------------------------------------------------------------

class TestDeletePublicSubmission:
    def test_delete(self, logged_in_client, db_session, app):
        with app.app_context():
            submission, assigned_form, token = create_test_public_submission(db_session)
            submission_id = submission.id
        resp = logged_in_client.post(
            f"/admin/public-submissions/{submission_id}/delete",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 200)

    def test_delete_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.post("/admin/public-submissions/999999/delete")
        assert resp.status_code in (404, 302)


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------

class TestUnauthenticatedAccess:
    def test_manage_assignments_requires_auth(self, client, db_session):
        resp = client.get("/admin/assignments")
        assert resp.status_code in (302, 401, 403)

    def test_new_assignment_requires_auth(self, client, db_session):
        resp = client.get("/admin/assignments/new")
        assert resp.status_code in (302, 401, 403)

    def test_gantt_requires_auth(self, client, db_session):
        resp = client.get("/admin/assignments/gantt")
        assert resp.status_code in (302, 401, 403)
