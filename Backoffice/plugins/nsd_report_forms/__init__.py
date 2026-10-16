"""NSD Report Forms: field types for the NSD reports and the NSD master import."""
from pathlib import Path

from flask import Blueprint

_PLUGIN_DIR = Path(__file__).resolve().parent

bp = Blueprint(
    "nsd_import",
    __name__,
    url_prefix="/admin/nsd-import",
    template_folder=str(_PLUGIN_DIR / "templates"),
)

from plugins.nsd_report_forms import access_on_create, routes  # noqa: E402, F401

__all__ = ["bp"]
