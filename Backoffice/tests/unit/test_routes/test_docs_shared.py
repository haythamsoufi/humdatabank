"""Tests for app/routes/docs/_shared.py."""

import pytest

pytestmark = [pytest.mark.unit]


class TestCanonicalDocPathForUrl:
    def test_empty_returns_empty(self):
        from app.routes.docs._shared import canonical_doc_path_for_url

        assert canonical_doc_path_for_url("") == ""

    def test_readme_returns_empty(self):
        from app.routes.docs._shared import canonical_doc_path_for_url

        assert canonical_doc_path_for_url("README") == ""
        assert canonical_doc_path_for_url("README.md") == ""

    def test_strips_md_extension(self):
        from app.routes.docs._shared import canonical_doc_path_for_url

        assert canonical_doc_path_for_url("user-guides/navigation.md") == "user-guides/navigation"

    def test_backslash_normalized(self):
        from app.routes.docs._shared import canonical_doc_path_for_url

        assert canonical_doc_path_for_url("user-guides\\navigation.md") == "user-guides/navigation"


class TestResolveDocsRootForPath:
    def test_falls_back_to_core_docs_without_plugin_manager(self, app):
        from app.services.documentation.service import docs_root, resolve_docs_root_for_path

        with app.app_context():
            assert resolve_docs_root_for_path("getting-started/start-here") == docs_root()

    def test_plugin_category_uses_plugin_root(self, app, tmp_path):
        from types import SimpleNamespace

        from app.plugins.base import PluginDocsSource
        from app.services.documentation.service import resolve_docs_root_for_path

        plugin_root = tmp_path / "plugin-docs"
        plugin_root.mkdir()
        source = PluginDocsSource(
            category="upr",
            root_dir=plugin_root,
            display_name="UPR",
            include_in_help=False,
        )
        app.plugin_manager = SimpleNamespace(get_documentation_sources=lambda: [source])

        with app.app_context():
            assert resolve_docs_root_for_path("upr/overview") == plugin_root.resolve()
            assert resolve_docs_root_for_path("upr/overview.md") == plugin_root.resolve()

    def test_help_eligible_only_skips_admin_plugin_source(self, app, tmp_path):
        from types import SimpleNamespace

        from app.plugins.base import PluginDocsSource
        from app.services.documentation.service import docs_root, resolve_docs_root_for_path

        plugin_root = tmp_path / "plugin-docs"
        plugin_root.mkdir()
        source = PluginDocsSource(
            category="upr",
            root_dir=plugin_root,
            display_name="UPR",
            include_in_help=False,
        )
        app.plugin_manager = SimpleNamespace(get_documentation_sources=lambda: [source])

        with app.app_context():
            assert resolve_docs_root_for_path(
                "upr/overview", help_eligible_only=True
            ) == docs_root()
