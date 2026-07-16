"""Flask hooks for inline translation review marker injection."""

from __future__ import annotations

from flask import g, request, session
from flask_login import current_user

from app.i18n import get_locale
from app.services.translation_review.assignment_service import (
    user_can_use_translation_review,
    user_wants_translation_review_tool,
)
from app.services.translation_review.marker import encode, strip

_NON_HTML_PATH_PREFIXES = (
    '/api/',
    '/admin/api/',
    '/mobile/',
    '/swagger',
    '/static/',
    '/favicon.ico',
)

_NON_HTML_ENDPOINT_PREFIXES = (
    'forms_api.',
    'ai.',
    'ai_docs.',
    'mobile.',
    'excel.',
    'public.',
)


def _request_wants_html() -> bool:
    accept = (request.headers.get('Accept') or '').lower()
    if 'application/json' in accept and 'text/html' not in accept:
        return False
    if request.path.startswith(_NON_HTML_PATH_PREFIXES):
        return False
    endpoint = request.endpoint or ''
    if any(endpoint.startswith(prefix) for prefix in _NON_HTML_ENDPOINT_PREFIXES):
        return False
    return request.method in {'GET', 'HEAD', 'POST'}


def _review_mode_requested() -> bool:
    return bool(session.get('translation_review_mode'))


def _should_activate_translation_review() -> bool:
    """Markers are always injected when the user has permission — no session gate.
    The client-side active mode (cursor/hover) is controlled by JS using the session flag."""
    if not _request_wants_html():
        return False
    if not current_user.is_authenticated:
        return False
    if not user_wants_translation_review_tool(current_user):
        return False
    return user_can_use_translation_review(current_user, get_locale())


def maybe_mark(msgid: str, rendered: str) -> str:
    if not msgid or rendered is None:
        return rendered
    try:
        from flask import g, has_request_context

        if not has_request_context():
            return rendered
        if not getattr(g, 'translation_review_active', False):
            return rendered
    except RuntimeError:
        return rendered
    return f'{rendered}{encode(msgid)}'


def install_translation_review_hooks(app) -> None:
    """Wrap gettext callables and register request lifecycle hooks."""

    @app.before_request
    def _activate_translation_review_context():
        g.translation_review_active = _should_activate_translation_review()

    @app.after_request
    def _strip_markers_from_non_html(response):
        if not getattr(g, 'translation_review_active', False):
            return response
        content_type = (response.content_type or '').lower()
        if content_type.startswith('text/html'):
            return response
        if response.direct_passthrough:
            return response
        try:
            data = response.get_data(as_text=True)
        except Exception:
            return response
        cleaned = strip(data)
        if cleaned != data:
            response.set_data(cleaned)
        return response

    _patch_flask_babel_domain()


def _patch_flask_babel_domain() -> None:
    try:
        from flask_babel import Domain
    except ImportError:
        return

    if getattr(Domain, '_translation_review_patched', False):
        return

    original_gettext = Domain.gettext
    original_ngettext = Domain.ngettext
    original_pgettext = Domain.pgettext
    original_npgettext = Domain.npgettext

    def gettext(self, string, **variables):
        result = original_gettext(self, string, **variables)
        return maybe_mark(string, result)

    def ngettext(self, singular, plural, num, **variables):
        result = original_ngettext(self, singular, plural, num, **variables)
        return maybe_mark(singular, result)

    def pgettext(self, context, string, **variables):
        result = original_pgettext(self, context, string, **variables)
        return maybe_mark(string, result)

    def npgettext(self, context, singular, plural, num, **variables):
        result = original_npgettext(self, context, singular, plural, num, **variables)
        return maybe_mark(singular, result)

    Domain.gettext = gettext
    Domain.ngettext = ngettext
    Domain.pgettext = pgettext
    Domain.npgettext = npgettext
    Domain._translation_review_patched = True
