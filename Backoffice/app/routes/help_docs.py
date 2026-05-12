"""
Help / Documentation pages for all logged-in users.

This mirrors the admin docs UI but is accessible without /admin,
and filters the navigation to only show docs relevant to the user's roles.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, render_template, send_from_directory, url_for
from flask_babel import _
from flask_login import current_user, login_required

from app.services import documentation_service as docs


bp = Blueprint("help_docs", __name__, url_prefix="/help/docs")

VISIBLE_TOP_LEVEL_DIRS = {
    # Keep the help docs UI user-focused. Only user guides are shown here.
    "getting-started",
    "user-guides",
}

def _canonical_doc_path_for_url(doc_path: str) -> str:
    """
    Convert a docs-relative markdown path into a clean, extensionless URL path.

    Examples:
      - "user-guides/common/navigation.md"   -> "user-guides/common/navigation"
      - "user-guides/admin/add-user.fr.md"   -> "user-guides/admin/add-user.fr"
      - "README.md" / "README" / ""          -> ""
    """
    raw = (doc_path or "").strip().lstrip("/").replace("\\", "/")
    if not raw:
        return ""
    if raw.lower() in ("readme", "readme.md"):
        return ""
    if raw.lower().endswith(".md"):
        raw = raw[: -len(".md")]
    return raw

def _build_doc_url(rel: str) -> str:
    clean = _canonical_doc_path_for_url(rel)
    if not clean:
        return url_for("help_docs.index")
    return url_for("help_docs.view_doc", doc_path=clean)


@bp.route("/", methods=["GET"])
@login_required
def index():
    """Main help/documentation index page (for all logged-in users)."""
    root = docs.docs_root()
    if not root.exists():
        abort(404)

    build_doc_url = _build_doc_url
    build_asset_url = lambda rel_asset: url_for("help_docs.asset", asset_path=rel_asset)

    file_path, current_rel = docs.resolve_doc_path(root, "", current_user)
    docs.ensure_doc_page_access(
        current_user,
        current_rel,
        visible_top_level_dirs=VISIBLE_TOP_LEVEL_DIRS,
    )
    nav_categories = docs.build_hierarchical_nav(
        root=root,
        doc_url_builder=build_doc_url,
        visible_top_level_dirs=VISIBLE_TOP_LEVEL_DIRS,
        user=current_user,
    )
    content_html = docs.render_markdown_file(
        root=root,
        file_path=file_path,
        current_rel=current_rel,
        doc_url_builder=build_doc_url,
        asset_url_builder=build_asset_url,
    )
    title = docs.extract_page_title(file_path)
    workflow_id = docs.get_workflow_id_for_doc(file_path, root)

    return render_template(
        "admin/docs/documentation.html",
        title=_("Help"),
        header_title=_("Help"),
        page_title=title,
        nav_categories=nav_categories,
        current_rel=current_rel,
        content_html=content_html,
        workflow_id=workflow_id,
        breadcrumbs=[
            {"name": _("Dashboard"), "url": url_for("main.dashboard")},
            {"name": _("Help")},
        ],
    )


@bp.route("/<path:doc_path>", methods=["GET"])
@login_required
def view_doc(doc_path: str):
    """View a specific documentation file."""
    root = docs.docs_root()
    if not root.exists():
        abort(404)

    requested = (doc_path or "").strip().lstrip("/").replace("\\", "/")
    # Only allow extensionless doc URLs (do not support legacy ".md" URLs).
    if requested.lower().endswith(".md") or requested.lower() in ("readme", "readme.md"):
        abort(404)

    build_doc_url = _build_doc_url
    build_asset_url = lambda rel_asset: url_for("help_docs.asset", asset_path=rel_asset)

    file_path, current_rel = docs.resolve_doc_path(root, doc_path, current_user)
    docs.ensure_doc_page_access(
        current_user,
        current_rel,
        visible_top_level_dirs=VISIBLE_TOP_LEVEL_DIRS,
    )
    nav_categories = docs.build_hierarchical_nav(
        root=root,
        doc_url_builder=build_doc_url,
        visible_top_level_dirs=VISIBLE_TOP_LEVEL_DIRS,
        user=current_user,
    )
    content_html = docs.render_markdown_file(
        root=root,
        file_path=file_path,
        current_rel=current_rel,
        doc_url_builder=build_doc_url,
        asset_url_builder=build_asset_url,
    )
    title = docs.extract_page_title(file_path)
    workflow_id = docs.get_workflow_id_for_doc(file_path, root)

    return render_template(
        "admin/docs/documentation.html",
        title=_("Help"),
        header_title=_("Help"),
        page_title=title,
        nav_categories=nav_categories,
        current_rel=current_rel,
        content_html=content_html,
        workflow_id=workflow_id,
        breadcrumbs=[
            {"name": _("Dashboard"), "url": url_for("main.dashboard")},
            {"name": _("Help")},
        ],
    )


@bp.route("/assets/<path:asset_path>", methods=["GET"])
@login_required
def asset(asset_path: str):
    """Serve static assets (images, etc.) from docs directory."""
    root = docs.docs_root()
    if not root.exists():
        abort(404)

    raw = (asset_path or "").strip().lstrip("/").replace("\\", "/")
    candidate = (root / raw).resolve()
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        abort(404)  # Path traversal attempt (candidate not under root)
    if not candidate.exists() or not candidate.is_file():
        abort(404)

    docs.ensure_docs_asset_access(
        current_user,
        candidate.relative_to(root).as_posix(),
        visible_top_level_dirs=VISIBLE_TOP_LEVEL_DIRS,
    )

    return send_from_directory(root, candidate.relative_to(root).as_posix())
