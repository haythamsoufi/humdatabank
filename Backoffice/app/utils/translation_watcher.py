"""
Translation file watcher utility for automatic reloading of translations.
This module provides functionality to watch translation files and automatically
reload them when they change, eliminating the need to restart the Flask application.
"""

import os
import time
import threading
from pathlib import Path
from flask import current_app
from flask_babel import refresh

class TranslationWatcher:
    """Watches translation files for changes and automatically reloads them."""

    def __init__(self, app=None):
        self.app = app
        self.watching = False
        self.watcher_thread = None
        self.last_modified = {}

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the translation watcher with the Flask app."""
        self.app = app

        # Only start watching in development mode
        if app.config.get('DEBUG', False):
            self.start_watching()

    def get_translation_files(self):
        """Get all translation files to watch."""
        translation_dir = Path(self.app.root_path).parent / 'translations'
        files_to_watch = []

        if translation_dir.exists():
            for lang_dir in translation_dir.iterdir():
                if lang_dir.is_dir():
                    po_file = lang_dir / 'LC_MESSAGES' / 'messages.po'
                    mo_file = lang_dir / 'LC_MESSAGES' / 'messages.mo'
                    if po_file.exists():
                        files_to_watch.append(po_file)
                    if mo_file.exists():
                        files_to_watch.append(mo_file)

        return files_to_watch

    def check_for_changes(self):
        """Check if any translation files have changed."""
        files_to_watch = self.get_translation_files()
        changed_files = []

        for file_path in files_to_watch:
            try:
                current_mtime = file_path.stat().st_mtime
                last_mtime = self.last_modified.get(str(file_path), 0)

                if current_mtime > last_mtime:
                    self.last_modified[str(file_path)] = current_mtime
                    changed_files.append(file_path)

            except (OSError, FileNotFoundError):
                continue

        return changed_files

    def reload_translations(self):
        """Reload translations using Flask-Babel's refresh function."""
        try:
            with self.app.app_context():
                refresh()
        except Exception as e:
            self.app.logger.error(f"Error reloading translations: {e}")

    def watch_loop(self):
        """Main watching loop that checks for file changes."""
        while self.watching:
            try:
                changed_files = self.check_for_changes()

                if changed_files:
                    self.reload_translations()

                # Check every 1 second in development for faster response
                time.sleep(1)

            except Exception as e:
                self.app.logger.error(f"Error in translation watcher: {e}")
                time.sleep(5)  # Wait longer on error

    def start_watching(self):
        """Start watching translation files."""
        if not self.watching:
            self.watching = True
            self.watcher_thread = threading.Thread(target=self.watch_loop, daemon=True)
            self.watcher_thread.start()

    def stop_watching(self):
        """Stop watching translation files."""
        self.watching = False
        if self.watcher_thread:
            self.watcher_thread.join(timeout=1)
        self.app.logger.info("Translation file watcher stopped")

# Global instance
translation_watcher = TranslationWatcher()

def init_translation_watcher(app):
    """Initialize the translation watcher with the Flask app."""
    translation_watcher.init_app(app)
