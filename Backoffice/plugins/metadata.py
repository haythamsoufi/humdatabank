"""Shared first-party plugin metadata.

Keep author/homepage/license in one place so Plugin Management, settings pages,
and ``BasePlugin.get_installation_info()`` stay aligned.
"""

from __future__ import annotations

PLUGIN_AUTHOR = "Haytham Alsoufi"
PLUGIN_HOMEPAGE = "https://github.com/haythamsoufi"
PLUGIN_LICENSE = "MIT"

# Plugins whose author metadata is stamped by FirstPartyPluginMetadata.
FIRST_PARTY_PLUGIN_IDS = (
    "interactive_map",
)

# Plugins that ship in the application image. Core code imports their modules
# directly (models, Excel routes, scheduler, AI tools), so deleting a bundled
# plugin directory would stop the app from booting. They can be deactivated but
# never uninstalled. tests/unit/test_plugins/test_first_party_plugins.py fails if
# a plugin folder under Backoffice/plugins/ is missing from this tuple.
BUNDLED_PLUGIN_IDS = (
    "emergency_operations",
    "fdrs",
    "ifrc",
    "interactive_map",
    "nsd_report_forms",
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
