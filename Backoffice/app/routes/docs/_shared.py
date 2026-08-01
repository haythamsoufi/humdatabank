"""Shared documentation route factory and helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Union

from flask import Blueprint, abort, make_response, render_template, send_from_directory, url_for
from flask_login import current_user

from app.services.documentation import service as docs


def canonical_doc_path_for_url(doc_path: str) -> str:
    """
    Convert a docs-relative markdown path into a clean, extensionless URL path.

    Examples:
      - "getting-started/how-it-works.md"   -> "getting-started/how-it-works"
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


def make_build_doc_url(blueprint_name: str) -> Callable[[str], str]:
    def _build_doc_url(rel: str) -> str:
        clean = canonical_doc_path_for_url(rel)
        if not clean:
            return url_for(f"{blueprint_name}.index")
        return url_for(f"{blueprint_name}.view_doc", doc_path=clean)

    return _build_doc_url


def register_docs_routes(
    bp: Blueprint,
    auth_decorator: Callable,
    *,
    visible_top_level_dirs: Iterable[str],
    page_title: str,
    breadcrumbs: Union[list[dict[str, Any]], Callable[[], list[dict[str, Any]]]],
    header_title: str | None = None,
    prefer_user_landing: bool = False,
    asset_cache_max_age: int | None = None,
) -> None:
    """Register index, view, asset, and PDF export routes on *bp*."""
    visible_dirs = set(visible_top_level_dirs)
    build_doc_url = make_build_doc_url(bp.name)

    def _build_asset_url(rel_asset: str) -> str:
        return url_for(f"{bp.name}.asset", asset_path=rel_asset)

    def _render_docs_page(root: Path, file_path: Path, current_rel: str) -> str:
        docs.ensure_doc_page_access(
            current_user,
            current_rel,
            visible_top_level_dirs=visible_dirs,
        )
        nav_categories = docs.build_hierarchical_nav(
            root=root,
            doc_url_builder=build_doc_url,
            visible_top_level_dirs=visible_dirs,
            user=current_user,
        )
        content_html = docs.render_markdown_file(
            root=root,
            file_path=file_path,
            current_rel=current_rel,
            doc_url_builder=build_doc_url,
            asset_url_builder=_build_asset_url,
        )
        title = docs.extract_page_title(file_path)
        workflow_id = docs.get_workflow_id_for_doc(file_path, root)
        template_kwargs: dict[str, Any] = {
            "title": page_title,
            "page_title": title,
            "nav_categories": nav_categories,
            "current_rel": current_rel,
            "content_html": content_html,
            "workflow_id": workflow_id,
            "breadcrumbs": breadcrumbs() if callable(breadcrumbs) else breadcrumbs,
        }
        if header_title is not None:
            template_kwargs["header_title"] = header_title
        return render_template("admin/docs/documentation.html", **template_kwargs)

    @bp.route("/export.pdf", methods=["GET"])
    @auth_decorator
    def export_pdf_index():
        """Download the documentation index as PDF."""
        if not docs.is_pdf_export_enabled():
            abort(404)
        root = docs.docs_root()
        if not root.exists():
            abort(404)
        from app.services.documentation.pdf_service import send_doc_pdf

        return send_doc_pdf(
            root=root,
            doc_path="",
            user=current_user,
            visible_top_level_dirs=visible_dirs,
            doc_url_builder=build_doc_url,
            prefer_user_landing=prefer_user_landing,
        )

    @bp.route("/<path:doc_path>/export.pdf", methods=["GET"])
    @auth_decorator
    def export_pdf_doc(doc_path: str):
        """Download a documentation page as PDF."""
        if not docs.is_pdf_export_enabled():
            abort(404)
        root = docs.docs_root()
        if not root.exists():
            abort(404)

        requested = (doc_path or "").strip().lstrip("/").replace("\\", "/")
        if requested.lower().endswith(".md") or requested.lower() in ("readme", "readme.md"):
            abort(404)

        from app.services.documentation.pdf_service import send_doc_pdf

        return send_doc_pdf(
            root=root,
            doc_path=doc_path,
            user=current_user,
            visible_top_level_dirs=visible_dirs,
            doc_url_builder=build_doc_url,
            prefer_user_landing=prefer_user_landing,
        )

    @bp.route("/", methods=["GET"])
    @auth_decorator
    def index():
        """Main documentation index page."""
        root = docs.docs_root()
        if not root.exists():
            abort(404)

        file_path, current_rel = docs.resolve_doc_path(
            root, "", current_user, prefer_user_landing=prefer_user_landing
        )
        return _render_docs_page(root, file_path, current_rel)

    @bp.route("/<path:doc_path>", methods=["GET"])
    @auth_decorator
    def view_doc(doc_path: str):
        """View a specific documentation file."""
        root = docs.docs_root()
        if not root.exists():
            abort(404)

        requested = (doc_path or "").strip().lstrip("/").replace("\\", "/")
        if requested.lower().endswith(".md") or requested.lower() in ("readme", "readme.md"):
            abort(404)

        file_path, current_rel = docs.resolve_doc_path(
            root, doc_path, current_user, prefer_user_landing=prefer_user_landing
        )
        return _render_docs_page(root, file_path, current_rel)

    @bp.route("/assets/<path:asset_path>", methods=["GET"])
    @auth_decorator
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
            abort(404)
        if not candidate.exists() or not candidate.is_file():
            abort(404)

        docs.ensure_docs_asset_access(
            current_user,
            candidate.relative_to(root).as_posix(),
            visible_top_level_dirs=visible_dirs,
        )

        response = make_response(send_from_directory(root, candidate.relative_to(root).as_posix()))
        if asset_cache_max_age is not None:
            response.headers["Cache-Control"] = f"private, max-age={asset_cache_max_age}"
        return response
