"""IFRC Plan & Budget progress module — self-contained integration for the Visuals tool."""

from flask import Blueprint

bp = Blueprint(
    "pb_progress",
    __name__,
    url_prefix="/admin/data-exploration",
)

from app.pb_progress import routes  # noqa: E402, F401
