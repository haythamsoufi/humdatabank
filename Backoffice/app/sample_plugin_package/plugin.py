"""Minimal sample plugin for the Humanitarian Databank.

Starter template. Upload the ZIP from the admin plugin management page (needs
PLUGIN_UPLOAD_ENABLED and the System Manager role), or extract it to
Backoffice/plugins/sample_plugin/ and restart the application.
"""
from app.plugins.base import BasePlugin
from typing import List


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
