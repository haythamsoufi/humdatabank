# ========== API Authentication Utilities ==========
"""
Authentication and authorization for API routes.

One credential pipeline, one authorization point
------------------------------------------------
Every API-key request (``require_api_key``, ``require_api_key_or_session``,
``authenticate_api_request``, ``authenticate_db_api_key_only`` and ``X-Mobile-Auth``)
goes through ``_resolve_key_principal`` (identify the key, check status and rate
limit) and ``_authorize_principal`` (does the key hold the capability the route
declared, and can the route honour the key's data scope). Routes declare their
capability once with ``@require_api_key(capability=...)`` or ``@api_capability(...)``;
a route that declares nothing is denied (fail closed).

Contract:
- ``authenticate_api_request`` returns a 3-tuple on success:
    (elevated_access: bool, auth_user: User|None, api_key_record: APIKey|None)
  ``elevated_access`` means "API key with no data scope". A scoped key returns
  ``elevated_access=False`` with ``api_key_record`` set: routes MUST apply
  ``get_api_key_data_scope()`` to every query that returns data.
- Failure always returns a JSON Response using the standardized API error schema.
"""

from app.utils.datetime_helpers import utcnow, ensure_utc

import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from flask import request, current_app, g
from flask_login import current_user
from sqlalchemy import select, union_all, literal
from app import db
from app.models import FormTemplate, TemplateShare, FormData, AssignedForm, PublicSubmission
from app.models.assignments import AssignmentEntityStatus
from app.services.security.api_key_permissions import (
    ALL_CAPABILITY_CODES,
    MOBILE_CLIENT,
    SCOPABLE_CAPABILITY_CODES,
    USERS_READ,
    KeyPermissions,
    parse_key_permissions,
)
from app.utils.api_helpers import json_response, api_error, MAX_PER_PAGE, DEFAULT_PER_PAGE, DEFAULT_PAGE
from datetime import datetime

# Rate limiting storage for API keys (key_id -> list of timestamps).
# In-process: with N worker processes the effective ceiling is N x the configured limit.
_api_key_rate_limit_storage = {}

# In-process rate bucket for env-based MOBILE_APP_API_KEY (no DB row)
_ENV_MOBILE_API_KEY_RATE_BUCKET = "env_mobile_app_api_key"

DEFAULT_ENV_MOBILE_CAPABILITIES = "reference:read,content:read,mobile:client"
DEFAULT_API_KEY_MAX_PER_PAGE = 10000

_SECRET_QUERY_PARAMS = frozenset({"api_key", "apikey", "key", "token", "access_token"})

_warned_env_mobile_key = False
_warned_legacy_key_ids: set = set()


@dataclass(frozen=True)
class ApiPrincipal:
    """Who is calling and what they may do. Stored on ``g.api_principal``."""

    source: str  # 'db_key' | 'env_mobile'
    permissions: KeyPermissions
    key_location: str = "header"  # 'header' | 'query'
    api_key_id: Optional[int] = None
    client_name: Optional[str] = None

    @property
    def capabilities(self) -> FrozenSet[str]:
        return self.permissions.capabilities

    @property
    def data_scope(self) -> Optional[Dict[str, List[int]]]:
        return self.permissions.data_scope

    def has(self, capability: str) -> bool:
        return self.permissions.has(capability)


def redact_request_params(args=None) -> Dict[str, Any]:
    """Request parameters that are safe to log (secrets in the query string masked)."""
    source = request.args if args is None else args
    return {
        k: ("***" if str(k).lower() in _SECRET_QUERY_PARAMS else v)
        for k, v in dict(source).items()
    }


def api_key_max_per_page() -> int:
    """Hard ceiling for ``per_page`` on key-authenticated list endpoints."""
    try:
        configured = int(current_app.config.get("API_KEY_MAX_PER_PAGE") or DEFAULT_API_KEY_MAX_PER_PAGE)
    except (TypeError, ValueError):
        configured = DEFAULT_API_KEY_MAX_PER_PAGE
    return max(1, min(configured, MAX_PER_PAGE))


def get_api_principal() -> Optional[ApiPrincipal]:
    return getattr(g, "api_principal", None)


def get_api_key_data_scope() -> Optional[Dict[str, List[int]]]:
    """Template/country scope of the current key, or None when unrestricted / not a key."""
    principal = get_api_principal()
    return principal.data_scope if principal is not None else None


def api_key_has_capability(capability: str) -> bool:
    """True for session/user auth (RBAC applies instead) and for keys holding ``capability``."""
    principal = get_api_principal()
    return principal is None or principal.has(capability)


def api_key_can_read_personal_data() -> bool:
    """True for session/user auth and for keys that hold ``users:read``."""
    return api_key_has_capability(USERS_READ)


def api_key_scope_allows(scope: Optional[Dict[str, List[int]]], template_id, country_id=None) -> bool:
    """Whether one (template, country) pair is inside ``scope`` (None = unrestricted)."""
    if scope is None:
        return True
    template_ids = scope.get("template_ids") or []
    country_ids = scope.get("country_ids") or []
    if not template_ids and not country_ids:
        return False
    if template_ids and (template_id is None or int(template_id) not in template_ids):
        return False
    if country_ids and (country_id is None or int(country_id) not in country_ids):
        return False
    return True


def api_key_dimension_allows(
    scope: Optional[Dict[str, List[int]]], *, template_id=None, country_id=None
) -> bool:
    """Whether a key may address one dimension only (e.g. ``/templates/<id>/data``).

    The other dimension is enforced by the query filter, not here.
    """
    if scope is None:
        return True
    template_ids = scope.get("template_ids") or []
    country_ids = scope.get("country_ids") or []
    if not template_ids and not country_ids:
        return False
    if template_id is not None and template_ids and int(template_id) not in template_ids:
        return False
    if country_id is not None and country_ids and int(country_id) not in country_ids:
        return False
    return True


def api_key_template_filter(scope: Optional[Dict[str, List[int]]]) -> Optional[List[int]]:
    """Template ids a scoped key may read structure for; None = unrestricted, [] = none.

    Template definitions are not country-bound, so a country-only scope leaves them open.
    """
    if scope is None:
        return None
    if not scope.get("template_ids") and not scope.get("country_ids"):
        return []
    return list(scope["template_ids"]) or None


def declared_api_capability() -> Tuple[Optional[str], bool]:
    """(capability, scope_aware) declared on the current request's view function."""
    endpoint = request.endpoint
    view = current_app.view_functions.get(endpoint) if endpoint else None
    seen = 0
    while view is not None and seen < 20:
        capability = getattr(view, "_ep_capability", None)
        if capability is not None:
            return capability, bool(getattr(view, "_ep_scope_aware", False))
        view = getattr(view, "__wrapped__", None)
        seen += 1
    return None, False


def _configured_env_mobile_api_key_plaintext():
    return (current_app.config.get("MOBILE_APP_API_KEY") or "").strip()


def _plaintext_matches_env_mobile_api_key(provided_key: str) -> bool:
    expected = _configured_env_mobile_api_key_plaintext()
    prov = (provided_key or "").strip()
    if not expected or not prov:
        return False
    try:
        eb = expected.encode("utf-8")
        pb = prov.encode("utf-8")
        if len(eb) != len(pb):
            return False
        return secrets.compare_digest(pb, eb)
    except Exception:
        return False


def _consume_rate_limit(bucket: str, limit: int) -> bool:
    """Record one request; return True if the bucket is already over ``limit``."""
    from collections import deque

    now = time.time()
    if bucket not in _api_key_rate_limit_storage:
        _api_key_rate_limit_storage[bucket] = deque()
    storage = _api_key_rate_limit_storage[bucket]
    while storage and storage[0] < now - 60:
        storage.popleft()
    if len(storage) >= limit:
        return True
    storage.append(now)
    return False


def _env_mobile_api_key_rate_limit_exceeded() -> bool:
    """Return True if the env-based mobile key is over its per-minute limit."""
    limit = int(current_app.config.get("MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE") or 300)
    return _consume_rate_limit(_ENV_MOBILE_API_KEY_RATE_BUCKET, limit)


def _env_mobile_permissions() -> KeyPermissions:
    """Restricted capability set for the ``MOBILE_APP_API_KEY`` env fallback."""
    raw = current_app.config.get("MOBILE_APP_API_KEY_CAPABILITIES")
    if raw is None:
        raw = DEFAULT_ENV_MOBILE_CAPABILITIES
    if isinstance(raw, str):
        requested = [part.strip() for part in raw.split(",") if part.strip()]
    else:
        requested = [str(part).strip() for part in (raw or []) if str(part).strip()]
    granted = frozenset(c for c in requested if c in ALL_CAPABILITY_CODES)
    dropped = [c for c in requested if c not in ALL_CAPABILITY_CODES]
    if dropped:
        current_app.logger.warning(
            "MOBILE_APP_API_KEY_CAPABILITIES contains unknown capabilities (ignored): %s",
            ", ".join(dropped),
        )
    return KeyPermissions(capabilities=granted, schema="v2")


def _effective_permissions(db_api_key) -> KeyPermissions:
    """Parsed permissions for a DB key, honouring the legacy full-access kill switch."""
    perms = parse_key_permissions(db_api_key.permissions)
    if perms.legacy_full_access and not current_app.config.get("API_KEY_ALLOW_LEGACY_FULL_ACCESS", True):
        return KeyPermissions(schema=perms.schema, legacy=True, warnings=("legacy full access disabled",))
    if perms.legacy_full_access and db_api_key.id not in _warned_legacy_key_ids:
        _warned_legacy_key_ids.add(db_api_key.id)
        current_app.logger.warning(
            "[API auth] legacy full-access API key in use: api_keys.id=%s client=%r. "
            "Narrow its permissions in Admin > API Management > API Keys.",
            db_api_key.id,
            db_api_key.client_name,
        )
    return perms


def _try_finish_auth_with_env_mobile_api_key(*, log_prefix: str, provided_key: str):
    """
    If MOBILE_APP_API_KEY env matches ``provided_key``, apply env rate limit and return True.
    Otherwise return False. Caller handles g.* for DB keys; on success here, caller should
    clear g.api_key_record / usage scalars if appropriate.
    """
    global _warned_env_mobile_key
    if not _plaintext_matches_env_mobile_api_key(provided_key):
        return False
    if _env_mobile_api_key_rate_limit_exceeded():
        current_app.logger.warning(
            "%s rate limit exceeded for env MOBILE_APP_API_KEY path=%s",
            log_prefix,
            request.path,
        )
        return False
    if not _warned_env_mobile_key:
        _warned_env_mobile_key = True
        current_app.logger.warning(
            "MOBILE_APP_API_KEY environment fallback is deprecated and restricted to %s. "
            "Create a database API key with the 'Mobile app client' preset and remove the env value.",
            ", ".join(sorted(_env_mobile_permissions().capabilities)) or "no capabilities",
        )
    if current_app.config.get("LOG_API_KEY_USAGE", False):
        current_app.logger.info("%s env MOBILE_APP_API_KEY ok", log_prefix)
    return True


def _best_effort_touch_api_key_last_used(db_api_key) -> None:
    """Update last_used_at without blocking or poisoning the request session."""
    from app.models.api_key_management import APIKey

    try:
        APIKey.touch_last_used(db_api_key.id)
    except Exception as e:
        current_app.logger.warning("Failed to update API key last_used_at: %s", e)


def _extract_api_credential() -> Tuple[str, Optional[str]]:
    """Return ``(key, location)``; ``location`` is ``'header'`` or ``'query'``.

    Order: ``Authorization: Bearer``, ``X-API-Key``, then ``?api_key=``. The query form
    is accepted only for keys that opt in (``allow_query_api_key``), see
    ``_resolve_key_principal``.
    """
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:].strip(), 'header'
    header_key = (request.headers.get('X-API-Key') or request.headers.get('X-API-KEY') or '').strip()
    if header_key:
        return header_key, 'header'
    query_key = (request.args.get('api_key') or '').strip()
    if query_key:
        return query_key, 'query'
    return '', None


def _extract_bearer_or_x_api_key() -> str:
    """Return the presented API key (Bearer, X-API-Key, or ``api_key`` query parameter)."""
    return _extract_api_credential()[0]


def _resolve_key_principal(provided_key: str, key_location: str, *, log_prefix: str = "[API auth]"):
    """
    Identify the key and check status, rate limit and where it was sent.

    Returns an ``ApiPrincipal`` (also stored on ``g``) or a JSON error Response.
    Does not check route capabilities; see ``_authorize_principal``.
    """
    from app.models.api_key_management import APIKey

    endpoint = request.endpoint or request.path or 'unknown'
    try:
        db_api_key = APIKey.query.filter_by(key_hash=APIKey.hash_key(provided_key)).first()

        if not db_api_key:
            if key_location == 'header' and _try_finish_auth_with_env_mobile_api_key(
                log_prefix=log_prefix, provided_key=provided_key
            ):
                g.api_key_record = None
                g.api_key_usage_id = None
                g.api_key_usage_client_name = None
                principal = ApiPrincipal(
                    source='env_mobile',
                    permissions=_env_mobile_permissions(),
                    key_location=key_location,
                    client_name='env:MOBILE_APP_API_KEY',
                )
                _store_principal(principal)
                return principal
            current_app.logger.warning(
                "[API auth] 401 %s: invalid API key (no matching key). path=%s",
                endpoint,
                request.path,
            )
            return api_error("Invalid API key", 401)

        if not db_api_key.is_valid():
            if db_api_key.is_revoked:
                current_app.logger.warning("[API auth] 401 %s: API key revoked. path=%s", endpoint, request.path)
                return api_error("API key has been revoked", 401)
            expires_at = ensure_utc(db_api_key.expires_at) if db_api_key.expires_at else None
            if expires_at and expires_at <= utcnow():
                current_app.logger.warning("[API auth] 401 %s: API key expired. path=%s", endpoint, request.path)
                return api_error("API key has expired", 401)
            current_app.logger.warning("[API auth] 401 %s: API key not active. path=%s", endpoint, request.path)
            return api_error("API key is not active", 401)

        perms = _effective_permissions(db_api_key)

        if _consume_rate_limit(f"api_key_{db_api_key.id}", db_api_key.rate_limit_per_minute):
            return api_error("Rate limit exceeded", 429, extra={"retry_after": 60})

        g.api_key_record = db_api_key
        # Scalars for after_request usage tracking (ORM instance may be detached/expired later)
        g.api_key_usage_id = db_api_key.id
        g.api_key_usage_client_name = db_api_key.client_name

        _best_effort_touch_api_key_last_used(db_api_key)

        principal = ApiPrincipal(
            source='db_key',
            permissions=perms,
            key_location=key_location,
            api_key_id=db_api_key.id,
            client_name=db_api_key.client_name,
        )
        _store_principal(principal)

        if key_location == 'query' and not perms.allow_query_api_key:
            current_app.logger.warning(
                "[API auth] 403 %s: API key sent in query string but not enabled for it "
                "(api_keys.id=%s). path=%s",
                endpoint,
                db_api_key.id,
                request.path,
            )
            return api_error(
                "This API key may not be sent in the URL query string",
                403,
                extra={"hint": "Send it as 'Authorization: Bearer <key>' or the 'X-API-Key' header."},
            )

        if current_app.config.get('LOG_API_KEY_USAGE', False):
            current_app.logger.info(
                f"Database API key authenticated: {db_api_key.client_name} "
                f"(prefix: {db_api_key.key_prefix}..., location: {key_location}, endpoint: {request.endpoint})"
            )

        return principal
    except Exception as e:
        current_app.logger.error(f"Error checking database API keys: {e}", exc_info=True)
        return api_error("API authentication error", 500)


def _store_principal(principal: ApiPrincipal) -> None:
    g.api_principal = principal
    g.api_key_data_scope = principal.data_scope
    g.api_elevated_data_access = principal.data_scope is None
    g.api_key_via_query = principal.key_location == 'query'


def _authorize_principal(principal: ApiPrincipal, capability: Optional[str], scope_aware: bool):
    """Return an error Response when ``principal`` may not call this route, else None."""
    endpoint = request.endpoint or request.path or 'unknown'
    if not capability:
        current_app.logger.error(
            "[API auth] 403 %s: route accepts API keys but declares no capability (denied)", endpoint
        )
        return api_error("This endpoint is not available to API keys", 403)
    if capability not in ALL_CAPABILITY_CODES:
        current_app.logger.error("[API auth] 403 %s: unknown capability %r declared", endpoint, capability)
        return api_error("This endpoint is not available to API keys", 403)
    if not principal.has(capability):
        current_app.logger.warning(
            "[API auth] 403 %s: key %s (%s) lacks %s. path=%s",
            endpoint, principal.api_key_id, principal.client_name, capability, request.path,
        )
        return api_error(
            "API key does not have permission for this endpoint",
            403,
            extra={"required_permission": capability},
        )
    if (
        principal.data_scope is not None
        and capability in SCOPABLE_CAPABILITY_CODES
        and not scope_aware
    ):
        current_app.logger.warning(
            "[API auth] 403 %s: key %s is data-scoped but the route cannot apply a scope. path=%s",
            endpoint, principal.api_key_id, request.path,
        )
        return api_error(
            "This endpoint cannot be limited to a data scope; use a key without data restrictions",
            403,
            extra={"required_permission": capability},
        )
    return None


def _clear_principal() -> None:
    """Drop any principal left on ``g`` so a later credential-less path never inherits a scope."""
    g.api_principal = None
    g.api_key_data_scope = None
    g.api_elevated_data_access = False
    g.api_key_via_query = False


def _authenticate_key_request(provided_key, key_location, capability, scope_aware, log_prefix):
    """Shared pipeline: identify, then authorize. Returns ApiPrincipal or Response."""
    _clear_principal()
    if capability is None:
        capability, declared_scope_aware = declared_api_capability()
        scope_aware = scope_aware or declared_scope_aware
    principal = _resolve_key_principal(provided_key, key_location, log_prefix=log_prefix)
    if hasattr(principal, "status_code"):
        return principal
    denied = _authorize_principal(principal, capability, bool(scope_aware))
    if denied is not None:
        return denied
    return principal


def authenticate_db_api_key_only(capability: Optional[str] = None, scope_aware: Optional[bool] = None):
    """
    Authenticate request using an API key and authorize it for the route's capability.

    Accepted locations, in order: ``Authorization: Bearer``, ``X-API-Key``, then
    ``?api_key=`` (only for keys with ``allow_query_api_key``). Accepts a
    database-managed key (``api_keys``) or, when no matching row exists, the optional
    ``MOBILE_APP_API_KEY`` environment value (restricted capability set).

    ``capability`` defaults to the one declared on the view (``@api_capability`` /
    ``@require_api_key(capability=...)``).

    Returns:
      APIKey ORM instance on DB success, True on env-key success, or a JSON Response on failure.
    """
    endpoint = request.endpoint or request.path or 'unknown'
    provided_key, key_location = _extract_api_credential()
    if not provided_key:
        current_app.logger.warning(
            "[API auth] 401 %s: missing API key (expected Bearer or X-API-Key). path=%s",
            endpoint, request.path
        )
        return api_error(
            "Authentication required",
            401,
            extra={"hint": "Use Authorization: Bearer YOUR_API_KEY or the X-API-Key header"},
        )

    principal = _authenticate_key_request(
        provided_key, key_location, capability, bool(scope_aware), "[API auth Bearer]"
    )
    if hasattr(principal, "status_code"):
        return principal
    if principal.source == 'env_mobile':
        return True
    return g.api_key_record


def validate_plaintext_db_api_key_for_mobile_auth(provided_key: str) -> bool:
    """
    Return True if ``provided_key`` is an active database key holding ``mobile:client``
    (or the ``MOBILE_APP_API_KEY`` env value when its capability set includes it).

    Used for ``X-Mobile-Auth`` (skips CSRF for non-browser mobile clients). Same status
    and rate-limit rules as ``Authorization: Bearer`` on /api/v1. Unlike Bearer auth this
    does not set ``g.api_principal``: the header only proves the client is the mobile app.
    """
    from app.models.api_key_management import APIKey

    key = (provided_key or "").strip()
    if not key:
        return False

    try:
        db_api_key = APIKey.query.filter_by(key_hash=APIKey.hash_key(key)).first()
        if db_api_key:
            if not db_api_key.is_valid():
                return False
            if not _effective_permissions(db_api_key).has(MOBILE_CLIENT):
                current_app.logger.warning(
                    "[X-Mobile-Auth] key api_keys.id=%s lacks %s (denied) path=%s",
                    db_api_key.id, MOBILE_CLIENT, request.path,
                )
                return False
            if _consume_rate_limit(f"api_key_{db_api_key.id}", db_api_key.rate_limit_per_minute):
                current_app.logger.warning(
                    "[X-Mobile-Auth] rate limit exceeded for api_keys.id=%s path=%s",
                    db_api_key.id,
                    request.path,
                )
                return False

            _best_effort_touch_api_key_last_used(db_api_key)

            if current_app.config.get("LOG_API_KEY_USAGE", False):
                current_app.logger.info(
                    "X-Mobile-Auth DB API key ok: %s (prefix: %s...)",
                    db_api_key.client_name,
                    db_api_key.key_prefix,
                )

            return True

        if not _plaintext_matches_env_mobile_api_key(key):
            return False
        if not _env_mobile_permissions().has(MOBILE_CLIENT):
            return False
        return _try_finish_auth_with_env_mobile_api_key(
            log_prefix="[X-Mobile-Auth]", provided_key=key
        )
    except Exception as e:
        current_app.logger.error("Error validating X-Mobile-Auth API key: %s", e, exc_info=True)
        return False


def authenticate_api_request(capability: Optional[str] = None, scope_aware: Optional[bool] = None):
    """
    Authenticate API request and determine access level.

    Standard authentication (one of):
    1. API key: ``Authorization: Bearer``, ``X-API-Key``, or ``?api_key=`` for keys that
       opted in. The key must hold the capability declared on the route.
    2. HTTP Basic auth (email/password)
    3. Flask-Login session (browser)

    Returns:
        A 3-tuple (elevated_access, auth_user, api_key_record) on success, or a Response on failure.
        Scoped keys return ``elevated_access=False`` with ``api_key_record`` set; the caller
        must filter results with ``get_api_key_data_scope()``.
    """
    from app.models import User

    elevated_access = False
    auth_user = None

    provided_key, key_location = _extract_api_credential()
    _clear_principal()

    if provided_key:
        principal = _authenticate_key_request(
            provided_key, key_location, capability, bool(scope_aware), "[API auth Bearer]"
        )
        if hasattr(principal, "status_code"):
            return principal
        elevated_access = principal.data_scope is None
        api_key_record = g.api_key_record if principal.source == 'db_key' else None
        return (elevated_access, None, api_key_record)

    # If no valid API key, try user authentication
    # If a user is already logged in via Flask-Login, use that session
    if getattr(current_user, 'is_authenticated', False):
        auth_user = current_user
        return (elevated_access, auth_user, None)
    else:
        # Try HTTP Basic auth
        auth = request.authorization
        if auth and (auth.username or '').strip():
            submitted_email = (auth.username or '').strip().lower()
            submitted_password = auth.password or ''
            user = User.query.filter_by(email=submitted_email).first()
            if not user or not user.check_password(submitted_password):
                # Send Basic challenge for browsers/clients
                resp = api_error("Invalid credentials", 401)
                from app.services.platform.app_settings_service import get_organization_name
                org_name = get_organization_name()
                resp.headers['WWW-Authenticate'] = f'Basic realm="{org_name} API", charset="UTF-8"'
                return resp
            auth_user = user
            return (elevated_access, auth_user, None)
        else:
            # No valid API key and no Basic credentials; send Basic challenge
            resp = api_error(
                "Authentication required",
                401,
                extra={"hint": "Use Authorization: Bearer YOUR_API_KEY, the X-API-Key header, or HTTP Basic auth (email/password)"},
            )
            from app.services.platform.app_settings_service import get_organization_name
            org_name = get_organization_name()
            resp.headers['WWW-Authenticate'] = f'Basic realm="{org_name} API", charset="UTF-8"'
            return resp


def get_user_allowed_template_ids(user_id):
    """Get template IDs that a user can access (owned or shared). Uses efficient UNION query."""
    try:
        # Single query with UNION for efficiency
        allowed_ids = db.session.execute(
            union_all(
                select(FormTemplate.id).where(FormTemplate.owned_by == user_id),
                select(TemplateShare.template_id).where(TemplateShare.shared_with_user_id == user_id)
            )
        ).scalars().all()
        return list(allowed_ids)
    except Exception as e:
        current_app.logger.error(f"Error fetching user allowed templates: {e}", exc_info=True)
        return []


def _get_user_allowed_country_ids(auth_user):
    """Return set of country IDs the user may access, or None if unrestricted."""
    from app.services.organization.authorization_service import AuthorizationService
    if AuthorizationService.is_system_manager(auth_user):
        return None
    if AuthorizationService.has_rbac_permission(auth_user, "admin.countries.view"):
        return None
    from app.models.core import UserEntityPermission
    perms = UserEntityPermission.query.filter_by(
        user_id=auth_user.id, entity_type="country"
    ).all()
    return {p.entity_id for p in perms}


def apply_user_template_scoping(
    queries,
    auth_user,
    template_id=None,
    country_id=None,
    period_name=None,
    assignment_ids=None,
):
    """Apply RBAC template + entity-level filtering to queries for user-scoped access."""
    assigned_form_data_query = queries['assigned']
    public_form_data_query = queries['public']

    from app.services.organization.authorization_service import AuthorizationService
    if AuthorizationService.is_system_manager(auth_user):
        return queries

    allowed_template_ids = get_user_allowed_template_ids(auth_user.id)

    if not allowed_template_ids:
        return {
            'assigned': FormData.query.filter(literal(False)),
            'public': FormData.query.filter(literal(False))
        }

    # Template scoping
    if assigned_form_data_query is not None:
        joins_exist = (
            template_id is not None
            or country_id is not None
            or period_name is not None
            or assignment_ids
        )
        if joins_exist:
            assigned_form_data_query = assigned_form_data_query.filter(AssignedForm.template_id.in_(allowed_template_ids))
        else:
            assigned_form_data_query = assigned_form_data_query.join(AssignmentEntityStatus).join(AssignedForm).filter(AssignedForm.template_id.in_(allowed_template_ids))

    if public_form_data_query is not None:
        public_form_data_query = public_form_data_query.filter(AssignedForm.template_id.in_(allowed_template_ids))

    # Entity/country scoping: restrict to countries the user has permission for
    allowed_country_ids = _get_user_allowed_country_ids(auth_user)
    if allowed_country_ids is not None:
        if not allowed_country_ids:
            return {
                'assigned': FormData.query.filter(literal(False)),
                'public': FormData.query.filter(literal(False))
            }
        if assigned_form_data_query is not None:
            assigned_form_data_query = assigned_form_data_query.filter(
                AssignmentEntityStatus.entity_type == 'country',
                AssignmentEntityStatus.entity_id.in_(allowed_country_ids)
            )
        if public_form_data_query is not None:
            public_form_data_query = public_form_data_query.filter(
                PublicSubmission.country_id.in_(allowed_country_ids)
            )

    return {
        'assigned': assigned_form_data_query,
        'public': public_form_data_query
    }


def apply_api_key_data_scoping(
    queries,
    scope,
    template_id=None,
    country_id=None,
    period_name=None,
    assignment_ids=None,
):
    """
    Restrict data queries to template/country IDs allowed on a scoped API key.

    ``scope`` is the dict returned by ``resolve_api_key_data_access`` for
    ``read_scoped`` keys: ``{"template_ids": [...], "country_ids": [...]}``.
    """
    if not scope or not isinstance(scope, dict):
        return queries

    assigned_form_data_query = queries['assigned']
    public_form_data_query = queries['public']

    allowed_template_ids = scope.get('template_ids') or []
    allowed_country_ids = scope.get('country_ids') or []

    if not allowed_template_ids and not allowed_country_ids:
        return {
            'assigned': FormData.query.filter(literal(False)),
            'public': FormData.query.filter(literal(False)),
        }

    if allowed_template_ids:
        if template_id is not None and int(template_id) not in allowed_template_ids:
            return {
                'assigned': FormData.query.filter(literal(False)),
                'public': FormData.query.filter(literal(False)),
            }
        if assigned_form_data_query is not None:
            joins_exist = (
                template_id is not None
                or country_id is not None
                or period_name is not None
                or assignment_ids
            )
            if joins_exist:
                assigned_form_data_query = assigned_form_data_query.filter(
                    AssignedForm.template_id.in_(allowed_template_ids)
                )
            else:
                assigned_form_data_query = (
                    assigned_form_data_query
                    .join(AssignmentEntityStatus)
                    .join(AssignedForm)
                    .filter(AssignedForm.template_id.in_(allowed_template_ids))
                )
        if public_form_data_query is not None:
            public_form_data_query = public_form_data_query.filter(
                AssignedForm.template_id.in_(allowed_template_ids)
            )

    if allowed_country_ids:
        if country_id is not None and int(country_id) not in allowed_country_ids:
            return {
                'assigned': FormData.query.filter(literal(False)),
                'public': FormData.query.filter(literal(False)),
            }
        if assigned_form_data_query is not None:
            assigned_form_data_query = assigned_form_data_query.filter(
                AssignmentEntityStatus.entity_type == 'country',
                AssignmentEntityStatus.entity_id.in_(allowed_country_ids),
            )
        if public_form_data_query is not None:
            public_form_data_query = public_form_data_query.filter(
                PublicSubmission.country_id.in_(allowed_country_ids)
            )

    return {
        'assigned': assigned_form_data_query,
        'public': public_form_data_query,
    }
