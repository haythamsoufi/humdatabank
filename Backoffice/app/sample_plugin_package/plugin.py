"""Minimal sample plugin for the Humanitarian Databank.

This package is a starter template. After downloading, extract it to the
Backoffice/plugins/ directory as plugins/sample-package/ and upload or
activate it from the admin plugin management page.
"""
from app.plugins.base import BasePlugin
from typing import List


class SamplePackagePlugin(BasePlugin):
    """Minimal plugin with no field types. Use as a starting point for new plugins."""

    @property
    def plugin_id(self) -> str:
        return "sample-package"

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
        return "Humanitarian Databank"

    @property
    def license(self) -> str:
        return "MIT"

    def get_field_types(self) -> List:
        return []
