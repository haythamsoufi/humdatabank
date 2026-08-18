"""
Unit tests for app/utils/translation_watcher.py (sentinel-based watcher).

File-system and threading interactions are mocked or use tmp_path throughout.
Covers the current API: init_app/start_watching/stop_watching lifecycle,
_translations_dir/_sentinel_path resolution, the sentinel fast-path vs the
fallback .po/.mo scan, _mtime/_changed mtime tracking, _reload, and the
_watch_loop's sentinel-vs-fallback branching plus its exception handling.
"""
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.utils.translation_watcher import TranslationWatcher, init_translation_watcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_app(debug=False, translation_dir=None, root_path='/fake/app'):
    app = MagicMock()
    app.config = {'DEBUG': debug}
    if translation_dir is not None:
        app.config['BACKOFFICE_TRANSLATIONS_DIR'] = str(translation_dir)
    app.root_path = root_path
    app.logger = MagicMock()
    app.app_context.return_value.__enter__ = MagicMock(return_value=None)
    app.app_context.return_value.__exit__ = MagicMock(return_value=False)
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
        assert watcher._last_mtime == {}

    def test_init_with_app_debug_false_starts_watching(self):
        app = _make_app(debug=False)
        watcher = TranslationWatcher(app=app)
        assert watcher.watching is True
        watcher.stop_watching()

    def test_init_with_app_debug_true_does_not_start_watching(self):
        app = _make_app(debug=True)
        watcher = TranslationWatcher(app=app)
        assert watcher.watching is False
        app.logger.debug.assert_called_once()

    def test_init_app_assigns_app(self):
        app = _make_app(debug=True)
        watcher = TranslationWatcher()
        watcher.init_app(app)
        assert watcher.app is app


# ---------------------------------------------------------------------------
# _translations_dir / _sentinel_path
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestTranslationsDir:
    def test_configured_dir_used_when_set(self, tmp_path):
        app = _make_app(debug=True, translation_dir=tmp_path)
        watcher = TranslationWatcher()
        watcher.app = app
        assert watcher._translations_dir() == Path(str(tmp_path))

    def test_default_dir_used_when_not_configured(self):
        app = _make_app(debug=True, root_path='/fake/app')
        watcher = TranslationWatcher()
        watcher.app = app
        assert watcher._translations_dir() == Path('/fake') / 'translations'

    def test_sentinel_path_is_inside_translations_dir(self, tmp_path):
        app = _make_app(debug=True, translation_dir=tmp_path)
        watcher = TranslationWatcher()
        watcher.app = app
        assert watcher._sentinel_path() == tmp_path / '.sentinel'


# ---------------------------------------------------------------------------
# _fallback_files
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestFallbackFiles:
    def test_nonexistent_translation_dir_returns_empty(self, tmp_path):
        missing = tmp_path / 'does-not-exist'
        app = _make_app(debug=True, translation_dir=missing)
        watcher = TranslationWatcher()
        watcher.app = app
        assert watcher._fallback_files() == []

    def test_po_and_mo_collected_when_present(self, tmp_path):
        lang_dir = tmp_path / 'en' / 'LC_MESSAGES'
        lang_dir.mkdir(parents=True)
        (lang_dir / 'messages.po').write_text('# po')
        (lang_dir / 'messages.mo').write_bytes(b'\x00mo')

        app = _make_app(debug=True, translation_dir=tmp_path)
        watcher = TranslationWatcher()
        watcher.app = app
        files = watcher._fallback_files()
        names = [f.name for f in files]
        assert 'messages.po' in names
        assert 'messages.mo' in names

    def test_only_po_files_collected_when_no_mo(self, tmp_path):
        lang_dir = tmp_path / 'ar' / 'LC_MESSAGES'
        lang_dir.mkdir(parents=True)
        (lang_dir / 'messages.po').write_text('# ar')

        app = _make_app(debug=True, translation_dir=tmp_path)
        watcher = TranslationWatcher()
        watcher.app = app
        files = watcher._fallback_files()
        assert any(f.name == 'messages.po' for f in files)
        assert not any(f.name == 'messages.mo' for f in files)

    def test_non_directory_entries_skipped(self, tmp_path):
        (tmp_path / 'README.txt').write_text('readme')
        app = _make_app(debug=True, translation_dir=tmp_path)
        watcher = TranslationWatcher()
        watcher.app = app
        assert watcher._fallback_files() == []

    def test_hidden_sentinel_like_files_at_root_are_not_locale_dirs(self, tmp_path):
        # A stray file directly under translations/ (e.g. .sentinel) is not a
        # locale directory and must not raise when iterated.
        (tmp_path / '.sentinel').write_text('123.0')
        lang_dir = tmp_path / 'fr' / 'LC_MESSAGES'
        lang_dir.mkdir(parents=True)
        (lang_dir / 'messages.po').write_text('# fr')

        app = _make_app(debug=True, translation_dir=tmp_path)
        watcher = TranslationWatcher()
        watcher.app = app
        files = watcher._fallback_files()
        assert any(f.name == 'messages.po' for f in files)


# ---------------------------------------------------------------------------
# _mtime / _changed
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestMtimeAndChanged:
    def test_mtime_of_existing_file(self, tmp_path):
        f = tmp_path / 'messages.po'
        f.write_text('data')
        watcher = TranslationWatcher()
        assert watcher._mtime(f) == pytest.approx(f.stat().st_mtime)

    def test_mtime_of_missing_file_returns_zero(self, tmp_path):
        watcher = TranslationWatcher()
        assert watcher._mtime(tmp_path / 'ghost.po') == 0.0

    def test_changed_true_on_first_sighting(self, tmp_path):
        f = tmp_path / 'messages.po'
        f.write_text('data')
        watcher = TranslationWatcher()
        assert watcher._changed(f) is True

    def test_changed_false_when_mtime_unchanged(self, tmp_path):
        f = tmp_path / 'messages.po'
        f.write_text('data')
        watcher = TranslationWatcher()
        watcher._changed(f)  # seed
        assert watcher._changed(f) is False

    def test_changed_true_when_mtime_advances(self, tmp_path):
        f = tmp_path / 'messages.po'
        f.write_text('data')
        watcher = TranslationWatcher()
        watcher._last_mtime[str(f)] = watcher._mtime(f) - 1000  # force "stale"
        assert watcher._changed(f) is True

    def test_changed_updates_last_mtime(self, tmp_path):
        f = tmp_path / 'messages.po'
        f.write_text('data')
        watcher = TranslationWatcher()
        watcher._changed(f)
        assert watcher._last_mtime[str(f)] == pytest.approx(f.stat().st_mtime)


# ---------------------------------------------------------------------------
# _reload
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestReload:
    def test_reload_calls_refresh_within_app_context(self):
        app = _make_app(debug=True)
        watcher = TranslationWatcher()
        watcher.app = app

        with patch('app.utils.translation_watcher.refresh') as mock_refresh:
            watcher._reload()
        mock_refresh.assert_called_once()
        app.app_context.assert_called_once()

    def test_reload_logs_error_on_exception(self):
        app = _make_app(debug=True)
        watcher = TranslationWatcher()
        watcher.app = app

        with patch('app.utils.translation_watcher.refresh', side_effect=Exception('fail')):
            watcher._reload()
        app.logger.error.assert_called_once()


# ---------------------------------------------------------------------------
# start_watching / stop_watching
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestStartStopWatching:
    def test_start_watching_sets_flag(self):
        app = _make_app(debug=True)
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.start_watching()
        assert watcher.watching is True
        watcher.stop_watching()

    def test_start_watching_creates_daemon_thread(self):
        app = _make_app(debug=True)
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.start_watching()
        assert isinstance(watcher.watcher_thread, threading.Thread)
        assert watcher.watcher_thread.daemon is True
        watcher.stop_watching()

    def test_start_watching_idempotent(self):
        app = _make_app(debug=True)
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.start_watching()
        thread1 = watcher.watcher_thread
        watcher.start_watching()  # call again while already running
        assert watcher.watcher_thread is thread1
        watcher.stop_watching()

    def test_stop_watching_clears_flag(self):
        app = _make_app(debug=True)
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.start_watching()
        watcher.stop_watching()
        assert watcher.watching is False

    def test_stop_watching_logs_info(self):
        app = _make_app(debug=True)
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.start_watching()
        watcher.stop_watching()
        app.logger.info.assert_called_once()

    def test_stop_watching_without_thread_is_safe(self):
        app = _make_app(debug=True)
        watcher = TranslationWatcher()
        watcher.app = app
        assert watcher.watcher_thread is None
        watcher.stop_watching()  # should not raise
        app.logger.info.assert_called_once()


# ---------------------------------------------------------------------------
# _watch_loop
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestWatchLoop:
    def test_sentinel_change_triggers_reload(self, tmp_path):
        app = _make_app(debug=True, translation_dir=tmp_path)
        app.config['TRANSLATION_WATCHER_INTERVAL'] = 0
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.watching = True

        sentinel = tmp_path / '.sentinel'
        sentinel.write_text('0')

        call_count = {'n': 0}

        def fake_sleep(_secs):
            call_count['n'] += 1
            if call_count['n'] == 1:
                # Touch the sentinel with a newer mtime before the next poll.
                sentinel.write_text('1')
                new_time = time.time() + 5
                import os
                os.utime(sentinel, (new_time, new_time))
            else:
                watcher.watching = False

        with patch('app.utils.translation_watcher.time.sleep', side_effect=fake_sleep), \
             patch.object(watcher, '_reload') as mock_reload:
            watcher._watch_loop()

        assert mock_reload.call_count >= 1

    def test_no_sentinel_falls_back_to_file_scan(self, tmp_path):
        app = _make_app(debug=True, translation_dir=tmp_path)
        app.config['TRANSLATION_WATCHER_INTERVAL'] = 0
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.watching = True

        lang_dir = tmp_path / 'fr' / 'LC_MESSAGES'
        lang_dir.mkdir(parents=True)
        po = lang_dir / 'messages.po'
        po.write_text('# fr')

        iterations = {'n': 0}

        def fake_sleep(_secs):
            iterations['n'] += 1
            if iterations['n'] == 1:
                new_time = time.time() + 5
                import os
                os.utime(po, (new_time, new_time))
            else:
                watcher.watching = False

        with patch('app.utils.translation_watcher.time.sleep', side_effect=fake_sleep), \
             patch.object(watcher, '_reload') as mock_reload:
            watcher._watch_loop()

        assert not watcher._sentinel_path().exists()
        assert mock_reload.call_count >= 1

    def test_no_changes_does_not_reload(self, tmp_path):
        app = _make_app(debug=True, translation_dir=tmp_path)
        app.config['TRANSLATION_WATCHER_INTERVAL'] = 0
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.watching = True

        calls = {'n': 0}

        def fake_sleep(_secs):
            calls['n'] += 1
            if calls['n'] >= 2:
                watcher.watching = False

        with patch('app.utils.translation_watcher.time.sleep', side_effect=fake_sleep), \
             patch.object(watcher, '_reload') as mock_reload:
            watcher._watch_loop()

        mock_reload.assert_not_called()

    def test_seed_failure_is_logged_and_does_not_kill_the_thread(self, tmp_path):
        # An exception during the initial mtime-seeding step (before the
        # polling loop starts) must not propagate — otherwise the daemon
        # thread would die silently and translations would never refresh.
        app = _make_app(debug=True, translation_dir=tmp_path)
        app.config['TRANSLATION_WATCHER_INTERVAL'] = 0
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.watching = True

        calls = {'n': 0}

        def fake_sleep(_secs):
            calls['n'] += 1
            watcher.watching = False

        with patch('app.utils.translation_watcher.time.sleep', side_effect=fake_sleep), \
             patch.object(watcher, '_fallback_files', side_effect=RuntimeError('boom')):
            watcher._watch_loop()  # must not raise

        app.logger.error.assert_called()
        assert calls['n'] == 1  # loop body still ran after the seed failure

    def test_loop_body_exception_is_logged_and_backs_off(self, tmp_path):
        app = _make_app(debug=True, translation_dir=tmp_path)
        app.config['TRANSLATION_WATCHER_INTERVAL'] = 0
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.watching = True

        calls = {'n': 0}

        def fake_sleep(secs):
            calls['n'] += 1
            if calls['n'] >= 1:
                watcher.watching = False

        # Seeding succeeds (no sentinel/fallback files yet); the failure is
        # injected inside the loop body via `_changed`, which is only called
        # once the sentinel file exists.
        (tmp_path / '.sentinel').write_text('0')

        with patch('app.utils.translation_watcher.time.sleep', side_effect=fake_sleep), \
             patch.object(watcher, '_changed', side_effect=RuntimeError('boom')):
            watcher._watch_loop()

        app.logger.error.assert_called()

    def test_poll_interval_read_from_config(self, tmp_path):
        app = _make_app(debug=True, translation_dir=tmp_path)
        app.config['TRANSLATION_WATCHER_INTERVAL'] = 42
        watcher = TranslationWatcher()
        watcher.app = app
        watcher.watching = True

        seen_intervals = []

        def fake_sleep(secs):
            seen_intervals.append(secs)
            watcher.watching = False

        with patch('app.utils.translation_watcher.time.sleep', side_effect=fake_sleep):
            watcher._watch_loop()

        assert seen_intervals == [42.0]


# ---------------------------------------------------------------------------
# init_translation_watcher
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestInitTranslationWatcher:
    def test_init_translation_watcher_calls_init_app(self):
        app = _make_app(debug=True)
        with patch('app.utils.translation_watcher.translation_watcher') as mock_tw:
            init_translation_watcher(app)
            mock_tw.init_app.assert_called_once_with(app)
