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
from app.services.translation.placeholder_validator import (
    extract_placeholders,
    localized_validation_message,
    validate_placeholders,
)
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
    from app.services.translation.catalog_service import get_row, get_msgstr

    row = get_row(msgid, locale)
    current_translation = get_msgstr(msgid, locale) or _read_po_msgstr(msgid, locale)
    machine_suggestion = ''
    try:
        from app.services.translation.result_cache import get_cached

        machine_suggestion = get_cached(msgid, 'en', locale, 'ifrc') or get_cached(msgid, 'en', locale, 'google') or ''
        if row and row.provenance == 'machine' and row.msgstr:
            machine_suggestion = machine_suggestion or row.msgstr
    except Exception:
        current_app.logger.debug('review machine suggestion skipped', exc_info=True)
    from config import Config

    language_display_names = getattr(Config, 'LANGUAGE_DISPLAY_NAMES', {}) or {}

    return json_ok(
        msgid=msgid,
        english=english,
        locale=locale,
        current_translation=current_translation,
        machine_suggestion=machine_suggestion,
        provenance=getattr(row, 'provenance', None) or 'unknown_presumed_machine',
        status=getattr(row, 'status', None) or 'unreviewed',
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
        return json_bad_request(localized_validation_message(validation))

    from app.services.translation.catalog_service import PROVENANCE_HUMAN, get_msgstr

    old_value = get_msgstr(msgid, locale) or _read_po_msgstr(msgid, locale)
    updated_count, updated_langs = _update_po_translations(
        msgid, {locale: translation}, provenance=PROVENANCE_HUMAN
    )
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


@bp.route('/api/queue', methods=['GET'])
@login_required
def review_queue():
    denied = _require_review_access()
    if denied:
        return denied
    locale = _resolve_locale(request.args.get('locale'))
    if not locale or locale == 'en':
        return json_bad_request(_('A non-English locale is required'))
    if not user_can_edit_locale(current_user, locale):
        return json_forbidden(_('You do not have permission to edit translations for this language'))
    from app.services.translation.catalog_service import list_unreviewed

    rows = list_unreviewed(locale, limit=int(request.args.get('limit') or 50))
    return json_ok(
        locale=locale,
        items=[
            {
                'msgid': r.msgid,
                'msgstr': r.msgstr,
                'provenance': r.provenance,
                'status': r.status,
                'engine': r.engine,
            }
            for r in rows
        ],
    )


@bp.route('/api/glossary-candidates', methods=['GET'])
@login_required
def list_glossary_candidates():
    denied = _require_review_access()
    if denied:
        return denied
    from app.models.translation_quality import TranslationGlossaryCandidate

    locale = _resolve_locale(request.args.get('locale'))
    q = TranslationGlossaryCandidate.query.filter_by(status='pending')
    if locale and locale != 'en':
        q = q.filter_by(target_lang=locale)
    rows = q.order_by(TranslationGlossaryCandidate.confidence.desc()).limit(80).all()
    return json_ok(
        items=[
            {
                'id': r.id,
                'source_term': r.source_term,
                'target_term': r.target_term,
                'target_lang': r.target_lang,
                'extractor': r.extractor,
                'confidence': r.confidence,
                'proposed_tier': r.proposed_tier,
                'occurrence_count': r.occurrence_count,
                'evidence': r.evidence,
                'example_sentences': r.example_sentences,
            }
            for r in rows
        ]
    )


@bp.route('/api/glossary-candidates/<int:candidate_id>', methods=['POST'])
@login_required
@limiter.limit('60 per minute')
def decide_glossary_candidate(candidate_id):
    denied = _require_review_access()
    if denied:
        return denied
    if not is_json_request():
        return json_bad_request(_('JSON request required'))
    data = get_request_data() or {}
    accept = bool(data.get('accept'))
    from app.services.translation.glossary_mining import decide_candidate

    ok = decide_candidate(candidate_id, accept=accept, tier=data.get('tier'))
    if not ok:
        return json_bad_request(_('Candidate not found or already reviewed'))
    return json_ok(accepted=accept)


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
