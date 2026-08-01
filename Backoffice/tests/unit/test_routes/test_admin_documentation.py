"""
Tests for app/routes/admin/documentation.py

Coverage targets:
- index(): docs_root missing → 404; docs_root exists → renders page
- view_doc(): .md extension → 404; README → 404; valid path → renders page
- asset(): path traversal → 404; missing file → 404; valid file → served
- _canonical_doc_path_for_url(): via index / view_doc
- _build_doc_url(): exercised as part of route rendering

The admin user created by `create_test_admin` does NOT have `admin.docs.view`
by default.  The `docs_client` fixture here grants that permission explicitly.
"""
import os
import tempfile
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helper fixture: adds admin.docs.view to the admin_core role
# ---------------------------------------------------------------------------

@pytest.fixture()
def docs_client(logged_in_client, db_session, app):
    """logged_in_client that also has admin.docs.view permission."""
    with app.app_context():
        from tests.factories import _grant_role_permission
        _grant_role_permission(db_session, "admin_core", "admin.docs.view")
        db_session.commit()
    return logged_in_client


@pytest.fixture()
def temp_docs_dir():
    """A temporary directory with a minimal docs structure."""
    d = tempfile.mkdtemp()
    # Create a minimal README.md in root
    (Path(d) / "README.md").write_text("# Test Docs\n\nWelcome.", encoding="utf-8")
    # Create a visible subdir
    sub = Path(d) / "user-guides"
    sub.mkdir()
    (sub / "README.md").write_text("# User Guides\n", encoding="utf-8")
    (sub / "intro.md").write_text("# Intro\n\nIntroduction page.", encoding="utf-8")
    # Image asset
    img = Path(d) / "user-guides" / "screenshot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header bytes
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# index route
# ---------------------------------------------------------------------------

class TestDocsIndex:
    def test_index_docs_root_missing_returns_404(self, docs_client, db_session, app):
        """When the docs root directory does not exist, abort(404)."""
        non_existent = Path("/non/existent/path/docs")
        with patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = non_existent
            resp = docs_client.get("/admin/docs/")
        assert resp.status_code == 404

    def test_index_renders_with_valid_docs_root(self, docs_client, db_session, app, temp_docs_dir):
        """When the docs root exists, the page should render (200)."""
        root = Path(temp_docs_dir)
        with patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = root
            mock_docs.resolve_doc_path.return_value = (root / "README.md", "")
            mock_docs.ensure_doc_page_access.return_value = None
            mock_docs.build_hierarchical_nav.return_value = []
            mock_docs.render_markdown_file.return_value = "<p>Welcome</p>"
            mock_docs.extract_page_title.return_value = "Test Docs"
            mock_docs.get_workflow_id_for_doc.return_value = None
            resp = docs_client.get("/admin/docs/")
        assert resp.status_code == 200

    def test_index_unauthenticated_redirects(self, client, db_session, app):
        resp = client.get("/admin/docs/")
        assert resp.status_code == 302

    def test_index_without_docs_permission_redirects(self, logged_in_client, db_session, app):
        """Admin without admin.docs.view should be redirected."""
        resp = logged_in_client.get("/admin/docs/")
        # Will redirect because admin_core role lacks admin.docs.view by default
        assert resp.status_code in (302, 403)


# ---------------------------------------------------------------------------
# view_doc route
# ---------------------------------------------------------------------------

class TestViewDoc:
    def test_view_doc_with_md_extension_returns_404(self, docs_client, db_session, app, temp_docs_dir):
        """Legacy .md URLs should 404."""
        root = Path(temp_docs_dir)
        with patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = root
            resp = docs_client.get("/admin/docs/user-guides/intro.md")
        assert resp.status_code == 404

    def test_view_doc_readme_url_returns_404(self, docs_client, db_session, app, temp_docs_dir):
        """Explicit 'readme' or 'README.md' path is 404."""
        root = Path(temp_docs_dir)
        with patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = root
            resp = docs_client.get("/admin/docs/readme")
        assert resp.status_code == 404

    def test_view_doc_readme_md_returns_404(self, docs_client, db_session, app, temp_docs_dir):
        root = Path(temp_docs_dir)
        with patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = root
            resp = docs_client.get("/admin/docs/README.md")
        assert resp.status_code == 404

    def test_view_doc_root_missing_returns_404(self, docs_client, db_session, app):
        non_existent = Path("/non/existent/path/docs")
        with patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = non_existent
            resp = docs_client.get("/admin/docs/user-guides/intro")
        assert resp.status_code == 404

    def test_view_doc_valid_path_renders(self, docs_client, db_session, app, temp_docs_dir):
        root = Path(temp_docs_dir)
        intro_path = root / "user-guides" / "intro.md"
        with patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = root
            mock_docs.resolve_doc_path.return_value = (intro_path, "user-guides/intro")
            mock_docs.ensure_doc_page_access.return_value = None
            mock_docs.build_hierarchical_nav.return_value = []
            mock_docs.render_markdown_file.return_value = "<p>Introduction page.</p>"
            mock_docs.extract_page_title.return_value = "Intro"
            mock_docs.get_workflow_id_for_doc.return_value = None
            resp = docs_client.get("/admin/docs/user-guides/intro")
        assert resp.status_code == 200

    def test_view_doc_unauthenticated_redirects(self, client, db_session, app):
        resp = client.get("/admin/docs/user-guides/intro")
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# asset route
# ---------------------------------------------------------------------------

class TestDocAsset:
    def test_asset_root_missing_returns_404(self, docs_client, db_session, app):
        non_existent = Path("/non/existent/docs")
        with patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = non_existent
            resp = docs_client.get("/admin/docs/assets/screenshot.png")
        assert resp.status_code == 404

    def test_asset_path_traversal_returns_404(self, docs_client, db_session, app, temp_docs_dir):
        """Path traversal attempts should be rejected."""
        root = Path(temp_docs_dir)
        with patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = root
            # Requesting ../../etc/passwd style
            resp = docs_client.get("/admin/docs/assets/../../../etc/passwd")
        assert resp.status_code == 404

    def test_asset_nonexistent_file_returns_404(self, docs_client, db_session, app, temp_docs_dir):
        root = Path(temp_docs_dir)
        with patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = root
            mock_docs.ensure_docs_asset_access.return_value = None
            resp = docs_client.get("/admin/docs/assets/no_such_file.png")
        assert resp.status_code == 404

    def test_asset_valid_file_served(self, docs_client, db_session, app, temp_docs_dir):
        root = Path(temp_docs_dir)
        with patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = root
            mock_docs.ensure_docs_asset_access.return_value = None
            # The PNG file we wrote to the temp dir
            resp = docs_client.get("/admin/docs/assets/user-guides/screenshot.png")
        assert resp.status_code == 200

    def test_asset_unauthenticated_redirects(self, client, db_session, app):
        resp = client.get("/admin/docs/assets/screenshot.png")
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# _canonical_doc_path_for_url (internal helper – unit tested directly)
# ---------------------------------------------------------------------------

class TestCanonicalDocPathForUrl:
    def test_empty_string_returns_empty(self, app):
        from app.routes.admin.documentation import _canonical_doc_path_for_url
        with app.app_context():
            assert _canonical_doc_path_for_url("") == ""

    def test_none_returns_empty(self, app):
        from app.routes.admin.documentation import _canonical_doc_path_for_url
        with app.app_context():
            assert _canonical_doc_path_for_url(None) == ""

    def test_readme_returns_empty(self, app):
        from app.routes.admin.documentation import _canonical_doc_path_for_url
        with app.app_context():
            assert _canonical_doc_path_for_url("README") == ""
            assert _canonical_doc_path_for_url("readme") == ""
            assert _canonical_doc_path_for_url("README.md") == ""
            assert _canonical_doc_path_for_url("readme.md") == ""

    def test_strips_md_extension(self, app):
        from app.routes.admin.documentation import _canonical_doc_path_for_url
        with app.app_context():
            result = _canonical_doc_path_for_url("user-guides/add-user.md")
            assert result == "user-guides/add-user"

    def test_normalises_backslash(self, app):
        from app.routes.admin.documentation import _canonical_doc_path_for_url
        with app.app_context():
            result = _canonical_doc_path_for_url("user-guides\\add-user.md")
            assert result == "user-guides/add-user"

    def test_strips_leading_slash(self, app):
        from app.routes.admin.documentation import _canonical_doc_path_for_url
        with app.app_context():
            result = _canonical_doc_path_for_url("/user-guides/intro")
            assert result == "user-guides/intro"

    def test_locale_variant_keeps_locale(self, app):
        from app.routes.admin.documentation import _canonical_doc_path_for_url
        with app.app_context():
            result = _canonical_doc_path_for_url("user-guides/add-user.fr.md")
            assert result == "user-guides/add-user.fr"

    def test_no_extension_returned_as_is(self, app):
        from app.routes.admin.documentation import _canonical_doc_path_for_url
        with app.app_context():
            result = _canonical_doc_path_for_url("user-guides/intro")
            assert result == "user-guides/intro"
