"""Unit tests for guidance-document AI import prep."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.ai.documents.ingest import _prepare_guidance_document_ai_import


pytestmark = [pytest.mark.unit]


def test_prepare_guidance_missing_row_returns_error():
    with patch("app.models.GuidanceDocument") as Model:
        Model.query.get.return_value = None
        result = _prepare_guidance_document_ai_import(99)
    assert result["ok"] is False
    assert result["code"] == "guidance_document_not_found"


def test_prepare_guidance_missing_file_returns_error():
    guidance = SimpleNamespace(id=3, storage_path="guidance/upr/abc/guide.pdf", filename="guide.pdf")
    with (
        patch("app.models.GuidanceDocument") as Model,
        patch("app.services.platform.storage_service.exists", return_value=False),
    ):
        Model.query.get.return_value = guidance
        result = _prepare_guidance_document_ai_import(3)
    assert result["ok"] is False
    assert result["code"] == "file_not_found"


def test_prepare_guidance_reuses_existing_ai_document():
    guidance = SimpleNamespace(
        id=4,
        storage_path="guidance/upr/abc/guide.pdf",
        filename="guide.pdf",
        title="UPR Guide",
        owner_key="upr",
        uploaded_by_user_id=7,
        file_size_bytes=12,
    )
    existing = SimpleNamespace(
        id=55,
        processing_status="completed",
        processing_error="old",
        title="old",
        filename="old.pdf",
        is_public=True,
    )
    processor = MagicMock()
    processor.is_supported_file.return_value = True

    with (
        patch("app.models.GuidanceDocument") as GModel,
        patch("app.models.AIDocument") as AModel,
        patch("app.services.platform.storage_service.exists", return_value=True),
        patch("app.services.platform.storage_service.get_absolute_path", return_value="/tmp/guide.pdf"),
        patch("app.services.platform.storage_service.is_azure", return_value=False),
        patch("app.services.ai.documents.processor.AIDocumentProcessor", return_value=processor),
        patch("app.extensions.db.session.commit"),
    ):
        GModel.query.get.return_value = guidance
        AModel.query.filter_by.return_value.first.return_value = existing
        result = _prepare_guidance_document_ai_import(4, user_id=9)

    assert result["ok"] is True
    assert result["ai_document_id"] == 55
    assert existing.processing_status == "pending"
    assert existing.is_public is False
    assert existing.title == "UPR Guide"


def test_upr_prompt_mentions_guidance_assistant():
    from plugins.upr.ai.prompts import get_upr_prompt_section

    text = get_upr_prompt_section()
    assert "Unified Planning and Reporting Assistant" in text
    assert "UPR Guidance" in text


def test_upr_plugin_documentation_source():
    from plugins.upr.plugin import UprPlugin

    source = UprPlugin().get_documentation_source()
    assert source is not None
    assert source.category == "upr"
    assert source.include_in_help is False
    assert (source.root_dir / "upr" / "overview.md").is_file()
