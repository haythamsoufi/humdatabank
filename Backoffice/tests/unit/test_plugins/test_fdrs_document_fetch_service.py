"""Unit tests for plugins.fdrs.services.fdrs_document_fetch_service."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

from plugins.fdrs.services import fdrs_document_fetch_service as svc

pytestmark = pytest.mark.unit

# fdrs_document_fetch_service imports `fdrs_documents_sync` (a standalone script,
# not a package module) via sys.path manipulation at call time. Insert it here too
# so tests can patch `fdrs_documents_sync.fetch_fdrs_document_bytes` directly
# (mirrors plugins/fdrs/tests/test_fdrs_sync_helpers.py).
_SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "plugins", "fdrs", "scripts")
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def test_fdrs_imports_dir_points_at_plugin_scripts():
    imports_dir = os.path.abspath(svc._fdrs_imports_dir())
    assert imports_dir.endswith(os.path.join("plugins", "fdrs", "scripts"))
    assert os.path.isfile(os.path.join(imports_dir, "fdrs_documents_sync.py"))


class TestDownloadFdrsDocumentToTemp:
    def test_raises_when_fetch_fails(self):
        with patch("fdrs_documents_sync.fetch_fdrs_document_bytes", return_value=(None, 403)):
            with pytest.raises(FileNotFoundError):
                svc.download_fdrs_document_to_temp("https://example.test/report.pdf", "report.pdf")

    def test_writes_bytes_to_temp_file_and_defaults_extension(self):
        data = b"%PDF-1.4 test"
        with patch("fdrs_documents_sync.fetch_fdrs_document_bytes", return_value=(data, 200)):
            temp_path, filename, file_size, content_hash, file_type = svc.download_fdrs_document_to_temp(
                "https://example.test/report", "report"
            )

        try:
            assert filename == "report.pdf"
            assert file_size == len(data)
            assert file_type == "pdf"
            assert content_hash
            with open(temp_path, "rb") as handle:
                assert handle.read() == data
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
