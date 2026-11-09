"""Field edits and edit permission for the focal document repository."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.documents.entity_document_edit import (
    DocumentEditError,
    apply_entity_document_fields,
    document_language_options,
    focal_repository_can_edit,
    replace_submitted_document_file,
)

pytestmark = [pytest.mark.unit]

_AUTH = "app.services.organization.authorization_service.AuthorizationService"
_ACCESS = "app.routes.admin.content_management._focal_user_can_access_submitted_document"


def _doc(**kwargs):
    defaults = {
        "id": 7,
        "filename": "report.pdf",
        "document_type": "Annual Report",
        "language": "en",
        "period": "2024",
        "is_public": False,
        "status": "pending",
        "uploaded_by_user_id": 3,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestApplyEntityDocumentFields:
    def test_updates_type_language_period_and_privacy(self):
        doc = _doc()
        apply_entity_document_fields(
            doc,
            {
                "document_type": "Audit",
                "language": "fr",
                "period": "2023-2024",
                "is_public": True,
                "filename": "audit.pdf",
            },
        )
        assert doc.document_type == "Audit"
        assert doc.language == "fr"
        assert doc.period == "2023-2024"
        assert doc.is_public is True
        assert doc.filename == "audit.pdf"

    def test_cover_image_clears_language_and_period_and_stays_public(self):
        doc = _doc()
        apply_entity_document_fields(
            doc,
            {
                "document_type": "Cover Image",
                "language": "fr",
                "period": "2024",
                "is_public": False,
            },
        )
        assert doc.document_type == "Cover Image"
        assert doc.language is None
        assert doc.period is None
        assert doc.is_public is True
        assert doc.status == "pending"

    def test_ignores_status_unless_the_caller_may_change_it(self):
        doc = _doc(status="pending")
        apply_entity_document_fields(doc, {"status": "approved"})
        assert doc.status == "pending"

    def test_document_admin_can_set_approval_status(self):
        doc = _doc(status="pending")
        previous = apply_entity_document_fields(
            doc,
            {"status": "approved", "document_type": "Cover Image"},
            allow_status=True,
        )
        assert previous == "pending"
        assert doc.status == "approved"
        assert doc.document_type == "Cover Image"
        assert doc.is_public is True

    def test_rejects_an_overlong_language_code(self):
        doc = _doc()
        with pytest.raises(DocumentEditError):
            apply_entity_document_fields(doc, {"language": "this-code-is-too-long"})


class TestFocalRepositoryCanEdit:
    def _as_focal(self):
        return (
            patch(f"{_AUTH}.is_system_manager", return_value=False),
            patch(f"{_AUTH}.has_rbac_permission", return_value=False),
        )

    def test_approved_document_is_locked_for_focal_uploader(self):
        user = SimpleNamespace(id=3, is_authenticated=True)
        sys_patch, perm_patch = self._as_focal()
        with sys_patch, perm_patch, \
             patch(f"{_AUTH}.can_access_entity_document_repository", return_value=True), \
             patch(_ACCESS, return_value=True):
            assert focal_repository_can_edit(user, _doc(status="approved")) is False

    def test_pending_document_in_scope_can_be_edited(self):
        user = SimpleNamespace(id=3, is_authenticated=True)
        sys_patch, perm_patch = self._as_focal()
        with sys_patch, perm_patch, \
             patch(f"{_AUTH}.can_access_entity_document_repository", return_value=True), \
             patch(_ACCESS, return_value=True):
            assert focal_repository_can_edit(user, _doc(status="pending")) is True

    def test_user_without_repository_access_cannot_edit(self):
        user = SimpleNamespace(id=3, is_authenticated=True)
        sys_patch, perm_patch = self._as_focal()
        with sys_patch, perm_patch, \
             patch(f"{_AUTH}.can_access_entity_document_repository", return_value=False):
            assert focal_repository_can_edit(user, _doc()) is False

    def test_document_admin_can_edit_an_approved_document(self):
        user = SimpleNamespace(id=3, is_authenticated=True)

        def _permission(_user, code):
            return code == "admin.documents.manage"

        with patch(f"{_AUTH}.is_system_manager", return_value=False), \
             patch(f"{_AUTH}.has_rbac_permission", side_effect=_permission), \
             patch(_ACCESS, return_value=True):
            assert focal_repository_can_edit(user, _doc(status="approved")) is True


class TestReplaceSubmittedDocumentFile:
    def test_rejects_a_disallowed_extension(self):
        upload = SimpleNamespace(filename="payload.exe")
        replaced, warnings = replace_submitted_document_file(_doc(), upload)
        assert replaced is False
        assert warnings
        assert "not allowed" in warnings[0]


class TestDocumentLanguageOptions:
    def test_includes_languages_outside_the_ui_set(self):
        options = document_language_options()
        codes = [item["code"] for item in options]
        assert "en" in codes
        assert "de" in codes
        assert "sw" in codes
        assert len(codes) > 20
        assert len(codes) == len(set(codes))
        assert all(len(code) <= 10 for code in codes)
        german = next(item for item in options if item["code"] == "de")
        assert german["english_name"] == "German"
