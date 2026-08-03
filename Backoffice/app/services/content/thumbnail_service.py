"""PDF thumbnail generation and deletion for resources and submitted documents."""

from __future__ import annotations

import io
import os
from contextlib import suppress
from typing import Optional

from flask import current_app

from app.services.platform import storage_service as storage


class ThumbnailService:
    """Generate and delete PDF thumbnails stored via the platform storage service."""

    @staticmethod
    def check_pdf_processing_capability() -> bool:
        """Return True when PyMuPDF (fitz) and Pillow are importable."""
        try:
            import fitz  # noqa: F401
            from PIL import Image  # noqa: F401
            return True
        except ImportError:
            current_app.logger.warning("PDF processing libraries not available")
            return False

    @staticmethod
    def generate_pdf_thumbnail_to_storage(
        pdf_full_path: str,
        unique_folder_name: str,
        language_code: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[str]:
        """Generate a PDF thumbnail and save it via the storage service.

        Returns the relative path stored by the storage service, or ``None`` on failure.
        """
        try:
            if not ThumbnailService.check_pdf_processing_capability():
                return None

            import fitz
            from PIL import Image

            with fitz.open(pdf_full_path) as pdf_document:
                page = pdf_document[0]
                mat = fitz.Matrix(1.5, 1.5)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")

                img = Image.open(io.BytesIO(img_data))
                img.thumbnail((300, 400), Image.Resampling.LANCZOS)

                thumbnail_filename = (
                    f"thumbnail_{language_code}.png" if language_code else "thumbnail.png"
                )
                rel_path = f"{unique_folder_name}/thumbnails/{thumbnail_filename}"

                buf = io.BytesIO()
                img.save(buf, "PNG")
                png_bytes = buf.getvalue()

            cat = category or storage.ADMIN_DOCUMENTS
            return storage.upload(cat, rel_path, png_bytes)

        except Exception as e:
            current_app.logger.error("Error generating PDF thumbnail: %s", e, exc_info=True)
            return None

    @staticmethod
    def delete_stored_thumbnail(storage_category: str, relative_path: str) -> bool:
        """Delete a thumbnail blob from storage. Returns True when storage.delete succeeds."""
        return storage.delete(storage_category, relative_path)

    @staticmethod
    def clear_model_thumbnail_fields(model) -> None:
        """Clear thumbnail path/filename fields on a resource translation or document model."""
        model.thumbnail_relative_path = None
        model.thumbnail_filename = None

    @staticmethod
    def apply_generated_thumbnail(model, thumbnail_path: str) -> None:
        """Persist generated thumbnail metadata on a model with thumbnail fields."""
        model.thumbnail_relative_path = thumbnail_path
        model.thumbnail_filename = os.path.basename(thumbnail_path)

    @staticmethod
    def generate_for_local_pdf(
        pdf_full_path: str,
        folder_prefix: str,
        *,
        language_code: Optional[str] = None,
        category: str,
        cleanup_temp: bool = False,
    ) -> Optional[str]:
        """Generate a thumbnail from a local PDF path, optionally removing a temp download."""
        try:
            return ThumbnailService.generate_pdf_thumbnail_to_storage(
                pdf_full_path,
                folder_prefix,
                language_code=language_code,
                category=category,
            )
        finally:
            if cleanup_temp:
                with suppress(OSError):
                    os.remove(pdf_full_path)
