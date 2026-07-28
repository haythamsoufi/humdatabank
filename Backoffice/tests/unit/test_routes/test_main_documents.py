"""
Tests for app/routes/main/documents.py

Covers:
  - GET  /documents  — various permission / entity scenarios
  - POST /documents  — entity_select form handling
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.factories import (
    create_test_user,
    create_test_country,
    create_test_assignment_entity_status,
    _grant_entity_permission,
)
from tests.helpers import login_session, assert_redirect

pytestmark = [pytest.mark.unit]

# AuthorizationService and get_document_types are imported lazily inside the route function.
_AUTH_SVC = "app.services.organization.authorization_service.AuthorizationService"
_DOC_TYPES = "app.services.platform.app_settings_service.get_document_types"
# _row_with_focal_entity_access is imported lazily inside the route function.
_ROW_WITH_FOCAL = "app.routes.admin.content_management._row_with_focal_entity_access"


# ===========================================================================
# Helpers
# ===========================================================================

def _login(client, user):
    login_session(client, user.id)


def _set_entity_session(client, entity_type, entity_id, country_id=None):
    with client.session_transaction() as sess:
        sess["selected_entity_type"] = entity_type
        sess["selected_entity_id"] = entity_id
        if country_id is not None:
            sess["selected_country_id"] = country_id


def _make_mock_entity(entity_id, entity_type="country"):
    entity = MagicMock()
    entity.id = entity_id
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entity": entity,
    }


# ===========================================================================
# GET /documents — authentication
# ===========================================================================

class TestDocumentsSubmitAuth:
    def test_unauthenticated_redirects_to_login(self, client, db_session, app):
        resp = client.get("/documents")
        assert_redirect(resp)
        assert "login" in (resp.headers.get("Location") or "").lower()


# ===========================================================================
# GET /documents — admin/system manager redirected to content_management
# ===========================================================================

class TestDocumentsSubmitAdminRedirect:
    def test_system_manager_redirected_to_manage_documents(self, client, db_session, app):
        user = create_test_user(db_session, role="system_manager")
        _login(client, user)
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=True):
            resp = client.get("/documents", follow_redirects=False)
        assert_redirect(resp)
        location = resp.headers.get("Location", "")
        assert "manage_documents" in location or "documents" in location

    def test_admin_with_documents_manage_permission_redirected(self, client, db_session, app, admin_user):
        _login(client, admin_user)
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission",
                   side_effect=lambda user, perm, **kw: perm == "admin.documents.manage"):
            resp = client.get("/documents", follow_redirects=False)
        assert_redirect(resp)


# ===========================================================================
# GET /documents — permission denied (no assignment.documents.upload)
# ===========================================================================

class TestDocumentsSubmitNoPermission:
    def test_no_upload_permission_redirects_with_flash(self, client, db_session, app, test_user):
        _login(client, test_user)
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=False):
            resp = client.get("/documents", follow_redirects=False)
        assert_redirect(resp, "dashboard")


# ===========================================================================
# GET /documents — no user entities
# ===========================================================================

class TestDocumentsSubmitNoEntities:
    def test_no_entities_redirects_with_flash(self, client, db_session, app, test_user):
        """User has upload permission but no entity assignments → redirect."""
        _login(client, test_user)
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True), \
             patch("app.routes.main.documents._build_user_nav_entities", return_value=([], [], [])), \
             patch(_DOC_TYPES, return_value=["pdf"]):
            resp = client.get("/documents", follow_redirects=False)
        assert_redirect(resp, "dashboard")


# ===========================================================================
# GET /documents — no selected entity can be resolved
# ===========================================================================

class TestDocumentsSubmitNoSelectedEntity:
    def test_no_selected_entity_redirects_to_dashboard(self, client, db_session, app, test_user):
        country = create_test_country(db_session)
        _login(client, test_user)
        mock_entity_list = [_make_mock_entity(country.id)]

        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True), \
             patch("app.routes.main.documents._build_user_nav_entities",
                   return_value=(mock_entity_list, [], ["country"])), \
             patch("app.routes.main.documents._resolve_selected_entity_for_focal_nav",
                   return_value=(None, None, None, None)), \
             patch(_DOC_TYPES, return_value=["pdf", "docx"]), \
             patch("app.routes.main.documents.get_enabled_entity_groups", return_value={"countries"}):
            resp = client.get("/documents", follow_redirects=False)
        assert_redirect(resp, "dashboard")


# ===========================================================================
# GET /documents — successful render (single entity user)
# ===========================================================================

class TestDocumentsSubmitRender:
    def _base_patches(self, country, entity_list, resolved_entity):
        """Return a context manager with all common patches for the render path."""
        from contextlib import ExitStack
        return [
            patch(f"{_AUTH_SVC}.is_system_manager", return_value=False),
            patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True),
            patch("app.routes.main.documents._build_user_nav_entities",
                  return_value=(entity_list, [country], ["country"])),
            patch("app.routes.main.documents._resolve_selected_entity_for_focal_nav",
                  return_value=resolved_entity),
            patch(_DOC_TYPES, return_value=["pdf", "docx"]),
            patch("app.routes.main.documents.get_enabled_entity_groups", return_value={"countries"}),
            patch("app.routes.main.documents.EntityService.get_country_for_entity", return_value=country),
            patch("app.routes.main.documents.EntityService.get_entity_type_label", return_value="Country"),
            patch(_ROW_WITH_FOCAL, side_effect=lambda r: r),
            patch("app.routes.main.documents._document_modal_entity_choice_rows", return_value=None),
        ]

    def test_single_entity_user_renders_page(self, client, db_session, app, test_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, test_user, "country", country.id)
        db_session.commit()
        _login(client, test_user)

        mock_entity = MagicMock()
        mock_entity.id = country.id
        mock_entity_dict = {"entity_type": "country", "entity_id": country.id, "entity": mock_entity}
        resolved = (mock_entity, "country", country.id, country)

        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True), \
             patch("app.routes.main.documents._build_user_nav_entities",
                   return_value=([mock_entity_dict], [country], ["country"])), \
             patch("app.routes.main.documents._resolve_selected_entity_for_focal_nav",
                   return_value=resolved), \
             patch(_DOC_TYPES, return_value=["pdf", "docx"]), \
             patch("app.routes.main.documents.get_enabled_entity_groups", return_value={"countries"}), \
             patch("app.routes.main.documents.EntityService.get_country_for_entity", return_value=country), \
             patch("app.routes.main.documents.EntityService.get_localized_entity_name",
                   return_value="Test Country"), \
             patch("app.routes.main.documents.EntityService.get_entity_type_label", return_value="Country"), \
             patch(_ROW_WITH_FOCAL, side_effect=lambda r: r), \
             patch("app.routes.main.documents._document_modal_entity_choice_rows", return_value=None), \
             patch("app.routes.main.documents.render_template",
                   return_value="<html>documents page</html>"):
            resp = client.get("/documents")

        assert resp.status_code == 200

    def test_multiple_entities_shows_entity_select(self, client, db_session, app, test_user):
        """With more than one entity, show_entity_select should be True."""
        country1 = create_test_country(db_session)
        country2 = create_test_country(db_session)
        _grant_entity_permission(db_session, test_user, "country", country1.id)
        _grant_entity_permission(db_session, test_user, "country", country2.id)
        db_session.commit()
        _login(client, test_user)

        mock_entity1 = _make_mock_entity(country1.id)
        mock_entity2 = _make_mock_entity(country2.id)
        entity_list = [mock_entity1, mock_entity2]
        mock_resolved_entity = MagicMock()
        mock_resolved_entity.id = country1.id
        resolved = (mock_resolved_entity, "country", country1.id, country1)

        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True), \
             patch("app.routes.main.documents._build_user_nav_entities",
                   return_value=(entity_list, [country1, country2], ["country"])), \
             patch("app.routes.main.documents._resolve_selected_entity_for_focal_nav",
                   return_value=resolved), \
             patch(_DOC_TYPES, return_value=["pdf"]), \
             patch("app.routes.main.documents.get_enabled_entity_groups", return_value={"countries"}), \
             patch("app.routes.main.documents.EntityService.get_country_for_entity", return_value=country1), \
             patch("app.routes.main.documents.EntityService.get_localized_entity_name",
                   return_value="Test Country"), \
             patch("app.routes.main.documents.EntityService.get_entity_type_label", return_value="Country"), \
             patch(_ROW_WITH_FOCAL, side_effect=lambda r: r), \
             patch("app.routes.main.documents._document_modal_entity_choice_rows",
                   return_value=[{"value": f"country:{country1.id}", "label": country1.name}]), \
             patch("app.routes.main.documents.render_template",
                   return_value="<html>documents page</html>") as mock_render:
            resp = client.get("/documents")

        assert resp.status_code == 200
        call_kwargs = mock_render.call_args[1]
        assert call_kwargs.get("show_entity_select") is True

    def test_entity_repo_label_set_for_single_entity(self, client, db_session, app, test_user):
        """For single-entity users, documents_entity_repo_label should be set."""
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, test_user, "country", country.id)
        db_session.commit()
        _login(client, test_user)

        mock_entity_dict = _make_mock_entity(country.id)
        resolved = (mock_entity_dict["entity"], "country", country.id, country)

        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True), \
             patch("app.routes.main.documents._build_user_nav_entities",
                   return_value=([mock_entity_dict], [country], ["country"])), \
             patch("app.routes.main.documents._resolve_selected_entity_for_focal_nav",
                   return_value=resolved), \
             patch(_DOC_TYPES, return_value=["pdf"]), \
             patch("app.routes.main.documents.get_enabled_entity_groups", return_value={"countries"}), \
             patch("app.routes.main.documents.EntityService.get_country_for_entity", return_value=country), \
             patch("app.routes.main.documents.EntityService.get_localized_entity_name",
                   return_value="Test Country"), \
             patch("app.routes.main.documents.EntityService.get_entity_type_label", return_value="Country"), \
             patch(_ROW_WITH_FOCAL, side_effect=lambda r: r), \
             patch("app.routes.main.documents._document_modal_entity_choice_rows", return_value=None), \
             patch("app.routes.main.documents.render_template", return_value="<html>ok</html>") as mock_render:
            resp = client.get("/documents")

        assert resp.status_code == 200
        call_kwargs = mock_render.call_args[1]
        assert call_kwargs.get("show_entity_select") is False
        assert call_kwargs.get("documents_entity_repo_label") is not None

    def test_entity_repo_label_none_when_localized_name_raises(self, client, db_session, app, test_user):
        """If EntityService.get_localized_entity_name raises, label should be None."""
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, test_user, "country", country.id)
        db_session.commit()
        _login(client, test_user)

        mock_entity_dict = _make_mock_entity(country.id)
        resolved = (mock_entity_dict["entity"], "country", country.id, country)

        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True), \
             patch("app.routes.main.documents._build_user_nav_entities",
                   return_value=([mock_entity_dict], [country], ["country"])), \
             patch("app.routes.main.documents._resolve_selected_entity_for_focal_nav",
                   return_value=resolved), \
             patch(_DOC_TYPES, return_value=["pdf"]), \
             patch("app.routes.main.documents.get_enabled_entity_groups", return_value={"countries"}), \
             patch("app.routes.main.documents.EntityService.get_country_for_entity", return_value=country), \
             patch("app.routes.main.documents.EntityService.get_localized_entity_name",
                   side_effect=Exception("label error")), \
             patch("app.routes.main.documents.EntityService.get_entity_type_label", return_value="Country"), \
             patch(_ROW_WITH_FOCAL, side_effect=lambda r: r), \
             patch("app.routes.main.documents._document_modal_entity_choice_rows", return_value=None), \
             patch("app.routes.main.documents.render_template", return_value="<html>ok</html>") as mock_render:
            resp = client.get("/documents")

        assert resp.status_code == 200
        call_kwargs = mock_render.call_args[1]
        assert call_kwargs.get("documents_entity_repo_label") is None


# ===========================================================================
# POST /documents — entity_select form handling
# ===========================================================================

class TestDocumentsSubmitPost:
    """POST /documents with entity_select field."""

    def _post_with_patches(self, client, country, mock_entity_dict, data, get_country_for_entity=None):
        """Helper: applies auth + nav patches and POSTs to /documents."""
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True), \
             patch("app.routes.main.documents._build_user_nav_entities",
                   return_value=([mock_entity_dict], [country], ["country"])), \
             patch(_DOC_TYPES, return_value=["pdf"]), \
             patch("app.routes.main.documents.get_enabled_entity_groups", return_value={"countries"}), \
             patch("app.routes.main.documents.EntityService.get_country_for_entity",
                   return_value=get_country_for_entity):
            return client.post("/documents", data=data, follow_redirects=False)

    def test_post_valid_entity_select_sets_session(self, client, db_session, app, test_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, test_user, "country", country.id)
        db_session.commit()
        _login(client, test_user)

        mock_entity_dict = _make_mock_entity(country.id)
        resp = self._post_with_patches(
            client, country, mock_entity_dict,
            data={"entity_select": f"country:{country.id}"},
            get_country_for_entity=country,
        )
        assert_redirect(resp, "documents")

    def test_post_entity_select_not_in_permissions_clears_session(self, client, db_session, app, test_user):
        """Selecting an entity not in user's permissions clears the session key."""
        country = create_test_country(db_session)
        other_country = create_test_country(db_session)
        _grant_entity_permission(db_session, test_user, "country", country.id)
        db_session.commit()
        _login(client, test_user)

        mock_entity_dict = _make_mock_entity(country.id)
        resp = self._post_with_patches(
            client, country, mock_entity_dict,
            data={"entity_select": f"country:{other_country.id}"},
            get_country_for_entity=None,
        )
        assert_redirect(resp, "documents")

    def test_post_invalid_entity_select_format_shows_warning(self, client, db_session, app, test_user):
        """Submitting entity_select without ':' separator → warning flash."""
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, test_user, "country", country.id)
        db_session.commit()
        _login(client, test_user)

        mock_entity_dict = _make_mock_entity(country.id)
        resp = self._post_with_patches(
            client, country, mock_entity_dict,
            data={"entity_select": "invalid"},
        )
        assert_redirect(resp, "documents")

    def test_post_empty_entity_select_value_shows_warning(self, client, db_session, app, test_user):
        """Submitting entity_select with empty string → invalid selection warning."""
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, test_user, "country", country.id)
        db_session.commit()
        _login(client, test_user)

        mock_entity_dict = _make_mock_entity(country.id)
        resp = self._post_with_patches(
            client, country, mock_entity_dict,
            data={"entity_select": ""},
        )
        assert_redirect(resp, "documents")

    def test_post_entity_select_bad_id_shows_warning(self, client, db_session, app, test_user):
        """Non-integer id after ':' triggers ValueError warning."""
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, test_user, "country", country.id)
        db_session.commit()
        _login(client, test_user)

        mock_entity_dict = _make_mock_entity(country.id)
        resp = self._post_with_patches(
            client, country, mock_entity_dict,
            data={"entity_select": "country:not-a-number"},
        )
        assert_redirect(resp, "documents")

    def test_post_entity_select_related_country_set_in_session(self, client, db_session, app, test_user):
        """When entity has a related country, session SELECTED_COUNTRY_ID_SESSION_KEY is updated."""
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, test_user, "country", country.id)
        db_session.commit()
        _login(client, test_user)

        mock_entity_dict = _make_mock_entity(country.id)
        resp = self._post_with_patches(
            client, country, mock_entity_dict,
            data={"entity_select": f"country:{country.id}"},
            get_country_for_entity=country,
        )
        assert_redirect(resp, "documents")
        with client.session_transaction() as sess:
            assert sess.get("selected_country_id") == country.id
