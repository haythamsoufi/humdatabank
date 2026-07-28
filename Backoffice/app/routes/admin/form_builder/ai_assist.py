"""
Form-builder AI assistant support endpoints.

- ``POST /admin/templates/ai-extract-document`` — text from PDF/Word/text files
- ``POST /admin/templates/ai-extract-image`` — structure from pasted/dropped images (vision)

Extracted content is injected into the chat message so the agent can rebuild the
questionnaire as a template via ``create_form_template``.
"""

import base64
import os
import re
import tempfile

from flask import current_app, request
from flask_login import current_user

from app.routes.admin.shared import permission_required_any
from app.utils.advanced_validation import validate_upload_extension_and_mime
from app.utils.api_responses import json_bad_request, json_forbidden, json_ok, json_server_error

from . import bp


def _ai_beta_denied_response():
    """Return a JSON denial when AI beta access blocks this user."""
    try:
        from app.services.app_settings_service import is_ai_beta_restricted, user_has_ai_beta_access

        if not is_ai_beta_restricted():
            return None
        if not getattr(current_user, "is_authenticated", False):
            return json_forbidden("AI beta access is limited to selected users.")
        if not user_has_ai_beta_access(current_user):
            return json_forbidden("AI beta access is limited to selected users.")
    except Exception as exc:
        current_app.logger.debug(
            "form_builder AI beta gate check failed: %s", exc, exc_info=True
        )
    return None

# Formats the AI panel accepts for questionnaire import (Excel/Kobo files have
# dedicated import routes in the builder and are intentionally excluded here).
ALLOWED_EXTRACT_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# Keep extraction bounded: the result is injected into a chat message.
MAX_EXTRACT_CHARS = 60_000
MAX_EXTRACT_PAGES = 40
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _extract_form_image_with_vision(image_bytes: bytes, mime_type: str, filename: str) -> str:
    """Describe a pasted form screenshot using a vision-capable OpenAI model."""
    import os as _os

    api_key = current_app.config.get("OPENAI_API_KEY") or _os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    model = str(
        current_app.config.get("AI_FORM_BUILDER_VISION_MODEL")
        or current_app.config.get("OPENAI_MODEL", "gpt-4o-mini")
    ).strip()

    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64}"
    prompt = (
        "The user pasted a screenshot of a form, questionnaire, or table they want recreated "
        "as a humanitarian data-collection template.\n\n"
        "Extract EVERY question/field using this exact format for each one:\n\n"
        "FIELD: <clean label — no leading numbers, letters, or bullets; no trailing asterisks>\n"
        "TYPE: <text | textarea | number | percentage | date | datetime | yes/no | "
        "single_choice | multiple_choice | matrix>\n"
        "REQUIRED: <yes | no>\n"
        "HELP: <any explanatory text, guidance, examples, or instructions shown beneath the "
        "field — omit this line if none>\n"
        "OPTIONS: <comma-separated choices for single_choice or multiple_choice — omit if none>\n\n"
        "Before listing fields, output:\n"
        "FORM TITLE: <title>\n"
        "SECTION: <name> (only for genuine section headings that group multiple questions; "
        "skip form preamble banners, footer notes, and submit buttons — those are not sections)\n\n"
        "Rules:\n"
        "- Extract ALL visible fields without exception.\n"
        "- Strip question numbers (1., Q2., a)) and required markers (* ∗) from FIELD labels.\n"
        "- Put all helper text / guidance / examples under HELP, never in FIELD.\n"
        "- Preserve original wording in labels and help text.\n"
        "- If the image is not a form, say so briefly and describe what you see."
    )

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Return plain text only. No markdown code fences."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        max_completion_tokens=4000,
    )
    msg = resp.choices[0].message if (resp and resp.choices) else None
    text = (getattr(msg, "content", None) or "").strip()
    if not text:
        raise RuntimeError("Vision model returned an empty description.")
    return text


def _guess_sections_from_text(text: str) -> list:
    """Lightweight section heading detection for vision-extracted plain text.

    Recognises both the structured ``SECTION: <name>`` format produced by the
    vision prompt and the legacy heuristic (ALL-CAPS / markdown headings) used
    for plain document extractions.
    """
    sections = []
    for line in (text or "").splitlines():
        raw = line.strip()
        if not raw or len(raw) > 300:
            continue
        # Structured format produced by the updated vision prompt
        m = re.match(r"^SECTION:\s*(.+)$", raw, re.IGNORECASE)
        if m:
            title = m.group(1).strip()[:300]
            if title:
                sections.append({"title": title})
        # Legacy heuristic: markdown headings or ALL-CAPS title-case lines
        elif re.match(r"^(?:#{1,3}\s+|[A-Z][A-Za-z0-9 ,/&()-]{2,80}:?\s*)$", raw):
            if not re.match(r"^\d+[\.)]\s", raw):
                sections.append({"title": raw.lstrip("# ").strip()[:300]})
        if len(sections) >= 100:
            break
    return sections


@bp.route("/templates/ai-extract-document", methods=["POST"])
@permission_required_any("admin.templates.create", "admin.templates.edit")
def ai_extract_document():
    """Extract text + section structure from an uploaded questionnaire document."""
    denied = _ai_beta_denied_response()
    if denied is not None:
        return denied

    file = request.files.get("file")
    if not file or not file.filename:
        return json_bad_request("No file provided.")

    valid, error_message, _ext = validate_upload_extension_and_mime(
        file, ALLOWED_EXTRACT_EXTENSIONS
    )
    if not valid:
        return json_bad_request(error_message or "Unsupported file type.")

    from app.services.ai.documents.processor import AIDocumentProcessor, DocumentProcessingError

    tmp_path = None
    try:
        suffix = os.path.splitext(file.filename)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            file.save(tmp)
            tmp_path = tmp.name

        processor = AIDocumentProcessor()
        result = processor.process_document(
            tmp_path,
            filename=file.filename,
            extract_images=False,
            ocr_enabled=False,
            max_pages=MAX_EXTRACT_PAGES,
        )

        text = str(result.get("text") or "")
        truncated = len(text) > MAX_EXTRACT_CHARS
        if truncated:
            text = text[:MAX_EXTRACT_CHARS]

        sections = []
        for section in (result.get("sections") or [])[:100]:
            if isinstance(section, dict):
                sections.append(
                    {
                        "title": str(section.get("title") or section.get("name") or "")[:300],
                        "page_number": section.get("page_number") or section.get("page"),
                    }
                )

        current_app.logger.info(
            "AI form-builder extraction: user=%s file=%s chars=%s sections=%s truncated=%s",
            current_user.id,
            file.filename,
            len(text),
            len(sections),
            truncated,
        )
        return json_ok(
            filename=file.filename,
            text=text,
            sections=sections,
            truncated=truncated,
        )
    except DocumentProcessingError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        current_app.logger.error("ai_extract_document failed: %s", exc, exc_info=True)
        return json_server_error("Failed to extract text from the document.")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError as exc:
                current_app.logger.debug("temp file cleanup failed: %s", exc)


@bp.route("/templates/ai-extract-image", methods=["POST"])
@permission_required_any("admin.templates.create", "admin.templates.edit")
def ai_extract_image():
    """Extract form structure from a pasted or uploaded image via vision."""
    denied = _ai_beta_denied_response()
    if denied is not None:
        return denied

    file = request.files.get("file")
    if not file or not file.filename:
        return json_bad_request("No image provided.")

    valid, error_message, _ext = validate_upload_extension_and_mime(
        file, ALLOWED_IMAGE_EXTENSIONS
    )
    if not valid:
        return json_bad_request(error_message or "Unsupported image type.")

    raw = file.read()
    if not raw:
        return json_bad_request("Empty image file.")
    if len(raw) > MAX_IMAGE_BYTES:
        return json_bad_request("Image is too large (max 5 MB).")

    mime_type = (file.mimetype or "image/png").split(";")[0].strip().lower()
    if not mime_type.startswith("image/"):
        mime_type = "image/png"

    try:
        text = _extract_form_image_with_vision(raw, mime_type, file.filename)
        truncated = len(text) > MAX_EXTRACT_CHARS
        if truncated:
            text = text[:MAX_EXTRACT_CHARS]
        sections = _guess_sections_from_text(text)

        current_app.logger.info(
            "AI form-builder image extraction: user=%s file=%s chars=%s truncated=%s",
            current_user.id,
            file.filename,
            len(text),
            truncated,
        )
        return json_ok(
            kind="image",
            filename=file.filename,
            text=text,
            sections=sections,
            truncated=truncated,
        )
    except Exception as exc:
        current_app.logger.error("ai_extract_image failed: %s", exc, exc_info=True)
        return json_server_error("Failed to read the pasted image.")


@bp.route("/templates/<int:template_id>/ai-restore-structure", methods=["POST"])
@permission_required_any("admin.templates.edit")
def ai_restore_structure(template_id):
    """Restore the template draft from a structure snapshot (AI undo/redo)."""
    denied = _ai_beta_denied_response()
    if denied is not None:
        return denied

    from app.services.form_template_ai_service import FormTemplateAIError, FormTemplateAIService

    payload = request.get_json(silent=True) or {}
    structure = payload.get("structure")
    if not isinstance(structure, dict):
        return json_bad_request("Request body must include a 'structure' object.")

    try:
        result = FormTemplateAIService().restore_draft_structure(
            int(template_id), structure, current_user
        )
        return json_ok(**result)
    except FormTemplateAIError as exc:
        return json_bad_request(str(exc), success=False)
    except Exception as exc:
        current_app.logger.error("ai_restore_structure failed: %s", exc, exc_info=True)
        return json_server_error("Failed to restore the draft structure.")
