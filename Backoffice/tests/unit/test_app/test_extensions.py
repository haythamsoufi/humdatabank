"""Tests for app/extensions.py — 100% branch coverage."""

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from flask import Flask


# ---------------------------------------------------------------------------
# resolve_translations_directory
# ---------------------------------------------------------------------------

class TestResolveTranslationsDirectory:
    def test_uses_env_override_when_valid_dir(self, tmp_path):
        """Valid BACKOFFICE_TRANSLATIONS_DIR env override should be returned."""
        from app.extensions import resolve_translations_directory

        flask_app = Flask(__name__)
        with patch.dict(os.environ, {'BACKOFFICE_TRANSLATIONS_DIR': str(tmp_path)}):
            result = resolve_translations_directory(flask_app)
        assert result == str(tmp_path.resolve())

    def test_warns_and_falls_back_when_env_override_not_a_dir(self, tmp_path):
        """Invalid BACKOFFICE_TRANSLATIONS_DIR should log warning and use default."""
        from app.extensions import resolve_translations_directory

        non_existent = str(tmp_path / "does_not_exist")
        flask_app = Flask(__name__)

        with patch.dict(os.environ, {'BACKOFFICE_TRANSLATIONS_DIR': non_existent}):
            with patch.object(flask_app.logger, 'warning') as mock_warn:
                result = resolve_translations_directory(flask_app)
            mock_warn.assert_called_once()
        # Falls back to sibling "translations" dir
        assert result.endswith('translations') or 'translations' in result

    def test_uses_default_when_no_env_override(self):
        """Without env var, should return path relative to app root."""
        from app.extensions import resolve_translations_directory

        flask_app = Flask(__name__)
        with patch.dict(os.environ, {}, clear=False):
            env_save = os.environ.pop('BACKOFFICE_TRANSLATIONS_DIR', None)
            try:
                result = resolve_translations_directory(flask_app)
            finally:
                if env_save is not None:
                    os.environ['BACKOFFICE_TRANSLATIONS_DIR'] = env_save
        assert 'translations' in result

    def test_empty_env_override_uses_default(self):
        """Empty string env var should be treated as unset."""
        from app.extensions import resolve_translations_directory

        flask_app = Flask(__name__)
        with patch.dict(os.environ, {'BACKOFFICE_TRANSLATIONS_DIR': '  '}):
            result = resolve_translations_directory(flask_app)
        assert 'translations' in result


# ---------------------------------------------------------------------------
# ensure_translation_mo_files
# ---------------------------------------------------------------------------

class TestEnsureTranslationMoFiles:
    def test_returns_early_when_polib_not_available(self, tmp_path):
        """If polib is not importable, function returns silently."""
        from app.extensions import ensure_translation_mo_files

        flask_app = Flask(__name__)
        with patch.dict('sys.modules', {'polib': None}):
            # Should not raise
            ensure_translation_mo_files(flask_app, str(tmp_path))

    def test_returns_early_when_translations_dir_not_exists(self, tmp_path):
        """Non-existent translations directory: return without error."""
        from app.extensions import ensure_translation_mo_files

        flask_app = Flask(__name__)
        non_existent = tmp_path / "nonexistent"
        # Should not raise
        ensure_translation_mo_files(flask_app, str(non_existent))

    def test_skips_hidden_directories(self, tmp_path):
        """Directories starting with '.' should be skipped."""
        from app.extensions import ensure_translation_mo_files

        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        lc = hidden / "LC_MESSAGES"
        lc.mkdir()
        (lc / "messages.po").write_text("", encoding="utf-8")

        flask_app = Flask(__name__)
        polib_mock = MagicMock()

        with patch.dict('sys.modules', {'polib': polib_mock}):
            ensure_translation_mo_files(flask_app, str(tmp_path))

        # pofile should not be called for hidden dirs
        polib_mock.pofile.assert_not_called()

    def test_skips_locale_without_po_file(self, tmp_path):
        """Locale dir without messages.po should be skipped."""
        from app.extensions import ensure_translation_mo_files

        locale_dir = tmp_path / "fr"
        locale_dir.mkdir()
        lc = locale_dir / "LC_MESSAGES"
        lc.mkdir()
        # No .po file

        flask_app = Flask(__name__)
        polib_mock = MagicMock()

        with patch.dict('sys.modules', {'polib': polib_mock}):
            ensure_translation_mo_files(flask_app, str(tmp_path))

        polib_mock.pofile.assert_not_called()

    def test_compiles_po_when_mo_missing(self, tmp_path):
        """When .mo is missing, polib should compile the .po file."""
        from app.extensions import ensure_translation_mo_files

        locale_dir = tmp_path / "fr"
        locale_dir.mkdir()
        lc = locale_dir / "LC_MESSAGES"
        lc.mkdir()
        po_file = lc / "messages.po"
        po_file.write_text("", encoding="utf-8")
        # No .mo file

        flask_app = Flask(__name__)
        mock_catalog = MagicMock()
        polib_mock = MagicMock()
        polib_mock.pofile.return_value = mock_catalog

        with patch.dict('sys.modules', {'polib': polib_mock}):
            ensure_translation_mo_files(flask_app, str(tmp_path))

        polib_mock.pofile.assert_called_once_with(str(po_file))
        mock_catalog.save_as_mofile.assert_called_once()

    def test_skips_compile_when_mo_newer(self, tmp_path):
        """When .mo exists and is newer than .po, compilation should be skipped."""
        from app.extensions import ensure_translation_mo_files
        import time

        locale_dir = tmp_path / "en"
        locale_dir.mkdir()
        lc = locale_dir / "LC_MESSAGES"
        lc.mkdir()
        po_file = lc / "messages.po"
        po_file.write_text("", encoding="utf-8")
        time.sleep(0.01)  # ensure distinct mtime
        mo_file = lc / "messages.mo"
        mo_file.write_bytes(b"")
        # touch mo to make it newer than po
        os.utime(str(mo_file), None)

        flask_app = Flask(__name__)
        polib_mock = MagicMock()

        with patch.dict('sys.modules', {'polib': polib_mock}):
            ensure_translation_mo_files(flask_app, str(tmp_path))

        polib_mock.pofile.assert_not_called()

    def test_handles_compile_exception(self, tmp_path):
        """Exception during compile should be logged as warning, not raise."""
        from app.extensions import ensure_translation_mo_files

        locale_dir = tmp_path / "es"
        locale_dir.mkdir()
        lc = locale_dir / "LC_MESSAGES"
        lc.mkdir()
        po_file = lc / "messages.po"
        po_file.write_text("", encoding="utf-8")
        # No .mo file - so compile will be attempted

        flask_app = Flask(__name__)
        polib_mock = MagicMock()
        polib_mock.pofile.side_effect = Exception("compile error")

        with patch.dict('sys.modules', {'polib': polib_mock}):
            with patch.object(flask_app.logger, 'warning') as mock_warn:
                ensure_translation_mo_files(flask_app, str(tmp_path))

        mock_warn.assert_called_once()


# ---------------------------------------------------------------------------
# configure_babel
# ---------------------------------------------------------------------------

class TestConfigureBabel:
    def test_sets_babel_config_keys(self):
        """configure_babel should set BABEL_TRANSLATION_DIRECTORIES and defaults."""
        from app.extensions import configure_babel

        flask_app = Flask(__name__)
        with patch('app.extensions.resolve_translations_directory', return_value='/fake/translations'):
            with patch('app.extensions.ensure_translation_mo_files'):
                configure_babel(flask_app)

        assert flask_app.config['BABEL_TRANSLATION_DIRECTORIES'] == '/fake/translations'
        assert flask_app.config.get('BABEL_DEFAULT_LOCALE') == 'en'
        assert flask_app.config.get('BABEL_DEFAULT_TIMEZONE') == 'UTC'

    def test_disables_cache_in_debug_mode(self):
        """In DEBUG mode, BABEL_CACHE_ENABLED should be False and before_request hook added."""
        from app.extensions import configure_babel

        flask_app = Flask(__name__)
        flask_app.config['DEBUG'] = True

        with patch('app.extensions.resolve_translations_directory', return_value='/fake/translations'):
            with patch('app.extensions.ensure_translation_mo_files'):
                configure_babel(flask_app)

        assert flask_app.config.get('BABEL_CACHE_ENABLED') is False

    def test_does_not_disable_cache_in_non_debug(self):
        """In non-debug mode, cache settings should not be explicitly disabled."""
        from app.extensions import configure_babel

        flask_app = Flask(__name__)
        flask_app.config['DEBUG'] = False

        with patch('app.extensions.resolve_translations_directory', return_value='/fake/translations'):
            with patch('app.extensions.ensure_translation_mo_files'):
                configure_babel(flask_app)

        # Key should not be set (or not False) in non-debug
        assert flask_app.config.get('BABEL_CACHE_ENABLED') is not False
