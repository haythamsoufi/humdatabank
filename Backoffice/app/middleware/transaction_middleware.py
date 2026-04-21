"""
Hybrid transaction middleware.

Default behavior (managed requests):
- Commit at end of request if response status < 400
- Roll back at end of request if response status >= 400 or if an exception occurred
- Always remove the session (or on-close for streaming responses)

Opt-outs:
- Views decorated with @no_auto_transaction (see app/utils/transactions.py)
- Streaming responses (SSE/generator responses) are not auto-committed/rolled back;
  session removal is deferred to response close.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any, Optional

from flask import current_app, g, request

from app.extensions import db
from app.utils.transactions import (
    is_streaming_response,
    is_view_forced,
    is_view_opted_out,
    run_post_commit_callbacks,
    safe_remove,
    safe_rollback,
)

logger = logging.getLogger(__name__)


def _get_view_func() -> Optional[Any]:
    try:
        if not request.endpoint:
            return None
        return current_app.view_functions.get(request.endpoint)
    except Exception as e:
        # If endpoint lookup fails, fall back to None and let middleware treat it as managed/unmanaged accordingly.
        logger.debug("Transaction middleware: failed to resolve view function for endpoint=%s: %s", getattr(request, "endpoint", None), e, exc_info=True)
        return None


def init_transaction_middleware(app):
    """
    Register request lifecycle hooks for transaction management.
    """
    # Ensure exceptions that Flask converts into 500 responses still trigger rollback.
    # In some Flask execution paths, after_request/teardown_request may not receive the original exception.
    if not getattr(app, "_auto_txn_handle_exception_wrapped", False):
        original_handle_exception = app.handle_exception

        def _auto_txn_handle_exception(e):  # type: ignore[no-redef]
            try:
                # Rollback any pending work and clear failed state
                safe_rollback(reason="handle_exception")
            finally:
                safe_remove(reason="handle_exception")
            return original_handle_exception(e)

        app.handle_exception = _auto_txn_handle_exception  # type: ignore[assignment]
        app._auto_txn_handle_exception_wrapped = True

    @app.before_request
    def _txn_before_request():
        # Defaults
        g._auto_txn_managed = False
        g._auto_txn_streaming = False

        # Skip static and unknown endpoints
        if not request.endpoint or request.endpoint.startswith("static"):
            return

        view_func = _get_view_func()
        if is_view_opted_out(view_func) and not is_view_forced(view_func):
            g._auto_txn_managed = False
            return

        # Default: manage all non-opted-out endpoints
        g._auto_txn_managed = True

    @app.after_request
    def _txn_after_request(response):
        managed = bool(getattr(g, "_auto_txn_managed", False))
        force_rollback = bool(getattr(g, "_auto_txn_force_rollback", False))

        # Detect streaming responses and defer session cleanup
        if is_streaming_response(response):
            g._auto_txn_streaming = True
            with suppress(Exception):
                response.call_on_close(lambda: safe_remove(reason="stream_close"))
            return response

        if not managed:
            # Not managed: do nothing (leave existing explicit commit/rollback patterns)
            return response

        # Managed, non-streaming response: commit or rollback based on status code
        try:
            status_code = getattr(response, "status_code", 500)
            if force_rollback:
                safe_rollback(reason="manual_request")
            elif status_code >= 400:
                safe_rollback(reason=f"response_status_{status_code}")
            else:
                db.session.commit()
                run_post_commit_callbacks()
        except Exception as e:
            # Commit failure must rollback to clear failed state
            safe_rollback(reason="commit_failed")
            logger.error("Auto transaction commit failed: %s", e, exc_info=True)
            raise
        finally:
            safe_remove(reason="after_request")

        return response

    @app.teardown_request
    def _txn_teardown_request(exception):
        streaming = bool(getattr(g, "_auto_txn_streaming", False))

        # Streaming responses handle cleanup on close
        if streaming:
            return

        # On any exception, rollback to clear failed/dirty state (even for opt-out endpoints).
        if exception is not None:
            safe_rollback(reason="teardown_exception")

        # Always remove; safe_remove is idempotent
        safe_remove(reason="teardown")
