"""Preview translation for entry-form text and textarea values.

The preview is computed on demand and returned to the browser. Nothing is
written back to the field, the submission, or the assignment.
"""

from __future__ import annotations

import base64

from flask import current_app
from flask_login import current_user, login_required

from app import get_locale
from app.extensions import limiter
from app.utils.api.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api.api_responses import json_bad_request, json_forbidden, json_not_found, json_ok
from app.utils.common.error_handling import handle_json_view_exception
from app.utils.http.request_validation import enforce_csrf_json
from app.utils.i18n.language_names import language_display_name

from app.services.forms.field_text_language import (
    normalize_language_code,
    translation_preview_decision,
)

# Long enough for a narrative answer. The stored value is never truncated;
# only the text sent to the translator is.
_MAX_PREVIEW_CHARS = 8000


def register_field_translation_routes(bp):
    """Register the entry-form translation preview route."""

    @bp.route("/api/field-text-translation-preview", methods=["POST"])
    @login_required
    @limiter.limit("40 per minute")
    def field_text_translation_preview():
        """Return a display-language preview of one free-text answer.

        The caller's selected display language (session locale) is the target.
        The response is a preview only: callers must not write it into the field.
        """
        csrf_error = enforce_csrf_json()
        if csrf_error is not None:
            return csrf_error

        data = get_json_safe()
        if not isinstance(data, dict):
            return json_bad_request("A JSON body is required.")

        try:
            text = _read_text(data)
        except ValueError:
            return json_bad_request("The text could not be read.")

        text = text.strip()
        if not text:
            return json_bad_request("Text is required.")

        auth_error = _authorize_preview(data)
        if auth_error is not None:
            return auth_error

        truncated = False
        if len(text) > _MAX_PREVIEW_CHARS:
            text = text[:_MAX_PREVIEW_CHARS]
            truncated = True

        target = normalize_language_code(str(get_locale() or "en"))
        decision = translation_preview_decision(text, target)
        payload = {
            "preview_only": True,
            "show_preview": False,
            "detected_language": decision["detected_language"],
            "target_language": target,
            "target_language_name": _language_name(target, target),
            "translation": None,
            "truncated": truncated,
        }
        if decision["detected_language"]:
            payload["detected_language_name"] = _language_name(decision["detected_language"], target)

        if not decision["offer"]:
            return json_ok(**payload)

        payload["show_preview"] = True
        try:
            from app.services.translation.auto_translator import get_auto_translator

            translated = get_auto_translator().translate_text(
                text,
                target,
                decision["detected_language"],
            )
        except Exception as exc:
            return handle_json_view_exception(
                exc,
                GENERIC_ERROR_MESSAGE,
                status_code=500,
                log_message="Field translation preview failed",
            )

        if not translated or not str(translated).strip():
            payload["unavailable"] = True
            return json_ok(**payload)

        payload["translation"] = str(translated)
        return json_ok(**payload)


def _read_text(data: dict) -> str:
    """Read plain text, or base64 text posted to avoid WAF false positives."""
    encoded = data.get("text_b64")
    if encoded:
        try:
            return base64.b64decode(str(encoded), validate=False).decode("utf-8")
        except Exception as exc:
            raise ValueError("invalid text_b64") from exc
    text = data.get("text")
    if text is None:
        return ""
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    return text


def _language_name(code: str, viewer: str) -> str:
    try:
        name = language_display_name(code, viewer)
    except Exception:
        current_app.logger.debug("language name lookup failed for %s", code, exc_info=True)
        name = None
    return name or code.upper()


def _authorize_preview(data: dict):
    """Allow the preview only for a form the caller can already open.

    Assignment viewers (focal points and admins) pass the assignment id.
    Public-submission reviewers pass the submission id. Template preview has
    neither id and is limited to admins.
    """
    from app.extensions import db
    from app.models import PublicSubmission
    from app.services.organization.authorization_service import AuthorizationService
    from app.utils.forms.form_authorization import (
        AES_ACTION_VIEW,
        AUTH_OK,
        PUBLIC_SUBMISSION_ACTION_VIEW,
        authorize_aes_json,
        public_submission_access,
    )

    aes_id = data.get("assignment_entity_status_id")
    if aes_id not in (None, ""):
        _aes, err = authorize_aes_json(aes_id, AES_ACTION_VIEW)
        return err

    submission_id = data.get("public_submission_id")
    if submission_id not in (None, ""):
        try:
            pk = int(submission_id)
        except (TypeError, ValueError):
            return json_not_found("Submission not found")
        submission = db.session.get(PublicSubmission, pk)
        if public_submission_access(submission, current_user, PUBLIC_SUBMISSION_ACTION_VIEW) != AUTH_OK:
            return json_not_found("Submission not found")
        return None

    if AuthorizationService.is_admin(current_user):
        return None
    return json_forbidden("You cannot preview a translation for this form.")
