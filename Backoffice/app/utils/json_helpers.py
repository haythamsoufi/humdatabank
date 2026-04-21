"""Shared JSON utility helpers.

Provides a robust deep-copy function for JSON-serializable values,
used by template cloning, item duplication, and similar workflows.
"""

import copy
import json
import logging

logger = logging.getLogger(__name__)


def deep_copy_json(value):
    """Best-effort deep copy for JSON-serializable values.

    Attempts ``json.loads(json.dumps(value))`` first for a clean copy.
    Falls back to :func:`copy.deepcopy`, then shallow ``.copy()`` for
    dicts/lists, and finally returns primitives as-is.

    Args:
        value: Any JSON-serializable value (dict, list, str, int, etc.).

    Returns:
        A deep copy of *value*, or *value* itself when copying is impossible.
        Returns ``None`` when *value* is ``None``.
    """
    if value is None:
        return None
    try:
        return json.loads(json.dumps(value))
    except Exception:
        logger.debug("deep_copy_json: json roundtrip failed, trying deepcopy")
        try:
            return copy.deepcopy(value)
        except Exception:
            logger.debug("deep_copy_json: deepcopy failed, using shallow fallback")
            if isinstance(value, (str, int, float, bool)):
                return value
            if isinstance(value, dict):
                return value.copy()
            if isinstance(value, list):
                return value.copy()
            return value
