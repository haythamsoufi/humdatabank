"""
Activity Tracking Middleware

This module provides middleware and decorators for automatically tracking
user activities across the application.
"""

from __future__ import annotations

from functools import wraps
from flask import request, g, session, current_app
from flask_login import current_user
from app.utils.request_utils import is_static_asset_request
from app.services.user_analytics_service import (
    log_user_activity,
    log_admin_action,
    increment_session_page_views_without_activity_log,
    increment_session_page_views_without_activity_log_deferred,
    log_user_activity_explicit,
)
from app.utils.activity_endpoint_overrides import (
    resolve_post_activity_type,
    resolve_delete_activity_type,
    description_for_activity_type,
    endpoint_last_segment,
    strip_endpoint_verb_prefix,
)
from app.utils.activity_endpoint_catalog import (
    resolve_activity_catalog_spec,
    fallback_description_for_unmapped,
)
from app.utils.activity_endpoint_catalog.defaults import describe_get_request_without_catalog
from app.utils.activity_form_data_redaction import redact_activity_form_data
from app.utils.page_view_paths import page_view_path_key_from_request
from app.utils.activity_logging_skip import should_skip_activity_endpoint
import time


def _should_skip_endpoint(endpoint):
    """Return True if this endpoint should never be logged."""
    return should_skip_activity_endpoint(endpoint)


def _should_skip_auto_activity_request(req):
    """Skip automatic activity logging for noisy endpoints and embedded partial HTML fetches."""
    if not req or not req.endpoint:
        return False
    if _should_skip_endpoint(req.endpoint):
        return True
    # User form embeds analytics via ?partial=1 — do not log as a separate page view
    if req.endpoint == 'analytics.user_analytics' and req.args.get('partial', '0') == '1':
        return True
    return False


def _endpoint_last_segment(endpoint: str) -> str:
    if not endpoint or "." not in endpoint:
        return endpoint or ""
    return endpoint.rsplit(".", 1)[-1]


def _should_count_session_page_view_for_request(req) -> bool:
    """
    Decide whether to bump ``UserSessionLog.page_views`` for this request.

    Historically every GET was treated as a "page view", which inflated session
    counts with JSON/API/plugin GETs (``api_*`` routes, fetch() calls, etc.).
    We align with browser Fetch Metadata where available: real top-level document
    navigations send Sec-Fetch-Mode: navigate and Sec-Fetch-Dest: document.
    Subresource GETs (cors, same-origin XHR, etc.) typically do not.

    When Fetch Metadata is absent (older clients, some bots), we still exclude
    obvious JSON route names (last segment ``api_*``).

    The deferred path also maps main.dashboard POST to page_view for filter UI;
    those still bump the counter.
    """
    if not req:
        return False
    if req.endpoint == "main.dashboard" and req.method == "POST":
        return True
    if req.method != "GET":
        return False
    if _should_skip_auto_activity_request(req):
        return False
    seg = _endpoint_last_segment(req.endpoint or "")
    if seg.startswith("api_"):
        return False
    mode = (req.headers.get("Sec-Fetch-Mode") or "").lower()
    dest = (req.headers.get("Sec-Fetch-Dest") or "").lower()
    if mode or dest:
        return mode == "navigate" and dest == "document"
    return True


# ---------------------------------------------------------------------------
# Shared helpers (used by both deferred and non-deferred tracking paths)
# ---------------------------------------------------------------------------

def _determine_activity_type(method, endpoint, form_data=None):
    """Derive a specific, user-friendly activity type from request context.

    Returns one of the canonical activity-type strings understood by the
    audit trail's activityMap.
    """
    endpoint = endpoint or ''
    action = (form_data or {}).get('action', '').lower().strip()

    if method == 'GET':
        return 'page_view'

    if method in ('PUT', 'PATCH'):
        return 'data_modified'

    if method == 'DELETE':
        specific = resolve_delete_activity_type(endpoint)
        if specific:
            return specific
        return 'data_deleted'

    if method == 'POST':
        # Dedicated assignment lifecycle endpoints (no 'action' form field)
        if 'approve_assignment' in endpoint:
            return 'form_approved'
        if 'reopen_assignment' in endpoint:
            return 'form_reopened'
        if 'validate' in endpoint or 'verify' in endpoint:
            return 'form_validated'

        # Entry-form (focal-point data entry) — has an explicit 'action' field
        if endpoint in ('forms.enter_data',) or 'enter_data' in endpoint:
            if action == 'save':
                return 'form_saved'
            elif action == 'submit':
                return 'form_submitted'
            elif action == 'approve':
                return 'form_approved'
            elif action == 'reopen':
                return 'form_reopened'
            elif action == 'validate':
                return 'form_validated'
            else:
                # Autosave / AJAX / unknown action — not a formal submission
                return 'request'

        # File uploads
        if 'upload' in endpoint:
            return 'file_uploaded'

        # Generic: use the form action field
        if action == 'save':
            return 'form_saved'
        if action == 'submit':
            return 'form_submitted'
        if action == 'approve':
            return 'form_approved'
        if action == 'reopen':
            return 'form_reopened'
        if action == 'validate':
            return 'form_validated'

        # Known POST endpoints (settings, devices, access, …) — before generic ``request``
        specific = resolve_post_activity_type(endpoint)
        if specific:
            return specific

        # Generic POST (JSON APIs, AJAX, CSRF-only forms, etc.) — not assignment submit
        return 'request'

    return 'request'


# Catalog may replace generic activity types with a finite admin_* badge key.
_CATALOG_ACTIVITY_TYPE_OVERRIDABLE = frozenset(
    {
        "request",
        "page_view",
        "data_deleted",
        "data_modified",
        "file_uploaded",
        "ai_conversation_deleted",
        "ai_conversations_deleted_all",
        # Logged as settings_updated from POST segment map; catalog maps to admin_settings like other settings routes
        "settings_updated",
    }
)


def _apply_activity_catalog(method: str, endpoint: str | None, activity_type: str) -> tuple[str, str | None]:
    """
    If the endpoint is in ENDPOINT_ACTIVITY_SPECS, use its description and
    optionally override activity_type for generic buckets.
    Returns (activity_type, description_or_none). description_or_none is None if
    no catalog row exists.
    """
    m = (method or "GET").strip().upper() or "GET"
    # GET navigations are session page_views only — never attach catalog (or wildcard overrides).
    if m == "GET" and activity_type == "page_view":
        return activity_type, None
    spec = resolve_activity_catalog_spec(method, endpoint)
    if not spec:
        return activity_type, None
    at = activity_type
    if spec.activity_type and at in _CATALOG_ACTIVITY_TYPE_OVERRIDABLE:
        at = spec.activity_type
    return at, spec.description


def _build_activity_description(method, endpoint, activity_type):
    """Build a plain-English description for an activity log entry."""
    endpoint = endpoint or ''

    if activity_type == 'page_view':
        return describe_get_request_without_catalog(endpoint)

    if activity_type == 'request':
        return fallback_description_for_unmapped(method, endpoint)

    preset = description_for_activity_type(activity_type)
    if preset:
        return preset

    descriptions = {
        'form_saved':      "Saved form data as draft",
        'form_submitted':  "Submitted form data for review",
        'form_approved':   "Approved form submission",
        'form_reopened':   "Reopened form for editing",
        'form_validated':  "Validated form data",
        'data_modified':   "Updated data",
        'data_deleted':    "Deleted item",
        'file_uploaded':   "Uploaded a file",
        'login':           "Logged in",
        'logout':          "Logged out",
        'profile_update':  "Updated profile",
        'data_export':     "Exported data",
    }
    if activity_type in descriptions:
        return descriptions[activity_type]

    # Fallback: humanise the raw type string
    return activity_type.replace('_', ' ').title()


def track_activity(activity_type=None, description=None, admin_action=False, risk_level='low'):
    """
    Decorator to automatically track user activities.

    Args:
        activity_type (str): Type of activity to log
        description (str): Description of the activity
        admin_action (bool): Whether this is an admin action
        risk_level (str): Risk level for admin actions
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Record start time for performance tracking
            start_time = time.time()

            # Execute the function
            try:
                response = f(*args, **kwargs)
                status_code = getattr(response, 'status_code', 200)
            except Exception as e:
                status_code = 500
                raise e
            finally:
                # Calculate response time
                response_time_ms = int((time.time() - start_time) * 1000)

                # Log the activity if user is authenticated
                if current_user.is_authenticated:
                    # Determine activity type if not specified
                    if not activity_type:
                        form_data = request.form if request.form else None
                        act_type = _determine_activity_type(request.method, request.endpoint, form_data)
                        act_type, cdesc = _apply_activity_catalog(
                            request.method, request.endpoint, act_type
                        )
                    else:
                        act_type = activity_type
                        cdesc = None

                    # Build description if not provided
                    if not description:
                        desc = (
                            cdesc
                            if cdesc is not None
                            else _build_activity_description(
                                request.method, request.endpoint, act_type
                            )
                        )
                    else:
                        desc = description

                    # Gather context data
                    context_data = {
                        'endpoint': request.endpoint,
                        'method': request.method,
                        'status_code': status_code
                    }

                    # Add form data for POST requests (redacted; see activity_form_data_redaction)
                    if request.method == 'POST' and request.form:
                        context_data['form_data'] = redact_activity_form_data(request.form.items())

                    # Log as admin action if specified
                    from app.services.authorization_service import AuthorizationService
                    if admin_action and AuthorizationService.is_admin(current_user):
                        log_admin_action(
                            action_type=act_type,
                            description=desc,
                            risk_level=risk_level
                        )
                    else:
                        # Log regular user activity
                        log_user_activity(
                            activity_type=act_type,
                            description=desc,
                            context_data=context_data,
                            response_time_ms=response_time_ms,
                            status_code=status_code
                        )

            return response
        return decorated_function
    return decorator


def track_page_view(description=None):
    """Decorator specifically for tracking page views."""
    return track_activity(activity_type='page_view', description=description)


def track_form_submission(description=None):
    """Decorator specifically for tracking form submissions."""
    return track_activity(activity_type='form_submitted', description=description)


def track_file_upload(description=None):
    """Decorator specifically for tracking file uploads."""
    return track_activity(activity_type='file_uploaded', description=description)


def track_admin_action(action_type, description=None, risk_level='low'):
    """Decorator specifically for tracking admin actions."""
    return track_activity(
        activity_type=action_type,
        description=description,
        admin_action=True,
        risk_level=risk_level
    )


def _extract_entity_into_context(app, req, context_data):
    """Resolve the assignment entity (country, NS branch, etc.) from the request
    and write entity_type / entity_id / entity_name into context_data.

    Checks, in order:
      1. AssignmentEntityStatus ID from form fields
         (assignment_entity_status_id, aes_id)
      2. AssignmentEntityStatus ID from URL view_args (aes_id)
      3. Direct country_id from form data, URL args, or query string (legacy)

    Stores:
      entity_type  – 'country', 'ns_branch', etc.
      entity_id    – primary key of the entity
      entity_name  – display name for the audit trail
      (country_id / country_name kept for backward compatibility)
    """
    if 'entity_id' in context_data:
        return

    def _store_from_aes(aes_id):
        """Resolve an AssignmentEntityStatus row and populate context_data."""
        try:
            from app.models.assignments import AssignmentEntityStatus
            from app.services.entity_service import EntityService
            aes = AssignmentEntityStatus.query.get(int(aes_id))
            if not aes:
                return False
            entity_name = EntityService.get_entity_display_name(aes.entity_type, aes.entity_id)
            context_data['entity_type'] = aes.entity_type
            context_data['entity_id'] = aes.entity_id
            context_data['entity_name'] = entity_name
            # Backward compat — resolve the associated country too
            country = aes.country
            if country:
                context_data['country_id'] = country.id
                context_data['country_name'] = country.name
            return True
        except Exception:
            return False

    def _store_from_country(country_id):
        """Resolve a Country row and populate context_data."""
        try:
            from app.models import Country
            country = Country.query.get(int(country_id))
            if not country:
                return False
            context_data['entity_type'] = 'country'
            context_data['entity_id'] = country.id
            context_data['entity_name'] = country.name
            context_data['country_id'] = country.id
            context_data['country_name'] = country.name
            return True
        except Exception:
            return False

    try:
        # ── 1. Look for AES id in POST form data ──────────────────────────
        if req.method == 'POST' and req.form:
            # All naming variants used across the codebase
            aes_raw = (
                req.form.get('assignment_entity_status_id') or
                req.form.get('aes_id')
            )
            if aes_raw and str(aes_raw).isdigit():
                if _store_from_aes(aes_raw):
                    return

            # Direct country_id in form (admin forms, etc.)
            c_raw = req.form.get('country_id')
            if c_raw and str(c_raw).isdigit():
                if _store_from_country(c_raw):
                    return

        # ── 2. Look for AES id in URL route arguments ─────────────────────
        view_args = req.view_args or {}
        aes_url = view_args.get('aes_id')
        if aes_url and str(aes_url).isdigit():
            if _store_from_aes(aes_url):
                return

        # ── 3. Direct country_id from URL args or query string ─────────────
        c_url = view_args.get('country_id') or req.args.get('country_id')
        if c_url and str(c_url).isdigit():
            _store_from_country(c_url)

    except Exception as e:
        app.logger.debug(f"Could not extract entity info: {e}")


def init_activity_tracking(app):
    """
    Initialize activity tracking for the Flask app.
    This sets up automatic tracking for all requests.
    """
    # Register before_request first to ensure it runs before after_request
    @app.before_request
    def before_request():
        # Always set start_time for all requests
        g.start_time = time.time()

        # Skip tracking for static files and API routes
        if (is_static_asset_request() or
            not request.endpoint or
            _should_skip_auto_activity_request(request) or
            request.path.startswith('/api/v1/') or
            request.path.startswith('/api/mobile/')):
            return

        # Snapshot user identity now while the instance is still session-bound.
        # Route handlers may commit/rollback and detach current_user before
        # after_request runs.
        try:
            if current_user.is_authenticated:
                g.activity_user_id = current_user.id
                g.activity_session_id = session.get('session_id')
            else:
                g.activity_user_id = None
        except Exception as e:
            current_app.logger.debug("activity user snapshot failed: %s", e)
            g.activity_user_id = None

    @app.after_request
    def after_request(response):
        # Skip logging for background/static/API routes
        if (is_static_asset_request() or
            not request.endpoint or
            _should_skip_auto_activity_request(request) or
            request.path.startswith('/api/v1/') or
            request.path.startswith('/api/mobile/')):
            return response

        # Only log for authenticated users and successful requests
        user_id = getattr(g, 'activity_user_id', None)
        if user_id and response.status_code < 400:
            # If requests are transaction-managed, do NOT touch the request's db.session here.
            # Instead, log activity after the response closes using a fresh app context / new transaction.
            if getattr(g, "_auto_txn_managed", False):
                try:
                    from flask import current_app as _current_app

                    app_obj = _current_app._get_current_object()
                    session_id = getattr(g, 'activity_session_id', None)

                    # Capture request data now (request context won't exist in call_on_close)
                    endpoint = request.endpoint
                    method = request.method
                    url_path = request.path
                    referrer = request.referrer
                    from app.services.user_analytics_service import get_client_ip
                    ip_address = get_client_ip()
                    user_agent = request.headers.get('User-Agent')

                    # Safety check for start_time
                    if not hasattr(g, 'start_time'):
                        g.start_time = time.time()
                    response_time_ms = int((time.time() - g.start_time) * 1000)

                    # Determine activity type based on request
                    if endpoint == 'main.dashboard' and request.method == 'POST':
                        # Dashboard POST requests are UI interactions only (filtering/selection)
                        activity_type = 'page_view'
                    else:
                        form_data = request.form if request.form else None
                        activity_type = _determine_activity_type(request.method, endpoint, form_data)

                    # Skip background / noisy endpoints
                    if _should_skip_auto_activity_request(request):
                        return response

                    # Skip POSTs to blueprints that call log_admin_action for mutations, so we do not
                    # duplicate UserActivityLog + AdminActionLog. Assignment and AI admin POSTs are
                    # not skipped — they rely on automatic activity logging.
                    admin_routes_with_explicit_logging = (
                        'user_management.',
                        'form_builder.',
                    )
                    is_admin_route_with_logging = any(
                        request.endpoint and request.endpoint.startswith(p)
                        for p in admin_routes_with_explicit_logging
                    )
                    if request.method == 'POST' and is_admin_route_with_logging:
                        return response

                    if activity_type == "page_view" and not _should_count_session_page_view_for_request(
                        request
                    ):
                        return response

                    page_view_path_key = page_view_path_key_from_request(request)

                    activity_type, catalog_desc = _apply_activity_catalog(
                        method, endpoint, activity_type
                    )
                    description = (
                        catalog_desc
                        if catalog_desc is not None
                        else _build_activity_description(method, endpoint, activity_type)
                    )
                    _audit_desc = getattr(g, "audit_activity_description", None)
                    if _audit_desc:
                        description = _audit_desc

                    context_data = {
                        'endpoint': request.endpoint,
                        'method': request.method,
                        'status_code': response.status_code
                    }

                    # Enhanced context data for POST requests (redacted)
                    if request.method == 'POST' and request.form:
                        context_data['form_data'] = redact_activity_form_data(request.form.items())

                    # Extract country information (mirrors the non-deferred path)
                    _extract_entity_into_context(app, request, context_data)

                    def _on_close():
                        try:
                            with app_obj.app_context():
                                if activity_type == "page_view":
                                    increment_session_page_views_without_activity_log_deferred(
                                        session_id,
                                        page_view_path_key=page_view_path_key,
                                    )
                                else:
                                    log_user_activity_explicit(
                                        user_id=user_id,
                                        session_id=session_id,
                                        activity_type=activity_type,
                                        description=description,
                                        context_data=context_data,
                                        response_time_ms=response_time_ms,
                                        status_code=response.status_code,
                                        endpoint=endpoint,
                                        http_method=method,
                                        url_path=url_path,
                                        referrer=referrer,
                                        ip_address=ip_address,
                                        user_agent=user_agent,
                                    )
                        except Exception as e:
                            app_obj.logger.warning(f"Deferred activity logging failed: {str(e)}")

                    response.call_on_close(_on_close)
                    return response
                except Exception as e:
                    app.logger.warning(f"Skipping deferred activity logging due to setup error: {str(e)}")
                    return response

            try:
                # Safety check for start_time
                if not hasattr(g, 'start_time'):
                    g.start_time = time.time()
                response_time_ms = int((time.time() - g.start_time) * 1000)

                # Determine activity type based on request
                activity_type = _determine_activity_type(
                    request.method, request.endpoint,
                    request.form if request.form else None
                )

                # Skip background / noisy endpoints
                if _should_skip_auto_activity_request(request):
                    return response

                # See deferred path: only blueprints with explicit log_admin_action on POST.
                admin_routes_with_explicit_logging = (
                    'user_management.',
                    'form_builder.',
                )
                is_admin_route_with_logging = any(
                    request.endpoint and request.endpoint.startswith(p)
                    for p in admin_routes_with_explicit_logging
                )
                if request.method == 'POST' and is_admin_route_with_logging:
                    return response

                if activity_type == "page_view" and not _should_count_session_page_view_for_request(
                    request
                ):
                    return response

                activity_type, catalog_desc = _apply_activity_catalog(
                    request.method, request.endpoint, activity_type
                )
                description = (
                    catalog_desc
                    if catalog_desc is not None
                    else _build_activity_description(
                        request.method, request.endpoint, activity_type
                    )
                )
                _audit_desc = getattr(g, "audit_activity_description", None)
                if _audit_desc:
                    description = _audit_desc

                # Gather context data
                context_data = {
                    'endpoint': request.endpoint,
                    'method': request.method,
                    'status_code': response.status_code
                }

                # Enhanced context data for POST requests (redacted)
                if request.method == 'POST' and request.form:
                    context_data['form_data'] = redact_activity_form_data(request.form.items())

                # Extract country information from form data, URL args, or view args
                _extract_entity_into_context(app, request, context_data)

                # Automatic GET "page_view" — session stats only (no per-hit audit row)
                if activity_type == "page_view":
                    increment_session_page_views_without_activity_log()
                else:
                    log_user_activity(
                        activity_type=activity_type,
                        description=description,
                        context_data=context_data,
                        response_time_ms=response_time_ms,
                        status_code=response.status_code
                    )
            except Exception as e:
                app.logger.error(f"Error in activity tracking: {str(e)}")
                # Don't let activity tracking errors affect the response
                # The database session might be in a failed state, so we can't do much more

        return response


class ActivityLogger:
    """
    Context manager for logging complex activities.

    Usage:
        with ActivityLogger('complex_operation', 'Processing form data') as logger:
            # Do some work
            logger.add_context('processed_items', 50)
            # Do more work
            logger.add_context('errors', 2)
    """

    def __init__(self, activity_type, description, admin_action=False, risk_level='low'):
        self.activity_type = activity_type
        self.description = description
        self.admin_action = admin_action
        self.risk_level = risk_level
        self.context_data = {}
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        response_time_ms = int((time.time() - self.start_time) * 1000)

        if exc_type:
            self.context_data['error'] = str(exc_val)
            self.context_data['error_type'] = exc_type.__name__

        if current_user.is_authenticated:
            from app.services.authorization_service import AuthorizationService
            if self.admin_action and AuthorizationService.is_admin(current_user):
                log_admin_action(
                    action_type=self.activity_type,
                    description=self.description,
                    risk_level=self.risk_level
                )
            else:
                log_user_activity(
                    activity_type=self.activity_type,
                    description=self.description,
                    context_data=self.context_data,
                    response_time_ms=response_time_ms
                )

    def add_context(self, key, value):
        """Add context data to the activity log."""
        self.context_data[key] = value
