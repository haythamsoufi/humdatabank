"""Template-owned image assets for form-builder Image items."""

from __future__ import annotations

import os
import re
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from flask import current_app, url_for
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.services import storage_service as storage

TEMPLATE_ASSETS = "template_assets"

ALLOWED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB

_UNSAFE_URL_SCHEMES = frozenset({"javascript", "data", "vbscript", "file"})
_STATIC_PATH_PREFIX = re.compile(r"^/(static|uploads)/", re.I)


def _supported_language_codes() -> list[str]:
    from config.config import Config

    codes = current_app.config.get("SUPPORTED_LANGUAGES", getattr(Config, "LANGUAGES", ["en"]))
    return [str(c).split("_", 1)[0].lower() for c in (codes or []) if c]


def validate_image_url(url: str) -> Optional[str]:
    """Validate and normalize an external or site-relative image URL."""
    if not url or not isinstance(url, str):
        return None
    cleaned = url.strip()
    if not cleaned or any(ch in cleaned for ch in ('"', "'", "<", ">", "\n", "\r")):
        return None
    if _STATIC_PATH_PREFIX.match(cleaned):
        return cleaned
    if cleaned.startswith("/") and not cleaned.startswith("//"):
        return cleaned
    try:
        parsed = urlparse(cleaned)
    except Exception:
        return None
    scheme = (parsed.scheme or "").lower()
    if scheme in _UNSAFE_URL_SCHEMES:
        return None
    if scheme not in ("http", "https", ""):
        return None
    if scheme in ("http", "https") and not parsed.netloc:
        return None
    return cleaned


def build_storage_rel_path(
    template_id: int,
    version_id: int,
    item_id: Optional[int],
    language: str,
    filename: str,
) -> str:
    """Build a normalized relative path under template_assets/."""
    lang = (language or "en").strip().lower().split("_", 1)[0] or "en"
    safe_name = secure_filename(filename) or "image.png"
    item_segment = str(item_id) if item_id else "draft"
    return f"{template_id}/v{version_id}/items/{item_segment}/{lang}/{safe_name}"


def upload_template_image(
    file_storage: FileStorage,
    *,
    template_id: int,
    version_id: int,
    language: str,
    item_id: Optional[int] = None,
) -> Dict[str, str]:
    """Upload image bytes and return metadata for config storage."""
    from app.utils.advanced_validation import validate_upload_extension_and_mime

    if not file_storage or not file_storage.filename:
        raise ValueError("No file selected")
    name = secure_filename(file_storage.filename)
    if not name:
        raise ValueError("Invalid filename")
    _, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(
            "File type not allowed. Allowed: " + ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
        )
    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > MAX_IMAGE_BYTES:
        raise ValueError(f"File is too large (max {MAX_IMAGE_BYTES // (1024 * 1024)} MB)")
    validate_upload_extension_and_mime(file_storage, ALLOWED_IMAGE_EXTENSIONS)
    file_storage.seek(0)
    uniq = uuid.uuid4().hex[:12]
    stem = os.path.splitext(name)[0] or "image"
    stored_filename = f"{uniq}_{secure_filename(stem)}{ext}"
    rel = build_storage_rel_path(template_id, version_id, item_id, language, stored_filename)
    storage.upload(TEMPLATE_ASSETS, rel, file_storage)
    return {
        "source_type": "upload",
        "storage_path": rel,
        "filename": stored_filename,
    }


def normalize_storage_path(storage_path: Optional[str]) -> Optional[str]:
    return _normalize_storage_path(storage_path)


def delete_template_image_if_present(storage_path: Optional[str]) -> None:
    """Remove a stored template image when replaced or deleted."""
    rel = _normalize_storage_path(storage_path)
    if not rel:
        return
    try:
        storage.delete(TEMPLATE_ASSETS, rel)
    except Exception:
        pass


def _normalize_storage_path(storage_path: Optional[str]) -> Optional[str]:
    if not storage_path or not isinstance(storage_path, str):
        return None
    rel = storage_path.strip().replace("\\", "/").strip("/")
    if not rel or ".." in rel.split("/"):
        return None
    return rel


def delete_all_image_sources_from_config(config: Optional[dict]) -> None:
    """Delete all uploaded blobs referenced in an image item config."""
    if not isinstance(config, dict):
        return
    image_cfg = config.get("image")
    if not isinstance(image_cfg, dict):
        return
    sources = image_cfg.get("sources")
    if not isinstance(sources, dict):
        return
    for src in sources.values():
        if isinstance(src, dict) and src.get("source_type") == "upload":
            delete_template_image_if_present(src.get("storage_path"))


def build_admin_serve_url(template_id: int, storage_path: str) -> str:
    rel = _normalize_storage_path(storage_path)
    if not rel:
        return ""
    try:
        return url_for(
            "form_builder.serve_template_image_asset",
            template_id=template_id,
            rel_path=rel,
        )
    except Exception:
        return ""


def build_entry_serve_url(item_id: int, storage_path: str, language: Optional[str] = None) -> str:
    rel = _normalize_storage_path(storage_path)
    if not rel:
        return ""
    try:
        return url_for(
            "forms.serve_template_image",
            item_id=item_id,
            rel_path=rel,
            lang=language or "",
        )
    except Exception:
        return ""


def resolve_display_url(
    source: Optional[dict],
    *,
    template_id: Optional[int] = None,
    item_id: Optional[int] = None,
    language: Optional[str] = None,
    for_entry: bool = False,
) -> str:
    """Resolve a source dict to a browser-safe display URL."""
    if not isinstance(source, dict):
        return ""
    source_type = (source.get("source_type") or "").strip().lower()
    if source_type == "upload":
        storage_path = source.get("storage_path")
        if not storage_path:
            return ""
        if for_entry and item_id:
            return build_entry_serve_url(item_id, storage_path, language)
        if template_id:
            return build_admin_serve_url(template_id, storage_path)
        return ""
    if source_type == "url":
        return validate_image_url(source.get("url") or "") or ""
    return ""


def resolve_locale_image_source(
    config: Optional[dict],
    locale: str,
    *,
    fallback_locales: Optional[list[str]] = None,
) -> Optional[dict]:
    """Pick the best image source for a locale from config.image.sources."""
    if not isinstance(config, dict):
        return None
    image_cfg = config.get("image")
    if not isinstance(image_cfg, dict):
        return None
    sources = image_cfg.get("sources")
    if not isinstance(sources, dict) or not sources:
        return None
    locale = (locale or "en").strip().lower().split("_", 1)[0] or "en"
    keys = [locale]
    if fallback_locales:
        keys.extend(fallback_locales)
    keys.extend(["en"])
    seen = set()
    for key in keys:
        if not key or key in seen:
            continue
        seen.add(key)
        src = sources.get(key)
        if not isinstance(src, dict):
            continue
        if src.get("source_type") == "upload" and src.get("storage_path"):
            return src
        if src.get("source_type") == "url" and validate_image_url(src.get("url") or ""):
            return src
    for src in sources.values():
        if not isinstance(src, dict):
            continue
        if src.get("source_type") == "upload" and src.get("storage_path"):
            return src
        if src.get("source_type") == "url" and validate_image_url(src.get("url") or ""):
            return src
    return None


def normalize_image_config(raw_config: Any, *, previous_config: Optional[dict] = None) -> dict:
    """Validate and normalize image config from client JSON."""
    supported = set(_supported_language_codes())
    result: dict = {
        "alignment": "center",
        "max_width": "100%",
        "sources": {},
    }
    if not isinstance(raw_config, dict):
        raw_config = {}
    image_raw = raw_config.get("image") if "image" in raw_config else raw_config
    if not isinstance(image_raw, dict):
        image_raw = {}

    alignment = (image_raw.get("alignment") or "center").strip().lower()
    if alignment not in ("left", "center", "right"):
        alignment = "center"
    result["alignment"] = alignment

    max_width = (image_raw.get("max_width") or "100%").strip()
    if max_width not in ("auto", "100%", "75%", "50%"):
        max_width = "100%"
    result["max_width"] = max_width

    sources_in = image_raw.get("sources") or {}
    if not isinstance(sources_in, dict):
        sources_in = {}

    prev_sources = {}
    if isinstance(previous_config, dict):
        prev_image = previous_config.get("image") or {}
        if isinstance(prev_image, dict):
            prev_sources = prev_image.get("sources") or {}

    for lang, src in sources_in.items():
        if not isinstance(lang, str) or not isinstance(src, dict):
            continue
        code = lang.strip().lower().split("_", 1)[0]
        if code not in supported:
            continue
        source_type = (src.get("source_type") or "").strip().lower()
        if source_type == "upload":
            storage_path = _normalize_storage_path(src.get("storage_path"))
            if not storage_path:
                continue
            result["sources"][code] = {
                "source_type": "upload",
                "storage_path": storage_path,
                "filename": (src.get("filename") or "").strip() or None,
            }
        elif source_type == "url":
            url = validate_image_url(src.get("url") or "")
            if url:
                result["sources"][code] = {"source_type": "url", "url": url}

    # Delete replaced upload paths
    if isinstance(prev_sources, dict):
        for code, prev_src in prev_sources.items():
            if not isinstance(prev_src, dict) or prev_src.get("source_type") != "upload":
                continue
            prev_path = prev_src.get("storage_path")
            new_src = result["sources"].get(code)
            new_path = new_src.get("storage_path") if isinstance(new_src, dict) else None
            if prev_path and prev_path != new_path:
                delete_template_image_if_present(prev_path)

    return {"image": result}


def collect_orphan_paths_after_update(previous_config: Optional[dict], new_config: dict) -> None:
    """Delete upload paths removed from config during edit."""
    if not isinstance(previous_config, dict):
        return
    prev_image = previous_config.get("image") or {}
    new_image = (new_config or {}).get("image") or {}
    prev_sources = prev_image.get("sources") if isinstance(prev_image, dict) else {}
    new_sources = new_image.get("sources") if isinstance(new_image, dict) else {}
    if not isinstance(prev_sources, dict):
        return
    new_paths = set()
    if isinstance(new_sources, dict):
        for src in new_sources.values():
            if isinstance(src, dict) and src.get("source_type") == "upload" and src.get("storage_path"):
                new_paths.add(src["storage_path"])
    for src in prev_sources.values():
        if not isinstance(src, dict) or src.get("source_type") != "upload":
            continue
        path = src.get("storage_path")
        if path and path not in new_paths:
            delete_template_image_if_present(path)
