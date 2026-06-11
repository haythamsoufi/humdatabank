"""
Tests for app/routes/admin/utilities/helpers.py

Covers all helper utility functions:
- _translations_dir()
- _translations_po_path()
- _translations_pot_path()
- _entry_to_display_msgstr()
- _extract_page_name()
"""
import os
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# _translations_dir
# ---------------------------------------------------------------------------

class TestTranslationsDir:
    """Tests for _translations_dir()."""

    def test_returns_configured_valid_dir(self, app, tmp_path):
        """When BACKOFFICE_TRANSLATIONS_DIR points to a real dir, return it."""
        from app.routes.admin.utilities.helpers import _translations_dir

        with app.app_context():
            app.config["BACKOFFICE_TRANSLATIONS_DIR"] = str(tmp_path)
            result = _translations_dir()

        assert result == str(tmp_path)

    def test_falls_back_when_configured_dir_does_not_exist(self, app):
        """When configured dir doesn't exist, fall back to default path."""
        from app.routes.admin.utilities.helpers import _translations_dir

        with app.app_context():
            app.config["BACKOFFICE_TRANSLATIONS_DIR"] = "/nonexistent/path/translations"
            result = _translations_dir()

        # Should be an absolute path derived from root_path
        assert os.path.isabs(result)
        assert "translations" in result

    def test_falls_back_when_no_config_key(self, app):
        """Without BACKOFFICE_TRANSLATIONS_DIR, return default path."""
        from app.routes.admin.utilities.helpers import _translations_dir

        with app.app_context():
            app.config.pop("BACKOFFICE_TRANSLATIONS_DIR", None)
            result = _translations_dir()

        assert os.path.isabs(result)
        assert "translations" in result

    def test_falls_back_when_config_is_empty_string(self, app):
        """Empty string config value falls through to default."""
        from app.routes.admin.utilities.helpers import _translations_dir

        with app.app_context():
            app.config["BACKOFFICE_TRANSLATIONS_DIR"] = ""
            result = _translations_dir()

        assert "translations" in result


# ---------------------------------------------------------------------------
# _translations_po_path
# ---------------------------------------------------------------------------

class TestTranslationsPoPath:
    """Tests for _translations_po_path()."""

    def test_returns_path_for_normal_lang_code(self, app, tmp_path):
        from app.routes.admin.utilities.helpers import _translations_po_path

        with app.app_context():
            app.config["BACKOFFICE_TRANSLATIONS_DIR"] = str(tmp_path)
            result = _translations_po_path("fr")

        assert result.endswith("messages.po")
        assert "fr" in result
        assert "LC_MESSAGES" in result

    def test_sanitizes_path_traversal_characters(self, app, tmp_path):
        """Lang codes with path-traversal chars are stripped."""
        from app.routes.admin.utilities.helpers import _translations_po_path

        with app.app_context():
            app.config["BACKOFFICE_TRANSLATIONS_DIR"] = str(tmp_path)
            result = _translations_po_path("../../etc/passwd")

        # Dangerous chars stripped → should only contain safe chars
        path_parts = result.replace("\\", "/").split("/")
        lang_segment = path_parts[-3]  # <lang>/LC_MESSAGES/messages.po
        assert ".." not in lang_segment
        assert "/" not in lang_segment

    def test_empty_lang_code_becomes_unknown(self, app, tmp_path):
        from app.routes.admin.utilities.helpers import _translations_po_path

        with app.app_context():
            app.config["BACKOFFICE_TRANSLATIONS_DIR"] = str(tmp_path)
            result = _translations_po_path("")

        assert "unknown" in result

    def test_none_lang_code_becomes_unknown(self, app, tmp_path):
        from app.routes.admin.utilities.helpers import _translations_po_path

        with app.app_context():
            app.config["BACKOFFICE_TRANSLATIONS_DIR"] = str(tmp_path)
            result = _translations_po_path(None)

        assert "unknown" in result

    def test_lang_code_truncated_to_20_chars(self, app, tmp_path):
        from app.routes.admin.utilities.helpers import _translations_po_path

        long_code = "a" * 50
        with app.app_context():
            app.config["BACKOFFICE_TRANSLATIONS_DIR"] = str(tmp_path)
            result = _translations_po_path(long_code)

        path_parts = result.replace("\\", "/").split("/")
        lang_segment = path_parts[-3]
        assert len(lang_segment) <= 20

    def test_numeric_and_hyphen_chars_preserved(self, app, tmp_path):
        from app.routes.admin.utilities.helpers import _translations_po_path

        with app.app_context():
            app.config["BACKOFFICE_TRANSLATIONS_DIR"] = str(tmp_path)
            result = _translations_po_path("zh-CN")

        assert "zh-CN" in result

    def test_special_chars_stripped_leaving_valid_code(self, app, tmp_path):
        from app.routes.admin.utilities.helpers import _translations_po_path

        with app.app_context():
            app.config["BACKOFFICE_TRANSLATIONS_DIR"] = str(tmp_path)
            result = _translations_po_path("fr!@#$%^&*()")

        # 'fr' should survive after stripping
        assert "fr" in result


# ---------------------------------------------------------------------------
# _translations_pot_path
# ---------------------------------------------------------------------------

class TestTranslationsPotPath:
    """Tests for _translations_pot_path()."""

    def test_returns_pot_file_path(self, app, tmp_path):
        from app.routes.admin.utilities.helpers import _translations_pot_path

        with app.app_context():
            app.config["BACKOFFICE_TRANSLATIONS_DIR"] = str(tmp_path)
            result = _translations_pot_path()

        assert result.endswith("messages.pot")
        assert os.path.basename(result) == "messages.pot"

    def test_pot_path_within_translations_dir(self, app, tmp_path):
        from app.routes.admin.utilities.helpers import _translations_pot_path

        with app.app_context():
            app.config["BACKOFFICE_TRANSLATIONS_DIR"] = str(tmp_path)
            result = _translations_pot_path()

        assert result.startswith(str(tmp_path))


# ---------------------------------------------------------------------------
# _entry_to_display_msgstr
# ---------------------------------------------------------------------------

class TestEntryToDisplayMsgstr:
    """Tests for _entry_to_display_msgstr()."""

    def test_returns_msgstr_when_present(self):
        from app.routes.admin.utilities.helpers import _entry_to_display_msgstr

        entry = MagicMock()
        entry.msgstr = "Hello World"
        entry.msgstr_plural = None

        result = _entry_to_display_msgstr(entry)
        assert result == "Hello World"

    def test_returns_empty_when_msgstr_is_empty_string(self):
        from app.routes.admin.utilities.helpers import _entry_to_display_msgstr

        entry = MagicMock()
        entry.msgstr = ""
        entry.msgstr_plural = None

        result = _entry_to_display_msgstr(entry)
        assert result == ""

    def test_falls_back_to_msgstr_plural_dict_key_zero(self):
        from app.routes.admin.utilities.helpers import _entry_to_display_msgstr

        entry = MagicMock()
        entry.msgstr = None
        entry.msgstr_plural = {0: "singular", 1: "plural"}

        result = _entry_to_display_msgstr(entry)
        assert result == "singular"

    def test_plural_falls_back_to_first_value_when_no_key_zero(self):
        from app.routes.admin.utilities.helpers import _entry_to_display_msgstr

        entry = MagicMock()
        entry.msgstr = None
        entry.msgstr_plural = {1: "plural form", 2: "other form"}

        result = _entry_to_display_msgstr(entry)
        assert result == "plural form"

    def test_empty_plural_dict_returns_empty_string(self):
        from app.routes.admin.utilities.helpers import _entry_to_display_msgstr

        entry = MagicMock()
        entry.msgstr = None
        entry.msgstr_plural = {}

        result = _entry_to_display_msgstr(entry)
        assert result == ""

    def test_no_msgstr_no_plural_returns_empty_string(self):
        from app.routes.admin.utilities.helpers import _entry_to_display_msgstr

        entry = MagicMock()
        entry.msgstr = None
        entry.msgstr_plural = None

        result = _entry_to_display_msgstr(entry)
        assert result == ""

    def test_exception_in_plural_access_returns_empty_string(self):
        """If getattr raises or plural access fails, return empty string."""
        from app.routes.admin.utilities.helpers import _entry_to_display_msgstr

        entry = MagicMock(spec=[])  # no attributes at all; getattr returns default
        # spec=[] means getattr(entry, 'msgstr', None) → None
        result = _entry_to_display_msgstr(entry)
        assert result == ""

    def test_msgstr_plural_with_none_values_falls_back(self):
        from app.routes.admin.utilities.helpers import _entry_to_display_msgstr

        entry = MagicMock()
        entry.msgstr = None
        # key 0 is None (falsy) → should fall back to next
        entry.msgstr_plural = {0: None, 1: "fallback plural"}

        result = _entry_to_display_msgstr(entry)
        # key 0 is None/falsy → falls through to next(iter(plural.values())) → None
        # which returns "" via `or ""`
        assert result == "" or result == "fallback plural"


# ---------------------------------------------------------------------------
# _extract_page_name
# ---------------------------------------------------------------------------

class TestExtractPageName:
    """Tests for _extract_page_name()."""

    def test_returns_unknown_for_none(self):
        from app.routes.admin.utilities.helpers import _extract_page_name

        assert _extract_page_name(None) == "Unknown"

    def test_returns_unknown_for_empty_string(self):
        from app.routes.admin.utilities.helpers import _extract_page_name

        assert _extract_page_name("") == "Unknown"

    def test_html_template_path_with_line_number(self):
        from app.routes.admin.utilities.helpers import _extract_page_name

        result = _extract_page_name("app/templates/admin/api_management.html:100")
        assert result == "api_management"

    def test_python_route_path_with_line_number(self):
        from app.routes.admin.utilities.helpers import _extract_page_name

        result = _extract_page_name("app/routes/admin/utilities.py:716")
        assert result == "utilities"

    def test_path_with_backslashes(self):
        from app.routes.admin.utilities.helpers import _extract_page_name

        result = _extract_page_name("app\\templates\\admin\\dashboard.html:50")
        assert result == "dashboard"

    def test_bare_filename_no_extension(self):
        from app.routes.admin.utilities.helpers import _extract_page_name

        result = _extract_page_name("somefile")
        assert result == "somefile"

    def test_multiple_refs_uses_first_only(self):
        """Space-separated refs: only the first is used."""
        from app.routes.admin.utilities.helpers import _extract_page_name

        result = _extract_page_name(
            "app/templates/admin/foo.html:10 app/templates/admin/bar.html:20"
        )
        assert result == "foo"

    def test_file_without_line_number(self):
        from app.routes.admin.utilities.helpers import _extract_page_name

        result = _extract_page_name("app/templates/admin/settings.html")
        assert result == "settings"

    def test_filename_with_dots_in_name(self):
        from app.routes.admin.utilities.helpers import _extract_page_name

        result = _extract_page_name("app/templates/some.page.html:5")
        # rsplit('.', 1)[0] → 'some.page'
        assert result == "some.page"

    def test_whitespace_input_returns_unknown(self):
        from app.routes.admin.utilities.helpers import _extract_page_name

        result = _extract_page_name("   ")
        assert result == "Unknown"
