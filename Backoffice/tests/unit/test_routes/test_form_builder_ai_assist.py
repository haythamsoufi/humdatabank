"""Tests for app/routes/admin/form_builder/ai_assist.py — form-builder AI assistant routes.

Routes covered:
- POST /admin/templates/ai-extract-document           (ai_extract_document)
- POST /admin/templates/ai-extract-image               (ai_extract_image)
- POST /admin/templates/<id>/ai-restore-structure      (ai_restore_structure)

Plus the pure helper ``_guess_sections_from_text``.

These were previously untested at the route layer: request parsing (file
presence/type validation, JSON body shape), the AI-beta gate, RBAC decorator
wiring, and service/processor-exception-to-HTTP-status mapping all had zero
coverage. Service-level business logic (``FormTemplateAIService``) has its
own dedicated suite in ``test_form_template_ai_service.py`` and is not
re-verified here except via a couple of true end-to-end smoke tests for
``ai_restore_structure``, which had no coverage at any layer.
"""
import io

import pytest
from unittest.mock import MagicMock, patch

from app.models import FormItem, FormSection
from app.routes.admin.form_builder.ai_assist import (
    MAX_EXTRACT_CHARS,
    MAX_IMAGE_BYTES,
    _guess_sections_from_text,
)
from tests.factories import create_test_item, create_test_section, create_test_template

pytestmark = [pytest.mark.unit]

JSON_HEADERS = {"Accept": "application/json"}

PROCESSOR = "app.services.ai.documents.processor.AIDocumentProcessor.process_document"
VISION = "app.routes.admin.form_builder.ai_assist._extract_form_image_with_vision"
RESTORE = "app.services.forms.template_ai_service.FormTemplateAIService.restore_draft_structure"
BETA_RESTRICTED = "app.services.platform.app_settings_service.is_ai_beta_restricted"
BETA_ACCESS = "app.services.platform.app_settings_service.user_has_ai_beta_access"

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_owned_draft(db_session, admin_user, **kwargs):
    """Draft-status template owned by admin_user (RBAC + template-access both pass)."""
    kwargs.setdefault("status", "draft")
    return create_test_template(db_session, owner_id=admin_user.id, **kwargs)


def _restore_url(template_id):
    return f"/admin/templates/{template_id}/ai-restore-structure"


# ---------------------------------------------------------------------------
# _guess_sections_from_text (pure helper)
# ---------------------------------------------------------------------------

class TestGuessSectionsFromText:
    def test_detects_structured_section_lines(self):
        text = "SECTION: Household Info\nFIELD: Name\nSECTION: Health\nFIELD: Age"
        sections = _guess_sections_from_text(text)
        assert [s["title"] for s in sections] == ["Household Info", "Health"]

    def test_detects_markdown_heading_with_content(self):
        """Regression: '#{1,3}\\s+' alone (no trailing content) could never match
        a real heading like '### Method', making the legacy markdown branch dead
        code despite the later lstrip("# ") cleanup implying it should work."""
        text = "### Method\nsome lowercase body text\n## Results"
        sections = _guess_sections_from_text(text)
        assert [s["title"] for s in sections] == ["Method", "Results"]

    def test_detects_allcaps_and_titlecase_headings(self):
        text = "HOUSEHOLD INFORMATION\nWhat is your name?\nHealth Status:\nHow do you feel?"
        sections = _guess_sections_from_text(text)
        titles = [s["title"] for s in sections]
        assert "HOUSEHOLD INFORMATION" in titles
        assert "Health Status:" in titles
        # Plain lowercase question lines are not headings.
        assert "What is your name?" not in titles

    def test_ignores_numbered_list_items_and_blank_overlong_lines(self):
        text = "\n".join(["", "1. First question", "2) Second question", "A" * 400])
        sections = _guess_sections_from_text(text)
        assert sections == []

    def test_caps_at_100_sections(self):
        text = "\n".join(f"SECTION: S{i}" for i in range(150))
        sections = _guess_sections_from_text(text)
        assert len(sections) == 100


# ---------------------------------------------------------------------------
# ai_extract_document
# ---------------------------------------------------------------------------

class TestAiExtractDocument:
    URL = "/admin/templates/ai-extract-document"

    def test_requires_login(self, client, db_session, app):
        resp = client.post(
            self.URL,
            data={"file": (io.BytesIO(b"hello"), "doc.txt")},
            content_type="multipart/form-data",
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 401
        assert "error" in resp.get_json()

    def test_denies_without_create_or_edit_permission(self, logged_in_focal_client, db_session, app):
        resp = logged_in_focal_client.post(
            self.URL,
            data={"file": (io.BytesIO(b"hello"), "doc.txt")},
            content_type="multipart/form-data",
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 403
        assert "error" in resp.get_json()

    def test_ai_beta_restricted_denies_access(self, logged_in_client, db_session, admin_user, app):
        with patch(BETA_RESTRICTED, return_value=True), patch(BETA_ACCESS, return_value=False):
            resp = logged_in_client.post(
                self.URL,
                data={"file": (io.BytesIO(b"hello"), "doc.txt")},
                content_type="multipart/form-data",
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 403
        assert "error" in resp.get_json()

    def test_no_file_returns_400(self, logged_in_client, db_session, admin_user, app):
        resp = logged_in_client.post(
            self.URL,
            data={},
            content_type="multipart/form-data",
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "No file provided."

    def test_unsupported_extension_returns_400(self, logged_in_client, db_session, admin_user, app):
        resp = logged_in_client.post(
            self.URL,
            data={"file": (io.BytesIO(b"MZ fake binary"), "evil.exe")},
            content_type="multipart/form-data",
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.get_json()["error"]

    def test_successful_extraction_returns_text_and_sections(
        self, logged_in_client, db_session, admin_user, app
    ):
        fake_result = {
            "text": "Q1: What is your name?",
            "sections": [{"title": "Intro", "page_number": 1}],
        }
        with patch(PROCESSOR, return_value=fake_result):
            resp = logged_in_client.post(
                self.URL,
                data={"file": (io.BytesIO(b"plain text content"), "doc.txt")},
                content_type="multipart/form-data",
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["filename"] == "doc.txt"
        assert data["text"] == "Q1: What is your name?"
        assert data["sections"] == [{"title": "Intro", "page_number": 1}]
        assert data["truncated"] is False

    def test_truncates_long_text(self, logged_in_client, db_session, admin_user, app):
        long_text = "A" * (MAX_EXTRACT_CHARS + 500)
        with patch(PROCESSOR, return_value={"text": long_text, "sections": []}):
            resp = logged_in_client.post(
                self.URL,
                data={"file": (io.BytesIO(b"plain text content"), "doc.txt")},
                content_type="multipart/form-data",
                headers=JSON_HEADERS,
            )
        data = resp.get_json()
        assert data["truncated"] is True
        assert len(data["text"]) == MAX_EXTRACT_CHARS

    def test_document_processing_error_returns_400(self, logged_in_client, db_session, admin_user, app):
        from app.services.ai.documents.processor import DocumentProcessingError

        with patch(PROCESSOR, side_effect=DocumentProcessingError("Corrupt PDF")):
            resp = logged_in_client.post(
                self.URL,
                data={"file": (io.BytesIO(b"plain text content"), "doc.txt")},
                content_type="multipart/form-data",
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Corrupt PDF"

    def test_unexpected_error_returns_500_and_cleans_up_temp_file(
        self, logged_in_client, db_session, admin_user, app
    ):
        with patch(PROCESSOR, side_effect=RuntimeError("boom")), patch(
            "app.routes.admin.form_builder.ai_assist.os.unlink"
        ) as mock_unlink:
            resp = logged_in_client.post(
                self.URL,
                data={"file": (io.BytesIO(b"plain text content"), "doc.txt")},
                content_type="multipart/form-data",
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 500
        assert resp.get_json()["error"] == "Failed to extract text from the document."
        # The temp file created for processing must be cleaned up even on failure.
        mock_unlink.assert_called_once()


# ---------------------------------------------------------------------------
# ai_extract_image
# ---------------------------------------------------------------------------

class TestAiExtractImage:
    URL = "/admin/templates/ai-extract-image"

    def test_requires_login(self, client, db_session, app):
        resp = client.post(
            self.URL,
            data={"file": (io.BytesIO(PNG_BYTES), "shot.png")},
            content_type="multipart/form-data",
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 401

    def test_denies_without_permission(self, logged_in_focal_client, db_session, app):
        resp = logged_in_focal_client.post(
            self.URL,
            data={"file": (io.BytesIO(PNG_BYTES), "shot.png")},
            content_type="multipart/form-data",
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 403

    def test_ai_beta_restricted_denies_access(self, logged_in_client, db_session, admin_user, app):
        with patch(BETA_RESTRICTED, return_value=True), patch(BETA_ACCESS, return_value=False):
            resp = logged_in_client.post(
                self.URL,
                data={"file": (io.BytesIO(PNG_BYTES), "shot.png")},
                content_type="multipart/form-data",
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 403

    def test_no_file_returns_400(self, logged_in_client, db_session, admin_user, app):
        resp = logged_in_client.post(
            self.URL,
            data={},
            content_type="multipart/form-data",
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "No image provided."

    def test_unsupported_extension_returns_400(self, logged_in_client, db_session, admin_user, app):
        resp = logged_in_client.post(
            self.URL,
            data={"file": (io.BytesIO(b"not an image"), "notes.txt")},
            content_type="multipart/form-data",
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.get_json()["error"]

    def test_empty_file_returns_400(self, logged_in_client, db_session, admin_user, app):
        resp = logged_in_client.post(
            self.URL,
            data={"file": (io.BytesIO(b""), "shot.png")},
            content_type="multipart/form-data",
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 400

    def test_file_too_large_returns_400(self, logged_in_client, db_session, admin_user, app):
        big = PNG_BYTES + b"\x00" * (MAX_IMAGE_BYTES + 10)
        resp = logged_in_client.post(
            self.URL,
            data={"file": (io.BytesIO(big), "shot.png")},
            content_type="multipart/form-data",
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 400
        assert "too large" in resp.get_json()["error"].lower()

    def test_successful_extraction_returns_sections(self, logged_in_client, db_session, admin_user, app):
        vision_text = (
            "FORM TITLE: Test\nSECTION: Household\nFIELD: Name\nTYPE: text\nREQUIRED: yes\n"
        )
        with patch(VISION, return_value=vision_text) as mock_vision:
            resp = logged_in_client.post(
                self.URL,
                data={"file": (io.BytesIO(PNG_BYTES), "shot.png")},
                content_type="multipart/form-data",
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["kind"] == "image"
        assert data["sections"] == [{"title": "Household"}]
        mock_vision.assert_called_once()

    def test_non_image_content_type_defaults_mime_to_png(
        self, logged_in_client, db_session, admin_user, app
    ):
        with patch(VISION, return_value="text") as mock_vision:
            resp = logged_in_client.post(
                self.URL,
                data={"file": (io.BytesIO(PNG_BYTES), "shot.png", "application/octet-stream")},
                content_type="multipart/form-data",
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        args = mock_vision.call_args.args
        assert args[1] == "image/png"

    def test_vision_failure_returns_500(self, logged_in_client, db_session, admin_user, app):
        with patch(VISION, side_effect=RuntimeError("Vision model unavailable")):
            resp = logged_in_client.post(
                self.URL,
                data={"file": (io.BytesIO(PNG_BYTES), "shot.png")},
                content_type="multipart/form-data",
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 500
        assert resp.get_json()["error"] == "Failed to read the pasted image."


# ---------------------------------------------------------------------------
# ai_restore_structure
# ---------------------------------------------------------------------------

class TestAiRestoreStructure:
    def test_requires_login(self, client, db_session, app):
        resp = client.post(
            _restore_url(1), json={"structure": {"sections": []}}, headers=JSON_HEADERS
        )
        assert resp.status_code == 401

    def test_denies_without_edit_permission(self, logged_in_focal_client, db_session, app):
        template = create_test_template(db_session, status="draft")
        resp = logged_in_focal_client.post(
            _restore_url(template.id),
            json={"structure": {"sections": []}},
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 403

    def test_ai_beta_restricted_denies_access(self, logged_in_client, db_session, admin_user, app):
        template = _make_owned_draft(db_session, admin_user)
        with patch(BETA_RESTRICTED, return_value=True), patch(BETA_ACCESS, return_value=False):
            resp = logged_in_client.post(
                _restore_url(template.id),
                json={"structure": {"sections": []}},
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 403

    def test_missing_structure_returns_400(self, logged_in_client, db_session, admin_user, app):
        template = _make_owned_draft(db_session, admin_user)
        resp = logged_in_client.post(
            _restore_url(template.id), json={}, headers=JSON_HEADERS
        )
        assert resp.status_code == 400
        assert "structure" in resp.get_json()["error"]

    def test_structure_must_be_object_returns_400(self, logged_in_client, db_session, admin_user, app):
        template = _make_owned_draft(db_session, admin_user)
        resp = logged_in_client.post(
            _restore_url(template.id), json={"structure": "not-an-object"}, headers=JSON_HEADERS
        )
        assert resp.status_code == 400

    def test_template_not_found_returns_400(self, logged_in_client, db_session, admin_user, app):
        resp = logged_in_client.post(
            _restore_url(999_999_999),
            json={"structure": {"sections": []}},
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert "not found" in body["error"].lower()

    def test_structure_without_sections_list_returns_400(
        self, logged_in_client, db_session, admin_user, app
    ):
        """Route only checks `structure` is a dict; the 'sections must be a list'
        invariant is enforced by the service and mapped back to a 400 here."""
        template = _make_owned_draft(db_session, admin_user)
        resp = logged_in_client.post(
            _restore_url(template.id),
            json={"structure": {"name": "No sections key"}},
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert "sections" in body["error"].lower()

    def test_service_error_maps_to_400_with_success_false(
        self, logged_in_client, db_session, admin_user, app
    ):
        from app.services.forms.template_ai_service import FormTemplateAIError

        template = _make_owned_draft(db_session, admin_user)
        with patch(
            RESTORE,
            side_effect=FormTemplateAIError(
                "Cannot restore this snapshot because some fields already have submitted data."
            ),
        ):
            resp = logged_in_client.post(
                _restore_url(template.id),
                json={"structure": {"sections": []}},
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert "submitted data" in body["error"]

    def test_unexpected_error_returns_500(self, logged_in_client, db_session, admin_user, app):
        template = _make_owned_draft(db_session, admin_user)
        with patch(RESTORE, side_effect=RuntimeError("boom")):
            resp = logged_in_client.post(
                _restore_url(template.id),
                json={"structure": {"sections": []}},
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 500
        assert resp.get_json()["error"] == "Failed to restore the draft structure."

    def test_successful_restore_replaces_existing_structure(
        self, logged_in_client, db_session, admin_user, app
    ):
        """End-to-end smoke test: ai_restore_structure had zero coverage at any
        layer. Confirms the route wires a real structure snapshot through to
        FormTemplateAIService.restore_draft_structure and that the previous
        draft section/item are replaced by the restored ones."""
        template = _make_owned_draft(db_session, admin_user)
        old_section = create_test_section(db_session, template, name="Old Section")
        create_test_item(
            db_session, old_section, template, item_type="question", type="text", label="Old Question"
        )
        old_section_id = old_section.id

        payload = {
            "structure": {
                "name": "Restored Name",
                "sections": [
                    {
                        "name": "New Section",
                        "order": 1,
                        "items": [
                            {
                                "item_type": "question",
                                "question_type": "text",
                                "label": "New Question",
                                "order": 1,
                            }
                        ],
                    }
                ],
            }
        }
        resp = logged_in_client.post(
            _restore_url(template.id), json=payload, headers=JSON_HEADERS
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["template_id"] == template.id
        assert body["sections_restored"] == 1
        assert body["items_restored"] == 1
        assert str(template.id) in body["edit_url"]

        # The service's bulk delete/insert runs on the app's own db.session and
        # commits there; refresh the test session's identity map so queries
        # below see the post-request DB state rather than stale cached objects.
        db_session.expire_all()

        version_id = body["version_id"]
        sections = FormSection.query.filter_by(version_id=version_id, archived=False).all()
        assert [s.name for s in sections] == ["New Section"]
        items = FormItem.query.filter_by(version_id=version_id, archived=False).all()
        assert [i.label for i in items] == ["New Question"]
        # The pre-existing section/item must be gone, not just superseded.
        assert FormSection.query.get(old_section_id) is None
