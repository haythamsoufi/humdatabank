"""IFRC Plan & Budget progress extension — Visuals tool integration."""

from pathlib import Path

from flask import Blueprint

_PLUGIN_DIR = Path(__file__).resolve().parent
_IFRC_TEMPLATES = _PLUGIN_DIR.parent / "templates"

bp = Blueprint(
    "pb_progress",
    __name__,
    url_prefix="/admin/data-exploration",
    template_folder=str(_IFRC_TEMPLATES),
)

settings_bp = Blueprint(
    "pb_progress_settings",
    __name__,
    # Plugin contract: the settings page lives at /admin/plugins/<plugin_id>/settings
    # (the plugin id is "ifrc"; "pb_progress" was a legacy activation token).
    url_prefix="/admin/plugins/ifrc",
    template_folder=str(_IFRC_TEMPLATES),
)

from plugins.ifrc.pb_progress import routes  # noqa: E402, F401

__all__ = ["bp", "settings_bp", "_PLUGIN_DIR"]
