# ========== Authorization Service ==========
"""
Centralized authorization service for the application.
Consolidates all authorization logic into a single source of truth.

This service replaces scattered authorization decorators and checks across:
- app/utils/form_authorization.py
- app/routes/admin/shared.py
- Inline authorization checks throughout routes

Usage:
    from app.services.authorization_service import AuthorizationService

    # Use decorators
    @AuthorizationService.admin_required
    def my_admin_route():
        pass

    # Check permissions directly
    if AuthorizationService.can_edit_assignment(aes, current_user):
        # Allow edit
"""

from functools import wraps
from flask import flash, redirect, url_for, current_app, request
from flask_login import current_user, login_user
from typing import Any, Dict, List, Optional
from app.models import PublicSubmission, User
from app.models.assignments import AssignmentEntityStatus


def _request_g():
    """Return Flask g if in request context, else None. Avoids repeating try/except in every method."""
    try:
        from flask import g
        return g
    except (ImportError, RuntimeError):
        return None


def _rbac_cache_get(g, cache_attr: str, key: Any) -> Optional[Any]:
    """Get value from request-local RBAC cache. Returns None if not found or on error."""
    if g is None:
        return None
    try:
        cache = getattr(g, cache_attr, None)
        if cache is None:
            return None
        return cache.get(key)
    except Exception as e:
        current_app.logger.debug("RBAC cache get failed: %s", e, exc_info=True)
        return None


def _rbac_cache_set(g, cache_attr: str, key: Any, value: Any) -> None:
    """Set value in request-local RBAC cache. No-op on error."""
    if g is None:
        return
    try:
        if not hasattr(g, cache_attr):
            setattr(g, cache_attr, {})
        getattr(g, cache_attr)[key] = value
    except Exception as e:
        current_app.logger.debug("RBAC cache set failed: %s", e, exc_info=True)


class AuthorizationService:
    """Unified authorization service for all access control decisions."""

    # Role fallback when permissions are not seeded yet
    ADMIN_ROLE_PREFIXES = ("admin_",)
    ADMIN_ROLE_CODES = {"admin_core"}

    # ========== RBAC Role Checking (legacy-free) ==========
    #
    # Legacy `User.role` and `can_manage_*` flags are removed. All authorization
    # decisions are made using RBAC roles/permissions (plus entity permissions).

    @staticmethod
    def has_role(user, role_code: str) -> bool:
        """Check if the user has an RBAC role by code."""
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if not isinstance(role_code, str) or not role_code.strip():
            return False
        role_code = role_code.strip()

        # Avoid DetachedInstanceError in edge/test scenarios by reading identity safely.
        user_id = 0
        try:
            from sqlalchemy import inspect as _sa_inspect
            ident = _sa_inspect(user).identity  # type: ignore[arg-type]
            if ident and ident[0]:
                user_id = int(ident[0])
        except Exception as e:
            try:
                user_id = int(getattr(user, "id", 0) or 0)
            except (ValueError, TypeError):
                user_id = 0

        g = _request_g()
        cache_key = ("rbac_has_role", user_id, role_code)
        cached = _rbac_cache_get(g, "_rbac_role_cache", cache_key)
        if cached is not None:
            return bool(cached)

        has = False
        try:
            from app.models.rbac import RbacUserRole, RbacRole
            has = (
                RbacUserRole.query.join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                .filter(RbacUserRole.user_id == user_id, RbacRole.code == role_code)
                .first()
                is not None
            )
        except Exception as e:
            current_app.logger.debug("has_role check failed: %s", e)
            has = False

        _rbac_cache_set(g, "_rbac_role_cache", cache_key, has)
        return bool(has)

    @staticmethod
    def is_system_manager(user) -> bool:
        """System Manager is the RBAC superuser."""
        return AuthorizationService.has_role(user, "system_manager")

    @staticmethod
    def is_admin(user) -> bool:
        """
        Admin = any user with at least one admin permission (or system manager).

        Note: specific pages are still guarded by granular `admin.*` permissions.
        """
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if AuthorizationService.is_system_manager(user):
            return True
        # If permissions aren't seeded yet, fall back to role-based admin detection
        if not AuthorizationService._permissions_seeded():
            return AuthorizationService._has_admin_role(user)
        # Prefer a prefix-based check to avoid a brittle hardcoded gate list.
        return AuthorizationService._has_any_admin_permission(user)

    @staticmethod
    def access_level(user) -> str:
        """
        Return a stable access classification derived from RBAC.

        Values:
        - public (not authenticated)
        - system_manager
        - admin
        - focal_point (assignment editor/submitter)
        - user
        """
        if not user or not getattr(user, "is_authenticated", False):
            return "public"
        if AuthorizationService.is_system_manager(user):
            return "system_manager"
        if AuthorizationService.is_admin(user):
            return "admin"
        if AuthorizationService.has_role(user, "assignment_editor_submitter"):
            return "focal_point"
        return "user"

    @staticmethod
    def get_role_codes(user) -> List[str]:
        """Return RBAC role codes for one user (cached per-request)."""
        if not user or not getattr(user, "is_authenticated", False):
            return []
        user_id = int(getattr(user, "id", 0) or 0)
        if not user_id:
            return []

        g = _request_g()
        cached = _rbac_cache_get(g, "_rbac_role_codes_cache", user_id)
        if cached is not None:
            return list(cached)

        codes: List[str] = []
        try:
            from app.models.rbac import RbacUserRole, RbacRole
            rows = (
                RbacUserRole.query.join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                .with_entities(RbacRole.code)
                .filter(RbacUserRole.user_id == user_id)
                .all()
            )
            codes = [r[0] for r in rows if r and r[0]]
        except Exception as e:
            current_app.logger.debug("RBAC role codes fetch failed for user %s: %s", user_id, e)
            codes = []

        _rbac_cache_set(g, "_rbac_role_codes_cache", user_id, list(codes))
        return list(codes)

    @staticmethod
    def _get_role_ids_for_user_id(user_id: int) -> List[int]:
        """
        Return RBAC role IDs for a user (cached per-request).

        This is a low-level helper used by permission/grant evaluation to avoid
        repeating the same `rbac_user_role` query many times during one request.
        """
        uid = int(user_id or 0)
        if not uid:
            return []

        g = _request_g()
        cached = _rbac_cache_get(g, "_rbac_role_ids_cache", uid)
        if cached is not None:
            return [int(x) for x in (cached or []) if x is not None]

        role_ids: List[int] = []
        try:
            from app.models.rbac import RbacUserRole
            rows = RbacUserRole.query.with_entities(RbacUserRole.role_id).filter(RbacUserRole.user_id == uid).all()
            role_ids = [int(r[0]) for r in rows if r and r[0] is not None]
        except Exception as e:
            current_app.logger.debug("RBAC role IDs fetch failed for user %s: %s", uid, e)
            role_ids = []

        _rbac_cache_set(g, "_rbac_role_ids_cache", uid, list(role_ids))
        return list(role_ids)

    @staticmethod
    def _permissions_seeded() -> bool:
        """Return True if RBAC permissions exist in DB (best-effort)."""
        try:
            from app.models.rbac import RbacPermission
            return RbacPermission.query.first() is not None
        except Exception as e:
            current_app.logger.debug("RBAC permissions check failed (tables may not exist): %s", e)
            return False

    @staticmethod
    def _has_admin_role(user) -> bool:
        """Return True if user has any admin-role code (fallback for bootstrap)."""
        if not user or not getattr(user, "is_authenticated", False):
            return False
        try:
            role_codes = AuthorizationService.get_role_codes(user)
        except Exception as e:
            current_app.logger.debug("get_role_codes failed: %s", e)
            return False
        for code in role_codes:
            if not code:
                continue
            code_str = str(code)
            if code_str in AuthorizationService.ADMIN_ROLE_CODES:
                return True
            if any(code_str.startswith(prefix) for prefix in AuthorizationService.ADMIN_ROLE_PREFIXES):
                return True
        return False

    @staticmethod
    def _has_any_admin_permission(user) -> bool:
        """
        Return True if user has ANY permission whose code starts with 'admin.'.

        This avoids having to keep ADMIN_GATE_PERMISSIONS perfectly in sync with
        the ever-growing set of admin permissions.
        """
        if not user or not getattr(user, "is_authenticated", False):
            return False

        g = _request_g()
        # Avoid DetachedInstanceError in edge/test scenarios by reading identity safely.
        user_id = 0
        try:
            from sqlalchemy import inspect as _sa_inspect
            ident = _sa_inspect(user).identity  # type: ignore[arg-type]
            if ident and ident[0]:
                user_id = int(ident[0])
        except Exception as e:
            try:
                user_id = int(getattr(user, "id", 0) or 0)
            except (ValueError, TypeError):
                user_id = 0
        if not user_id:
            return False

        cached = _rbac_cache_get(g, "_rbac_is_admin_cache", user_id)
        if cached is not None:
            return bool(cached)

        try:
            from app.models.rbac import RbacUserRole, RbacRolePermission, RbacPermission, RbacAccessGrant
            from app import db
        except Exception as e:
            current_app.logger.debug("has_rbac_permission import/query failed: %s", e)
            return False

        # Role-based permissions
        has_admin = (
            db.session.query(RbacPermission.id)
            .select_from(RbacUserRole)
            .join(RbacRolePermission, RbacUserRole.role_id == RbacRolePermission.role_id)
            .join(RbacPermission, RbacRolePermission.permission_id == RbacPermission.id)
            .filter(RbacUserRole.user_id == user_id)
            .filter(RbacPermission.code.like("admin.%"))
            .first()
            is not None
        )

        # Scoped grants (allow) can also make a user an admin, but ONLY if the
        # grant is GLOBAL. Entity/template/assignment-scoped admin grants should
        # not classify the user as an admin, otherwise the UI/admin gating can
        # become inconsistent with route-level checks (which are typically global).
        if not has_admin:
            try:
                role_ids = AuthorizationService._get_role_ids_for_user_id(user_id)
                principal_filters = [
                    db.and_(RbacAccessGrant.principal_type == "user", RbacAccessGrant.principal_id == user_id),
                ]
                for rid in role_ids:
                    principal_filters.append(db.and_(RbacAccessGrant.principal_type == "role", RbacAccessGrant.principal_id == int(rid)))

                has_admin = (
                    db.session.query(RbacAccessGrant.id)
                    .join(RbacPermission, RbacAccessGrant.permission_id == RbacPermission.id)
                    .filter(db.or_(*principal_filters))
                    .filter(RbacAccessGrant.effect == "allow")
                    .filter(RbacAccessGrant.scope_kind == "global")
                    .filter(RbacPermission.code.like("admin.%"))
                    .first()
                    is not None
                )
            except Exception as e:
                current_app.logger.debug("is_admin query failed: %s", e)
                has_admin = False

        if g is not None:
            _rbac_cache_set(g, "_rbac_is_admin_cache", user_id, bool(has_admin))
        return bool(has_admin)

    @staticmethod
    def prefetch_role_codes(user_ids: List[int]) -> Dict[int, List[str]]:
        """
        Bulk-load RBAC role codes for many users in one query.

        Returns: {user_id: [role_code, ...]}
        """
        out: Dict[int, List[str]] = {}
        ids = [int(x) for x in (user_ids or []) if x is not None]
        if not ids:
            return out
        try:
            from app.models.rbac import RbacUserRole, RbacRole
            rows = (
                RbacUserRole.query.join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                .with_entities(RbacUserRole.user_id, RbacRole.code)
                .filter(RbacUserRole.user_id.in_(ids))
                .all()
            )
            for uid, code in rows:
                if uid is None or not code:
                    continue
                out.setdefault(int(uid), []).append(str(code))
        except Exception as e:
            current_app.logger.debug("get_user_role_codes failed: %s", e)
            return {}
        return out

    # ========== RBAC (Granular permissions) ==========

    @staticmethod
    def has_rbac_permission(
        user,
        permission_code: str,
        *,
        scope: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Check a granular RBAC permission code (e.g., 'admin.users.view').

        Scope keys (optional):
          - entity_type, entity_id
          - template_id
          - assigned_form_id
        """
        if not user or not getattr(user, "is_authenticated", False):
            return False

        # Superuser shortcut
        if AuthorizationService.is_system_manager(user):
            return True

        if not isinstance(permission_code, str) or not permission_code.strip():
            return False
        permission_code = permission_code.strip()

        scope = scope or {}
        entity_type = scope.get("entity_type")
        entity_id = scope.get("entity_id")
        template_id = scope.get("template_id")
        assigned_form_id = scope.get("assigned_form_id")

        # Avoid DetachedInstanceError in edge/test scenarios by reading identity safely.
        user_id = 0
        try:
            from sqlalchemy import inspect as _sa_inspect
            ident = _sa_inspect(user).identity  # type: ignore[arg-type]
            if ident and ident[0]:
                user_id = int(ident[0])
        except Exception as e:
            try:
                user_id = int(getattr(user, "id", 0) or 0)
            except (ValueError, TypeError):
                user_id = 0

        g = _request_g()
        cache_key = (
            user_id,
            permission_code,
            str(entity_type or ""),
            int(entity_id or 0),
            int(template_id or 0),
            int(assigned_form_id or 0),
        )
        cached = _rbac_cache_get(g, "_rbac_cache", cache_key)
        if cached is not None:
            return bool(cached)

        try:
            from app.models.rbac import (
                RbacPermission,
                RbacRolePermission,
                RbacAccessGrant,
            )
            from app import db
        except (ImportError, Exception) as e:
            current_app.logger.debug("RBAC import failed (tables may not exist): %s", e)
            return False

        # 1) Resolve permission_id (cache per-request)
        perm_id = _rbac_cache_get(g, "_rbac_permission_id_cache", permission_code)
        if perm_id is None:
            perm = RbacPermission.query.filter_by(code=permission_code).first()
            perm_id = int(perm.id) if perm else None
            if perm_id is not None:
                _rbac_cache_set(g, "_rbac_permission_id_cache", permission_code, perm_id)

        if perm_id is None:
            # Unknown permission code
            # In development/staging this is usually a typo or a missing seed.
            # Log once per request per permission code to avoid log spam.
            try:
                from flask import current_app
                debug = bool(getattr(current_app, "debug", False)) or bool(current_app.config.get("DEBUG", False))
            except Exception as e:
                current_app.logger.debug("DEBUG config check failed: %s", e)
                debug = False
            if debug:
                try:
                    if g is not None:
                        if not hasattr(g, "_rbac_unknown_permissions"):
                            g._rbac_unknown_permissions = set()
                        if permission_code not in g._rbac_unknown_permissions:
                            g._rbac_unknown_permissions.add(permission_code)
                            try:
                                from flask import current_app
                                current_app.logger.warning(
                                    f"RBAC: unknown permission code '{permission_code}' (seed missing or typo)."
                                )
                            except Exception as log_e:
                                current_app.logger.debug("RBAC unknown permission log failed: %s", log_e)
                except Exception as e:
                    current_app.logger.debug("RBAC permission check failed: %s", e)
            _rbac_cache_set(g, "_rbac_cache", cache_key, False)
            return False

        # 2) Collect principals: user + user's roles
        role_ids = AuthorizationService._get_role_ids_for_user_id(user_id)

        # 3) Evaluate scoped grants (most-specific wins; deny wins ties)
        def _matches_scope(grant: RbacAccessGrant) -> bool:
            sk = (grant.scope_kind or "").strip()
            if sk == "global":
                return True
            if sk == "entity":
                return bool(entity_type and entity_id is not None) and grant.entity_type == entity_type and int(grant.entity_id or 0) == int(entity_id)
            if sk == "template":
                return template_id is not None and int(grant.template_id or 0) == int(template_id)
            if sk == "assignment":
                return assigned_form_id is not None and int(grant.assigned_form_id or 0) == int(assigned_form_id)
            return False

        scope_priority = {"global": 0, "entity": 1, "template": 2, "assignment": 3}

        # Fetch candidate grants for user and roles (filter by permission_id and principal)
        principal_filters = [
            db.and_(RbacAccessGrant.principal_type == "user", RbacAccessGrant.principal_id == user_id),
        ]
        for rid in role_ids:
            principal_filters.append(db.and_(RbacAccessGrant.principal_type == "role", RbacAccessGrant.principal_id == int(rid)))

        grants = []
        if principal_filters:
            grants = (
                RbacAccessGrant.query.filter(
                    RbacAccessGrant.permission_id == perm_id,
                    db.or_(*principal_filters),
                )
                .all()
            )

        best_effect = None
        best_rank = None
        for gr in grants:
            if not _matches_scope(gr):
                continue
            prio = scope_priority.get((gr.scope_kind or "").strip(), -1)
            deny_rank = 1 if (gr.effect or "") == "deny" else 0
            rank = (prio, deny_rank)
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_effect = (gr.effect or "allow").strip()

        if best_effect is not None:
            allowed = best_effect != "deny"
            _rbac_cache_set(g, "_rbac_cache", cache_key, allowed)
            return allowed

        # 4) Fall back to role permissions (global allow)
        if not role_ids:
            _rbac_cache_set(g, "_rbac_cache", cache_key, False)
            return False

        role_allow = (
            RbacRolePermission.query.filter(
                RbacRolePermission.permission_id == perm_id,
                RbacRolePermission.role_id.in_([int(r) for r in role_ids]),
            )
            .first()
            is not None
        )

        _rbac_cache_set(g, "_rbac_cache", cache_key, bool(role_allow))
        return bool(role_allow)

    @staticmethod
    def get_scoped_grant_decision(
        user,
        permission_code: str,
        *,
        scope: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Return the best matching scoped grant decision for a permission.

        Returns a dict like:
          {"effect": "allow"|"deny", "scope_kind": "global"|"entity"|"template"|"assignment"}
        or None if no matching scoped grant exists.
        """
        if not user or not getattr(user, "is_authenticated", False):
            return None
        if AuthorizationService.is_system_manager(user):
            return {"effect": "allow", "scope_kind": "global"}
        if not isinstance(permission_code, str) or not permission_code.strip():
            return None
        permission_code = permission_code.strip()

        scope = scope or {}
        entity_type = scope.get("entity_type")
        entity_id = scope.get("entity_id")
        template_id = scope.get("template_id")
        assigned_form_id = scope.get("assigned_form_id")

        g = _request_g()
        cache_key = (
            int(getattr(user, "id", 0) or 0),
            permission_code,
            str(entity_type or ""),
            int(entity_id or 0),
            int(template_id or 0),
            int(assigned_form_id or 0),
        )
        cached = _rbac_cache_get(g, "_rbac_grant_decision_cache", cache_key)
        if cached is not None:
            return cached

        try:
            from app.models.rbac import RbacPermission, RbacAccessGrant
            from app import db
        except Exception as e:
            current_app.logger.debug("get_permission_scope import/query failed: %s", e)
            return None

        perm_id = _rbac_cache_get(g, "_rbac_permission_id_cache", permission_code)
        if perm_id is None:
            perm = RbacPermission.query.filter_by(code=permission_code).first()
            perm_id = int(perm.id) if perm else None
            if perm_id is not None:
                _rbac_cache_set(g, "_rbac_permission_id_cache", permission_code, perm_id)

        if perm_id is None:
            return None

        # Collect principals: user + user's roles
        user_id = int(getattr(user, "id", 0) or 0)
        role_ids = AuthorizationService._get_role_ids_for_user_id(user_id)

        def _matches_scope(grant: RbacAccessGrant) -> bool:
            sk = (grant.scope_kind or "").strip()
            if sk == "global":
                return True
            if sk == "entity":
                return bool(entity_type and entity_id is not None) and grant.entity_type == entity_type and int(grant.entity_id or 0) == int(entity_id)
            if sk == "template":
                return template_id is not None and int(grant.template_id or 0) == int(template_id)
            if sk == "assignment":
                return assigned_form_id is not None and int(grant.assigned_form_id or 0) == int(assigned_form_id)
            return False

        scope_priority = {"global": 0, "entity": 1, "template": 2, "assignment": 3}

        principal_filters = [
            db.and_(RbacAccessGrant.principal_type == "user", RbacAccessGrant.principal_id == user_id),
        ]
        for rid in role_ids:
            principal_filters.append(db.and_(RbacAccessGrant.principal_type == "role", RbacAccessGrant.principal_id == int(rid)))

        grants = []
        if principal_filters:
            grants = (
                RbacAccessGrant.query.filter(
                    RbacAccessGrant.permission_id == perm_id,
                    db.or_(*principal_filters),
                )
                .all()
            )

        best_effect = None
        best_rank = None
        best_scope_kind = None
        for gr in grants:
            if not _matches_scope(gr):
                continue
            prio = scope_priority.get((gr.scope_kind or "").strip(), -1)
            deny_rank = 1 if (gr.effect or "") == "deny" else 0
            rank = (prio, deny_rank)
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_effect = (gr.effect or "allow").strip()
                best_scope_kind = (gr.scope_kind or "").strip()

        out = None
        if best_effect is not None and best_scope_kind:
            out = {"effect": best_effect, "scope_kind": best_scope_kind}

        _rbac_cache_set(g, "_rbac_grant_decision_cache", cache_key, out)
        return out

    @staticmethod
    def get_scoped_grant_effect(
        user,
        permission_code: str,
        *,
        scope: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Backward-compatible helper: return only the grant effect string."""
        decision = AuthorizationService.get_scoped_grant_decision(user, permission_code, scope=scope)
        if not decision:
            return None
        return str(decision.get("effect")) if decision.get("effect") else None

    @staticmethod
    def rbac_enabled() -> bool:
        """Return True if RBAC tables are available (best-effort)."""
        g = _request_g()
        if g is not None and hasattr(g, "_rbac_enabled"):
            return bool(getattr(g, "_rbac_enabled"))

        enabled = False
        try:
            from app.models.rbac import RbacRole
            enabled = RbacRole.query.first() is not None
        except Exception as e:
            current_app.logger.debug("RbacRole.query.first failed: %s", e)
            enabled = False

        if g is not None:
            try:
                g._rbac_enabled = enabled
            except Exception as e:
                current_app.logger.debug("RBAC enabled cache set failed: %s", e, exc_info=True)
        return bool(enabled)

    @staticmethod
    def rbac_active_for_user(user) -> bool:
        """Return True if RBAC should be enforced for this user.

        Legacy roles/flags are removed, so RBAC is enforced for all authenticated users
        as soon as RBAC tables are available.
        """
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if AuthorizationService.is_system_manager(user):
            return True
        if not AuthorizationService.rbac_enabled():
            return False
        return True

    # ========== Country Access ==========

    @staticmethod
    def has_country_access(user, country_id: int) -> bool:
        """
        Check if user has access to a specific country.

        Args:
            user: User object to check
            country_id: ID of the country to check

        Returns:
            bool: True if user has access to the country
        """
        if not user or not user.is_authenticated:
            return False

        # System managers have access to all countries
        if AuthorizationService.is_system_manager(user):
            return True

        # Admin country/org managers have access to all countries (global)
        if AuthorizationService.has_rbac_permission(user, "admin.countries.view"):
            return True
        if AuthorizationService.has_rbac_permission(user, "admin.countries.edit"):
            return True
        if AuthorizationService.has_rbac_permission(user, "admin.organization.manage"):
            return True

        # Focal points have access to their assigned countries
        user_country_ids = [c.id for c in user.countries.all()]
        return country_id in user_country_ids

    @staticmethod
    def validate_country_list_access(user, country_ids: List[int]) -> List[int]:
        """
        Validate and filter a list of country IDs based on user access.

        Args:
            user: User object to check
            country_ids: List of country IDs to validate

        Returns:
            List of country IDs the user has access to
        """
        if AuthorizationService.is_admin(user):
            return country_ids

        user_country_ids = [c.id for c in user.countries.all()]
        return [cid for cid in country_ids if cid in user_country_ids]

    # ========== Assignment Access ==========

    @staticmethod
    def can_access_assignment(assignment_entity_status: AssignmentEntityStatus, user) -> bool:
        """
        Check if user can access (view) an assignment for any entity type.

        Args:
            assignment_entity_status: Assignment to check
            user: User object to check

        Returns:
            bool: True if user can access the assignment
        """
        if not user or not user.is_authenticated:
            return False

        # System managers have access to all assignments
        if AuthorizationService.is_system_manager(user):
            return True

        # Build a scope payload for scoped grants
        try:
            scope = {
                "entity_type": assignment_entity_status.entity_type,
                "entity_id": assignment_entity_status.entity_id,
                "assigned_form_id": assignment_entity_status.assigned_form_id,
                "template_id": assignment_entity_status.assigned_form.template_id if assignment_entity_status.assigned_form else None,
            }
        except Exception as e:
            current_app.logger.debug("can_access_assignment scope build failed: %s", e)
            scope = {
                "entity_type": assignment_entity_status.entity_type,
                "entity_id": assignment_entity_status.entity_id,
                "assigned_form_id": assignment_entity_status.assigned_form_id,
            }

        # Assignment admins can view all assignments globally (no entity assignment required)
        if AuthorizationService.has_rbac_permission(user, "admin.assignments.view"):
            return True

        # Scoped grants can override assignment access at entity/template/assignment level.
        # IMPORTANT: A *global* allow for assignment.view should NOT bypass entity assignment checks,
        # otherwise a generic assignment viewer could see all entities.
        decision = AuthorizationService.get_scoped_grant_decision(user, "assignment.view", scope=scope)
        if decision and decision.get("effect") == "deny":
            return False
        if decision and decision.get("effect") == "allow" and decision.get("scope_kind") in ("entity", "template", "assignment"):
            return True

        # Everyone else must have assignment.view (optionally scoped), but still needs entity assignment.
        if not AuthorizationService.has_rbac_permission(user, "assignment.view", scope=scope):
            return False

        # Check entity access using UserEntityPermission
        from app.models.core import UserEntityPermission

        entity_type = assignment_entity_status.entity_type
        entity_id = assignment_entity_status.entity_id

        # Check if user has permission for this entity
        has_entity_permission = UserEntityPermission.query.filter_by(
            user_id=user.id,
            entity_type=entity_type,
            entity_id=entity_id
        ).first() is not None

        return has_entity_permission

    @staticmethod
    def can_edit_assignment(assignment_entity_status: AssignmentEntityStatus, user) -> bool:
        """
        Check if user can edit an assignment based on status and role for any entity type.

        Args:
            assignment_entity_status: Assignment to check
            user: User object to check

        Returns:
            bool: True if user can edit the assignment
        """
        if not user or not user.is_authenticated:
            return False

        # Must have entity access first
        if not AuthorizationService.can_access_assignment(assignment_entity_status, user):
            return False

        # System managers can edit any assignment
        if AuthorizationService.is_system_manager(user):
            return True

        # RBAC gate: require assignment.enter
        try:
            scope = {
                "entity_type": assignment_entity_status.entity_type,
                "entity_id": assignment_entity_status.entity_id,
                "assigned_form_id": assignment_entity_status.assigned_form_id,
                "template_id": assignment_entity_status.assigned_form.template_id if assignment_entity_status.assigned_form else None,
            }
        except Exception as e:
            current_app.logger.debug("can_edit_assignment scope build failed: %s", e)
            scope = {
                "entity_type": assignment_entity_status.entity_type,
                "entity_id": assignment_entity_status.entity_id,
                "assigned_form_id": assignment_entity_status.assigned_form_id,
            }
        if not AuthorizationService.has_rbac_permission(user, "assignment.enter", scope=scope):
            return False

        # Focal points can only edit assignments that are not submitted or approved
        return assignment_entity_status.status not in ["Submitted", "Approved"]

    @staticmethod
    def can_submit_assignment(assignment_entity_status: AssignmentEntityStatus, user) -> bool:
        """
        Check if user can submit an assignment.

        Args:
            assignment_entity_status: Assignment to check
            user: User object to check

        Returns:
            bool: True if user can submit
        """
        if not user or not user.is_authenticated:
            return False

        # Must have access first
        if not AuthorizationService.can_access_assignment(assignment_entity_status, user):
            return False

        # System managers can always submit
        if AuthorizationService.is_system_manager(user):
            return True

        # RBAC gate: require assignment.submit
        try:
            scope = {
                "entity_type": assignment_entity_status.entity_type,
                "entity_id": assignment_entity_status.entity_id,
                "assigned_form_id": assignment_entity_status.assigned_form_id,
                "template_id": assignment_entity_status.assigned_form.template_id if assignment_entity_status.assigned_form else None,
            }
        except Exception as e:
            current_app.logger.debug("can_submit_assignment scope build failed: %s", e)
            scope = {
                "entity_type": assignment_entity_status.entity_type,
                "entity_id": assignment_entity_status.entity_id,
                "assigned_form_id": assignment_entity_status.assigned_form_id,
            }
        if not AuthorizationService.has_rbac_permission(user, "assignment.submit", scope=scope):
            return False

        # Can only submit if status allows (not already approved)
        return assignment_entity_status.status not in ["Approved"]

    @staticmethod
    def can_approve_assignment(assignment_entity_status: AssignmentEntityStatus, user) -> bool:
        """
        Check if user can approve an assignment.

        Args:
            assignment_entity_status: Assignment to check
            user: User object to check

        Returns:
            bool: True if user can approve
        """
        if not user or not user.is_authenticated:
            return False

        # Must have access first
        if not AuthorizationService.can_access_assignment(assignment_entity_status, user):
            return False

        # System managers can always approve
        if AuthorizationService.is_system_manager(user):
            return True

        # RBAC gate: require assignment.approve
        try:
            scope = {
                "entity_type": assignment_entity_status.entity_type,
                "entity_id": assignment_entity_status.entity_id,
                "assigned_form_id": assignment_entity_status.assigned_form_id,
                "template_id": assignment_entity_status.assigned_form.template_id if assignment_entity_status.assigned_form else None,
            }
        except Exception as e:
            current_app.logger.debug("can_approve_assignment scope build failed: %s", e)
            scope = {
                "entity_type": assignment_entity_status.entity_type,
                "entity_id": assignment_entity_status.entity_id,
                "assigned_form_id": assignment_entity_status.assigned_form_id,
            }
        return AuthorizationService.has_rbac_permission(user, "assignment.approve", scope=scope)

    @staticmethod
    def can_reopen_assignment(assignment_entity_status: AssignmentEntityStatus, user) -> bool:
        """
        Check if user can reopen an assignment.

        Args:
            assignment_entity_status: Assignment to check
            user: User object to check

        Returns:
            bool: True if user can reopen
        """
        if not user or not user.is_authenticated:
            return False

        # Must have access first
        if not AuthorizationService.can_access_assignment(assignment_entity_status, user):
            return False

        # System managers can always reopen
        if AuthorizationService.is_system_manager(user):
            return True

        # RBAC gate: require assignment.reopen
        try:
            scope = {
                "entity_type": assignment_entity_status.entity_type,
                "entity_id": assignment_entity_status.entity_id,
                "assigned_form_id": assignment_entity_status.assigned_form_id,
                "template_id": assignment_entity_status.assigned_form.template_id if assignment_entity_status.assigned_form else None,
            }
        except Exception as e:
            current_app.logger.debug("can_reopen_assignment scope build failed: %s", e)
            scope = {
                "entity_type": assignment_entity_status.entity_type,
                "entity_id": assignment_entity_status.entity_id,
                "assigned_form_id": assignment_entity_status.assigned_form_id,
            }
        return AuthorizationService.has_rbac_permission(user, "assignment.reopen", scope=scope)

    @staticmethod
    def check_self_report_access(assignment_entity_status: AssignmentEntityStatus, user) -> bool:
        """
        Check if user can access/modify a self-report assignment.

        Args:
            assignment_entity_status: Assignment to check
            user: User object to check

        Returns:
            bool: True if user has access
        """
        # Import here to avoid circular imports from routes
        from app.utils.constants import SELF_REPORT_PERIOD_NAME

        if not user or not user.is_authenticated:
            return False

        if assignment_entity_status.assigned_form.period_name != SELF_REPORT_PERIOD_NAME:
            return False

        # System managers can always access/modify
        if AuthorizationService.is_system_manager(user):
            return True

        # Must have country access first
        country_id = assignment_entity_status.entity_id if assignment_entity_status.entity_type == 'country' else None
        if not country_id or not AuthorizationService.has_country_access(user, country_id):
            return False

        # Self-report is a data-entry workflow: require assignment.enter
        try:
            scope = {
                "entity_type": assignment_entity_status.entity_type,
                "entity_id": assignment_entity_status.entity_id,
                "assigned_form_id": assignment_entity_status.assigned_form_id,
                "template_id": assignment_entity_status.assigned_form.template_id if assignment_entity_status.assigned_form else None,
            }
        except Exception as e:
            current_app.logger.debug("check_self_report_access scope build failed: %s", e)
            scope = {
                "entity_type": assignment_entity_status.entity_type,
                "entity_id": assignment_entity_status.entity_id,
                "assigned_form_id": assignment_entity_status.assigned_form_id,
            }
        return AuthorizationService.has_rbac_permission(user, "assignment.enter", scope=scope)

    # ========== Template Access ==========

    @staticmethod
    def check_template_access(template_id: int, user_id: int) -> bool:
        """
        Check if a user has access to a template (owner or shared with).

        Args:
            template_id: ID of the template to check
            user_id: ID of the user to check

        Returns:
            bool: True if user has access
        """
        from app.models import FormTemplate, TemplateShare

        # System managers have full access to all templates
        # Check current_user first if available, otherwise query by user_id
        if current_user.is_authenticated and current_user.id == user_id and AuthorizationService.is_system_manager(current_user):
            return True
        else:
            # Query user to check RBAC role if current_user doesn't match
            user = User.query.get(user_id)
            if user and AuthorizationService.is_system_manager(user):
                return True

        template = FormTemplate.query.get(template_id)
        if not template:
            return False

        # Check if user is the owner
        if template.owned_by == user_id:
            return True

        # Check if template is shared with the user
        share = TemplateShare.query.filter_by(
            template_id=template_id,
            shared_with_user_id=user_id
        ).first()

        return share is not None

    # ========== Decorators ==========

    @staticmethod
    def admin_required(f):
        """
        Decorator to require admin or system_manager role.

        NOTE: For admin blueprint routes, prefer importing admin_required from
        app.routes.admin.shared (single source of truth for admin decorators).
        This static method is kept for compatibility where AuthorizationService is
        already used; it delegates to shared.py.
        """
        from app.routes.admin.shared import admin_required as _admin_required
        return _admin_required(f)

    @staticmethod
    def permission_required(permission_name: str):
        """
        Decorator to require a specific permission.

        Args:
            permission_name: Name of the required permission
        """
        from app.routes.admin.shared import permission_required as _permission_required
        return _permission_required(permission_name)

    @staticmethod
    def assignment_access_required(f):
        """
        Decorator to check if user has access to an assignment.
        Expects the first argument to be aes_id (assignment entity status ID).
        """
        @wraps(f)
        def decorated_function(aes_id, *args, **kwargs):
            try:
                aes = AssignmentEntityStatus.query.get_or_404(aes_id)

                if not AuthorizationService.can_access_assignment(aes, current_user):
                    from app.services.entity_service import EntityService
                    entity_name = EntityService.get_entity_display_name(aes.entity_type, aes.entity_id)
                    current_app.logger.warning(
                        f"Access denied for user {current_user.email} to AssignmentEntityStatus {aes_id} "
                        f"(Entity: {aes.entity_type} {aes.entity_id} - {entity_name})"
                    )
                    flash(f"You are not authorized to access this assignment for {entity_name}.", "warning")
                    return redirect(url_for("main.dashboard"))

                return f(aes_id, *args, **kwargs)
            except Exception as e:
                current_app.logger.error(f"Error in assignment access check: {e}")
                flash("An error occurred while checking access permissions.", "danger")
                return redirect(url_for("main.dashboard"))

        return decorated_function

    @staticmethod
    def assignment_edit_required(f):
        """
        Decorator to check if user can edit an assignment.
        Combines access check with edit permission check.
        """
        @wraps(f)
        def decorated_function(aes_id, *args, **kwargs):
            try:
                aes = AssignmentEntityStatus.query.get_or_404(aes_id)

                # Check if user can edit
                if not AuthorizationService.can_edit_assignment(aes, current_user):
                    # Check if it's an access issue or edit permission issue
                    if not AuthorizationService.can_access_assignment(aes, current_user):
                        from app.services.entity_service import EntityService
                        entity_name = EntityService.get_entity_display_name(aes.entity_type, aes.entity_id)
                        flash(f"You are not authorized to access this assignment for {entity_name}.", "warning")
                    else:
                        from app.services.entity_service import EntityService
                        entity_name = EntityService.get_entity_display_name(aes.entity_type, aes.entity_id)
                        flash(
                            f"This assignment for {entity_name} is in '{aes.status}' status and cannot be edited by you at this time.",
                            "warning"
                        )
                    return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes.id))

                return f(aes_id, *args, **kwargs)
            except Exception as e:
                current_app.logger.error(f"Error in assignment edit access check: {e}")
                flash("An error occurred while checking edit permissions.", "danger")
                return redirect(url_for("main.dashboard"))

        return decorated_function
