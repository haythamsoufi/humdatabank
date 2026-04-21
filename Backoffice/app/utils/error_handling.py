"""
Centralized exception handling for Flask views.

=============================================================================
When to use which helper
=============================================================================

1. handle_view_exception(error, message, ...)
   - HTML/form views that flash and redirect
   - Use in: except Exception as e: return handle_view_exception(e, "Error message")

2. handle_json_view_exception(error, message, status_code=500)
   - JSON/AJAX routes that return JSON on error
   - Use in: except Exception as e: return handle_json_view_exception(e, "Error message")

3. @json_error_handler('Route name') (from api_responses)
   - Decorator for JSON-only routes; no per-route try/except needed
   - Catches Exception, rolls back, logs, returns json_server_error

4. Prefer specific exceptions where possible:
   - Config/parsing: except (ValueError, TypeError, KeyError): use default
   - DB: except (IntegrityError, OperationalError): handle known DB errors
   - Path ops: except ValueError for path.relative_to() (path traversal)
   - Avoid bare "except Exception: pass" without logging; use suppress_with_log() for optional ops
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Dict, Iterator, Optional, Tuple, TypeVar

from flask import current_app, flash, redirect, url_for

from app.utils.transactions import request_transaction_rollback

logger = logging.getLogger(__name__)

T = TypeVar("T")


@contextmanager
def suppress_with_log(
    *exceptions: type[BaseException],
    message: str = "Operation failed (suppressed)",
    log_level: int = logging.DEBUG,
) -> Iterator[None]:
    """
    Context manager that logs before suppressing specified exceptions.
    Use for optional operations where failure is acceptable but should be visible in logs.

    Example:
        with suppress_with_log(AttributeError, ValueError, message="Optional metadata"):
            obj.extra = parse_metadata(raw)
    """
    try:
        yield
    except exceptions as e:
        logger.log(log_level, f"{message}: {e}", exc_info=log_level <= logging.DEBUG)


def handle_view_exception(
    error: Exception,
    user_message: str,
    *,
    flash_category: str = "danger",
    redirect_endpoint: Optional[str] = None,
    redirect_kwargs: Optional[Dict[str, object]] = None,
    redirect_url: Optional[str] = None,
    status_code: int = 500,
    abort_on_unhandled: bool = False,
    log_message: Optional[str] = None,
    rollback_reason: str = "view_exception",
):
    """
    Centralized helper for handling exceptions inside view functions.

    - Rolls back the current transaction via request_transaction_rollback
    - Logs the exception with stack trace
    - Flashes a user-facing message
    - Optionally redirects or aborts

    Returns:
        Optional[Response]: redirect response when redirect parameters are provided.
    """
    request_transaction_rollback(reason=rollback_reason)

    logger = current_app.logger
    log_text = log_message or user_message or "Unhandled error in view"
    logger.error(log_text, exc_info=True)

    if user_message:
        flash(user_message, flash_category)

    if redirect_url:
        return redirect(redirect_url)

    if redirect_endpoint:
        kwargs = redirect_kwargs or {}
        return redirect(url_for(redirect_endpoint, **kwargs))

    if abort_on_unhandled:
        from flask import abort
        abort(status_code)

    return None


def handle_json_view_exception(
    error: Exception,
    user_message: str,
    *,
    status_code: int = 500,
    log_message: Optional[str] = None,
    rollback_reason: str = "view_exception",
) -> Tuple[object, int]:
    """
    Handle exceptions in JSON/AJAX views; returns (response, status_code) for return.

    Use in routes that always return JSON (AJAX, API). Rolls back transaction,
    logs the exception, and returns a JSON error response.

    Returns:
        Tuple of (json_response, status_code) suitable for: return handle_json_view_exception(...)

    Example:
        try:
            ...
        except Exception as e:
            return handle_json_view_exception(e, "Failed to save.", status_code=400)
    """
    from app.utils.api_responses import json_error

    request_transaction_rollback(reason=rollback_reason)

    logger = current_app.logger
    log_text = log_message or user_message or "Unhandled error in JSON view"
    logger.error(log_text, exc_info=True)

    return json_error(user_message, status=status_code, success=False)
