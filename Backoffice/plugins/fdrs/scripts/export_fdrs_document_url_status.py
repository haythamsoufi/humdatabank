"""
Export all FDRS document URLs with HTTP probe status to Excel.

The catalog is ``GET /api/DocumentAdmin`` (via ``fdrs_documents_sync``), the same
call the document importer uses. Run it from ``plugins/fdrs/scripts``.

    pip install pandas openpyxl
    python export_fdrs_document_url_status.py --api-key YOUR_KEY

In Backoffice (reads FDRS_DATA_API_KEY from env / .env):
    python plugins/fdrs/scripts/export_fdrs_document_url_status.py
    python plugins/fdrs/scripts/export_fdrs_document_url_status.py --year 2024
    python plugins/fdrs/scripts/export_fdrs_document_url_status.py --limit 50

Also reports Backoffice migration status when run with a Flask app context:
whether each catalog document exists as a SubmittedDocument (``fdrs_import_key``)
and whether file bytes were downloaded (``file_pending`` / ``storage_path``).

On HTTP 403/404, retries once without a trailing _1 / _2 filename suffix
(the API catalog sometimes includes a suffix the file store does not).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

# Migration status values written to the Excel / grid (stable for filters).
MIGRATION_NOT_IN_BACKOFFICE = "not_in_backoffice"
MIGRATION_PENDING_DOWNLOAD = "pending_download"
MIGRATION_MIGRATED = "migrated"
MIGRATION_UNKNOWN = ""  # standalone / no app context

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MAYBE_BACKOFFICE = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))
IN_BACKOFFICE = os.path.isdir(os.path.join(_MAYBE_BACKOFFICE, "app")) and os.path.isfile(
    os.path.join(_MAYBE_BACKOFFICE, "config.py")
)
BACKOFFICE_DIR = _MAYBE_BACKOFFICE if IN_BACKOFFICE else None

DEFAULT_BASE = "https://data-api.ifrc.org"
DEFAULT_OUTPUT = (
    os.path.join(BACKOFFICE_DIR, "instance", "fdrs_document_url_status.xlsx")
    if BACKOFFICE_DIR
    else os.path.join(os.getcwd(), "fdrs_document_url_status.xlsx")
)
_DUP_SUFFIX_RE = re.compile(r"_([1-9]\d?)(\.[A-Za-z0-9]+)$")
_YEAR_IN_TEXT_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
SCAN_YEAR_MIN = 1990
SCAN_YEAR_MAX = 2100


class FdrsDocumentScanCancelled(Exception):
    """User cancelled the FDRS document URL status scan."""


def _load_api_key(explicit: Optional[str]) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    key = (os.environ.get("FDRS_DATA_API_KEY") or "").strip()
    if key:
        return key
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            cfg = (current_app.config.get("FDRS_DATA_API_KEY") or "").strip()
            if cfg:
                return cfg
    except Exception:
        pass
    env_candidates = [
        os.path.join(SCRIPT_DIR, ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]
    if BACKOFFICE_DIR:
        env_candidates.append(os.path.join(BACKOFFICE_DIR, ".env"))
    for env_path in env_candidates:
        if not os.path.isfile(env_path):
            continue
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("FDRS_DATA_API_KEY="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    raise RuntimeError(
        "FDRS_DATA_API_KEY is required (--api-key, env, or .env)."
    )


def encode_document_url(url: str) -> str:
    # Decode first: some catalog links are already percent-encoded.
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def url_without_duplicate_suffix(url: str) -> Optional[str]:
    raw = (url or "").strip()
    if not raw:
        return None
    parts = urllib.parse.urlsplit(raw)
    dirname, sep, filename = (parts.path or "").rpartition("/")
    if not filename:
        return None
    new_name, n = _DUP_SUFFIX_RE.subn(r"\2", filename, count=1)
    if n != 1 or new_name == filename:
        return None
    new_path = f"{dirname}{sep}{new_name}" if sep else new_name
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, new_path, parts.query, parts.fragment)
    )


def probe_url(url: str, *, timeout: int = 25) -> Tuple[int, str]:
    """GET with Range bytes=0-0; returns (status_code, detail)."""
    raw = (url or "").strip()
    if not raw:
        return 0, "empty_url"
    enc = encode_document_url(raw)
    req = urllib.request.Request(
        enc,
        headers={"User-Agent": "HumanitarianDatabank-FDRS-url-export/1.0", "Range": "bytes=0-0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ct = (resp.headers.get("Content-Type") or "")[:80]
            return int(resp.status), ct
    except urllib.error.HTTPError as e:
        reason = (getattr(e, "reason", "") or "")[:80]
        return int(e.code), reason
    except Exception as e:
        return -1, type(e).__name__


def fetch_fdrs_documents(base_url: str, api_key: str) -> List[Dict[str, Any]]:
    """DocumentAdmin catalog, shared with the FDRS document importer."""
    print("Fetching FDRS document catalog...", flush=True)
    from fdrs_documents_sync import fetch_fdrs_documents_api

    flat = fetch_fdrs_documents_api(base_url, api_key)
    print(f"Loaded {len(flat)} documents.", flush=True)
    return flat


def parse_scan_year(raw: Any) -> Optional[int]:
    """Return a catalog year, or ``None`` for a full scan.

    Accepts ``None``, ``""``, and ``"all"`` as full scan. Raises ``ValueError``
    for values that are not a 4-digit year in ``SCAN_YEAR_MIN``–``SCAN_YEAR_MAX``.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError("Invalid year")
    if isinstance(raw, str):
        text = raw.strip()
        if not text or text.lower() == "all":
            return None
        raw = text
    try:
        year = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid year") from exc
    if year < SCAN_YEAR_MIN or year > SCAN_YEAR_MAX:
        raise ValueError("Invalid year")
    return year


def _parse_year_token(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        match = _YEAR_IN_TEXT_RE.search(text)
        return int(match.group(1)) if match else None


def document_matches_scan_year(doc: Dict[str, Any], year: int) -> bool:
    """True when a catalog document belongs to *year*.

    Matches the numeric API ``year`` field, or a YearText range that includes
    *year* (so a 2021–2024 annual report is included in a 2024 scan).
    """
    api_year = _parse_year_token(doc.get("year"))
    if api_year == year:
        return True
    year_text = doc.get("YearText") if doc.get("YearText") not in (None, "") else doc.get("year_text")
    nums = [int(token) for token in _YEAR_IN_TEXT_RE.findall(str(year_text or ""))]
    if not nums:
        return False
    return min(nums) <= year <= max(nums)


def filter_documents_for_scan_year(
    documents: List[Dict[str, Any]],
    year: Optional[int],
) -> List[Dict[str, Any]]:
    """Return *documents* unchanged when *year* is None, else the year slice."""
    if year is None:
        return documents
    year_i = int(year)
    return [doc for doc in documents if document_matches_scan_year(doc, year_i)]


def document_is_public(approval_status: Any, public_code: Any) -> bool:
    """FDRS Public 1–3 or ApprovalStatus ``(Public)``. Private 403s are expected."""
    approval = (str(approval_status) if approval_status is not None else "").strip()
    if approval.endswith("(Private)"):
        return False
    if approval.endswith("(Public)"):
        return True
    try:
        code = int(public_code) if public_code is not None and str(public_code).strip() != "" else None
    except (TypeError, ValueError):
        code = None
    return code in (1, 2, 3)


def document_import_key(doc: Dict[str, Any]) -> str:
    """Stable key matching ``fdrs_documents_sync._fdrs_document_import_key``."""
    raw = "|".join(
        [
            (doc.get("don_code") or "").strip(),
            str(doc.get("year") or ""),
            str(doc.get("document_typeId") or doc.get("document_type_id") or ""),
            (doc.get("name") or "").strip(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def load_backoffice_migration_index() -> Optional[Dict[str, Dict[str, Any]]]:
    """Map ``fdrs_import_key`` → Backoffice row info, or None when unavailable.

    Returns an empty dict when the app context is present but there are no FDRS
    documents yet. Returns ``None`` when running standalone (no Flask context)
    so callers can leave migration columns blank instead of marking everything
    as not migrated.
    """
    try:
        from flask import has_app_context

        if not has_app_context():
            return None
        from app.models.documents import SubmittedDocument

        rows = (
            SubmittedDocument.query.filter(SubmittedDocument.fdrs_import_key.isnot(None))
            .with_entities(
                SubmittedDocument.id,
                SubmittedDocument.fdrs_import_key,
                SubmittedDocument.file_pending,
                SubmittedDocument.storage_path,
                SubmittedDocument.source_url_http_status,
                SubmittedDocument.is_public,
                SubmittedDocument.status,
            )
            .all()
        )
    except Exception as exc:
        print(
            f"Warning: Backoffice migration lookup skipped ({type(exc).__name__}: {exc}).",
            flush=True,
        )
        return None

    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = (row.fdrs_import_key or "").strip()
        if not key:
            continue
        storage = (row.storage_path or "").strip()
        file_pending = bool(row.file_pending)
        file_migrated = bool(storage) and not file_pending
        if file_migrated:
            migration_status = MIGRATION_MIGRATED
        else:
            migration_status = MIGRATION_PENDING_DOWNLOAD
        out[key] = {
            "backoffice_doc_id": int(row.id),
            "in_backoffice": True,
            "file_pending": file_pending,
            "file_migrated": file_migrated,
            "storage_path": storage,
            "backoffice_source_url_http_status": row.source_url_http_status,
            "backoffice_is_public": bool(row.is_public),
            "backoffice_status": (
                row.status.value if hasattr(row.status, "value") else str(row.status or "")
            ),
            "migration_status": migration_status,
        }
    return out


def empty_migration_fields(*, available: bool) -> Dict[str, Any]:
    """Default migration columns when a catalog doc is not in Backoffice (or unknown)."""
    if not available:
        return {
            "fdrs_import_key": "",
            "in_backoffice": "",
            "file_migrated": "",
            "file_pending": "",
            "migration_status": MIGRATION_UNKNOWN,
            "backoffice_doc_id": "",
            "storage_path": "",
            "backoffice_source_url_http_status": "",
            "backoffice_is_public": "",
            "backoffice_status": "",
        }
    return {
        "fdrs_import_key": "",
        "in_backoffice": False,
        "file_migrated": False,
        "file_pending": "",
        "migration_status": MIGRATION_NOT_IN_BACKOFFICE,
        "backoffice_doc_id": "",
        "storage_path": "",
        "backoffice_source_url_http_status": "",
        "backoffice_is_public": "",
        "backoffice_status": "",
    }


def enrich_rows_with_backoffice_migration(
    rows: List[Dict[str, Any]],
    index: Optional[Dict[str, Dict[str, Any]]],
) -> Dict[str, int]:
    """Attach migration columns in-place. Returns migration counters."""
    available = index is not None
    index = index or {}
    migrated = 0
    pending = 0
    missing = 0
    for row in rows:
        key = document_import_key(
            {
                "don_code": row.get("don_code"),
                "year": row.get("year"),
                "document_typeId": row.get("document_type_id"),
                "name": row.get("name"),
            }
        )
        local = index.get(key) if available else None
        if local is None:
            fields = empty_migration_fields(available=available)
            fields["fdrs_import_key"] = key if available else ""
            row.update(fields)
            if available:
                missing += 1
            continue
        row.update(
            {
                "fdrs_import_key": key,
                "in_backoffice": True,
                "file_migrated": bool(local.get("file_migrated")),
                "file_pending": bool(local.get("file_pending")),
                "migration_status": local.get("migration_status") or MIGRATION_PENDING_DOWNLOAD,
                "backoffice_doc_id": local.get("backoffice_doc_id") or "",
                "storage_path": local.get("storage_path") or "",
                "backoffice_source_url_http_status": local.get("backoffice_source_url_http_status"),
                "backoffice_is_public": local.get("backoffice_is_public"),
                "backoffice_status": local.get("backoffice_status") or "",
            }
        )
        if row["file_migrated"]:
            migrated += 1
        else:
            pending += 1
    return {
        "file_migrated_count": migrated,
        "pending_download_count": pending,
        "not_in_backoffice_count": missing,
        "not_migrated_count": pending + missing,
        "migration_lookup_available": 1 if available else 0,
    }


def _probe_row(doc: Dict[str, Any]) -> Dict[str, Any]:
    url = (doc.get("url") or "").strip()
    status, detail = probe_url(url)
    fallback_url = ""
    fallback_http_status: Optional[int] = None
    if status in (403, 404):
        from fdrs_documents_sync import fdrs_alternate_urls

        for alt in fdrs_alternate_urls(url):
            fallback_url = alt
            fb_status, fb_detail = probe_url(alt)
            fallback_http_status = fb_status
            if fb_status in (200, 206):
                status, detail = fb_status, fb_detail
                break
    is_public = document_is_public(doc.get("ApprovalStatus"), doc.get("Public"))
    return {
        "don_code": doc.get("don_code") or "",
        "iso3": doc.get("iso3") or "",
        "year": doc.get("year"),
        "year_text": doc.get("YearText") or "",
        "document_type": doc.get("document_type") or "",
        "document_type_id": doc.get("document_typeId"),
        "name": doc.get("name") or "",
        "lang_code": doc.get("LangCode") or "",
        "approval_status": doc.get("ApprovalStatus") or "",
        "public": doc.get("Public"),
        "is_public": is_public,
        "modified_at": doc.get("ModifiedAt") or "",
        "url": url,
        "url_encoded": encode_document_url(url) if url else "",
        "fallback_url": fallback_url,
        "fallback_http_status": fallback_http_status,
        "http_status": status,
        "http_detail": detail,
        "downloadable": status in (200, 206),
    }


def ratio_pct(part: int, whole: int, *, digits: int = 1) -> float:
    if whole <= 0:
        return 0.0
    return round(100.0 * int(part) / int(whole), digits)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in ("true", "1", "yes")


def _http_status_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def row_is_probe_failure(row: Dict[str, Any]) -> bool:
    """True when a stored scan row should be retried after an IFRC URL fix.

    Downloadable (200/206) rows are left alone. Expected private 403s are also
    skipped — they are not endpoint defects. Public 403s, 404s, 5xx, and
    network errors are retried.
    """
    if _as_bool(row.get("downloadable")):
        return False
    if _http_status_int(row.get("http_status")) == 403 and not _as_bool(row.get("is_public")):
        return False
    return True


def stored_row_to_catalog_doc(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map a documents-sheet row back to the catalog shape ``_probe_row`` expects."""
    return {
        "don_code": row.get("don_code") or "",
        "iso3": row.get("iso3") or "",
        "year": row.get("year"),
        "YearText": row.get("year_text") if row.get("year_text") not in (None, "") else row.get("YearText") or "",
        "document_type": row.get("document_type") or "",
        "document_typeId": row.get("document_type_id") if row.get("document_type_id") not in (None, "") else row.get("document_typeId"),
        "name": row.get("name") or "",
        "LangCode": row.get("lang_code") if row.get("lang_code") not in (None, "") else row.get("LangCode") or "",
        "ApprovalStatus": row.get("approval_status") if row.get("approval_status") not in (None, "") else row.get("ApprovalStatus") or "",
        "Public": row.get("public") if row.get("public") not in (None, "") else row.get("Public"),
        "ModifiedAt": row.get("modified_at") if row.get("modified_at") not in (None, "") else row.get("ModifiedAt") or "",
        "url": (row.get("url") or "").strip(),
    }


def _cell_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def load_documents_sheet_rows(path: str) -> List[Dict[str, Any]]:
    import pandas as pd

    df = pd.read_excel(path, sheet_name="documents")
    rows: List[Dict[str, Any]] = []
    for rec in df.to_dict(orient="records"):
        rows.append({str(k): _cell_value(v) for k, v in rec.items()})
    return rows


def load_scan_year_from_workbook(path: str) -> Optional[int]:
    import pandas as pd

    try:
        meta = pd.read_excel(path, sheet_name="meta")
    except Exception:
        return None
    for rec in meta.to_dict(orient="records"):
        if str(rec.get("key") or "").strip() != "scan_year":
            continue
        try:
            return parse_scan_year(rec.get("value"))
        except ValueError:
            return None
    return None


def _probe_document_list(
    documents: List[Dict[str, Any]],
    *,
    workers: int,
    progress: Callable[[Dict[str, Any]], None],
    cancelled: Callable[[], bool],
    message: str,
) -> List[Dict[str, Any]]:
    total = len(documents)
    rows: List[Optional[Dict[str, Any]]] = [None] * total
    done = 0
    workers = max(1, min(int(workers), 64))
    progress({
        "stage": "probe",
        "message": message,
        "current": 0,
        "total": total,
        "percent": 5.0,
    })
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {pool.submit(_probe_row, doc): i for i, doc in enumerate(documents)}
        for fut in as_completed(futures):
            if cancelled():
                raise FdrsDocumentScanCancelled()
            idx = futures[fut]
            rows[idx] = fut.result()
            done += 1
            if done == 1 or done % 50 == 0 or done == total:
                pct = 5.0 + (90.0 * done / total) if total else 95.0
                progress({
                    "stage": "probe",
                    "message": f"Probed {done}/{total} document URLs",
                    "current": done,
                    "total": total,
                    "percent": pct,
                })
                if done == 1 or done % 250 == 0 or done == total:
                    print(f"Probed {done}/{total}...", flush=True)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    if cancelled():
        raise FdrsDocumentScanCancelled()
    assert all(r is not None for r in rows)
    return list(rows)  # type: ignore[arg-type]


def execute_document_url_status_scan(
    *,
    output_path: str,
    api_key: Optional[str] = None,
    base_url: str = DEFAULT_BASE,
    workers: int = 20,
    limit: Optional[int] = None,
    year: Optional[int] = None,
    retry_failed: bool = False,
    source_path: Optional[str] = None,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """Probe the FDRS document catalog and write the status Excel.

    *year* limits the probe to documents for that catalog / YearText year.
    ``None`` scans every document. *retry_failed* re-probes unexpected URL
    failures from *source_path* (the previous scan workbook) and merges them
    back. Returns a stats dict (total_documents, downloadable_count, …).
    Raises ``FdrsDocumentScanCancelled`` when *cancel_check* returns True.
    """
    import pandas as pd

    def _progress(payload: Dict[str, Any]) -> None:
        if progress_cb:
            progress_cb(payload)

    def _cancelled() -> bool:
        return bool(cancel_check and cancel_check())

    if _cancelled():
        raise FdrsDocumentScanCancelled()

    scan_year = parse_scan_year(year)
    retry_attempted = 0
    retry_recovered = 0
    workers = max(1, min(int(workers), 64))

    if retry_failed:
        src = (source_path or "").strip()
        if not src or not os.path.isfile(src):
            raise RuntimeError("No previous document scan to retry.")
        _progress({
            "stage": "load_previous",
            "message": "Loading previous scan to retry failed URLs...",
            "percent": 2.0,
        })
        existing_rows = load_documents_sheet_rows(src)
        if not existing_rows:
            raise RuntimeError("Previous document scan has no rows to retry.")
        requested_year = scan_year
        if scan_year is None:
            scan_year = load_scan_year_from_workbook(src)
        failed_idxs = [
            i for i, row in enumerate(existing_rows)
            if row_is_probe_failure(row)
        ]
        if requested_year is not None:
            failed_idxs = [
                i for i in failed_idxs
                if document_matches_scan_year(
                    {
                        "year": existing_rows[i].get("year"),
                        "YearText": existing_rows[i].get("year_text")
                        or existing_rows[i].get("YearText")
                        or "",
                    },
                    requested_year,
                )
            ]
        if limit is not None:
            failed_idxs = failed_idxs[: int(limit)]
        retry_attempted = len(failed_idxs)
        if retry_attempted == 0:
            raise RuntimeError("No failed document URLs to retry.")
        retry_msg = f"Retrying {retry_attempted} failed document URLs..."
        if scan_year is not None:
            retry_msg = f"Retrying {retry_attempted} failed document URLs (year {scan_year})..."
        probed = _probe_document_list(
            [stored_row_to_catalog_doc(existing_rows[i]) for i in failed_idxs],
            workers=workers,
            progress=_progress,
            cancelled=_cancelled,
            message=retry_msg,
        )
        typed_rows = list(existing_rows)
        for idx, new_row in zip(failed_idxs, probed):
            was_ok = _as_bool(existing_rows[idx].get("downloadable"))
            typed_rows[idx] = new_row
            if (not was_ok) and _as_bool(new_row.get("downloadable")):
                retry_recovered += 1
    else:
        key = _load_api_key(api_key)
        catalog_msg = "Fetching FDRS document catalog..."
        if scan_year is not None:
            catalog_msg = f"Fetching FDRS document catalog (year {scan_year})..."
        _progress({"stage": "fetch_catalog", "message": catalog_msg, "percent": 2.0})
        documents = fetch_fdrs_documents(base_url, key)
        catalog_total = len(documents)
        documents = filter_documents_for_scan_year(documents, scan_year)
        if scan_year is not None:
            _progress({
                "stage": "filter_year",
                "message": (
                    f"Year {scan_year}: {len(documents)} of {catalog_total} catalog documents"
                ),
                "percent": 4.0,
            })
        if limit is not None:
            documents = documents[: int(limit)]

        total = len(documents)
        if total == 0:
            if scan_year is not None:
                raise RuntimeError(f"No FDRS documents found for year {scan_year}.")
            raise RuntimeError("No documents returned from FDRS API.")

        probe_msg = f"Probing {total} document URLs..."
        if scan_year is not None:
            probe_msg = f"Probing {total} document URLs (year {scan_year})..."
        typed_rows = _probe_document_list(
            documents,
            workers=workers,
            progress=_progress,
            cancelled=_cancelled,
            message=probe_msg,
        )

    if _cancelled():
        raise FdrsDocumentScanCancelled()

    total = len(typed_rows)
    for row in typed_rows:
        row["is_public"] = _as_bool(row.get("is_public"))
        row["downloadable"] = _as_bool(row.get("downloadable"))
    _progress({
        "stage": "migration_lookup",
        "message": "Checking Backoffice migration status...",
        "percent": 94.0,
        "current": total,
        "total": total,
    })
    migration_index = load_backoffice_migration_index()
    migration_counts = enrich_rows_with_backoffice_migration(typed_rows, migration_index)

    df = pd.DataFrame(typed_rows)

    def _pct(part: int, whole: int) -> str:
        return f"{ratio_pct(part, whole):.1f}%"

    summary = df["http_status"].value_counts().sort_index()
    print("\nStatus summary:")
    for code, count in summary.items():
        count_i = int(count)
        extra = ""
        if int(code) == 403:
            blocked = df[df["http_status"] == 403]
            pub = int(blocked["is_public"].sum())
            priv = int((~blocked["is_public"]).sum())
            extra = (
                f"  (public: {pub} {_pct(pub, count_i)} unexpected, "
                f"private: {priv} {_pct(priv, count_i)} expected)"
            )
        print(f"  {code}: {count_i} ({_pct(count_i, total)}){extra}")
    ok = int(df["downloadable"].sum())
    print(f"Downloadable (200/206): {ok}/{total} ({100.0 * ok / total:.1f}%)")
    fallback_tried = int(df["fallback_url"].fillna("").astype(str).str.len().gt(0).sum())
    fallback_ok = int(
        (
            df["fallback_url"].fillna("").astype(str).str.len().gt(0)
            & df["fallback_http_status"].isin([200, 206])
        ).sum()
    )
    print(f"Suffix fallback tried: {fallback_tried}; recovered: {fallback_ok}")
    if migration_counts.get("migration_lookup_available"):
        print(
            "Backoffice migration: "
            f"migrated={migration_counts['file_migrated_count']}, "
            f"pending_download={migration_counts['pending_download_count']}, "
            f"not_in_backoffice={migration_counts['not_in_backoffice_count']} "
            f"(not migrated={migration_counts['not_migrated_count']}/{total}, "
            f"migrated={ratio_pct(int(migration_counts['file_migrated_count']), total):.1f}%)",
            flush=True,
        )
    else:
        print("Backoffice migration: skipped (no Flask app context).", flush=True)

    if _cancelled():
        raise FdrsDocumentScanCancelled()

    _progress({"stage": "write_excel", "message": "Writing Excel...", "percent": 96.0, "current": total, "total": total})
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    scanned_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    migrated_n = int(migration_counts.get("file_migrated_count") or 0)
    migrated_pct = ratio_pct(migrated_n, total)
    downloadable_pct = ratio_pct(ok, total)
    failed_count = sum(1 for row in typed_rows if row_is_probe_failure(row))

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.sort_values(["year", "iso3", "document_type", "name"], na_position="last").to_excel(
            writer, sheet_name="documents", index=False
        )
        summary_rows = []
        for code, count in summary.items():
            count_i = int(count)
            sub = df[df["http_status"] == code]
            pub = int(sub["is_public"].sum())
            priv = int((~sub["is_public"]).sum())
            summary_rows.append(
                {
                    "http_status": str(code),
                    "count": count_i,
                    "pct_of_total": ratio_pct(count_i, total),
                    "public": pub,
                    "public_pct": round(100.0 * pub / count_i, 1) if count_i else 0.0,
                    "private": priv,
                    "private_pct": round(100.0 * priv / count_i, 1) if count_i else 0.0,
                }
            )
        if migration_counts.get("migration_lookup_available"):
            for status_key, count_key in (
                (MIGRATION_MIGRATED, "file_migrated_count"),
                (MIGRATION_PENDING_DOWNLOAD, "pending_download_count"),
                (MIGRATION_NOT_IN_BACKOFFICE, "not_in_backoffice_count"),
            ):
                count_i = int(migration_counts.get(count_key) or 0)
                summary_rows.append(
                    {
                        "http_status": f"migration:{status_key}",
                        "count": count_i,
                        "pct_of_total": ratio_pct(count_i, total),
                        "public": "",
                        "public_pct": "",
                        "private": "",
                        "private_pct": "",
                    }
                )
        summary_rows.append(
            {
                "http_status": "probe:downloadable",
                "count": ok,
                "pct_of_total": downloadable_pct,
                "public": "",
                "public_pct": "",
                "private": "",
                "private_pct": "",
            }
        )
        summary_rows.append(
            {
                "http_status": "probe:failed",
                "count": failed_count,
                "pct_of_total": ratio_pct(failed_count, total),
                "public": "",
                "public_pct": "",
                "private": "",
                "private_pct": "",
            }
        )
        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        blocked = df[df["http_status"] == 403]
        n403 = int(len(blocked))
        pub403 = int(blocked["is_public"].sum())
        priv403 = int((~blocked["is_public"]).sum())
        meta_rows = [
            {"key": "scanned_at_utc", "value": scanned_at},
            {"key": "scan_year", "value": scan_year if scan_year is not None else "all"},
            {"key": "retry_failed", "value": bool(retry_failed)},
            {"key": "retry_attempted", "value": retry_attempted},
            {"key": "retry_recovered", "value": retry_recovered},
            {"key": "total_documents", "value": total},
            {"key": "downloadable_count", "value": ok},
            {"key": "downloadable_pct", "value": downloadable_pct},
            {"key": "failed_count", "value": failed_count},
            {"key": "file_migrated_count", "value": migrated_n},
            {"key": "migrated_pct", "value": migrated_pct},
            {"key": "pending_download_count", "value": migration_counts.get("pending_download_count", "")},
            {"key": "not_in_backoffice_count", "value": migration_counts.get("not_in_backoffice_count", "")},
            {"key": "not_migrated_count", "value": migration_counts.get("not_migrated_count", "")},
            {
                "key": "migration_lookup_available",
                "value": bool(migration_counts.get("migration_lookup_available")),
            },
            {"key": "http_403_public_unexpected", "value": pub403},
            {"key": "http_403_public_unexpected_pct", "value": ratio_pct(pub403, n403)},
            {"key": "http_403_private_expected", "value": priv403},
            {"key": "http_403_private_expected_pct", "value": ratio_pct(priv403, n403)},
            {"key": "suffix_fallback_tried", "value": fallback_tried},
            {"key": "suffix_fallback_recovered", "value": fallback_ok},
            {"key": "workers", "value": workers},
            {"key": "base_url", "value": base_url},
        ]
        meta_df = pd.DataFrame(meta_rows)
        meta_df.to_excel(writer, sheet_name="meta", index=False)

    print(f"\nWrote {output_path}")
    years: List[int] = []
    for y in df["year"].dropna().tolist():
        try:
            years.append(int(y))
        except (TypeError, ValueError):
            continue
    years = sorted(set(years), reverse=True)
    document_types = sorted({str(t).strip() for t in df["document_type"].fillna("").tolist() if str(t).strip()})
    http_statuses = [str(c) for c in summary.index.tolist()]
    migration_statuses = sorted(
        {
            str(s).strip()
            for s in df["migration_status"].fillna("").tolist()
            if str(s).strip()
        }
    )
    stats = {
        "scanned_at_utc": scanned_at,
        "scan_year": scan_year,
        "retry_failed": bool(retry_failed),
        "retry_attempted": retry_attempted,
        "retry_recovered": retry_recovered,
        "total_documents": total,
        "downloadable_count": ok,
        "downloadable_pct": downloadable_pct,
        "failed_count": failed_count,
        "file_migrated_count": migrated_n,
        "migrated_pct": migrated_pct,
        "pending_download_count": int(migration_counts.get("pending_download_count") or 0),
        "not_in_backoffice_count": int(migration_counts.get("not_in_backoffice_count") or 0),
        "not_migrated_count": int(migration_counts.get("not_migrated_count") or 0),
        "migration_lookup_available": bool(migration_counts.get("migration_lookup_available")),
        "http_403_public_unexpected": pub403,
        "http_403_private_expected": priv403,
        "suffix_fallback_tried": fallback_tried,
        "suffix_fallback_recovered": fallback_ok,
        "workers": workers,
        "base_url": base_url,
        "limit": limit,
        "year": scan_year,
        "filter_options": {
            "years": years,
            "document_types": document_types,
            "http_statuses": http_statuses,
            "migration_statuses": migration_statuses,
        },
    }
    _progress({"stage": "complete", "message": "Completed", "percent": 100.0, "current": total, "total": total, "stats": stats})
    return stats


def export_url_status_excel(
    *,
    output_path: str,
    api_key: Optional[str] = None,
    base_url: str = DEFAULT_BASE,
    workers: int = 20,
    limit: Optional[int] = None,
    year: Optional[int] = None,
    retry_failed: bool = False,
    source_path: Optional[str] = None,
) -> str:
    execute_document_url_status_scan(
        output_path=output_path,
        api_key=api_key,
        base_url=base_url,
        workers=workers,
        limit=limit,
        year=year,
        retry_failed=retry_failed,
        source_path=source_path,
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export FDRS document URL HTTP status to Excel.",
        epilog=(
            "Standalone:  python export_fdrs_document_url_status.py --api-key YOUR_KEY\n"
            "Backoffice:  python plugins/fdrs/scripts/export_fdrs_document_url_status.py"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help="Output .xlsx path")
    parser.add_argument("--api-key", default=None, help="FDRS data API key (default: env / .env)")
    parser.add_argument("--base-url", default=DEFAULT_BASE, help="FDRS data API base URL")
    parser.add_argument("--workers", type=int, default=20, help="Concurrent probe workers")
    parser.add_argument("--limit", type=int, default=None, help="Probe only first N documents (testing)")
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Probe only documents for this catalog year (default: all years)",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Re-probe unexpected URL failures from a previous workbook (see --source)",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Previous .xlsx to retry (default: --output path)",
    )
    args = parser.parse_args()
    try:
        export_url_status_excel(
            output_path=args.output,
            api_key=args.api_key,
            base_url=args.base_url,
            workers=args.workers,
            limit=args.limit,
            year=args.year,
            retry_failed=args.retry_failed,
            source_path=args.source or (args.output if args.retry_failed else None),
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
