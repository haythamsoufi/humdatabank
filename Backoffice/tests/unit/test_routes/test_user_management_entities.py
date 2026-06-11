"""Tests for admin user management entity permission routes.

Covers: app/routes/admin/user_management/entities.py
"""

import pytest
from unittest.mock import patch, MagicMock
from tests.factories import create_test_user, create_test_country

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _grant_perm(db_session, perm_code, role_code="admin_core"):
    from app.models.rbac import RbacRole, RbacRolePermission, RbacPermission
    role = db_session.query(RbacRole).filter_by(code=role_code).first()
    if not role:
        return
    perm = db_session.query(RbacPermission).filter_by(code=perm_code).first()
    if not perm:
        perm = RbacPermission(code=perm_code, name=perm_code, description=perm_code)
        db_session.add(perm)
        db_session.flush()
    existing = db_session.query(RbacRolePermission).filter_by(
        role_id=role.id, permission_id=perm.id
    ).first()
    if not existing:
        db_session.add(RbacRolePermission(role_id=role.id, permission_id=perm.id))
        db_session.commit()


def _ensure_grants_perm(db_session):
    _grant_perm(db_session, "admin.users.grants.manage")


def _make_entity_permission(db_session, user, entity_type, entity_id):
    from app.models.core import UserEntityPermission
    perm = UserEntityPermission(
        user_id=user.id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db_session.add(perm)
    db_session.commit()
    db_session.refresh(perm)
    return perm


# ---------------------------------------------------------------------------
# get_user_entities (GET /admin/users/<id>/entities)
# ---------------------------------------------------------------------------

class TestGetUserEntities:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/users/1/entities")
        assert resp.status_code in (302, 401)

    def test_missing_permission_forbidden(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="ent_no_perm@example.com")
        resp = logged_in_client.get(f"/admin/users/{user.id}/entities")
        assert resp.status_code in (302, 403)

    def test_returns_empty_list_for_new_user(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        user = create_test_user(db_session, email="ent_empty@example.com")
        resp = logged_in_client.get(f"/admin/users/{user.id}/entities")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "entities" in data
        assert isinstance(data["entities"], list)

    def test_returns_entities_for_user(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        user = create_test_user(db_session, email="ent_with_perm@example.com")
        country = create_test_country(db_session)
        _make_entity_permission(db_session, user, "country", country.id)
        resp = logged_in_client.get(f"/admin/users/{user.id}/entities")
        assert resp.status_code == 200

    def test_404_for_nonexistent_user(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get("/admin/users/999999/entities")
        assert resp.status_code == 404

    def test_skips_entity_not_found(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        user = create_test_user(db_session, email="ent_ghost@example.com")
        # Permission pointing to a nonexistent entity
        from app.models.core import UserEntityPermission
        perm = UserEntityPermission(
            user_id=user.id,
            entity_type="country",
            entity_id=999999,
        )
        db_session.add(perm)
        db_session.commit()
        resp = logged_in_client.get(f"/admin/users/{user.id}/entities")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# add_user_entity (POST /admin/users/<id>/entities/add)
# ---------------------------------------------------------------------------

class TestAddUserEntity:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post(
            "/admin/users/1/entities/add",
            json={"entity_type": "country", "entity_id": 1},
        )
        assert resp.status_code in (302, 401)

    def test_missing_permission_forbidden(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="add_ent_no_perm@example.com")
        resp = logged_in_client.post(
            f"/admin/users/{user.id}/entities/add",
            json={"entity_type": "country", "entity_id": 1},
        )
        assert resp.status_code in (302, 403)

    def test_404_for_nonexistent_user(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.post(
            "/admin/users/999999/entities/add",
            json={"entity_type": "country", "entity_id": 1},
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_missing_entity_type_returns_400(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        user = create_test_user(db_session, email="add_ent_miss_type@example.com")
        resp = logged_in_client.post(
            f"/admin/users/{user.id}/entities/add",
            json={"entity_id": 1},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_missing_entity_id_returns_400(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        user = create_test_user(db_session, email="add_ent_miss_id@example.com")
        resp = logged_in_client.post(
            f"/admin/users/{user.id}/entities/add",
            json={"entity_type": "country"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_invalid_entity_id_returns_400(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        user = create_test_user(db_session, email="add_ent_bad_id@example.com")
        resp = logged_in_client.post(
            f"/admin/users/{user.id}/entities/add",
            json={"entity_type": "country", "entity_id": "not-an-int"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_entity_not_found_returns_404(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        user = create_test_user(db_session, email="add_ent_no_entity@example.com")
        with patch(
            "app.routes.admin.user_management.entities.EntityService.get_entity",
            return_value=None,
        ):
            resp = logged_in_client.post(
                f"/admin/users/{user.id}/entities/add",
                json={"entity_type": "country", "entity_id": 999999},
                content_type="application/json",
            )
        assert resp.status_code == 404

    def test_adds_country_entity(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        user = create_test_user(db_session, email="add_country@example.com")
        country = create_test_country(db_session)
        resp = logged_in_client.post(
            f"/admin/users/{user.id}/entities/add",
            json={"entity_type": "country", "entity_id": country.id},
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_duplicate_permission_returns_409(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        user = create_test_user(db_session, email="add_dup_perm@example.com")
        country = create_test_country(db_session)
        _make_entity_permission(db_session, user, "country", country.id)
        resp = logged_in_client.post(
            f"/admin/users/{user.id}/entities/add",
            json={"entity_type": "country", "entity_id": country.id},
            content_type="application/json",
        )
        assert resp.status_code == 409

    def test_empty_entity_type_returns_400(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        user = create_test_user(db_session, email="add_empty_type@example.com")
        resp = logged_in_client.post(
            f"/admin/users/{user.id}/entities/add",
            json={"entity_type": "", "entity_id": 1},
            content_type="application/json",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# remove_user_entity (DELETE /admin/users/<id>/entities/remove/<perm_id>)
# ---------------------------------------------------------------------------

class TestRemoveUserEntity:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.delete("/admin/users/1/entities/remove/1")
        assert resp.status_code in (302, 401)

    def test_missing_permission_forbidden(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="rem_ent_no_perm@example.com")
        resp = logged_in_client.delete(f"/admin/users/{user.id}/entities/remove/1")
        assert resp.status_code in (302, 403)

    def test_404_for_nonexistent_user(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.delete("/admin/users/999999/entities/remove/1")
        assert resp.status_code == 404

    def test_404_for_nonexistent_perm(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        user = create_test_user(db_session, email="rem_no_perm_id@example.com")
        resp = logged_in_client.delete(
            f"/admin/users/{user.id}/entities/remove/999999"
        )
        assert resp.status_code == 404

    def test_removes_non_country_permission(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        user = create_test_user(db_session, email="rem_non_country@example.com")
        perm = _make_entity_permission(db_session, user, "division", 1)
        resp = logged_in_client.delete(
            f"/admin/users/{user.id}/entities/remove/{perm.id}"
        )
        assert resp.status_code == 200

    def test_removes_country_permission(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        user = create_test_user(db_session, email="rem_country@example.com")
        country = create_test_country(db_session)
        perm = _make_entity_permission(db_session, user, "country", country.id)
        resp = logged_in_client.delete(
            f"/admin/users/{user.id}/entities/remove/{perm.id}"
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# search_entities (GET /admin/entities/search)
# ---------------------------------------------------------------------------

class TestSearchEntities:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/entities/search?type=country&q=test")
        assert resp.status_code in (302, 401)

    def test_missing_permission_redirects(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/entities/search?type=country&q=test")
        assert resp.status_code in (302, 403)

    def test_missing_entity_type_returns_400(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get("/admin/entities/search?q=test")
        assert resp.status_code == 400

    def test_search_countries(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        create_test_country(db_session, name="Searchable Country")
        resp = logged_in_client.get(
            "/admin/entities/search?type=country&q=Searchable"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "results" in data

    def test_search_ns_branches(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/search?type=ns_branch&q=test"
        )
        assert resp.status_code == 200

    def test_search_ns_subbranches(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/search?type=ns_subbranch&q=test"
        )
        assert resp.status_code == 200

    def test_search_divisions(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/search?type=division&q=test"
        )
        assert resp.status_code == 200

    def test_search_departments(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/search?type=department&q=test"
        )
        assert resp.status_code == 200

    def test_search_regional_offices(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/search?type=regional_office&q=test"
        )
        assert resp.status_code == 200

    def test_search_cluster_offices(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/search?type=cluster_office&q=test"
        )
        assert resp.status_code == 200

    def test_search_national_societies(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/search?type=national_society&q=test"
        )
        assert resp.status_code == 200

    def test_empty_query_returns_results(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get("/admin/entities/search?type=country")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# get_ns_hierarchy (GET /admin/structure/ns-hierarchy)
# ---------------------------------------------------------------------------

class TestGetNsHierarchy:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/structure/ns-hierarchy")
        assert resp.status_code in (302, 401)

    def test_missing_permission_redirects(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/structure/ns-hierarchy")
        assert resp.status_code in (302, 403)

    def test_returns_hierarchy(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get("/admin/structure/ns-hierarchy")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "hierarchy" in data

    def test_returns_hierarchy_for_country(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        country = create_test_country(db_session)
        resp = logged_in_client.get(
            f"/admin/structure/ns-hierarchy?country_id={country.id}"
        )
        assert resp.status_code == 200

    def test_404_for_nonexistent_country(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/structure/ns-hierarchy?country_id=999999"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# get_secretariat_hierarchy (GET /admin/structure/secretariat-hierarchy)
# ---------------------------------------------------------------------------

class TestGetSecretariatHierarchy:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/structure/secretariat-hierarchy")
        assert resp.status_code in (302, 401)

    def test_missing_permission_redirects(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/structure/secretariat-hierarchy")
        assert resp.status_code in (302, 403)

    def test_returns_hierarchy(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get("/admin/structure/secretariat-hierarchy")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "hierarchy" in data

    def test_hierarchy_structure(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        from app.models import SecretariatDivision
        div = SecretariatDivision(name="Test Div", code="TD", is_active=True)
        db_session.add(div)
        db_session.commit()
        resp = logged_in_client.get("/admin/structure/secretariat-hierarchy")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# get_hierarchical_entities (GET /admin/entities/hierarchical)
# ---------------------------------------------------------------------------

class TestGetHierarchicalEntities:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/entities/hierarchical?types=country")
        assert resp.status_code in (302, 401)

    def test_missing_permission_redirects(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/entities/hierarchical?types=country")
        assert resp.status_code in (302, 403)

    def test_no_types_returns_400(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get("/admin/entities/hierarchical")
        assert resp.status_code == 400

    def test_returns_countries(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        create_test_country(db_session)
        resp = logged_in_client.get("/admin/entities/hierarchical?types=country")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "countries" in data

    def test_returns_ns_branches(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/hierarchical?types=ns_branch"
        )
        assert resp.status_code == 200

    def test_returns_ns_subbranches(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/hierarchical?types=ns_subbranch"
        )
        assert resp.status_code == 200

    def test_returns_ns_localunits(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/hierarchical?types=ns_localunit"
        )
        assert resp.status_code == 200

    def test_returns_divisions(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/hierarchical?types=division"
        )
        assert resp.status_code == 200

    def test_returns_departments(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/hierarchical?types=department"
        )
        assert resp.status_code == 200

    def test_returns_regional_offices(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/hierarchical?types=regional_office"
        )
        assert resp.status_code == 200

    def test_returns_cluster_offices(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/hierarchical?types=cluster_office"
        )
        assert resp.status_code == 200

    def test_returns_national_societies(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/hierarchical?types=national_society"
        )
        assert resp.status_code == 200

    def test_multiple_types(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get(
            "/admin/entities/hierarchical?types=country&types=division"
        )
        assert resp.status_code == 200

    def test_country_without_region(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        from app.models import Country
        c = Country(name="NoRegionLand", iso2="NR", iso3="NRL")
        db_session.add(c)
        db_session.commit()
        resp = logged_in_client.get("/admin/entities/hierarchical?types=country")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# get_secretariat_regions_hierarchy (GET /admin/structure/secretariat-regions-hierarchy)
# ---------------------------------------------------------------------------

class TestGetSecretariatRegionsHierarchy:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/structure/secretariat-regions-hierarchy")
        assert resp.status_code in (302, 401)

    def test_missing_permission_redirects(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/structure/secretariat-regions-hierarchy")
        assert resp.status_code in (302, 403)

    def test_returns_hierarchy(self, logged_in_client, db_session, admin_user):
        _ensure_grants_perm(db_session)
        resp = logged_in_client.get("/admin/structure/secretariat-regions-hierarchy")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "hierarchy" in data

    def test_returns_clusters_for_region(
        self, logged_in_client, db_session, admin_user
    ):
        _ensure_grants_perm(db_session)
        from app.models.organization import SecretariatRegionalOffice, SecretariatClusterOffice
        region = SecretariatRegionalOffice(
            name="Test Region", code="TR", is_active=True
        )
        db_session.add(region)
        db_session.flush()
        cluster = SecretariatClusterOffice(
            name="Test Cluster",
            code="TC",
            regional_office_id=region.id,
            is_active=True,
        )
        db_session.add(cluster)
        db_session.commit()

        resp = logged_in_client.get("/admin/structure/secretariat-regions-hierarchy")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "hierarchy" in data
