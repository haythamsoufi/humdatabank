"""Internationalization helpers for Flask-Babel and session activity."""

from datetime import datetime, timezone

from flask import current_app, request, session
from flask_login import current_user

from config import Config


def get_locale():
    """Determine the active locale from session or Accept-Language."""
    supported_langs = current_app.config.get('SUPPORTED_LANGUAGES', Config.LANGUAGES)
    if 'language' in session:
        return session['language']
    return request.accept_languages.best_match(supported_langs) or supported_langs[0]


def update_session_activity():
    """Update the last activity timestamp in the session."""
    if current_user.is_authenticated:
        session['last_activity'] = datetime.now(timezone.utc).isoformat()
        session.permanent = True
