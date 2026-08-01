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
