"""
Export all FDRS document URLs with HTTP probe status to Excel.

Works in this repo or as a single copied file (no Backoffice app required).

Standalone:
    pip install pandas openpyxl
    python export_fdrs_document_url_status.py --api-key YOUR_KEY

In Backoffice (reads FDRS_DATA_API_KEY from env / .env):
    python scripts/dev/export_fdrs_document_url_status.py
    python scripts/dev/export_fdrs_document_url_status.py --limit 50

Also reports Backoffice migration status when run with a Flask app context:
whether each catalog document exists as a SubmittedDocument (``fdrs_import_key``)
and whether file bytes were downloaded (``file_pending`` / ``storage_path``).

On HTTP 403/404, retries once without a trailing _1 / _2 filename suffix
(the API catalog sometimes includes a suffix the file store does not).
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/")
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


def _json_get(url: str, *, timeout: int) -> Any:
    req = urllib.request.Request(
        url, headers={"User-Agent": "HumanitarianDatabank-FDRS-url-export/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_country_map(base_url: str, api_key: str) -> Dict[str, str]:
    qs = urllib.parse.urlencode({"apiKey": api_key})
    url = f"{base_url.rstrip('/')}/api/entities/ns?{qs}"
    try:
        data = _json_get(url, timeout=120)
    except Exception as e:
        print(f"Warning: country map failed ({type(e).__name__}); ISO3 may be blank.", flush=True)
        return {}
    rows = data if isinstance(data, list) else []
    out: Dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        don = (row.get("KPI_DON_code") or row.get("DonCode") or "").strip()
        iso3 = (row.get("iso_3") or row.get("ISO3") or "").strip()
        if don:
            out[don] = iso3
    return out


def fetch_fdrs_documents(base_url: str, api_key: str) -> List[Dict[str, Any]]:
    print("Fetching FDRS document catalog...", flush=True)
    qs = urllib.parse.urlencode(
        {"apiKey": api_key, "showunpublished": "true", "force": "true"}
    )
    url = f"{base_url.rstrip('/')}/api/documents?{qs}"
    payload = _json_get(url, timeout=180)
    if not isinstance(payload, list):
        raise SystemExit("Unexpected documents API response (not a list).")
    don_to_iso = _fetch_country_map(base_url, api_key)
    flat: List[Dict[str, Any]] = []
    for ns_block in payload:
        if not isinstance(ns_block, dict):
            continue
        don_code = (ns_block.get("code") or "").strip()
        iso3 = don_to_iso.get(don_code, "")
        for doc in ns_block.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            rec = dict(doc)
            rec["don_code"] = don_code
            rec["iso3"] = iso3
            flat.append(rec)
    print(f"Loaded {len(flat)} documents.", flush=True)
    return flat


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
        alt = url_without_duplicate_suffix(url)
        if alt:
            fallback_url = alt
            fb_status, fb_detail = probe_url(alt)
            fallback_http_status = fb_status
            if fb_status in (200, 206):
                status, detail = fb_status, fb_detail
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


def execute_document_url_status_scan(
    *,
    output_path: str,
    api_key: Optional[str] = None,
    base_url: str = DEFAULT_BASE,
    workers: int = 20,
    limit: Optional[int] = None,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """Probe the FDRS document catalog and write the status Excel.

    Returns a stats dict (total_documents, downloadable_count, …). Raises
    ``FdrsDocumentScanCancelled`` when *cancel_check* returns True.
    """
    import pandas as pd

    def _progress(payload: Dict[str, Any]) -> None:
        if progress_cb:
            progress_cb(payload)

    def _cancelled() -> bool:
        return bool(cancel_check and cancel_check())

    if _cancelled():
        raise FdrsDocumentScanCancelled()

    key = _load_api_key(api_key)
    _progress({"stage": "fetch_catalog", "message": "Fetching FDRS document catalog...", "percent": 2.0})
    documents = fetch_fdrs_documents(base_url, key)
    if limit is not None:
        documents = documents[: int(limit)]

    total = len(documents)
    if total == 0:
        raise RuntimeError("No documents returned from FDRS API.")

    rows: List[Optional[Dict[str, Any]]] = [None] * total
    done = 0
    workers = max(1, min(int(workers), 64))

    _progress({
        "stage": "probe",
        "message": f"Probing {total} document URLs...",
        "current": 0,
        "total": total,
        "percent": 5.0,
    })

    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {pool.submit(_probe_row, doc): i for i, doc in enumerate(documents)}
        for fut in as_completed(futures):
            if _cancelled():
                raise FdrsDocumentScanCancelled()
            idx = futures[fut]
            rows[idx] = fut.result()
            done += 1
            if done == 1 or done % 50 == 0 or done == total:
                pct = 5.0 + (90.0 * done / total) if total else 95.0
                _progress({
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

    if _cancelled():
        raise FdrsDocumentScanCancelled()

    assert all(r is not None for r in rows)
    typed_rows: List[Dict[str, Any]] = list(rows)  # type: ignore[arg-type]

    if _cancelled():
        raise FdrsDocumentScanCancelled()

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
        if whole <= 0:
            return "0.0%"
        return f"{100.0 * part / whole:.1f}%"

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
            f"(not migrated={migration_counts['not_migrated_count']}/{total})",
            flush=True,
        )
    else:
        print("Backoffice migration: skipped (no Flask app context).", flush=True)

    if _cancelled():
        raise FdrsDocumentScanCancelled()

    _progress({"stage": "write_excel", "message": "Writing Excel...", "percent": 96.0, "current": total, "total": total})
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    scanned_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

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
                    "pct_of_total": round(100.0 * count_i / total, 1) if total else 0.0,
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
                        "pct_of_total": round(100.0 * count_i / total, 1) if total else 0.0,
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
            {"key": "total_documents", "value": total},
            {"key": "downloadable_count", "value": ok},
            {"key": "file_migrated_count", "value": migration_counts.get("file_migrated_count", "")},
            {"key": "pending_download_count", "value": migration_counts.get("pending_download_count", "")},
            {"key": "not_in_backoffice_count", "value": migration_counts.get("not_in_backoffice_count", "")},
            {"key": "not_migrated_count", "value": migration_counts.get("not_migrated_count", "")},
            {
                "key": "migration_lookup_available",
                "value": bool(migration_counts.get("migration_lookup_available")),
            },
            {"key": "http_403_public_unexpected", "value": pub403},
            {"key": "http_403_public_unexpected_pct", "value": round(100.0 * pub403 / n403, 1) if n403 else 0.0},
            {"key": "http_403_private_expected", "value": priv403},
            {"key": "http_403_private_expected_pct", "value": round(100.0 * priv403 / n403, 1) if n403 else 0.0},
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
        "total_documents": total,
        "downloadable_count": ok,
        "file_migrated_count": int(migration_counts.get("file_migrated_count") or 0),
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
) -> str:
    execute_document_url_status_scan(
        output_path=output_path,
        api_key=api_key,
        base_url=base_url,
        workers=workers,
        limit=limit,
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export FDRS document URL HTTP status to Excel.",
        epilog=(
            "Standalone:  python export_fdrs_document_url_status.py --api-key YOUR_KEY\n"
            "Backoffice:  python scripts/dev/export_fdrs_document_url_status.py"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help="Output .xlsx path")
    parser.add_argument("--api-key", default=None, help="FDRS data API key (default: env / .env)")
    parser.add_argument("--base-url", default=DEFAULT_BASE, help="FDRS data API base URL")
    parser.add_argument("--workers", type=int, default=20, help="Concurrent probe workers")
    parser.add_argument("--limit", type=int, default=None, help="Probe only first N documents (testing)")
    args = parser.parse_args()
    try:
        export_url_status_excel(
            output_path=args.output,
            api_key=args.api_key,
            base_url=args.base_url,
            workers=args.workers,
            limit=args.limit,
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
