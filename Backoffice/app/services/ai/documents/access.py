"""Single authority for "may this principal read this AI document?".

Semantics (enforced identically in SQL for retrieval and in Python for single-document checks)::

    readable(doc, principal) :=
          principal.is_document_admin                                   # admin / system manager / admin.documents.manage / admin.ai.manage
       OR principal.is_internal                                          # server-side jobs (no user)
       OR ( doc.is_public AND role_ok(doc, principal) )                  # world-readable, optionally role-restricted
       OR ( doc.user_id == principal.user_id AND owner_scope_ok(...) )   # uploader, while still in scope

    role_ok        := doc.allowed_roles is NULL  OR  principal.role_tokens ∩ doc.allowed_roles ≠ ∅
                      (an empty list means "nobody"; anonymous principals only carry the token ``public``)
    owner_scope_ok := doc is not tied to a submission country, OR the owner still has access to at least
                      one of the document's countries (an owner who lost country access loses the
                      private submitted document too)

``allowed_roles`` therefore *restricts* who may read a public document and never grants access to a
private one. Country tags on a document are retrieval metadata; they do not widen access.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, FrozenSet, Iterable, Optional

from sqlalchemy import Text, and_, bindparam, cast, exists, false, or_, select, text, true

logger = logging.getLogger(__name__)

ROLE_PUBLIC = "public"


@dataclass(frozen=True)
class DocumentPrincipal:
    user_id: Optional[int] = None
    role_tokens: FrozenSet[str] = frozenset({ROLE_PUBLIC})
    is_document_admin: bool = False
    is_internal: bool = False
    unrestricted_countries: bool = False
    country_ids: FrozenSet[int] = field(default_factory=frozenset)

    @property
    def is_anonymous(self) -> bool:
        return self.user_id is None and not self.is_internal


ANONYMOUS_PRINCIPAL = DocumentPrincipal()
INTERNAL_PRINCIPAL = DocumentPrincipal(
    role_tokens=frozenset({"system_manager"}), is_document_admin=True, is_internal=True, unrestricted_countries=True
)


def _role_tokens(user: Any, access_level: str) -> FrozenSet[str]:
    from app.services.organization.authorization_service import AuthorizationService

    tokens = {str(access_level or "user").strip().lower(), "authenticated"}
    try:
        tokens.update(str(c).strip().lower() for c in AuthorizationService.get_role_codes(user) if c)
    except Exception as exc:
        logger.debug("document principal role codes failed: %s", exc)
    tokens.discard("")
    return frozenset(tokens)


def principal_for_user(user: Any) -> DocumentPrincipal:
    """Build a principal from a Flask-Login user (``None`` / anonymous / inactive => public principal)."""
    if user is None or not getattr(user, "is_authenticated", False) or getattr(user, "active", True) is False:
        return ANONYMOUS_PRINCIPAL

    from app.services.data_retrieval.access import build_data_access_policy
    from app.services.organization.authorization_service import AuthorizationService

    try:
        uid = int(getattr(user, "id", 0) or 0) or None
    except (TypeError, ValueError):
        uid = None
    if uid is None:
        return ANONYMOUS_PRINCIPAL

    level = AuthorizationService.access_level(user)
    doc_admin = level in ("admin", "system_manager")
    if not doc_admin:
        try:
            doc_admin = bool(
                AuthorizationService.has_rbac_permission(user, "admin.documents.manage")
                or AuthorizationService.has_rbac_permission(user, "admin.ai.manage")
            )
        except Exception as exc:
            logger.debug("document admin permission check failed: %s", exc)
    data = build_data_access_policy(user)
    return DocumentPrincipal(
        user_id=uid,
        role_tokens=_role_tokens(user, level),
        is_document_admin=doc_admin,
        unrestricted_countries=data.unrestricted_countries,
        country_ids=data.country_ids,
    )


def _request_cache() -> Optional[dict]:
    try:
        from flask import g, has_request_context

        if not has_request_context():
            return None
        cache = getattr(g, "_ai_doc_principal_cache", None)
        if cache is None:
            cache = {}
            g._ai_doc_principal_cache = cache
        return cache
    except Exception:
        return None


def principal_for_legacy_args(user_id: Optional[int], user_role: Optional[str]) -> DocumentPrincipal:
    """Bridge for callers that still pass ``(user_id, user_role)``.

    When ``user_id`` resolves to a user the role string is ignored and everything is recomputed from the
    database. Without a user id only the internal marker role ``system_manager`` (used by trusted
    server-side jobs) is honoured; any other role string is treated as anonymous.
    """
    if user_id:
        cache = _request_cache()
        key = int(user_id)
        if cache is not None and key in cache:
            return cache[key]
        try:
            from app.extensions import db
            from app.models import User

            user = db.session.get(User, key)
        except Exception as exc:
            logger.debug("principal_for_legacy_args: user lookup failed: %s", exc)
            user = None
        principal = principal_for_user(user) if user is not None else ANONYMOUS_PRINCIPAL
        if cache is not None:
            cache[key] = principal
        return principal
    if (user_role or "").strip().lower() == "system_manager":
        return INTERNAL_PRINCIPAL
    return ANONYMOUS_PRINCIPAL


_ROLE_TOKEN_RE = re.compile(r"^[a-z0-9_]{1,64}$")
MAX_ALLOWED_ROLES = 20


def normalize_allowed_roles(raw: Any) -> tuple[bool, Optional[list]]:
    """Validate admin input for ``AIDocument.allowed_roles``.

    Accepts ``None`` / ``""`` (no role restriction), a list, or a comma-separated string. Returns
    ``(ok, value)`` where ``value`` is ``None`` (unrestricted) or a sorted list of lower-case role tokens
    (``[]`` means nobody, apart from owner and document admins).
    """
    if raw is None:
        return True, None
    if isinstance(raw, str):
        if not raw.strip():
            return True, None
        raw = raw.split(",")
    if not isinstance(raw, (list, tuple, set)):
        return False, None
    tokens = {str(r).strip().lower() for r in raw if str(r).strip()}
    if len(tokens) > MAX_ALLOWED_ROLES or any(not _ROLE_TOKEN_RE.match(t) for t in tokens):
        return False, None
    return True, sorted(tokens)


def _roles_match_python(allowed_roles: Any, tokens: Iterable[str]) -> bool:
    if allowed_roles is None:
        return True
    if not isinstance(allowed_roles, (list, tuple, set)):
        return False
    allowed = {str(r).strip().lower() for r in allowed_roles}
    return bool(allowed & set(tokens))


def _doc_country_ids(doc: Any) -> set:
    ids = set()
    cid = getattr(doc, "country_id", None)
    if cid:
        ids.add(int(cid))
    try:
        for c in getattr(doc, "countries", None) or []:
            if getattr(c, "id", None):
                ids.add(int(c.id))
    except Exception as exc:
        logger.debug("document countries lookup failed: %s", exc)
    return ids


def _owner_scope_ok_python(doc: Any, principal: DocumentPrincipal) -> bool:
    if getattr(doc, "submitted_document_id", None) is None:
        return True
    countries = _doc_country_ids(doc)
    if not countries or principal.unrestricted_countries:
        return True
    return bool(countries & set(principal.country_ids))


def can_read_ai_document(principal_or_user: Any, doc: Any) -> bool:
    """Python-side decision for one already-loaded ``AIDocument``. Deny by default."""
    if doc is None:
        return False
    principal = (
        principal_or_user
        if isinstance(principal_or_user, DocumentPrincipal)
        else principal_for_user(principal_or_user)
    )
    if principal.is_document_admin or principal.is_internal:
        return True
    if getattr(doc, "is_public", False) is True and _roles_match_python(
        getattr(doc, "allowed_roles", None), principal.role_tokens
    ):
        return True
    owner_id = getattr(doc, "user_id", None)
    if principal.user_id is not None and owner_id is not None and int(owner_id) == int(principal.user_id):
        return _owner_scope_ok_python(doc, principal)
    return False


def ai_document_read_filter(principal: DocumentPrincipal):
    """SQLAlchemy predicate over ``AIDocument`` equivalent to :func:`can_read_ai_document`."""
    from app.models.embeddings import AIDocument, ai_document_countries

    if principal.is_document_admin or principal.is_internal:
        return true()

    allowed_null = or_(
        AIDocument.allowed_roles.is_(None),
        cast(AIDocument.allowed_roles, Text) == "null",
    )
    roles = sorted(principal.role_tokens)
    role_ok = or_(
        allowed_null,
        text("(ai_documents.allowed_roles::jsonb ?| CAST(:doc_roles AS text[]))").bindparams(
            bindparam("doc_roles", value=roles, unique=True)
        ),
    )
    public_readable = and_(AIDocument.is_public.is_(True), role_ok)

    if principal.user_id is None:
        return public_readable

    if principal.unrestricted_countries:
        owner_scope_ok = true()
    else:
        allowed = sorted(int(c) for c in principal.country_ids)
        no_country = and_(
            AIDocument.country_id.is_(None),
            ~exists(select(ai_document_countries.c.ai_document_id).where(
                ai_document_countries.c.ai_document_id == AIDocument.id
            )),
        )
        if allowed:
            in_scope = or_(
                AIDocument.country_id.in_(allowed),
                exists(select(ai_document_countries.c.ai_document_id).where(
                    and_(
                        ai_document_countries.c.ai_document_id == AIDocument.id,
                        ai_document_countries.c.country_id.in_(allowed),
                    )
                )),
            )
        else:
            in_scope = false()
        owner_scope_ok = or_(AIDocument.submitted_document_id.is_(None), no_country, in_scope)

    owner_readable = and_(AIDocument.user_id == int(principal.user_id), owner_scope_ok)
    return or_(public_readable, owner_readable)


def apply_document_read_filter(query, principal: DocumentPrincipal):
    """Restrict any query that already joins ``AIDocument`` to documents ``principal`` may read."""
    return query.filter(ai_document_read_filter(principal))
