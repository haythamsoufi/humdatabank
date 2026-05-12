"""
Admin routes for managing embed content (Power BI iframes, etc.)
served to the public website.
"""
from flask import Blueprint, render_template, request, current_app
from app.routes.admin.shared import permission_required
from app.utils.request_utils import is_json_request
from app.utils.api_responses import json_ok, json_bad_request, json_not_found, json_server_error
from app import db
from app.models import EmbedContent
from app.models.embed_content import validate_embed_url, validate_embed_category, validate_aspect_ratio, PAGE_SLOTS

ALLOWED_EMBED_TYPES = frozenset({'powerbi', 'tableau', 'iframe'})

bp = Blueprint("embed_management", __name__, url_prefix="/admin")


@bp.route("/embed-content", methods=["GET"])
@permission_required('admin.resources.manage')
def manage_embed_content():
    """List all embed content items."""
    try:
        items = EmbedContent.query.order_by(
            EmbedContent.category, EmbedContent.sort_order, EmbedContent.id
        ).all()

        if is_json_request():
            return json_ok(items=[i.to_dict() for i in items])

        categories = db.session.query(EmbedContent.category).distinct().all()
        category_list = sorted(set(c[0] for c in categories)) if categories else []

        return render_template(
            "admin/embed_content/manage_embed_content.html",
            items=items,
            categories=category_list,
            title="Manage Embed Content",
        )
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error loading embed content: {e}", exc_info=True)
        if is_json_request():
            return json_server_error("Failed to load embed content")
        return render_template(
            "admin/embed_content/manage_embed_content.html",
            items=[],
            categories=[],
            title="Manage Embed Content",
            error="Failed to load embed content",
        )


@bp.route("/embed-content/create", methods=["POST"])
@permission_required('admin.resources.manage')
def create_embed_content():
    """Create a new embed content item."""
    try:
        data = request.get_json(silent=True) or {}
        current_app.logger.debug("embed-content/create payload: %s", {k: v for k, v in data.items() if k != 'embed_url'} if data else data)
        title = (data.get('title') or '').strip()
        embed_url = (data.get('embed_url') or '').strip()
        embed_type = (data.get('embed_type') or 'powerbi').strip().lower()

        cat_ok, category, cat_err = validate_embed_category(
            (data.get('category') or 'global_initiative').strip()
        )
        if not cat_ok:
            return json_bad_request(cat_err)

        if embed_type not in ALLOWED_EMBED_TYPES:
            return json_bad_request("Invalid embed type")
        if not title:
            return json_bad_request("Title is required")
        if len(title) > 255:
            return json_bad_request("Title must be 255 characters or fewer")
        if not embed_url:
            return json_bad_request("Embed URL is required")

        url_valid, url_or_error, snippet_ratio = validate_embed_url(embed_url, embed_type)
        if not url_valid:
            return json_bad_request(url_or_error)
        embed_url = url_or_error

        aspect_ratio = validate_aspect_ratio(data.get('aspect_ratio'))
        if aspect_ratio is None and snippet_ratio:
            aspect_ratio = snippet_ratio

        page_slot = (data.get('page_slot') or '').strip().lower() or None
        if page_slot and page_slot not in PAGE_SLOTS:
            return json_bad_request(f"Invalid page slot. Allowed: {', '.join(PAGE_SLOTS)}")

        max_order = db.session.query(db.func.max(EmbedContent.sort_order)).filter_by(
            category=category
        ).scalar() or 0

        item = EmbedContent(
            title=title,
            description=(data.get('description') or '').strip()[:2000] or None,
            category=category,
            embed_url=embed_url,
            embed_type=embed_type,
            aspect_ratio=aspect_ratio,
            page_slot=page_slot,
            is_active=data.get('is_active', True),
            sort_order=max_order + 1,
        )
        db.session.add(item)
        db.session.commit()

        return json_ok(item=item.to_dict(), message="Embed content created")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating embed content: {e}", exc_info=True)
        return json_server_error("Failed to create embed content")


@bp.route("/embed-content/<int:item_id>", methods=["PUT", "PATCH"])
@permission_required('admin.resources.manage')
def update_embed_content(item_id):
    """Update an existing embed content item."""
    try:
        item = db.session.get(EmbedContent, item_id)
        if not item:
            return json_not_found("Embed content not found")

        data = request.get_json(silent=True) or {}

        if 'title' in data:
            title = (data['title'] or '').strip()
            if not title:
                return json_bad_request("Title cannot be empty")
            if len(title) > 255:
                return json_bad_request("Title must be 255 characters or fewer")
            item.title = title

        if 'embed_url' in data:
            embed_url = (data['embed_url'] or '').strip()
            if not embed_url:
                return json_bad_request("Embed URL cannot be empty")
            eff_type = (data.get('embed_type') or item.embed_type or 'powerbi').strip().lower()
            url_valid, url_or_error, snippet_ratio = validate_embed_url(embed_url, eff_type)
            if not url_valid:
                return json_bad_request(url_or_error)
            item.embed_url = url_or_error
            if 'aspect_ratio' not in data and snippet_ratio:
                item.aspect_ratio = snippet_ratio

        if 'description' in data:
            item.description = (data['description'] or '').strip()[:2000] or None
        if 'category' in data:
            cat_ok, cat_slug, cat_err = validate_embed_category((data['category'] or '').strip())
            if not cat_ok:
                return json_bad_request(cat_err)
            item.category = cat_slug
        if 'embed_type' in data:
            val = (data['embed_type'] or 'powerbi').strip().lower()
            if val not in ALLOWED_EMBED_TYPES:
                return json_bad_request("Invalid embed type")
            item.embed_type = val
            if 'embed_url' not in data:
                url_valid, url_or_error, _ = validate_embed_url(item.embed_url, val)
                if not url_valid:
                    return json_bad_request(url_or_error)
        if 'aspect_ratio' in data:
            item.aspect_ratio = validate_aspect_ratio(data['aspect_ratio'])
        if 'page_slot' in data:
            ps = (data['page_slot'] or '').strip().lower() or None
            if ps and ps not in PAGE_SLOTS:
                return json_bad_request(f"Invalid page slot. Allowed: {', '.join(PAGE_SLOTS)}")
            item.page_slot = ps
        if 'is_active' in data:
            item.is_active = bool(data['is_active'])
        if 'sort_order' in data:
            try:
                item.sort_order = max(0, min(int(data['sort_order']), 9999))
            except (ValueError, TypeError):
                return json_bad_request("Invalid sort order")

        db.session.commit()
        return json_ok(item=item.to_dict(), message="Embed content updated")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating embed content: {e}", exc_info=True)
        return json_server_error("Failed to update embed content")


@bp.route("/embed-content/<int:item_id>", methods=["DELETE"])
@permission_required('admin.resources.manage')
def delete_embed_content(item_id):
    """Delete an embed content item."""
    try:
        item = db.session.get(EmbedContent, item_id)
        if not item:
            return json_not_found("Embed content not found")

        db.session.delete(item)
        db.session.commit()
        return json_ok(message="Embed content deleted")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting embed content: {e}", exc_info=True)
        return json_server_error("Failed to delete embed content")


@bp.route("/embed-content/reorder", methods=["POST"])
@permission_required('admin.resources.manage')
def reorder_embed_content():
    """Reorder embed content items within a category."""
    try:
        data = request.get_json(silent=True) or {}
        order = data.get('order', [])

        if not order or not isinstance(order, list):
            return json_bad_request("Order list is required")

        if len(order) > 500:
            return json_bad_request("Too many items in order list")

        for idx, item_id in enumerate(order):
            if not isinstance(item_id, int):
                continue
            item = db.session.get(EmbedContent, item_id)
            if item:
                item.sort_order = idx

        db.session.commit()
        return json_ok(message="Order updated")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error reordering embed content: {e}", exc_info=True)
        return json_server_error("Failed to reorder embed content")
