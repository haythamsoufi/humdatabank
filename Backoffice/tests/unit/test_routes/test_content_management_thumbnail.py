"""Unit tests for PDF thumbnail generation via ThumbnailService."""
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


class TestGeneratePdfThumbnailToStorage:
    def test_uses_context_manager_for_pdf_document(self, app):
        from app.services.content.thumbnail_service import ThumbnailService

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"fake-png"
        mock_page.get_pixmap.return_value = mock_pix

        mock_pdf = MagicMock()
        mock_pdf.__getitem__.return_value = mock_page

        mock_fitz = MagicMock()
        mock_fitz.open.return_value.__enter__.return_value = mock_pdf
        mock_fitz.open.return_value.__exit__.return_value = None
        mock_fitz.Matrix.return_value = MagicMock()

        mock_image = MagicMock()
        mock_pil = MagicMock()
        mock_pil.open.return_value = mock_image
        mock_pil.Resampling.LANCZOS = 1

        with app.app_context(), \
             patch(
                 "app.services.content.thumbnail_service.ThumbnailService.check_pdf_processing_capability",
                 return_value=True,
             ), \
             patch.dict("sys.modules", {"fitz": mock_fitz}), \
             patch("PIL.Image", mock_pil), \
             patch("app.services.platform.storage_service.upload", return_value="thumb/path.png"):
            result = ThumbnailService.generate_pdf_thumbnail_to_storage(
                "/tmp/test.pdf", "folder123", language_code="en",
            )

        assert result == "thumb/path.png"
        mock_fitz.open.assert_called_once_with("/tmp/test.pdf")
        mock_fitz.open.return_value.__enter__.assert_called_once()
        mock_fitz.open.return_value.__exit__.assert_called_once()
