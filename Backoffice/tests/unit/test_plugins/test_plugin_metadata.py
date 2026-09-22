"""First-party plugin author/homepage metadata stays consistent."""

from __future__ import annotations

import pytest

from plugins.metadata import (
    FIRST_PARTY_PLUGIN_IDS,
    PLUGIN_AUTHOR,
    PLUGIN_HOMEPAGE,
    PLUGIN_LICENSE,
)

pytestmark = pytest.mark.unit


def test_all_first_party_plugins_credit_haytham_alsoufi(app):
    plugin_manager = getattr(app, "plugin_manager", None)
    assert plugin_manager is not None, "plugin_manager not initialized"

    missing = [plugin_id for plugin_id in FIRST_PARTY_PLUGIN_IDS if plugin_id not in plugin_manager.plugins]
    assert missing == [], f"Expected first-party plugins to be loaded: {missing}"

    for plugin_id in FIRST_PARTY_PLUGIN_IDS:
        plugin = plugin_manager.plugins[plugin_id]
        info = plugin.get_installation_info()
        assert plugin.author == PLUGIN_AUTHOR, plugin_id
        assert plugin.homepage == PLUGIN_HOMEPAGE, plugin_id
        assert plugin.license == PLUGIN_LICENSE, plugin_id
        assert info["author"] == PLUGIN_AUTHOR, plugin_id
        assert info["homepage"] == PLUGIN_HOMEPAGE, plugin_id


def test_settings_plugin_info_uses_live_plugin_metadata(app):
    from app.plugins.plugin_utils import settings_plugin_info

    info = settings_plugin_info("fdrs")
    assert info["plugin_id"] == "fdrs"
    assert info["author"] == PLUGIN_AUTHOR
    assert info["homepage"] == PLUGIN_HOMEPAGE


@pytest.mark.parametrize(
    ("path", "title"),
    [
        ("/admin/plugins/fdrs/settings", b"FDRS Plugin Settings"),
        ("/admin/plugins/upr/settings", b"UPR Plugin Settings"),
        ("/admin/plugins/emergency_operations/settings", b"Emergency Operations Plugin Settings"),
        ("/admin/plugins/interactive_map/settings", b"Interactive Map Plugin Settings"),
        ("/admin/plugins/pb_progress/settings", b"P&amp;B Progress Plugin Settings"),
    ],
)
def test_settings_pages_render_author_homepage(logged_in_sm_client, path, title):
    response = logged_in_sm_client.get(path)
    assert response.status_code == 200
    assert title in response.data
    assert PLUGIN_AUTHOR.encode() in response.data
    assert PLUGIN_HOMEPAGE.encode() in response.data
    assert b"IFRC Development Team" not in response.data
