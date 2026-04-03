# ========== API Authentication Utilities ==========
"""
Authentication and authorization functions for API routes.

Contract:
- Auth success always returns a 3-tuple:
    (elevated_access: bool, auth_user: User|None, api_key_record: APIKey|None)
- Auth failure always returns a JSON Response using the standardized API error schema.
"""

from app.utils.datetime_helpers import utcnow, ensure_utc

import time
from flask import request, current_app, g
from flask_login import current_user
from sqlalchemy import select, union_all, literal
from app import db
from app.models import FormTemplate, TemplateShare, FormData, AssignedForm
from app.models.assignments import AssignmentEntityStatus
from app.utils.api_helpers import json_response, api_error, MAX_PER_PAGE, DEFAULT_PER_PAGE, DEFAULT_PAGE
from datetime import datetime

# Rate limiting storage for API keys (key_id -> list of timestamps)
_api_key_rate_limit_storage = {}


def authenticate_db_api_key_only():
    """
    Authenticate request using ONLY a database-managed API key.

    Expected header:
      Authorization: Bearer <api_key>

    Returns:
      APIKey record on success, or a JSON Response on failure.
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
            current_app.logger.warning("[API auth] 401 %s: invalid API key (no matching key). path=%s", endpoint, request.path)
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


def authenticate_api_request():
    """
    Authenticate API request and determine access level.

    Standard authentication (one of):
    1. API key in Authorization header: Bearer YOUR_API_KEY (database-managed)
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
                api_key_record = db_api_key
                elevated_access = True

                # Log API key usage for security monitoring (optional)
                if current_app.config.get('LOG_API_KEY_USAGE', False):
                    current_app.logger.info(
                        f"Database API key authenticated: {db_api_key.client_name} "
                        f"(prefix: {db_api_key.key_prefix}..., source: {key_source}, endpoint: {request.endpoint})"
                    )

                return (elevated_access, auth_user, api_key_record)
            # Bearer header was present but did not match a DB key
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
                from app.utils.app_settings import get_organization_name
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
            from app.utils.app_settings import get_organization_name
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


def apply_user_template_scoping(queries, auth_user, template_id=None, country_id=None, period_name=None):
    """Apply RBAC template filtering to queries for user-scoped access."""
    assigned_form_data_query = queries['assigned']
    public_form_data_query = queries['public']

    # System managers have access to all templates - skip filtering
    from app.services.authorization_service import AuthorizationService
    if AuthorizationService.is_system_manager(auth_user):
        # Return queries unchanged - system managers see all templates
        return queries

    # Get allowed template IDs efficiently
    allowed_template_ids = get_user_allowed_template_ids(auth_user.id)

    if not allowed_template_ids:
        # User has no access to any templates
        return {
            'assigned': FormData.query.filter(literal(False)),
            'public': FormData.query.filter(literal(False))
        }

    # Apply template scoping to queries
    if assigned_form_data_query is not None:
        # Check if joins already exist (they do if template_id, country_id, or period_name was provided)
        joins_exist = template_id is not None or country_id is not None or period_name is not None
        if joins_exist:
            # Joins already exist, just add the filter
            assigned_form_data_query = assigned_form_data_query.filter(AssignedForm.template_id.in_(allowed_template_ids))
        else:
            # Joins don't exist yet, add them before filtering
            assigned_form_data_query = assigned_form_data_query.join(AssignmentEntityStatus).join(AssignedForm).filter(AssignedForm.template_id.in_(allowed_template_ids))

    if public_form_data_query is not None:
        # Public query already joins AssignedForm
        public_form_data_query = public_form_data_query.filter(AssignedForm.template_id.in_(allowed_template_ids))

    return {
        'assigned': assigned_form_data_query,
        'public': public_form_data_query
    }
