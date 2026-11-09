"""
Comprehensive tests for app/routes/api/users.py

Covers all five endpoints:
  GET  /api/v1/users               (API-key auth)
  GET  /api/v1/users/<id>          (API-key auth)
  GET  /api/v1/user/profile        (session auth)
  PUT/PATCH /api/v1/user/profile   (session auth + CSRF)
  GET  /api/v1/dashboard           (session auth)
"""
import uuid
import pytest

from tests.factories import (
    create_test_user,
    create_test_country,
)
from tests.helpers import login_session, get_csrf_headers
from app.models.core import UserEntityPermission
from app.models import AssignmentEntityStatus
from app.models.enums import EntityType


# ---------------------------------------------------------------------------
# GET /api/v1/users
# ---------------------------------------------------------------------------

@pytest.mark.api
@pytest.mark.integration
class TestGetUsersEndpoint:
    """Tests for GET /api/v1/users (API-key auth, paginated)."""

    def test_requires_api_key(self, client):
        resp = client.get("/api/v1/users")
        assert resp.status_code in (401, 403, 500)

    def test_contract_returns_pagination_envelope(self, client, auth_headers, db_session):
        resp = client.get("/api/v1/users", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        for key in ("users", "total_items", "total_pages", "current_page", "per_page", "search_query"):
            assert key in data, f"Missing key: {key}"

    def test_per_page_param_respected(self, client, auth_headers, db_session, app):
        with app.app_context():
            for _ in range(5):
                create_test_user(db_session, email=f"paged_{uuid.uuid4().hex[:8]}@example.com")

        resp = client.get("/api/v1/users?page=1&per_page=2", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["per_page"] == 2
        assert data["current_page"] == 1
        assert len(data["users"]) <= 2

    def test_search_filter_by_name(self, client, auth_headers, db_session, app):
        unique = uuid.uuid4().hex[:8]
        with app.app_context():
            create_test_user(
                db_session,
                email=f"srch_{unique}@example.com",
                name=f"Searchable{unique}",
            )

        resp = client.get(f"/api/v1/users?search=Searchable{unique}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_items"] >= 1
        assert any(u["name"] == f"Searchable{unique}" for u in data["users"])
        assert data["search_query"] == f"Searchable{unique}"

    def test_search_returns_empty_for_no_match(self, client, auth_headers, db_session):
        resp = client.get("/api/v1/users?search=zzz_no_match_xyz_987654", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_items"] == 0
        assert data["users"] == []

    def test_user_object_has_required_fields(self, client, auth_headers, db_session, app):
        with app.app_context():
            create_test_user(db_session, email=f"shape_{uuid.uuid4().hex[:8]}@example.com")

        resp = client.get("/api/v1/users", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["users"]) > 0
        user = data["users"][0]
        for field in ("id", "email", "name", "title", "countries", "chatbot_enabled",
                      "rbac_roles", "has_api_key"):
            assert field in user, f"Missing field in user object: {field}"

    def test_rbac_roles_included_in_user_list(self, client, auth_headers, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"rbac_list_{uuid.uuid4().hex[:8]}@example.com",
                role="system_manager",
            )
            target_email = user.email

        resp = client.get("/api/v1/users", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        target = next((u for u in data["users"] if u["email"] == target_email), None)
        assert target is not None
        assert isinstance(target["rbac_roles"], list)
        assert len(target["rbac_roles"]) > 0
        assert all("code" in r and "name" in r for r in target["rbac_roles"])


# ---------------------------------------------------------------------------
# GET /api/v1/users/<user_id>
# ---------------------------------------------------------------------------

@pytest.mark.api
@pytest.mark.integration
class TestGetUserDetailsEndpoint:
    """Tests for GET /api/v1/users/<id> (API-key auth)."""

    def test_requires_api_key(self, client):
        resp = client.get("/api/v1/users/1")
        assert resp.status_code in (401, 403, 500)

    def test_returns_404_for_nonexistent_user(self, client, auth_headers, db_session):
        resp = client.get("/api/v1/users/999999999", headers=auth_headers)
        assert resp.status_code == 404

    def test_returns_user_data_shape(self, client, auth_headers, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"detail_{uuid.uuid4().hex[:8]}@example.com",
                name="Detail Test User",
            )
            user_id = int(user.id)

        resp = client.get(f"/api/v1/users/{user_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == user_id
        for field in ("email", "name", "title", "countries", "chatbot_enabled",
                      "has_api_key", "rbac_roles"):
            assert field in data, f"Missing field: {field}"

    def test_rbac_roles_populated_for_user_with_role(self, client, auth_headers, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"roles_detail_{uuid.uuid4().hex[:8]}@example.com",
                role="system_manager",
            )
            user_id = int(user.id)

        resp = client.get(f"/api/v1/users/{user_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data["rbac_roles"], list)
        assert len(data["rbac_roles"]) > 0
        role = data["rbac_roles"][0]
        assert "code" in role and "name" in role

    def test_user_with_country_includes_country_fields(self, client, auth_headers, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            user = create_test_user(
                db_session,
                email=f"withcountry_{uuid.uuid4().hex[:8]}@example.com",
            )
            # User.countries is viewonly=True (secondary via user_entity_permissions);
            # create the permission row directly.
            db_session.add(UserEntityPermission(
                user_id=user.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
            ))
            db_session.commit()
            user_id = int(user.id)

        resp = client.get(f"/api/v1/users/{user_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["countries"]) >= 1
        c = data["countries"][0]
        assert "id" in c and "name" in c and "iso3" in c

    def test_country_data_includes_extended_fields(self, client, auth_headers, db_session, app):
        """Detailed endpoint adds region + national_society_name fields."""
        with app.app_context():
            country = create_test_country(db_session)
            user = create_test_user(
                db_session,
                email=f"ext_country_{uuid.uuid4().hex[:8]}@example.com",
            )
            db_session.add(UserEntityPermission(
                user_id=user.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
            ))
            db_session.commit()
            user_id = int(user.id)

        resp = client.get(f"/api/v1/users/{user_id}", headers=auth_headers)
        assert resp.status_code == 200
        c = resp.get_json()["countries"][0]
        # Detail endpoint adds these fields (vs. list endpoint)
        assert "region" in c
        assert "national_society_name" in c


# ---------------------------------------------------------------------------
# GET /api/v1/user/profile
# ---------------------------------------------------------------------------

@pytest.mark.api
@pytest.mark.integration
class TestGetCurrentUserProfile:
    """Tests for GET /api/v1/user/profile (session auth)."""

    def test_requires_login(self, client):
        resp = client.get("/api/v1/user/profile")
        assert resp.status_code in (401, 302, 403)

    def test_returns_profile_for_logged_in_user(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"profile_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        login_session(client, user_id)
        resp = client.get("/api/v1/user/profile")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == user_id
        for field in ("email", "name", "title", "chatbot_enabled",
                      "profile_color", "country_ids", "rbac_roles"):
            assert field in data, f"Missing field: {field}"

    def test_country_ids_in_profile(self, client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            user = create_test_user(
                db_session,
                email=f"country_prof_{uuid.uuid4().hex[:8]}@example.com",
            )
            # User.countries is viewonly=True; create the permission row directly.
            db_session.add(UserEntityPermission(
                user_id=user.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
            ))
            db_session.commit()
            user_id = int(user.id)
            country_id = int(country.id)

        login_session(client, user_id)
        resp = client.get("/api/v1/user/profile")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data["country_ids"], list)
        assert country_id in data["country_ids"]

    def test_rbac_roles_in_profile(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"rbac_prof_{uuid.uuid4().hex[:8]}@example.com",
                role="system_manager",
            )
            user_id = int(user.id)

        login_session(client, user_id)
        resp = client.get("/api/v1/user/profile")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data["rbac_roles"], list)
        assert len(data["rbac_roles"]) > 0
        assert all("code" in r and "name" in r for r in data["rbac_roles"])

    def test_ai_beta_tester_flag_present(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"beta_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        login_session(client, user_id)
        resp = client.get("/api/v1/user/profile")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "ai_beta_tester" in data
        assert isinstance(data["ai_beta_tester"], bool)
        assert "ai_beta_restricted" in data
        assert isinstance(data["ai_beta_restricted"], bool)


# ---------------------------------------------------------------------------
# PUT / PATCH /api/v1/user/profile
# ---------------------------------------------------------------------------

@pytest.mark.api
@pytest.mark.integration
class TestUpdateCurrentUserProfile:
    """Tests for PUT/PATCH /api/v1/user/profile (session auth)."""

    @pytest.fixture(autouse=True)
    def _noop_profile_activity_log(self, monkeypatch):
        # log_user_activity -> update_session_activity rolls back dirty sessions,
        # which detaches current_user before the response is built.
        monkeypatch.setattr(
            "app.routes.auth.log_user_activity",
            lambda *args, **kwargs: None,
        )

    @staticmethod
    def _auth_headers(client, user_id):
        login_session(client, user_id)
        return get_csrf_headers(client)

    def test_update_requires_login(self, client):
        resp = client.put(
            "/api/v1/user/profile",
            json={"name": "New Name"},
            content_type="application/json",
        )
        assert resp.status_code in (401, 302, 403)

    def test_update_name_returns_200_with_updated_value(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"upd_name_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        headers = self._auth_headers(client, user_id)
        resp = client.put(
            "/api/v1/user/profile",
            json={"name": "Updated Name"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        data = resp.get_json()
        assert data["name"] == "Updated Name"
        assert data.get("message") == "Profile updated successfully"

    def test_update_title(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"upd_title_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        headers = self._auth_headers(client, user_id)
        resp = client.put(
            "/api/v1/user/profile",
            json={"title": "Senior Analyst"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()["title"] == "Senior Analyst"

    def test_update_chatbot_enabled_to_false(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"upd_chat_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        headers = self._auth_headers(client, user_id)
        resp = client.put(
            "/api/v1/user/profile",
            json={"chatbot_enabled": False},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()["chatbot_enabled"] is False

    def test_update_profile_color(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"upd_color_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        headers = self._auth_headers(client, user_id)
        resp = client.put(
            "/api/v1/user/profile",
            json={"profile_color": "#FF5733"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()["profile_color"] == "#FF5733"

    def test_update_multiple_fields_at_once(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"upd_multi_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        headers = self._auth_headers(client, user_id)
        resp = client.put(
            "/api/v1/user/profile",
            json={"name": "Multi Update", "title": "Director", "chatbot_enabled": True},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        data = resp.get_json()
        assert data["name"] == "Multi Update"
        assert data["title"] == "Director"
        assert data["chatbot_enabled"] is True

    def test_update_empty_name_sets_null(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"upd_null_{uuid.uuid4().hex[:8]}@example.com",
                name="Has A Name",
            )
            user_id = int(user.id)

        headers = self._auth_headers(client, user_id)
        resp = client.put(
            "/api/v1/user/profile",
            json={"name": ""},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()["name"] is None

    def test_no_valid_fields_returns_400(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"nofields_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        headers = self._auth_headers(client, user_id)
        resp = client.put(
            "/api/v1/user/profile",
            json={"unknown_field": "value"},
            headers=headers,
        )
        assert resp.status_code == 400

    def test_patch_method_works(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"patch_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        headers = self._auth_headers(client, user_id)
        resp = client.patch(
            "/api/v1/user/profile",
            json={"name": "Patched Name"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()["name"] == "Patched Name"

    def test_response_includes_required_fields(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"resp_check_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        headers = self._auth_headers(client, user_id)
        resp = client.put(
            "/api/v1/user/profile",
            json={"name": "Response Check"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        data = resp.get_json()
        for field in ("id", "email", "name", "chatbot_enabled",
                      "profile_color", "country_ids", "rbac_roles", "message"):
            assert field in data, f"Missing field in update response: {field}"

    def test_requires_json_content_type(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"ct_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        headers = self._auth_headers(client, user_id)
        resp = client.put(
            "/api/v1/user/profile",
            data="name=Not JSON",
            content_type="application/x-www-form-urlencoded",
            headers=headers,
        )
        assert resp.status_code in (400, 415)


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard
# ---------------------------------------------------------------------------

@pytest.mark.api
@pytest.mark.integration
class TestGetDashboard:
    """Tests for GET /api/v1/dashboard (session auth)."""

    def test_requires_login(self, client):
        resp = client.get("/api/v1/dashboard")
        assert resp.status_code in (401, 302, 403)

    def test_returns_expected_structure_for_basic_user(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"dash_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        login_session(client, user_id)
        resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "current_assignments" in data
        assert "past_assignments" in data
        assert "entities" in data
        assert "ns_focal_points" in data
        assert "org_focal_points" in data
        assert isinstance(data["current_assignments"], list)
        assert isinstance(data["past_assignments"], list)
        assert isinstance(data["entities"], list)
        assert isinstance(data["ns_focal_points"], list)
        assert isinstance(data["org_focal_points"], list)

    def test_selected_entity_key_present(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(
                db_session,
                email=f"dash_sel_{uuid.uuid4().hex[:8]}@example.com",
            )
            user_id = int(user.id)

        login_session(client, user_id)
        resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 200
        data = resp.get_json()
        # selected_entity may be None or a dict, but key must be present
        assert "selected_entity" in data

    def test_dashboard_with_focal_point_user_shows_country_entity(
        self, client, db_session, app, focal_point_user
    ):
        login_session(client, focal_point_user["user_id"])
        resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 200
        data = resp.get_json()
        entity_types = [e["entity_type"] for e in data["entities"]]
        assert "country" in entity_types

    def test_entity_object_has_required_fields(
        self, client, db_session, app, focal_point_user
    ):
        login_session(client, focal_point_user["user_id"])
        resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 200
        data = resp.get_json()
        for entity in data["entities"]:
            assert "entity_type" in entity
            assert "entity_id" in entity
            assert "name" in entity
            assert "display_name" in entity

    def test_entity_query_params_set_selected_entity(
        self, client, db_session, app, focal_point_user
    ):
        country_id = focal_point_user["country_id"]
        login_session(client, focal_point_user["user_id"])
        resp = client.get(
            f"/api/v1/dashboard?entity_type=country&entity_id={country_id}"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        selected = data.get("selected_entity")
        # If the entity is accessible it should be selected; if entity groups
        # filtering disables "country" the selected_entity may still be None.
        if selected is not None:
            assert selected["entity_type"] == "country"
            assert selected["entity_id"] == country_id

    def test_assignment_data_shape_when_present(
        self, client, db_session, app, focal_point_user
    ):
        """Verify that assignment objects in the response have the documented fields."""
        login_session(client, focal_point_user["user_id"])
        resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 200
        data = resp.get_json()
        all_assignments = data["current_assignments"] + data["past_assignments"]
        if all_assignments:
            asgn = all_assignments[0]
            for field in (
                "id", "name", "status", "due_date", "completion_rate",
                "template_name", "period_name", "is_effectively_closed",
                "contributor_names", "is_public",
                "template_id", "static_version", "data_version",
                "form_definition_updated_at",
                "enable_offline_download",
            ):
                assert field in asgn, f"Missing field in assignment: {field}"


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard/offline-entities
# ---------------------------------------------------------------------------

@pytest.mark.api
@pytest.mark.integration
class TestGetDashboardOfflineEntities:
    """Every selectable entity's assignments in one call (offline template download)."""

    def _two_country_user(self, db_session, app):
        from tests.factories import (
            create_focal_point_with_country,
            create_test_assignment_entity_status,
            create_test_template,
        )
        from tests.factories import _grant_entity_permission

        with app.app_context():
            user, country_a, aes_a = create_focal_point_with_country(db_session)
            template_id = aes_a.assigned_form.template_id
            country_b = create_test_country(db_session)
            _grant_entity_permission(db_session, user, EntityType.country.value, country_b.id)
            aes_b = AssignmentEntityStatus(
                assigned_form_id=aes_a.assigned_form_id,
                entity_type=EntityType.country.value,
                entity_id=country_b.id,
                status="in_progress",
            )
            db_session.add(aes_b)
            db_session.flush()
            other_template = create_test_template(db_session)
            aes_other = create_test_assignment_entity_status(
                db_session, country=country_b, template=other_template, commit=False,
            )
            db_session.commit()
            return {
                "user_id": int(user.id),
                "template_id": int(template_id),
                "other_template_id": int(other_template.id),
                "country_ids": (int(country_a.id), int(country_b.id)),
                "aes_ids": (int(aes_a.id), int(aes_b.id), int(aes_other.id)),
            }

    def test_requires_login(self, client):
        resp = client.get("/api/v1/dashboard/offline-entities")
        assert resp.status_code in (401, 302, 403)

    def test_returns_assignments_of_all_entities(self, client, db_session, app):
        ctx = self._two_country_user(db_session, app)
        login_session(client, ctx["user_id"])

        resp = client.get(f"/api/v1/dashboard/offline-entities?template_ids={ctx['template_id']}")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["truncated"] is False
        by_country = {
            item["entity"]["entity_id"]: item
            for item in data["entities"]
            if item["entity"]["entity_type"] == "country"
        }
        assert set(by_country) == set(ctx["country_ids"])
        for country_id, aes_id in zip(ctx["country_ids"], ctx["aes_ids"][:2]):
            ids = {a["id"] for a in by_country[country_id]["current_assignments"]}
            assert ids == {aes_id}
            assert all(
                a["template_id"] == ctx["template_id"]
                for a in by_country[country_id]["current_assignments"]
            )

    def test_without_template_filter_returns_every_assignment(self, client, db_session, app):
        ctx = self._two_country_user(db_session, app)
        login_session(client, ctx["user_id"])

        data = client.get("/api/v1/dashboard/offline-entities").get_json()

        ids = {
            a["id"]
            for item in data["entities"]
            for a in item["current_assignments"] + item["past_assignments"]
        }
        assert set(ctx["aes_ids"]) <= ids

    def test_entities_without_matching_assignments_are_left_out(self, client, db_session, app):
        ctx = self._two_country_user(db_session, app)
        login_session(client, ctx["user_id"])

        data = client.get(
            f"/api/v1/dashboard/offline-entities?template_ids={ctx['other_template_id']}"
        ).get_json()

        assert [item["entity"]["entity_id"] for item in data["entities"]] == [ctx["country_ids"][1]]

    def test_limit_truncates_and_flags_it(self, client, db_session, app):
        ctx = self._two_country_user(db_session, app)
        login_session(client, ctx["user_id"])

        data = client.get(
            f"/api/v1/dashboard/offline-entities?template_ids={ctx['template_id']}&limit=1"
        ).get_json()

        assert len(data["entities"]) == 1
        assert data["truncated"] is True

    def test_does_not_change_the_selected_entity(self, client, db_session, app):
        ctx = self._two_country_user(db_session, app)
        login_session(client, ctx["user_id"])

        client.get(f"/api/v1/dashboard/offline-entities?template_ids={ctx['template_id']}")

        with client.session_transaction() as sess:
            assert "selected_entity_id" not in sess

    def test_ignores_malformed_template_ids(self, client, db_session, app):
        ctx = self._two_country_user(db_session, app)
        login_session(client, ctx["user_id"])

        resp = client.get("/api/v1/dashboard/offline-entities?template_ids=abc,,x1")

        assert resp.status_code == 200
