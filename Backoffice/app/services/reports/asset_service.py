"""Report image uploads. Keys always stay under ``{report_id}/``."""

from __future__ import annotations

import os
import re
import uuid

_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_MAX_ASSET_BYTES = 8 * 1024 * 1024


def asset_belongs_to_report(report_id: int, asset_key: str) -> bool:
    """True when *asset_key* is a relative path inside this report's storage prefix."""
    key = (asset_key or "").replace("\\", "/").strip().strip("/")
    if not key or ".." in key.split("/"):
        return False
    return key.startswith(f"{int(report_id)}/")


def build_asset_key(report_id: int, filename: str) -> str:
    """Return a storage key for an image upload, or raise ValueError."""
    base = os.path.basename((filename or "").replace("\\", "/")).replace("\x00", "")
    ext = os.path.splitext(base)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise ValueError("Upload a PNG, JPG, GIF, or WebP image.")
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.splitext(base)[0]).strip("._")[:40] or "image"
    return f"{int(report_id)}/assets/{uuid.uuid4().hex}_{stem}{ext}"


def read_upload(file, *, max_bytes: int = _MAX_ASSET_BYTES) -> bytes:
    data = file.read(max_bytes + 1)
    if not data:
        raise ValueError("file is empty")
    if len(data) > max_bytes:
        raise ValueError("Image must be 8 MB or smaller.")
    return data
