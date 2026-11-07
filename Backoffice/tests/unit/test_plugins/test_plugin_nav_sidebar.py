"""The admin sidebar renders links contributed through BasePlugin.get_nav_items."""
import pytest
from flask import render_template_string

def _render(app, *, is_sm, perms=()):
    with app.test_request_context("/"):
        return render_template_string(
            "{% include 'components/_sidebar_nav_categories.html' with context %}",
            is_system_manager=is_sm,
            has_permission=lambda p: p in perms,
        )


@pytest.mark.unit
def test_decision_maker_link_comes_from_active_ifrc_plugin(app):
    manager = app.plugin_manager
    was_active = "ifrc" in manager.active_plugins
    manager.active_plugins.add("ifrc")
    manager._invalidate_hook_caches()
    try:
        assert "Decision Maker" in _render(app, is_sm=True)
        assert "Decision Maker" not in _render(app, is_sm=False, perms=())
        assert "Decision Maker" in _render(app, is_sm=False, perms=("decisions.view",))

        manager.active_plugins.discard("ifrc")
        manager._invalidate_hook_caches()
        assert "Decision Maker" not in _render(app, is_sm=True)
    finally:
        if was_active:
            manager.active_plugins.add("ifrc")
        else:
            manager.active_plugins.discard("ifrc")
        manager._invalidate_hook_caches()
