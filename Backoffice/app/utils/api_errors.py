"""Distinguish deliberate, user-presentable validation errors from incidental ``ValueError``s.

``except ValueError as exc: return api_error(str(exc), 400)`` leaks whatever text the
failing library produced (parser internals, SQL fragments, file paths). Services that
want a message shown to the API client must raise :class:`ClientInputError`; routes then
use :func:`client_error_message`, which returns the message for a ``ClientInputError``
and a stable generic string for any other exception (whose detail is logged server-side).
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

GENERIC_BAD_REQUEST_MESSAGE = "Invalid request parameters."
GENERIC_NOT_FOUND_MESSAGE = "The requested resource was not found."


class ClientInputError(ValueError):
    """Validation failure whose message is safe to return to the caller.

    The deliberate text is kept in ``public_message`` so responses never depend on
    ``str(exc)``, which for other exception types can carry internal detail.
    """

    def __init__(self, message: str = "", *args):
        super().__init__(message, *args)
        self.public_message = str(message)


def client_error_message(
    exc: BaseException,
    fallback: str = GENERIC_BAD_REQUEST_MESSAGE,
    *,
    context: Optional[str] = None,
) -> str:
    if isinstance(exc, ClientInputError):
        return exc.public_message
    logger.warning(
        "Suppressed non-client ValueError%s: %.300s",
        f" ({context})" if context else "",
        exc,
        exc_info=True,
    )
    return fallback
