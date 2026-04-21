import time
from functools import wraps
from flask import request, g, current_app
from app.models.api_usage import APIUsage
from app.utils.api_helpers import get_json_safe
from app import db


def _should_skip_api_usage_tracking() -> bool:
    """
    High-volume or low-signal endpoints excluded from api_usage (and API key usage rows).
    Keep in sync with both before_request and after_request hooks.
    """
    path = request.path or ""
    method = (request.method or "").upper()

    if "notifications" in path or "refresh-csrf-token" in path:
        return True
    # Live presence heartbeats (not meaningful for aggregate API analytics)
    if path.startswith("/api/forms/presence/"):
        return True
    # WebSocket upgrade endpoints
    if path in ("/api/ai/v2/ws", "/api/ai/documents/ws"):
        return True
    # Streaming / cancel — tracked elsewhere; not comparable to normal REST latency
    if path in ("/api/ai/v2/chat/stream", "/api/ai/v2/chat/cancel"):
        return True
    # Product tour content under document workflows
    if path.startswith("/api/ai/documents/workflows/") and path.endswith("/tour"):
        return True
    # Lookup dropdown option fetches
    if path.startswith("/api/forms/lookup-lists/") and path.endswith("/options"):
        return True
    if path == "/api/forms/dynamic-indicators/render-pending":
        return True
    if path == "/api/ai/v2/token":
        return True
    if path == "/api/v1/variables/resolve":
        return True
    # Polled conversation list / single conversation (GET only)
    if method == "GET" and path == "/api/ai/v2/conversations":
        return True
    if method == "GET" and path.startswith("/api/ai/v2/conversations/"):
        rest = path[len("/api/ai/v2/conversations/"):]
        if rest and "/" not in rest:
            return True
    return False


def _api_tracker_logger():
    """
    API tracker emits *terminal* logs at a configurable level.
    DB tracking always runs regardless of this level.
    """
    level_name = str(current_app.config.get("API_TRACKER_LOG_LEVEL") or "DEBUG").strip().upper()
    import logging
    if level_name in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level = getattr(logging, level_name)
    else:
        level = logging.DEBUG
    return current_app.logger, level

def track_api_request():
    """Track API request before it's processed."""
    if request.path.startswith('/api/'):
        if _should_skip_api_usage_tracking():
            return

        g.api_start_time = time.time()
        logger, level = _api_tracker_logger()
        logger.log(level, "Starting API request tracking for: %s", request.path)

def track_api_response(response):
    """Track API response after it's processed."""
    if request.path.startswith('/api/'):
        if _should_skip_api_usage_tracking():
            return response

        try:
            # Calculate response time
            start_time = getattr(g, 'api_start_time', None)
            if start_time is None:
                # Missing start time; skip tracking for this response safely
                return response
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds

            # Create a separate database session to avoid transaction conflicts
            from sqlalchemy.orm import sessionmaker
            temp_db = sessionmaker(bind=db.engine)()
            try:
                raw_data = get_json_safe()
                if raw_data and isinstance(raw_data, dict):
                    _REDACT_KEYS = {
                        'password', 'password_hash', 'secret', 'token',
                        'api_key', 'apikey', 'access_token', 'refresh_token',
                        'secret_key', 'authorization', 'credit_card',
                        'ssn', 'social_security',
                    }
                    raw_data = {
                        k: '***REDACTED***' if k.lower() in _REDACT_KEYS else v
                        for k, v in raw_data.items()
                    }

                usage = APIUsage(
                    api_endpoint=request.path,
                    ip_address=request.remote_addr,
                    method=request.method,
                    status_code=response.status_code,
                    response_time=response_time,
                    user_agent=request.user_agent.string if request.user_agent else None,
                    request_data=raw_data
                )

                temp_db.add(usage)

                # Also track API key usage if a database-managed key was used
                api_key_id = getattr(g, 'api_key_usage_id', None)
                client_name = getattr(g, 'api_key_usage_client_name', None)
                if api_key_id is None:
                    api_key_record = getattr(g, 'api_key_record', None)
                    if api_key_record is not None:
                        from sqlalchemy import inspect as sa_inspect

                        insp = sa_inspect(api_key_record)
                        if insp.identity:
                            api_key_id = insp.identity[0]
                if api_key_id is not None:
                    from app.models.api_key_management import APIKeyUsage

                    key_usage = APIKeyUsage(
                        api_key_id=api_key_id,
                        endpoint=request.path,
                        method=request.method,
                        ip_address=request.remote_addr,
                        user_agent=request.user_agent.string if request.user_agent else None,
                        status_code=response.status_code,
                        response_time_ms=response_time,
                        request_data=get_json_safe()
                    )

                    temp_db.add(key_usage)

                    logger, level = _api_tracker_logger()
                    logger.log(
                        level,
                        "Tracked API key usage: %s (key_id: %s, endpoint: %s, status: %s, time: %.2fms)",
                        client_name or "?",
                        api_key_id,
                        request.path,
                        response.status_code,
                        response_time,
                    )

                temp_db.commit()

                logger, level = _api_tracker_logger()
                logger.log(
                    level,
                    "Tracked API usage: %s %s (status: %s, time: %.2fms)",
                    request.method,
                    request.path,
                    response.status_code,
                    response_time,
                )
            except Exception as e:
                current_app.logger.error(f"Error saving API usage: {str(e)}", exc_info=True)
                temp_db.rollback()
            finally:
                temp_db.close()

        except Exception as e:
            current_app.logger.error(f"Error in API tracking setup: {str(e)}", exc_info=True)

    return response

def track_api_usage(f):
    """Decorator for tracking API usage (legacy support)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        track_api_request()

        try:
            response = f(*args, **kwargs)
            return track_api_response(response)
        except Exception as e:
            current_app.logger.error(f"Error in API tracking: {str(e)}", exc_info=True)
            raise

    return decorated_function
