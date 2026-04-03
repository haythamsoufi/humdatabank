# Backoffice/app/routes/api/common.py
"""
Common Words API endpoints.
Part of the /api/v1 blueprint.
"""

from flask import request, current_app
from flask_login import login_required
from flask_wtf.csrf import generate_csrf

# Import the API blueprint from parent
from app.routes.api import api_bp

# Import models
from app.models import CommonWord
from app.utils.auth import require_api_key

# Import utility functions
from app.utils.api_helpers import json_response, api_error


@api_bp.route('/common-words', methods=['GET'])
@require_api_key
def get_common_words():
    """
    API endpoint to retrieve all common words for tooltips.
    Authentication: API key in Authorization header (Bearer token).
    Query Parameters:
        - language: Language code for translations (optional, defaults to 'en')
    Returns:
        JSON object containing:
        - common_words: List of common word objects with term and meaning
    """
    try:
        # Get language parameter (default to English)
        language = request.args.get('language', 'en')

        # Get all active common words
        common_words = CommonWord.query.filter_by(is_active=True).order_by(CommonWord.term).all()

        # Format response
        formatted_words = []
        for word in common_words:
            formatted_words.append({
                'id': word.id,
                'term': word.term,
                'meaning': word.get_meaning_translation(language) or word.meaning,
                'language': language
            })

        return json_response({
            'success': True,
            'common_words': formatted_words,
            'total': len(formatted_words)
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching common words: {e}", exc_info=True)
        return api_error("Could not fetch common words", 500)


@api_bp.route('/csrf-token', methods=['GET'])
@login_required
def get_csrf_token():
    """
    Issue a CSRF token for session-authenticated clients (e.g. MobileApp).

    The mobile app can call this once after login and send it back on unsafe
    requests via X-CSRFToken.
    """
    try:
        token = generate_csrf()
        return json_response({"success": True, "csrf_token": token})
    except Exception as e:
        current_app.logger.error(f"Error issuing CSRF token: {e}", exc_info=True)
        return api_error("Could not issue CSRF token", 500)
