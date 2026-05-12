from app.utils.transactions import request_transaction_rollback
# Backoffice/app/routes/api/quiz.py
"""
Quiz API endpoints.
Part of the /api/v1 blueprint.
"""

from flask import request, current_app
from flask_login import login_required, current_user
from sqlalchemy import desc

# Import the API blueprint from parent
from app.routes.api import api_bp

# Import models
from app.models import User
from app.utils.auth import require_api_key
from app.utils.rate_limiting import api_rate_limit

# Import utility functions
from app.utils.api_helpers import json_response, api_error, get_json_safe
from app.utils.api_responses import require_json_keys
from app import db
from app.utils.request_validation import enforce_csrf_json


@api_bp.route('/quiz/submit-score', methods=['POST'])
@login_required
def submit_quiz_score():
    """Submit quiz score for the current user.
    Authentication: Session (logged-in user). User identity is required to attribute the score.
    """
    try:
        csrf_error = enforce_csrf_json()
        if csrf_error:
            return csrf_error

        data = get_json_safe()
        err = require_json_keys(data, ['score'])
        if err:
            return err

        score = data.get('score', 0)
        if not isinstance(score, int) or score < 0:
            return api_error('Invalid score. Must be a non-negative integer.', 400)

        # Update user's quiz score (additive - accumulates points)
        user = current_user
        if not user:
            return api_error('User not authenticated', 401)

        # Add the new score to existing score
        user.quiz_score = (user.quiz_score or 0) + score
        db.session.flush()

        return json_response({
            'success': True,
            'message': 'Score submitted successfully',
            'total_score': user.quiz_score,
            'points_added': score
        })

    except Exception as e:
        current_app.logger.error(f"Error submitting quiz score: {e}", exc_info=True)
        request_transaction_rollback()
        return api_error('Failed to submit score', 500)


@api_bp.route('/quiz/leaderboard', methods=['GET'])
@require_api_key
@api_rate_limit()
def get_quiz_leaderboard():
    """Get top users on the quiz leaderboard.
    Authentication: API key in Authorization header (Bearer token).
    Returns top users by quiz_score.
    """
    try:
        limit = request.args.get('limit', type=int, default=5)
        if limit < 1 or limit > 100:
            limit = 5  # Default to 5 if invalid

        # Get top users by quiz score, only active users
        top_users = User.query.filter(
            User.active == True,
            User.quiz_score > 0
        ).order_by(
            desc(User.quiz_score),
            User.name.asc()  # Secondary sort by name for consistency
        ).limit(limit).all()

        leaderboard = []
        for rank, user in enumerate(top_users, start=1):
            leaderboard.append({
                'rank': rank,
                'user_id': user.id,
                'name': user.name or user.email.split('@')[0],
                'score': user.quiz_score or 0
            })

        return json_response({
            'success': True,
            'leaderboard': leaderboard,
            'total': len(leaderboard)
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching leaderboard: {e}", exc_info=True)
        return api_error('Failed to fetch leaderboard', 500)
