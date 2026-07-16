"""Audit logging for inline translation review edits."""

from __future__ import annotations

import hashlib
from typing import Optional

from flask import current_app, request
from flask_login import current_user

from app.extensions import db
from app.models.system import AdminActionLog
from app.utils.datetime_helpers import utcnow


def _client_info() -> dict:
    return {
        'ip_address': (request.remote_addr or '0.0.0.0')[:45],
        'user_agent': (request.headers.get('User-Agent') or '')[:2000] or None,
    }


def log_inline_translation_edit(
    *,
    msgid: str,
    locale: str,
    old_value: Optional[str],
    new_value: str,
) -> None:
    if not current_user.is_authenticated:
        return

    msgid_hash = hashlib.sha256(msgid.encode('utf-8')).hexdigest()[:16]
    client = _client_info()
    description = f'Inline translation review edit ({locale}) msgid_hash={msgid_hash}'

    db.session.add(
        AdminActionLog(
            admin_user_id=int(current_user.id),
            action_type='translation_review_edit',
            action_description=description,
            timestamp=utcnow(),
            target_type='translation',
            target_description=f'{locale}:{msgid_hash}',
            ip_address=client['ip_address'],
            user_agent=client['user_agent'],
            endpoint=getattr(request, 'endpoint', None),
            old_values={'locale': locale, 'msgid_hash': msgid_hash, 'msgstr': old_value},
            new_values={'locale': locale, 'msgid_hash': msgid_hash, 'msgstr': new_value},
            risk_level='low',
            requires_review=False,
        )
    )
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.warning('Failed to write translation review audit log', exc_info=True)
