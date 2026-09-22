"""Unit tests for guidance_document_service (no database)."""

from __future__ import annotations

from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from app.services.documents.guidance_document_service import (
    GuidanceDocumentError,
    normalize_owner_key,
    save_guidance_document,
)


pytestmark = [pytest.mark.unit]


class TestNormalizeOwnerKey:
    def test_valid_key(self):
        assert normalize_owner_key("UPR") == "upr"
        assert normalize_owner_key("system") == "system"

    def test_rejects_empty(self):
        with pytest.raises(GuidanceDocumentError):
            normalize_owner_key("")

    def test_rejects_path_chars(self):
        with pytest.raises(GuidanceDocumentError):
            normalize_owner_key("../etc")


class TestSaveGuidanceDocumentValidation:
    def test_rejects_missing_file(self):
        upload = FileStorage(stream=BytesIO(b""), filename="")
        with pytest.raises(GuidanceDocumentError):
            save_guidance_document(upload, owner_key="upr", uploaded_by_user_id=1)

    def test_rejects_unsupported_extension(self):
        upload = FileStorage(stream=BytesIO(b"exe"), filename="malware.exe")
        with pytest.raises(GuidanceDocumentError):
            save_guidance_document(upload, owner_key="upr", uploaded_by_user_id=1)
