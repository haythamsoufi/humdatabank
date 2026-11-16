"""Internationalization helpers for Flask-Babel and session activity."""

from datetime import datetime, timezone

from flask import current_app, g, request, session
from flask_login import current_user

from config import Config

LANGUAGE_COOKIE_NAME = "ui_language"


def resolve_supported_language(language, supported=None):
    """Return a supported language code matching *language*, or None."""
    if supported is None:
        supported = list(current_app.config.get("SUPPORTED_LANGUAGES", Config.LANGUAGES) or [])
    lang_norm = str(language).lower().replace("-", "_")
    base = lang_norm.split("_")[0] if lang_norm else ""

    if language in supported:
        return str(language).lower()
    if lang_norm in supported:
        return lang_norm
    if base and base in supported:
        return base
    for s in supported:
        s_norm = str(s).lower().replace("-", "_")
        if s_norm == lang_norm or (s_norm.split("_")[0] == base and base):
            return str(s).lower()
    return None


def persist_user_preferred_language(user, language_code):
    """Store the user's UI language preference when it changes."""
    if not user or not language_code:
        return False
    try:
        if getattr(user, "preferred_language", None) != language_code:
            user.preferred_language = language_code
            from app.extensions import db

            db.session.commit()
        return True
    except Exception:
        from app.extensions import db

        db.session.rollback()
        current_app.logger.warning(
            "Could not persist preferred language %r for user %s",
            language_code,
            getattr(user, "id", None),
            exc_info=True,
        )
        return False


def seed_session_language_from_user(user):
    """Apply stored user language preference to the current session after login."""
    if not user:
        return
    stored = getattr(user, "preferred_language", None)
    if not stored:
        return
    resolved = resolve_supported_language(stored)
    if resolved:
        session["language"] = resolved
        session.permanent = True
        queue_language_cookie(resolved)


def queue_language_cookie(language_code):
    """Queue the dedicated language cache cookie for this response."""
    resolved = resolve_supported_language(language_code)
    if resolved:
        g.language_cookie_to_set = resolved


def persist_queued_language_cookie(response):
    """Write a queued language cookie without touching it on ordinary requests."""
    language_code = getattr(g, "language_cookie_to_set", None)
    if not language_code:
        return response
    lifetime = current_app.permanent_session_lifetime
    response.set_cookie(
        LANGUAGE_COOKIE_NAME,
        language_code,
        max_age=int(lifetime.total_seconds()),
        secure=bool(current_app.config.get("SESSION_COOKIE_SECURE", False)),
        httponly=True,
        samesite=current_app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
        path="/",
    )
    return response


def get_locale():
    """Determine locale from the dedicated cache, seeding it once when needed."""
    supported_langs = current_app.config.get('SUPPORTED_LANGUAGES', Config.LANGUAGES)
    cached = request.cookies.get(LANGUAGE_COOKIE_NAME)
    if cached:
        resolved = resolve_supported_language(cached, supported_langs)
        if resolved:
            return resolved
    if current_user.is_authenticated:
        stored = getattr(current_user, 'preferred_language', None)
        if stored:
            resolved = resolve_supported_language(stored, supported_langs)
            if resolved:
                queue_language_cookie(resolved)
                return resolved
    if 'language' in session:
        resolved = resolve_supported_language(session['language'], supported_langs)
        if resolved:
            return resolved
    return request.accept_languages.best_match(supported_langs) or supported_langs[0]


def update_session_activity():
    """Update the last activity timestamp in the session."""
    if current_user.is_authenticated:
        session['last_activity'] = datetime.now(timezone.utc).isoformat()
        session.permanent = True
