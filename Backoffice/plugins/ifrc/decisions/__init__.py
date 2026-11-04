"""Decision Maker: configuration-backed decision pages, flags and evidence for the IFRC Network Databank."""

from pathlib import Path

from flask import Blueprint

_PLUGIN_DIR = Path(__file__).resolve().parent
_IFRC_TEMPLATES = _PLUGIN_DIR.parent / "templates"

bp = Blueprint(
    "decisions",
    __name__,
    url_prefix="",
    template_folder=str(_IFRC_TEMPLATES),
)

from plugins.ifrc.decisions import models  # noqa: E402, F401
from plugins.ifrc.decisions import routes  # noqa: E402, F401

__all__ = ["bp", "_PLUGIN_DIR"]
