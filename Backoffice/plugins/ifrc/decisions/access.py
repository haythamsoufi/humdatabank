"""Who may see what. Row filtering happens before any calculation.

The decision layer reuses the Databank's country scope (``DataAccessPolicy``) instead of a parallel
permission model. Aggregates, flags, evidence, exports and chatbot tools are all computed from rows
already filtered here, so a restricted value cannot be recovered from a total.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

VIEW_PERMISSION = "decisions.view"
MANAGE_PERMISSION = "admin.decisions.manage"
_ADMIN_LEVELS = frozenset({"system_manager", "admin"})
_ELEVATED_VISIBILITY = frozenset({"admin"})


@dataclass(frozen=True)
class AccessContext:
    user_id: int | None
    access_level: str  # system_manager | admin | user | public
    allowed_iso3: frozenset[str] | None  # None means every country
    can_view: bool = False
    can_manage: bool = False

    @property
    def authenticated(self) -> bool:
        return self.user_id is not None and self.access_level != "public"

    @property
    def scope_limited(self) -> bool:
        return self.allowed_iso3 is not None

    def can_read_iso3(self, iso3: str | None) -> bool:
        if not self.authenticated or not self.can_view:
            return False
        if self.allowed_iso3 is None:
            return True
        return bool(iso3) and iso3.upper() in self.allowed_iso3

    def filter_rows(self, rows: Iterable[dict[str, Any]], key: str = "ISO3") -> list[dict[str, Any]]:
        return [row for row in rows if self.can_read_iso3(row.get(key))]

    def can_see_decision(self, decision: dict[str, Any]) -> bool:
        if not self.authenticated or not self.can_view:
            return False
        if decision.get("status") not in ("active",) and not self.can_manage:
            return False
        if self.access_level not in set(decision.get("allowed_roles") or ()):
            return False
        if decision.get("visibility") in _ELEVATED_VISIBILITY and self.access_level not in _ADMIN_LEVELS:
            return False
        return True

    def public_view(self) -> dict[str, Any]:
        """Only what the browser needs: no user ids and no country lists."""
        return {"scope_limited": self.scope_limited}


DENIED = AccessContext(user_id=None, access_level="public", allowed_iso3=frozenset())


def resolve_access_context(user: Any = None) -> AccessContext:
    """Build the context for ``user`` (default: the request user). Unknown or failing lookups deny."""
    from flask_login import current_user

    subject = user if user is not None else current_user
    if not getattr(subject, "is_authenticated", False) or getattr(subject, "active", True) is False:
        return DENIED
    try:
        from app.extensions import db
        from app.models.core import Country
        from app.services.data_retrieval.access import build_data_access_policy
        from app.services.organization.authorization_service import AuthorizationService

        policy = build_data_access_policy(subject)
        level = AuthorizationService.access_level(subject)
        if level not in ("system_manager", "admin"):
            level = "user"
        can_view = bool(AuthorizationService.has_rbac_permission(subject, VIEW_PERMISSION)) or level in _ADMIN_LEVELS
        can_manage = bool(AuthorizationService.has_rbac_permission(subject, MANAGE_PERMISSION)) or (
            level == "system_manager"
        )
        allowed = policy.allowed_country_ids()
        if allowed is None:
            iso3s = None
        elif not allowed:
            iso3s = frozenset()
        else:
            iso3s = frozenset(
                str(code).upper()
                for (code,) in db.session.query(Country.iso3).filter(Country.id.in_(allowed)).all()
                if code
            )
        return AccessContext(
            user_id=int(subject.id),
            access_level=level,
            allowed_iso3=iso3s,
            can_view=can_view,
            can_manage=can_manage,
        )
    except Exception:
        import logging

        logging.getLogger(__name__).warning("Decision access resolution failed; denying", exc_info=True)
        return DENIED
