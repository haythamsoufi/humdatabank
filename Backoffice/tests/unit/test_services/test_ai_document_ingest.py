"""Tests for FDRS / source_url AI document ingest resolution."""

import os
from unittest.mock import MagicMock, patch

import pytest

from app.services.ai.documents import ingest

pytestmark = pytest.mark.unit


def _submitted_doc(**kwargs):
    doc = MagicMock()
    doc.id = kwargs.get("id", 42)
    doc.storage_path = kwargs.get("storage_path")
    doc.source_url = kwargs.get("source_url")
    doc.file_pending = kwargs.get("file_pending", False)
    doc.fdrs_import_key = kwargs.get("fdrs_import_key")
    doc.filename = kwargs.get("filename", "report.pdf")
    return doc


def _ai_doc(**kwargs):
    doc = MagicMock()
    doc.id = kwargs.get("id", 183)
    doc.filename = kwargs.get("filename", "report.pdf")
    doc.storage_path = kwargs.get("storage_path")
    doc.source_url = kwargs.get("source_url")
    doc.submitted_document_id = kwargs.get("submitted_document_id")
    return doc


class TestResolveAiDocumentSourceForProcessing:
    def test_delegates_to_submitted_document_when_no_ai_source_url(self, app):
        ai_doc = _ai_doc(source_url=None, submitted_document_id=3559)
        submitted = _submitted_doc(
            source_url="https://example.test/fdrs/report.pdf",
            file_pending=False,
        )

        with app.app_context():
            with patch("app.models.SubmittedDocument") as mock_model:
                mock_model.query.get.return_value = submitted
                with patch.object(
                    ingest,
                    "_resolve_submitted_document_for_ai_processing",
                    return_value={
                        "ok": True,
                        "file_path": "/tmp/report.pdf",
                        "cleanup_temp": True,
                        "filename": "report.pdf",
                        "from_url": True,
                        "source_url": "https://example.test/fdrs/report.pdf",
                    },
                ) as mock_resolve:
                    result = ingest.resolve_ai_document_source_for_processing(ai_doc)

        mock_model.query.get.assert_called_once_with(3559)
        mock_resolve.assert_called_once_with(submitted)
        assert result["ok"] is True
        assert result["backfill_source_url"] == "https://example.test/fdrs/report.pdf"


class TestResolveSubmittedDocumentForAiProcessing:
    def test_file_pending_downloads_from_source_url(self, app, tmp_path):
        pdf_path = tmp_path / "report.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test")

        doc = _submitted_doc(
            storage_path="submissions/stale/path.pdf",
            source_url="https://example.test/fdrs/report.pdf",
            file_pending=True,
            fdrs_import_key="abc",
        )

        with app.app_context():
            with patch.object(
                ingest,
                "_download_submitted_document_from_source_url",
                return_value=(str(pdf_path), "report.pdf", 12, "hash", "pdf"),
            ) as mock_download:
                result = ingest._resolve_submitted_document_for_ai_processing(doc)

        mock_download.assert_called_once_with(doc)
        assert result["ok"] is True
        assert result["from_url"] is True
        assert result["file_path"] == str(pdf_path)
        assert result["cleanup_temp"] is True

    def test_skips_local_storage_when_file_pending(self, app, tmp_path):
        pdf_path = tmp_path / "report.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test")

        doc = _submitted_doc(
            storage_path="submissions/stale/path.pdf",
            source_url="https://example.test/fdrs/report.pdf",
            file_pending=True,
        )

        with app.app_context():
            with patch(
                "app.services.platform.storage_service.local_path_for_submitted_document_processing"
            ) as mock_local:
                with patch.object(
                    ingest,
                    "_download_submitted_document_from_source_url",
                    return_value=(str(pdf_path), "report.pdf", 12, "hash", "pdf"),
                ):
                    result = ingest._resolve_submitted_document_for_ai_processing(doc)

        mock_local.assert_not_called()
        assert result["ok"] is True
        assert result["from_url"] is True

    def test_no_storage_and_no_source_url(self, app):
        doc = _submitted_doc(storage_path=None, source_url=None)

        with app.app_context():
            result = ingest._resolve_submitted_document_for_ai_processing(doc)

        assert result["ok"] is False
        assert result["code"] == "missing_storage_path"

    def test_fdrs_imports_dir_points_at_scripts_imports(self):
        imports_dir = os.path.abspath(ingest._fdrs_imports_dir())
        assert imports_dir.endswith(os.path.join("scripts", "imports"))
        assert os.path.isfile(os.path.join(imports_dir, "fdrs_documents_sync.py"))
