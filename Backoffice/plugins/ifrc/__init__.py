"""IFRC programmes plugin — public dashboards for PPP and later IFRC programmes."""

from pathlib import Path

from flask import Blueprint

_PLUGIN_DIR = Path(__file__).resolve().parent

bp = Blueprint(
    "ifrc",
    __name__,
    url_prefix="",
    template_folder=str(_PLUGIN_DIR / "ppp" / "templates"),
)

from plugins.ifrc import routes  # noqa: E402, F401

__all__ = ["bp", "_PLUGIN_DIR"]
