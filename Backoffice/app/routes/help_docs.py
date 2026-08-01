"""
Help / Documentation pages for all logged-in users.

This mirrors the admin docs UI but is accessible without /admin,
and filters the navigation to only show docs relevant to the user's roles.
"""

from __future__ import annotations

from flask import Blueprint, url_for
from flask_babel import _
from flask_login import login_required

from app.routes.docs._shared import (
    canonical_doc_path_for_url,
    make_build_doc_url,
    register_docs_routes,
)


bp = Blueprint("help_docs", __name__, url_prefix="/help/docs")

VISIBLE_TOP_LEVEL_DIRS = {
    "getting-started",
    "user-guides",
    "data-reporting",
}

# Backward-compatible aliases for tests and callers.
_canonical_doc_path_for_url = canonical_doc_path_for_url
_build_doc_url = make_build_doc_url("help_docs")

register_docs_routes(
    bp,
    login_required,
    visible_top_level_dirs=VISIBLE_TOP_LEVEL_DIRS,
    page_title=_("Help"),
    header_title=_("Help"),
    prefer_user_landing=True,
    asset_cache_max_age=3600,
    breadcrumbs=lambda: [
        {"name": _("Dashboard"), "url": url_for("main.dashboard")},
        {"name": _("Help")},
    ],
)
