"""Federation-wide Databank & Reporting System (FDRS) plugin.

Route modules are imported lazily from ``FdrsPlugin.get_blueprint()`` so that
importing ``plugins.fdrs.data_quality.*`` (methodology / catalog) does not pull
in admin routes and create a circular import with ``app.services.data_quality``.
"""

from pathlib import Path

from flask import Blueprint

_PLUGIN_DIR = Path(__file__).resolve().parent

bp = Blueprint(
    "fdrs",
    __name__,
    url_prefix="",
    template_folder=str(_PLUGIN_DIR / "templates"),
)

def load_routes() -> None:
    """Register FDRS HTTP routes onto ``bp`` (idempotent side-effect imports)."""
    from plugins.fdrs import routes  # noqa: F401
    from plugins.fdrs import compliance_routes  # noqa: F401
    from plugins.fdrs import service_income_routes  # noqa: F401
    from plugins.fdrs import publication_routes  # noqa: F401
    from plugins.fdrs import document_status_routes  # noqa: F401
    from plugins.fdrs import public_api_routes  # noqa: F401


__all__ = ["bp", "_PLUGIN_DIR", "load_routes"]
