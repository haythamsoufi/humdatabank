"""
FDRS documents API → SubmittedDocument metadata import (files deferred until IFRC fixes URLs).

GET https://data-api.ifrc.org/api/documents?apiKey=...&showunpublished=true&force=true[&year=YYYY]
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from fdrs_sync_constants import (
    FDRS_DOCUMENT_APPROVAL_OK,
    FDRS_DOCUMENT_PUBLIC_OK,
    FDRS_DOCUMENT_TYPE_TO_CONFIG_LABEL,
    FDRS_DOCUMENT_TYPE_TO_ITEM,
    fdrs_document_status_from_approval,
)

logger = logging.getLogger(__name__)

DEFAULT_DOCUMENTS_PATH = "/api/documents"
_YEAR_IN_TEXT_RE = re.compile(r"\b(20\d{2})\b")


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
    approval_rank = 2 if approval == "Validated (Public)" else 1 if approval in FDRS_DOCUMENT_APPROVAL_OK else 0
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
        try:
            is_public = int(doc.get("Public") or 0) == 1
        except (TypeError, ValueError):
            is_public = False
        approval_status = (doc.get("ApprovalStatus") or "").strip()
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
                "status": fdrs_document_status_from_approval(approval_status),
                "modified_at": doc.get("ModifiedAt"),
                "file_pending": True,
            }
        )
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


def upsert_fdrs_document_metadata(
    plan_rows: List[Dict[str, Any]],
    *,
    uploaded_by_user_id: int,
    dry_run: bool = False,
    batch_size: int = 500,
) -> Dict[str, int]:
    """Insert or update SubmittedDocument rows (metadata + source_url; no file bytes)."""
    from app.extensions import db
    from app.models.documents import SubmittedDocument
    from app.models.enums import DocumentStatusValue

    stats = {"loaded": len(plan_rows), "inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
    if not plan_rows:
        return stats

    keys = [r["fdrs_import_key"] for r in plan_rows if r.get("fdrs_import_key")]
    existing_by_key: Dict[str, SubmittedDocument] = {}
    if keys:
        for doc in SubmittedDocument.query.filter(SubmittedDocument.fdrs_import_key.in_(keys)).all():
            if doc.fdrs_import_key:
                existing_by_key[doc.fdrs_import_key] = doc

    for i, row in enumerate(plan_rows, start=1):
        import_key = row.get("fdrs_import_key")
        if not import_key:
            stats["skipped"] += 1
            continue
        try:
            existing = existing_by_key.get(import_key)
            modified_at = _parse_fdrs_modified_at(row.get("modified_at"))
            from app.utils.datetime_helpers import utcnow

            uploaded_at = modified_at or utcnow()
            if dry_run:
                if existing:
                    stats["updated"] += 1
                else:
                    stats["inserted"] += 1
                continue

            doc_status = DocumentStatusValue.normalize(
                row.get("status")
                or fdrs_document_status_from_approval(row.get("approval_status"))
            )

            if existing:
                existing.filename = row["filename"]
                existing.source_url = row.get("source_url")
                existing.thumbnail_source_url = row.get("thumbnail_url")
                existing.language = row.get("language")
                existing.document_type = row.get("document_type")
                existing.period = row.get("period")
                existing.is_public = bool(row.get("is_public"))
                existing.status = doc_status
                existing.file_pending = True
                if modified_at:
                    existing.uploaded_at = modified_at
                db.session.add(existing)
                stats["updated"] += 1
            else:
                entry = SubmittedDocument(
                    assignment_entity_status_id=int(row["assignment_entity_status_id"]),
                    form_item_id=int(row["form_item_id"]),
                    filename=row["filename"],
                    storage_path=None,
                    source_url=row.get("source_url"),
                    thumbnail_source_url=row.get("thumbnail_url"),
                    uploaded_at=uploaded_at,
                    uploaded_by_user_id=uploaded_by_user_id,
                    language=row.get("language"),
                    document_type=row.get("document_type"),
                    period=row.get("period"),
                    is_public=bool(row.get("is_public")),
                    fdrs_import_key=import_key,
                    file_pending=True,
                    status=doc_status,
                )
                db.session.add(entry)
                existing_by_key[import_key] = entry
                stats["inserted"] += 1

            if batch_size and i % batch_size == 0:
                db.session.commit()
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
) -> Dict[str, Any]:
    def _progress(**kwargs: Any) -> None:
        if progress_cb:
            try:
                progress_cb(kwargs)
            except Exception as e:
                logger.debug("documents progress_cb failed: %s", e)

    _progress(stage="fetch_documents", message="Fetching FDRS documents API...", percent=90.0)
    documents = fetch_fdrs_documents_api(base_url, api_key, years=years)
    plan, summary = build_document_import_plan(documents, assignment_rows, sync_years=years)
    _progress(
        stage="documents_plan",
        message=f"FDRS documents planned: {summary.get('planned', 0)}",
        percent=92.0,
        extra={"documents_summary": summary},
    )
    doc_stats = upsert_fdrs_document_metadata(
        plan,
        uploaded_by_user_id=uploaded_by_user_id,
        dry_run=dry_run,
        batch_size=batch_size,
    )
    return {"documents_summary": summary, "documents_stats": doc_stats}
