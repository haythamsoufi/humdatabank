"""Validation and abuse throttles for anonymous indicator-suggestion submissions."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from flask import current_app

from app.models.enums import IndicatorSuggestionTypeValue
from app.utils.advanced_validation import AdvancedValidator
from app.utils.datetime_helpers import utcnow

MAX_SHORT_TEXT = 255
MAX_MEDIUM_TEXT = 50
MAX_LONG_TEXT = 5000
DEFAULT_PER_EMAIL_DAILY_LIMIT = 3
DEFAULT_GLOBAL_HOURLY_LIMIT = 100

_SECTOR_LEVELS = ("primary", "secondary", "tertiary")


class SuggestionValidationError(ValueError):
    """Raised with a client-safe message when a suggestion payload is rejected."""


def _text(data: dict, key: str, max_len: int, *, required: bool = False) -> Optional[str]:
    value = data.get(key)
    if value is None or value == "":
        if required:
            raise SuggestionValidationError(f"Missing required field: {key}")
        return None
    if not isinstance(value, str):
        raise SuggestionValidationError(f"Field must be a string: {key}")
    value = value.strip()
    if not value:
        if required:
            raise SuggestionValidationError(f"Missing required field: {key}")
        return None
    if len(value) > max_len:
        raise SuggestionValidationError(f"Field too long (max {max_len} characters): {key}")
    return value


def _classification(data: dict, key: str, label: str) -> Optional[dict]:
    raw = data.get(key)
    if raw in (None, "", {}):
        return None
    if isinstance(raw, str):
        raw = {"primary": raw}
    if not isinstance(raw, dict):
        raise SuggestionValidationError(f"Field must be a string or object: {key}")
    unknown = set(raw) - set(_SECTOR_LEVELS)
    if unknown:
        raise SuggestionValidationError(f"Unsupported keys in {key}")
    result: dict[str, Optional[str]] = {}
    for level in _SECTOR_LEVELS:
        result[level] = _text(raw, level, MAX_SHORT_TEXT)
    if not result["primary"]:
        raise SuggestionValidationError(f"Primary {label} must be filled")
    return result


def _indicator_id(data: dict) -> Optional[int]:
    raw = data.get("indicator_id")
    if raw in (None, ""):
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise SuggestionValidationError("indicator_id must be an integer")
    try:
        indicator_id = int(raw)
    except (TypeError, ValueError):
        raise SuggestionValidationError("indicator_id must be an integer") from None
    if indicator_id <= 0:
        raise SuggestionValidationError("indicator_id must be an integer")
    return indicator_id


def _emergency(data: dict) -> bool:
    raw = data.get("emergency", False)
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw.strip().lower() in ("true", "false", "yes", "no", "1", "0"):
        return raw.strip().lower() in ("true", "yes", "1")
    raise SuggestionValidationError("emergency must be a boolean")


def validate_suggestion_payload(data: Any) -> dict:
    """Return sanitized ``IndicatorSuggestion`` column values or raise ``SuggestionValidationError``."""
    from app.extensions import db
    from app.models import IndicatorBank

    if not isinstance(data, dict):
        raise SuggestionValidationError("Request body must be a JSON object")

    email = _text(data, "submitter_email", MAX_SHORT_TEXT, required=True)
    if not AdvancedValidator.validate_email(email):
        raise SuggestionValidationError("submitter_email must be a valid email address")

    suggestion_type = _text(data, "suggestion_type", MAX_MEDIUM_TEXT, required=True)
    if suggestion_type not in IndicatorSuggestionTypeValue.values():
        raise SuggestionValidationError("Unsupported suggestion_type")

    indicator_id = _indicator_id(data)
    if indicator_id is not None and db.session.get(IndicatorBank, indicator_id) is None:
        raise SuggestionValidationError("Unknown indicator_id")

    return {
        "submitter_name": _text(data, "submitter_name", MAX_SHORT_TEXT, required=True),
        "submitter_email": email.lower(),
        "suggestion_type": suggestion_type,
        "indicator_id": indicator_id,
        "indicator_name": _text(data, "indicator_name", MAX_SHORT_TEXT, required=True),
        "definition": _text(data, "definition", MAX_LONG_TEXT),
        "type": _text(data, "type", MAX_MEDIUM_TEXT),
        "unit": _text(data, "unit", MAX_MEDIUM_TEXT),
        "sector": _classification(data, "sector", "sector"),
        "sub_sector": _classification(data, "sub_sector", "subsector"),
        "emergency": _emergency(data),
        "related_programs": _text(data, "related_programs", MAX_LONG_TEXT),
        "reason": _text(data, "reason", MAX_LONG_TEXT, required=True),
        "additional_notes": _text(data, "additional_notes", MAX_LONG_TEXT),
    }


def suggestion_throttle_error(email: str) -> Optional[str]:
    """Persistent (DB-backed, so worker-independent) per-email and global submission caps."""
    from app.extensions import db
    from app.models import IndicatorSuggestion

    per_email = int(current_app.config.get("SUGGESTION_PER_EMAIL_DAILY_LIMIT", DEFAULT_PER_EMAIL_DAILY_LIMIT))
    global_hourly = int(current_app.config.get("SUGGESTION_GLOBAL_HOURLY_LIMIT", DEFAULT_GLOBAL_HOURLY_LIMIT))
    now = utcnow()

    if per_email > 0:
        recent_for_email = IndicatorSuggestion.query.filter(
            db.func.lower(IndicatorSuggestion.submitter_email) == email.lower(),
            IndicatorSuggestion.submitted_at >= now - timedelta(days=1),
        ).count()
        if recent_for_email >= per_email:
            return "Too many suggestions from this email address. Please try again later."

    if global_hourly > 0:
        recent_total = IndicatorSuggestion.query.filter(
            IndicatorSuggestion.submitted_at >= now - timedelta(hours=1),
        ).count()
        if recent_total >= global_hourly:
            return "Suggestions are temporarily unavailable. Please try again later."
    return None
