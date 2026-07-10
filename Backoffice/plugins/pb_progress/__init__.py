"""IFRC Plan & Budget progress extension — Visuals tool integration."""

from pathlib import Path

from flask import Blueprint

_PLUGIN_DIR = Path(__file__).resolve().parent

bp = Blueprint(
    "pb_progress",
    __name__,
    url_prefix="/admin/data-exploration",
    template_folder=str(_PLUGIN_DIR / "templates"),
    static_folder=str(_PLUGIN_DIR / "static"),
    static_url_path="/pb-progress/static",
)

from plugins.pb_progress import routes  # noqa: E402, F401

__all__ = ["bp"]
