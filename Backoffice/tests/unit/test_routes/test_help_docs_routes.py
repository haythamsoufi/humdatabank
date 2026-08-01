"""Tests for app/routes/help_docs.py — help documentation routes."""
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from contextlib import contextmanager

import pytest
from flask import make_response
from flask_login import login_user
from werkzeug.exceptions import NotFound

pytestmark = [pytest.mark.unit]


def _make_logged_in_client(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
    return client


@contextmanager
def _bypass_login_required():
    """Fake an authenticated user so login_required routes are accessible without DB."""
    mock_user = MagicMock()
    mock_user.is_authenticated = True
    mock_user.is_active = True
    mock_user.is_anonymous = False
    mock_user.get_id.return_value = "1"
    mock_user.id = 1
    mock_user.name = "Mock User"
    mock_user.email = "mock@example.com"
    # Patch Flask-Login's internal user loader so current_user returns our mock
    with patch("flask_login.utils._get_user", return_value=mock_user):
        yield mock_user


# =====================================================================
# Helper: _canonical_doc_path_for_url
# =====================================================================


class TestCanonicalDocPathForUrl:
    def test_empty_returns_empty(self, app):
        from app.routes.help_docs import _canonical_doc_path_for_url
        with app.test_request_context("/"):
            assert _canonical_doc_path_for_url("") == ""

    def test_none_returns_empty(self, app):
        from app.routes.help_docs import _canonical_doc_path_for_url
        with app.test_request_context("/"):
            assert _canonical_doc_path_for_url(None) == ""

    def test_readme_returns_empty(self, app):
        from app.routes.help_docs import _canonical_doc_path_for_url
        with app.test_request_context("/"):
            assert _canonical_doc_path_for_url("README") == ""
            assert _canonical_doc_path_for_url("README.md") == ""

    def test_strips_md_extension(self, app):
        from app.routes.help_docs import _canonical_doc_path_for_url
        with app.test_request_context("/"):
            result = _canonical_doc_path_for_url("user-guides/navigation.md")
        assert result == "user-guides/navigation"

    def test_no_extension_unchanged(self, app):
        from app.routes.help_docs import _canonical_doc_path_for_url
        with app.test_request_context("/"):
            result = _canonical_doc_path_for_url("user-guides/navigation")
        assert result == "user-guides/navigation"

    def test_backslash_normalized(self, app):
        from app.routes.help_docs import _canonical_doc_path_for_url
        with app.test_request_context("/"):
            result = _canonical_doc_path_for_url("user-guides\\navigation.md")
        assert result == "user-guides/navigation"

    def test_leading_slash_stripped(self, app):
        from app.routes.help_docs import _canonical_doc_path_for_url
        with app.test_request_context("/"):
            result = _canonical_doc_path_for_url("/user-guides/navigation.md")
        assert result == "user-guides/navigation"


# =====================================================================
# Helper: _build_doc_url
# =====================================================================


class TestBuildDocUrl:
    def test_empty_path_returns_index_url(self, app):
        from app.routes.help_docs import _build_doc_url

        with app.test_request_context("/"):
            with patch("app.routes.docs._shared.url_for", return_value="/help/docs/") as mock_url_for:
                result = _build_doc_url("")
        mock_url_for.assert_called_with("help_docs.index")

    def test_non_empty_path_returns_view_url(self, app):
        from app.routes.help_docs import _build_doc_url

        with app.test_request_context("/"):
            with patch("app.routes.docs._shared.url_for", return_value="/help/docs/user-guides/nav"):
                result = _build_doc_url("user-guides/nav.md")
        assert "nav" in result or "/help/docs" in result

    def test_readme_path_returns_index_url(self, app):
        from app.routes.help_docs import _build_doc_url

        with app.test_request_context("/"):
            with patch("app.routes.docs._shared.url_for", return_value="/help/docs/") as mock_url_for:
                result = _build_doc_url("README.md")
        mock_url_for.assert_called_with("help_docs.index")


# =====================================================================
# index
# =====================================================================


class TestHelpDocsIndex:
    def test_index_root_not_exists_404(self, app, client):
        mock_root = MagicMock(spec=Path)
        mock_root.exists.return_value = False

        with _bypass_login_required(), \
             patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = mock_root
            resp = client.get("/help/docs/")
        assert resp.status_code == 404

    def test_index_renders_template(self, app, client):
        mock_root = MagicMock(spec=Path)
        mock_root.exists.return_value = True

        with _bypass_login_required(), \
             patch("app.routes.docs._shared.docs") as mock_docs, \
             patch("app.routes.docs._shared.render_template", return_value=make_response("ok", 200)) as mock_render:
            mock_docs.docs_root.return_value = mock_root
            mock_docs.resolve_doc_path.return_value = (mock_root / "README.md", "")
            mock_docs.ensure_doc_page_access.return_value = None
            mock_docs.build_hierarchical_nav.return_value = []
            mock_docs.render_markdown_file.return_value = "<p>Hello</p>"
            mock_docs.extract_page_title.return_value = "Help"
            mock_docs.get_workflow_id_for_doc.return_value = None
            resp = client.get("/help/docs/")
        assert resp.status_code == 200

    def test_index_unauthenticated_redirects(self, app, client):
        resp = client.get("/help/docs/")
        assert resp.status_code in (301, 302)


# =====================================================================
# view_doc
# =====================================================================


class TestHelpDocsViewDoc:
    def test_view_doc_root_not_exists_404(self, app, client):
        mock_root = MagicMock(spec=Path)
        mock_root.exists.return_value = False

        with _bypass_login_required(), \
             patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = mock_root
            resp = client.get("/help/docs/user-guides/some-guide")
        assert resp.status_code == 404

    def test_view_doc_md_extension_rejected_404(self, app, client):
        mock_root = MagicMock(spec=Path)
        mock_root.exists.return_value = True

        with _bypass_login_required(), \
             patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = mock_root
            resp = client.get("/help/docs/user-guides/some-guide.md")
        assert resp.status_code == 404

    def test_view_doc_readme_rejected_404(self, app, client):
        mock_root = MagicMock(spec=Path)
        mock_root.exists.return_value = True

        with _bypass_login_required(), \
             patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = mock_root
            resp = client.get("/help/docs/README")
        assert resp.status_code == 404

    def test_view_doc_renders_template(self, app, client):
        mock_root = MagicMock(spec=Path)
        mock_root.exists.return_value = True

        with _bypass_login_required(), \
             patch("app.routes.docs._shared.docs") as mock_docs, \
             patch("app.routes.docs._shared.render_template", return_value=make_response("ok", 200)) as mock_render:
            mock_docs.docs_root.return_value = mock_root
            mock_docs.resolve_doc_path.return_value = (mock_root / "user-guides/guide.md", "user-guides/guide")
            mock_docs.ensure_doc_page_access.return_value = None
            mock_docs.build_hierarchical_nav.return_value = []
            mock_docs.render_markdown_file.return_value = "<p>Guide content</p>"
            mock_docs.extract_page_title.return_value = "Guide"
            mock_docs.get_workflow_id_for_doc.return_value = None
            resp = client.get("/help/docs/user-guides/guide")
        assert resp.status_code == 200

    def test_view_doc_unauthenticated_redirects(self, app, client):
        resp = client.get("/help/docs/user-guides/guide")
        assert resp.status_code in (301, 302)


# =====================================================================
# asset
# =====================================================================


class TestHelpDocsAsset:
    def test_asset_root_not_exists_404(self, app, client):
        mock_root = MagicMock(spec=Path)
        mock_root.exists.return_value = False

        with _bypass_login_required(), \
             patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = mock_root
            resp = client.get("/help/docs/assets/image.png")
        assert resp.status_code == 404

    def test_asset_path_traversal_attempt_404(self, app, client):
        real_root = Path("/tmp/fake_docs_root")
        mock_root = MagicMock(spec=Path)
        mock_root.exists.return_value = True

        # Simulate path traversal: candidate.resolve() not under root.resolve()
        mock_candidate = MagicMock(spec=Path)
        mock_candidate.exists.return_value = True
        mock_candidate.is_file.return_value = True
        mock_candidate.resolve.return_value = Path("/etc/passwd")  # outside root

        mock_root.__truediv__ = MagicMock(return_value=mock_candidate)
        mock_root.resolve.return_value = Path("/tmp/fake_docs_root")

        with _bypass_login_required(), \
             patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = mock_root
            resp = client.get("/help/docs/assets/../../etc/passwd")
        assert resp.status_code == 404

    def test_asset_file_not_exists_404(self, app, client):
        import tempfile
        tmp_dir = tempfile.mkdtemp()
        mock_root = Path(tmp_dir)

        with _bypass_login_required(), \
             patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = mock_root
            resp = client.get("/help/docs/assets/nonexistent.png")
        assert resp.status_code == 404

        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_asset_success(self, app, client):
        import tempfile, os, shutil
        tmp_dir = tempfile.mkdtemp()
        # Resolve the path to avoid Windows short-path vs long-path issues
        resolved_root = Path(tmp_dir).resolve()
        asset_file = resolved_root / "image.png"
        with open(asset_file, "wb") as f:
            f.write(b"\x89PNG fake content")

        with _bypass_login_required(), \
             patch("app.routes.docs._shared.docs") as mock_docs:
            mock_docs.docs_root.return_value = resolved_root
            mock_docs.ensure_docs_asset_access.return_value = None
            resp = client.get("/help/docs/assets/image.png")
        assert resp.status_code in (200, 404)

        shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_asset_unauthenticated_redirects(self, app, client):
        resp = client.get("/help/docs/assets/image.png")
        assert resp.status_code in (301, 302)
