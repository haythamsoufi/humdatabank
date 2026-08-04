"""
FDRS documents API → SubmittedDocument import (metadata + file bytes when URL is reachable).

GET https://data-api.ifrc.org/api/documents?apiKey=...&showunpublished=true&force=true[&year=YYYY]

Public document URLs must be percent-encoded (spaces in paths). Use GET (HEAD is unreliable).
HTTP 200/206 → save to submission storage and clear ``file_pending``.
HTTP 403/404 → keep ``file_pending=True`` (retried on later syncs).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from io import BytesIO
from typing import Any, Callable, Dict, List, Optional, Tuple

from werkzeug.datastructures import FileStorage

from fdrs_sync_constants import (
    FDRS_DOCUMENT_APPROVAL_OK,
    FDRS_DOCUMENT_PUBLIC_OK,
    FDRS_DOCUMENT_TYPE_TO_CONFIG_LABEL,
    FDRS_DOCUMENT_TYPE_TO_ITEM,
    FdrsSyncCancelled,
    fdrs_document_approval_rank,
    fdrs_document_is_public_visibility,
    fdrs_document_status_from_approval,
)

logger = logging.getLogger(__name__)

DEFAULT_DOCUMENTS_PATH = "/api/documents"


def _format_documents_upsert_progress(index: int, total: int, stats: Dict[str, int]) -> str:
    """Human-readable progress while upserting FDRS document metadata and optional file bytes."""
    return (
        f"FDRS documents: record {index} of {total} "
        f"(files saved this run: {stats['downloaded']}, "
        f"awaiting IFRC file download: {stats['pending']})"
    )


def _format_documents_done_message(doc_stats: Dict[str, Any]) -> str:
    inserted = doc_stats.get("inserted", 0)
    updated = doc_stats.get("updated", 0)
    downloaded = doc_stats.get("downloaded", 0)
    pending = doc_stats.get("pending", 0)
    download_errors = doc_stats.get("download_errors", 0)
    status_approved = doc_stats.get("status_approved", 0)
    status_pending = doc_stats.get("status_pending", 0)
    status_rejected = doc_stats.get("status_rejected", 0)
    return (
        f"FDRS documents complete: {inserted} inserted, {updated} updated; "
        f"status approved={status_approved} pending={status_pending} rejected={status_rejected}; "
        f"files saved: {downloaded}, awaiting IFRC file download: {pending}, "
        f"download errors: {download_errors}"
    )
_FDRS_DOC_USER_AGENT = "HumanitarianDatabank-FDRS-sync/1.0"
_DEFAULT_DOWNLOAD_TIMEOUT = 120
_PROGRESS_REPORT_EVERY = 10
_YEAR_IN_TEXT_RE = re.compile(r"\b(20\d{2})\b")


def encode_fdrs_document_url(url: str) -> str:
    """Percent-encode FDRS document URL paths (API returns unencoded spaces)."""
    parts = urllib.parse.urlsplit((url or "").strip())
    path = urllib.parse.quote(parts.path, safe="/")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def fetch_fdrs_document_bytes(
    url: str,
    *,
    timeout: int = _DEFAULT_DOWNLOAD_TIMEOUT,
    dry_run: bool = False,
) -> Tuple[Optional[bytes], int]:
    """
    Download FDRS document content via GET.

    Returns ``(data, http_status)``. *data* is set for 200/206 when not *dry_run*
    (dry_run uses a Range probe and returns ``(None, status)``).
    """
    raw = (url or "").strip()
    if not raw:
        return None, 0
    enc = encode_fdrs_document_url(raw)
    headers = {"User-Agent": _FDRS_DOC_USER_AGENT}
    if dry_run:
        headers["Range"] = "bytes=0-0"
    req = urllib.request.Request(enc, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            if status in (200, 206):
                if dry_run:
                    return None, status
                return resp.read(), status
            return None, status
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception as e:
        logger.warning("FDRS document download failed for %s: %s", raw[:120], e)
        return None, -1


def _save_fdrs_document_bytes(
    *,
    data: bytes,
    filename: str,
    assignment_entity_status_id: int,
    entity_type: str,
    entity_id: int,
) -> str:
    """Persist downloaded bytes using the same layout as manual submission uploads."""
    from app.utils.file_paths import save_submission_document

    file_storage = FileStorage(stream=BytesIO(data), filename=filename)
    return save_submission_document(
        file_storage=file_storage,
        assignment_id=assignment_entity_status_id,
        filename=filename,
        is_public=False,
        entity_type=entity_type,
        entity_id=entity_id,
    )


def _fdrs_local_file_exists(storage_path: Optional[str]) -> bool:
    """True when ``storage_path`` points at a file in the active storage provider."""
    sp = (storage_path or "").strip()
    if not sp:
        return False
    from app.services.platform import storage_service as storage

    return storage.submitted_source_exists(sp)


def _should_attempt_download(
    row: Dict[str, Any],
    existing: Optional[Any],
) -> bool:
    if not row.get("is_public"):
        return False
    source_url = (row.get("source_url") or "").strip()
    if not source_url:
        return False
    if existing is None:
        return True
    if existing.file_pending or not existing.storage_path:
        return True
    if not _fdrs_local_file_exists(existing.storage_path):
        return True
    if (existing.source_url or "").strip() != source_url:
        return True
    return False


def _resolve_download_outcome(
    existing: Optional[Any],
    http_status: int,
    data: Optional[bytes],
) -> Tuple[Optional[bytes], bool]:
    """
    Return ``(bytes_to_save, file_pending)``.

    Keeps an already-stored file when a re-fetch returns 403/404.
    """
    if http_status in (200, 206) and data:
        return data, False
    if (
        existing is not None
        and existing.storage_path
        and not existing.file_pending
        and _fdrs_local_file_exists(existing.storage_path)
    ):
        return None, False
    return None, True


def _parse_year_text_bounds(year_text: Any) -> Tuple[Optional[int], Optional[int]]:
    """Return inclusive (start, end) calendar years parsed from FDRS YearText."""
    if year_text is None:
        return None, None
    nums = [int(y) for y in _YEAR_IN_TEXT_RE.findall(str(year_text))]
    if not nums:
        return None, None
    return min(nums), max(nums)


def _resolve_document_assignment_year(
    doc: Dict[str, Any],
    iso3: str,
    assignment_by_key: Dict[Tuple[str, str], int],
) -> Optional[str]:
    """
    Map a FDRS document row to an assignment period_name (reporting year string).

    YearText ranges such as ``2021-2024`` are indexed under ``year=2021`` in the API
    but belong on the latest assignment year in the range (here 2024).
    """
    start, end = _parse_year_text_bounds(doc.get("YearText"))
    if end is not None:
        floor = start if start is not None else end
        for candidate in range(end, floor - 1, -1):
            year_str = str(candidate)
            if (year_str, iso3) in assignment_by_key:
                return year_str
    raw_year = doc.get("year")
    if raw_year is not None:
        year_str = str(raw_year).strip()
        if year_str and (year_str, iso3) in assignment_by_key:
            return year_str
    return None


def fetch_fdrs_documents_api(
    base_url: str,
    api_key: str,
    *,
    years: Optional[List[int]] = None,
    show_unpublished: bool = True,
) -> List[Dict[str, Any]]:
    """
    Return flat document records with don_code, iso3, and normalized metadata.

    The API ``year`` query param only matches the numeric ``year`` field on each
    document, not YearText ranges (e.g. Bahrain annual report ``2021-2024`` has
    ``year=2021``). We always fetch the full catalog; ``build_document_import_plan``
    filters by resolved assignment year when ``sync_years`` is set.
    """
    from fdrs_data_fetcher import fetch_country_map

    base = (base_url or "").strip().rstrip("/")
    country_map = fetch_country_map(base_url=base, api_key=api_key)
    don_to_iso = {don: iso for don, iso in country_map.items() if don and iso}

    del years  # reserved; filtering happens in build_document_import_plan
    flat: List[Dict[str, Any]] = []

    params = {
        "apiKey": api_key,
        "showunpublished": "true" if show_unpublished else "false",
        "force": "true",
    }
    qs = urllib.parse.urlencode(params)
    url = f"{base}{DEFAULT_DOCUMENTS_PATH}?{qs}"
    with urllib.request.urlopen(url, timeout=180) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not isinstance(payload, list):
        logger.warning("Unexpected documents API payload type: %s", type(payload))
        return flat
    for ns_block in payload:
        don_code = (ns_block.get("code") or "").strip()
        iso3 = don_to_iso.get(don_code, "")
        for doc in ns_block.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            rec = dict(doc)
            rec["don_code"] = don_code
            rec["iso3"] = iso3
            flat.append(rec)
    return flat


def _doc_score(doc: Dict[str, Any]) -> Tuple[int, str]:
    """Higher is better for dedupe within (iso3, year, document_type)."""
    approval = (doc.get("ApprovalStatus") or "").strip()
    public = doc.get("Public")
    try:
        public_i = int(public) if public is not None else -1
    except (TypeError, ValueError):
        public_i = -1
    approval_rank = fdrs_document_approval_rank(approval)
    public_rank = 2 if public_i == 1 else 1 if public_i in FDRS_DOCUMENT_PUBLIC_OK else 0
    lang_rank = 1 if (doc.get("LangCode") or "").strip().lower() == "en" else 0
    modified = (doc.get("ModifiedAt") or "")[:19]
    return (approval_rank, public_rank, lang_rank, modified)


def _fdrs_document_import_key(doc: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            (doc.get("don_code") or "").strip(),
            str(doc.get("year") or ""),
            str(doc.get("document_typeId") or ""),
            (doc.get("name") or "").strip(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def build_document_import_plan(
    documents: List[Dict[str, Any]],
    assignment_rows: List[Dict[str, Any]],
    *,
    template_id: int = 21,
    sync_years: Optional[List[int]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Select importable FDRS documents and map to assignment + form_item_id.
    Returns (plan_rows, summary).
    """
    del template_id  # reserved for future template-specific rules
    assignment_by_key: Dict[Tuple[str, str], int] = {
        (r["period_name"], r["iso3"]): int(r["assignment_entity_status_id"]) for r in assignment_rows
    }
    sync_year_set = {int(y) for y in sync_years} if sync_years else None

    summary: Dict[str, Any] = {
        "total_api_docs": len(documents),
        "skipped_no_iso3": 0,
        "skipped_no_assignment": 0,
        "skipped_unmapped_type": 0,
        "skipped_approval": 0,
        "skipped_duplicate": 0,
        "skipped_sync_year": 0,
        "planned": 0,
        "status_approved": 0,
        "status_pending": 0,
        "status_rejected": 0,
    }

    # Best doc per (iso3, reporting_year, document_type)
    best: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for doc in documents:
        doc_type = (doc.get("document_type") or "").strip()
        if doc_type not in FDRS_DOCUMENT_TYPE_TO_ITEM:
            summary["skipped_unmapped_type"] += 1
            continue
        approval = (doc.get("ApprovalStatus") or "").strip()
        if approval and approval not in FDRS_DOCUMENT_APPROVAL_OK:
            summary["skipped_approval"] += 1
            continue
        try:
            public_i = int(doc.get("Public")) if doc.get("Public") is not None else None
        except (TypeError, ValueError):
            public_i = None
        if public_i is not None and public_i not in FDRS_DOCUMENT_PUBLIC_OK:
            summary["skipped_approval"] += 1
            continue

        iso3 = (doc.get("iso3") or "").strip()
        if not iso3:
            summary["skipped_no_iso3"] += 1
            continue
        year_str = _resolve_document_assignment_year(doc, iso3, assignment_by_key)
        if not year_str:
            summary["skipped_no_assignment"] += 1
            continue
        if sync_year_set is not None and int(year_str) not in sync_year_set:
            summary["skipped_sync_year"] += 1
            continue

        key = (iso3, year_str, doc_type)
        prev = best.get(key)
        if prev is None or _doc_score(doc) > _doc_score(prev):
            best[key] = doc

    plan: List[Dict[str, Any]] = []
    seen_keys: set = set()
    for (iso3, year_str, doc_type), doc in sorted(best.items()):
        import_key = _fdrs_document_import_key(doc)
        if import_key in seen_keys:
            summary["skipped_duplicate"] += 1
            continue
        seen_keys.add(import_key)
        aes_id = assignment_by_key[(year_str, iso3)]
        form_item_id = FDRS_DOCUMENT_TYPE_TO_ITEM[doc_type]
        period = (doc.get("YearText") or year_str).strip()
        lang = (doc.get("LangCode") or "en").strip().lower() or "en"
        approval_status = (doc.get("ApprovalStatus") or "").strip()
        is_public = fdrs_document_is_public_visibility(
            approval_status,
            public_code=doc.get("Public"),
        )
        doc_status = fdrs_document_status_from_approval(approval_status)
        plan.append(
            {
                "fdrs_import_key": import_key,
                "assignment_entity_status_id": aes_id,
                "form_item_id": form_item_id,
                "filename": (doc.get("name") or "document.pdf").strip(),
                "source_url": (doc.get("url") or "").strip(),
                "thumbnail_url": (doc.get("thumbnail") or "").strip() or None,
                "language": lang,
                "document_type": FDRS_DOCUMENT_TYPE_TO_CONFIG_LABEL.get(doc_type, doc_type),
                "period": period,
                "is_public": is_public,
                "iso3": iso3,
                "year": year_str,
                "fdrs_document_type": doc_type,
                "approval_status": approval_status,
                "status": doc_status,
                "modified_at": doc.get("ModifiedAt"),
            }
        )
        if doc_status == "approved":
            summary["status_approved"] += 1
        elif doc_status == "rejected":
            summary["status_rejected"] += 1
        else:
            summary["status_pending"] += 1
    summary["planned"] = len(plan)
    return plan, summary


def _parse_fdrs_modified_at(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s[:26])
    except ValueError:
        return None


def _check_cancel(cancel_check: Optional[Callable[[], bool]]) -> None:
    if cancel_check and cancel_check():
        raise FdrsSyncCancelled()


def _document_progress_percent(
    index: int,
    total: int,
    *,
    progress_start_pct: float,
    progress_end_pct: float,
) -> float:
    if total <= 0:
        return progress_end_pct
    span = max(progress_end_pct - progress_start_pct, 0.0)
    return progress_start_pct + (span * (index / total))


def upsert_fdrs_document_metadata(
    plan_rows: List[Dict[str, Any]],
    *,
    uploaded_by_user_id: int,
    dry_run: bool = False,
    batch_size: int = 500,
    download_timeout: int = _DEFAULT_DOWNLOAD_TIMEOUT,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    progress_start_pct: float = 82.0,
    progress_end_pct: float = 94.0,
) -> Dict[str, int]:
    """Insert or update SubmittedDocument rows; download file bytes when the FDRS URL responds 200/206."""
    from app.extensions import db
    from app.models.assignments import AssignmentEntityStatus
    from app.models.documents import SubmittedDocument
    from app.models.enums import DocumentStatusValue

    stats = {
        "loaded": len(plan_rows),
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "downloaded": 0,
        "pending": 0,
        "download_errors": 0,
        "status_approved": 0,
        "status_pending": 0,
        "status_rejected": 0,
    }
    if not plan_rows:
        return stats

    total_rows = len(plan_rows)

    def _emit_progress(index: int, *, message: str) -> None:
        if not progress_cb and not cancel_check:
            return
        _check_cancel(cancel_check)
        if not progress_cb:
            return
        pct = _document_progress_percent(
            index,
            total_rows,
            progress_start_pct=progress_start_pct,
            progress_end_pct=progress_end_pct,
        )
        try:
            progress_cb(
                {
                    "stage": "documents_upsert",
                    "message": message,
                    "current": index,
                    "total": total_rows,
                    "percent": pct,
                    "stats": dict(stats),
                }
            )
        except FdrsSyncCancelled:
            raise
        except Exception as e:
            logger.debug("documents upsert progress_cb failed: %s", e)

    _emit_progress(
        0,
        message=f"Starting FDRS document sync ({total_rows} records from IFRC API)...",
    )

    keys = [r["fdrs_import_key"] for r in plan_rows if r.get("fdrs_import_key")]
    existing_by_key: Dict[str, SubmittedDocument] = {}
    if keys:
        for doc in SubmittedDocument.query.filter(SubmittedDocument.fdrs_import_key.in_(keys)).all():
            if doc.fdrs_import_key:
                existing_by_key[doc.fdrs_import_key] = doc

    aes_ids = {
        int(r["assignment_entity_status_id"])
        for r in plan_rows
        if r.get("assignment_entity_status_id") is not None
    }
    aes_by_id: Dict[int, AssignmentEntityStatus] = {}
    if aes_ids:
        for aes in AssignmentEntityStatus.query.filter(AssignmentEntityStatus.id.in_(aes_ids)).all():
            aes_by_id[aes.id] = aes

    for i, row in enumerate(plan_rows, start=1):
        _check_cancel(cancel_check)
        import_key = row.get("fdrs_import_key")
        if not import_key:
            stats["skipped"] += 1
            continue
        try:
            existing = existing_by_key.get(import_key)
            modified_at = _parse_fdrs_modified_at(row.get("modified_at"))
            from app.utils.datetime_helpers import utcnow

            uploaded_at = modified_at or utcnow()
            doc_status = DocumentStatusValue.normalize(
                row.get("status")
                or fdrs_document_status_from_approval(row.get("approval_status"))
            )
            if doc_status == DocumentStatusValue.approved:
                stats["status_approved"] += 1
            elif doc_status == DocumentStatusValue.rejected:
                stats["status_rejected"] += 1
            else:
                stats["status_pending"] += 1

            storage_path = existing.storage_path if existing else None
            file_pending = True
            source_url = (row.get("source_url") or "").strip()
            is_public_doc = bool(row.get("is_public"))

            if not is_public_doc:
                file_pending = False
                if existing and existing.storage_path and _fdrs_local_file_exists(existing.storage_path):
                    storage_path = existing.storage_path
                else:
                    storage_path = None
            elif not source_url:
                if existing and existing.storage_path and not existing.file_pending:
                    file_pending = False
            elif _should_attempt_download(row, existing):
                _check_cancel(cancel_check)
                data, download_status = fetch_fdrs_document_bytes(
                    source_url,
                    timeout=download_timeout,
                    dry_run=dry_run,
                )
                save_bytes, file_pending = _resolve_download_outcome(existing, download_status, data)
                if save_bytes and not dry_run:
                    aes = aes_by_id.get(int(row["assignment_entity_status_id"]))
                    if aes is None:
                        stats["download_errors"] += 1
                        logger.error(
                            "FDRS document missing assignment_entity_status_id=%s for import_key=%s",
                            row.get("assignment_entity_status_id"),
                            import_key,
                        )
                        file_pending = True
                        storage_path = existing.storage_path if existing else None
                    else:
                        storage_path = _save_fdrs_document_bytes(
                            data=save_bytes,
                            filename=row["filename"],
                            assignment_entity_status_id=aes.id,
                            entity_type=aes.entity_type,
                            entity_id=aes.entity_id,
                        )
                        stats["downloaded"] += 1
                elif dry_run and download_status in (200, 206):
                    stats["downloaded"] += 1
                elif download_status in (403, 404):
                    stats["pending"] += 1
                    if existing and _fdrs_local_file_exists(existing.storage_path):
                        storage_path = existing.storage_path
                    else:
                        storage_path = None
                elif download_status not in (200, 206):
                    stats["download_errors"] += 1
                    if existing and _fdrs_local_file_exists(existing.storage_path):
                        storage_path = existing.storage_path
                    else:
                        storage_path = None
                else:
                    stats["pending"] += 1
                    if existing and _fdrs_local_file_exists(existing.storage_path):
                        storage_path = existing.storage_path
                    else:
                        storage_path = None
            elif existing is not None:
                if existing.storage_path and _fdrs_local_file_exists(existing.storage_path):
                    file_pending = False
                    storage_path = existing.storage_path
                else:
                    file_pending = True
                    storage_path = None

            if dry_run:
                if existing:
                    stats["updated"] += 1
                else:
                    stats["inserted"] += 1
                continue

            if existing:
                existing.filename = row["filename"]
                existing.source_url = row.get("source_url")
                existing.thumbnail_source_url = row.get("thumbnail_url")
                existing.language = row.get("language")
                existing.document_type = row.get("document_type")
                existing.period = row.get("period")
                existing.is_public = bool(row.get("is_public"))
                existing.status = doc_status
                existing.file_pending = file_pending
                existing.storage_path = storage_path
                if modified_at:
                    existing.uploaded_at = modified_at
                db.session.add(existing)
                stats["updated"] += 1
            else:
                entry = SubmittedDocument(
                    assignment_entity_status_id=int(row["assignment_entity_status_id"]),
                    form_item_id=int(row["form_item_id"]),
                    filename=row["filename"],
                    storage_path=storage_path,
                    source_url=row.get("source_url"),
                    thumbnail_source_url=row.get("thumbnail_url"),
                    uploaded_at=uploaded_at,
                    uploaded_by_user_id=uploaded_by_user_id,
                    language=row.get("language"),
                    document_type=row.get("document_type"),
                    period=row.get("period"),
                    is_public=bool(row.get("is_public")),
                    fdrs_import_key=import_key,
                    file_pending=file_pending,
                    status=doc_status,
                )
                db.session.add(entry)
                existing_by_key[import_key] = entry
                stats["inserted"] += 1

            if batch_size and i % batch_size == 0:
                db.session.commit()

            if i == 1 or i % _PROGRESS_REPORT_EVERY == 0 or i == total_rows:
                _emit_progress(
                    i,
                    message=_format_documents_upsert_progress(i, total_rows, stats),
                )
        except FdrsSyncCancelled:
            raise
        except Exception as e:
            stats["errors"] += 1
            logger.error("FDRS document row error: %s", e)

    if not dry_run and (stats["inserted"] + stats["updated"]) > 0:
        db.session.commit()
    return stats


def run_fdrs_documents_sync(
    *,
    base_url: str,
    api_key: str,
    assignment_rows: List[Dict[str, Any]],
    years: Optional[List[int]] = None,
    uploaded_by_user_id: int,
    dry_run: bool = False,
    batch_size: int = 500,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    progress_start_pct: float = 82.0,
    progress_end_pct: float = 94.0,
) -> Dict[str, Any]:
    def _progress(**kwargs: Any) -> None:
        _check_cancel(cancel_check)
        if not progress_cb:
            return
        try:
            progress_cb(kwargs)
        except FdrsSyncCancelled:
            raise
        except Exception as e:
            logger.debug("documents progress_cb failed: %s", e)

    fetch_pct = progress_start_pct
    _progress(
        stage="fetch_documents",
        message="Fetching FDRS document list from IFRC API...",
        percent=fetch_pct,
        current=0,
        total=0,
    )
    documents = fetch_fdrs_documents_api(base_url, api_key, years=years)
    plan, summary = build_document_import_plan(documents, assignment_rows, sync_years=years)
    planned = int(summary.get("planned") or 0)
    _progress(
        stage="documents_plan",
        message=f"FDRS documents: {planned} records to sync (metadata + file download when available)",
        percent=progress_start_pct,
        current=0,
        total=planned,
        extra={"documents_summary": summary},
    )
    doc_stats = upsert_fdrs_document_metadata(
        plan,
        uploaded_by_user_id=uploaded_by_user_id,
        dry_run=dry_run,
        batch_size=batch_size,
        progress_cb=progress_cb,
        cancel_check=cancel_check,
        progress_start_pct=progress_start_pct,
        progress_end_pct=progress_end_pct,
    )
    _progress(
        stage="documents_done",
        message=_format_documents_done_message(doc_stats),
        percent=progress_end_pct,
        current=planned,
        total=planned,
        extra={"documents_stats": doc_stats},
    )
    return {"documents_summary": summary, "documents_stats": doc_stats}
