"""
Comprehensive pytest tests for app/routes/admin/assignment_management.py

Covers assignment CRUD, entity management, public submissions, and all edge cases.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from app.routes.admin.assignment_management import (
    _start_assignment_notification_dispatch,
    _dispatch_assignment_created_notifications,
)
from tests.factories import (
    create_test_admin,
    create_test_country,
    create_test_template,
    create_test_assignment_entity_status,
    create_test_public_submission,
    create_test_user,
    create_focal_point_with_country,
    _grant_entity_permission,
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
# new_assignment — async notification dispatch
# (docs/runbooks/incidents/2026-08-12-prod-assignment-create-gateway-timeout.md)
# ---------------------------------------------------------------------------

class TestNewAssignmentNotificationDispatch:
    def test_registers_post_commit_dispatch_for_created_entities(self, logged_in_client, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            country = create_test_country(db_session)
            template_id = template.id
            country_id = country.id

        with patch("app.routes.admin.assignment_management.register_post_commit") as mock_register:
            resp = logged_in_client.post(
                "/admin/assignments/new",
                data={
                    "template_id": str(template_id),
                    "period_name": "AsyncDispatchPeriod",
                    "countries": [str(country_id)],
                    "send_notifications": "y",
                    "notify_admins": "y",
                    "submit": "1",
                },
                follow_redirects=False,
            )

        assert resp.status_code in (200, 302)
        mock_register.assert_called_once()
        callback, aes_ids, notify_admins = mock_register.call_args[0]
        assert callback is _start_assignment_notification_dispatch
        assert len(aes_ids) == 1
        assert notify_admins is True

    def test_send_notifications_unchecked_skips_dispatch(self, logged_in_client, db_session, app):
        """Unchecked 'send notifications' checkbox (omitted from POST, like a real
        browser) must not queue any background dispatch at all."""
        with app.app_context():
            template = create_test_template(db_session)
            country = create_test_country(db_session)
            template_id = template.id
            country_id = country.id

        with patch("app.routes.admin.assignment_management.register_post_commit") as mock_register:
            resp = logged_in_client.post(
                "/admin/assignments/new",
                data={
                    "template_id": str(template_id),
                    "period_name": "NoNotifyPeriod",
                    "countries": [str(country_id)],
                    "submit": "1",
                },
                follow_redirects=False,
            )

        assert resp.status_code in (200, 302)
        mock_register.assert_not_called()

    def test_dispatch_runs_after_commit_and_excludes_creator(
        self, logged_in_client, db_session, app, admin_user
    ):
        """End-to-end (no mocking of register_post_commit): the real post-commit
        callback must fire within the same request (TESTING short-circuits the
        background thread to a synchronous call — see _start_assignment_notification_dispatch)
        and call notify_assignment_created with the committed AES row and the
        creating admin as actor_user_id."""
        with app.app_context():
            template = create_test_template(db_session)
            country = create_test_country(db_session)
            template_id = template.id
            country_id = country.id
            admin_id = admin_user.id

        with patch(
            "app.services.notification.core.notify_assignment_created", return_value=[]
        ) as mock_notify:
            resp = logged_in_client.post(
                "/admin/assignments/new",
                data={
                    "template_id": str(template_id),
                    "period_name": "AsyncDispatchEndToEnd",
                    "countries": [str(country_id)],
                    "send_notifications": "y",
                    "submit": "1",
                },
                follow_redirects=False,
            )

        assert resp.status_code in (200, 302)
        mock_notify.assert_called_once()
        aes_arg = mock_notify.call_args[0][0]
        assert aes_arg.entity_id == country_id
        assert mock_notify.call_args.kwargs["actor_user_id"] == admin_id
        assert mock_notify.call_args.kwargs["notify_admins"] is False


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
# add_countries_to_assignment — async notification dispatch
# ---------------------------------------------------------------------------

class TestAddCountriesToAssignmentNotificationDispatch:
    def test_registers_post_commit_dispatch_for_new_country(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            new_country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            new_country_id = new_country.id

        with patch("app.routes.admin.assignment_management.register_post_commit") as mock_register:
            resp = logged_in_client.post(
                f"/admin/assignments/edit/{assignment_id}/add_countries",
                data={"country_ids": [str(new_country_id)]},
                follow_redirects=False,
            )

        assert resp.status_code in (302, 200)
        mock_register.assert_called_once()
        callback, aes_ids, notify_admins = mock_register.call_args[0]
        assert callback is _start_assignment_notification_dispatch
        assert len(aes_ids) == 1
        assert notify_admins is False

    def test_no_new_country_skips_dispatch(self, logged_in_client, db_session, app):
        """Re-adding an already-assigned country creates no new AES rows, so no
        dispatch should be queued."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            country_id = country.id

        with patch("app.routes.admin.assignment_management.register_post_commit") as mock_register:
            resp = logged_in_client.post(
                f"/admin/assignments/edit/{assignment_id}/add_countries",
                data={"country_ids": [str(country_id)]},
                follow_redirects=False,
            )

        assert resp.status_code in (302, 200)
        mock_register.assert_not_called()


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
# add_entity_to_assignment — async notification dispatch
# ---------------------------------------------------------------------------

class TestAddEntityToAssignmentNotificationDispatch:
    def test_registers_post_commit_dispatch(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            new_country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            new_country_id = new_country.id

        with patch("app.routes.admin.assignment_management.register_post_commit") as mock_register, \
             patch("app.services.organization.entity_service.EntityService.get_entity", return_value=MagicMock()), \
             patch("app.services.organization.entity_service.EntityService.get_entity_name", return_value="New Country"):
            resp = logged_in_client.post(
                f"/admin/assignments/{assignment_id}/entities/add",
                json={"entity_type": "country", "entity_id": new_country_id},
            )

        assert resp.status_code in (200, 302)
        mock_register.assert_called_once()
        callback, aes_ids, notify_admins = mock_register.call_args[0]
        assert callback is _start_assignment_notification_dispatch
        assert len(aes_ids) == 1
        assert notify_admins is False


# ---------------------------------------------------------------------------
# _start_assignment_notification_dispatch / _dispatch_assignment_created_notifications
# (docs/runbooks/incidents/2026-08-12-prod-assignment-create-gateway-timeout.md)
# ---------------------------------------------------------------------------

class TestAssignmentNotificationDispatchHelpers:
    def test_spawns_non_daemon_thread_outside_testing_mode(self, app):
        """Outside TESTING, the request thread must only *start* a background
        thread (fast) rather than run the notify loop inline — this is the actual
        fix for the 504: the slow work must never block the response."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 4242

        with app.app_context():
            with patch("app.routes.admin.assignment_management.current_user", mock_user), \
                 patch.dict(app.config, {"TESTING": False}), \
                 patch("app.routes.admin.assignment_management.threading.Thread") as mock_thread_cls, \
                 patch(
                     "app.routes.admin.assignment_management._dispatch_assignment_created_notifications"
                 ) as mock_dispatch:
                _start_assignment_notification_dispatch([101, 102], True)

        mock_dispatch.assert_not_called()  # must not run inline on the request thread
        mock_thread_cls.assert_called_once()
        _, kwargs = mock_thread_cls.call_args
        assert kwargs["daemon"] is False
        assert kwargs["target"] is mock_dispatch
        assert kwargs["args"][1:] == ([101, 102], True, 4242)
        mock_thread_cls.return_value.start.assert_called_once()

    def test_runs_synchronously_under_testing_mode(self, app):
        """Under TESTING, dispatch runs on the caller's thread (no real Thread spawned)
        so assertions on notify_assignment_created don't race a background thread."""
        with app.app_context():
            with patch("app.routes.admin.assignment_management.current_user", None), \
                 patch("app.routes.admin.assignment_management.threading.Thread") as mock_thread_cls, \
                 patch(
                     "app.routes.admin.assignment_management._dispatch_assignment_created_notifications"
                 ) as mock_dispatch:
                _start_assignment_notification_dispatch([101], False)

        mock_thread_cls.assert_not_called()
        mock_dispatch.assert_called_once()
        args = mock_dispatch.call_args[0]
        assert args[1:] == ([101], False, None)

    def test_empty_aes_ids_is_noop(self, app):
        with app.app_context():
            with patch("app.routes.admin.assignment_management.threading.Thread") as mock_thread_cls, \
                 patch(
                     "app.routes.admin.assignment_management._dispatch_assignment_created_notifications"
                 ) as mock_dispatch:
                _start_assignment_notification_dispatch([], False)

        mock_thread_cls.assert_not_called()
        mock_dispatch.assert_not_called()

    def test_dispatch_skips_missing_aes_and_isolates_per_entity_errors(self, db_session, app):
        """Mirrors the original synchronous loop's error handling: one entity's
        notify failure must not stop the rest, and a stale/missing id (e.g. the
        row was deleted between commit and dispatch) is skipped, not fatal."""
        with app.app_context():
            country1 = create_test_country(db_session)
            country2 = create_test_country(db_session)
            aes1 = create_test_assignment_entity_status(db_session, country=country1)
            aes2 = create_test_assignment_entity_status(db_session, country=country2)
            aes1_id, aes2_id = aes1.id, aes2.id
            missing_id = max(aes1_id, aes2_id) + 999999

        with patch(
            "app.services.notification.core.notify_assignment_created",
            side_effect=[["n1"], RuntimeError("boom")],
        ) as mock_notify, patch(
            "app.routes.admin.assignment_management.safe_remove"
        ) as mock_safe_remove:
            _dispatch_assignment_created_notifications(
                app, [aes1_id, missing_id, aes2_id], True, 777
            )

        assert mock_notify.call_count == 2
        first_kwargs = mock_notify.call_args_list[0].kwargs
        assert first_kwargs == {"notify_admins": True, "actor_user_id": 777}
        mock_safe_remove.assert_called_once()


# ---------------------------------------------------------------------------
# add_entity_to_assignment — direct mock tests (no DB)
# ---------------------------------------------------------------------------

class TestAddEntityToAssignmentDirect:
    """Mock-based tests for entity add edge cases without DB fixtures."""

    def test_add_entity_non_json_body_returns_400(self, app):
        from contextlib import ExitStack
        from app.routes.admin.assignment_management import add_entity_to_assignment

        mock_assignment = MagicMock()
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        with app.test_request_context(
            "/admin/assignments/1/entities/add",
            method="POST",
            data="not json",
            content_type="text/plain",
        ), ExitStack() as stack:
            stack.enter_context(patch("app.routes.admin.shared.user_has_permission", return_value=True))
            stack.enter_context(patch("app.routes.admin.shared.current_user", mock_user))
            mock_af = stack.enter_context(patch("app.routes.admin.assignment_management.AssignedForm"))
            mock_af.query.get_or_404.return_value = mock_assignment
            resp = add_entity_to_assignment(1)
        assert resp.status_code == 400
        data = json.loads(resp.get_data(as_text=True))
        assert "entity_type" in data.get("error", "").lower() or data.get("success") is False

    def test_add_entity_integrity_error_returns_409(self, app):
        from contextlib import ExitStack
        from sqlalchemy.exc import IntegrityError
        from app.routes.admin.assignment_management import add_entity_to_assignment

        mock_assignment = MagicMock()
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        with app.test_request_context(
            "/admin/assignments/1/entities/add",
            method="POST",
            json={"entity_type": "country", "entity_id": 99},
        ), ExitStack() as stack:
            stack.enter_context(patch("app.routes.admin.shared.user_has_permission", return_value=True))
            stack.enter_context(patch("app.routes.admin.shared.current_user", mock_user))
            mock_af = stack.enter_context(patch("app.routes.admin.assignment_management.AssignedForm"))
            stack.enter_context(patch("app.services.organization.entity_service.EntityService.get_entity", return_value=MagicMock()))
            stack.enter_context(patch("app.routes.admin.assignment_management.request_transaction_rollback"))
            stack.enter_context(patch("app.routes.admin.assignment_management.db.session.add"))
            stack.enter_context(patch("app.routes.admin.assignment_management.db.session.flush", side_effect=IntegrityError("", "", "")))
            mock_query = stack.enter_context(patch("app.routes.admin.assignment_management.AssignmentEntityStatus.query"))
            mock_af.query.get_or_404.return_value = mock_assignment
            mock_query.filter_by.return_value.first.return_value = None
            resp = add_entity_to_assignment(1)
        assert resp.status_code == 409
        data = json.loads(resp.get_data(as_text=True))
        assert "already assigned" in data.get("error", "").lower()


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

    def test_update_cancelled(self, logged_in_client, db_session, app):
        from app.models.assignments import AssignmentEntityStatus
        from app.models.enums import AssignmentEntityStatusValue

        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.put(
            f"/admin/assignments/{assignment_id}/entities/{aes_id}",
            json={"status": "cancelled"},
        )
        assert resp.status_code in (200, 302)
        with app.app_context():
            refreshed = AssignmentEntityStatus.query.get(aes_id)
            assert refreshed.status == AssignmentEntityStatusValue.cancelled

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

    def test_update_non_json_body_does_not_crash(self, app):
        from contextlib import ExitStack
        from app.routes.admin.assignment_management import update_entity_status

        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 1
        mock_aes = MagicMock()
        with app.test_request_context(
            "/admin/assignments/1/entities/10",
            method="PUT",
            data="not json",
            content_type="text/plain",
        ), ExitStack() as stack:
            stack.enter_context(patch("app.routes.admin.shared.user_has_permission", return_value=True))
            stack.enter_context(patch("app.routes.admin.shared.current_user", mock_user))
            mock_aes_cls = stack.enter_context(patch("app.routes.admin.assignment_management.AssignmentEntityStatus"))
            stack.enter_context(patch("app.routes.admin.assignment_management.db.session.flush"))
            mock_aes_cls.query.filter_by.return_value.first_or_404.return_value = mock_aes
            resp = update_entity_status(1, 10)
        assert resp.status_code == 200


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

    def test_bulk_update_cancelled(self, logged_in_client, db_session, app):
        from app.models.assignments import AssignmentEntityStatus
        from app.models.enums import AssignmentEntityStatusValue

        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assignment_id = aes.assigned_form_id
            aes_id = aes.id
        resp = logged_in_client.post(
            f"/admin/assignments/{assignment_id}/entities/bulk-update-status",
            json={"status_ids": [aes_id], "status": "cancelled"},
        )
        assert resp.status_code in (200, 302)
        with app.app_context():
            refreshed = AssignmentEntityStatus.query.get(aes_id)
            assert refreshed.status == AssignmentEntityStatusValue.cancelled

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
            # Commit (not just flush): the route runs in its own request context/
            # transaction, so an uncommitted public URL wouldn't be visible to it.
            db_session.commit()
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
            # Commit (not just flush): the route runs in its own request context/
            # transaction, so an uncommitted public URL wouldn't be visible to it.
            db_session.commit()
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
            # Commit (not just flush): the route runs in its own request context/
            # transaction, so an uncommitted public URL wouldn't be visible to it.
            db_session.commit()
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
# Assignment notification preview
#
# These assert that the preview endpoint's recipient counts are produced by
# the *same* eligibility helpers used when the grouped email is actually sent
# (filter_instant_email_eligible_user_ids / collect_entity_admin_audience_recipient_ids),
# so the numbers shown before sending never diverge from what actually goes out.
# ---------------------------------------------------------------------------

class TestAssignmentNotificationPreview:
    def _preview(self, logged_in_client, country_ids, **extra_params):
        qs = [("country_ids[]", str(cid)) for cid in country_ids]
        for key, value in extra_params.items():
            qs.append((key, str(value)))
        return logged_in_client.get("/admin/assignments/notification-preview", query_string=qs)

    def test_no_countries_returns_zero_counts(self, logged_in_client, db_session):
        resp = self._preview(logged_in_client, [])
        _assert_ok(resp)
        data = _get_json(resp)
        assert data["entities_count"] == 0
        assert data["total_focal_users"] == 0
        assert data["email_batch_count"] == 0
        assert data["countries_without_focal_count"] == 0

    def test_country_without_focal_point_is_counted(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            country_id = country.id

        resp = self._preview(logged_in_client, [country_id])
        _assert_ok(resp)
        data = _get_json(resp)
        assert data["entities_count"] == 1
        assert data["total_focal_users"] == 0
        assert data["email_batch_count"] == 0
        # This is the count that used to be missing entirely: countries selected
        # for the assignment but with nobody to actually receive a focal email.
        assert data["countries_without_focal_count"] == 1

    def test_instant_focal_point_counted_as_email_recipient(self, logged_in_client, db_session, app):
        with app.app_context():
            _user, country, _aes = create_focal_point_with_country(db_session)
            country_id = country.id

        resp = self._preview(logged_in_client, [country_id])
        _assert_ok(resp)
        data = _get_json(resp)
        assert data["focal_points_enabled"] is True
        assert data["total_focal_users"] == 1
        assert data["email_users"] == 1
        assert data["email_batch_count"] == 1
        assert data["countries_without_focal_count"] == 0

    def test_digest_focal_point_excluded_from_email_counts_but_not_in_app(
        self, logged_in_client, db_session, app
    ):
        """
        A focal point on a daily/weekly digest still gets an in-app notification,
        but the grouped instant email is only ever sent to `instant`-frequency
        users (filter_instant_email_eligible_user_ids). The preview must mirror
        that instead of counting every focal point as an email recipient.
        """
        from app.models import NotificationPreferences

        with app.app_context():
            user, country, _aes = create_focal_point_with_country(db_session)
            db_session.add(NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=[],
                in_app_notification_types_enabled=[],
                notification_frequency='daily',
            ))
            db_session.commit()
            country_id = country.id

        resp = self._preview(logged_in_client, [country_id])
        _assert_ok(resp)
        data = _get_json(resp)
        assert data["total_focal_users"] == 1
        assert data["email_users"] == 0
        assert data["email_batch_count"] == 0
        # The country does have a focal point — it's just not email-eligible.
        assert data["countries_without_focal_count"] == 0

    def test_email_disabled_focal_point_excluded_from_email_counts(
        self, logged_in_client, db_session, app
    ):
        from app.models import NotificationPreferences

        with app.app_context():
            user, country, _aes = create_focal_point_with_country(db_session)
            db_session.add(NotificationPreferences(
                user_id=user.id,
                email_notifications=False,
                notification_types_enabled=[],
                in_app_notification_types_enabled=[],
                notification_frequency='instant',
            ))
            db_session.commit()
            country_id = country.id

        resp = self._preview(logged_in_client, [country_id])
        _assert_ok(resp)
        data = _get_json(resp)
        assert data["total_focal_users"] == 1
        assert data["email_users"] == 0
        assert data["email_batch_count"] == 0

    def test_admin_only_country_promoted_into_email_batch_with_notify_admins(
        self, logged_in_client, db_session, app
    ):
        """
        A country with an entity-scoped org admin but no focal point should
        count toward email_batch_count once 'notify admins' is requested and
        the admin_users audience bucket is enabled — matching the to/cc swap
        onto admins in notify_assignment_created / send_grouped_entity_email.
        """
        from app.models.enums import EntityType
        from app.services.platform.app_settings_service import set_notification_audience_rules

        with app.app_context():
            set_notification_audience_rules({
                "assignment_created": {"focal_points": True, "admin_users": True, "system_managers": False},
            })
            country = create_test_country(db_session)
            admin = create_test_admin(db_session)
            _grant_entity_permission(db_session, admin, EntityType.country.value, country.id)
            db_session.commit()
            country_id = country.id

        resp = self._preview(logged_in_client, [country_id], notify_admins=1)
        _assert_ok(resp)
        data = _get_json(resp)
        assert data["admins_enabled"] is True
        assert data["admin_users"] == 1
        assert data["countries_without_focal_count"] == 1
        assert data["email_batch_count"] == 1

    def test_admin_only_country_not_batched_without_notify_admins(
        self, logged_in_client, db_session, app
    ):
        from app.models.enums import EntityType
        from app.services.platform.app_settings_service import set_notification_audience_rules

        with app.app_context():
            set_notification_audience_rules({
                "assignment_created": {"focal_points": True, "admin_users": True, "system_managers": False},
            })
            country = create_test_country(db_session)
            admin = create_test_admin(db_session)
            _grant_entity_permission(db_session, admin, EntityType.country.value, country.id)
            db_session.commit()
            country_id = country.id

        resp = self._preview(logged_in_client, [country_id])
        _assert_ok(resp)
        data = _get_json(resp)
        assert data["admin_users"] == 1
        # notify_admins was not requested, so the admin-only country is not
        # promoted into the grouped-email batch.
        assert data["email_batch_count"] == 0

    def test_focal_points_bucket_disabled_still_reports_admin_recipients(
        self, logged_in_client, db_session, app
    ):
        """
        When the focal_points audience bucket is disabled, the preview must
        still surface admin recipients (and any resulting email) instead of
        hard-coding zero — mirrors notify_assignment_created, which stops
        emailing focal_user_ids when this bucket is off but still emails/CCs
        admin-only recipients.
        """
        from app.models.enums import EntityType
        from app.services.platform.app_settings_service import set_notification_audience_rules

        with app.app_context():
            set_notification_audience_rules({
                "assignment_created": {"focal_points": False, "admin_users": True, "system_managers": False},
            })
            _user, country, _aes = create_focal_point_with_country(db_session)
            admin = create_test_admin(db_session)
            _grant_entity_permission(db_session, admin, EntityType.country.value, country.id)
            db_session.commit()
            country_id = country.id

        resp = self._preview(logged_in_client, [country_id], notify_admins=1)
        _assert_ok(resp)
        data = _get_json(resp)
        assert data["focal_points_enabled"] is False
        assert data["total_focal_users"] == 0
        assert data["email_users"] == 0
        assert data["admins_enabled"] is True
        assert data["admin_users"] == 1
        assert data["email_batch_count"] == 1


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
