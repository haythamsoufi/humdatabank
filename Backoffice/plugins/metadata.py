"""Shared first-party plugin metadata.

Keep author/homepage/license in one place so Plugin Management, settings pages,
and ``BasePlugin.get_installation_info()`` stay aligned.
"""

from __future__ import annotations

PLUGIN_AUTHOR = "Haytham Alsoufi"
PLUGIN_HOMEPAGE = "https://github.com/haythamsoufi"
PLUGIN_LICENSE = "MIT"

# Folder names under Backoffice/plugins/ that ship with the app.
FIRST_PARTY_PLUGIN_IDS = (
    "emergency_operations",
    "fdrs",
    "interactive_map",
    "pb_progress",
    "upr",
)


class FirstPartyPluginMetadata:
    """Mixin that stamps first-party author metadata on a ``BasePlugin``."""

    @property
    def author(self) -> str:
        return PLUGIN_AUTHOR

    @property
    def homepage(self) -> str:
        return PLUGIN_HOMEPAGE

    @property
    def license(self) -> str:
        return PLUGIN_LICENSE
