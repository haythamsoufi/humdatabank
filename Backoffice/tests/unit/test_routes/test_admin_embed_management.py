"""
Tests for app/routes/admin/embed_management.py

Coverage targets:
- manage_embed_content (GET HTML / GET JSON / exception HTML / exception JSON)
- create_embed_content (validation failures, success, exception)
- update_embed_content (various field validations, 404, success, exception)
- delete_embed_content (success, 404, exception)
- reorder_embed_content (success, missing list, too many items, exception)

All endpoints use @permission_required('admin.resources.manage').
The `admin_core` role created by `create_test_admin` has this permission
granted by default, so `logged_in_client` works here without extra fixtures.
"""
import json
import pytest
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.unit]

# Valid Power BI embed URL for tests
_VALID_POWERBI_URL = "https://app.powerbi.com/reportEmbed?reportId=test-report"
_VALID_TABLEAU_URL = "https://public.tableau.com/views/test/report"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_json(client, url, payload):
    return client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
    )


def _put_json(client, url, payload):
    return client.put(
        url,
        data=json.dumps(payload),
        content_type="application/json",
    )


def _patch_json(client, url, payload):
    return client.patch(
        url,
        data=json.dumps(payload),
        content_type="application/json",
    )


def _delete(client, url):
    return client.delete(url, content_type="application/json")


def _create_embed_item(db_session, app, **kwargs):
    """Insert an EmbedContent row directly and return it."""
    from app.models.embed_content import EmbedContent
    with app.app_context():
        defaults = {
            "title": kwargs.get("title", "Test Embed"),
            "category": kwargs.get("category", "global_initiative"),
            "embed_url": kwargs.get("embed_url", _VALID_POWERBI_URL),
            "embed_type": kwargs.get("embed_type", "powerbi"),
            "is_active": kwargs.get("is_active", True),
            "sort_order": kwargs.get("sort_order", 0),
        }
        item = EmbedContent(**defaults)
        db_session.add(item)
        db_session.commit()
        db_session.refresh(item)
        return item


# ---------------------------------------------------------------------------
# manage_embed_content
# ---------------------------------------------------------------------------

class TestManageEmbedContent:
    def test_get_html_returns_200(self, logged_in_client, db_session, app):
        resp = logged_in_client.get("/admin/embed-content")
        assert resp.status_code == 200

    def test_get_json_returns_items_list(self, logged_in_client, db_session, app):
        _create_embed_item(db_session, app, title="JSON List Item")
        resp = logged_in_client.get(
            "/admin/embed-content",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True
        assert isinstance(data.get("items"), list)

    def test_get_unauthenticated_redirects(self, client, db_session, app):
        resp = client.get("/admin/embed-content")
        assert resp.status_code == 302

    def test_get_exception_renders_error_template(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.embed_management.EmbedContent") as mock_ec:
            mock_ec.query.order_by.side_effect = Exception("db error")
            resp = logged_in_client.get("/admin/embed-content")
        assert resp.status_code == 200  # renders error template, not 500

    def test_get_exception_json_returns_server_error(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.embed_management.EmbedContent") as mock_ec:
            mock_ec.query.order_by.side_effect = Exception("db error")
            resp = logged_in_client.get(
                "/admin/embed-content",
                headers={"Accept": "application/json"},
            )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# create_embed_content
# ---------------------------------------------------------------------------

class TestCreateEmbedContent:
    def test_create_success_powerbi(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/create",
            {
                "title": "New Power BI Dashboard",
                "embed_url": _VALID_POWERBI_URL,
                "embed_type": "powerbi",
                "category": "global_initiative",
            },
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_create_success_tableau(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/create",
            {
                "title": "Tableau View",
                "embed_url": _VALID_TABLEAU_URL,
                "embed_type": "tableau",
                "category": "analysis",
            },
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_create_success_with_optional_fields(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/create",
            {
                "title": "Full Embed Item",
                "embed_url": _VALID_POWERBI_URL,
                "embed_type": "powerbi",
                "category": "global_initiative",
                "description": "A longer description",
                "aspect_ratio": "16:9",
                "is_active": True,
            },
        )
        assert resp.status_code == 200

    def test_create_success_with_page_slot(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/create",
            {
                "title": "Slotted Embed",
                "embed_url": _VALID_POWERBI_URL,
                "embed_type": "powerbi",
                "category": "global_initiative",
                "page_slot": "grbm",
            },
        )
        assert resp.status_code == 200

    def test_create_missing_title_returns_400(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/create",
            {"embed_url": _VALID_POWERBI_URL, "category": "global_initiative"},
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "title" in data.get("error", "").lower()

    def test_create_title_too_long_returns_400(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/create",
            {
                "title": "x" * 256,
                "embed_url": _VALID_POWERBI_URL,
                "category": "global_initiative",
            },
        )
        assert resp.status_code == 400

    def test_create_missing_embed_url_returns_400(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/create",
            {"title": "No URL", "category": "global_initiative"},
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "url" in data.get("error", "").lower()

    def test_create_invalid_embed_type_returns_400(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/create",
            {
                "title": "Bad Type",
                "embed_url": _VALID_POWERBI_URL,
                "embed_type": "unknown_type",
                "category": "global_initiative",
            },
        )
        assert resp.status_code == 400

    def test_create_invalid_category_returns_400(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/create",
            {
                "title": "Bad Category",
                "embed_url": _VALID_POWERBI_URL,
                "category": "not_a_real_category",
            },
        )
        assert resp.status_code == 400

    def test_create_invalid_url_domain_returns_400(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/create",
            {
                "title": "Bad Domain",
                "embed_url": "https://untrusted.example.com/embed",
                "embed_type": "powerbi",
                "category": "global_initiative",
            },
        )
        assert resp.status_code == 400

    def test_create_invalid_page_slot_returns_400(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/create",
            {
                "title": "Bad Slot",
                "embed_url": _VALID_POWERBI_URL,
                "category": "global_initiative",
                "page_slot": "invalid_slot_xyz",
            },
        )
        assert resp.status_code == 400

    def test_create_iframe_type_success(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/create",
            {
                "title": "Iframe Embed",
                "embed_url": _VALID_POWERBI_URL,
                "embed_type": "iframe",
                "category": "other",
            },
        )
        assert resp.status_code == 200

    def test_create_exception_returns_server_error(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.embed_management.db") as mock_db:
            mock_db.session.query.return_value.filter_by.return_value.scalar.return_value = 0
            mock_db.session.add.side_effect = Exception("db insert fail")
            mock_db.func.max.return_value = None
            resp = _post_json(
                logged_in_client,
                "/admin/embed-content/create",
                {
                    "title": "Exception Create",
                    "embed_url": _VALID_POWERBI_URL,
                    "category": "global_initiative",
                },
            )
        assert resp.status_code == 500

    def test_create_with_snippet_containing_url(self, logged_in_client, db_session, app):
        """HTML snippet with a PowerBI URL should be auto-extracted."""
        snippet = f'<iframe src="{_VALID_POWERBI_URL}" width="800" height="600"></iframe>'
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/create",
            {
                "title": "Snippet Embed",
                "embed_url": snippet,
                "embed_type": "powerbi",
                "category": "global_initiative",
            },
        )
        assert resp.status_code == 200

    def test_create_unauthenticated_redirects(self, client, db_session, app):
        resp = _post_json(
            client,
            "/admin/embed-content/create",
            {"title": "Anon", "embed_url": _VALID_POWERBI_URL},
        )
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# update_embed_content
# ---------------------------------------------------------------------------

class TestUpdateEmbedContent:
    def test_update_title(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app, title="Old Title")
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"title": "New Title"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_update_empty_title_returns_400(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"title": ""},
        )
        assert resp.status_code == 400

    def test_update_title_too_long_returns_400(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"title": "x" * 256},
        )
        assert resp.status_code == 400

    def test_update_embed_url(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"embed_url": _VALID_POWERBI_URL + "?updated=1"},
        )
        assert resp.status_code == 200

    def test_update_empty_embed_url_returns_400(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"embed_url": ""},
        )
        assert resp.status_code == 400

    def test_update_invalid_embed_url_returns_400(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"embed_url": "https://evil.com/bad"},
        )
        assert resp.status_code == 400

    def test_update_embed_type_invalid_returns_400(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"embed_type": "invalid_type"},
        )
        assert resp.status_code == 400

    def test_update_embed_type_revalidates_url(self, logged_in_client, db_session, app):
        """Changing type without changing URL should revalidate the stored URL."""
        item = _create_embed_item(db_session, app, embed_type="powerbi")
        # tableau type won't accept powerbi URL
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"embed_type": "tableau"},
        )
        assert resp.status_code == 400  # powerbi URL invalid for tableau

    def test_update_category(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"category": "analysis"},
        )
        assert resp.status_code == 200

    def test_update_invalid_category_returns_400(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"category": "bad_cat"},
        )
        assert resp.status_code == 400

    def test_update_aspect_ratio(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"aspect_ratio": "4:3"},
        )
        assert resp.status_code == 200

    def test_update_page_slot(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"page_slot": "echo_partnership"},
        )
        assert resp.status_code == 200

    def test_update_invalid_page_slot_returns_400(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"page_slot": "not_a_real_slot"},
        )
        assert resp.status_code == 400

    def test_update_clear_page_slot(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"page_slot": ""},
        )
        assert resp.status_code == 200

    def test_update_is_active(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app, is_active=True)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"is_active": False},
        )
        assert resp.status_code == 200

    def test_update_sort_order(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"sort_order": 5},
        )
        assert resp.status_code == 200

    def test_update_invalid_sort_order_returns_400(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"sort_order": "not_a_number"},
        )
        assert resp.status_code == 400

    def test_update_description(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"description": "New description text"},
        )
        assert resp.status_code == 200

    def test_update_clears_description(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"description": ""},
        )
        assert resp.status_code == 200

    def test_update_url_with_snippet_extracts_ratio(self, logged_in_client, db_session, app):
        """Snippet with width/height should auto-extract aspect ratio."""
        item = _create_embed_item(db_session, app)
        snippet = f'<iframe src="{_VALID_POWERBI_URL}" width="1600" height="900"></iframe>'
        resp = _put_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"embed_url": snippet},
        )
        assert resp.status_code == 200

    def test_update_via_patch_method(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        resp = _patch_json(
            logged_in_client,
            f"/admin/embed-content/{item.id}",
            {"title": "Patched Title"},
        )
        assert resp.status_code == 200

    def test_update_nonexistent_returns_404(self, logged_in_client, db_session, app):
        resp = _put_json(
            logged_in_client,
            "/admin/embed-content/99999",
            {"title": "Ghost"},
        )
        assert resp.status_code == 404

    def test_update_exception_returns_server_error(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app)
        with patch("app.routes.admin.embed_management.db") as mock_db:
            mock_db.session.get.return_value = MagicMock(
                id=item.id,
                embed_type="powerbi",
                embed_url=_VALID_POWERBI_URL,
            )
            mock_db.session.commit.side_effect = Exception("commit fail")
            resp = _put_json(
                logged_in_client,
                f"/admin/embed-content/{item.id}",
                {"title": "Exception Update"},
            )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# delete_embed_content
# ---------------------------------------------------------------------------

class TestDeleteEmbedContent:
    def test_delete_existing_item(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app, title="To Delete")
        resp = _delete(logged_in_client, f"/admin/embed-content/{item.id}")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_delete_nonexistent_returns_404(self, logged_in_client, db_session, app):
        resp = _delete(logged_in_client, "/admin/embed-content/99999")
        assert resp.status_code == 404

    def test_delete_exception_returns_server_error(self, logged_in_client, db_session, app):
        item = _create_embed_item(db_session, app, title="Exception Delete")
        with patch("app.routes.admin.embed_management.db") as mock_db:
            mock_db.session.get.return_value = MagicMock()
            mock_db.session.delete.side_effect = Exception("delete fail")
            resp = _delete(logged_in_client, f"/admin/embed-content/{item.id}")
        assert resp.status_code == 500

    def test_delete_unauthenticated_redirects(self, client, db_session, app):
        resp = _delete(client, "/admin/embed-content/1")
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# reorder_embed_content
# ---------------------------------------------------------------------------

class TestReorderEmbedContent:
    def test_reorder_success(self, logged_in_client, db_session, app):
        item1 = _create_embed_item(db_session, app, title="Item 1")
        item2 = _create_embed_item(db_session, app, title="Item 2")
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/reorder",
            {"order": [item2.id, item1.id]},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_reorder_missing_order_returns_400(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/reorder",
            {},
        )
        assert resp.status_code == 400

    def test_reorder_empty_list_returns_400(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/reorder",
            {"order": []},
        )
        assert resp.status_code == 400

    def test_reorder_not_a_list_returns_400(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/reorder",
            {"order": "not-a-list"},
        )
        assert resp.status_code == 400

    def test_reorder_too_many_items_returns_400(self, logged_in_client, db_session, app):
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/reorder",
            {"order": list(range(501))},
        )
        assert resp.status_code == 400

    def test_reorder_skips_non_int_ids(self, logged_in_client, db_session, app):
        """Non-integer IDs are silently skipped, not an error."""
        item = _create_embed_item(db_session, app, title="Reorder Skip")
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/reorder",
            {"order": [item.id, "not_an_int", None]},
        )
        assert resp.status_code == 200

    def test_reorder_nonexistent_ids_skipped(self, logged_in_client, db_session, app):
        """IDs for items that don't exist are silently ignored."""
        resp = _post_json(
            logged_in_client,
            "/admin/embed-content/reorder",
            {"order": [99998, 99999]},
        )
        assert resp.status_code == 200

    def test_reorder_exception_returns_server_error(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.embed_management.db") as mock_db:
            mock_db.session.get.return_value = MagicMock()
            mock_db.session.commit.side_effect = Exception("reorder commit fail")
            resp = _post_json(
                logged_in_client,
                "/admin/embed-content/reorder",
                {"order": [1, 2, 3]},
            )
        assert resp.status_code == 500
