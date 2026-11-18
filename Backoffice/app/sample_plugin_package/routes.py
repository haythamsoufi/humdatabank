"""Routes for the sample plugin.

Every plugin MUST serve a settings page at ``/admin/plugins/<plugin_id>/settings``.
Plugin Management links to it, and ``scripts/ci/check_plugin_contract.py`` fails CI
when it is missing or unguarded.
"""
from pathlib import Path

from flask import Blueprint, render_template

from app.plugins.plugin_utils import plugin_admin_route_wrapper, settings_plugin_info

PLUGIN_ID = "sample_plugin"
_PLUGIN_DIR = Path(__file__).resolve().parent

bp = Blueprint(
    PLUGIN_ID,
    __name__,
    url_prefix="",
    template_folder=str(_PLUGIN_DIR / "templates"),
)


def settings_status() -> dict:
    """Values shown on the settings page. Replace with real plugin state."""
    return {"example_setting": "value"}


@bp.route(f"/admin/plugins/{PLUGIN_ID}/settings", methods=["GET"])
@plugin_admin_route_wrapper("Sample Plugin")  # login + admin.plugins.manage + error handling
def settings_page():
    return render_template(
        f"plugins/{PLUGIN_ID}/settings.html",
        settings=settings_status(),
        plugin_info=settings_plugin_info(PLUGIN_ID),
    )
