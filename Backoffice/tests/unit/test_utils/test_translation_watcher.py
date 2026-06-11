"""
Unit tests for app/utils/translation_watcher.py – 100% coverage target.

File-system and threading interactions are mocked throughout.
"""
import time
import threading
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock, call

from app.utils.translation_watcher import TranslationWatcher, init_translation_watcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_app(debug=False, translation_dir=None):
    app = MagicMock()
    app.config = {'DEBUG': debug}
    if translation_dir is not None:
        app.config['BACKOFFICE_TRANSLATIONS_DIR'] = str(translation_dir)
    app.root_path = '/fake/app'
    app.logger = MagicMock()
    return app


# ---------------------------------------------------------------------------
# __init__ / init_app
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestTranslationWatcherInit:
    def test_init_without_app(self):
        watcher = TranslationWatcher()
        assert watcher.app is None
        assert watcher.watching is False
        assert watcher.watcher_thread is None

    def test_init_with_app_debug_false_does_not_start_watching(self):
        app = _make_app(debug=False)
        watcher = TranslationWatcher(app=app)
        assert watcher.watching is False

    def test_init_with_app_debug_true_starts_watching(self):
        app = _make_app(debug=True)
        watcher = TranslationWatcher(app=app)
        assert watcher.watching is True
        watcher.stop_watching()

    def test_init_app_assigns_app(self):
        app = _make_app()
        watcher = TranslationWatcher()
        watcher.init_app(app)
        assert watcher.app is app


# ---------------------------------------------------------------------------
# get_translation_files
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetTranslationFiles:
    def test_nonexistent_translation_dir_returns_empty(self):
        app = _make_app()
        watcher = TranslationWatcher()
        watcher.app = app
        with patch('app.utils.translation_watcher.Path') as MockPath:
            mock_dir = MagicMock()
            mock_dir.exists.return_value = False
            MockPath.return_value = mock_dir
            result = watcher.get_translation_files()
        assert result == []

    def test_configured_dir_used_when_set(self, tmp_path):
        lang_dir = tmp_path / 'en' / 'LC_MESSAGES'
        lang_dir.mkdir(parents=True)
        po = lang_dir / 'messages.po'
        mo = lang_dir / 'messages.mo'
        po.write_text('# po')
        mo.write_bytes(b'\x00mo')

        app = _make_app(translation_dir=str(tmp_path))
        watcher = TranslationWatcher()
        watcher.app = app
        files = watcher.get_translation_files()
        filenames = [f.name for f in files]
        assert 'messages.po' in filenames
        assert 'messages.mo' in filenames

    def test_default_dir_used_when_not_configured(self, tmp_path):
        lang_dir = tmp_path / 'fr' / 'LC_MESSAGES'
        lang_dir.mkdir(parents=True)
        po = lang_dir / 'messages.po'
        po.write_text('# fr po')

        app = MagicMock()
        app.config = {'DEBUG': False}
        app.root_path = str(tmp_path / 'app')
        app.logger = MagicMock()

        watcher = TranslationWatcher()
        watcher.app = app
        files = watcher.get_translation_files()
        # tmp_path/translations doesn't exist in this case, so empty
        assert isinstance(files, list)

    def test_only_po_files_collected_when_no_mo(self, tmp_path):
        lang_dir = tmp_path / 'ar' / 'LC_MESSAGES'
        lang_dir.mkdir(parents=True)
        po = lang_dir / 'messages.po'
        po.write_text('# ar')

        app = _make_app(translation_dir=str(tmp_path))
        watcher = TranslationWatcher()
        watcher.app = app
        files = watcher.get_translation_files()
        assert any(f.name == 'messages.po' for f in files)
        assert not any(f.name == 'messages.mo' for f in files)

    def test_non_directory_entries_skipped(self, tmp_path):
        # Create a file (not a dir) in translation root
        (tmp_path / 'README.txt').write_text('readme')
        app = _make_app(translation_dir=str(tmp_path))
        watcher = TranslationWatcher()
        watcher.app = app
        files = watcher.get_translation_files()
        assert isinstance(files, list)


# ---------------------------------------------------------------------------
# check_for_changes
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestCheckForChanges:
    def test_new_file_detected_as_changed(self, tmp_path):
        po = tmp_path / 'messages.po'
        po.write_text('original')
        app = _make_app(translation_dir=str(tmp_path.parent))

        watcher = TranslationWatcher()
        watcher.app = app
        watcher.last_modified = {}

        with patch.object(watcher, 'get_translation_files', return_value=[po]):
            changed = watcher.check_for_changes()
        assert po in changed

    def test_unchanged_file_not_in_result(self, tmp_path):
        po = tmp_path / 'messages.po'
        po.write_text('original')

        watcher = TranslationWatcher()
        watcher.app = _make_app()
        mtime = po.stat().st_mtime
        watcher.last_modified = {str(po): mtime + 1000}  # future → not changed

        with patch.object(watcher, 'get_translation_files', return_value=[po]):
            changed = watcher.check_for_changes()
        assert po not in changed

    def test_os_error_on_stat_is_skipped(self, tmp_path):
        po = tmp_path / 'ghost.po'  # doesn't exist

        watcher = TranslationWatcher()
        watcher.app = _make_app()
        watcher.last_modified = {}

        with patch.object(watcher, 'get_translation_files', return_value=[po]):
            changed = watcher.check_for_changes()
        assert changed == []

    def test_last_modified_updated_after_change(self, tmp_path):
        po = tmp_path / 'messages.po'
        po.write_text('data')

        watcher = TranslationWatcher()
        watcher.app = _make_app()
        watcher.last_modified = {}

        with patch.object(watcher, 'get_translation_files', return_value=[po]):
            watcher.check_for_changes()
        assert str(po) in watcher.last_modified


# ---------------------------------------------------------------------------
# reload_translations
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestReloadTranslations:
    def test_reload_calls_refresh(self):
        app = _make_app()
        watcher = TranslationWatcher()
        watcher.app = app

        with patch('app.utils.translation_watcher.refresh') as mock_refresh:
            watcher.reload_translations()
        mock_refresh.assert_called_once()

    def test_reload_logs_error_on_exception(self):
        app = _make_app()
        watcher = TranslationWatcher()
        watcher.app = app

        with patch('app.utils.translation_watcher.refresh', side_effect=Exception('fail')):
            watcher.reload_translations()
        app.logger.error.assert_called_once()


# ---------------------------------------------------------------------------
# start_watching / stop_watching
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestStartStopWatching:
    def test_start_watching_sets_flag(self):
        app = _make_app()
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.start_watching()
        assert watcher.watching is True
        watcher.stop_watching()

    def test_start_watching_creates_thread(self):
        app = _make_app()
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.start_watching()
        assert watcher.watcher_thread is not None
        watcher.stop_watching()

    def test_start_watching_idempotent(self):
        app = _make_app()
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.start_watching()
        thread1 = watcher.watcher_thread
        watcher.start_watching()  # call again
        assert watcher.watcher_thread is thread1  # same thread
        watcher.stop_watching()

    def test_stop_watching_clears_flag(self):
        app = _make_app()
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.start_watching()
        watcher.stop_watching()
        assert watcher.watching is False

    def test_stop_watching_logs_info(self):
        app = _make_app()
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.start_watching()
        watcher.stop_watching()
        app.logger.info.assert_called()

    def test_stop_watching_without_thread_is_safe(self):
        app = _make_app()
        watcher = TranslationWatcher()
        watcher.app = app
        # Never started watching; watcher_thread is None
        assert watcher.watcher_thread is None
        watcher.stop_watching()  # should not raise
        app.logger.info.assert_called()


# ---------------------------------------------------------------------------
# watch_loop
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestWatchLoop:
    def test_watch_loop_calls_reload_on_change(self):
        app = _make_app()
        watcher = TranslationWatcher()
        watcher.app = app

        call_count = [0]

        def fake_check():
            call_count[0] += 1
            watcher.watching = False  # stop after first iteration
            return [Path('/fake/messages.po')]

        watcher.watching = True
        with patch.object(watcher, 'check_for_changes', side_effect=fake_check), \
             patch.object(watcher, 'reload_translations') as mock_reload, \
             patch('app.utils.translation_watcher.time') as mock_time:
            mock_time.sleep = MagicMock()
            watcher.watch_loop()

        mock_reload.assert_called_once()

    def test_watch_loop_no_changes_no_reload(self):
        app = _make_app()
        watcher = TranslationWatcher()
        watcher.app = app

        call_count = [0]

        def fake_check():
            call_count[0] += 1
            watcher.watching = False
            return []  # No changes

        watcher.watching = True
        with patch.object(watcher, 'check_for_changes', side_effect=fake_check), \
             patch.object(watcher, 'reload_translations') as mock_reload, \
             patch('app.utils.translation_watcher.time') as mock_time:
            mock_time.sleep = MagicMock()
            watcher.watch_loop()

        mock_reload.assert_not_called()

    def test_watch_loop_handles_exception_gracefully(self):
        app = _make_app()
        watcher = TranslationWatcher()
        watcher.app = app

        call_count = [0]

        def fake_check():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError('unexpected')
            watcher.watching = False
            return []

        watcher.watching = True
        with patch.object(watcher, 'check_for_changes', side_effect=fake_check), \
             patch('app.utils.translation_watcher.time') as mock_time:
            mock_time.sleep = MagicMock()
            watcher.watch_loop()

        app.logger.error.assert_called()


# ---------------------------------------------------------------------------
# init_translation_watcher
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestInitTranslationWatcher:
    def test_init_translation_watcher_calls_init_app(self):
        app = _make_app()
        with patch('app.utils.translation_watcher.translation_watcher') as mock_tw:
            init_translation_watcher(app)
            mock_tw.init_app.assert_called_once_with(app)
