"""
Admin Documentation / Onboarding pages.

This module renders Markdown files stored under Backoffice/docs/
as a navigable documentation area within the admin UI with hierarchical navigation.
"""

from __future__ import annotations

from flask import Blueprint, url_for
from flask_babel import _

from app.routes.admin.shared import admin_permission_required
from app.routes.docs._shared import (
    canonical_doc_path_for_url,
    make_build_doc_url,
    register_docs_routes,
)


bp = Blueprint("admin_docs", __name__, url_prefix="/admin/docs")

VISIBLE_TOP_LEVEL_DIRS = {
    "getting-started",
    "user-guides",
    "data-reporting",
}

# Backward-compatible aliases for tests and callers.
_canonical_doc_path_for_url = canonical_doc_path_for_url
_build_doc_url = make_build_doc_url("admin_docs")

register_docs_routes(
    bp,
    admin_permission_required("admin.docs.view"),
    visible_top_level_dirs=VISIBLE_TOP_LEVEL_DIRS,
    page_title=_("Documentation"),
    prefer_user_landing=False,
    asset_cache_max_age=None,
    breadcrumbs=lambda: [
        {"name": _("Admin"), "url": url_for("admin.admin_dashboard")},
        {"name": _("Documentation")},
    ],
)
