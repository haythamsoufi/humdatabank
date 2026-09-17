"""
Translation catalog watcher for automatic multi-worker cache refresh.

Strategy
--------
The ``.po``/``.mo`` artifacts are materialized per container from
``translation_string``, so an edit made in one container never changes a file
on another container's disk.  The watcher therefore polls the
``translation_catalog_version`` counter, which every catalog write bumps:

* Reaches peer *containers*, not just peer workers on a shared mount.
* O(1) per tick — a primary-key lookup, not an O(locales × 2) file scan.
* When the counter is ahead of the version this container last built from, the
  worker rebuilds its catalogs from the database before refreshing Babel.

Fallback: when the counter cannot be read (database briefly unreachable), the
watcher reverts to the ``translations/.sentinel`` mtime, and to scanning
individual .po/.mo files when no sentinel exists (first boot, non-Docker dev).
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

    def _db_version(self):
        """Catalog version from the database, or None when it cannot be read."""
        try:
            with self.app.app_context():
                from app.services.translation.catalog_service import read_catalog_version

                return read_catalog_version()
        except Exception as exc:
            self.app.logger.debug("TranslationWatcher: version read failed: %s", exc)
            return None

    def _rebuild_if_stale(self) -> bool:
        """Materialize this container's catalogs when the database is ahead.

        Returns True when a rebuild happened, so the caller can refresh Babel.
        """
        try:
            with self.app.app_context():
                from app.services.translation.catalog_service import sync_catalogs_if_stale

                return sync_catalogs_if_stale() is not None
        except Exception as exc:
            self.app.logger.error("TranslationWatcher: catalog rebuild failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Watch loop
    # ------------------------------------------------------------------

    def _watch_loop(self):
        poll_interval = float(
            self.app.config.get("TRANSLATION_WATCHER_INTERVAL", DEFAULT_POLL_INTERVAL_S)
        )
        sentinel = self._sentinel_path()

        # Seed last-seen mtime for the sentinel (and fallback files) so we
        # don't trigger a spurious reload on startup.  A transient filesystem
        # error here must not kill the daemon thread permanently — log and
        # let the loop below retry on its next tick instead.
        try:
            self._last_mtime[str(sentinel)] = self._mtime(sentinel)
            for f in self._fallback_files():
                self._last_mtime[str(f)] = self._mtime(f)
        except Exception as exc:
            self.app.logger.error("TranslationWatcher: seed failed: %s", exc)

        last_version = self._db_version()

        while self.watching:
            try:
                changed = False

                # Preferred signal: the database version counter. It reaches
                # peer *containers*, which a local file mtime cannot now that
                # artifacts are materialized per container.
                version = self._db_version()
                if version is None:
                    # Database unreachable — fall back to the filesystem so a
                    # shared mount (or single-container deploy) still propagates.
                    if sentinel.exists():
                        if self._changed(sentinel):
                            changed = True
                    else:
                        for f in self._fallback_files():
                            if self._changed(f):
                                changed = True
                elif version != last_version:
                    last_version = version
                    self._rebuild_if_stale()
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
