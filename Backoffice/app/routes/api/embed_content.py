"""
Public API endpoint for embed content.
Part of the /api/v1 blueprint.
"""
import uuid

from flask import request, current_app

from app.routes.api import api_bp
from app.models import EmbedContent
from app.utils.auth import require_api_key
from app.utils.rate_limiting import api_rate_limit
from app.utils.api_helpers import json_response, api_error


@api_bp.route('/embed-content', methods=['GET'])
@require_api_key
@api_rate_limit()
def get_embed_content():
    """
    Return active embed content, optionally filtered by category.

    Query params:
        category (str): filter by category slug (e.g. 'global_initiative')
    """
    try:
        category = request.args.get('category', '').strip()

        query = EmbedContent.query.filter_by(is_active=True).order_by(
            EmbedContent.category, EmbedContent.sort_order, EmbedContent.id
        )

        if category:
            query = query.filter_by(category=category)

        items = query.all()

        return json_response({
            'embeds': [item.to_dict() for item in items],
            'total': len(items),
            'category_filter': category or None,
        })
    except Exception as e:
        current_app.logger.error(f"API error fetching embed content: {e}", exc_info=True)
        error_id = str(uuid.uuid4())
        return api_error("Could not fetch embed content", 500, error_id, None)
