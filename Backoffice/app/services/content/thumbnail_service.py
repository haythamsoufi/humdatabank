"""Thumbnails for resources and submitted documents.

PDFs use the first page. Word, PowerPoint, and Excel use the largest embedded
picture, then a text cover. YouTube resources use the public preview image.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from contextlib import suppress
from typing import Optional
from urllib.parse import parse_qs, urlparse

from flask import current_app

from app.services.platform import storage_service as storage
from app.utils.safe_image import clamp_render_scale, open_image_safe, render_page_size

_OFFICE_MEDIA = ("word/media/", "ppt/media/", "xl/media/")
_YOUTUBE_IMAGE_HOSTS = ("img.youtube.com",)
_MIN_EMBEDDED_EDGE = 120


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
                scale = clamp_render_scale(*render_page_size(page), 1.5)
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
                img_data = pix.tobytes("png")

                img = open_image_safe(img_data)
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

    @staticmethod
    def ensure_for_translation(
        translation,
        folder: str,
        *,
        category: Optional[str] = None,
        file_bytes: Optional[bytes] = None,
        remote_thumbnail_url: str = "",
        force: bool = False,
    ) -> Optional[str]:
        """Store a thumbnail for one language when one is missing.

        A remote cover image is tried first. Otherwise the file itself is
        rendered, or the YouTube preview is downloaded. ``force`` replaces a
        thumbnail that is already stored.
        """
        if translation is None or not folder:
            return None
        existing = (getattr(translation, "thumbnail_relative_path", None) or "").strip()
        if existing and not force:
            return existing

        cat = category or storage.RESOURCES
        language = (getattr(translation, "language_code", None) or "").strip() or None
        title = (getattr(translation, "title", None) or "").strip()
        filename = (getattr(translation, "filename", None) or "").strip()
        if not filename:
            path = (getattr(translation, "file_relative_path", None) or "").replace("\\", "/")
            filename = path.rsplit("/", 1)[-1]

        remote = (remote_thumbnail_url or "").strip()
        if remote:
            stored = ThumbnailService._store_remote_image(
                remote, folder, language, cat, allowed_hosts=ThumbnailService._cover_hosts(),
            )
            if stored:
                ThumbnailService.apply_generated_thumbnail(translation, stored)
                return stored

        data = file_bytes
        rel = (getattr(translation, "file_relative_path", None) or "").strip()
        if data is None and rel:
            with suppress(Exception):
                data = storage.download(cat, rel)
        if data:
            stored = ThumbnailService.generate_from_document_bytes(
                data, filename, folder, language_code=language, category=cat, title=title,
            )
            if stored:
                ThumbnailService.apply_generated_thumbnail(translation, stored)
                return stored

        link = (getattr(translation, "external_url", None) or "").strip()
        if link:
            stored = ThumbnailService.generate_from_youtube_url(
                link, folder, language_code=language, category=cat,
            )
            if stored:
                ThumbnailService.apply_generated_thumbnail(translation, stored)
                return stored
        return None

    @staticmethod
    def generate_from_document_bytes(
        data: bytes,
        filename: str,
        folder: str,
        *,
        language_code: Optional[str] = None,
        category: Optional[str] = None,
        title: str = "",
    ) -> Optional[str]:
        """Build a PNG thumbnail from a PDF, Office file, or image."""
        if not data or not folder:
            return None
        cat = category or storage.RESOURCES
        ext = os.path.splitext(filename or "")[1].lower()
        try:
            if ext == ".pdf":
                return ThumbnailService._pdf_bytes_to_storage(data, folder, language_code, cat)
            embedded = ThumbnailService._largest_embedded_image(data) if ext in {".docx", ".pptx", ".xlsx"} else None
            if embedded is None and ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                embedded = data
            if embedded is not None:
                return ThumbnailService._store_image_bytes(embedded, folder, language_code, cat)
            lines = ThumbnailService._cover_lines(data, ext, title or filename or "Document")
            return ThumbnailService._store_image_bytes(
                ThumbnailService._cover_card(lines), folder, language_code, cat,
            )
        except Exception as exc:
            current_app.logger.error("Error generating document thumbnail: %s", exc, exc_info=True)
            return None

    @staticmethod
    def generate_from_youtube_url(
        url: str,
        folder: str,
        *,
        language_code: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[str]:
        """Download the public YouTube preview image and store it."""
        video_id = ThumbnailService.youtube_video_id(url)
        if not video_id or not folder:
            return None
        image_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
        return ThumbnailService._store_remote_image(
            image_url, folder, language_code, category or storage.RESOURCES,
            allowed_hosts=_YOUTUBE_IMAGE_HOSTS,
        )

    @staticmethod
    def youtube_video_id(url: str) -> Optional[str]:
        """Return the 11-character YouTube id, or None."""
        parts = urlparse((url or "").strip())
        host = (parts.hostname or "").lower()
        video_id = ""
        if host == "youtu.be" or host.endswith(".youtu.be"):
            video_id = parts.path.strip("/").split("/")[0]
        elif host == "youtube.com" or host.endswith(".youtube.com") or host.endswith(".youtube-nocookie.com"):
            video_id = parse_qs(parts.query).get("v", [""])[0]
            if not video_id and parts.path.startswith("/embed/"):
                bits = [bit for bit in parts.path.split("/") if bit]
                video_id = bits[1] if len(bits) > 1 else ""
            if not video_id and parts.path.startswith("/shorts/"):
                bits = [bit for bit in parts.path.split("/") if bit]
                video_id = bits[1] if len(bits) > 1 else ""
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id or ""):
            return video_id
        return None

    @staticmethod
    def _pdf_bytes_to_storage(data: bytes, folder: str, language_code: Optional[str], category: str) -> Optional[str]:
        if not ThumbnailService.check_pdf_processing_capability():
            return None
        import fitz
        from PIL import Image

        with fitz.open(stream=data, filetype="pdf") as pdf_document:
            page = pdf_document[0]
            scale = clamp_render_scale(*render_page_size(page), 1.5)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
            img = open_image_safe(pix.tobytes("png"))
            img.thumbnail((300, 400), Image.Resampling.LANCZOS)
            return ThumbnailService._upload_png(ThumbnailService._png_bytes(img), folder, language_code, category)

    @staticmethod
    def _store_remote_image(
        url: str,
        folder: str,
        language_code: Optional[str],
        category: str,
        allowed_hosts: Optional[tuple] = None,
    ) -> Optional[str]:
        try:
            raw = ThumbnailService._download_https(url, allowed_hosts=allowed_hosts)
            return ThumbnailService._store_image_bytes(raw, folder, language_code, category)
        except Exception as exc:
            current_app.logger.warning("Thumbnail image was not stored from %s: %s", url, exc)
            return None

    @staticmethod
    def _store_image_bytes(data: bytes, folder: str, language_code: Optional[str], category: str) -> Optional[str]:
        from PIL import Image

        img = open_image_safe(data)
        img.thumbnail((300, 400), Image.Resampling.LANCZOS)
        if img.mode not in {"RGB", "RGBA"}:
            img = img.convert("RGB")
        return ThumbnailService._upload_png(ThumbnailService._png_bytes(img), folder, language_code, category)

    @staticmethod
    def _upload_png(png: bytes, folder: str, language_code: Optional[str], category: str) -> str:
        name = f"thumbnail_{language_code}.png" if language_code else "thumbnail.png"
        return storage.upload(category, f"{folder}/thumbnails/{name}", png)

    @staticmethod
    def _png_bytes(img) -> bytes:
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    @staticmethod
    def _cover_hosts() -> tuple:
        from app.utils.external_url_validation import resource_link_hosts

        hosts = list(resource_link_hosts())
        if "data-api.ifrc.org" not in hosts:
            hosts.append("data-api.ifrc.org")
        return tuple(hosts)

    @staticmethod
    def _download_https(url: str, *, allowed_hosts: Optional[tuple] = None) -> bytes:
        import urllib.request

        from app.utils.outbound_url import validate_outbound_url

        hosts = list(allowed_hosts or ())
        result = validate_outbound_url(url, allowed_hosts=hosts, allowed_ports=(443,), resolve_dns=True)
        if not result.ok:
            raise ValueError(result.reason or "URL is not allowed")
        request = urllib.request.Request(url, headers={"User-Agent": "HumanitarianDatabank-thumbnail/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - host was just validated
            return response.read(8 * 1024 * 1024)

    @staticmethod
    def _largest_embedded_image(data: bytes) -> Optional[bytes]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            return None
        best: Optional[bytes] = None
        best_area = 0
        with archive:
            names = [
                name for name in archive.namelist()
                if name.startswith(_OFFICE_MEDIA) and not name.endswith("/")
            ]
            for name in names:
                raw = archive.read(name)
                try:
                    img = open_image_safe(raw)
                except Exception:
                    continue
                width, height = img.size
                img.close()
                if width < _MIN_EMBEDDED_EDGE or height < _MIN_EMBEDDED_EDGE:
                    continue
                area = width * height
                if area > best_area:
                    best = raw
                    best_area = area
        return best

    @staticmethod
    def _cover_lines(data: bytes, ext: str, title: str) -> list[str]:
        lines = [title.strip() or "Document"]
        extracted: list[str] = []
        if ext == ".docx":
            extracted = ThumbnailService._docx_paragraphs(data)
        elif ext == ".pptx":
            extracted = ThumbnailService._pptx_slide_text(data)
        for line in extracted:
            if line.casefold() == lines[0].casefold():
                continue
            lines.append(line)
            if len(lines) >= 8:
                break
        return lines

    @staticmethod
    def _docx_paragraphs(data: bytes) -> list[str]:
        try:
            from docx import Document
        except ImportError:
            return []
        document = Document(io.BytesIO(data))
        return [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text and paragraph.text.strip()]

    @staticmethod
    def _pptx_slide_text(data: bytes) -> list[str]:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                xml = archive.read("ppt/slides/slide1.xml").decode("utf-8", "ignore")
        except (KeyError, zipfile.BadZipFile):
            return []
        text = re.sub(r"<[^>]+>", " ", xml)
        return [part.strip() for part in re.split(r"\s{2,}", re.sub(r"\s+", " ", text)) if part.strip()]

    @staticmethod
    def _cover_card(lines: list[str]) -> bytes:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (300, 400), "#011E41")
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, 300, 10), fill="#EE1C25")
        try:
            title_font = ImageFont.load_default(size=22)
            body_font = ImageFont.load_default(size=16)
        except TypeError:
            title_font = body_font = ImageFont.load_default()
        y = 28
        for index, line in enumerate(lines[:8]):
            font = title_font if index == 0 else body_font
            words = (line or "").split()
            current = ""
            for word in words:
                trial = f"{current} {word}".strip()
                if len(trial) > 28 and current:
                    draw.text((16, y), current, fill="white", font=font)
                    y += 28 if index == 0 else 22
                    current = word
                else:
                    current = trial
            if current:
                draw.text((16, y), current[:40], fill="white", font=font)
                y += 32 if index == 0 else 24
            if y > 360:
                break
        return ThumbnailService._png_bytes(img)
