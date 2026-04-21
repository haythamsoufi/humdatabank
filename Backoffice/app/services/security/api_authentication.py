# ========== API Authentication Utilities ==========
"""
Authentication and authorization functions for API routes.

Contract:
- Auth success always returns a 3-tuple:
    (elevated_access: bool, auth_user: User|None, api_key_record: APIKey|None)
- Auth failure always returns a JSON Response using the standardized API error schema.
"""

from app.utils.datetime_helpers import utcnow, ensure_utc

import secrets
import time
from flask import request, current_app, g
from flask_login import current_user
from sqlalchemy import select, union_all, literal
from app import db
from app.models import FormTemplate, TemplateShare, FormData, AssignedForm, PublicSubmission
from app.models.assignments import AssignmentEntityStatus
from app.utils.api_helpers import json_response, api_error, MAX_PER_PAGE, DEFAULT_PER_PAGE, DEFAULT_PAGE
from datetime import datetime

# Rate limiting storage for API keys (key_id -> list of timestamps)
_api_key_rate_limit_storage = {}

# In-process rate bucket for env-based MOBILE_APP_API_KEY (no DB row)
_ENV_MOBILE_API_KEY_RATE_BUCKET = "env_mobile_app_api_key"


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


def _env_mobile_api_key_rate_limit_exceeded() -> bool:
    """Return True if the env-based mobile key is over its per-minute limit."""
    from collections import deque

    limit = int(current_app.config.get("MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE") or 300)
    now = time.time()
    bucket = _ENV_MOBILE_API_KEY_RATE_BUCKET
    if bucket not in _api_key_rate_limit_storage:
        _api_key_rate_limit_storage[bucket] = deque()
    storage = _api_key_rate_limit_storage[bucket]
    while storage and storage[0] < now - 60:
        storage.popleft()
    if len(storage) >= limit:
        return True
    storage.append(now)
    return False


def _try_finish_auth_with_env_mobile_api_key(*, log_prefix: str, provided_key: str):
    """
    If MOBILE_APP_API_KEY env matches ``provided_key``, apply env rate limit and return True.
    Otherwise return False. Caller handles g.* for DB keys; on success here, caller should
    clear g.api_key_record / usage scalars if appropriate.
    """
    if not _plaintext_matches_env_mobile_api_key(provided_key):
        return False
    if _env_mobile_api_key_rate_limit_exceeded():
        current_app.logger.warning(
            "%s rate limit exceeded for env MOBILE_APP_API_KEY path=%s",
            log_prefix,
            request.path,
        )
        return False
    if current_app.config.get("LOG_API_KEY_USAGE", False):
        current_app.logger.info("%s env MOBILE_APP_API_KEY ok", log_prefix)
    return True


def authenticate_db_api_key_only():
    """
    Authenticate request using an API key from Authorization: Bearer.

    Accepts a database-managed key (``api_keys``) or, when no matching row exists,
    the optional ``MOBILE_APP_API_KEY`` environment value (same plaintext as the Flutter app).

    Returns:
      APIKey ORM instance on DB success, True on env-key success, or a JSON Response on failure.
    """
    from app.models.api_key_management import APIKey
    from collections import deque

    auth_header = request.headers.get('Authorization', '')
    endpoint = request.endpoint or request.path or 'unknown'
    if not auth_header.startswith('Bearer '):
        current_app.logger.warning(
            "[API auth] 401 %s: missing or invalid Authorization (expected Bearer <key>). path=%s",
            endpoint, request.path
        )
        return api_error(
            "Authentication required",
            401,
            extra={"hint": "Use Authorization: Bearer YOUR_API_KEY"},
        )

    provided_key = auth_header[7:].strip()
    if not provided_key:
        current_app.logger.warning("[API auth] 401 %s: Authorization Bearer present but key empty. path=%s", endpoint, request.path)
        return api_error(
            "Authentication required",
            401,
            extra={"hint": "Use Authorization: Bearer YOUR_API_KEY"},
        )

    try:
        key_hash = APIKey.hash_key(provided_key)
        db_api_key = APIKey.query.filter_by(key_hash=key_hash).first()
        if not db_api_key:
            if _try_finish_auth_with_env_mobile_api_key(
                log_prefix="[API auth Bearer]", provided_key=provided_key
            ):
                g.api_key_record = None
                g.api_key_usage_id = None
                g.api_key_usage_client_name = None
                return True
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

        # Rate limiting
        now = time.time()
        rate_limit_key = f"api_key_{db_api_key.id}"
        if rate_limit_key not in _api_key_rate_limit_storage:
            _api_key_rate_limit_storage[rate_limit_key] = deque()

        storage = _api_key_rate_limit_storage[rate_limit_key]
        while storage and storage[0] < now - 60:
            storage.popleft()
        if len(storage) >= db_api_key.rate_limit_per_minute:
            return api_error("Rate limit exceeded", 429, extra={"retry_after": 60})
        storage.append(now)

        # Store in request context
        g.api_key_record = db_api_key
        # Scalars for after_request usage tracking (ORM instance may be detached/expired later)
        g.api_key_usage_id = db_api_key.id
        g.api_key_usage_client_name = db_api_key.client_name

        # Best-effort usage bookkeeping
        try:
            db_api_key.update_last_used()
        except Exception as e:
            current_app.logger.warning(f"Failed to update API key last_used_at: {e}")

        if current_app.config.get('LOG_API_KEY_USAGE', False):
            current_app.logger.info(
                f"Database API key authenticated: {db_api_key.client_name} "
                f"(prefix: {db_api_key.key_prefix}..., endpoint: {request.endpoint})"
            )

        return db_api_key
    except Exception as e:
        current_app.logger.error(f"Error checking database API keys: {e}", exc_info=True)
        return api_error("API authentication error", 500)


def validate_plaintext_db_api_key_for_mobile_auth(provided_key: str) -> bool:
    """
    Return True if ``provided_key`` matches an active database-managed API key,
    or the optional ``MOBILE_APP_API_KEY`` config/env value when no DB row exists.

    Same rules as ``Authorization: Bearer`` for /api/v1 for DB keys (hash lookup,
    validity, per-key rate limit, ``last_used_at``). Used for ``X-Mobile-Auth``;
    the app sends the same plaintext as Flutter ``MOBILE_APP_API_KEY`` / Bearer.
    """
    from collections import deque

    from app.models.api_key_management import APIKey

    key = (provided_key or "").strip()
    if not key:
        return False

    try:
        key_hash = APIKey.hash_key(key)
        db_api_key = APIKey.query.filter_by(key_hash=key_hash).first()
        if db_api_key:
            if not db_api_key.is_valid():
                return False

            now = time.time()
            rate_limit_key = f"api_key_{db_api_key.id}"
            if rate_limit_key not in _api_key_rate_limit_storage:
                _api_key_rate_limit_storage[rate_limit_key] = deque()

            storage = _api_key_rate_limit_storage[rate_limit_key]
            while storage and storage[0] < now - 60:
                storage.popleft()
            if len(storage) >= db_api_key.rate_limit_per_minute:
                current_app.logger.warning(
                    "[X-Mobile-Auth] rate limit exceeded for api_keys.id=%s path=%s",
                    db_api_key.id,
                    request.path,
                )
                return False
            storage.append(now)

            try:
                db_api_key.update_last_used()
            except Exception as e:
                current_app.logger.warning("Failed to update API key last_used_at: %s", e)

            if current_app.config.get("LOG_API_KEY_USAGE", False):
                current_app.logger.info(
                    "X-Mobile-Auth DB API key ok: %s (prefix: %s...)",
                    db_api_key.client_name,
                    db_api_key.key_prefix,
                )

            return True

        return _try_finish_auth_with_env_mobile_api_key(
            log_prefix="[X-Mobile-Auth]", provided_key=key
        )
    except Exception as e:
        current_app.logger.error("Error validating X-Mobile-Auth API key: %s", e, exc_info=True)
        return False


def authenticate_api_request():
    """
    Authenticate API request and determine access level.

    Standard authentication (one of):
    1. API key in Authorization header: Bearer YOUR_API_KEY (database ``api_keys``
       or optional ``MOBILE_APP_API_KEY`` env when no DB row matches)
    2. HTTP Basic auth (email/password)
    3. Flask-Login session (browser)

    Returns:
        A 3-tuple (elevated_access, auth_user, api_key_record) on success, or a Response on failure.
    """
    from app.models import User
    from app.models.api_key_management import APIKey, APIKeyUsage
    from collections import deque

    elevated_access = False
    auth_user = None
    api_key_record = None

    # API key only from Authorization header (no query params for security)
    provided_key = None
    key_source = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        provided_key = auth_header[7:].strip()
        key_source = 'header'

    # Authenticate with database-managed API keys
    if provided_key:
        try:
            # Hash the provided key to search in database
            key_hash = APIKey.hash_key(provided_key)

            # Find matching API key
            db_api_key = APIKey.query.filter_by(key_hash=key_hash).first()

            if db_api_key:
                # Verify key is valid (active, not revoked, not expired)
                if not db_api_key.is_valid():
                    if db_api_key.is_revoked:
                        return api_error("API key has been revoked", 401)
                    expires_at = ensure_utc(db_api_key.expires_at) if db_api_key.expires_at else None
                    if expires_at and expires_at <= utcnow():
                        return api_error("API key has expired", 401)
                    else:
                        return api_error("API key is not active", 401)

                # Check rate limiting
                now = time.time()
                rate_limit_key = f"api_key_{db_api_key.id}"

                # Initialize storage if needed
                if rate_limit_key not in _api_key_rate_limit_storage:
                    _api_key_rate_limit_storage[rate_limit_key] = deque()

                # Clean old entries (older than 1 minute)
                storage = _api_key_rate_limit_storage[rate_limit_key]
                while storage and storage[0] < now - 60:
                    storage.popleft()

                # Check if rate limit exceeded
                if len(storage) >= db_api_key.rate_limit_per_minute:
                    return api_error("Rate limit exceeded", 429, extra={"retry_after": 60})

                # Add current request timestamp
                storage.append(now)

                # Update last used timestamp (async, don't block)
                try:
                    db_api_key.update_last_used()
                except Exception as e:
                    current_app.logger.warning(f"Failed to update API key last_used_at: {e}")

                # Store API key record in Flask g for usage tracking
                g.api_key_record = db_api_key
                g.api_key_usage_id = db_api_key.id
                g.api_key_usage_client_name = db_api_key.client_name
                api_key_record = db_api_key
                elevated_access = True

                # Log API key usage for security monitoring (optional)
                if current_app.config.get('LOG_API_KEY_USAGE', False):
                    current_app.logger.info(
                        f"Database API key authenticated: {db_api_key.client_name} "
                        f"(prefix: {db_api_key.key_prefix}..., source: {key_source}, endpoint: {request.endpoint})"
                    )

                return (elevated_access, auth_user, api_key_record)
            if _try_finish_auth_with_env_mobile_api_key(
                log_prefix="[API auth Bearer]", provided_key=provided_key
            ):
                g.api_key_record = None
                g.api_key_usage_id = None
                g.api_key_usage_client_name = None
                return (True, None, None)
            return api_error("Invalid API key", 401)
        except Exception as e:
            current_app.logger.error(f"Error checking database API keys: {e}", exc_info=True)
            return api_error("API authentication error", 500)

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
                from app.services.app_settings_service import get_organization_name
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
                extra={"hint": "Use Authorization: Bearer YOUR_API_KEY or HTTP Basic auth (email/password)"},
            )
            from app.services.app_settings_service import get_organization_name
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
    from app.services.authorization_service import AuthorizationService
    if AuthorizationService.is_system_manager(auth_user):
        return None
    if AuthorizationService.has_rbac_permission(auth_user, "admin.countries.view"):
        return None
    from app.models.core import UserEntityPermission
    perms = UserEntityPermission.query.filter_by(
        user_id=auth_user.id, entity_type="country"
    ).all()
    return {p.entity_id for p in perms}


def apply_user_template_scoping(queries, auth_user, template_id=None, country_id=None, period_name=None):
    """Apply RBAC template + entity-level filtering to queries for user-scoped access."""
    assigned_form_data_query = queries['assigned']
    public_form_data_query = queries['public']

    from app.services.authorization_service import AuthorizationService
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
        joins_exist = template_id is not None or country_id is not None or period_name is not None
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
