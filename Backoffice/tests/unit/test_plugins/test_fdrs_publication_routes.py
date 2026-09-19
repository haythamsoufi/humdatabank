"""HTTP route tests for the FDRS "Manage Publication" admin tool
(plugins/fdrs/publication_routes.py).

Uses real RBAC (no AuthorizationService mocking): `logged_in_sm_client` is a
system-manager user, which `AuthorizationService` treats as a superuser for
every check this module relies on (`is_admin`, `is_system_manager`,
`has_rbac_permission`, `check_template_access`) — see
app/services/organization/authorization_service.py. `logged_in_admin_client`
is a real admin *without* the system-manager role and without ownership of the
test template, so it naturally exercises the permission-denied paths too.
"""
from __future__ import annotations

import pytest

from app.models import FormData
from tests.factories import (
    create_test_admin,
    create_test_assignment_entity_status,
    create_test_country,
    create_test_item,
    create_test_section,
    create_test_template,
)
from tests.helpers import assert_api_response

pytestmark = [pytest.mark.unit]


def _patch_fdrs_template_id(monkeypatch, template_id: int) -> None:
    import plugins.fdrs.public_api_routes as public_api_routes
    import plugins.fdrs.publication_routes as publication_routes
    import plugins.fdrs.services.fdrs_publication_service as svc

    monkeypatch.setattr(svc, "FDRS_TEMPLATE_ID", template_id)
    monkeypatch.setattr(publication_routes, "FDRS_TEMPLATE_ID", template_id)
    monkeypatch.setattr(public_api_routes, "FDRS_TEMPLATE_ID", template_id)


@pytest.fixture
def fdrs_route_scenario(db_session, monkeypatch):
    """One FDRS assignment, one public item with a pending ('new') change."""
    template = create_test_template(db_session, name="FDRS Route Test Template")
    _patch_fdrs_template_id(monkeypatch, template.id)

    section = create_test_section(db_session, template)
    item = create_test_item(db_session, section, template, label="Public Route Item")
    from sqlalchemy.orm.attributes import flag_modified
    item.set_privacy("public")
    flag_modified(item, "config")
    db_session.commit()

    country = create_test_country(db_session, name="Routeland")
    aes = create_test_assignment_entity_status(
        db_session, country=country, template=template, period_name="2024",
    )

    row = FormData(assignment_entity_status_id=aes.id, form_item_id=item.id, value="42")
    db_session.add(row)
    db_session.commit()

    return {"template": template, "assigned_form_id": aes.assigned_form_id, "aes": aes, "item": item}


@pytest.mark.usefixtures("app")
class TestRoutesRegistered:
    def test_publication_page_registered(self, app):
        endpoint, values = app.url_map.bind("localhost").match("/admin/plugins/fdrs/publication")
        assert endpoint == "fdrs.publication_page"
        assert values == {}

    def test_publication_summary_registered(self, app):
        endpoint, values = app.url_map.bind("localhost").match("/admin/plugins/fdrs/publication/5/summary")
        assert endpoint == "fdrs.publication_summary"
        assert values == {"assigned_form_id": 5}

    def test_publication_country_detail_registered(self, app):
        endpoint, values = app.url_map.bind("localhost").match(
            "/admin/plugins/fdrs/publication/5/countries/9/detail"
        )
        assert endpoint == "fdrs.publication_country_detail"
        assert values == {"assigned_form_id": 5, "assignment_entity_status_id": 9}

    def test_publication_publish_registered(self, app):
        endpoint, values = app.url_map.bind("localhost").match(
            "/admin/plugins/fdrs/publication/5/publish", method="POST"
        )
        assert endpoint == "fdrs.publication_publish"
        assert values == {"assigned_form_id": 5}


class TestPublicationPage:
    def test_requires_login(self, client):
        response = client.get("/admin/plugins/fdrs/publication")
        assert response.status_code in (302, 401)

    def test_renders_for_system_manager(self, logged_in_sm_client, db_session, fdrs_route_scenario):
        response = logged_in_sm_client.get("/admin/plugins/fdrs/publication")
        assert response.status_code == 200
        assert b"Manage Publication" in response.data

    def test_denied_for_admin_without_system_manager_role(self, logged_in_admin_client, db_session, fdrs_route_scenario):
        response = logged_in_admin_client.get("/admin/plugins/fdrs/publication", follow_redirects=False)
        assert response.status_code in (302, 403)


class TestPublicationSummary:
    def _url(self, assigned_form_id):
        return f"/admin/plugins/fdrs/publication/{assigned_form_id}/summary"

    def test_success_for_system_manager(self, logged_in_sm_client, db_session, fdrs_route_scenario):
        response = logged_in_sm_client.get(self._url(fdrs_route_scenario["assigned_form_id"]))
        assert_api_response(response, 200, expected_keys=["success", "countries", "totals", "countries_total"])
        data = response.get_json()
        assert data["countries_total"] == 1
        assert data["totals"]["new"] == 1

    def test_404_for_non_fdrs_assignment(self, logged_in_sm_client, db_session, fdrs_route_scenario):
        other_template = create_test_template(db_session, name="Not FDRS Route Template")
        other_aes = create_test_assignment_entity_status(
            db_session, template=other_template, period_name="2024-other",
        )
        response = logged_in_sm_client.get(self._url(other_aes.assigned_form_id))
        assert response.status_code == 404

    def test_denied_for_admin_without_template_access(self, logged_in_admin_client, db_session, fdrs_route_scenario):
        # logged_in_admin_client has admin.templates.view but does not own/share this template,
        # so the manual check_template_access() guard in the route should still deny it.
        response = logged_in_admin_client.get(
            self._url(fdrs_route_scenario["assigned_form_id"]),
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 403

    def test_requires_login(self, client, db_session, fdrs_route_scenario):
        response = client.get(
            self._url(fdrs_route_scenario["assigned_form_id"]), headers={"Accept": "application/json"}
        )
        assert response.status_code in (302, 401)


class TestPublicationCountryDetail:
    def _url(self, assigned_form_id, aes_id):
        return f"/admin/plugins/fdrs/publication/{assigned_form_id}/countries/{aes_id}/detail"

    def test_success_for_system_manager(self, logged_in_sm_client, db_session, fdrs_route_scenario):
        response = logged_in_sm_client.get(
            self._url(fdrs_route_scenario["assigned_form_id"], fdrs_route_scenario["aes"].id)
        )
        assert_api_response(response, 200, expected_keys=["success", "items", "country_name"])
        data = response.get_json()
        assert data["country_name"] == "Routeland"
        assert data["items"][0]["kind"] == "new"

    def test_404_for_mismatched_aes(self, logged_in_sm_client, db_session, fdrs_route_scenario):
        other_country = create_test_country(db_session, name="Otherland")
        other_aes = create_test_assignment_entity_status(
            db_session,
            country=other_country,
            template=fdrs_route_scenario["template"],
            period_name="2025",
        )
        response = logged_in_sm_client.get(
            self._url(fdrs_route_scenario["assigned_form_id"], other_aes.id)
        )
        assert response.status_code == 404


class TestPublicationPublish:
    def _url(self, assigned_form_id):
        return f"/admin/plugins/fdrs/publication/{assigned_form_id}/publish"

    def test_publish_all_countries(self, logged_in_sm_client, db_session, fdrs_route_scenario):
        response = logged_in_sm_client.post(self._url(fdrs_route_scenario["assigned_form_id"]), json={})
        assert_api_response(response, 200, expected_keys=["success", "published_countries", "totals"])
        data = response.get_json()
        assert data["published_countries"] == 1
        assert data["totals"]["new"] == 1

        row = FormData.query.filter_by(
            assignment_entity_status_id=fdrs_route_scenario["aes"].id,
            form_item_id=fdrs_route_scenario["item"].id,
        ).one()
        assert row.published_value == "42"

    def test_publish_scoped_to_selected_countries(self, logged_in_sm_client, db_session, fdrs_route_scenario):
        response = logged_in_sm_client.post(
            self._url(fdrs_route_scenario["assigned_form_id"]),
            json={"assignment_entity_status_ids": [fdrs_route_scenario["aes"].id]},
        )
        assert response.status_code == 200
        assert response.get_json()["published_countries"] == 1

    def test_invalid_payload_returns_400(self, logged_in_sm_client, db_session, fdrs_route_scenario):
        response = logged_in_sm_client.post(
            self._url(fdrs_route_scenario["assigned_form_id"]),
            json={"assignment_entity_status_ids": "not-a-list"},
        )
        assert response.status_code == 400

    def test_denied_for_admin_without_system_manager_role(self, logged_in_admin_client, db_session, fdrs_route_scenario):
        response = logged_in_admin_client.post(self._url(fdrs_route_scenario["assigned_form_id"]), json={})
        assert response.status_code == 403

    def test_requires_login(self, client, db_session, fdrs_route_scenario):
        response = client.post(self._url(fdrs_route_scenario["assigned_form_id"]), json={})
        assert response.status_code in (302, 401)
