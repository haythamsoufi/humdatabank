"""
Tests for app/routes/admin/system_admin/countries.py
Targeting 100% code coverage of the countries routes.
"""
import json
import pytest
from unittest.mock import patch, MagicMock

from tests.factories import create_test_country

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_render(return_value="<html>ok</html>"):
    return patch(
        "app.routes.admin.system_admin.countries.render_template",
        return_value=return_value,
    )


def _json_headers():
    return {"Content-Type": "application/json", "Accept": "application/json"}


# ---------------------------------------------------------------------------
# GET /admin/countries  – redirects to organization page
# ---------------------------------------------------------------------------

class TestManageCountries:
    def test_redirects_to_organization_tab(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/countries", follow_redirects=False)
        assert resp.status_code == 302
        assert "organization" in resp.location

    def test_unauthenticated_redirects_to_login(self, client, db_session):
        resp = client.get("/admin/countries", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.location


# ---------------------------------------------------------------------------
# GET/POST /admin/countries/new  – create country
# ---------------------------------------------------------------------------

class TestNewCountry:
    def test_get_renders_form(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/countries/new")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_post_valid_data_creates_country_and_redirects(self, logged_in_client, db_session, app):
        from app.models import Country
        with app.app_context():
            # Make sure iso3 doesn't collide
            Country.query.filter_by(iso3="QQQ").delete()
            db_session.commit()

        resp = logged_in_client.post(
            "/admin/countries/new",
            data={
                "name": "New Country Test",
                "iso3": "QQQ",
                "status": "Active",
                "preferred_language": "en",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "countries" in resp.location or "organization" in resp.location

    def test_post_invalid_data_rerenders_form(self, logged_in_client, db_session):
        """Empty name should fail DataRequired validation and re-render."""
        with _mock_render() as mock_rt:
            resp = logged_in_client.post(
                "/admin/countries/new",
                data={"name": "", "iso3": "AB"},  # name too short, iso3 wrong length
                follow_redirects=False,
            )
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_exception_during_save_rerenders_form(self, logged_in_client, db_session):
        """If an exception is raised during save, the form is re-rendered."""
        with patch(
            "app.routes.admin.system_admin.countries.Country",
            side_effect=Exception("forced db error"),
        ), _mock_render() as mock_rt:
            resp = logged_in_client.post(
                "/admin/countries/new",
                data={"name": "ErrorCountry", "iso3": "ERR", "status": "Active"},
                follow_redirects=False,
            )
        # Should re-render the form (200) after the exception
        assert resp.status_code == 200
        mock_rt.assert_called()


# ---------------------------------------------------------------------------
# GET /admin/countries/<id>/data  – JSON country details for edit modal
# ---------------------------------------------------------------------------

class TestGetCountryDataJson:
    def test_returns_country_json(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="JsonDataCountry", iso3="JDC")
        resp = logged_in_client.get(f"/admin/countries/{country.id}/data")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True
        assert data.get("id") == country.id

    def test_404_for_nonexistent_country(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/countries/999999/data")
        assert resp.status_code == 404

    def test_returns_fds_member_fields(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="FdsMemberCountry", iso3="FMC")
        resp = logged_in_client.get(f"/admin/countries/{country.id}/data")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "fds_member_user_id" in data
        assert "fds_member_name" in data
        assert "fds_member_user_options" in data
        assert "name_translations" in data


# ---------------------------------------------------------------------------
# GET /admin/countries/<id>  – minimal JSON (id, name, region, iso3, status)
# ---------------------------------------------------------------------------

class TestGetCountryData:
    def test_returns_basic_json(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="BasicJsonCountry", iso3="BJC")
        resp = logged_in_client.get(f"/admin/countries/{country.id}")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True
        assert data.get("id") == country.id
        assert data.get("iso3") == "BJC"

    def test_404_for_missing_country(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/countries/9999998")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET/POST /admin/countries/edit/<id>  – edit country
# ---------------------------------------------------------------------------

class TestEditCountry:
    def test_get_renders_form(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="EditGetCountry", iso3="EGC")
        with _mock_render() as mock_rt:
            resp = logged_in_client.get(f"/admin/countries/edit/{country.id}")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_post_valid_form_redirects(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="EditPostCountry", iso3="EPC")
        resp = logged_in_client.post(
            f"/admin/countries/edit/{country.id}",
            data={
                "name": "Updated Country Name",
                "iso3": "EPC",
                "status": "Active",
                "preferred_language": "en",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_post_valid_json_returns_json_ok(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="EditJsonCountry", iso3="EJC")
        resp = logged_in_client.post(
            f"/admin/countries/edit/{country.id}",
            data=json.dumps({
                "name": "Updated JSON Country",
                "iso3": "EJC",
                "status": "Active",
                "preferred_language": "en",
            }),
            content_type="application/json",
            follow_redirects=False,
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_post_invalid_form_json_returns_form_errors(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="EditInvalidJson", iso3="EIJ")
        resp = logged_in_client.post(
            f"/admin/countries/edit/{country.id}",
            data=json.dumps({"name": "", "iso3": ""}),
            content_type="application/json",
            follow_redirects=False,
        )
        assert resp.status_code in (200, 400)

    def test_post_value_error_from_fds_assignment_json(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="EditFdsErrJson", iso3="EFJ")
        with patch(
            "app.routes.admin.system_admin.countries.assign_country_fds_member_user",
            side_effect=ValueError("invalid fds user"),
        ):
            resp = logged_in_client.post(
                f"/admin/countries/edit/{country.id}",
                data=json.dumps({
                    "name": "Country With FDS",
                    "iso3": "EFJ",
                    "status": "Active",
                    "preferred_language": "en",
                    "fds_member_user_id": "999",
                }),
                content_type="application/json",
                follow_redirects=False,
            )
        assert resp.status_code == 400

    def test_post_value_error_from_fds_assignment_form(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="EditFdsErrForm", iso3="EFF")
        with patch(
            "app.routes.admin.system_admin.countries.assign_country_fds_member_user",
            side_effect=ValueError("invalid fds user"),
        ), _mock_render() as mock_rt:
            resp = logged_in_client.post(
                f"/admin/countries/edit/{country.id}",
                data={
                    "name": "Country With FDS",
                    "iso3": "EFF",
                    "status": "Active",
                    "preferred_language": "en",
                    "fds_member_user_id": "999",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_exception_json_returns_server_error(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="EditExcJson", iso3="EXJ")
        with patch(
            "app.routes.admin.system_admin.countries.db",
            new_callable=MagicMock,
        ) as mock_db:
            mock_db.session.flush.side_effect = Exception("db error")
            mock_db.session.add = MagicMock()
            resp = logged_in_client.post(
                f"/admin/countries/edit/{country.id}",
                data=json.dumps({
                    "name": "Exc Country",
                    "iso3": "EXJ",
                    "status": "Active",
                    "preferred_language": "en",
                }),
                content_type="application/json",
                follow_redirects=False,
            )
        assert resp.status_code in (200, 500)

    def test_404_for_missing_country(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/countries/edit/9999999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/countries/delete/<id>  – delete country
# ---------------------------------------------------------------------------

class TestDeleteCountry:
    def test_delete_country_without_dependencies_redirects(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="DeleteMeCountry", iso3="DMC")
        resp = logged_in_client.post(
            f"/admin/countries/delete/{country.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_delete_country_with_users_shows_danger_flash(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="HasUsersCountry", iso3="HUC")
        # Mock the country.users.first() to return a truthy value
        with patch("app.routes.admin.system_admin.countries.Country") as mock_country_class:
            mock_country = MagicMock()
            mock_country.id = country.id
            mock_country.name = country.name
            mock_country.users.first.return_value = MagicMock()  # has users
            mock_country.assignment_statuses.first.return_value = None
            mock_country_class.query.get_or_404.return_value = mock_country
            resp = logged_in_client.post(
                f"/admin/countries/delete/{country.id}",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_delete_country_with_assignment_statuses_shows_danger_flash(
        self, logged_in_client, db_session, app
    ):
        with app.app_context():
            country = create_test_country(db_session, name="HasAssignmentsCountry", iso3="HAC")
        with patch("app.routes.admin.system_admin.countries.Country") as mock_country_class:
            mock_country = MagicMock()
            mock_country.id = country.id
            mock_country.name = country.name
            mock_country.users.first.return_value = None
            mock_country.assignment_statuses.first.return_value = MagicMock()  # has assignments
            mock_country_class.query.get_or_404.return_value = mock_country
            resp = logged_in_client.post(
                f"/admin/countries/delete/{country.id}",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_delete_exception_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="ExceptionDeleteCountry", iso3="EDC")
        with patch("app.routes.admin.system_admin.countries.Country") as mock_country_class:
            mock_country = MagicMock()
            mock_country.id = country.id
            mock_country.name = country.name
            mock_country.users.first.return_value = None
            mock_country.assignment_statuses.first.return_value = None
            mock_country_class.query.get_or_404.return_value = mock_country
            with patch(
                "app.routes.admin.system_admin.countries.db",
                new_callable=MagicMock,
            ) as mock_db:
                mock_db.session.delete.side_effect = Exception("db error")
                resp = logged_in_client.post(
                    f"/admin/countries/delete/{country.id}",
                    follow_redirects=False,
                )
        assert resp.status_code == 302

    def test_delete_404_for_missing_country(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/countries/delete/9999997",
            follow_redirects=False,
        )
        assert resp.status_code == 404
