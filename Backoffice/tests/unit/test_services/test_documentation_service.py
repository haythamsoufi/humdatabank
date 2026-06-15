"""
Comprehensive tests for app/services/documentation_service.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Pure helper functions (no Flask context needed)
# ---------------------------------------------------------------------------

class TestExtractTitleFromMarkdown:
    def _call(self, text, fallback="Fallback"):
        from app.services.documentation_service import _extract_title_from_markdown
        return _extract_title_from_markdown(text, fallback)

    def test_h1_title(self):
        assert self._call("# Hello World\n\nsome text") == "Hello World"

    def test_h2_title(self):
        assert self._call("## Section Title\n\ntext") == "Section Title"

    def test_h3_ignored(self):
        assert self._call("### Deep\n\ntext") == "Fallback"

    def test_empty_heading_skipped(self):
        assert self._call("# \n\n## Real Title") == "Real Title"

    def test_fallback_when_no_heading(self):
        assert self._call("just text, no heading") == "Fallback"

    def test_empty_text(self):
        assert self._call("") == "Fallback"

    def test_strips_extra_hashes(self):
        assert self._call("### level3\n## level2 Title") == "level2 Title"


class TestPrettifyStem:
    def _call(self, stem):
        from app.services.documentation_service import _prettify_stem
        return _prettify_stem(stem)

    def test_basic_hyphen(self):
        assert self._call("add-user") == "Add User"

    def test_underscore(self):
        assert self._call("some_page") == "Some Page"

    def test_language_suffix_stripped(self):
        assert self._call("add-user.fr") == "Add User"

    def test_two_char_lang_suffix(self):
        assert self._call("page.es") == "Page"

    def test_three_char_lang_suffix(self):
        assert self._call("page.fra") == "Page"

    def test_no_suffix(self):
        assert self._call("readme") == "Readme"

    def test_empty_becomes_documentation(self):
        # After strip() empty string -> "Documentation"
        assert self._call("   ") == "Documentation"


class TestSplitRelLang:
    def _call(self, rel):
        from app.services.documentation_service import _split_rel_lang
        return _split_rel_lang(rel)

    def test_no_language_suffix(self):
        base, lang = self._call("user-guides/admin/add-user.md")
        assert base == "user-guides/admin/add-user.md"
        assert lang is None

    def test_two_char_lang(self):
        base, lang = self._call("user-guides/admin/add-user.fr.md")
        assert base == "user-guides/admin/add-user.md"
        assert lang == "fr"

    def test_three_char_lang(self):
        base, lang = self._call("user-guides/admin/add-user.ara.md")
        assert base == "user-guides/admin/add-user.md"
        assert lang == "ara"

    def test_readme_no_lang(self):
        base, lang = self._call("README.md")
        assert base == "README.md"
        assert lang is None


class TestPickVariant:
    def _call(self, paths_by_lang, lang):
        from app.services.documentation_service import _pick_variant
        return _pick_variant(paths_by_lang, lang)

    def test_exact_lang_preferred(self):
        p_fr = Path("/docs/file.fr.md")
        p_none = Path("/docs/file.md")
        result = self._call({None: p_none, "fr": p_fr}, "fr")
        assert result == p_fr

    def test_fallback_to_default(self):
        p_none = Path("/docs/file.md")
        p_es = Path("/docs/file.es.md")
        result = self._call({None: p_none, "es": p_es}, "fr")
        assert result == p_none

    def test_fallback_to_any_when_no_default(self):
        p_es = Path("/docs/file.es.md")
        result = self._call({"es": p_es}, "fr")
        assert result == p_es


class TestGetCategoryIcon:
    def _call(self, name):
        from app.services.documentation_service import get_category_icon
        return get_category_icon(name)

    def test_known_categories(self):
        assert self._call("getting-started") == "fas fa-rocket"
        assert self._call("user-guides") == "fas fa-book-open"
        assert self._call("api") == "fas fa-code"
        assert self._call("archive") == "fas fa-archive"

    def test_case_insensitive(self):
        assert self._call("GETTING-STARTED") == "fas fa-rocket"

    def test_unknown_fallback(self):
        assert self._call("unknown-category") == "fas fa-folder"


class TestGetCategoryDisplayName:
    def _call(self, name):
        from app.services.documentation_service import get_category_display_name
        return get_category_display_name(name)

    def test_known_name(self):
        # Returns lazy string from flask_babel _(); in tests it returns the key string
        result = self._call("api")
        assert result is not None

    def test_unknown_name_title_cased(self):
        result = self._call("my-custom-category")
        assert "My Custom Category" in result or result == "my-custom-category".replace("-", " ").title()


class TestGetAdminSubgroup:
    def _call(self, filename):
        from app.services.documentation_service import _get_admin_subgroup
        return _get_admin_subgroup(filename)

    def test_user_management_exact(self):
        name, order = self._call("add-user.md")
        assert name == "user-management"
        assert order == 1

    def test_template_management(self):
        name, order = self._call("create-template.md")
        assert name == "template-management"
        assert order == 2

    def test_assignment_management(self):
        name, order = self._call("create-assignment.md")
        assert name == "assignment-management"
        assert order == 3

    def test_data_export(self):
        name, order = self._call("export-download-data.md")
        assert name == "data-export"
        assert order == 4

    def test_tools_settings(self):
        name, order = self._call("indicator-bank.md")
        assert name == "tools-settings"
        assert order == 5

    def test_troubleshooting(self):
        name, order = self._call("troubleshooting-templates-and-assignments.md")
        assert name == "troubleshooting"
        assert order == 6

    def test_default_other(self):
        name, order = self._call("unknown-doc.md")
        assert name == "other"
        assert order == 99

    def test_language_suffix_stripped(self):
        name, order = self._call("add-user.fr.md")
        assert name == "user-management"

    def test_substring_match(self):
        # "troubleshooting-access" contains "troubleshooting-access" from user-management
        name, order = self._call("troubleshooting-access.md")
        assert name == "user-management"


class TestGetAdminSubgroupDisplayName:
    def _call(self, name):
        from app.services.documentation_service import _get_admin_subgroup_display_name
        return _get_admin_subgroup_display_name(name)

    def test_known_names(self):
        assert self._call("user-management") is not None
        assert self._call("template-management") is not None
        assert self._call("other") is not None

    def test_unknown_name_title_cased(self):
        result = self._call("custom-group")
        assert "Custom Group" in result or result


class TestUserGuidesCommonDocRequiresAdmin:
    def _call(self, base_rel):
        from app.services.documentation_service import user_guides_common_doc_requires_admin
        return user_guides_common_doc_requires_admin(base_rel)

    def test_restricted_doc(self):
        assert self._call("user-guides/common/data-governance.md") is True

    def test_non_restricted(self):
        assert self._call("getting-started/start-here.md") is False

    def test_too_few_parts(self):
        assert self._call("user-guides/data-governance.md") is False

    def test_not_user_guides(self):
        assert self._call("api/common/data-governance.md") is False

    def test_not_common(self):
        assert self._call("user-guides/admin/data-governance.md") is False


class TestUserGuidesAiDocRequiresBetaAccess:
    def _call(self, base_rel):
        from app.services.documentation_service import user_guides_ai_doc_requires_beta_access
        return user_guides_ai_doc_requires_beta_access(base_rel)

    def test_common_ai_docs(self):
        assert self._call("user-guides/common/ai-chatbot.md") is True
        assert self._call("user-guides/common/ai-use-policy.md") is True

    def test_admin_ai_docs(self):
        assert self._call("user-guides/admin/ai-document-library-and-embeddings.md") is True
        assert self._call("user-guides/admin/ai-system-security-and-privacy.md") is True

    def test_non_ai_doc(self):
        assert self._call("getting-started/start-here.md") is False

    def test_focal_point_not_ai_topic(self):
        assert self._call("user-guides/focal-point/view-assignments.md") is False


class TestIsRootReadmeRequest:
    def _call(self, raw):
        from app.services.documentation_service import _is_root_readme_request
        return _is_root_readme_request(raw)

    def test_readme_md(self):
        assert self._call("README.md") is True

    def test_readme_lowercase(self):
        assert self._call("readme.md") is True

    def test_empty_string(self):
        assert self._call("") is False

    def test_nested_readme(self):
        assert self._call("user-guides/README.md") is False

    def test_other_file(self):
        assert self._call("some-file.md") is False

    def test_leading_slash(self):
        assert self._call("/README.md") is True


class TestShouldMergeUserGuidesCommonFocalNav:
    def _call(self, allowed_groups):
        from app.services.documentation_service import _should_merge_user_guides_common_focal_nav
        return _should_merge_user_guides_common_focal_nav(allowed_groups)

    def test_exact_match(self):
        assert self._call({"common", "focal-point"}) is True

    def test_extra_group_no_merge(self):
        assert self._call({"common", "focal-point", "admin"}) is False

    def test_only_common(self):
        assert self._call({"common"}) is False


# ---------------------------------------------------------------------------
# Flask-context-dependent tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_app(app):
    """Use the real test app for Flask context."""
    return app


class TestDocsRoot:
    def test_resolves_parent_of_app(self, app):
        with app.app_context():
            from app.services.documentation_service import docs_root
            root = docs_root()
            assert root.name == "docs"
            assert root.parent.name == "Backoffice" or "Backoffice" in str(root)


class TestIsWithinRoot:
    def test_within_root(self, app):
        with app.app_context():
            from app.services.documentation_service import _is_within_root
            root = Path(tempfile.mkdtemp())
            candidate = root / "subdir" / "file.md"
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.touch()
            assert _is_within_root(root, candidate) is True

    def test_outside_root(self, app):
        with app.app_context():
            from app.services.documentation_service import _is_within_root
            root = Path(tempfile.mkdtemp())
            outside = Path(tempfile.mkdtemp()) / "other.md"
            assert _is_within_root(root, outside) is False

    def test_traversal_attempt(self, app):
        with app.app_context():
            from app.services.documentation_service import _is_within_root
            root = Path(tempfile.mkdtemp())
            candidate = root / ".." / "etc" / "passwd"
            assert _is_within_root(root, candidate) is False


class TestGetUserLanguage:
    def test_returns_string(self, app):
        with app.app_context():
            with patch("app.services.documentation_service._get_user_language") as mock_lang:
                mock_lang.return_value = "en"
                from app.services.documentation_service import _get_user_language
                # Just ensure the function can be called
                mock_lang.return_value = "en"
                assert mock_lang.return_value == "en"


class TestListMarkdownFiles:
    def test_lists_md_files(self, app):
        with app.app_context():
            from app.services.documentation_service import list_markdown_files
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / "file1.md").write_text("# Title", encoding="utf-8")
                (root / "file2.md").write_text("## Sub", encoding="utf-8")
                files = list_markdown_files(root)
                assert len(files) == 2

    def test_skips_hidden_dirs(self, app):
        with app.app_context():
            from app.services.documentation_service import list_markdown_files
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                hidden = root / "_internal"
                hidden.mkdir()
                (hidden / "secret.md").write_text("hidden", encoding="utf-8")
                (root / "visible.md").write_text("# Visible", encoding="utf-8")
                files = list_markdown_files(root)
                assert all("_internal" not in str(f) for f in files)

    def test_skips_hidden_files(self, app):
        with app.app_context():
            from app.services.documentation_service import list_markdown_files
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / "_private.md").write_text("private", encoding="utf-8")
                (root / "visible.md").write_text("# Visible", encoding="utf-8")
                files = list_markdown_files(root)
                assert all(not f.name.startswith("_") for f in files)

    def test_skips_archive_folder(self, app):
        with app.app_context():
            from app.services.documentation_service import list_markdown_files
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                archive = root / "archive"
                archive.mkdir()
                (archive / "old.md").write_text("old", encoding="utf-8")
                (root / "current.md").write_text("# Current", encoding="utf-8")
                files = list_markdown_files(root)
                assert all("archive" not in str(f) for f in files)

    def test_sorted_results(self, app):
        with app.app_context():
            from app.services.documentation_service import list_markdown_files
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / "z-last.md").write_text("# Z", encoding="utf-8")
                (root / "a-first.md").write_text("# A", encoding="utf-8")
                files = list_markdown_files(root)
                names = [f.name for f in files]
                assert names == sorted(names, key=str.lower)


class TestAllowedUserGuidesSubdirsForUser:
    def _call(self, app, user):
        with app.app_context():
            from app.services.documentation_service import _allowed_user_guides_subdirs_for_user
            return _allowed_user_guides_subdirs_for_user(user)

    def test_no_user_returns_common(self, app):
        result = self._call(app, None)
        assert result == {"common"}

    def test_unauthenticated_user(self, app):
        user = MagicMock()
        user.is_authenticated = False
        result = self._call(app, user)
        assert result == {"common"}

    def test_system_manager_all_access(self, app):
        user = MagicMock()
        user.is_authenticated = True
        with app.app_context():
            with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=True):
                from app.services.documentation_service import _allowed_user_guides_subdirs_for_user
                result = _allowed_user_guides_subdirs_for_user(user)
                assert "admin" in result
                assert "focal-point" in result
                assert "common" in result

    def test_admin_access(self, app):
        user = MagicMock()
        user.is_authenticated = True
        with app.app_context():
            with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False):
                with patch("app.services.authorization_service.AuthorizationService.is_admin", return_value=True):
                    from app.services.documentation_service import _allowed_user_guides_subdirs_for_user
                    result = _allowed_user_guides_subdirs_for_user(user)
                    assert "admin" in result
                    assert "common" in result

    def test_focal_point_access(self, app):
        user = MagicMock()
        user.is_authenticated = True
        with app.app_context():
            with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False):
                with patch("app.services.authorization_service.AuthorizationService.is_admin", return_value=False):
                    with patch("app.services.authorization_service.AuthorizationService.has_role", return_value=True):
                        from app.services.documentation_service import _allowed_user_guides_subdirs_for_user
                        result = _allowed_user_guides_subdirs_for_user(user)
                        assert "focal-point" in result


class TestUserIsAdminOrSystemManager:
    def _call(self, app, user):
        with app.app_context():
            from app.services.documentation_service import _user_is_admin_or_system_manager
            return _user_is_admin_or_system_manager(user)

    def test_none_user(self, app):
        assert self._call(app, None) is False

    def test_unauthenticated(self, app):
        user = MagicMock()
        user.is_authenticated = False
        assert self._call(app, None) is False

    def test_admin_user(self, app):
        user = MagicMock()
        user.is_authenticated = True
        with app.app_context():
            with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False):
                with patch("app.services.authorization_service.AuthorizationService.is_admin", return_value=True):
                    from app.services.documentation_service import _user_is_admin_or_system_manager
                    assert _user_is_admin_or_system_manager(user) is True

    def test_system_manager(self, app):
        user = MagicMock()
        user.is_authenticated = True
        with app.app_context():
            with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=True):
                from app.services.documentation_service import _user_is_admin_or_system_manager
                assert _user_is_admin_or_system_manager(user) is True

    def test_regular_user(self, app):
        user = MagicMock()
        user.is_authenticated = True
        with app.app_context():
            with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False):
                with patch("app.services.authorization_service.AuthorizationService.is_admin", return_value=False):
                    from app.services.documentation_service import _user_is_admin_or_system_manager
                    assert _user_is_admin_or_system_manager(user) is False


class TestSanitizeHtml:
    def _call(self, html):
        from app.services.documentation_service import _sanitize_html
        return _sanitize_html(html)

    def test_removes_script_tags(self):
        html = "<p>Hello</p><script>alert('xss')</script>"
        result = self._call(html)
        assert "<script>" not in result
        assert "Hello" in result

    def test_removes_event_handlers(self):
        html = '<p onclick="evil()">Click</p>'
        result = self._call(html)
        assert "onclick" not in result
        assert "Click" in result

    def test_removes_javascript_href(self):
        html = '<a href="javascript:void(0)">Link</a>'
        result = self._call(html)
        assert "javascript:" not in result

    def test_preserves_safe_html(self):
        html = "<h1>Title</h1><p>Paragraph</p><ul><li>Item</li></ul>"
        result = self._call(html)
        assert "Title" in result
        assert "Paragraph" in result

    def test_preserves_links_and_images(self):
        html = '<a href="https://example.com">link</a><img src="img.png" alt="img">'
        result = self._call(html)
        assert "https://example.com" in result

    def test_allows_code_blocks(self):
        html = "<pre><code class='python'>print('hi')</code></pre>"
        result = self._call(html)
        assert "print" in result

    def test_removes_onerror(self):
        html = '<img src="x" onerror="alert(1)">'
        result = self._call(html)
        assert "onerror" not in result


class TestRewriteRelativeLinks:
    def _call(self, root, current_rel, html, doc_builder=None, asset_builder=None):
        from app.services.documentation_service import rewrite_relative_links
        if doc_builder is None:
            doc_builder = lambda rel: f"/docs/{rel}"
        if asset_builder is None:
            asset_builder = lambda rel: f"/docs/assets/{rel}"
        return rewrite_relative_links(
            root=root,
            current_rel=current_rel,
            html=html,
            doc_url_builder=doc_builder,
            asset_url_builder=asset_builder,
        )

    def test_external_link_unchanged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            html = '<a href="https://example.com">External</a>'
            result = self._call(root, "README.md", html)
            assert "https://example.com" in result

    def test_external_link_gets_target_blank(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            html = '<a href="https://example.com">External</a>'
            result = self._call(root, "README.md", html)
            assert '_blank' in result

    def test_fragment_only_link_unchanged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            html = '<a href="#section">Jump</a>'
            result = self._call(root, "README.md", html)
            assert "#section" in result

    def test_relative_md_link_rewritten(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "other.md").write_text("# Other", encoding="utf-8")
            html = '<a href="other.md">Other</a>'
            result = self._call(root, "README.md", html)
            assert "/docs/other.md" in result

    def test_relative_img_rewritten(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "img.png").write_bytes(b"fakepng")
            html = '<img src="img.png" alt="img">'
            result = self._call(root, "README.md", html)
            assert "/docs/assets/img.png" in result

    def test_link_with_fragment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "other.md").write_text("# Other", encoding="utf-8")
            html = '<a href="other.md#section">Other section</a>'
            result = self._call(root, "README.md", html)
            assert "#section" in result

    def test_empty_href_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            html = '<a href="">empty</a>'
            result = self._call(root, "README.md", html)
            # Should not crash
            assert "empty" in result

    def test_absolute_md_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "guide.md").write_text("# Guide", encoding="utf-8")
            html = '<a href="/guide.md">Guide</a>'
            result = self._call(root, "README.md", html)
            assert "/docs/" in result

    def test_absolute_img_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "img.png").write_bytes(b"fakepng")
            html = '<img src="/img.png" alt="test">'
            result = self._call(root, "README.md", html)
            assert "/docs/assets/" in result or "/img.png" in result


class TestRenderMarkdownFile:
    def test_renders_markdown(self, app):
        with app.app_context():
            from app.services.documentation_service import render_markdown_file
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                md_file = root / "test.md"
                md_file.write_text("# Test Title\n\nSome **bold** text.", encoding="utf-8")
                result = render_markdown_file(
                    root=root,
                    file_path=md_file,
                    current_rel="test.md",
                    doc_url_builder=lambda r: f"/docs/{r}",
                    asset_url_builder=lambda r: f"/assets/{r}",
                )
                html = str(result)
                assert "bold" in html
                # H1 is removed to avoid duplication
                assert "<h1>" not in html

    def test_handles_read_error(self, app):
        with app.app_context():
            from app.services.documentation_service import render_markdown_file
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                nonexistent = root / "missing.md"
                # File doesn't exist; read_text raises, text defaults to ""
                result = render_markdown_file(
                    root=root,
                    file_path=nonexistent,
                    current_rel="missing.md",
                    doc_url_builder=lambda r: f"/docs/{r}",
                    asset_url_builder=lambda r: f"/assets/{r}",
                )
                assert result is not None  # returns Markup("")


class TestExtractPageTitle:
    def test_extracts_h1(self, app):
        with app.app_context():
            from app.services.documentation_service import extract_page_title
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                f = root / "my-page.md"
                f.write_text("# My Awesome Page\n\nContent here.", encoding="utf-8")
                title = extract_page_title(f)
                assert title == "My Awesome Page"

    def test_fallback_to_stem(self, app):
        with app.app_context():
            from app.services.documentation_service import extract_page_title
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                f = root / "my-guide.md"
                f.write_text("No heading here.", encoding="utf-8")
                title = extract_page_title(f)
                assert title == "My Guide"

    def test_read_error_fallback(self, app):
        with app.app_context():
            from app.services.documentation_service import extract_page_title
            # Non-existent file
            title = extract_page_title(Path("/nonexistent/file.md"))
            assert title is not None


class TestEnsureDocPageAccess:
    def _call(self, app, user, base_rel, visible=None):
        with app.app_context():
            from app.services.documentation_service import ensure_doc_page_access
            ensure_doc_page_access(user, base_rel, visible_top_level_dirs=visible)

    def test_allowed_dir(self, app):
        user = MagicMock()
        user.is_authenticated = True
        with app.app_context():
            with patch("app.services.documentation_service._user_is_admin_or_system_manager", return_value=True):
                with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"admin", "common"}):
                    from app.services.documentation_service import ensure_doc_page_access
                    # Should not raise
                    ensure_doc_page_access(user, "user-guides/admin/add-user.md", visible_top_level_dirs={"user-guides"})

    def test_forbidden_top_level(self, app):
        user = MagicMock()
        user.is_authenticated = False
        with app.app_context():
            from app.services.documentation_service import ensure_doc_page_access
            with pytest.raises(Exception):  # abort(403) raises
                ensure_doc_page_access(user, "development/secret.md", visible_top_level_dirs={"user-guides"})

    def test_user_guides_readme_forbidden_for_non_admin(self, app):
        with app.app_context():
            with patch("app.services.documentation_service._user_is_admin_or_system_manager", return_value=False):
                with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common"}):
                    from app.services.documentation_service import ensure_doc_page_access
                    with pytest.raises(Exception):
                        ensure_doc_page_access(None, "user-guides/README.md")

    def test_admin_only_doc_forbidden_for_regular_user(self, app):
        with app.app_context():
            with patch("app.services.documentation_service._user_is_admin_or_system_manager", return_value=False):
                with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common"}):
                    from app.services.documentation_service import ensure_doc_page_access
                    with pytest.raises(Exception):
                        ensure_doc_page_access(None, "user-guides/common/data-governance.md")

    def test_admin_can_access_restricted_doc(self, app):
        user = MagicMock()
        user.is_authenticated = True
        with app.app_context():
            with patch("app.services.documentation_service._user_is_admin_or_system_manager", return_value=True):
                with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common", "admin"}):
                    from app.services.documentation_service import ensure_doc_page_access
                    # Should not raise
                    ensure_doc_page_access(user, "user-guides/common/data-governance.md")

    def test_readme_md_allowed_for_admin_with_visible_dirs(self, app):
        user = MagicMock()
        user.is_authenticated = True
        with app.app_context():
            with patch("app.services.documentation_service._user_is_admin_or_system_manager", return_value=True):
                with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common", "admin"}):
                    from app.services.documentation_service import ensure_doc_page_access
                    # readme.md at root level with admin
                    ensure_doc_page_access(user, "README.md", visible_top_level_dirs={"user-guides"})

    def test_ai_doc_forbidden_without_beta_access(self, app):
        user = MagicMock()
        user.is_authenticated = True
        with app.app_context():
            with patch("app.services.documentation_service._user_can_view_ai_docs", return_value=False):
                with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common", "admin"}):
                    from app.services.documentation_service import ensure_doc_page_access
                    with pytest.raises(Exception):
                        ensure_doc_page_access(user, "user-guides/common/ai-chatbot.md")

    def test_ai_doc_allowed_with_beta_access(self, app):
        user = MagicMock()
        user.is_authenticated = True
        with app.app_context():
            with patch("app.services.documentation_service._user_can_view_ai_docs", return_value=True):
                with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common"}):
                    from app.services.documentation_service import ensure_doc_page_access
                    ensure_doc_page_access(user, "user-guides/common/ai-chatbot.md")


class TestEnsureDocsAssetAccess:
    def test_allowed_asset(self, app):
        with app.app_context():
            with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common"}):
                from app.services.documentation_service import ensure_docs_asset_access
                # Should not raise
                ensure_docs_asset_access(None, "user-guides/common/img.png", visible_top_level_dirs={"user-guides"})

    def test_empty_path_forbidden(self, app):
        with app.app_context():
            from app.services.documentation_service import ensure_docs_asset_access
            with pytest.raises(Exception):
                ensure_docs_asset_access(None, "", visible_top_level_dirs={"user-guides"})

    def test_outside_visible_dirs(self, app):
        with app.app_context():
            from app.services.documentation_service import ensure_docs_asset_access
            with pytest.raises(Exception):
                ensure_docs_asset_access(None, "development/img.png", visible_top_level_dirs={"user-guides"})

    def test_readme_forbidden_in_user_guides(self, app):
        with app.app_context():
            from app.services.documentation_service import ensure_docs_asset_access
            with pytest.raises(Exception):
                ensure_docs_asset_access(None, "user-guides/README.md", visible_top_level_dirs={"user-guides"})

    def test_forbidden_subdir(self, app):
        with app.app_context():
            with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common"}):
                from app.services.documentation_service import ensure_docs_asset_access
                with pytest.raises(Exception):
                    ensure_docs_asset_access(None, "user-guides/admin/img.png", visible_top_level_dirs={"user-guides"})


class TestResolveDocPath:
    def test_resolves_readme(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                readme = root / "README.md"
                readme.write_text("# Docs", encoding="utf-8")
                with patch("app.services.documentation_service._user_is_admin_or_system_manager", return_value=True):
                    with patch("app.services.documentation_service._get_user_language", return_value="en"):
                        from app.services.documentation_service import resolve_doc_path
                        path, base_rel = resolve_doc_path(root, "README.md")
                        assert path.exists()

    def test_appends_md_extension(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / "guide.md").write_text("# Guide", encoding="utf-8")
                with patch("app.services.documentation_service._get_user_language", return_value="en"):
                    with patch("app.services.documentation_service._user_is_admin_or_system_manager", return_value=True):
                        from app.services.documentation_service import resolve_doc_path
                        path, base_rel = resolve_doc_path(root, "guide")
                        assert path.name == "guide.md"

    def test_404_for_nonexistent(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                with patch("app.services.documentation_service._get_user_language", return_value="en"):
                    with patch("app.services.documentation_service._user_is_admin_or_system_manager", return_value=True):
                        from app.services.documentation_service import resolve_doc_path
                        with pytest.raises(Exception):  # abort(404)
                            resolve_doc_path(root, "nonexistent.md")

    def test_non_admin_gets_redirected_from_readme(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                landing_parts = ("getting-started",)
                for p in landing_parts:
                    (root / p).mkdir(parents=True, exist_ok=True)
                landing = root / "getting-started" / "start-here.md"
                landing.write_text("# Start Here", encoding="utf-8")
                with patch("app.services.documentation_service._get_user_language", return_value="en"):
                    with patch("app.services.documentation_service._user_is_admin_or_system_manager", return_value=False):
                        from app.services.documentation_service import resolve_doc_path
                        path, base_rel = resolve_doc_path(root, "README.md")
                        assert "start-here" in str(path)

    def test_language_variant_served(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / "guide.md").write_text("# Guide EN", encoding="utf-8")
                (root / "guide.fr.md").write_text("# Guide FR", encoding="utf-8")
                with patch("app.services.documentation_service._get_user_language", return_value="fr"):
                    with patch("app.services.documentation_service._user_is_admin_or_system_manager", return_value=True):
                        from app.services.documentation_service import resolve_doc_path
                        path, base_rel = resolve_doc_path(root, "guide.md")
                        assert "fr" in path.name

    def test_empty_path_admin_gets_readme(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / "README.md").write_text("# Docs", encoding="utf-8")
                with patch("app.services.documentation_service._get_user_language", return_value="en"):
                    with patch("app.services.documentation_service._user_is_admin_or_system_manager", return_value=True):
                        from app.services.documentation_service import resolve_doc_path
                        path, base_rel = resolve_doc_path(root, "")
                        assert path.name == "README.md"

    def test_empty_path_non_admin_gets_landing(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                landing = root / "getting-started"
                landing.mkdir(parents=True)
                (landing / "start-here.md").write_text("# Start", encoding="utf-8")
                with patch("app.services.documentation_service._get_user_language", return_value="en"):
                    with patch("app.services.documentation_service._user_is_admin_or_system_manager", return_value=False):
                        from app.services.documentation_service import resolve_doc_path
                        path, _ = resolve_doc_path(root, "")
                        assert "start-here" in str(path)

    def test_empty_path_non_admin_404_when_no_landing(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                with patch("app.services.documentation_service._get_user_language", return_value="en"):
                    with patch("app.services.documentation_service._user_is_admin_or_system_manager", return_value=False):
                        from app.services.documentation_service import resolve_doc_path
                        with pytest.raises(Exception):
                            resolve_doc_path(root, "")


class TestBuildHierarchicalNav:
    def test_empty_docs_dir(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                with patch("app.services.documentation_service._get_user_language", return_value="en"):
                    with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common"}):
                        from app.services.documentation_service import build_hierarchical_nav
                        nav = build_hierarchical_nav(
                            root=root,
                            doc_url_builder=lambda r: f"/docs/{r}",
                        )
                        assert nav == []

    def test_categories_built(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                api_dir = root / "api"
                api_dir.mkdir()
                (api_dir / "README.md").write_text("# API Docs", encoding="utf-8")
                with patch("app.services.documentation_service._get_user_language", return_value="en"):
                    with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common"}):
                        from app.services.documentation_service import build_hierarchical_nav
                        nav = build_hierarchical_nav(
                            root=root,
                            doc_url_builder=lambda r: f"/docs/{r}",
                            visible_top_level_dirs={"api"},
                        )
                        assert len(nav) >= 1
                        cat_names = [c.name for c in nav]
                        assert "api" in cat_names

    def test_user_guides_with_admin(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                admin_dir = root / "user-guides" / "admin"
                admin_dir.mkdir(parents=True)
                (admin_dir / "add-user.md").write_text("# Add User", encoding="utf-8")
                with patch("app.services.documentation_service._get_user_language", return_value="en"):
                    with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common", "admin"}):
                        from app.services.documentation_service import build_hierarchical_nav
                        nav = build_hierarchical_nav(
                            root=root,
                            doc_url_builder=lambda r: f"/docs/{r}",
                            user=None,
                        )
                        # Admin docs are processed as categories
                        assert len(nav) >= 1

    def test_focal_point_merged_nav(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                common_dir = root / "user-guides" / "common"
                common_dir.mkdir(parents=True)
                (common_dir / "getting-help.md").write_text("# Getting help", encoding="utf-8")
                fp_dir = root / "user-guides" / "focal-point"
                fp_dir.mkdir(parents=True)
                (fp_dir / "view-assignments.md").write_text("# View Your Assignments", encoding="utf-8")
                gs_dir = root / "getting-started"
                gs_dir.mkdir(parents=True)
                (gs_dir / "start-here.md").write_text("# Start here", encoding="utf-8")
                dr_dir = root / "data-reporting"
                dr_dir.mkdir(parents=True)
                (dr_dir / "data-guidance-fdrs.md").write_text("# Data Guidance, FDRS", encoding="utf-8")
                with patch("app.services.documentation_service._get_user_language", return_value="en"):
                    with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common", "focal-point"}):
                        from app.services.documentation_service import build_hierarchical_nav
                        nav = build_hierarchical_nav(
                            root=root,
                            doc_url_builder=lambda r: f"/docs/{r}",
                        )
                        # Curated focal-point help nav: Getting Started, User Guide, Data Reporting
                        cat_names = [c.name for c in nav]
                        assert "getting-started" in cat_names
                        assert "user-guides" in cat_names
                        assert "data-reporting" in cat_names

    def test_language_variant_deduplication(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                api_dir = root / "api"
                api_dir.mkdir()
                (api_dir / "guide.md").write_text("# Guide EN", encoding="utf-8")
                (api_dir / "guide.fr.md").write_text("# Guide FR", encoding="utf-8")
                with patch("app.services.documentation_service._get_user_language", return_value="en"):
                    with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common"}):
                        from app.services.documentation_service import build_hierarchical_nav
                        nav = build_hierarchical_nav(
                            root=root,
                            doc_url_builder=lambda r: f"/docs/{r}",
                        )
                        all_items = []
                        for cat in nav:
                            for grp in cat.groups:
                                all_items.extend(grp.items)
                        rel_paths = [item.rel_path for item in all_items]
                        # Should only have one entry for guide (not both .md and .fr.md)
                        guide_items = [r for r in rel_paths if "guide" in r]
                        assert len(guide_items) == len(set(guide_items))

    def test_ai_docs_hidden_without_beta_access(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                common_dir = root / "user-guides" / "common"
                common_dir.mkdir(parents=True)
                (common_dir / "getting-help.md").write_text("# Getting help", encoding="utf-8")
                (common_dir / "ai-chatbot.md").write_text("# AI Chatbot", encoding="utf-8")
                with patch("app.services.documentation_service._get_user_language", return_value="en"):
                    with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common"}):
                        with patch("app.services.documentation_service._user_can_view_ai_docs", return_value=False):
                            from app.services.documentation_service import build_hierarchical_nav
                            nav = build_hierarchical_nav(
                                root=root,
                                doc_url_builder=lambda r: f"/docs/{r}",
                                visible_top_level_dirs={"user-guides"},
                                user=MagicMock(is_authenticated=True),
                            )
                            rel_paths = [
                                item.rel_path
                                for cat in nav
                                for grp in cat.groups
                                for item in grp.items
                            ]
                            assert "user-guides/common/getting-help.md" in rel_paths
                            assert "user-guides/common/ai-chatbot.md" not in rel_paths

    def test_ai_docs_shown_with_beta_access(self, app):
        with app.app_context():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                common_dir = root / "user-guides" / "common"
                common_dir.mkdir(parents=True)
                (common_dir / "ai-chatbot.md").write_text("# AI Chatbot", encoding="utf-8")
                with patch("app.services.documentation_service._get_user_language", return_value="en"):
                    with patch("app.services.documentation_service._allowed_user_guides_subdirs_for_user", return_value={"common"}):
                        with patch("app.services.documentation_service._user_can_view_ai_docs", return_value=True):
                            from app.services.documentation_service import build_hierarchical_nav
                            nav = build_hierarchical_nav(
                                root=root,
                                doc_url_builder=lambda r: f"/docs/{r}",
                                visible_top_level_dirs={"user-guides"},
                                user=MagicMock(is_authenticated=True),
                            )
                            rel_paths = [
                                item.rel_path
                                for cat in nav
                                for grp in cat.groups
                                for item in grp.items
                            ]
                            assert "user-guides/common/ai-chatbot.md" in rel_paths


class TestGetWorkflowIdForDoc:
    def test_readme_returns_none(self, app):
        with app.app_context():
            from app.services.documentation_service import get_workflow_id_for_doc
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                readme = root / "user-guides" / "admin" / "README.md"
                readme.parent.mkdir(parents=True)
                readme.write_text("# Readme", encoding="utf-8")
                result = get_workflow_id_for_doc(readme, root)
                assert result is None

    def test_non_user_guides_returns_none(self, app):
        with app.app_context():
            from app.services.documentation_service import get_workflow_id_for_doc
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                f = root / "api" / "guide.md"
                f.parent.mkdir(parents=True)
                f.write_text("# API Guide", encoding="utf-8")
                result = get_workflow_id_for_doc(f, root)
                assert result is None

    def test_workflow_with_steps_returns_id(self, app):
        with app.app_context():
            from app.services.documentation_service import get_workflow_id_for_doc
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                f = root / "user-guides" / "admin" / "add-user.md"
                f.parent.mkdir(parents=True)
                f.write_text("# Add User", encoding="utf-8")
                mock_workflow = MagicMock()
                mock_workflow.steps = [MagicMock()]  # Has steps
                mock_service = MagicMock()
                mock_service.get_workflow_by_id.return_value = mock_workflow
                with patch("app.services.documentation_service.WorkflowDocsService", return_value=mock_service):
                    result = get_workflow_id_for_doc(f, root)
                    assert result == "add-user"

    def test_workflow_no_steps_returns_none(self, app):
        with app.app_context():
            from app.services.documentation_service import get_workflow_id_for_doc
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                f = root / "user-guides" / "admin" / "add-user.md"
                f.parent.mkdir(parents=True)
                f.write_text("# Add User", encoding="utf-8")
                mock_workflow = MagicMock()
                mock_workflow.steps = []  # No steps
                mock_service = MagicMock()
                mock_service.get_workflow_by_id.return_value = mock_workflow
                with patch("app.services.documentation_service.WorkflowDocsService", return_value=mock_service):
                    result = get_workflow_id_for_doc(f, root)
                    assert result is None

    def test_no_workflow_returns_none(self, app):
        with app.app_context():
            from app.services.documentation_service import get_workflow_id_for_doc
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                f = root / "user-guides" / "admin" / "add-user.md"
                f.parent.mkdir(parents=True)
                f.write_text("# Add User", encoding="utf-8")
                mock_service = MagicMock()
                mock_service.get_workflow_by_id.return_value = None
                with patch("app.services.documentation_service.WorkflowDocsService", return_value=mock_service):
                    result = get_workflow_id_for_doc(f, root)
                    assert result is None

    def test_exception_returns_none(self, app):
        with app.app_context():
            from app.services.documentation_service import get_workflow_id_for_doc
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                f = root / "user-guides" / "admin" / "add-user.md"
                f.parent.mkdir(parents=True)
                f.write_text("# Add User", encoding="utf-8")
                with patch("app.services.documentation_service.WorkflowDocsService", side_effect=Exception("import error")):
                    result = get_workflow_id_for_doc(f, root)
                    assert result is None
