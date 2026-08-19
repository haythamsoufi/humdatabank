"""Resolve public URLs for sector logo images."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from flask import url_for


def _logo_filename(entity: Any) -> Optional[str]:
    name = (getattr(entity, "logo_filename", None) or "").strip()
    if name:
        return name
    legacy = (getattr(entity, "logo_path", None) or "").strip()
    return legacy or None


def _cache_version(updated_at: Any) -> Optional[str]:
    if updated_at is None:
        return None
    if isinstance(updated_at, datetime):
        return str(int(updated_at.timestamp()))
    return None


def _cdn_logo_url(filename: str, updated_at: Any = None, subdir: str = "sectors") -> Optional[str]:
    from app.services.platform import storage_service as storage

    if not storage.public_cdn_enabled():
        return None
    base = (storage.public_cdn_base_url() or "").rstrip("/")
    if not base:
        return None
    safe_name = filename.replace("\\", "/").split("/")[-1]
    blob_path = storage.system_logo_cdn_blob_name(subdir, safe_name)
    url = f"{base}/{blob_path}"
    version = _cache_version(updated_at)
    if version:
        return f"{url}?v={version}"
    return url


def sector_logo_url(
    sector: Any,
    *,
    external: bool = False,
    via_api: bool = False,
) -> Optional[str]:
    """Return the best public URL for a sector logo."""
    filename = _logo_filename(sector)
    if not filename:
        return None

    cdn_url = _cdn_logo_url(filename, getattr(sector, "updated_at", None))
    if cdn_url:
        return cdn_url

    if via_api:
        from flask import request

        path = f"/api/v1/uploads/sectors/{filename}"
        if external:
            return f"{request.host_url.rstrip('/')}{path}"
        return url_for("api.serve_sector_logo", filename=filename)

    return url_for(
        "system_admin.sector_logo",
        sector_id=sector.id,
        _external=external,
    )


def spef_icon_url(
    row: Any,
    *,
    external: bool = False,
    via_api: bool = False,
) -> Optional[str]:
    """Return the best public URL for an SP/EF catalog icon."""
    filename = (getattr(row, "icon_filename", None) or "").strip()
    if not filename:
        return None

    cdn_url = _cdn_logo_url(filename, getattr(row, "updated_at", None), subdir="spef")
    if cdn_url:
        return cdn_url

    if via_api:
        from flask import request

        path = f"/api/v1/uploads/spef/{filename}"
        if external:
            return f"{request.host_url.rstrip('/')}{path}"
        return url_for("api.serve_spef_icon", filename=filename)

    row_id = getattr(row, "id", None)
    if not row_id:
        return None
    return url_for(
        "system_admin.spef_icon",
        sid=row_id,
        _external=external,
    )
