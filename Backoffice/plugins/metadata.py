"""Shared first-party plugin metadata.

Keep author/homepage/license in one place so Plugin Management, settings pages,
and ``BasePlugin.get_installation_info()`` stay aligned.
"""

from __future__ import annotations

PLUGIN_AUTHOR = "Haytham Alsoufi"
PLUGIN_HOMEPAGE = "https://github.com/haythamsoufi"
PLUGIN_LICENSE = "MIT"

# Plugins that cannot be uninstalled from the UI (tracked product code).
# Other folders under Backoffice/plugins/ may still ship in the image but are
# activation-gated and uninstallable like uploaded plugins.
FIRST_PARTY_PLUGIN_IDS = (
    "interactive_map",
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
