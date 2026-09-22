"""IFRC Unified Plan and Report plugin."""

from pathlib import Path

from flask import Blueprint

_PLUGIN_DIR = Path(__file__).resolve().parent

bp = Blueprint(
    "upr",
    __name__,
    url_prefix="",
    template_folder=str(_PLUGIN_DIR / "templates"),
)

from plugins.upr import routes  # noqa: E402, F401
from plugins.upr import guidance  # noqa: E402, F401

__all__ = ["bp", "_PLUGIN_DIR"]
