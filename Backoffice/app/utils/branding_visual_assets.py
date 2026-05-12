"""Organization logo/favicon uploads for settings (stored under ``system/branding/*``).

Upload UI is exposed only when :func:`storage_service.is_azure` is active and an Azure
Blob connection string is configured (same pattern as documents and sector logos).
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Optional
from urllib.parse import unquote

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.services import storage_service as storage

SYSTEM_BRANDING_REL_PREFIX = "branding"

_ALLOWED_LOGO_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
)
_ALLOWED_FAV_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"}
)

_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


def branding_visual_upload_available() -> bool:
    """True when uploads go to Azure Blob using the app's upload storage wiring."""
    if not storage.is_azure():
        return False
    return bool((current_app.config.get("AZURE_STORAGE_CONNECTION_STRING") or "").strip())


def branding_visual_assets_ui_context() -> Dict[str, Any]:
    """Facts for the Branding → Visual Assets panel (help text for upload vs path-only modes)."""
    cfg = current_app.config
    conn = (cfg.get("AZURE_STORAGE_CONNECTION_STRING") or "").strip()
    provider = (cfg.get("UPLOAD_STORAGE_PROVIDER") or "filesystem").strip().lower()
    has_file_share_env = bool((cfg.get("AZURE_FILE_SHARE_CONNECTION_STRING") or "").strip())
    upload_ok = branding_visual_upload_available()
    azure_configured_but_filesystem = bool(conn) and provider != "azure_blob"
    return {
        "upload_available": upload_ok,
        "has_azure_storage_connection_string": bool(conn),
        "upload_storage_provider": provider,
        "has_azure_file_share_env": has_file_share_env,
        "azure_configured_but_filesystem_provider": azure_configured_but_filesystem,
    }


def relative_path_under_branding(stored_rel: Optional[str]) -> Optional[str]:
    """Return normalized ``branding/<file>`` or None."""
    raw = (stored_rel or "").strip().replace("\\", "/").strip("/")
    if raw.lower().startswith(f"{SYSTEM_BRANDING_REL_PREFIX}/"):
        return raw
    return None


def _validate_and_upload(
    file_storage: FileStorage,
    *,
    basename_stem: str,
    allowed_ext: frozenset,
) -> str:
    """Upload to ``SYSTEM/branding/<uuid>_<stem>.ext``; return stored rel path."""
    if not file_storage or not file_storage.filename:
        raise ValueError("No file")
    name = secure_filename(file_storage.filename)
    if not name:
        raise ValueError("Invalid filename")
    _, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext not in allowed_ext:
        raise ValueError(
            "File type not allowed. Allowed: " + ", ".join(sorted(allowed_ext))
        )
    file_storage.seek(0, os.SEEK_END)
    sz = file_storage.tell()
    file_storage.seek(0)
    if sz > _MAX_BYTES:
        raise ValueError(f"File is too large (max {_MAX_BYTES // (1024 * 1024)} MB)")
    uniq = uuid.uuid4().hex[:12]
    safe_stem = secure_filename(basename_stem) or basename_stem
    stored_filename = f"{uniq}_{safe_stem}{ext}"
    rel = f"{SYSTEM_BRANDING_REL_PREFIX}/{stored_filename}"
    storage.upload(storage.SYSTEM, rel, file_storage)
    return rel


def upload_organization_logo(file_storage: FileStorage) -> str:
    return _validate_and_upload(
        file_storage, basename_stem="logo", allowed_ext=_ALLOWED_LOGO_EXTENSIONS
    )


def upload_organization_favicon(file_storage: FileStorage) -> str:
    return _validate_and_upload(
        file_storage, basename_stem="favicon", allowed_ext=_ALLOWED_FAV_EXTENSIONS
    )


def delete_branding_object_if_present(rel_path: Optional[str]) -> None:
    """Remove a blob/local file under ``branding/`` when replacing assets."""
    rel = relative_path_under_branding(rel_path)
    if not rel:
        return
    try:
        storage.delete(storage.SYSTEM, rel)
    except Exception:
        pass


def safe_branding_download_filename(url_path: str) -> str:
    """Basename suitable for Flask ``download_name``."""
    tail = url_path.rstrip("/").split("/")[-1]
    return secure_filename(unquote(tail)) or "asset"

