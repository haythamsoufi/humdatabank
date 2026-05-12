# Backoffice/app/routes/api/resources.py
"""
Resource API endpoints.
Part of the /api/v1 blueprint.
"""

from flask import request, current_app, url_for
import uuid
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

# Import the API blueprint from parent
from app.routes.api import api_bp
from app.utils.sql_utils import safe_ilike_pattern

# Import models
from app.models import Resource, ResourceTranslation
from app.utils.auth import require_api_key
from app.utils.rate_limiting import api_rate_limit

# Import utility functions
from app.utils.api_helpers import json_response, api_error


def _has_thumbnail_with_fallback(resource, language):
    """Check if resource has a thumbnail, with fallback logic."""
    translation = resource.get_translation(language)
    if translation and translation.thumbnail_relative_path:
        return True
    # Fallback to default language
    default_translation = resource.get_translation('en')
    if default_translation and default_translation.thumbnail_relative_path:
        return True
    return False


def _get_thumbnail_url_with_fallback(resource, language):
    """Get thumbnail URL with fallback to default language."""
    translation = resource.get_translation(language)
    if translation and translation.thumbnail_relative_path:
        return url_for('public.download_resource_thumbnail',
                      resource_id=resource.id,
                      language=language,
                      _external=True)
    # Fallback to default language
    default_translation = resource.get_translation('en')
    if default_translation and default_translation.thumbnail_relative_path:
        return url_for('public.download_resource_thumbnail',
                      resource_id=resource.id,
                      language='en',
                      _external=True)
    return None


@api_bp.route('/resources', methods=['GET'])
@require_api_key
@api_rate_limit()
def get_resources():
    """
    API endpoint to retrieve a list of resources.
    Authentication: API key in Authorization header (Bearer token).
    Query Parameters:
        - page: Page number (default: 1)
        - per_page: Items per page (default: 10)
        - search: Search query for resource title
        - resource_type: Filter by resource type ('publication', 'other')
        - language: Language code for translations (default: 'en')
    Returns:
        JSON object containing:
        - resources: List of resource objects with multilingual support
        - total_items: Total number of resources
        - total_pages: Total number of pages
        - current_page: Current page number
        - per_page: Items per page
        - search_query: Search query used (if any)
        - resource_type_filter: Resource type filter applied (if any)
        - language: Language code used for translations
    """
    # Log that we're entering the endpoint
    current_app.logger.debug("Entering resources API endpoint")

    try:
        from app.utils.api_pagination import validate_pagination_params
        page, per_page = validate_pagination_params(request.args, default_per_page=10)
        search_query = request.args.get('search', default='', type=str).strip()
        resource_type_filter = request.args.get('resource_type', default='', type=str).strip()
        language = request.args.get('language', default='en', type=str).strip()

        query = (
            Resource.query.options(joinedload(Resource.resource_subcategory))
            .order_by(Resource.publication_date.desc(), Resource.created_at.desc())
        )

        # Filter by resource type if specified
        if resource_type_filter:
            query = query.filter(Resource.resource_type == resource_type_filter)

        # Search in default title and description
        if search_query:
            safe_pattern = safe_ilike_pattern(search_query)
            query = query.filter(
                or_(
                    Resource.default_title.ilike(safe_pattern),
                    Resource.default_description.ilike(safe_pattern)
                )
            )

        paginated_resources = query.paginate(page=page, per_page=per_page, error_out=False)

        resources_data = []
        for resource in paginated_resources.items:
            # Get translation for the requested language
            translation = resource.get_translation(language)

            # Build resource data with multilingual support
            sub = getattr(resource, 'resource_subcategory', None)
            resource_data = {
                'id': resource.id,
                'resource_type': resource.resource_type,
                'subcategory': (
                    {'id': sub.id, 'name': sub.name, 'display_order': sub.display_order}
                    if sub is not None
                    else None
                ),
                'publication_date': resource.publication_date.isoformat() if resource.publication_date else None,
                'created_at': resource.created_at.isoformat(),
                'updated_at': resource.updated_at.isoformat(),

                # Default/fallback content
                'default_title': resource.default_title,
                'default_description': resource.default_description,

                # Language-specific content
                'title': translation.title if translation else resource.default_title,
                'description': translation.description if translation else resource.default_description,
                'language': language,

                # File information and URLs
                'filename': translation.filename if translation else None,
                'has_file': bool(translation and translation.file_relative_path),
                'has_thumbnail': _has_thumbnail_with_fallback(resource, language),
                'file_available': bool(translation and translation.file_relative_path),
                'download_url': url_for('public.download_resource_file',
                                      resource_id=resource.id,
                                      language=language,
                                      _external=True) if translation and translation.file_relative_path else None,
                'thumbnail_url': _get_thumbnail_url_with_fallback(resource, language),

                # Available languages
                'available_languages': resource.get_available_languages()
            }

            resources_data.append(resource_data)

        # Log before returning response
        current_app.logger.debug(f"Resources API returning {len(resources_data)} items")

        response_data = {
            'resources': resources_data,
            'total_items': paginated_resources.total,
            'total_pages': paginated_resources.pages,
            'current_page': paginated_resources.page,
            'per_page': paginated_resources.per_page,
            'search_query': search_query,
            'resource_type_filter': resource_type_filter,
            'language': language
        }
        return json_response(response_data)
    except Exception as e:
        current_app.logger.error(f"API Error fetching resources: {e}", exc_info=True)
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            f"API Error [ID: {error_id}] fetching resources: {e}",
            exc_info=True,
            extra={'endpoint': '/resources', 'params': dict(request.args)}
        )
        return api_error("Could not fetch resources", 500, error_id, None)
