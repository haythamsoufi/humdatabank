"""Minimal sample plugin for the Humanitarian Databank.

Starter template. Copy this folder to Backoffice/plugins/<plugin_id>/ and restart
the application. Plugins ship with the core image; there is no runtime upload.
"""
from typing import Any, Dict, List

from app.plugins.base import BasePlugin


class SamplePlugin(BasePlugin):
    """Minimal plugin with no field types. Use as a starting point for new plugins."""

    @property
    def plugin_id(self) -> str:
        return "sample_plugin"

    @property
    def display_name(self) -> str:
        return "Sample Plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Starter plugin package for the Humanitarian Databank plugin system."

    @property
    def author(self) -> str:
        return "Haytham Alsoufi"

    @property
    def homepage(self) -> str:
        return "https://github.com/haythamsoufi"

    @property
    def license(self) -> str:
        return "MIT"

    def get_field_types(self) -> List:
        return []

    def get_blueprint(self):
        # Registered at application start; serves /admin/plugins/sample_plugin/settings.
        from plugins.sample_plugin.routes import bp

        return bp

    def get_settings(self) -> Dict[str, Any]:
        from plugins.sample_plugin.routes import settings_status

        return settings_status()

    def is_admin_feature(self) -> bool:
        return True
