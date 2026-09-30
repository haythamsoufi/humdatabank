"""Authoritative read-access policy for structured (form) data.

One answer to "which submitted values may this principal read?", shared by AI tools, RAG-adjacent
data tools, and any other server-side data retrieval:

==================  ==========================================  ==============================================
Principal           ``privacy='public'`` items                  non-public (``ifrc_network``) items
==================  ==========================================  ==============================================
anonymous           submitted/approved, any country             never
authenticated user  submitted/approved, any country             only countries the user may access
                                                                (assigned via ``UserEntityPermission``)
admin / countries   submitted/approved, any country             every country (``user_allowed_country_ids``
manager / sys mgr                                               is ``None`` or ``is_admin``)
elevated API key    submitted/approved, any country             every country
==================  ==========================================  ==============================================

Same-organisation e-mail domain alone does **not** widen access: non-public data is scoped to
countries, exactly like ``check_country_access`` and ``get_assignment_indicator_values``.
Draft / saved (not yet submitted) values are only readable for countries the principal may access.

The policy is a small immutable object computed once per request (see :func:`resolve_data_access_policy`)
and enforced **in the query** via :meth:`DataAccessPolicy.apply_privacy_filter`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

from sqlalchemy import false, or_, true

logger = logging.getLogger(__name__)

PRINCIPAL_ANONYMOUS = "anonymous"
PRINCIPAL_USER = "user"
PRINCIPAL_ADMIN = "admin"
PRINCIPAL_SYSTEM_MANAGER = "system_manager"
PRINCIPAL_API_KEY = "api_key"
PRINCIPAL_INTERNAL = "internal"


@dataclass(frozen=True)
class DataAccessPolicy:
    principal: str = PRINCIPAL_ANONYMOUS
    user_id: Optional[int] = None
    unrestricted_countries: bool = False
    country_ids: frozenset = frozenset()

    @property
    def is_anonymous(self) -> bool:
        return self.principal == PRINCIPAL_ANONYMOUS

    @property
    def may_read_any_non_public(self) -> bool:
        return self.unrestricted_countries or bool(self.country_ids)

    def can_read_country(self, country_id: Optional[int]) -> bool:
        if self.is_anonymous or country_id is None:
            return False
        if self.unrestricted_countries:
            return True
        try:
            return int(country_id) in self.country_ids
        except (TypeError, ValueError):
            return False

    def can_read_non_public(self, country_id: Optional[int]) -> bool:
        """Non-public items (and unsubmitted drafts) are readable only for accessible countries."""
        return self.can_read_country(country_id)

    def allowed_country_ids(self) -> Optional[List[int]]:
        """``None`` when unrestricted, else the (possibly empty) list of readable country ids."""
        if self.unrestricted_countries:
            return None
        return sorted(int(c) for c in self.country_ids)

    def visible_items(self, items: Iterable[Any], country_id: Optional[int]) -> List[Any]:
        """Python-side twin of :meth:`apply_privacy_filter` for already-loaded ``FormItem`` rows."""
        if self.can_read_non_public(country_id):
            return list(items)
        return [i for i in items if (getattr(i, "privacy", None) or "").strip().lower() == "public"]

    def privacy_predicate(self, country_col):
        """SQL predicate: public item, or any item in a country this principal may read."""
        from app.services.data_retrieval.shared import form_item_privacy_is_public_expr

        public = form_item_privacy_is_public_expr()
        if self.unrestricted_countries:
            return true()
        if not self.country_ids:
            return public
        return or_(public, country_col.in_(sorted(int(c) for c in self.country_ids)))

    def apply_privacy_filter(self, query, country_col):
        """Filter ``query`` (already joined to ``FormItem`` and the country column) to readable rows."""
        if self.unrestricted_countries:
            return query
        return query.filter(self.privacy_predicate(country_col))

    def apply_public_only(self, query):
        from app.services.data_retrieval.shared import form_item_privacy_is_public_expr

        return query.filter(form_item_privacy_is_public_expr())

    def deny_all(self, query):
        return query.filter(false())


def _principal_for(user, unrestricted: bool) -> str:
    from app.services.organization.authorization_service import AuthorizationService

    if AuthorizationService.is_system_manager(user):
        return PRINCIPAL_SYSTEM_MANAGER
    if AuthorizationService.is_admin(user):
        return PRINCIPAL_ADMIN
    return PRINCIPAL_USER


def build_data_access_policy(user: Any = None, *, elevated_api_key: bool = False) -> DataAccessPolicy:
    """Compute a policy for ``user`` (``None`` / unauthenticated => anonymous, public only)."""
    if elevated_api_key:
        return DataAccessPolicy(principal=PRINCIPAL_API_KEY, unrestricted_countries=True)

    if user is None or not getattr(user, "is_authenticated", False):
        return DataAccessPolicy()
    if getattr(user, "active", True) is False:
        return DataAccessPolicy()

    from app.services.data_retrieval.shared import user_allowed_country_ids
    from app.services.organization.authorization_service import AuthorizationService

    try:
        allowed = user_allowed_country_ids(user)
        unrestricted = allowed is None or bool(AuthorizationService.is_admin(user))
    except Exception as exc:
        logger.warning("build_data_access_policy: country scope failed, denying non-public: %s", exc)
        return DataAccessPolicy(principal=PRINCIPAL_USER, user_id=_uid(user))

    return DataAccessPolicy(
        principal=_principal_for(user, unrestricted),
        user_id=_uid(user),
        unrestricted_countries=unrestricted,
        country_ids=frozenset() if unrestricted else frozenset(int(c) for c in (allowed or ())),
    )


def _uid(user: Any) -> Optional[int]:
    try:
        return int(getattr(user, "id", 0) or 0) or None
    except (TypeError, ValueError):
        return None


def resolve_data_access_policy(user: Any = None) -> DataAccessPolicy:
    """Policy for ``user`` or, by default, the effective request user (session, bearer, or ``g.ai_user_id``).

    Cached on ``flask.g`` per user id so a request computes the country scope once.
    """
    from flask import g, has_request_context

    from app.services.data_retrieval.shared import get_effective_request_user

    explicit = user is not None
    subject = user if explicit else get_effective_request_user()
    elevated = False
    if has_request_context():
        elevated = bool(getattr(g, "api_elevated_data_access", False)) and not explicit
        override = getattr(g, "ai_access_policy", None)
        if not explicit and override is not None and getattr(override, "data", None) is not None:
            return override.data

    cache_key = (_uid(subject) if subject is not None else None, elevated)
    if has_request_context():
        cache = getattr(g, "_data_access_policy_cache", None)
        if cache is None:
            cache = {}
            g._data_access_policy_cache = cache
        if cache_key in cache:
            return cache[cache_key]
        policy = build_data_access_policy(subject, elevated_api_key=elevated)
        cache[cache_key] = policy
        return policy
    return build_data_access_policy(subject, elevated_api_key=elevated)
