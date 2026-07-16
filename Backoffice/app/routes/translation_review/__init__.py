"""Inline translation review routes."""

from __future__ import annotations

import base64
import hashlib
import os

from flask import Blueprint, current_app, redirect, request, session, url_for
from flask_babel import _
from flask_login import current_user, login_required

from app.extensions import limiter
from app.i18n import get_locale, resolve_supported_language
from app.routes.admin.shared import permission_required
from app.routes.admin.utilities.helpers import _translations_po_path
from app.routes.admin.utilities.translations import _msgid_from_payload, _update_po_translations
from app.services.translation.placeholder_validator import extract_placeholders, validate_placeholders
from app.services.translation_review.assignment_service import (
    user_can_edit_locale,
    user_can_use_translation_review,
    user_has_manage_translations,
    user_has_review_permission,
    user_wants_translation_review_tool,
)
from app.services.translation_review.audit import log_inline_translation_edit
from app.services.translation_review.compile_helper import compile_and_refresh_locale
from app.utils.api_responses import json_auth_required, json_bad_request, json_forbidden, json_ok
from app.utils.request_utils import get_request_data, is_json_request

bp = Blueprint('translation_review', __name__, url_prefix='/translation-review')


def _decode_msgid_arg() -> str | None:
    msgid_b64 = request.args.get('msgid_b64')
    if msgid_b64:
        try:
            return base64.b64decode(msgid_b64).decode('utf-8')
        except Exception:
            return None
    msgid = request.args.get('msgid')
    return msgid if msgid is not None else None


def _resolve_locale(raw_locale: str | None = None) -> str | None:
    supported = current_app.config.get('SUPPORTED_LANGUAGES') or ['en']
    locale = raw_locale or get_locale()
    return resolve_supported_language(locale, supported)


def _read_po_msgstr(msgid: str, locale: str) -> str:
    try:
        import polib  # type: ignore
    except ImportError:
        return ''

    po_file_path = _translations_po_path(locale)
    if not os.path.exists(po_file_path):
        return ''
    try:
        po = polib.pofile(po_file_path)
        entry = po.find(msgid)
        if entry is None:
            return ''
        return entry.msgstr or ''
    except Exception as exc:
        current_app.logger.warning('Failed reading PO entry for %s/%s: %s', locale, msgid[:40], exc)
        return ''


def _require_review_access():
    if not current_user.is_authenticated:
        return json_auth_required(_('Authentication required'))
    if not (user_has_review_permission(current_user) or user_has_manage_translations(current_user)):
        return json_forbidden(_('You do not have permission to use translation review'))
    return None


@bp.route('/toggle', methods=['POST'])
@login_required
def toggle_review_mode():
    if not user_can_use_translation_review(current_user, get_locale()):
        return json_forbidden(_('Translation review is not available for your account or language'))
    if not user_wants_translation_review_tool(current_user):
        return json_forbidden(_('Enable the translation review tool in Account Settings first'))

    data = get_request_data() if request.is_json else {}
    if isinstance(data, dict) and 'active' in data:
        session['translation_review_mode'] = bool(data.get('active'))
    else:
        session['translation_review_mode'] = not bool(session.get('translation_review_mode'))
    session.modified = True
    return json_ok(active=bool(session.get('translation_review_mode')))


@bp.route('/api/string', methods=['GET'])
@login_required
def get_review_string():
    denied = _require_review_access()
    if denied:
        return denied

    msgid = _decode_msgid_arg()
    if not msgid:
        return json_bad_request(_('msgid is required'))

    locale = _resolve_locale(request.args.get('locale'))
    if not locale or locale == 'en':
        return json_bad_request(_('A non-English locale is required'))

    if not user_can_edit_locale(current_user, locale):
        return json_forbidden(_('You do not have permission to edit translations for this language'))

    english = msgid
    current_translation = _read_po_msgstr(msgid, locale)
    from config import Config

    language_display_names = getattr(Config, 'LANGUAGE_DISPLAY_NAMES', {}) or {}

    return json_ok(
        msgid=msgid,
        english=english,
        locale=locale,
        current_translation=current_translation,
        placeholders=extract_placeholders(msgid),
        language_display_name=language_display_names.get(locale) or locale.upper(),
    )


@bp.route('/api/string', methods=['POST'])
@login_required
@limiter.limit('60 per minute')
def save_review_string():
    denied = _require_review_access()
    if denied:
        return denied

    if not is_json_request():
        return json_bad_request(_('JSON request required'))

    data = get_request_data()
    msgid = _msgid_from_payload(data)
    if not msgid:
        return json_bad_request(_('msgid is required'))

    locale = _resolve_locale(data.get('locale'))
    if not locale or locale == 'en':
        return json_bad_request(_('A non-English locale is required'))

    if not user_can_edit_locale(current_user, locale):
        return json_forbidden(_('You do not have permission to edit translations for this language'))

    translation = data.get('translation')
    if translation is None:
        return json_bad_request(_('translation is required'))

    validation = validate_placeholders(msgid, translation)
    if not validation.get('valid'):
        return json_bad_request(validation.get('message') or _('Invalid placeholders'))

    old_value = _read_po_msgstr(msgid, locale)
    updated_count, updated_langs = _update_po_translations(msgid, {locale: translation})
    if updated_count <= 0:
        return json_bad_request(_('No translations were updated'))

    compile_and_refresh_locale(locale)
    log_inline_translation_edit(
        msgid=msgid,
        locale=locale,
        old_value=old_value,
        new_value=translation,
    )

    return json_ok(
        message=_('Translation updated successfully'),
        new_translation=translation,
        updated_languages=updated_langs,
        msgid_hash=hashlib.sha256(msgid.encode('utf-8')).hexdigest()[:16],
    )


@bp.route('/status', methods=['GET'])
@login_required
def review_status():
    locale = _resolve_locale()
    return json_ok(
        enabled=bool(current_app.config.get('TRANSLATION_REVIEW_ENABLED', True)),
        can_use=user_can_use_translation_review(current_user, locale),
        active=bool(session.get('translation_review_mode')),
        locale=locale,
    )
