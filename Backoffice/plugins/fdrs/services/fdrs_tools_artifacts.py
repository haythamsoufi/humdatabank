"""Durable FDRS Tools artifacts (verification + document-status Excel).

Workbooks used to live in OS temp files / ``instance/``, which App Service
wipes on deploy. These helpers write the latest workbook + a small JSON
sidecar through ``storage_service`` (filesystem locally, Azure Blob in prod).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, BinaryIO, Dict, List, Optional, Sequence, Tuple, Union

from app.services.platform import storage_service

logger = logging.getLogger(__name__)

STORAGE_CATEGORY = "fdrs_tools"

Source = Union[str, bytes, BinaryIO]


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def verify_xlsx_rel(template_id: int) -> str:
    return f"verify/{int(template_id)}/latest.xlsx"


def verify_meta_rel(template_id: int) -> str:
    return f"verify/{int(template_id)}/latest.json"


def documents_xlsx_rel() -> str:
    return "documents/latest.xlsx"


def documents_meta_rel() -> str:
    return "documents/latest.json"


def exists(rel_path: str) -> bool:
    return storage_service.exists(STORAGE_CATEGORY, rel_path)


def verify_latest_exists(template_id: int) -> bool:
    return exists(verify_xlsx_rel(template_id)) and exists(verify_meta_rel(template_id))


def documents_latest_exists() -> bool:
    return exists(documents_xlsx_rel()) and exists(documents_meta_rel())


def upload_bytes(rel_path: str, data: bytes) -> str:
    return storage_service.upload(STORAGE_CATEGORY, rel_path, data)


def download_bytes(rel_path: str) -> bytes:
    return storage_service.download(STORAGE_CATEGORY, rel_path)


def stream_xlsx(rel_path: str, filename: str):
    return storage_service.stream_response(
        STORAGE_CATEGORY,
        rel_path,
        filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
    )


def load_json(rel_path: str) -> Optional[Dict[str, Any]]:
    if not exists(rel_path):
        return None
    try:
        raw = download_bytes(rel_path)
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        logger.exception("Failed to read FDRS tools artifact JSON: %s", rel_path)
        return None
    return data if isinstance(data, dict) else None


def persist_json(rel_path: str, payload: Dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    return upload_bytes(rel_path, body)


def persist_xlsx_and_meta(
    *,
    xlsx_rel: str,
    meta_rel: str,
    local_xlsx_path: str,
    meta: Dict[str, Any],
) -> Dict[str, Any]:
    """Upload a local workbook + sidecar JSON. Returns the stored meta."""
    with open(local_xlsx_path, "rb") as handle:
        upload_bytes(xlsx_rel, handle.read())
    stored = dict(meta)
    stored.setdefault("completed_at", utc_iso_now())
    persist_json(meta_rel, stored)
    return stored


def persist_verify_latest(
    *,
    template_id: int,
    local_xlsx_path: str,
    stats: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "kind": "fdrs.sync_verify",
        "template_id": int(template_id),
        "stats": dict(stats or {}),
        "completed_at": utc_iso_now(),
    }
    if extra:
        meta.update(extra)
    return persist_xlsx_and_meta(
        xlsx_rel=verify_xlsx_rel(template_id),
        meta_rel=verify_meta_rel(template_id),
        local_xlsx_path=local_xlsx_path,
        meta=meta,
    )


def persist_documents_latest(
    *,
    local_xlsx_path: str,
    stats: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "kind": "fdrs.document_status",
        "stats": dict(stats or {}),
        "completed_at": utc_iso_now(),
    }
    if extra:
        meta.update(extra)
    return persist_xlsx_and_meta(
        xlsx_rel=documents_xlsx_rel(),
        meta_rel=documents_meta_rel(),
        local_xlsx_path=local_xlsx_path,
        meta=meta,
    )


def load_verify_latest_meta(template_id: int) -> Optional[Dict[str, Any]]:
    if not verify_latest_exists(template_id):
        return None
    return load_json(verify_meta_rel(template_id))


def load_documents_latest_meta() -> Optional[Dict[str, Any]]:
    if not documents_latest_exists():
        return None
    return load_json(documents_meta_rel())


def _cell_to_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _as_filter_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip().lower()


# Parsed verification workbooks are large (one row per society × year × base KPI).
# Keep a couple of sheets in memory so paging and search do not re-read the xlsx.
_SHEET_CACHE_LOCK = threading.Lock()
_SHEET_CACHE: "OrderedDict[tuple, Dict[str, Any]]" = OrderedDict()
_SHEET_CACHE_LIMIT = 2


def _sheet_cache_key(source: Source, sheet_name: str, cache_token: Optional[str]) -> Optional[tuple]:
    if cache_token:
        return ("token", str(cache_token), sheet_name)
    if isinstance(source, (str, os.PathLike)):
        path = os.path.abspath(os.fspath(source))
        try:
            st = os.stat(path)
        except OSError:
            return None
        return ("path", path, st.st_mtime_ns, st.st_size, sheet_name)
    if isinstance(source, (bytes, bytearray)):
        digest = hashlib.sha256(source).hexdigest()
        return ("bytes", len(source), digest, sheet_name)
    return None


def _sheet_cache_get(key: Optional[tuple]) -> Optional[Dict[str, Any]]:
    if key is None:
        return None
    with _SHEET_CACHE_LOCK:
        hit = _SHEET_CACHE.get(key)
        if hit is None:
            return None
        _SHEET_CACHE.move_to_end(key)
        return hit


def _sheet_cache_put(key: Optional[tuple], value: Dict[str, Any]) -> None:
    if key is None:
        return
    with _SHEET_CACHE_LOCK:
        _SHEET_CACHE[key] = value
        _SHEET_CACHE.move_to_end(key)
        while len(_SHEET_CACHE) > _SHEET_CACHE_LIMIT:
            _SHEET_CACHE.popitem(last=False)


def _open_workbook(source: Source):
    from app.utils.safe_workbook import load_workbook_safe, read_workbook_file_bytes

    if isinstance(source, (str, os.PathLike)):
        return load_workbook_safe(read_workbook_file_bytes(source), read_only=True, data_only=True)
    if hasattr(source, "read") and not isinstance(source, (bytes, bytearray)):
        data = source.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        return load_workbook_safe(data, read_only=True, data_only=True)
    return load_workbook_safe(source, read_only=True, data_only=True)


def _load_sheet_rows(source: Source, wanted: str) -> Dict[str, Any]:
    """Parse one sheet into column-aligned tuples. Empty result when the sheet is missing."""
    wb = _open_workbook(source)
    try:
        sheet_names = list(wb.sheetnames)
        resolved = wanted
        if resolved not in wb.sheetnames:
            resolved = sheet_names[0] if sheet_names else resolved
        ws = wb[resolved] if resolved in wb.sheetnames else None
        if ws is None:
            return {
                "sheet": resolved,
                "sheets": sheet_names,
                "columns": [],
                "col_index": {},
                "rows": [],
            }
        rows_iter = ws.iter_rows(values_only=True)
        raw_header = next(rows_iter, None) or ()
        columns = [str(c) if c is not None else "" for c in raw_header]
        col_index = {col.lower(): i for i, col in enumerate(columns) if col}
        width = len(columns)
        stored: List[Tuple[Any, ...]] = []
        for raw in rows_iter:
            stored.append(tuple(_cell_to_json(raw[i] if i < len(raw) else None) for i in range(width)))
        return {
            "sheet": resolved,
            "sheets": sheet_names,
            "columns": columns,
            "col_index": col_index,
            "rows": stored,
        }
    finally:
        wb.close()


def _row_matches(
    raw: Tuple[Any, ...],
    *,
    columns: Sequence[str],
    col_index: Dict[str, int],
    active_filters: Dict[str, str],
    any_filters: Dict[str, set],
    query: Optional[str],
    search_cols: set,
) -> bool:
    for col_key, expected in active_filters.items():
        idx = col_index.get(col_key)
        cell = raw[idx] if idx is not None and idx < len(raw) else None
        if _as_filter_text(cell) != expected:
            return False
    for col_key, allowed in any_filters.items():
        idx = col_index.get(col_key)
        cell = raw[idx] if idx is not None and idx < len(raw) else None
        if _as_filter_text(cell) not in allowed:
            return False
    if not query:
        return True
    haystack_idxs = (
        [col_index[c] for c in search_cols if c in col_index]
        if search_cols
        else range(len(columns))
    )
    for idx in haystack_idxs:
        cell = raw[idx] if idx < len(raw) else None
        if query in _as_filter_text(cell):
            return True
    return False


def _tuple_to_row(raw: Tuple[Any, ...], columns: Sequence[str]) -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    for i, col in enumerate(columns):
        if not col:
            continue
        row[col] = raw[i] if i < len(raw) else None
    return row


def read_xlsx_sheet(
    source: Source,
    *,
    sheet: str,
    aliases: Optional[Dict[str, str]] = None,
    page: int = 1,
    per_page: int = 200,
    filters: Optional[Dict[str, str]] = None,
    column_in: Optional[Dict[str, Sequence[str]]] = None,
    search: Optional[str] = None,
    search_columns: Optional[List[str]] = None,
    cache_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Read one sheet as a paginated JSON table.

    *filters* is ``{column_name_lower: expected_value_lower}`` and matches
    case-insensitively (booleans become ``true``/``false``). *column_in*
    keeps a row when the cell is one of the listed values (also
    case-insensitive). *search* is a substring match across *search_columns*
    (or every column when omitted). ``per_page <= 0`` returns every matching
    row (capped at 50_000) so client-side grids can filter locally.
    ``truncated`` is true when that cap drops matching rows.

    Parsed rows are cached (path mtime, content hash, or *cache_token*) so
    later pages do not reopen the workbook.
    """
    page = max(1, int(page or 1))
    try:
        requested = int(per_page) if per_page is not None else 200
    except (TypeError, ValueError):
        requested = 200
    return_all = requested <= 0
    per_page = 50000 if return_all else min(500, max(1, requested))
    wanted = (sheet or "").strip()
    if aliases:
        wanted = aliases.get(wanted.lower(), wanted)
    active_filters = {
        str(key).strip().lower(): str(val).strip().lower()
        for key, val in (filters or {}).items()
        if val is not None and str(val).strip() != ""
    }
    query = (search or "").strip().lower() or None
    search_cols = {c.strip().lower() for c in (search_columns or []) if c and c.strip()}
    any_filters = {
        str(key).strip().lower(): {str(val).strip().lower() for val in values if str(val).strip()}
        for key, values in (column_in or {}).items()
        if values
    }

    cache_key = _sheet_cache_key(source, wanted, cache_token)
    parsed = _sheet_cache_get(cache_key)
    if parsed is None:
        parsed = _load_sheet_rows(source, wanted)
        _sheet_cache_put(cache_key, parsed)

    columns: List[str] = list(parsed.get("columns") or [])
    col_index: Dict[str, int] = dict(parsed.get("col_index") or {})
    stored: List[Tuple[Any, ...]] = list(parsed.get("rows") or [])
    sheet_names = list(parsed.get("sheets") or [])
    resolved = parsed.get("sheet") or wanted
    total_rows = len(stored)
    visible_columns = [c for c in columns if c]

    if not columns and not stored:
        return {
            "sheet": resolved,
            "sheets": sheet_names,
            "columns": [],
            "rows": [],
            "page": page,
            "per_page": per_page,
            "total_rows": 0,
            "filtered_rows": 0,
            "truncated": False,
        }

    needs_scan = bool(active_filters or any_filters or query)
    if needs_scan:
        matched = [
            raw
            for raw in stored
            if _row_matches(
                raw,
                columns=columns,
                col_index=col_index,
                active_filters=active_filters,
                any_filters=any_filters,
                query=query,
                search_cols=search_cols,
            )
        ]
    else:
        matched = stored

    filtered_rows = len(matched)
    if return_all:
        start = 0
        window = matched[:per_page]
        page = 1
        reported_per_page = len(window)
    else:
        start = (page - 1) * per_page
        window = matched[start:start + per_page]
        reported_per_page = per_page
    return {
        "sheet": resolved,
        "sheets": sheet_names,
        "columns": visible_columns,
        "rows": [_tuple_to_row(raw, columns) for raw in window],
        "page": page,
        "per_page": reported_per_page,
        "total_rows": total_rows,
        "filtered_rows": filtered_rows,
        "truncated": bool(return_all and filtered_rows > len(window)),
    }
