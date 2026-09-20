"""Unit tests for plugins.upr.plugin.UprPlugin — admin-feature blueprint wiring."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestUprPluginBlueprints:
    def test_get_blueprint_returns_main_upr_blueprint(self):
        from plugins.upr.plugin import UprPlugin

        plugin = UprPlugin()
        bp = plugin.get_blueprint()
        assert bp is not None
        assert bp.name == "upr"

    def test_get_additional_blueprints_returns_excel_import_blueprints(self):
        from plugins.upr.plugin import UprPlugin

        plugin = UprPlugin()
        extra = plugin.get_additional_blueprints()
        names = {bp.name for bp in extra}
        assert names == {"upr_excel_import", "upr_excel_import_legacy"}

    def test_is_admin_feature(self):
        from plugins.upr.plugin import UprPlugin

        assert UprPlugin().is_admin_feature() is True
