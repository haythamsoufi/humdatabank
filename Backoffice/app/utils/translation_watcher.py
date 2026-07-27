"""
Translation file watcher for automatic multi-worker cache refresh.

Strategy
--------
Rather than rescanning every locale directory on each tick (O(locales) I/O,
unreliable on Azure Files SMB), the watcher now checks a single sentinel file
``translations/.sentinel`` whose mtime is updated by any PO/MO write
(via ``app.utils.po_lock.touch_translation_sentinel``).  This gives:

* O(1) I/O per tick instead of O(locales × 2 files).
* Reliable detection on network file systems where per-file mtime propagation
  can lag across SMB connections.
* Immediate cross-worker notification: the admin "Compile" route writes the
  sentinel immediately after refreshing its own worker, so peer workers pick
  up the change on their next poll (≤ POLL_INTERVAL_S seconds).

Fallback: if the sentinel file does not exist (first boot, non-Docker dev),
the watcher falls back to scanning individual .po/.mo files as before, and
creates the sentinel on first detection.
"""

import time
import threading
from pathlib import Path
from flask_babel import refresh

from app.utils.po_lock import SENTINEL_FILENAME

# How often to check for changes (seconds).  Keep at 1 s in production;
# configurable via TRANSLATION_WATCHER_INTERVAL app config for testing.
DEFAULT_POLL_INTERVAL_S = 1


class TranslationWatcher:
    """Watches translations for changes and calls flask_babel.refresh() in all
    Gunicorn workers when any PO or MO file is updated."""

    def __init__(self, app=None):
        self.app = app
        self.watching = False
        self.watcher_thread = None
        # Tracks last-seen mtime for each watched path (str → float).
        self._last_mtime: dict[str, float] = {}

        if app is not None:
            self.init_app(app)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init_app(self, app):
        """Initialize the translation watcher with the Flask app."""
        self.app = app

        # In DEBUG mode, extensions.py already calls flask_babel.refresh() on
        # every request via a before_request hook, so a background polling
        # thread is redundant overhead.  The watcher is only meaningful in
        # production/staging where multi-worker Gunicorn needs each process to
        # pick up PO/MO changes written by a peer worker.
        if app.config.get("DEBUG", False):
            app.logger.debug(
                "Translation watcher disabled in DEBUG mode "
                "(per-request Babel refresh is active)"
            )
            return

        # Poll shared translation catalogs so all Gunicorn workers pick up
        # PO/MO changes without a manual restart.
        self.start_watching()

    def start_watching(self):
        """Start the background watcher thread."""
        if not self.watching:
            self.watching = True
            self.watcher_thread = threading.Thread(
                target=self._watch_loop, daemon=True, name="translation-watcher"
            )
            self.watcher_thread.start()

    def stop_watching(self):
        """Stop the background watcher thread."""
        self.watching = False
        if self.watcher_thread:
            self.watcher_thread.join(timeout=2)
        self.app.logger.info("Translation file watcher stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _translations_dir(self) -> Path:
        configured = self.app.config.get("BACKOFFICE_TRANSLATIONS_DIR")
        if configured:
            return Path(configured)
        return Path(self.app.root_path).parent / "translations"

    def _sentinel_path(self) -> Path:
        return self._translations_dir() / SENTINEL_FILENAME

    def _fallback_files(self) -> list[Path]:
        """Return .po and .mo paths for the fallback (no-sentinel) strategy."""
        trans_dir = self._translations_dir()
        files: list[Path] = []
        if not trans_dir.exists():
            return files
        for lang_dir in trans_dir.iterdir():
            if not lang_dir.is_dir():
                continue
            for name in ("messages.po", "messages.mo"):
                f = lang_dir / "LC_MESSAGES" / name
                if f.exists():
                    files.append(f)
        return files

    def _mtime(self, path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _changed(self, path: Path) -> bool:
        key = str(path)
        current = self._mtime(path)
        if current > self._last_mtime.get(key, 0.0):
            self._last_mtime[key] = current
            return True
        return False

    def _reload(self):
        try:
            with self.app.app_context():
                refresh()
        except Exception as exc:
            self.app.logger.error("TranslationWatcher: refresh failed: %s", exc)

    # ------------------------------------------------------------------
    # Watch loop
    # ------------------------------------------------------------------

    def _watch_loop(self):
        poll_interval = float(
            self.app.config.get("TRANSLATION_WATCHER_INTERVAL", DEFAULT_POLL_INTERVAL_S)
        )
        sentinel = self._sentinel_path()

        # Seed last-seen mtime for the sentinel (and fallback files) so we
        # don't trigger a spurious reload on startup.
        self._last_mtime[str(sentinel)] = self._mtime(sentinel)
        for f in self._fallback_files():
            self._last_mtime[str(f)] = self._mtime(f)

        while self.watching:
            try:
                changed = False

                if sentinel.exists():
                    # Fast path: single-file check.
                    if self._changed(sentinel):
                        changed = True
                else:
                    # Fallback: scan individual .po / .mo files.
                    for f in self._fallback_files():
                        if self._changed(f):
                            changed = True

                if changed:
                    self._reload()

                time.sleep(poll_interval)

            except Exception as exc:
                self.app.logger.error("TranslationWatcher loop error: %s", exc)
                time.sleep(5)


# Module-level singleton — initialised lazily by init_translation_watcher().
translation_watcher = TranslationWatcher()


def init_translation_watcher(app):
    """Attach the global TranslationWatcher to *app* and start it."""
    translation_watcher.init_app(app)
