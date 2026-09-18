"""Federation-wide Databank & Reporting System (FDRS) plugin."""

from pathlib import Path

from flask import Blueprint

_PLUGIN_DIR = Path(__file__).resolve().parent

bp = Blueprint(
    "fdrs",
    __name__,
    url_prefix="",
    template_folder=str(_PLUGIN_DIR / "templates"),
)

from plugins.fdrs import routes  # noqa: E402, F401

__all__ = ["bp", "_PLUGIN_DIR"]
