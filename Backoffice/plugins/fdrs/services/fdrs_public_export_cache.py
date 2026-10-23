"""Daily files for the public FDRS CSV and Excel downloads.

``/csv/export`` and ``/csv/exportns`` read these files instead of querying the
published snapshot on the request. A scheduler job rebuilds them once a day.
The previous files stay in place until a new build finishes, and the two full
files are also kept for the last 14 UTC days.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from flask import current_app
from werkzeug.exceptions import NotFound

from app.services.platform import storage_service
from plugins.fdrs.services import fdrs_public_adapter as adapter

logger = logging.getLogger(__name__)

STORAGE_CATEGORY = "fdrs_public_export"
MANIFEST_REL = "latest/manifest.json"
RETENTION_DAYS = 14
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DON_RE = re.compile(r"^[A-Z0-9]{1,32}$")
_CSV_MIMETYPE = "text/csv; charset=utf-8"
_XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def cache_enabled() -> bool:
    return bool(current_app.config.get("FDRS_PUBLIC_EXPORT_CACHE_ENABLED", True))


def select_archives(existing: Iterable[str], today: str, *, keep: int = RETENTION_DAYS) -> tuple[list[str], list[str]]:
    """Dates to retain, and dates to delete. ``today`` is always retained."""
    valid = sorted({day for day in existing if _DATE_RE.fullmatch(day or "")})
    if not _DATE_RE.fullmatch(today or ""):
        return valid, []
    older = [day for day in reversed(valid) if day != today]
    kept = sorted(set(older[: max(keep - 1, 0)]) | {today})
    dropped = [day for day in valid if day not in kept]
    return kept, dropped


def build_public_export_snapshot() -> dict[str, Any]:
    """Write today's full export and one file pair per society that has rows."""
    rows = adapter.export_rows()
    mapping = adapter.export_mapping(rows)
    csv_bytes = adapter.export_csv(rows)
    xlsx_bytes = adapter.export_xlsx(rows, mapping=mapping)
    today = datetime.now(timezone.utc).date().isoformat()
    previous = _load_manifest()

    by_don: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        code = str(row.get("KPI_DON_code") or "").strip().upper()
        if _DON_RE.fullmatch(code):
            by_don.setdefault(code, []).append(row)

    _upload(f"archive/{today}/fdrs.csv", csv_bytes)
    _upload(f"archive/{today}/fdrs.xlsx", xlsx_bytes)
    for code, subset in sorted(by_don.items()):
        codes = {item.get("KPI_code") for item in subset}
        subset_mapping = [item for item in mapping if item.get("KPI_code") in codes]
        _upload(f"latest/ns/{code}.csv", adapter.export_csv(subset))
        _upload(f"latest/ns/{code}.xlsx", adapter.export_xlsx(subset, mapping=subset_mapping))
    _upload("latest/fdrs.csv", csv_bytes)
    _upload("latest/fdrs.xlsx", xlsx_bytes)

    kept, dropped = select_archives(previous.get("archives") or [], today)
    retired = sorted(set(_society_codes(previous)) - set(by_don))
    manifest = {
        "snapshot_date": today,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "row_count": len(rows),
        "societies": sorted(by_don),
        "archives": kept,
    }
    _upload(MANIFEST_REL, json.dumps(manifest).encode("utf-8"))
    for day in dropped:
        storage_service.delete(STORAGE_CATEGORY, f"archive/{day}/fdrs.csv")
        storage_service.delete(STORAGE_CATEGORY, f"archive/{day}/fdrs.xlsx")
    for code in retired:
        storage_service.delete(STORAGE_CATEGORY, f"latest/ns/{code}.csv")
        storage_service.delete(STORAGE_CATEGORY, f"latest/ns/{code}.xlsx")

    logger.info(
        "FDRS public export snapshot built date=%s rows=%s societies=%s",
        today,
        len(rows),
        len(by_don),
    )
    return manifest


def cached_download(*, excel: bool, don_code: Optional[str] = None):
    """The stored file, or ``None`` when the cache is off or this file is missing."""
    if not cache_enabled():
        return None
    rel = _download_rel(excel=excel, don_code=don_code)
    if rel is None or not storage_service.exists(STORAGE_CATEGORY, rel):
        return None
    filename = _download_name(excel=excel, don_code=don_code)
    try:
        return storage_service.stream_response(
            STORAGE_CATEGORY,
            rel,
            filename,
            mimetype=_XLSX_MIMETYPE if excel else _CSV_MIMETYPE,
            as_attachment=True,
        )
    except NotFound:
        return None


def _download_rel(*, excel: bool, don_code: Optional[str]) -> Optional[str]:
    ext = "xlsx" if excel else "csv"
    if not don_code:
        return f"latest/fdrs.{ext}"
    code = don_code.strip().upper()
    if not _DON_RE.fullmatch(code):
        return None
    return f"latest/ns/{code}.{ext}"


def _download_name(*, excel: bool, don_code: Optional[str]) -> str:
    ext = "xlsx" if excel else "csv"
    if not don_code:
        return f"fdrs.{ext}"
    return f"fdrs-{don_code.strip().upper()}.{ext}"


def _upload(rel_path: str, data: bytes) -> None:
    storage_service.upload(STORAGE_CATEGORY, rel_path, data)


def _society_codes(manifest: Mapping[str, Any]) -> list[str]:
    codes = manifest.get("societies") or []
    if not isinstance(codes, list):
        return []
    return [code for code in codes if isinstance(code, str) and _DON_RE.fullmatch(code)]


def _load_manifest() -> dict[str, Any]:
    if not storage_service.exists(STORAGE_CATEGORY, MANIFEST_REL):
        return {}
    try:
        payload = json.loads(storage_service.download(STORAGE_CATEGORY, MANIFEST_REL).decode("utf-8"))
    except Exception:
        logger.exception("FDRS public export manifest could not be read")
        return {}
    return payload if isinstance(payload, dict) else {}
