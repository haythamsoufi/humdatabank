"""Helpers for translator language grants and inline review authorization."""

from __future__ import annotations

from typing import Iterable, List, Optional, Set

from flask import current_app
from flask_login import AnonymousUserMixin

from app.extensions import db
from app.i18n import resolve_supported_language
from app.models.rbac import RbacAccessGrant, RbacPermission, RbacRole, RbacUserRole
from app.services.authorization_service import AuthorizationService


TRANSLATOR_ROLE_CODE = 'translator'
REVIEW_PERMISSION = 'translations.review.use'
MANAGE_PERMISSION = 'admin.translations.manage'


def _review_permission_id() -> Optional[int]:
    perm = RbacPermission.query.filter_by(code=REVIEW_PERMISSION).first()
    return int(perm.id) if perm else None


def get_assigned_language_codes(user) -> List[str]:
    """Return language codes granted via scoped RBAC grants."""
    if not user or isinstance(user, AnonymousUserMixin) or not getattr(user, 'is_authenticated', False):
        return []

    perm_id = _review_permission_id()
    if perm_id is None:
        return []

    rows = (
        RbacAccessGrant.query.filter_by(
            principal_type='user',
            principal_id=int(user.id),
            permission_id=perm_id,
            scope_kind='language',
            effect='allow',
        )
        .order_by(RbacAccessGrant.language_code.asc())
        .all()
    )
    return sorted({str(row.language_code).lower() for row in rows if row.language_code})


def user_has_manage_translations(user) -> bool:
    return AuthorizationService.has_rbac_permission(user, MANAGE_PERMISSION)


def user_has_review_permission(user) -> bool:
    if user_has_manage_translations(user):
        return True
    return bool(get_assigned_language_codes(user))


def user_wants_translation_review_tool(user, assigned_languages: Optional[List[str]] = None) -> bool:
    """
    Decide whether the inline review UI (floating button) should be shown.

    This is deliberately separate from *permission*: admins/system managers
    already have permission to use the tool via their role/grants, but the
    UI would be intrusive if shown to every admin by default. Users with
    explicit per-language grants (real translators) get the tool
    automatically since that's the entire point of the assignment. Everyone
    else must opt in via their own Account Settings preference.
    """
    if not user or isinstance(user, AnonymousUserMixin) or not getattr(user, 'is_authenticated', False):
        return False

    languages = assigned_languages if assigned_languages is not None else get_assigned_language_codes(user)
    if languages:
        return True

    return bool(getattr(user, 'translation_review_tool_enabled', False))


def user_can_use_translation_review(user, ui_language: Optional[str] = None) -> bool:
    if not user or isinstance(user, AnonymousUserMixin) or not getattr(user, 'is_authenticated', False):
        return False
    if not current_app.config.get('TRANSLATION_REVIEW_ENABLED', True):
        return False

    supported = current_app.config.get('SUPPORTED_LANGUAGES') or ['en']
    resolved_ui = resolve_supported_language(ui_language or 'en', supported)
    if not resolved_ui or resolved_ui == 'en':
        return False

    if user_has_manage_translations(user):
        return True

    return AuthorizationService.has_rbac_permission(
        user,
        REVIEW_PERMISSION,
        scope={'language_code': resolved_ui},
    )


def user_can_edit_locale(user, locale: str) -> bool:
    if not user or isinstance(user, AnonymousUserMixin) or not getattr(user, 'is_authenticated', False):
        return False
    if user_has_manage_translations(user):
        return True

    supported = current_app.config.get('SUPPORTED_LANGUAGES') or ['en']
    resolved = resolve_supported_language(locale, supported)
    if not resolved or resolved == 'en':
        return False

    return AuthorizationService.has_rbac_permission(
        user,
        REVIEW_PERMISSION,
        scope={'language_code': resolved},
    )


def sync_translator_role(user_id: int) -> None:
    """Grant or revoke the baseline translator role based on language grants."""
    role = RbacRole.query.filter_by(code=TRANSLATOR_ROLE_CODE).first()
    if role is None:
        return

    perm_id = _review_permission_id()
    has_grants = False
    if perm_id is not None:
        has_grants = (
            RbacAccessGrant.query.filter_by(
                principal_type='user',
                principal_id=int(user_id),
                permission_id=perm_id,
                scope_kind='language',
                effect='allow',
            ).first()
            is not None
        )

    link = RbacUserRole.query.filter_by(user_id=int(user_id), role_id=int(role.id)).first()
    if has_grants and link is None:
        db.session.add(RbacUserRole(user_id=int(user_id), role_id=int(role.id)))
    elif not has_grants and link is not None:
        db.session.delete(link)


def set_user_translator_languages(
    user_id: int,
    language_codes: Iterable[str],
    *,
    assigned_by_user_id: Optional[int] = None,
) -> List[str]:
    """Replace a user's per-language translation review grants."""
    perm_id = _review_permission_id()
    if perm_id is None:
        return []

    supported = current_app.config.get('SUPPORTED_LANGUAGES') or ['en']
    normalized: Set[str] = set()
    for raw in language_codes or []:
        resolved = resolve_supported_language(raw, supported)
        if resolved and resolved != 'en':
            normalized.add(resolved)

    existing = RbacAccessGrant.query.filter_by(
        principal_type='user',
        principal_id=int(user_id),
        permission_id=perm_id,
        scope_kind='language',
    ).all()
    existing_by_lang = {str(row.language_code).lower(): row for row in existing if row.language_code}

    for lang in normalized:
        current = existing_by_lang.get(lang)
        if current is None:
            db.session.add(
                RbacAccessGrant(
                    principal_type='user',
                    principal_id=int(user_id),
                    permission_id=perm_id,
                    scope_kind='language',
                    language_code=lang,
                    effect='allow',
                    created_by_user_id=assigned_by_user_id,
                )
            )
        elif (current.effect or 'allow') != 'allow':
            current.effect = 'allow'

    for lang, row in existing_by_lang.items():
        if lang not in normalized:
            db.session.delete(row)

    sync_translator_role(user_id)
    return sorted(normalized)
