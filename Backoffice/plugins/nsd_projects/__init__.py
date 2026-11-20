"""NSD Projects: CBF field types, import, and overview on core project reporting.

Route modules are imported lazily from ``NsdProjectsPlugin.get_blueprint()``.
"""
from pathlib import Path

from flask import Blueprint

_PLUGIN_DIR = Path(__file__).resolve().parent

bp = Blueprint(
    "nsd_import",
    __name__,
    url_prefix="/admin/nsd-import",
    template_folder=str(_PLUGIN_DIR / "templates"),
)


def load_routes() -> None:
    """Register NSD HTTP routes onto ``bp`` (idempotent side-effect imports)."""
    from plugins.nsd_projects import access_on_create  # noqa: F401
    from plugins.nsd_projects import routes  # noqa: F401


__all__ = ["bp", "_PLUGIN_DIR", "load_routes"]
